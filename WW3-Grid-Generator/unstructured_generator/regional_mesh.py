"""
Regional unstructured WW3 mesh (lat–lon box, stereographic JIGSAW).

Lives outside unst_msh_gen/ so upstream ocn_ww3.py / spacing.py stay unmodified.
Runtime: prepends unst_msh_gen to sys.path and imports those modules read-only.
"""

from __future__ import annotations

import configparser
import os
import sys
import importlib
from pathlib import Path
from typing import Any

import netCDF4 as nc
import numpy as np

# jigsawpy is imported from jigsaw-python/ after sys.path is fixed (see run_regional_from_config).
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
    jigsaw_python_root must contain jigsawpy/ (same checkout as Workflow.jigsaw_python_root).
    """
    jig = Path(jigsaw_python_root).resolve() if jigsaw_python_root is not None else None
    if jig is None or not jig.is_dir() or not (jig / "jigsawpy").is_dir():
        jig = Path(__file__).resolve().parent / "jigsaw-python"
    if not jig.is_dir() or not (jig / "jigsawpy").is_dir():
        print(
            "Cannot load jigsawpy: pass jigsaw_python_root=... to run_regional_from_config "
            f"(directory with jigsawpy/). Tried: {jig}",
            file=sys.stderr,
        )
        sys.exit(1)
    jr = str(jig)
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
        sys.argv = ["regional_mesh.py", "--config", config_path]
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
