"""
Create Grid - New Version Matching MATLAB create_grid.m

Create a grid for WAVEWATCH III based on a rectilinear grid.
This version matches the MATLAB create_grid.m implementation.

Copyright 2009 National Weather Service (NWS),
National Oceanic and Atmospheric Administration. All rights reserved.
Distributed with WAVEWATCH III

Last Update: 2024
"""

import argparse
import os
import sys
import time

import netCDF4
import numpy as np
import scipy.io

def _load_local_module(rel_path: str, module_id: str):
    """Load a ``.py`` under this directory by path (stable module id for importlib)."""
    import importlib.util

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), *rel_path.split("/"))
    for attempt in range(2):
        spec = importlib.util.spec_from_file_location(module_id, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module from {path}")
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            return mod
        except ValueError as e:
            msg = str(e).lower()
            if attempt == 0 and ("bad marshal data" in msg or "bad magic number" in msg):
                cache = importlib.util.cache_from_source(path)
                try:
                    if os.path.isfile(cache):
                        os.unlink(cache)
                except OSError:
                    pass
                continue
            raise


# Single import strategy:
# - Add this folder (…/pygridgen) to sys.path so ``grid`` / ``utils`` are unambiguous siblings.
# - Do not ``from io.xxx import`` — stdlib ``io`` would win; load local ``io/*.py`` via paths.
_pkg_root = os.path.dirname(os.path.abspath(__file__))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from grid.clean_mask import clean_mask
from grid.compute_boundary import compute_boundary
from grid.create_obstr import create_obstr
from grid.generate_grid import generate_grid
from grid.remove_lake import remove_lake
from grid.split_boundary import split_boundary

_ob = _load_local_module("io/optional_bound.py", "ww3grid_optional_bound")
optional_bound = _ob.optional_bound
_rnl = _load_local_module("io/read_namelist.py", "ww3grid_read_namelist")
read_namelist = _rnl.read_namelist
_wwf = _load_local_module("io/write_ww3file.py", "ww3grid_write_ww3file")
write_ww3file = _wwf.write_ww3file
_wwm = _load_local_module("io/write_ww3meta.py", "ww3grid_write_ww3meta")
write_ww3meta = _wwm.write_ww3meta
_wwo = _load_local_module("io/write_ww3obstr.py", "ww3grid_write_ww3obstr")
write_ww3obstr = _wwo.write_ww3obstr

# Force unbuffered output for real-time logging
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

# ``nml_path`` keyword: use this sentinel when the caller did not pass ``nml_path``
_USE_DEFAULT_GRID_NML = object()


_BOUNDARY_ALIAS_TO_FILE = {
    "full": "coastal_bound_full.mat",
    "high": "coastal_bound_high.mat",
    "inter": "coastal_bound_inter.mat",
    "low": "coastal_bound_low.mat",
    "coarse": "coastal_bound_coarse.mat",
}


def _extract_array(data):
    """Extract a 1D numpy array from nested MATLAB-style structures."""
    if isinstance(data, np.ndarray):
        if data.dtype == object:
            if data.size > 0:
                return _extract_array(data.flat[0])
            return np.array([])
        return data.flatten()
    return np.array(data).flatten()


def _coerce_scalar(value, default=None, cast=float):
    """Convert MATLAB/scipy-loaded scalar-ish values to a Python scalar."""
    if value is None:
        return default
    if isinstance(value, np.ndarray):
        if value.size == 0:
            return default
        return _coerce_scalar(value.flat[0], default=default, cast=cast)
    if isinstance(value, (list, tuple)):
        if not value:
            return default
        return _coerce_scalar(value[0], default=default, cast=cast)
    try:
        return cast(value)
    except (TypeError, ValueError):
        return default


def _mat_struct_to_dicts(struct_array):
    """Convert a MATLAB struct array loaded by scipy into a list of dicts."""
    if isinstance(struct_array, list):
        return [item for item in struct_array if isinstance(item, dict)]
    if not isinstance(struct_array, np.ndarray):
        return [struct_array] if isinstance(struct_array, dict) else []
    if struct_array.dtype.names is None:
        items = struct_array.tolist()
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        return [items] if isinstance(items, dict) else []

    records = []
    for poly in struct_array.flatten():
        poly_dict = {}
        for field_name in poly.dtype.names:
            field_data = poly[field_name]
            scalar_int = {"n", "level"}
            scalar_float = {"west", "east", "south", "north", "height", "width"}
            if field_name in scalar_int:
                poly_dict[field_name] = _coerce_scalar(field_data, default=0, cast=int)
            elif field_name in scalar_float:
                poly_dict[field_name] = _coerce_scalar(field_data, default=0.0, cast=float)
            else:
                flat = _extract_array(field_data)
                if flat.size == 1:
                    poly_dict[field_name] = _coerce_scalar(flat, default=0.0, cast=float)
                else:
                    poly_dict[field_name] = flat
        records.append(poly_dict)
    return records


def _load_boundary_structs(boundary_file):
    """Load a coastline MAT file into a normalized list of polygon dicts."""
    mat_data = scipy.io.loadmat(boundary_file)
    return _mat_struct_to_dicts(mat_data["bound"])


def _load_optional_boundary_structs(ref_dir, fname_poly):
    """
    Load user-defined polygons while preserving MATLAB create_grid.m semantics.

    Optional polygons are processed independently from the main coastline
    dataset and only applied in the second clean-mask pass.
    """
    bound_user, count = optional_bound(ref_dir, fname_poly)
    if count <= 0 or not isinstance(bound_user, list) or bound_user[0] == -1:
        return [], 0
    return _normalize_boundaries(bound_user), count


def _split_dateline(poly):
    """Split polygon when it crosses the dateline (±180°)."""
    if poly is None or len(poly) == 0:
        return [poly]
    lon = np.asarray(poly[:, 0]).flatten()
    lat = np.asarray(poly[:, 1]).flatten()
    if len(lon) < 2:
        return [poly]
    lonc = np.concatenate([lon, [lon[0]]])
    latc = np.concatenate([lat, [lat[0]]])
    dlon = np.diff(lonc)
    cross_idx = np.where(np.abs(dlon) > 180)[0]
    if cross_idx.size == 0:
        return [poly]
    nseg = len(lonc) - 1
    nins = len(cross_idx)
    total_len = nseg + nins
    new_lon = np.zeros(total_len)
    new_lat = np.zeros(total_len)
    split_pos = np.zeros(nins, dtype=int)
    k = 0
    c = 0
    for i in range(nseg):
        x1, y1 = lonc[i], latc[i]
        x2, y2 = lonc[i + 1], latc[i + 1]
        new_lon[k] = x1
        new_lat[k] = y1
        k += 1
        d = x2 - x1
        if abs(d) > 180:
            xi = 180 if d > 0 else -180
            t = (xi - x1) / (x2 - x1)
            yi = y1 + t * (y2 - y1)
            new_lon[k] = xi
            new_lat[k] = yi
            split_pos[c] = k
            k += 1
            c += 1
    new_lon = new_lon[:k]
    new_lat = new_lat[:k]
    polys = []
    s = 0
    for i in range(nins):
        e = split_pos[i]
        polys.append(np.column_stack([new_lon[s:e + 1], new_lat[s:e + 1]]))
        s = e
    polys.append(np.column_stack([new_lon[s:], new_lat[s:]]))
    return polys


def _normalize_boundaries(bound):
    """Match MATLAB global handling: normalize lon range and split dateline."""
    processed = []
    for poly in bound:
        if not isinstance(poly, dict):
            continue
        x = _extract_array(poly.get('x', []))
        y = _extract_array(poly.get('y', []))
        if x.size == 0 or y.size == 0:
            continue
        min_len = min(len(x), len(y))
        x = x[:min_len]
        y = y[:min_len]
        # Force polygons to be defined between -180 and 180
        x = np.where(x >= 180, x - 360, x)
        east = float(np.max(x))
        west = float(np.min(x))
        north = float(np.max(y))
        south = float(np.min(y))
        base_poly = poly.copy()
        base_poly.update({
            'x': x,
            'y': y,
            'east': east,
            'west': west,
            'north': north,
            'south': south,
            'n': len(x)
        })
        # Split polygon if crossing dateline
        if east > 179 and west < -179:
            polys = _split_dateline(np.column_stack([x, y]))
            for p in polys:
                if p is None or len(p) == 0:
                    continue
                x2 = np.asarray(p[:, 0]).flatten()
                y2 = np.asarray(p[:, 1]).flatten()
                # Close polygon
                if x2[0] != x2[-1] or y2[0] != y2[-1]:
                    x2 = np.append(x2, x2[0])
                    y2 = np.append(y2, y2[0])
                new_poly = base_poly.copy()
                new_poly.update({
                    'x': x2,
                    'y': y2,
                    'east': float(np.max(x2)),
                    'west': float(np.min(x2)),
                    'north': float(np.max(y2)),
                    'south': float(np.min(y2)),
                    'n': len(x2),
                    'level': 1
                })
                processed.append(new_poly)
        else:
            processed.append(base_poly)
    return processed





_CURRENT_STAGE = ['startup']

# (name, seconds) for each finished stage, and the one still open.
_STAGE_LOG: list = []
_STAGE_OPEN: list = [None, 0.0]


def _begin_stage(name):
    """Mark the start of a stage, closing the timing of the previous one."""
    now = time.time()
    if _STAGE_OPEN[0] is not None:
        _STAGE_LOG.append((_STAGE_OPEN[0], now - _STAGE_OPEN[1]))
    _STAGE_OPEN[0] = name
    _STAGE_OPEN[1] = now
    _CURRENT_STAGE[0] = name


def _reset_stages():
    del _STAGE_LOG[:]
    _STAGE_OPEN[0] = None
    _STAGE_OPEN[1] = 0.0
    _CURRENT_STAGE[0] = 'startup'


def _report_stages():
    """Print where the run actually spent its time.

    Without this the only number reported was the total, which says nothing
    about which stage to optimise -- a global run took 80 minutes and the
    breakdown had to be guessed at.
    """
    now = time.time()
    if _STAGE_OPEN[0] is not None:
        _STAGE_LOG.append((_STAGE_OPEN[0], now - _STAGE_OPEN[1]))
        _STAGE_OPEN[0] = None
    if not _STAGE_LOG:
        return
    total = sum(sec for _, sec in _STAGE_LOG) or 1.0
    print('Stage timings:', flush=True)
    for name, sec in _STAGE_LOG:
        bar = '#' * int(round(30 * sec / total))
        print(f'  {name:<46} {sec:9.1f}s {100 * sec / total:5.1f}%  {bar}', flush=True)


def _start_memory_watchdog():
    """Start the runtime memory watchdog, or a no-op if unavailable."""
    try:
        from utils.parallel import start_memory_watchdog
    except ImportError:
        return lambda: None
    return start_memory_watchdog(lambda: _CURRENT_STAGE[0])


def _estimate_base_read_bytes(params, lon, lat):
    """Bytes ``generate_grid`` will hold for its slice of the base bathymetry.

    This is the term that decides a global run: the window is read in one
    slice, so a global domain against 15-arcsecond GEBCO is 3.7 billion points
    -- about 11 GiB once netCDF4's mask byte is counted -- regardless of how
    coarse the target grid is.  Estimated from the base file's own extent, so
    it follows whichever dataset was selected.
    """
    ref_grid = str(params.get('ref_grid') or '')
    path = os.path.join(params['ref_dir'], f'{ref_grid}.nc')
    if not os.path.isfile(path):
        return 0
    var_z = params.get('var_z') or (
        'z' if ref_grid.lower() in ('etopo1', 'etopo2') else 'elevation')
    try:
        f = netCDF4.Dataset(path, 'r')
    except OSError:
        return 0
    try:
        var = f.variables.get(var_z)
        if var is None or len(var.shape) != 2:
            return 0
        n_lat_base, n_lon_base = int(var.shape[0]), int(var.shape[1])
        itemsize = var.dtype.itemsize
        # netCDF4 adds a mask byte per point, unless the variable declares
        # nothing to mask and generate_grid therefore reads it unmasked.
        masking = {"_FillValue", "missing_value", "valid_min", "valid_max",
                   "valid_range"} & set(var.ncattrs())
        if masking:
            itemsize += 1
        var_x = params.get('var_x') or (
            'x' if ref_grid.lower() == 'etopo2' else 'lon')
        lon_var = f.variables.get(var_x)
        lon_hi = float(np.max(lon_var[:])) if lon_var is not None else None
    except (AttributeError, KeyError, TypeError, ValueError):
        return 0
    finally:
        f.close()

    # Fraction of the globe the domain covers, with a little slack for the
    # two-cell margin generate_grid adds on each side.
    #
    # Longitude has to be measured *after* folding into the base's convention,
    # exactly as generate_grid does: a domain straddling the base's seam (150~210
    # against -180..180 GEBCO) folds to -180..180 and is read at full width, so
    # taking the domain's own 60-degree span would understate it six-fold.
    lon_eff = np.asarray(lon, dtype=float)
    if n_lon_base and lon_hi is not None:
        if lon_hi > 180.0 + 1e-6:
            if np.min(lon_eff) < -1e-6:
                lon_eff = np.where(lon_eff < 0.0, lon_eff + 360.0, lon_eff)
        elif np.max(lon_eff) > 180.0 + 1e-6:
            lon_eff = np.where(lon_eff > 180.0, lon_eff - 360.0, lon_eff)
    lon_span = min(360.0, float(np.max(lon_eff)) - float(np.min(lon_eff)) + 4 * params['dx'])
    lat_span = min(180.0, float(np.max(lat)) - float(np.min(lat)) + 4 * params['dy'])
    rows = max(1.0, n_lat_base * lat_span / 180.0)
    cols = max(1.0, n_lon_base * lon_span / 360.0)
    return int(rows * cols * itemsize)


def _check_memory_plan(cells, base_read_bytes=0):
    """Whether a grid of *cells* points is expected to fit in memory.

    Deliberately tolerant: if the helpers are unavailable, or the budget
    cannot be read, the run proceeds.
    """
    try:
        from utils.parallel import (available_cpus, check_memory_plan,
                                    worker_baseline_bytes, _self_rss_bytes)
    except ImportError:
        return True, 'Memory estimate unavailable.'
    base = (_self_rss_bytes() or 0) + int(base_read_bytes)
    return check_memory_plan(
        cells,
        base_bytes=base,
        n_workers=available_cpus(),
        per_worker_bytes=worker_baseline_bytes() + (32 << 20),
    )


def _align_boundaries_to_grid(bound, lon_min, lon_max):
    """Shift coastline polygons into the target grid's longitude branch.

    GSHHS is stored in -180..180, but a grid may be written 0..360, or may
    cross the dateline — the desktop normalises a 170..-170 box to 170..190,
    so longitudes above 180 (or below -180) are ordinary input.  Without this
    step every polygon sits outside such a domain and the run silently
    produces no coastline at all: no mask cleanup and an all-zero obstruction
    file.

    Each polygon is offered at its own longitude and one turn either side; the
    copies whose bounding box overlaps the grid are kept.  A polygon sitting on
    the grid's seam is therefore kept twice, once from each side, and
    ``compute_boundary`` clips each copy to the part that is actually inside.
    A plain -180..180 grid keeps exactly the k=0 copy, i.e. the original list.
    """
    lon_min = float(lon_min)
    lon_max = float(lon_max)
    aligned = []
    for poly in bound:
        if not isinstance(poly, dict):
            continue
        west = float(poly.get('west', 0.0))
        east = float(poly.get('east', 0.0))
        for turn in (-360.0, 0.0, 360.0):
            if east + turn < lon_min or west + turn > lon_max:
                continue
            if turn == 0.0:
                aligned.append(poly)
                continue
            shifted = poly.copy()
            shifted['x'] = np.asarray(poly['x'], dtype=float) + turn
            shifted['west'] = west + turn
            shifted['east'] = east + turn
            aligned.append(shifted)
    return aligned


def _params_from_grid_nml(nml_path):
    """
    Map FORTRAN-style grid.nml sections to create_grid ``params`` keys.
    """
    init = read_namelist(nml_path, "GRID_INIT")
    out = read_namelist(nml_path, "OUTGRID")
    bathy = read_namelist(nml_path, "BATHY_FILE")
    gb = read_namelist(nml_path, "GRID_BOUND")
    gp = read_namelist(nml_path, "GRID_PARAM")

    gtype = str(out.get("type", "rect")).lower().strip()
    gtype = gtype.strip("'\"")

    def _strip_quotes(s):
        if isinstance(s, str) and len(s) >= 2 and s[0] in "'\"" and s[-1] == s[0]:
            return s[1:-1]
        return s

    p = {
        "ref_dir": init["ref_dir"],
        "out_dir": init["data_dir"],
        "fname": _strip_quotes(str(init.get("fname", "grid"))),
        "fname_poly": _strip_quotes(str(init.get("fname_poly", "user_polygons.flag"))),
        "type": gtype,
        "dx": float(out["dx"]),
        "dy": float(out["dy"]),
        "lon_range": [float(out["lon_west"]), float(out["lon_east"])],
        "lat_range": [float(out["lat_south"]), float(out["lat_north"])],
        "IS_GLOBAL": int(out.get("is_global", 0)),
        "ref_grid": _strip_quotes(str(bathy.get("ref_grid", "gebco"))).lower(),
        "lonfrom": float(bathy.get("lonfrom", -180)),
        "var_x": _strip_quotes(str(bathy.get("xvar", "lon"))),
        "var_y": _strip_quotes(str(bathy.get("yvar", "lat"))),
        "var_z": _strip_quotes(str(bathy.get("zvar", "elevation"))),
        "boundary": _strip_quotes(str(gb.get("boundary", "full"))),
        "read_boundary": int(gb.get("read_boundary", 1)),
        "opt_poly": int(gb.get("opt_poly", 0)),
        "MIN_DIST": float(gb.get("min_dist", 4.0)),
        "DRY_VAL": float(gp.get("dry_val", 999999)),
        "CUT_OFF": float(gp.get("cut_off", 0.1)),
        "LIM_BATHY": float(gp.get("lim_bathy", 0.1)),
        "LIM_VAL": float(gp.get("lim_val", 0.5)),
        "SPLIT_LIM": float(gp.get("split_lim", 0.0)),
        "LAKE_TOL": float(gp.get("lake_tol", -1)),
        "OBSTR_OFFSET": int(gp.get("obstr_offset", 1)),
    }
    if "offset" in gp and gp["offset"] is not None:
        p["OFFSET"] = float(gp["offset"])
    else:
        p["OFFSET"] = None
    return p


def _resolve_boundary_mat_file(ref_dir, boundary):
    """
    Resolve the coastline ``.mat`` file from ``GRID_BOUND.BOUNDARY``.

    Supported forms:
    - legacy short names: ``full`` / ``high`` / ``inter`` / ``low`` / ``coarse``
    - explicit basename stem: ``coastal_bound_full``
    - explicit file name: ``coastal_bound_full.mat``
    - relative / absolute path to any ``.mat`` file
    """
    raw = str(boundary).strip()
    if not raw:
        raw = "full"
    raw_lower = raw.lower()
    if raw_lower == "ultra":
        raw = "full"
        raw_lower = "full"

    if raw_lower in _BOUNDARY_ALIAS_TO_FILE:
        return os.path.normpath(os.path.join(ref_dir, _BOUNDARY_ALIAS_TO_FILE[raw_lower]))

    cand = raw
    if not cand.lower().endswith(".mat"):
        cand = cand + ".mat"
    if os.path.isabs(cand):
        return os.path.normpath(cand)

    rel_file = os.path.normpath(os.path.join(ref_dir, cand))
    if os.path.exists(rel_file):
        return rel_file

    stem = raw[:-4] if raw.lower().endswith(".mat") else raw
    if not stem.startswith("coastal_bound_"):
        stem = f"coastal_bound_{stem}"
    return os.path.normpath(os.path.join(ref_dir, f"{stem}.mat"))


def _write_ascii_matrix(fname, data, fmt):
    """Write a 2D matrix with a configurable float/int format."""
    out_dir = os.path.dirname(fname)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(fname, "w", encoding="utf-8", newline="\n") as fid:
        arr = np.asarray(data)
        for row in arr:
            fid.write(" ".join(fmt.format(v) for v in row) + "\n")


def _load_curv_arrays(fname_bathy, xvar, yvar, zvar):
    """Load curvilinear lon/lat/depth arrays from a NetCDF bathymetry file."""
    with netCDF4.Dataset(fname_bathy, "r") as ds:
        lon_raw = np.asarray(ds.variables[xvar][:], dtype=np.float32)
        lat_raw = np.asarray(ds.variables[yvar][:], dtype=np.float32)
        dep_var = ds.variables[zvar]
        depth_raw = np.asarray(dep_var[:], dtype=np.float32)
        fill_value = getattr(dep_var, "_FillValue", None)

    lon = lon_raw.T
    lat = lat_raw.T
    depth = depth_raw.T

    if lon.ndim == 1 and lat.ndim == 1:
        lon, lat = np.meshgrid(lon, lat)
    elif lon.ndim != 2 or lat.ndim != 2:
        raise ValueError(
            f"Curvilinear workflow expects 2D lon/lat (or matching 1D vectors); "
            f"got lon ndim={lon.ndim}, lat ndim={lat.ndim}"
        )

    if depth.ndim == 1:
        if lon.shape[0] == 1:
            depth = depth[np.newaxis, :]
        else:
            depth = depth[:, np.newaxis]

    if depth.shape != lon.shape:
        raise ValueError(
            f"Depth shape {depth.shape} does not match lon/lat shape {lon.shape} in {fname_bathy}"
        )

    return lon.astype(np.float32), lat.astype(np.float32), depth.astype(np.float32), fill_value


def create_grid(**kwargs):
    """
    Create a grid for WAVEWATCH III based on a rectilinear grid.
    
    Parameters (optional name-value pairs):
    ----------
    ref_dir : str
        Path to reference data directory (default: '../reference_data/')
    out_dir : str
        Path to output directory (default: '../result/')
    fname : str
        Output file name prefix (default: 'grid')
    dx : float
        Grid resolution in longitude (degrees) (default: 0.05)
    dy : float
        Grid resolution in latitude (degrees) (default: 0.05)
    lon_range : list
        [lon_west, lon_east] (default: [110, 130])
    lat_range : list
        [lat_south, lat_north] (default: [10, 30])
    ref_grid : str
        Bathymetry source ('etopo1', 'etopo2', 'gebco') (default: 'gebco')
    boundary : str
        Coastline boundary source. Supports legacy GSHHS levels
        ('full','high','inter','low','coarse') or an explicit ``.mat`` file /
        stem such as 'coastal_bound_full.mat'. (default: 'full')
    read_boundary : int
        Read boundary data? (default: 1)
    opt_poly : int
        Use optional polygons? (default: 0)
    fname_poly : str
        Optional polygon file name (default: 'user_polygons.flag')
    DRY_VAL : float
        Depth value for dry cells (default: 999999)
    CUT_OFF : float
        Cut-off depth to distinguish wet/dry (default: 0.1)
    LIM_BATHY : float
        Fraction of cell that must be wet (default: 0.1)
    LIM_VAL : float
        Fraction for polygon masking (default: 0.5)
    OFFSET : float
        Buffer around boundary (default: max(dx,dy))
    LAKE_TOL : float
        Lake removal tolerance (default: -1)
    IS_GLOBAL : int
        Is global grid? (default: 0)
    OBSTR_OFFSET : int
        Obstruction offset (default: 1)
    SPLIT_LIM : float
        Limit for splitting polygons (default: 5*max(dx,dy))
    show_plots : int
        Show visualization plots? (default: 1)
    nml_path : str or None
        If str, load this Fortran namelist (same layout as MATLAB ``grid.nml``).
        If omitted and ``<pygridgen>/grid.nml`` exists, load it.
        If ``None``, do not load a namelist (use defaults and **kwargs only).
    """
    # 0. Parse input arguments
    # Get the base directory (where this script is located)
    script_path = os.path.abspath(__file__)
    base_dir = os.path.dirname(script_path)
    # Toolkit root = meshgen/ (reference_data, result); scripts live in structured_generator/pygridgen/
    base_name = os.path.basename(base_dir)
    if base_name in ('python', 'python_version', 'pygridgen'):
        parent = os.path.dirname(base_dir)
        pname = os.path.basename(parent)
        if pname in ('structured_generator', 'gridgen'):
            project_root = os.path.dirname(parent)
        else:
            project_root = parent
    elif base_name == 'structured_generator':
        project_root = os.path.dirname(base_dir)
    elif base_name == 'gridgen':
        parent = os.path.dirname(base_dir)
        if os.path.basename(parent) == 'structured_generator':
            project_root = os.path.dirname(parent)
        else:
            project_root = base_dir
    else:
        project_root = base_dir
    
    # Set defaults
    params = {
        'ref_dir': os.path.join(project_root, 'reference_data'),
        'out_dir': os.path.join(project_root, 'result'),
        'fname': 'grid',
        'type': 'rect',
        'dx': 0.05,
        'dy': 0.05,
        'lon_range': [110, 130],
        'lat_range': [10, 30],
        'ref_grid': 'gebco',
        'lonfrom': -180,
        'boundary': 'full',
        'read_boundary': 1,
        'opt_poly': 0,
        'fname_poly': 'user_polygons.flag',
        'DRY_VAL': 999999,
        'CUT_OFF': 0.1,
        'LIM_BATHY': 0.1,
        'LIM_VAL': 0.5,
        'OFFSET': None,  # Will be set to max(dx,dy) if None
        'LAKE_TOL': -1,
        'IS_GLOBAL': 0,
        'OBSTR_OFFSET': 1,
        'MIN_DIST': 4.0,
        'SPLIT_LIM': 0.0,  # Align with MATLAB (splitting disabled by default)
        'show_plots': 1
    }

    nml_path_kw = kwargs.pop("nml_path", _USE_DEFAULT_GRID_NML)
    default_nml_file = os.path.join(base_dir, "grid.nml")
    if nml_path_kw is _USE_DEFAULT_GRID_NML:
        nml_path_resolved = default_nml_file if os.path.isfile(default_nml_file) else None
    elif not nml_path_kw:
        nml_path_resolved = None
    else:
        nml_path_resolved = os.path.abspath(os.path.normpath(str(nml_path_kw)))
        if not os.path.isfile(nml_path_resolved):
            raise FileNotFoundError(f"grid namelist not found: {nml_path_resolved}")

    fname_nml_abs = None
    if nml_path_resolved:
        params.update(_params_from_grid_nml(nml_path_resolved))
        fname_nml_abs = nml_path_resolved.replace("\\", "/")

    # Update with provided kwargs (overrides namelist)
    params.update(kwargs)
    
    # Normalize key paths to avoid Windows backslash/escape issues
    # Native separators (normpath); do not force "/" — on Windows join(ref_dir, "*.nc") would
    # otherwise become mixed slashes and netCDF4 fails with "Unknown file format".
    params['ref_dir'] = os.path.normpath(os.path.abspath(os.path.expanduser(params['ref_dir'])))
    params['out_dir'] = os.path.abspath(params['out_dir']).replace("\\", "/")
    
    # Set default values for computed parameters
    if params['OFFSET'] is None:
        params['OFFSET'] = max([params['dx'], params['dy']])
    if params['SPLIT_LIM'] is None:
        params['SPLIT_LIM'] = 0.0
    
    # 0. Initialization
    _reset_stages()
    start_time = time.time()
    # Force unbuffered output for real-time logging
    sys.stdout.flush()
    print('=' * 70, flush=True)
    title = 'Structured Grid Generation By Gridgen Python Version'
    pad = max((70 - len(title)) // 2, 0)
    print(' ' * pad + title, flush=True)
    print('=' * 70, flush=True)
    if fname_nml_abs:
        print(f"grid.nml: {fname_nml_abs}", flush=True)
    print(f"Grid name: {params['fname']}", flush=True)
    print(f"Grid type: {params['type']}", flush=True)
    print(f"Bathymetry source: {params['ref_grid']}", flush=True)
    print(f"Resolution: {params['dx']:.4f} x {params['dy']:.4f} degrees", flush=True)
    print(f"Domain: [{params['lon_range'][0]:.2f}, {params['lon_range'][1]:.2f}] x "
          f"[{params['lat_range'][0]:.2f}, {params['lat_range'][1]:.2f}]", flush=True)
    print('=' * 70 + '\n', flush=True)
    
    # Check bin directory

    
    # Create output directory if it doesn't exist
    os.makedirs(params['out_dir'], exist_ok=True)
    if not os.path.exists(params['out_dir']):
        print(f'Created output directory: {params["out_dir"]}', flush=True)
    
    # 1. Define grid coordinates
    print('Step 1: Defining grid coordinates...', flush=True)
    _begin_stage('Step 1')
    # MATLAB: lon1d = params.lon_range(1):params.dx:params.lon_range(2);
    # This creates an array from start to end with step dx, inclusive of both ends
    lon_start = params['lon_range'][0]
    lon_end = params['lon_range'][1]
    lat_start = params['lat_range'][0]
    lat_end = params['lat_range'][1]
    
    # Calculate number of points to match MATLAB's behavior
    # MATLAB's colon operator includes both endpoints
    nx = int(round((lon_end - lon_start) / params['dx'])) + 1
    ny = int(round((lat_end - lat_start) / params['dy'])) + 1
    
    lon1d = np.linspace(lon_start, lon_end, nx)
    lat1d = np.linspace(lat_start, lat_end, ny)
    
    # On a grid that wraps in longitude the first and last columns are the same
    # meridian, so keeping both is one column too many -- and WW3 does not
    # merely tolerate it.  With GRID%CLOS='SMPL' it recomputes the spacing as
    # SX = 360/NX (w3gridmd.F90: `IF ( ICLOSE.EQ.ICLOSE_SMPL ) SX = 360./REAL(NX)`),
    # so a 0.5 degree global grid written with 721 columns is placed at
    # 360/721 = 0.4993 degrees instead.  Every column then sits west of where
    # its data came from, by up to a full cell at the far end.  Dropping the
    # repeat makes NX = 360/dx, which is the spacing that was asked for.
    if int(params.get('IS_GLOBAL', 0) or 0) == 1 and nx > 1:
        span = float(lon1d[-1] - lon1d[0])
        if abs(span - 360.0) <= 0.5 * float(params['dx']):
            lon1d = lon1d[:-1]
            nx -= 1
            print(f'  Global grid: dropped the repeated meridian, '
                  f'NX = {nx} at {params["dx"]:g} deg (WW3 forces SX = 360/NX '
                  f'for GRID%CLOS=\'SMPL\').', flush=True)
    
    lon, lat = np.meshgrid(lon1d, lat1d)
    print(f'  Grid size: {lon.shape[1]} x {lon.shape[0]} points', flush=True)
    print('  Done.\n', flush=True)
    
    gtype = str(params.get("type", "rect")).lower().strip()
    if gtype == "curv":
        fname_bathy = os.path.join(params["ref_dir"], f"{params['ref_grid']}.nc")
        if not os.path.isfile(fname_bathy):
            raise FileNotFoundError(f"Bathymetry file not found: {fname_bathy}")

        print("Step 1b: Reading curvilinear bathymetry, lon, and lat...", flush=True)
        lon, lat, depth, fill_value = _load_curv_arrays(
            fname_bathy, params["var_x"], params["var_y"], params["var_z"]
        )
        print(f"  Curvilinear grid size: {lon.shape[1]} x {lon.shape[0]} points", flush=True)
        print("  Done.\n", flush=True)

        print("Step 2: Creating curvilinear land-sea mask...", flush=True)
        m4 = np.ones(depth.shape, dtype=np.int32)
        ny, nx = m4.shape
        m4[0, :] = 2
        m4[ny - 1, :] = 2
        m4[:, 0] = 2
        m4[:, nx - 1] = 2

        dry_mask = depth == float(params["DRY_VAL"])
        nan_mask = np.isnan(depth)
        fill_mask = np.zeros_like(dry_mask)
        if fill_value is not None:
            fill_mask = depth == np.float32(fill_value)
        land_mask = dry_mask | nan_mask | fill_mask
        m4[land_mask] = 0

        depth_out = np.array(depth, copy=True)
        depth_out[dry_mask] = 0
        depth_out[nan_mask] = 0
        depth_out[fill_mask] = 0
        print(f"  Sea points: {np.sum(m4 != 0)}", flush=True)
        print(f"  Land points: {np.sum(m4 == 0)}", flush=True)
        print("  Done.\n", flush=True)

        print("Step 3: Creating zero obstructions for curvilinear workflow...", flush=True)
        sx1 = np.zeros_like(depth_out, dtype=np.float32)
        sy1 = np.zeros_like(depth_out, dtype=np.float32)
        print("  Done.\n", flush=True)

        print("Step 4: Writing WAVEWATCH III output files...", flush=True)
        depth_scale = 1000
        obstr_scale = 100

        write_ww3file(
            os.path.join(params["out_dir"], f"{params['fname']}.bot"),
            np.round(depth_out * depth_scale).astype(int),
        )
        write_ww3file(os.path.join(params["out_dir"], f"{params['fname']}.mask"), m4.astype(int))
        write_ww3file(
            os.path.join(params["out_dir"], f"{params['fname']}.mask_nobound"),
            m4.astype(int),
        )
        _write_ascii_matrix(
            os.path.join(params["out_dir"], f"{params['fname']}.lon"),
            lon,
            "{:.10f}",
        )
        _write_ascii_matrix(
            os.path.join(params["out_dir"], f"{params['fname']}.lat"),
            lat,
            "{:.10f}",
        )
        write_ww3obstr(
            os.path.join(params["out_dir"], f"{params['fname']}.obst"),
            np.round(sx1 * obstr_scale).astype(int),
            np.round(sy1 * obstr_scale).astype(int),
        )

        meta_prefix = os.path.join(params["out_dir"], params["fname"])
        meta_prefix = os.path.abspath(meta_prefix).replace("\\", "/")
        _meta_msg, _meta_rc = write_ww3meta(
            meta_prefix,
            fname_nml_abs,
            "CURV",
            lon,
            lat,
            1.0 / depth_scale,
            1.0 / obstr_scale,
            1.0,
            is_global_override=params["IS_GLOBAL"],
            ref_dir_override=params["ref_dir"],
        )
        if _meta_rc != 0:
            raise RuntimeError(f"Failed to write grid.meta: {_meta_msg}")
        print(f"  Written: {params['fname']}.bot", flush=True)
        print(f"  Written: {params['fname']}.mask", flush=True)
        print(f"  Written: {params['fname']}.mask_nobound", flush=True)
        print(f"  Written: {params['fname']}.lon", flush=True)
        print(f"  Written: {params['fname']}.lat", flush=True)
        print(f"  Written: {params['fname']}.obst (all zeros)", flush=True)
        print("  Written: grid.meta", flush=True)
        print("  Done.\n", flush=True)

        elapsed_time = time.time() - start_time
        print("=" * 70, flush=True)
        title2 = "Grid Generation Complete!"
        pad = max((70 - len(title2)) // 2, 0)
        print(" " * pad + title2, flush=True)
        print("=" * 70, flush=True)
        print(f"Output directory: {params['out_dir']}", flush=True)
        print("Output files:", flush=True)
        print(f"  - {params['fname']}.bot  (bathymetry)", flush=True)
        print(f"  - {params['fname']}.mask / .mask_nobound (land-sea mask)", flush=True)
        print(f"  - {params['fname']}.lon / .lat (curvilinear coordinates)", flush=True)
        print(f"  - {params['fname']}.obst (obstructions, all zeros)", flush=True)
        print("  - grid.meta (WW3 grid description, CURV)", flush=True)
        print(f"Total time: {elapsed_time:.2f} seconds", flush=True)
        print("=" * 70, flush=True)
        return
    if gtype != "rect":
        raise ValueError(
            f"Python create_grid currently implements gridgen parity for TYPE='rect' and "
            f"the separate TYPE='curv' workflow only; got {gtype!r}."
        )

    # 2. Read boundary data
    bound_user = []
    Nu = 0
    if params['read_boundary']:
        print('Step 2: Reading GSHHS boundary data...', flush=True)
        _begin_stage('Step 2')
        boundary_file = _resolve_boundary_mat_file(params['ref_dir'], params['boundary'])
        
        if os.path.exists(boundary_file):
            bound = _load_boundary_structs(boundary_file)
            N = len(bound)
            print(f'  Loaded {N} boundary polygons', flush=True)
            
            # Load optional polygons if requested
            if params['opt_poly'] == 1:
                fname_poly = os.path.normpath(
                    os.path.join(params['ref_dir'], params['fname_poly'])
                )
                if os.path.exists(fname_poly):
                    bound_user, Nu = _load_optional_boundary_structs(params['ref_dir'], fname_poly)
                    if Nu > 0:
                        print(f'  Loaded {Nu} user-defined polygons', flush=True)
                    else:
                        print('  No user-defined polygons enabled in flag file', flush=True)
                        params['opt_poly'] = 0
                else:
                    print(f'  Warning: Optional polygon file not found: {fname_poly}', flush=True)
                    print('  Continuing without optional polygons...', flush=True)
                    params['opt_poly'] = 0
            # Normalize boundaries for global handling (dateline split, lon range)
            bound = _normalize_boundaries(bound)
            # Put the polygons in the same longitude branch as the target grid
            # (a 0~360 or dateline-crossing domain would otherwise see none).
            grid_lon_min = float(np.min(lon)) - params['dx']
            grid_lon_max = float(np.max(lon)) + params['dx']
            before = len(bound)
            bound = _align_boundaries_to_grid(bound, grid_lon_min, grid_lon_max)
            if bound_user:
                bound_user = _align_boundaries_to_grid(bound_user, grid_lon_min, grid_lon_max)
                Nu = len(bound_user)
            N = len(bound)
            print(f'  Normalized boundary polygons: {N}', flush=True)
            if N != before:
                print(f'  Aligned to grid longitudes [{grid_lon_min:.2f}, '
                      f'{grid_lon_max:.2f}]: {before} -> {N} polygons', flush=True)
        else:
            print(f'  Warning: Boundary file not found: {boundary_file}', flush=True)
            print('  Continuing without boundary data...', flush=True)
            params['read_boundary'] = 0
            bound = []
        print('  Done.\n', flush=True)
    else:
        print('Step 2: Skipping boundary data (read_boundary = 0)\n', flush=True)
        bound = []
        bound_user = []
        Nu = 0
    
    # Check the run is expected to fit before paying for it.  The coastline
    # database is loaded by now, so the fixed part of the estimate is measured
    # rather than guessed, and a grid that cannot fit says so here instead of
    # being killed by the OOM handler somewhere in step 7.
    # Watch the real number for the rest of the run.  The estimate below can
    # only ever be advisory -- validated against measured peaks it ranged from
    # 0.4x to 2.1x -- so it warns, while the watchdog is what actually stops a
    # run before the OOM killer does.
    _stop_watchdog = _start_memory_watchdog()

    _base_read = _estimate_base_read_bytes(params, lon, lat)
    if _base_read:
        print(f'  Base bathymetry slice: ~{_base_read / 1024 ** 3:.1f} GiB '
              f"({params['ref_grid']})", flush=True)
    _status, _mem_msg = _check_memory_plan(int(np.asarray(lon).size), _base_read)
    if _status == 'over':
        print(f'  {_mem_msg}', flush=True)
        raise MemoryError(_mem_msg)
    if _status in ('tight', 'unknown'):
        print(f'  WARNING: {_mem_msg}', flush=True)
    else:
        print(f'  {_mem_msg}', flush=True)
    print('', flush=True)

    # 3. Generate bathymetry
    _begin_stage('Step 3')
    print(f"Step 3: Generating bathymetry from {params['ref_grid']}...", flush=True)
    print('  This may take a while...', flush=True)
    try:
        # generate_grid(type_grid, x, y, ref_dir, bathy_source, limit, cut_off, dry, xvar, yvar, zvar)
        # Match MATLAB: generate_grid(lon, lat, params.ref_dir, params.ref_grid, ...)
        # Python version requires type_grid as first parameter
        # Variable names: from namelist (BATHY_FILE) when present, else by bathy source
        var_x = params.get("var_x")
        var_y = params.get("var_y")
        var_z = params.get("var_z")
        if not var_x or not var_y or not var_z:
            ref_grid_lower = params["ref_grid"].lower()
            if ref_grid_lower == "etopo2":
                var_x, var_y, var_z = "x", "y", "z"
            elif ref_grid_lower == "etopo1":
                var_x, var_y, var_z = "lon", "lat", "z"
            else:
                var_x, var_y, var_z = "lon", "lat", "elevation"
        depth = generate_grid('rect', lon, lat, params['ref_dir'], params['ref_grid'],
                            params['LIM_BATHY'], params['CUT_OFF'], params['DRY_VAL'],
                            var_x, var_y, var_z)
        print('  Done.\n', flush=True)
    except Exception as e:
        print(f'  ERROR: Failed to generate bathymetry', flush=True)
        print(f'  Error message: {e}', flush=True)
        import traceback
        traceback.print_exc()
        raise
    
    # 4. Compute boundaries within grid
    if params['read_boundary']:
        _begin_stage('Step 4')
        _s4 = 'Step 4: Computing boundaries within grid domain...'
        try:
            sys.stdout.buffer.write(
                (_s4 + '\n').encode(sys.stdout.encoding or 'utf-8', errors='replace')
            )
            sys.stdout.buffer.flush()
        except (AttributeError, OSError, ValueError):
            print(_s4, flush=True)
            sys.stdout.flush()
        lon_start = np.min(lon) - params['dx']
        lon_end = np.max(lon) + params['dx']
        lat_start = np.min(lat) - params['dy']
        lat_end = np.max(lat) + params['dy']
        
        coord = [lat_start, lon_start, lat_end, lon_end]
        b, N1 = compute_boundary(coord, bound, params['MIN_DIST'])
        if params['opt_poly'] == 1 and Nu > 0:
            b_opt, N2 = compute_boundary(coord, bound_user, params['MIN_DIST'])
        else:
            b_opt, N2 = [], 0
        sys.stdout.flush()
        print(f'  Found {N1} boundary segments in grid domain', flush=True)
        if params['opt_poly'] == 1:
            print(f'  Found {N2} optional boundary segments in grid domain', flush=True)
        print('  Done.\n', flush=True)
    else:
        b = []
        N1 = 0
        b_opt = []
        N2 = 0
        print('Step 4: Skipping boundary computation\n', flush=True)
    
    # 5. Create initial land-sea mask
    print('Step 5: Creating initial land-sea mask...', flush=True)
    _begin_stage('Step 5')
    m = np.ones_like(depth)
    m[depth == params['DRY_VAL']] = 0
    print(f'  Initial wet cells: {np.sum(m == 1)}', flush=True)
    print(f'  Initial dry cells: {np.sum(m == 0)}', flush=True)
    print('  Done.\n', flush=True)
    
    # 6. Split large boundary polygons (for efficiency)
    if params['read_boundary'] and N1 > 0:
        print('Step 6: Splitting large boundary polygons...', flush=True)
        _begin_stage('Step 6')
        sys.stdout.flush()
        b_split = split_boundary(b, params['SPLIT_LIM'], params['MIN_DIST'])
        sys.stdout.flush()
        print('  Done.\n', flush=True)
    else:
        b_split = b
        print('Step 6: Skipping boundary splitting\n', flush=True)
    
    # 7. Clean mask using boundary polygons
    if params['read_boundary'] and N1 > 0:
        print('Step 7: Cleaning mask using boundary polygons...', flush=True)
        _begin_stage('Step 7')
        sys.stdout.flush()
        m2 = clean_mask(lon, lat, m, b_split, params['LIM_VAL'], params['OFFSET'])
        if params['opt_poly'] == 1 and N2 != 0:
            m3 = clean_mask(lon, lat, m2, b_opt, params['LIM_VAL'], params['OFFSET'])
        else:
            m3 = m2
        print(f'  Wet cells after cleaning: {np.sum(m2 == 1)}', flush=True)
        print(f'  Dry cells after cleaning: {np.sum(m2 == 0)}', flush=True)
        if params['opt_poly'] == 1 and N2 != 0:
            print(f'  Wet cells after optional polygons: {np.sum(m3 == 1)}', flush=True)
            print(f'  Dry cells after optional polygons: {np.sum(m3 == 0)}', flush=True)
        print('  Done.\n', flush=True)
    else:
        m2 = m
        m3 = m2
        print('Step 7: Skipping mask cleaning (no boundaries)\n', flush=True)
    
    # 8. Remove lakes and small water bodies
    print('Step 8: Removing lakes and small water bodies...', flush=True)
    _begin_stage('Step 8')
    m4, mask_map = remove_lake(m3, params['LAKE_TOL'], params['IS_GLOBAL'])
    print(f'  Final wet cells: {np.sum(m4 == 1)}', flush=True)
    print(f'  Final dry cells: {np.sum(m4 == 0)}', flush=True)
    print('  Done.\n', flush=True)
    
    # 9. Create obstruction grids
    if params['read_boundary'] and N1 > 0:
        print('Step 9: Creating obstruction grids...', flush=True)
        _begin_stage('Step 9')
        sx1, sy1 = create_obstr(lon, lat, b, m4, params['OBSTR_OFFSET'],
                                params['OBSTR_OFFSET'],
                                is_global=params.get('IS_GLOBAL', 0))
        print('  Done.\n', flush=True)
    else:
        print('Step 9: Skipping obstruction grid creation (no boundaries)', flush=True)
        sx1 = np.zeros_like(m4)
        sy1 = np.zeros_like(m4)
        print('  Done.\n', flush=True)
    
    # 10. Write output files
    print('Step 10: Writing WAVEWATCH III output files...', flush=True)
    _begin_stage('Step 10')
    depth_scale = 1000
    obstr_scale = 100
    
    # Write bathymetry file
    d = np.round(depth * depth_scale).astype(int)
    write_ww3file(os.path.join(params['out_dir'], f"{params['fname']}.bot"), d)
    print(f"  Written: {params['fname']}.bot", flush=True)
    
    # Mask file: align with MATLAB gridgen (write_ww3file ... '.mask_nobound')
    write_ww3file(os.path.join(params['out_dir'], f"{params['fname']}.mask_nobound"), m4)
    print(f"  Written: {params['fname']}.mask_nobound", flush=True)
    
    # Write obstruction file
    # Always write obstruction file, even if no boundaries (write zeros)
    d1 = np.round(sx1 * obstr_scale).astype(int)
    d2 = np.round(sy1 * obstr_scale).astype(int)
    write_ww3obstr(os.path.join(params['out_dir'], f"{params['fname']}.obst"), d1, d2)
    if params['read_boundary'] and N1 > 0:
        print(f"  Written: {params['fname']}.obst (with obstructions)", flush=True)
    else:
        print(f"  Written: {params['fname']}.obst (no obstructions, all zeros)", flush=True)
    
    # WW3 grid description file (same as MATLAB gridgen: grid.nml in output dir)
    meta_prefix = os.path.join(params['out_dir'], params['fname'])
    meta_prefix = os.path.abspath(meta_prefix).replace("\\", "/")
    _meta_msg, _meta_rc = write_ww3meta(
        meta_prefix,
        fname_nml_abs,
        "RECT",
        lon,
        lat,
        1.0 / depth_scale,
        1.0 / obstr_scale,
        1.0,
        is_global_override=params["IS_GLOBAL"],
        ref_dir_override=params["ref_dir"],
    )
    if _meta_rc != 0:
        raise RuntimeError(f"Failed to write grid.meta: {_meta_msg}")
    print("  Written: grid.meta (WW3 grid description)", flush=True)
    print('  Done.\n', flush=True)
    
    # Summary
    elapsed_time = time.time() - start_time
    print('=' * 70, flush=True)
    title2 = 'Grid Generation Complete!'
    pad = max((70 - len(title2)) // 2, 0)
    print(' ' * pad + title2, flush=True)
    print('=' * 70, flush=True)
    print(f"Output directory: {params['out_dir']}", flush=True)
    print('Output files:', flush=True)
    print(f"  - {params['fname']}.bot  (bathymetry)", flush=True)
    print(f"  - {params['fname']}.mask_nobound (land-sea mask)", flush=True)
    if params['read_boundary'] and N1 > 0:
        print(f"  - {params['fname']}.obst (obstructions)", flush=True)
    else:
        print(f"  - {params['fname']}.obst (obstructions, all zeros)", flush=True)
    print("  - grid.nml (WW3 grid description, same as MATLAB gridgen)", flush=True)
    _report_stages()
    print(f'Total time: {elapsed_time:.2f} seconds', flush=True)
    print('=' * 70, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate a WW3 structured grid from grid.nml or kwargs defaults."
    )
    default_nml = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grid.nml")
    parser.add_argument(
        "--nml",
        default=default_nml,
        help="Path to grid.nml (default: pygridgen/grid.nml).",
    )
    parser.add_argument(
        "--no-nml",
        action="store_true",
        help="Ignore any grid.nml and use built-in defaults/kwargs only.",
    )
    args = parser.parse_args()

    nml_path = None if args.no_nml else args.nml
    create_grid(nml_path=nml_path)
