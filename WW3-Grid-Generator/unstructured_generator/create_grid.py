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

# Regional stereographic mesh (merged from former regional_mesh.py).

import importlib
import importlib.util
import netCDF4 as nc
import numpy as np
from typing import Any


# jigsawpy: ``WW3_JIGSAW_PYTHON_ROOT`` or ``jigsaw-python`` next to this file, then site-packages / pip / GitHub source.

# Upstream Python bindings (source install when PyPI has no wheel for this Python).
_JIGSAW_PYTHON_GIT_PIP = "git+https://github.com/dengwirda/jigsaw-python.git"
jigsawpy = None  # type: ignore


# --- helpers (not present in stock spacing.py; kept here on purpose) ---


def _align_field_to_shape(arr: np.ndarray, shape: tuple, *, order: int = 1) -> np.ndarray:
    a = np.asarray(arr, dtype=float)
    if a.shape == shape:
        return a
    if a.ndim != 2 or len(shape) != 2:
        raise ValueError("_align_field_to_shape expects 2D array and (rows, cols) shape")
    from scipy.ndimage import zoom

    zr = shape[0] / a.shape[0]
    zc = shape[1] / a.shape[1]
    return zoom(a, (zr, zc), order=order)


def _apply_deep_ocean_hmax_floor(
    hmat, elev, land, hmax_km: float, depth_m: float = -300.0
):
    if hmax_km <= 0:
        return hmat
    el = np.asarray(elev, dtype=float)
    ld = np.asarray(land, dtype=bool)
    oc = ~ld
    deep = oc & (el < float(depth_m))
    if not np.any(deep):
        return hmat
    out = np.asarray(hmat, dtype=np.float32, copy=True)
    out[deep] = np.maximum(out[deep].astype(np.float64), float(hmax_km)).astype(np.float32)
    return out


def _repair_deep_ocean_spacing_after_harmonic(hmat, hmat_pre, elev, land, depth_m=-300.0):
    el = np.asarray(elev, dtype=float)
    oc = ~np.asarray(land, dtype=bool)
    deep = oc & (el < float(depth_m))
    if not np.any(deep):
        return hmat
    out = np.asarray(hmat, dtype=hmat.dtype, copy=True)
    pre = np.asarray(hmat_pre, dtype=hmat.dtype)
    out[deep] = np.maximum(out[deep], pre[deep])
    return out


class _MaskArgs:
    __slots__ = ("mask_file",)

    def __init__(self, path: str) -> None:
        self.mask_file = path


def _ensure_unst_on_path(unst_dir: Path) -> None:
    root = str(unst_dir.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)


def load_regional_config(path: str) -> dict[str, Any]:
    path = os.path.expanduser(path)
    cfg = configparser.ConfigParser()
    if not cfg.read(path):
        raise FileNotFoundError(f"Cannot read config: {path}")

    ww3 = cfg.get("MeshSettings", "ww3_mesh_file", fallback=None)
    if ww3 is None or not str(ww3).strip():
        ww3 = cfg.get("MeshSettings", "WW3_mesh_file", fallback="grid.ww3")

    base = {
        "mesh_file": cfg.get("MeshSettings", "mesh_file", fallback="grid.msh"),
        "ww3_mesh_file": str(ww3).strip() or "grid.ww3",
        "hfun_hmax": float(cfg.get("MeshSettings", "hfun_hmax", fallback="100")),
        "black_sea": cfg.getint("CommandLineArgs", "black_sea", fallback=3),
        "mask_file": cfg.get("CommandLineArgs", "mask_file", fallback="").strip(),
        "hmax": float(cfg.get("Spacing", "hmax", fallback="100.0")),
        "hshr": float(cfg.get("Spacing", "hshr", fallback="100")),
        "nwav": int(cfg.get("Spacing", "nwav", fallback="400")),
        "hmin": float(cfg.get("Spacing", "hmin", fallback="100.0")),
        "dhdx": float(cfg.get("Spacing", "dhdx", fallback="0.05")),
        "deep_ocean_threshold_m": float(
            cfg.get("Spacing", "deep_ocean_threshold_m", fallback="4000.0")
        ),
        "dem_file": cfg.get("DataFiles", "dem_file", fallback="").strip(),
    }
    reg = {
        "lon_min": cfg.getfloat("Regional", "lon_min"),
        "lon_max": cfg.getfloat("Regional", "lon_max"),
        "lat_min": cfg.getfloat("Regional", "lat_min"),
        "lat_max": cfg.getfloat("Regional", "lat_max"),
        "margin_deg": cfg.getfloat("Regional", "margin_deg", fallback=1.0),
        "edge_segments": cfg.getint("Regional", "edge_segments", fallback=48),
        "stereo_lon": cfg.getfloat("Regional", "stereo_lon"),
        "stereo_lat": cfg.getfloat("Regional", "stereo_lat"),
    }
    return {**base, **reg}


