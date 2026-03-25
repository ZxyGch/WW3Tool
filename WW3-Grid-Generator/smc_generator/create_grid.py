#!/usr/bin/env python3
"""
Generate SMC grid data files from grid.json (or path via --config / --grid).

Final outputs in output_dir (smcellgen/smcellbdy write to a temp stem, then rename):

- grid_cell.dat — SMC inner cells (from *Cels.dat)
- grid_boundary.dat — regional open-boundary strip (from *Bdys.dat), only if
  grid.global is false and boundary.generate_boundary_cells is true
- grid_arctic_cells.dat — Arctic partition (from *BArc.dat), only if
  grid.global is true and grid.arctic is true
- grid_run_info.json — run metadata (paths, resolution, variables)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

OUT_CELL_NAME = "grid_cell.dat"
OUT_BOUNDARY_NAME = "grid_boundary.dat"
OUT_ARCTIC_NAME = "grid_arctic_cells.dat"
OUT_RUN_INFO_NAME = "grid_run_info.json"
WORK_STEM_NAME = "_smc_generate_tmp"

import numpy as np


def _require_dependencies() -> None:
    missing = []
    try:
        import netCDF4  # noqa: F401
    except Exception:
        missing.append("netCDF4")

    try:
        import pandas  # noqa: F401
    except Exception:
        missing.append("pandas")

    if missing:
        names = ", ".join(missing)
        install_names = " ".join(missing)
        raise SystemExit(
            "Missing Python dependencies: "
            f"{names}\nInstall with: python3 -m pip install {install_names}"
        )


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_path(base: Path, value: str) -> Path:
    p = Path(value)
    if not p.is_absolute():
        p = (base / p).resolve()
    return p


def _pick_var(
    variables: dict[str, Any],
    configured: Any,
    candidates: list[str],
    label: str,
) -> str:
    if isinstance(configured, str) and configured:
        if configured not in variables:
            raise SystemExit(
                f"Configured {label} variable '{configured}' not found."
            )
        return configured

    for name in candidates:
        if name in variables:
            return name

    raise SystemExit(
        f"Could not auto-detect {label} variable. "
        f"Please set it explicitly in grid.json."
    )


def _regular_step(
    axis: np.ndarray,
    axis_name: str,
    *,
    rtol: float = 1.0e-4,
    atol: float = 1.0e-8,
) -> float:
    if axis.ndim != 1:
        raise SystemExit(f"{axis_name} axis must be 1D.")
    if axis.size < 2:
        raise SystemExit(f"{axis_name} axis length must be >= 2.")

    diffs = np.diff(axis)
    if np.any(diffs <= 0.0):
        raise SystemExit(
            f"{axis_name} axis must be strictly increasing after auto-flip."
        )
    step = float(np.median(diffs))
    if not np.all(np.isfinite(diffs)):
        raise SystemExit(f"{axis_name} axis contains non-finite values.")
    if not np.allclose(diffs, step, rtol=rtol, atol=atol):
        raise SystemExit(
            f"{axis_name} axis is not regularly spaced. "
            "SMCGTools requires regular lon/lat spacing."
        )
    return step


def _to_2d_bathy(var_data: np.ndarray) -> np.ndarray:
    arr = np.asarray(var_data, dtype=float).squeeze()
    if arr.ndim != 2:
        raise SystemExit(
            f"Bathymetry variable must be 2D after squeeze, got shape {arr.shape}"
        )
    return arr


def _pysmcs_dir(script_dir: Path) -> Path:
    for candidate in (script_dir / "PySMCs", script_dir / "SMCGTools" / "PySMCs"):
        if (candidate / "smcellgen.py").is_file():
            return candidate
    return script_dir / "PySMCs"


def _read_alias_float(mapping: dict[str, Any], aliases: list[str], label: str) -> float:
    for key in aliases:
        if key in mapping and mapping[key] is not None:
            return float(mapping[key])
    raise SystemExit(
        f"Missing '{label}'. Supported keys: {', '.join(aliases)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate SMC grid files from grid.json."
    )
    parser.add_argument(
        "-c",
        "--config",
        "--grid",
        default="grid.json",
        dest="config",
        help="Path to grid JSON (default: ./grid.json)",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    config_path = _resolve_path(script_dir, args.config)
    config = _load_json(config_path)

    _require_dependencies()
    import netCDF4 as nc

    pysmcs_dir = _pysmcs_dir(script_dir)
    if str(pysmcs_dir) not in sys.path:
        sys.path.insert(0, str(pysmcs_dir))

    from smcellbdy import smcellbdy
    from smcellgen import smcellgen

    input_cfg = config["input"]
    grid_cfg = config["grid"]
    physics_cfg = config["physics"]
    boundary_cfg = config["boundary"]
    output_cfg = config["output"]

    bathy_path = _resolve_path(config_path.parent, input_cfg["bathymetry_file"])
    if not bathy_path.exists():
        raise SystemExit(f"Bathymetry file not found: {bathy_path}")

    with nc.Dataset(str(bathy_path), "r") as ds:
        lon_var = _pick_var(
            ds.variables,
            input_cfg.get("lon_var"),
            ["lon", "longitude", "x", "LON", "XLONG"],
            "longitude",
        )
        lat_var = _pick_var(
            ds.variables,
            input_cfg.get("lat_var"),
            ["lat", "latitude", "y", "LAT", "XLAT"],
            "latitude",
        )
        bathy_var = _pick_var(
            ds.variables,
            input_cfg.get("bathy_var"),
            ["elevation", "z", "depth", "bathymetry", "Bathymetry"],
            "bathymetry",
        )

        lon = np.asarray(ds.variables[lon_var][:], dtype=float).squeeze()
        lat = np.asarray(ds.variables[lat_var][:], dtype=float).squeeze()
        bathy = _to_2d_bathy(ds.variables[bathy_var][:])

    if lon.ndim != 1 or lat.ndim != 1:
        raise SystemExit("This script supports 1D lon/lat axes only.")

    if bathy.shape == (lon.size, lat.size):
        bathy = bathy.T
    if bathy.shape != (lat.size, lon.size):
        raise SystemExit(
            f"Bathymetry shape {bathy.shape} does not match "
            f"(lat, lon)=({lat.size}, {lon.size})."
        )

    if bool(input_cfg.get("auto_flip_lat", True)) and lat[0] > lat[-1]:
        lat = lat[::-1]
        bathy = bathy[::-1, :]

    if bool(input_cfg.get("auto_flip_lon", True)) and lon[0] > lon[-1]:
        lon = lon[::-1]
        bathy = bathy[:, ::-1]

    spacing_rtol = float(input_cfg.get("coord_spacing_rtol", 1.0e-4))
    spacing_atol = float(input_cfg.get("coord_spacing_atol", 1.0e-8))
    dlon = _regular_step(
        lon,
        "Longitude",
        rtol=spacing_rtol,
        atol=spacing_atol,
    )
    dlat = _regular_step(
        lat,
        "Latitude",
        rtol=spacing_rtol,
        atol=spacing_atol,
    )
    if dlon <= 0.0 or dlat <= 0.0:
        raise SystemExit("Longitude/Latitude spacing must be positive after flipping.")

    convention = str(input_cfg.get("bathy_convention", "elevation")).lower()
    if convention == "elevation":
        bathy_elev = bathy
    elif convention in {"depth", "depth_positive_down", "positive_down"}:
        bathy_elev = -bathy
    else:
        raise SystemExit(
            "input.bathy_convention must be one of: "
            "'elevation', 'depth', 'depth_positive_down', 'positive_down'."
        )

    depmin = float(physics_cfg.get("depmin", 0.0))
    nan_fill = float(input_cfg.get("nan_fill_value", depmin + 1.0))
    bathy_elev = np.nan_to_num(
        bathy_elev,
        nan=nan_fill,
        posinf=nan_fill,
        neginf=depmin - 1000.0,
    )

    n_levels = int(grid_cfg["n_levels"])
    global_grid = bool(grid_cfg.get("global", True))
    arctic_grid = bool(grid_cfg.get("arctic", False))
    arc_lat = float(grid_cfg.get("glb_arc_lat", 84.4))
    origin_cfg = grid_cfg["origin"]
    x0lon = _read_alias_float(origin_cfg, ["x0lon", "lon0"], "origin longitude")
    y0lat = _read_alias_float(origin_cfg, ["y0lat", "lat0"], "origin latitude")

    mlvlxy0 = [n_levels, x0lon, y0lat]
    if not global_grid:
        bounds = grid_cfg.get("regional_bounds")
        if not isinstance(bounds, dict):
            raise SystemExit(
                "regional_bounds must be set when grid.global is false."
            )
        west_lon = _read_alias_float(
            bounds,
            ["west_lon", "xstart", "lon_min", "min_lon"],
            "regional west longitude",
        )
        south_lat = _read_alias_float(
            bounds,
            ["south_lat", "ystart", "lat_min", "min_lat"],
            "regional south latitude",
        )
        east_lon = _read_alias_float(
            bounds,
            ["east_lon", "xend", "lon_max", "max_lon"],
            "regional east longitude",
        )
        north_lat = _read_alias_float(
            bounds,
            ["north_lat", "yend", "lat_max", "max_lat"],
            "regional north latitude",
        )

        mlvlxy0.extend(
            [
                west_lon,
                south_lat,
                east_lon,
                north_lat,
            ]
        )

    ndzlonlat = [int(lon.size), int(lat.size), float(dlon), float(dlat), float(lon[0]), float(lat[0])]

    out_dir = _resolve_path(config_path.parent, output_cfg.get("output_dir", "./output"))
    out_dir.mkdir(parents=True, exist_ok=True)
    work_stem = out_dir / WORK_STEM_NAME
    work_prefix = str(work_stem)

    cells_tmp = Path(work_prefix + "Cels.dat")
    bdys_tmp = Path(work_prefix + "Bdys.dat")
    barc_tmp = Path(work_prefix + "BArc.dat")
    final_cell = out_dir / OUT_CELL_NAME
    final_boundary = out_dir / OUT_BOUNDARY_NAME
    final_arctic = out_dir / OUT_ARCTIC_NAME
    run_info_file = out_dir / OUT_RUN_INFO_NAME

    for p in (cells_tmp, bdys_tmp, barc_tmp):
        try:
            if p.is_file():
                p.unlink()
        except OSError:
            pass

    wlevel = float(physics_cfg.get("wlevel", 0.0))
    dshalw = float(physics_cfg.get("dshalw", 0.0))

    print(f"Generating cells (temp {cells_tmp.name}) → {final_cell.name}")
    smcellgen(
        bathy_elev,
        ndzlonlat,
        mlvlxy0,
        FileNm=work_prefix,
        Global=global_grid,
        Arctic=arctic_grid,
        depmin=depmin,
        dshalw=dshalw,
        wlevel=wlevel,
        GlbArcLat=arc_lat,
    )

    if not cells_tmp.is_file():
        raise SystemExit(f"Expected cell file not created: {cells_tmp}")

    generate_bdy = bool(boundary_cfg.get("generate_boundary_cells", True))
    msea = int(boundary_cfg.get("msea", 1))
    bdy_written = False
    if generate_bdy and not global_grid:
        print(f"Generating boundaries (temp {bdys_tmp.name}) → {final_boundary.name}")
        smcellbdy(
            bathy_elev,
            ndzlonlat,
            mlvlxy0,
            FileNm=work_prefix,
            Global=global_grid,
            Arctic=arctic_grid,
            depmin=depmin,
            dshalw=dshalw,
            wlevel=wlevel,
            msea=msea,
            GlbArcLat=arc_lat,
        )
        if not bdys_tmp.is_file():
            raise SystemExit(f"Expected boundary file not created: {bdys_tmp}")
        bdy_written = True

    os.replace(cells_tmp, final_cell)

    arctic_written = bool(barc_tmp.is_file())
    if arctic_written:
        os.replace(barc_tmp, final_arctic)

    if bdy_written:
        os.replace(bdys_tmp, final_boundary)

    run_info = {
        "grid_name": str(grid_cfg["name"]),
        "config_path": str(config_path),
        "bathymetry_file": str(bathy_path),
        "lon_var": lon_var,
        "lat_var": lat_var,
        "bathy_var": bathy_var,
        "nlon": int(lon.size),
        "nlat": int(lat.size),
        "dlon": float(dlon),
        "dlat": float(dlat),
        "output_dir": str(out_dir),
        "cells_file": str(final_cell),
        "boundary_file": str(final_boundary) if bdy_written else None,
        "arctic_cells_file": str(final_arctic) if arctic_written else None,
    }
    run_info_file.write_text(json.dumps(run_info, indent=2), encoding="utf-8")
    print(f"Wrote run metadata: {run_info_file}")


if __name__ == "__main__":
    main()
