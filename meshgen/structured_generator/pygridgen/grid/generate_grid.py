"""
Generate Grid Function

This function creates a 2D bathymetry data set from high resolution
"ETOPO1" or "ETOPO2" global bathymetry sets. Global bathymetry data
sets are assumed to be stored in NetCDF formats.

Copyright 2009 National Weather Service (NWS),
National Oceanic and Atmospheric Administration. All rights reserved.
Distributed with WAVEWATCH III

Last Update: 23-Oct-2012
"""

import os

import netCDF4
import numpy as np

try:
    from ..utils.compute_cellcorner import compute_cellcorner_grid
    from ..utils.parallel import chunk_ranges, describe_cpu_budget, resolve_workers, run_parallel
except ImportError:
    from utils.compute_cellcorner import compute_cellcorner_grid
    from utils.parallel import chunk_ranges, describe_cpu_budget, resolve_workers, run_parallel



def _integral_base(depth_base):
    """Return the base bathymetry as a plain int64 array, or None.

    Only *integer* base data qualifies (GEBCO and ETOPO1 store metres as
    int16).  Float bases are rejected even when their values happen to be
    whole numbers: ``np.mean`` accumulates a float32 array in float32, and a
    summed-area table would produce the exact mean instead — a different
    number in the last digits of the written bathymetry.  Those go through the
    per-cell loop, which is parallelised instead.

    ``None`` means the shortcut is not applicable and the caller must fall
    back to that loop.
    """
    db = depth_base
    if np.ma.isMaskedArray(db):
        if np.ma.getmaskarray(db).any():
            return None
        db = np.ma.getdata(db)
    db = np.asarray(db)
    if not np.issubdtype(db.dtype, np.integer):
        return None
    return db.astype(np.int64)



_AVG_STATE = {}


def _init_avg_state(state):
    _AVG_STATE.clear()
    _AVG_STATE.update(state)
    try:
        from ..utils.parallel import limit_worker_threads
    except ImportError:
        from utils.parallel import limit_worker_threads
    limit_worker_threads()


def _average_cells(task):
    """Average one slice of the averaging-cell list, cell by cell.

    Kept identical to the original loop body -- including doing the mean on
    the base array's own dtype -- because that rounding is visible in the
    written bathymetry.
    """
    start, stop = task
    st = _AVG_STATE
    depth_base = st['depth_base']
    avg_k = st['avg_k'][start:stop]
    avg_j = st['avg_j'][start:stop]
    lat_start_idx_all = st['lat_start_idx_all']
    lat_end_idx_all = st['lat_end_idx_all']
    lon_start_idx_all = st['lon_start_idx_all']
    lon_end_idx_all = st['lon_end_idx_all']
    cut_off = st['cut_off']
    limit = st['limit']
    dry = st['dry']

    out = np.empty(stop - start, dtype=float)
    for idx in range(stop - start):
        k, j = avg_k[idx], avg_j[idx]

        lon_start_idx = lon_start_idx_all[k, j]
        lon_end_idx = lon_end_idx_all[k, j]
        lat_start_idx = lat_start_idx_all[k, j]
        lat_end_idx = lat_end_idx_all[k, j]

        if lon_end_idx < lon_start_idx:
            depth_tmp = np.concatenate([
                depth_base[lat_start_idx:lat_end_idx + 1, lon_start_idx:],
                depth_base[lat_start_idx:lat_end_idx + 1, :lon_end_idx + 1]
            ], axis=1)
        else:
            depth_tmp = depth_base[lat_start_idx:lat_end_idx + 1,
                                   lon_start_idx:lon_end_idx + 1]

        if depth_tmp.size == 0:
            out[idx] = dry
            continue

        valid_depth = depth_tmp[depth_tmp <= cut_off]
        if len(valid_depth) > 0 and len(valid_depth) / depth_tmp.size > limit:
            out[idx] = np.mean(valid_depth)
        else:
            out[idx] = dry
    return start, stop, out

def _box_sum(sat, r0, r1, c0, c1):
    """Inclusive box sums over a summed-area table with a (1, 1) zero pad."""
    return (sat[r1 + 1, c1 + 1] - sat[r0, c1 + 1]
            - sat[r1 + 1, c0] + sat[r0, c0])