def _rectangle_boundary_lonlat(
    lon_min: float,
    lon_max: float,
    lat_min: float,
    lat_max: float,
    n_seg: int,
) -> np.ndarray:
    if n_seg < 4:
        raise ValueError("edge_segments must be >= 4")

    def interp2d(a, b, n):
        t = np.linspace(0.0, 1.0, n)
        return a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])

    c0 = (lon_min, lat_min)
    c1 = (lon_max, lat_min)
    c2 = (lon_max, lat_max)
    c3 = (lon_min, lat_max)

    pts = []
    lon, lat = interp2d(c0, c1, n_seg)
    pts.extend(zip(lon.tolist(), lat.tolist()))
    lon, lat = interp2d(c1, c2, n_seg)
    pts.extend(zip(lon[1:].tolist(), lat[1:].tolist()))
    lon, lat = interp2d(c2, c3, n_seg)
    pts.extend(zip(lon[1:].tolist(), lat[1:].tolist()))
    lon, lat = interp2d(c3, c0, n_seg)
    pts.extend(zip(lon[1:-1].tolist(), lat[1:-1].tolist()))

    return np.asarray(pts, dtype=np.float64)


def _build_geom_pslg(
    lon_min: float,
    lon_max: float,
    lat_min: float,
    lat_max: float,
    edge_segments: int,
) -> jigsawpy.jigsaw_msh_t:
    poly = _rectangle_boundary_lonlat(
        lon_min, lon_max, lat_min, lat_max, edge_segments
    )
    nv = poly.shape[0]
    vert2 = np.zeros(nv, dtype=jigsawpy.jigsaw_msh_t.VERT2_t)
    vert2["coord"][:, 0] = poly[:, 0]
    vert2["coord"][:, 1] = poly[:, 1]
    vert2["IDtag"] = 0

    edge2 = np.zeros(nv, dtype=jigsawpy.jigsaw_msh_t.EDGE2_t)
    for i in range(nv):
        edge2["index"][i] = [i, (i + 1) % nv]
        edge2["IDtag"][i] = 0

    seed2 = np.zeros(1, dtype=jigsawpy.jigsaw_msh_t.VERT2_t)
    seed2["coord"][0, 0] = 0.5 * (lon_min + lon_max)
    seed2["coord"][0, 1] = 0.5 * (lat_min + lat_max)
    seed2["IDtag"][0] = 0

    geom = jigsawpy.jigsaw_msh_t()
    geom.mshID = "euclidean-mesh"
    geom.ndims = 2
    geom.point = vert2
    geom.edge2 = edge2
    geom.seeds = seed2
    return geom


def _subset_dem(dem_file: str, lon0: float, lon1: float, lat0: float, lat1: float):
    data = nc.Dataset(dem_file, "r")
    lon = np.asarray(data["lon"][:], dtype=np.float64)
    lat = np.asarray(data["lat"][:], dtype=np.float64)
    bed = np.asarray(data["bed_elevation"][:], dtype=np.float64)
    if "ice_thickness" in data.variables:
        ice = np.asarray(data["ice_thickness"][:], dtype=np.float64)
    else:
        ice = np.zeros_like(bed)
    z = bed + ice

    if lon[0] > lon[-1]:
        lon = lon[::-1]
        z = z[:, ::-1]
    if lat[0] > lat[-1]:
        lat = lat[::-1]
        z = z[::-1, :]

    i0 = max(0, int(np.searchsorted(lon, lon0, side="left")) - 2)
    i1 = min(lon.size, int(np.searchsorted(lon, lon1, side="right")) + 2)
    j0 = max(0, int(np.searchsorted(lat, lat0, side="left")) - 2)
    j1 = min(lat.size, int(np.searchsorted(lat, lat1, side="right")) + 2)

    xs = lon[i0:i1]
    ys = lat[j0:j1]
    zsub = z[j0:j1, i0:i1]
    data.close()
    return xs, ys, zsub


