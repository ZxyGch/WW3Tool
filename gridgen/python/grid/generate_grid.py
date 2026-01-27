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
    from ..utils.compute_cellcorner import compute_cellcorner
except ImportError:
    from utils.compute_cellcorner import compute_cellcorner


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
    
    # Create cell structure (list of lists of dicts)
    cell = [[{'px': None, 'py': None, 'width': None, 'height': None}
             for _ in range(Nx)] for _ in range(Ny)]
    
    for j in range(1, Nx + 1):
        for k in range(1, Ny + 1):
            c1, c2, c3, c4, wdth, hgt = compute_cellcorner(x, y, j, k, Nx, Ny)
            cell[k - 1][j - 1]['px'] = np.array([c4[0], c1[0], c2[0], c3[0], c4[0]])
            cell[k - 1][j - 1]['py'] = np.array([c4[1], c1[1], c2[1], c3[1], c4[1]])
            cell[k - 1][j - 1]['width'] = wdth
            cell[k - 1][j - 1]['height'] = hgt
    
    # Get maximum cell dimensions
    all_widths = [cell[k][j]['width'] for k in range(Ny) for j in range(Nx)]
    all_heights = [cell[k][j]['height'] for k in range(Ny) for j in range(Nx)]
    dx = max(all_widths)
    dy = max(all_heights)
    
    # Determine dimensions and ranges of base bathymetry coords
    fname_base = os.path.join(ref_dir, f'{bathy_input}.nc')
    
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
        if lats < lats_base or lats > late_base or late < lats_base or late > late_base:
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
        
        # Pre-compute cell properties as numpy arrays for vectorization
        cell_widths = np.array([[cell[k][j]['width'] for j in range(Nx)] for k in range(Ny)])
        cell_heights = np.array([[cell[k][j]['height'] for j in range(Nx)] for k in range(Ny)])
        cell_px_min = np.array([[np.min(cell[k][j]['px']) for j in range(Nx)] for k in range(Ny)])
        cell_px_max = np.array([[np.max(cell[k][j]['px']) for j in range(Nx)] for k in range(Ny)])
        cell_py_min = np.array([[np.min(cell[k][j]['py']) for j in range(Nx)] for k in range(Ny)])
        cell_py_max = np.array([[np.max(cell[k][j]['py']) for j in range(Nx)] for k in range(Ny)])
        
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
            
            # Process in batches for progress reporting
            batch_size = max(1, n_avg // 20)
            last_progress = 0
            
            for idx in range(n_avg):
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
                    depth_tmp = depth_base[lat_start_idx:lat_end_idx + 1, lon_start_idx:lon_end_idx + 1]
                
                if depth_tmp.size == 0:
                    depth_sub[k, j] = dry
                else:
                    valid_depth = depth_tmp[depth_tmp <= cut_off]
                    if len(valid_depth) > 0:
                        ratio = len(valid_depth) / depth_tmp.size
                        if ratio > limit:
                            depth_sub[k, j] = np.mean(valid_depth)
                        else:
                            depth_sub[k, j] = dry
                    else:
                        depth_sub[k, j] = dry
                
                # Progress reporting
                progress = int((idx + 1) / n_avg * 100)
                if progress >= last_progress + 5:
                    last_progress = (progress // 5) * 5
                    total_progress = int((n_interp + idx + 1) / Nb * 100)
                    print(f'Completed {total_progress} per cent of the cells', flush=True)
        
        print('Completed 100 per cent of the cells', flush=True)
    
    return depth_sub
