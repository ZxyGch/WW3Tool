"""
Create Grid - New Version Matching MATLAB create_grid.m

Create a grid for WAVEWATCH III based on a rectilinear grid.
This version matches the MATLAB create_grid.m implementation.

Copyright 2009 National Weather Service (NWS),
National Oceanic and Atmospheric Administration. All rights reserved.
Distributed with WAVEWATCH III

Last Update: 2024
"""

import os
import sys
import time

import numpy as np
import scipy.io

def _load_local_module(rel_path: str, module_id: str):
    """Load a ``.py`` under this directory by path (stable module id for importlib)."""
    import importlib.util

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), *rel_path.split("/"))
    spec = importlib.util.spec_from_file_location(module_id, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def _extract_array(data):
    """Extract a 1D numpy array from nested MATLAB-style structures."""
    if isinstance(data, np.ndarray):
        if data.dtype == object:
            if data.size > 0:
                return _extract_array(data.flat[0])
            return np.array([])
        return data.flatten()
    return np.array(data).flatten()


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


def _params_from_grid_nml(nml_path):
    """
    Map FORTRAN-style grid.nml sections to create_grid ``params`` keys.
    Only TYPE='rect' is supported for the Python pipeline.
    """
    init = read_namelist(nml_path, "GRID_INIT")
    out = read_namelist(nml_path, "OUTGRID")
    bathy = read_namelist(nml_path, "BATHY_FILE")
    gb = read_namelist(nml_path, "GRID_BOUND")
    gp = read_namelist(nml_path, "GRID_PARAM")

    gtype = str(out.get("type", "rect")).lower().strip()
    gtype = gtype.strip("'\"")
    if gtype != "rect":
        raise ValueError(
            f"Python create_grid supports OUTGRID TYPE 'rect' only; got {gtype!r} in {nml_path}"
        )

    def _strip_quotes(s):
        if isinstance(s, str) and len(s) >= 2 and s[0] in "'\"" and s[-1] == s[0]:
            return s[1:-1]
        return s

    p = {
        "ref_dir": init["ref_dir"],
        "out_dir": init["data_dir"],
        "fname": _strip_quotes(str(init.get("fname", "grid"))),
        "fname_poly": _strip_quotes(str(init.get("fname_poly", "user_polygons.flag"))),
        "dx": float(out["dx"]),
        "dy": float(out["dy"]),
        "lon_range": [float(out["lon_west"]), float(out["lon_east"])],
        "lat_range": [float(out["lat_south"]), float(out["lat_north"])],
        "IS_GLOBAL": int(out.get("is_global", 0)),
        "ref_grid": _strip_quotes(str(bathy.get("ref_grid", "gebco"))).lower(),
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
        GSHHS boundary level ('full','high','inter','low','coarse') (default: 'full')
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
    # Toolkit root = WW3-Grid-Generator/ (reference_data, result); scripts live in structured_generator/pygridgen/
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
        'dx': 0.05,
        'dy': 0.05,
        'lon_range': [110, 130],
        'lat_range': [10, 30],
        'ref_grid': 'gebco',
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
    params['ref_dir'] = os.path.abspath(params['ref_dir']).replace("\\", "/")
    params['out_dir'] = os.path.abspath(params['out_dir']).replace("\\", "/")
    
    # Set default values for computed parameters
    if params['OFFSET'] is None:
        params['OFFSET'] = max([params['dx'], params['dy']])
    if params['SPLIT_LIM'] is None:
        params['SPLIT_LIM'] = 0.0
    
    # 0. Initialization
    start_time = time.time()
    # Force unbuffered output for real-time logging
    sys.stdout.flush()
    print('=' * 70, flush=True)
    title = 'Structured Rectangular Grid Generation By Gridgen Python Version'
    print(' ' * ((70 - len(title))) + title, flush=True)
    print('=' * 70, flush=True)
    if fname_nml_abs:
        print(f"grid.nml: {fname_nml_abs}", flush=True)
    print(f"Grid name: {params['fname']}", flush=True)
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
    
    lon, lat = np.meshgrid(lon1d, lat1d)
    print(f'  Grid size: {lon.shape[1]} x {lon.shape[0]} points', flush=True)
    print('  Done.\n', flush=True)
    
    # 2. Read boundary data
    if params['read_boundary']:
        print('Step 2: Reading GSHHS boundary data...', flush=True)
        boundary_file = os.path.join(params['ref_dir'], f"coastal_bound_{params['boundary']}.mat")
        
        if os.path.exists(boundary_file):
            mat_data = scipy.io.loadmat(boundary_file)
            bound = mat_data['bound']
            
            # Convert MATLAB struct array to Python list of dicts
            if isinstance(bound, np.ndarray):
                if bound.dtype.names is not None:
                    # Structured array
                    # MATLAB struct arrays are typically (1, N) shape when loaded by scipy
                    # Use .size to get total number of elements, or flatten first
                    bound_flat = bound.flatten()
                    N = bound_flat.size
                    bound_list = []
                    for i in range(N):
                        poly = bound_flat[i]
                        
                        poly_dict = {}
                        for field_name in poly.dtype.names:
                            field_data = poly[field_name]
                            if isinstance(field_data, np.ndarray):
                                if field_data.size == 1:
                                    if field_name in ['n', 'level']:
                                        poly_dict[field_name] = int(field_data.item())
                                    elif field_name in ['west', 'east', 'south', 'north', 'height', 'width']:
                                        poly_dict[field_name] = float(field_data.item())
                                    else:
                                        poly_dict[field_name] = float(field_data.item())
                                else:
                                    if field_data.dtype == object:
                                        if field_data.size > 0:
                                            first_elem = field_data.flat[0]
                                            if isinstance(first_elem, np.ndarray):
                                                poly_dict[field_name] = first_elem.flatten()
                                            else:
                                                poly_dict[field_name] = np.array(field_data.flat).flatten()
                                        else:
                                            poly_dict[field_name] = np.array([])
                                    else:
                                        poly_dict[field_name] = field_data.flatten()
                            else:
                                poly_dict[field_name] = field_data
                        
                        bound_list.append(poly_dict)
                    bound = bound_list
                else:
                    bound = bound.tolist()
            elif isinstance(bound, list):
                pass
            else:
                bound = [bound]
            
            N = len(bound) if isinstance(bound, list) else 1
            print(f'  Loaded {N} boundary polygons', flush=True)
            
            # Load optional polygons if requested
            Nu = 0
            if params['opt_poly'] == 1:
                fname_poly = os.path.join(params['ref_dir'], params['fname_poly'])
                if os.path.exists(fname_poly):
                    # optional_bound expects ref_dir and the full path to the flag file
                    bound_user, Nu = optional_bound(params['ref_dir'], fname_poly)
                    if Nu > 0:
                        print(f'  Loaded {Nu} user-defined polygons', flush=True)
                        # Append user polygons to bound list
                        if isinstance(bound_user, list) and len(bound_user) > 0 and bound_user[0] != -1:
                            bound.extend(bound_user)
                            N = len(bound)
                            print(f'  Total boundary polygons after adding user polygons: {N}', flush=True)
                    else:
                        print('  No user-defined polygons enabled in flag file', flush=True)
                        params['opt_poly'] = 0
                else:
                    print(f'  Warning: Optional polygon file not found: {fname_poly}', flush=True)
                    print('  Continuing without optional polygons...', flush=True)
                    params['opt_poly'] = 0
            # Normalize boundaries for global handling (dateline split, lon range)
            bound = _normalize_boundaries(bound)
            N = len(bound)
            print(f'  Normalized boundary polygons: {N}', flush=True)
        else:
            print(f'  Warning: Boundary file not found: {boundary_file}', flush=True)
            print('  Continuing without boundary data...', flush=True)
            params['read_boundary'] = 0
            bound = []
        print('  Done.\n', flush=True)
    else:
        print('Step 2: Skipping boundary data (read_boundary = 0)\n', flush=True)
        bound = []
    
    # 3. Generate bathymetry
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
        sys.stdout.flush()
        print(f'  Found {N1} boundary segments in grid domain', flush=True)
        print('  Done.\n', flush=True)
    else:
        b = []
        N1 = 0
        print('Step 4: Skipping boundary computation\n', flush=True)
    
    # 5. Create initial land-sea mask
    print('Step 5: Creating initial land-sea mask...', flush=True)
    m = np.ones_like(depth)
    m[depth == params['DRY_VAL']] = 0
    print(f'  Initial wet cells: {np.sum(m == 1)}', flush=True)
    print(f'  Initial dry cells: {np.sum(m == 0)}', flush=True)
    print('  Done.\n', flush=True)
    
    # 6. Split large boundary polygons (for efficiency)
    if params['read_boundary'] and N1 > 0:
        print('Step 6: Splitting large boundary polygons...', flush=True)
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
        sys.stdout.flush()
        m2 = clean_mask(lon, lat, m, b_split, params['LIM_VAL'], params['OFFSET'])
        print(f'  Wet cells after cleaning: {np.sum(m2 == 1)}', flush=True)
        print(f'  Dry cells after cleaning: {np.sum(m2 == 0)}', flush=True)
        print('  Done.\n', flush=True)
    else:
        m2 = m
        print('Step 7: Skipping mask cleaning (no boundaries)\n', flush=True)
    
    # 8. Remove lakes and small water bodies
    print('Step 8: Removing lakes and small water bodies...', flush=True)
    m4, mask_map = remove_lake(m2, params['LAKE_TOL'], params['IS_GLOBAL'])
    print(f'  Final wet cells: {np.sum(m4 == 1)}', flush=True)
    print(f'  Final dry cells: {np.sum(m4 == 0)}', flush=True)
    print('  Done.\n', flush=True)
    
    # 9. Create obstruction grids
    if params['read_boundary'] and N1 > 0:
        print('Step 9: Creating obstruction grids...', flush=True)
        sx1, sy1 = create_obstr(lon, lat, b, m4, params['OBSTR_OFFSET'], params['OBSTR_OFFSET'])
        print('  Done.\n', flush=True)
    else:
        print('Step 9: Skipping obstruction grid creation (no boundaries)', flush=True)
        sx1 = np.zeros_like(m4)
        sy1 = np.zeros_like(m4)
        print('  Done.\n', flush=True)
    
    # 10. Write output files
    print('Step 10: Writing WAVEWATCH III output files...', flush=True)
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
    write_ww3meta(
        meta_prefix,
        fname_nml_abs,
        "RECT",
        lon,
        lat,
        1.0 / depth_scale,
        1.0 / obstr_scale,
        1.0,
        is_global_override=params["IS_GLOBAL"],
    )
    print("  Written: grid.nml (WW3 grid description)", flush=True)
    print('  Done.\n', flush=True)
    
    # Summary
    elapsed_time = time.time() - start_time
    print('=' * 70, flush=True)
    title2 = 'Grid Generation Complete!'
    print(' ' * ((70 - len(title2))) + title2, flush=True)
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
    print(f'Total time: {elapsed_time:.2f} seconds', flush=True)
    print('=' * 70, flush=True)