def _centers_to_grid_edges(c: np.ndarray) -> np.ndarray:
    c = np.asarray(c, dtype=np.float64)
    if c.size < 2:
        raise ValueError("need at least 2 grid points along axis")
    dc = np.diff(c)
    left = c[0] - 0.5 * dc[0]
    right = c[-1] + 0.5 * dc[-1]
    mid = 0.5 * (c[:-1] + c[1:])
    return np.concatenate([[left], mid, [right]])


def _build_regional_spacing(
    spac: jigsawpy.jigsaw_msh_t,
    radii: np.ndarray,
    xlon: np.ndarray,
    ylat: np.ndarray,
    elev: np.ndarray,
    conf: dict,
    sp,
):
    hmax = float(conf["hmax"])
    hshr = float(conf["hshr"])
    nwav = int(conf["nwav"])
    hmin = float(conf["hmin"])
    dhdx = float(conf["dhdx"])
    deep_threshold_m = -abs(float(conf.get("deep_ocean_threshold_m", 4000.0)))
    mask_file = conf.get("mask_file") or ""

    land = sp.form_land_mask_connect(elev, edry=2) >= 1
    high = sp.form_land_mask_connect(elev, edry=8) >= 1

    hmat = np.full(elev.shape, hmax, dtype=spac.FLT32_t)
    hmat[land] = hmax
    if nwav > 0:
        hmat = np.minimum(
            hmat,
            sp.swe_wavelength_spacing(elev, land, nwav, hmin, hmax),
        )
    hmat[high] = hmax
    hmat = sp.setup_shoreline_pixels(hmat, land, hshr)

    if mask_file and os.path.isfile(mask_file):
        hmat = sp.scale_spacing_via_mask(_MaskArgs(mask_file), hmat)
        print("Scaling applied using mask_file:", mask_file)
    elif mask_file:
        print("mask_file set but not found, skipping:", mask_file)

    hmat_pre_smooth = np.array(hmat, copy=True)
    filt = sp.filter_pixels_harmonic(hmat, exp=2)
    hmat = np.minimum(hmat, filt)
    filt = sp.filter_pixels_harmonic(hmat, exp=1)
    hmat = np.minimum(hmat, filt)
    hmat = _repair_deep_ocean_spacing_after_harmonic(
        hmat, hmat_pre_smooth, elev, land, depth_m=deep_threshold_m
    )

    hmat = np.asarray(sp.remap_pixels_to_corner(hmat), dtype=spac.FLT32_t)

    pre_aln = _align_field_to_shape(hmat_pre_smooth, hmat.shape, order=1)
    elev_aln = _align_field_to_shape(elev, hmat.shape, order=1)
    land_aln = sp.form_land_mask_connect(elev_aln, edry=2) >= 1
    hmat = _repair_deep_ocean_spacing_after_harmonic(
        hmat,
        pre_aln.astype(spac.FLT32_t),
        elev_aln,
        land_aln,
        depth_m=deep_threshold_m,
    )
    hmat = np.asarray(hmat, dtype=spac.FLT32_t)
    hmat = _apply_deep_ocean_hmax_floor(
        hmat, elev_aln, land_aln, hmax, depth_m=deep_threshold_m
    )

    x_edge = _centers_to_grid_edges(xlon)
    y_edge = _centers_to_grid_edges(ylat)
    if hmat.shape != (y_edge.size, x_edge.size):
        raise ValueError(
            f"spacing shape {hmat.shape} != {(y_edge.size, x_edge.size)} "
            f"(DEM {elev.shape}); internal grid mismatch"
        )

    spac.mshID = "ellipsoid-grid"
    spac.radii = radii
    spac.xgrid = x_edge * np.pi / 180.0
    spac.ygrid = y_edge * np.pi / 180.0
    spac.value = np.minimum(hmax, hmat)
    spac.slope = np.array(dhdx, dtype=np.float64)

    with nc.Dataset("spac_regional.nc", "w") as ds:
        ds.createDimension("nlon", spac.xgrid.size)
        ds.createDimension("nlat", spac.ygrid.size)
        v = ds.createVariable("val", "f4", ("nlat", "nlon"))
        v[:, :] = np.asarray(spac.value, dtype=np.float32)