def _sat_average(depth_sub, depth_base, avg_k, avg_j,
                 lat_start_idx_all, lat_end_idx_all,
                 lon_start_idx_all, lon_end_idx_all,
                 cut_off, limit, dry):
    """Fill the averaging cells of ``depth_sub`` in one vectorised pass.

    Returns False when the shortcut does not apply, leaving ``depth_sub``
    untouched so the caller can run the original loop.
    """
    base = _integral_base(depth_base)
    if base is None:
        return False

    n_lat, n_lon = base.shape
    # Two int64 tables plus their int64 intermediates and the int64 base copy.
    if (n_lat + 1) * (n_lon + 1) * 40 > 8 * 1024 ** 3:
        print('  Base bathymetry too large for the summed-area shortcut.',
              flush=True)
        return False

    wet = base <= cut_off
    count_sat = np.zeros((n_lat + 1, n_lon + 1), dtype=np.int64)
    np.cumsum(np.cumsum(wet, axis=0, dtype=np.int64), axis=1,
              out=count_sat[1:, 1:])
    value_sat = np.zeros((n_lat + 1, n_lon + 1), dtype=np.int64)
    np.cumsum(np.cumsum(np.where(wet, base, 0), axis=0, dtype=np.int64), axis=1,
              out=value_sat[1:, 1:])
    del wet

    r0 = lat_start_idx_all[avg_k, avg_j].astype(np.intp)
    r1 = lat_end_idx_all[avg_k, avg_j].astype(np.intp)
    c0 = lon_start_idx_all[avg_k, avg_j].astype(np.intp)
    c1 = lon_end_idx_all[avg_k, avg_j].astype(np.intp)

    n_rows = r1 - r0 + 1
    empty = n_rows <= 0
    # Keep the index arithmetic in range for the empty rows too; they are
    # overwritten with ``dry`` at the end.
    r1_safe = np.where(empty, r0, r1)

    wrapped = c1 < c0
    c1_head = np.where(wrapped, n_lon - 1, c1)
    counts = _box_sum(count_sat, r0, r1_safe, c0, c1_head)
    values = _box_sum(value_sat, r0, r1_safe, c0, c1_head)
    n_cols = c1_head - c0 + 1

    if np.any(wrapped):
        c0_tail = np.zeros_like(c0)
        c1_tail = np.where(wrapped, c1, 0)
        tail_counts = _box_sum(count_sat, r0, r1_safe, c0_tail, c1_tail)
        tail_values = _box_sum(value_sat, r0, r1_safe, c0_tail, c1_tail)
        counts = counts + np.where(wrapped, tail_counts, 0)
        values = values + np.where(wrapped, tail_values, 0)
        n_cols = n_cols + np.where(wrapped, c1_tail + 1, 0)

    box_size = np.where(empty, 0, n_rows * n_cols)
    with np.errstate(invalid='ignore', divide='ignore'):
        ratio = np.where(box_size > 0, counts / np.maximum(box_size, 1), 0.0)
        mean = np.where(counts > 0, values / np.maximum(counts, 1), 0.0)

    keep = (box_size > 0) & (counts > 0) & (ratio > limit)
    depth_sub[avg_k, avg_j] = np.where(keep, mean, dry)
    return True

