#!/usr/bin/env python3
"""Read grid.json / grid.yaml / INI and run NOAA unst_msh_gen (ocn_ww3.py) to build an unstructured WW3 mesh."""

from __future__ import annotations

import argparse
import configparser
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Read grid config and invoke unst_msh_gen/ocn_ww3.py."
    )
    p.add_argument(
        "--grid",
        "--grid-info",
        type=Path,
        default=None,
        dest="grid_config",
        help=(
            "Path to grid.json, grid.yaml / .yml, or .ini / .info (default: grid.json if present, "
            "then yaml / yml / ini / info)."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Only write the resolved ini under unst_msh_gen; do not run mesh generation.",
    )
    return p.parse_args()


def _import_yaml():
    try:
        import yaml
    except ImportError:
        sys.exit(
            "Reading grid.yaml requires PyYAML on THIS Python:\n"
            f"  {sys.executable} -m pip install pyyaml\n"
            "Bare `pip install` may use a different Python (e.g. /Library/Frameworks vs /opt/homebrew).\n"
            "If pip reports externally-managed-environment, use a venv, then pip install pyyaml inside it."
        )
    return yaml


def _value_to_ini_str(val) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        return str(int(val)) if val.is_integer() else repr(val)
    if isinstance(val, str):
        return val
    return json.dumps(val, separators=(",", ":"))


def _dict_to_configparser(data: dict) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    for section, body in data.items():
        skey = str(section)
        if skey.startswith("_"):
            continue
        if not isinstance(body, dict):
            continue
        sect = skey
        if not cfg.has_section(sect):
            cfg.add_section(sect)
        for key, val in body.items():
            if str(key).startswith("_"):
                continue
            if val is None:
                continue
            if isinstance(val, list) and str(key) == "shape_file":
                norm = []
                for item in val:
                    if isinstance(item, dict):
                        norm.append(
                            {
                                "path": item.get("path", ""),
                                "scale": item.get("scale", 1),
                            }
                        )
                    else:
                        norm.append(item)
                val = json.dumps(norm, separators=(",", ":"))
            cfg.set(sect, str(key), _value_to_ini_str(val))
    return cfg


def _read_user_grid(path: Path) -> configparser.ConfigParser:
    suf = path.suffix.lower()
    if suf == ".json":
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not data or not isinstance(data, dict):
            sys.exit(f"Invalid or empty JSON: {path}")
        return _dict_to_configparser(data)
    if suf in (".yaml", ".yml"):
        yaml = _import_yaml()
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data or not isinstance(data, dict):
            sys.exit(f"Invalid or empty YAML: {path}")
        return _dict_to_configparser(data)
    cfg = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    if not cfg.read(path):
        sys.exit(f"Cannot read config: {path}")
    return cfg


def _default_grid_path(script_dir: Path) -> Path:
    for name in ("grid.json", "grid.yaml", "grid.yml", "grid.ini", "grid.info"):
        p = script_dir / name
        if p.is_file():
            return p
    return script_dir / "grid.json"


def _resolve_path(raw: str, base: Path) -> str:
    raw = raw.strip()
    if not raw:
        return raw
    path = Path(raw)
    if path.is_absolute():
        return str(path)
    return str((base / path).resolve())


def _resolve_dem_file(raw: str, grid_dir: Path) -> str:
    """
    Resolve DataFiles.dem_file. Relative paths are first resolved from the grid file's directory
    (e.g. Step 2 tmpdir); if the file is missing, try the same relative path from this script's
    directory (unstructured_generator/), so ../reference_data/... still works when grid.json lives
    outside the generator tree.
    """
    raw = raw.strip()
    if not raw:
        return raw
    path = Path(raw)
    if path.is_absolute():
        return str(path)
    primary = (grid_dir / path).resolve()
    if primary.is_file():
        return str(primary)
    alt = (Path(__file__).resolve().parent / path).resolve()
    if alt.is_file():
        return str(alt)
    return str(primary)


def _maybe_resolve_shape_file(value: str, base: Path) -> str:
    value = value.strip()
    if not value:
        return value
    data = json.loads(value)
    if not isinstance(data, list):
        return value
    for item in data:
        if isinstance(item, dict) and "path" in item:
            item["path"] = _resolve_path(str(item["path"]), base)
    return json.dumps(data, separators=(",", ":"))


def _prepare_config(grid_config_path: Path) -> tuple[configparser.ConfigParser, Path, Path]:
    grid_dir = grid_config_path.resolve().parent
    cfg = _read_user_grid(grid_config_path)

    if not cfg.has_section("Workflow"):
        cfg.add_section("Workflow")

    unst_rel = cfg.get("Workflow", "unst_msh_gen_dir", fallback="unst_msh_gen").strip()
    unst_candidate = Path(unst_rel)
    unst_dir = (
        unst_candidate.resolve()
        if unst_candidate.is_absolute()
        else (grid_dir / unst_rel).resolve()
    )
    if not unst_dir.is_dir():
        sys.exit(f"unst_msh_gen directory not found: {unst_dir}")

    mesh_base = unst_dir
    if cfg.has_section("Output"):
        mws = cfg.get("Output", "mesh_workspace_dir", fallback="").strip()
        if mws:
            mesh_base = Path(_resolve_path(mws, grid_dir))

    resolved_name = Path(
        cfg.get("Workflow", "resolved_config_name", fallback=".grid_run.ini")
    ).name

    if cfg.has_option("DataFiles", "dem_file"):
        v = cfg.get("DataFiles", "dem_file")
        cfg.set("DataFiles", "dem_file", _resolve_dem_file(v, grid_dir))

    if cfg.has_option("DataFiles", "shape_file"):
        v = cfg.get("DataFiles", "shape_file")
        if v.strip():
            cfg.set("DataFiles", "shape_file", _maybe_resolve_shape_file(v, grid_dir))

    mesh_base_path = mesh_base if isinstance(mesh_base, Path) else Path(mesh_base)
    for sec, opt, base in (
        ("CommandLineArgs", "mask_file", mesh_base_path),
        ("MeshSettings", "mesh_file", mesh_base_path),
        ("MeshSettings", "ww3_mesh_file", mesh_base_path),
    ):
        if cfg.has_option(sec, opt):
            v = cfg.get(sec, opt)
            if v.strip():
                b = base if isinstance(base, Path) else Path(base)
                cfg.set(sec, opt, _resolve_path(v, b))

    # Write resolved INI next to the grid config (e.g. tmpdir for WW3Tool), not under unst_msh_gen.
    out_ini = grid_dir / resolved_name
    return cfg, unst_dir, out_ini


def _write_resolved_config(cfg: configparser.ConfigParser, out_ini: Path) -> None:
    with out_ini.open("w", encoding="utf-8") as f:
        cfg.write(f)


def _subprocess_env(
    cfg: configparser.ConfigParser,
    grid_dir: Path,
    unst_dir: Path,
) -> dict[str, str]:
    """Ensure unst_msh_gen (spacing.py) and optional jigsaw-python are on PYTHONPATH."""
    env = os.environ.copy()
    prefixes: list[str] = [str(unst_dir)]
    if cfg.has_section("Workflow"):
        raw = cfg.get("Workflow", "jigsaw_python_root", fallback="").strip()
        if raw:
            root = Path(raw)
            if not root.is_absolute():
                root = (grid_dir / root).resolve()
            if not root.is_dir() or not (root / "jigsawpy").is_dir():
                sys.exit(
                    f"jigsaw_python_root is not a jigsaw-python repo root (need jigsawpy/): {root}"
                )
            prefixes.append(str(root))
    prev = env.get("PYTHONPATH", "")
    ordered: list[str] = []
    seen: set[str] = set()
    for p in prefixes + ([prev] if prev else []):
        for part in p.split(os.pathsep):
            if part and part not in seen:
                seen.add(part)
                ordered.append(part)
    env["PYTHONPATH"] = os.pathsep.join(ordered)
    return env


def _resolve_jigsaw_python_root(
    cfg: configparser.ConfigParser, grid_dir: Path
) -> Path:
    """jigsawpy lives under jigsaw-python/; must be on sys.path before regional_mesh imports spacing/ocn_ww3."""
    default = Path(__file__).resolve().parent / "jigsaw-python"
    if not cfg.has_section("Workflow"):
        if default.is_dir() and (default / "jigsawpy").is_dir():
            return default
        sys.exit(
            f"Cannot find jigsaw-python (need jigsawpy/ subdir). Expected: {default}"
        )
    raw = cfg.get("Workflow", "jigsaw_python_root", fallback="").strip()
    if not raw:
        if default.is_dir() and (default / "jigsawpy").is_dir():
            return default
        sys.exit(
            "Set Workflow.jigsaw_python_root in the grid config, or place jigsaw-python "
            f"next to create_grid.py ({default})."
        )
    root = Path(raw)
    if not root.is_absolute():
        root = (grid_dir / root).resolve()
    else:
        root = root.resolve()
    if not root.is_dir() or not (root / "jigsawpy").is_dir():
        sys.exit(
            f"jigsaw_python_root is not a jigsaw-python repo root (need jigsawpy/): {root}"
        )
    return root


def _run_cwd(cfg: configparser.ConfigParser, grid_dir: Path, unst_dir: Path) -> Path:
    if cfg.has_section("Output"):
        mws = cfg.get("Output", "mesh_workspace_dir", fallback="").strip()
        if mws:
            return Path(_resolve_path(mws, grid_dir))
    return unst_dir


def _validate_domain_zoom(cfg: configparser.ConfigParser) -> None:
    if not cfg.has_section("Domain"):
        return
    clip = cfg.getboolean("Domain", "clip_to_bounds", fallback=False)
    if not clip:
        return
    west = float(cfg.get("Domain", "west_lon", fallback="-180"))
    east = float(cfg.get("Domain", "east_lon", fallback="180"))
    south = float(cfg.get("Domain", "south_lat", fallback="-90"))
    north = float(cfg.get("Domain", "north_lat", fallback="90"))
    if south >= north:
        sys.exit("grid config [Domain]: require south_lat < north_lat")
    if west >= east:
        sys.exit(
            "grid config [Domain]: require west_lon < east_lon (same lon convention as DEM; "
            "straddling the dateline is not supported here)"
        )

    mask = cfg.get("CommandLineArgs", "mask_file", fallback="").strip()
    if mask:
        print(
            "Warning: clip_to_bounds=true with mask_file requires wmask.nc to match "
            "the clipped grid shape; regenerate wmask from a cropped DEM window_mask.",
            file=sys.stderr,
        )


def _config_is_regional(cfg: configparser.ConfigParser) -> bool:
    if not cfg.has_section("Regional"):
        return False
    need = ("lon_min", "lon_max", "lat_min", "lat_max", "stereo_lon", "stereo_lat")
    return all(cfg.has_option("Regional", k) for k in need)


def _nc_var_dtype(arr: np.ndarray) -> str:
    if arr.dtype == np.float32:
        return "f4"
    if arr.dtype == np.float64:
        return "f8"
    return "f8"


def _write_clipped_dem_nc(
    src: str,
    west: float,
    east: float,
    south: float,
    north: float,
    dest: Path,
) -> None:
    """Subset NWS/RTopo-style bathy NetCDF (lon, lat, bed_elevation [, ice_thickness]) to a lat–lon box."""
    try:
        from netCDF4 import Dataset
    except ImportError:
        sys.exit(
            "clip_to_bounds requires netCDF4. Run:\n"
            f"  {sys.executable} -m pip install netCDF4"
        )

    with Dataset(src, "r") as ds_in:
        if "lon" not in ds_in.variables or "lat" not in ds_in.variables:
            sys.exit("clip_to_bounds: DEM must contain lon and lat variables")
        if "bed_elevation" not in ds_in.variables:
            sys.exit("clip_to_bounds: DEM must contain bed_elevation")
        lon = np.asarray(ds_in["lon"][:]).ravel()
        lat = np.asarray(ds_in["lat"][:]).ravel()
        elev = np.asarray(ds_in["bed_elevation"][:])
        if "ice_thickness" in ds_in.variables:
            ice = np.asarray(ds_in["ice_thickness"][:])
        else:
            ice = np.zeros_like(elev)

        ilon = np.where((lon >= west) & (lon <= east))[0]
        ilat = np.where((lat >= south) & (lat <= north))[0]
        if ilon.size < 2 or ilat.size < 2:
            sys.exit(
                f"clip_to_bounds: selection has too few points (lon={ilon.size}, lat={ilat.size}). "
                "Widen bounds or check DEM / lon–lat convention."
            )

        if elev.shape == (len(lat), len(lon)):
            elev_c = elev[np.ix_(ilat, ilon)]
            ice_c = ice[np.ix_(ilat, ilon)]
            lon_c, lat_c = lon[ilon], lat[ilat]
        elif elev.shape == (len(lon), len(lat)):
            # Source is (lon, lat); ocn_ww3 expects bed_elevation (lat, lon).
            elev_c = elev[np.ix_(ilon, ilat)].T
            ice_c = ice[np.ix_(ilon, ilat)].T
            lon_c, lat_c = lon[ilon], lat[ilat]
        else:
            sys.exit(
                f"clip_to_bounds: bed_elevation shape {elev.shape} is not (nlat, nlon) or (nlon, nlat) "
                f"for lon length {len(lon)}, lat length {len(lat)}"
            )

    dest.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(str(dest), "w", format="NETCDF4") as ds_out:
        ds_out.createDimension("lon", int(lon_c.size))
        ds_out.createDimension("lat", int(lat_c.size))
        vlon = ds_out.createVariable("lon", "f8", ("lon",))
        vlat = ds_out.createVariable("lat", "f8", ("lat",))
        vb = ds_out.createVariable(
            "bed_elevation", _nc_var_dtype(elev_c), ("lat", "lon")
        )
        vi = ds_out.createVariable("ice_thickness", _nc_var_dtype(ice_c), ("lat", "lon"))
        vlon[:] = lon_c
        vlat[:] = lat_c
        vb[:, :] = elev_c
        vi[:, :] = ice_c


def _clip_dem_if_requested(
    cfg: configparser.ConfigParser,
    grid_dir: Path,
    run_dir: Path,
) -> None:
    """When [Domain] clip_to_bounds=true, replace DataFiles.dem_file with a cropped NetCDF in run_dir."""
    if not cfg.has_section("Domain"):
        return
    if not cfg.getboolean("Domain", "clip_to_bounds", fallback=False):
        return
    west = float(cfg.get("Domain", "west_lon", fallback="-180"))
    east = float(cfg.get("Domain", "east_lon", fallback="180"))
    south = float(cfg.get("Domain", "south_lat", fallback="-90"))
    north = float(cfg.get("Domain", "north_lat", fallback="90"))
    src = cfg.get("DataFiles", "dem_file", fallback="").strip()
    if not src:
        sys.exit("clip_to_bounds: DataFiles.dem_file is empty")
    if not Path(src).is_file():
        sys.exit(f"clip_to_bounds: DEM not found: {src}")
    dest = run_dir / "_clipped_dem.nc"
    print(
        f"clip_to_bounds: subsetting DEM [{west}, {east}] × [{south}, {north}] → {dest}",
        file=sys.stderr,
    )
    _write_clipped_dem_nc(src, west, east, south, north, dest)
    cfg.set("DataFiles", "dem_file", str(dest.resolve()))


def _print_unstructured_run_banner() -> None:
    """Match structured pygridgen/create_grid.py banner style (70 cols, right-aligned title)."""
    sys.stdout.flush()
    print("=" * 70, flush=True)
    title = "Unstructured Triangular Grid Generation By JIGSAW"
    print(" " * (70 - len(title)) + title, flush=True)
    print("=" * 70 + "\n", flush=True)


def main() -> None:
    args = _parse_args()
    script_dir = Path(__file__).resolve().parent
    grid_path = args.grid_config or _default_grid_path(script_dir)
    grid_path = grid_path.resolve()
    if not grid_path.is_file():
        sys.exit(
            f"No grid config found. Create grid.json (or grid.yaml / grid.ini) next to create_grid.py: {grid_path}"
        )

    _print_unstructured_run_banner()

    cfg, unst_dir, out_ini = _prepare_config(grid_path)
    _validate_domain_zoom(cfg)
    is_regional = _config_is_regional(cfg)

    if args.dry_run:
        _write_resolved_config(cfg, out_ini)
        run_dir = _run_cwd(cfg, grid_path.parent, unst_dir)
        extras = [f"run cwd → {run_dir.resolve()}"]
        if cfg.has_section("Domain") and cfg.getboolean(
            "Domain", "clip_to_bounds", fallback=False
        ):
            extras.append(
                "note: clip_to_bounds will subset DEM on full run (dry-run leaves dem_file unchanged)"
            )
        if cfg.has_section("Output"):
            pub = cfg.get("Output", "ww3_publish_dir", fallback="").strip()
            if pub:
                dest = Path(_resolve_path(pub, grid_path.parent))
                bn = (
                    cfg.get("Output", "ww3_publish_basename", fallback="grid.ww3").strip()
                    or "grid.ww3"
                )
                extras.append(f"publish ww3 → {dest.resolve() / Path(bn).name}")
        print(f"Wrote {out_ini}; " + "; ".join(extras), file=sys.stderr)
        return

    dem = cfg.get("DataFiles", "dem_file", fallback="").strip()
    if dem and not Path(dem).is_file():
        sys.exit(f"DEM file does not exist: {dem}")

    run_wm = False
    if cfg.has_section("Workflow"):
        run_wm = cfg.getboolean("Workflow", "run_window_mask", fallback=False)

    run_dir = _run_cwd(cfg, grid_path.parent, unst_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    if (
        cfg.has_section("Domain")
        and cfg.getboolean("Domain", "clip_to_bounds", fallback=False)
        and not is_regional
    ):
        _clip_dem_if_requested(cfg, grid_path.parent, run_dir)
        dem = cfg.get("DataFiles", "dem_file", fallback="").strip()
        if dem and not Path(dem).is_file():
            sys.exit(f"Clipped DEM not found: {dem}")

    _write_resolved_config(cfg, out_ini)

    config_arg = str(out_ini)
    py = sys.executable
    env = _subprocess_env(cfg, grid_path.parent, unst_dir)

    if run_wm:
        wm = unst_dir / "window_mask.py"
        if not wm.is_file():
            sys.exit(f"run_window_mask is true but missing: {wm}")
        print("Running window_mask.py ...", file=sys.stderr)
        subprocess.run(
            [py, str(wm), "--config", config_arg],
            cwd=str(run_dir),
            env=env,
            check=True,
        )

    if is_regional:
        # Regional pipeline ships next to create_grid (regional_mesh.py); does not modify unst_msh_gen.
        from regional_mesh import run_regional_from_config

        jig_root = _resolve_jigsaw_python_root(cfg, grid_path.parent)
        print("Running regional mesh (bundled regional_mesh) ...", file=sys.stderr)
        prev_cwd = os.getcwd()
        try:
            os.chdir(run_dir)
            run_regional_from_config(
                config_arg, unst_dir, jigsaw_python_root=jig_root
            )
        finally:
            os.chdir(prev_cwd)
    else:
        ocn = unst_dir / "ocn_ww3.py"
        if not ocn.is_file():
            sys.exit(f"ocn_ww3.py not found: {ocn}")

        print("Running ocn_ww3.py ...", file=sys.stderr)
        subprocess.run(
            [py, str(ocn), "--config", config_arg],
            cwd=str(run_dir),
            env=env,
            check=True,
        )

    if cfg.has_section("Output"):
        pub = cfg.get("Output", "ww3_publish_dir", fallback="").strip()
        if pub:
            dest_dir = Path(_resolve_path(pub, grid_path.parent))
            dest_dir.mkdir(parents=True, exist_ok=True)
            name = (
                cfg.get("Output", "ww3_publish_basename", fallback="grid.ww3").strip()
                or "grid.ww3"
            )
            name = Path(name).name
            src = Path(cfg.get("MeshSettings", "ww3_mesh_file", fallback=""))
            if not src.is_file():
                sys.exit(f"WW3 mesh not found for publish step: {src}")
            dest = dest_dir / name
            shutil.copy2(src, dest)
            print(f"Published WW3 mesh: {dest}", file=sys.stderr)


if __name__ == "__main__":
    main()