def run_regional_from_config(
    config_path: str,
    unst_dir: Path,
    *,
    jigsaw_python_root: Path | None = None,
) -> None:
    """
    Full regional pipeline. cwd should be mesh workspace (run_dir) before calling.
    If jigsaw_python_root points to a tree containing jigsawpy/, it is prepended to sys.path;
    otherwise ``jigsawpy`` is imported from the environment or installed with
    ``python -m pip install jigsawpy``.
    """
    local = Path(jigsaw_python_root).resolve() if jigsaw_python_root is not None else None
    repo = _ensure_jigsawpy(local)
    if repo is not None:
        jr = str(repo)
        if jr not in sys.path:
            sys.path.insert(0, jr)

    globals()["jigsawpy"] = importlib.import_module("jigsawpy")

    _ensure_unst_on_path(unst_dir)
    import ocn_ww3
    from ocn_ww3 import filter_ocn, inject_dem, write_gmsh_mesh
    import spacing as sp

    conf = load_regional_config(config_path)
    config_path = os.path.abspath(config_path)

    lon_min = conf["lon_min"]
    lon_max = conf["lon_max"]
    lat_min = conf["lat_min"]
    lat_max = conf["lat_max"]
    margin = conf["margin_deg"]

    dem_path = conf["dem_file"]
    if not os.path.isfile(dem_path):
        print("DEM not found:", dem_path, file=sys.stderr)
        sys.exit(1)

    print(
        f"*regional box: lon [{lon_min},{lon_max}]  "
        f"lat [{lat_min},{lat_max}]  margin {margin} deg"
    )

    xs, ys, elev = _subset_dem(
        dem_path,
        lon_min - margin,
        lon_max + margin,
        lat_min - margin,
        lat_max + margin,
    )
    print(
        f"*DEM subset: lon {xs[0]:.3f}..{xs[-1]:.3f}  "
        f"lat {ys[0]:.3f}..{ys[-1]:.3f}"
    )

    radii = np.full(3, 6.371e3, dtype=np.float64)
    spac = jigsawpy.jigsaw_msh_t()
    _build_regional_spacing(spac, radii, xs, ys, elev, conf, sp)

    geom = _build_geom_pslg(
        lon_min, lon_max, lat_min, lat_max, conf["edge_segments"]
    )

    proj = jigsawpy.jigsaw_prj_t()
    proj.prjID = "stereographic"
    proj.radii = 6.371e3
    proj.xbase = conf["stereo_lon"] * np.pi / 180.0
    proj.ybase = conf["stereo_lat"] * np.pi / 180.0

    geom_w = jigsawpy.jigsaw_msh_t()
    geom_w.mshID = geom.mshID
    geom_w.ndims = geom.ndims
    geom_w.point = np.copy(geom.point)
    geom_w.edge2 = np.copy(geom.edge2)
    geom_w.seeds = np.copy(geom.seeds)
    geom_w.point["coord"][:, :] *= np.pi / 180.0

    spac_w = jigsawpy.jigsaw_msh_t()
    spac_w.mshID = spac.mshID
    spac_w.radii = spac.radii.copy()
    spac_w.xgrid = spac.xgrid.copy()
    spac_w.ygrid = spac.ygrid.copy()
    spac_w.value = spac.value.copy()
    spac_w.slope = spac.slope.copy()

    jigsawpy.project(geom_w, proj, "fwd")
    jigsawpy.project(spac_w, proj, "fwd")

    opts = jigsawpy.jigsaw_jig_t()
    opts.geom_file = "geom_regional.msh"
    opts.hfun_file = "spac_regional.msh"
    opts.jcfg_file = "opts_regional.jig"
    opts.mesh_file = conf["mesh_file"]

    opts.hfun_scal = "absolute"
    opts.hfun_hmax = float(conf["hfun_hmax"])
    opts.hfun_hmin = min(float(conf["hmin"]), opts.hfun_hmax)

    jigsawpy.savemsh(opts.geom_file, geom_w)
    jigsawpy.savemsh(opts.hfun_file, spac_w)

    print("*marche...")
    jigsawpy.cmd.marche(opts, spac_w)

    opts.mesh_dims = 2
    opts.optm_iter = 64
    opts.optm_cost = "skew-cos"
    opts.mesh_eps1 = 1.0

    mesh = jigsawpy.jigsaw_msh_t()
    print("*jigsaw...")
    jigsawpy.cmd.jigsaw(opts, mesh)

    jigsawpy.project(mesh, proj, "inv")
    mesh.point["coord"][:, :] *= 180.0 / np.pi

    S2 = mesh.point["coord"][:, [0, 1]] * np.pi / 180.0
    R3 = jigsawpy.S2toR3(radii, S2)

    mesh_r3 = jigsawpy.jigsaw_msh_t()
    mesh_r3.mshID = "ellipsoid-mesh"
    mesh_r3.radii = radii.astype(mesh_r3.REALS_t)
    mesh_r3.tria3 = mesh.tria3
    mesh_r3.ndims = 3
    n = R3.shape[0]
    mesh_r3.vert3 = np.zeros(n, dtype=mesh_r3.VERT3_t)
    mesh_r3.vert3["coord"] = R3
    # ocn_ww3.inject_dem / filter_ocn read mesh.point["coord"] as R3 Cartesian
    mesh_r3.point = mesh_r3.vert3

    ocn_ww3.mesh = mesh_r3
    ocn_ww3.geom = jigsawpy.jigsaw_msh_t()
    ocn_ww3.geom.mshID = "ellipsoid-mesh"
    ocn_ww3.geom.radii = radii.astype(ocn_ww3.geom.REALS_t)

    prev_argv = sys.argv[:]
    try:
        sys.argv = ["create_grid.py", "--config", config_path]
        inject_dem()
        filter_ocn()
    finally:
        sys.argv = prev_argv

    jigsawpy.savevtk("test_regional.vtk", ocn_ww3.mesh)

    point = ocn_ww3.mesh.point["coord"]
    point = jigsawpy.R3toS2(ocn_ww3.geom.radii, point)
    point *= 180.0 / np.pi
    depth = np.reshape(-1.0 * ocn_ww3.mesh.value, (ocn_ww3.mesh.value.size, 1))
    depth[depth <= 0] = 2.0
    point = np.hstack((point, depth))
    tri_data = ocn_ww3.mesh.tria3["index"] + 1
    write_gmsh_mesh(conf["ww3_mesh_file"], point, tri_data)
    print("*wrote", conf["ww3_mesh_file"])


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


