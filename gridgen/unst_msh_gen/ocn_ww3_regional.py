"""
Regional unstructured mesh for WW3: lat–lon bounding box on the sphere.

Uses stereographic projection (same idea as regional/RWPSMeshGenScript.*),
DEM-driven spacing from a NetCDF subset, then inject_dem / filter_ocn / Gmsh
output compatible with ocn_ww3.py.

Run:
    python3 ocn_ww3_regional.py --config config_regional.ini
    python3 ocn_ww3_regional.py --config config.json

macOS: build JIGSAW with Debug if marche fails validation (see README notes).
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import netCDF4 as nc
import jigsawpy

from scipy.interpolate import RegularGridInterpolator

import ocn_ww3
from ocn_ww3 import (
    inject_dem,
    filter_ocn,
    write_gmsh_mesh,
    print_gridgen_banner_start,
    print_gridgen_banner_end,
)
from config_loader import load_regional_config
from spacing import (
    align_field_to_shape,
    form_land_mask_connect,
    setup_shoreline_pixels,
    swe_wavelength_spacing,
    filter_pixels_harmonic,
    remap_pixels_to_corner,
    scale_spacing_via_mask,
    repair_deep_ocean_spacing_after_harmonic,
    apply_deep_ocean_hmax_floor,
)


def parse_args():
    p = argparse.ArgumentParser(description="Regional WW3 mesh (lat-lon box).")
    p.add_argument("--config", type=str, required=True)
    return p.parse_args()


def rectangle_boundary_lonlat(
    lon_min: float,
    lon_max: float,
    lat_min: float,
    lat_max: float,
    n_seg: int,
) -> np.ndarray:
    """Closed CCW polygon in degrees (lon, lat), ~4*(n_seg-1) vertices."""
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


def build_geom_pslg(
    lon_min: float,
    lon_max: float,
    lat_min: float,
    lat_max: float,
    edge_segments: int,
) -> jigsawpy.jigsaw_msh_t:
    poly = rectangle_boundary_lonlat(
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


def subset_dem(
    dem_file: str,
    lon0: float,
    lon1: float,
    lat0: float,
    lat1: float,
):
    data = nc.Dataset(dem_file, "r")
    lon = np.asarray(data["lon"][:], dtype=np.float64)
    lat = np.asarray(data["lat"][:], dtype=np.float64)
    z = np.asarray(data["bed_elevation"][:], dtype=np.float64) + np.asarray(
        data["ice_thickness"][:], dtype=np.float64
    )

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


def centers_to_grid_edges(c: np.ndarray) -> np.ndarray:
    """1D ascending cell-centre coordinates -> len+1 edge coordinates (end caps)."""
    c = np.asarray(c, dtype=np.float64)
    if c.size < 2:
        raise ValueError("need at least 2 grid points along axis")
    dc = np.diff(c)
    left = c[0] - 0.5 * dc[0]
    right = c[-1] + 0.5 * dc[-1]
    mid = 0.5 * (c[:-1] + c[1:])
    return np.concatenate([[left], mid, [right]])


def build_regional_spacing(
    spac: jigsawpy.jigsaw_msh_t,
    radii: np.ndarray,
    xlon: np.ndarray,
    ylat: np.ndarray,
    elev: np.ndarray,
    conf: dict,
):
    hmax = float(conf["hmax"])
    hshr = float(conf["hshr"])
    nwav = int(conf["nwav"])
    hmin = float(conf["hmin"])
    dhdx = float(conf["dhdx"])
    mask_file = conf.get("mask_file") or ""

    land = form_land_mask_connect(elev, edry=2) >= 1
    high = form_land_mask_connect(elev, edry=8) >= 1

    hmat = np.full(elev.shape, hmax, dtype=spac.FLT32_t)
    hmat[land] = hmax
    if nwav > 0:
        hmat = np.minimum(
            hmat,
            swe_wavelength_spacing(elev, land, nwav, hmin, hmax),
        )
    hmat[high] = hmax
    hmat = setup_shoreline_pixels(hmat, land, hshr)

    if mask_file and os.path.isfile(mask_file):
        hmat = scale_spacing_via_mask(mask_file, hmat)
        print("Scaling applied using mask_file:", mask_file)
    elif mask_file:
        print("mask_file set but not found, skipping:", mask_file)

    hmat_pre_smooth = np.array(hmat, copy=True)
    filt = filter_pixels_harmonic(hmat, exp=2)
    hmat = np.minimum(hmat, filt)
    filt = filter_pixels_harmonic(hmat, exp=1)
    hmat = np.minimum(hmat, filt)
    hmat = repair_deep_ocean_spacing_after_harmonic(
        hmat, hmat_pre_smooth, elev, land)

    hmat = np.asarray(remap_pixels_to_corner(hmat), dtype=spac.FLT32_t)

    pre_aln = align_field_to_shape(hmat_pre_smooth, hmat.shape, order=1)
    elev_aln = align_field_to_shape(elev, hmat.shape, order=1)
    land_aln = form_land_mask_connect(elev_aln, edry=2) >= 1
    hmat = repair_deep_ocean_spacing_after_harmonic(
        hmat, pre_aln.astype(spac.FLT32_t), elev_aln, land_aln
    )
    hmat = np.asarray(hmat, dtype=spac.FLT32_t)
    hmat = apply_deep_ocean_hmax_floor(hmat, elev_aln, land_aln, hmax)

    # remap_pixels_to_corner is (Ny+1, Nx+1) on pixel grid (Ny, Nx); lon/lat must match.
    x_edge = centers_to_grid_edges(xlon)
    y_edge = centers_to_grid_edges(ylat)
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


def main():
    args = parse_args()
    conf = load_regional_config(args.config)

    print_gridgen_banner_start()

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

    xs, ys, elev = subset_dem(
        dem_path,
        lon_min - margin,
        lon_max + margin,
        lat_min - margin,
        lat_max + margin,
    )
    print(f"*DEM subset: lon {xs[0]:.3f}..{xs[-1]:.3f}  lat {ys[0]:.3f}..{ys[-1]:.3f}")

    radii = np.full(3, 6.371e3, dtype=np.float64)
    spac = jigsawpy.jigsaw_msh_t()
    build_regional_spacing(spac, radii, xs, ys, elev, conf)

    geom = build_geom_pslg(
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

    ocn_ww3.mesh = mesh_r3
    ocn_ww3.geom = jigsawpy.jigsaw_msh_t()
    ocn_ww3.geom.mshID = "ellipsoid-mesh"
    ocn_ww3.geom.radii = radii.astype(ocn_ww3.geom.REALS_t)

    sys.argv = ["ocn_ww3_regional.py", "--config", args.config]
    inject_dem()
    filter_ocn()

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
    print_gridgen_banner_end()


if __name__ == "__main__":
    main()