def generate_grid(type_grid, x, y, ref_dir, bathy_source, limit, cut_off, dry, *args):
    """
    Generate grid bathymetry from base bathymetry data.
    
    Parameters
    ----------
    type_grid : str
        Type of grid ('rect', 'curv', 'lamb')
    x : ndarray
        A 2D array specifying the longitudes of each cell
    y : ndarray
        A 2D array specifying the latitudes of each cell
    ref_dir : str
        PATH string to where the global reference bathymetry data sets
        are stored
    bathy_source : str
        String file to indicate which type of bathymetry is being used.
        Options: 'etopo1', 'etopo2', or custom name
    limit : float
        Value ranging between 0 and 1 indicating what fraction of a grid
        cell needs to be covered by wet cells (from the base grid) for
        the cell to be marked wet
    cut_off : float
        Cut_off depth to distinguish between dry and wet cells. All depths
        below the cut_off depth are marked wet
    dry : float
        Depth value assigned to the dry cells
    *args : tuple
        Optional string arrays for variable definition names for lon (x),
        lat (y) and depth respectively. If omitted default names are used.
        For etopo2.nc: 'x', 'y', 'z'
        For etopo1.nc: 'lon', 'lat', 'z'
    
    Returns
    -------
    depth_sub : ndarray
        A 2D array of dimensions (Ny, Nx) consisting of the grid depths
    """
    narg = len(args) + 8  # 8 required arguments
    
    # Determine if extra arguments present (requesting custom variable names)
    if narg == 11:  # Extra 3 arguments define the lat, lon and depth var names
        var_x = args[0]
        var_y = args[1]
        var_z = args[2]
        bathy_input = bathy_source
    elif narg == 8:
        bathy_input = 'none'
        # Use default variable names based on bathy_source
        if bathy_source.lower() == 'etopo1':
            var_x = 'lon'
            var_y = 'lat'
            var_z = 'z'
        elif bathy_source.lower() == 'etopo2':
            var_x = 'x'
            var_y = 'y'
            var_z = 'z'
        else:
            # Default to etopo1 naming
            var_x = 'lon'
            var_y = 'lat'
            var_z = 'z'
    elif narg < 8:
        raise ValueError('Too few input arguments')
    else:
        raise ValueError('Too many input arguments')
    
    # Initialize the corners of the grid domain and the depth values
    lats = np.min(y)
    lons = np.min(x)
    late = np.max(y)
    lone = np.max(x)
    
    # Convert 0~360 longitude format to -180~180 format if needed
    # This is needed because GEBCO and most bathymetry data use -180~180
    lon_converted = False
    if lons >= 0 and lone > 180:
        # User is using 0~360 format, convert to -180~180
        # For example: 130~200 becomes 130~180 and -180~-160
        # But for simplicity, we just convert values > 180 to negative
        x_converted = np.where(x > 180, x - 360, x)
        lons = np.min(x_converted)
        lone = np.max(x_converted)
        x = x_converted
        lon_converted = True
        print(f'  Converted longitude from 0~360 to -180~180 format: [{lons:.2f}, {lone:.2f}]', flush=True)
    
    depth_sub = np.zeros_like(x)
    
    # Compute cell corners
    Ny, Nx = x.shape
    
    # Cell corners for the whole grid at once.  The per-cell Python loop this
    # replaces was the single largest cost of this routine on fine grids, and
    # it also materialised a dict per cell (gigabytes at a few million cells).
    corners = compute_cellcorner_grid(x, y)
    cell_widths = corners['width']
    cell_heights = corners['height']
    cell_px_min = np.minimum.reduce([corners['c1x'], corners['c2x'],
                                     corners['c3x'], corners['c4x']])
    cell_px_max = np.maximum.reduce([corners['c1x'], corners['c2x'],
                                     corners['c3x'], corners['c4x']])
    cell_py_min = np.minimum.reduce([corners['c1y'], corners['c2y'],
                                     corners['c3y'], corners['c4y']])
    cell_py_max = np.maximum.reduce([corners['c1y'], corners['c2y'],
                                     corners['c3y'], corners['c4y']])
    del corners
    
    # Get maximum cell dimensions
    dx = float(np.max(cell_widths))
    dy = float(np.max(cell_heights))
    
    # Determine dimensions and ranges of base bathymetry coords
    fname_base = os.path.normpath(
        os.path.join(
            os.path.abspath(os.path.expanduser(str(ref_dir).strip())),
            f'{bathy_input}.nc',
        )
    )
    
    if not os.path.exists(fname_base):
        raise FileNotFoundError(f'Bathymetry file not found: {fname_base}')
    
    f = netCDF4.Dataset(fname_base, 'r')
    
    # Lambert conformal conic grid
    if type_grid == 'lamb':
        var_dep = f.variables[var_z]
        
        # Loop on the lat and lon
        # Get only the depth values which are in the lats late and lons lone
        depth_sub = np.zeros((Ny, Nx))
        for ilat in range(Ny):
            for ilon in range(Nx):
                depth_sub[ilat, ilon] = var_dep[ilon, ilat]
                if depth_sub[ilat, ilon] >= cut_off:
                    depth_sub[ilat, ilon] = dry
        f.close()
        
    elif type_grid in ['rect', 'curv']:
        var_lon = f.variables[var_x]
        var_lat = f.variables[var_y]
        var_dep = f.variables[var_z]
        
        # Get dimensions
        dim_lon = f.dimensions[var_x]
        dim_lat = f.dimensions[var_y]
        Nx_base = len(dim_lon)
        Ny_base = len(dim_lat)
        
        # Get actual range attributes
        try:
            lat_range = var_lat.actual_range
            lon_range = var_lon.actual_range
        except AttributeError:
            # If actual_range not available, compute from data
            lat_data = var_lat[:]
            lon_data = var_lon[:]
            lat_range = np.array([np.min(lat_data), np.max(lat_data)])
            lon_range = np.array([np.min(lon_data), np.max(lon_data)])
        
        dy_base = (lat_range[1] - lat_range[0]) / (Ny_base - 1)
        dx_base = (lon_range[1] - lon_range[0]) / (Nx_base - 1)
        
        lats_base = lat_range[0]
        late_base = lat_range[1]
        lons_base = lon_range[0]
        lone_base = lon_range[1]
        
        # Check if grid domain is within base bathymetry range
        # Allow slight overshoot at the poles due to dataset resolution
        lat_tolerance = 0.01  # Allow 0.01 degree tolerance
        lats_check = lats
        late_check = late
        # Clamp values that are very close to the boundary
        if lats < lats_base and lats >= -90.0 and lats_base > -89.999:
            lats_check = lats_base
        if late > late_base and late <= 90.0 and late_base < 89.999:
            late_check = late_base
        if lats_check < lats_base - lat_tolerance or lats_check > late_base + lat_tolerance or \
           late_check < lats_base - lat_tolerance or late_check > late_base + lat_tolerance:
            f.close()
            raise ValueError(f'Latitudes ({lats},{late}) beyond range ({lats_base},{late_base})')
        
        # For longitude, handle the wrap-around at 180/-180 degrees (date line)
        # Allow slight overshoot (e.g., 180.0 when base max is 179.997)
        lon_tolerance = 0.01  # Allow 0.01 degree tolerance
        lons_check = lons
        lone_check = lone
        
        # Clamp values that are very close to the boundary
        if lone > lone_base and lone <= 180.0 and lone_base > 179.0:
            lone_check = lone_base  # Clamp to max
        if lons < lons_base and lons >= -180.0 and lons_base < -179.0:
            lons_check = lons_base  # Clamp to min
            
        if lons_check < lons_base - lon_tolerance or lons_check > lone_base + lon_tolerance or \
           lone_check < lons_base - lon_tolerance or lone_check > lone_base + lon_tolerance:
            f.close()
            raise ValueError(f'Longitudes ({lons},{lone}) beyond range ({lons_base},{lone_base})')
        
        # Determine the starting and end points for extracting latitude data
        # from NETCDF
        # MATLAB: lat_start = floor(( (lats-2*dy) - lats_base)/dy_base);
        # MATLAB uses 1-based indexing for array access, but 0-based for netcdf.getVar
        lat_start = int(np.floor(((lats - 2 * dy) - lats_base) / dy_base))
        # MATLAB: if (lat_start < 1) lat_start = 1;
        # In MATLAB, lat_start < 1 means before first element (1-based)
        # In Python (0-based), this is lat_start < 0
        if lat_start < 0:
            lat_start = 0
        
        # MATLAB: lat_end = ceil(((late+2*dy) - lats_base)/dy_base) +1;
        lat_end = int(np.ceil(((late + 2 * dy) - lats_base) / dy_base)) + 1
        # MATLAB: if (lat_end > Ny_base) lat_end = Ny_base;
        # MATLAB uses 1-based indexing, so lat_end > Ny_base means beyond last element
        # In Python (0-based), this is lat_end > Ny_base (same check)
        if lat_end > Ny_base:
            lat_end = Ny_base
        
        # Determine the starting and end points for extracting longitude data
        # from NETCDF
        # MATLAB: lon_start = floor(((lons-2*dx) - lons_base)/dx_base);
        lon_start = int(np.floor(((lons - 2 * dx) - lons_base) / dx_base))
        # MATLAB: lon_end = ceil(((lone+2*dx) - lons_base)/dx_base) +1;
        lon_end = int(np.ceil(((lone + 2 * dx) - lons_base) / dx_base)) + 1
        
        # MATLAB: if (lon_start < 1) lon_start = 1;
        if lon_start < 0:
            lon_start = 0
        
        # MATLAB: if (lon_start > Nx_base) lon_start = Nx_base;
        # MATLAB uses 1-based indexing, so lon_start > Nx_base means beyond last element
        # In Python (0-based), this is lon_start >= Nx_base
        if lon_start >= Nx_base:
            lon_start = Nx_base - 1
        
        # MATLAB: if (lon_end < 1) lon_end = 1;
        if lon_end <= 0:
            lon_end = 1
        
        # MATLAB: if (lon_end >Nx_base) lon_end = Nx_base;
        if lon_end > Nx_base:
            lon_end = Nx_base
        
        # Extract data from NetCDF files
        print('read in the base bathymetry', flush=True)
        count_lat = lat_end - lat_start + 1
        
        # Validate count_lat
        if count_lat <= 0:
            f.close()
            raise ValueError(f'Invalid latitude range: lat_start={lat_start}, lat_end={lat_end}, Ny_base={Ny_base}')
        
        lat_base = var_lat[lat_start:lat_start + count_lat]
        
        if lon_end <= lon_start:
            # Handle wrap around
            # MATLAB: count_lon2 = (lon_end - 2) + 1 = lon_end - 1
            # Read from index 1 (MATLAB index 2, Python index 1) for count_lon2 elements
            count_lon1 = (Nx_base - lon_start) + 1
            count_lon2 = max(0, lon_end - 1)  # (lon_end - 2) + 1
            
            # Ensure count_lon1 doesn't exceed array bounds
            if lon_start + count_lon1 > len(var_lon):
                count_lon1 = len(var_lon) - lon_start
            
            if count_lon1 > 0 and lon_start < len(var_lon):
                lon1 = var_lon[lon_start:lon_start + count_lon1]
                # NetCDF dimension order is (lat, lon), so index as [lat, lon]
                dep1 = var_dep[lat_start:lat_start + count_lat, lon_start:lon_start + count_lon1]
            else:
                lon1 = np.array([])
                dep1 = np.array([]).reshape(count_lat, 0)
            
            if count_lon2 > 0 and count_lon2 < len(var_lon):
                # Start from index 1 (second element, MATLAB index 2)
                lon2 = var_lon[1:1 + count_lon2]
                # NetCDF dimension order is (lat, lon)
                dep2 = var_dep[lat_start:lat_start + count_lat, 1:1 + count_lon2]
            else:
                lon2 = np.array([])
                dep2 = np.array([]).reshape(count_lat, 0)
            
            if len(lon1) > 0 and len(lon2) > 0:
                lon_base = np.concatenate([lon1, lon2])
                # Concatenate along longitude axis (axis=1)
                depth_base = np.concatenate([dep1, dep2], axis=1)
            elif len(lon1) > 0:
                lon_base = lon1
                depth_base = dep1
            elif len(lon2) > 0:
                lon_base = lon2
                depth_base = dep2
            else:
                f.close()
                raise ValueError(f'Invalid longitude range: lon_start={lon_start}, lon_end={lon_end}, Nx_base={Nx_base}, count_lon1={count_lon1}, count_lon2={count_lon2}')
        else:
            count_lon = lon_end - lon_start + 1
            if count_lon <= 0:
                f.close()
                raise ValueError(f'Invalid longitude count: count_lon={count_lon}, lon_start={lon_start}, lon_end={lon_end}')
            lon_base = var_lon[lon_start:lon_start + count_lon]
            # Note: var_dep shape is (lat, lon) = (Ny, Nx)
            # So we need to index as [lat_start:lat_start+count_lat, lon_start:lon_start+count_lon]
            depth_base = var_dep[lat_start:lat_start + count_lat, lon_start:lon_start + count_lon]
        
        f.close()
        
        # Remove overlapped regions (occurs when longitudes wrap around)
        # MATLAB: [~,~,ib] = intersect(lon_base_tmp,lon_base);
        # intersect returns indices in lon_base where values from lon_base_tmp appear
        # In Python, we use unique with return_index to get first occurrence indices
        if len(lon_base) > 0 and depth_base.size > 0:
            # Check if depth_base has the expected shape
            if len(depth_base.shape) < 2 or depth_base.shape[1] == 0:
                f.close()
                raise ValueError(f'Invalid depth_base shape: {depth_base.shape}, expected (lat, lon) with lon > 0')
            
            lon_base_tmp, unique_positions = np.unique(lon_base, return_index=True)
            # unique_positions gives indices of first occurrence of each unique value
            # These are the indices we need to select from depth_base
            if len(unique_positions) > 0:
                # Ensure all indices are within bounds
                valid_mask = unique_positions < depth_base.shape[1]
                if np.any(valid_mask):
                    valid_indices = unique_positions[valid_mask]
                    depth_base_tmp = depth_base[:, valid_indices]
                    lon_base_tmp = lon_base_tmp[valid_mask]
                else:
                    # No valid indices, this shouldn't happen but handle gracefully
                    print(f'Warning: No valid indices found. lon_base len={len(lon_base)}, depth_base shape={depth_base.shape}', flush=True)
                    depth_base_tmp = depth_base
            else:
                depth_base_tmp = depth_base
        else:
            if len(lon_base) == 0:
                f.close()
                raise ValueError(f'No longitude data extracted: lon_start={lon_start}, lon_end={lon_end}, Nx_base={Nx_base}')
            lon_base_tmp = lon_base
            depth_base_tmp = depth_base
        
        lon_base = lon_base_tmp
        depth_base = depth_base_tmp
        
        # Obtaining data from base bathymetry. If desired grid is coarser than
        # base grid then 2D averaging of bathymetry, else grid is interpolated
        # from base grid.
        # Checks if grid cells wrap around in Longitudes. Does not do so for Latitudes
        
        Nb = Nx * Ny
        
        print('Generating grid bathymetry ....', flush=True)
        
        # Cell extents were already computed as arrays above.
        # Pre-compute ndx and ndy for all cells
        ndx_all = np.round(cell_widths / dx_base).astype(int)
        ndy_all = np.round(cell_heights / dy_base).astype(int)
        
        # Identify interpolation vs averaging cells
        interp_mask = (ndx_all <= 1) & (ndy_all <= 1)
        
        # Sort lat_base and lon_base for searchsorted (should already be sorted)
        lat_sorted = np.sort(lat_base) if not np.all(lat_base[:-1] <= lat_base[1:]) else lat_base
        lon_sorted = np.sort(lon_base) if not np.all(lon_base[:-1] <= lon_base[1:]) else lon_base
        
        # Pre-compute indices for all cells using searchsorted (vectorized)
        # For interpolation cells
        lon_prev_idx_all = np.searchsorted(lon_sorted, x, side='right') - 1
        lon_prev_idx_all = np.clip(lon_prev_idx_all, 0, len(lon_base) - 2)
        lon_next_idx_all = lon_prev_idx_all + 1
        
        lat_prev_idx_all = np.searchsorted(lat_sorted, y, side='right') - 1
        lat_prev_idx_all = np.clip(lat_prev_idx_all, 0, len(lat_base) - 2)
        lat_next_idx_all = lat_prev_idx_all + 1
        
        # For averaging cells - pre-compute bounding box indices
        lon_start_idx_all = np.searchsorted(lon_sorted, cell_px_min, side='right') - 1
        lon_start_idx_all = np.clip(lon_start_idx_all, 0, len(lon_base) - 1)
        lon_end_idx_all = np.searchsorted(lon_sorted, cell_px_max, side='left')
        lon_end_idx_all = np.clip(lon_end_idx_all, 0, len(lon_base) - 1)
        
        lat_start_idx_all = np.searchsorted(lat_sorted, cell_py_min, side='right') - 1
        lat_start_idx_all = np.clip(lat_start_idx_all, 0, len(lat_base) - 1)
        lat_end_idx_all = np.searchsorted(lat_sorted, cell_py_max, side='left')
        lat_end_idx_all = np.clip(lat_end_idx_all, 0, len(lat_base) - 1)
        
        den = dx_base * dy_base
        
        # ============================================================
        # FULLY VECTORIZED interpolation for ALL cells at once
        # This is MUCH faster than looping
        # ============================================================
        print('  Processing interpolation cells (vectorized)...', flush=True)
        
        # Get the 4 corner depths for bilinear interpolation (for all cells)
        a11 = depth_base[lat_prev_idx_all, lon_prev_idx_all]  # (Ny, Nx)
        a12 = depth_base[lat_prev_idx_all, lon_next_idx_all]
        a21 = depth_base[lat_next_idx_all, lon_prev_idx_all]
        a22 = depth_base[lat_next_idx_all, lon_next_idx_all]
        
        # Compute interpolation weights (vectorized)
        dx1 = np.abs(x - lon_base[lon_prev_idx_all])
        dx2 = dx_base - dx1
        dy1 = y - lat_base[lat_prev_idx_all]
        dy2 = dy_base - dy1
        
        # Bilinear interpolation (vectorized for all cells)
        depth_interp = (a11 * dy2 * dx2 + a12 * dy2 * dx1 + 
                        a21 * dy1 * dx2 + a22 * dx1 * dy1) / den
        
        # Apply to interpolation cells
        depth_sub[interp_mask] = depth_interp[interp_mask]
        depth_sub[interp_mask & (depth_sub >= cut_off)] = dry
        
        n_interp = np.sum(interp_mask)
        print(f'  Completed {n_interp} interpolation cells', flush=True)
        
        # ============================================================
        # Process averaging cells (need loop due to variable slice sizes)
        # ============================================================
        avg_mask = ~interp_mask
        n_avg = np.sum(avg_mask)
        
        if n_avg > 0:
            print(f'  Processing {n_avg} averaging cells...', flush=True)
            avg_k, avg_j = np.where(avg_mask)

            # Fast path: the wet-cell count and the wet-cell sum of every
            # averaging box are box queries on a summed-area table, so all the
            # cells can be answered at once instead of slicing per cell.  Only
            # taken when the base bathymetry is integer valued (ETOPO / GEBCO
            # are metres as integers), which keeps the sums exact.
            if _sat_average(depth_sub, depth_base, avg_k, avg_j,
                            lat_start_idx_all, lat_end_idx_all,
                            lon_start_idx_all, lon_end_idx_all,
                            cut_off, limit, dry):
                print('Completed 100 per cent of the cells', flush=True)
                return depth_sub

            print('  Base bathymetry is not integer typed; averaging cell by '
                  'cell across worker processes.', flush=True)

            n_workers = resolve_workers(n_avg, min_chunk=20_000)
            print(f'  Averaging on {n_workers} worker(s); {describe_cpu_budget()}',
                  flush=True)
            avg_state = {
                'depth_base': depth_base,
                'avg_k': avg_k, 'avg_j': avg_j,
                'lat_start_idx_all': lat_start_idx_all,
                'lat_end_idx_all': lat_end_idx_all,
                'lon_start_idx_all': lon_start_idx_all,
                'lon_end_idx_all': lon_end_idx_all,
                'cut_off': cut_off, 'limit': limit, 'dry': dry,
            }
            tasks = chunk_ranges(n_avg, max(n_workers * 4, 1))
            for start, stop, values in run_parallel(
                    _average_cells, tasks, n_workers,
                    initializer=_init_avg_state, initargs=(avg_state,)):
                depth_sub[avg_k[start:stop], avg_j[start:stop]] = values

        print('Completed 100 per cent of the cells', flush=True)
    
    return depth_sub