def _jigsaw_bundle_roots() -> list[Path]:
    """Ordered search roots for a tree containing ``jigsawpy/`` (for PYTHONPATH / pip install)."""
    base = Path(__file__).resolve().parent
    roots: list[Path] = []
    env_root = os.environ.get("WW3_JIGSAW_PYTHON_ROOT", "").strip()
    if env_root:
        roots.append(Path(env_root).expanduser().resolve())
    roots.append(base / "jigsaw-python")
    return roots


def _first_local_jigsaw_tree() -> Path | None:
    for root in _jigsaw_bundle_roots():
        if root.is_dir() and (root / "jigsawpy").is_dir():
            return root
    return None


def _local_jigsaw_repo(cfg: configparser.ConfigParser, grid_dir: Path) -> Path | None:
    """Directory that contains a ``jigsawpy`` package (``jigsawpy/`` subdir), or None."""
    if cfg.has_section("Workflow"):
        raw = cfg.get("Workflow", "jigsaw_python_root", fallback="").strip()
        if raw:
            root = Path(raw)
            if not root.is_absolute():
                root = (grid_dir / root).resolve()
            else:
                root = root.resolve()
            if root.is_dir() and (root / "jigsawpy").is_dir():
                return root
            return None
    return _first_local_jigsaw_tree()


def _ensure_jigsawpy(local_repo: Path | None) -> Path | None:
    """
    If ``local_repo`` has ``jigsawpy/``, return it for sys.path.
    Otherwise prefer ``WW3_JIGSAW_PYTHON_ROOT`` / ``jigsaw-python``, then site-packages,
    then ``pip install jigsawpy``, local ``pip install <dir>`` if that tree has setup files,
    then ``pip install`` from the upstream Git URL if needed.
    """
    if local_repo is not None:
        r = local_repo.resolve()
        if r.is_dir() and (r / "jigsawpy").is_dir():
            return r

    bundled = _first_local_jigsaw_tree()
    if bundled is not None:
        return bundled

    try:
        importlib.import_module("jigsawpy")
    except ImportError:
        print(
            "jigsawpy not importable; trying PyPI (`pip install jigsawpy`) ...",
            file=sys.stderr,
        )
        rc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "jigsawpy"],
            capture_output=True,
            text=True,
        )
        if rc.returncode != 0:
            for root in _jigsaw_bundle_roots():
                if root.is_dir() and (
                    (root / "pyproject.toml").is_file() or (root / "setup.py").is_file()
                ):
                    print(
                        f"PyPI install failed for this Python; "
                        f"installing jigsawpy from local tree: {root}",
                        file=sys.stderr,
                    )
                    subprocess.run(
                        [sys.executable, "-m", "pip", "install", str(root)],
                        check=True,
                    )
                    break
            else:
                print(
                    "Trying jigsaw-python from GitHub (source build; needs git, cmake, C++ toolchain) …",
                    file=sys.stderr,
                )
                git_rc = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        _JIGSAW_PYTHON_GIT_PIP,
                    ],
                    capture_output=True,
                    text=True,
                )
                if git_rc.returncode != 0:
                    if git_rc.stderr:
                        print(git_rc.stderr, file=sys.stderr, end="")
                    sys.exit(
                        "Could not install jigsawpy: PyPI has no wheel for this Python "
                        f"({sys.version.split()[0]}), and Git/source install failed.\n"
                        "Options: (1) export WW3_JIGSAW_PYTHON_ROOT=/path/to/a/dir/with/jigsawpy ; "
                        "(2) place that tree as `jigsaw-python` next to create_grid.py ; "
                        "(3) set Workflow.jigsaw_python_root in grid config ; "
                        "(4) use Python 3.11–3.12 where `pip install jigsawpy` may work ; "
                        "(5) fix toolchain and retry (see errors above)."
                    )
        importlib.import_module("jigsawpy")
    return None


def _marche_exe_name() -> str:
    return "marche.exe" if os.name == "nt" else "marche"


def _collect_jigsaw_bin_dirs() -> list[Path]:
    """Dirs containing the ``marche`` binary; jigsawpy looks here or on PATH."""
    out: list[Path] = []
    seen: set[Path] = set()
    name = _marche_exe_name()

    def add(p: Path) -> None:
        try:
            rp = p.resolve()
        except OSError:
            return
        if rp not in seen and (rp / name).is_file():
            seen.add(rp)
            out.append(rp)

    try:
        spec = importlib.util.find_spec("jigsawpy")
        if spec and spec.origin:
            add(Path(spec.origin).resolve().parent / "_bin")
    except (ImportError, ValueError, TypeError, OSError):
        pass

    for root in _jigsaw_bundle_roots():
        add(root / "jigsawpy" / "_bin")
        add(root / "_bin")

    env_bin = os.environ.get("WW3_JIGSAW_BIN", "").strip()
    if env_bin:
        add(Path(env_bin).expanduser())

    return out


def _prepend_jigsaw_bins_to_process_path() -> None:
    bins = _collect_jigsaw_bin_dirs()
    if not bins:
        return
    extra = os.pathsep.join(str(b) for b in bins)
    os.environ["PATH"] = extra + os.pathsep + os.environ.get("PATH", "")


def _try_auto_build_jigsaw() -> bool:
    """
    If a full jigsaw-python checkout is present (build.py + external/jigsaw), run build.py
    then ``pip install .`` so ``jigsawpy/_bin`` contains ``marche``.
    Skip when WW3_SKIP_JIGSAW_BUILD is set.
    """
    if os.environ.get("WW3_SKIP_JIGSAW_BUILD", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return False
    for root in _jigsaw_bundle_roots():
        build_py = root / "build.py"
        ext_jigsaw = root / "external" / "jigsaw"
        if not build_py.is_file() or not ext_jigsaw.is_dir():
            continue
        print(
            f"JIGSAW CLI (`marche`) missing; running `python build.py` under {root}\n"
            "  (needs cmake + C++ toolchain; set WW3_SKIP_JIGSAW_BUILD=1 to skip)\n",
            file=sys.stderr,
        )
        try:
            subprocess.run(
                [sys.executable, str(build_py)],
                cwd=str(root),
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            print(
                f"build.py failed (exit {exc.returncode}). Install cmake and a C++ compiler, "
                "then retry.",
                file=sys.stderr,
            )
            return False
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", "."],
                cwd=str(root),
                check=True,
            )
        except subprocess.CalledProcessError:
            print(
                "Note: `pip install .` failed after build; using `jigsawpy/_bin` under the source tree.",
                file=sys.stderr,
            )
        return True
    return False


def _marche_resolvable() -> bool:
    name = _marche_exe_name()
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if d and (Path(d) / name).is_file():
            return True
    return shutil.which("marche") is not None


def _require_jigsaw_cli_or_exit() -> None:
    _prepend_jigsaw_bins_to_process_path()
    if _marche_resolvable():
        return
    if _try_auto_build_jigsaw():
        _prepend_jigsaw_bins_to_process_path()
        if _marche_resolvable():
            print("JIGSAW `marche` is now on PATH.", file=sys.stderr)
            return
    sys.exit(
        "JIGSAW command-line tools not found: missing the `marche` executable (and later `jigsaw`).\n"
        "The `jigsawpy` package is importable but its native binaries are missing.\n"
        "Options:\n"
        "  • Clone https://github.com/dengwirda/jigsaw-python next to create_grid.py as "
        "`jigsaw-python`, run `python3 build.py` then `pip install .`, and re-run; or set "
        "WW3_JIGSAW_PYTHON_ROOT to that directory so auto-build can run.\n"
        "  • Or set WW3_JIGSAW_BIN to the directory that already contains `marche`.\n"
        "  • Or add that directory to PATH. Upstream: https://github.com/dengwirda/jigsaw-python"
    )


def _subprocess_env(
    cfg: configparser.ConfigParser,
    grid_dir: Path,
    unst_dir: Path,
) -> dict[str, str]:
    """Ensure unst_msh_gen (spacing.py) and optional local jigsaw-python are on PYTHONPATH."""
    env = os.environ.copy()
    prefixes: list[str] = [str(unst_dir)]
    if cfg.has_section("Workflow"):
        raw = cfg.get("Workflow", "jigsaw_python_root", fallback="").strip()
        if raw:
            root = Path(raw)
            if not root.is_absolute():
                root = (grid_dir / root).resolve()
            else:
                root = root.resolve()
            if root.is_dir() and (root / "jigsawpy").is_dir():
                prefixes.append(str(root))
            else:
                _ensure_jigsawpy(None)
        else:
            br = _first_local_jigsaw_tree()
            if br is not None:
                prefixes.append(str(br))
    else:
        br = _first_local_jigsaw_tree()
        if br is not None:
            prefixes.append(str(br))
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
    with nc.Dataset(src, "r") as ds_in:
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
    with nc.Dataset(str(dest), "w", format="NETCDF4") as ds_out:
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


def _print_banner_title_line(title: str, width: int = 70) -> None:
    """Center in monospace/log: left-pad only (WW3Tool log strips trailing spaces)."""
    pad = max((width - len(title)) // 2, 0)
    print(" " * pad + title, flush=True)


def _print_unstructured_run_banner() -> None:
    """70-column banner; title visually centered in fixed-width log."""
    sys.stdout.flush()
    print("=" * 70, flush=True)
    _print_banner_title_line("Unstructured Triangular Mesh Generation By JIGSAW")
    print("=" * 70 + "\n", flush=True)


def _print_unstructured_complete_banner() -> None:
    sys.stdout.flush()
    print("=" * 70, flush=True)
    _print_banner_title_line("Mesh Generation Complete!")
    print("=" * 70, flush=True)


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

    _ensure_jigsawpy(_local_jigsaw_repo(cfg, grid_path.parent))
    _require_jigsaw_cli_or_exit()

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
        # Regional pipeline (in this module); does not modify unst_msh_gen.
        jig_root = _local_jigsaw_repo(cfg, grid_path.parent)
        print("Running regional mesh pipeline ...", file=sys.stderr)
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

    _print_unstructured_complete_banner()


if __name__ == "__main__":
    main()
