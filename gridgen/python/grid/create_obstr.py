"""
Create Obstruction Function

This routine generates the 2D obstruction grid in x and y given a 2D
mask and set of boundary polygons. Obstructions are only generated for
wet cells and obstructions for cells on either side of a dry cell are
also set to 0 (to prevent spurious suppression of swell near the coast).
The routine allows for the possibility of curvilinear coordinates and
locally rotates the grid to align the coordinates in lat/lon space with
local p/q space which is determined by the 2D x and y matrices.

Copyright 2009 National Weather Service (NWS),
National Oceanic and Atmospheric Administration. All rights reserved.
Distributed with WAVEWATCH III

Last Update: 29-Mar-2013
"""

import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
from matplotlib.path import Path

try:
    from ..utils.compute_cellcorner import compute_cellcorner
except ImportError:
    from utils.compute_cellcorner import compute_cellcorner


def _process_wet_cell_batch(args):
    """Process a batch of wet cells (for parallel processing with reduced overhead)."""
    (cell_batch, cell_bounds, bnd_x, bnd_y, bnd_indx, bound_dict, bound_bboxes) = args
    
    results = []
    
    for k, j, cell_data in cell_batch:
        angle = cell_data['angle']
        x0 = cell_data['px'][0]
        y0 = cell_data['py'][0]
        px = cell_data['px']
        py = cell_data['py']
        cell_width = cell_data['width']
        cell_height = cell_data['height']
        
        cell_min_x = cell_bounds[k, j, 0]
        cell_max_x = cell_bounds[k, j, 1]
        cell_min_y = cell_bounds[k, j, 2]
        cell_max_y = cell_bounds[k, j, 3]
        
        # Fast bounding box pre-filter
        margin = max(cell_width, cell_height) * 0.1
        bbox_mask = ((bnd_x >= cell_min_x - margin) & (bnd_x <= cell_max_x + margin) &
                     (bnd_y >= cell_min_y - margin) & (bnd_y <= cell_max_y + margin))
        
        candidate_indices = np.where(bbox_mask)[0]
        
        if len(candidate_indices) == 0:
            results.append((k, j, 0, []))
            continue
        
        candidate_x = bnd_x[candidate_indices]
        candidate_y = bnd_y[candidate_indices]
        candidate_bnd_indx = bnd_indx[candidate_indices]
        
        # Ensure polygon is closed
        if px[0] != px[-1] or py[0] != py[-1]:
            px_cell = np.append(px[:4], px[0])
            py_cell = np.append(py[:4], py[0])
        else:
            px_cell = px
            py_cell = py
        
        cell_path = Path(np.column_stack([px_cell, py_cell]))
        points = np.column_stack([candidate_x, candidate_y])
        radius_tolerance = max(cell_width, cell_height) * 1e-2
        radius_tolerance = max(radius_tolerance, 1e-5)
        in_box = cell_path.contains_points(points, radius=radius_tolerance)
        bnds = np.unique(candidate_bnd_indx[in_box])
        Nbnds = len(bnds)
        
        # Process boundaries - optimized: reuse contains_points results
        cell_results = []
        RM = np.array([
            [np.cos(angle), -np.sin(angle)],
            [np.sin(angle), np.cos(angle)]
        ])
        
        # Process boundaries - optimized: use pre-computed bounding boxes
        for indx_bnd in bnds:
            # Quick bounding box check using pre-computed values
            bbox = bound_bboxes[indx_bnd]
            if (bbox['max_x'] < cell_min_x or bbox['min_x'] > cell_max_x or
                bbox['max_y'] < cell_min_y or bbox['min_y'] > cell_max_y):
                continue
            
            # Use pre-extracted boundary data
            bound_x_data = bound_dict[indx_bnd]['x']
            bound_y_data = bound_dict[indx_bnd]['y']
            
            # Only call contains_points if bounding boxes intersect
            bound_points = np.column_stack([bound_x_data, bound_y_data])
            in_box2 = cell_path.contains_points(bound_points, radius=radius_tolerance)
            in_box_coords = np.where(in_box2)[0]
            
            if len(in_box_coords) > 0:
                xt = bound_x_data[in_box_coords]
                yt = bound_y_data[in_box_coords]
                
                tmp = np.column_stack([xt - x0, yt - y0]) @ RM
                xt = tmp[:, 0]
                yt = tmp[:, 1]
                
                south_limit = max(0.0, min(1.0, np.min(yt) / cell_height))
                north_limit = max(0.0, min(1.0, np.max(yt) / cell_height))
                west_limit = max(0.0, min(1.0, np.min(xt) / cell_width))
                east_limit = max(0.0, min(1.0, np.max(xt) / cell_width))
                
                cell_results.append({
                    'indx_bnd': int(indx_bnd),
                    'south_lim': south_limit,
                    'north_lim': north_limit,
                    'west_lim': west_limit,
                    'east_lim': east_limit
                })
        
        results.append((k, j, Nbnds, cell_results))
    
    return results


def create_obstr(x, y, bound, mask, offset_left, offset_right):
    """
    Generate 2D obstruction grids in x and y directions.
    
    Parameters
    ----------
    x : ndarray
        A 2D array specifying the longitudes of each cell
    y : ndarray
        A 2D array specifying the latitudes of each cell
    bound : list
        Data structure array (list of dicts) of boundary polygons.
        Each dict should have keys: 'x', 'y', 'n', etc.
    mask : ndarray
        2D array of size (Ny, Nx) that determines land/sea mask
        (1=wet, 0=dry)
    offset_left : int
        Flag to determine if neighbor to the left/down in x/y should
        be considered. (0/1 = no/yes)
    offset_right : int
        Similar for neighbor to the right/up in x/y
    
    Returns
    -------
    sx : ndarray
        2D obstruction grid of size (Ny, Nx) for obstructions in x.
        Values range from 0 for no obstruction to 1 for full obstruction
    sy : ndarray
        2D obstruction grid of size (Ny, Nx) for obstructions in y.
        Values range from 0 for no obstruction to 1 for full obstruction
    """
    # Initialize variables
    Ny, Nx = x.shape
    sx = np.zeros((Ny, Nx))
    sy = np.zeros((Ny, Nx))
    
    loc = np.where(mask == 0)
    sx[loc] = 0
    sy[loc] = 0
    
    # Create cell structure (list of lists of dicts)
    cell = [[{
        'px': None, 'py': None, 'angle': None, 'width': None, 'height': None,
        'nx': 0, 'ny': 0, 'south_lim': [], 'north_lim': [], 'east_lim': [],
        'west_lim': [], 'bndx': [], 'bndy': []
    } for _ in range(Nx)] for _ in range(Ny)]
    
    cell_bnd = mask.copy()
    
    loc_wet = np.where(mask != 0)
    N_wet = len(loc_wet[0])
    Nb = Nx * Ny
    
    print(f' Total Number of cells = {Nb}', flush=True)
    print(f'   Number of wet cells = {N_wet}', flush=True)
    
    # Set up the cells
    for j in range(1, Nx + 1):
        for k in range(1, Ny + 1):
            c1, c2, c3, c4, wdth, hgt = compute_cellcorner(x, y, j, k, Nx, Ny)
            
            cell[k - 1][j - 1]['px'] = np.array([c4[0], c1[0], c2[0], c3[0], c4[0]])
            cell[k - 1][j - 1]['py'] = np.array([c4[1], c1[1], c2[1], c3[1], c4[1]])
            cell[k - 1][j - 1]['angle'] = np.arctan2(c1[1] - c4[1], c1[0] - c4[0])
            cell[k - 1][j - 1]['width'] = wdth
            cell[k - 1][j - 1]['height'] = hgt
            cell[k - 1][j - 1]['nx'] = 0
            cell[k - 1][j - 1]['ny'] = 0
            cell[k - 1][j - 1]['south_lim'] = []
            cell[k - 1][j - 1]['north_lim'] = []
            cell[k - 1][j - 1]['east_lim'] = []
            cell[k - 1][j - 1]['west_lim'] = []
            cell[k - 1][j - 1]['bndx'] = []
            cell[k - 1][j - 1]['bndy'] = []
    
    N = len(bound)
    
    # Preparing the boundaries
    print('Preparing the boundaries', flush=True)
    itmp = 0
    
    bnd_x = []
    bnd_y = []
    bnd_indx = []
    
    for i in range(N):
        bnd_x.extend(bound[i]['x'])
        bnd_y.extend(bound[i]['y'])
        bnd_indx.extend([i] * bound[i]['n'])
        
        itmp_prev = itmp
        itmp = int(i / N * 100)
        if (itmp % 10 == 0) and (itmp_prev != itmp):
            print(f' Completed {itmp} per cent of boundaries', flush=True)
    
    bnd_x = np.array(bnd_x)
    bnd_y = np.array(bnd_y)
    bnd_indx = np.array(bnd_indx)
    
    # Pre-compute cell bounding boxes for fast filtering (vectorized)
    print('Pre-computing cell bounding boxes for fast filtering...', flush=True)
    # Extract all px and py arrays at once
    all_px = np.array([[cell[k][j]['px'] for j in range(Nx)] for k in range(Ny)])  # (Ny, Nx, 5)
    all_py = np.array([[cell[k][j]['py'] for j in range(Nx)] for k in range(Ny)])  # (Ny, Nx, 5)
    cell_bounds = np.zeros((Ny, Nx, 4))  # [min_x, max_x, min_y, max_y]
    cell_bounds[:, :, 0] = np.min(all_px, axis=2)
    cell_bounds[:, :, 1] = np.max(all_px, axis=2)
    cell_bounds[:, :, 2] = np.min(all_py, axis=2)
    cell_bounds[:, :, 3] = np.max(all_py, axis=2)
    
    # Loop through the wet cells and determine the boundaries that are within
    print('Loop through the wet cells to identify boundaries', flush=True)
    
    # Use multiprocessing for parallel execution
    n_workers = max(1, mp.cpu_count())
    batch_size = max(50, N_wet // (n_workers * 8))  # Smaller batches for better load balancing
    print(f'  Using {n_workers} workers, batch size {batch_size}...', flush=True)
    
    # Pre-extract boundary data to reduce serialization overhead
    print('  Preparing data for parallel processing...', flush=True)
    bound_dict = {}
    bound_bboxes = {}  # Pre-compute bounding boxes for faster filtering
    for i in range(len(bound)):
        bound_x = np.array(bound[i]['x'])
        bound_y = np.array(bound[i]['y'])
        bound_dict[i] = {
            'x': bound_x,
            'y': bound_y
        }
        # Pre-compute bounding box for each boundary
        bound_bboxes[i] = {
            'min_x': np.min(bound_x),
            'max_x': np.max(bound_x),
            'min_y': np.min(bound_y),
            'max_y': np.max(bound_y)
        }
    
    # Prepare cell batches for parallel processing
    print('  Creating cell batches...', flush=True)
    cell_batches = []
    current_batch = []
    for indx_wet in range(N_wet):
        k = loc_wet[0][indx_wet]
        j = loc_wet[1][indx_wet]
        
        cell_data = {
            'angle': cell[k][j]['angle'],
            'px': np.array(cell[k][j]['px']),
            'py': np.array(cell[k][j]['py']),
            'width': cell[k][j]['width'],
            'height': cell[k][j]['height']
        }
        
        current_batch.append((k, j, cell_data))
        
        if len(current_batch) >= batch_size:
            cell_batches.append(current_batch)
            current_batch = []
    
    if current_batch:
        cell_batches.append(current_batch)
    
    print(f'  Created {len(cell_batches)} batches, starting parallel processing...', flush=True)
    
    # Process batches in parallel
    completed = 0
    last_progress = 0
    
    executor = None
    try:
        executor = ProcessPoolExecutor(max_workers=n_workers)
        # Submit all batch tasks
        print(f'  Submitting {len(cell_batches)} batch tasks to {n_workers} workers...', flush=True)
        futures = [executor.submit(_process_wet_cell_batch, 
                                   (batch, cell_bounds, bnd_x, bnd_y, bnd_indx, bound_dict, bound_bboxes))
                   for batch in cell_batches]
        
        print(f'  All tasks submitted, collecting results...', flush=True)
        
        # Collect results as they complete
        for future in as_completed(futures):
            try:
                batch_results = future.result()
                
                for k, j, Nbnds, results in batch_results:
                    cell_bnd[k, j] = Nbnds
                    
                    # Update cell data with results
                    for result in results:
                        indx_bnd = result['indx_bnd']
                        south_limit = result['south_lim']
                        north_limit = result['north_lim']
                        west_limit = result['west_lim']
                        east_limit = result['east_lim']
                        
                        # Store x-direction boundary
                        cell[k][j]['nx'] = cell[k][j]['nx'] + 1
                        if not isinstance(cell[k][j]['south_lim'], list):
                            cell[k][j]['south_lim'] = []
                        if not isinstance(cell[k][j]['north_lim'], list):
                            cell[k][j]['north_lim'] = []
                        if not isinstance(cell[k][j]['bndx'], list):
                            cell[k][j]['bndx'] = []
                        
                        cell[k][j]['south_lim'].append(south_limit)
                        cell[k][j]['north_lim'].append(north_limit)
                        cell[k][j]['bndx'].append(indx_bnd)
                        
                        # Store y-direction boundary
                        cell[k][j]['ny'] = cell[k][j]['ny'] + 1
                        if not isinstance(cell[k][j]['east_lim'], list):
                            cell[k][j]['east_lim'] = []
                        if not isinstance(cell[k][j]['west_lim'], list):
                            cell[k][j]['west_lim'] = []
                        if not isinstance(cell[k][j]['bndy'], list):
                            cell[k][j]['bndy'] = []
                        
                        cell[k][j]['east_lim'].append(east_limit)
                        cell[k][j]['west_lim'].append(west_limit)
                        cell[k][j]['bndy'].append(indx_bnd)
                    
                    completed += 1
                    progress = int(completed / N_wet * 100)
                    if progress >= last_progress + 5:
                        last_progress = (progress // 5) * 5
                        print(f' Completed {last_progress} per cent', flush=True)
            except Exception as e:
                print(f'  Warning: Error processing batch: {e}', flush=True)
                import traceback
                traceback.print_exc()
    finally:
        # Explicitly shutdown the executor to ensure all processes are closed
        if executor is not None:
            print('  Shutting down worker processes...', flush=True)
            executor.shutdown(wait=True, cancel_futures=False)
            print('  Worker processes closed.', flush=True)
    
    
    # Loop through all the wet cells with boundaries and move boundary segments
    # that are part of the same boundary and cross neighboring cells
    loc_bnd = np.where(cell_bnd != 0)
    N_bnd = len(loc_bnd[0])
    row_bnd = loc_bnd[0]
    column_bnd = loc_bnd[1]
    
    print(f'Number of wet cells enclosing boundaries = {N_bnd}', flush=True)
    
    # First loop: Merge boundaries that cross neighboring cells
    for indx_bnd in range(N_bnd):
        j = column_bnd[indx_bnd]
        k = row_bnd[indx_bnd]
        
        # Check neighbors in x direction
        if j < Nx - 1:
            jj = j + 1
            
            if cell[k][j]['nx'] != 0 and cell[k][jj]['nx'] != 0:
                # Save information to temporary variables (MATLAB style)
                set1 = {
                    'nx': cell[k][j]['nx'],
                    'bndx': cell[k][j]['bndx'].copy(),
                    'north_lim': cell[k][j]['north_lim'].copy(),
                    'south_lim': cell[k][j]['south_lim'].copy()
                }
                set2 = {
                    'nx': cell[k][jj]['nx'],
                    'bndx': cell[k][jj]['bndx'].copy(),
                    'north_lim': cell[k][jj]['north_lim'].copy(),
                    'south_lim': cell[k][jj]['south_lim'].copy()
                }
                found_common = False
                
                # Loop through boundary segments and move segments
                # of common boundaries to the cell with the larger segment
                for l in range(set1['nx']):
                    for m in range(set2['nx']):
                        if set1['bndx'][l] == set2['bndx'][m]:
                            seg1_len = set1['north_lim'][l] - set1['south_lim'][l]
                            seg2_len = set2['north_lim'][m] - set2['south_lim'][m]
                            
                            if seg1_len >= seg2_len:
                                # Merge into set1
                                set1['north_lim'][l] = max(set1['north_lim'][l], set2['north_lim'][m])
                                set1['south_lim'][l] = min(set1['south_lim'][l], set2['south_lim'][m])
                                # Remove from set2 by shifting elements
                                for n in range(m + 1, set2['nx']):
                                    set2['bndx'][n - 1] = set2['bndx'][n]
                                    set2['north_lim'][n - 1] = set2['north_lim'][n]
                                    set2['south_lim'][n - 1] = set2['south_lim'][n]
                                set2['nx'] -= 1
                            else:
                                # Merge into set2
                                set2['north_lim'][m] = max(set1['north_lim'][l], set2['north_lim'][m])
                                set2['south_lim'][m] = min(set1['south_lim'][l], set2['south_lim'][m])
                                # Remove from set1 by shifting elements
                                for n in range(l + 1, set1['nx']):
                                    set1['bndx'][n - 1] = set1['bndx'][n]
                                    set1['north_lim'][n - 1] = set1['north_lim'][n]
                                    set1['south_lim'][n - 1] = set1['south_lim'][n]
                                set1['nx'] -= 1
                            
                            found_common = True
                            break
                    
                    if found_common:
                        break
                
                # Write cell information back from temporary variables
                # if common boundaries were found
                if found_common:
                    cell[k][j]['bndx'] = set1['bndx'][:set1['nx']]
                    cell[k][j]['north_lim'] = set1['north_lim'][:set1['nx']]
                    cell[k][j]['south_lim'] = set1['south_lim'][:set1['nx']]
                    cell[k][j]['nx'] = set1['nx']
                    
                    cell[k][jj]['bndx'] = set2['bndx'][:set2['nx']]
                    cell[k][jj]['north_lim'] = set2['north_lim'][:set2['nx']]
                    cell[k][jj]['south_lim'] = set2['south_lim'][:set2['nx']]
                    cell[k][jj]['nx'] = set2['nx']
        
        # Check neighbors in y direction
        if k < Ny - 1:
            kk = k + 1
            
            if cell[k][j]['ny'] != 0 and cell[kk][j]['ny'] != 0:
                # Save information to temporary variables
                set1 = {
                    'ny': cell[k][j]['ny'],
                    'bndy': cell[k][j]['bndy'].copy(),
                    'east_lim': cell[k][j]['east_lim'].copy(),
                    'west_lim': cell[k][j]['west_lim'].copy()
                }
                set2 = {
                    'ny': cell[kk][j]['ny'],
                    'bndy': cell[kk][j]['bndy'].copy(),
                    'east_lim': cell[kk][j]['east_lim'].copy(),
                    'west_lim': cell[kk][j]['west_lim'].copy()
                }
                found_common = False
                
                for l in range(set1['ny']):
                    for m in range(set2['ny']):
                        if set1['bndy'][l] == set2['bndy'][m]:
                            seg1_len = set1['east_lim'][l] - set1['west_lim'][l]
                            seg2_len = set2['east_lim'][m] - set2['west_lim'][m]
                            
                            if seg1_len >= seg2_len:
                                set1['east_lim'][l] = max(set1['east_lim'][l], set2['east_lim'][m])
                                set1['west_lim'][l] = min(set1['west_lim'][l], set2['west_lim'][m])
                                # Remove from set2 by shifting
                                for n in range(m + 1, set2['ny']):
                                    set2['bndy'][n - 1] = set2['bndy'][n]
                                    set2['east_lim'][n - 1] = set2['east_lim'][n]
                                    set2['west_lim'][n - 1] = set2['west_lim'][n]
                                set2['ny'] -= 1
                            else:
                                set2['east_lim'][m] = max(set1['east_lim'][l], set2['east_lim'][m])
                                set2['west_lim'][m] = min(set1['west_lim'][l], set2['west_lim'][m])
                                # Remove from set1 by shifting
                                for n in range(l + 1, set1['ny']):
                                    set1['bndy'][n - 1] = set1['bndy'][n]
                                    set1['east_lim'][n - 1] = set1['east_lim'][n]
                                    set1['west_lim'][n - 1] = set1['west_lim'][n]
                                set1['ny'] -= 1
                            
                            found_common = True
                            break
                    
                    if found_common:
                        break
                
                # Write cell information back
                if found_common:
                    cell[k][j]['bndy'] = set1['bndy'][:set1['ny']]
                    cell[k][j]['east_lim'] = set1['east_lim'][:set1['ny']]
                    cell[k][j]['west_lim'] = set1['west_lim'][:set1['ny']]
                    cell[k][j]['ny'] = set1['ny']
                    
                    cell[kk][j]['bndy'] = set2['bndy'][:set2['ny']]
                    cell[kk][j]['east_lim'] = set2['east_lim'][:set2['ny']]
                    cell[kk][j]['west_lim'] = set2['west_lim'][:set2['ny']]
                    cell[kk][j]['ny'] = set2['ny']
    
    # Second loop: Remove overlapping segments within each cell
    for indx_bnd in range(N_bnd):
        j = column_bnd[indx_bnd]
        k = row_bnd[indx_bnd]
        
        # Process x-direction segments
        if cell[k][j]['nx'] > 1:
            n_segs = cell[k][j]['nx']
            baseseg_n = cell[k][j]['north_lim'].copy()
            baseseg_s = cell[k][j]['south_lim'].copy()
            cell[k][j]['north_lim'] = []
            cell[k][j]['south_lim'] = []
            ind_segs = 0
            indseg_n = []
            indseg_s = []
            
            while n_segs > 0:
                overlap_found = False
                if n_segs > 1:
                    for l in range(1, n_segs):
                        if baseseg_n[0] >= baseseg_s[l] and baseseg_s[0] <= baseseg_n[l]:
                            # Overlap found, merge
                            baseseg_n[0] = max(baseseg_n[0], baseseg_n[l])
                            baseseg_s[0] = min(baseseg_s[0], baseseg_s[l])
                            overlap_found = True
                            # Remove segment l
                            if l == n_segs - 1:
                                n_segs -= 1
                            else:
                                for m in range(l + 1, n_segs):
                                    baseseg_n[m - 1] = baseseg_n[m]
                                    baseseg_s[m - 1] = baseseg_s[m]
                                n_segs -= 1
                            break
                
                if n_segs == 1:
                    ind_segs += 1
                    indseg_n.append(baseseg_n[0])
                    indseg_s.append(baseseg_s[0])
                    n_segs = 0
                else:
                    if not overlap_found:
                        ind_segs += 1
                        indseg_n.append(baseseg_n[0])
                        indseg_s.append(baseseg_s[0])
                        for l in range(1, n_segs):
                            baseseg_n[l - 1] = baseseg_n[l]
                            baseseg_s[l - 1] = baseseg_s[l]
                        n_segs -= 1
            
            cell[k][j]['nx'] = ind_segs
            cell[k][j]['north_lim'] = indseg_n
            cell[k][j]['south_lim'] = indseg_s
        
        # Process y-direction segments
        if cell[k][j]['ny'] > 1:
            n_segs = cell[k][j]['ny']
            baseseg_n = cell[k][j]['east_lim'].copy()
            baseseg_s = cell[k][j]['west_lim'].copy()
            cell[k][j]['east_lim'] = []
            cell[k][j]['west_lim'] = []
            ind_segs = 0
            indseg_n = []
            indseg_s = []
            
            while n_segs > 0:
                overlap_found = False
                if n_segs > 1:
                    for l in range(1, n_segs):
                        if baseseg_n[0] >= baseseg_s[l] and baseseg_s[0] <= baseseg_n[l]:
                            baseseg_n[0] = max(baseseg_n[0], baseseg_n[l])
                            baseseg_s[0] = min(baseseg_s[0], baseseg_s[l])
                            overlap_found = True
                            if l == n_segs - 1:
                                n_segs -= 1
                            else:
                                for m in range(l + 1, n_segs):
                                    baseseg_n[m - 1] = baseseg_n[m]
                                    baseseg_s[m - 1] = baseseg_s[m]
                                n_segs -= 1
                            break
                
                if n_segs == 1:
                    ind_segs += 1
                    indseg_n.append(baseseg_n[0])
                    indseg_s.append(baseseg_s[0])
                    n_segs = 0
                else:
                    if not overlap_found:
                        ind_segs += 1
                        indseg_n.append(baseseg_n[0])
                        indseg_s.append(baseseg_s[0])
                        for l in range(1, n_segs):
                            baseseg_n[l - 1] = baseseg_n[l]
                            baseseg_s[l - 1] = baseseg_s[l]
                        n_segs -= 1
            
            cell[k][j]['ny'] = ind_segs
            cell[k][j]['east_lim'] = indseg_n
            cell[k][j]['west_lim'] = indseg_s
    
    # Final loop: Construct obstruction grids accounting for neighboring cells
    # Track statistics before neighbor check
    sx_before_neighbor = np.zeros((Ny, Nx))
    sy_before_neighbor = np.zeros((Ny, Nx))
    cells_with_sx_before = 0
    cells_with_sy_before = 0
    cells_with_nx_but_no_sx = 0  # Cells with nx>0 but sx=0 (no_boundary=True or shadow removal)
    cells_with_ny_but_no_sy = 0  # Cells with ny>0 but sy=0 (no_boundary=True or shadow removal)
    
    for indx_bnd in range(N_bnd):
        j = column_bnd[indx_bnd]
        k = row_bnd[indx_bnd]
        
        # Computing x obstruction
        if cell[k][j]['nx'] != 0:
            # MATLAB: n_segs = cell(k,j).nx;
            # MATLAB: baseseg_n = cell(k,j).north_lim;
            # MATLAB: baseseg_s = cell(k,j).south_lim;
            n_segs = cell[k][j]['nx']
            baseseg_n = np.array(cell[k][j]['north_lim'])
            baseseg_s = np.array(cell[k][j]['south_lim'])
            
            no_boundary = False
            
            # Compare with left neighbors
            for off in range(1, offset_left + 1):
                jj = j - off
                if jj >= 0:
                    if cell[k][jj]['nx'] != 0:
                        set1 = {
                            'nx': cell[k][jj]['nx'],
                            'north_lim': cell[k][jj]['north_lim'].copy(),
                            'south_lim': cell[k][jj]['south_lim'].copy()
                        }
                        
                        # Remove segments in shadow of previous cell
                        shadow_flags = np.zeros(n_segs, dtype=bool)
                        for m in range(n_segs):
                            for l in range(set1['nx']):
                                if (set1['north_lim'][l] >= baseseg_n[m] and
                                    set1['south_lim'][l] <= baseseg_s[m]):
                                    shadow_flags[m] = True
                                    break
                        
                        loc = np.where(~shadow_flags)[0]
                        if len(loc) == 0:
                            no_boundary = True
                            n_segs = 0
                            baseseg_n = np.array([])
                            baseseg_s = np.array([])
                        elif len(loc) < n_segs:
                            baseseg_n = baseseg_n[loc]
                            baseseg_s = baseseg_s[loc]
                            n_segs = len(baseseg_n)
                        
                        # Remove segments from previous cell that are shadows
                        if not no_boundary:
                            shadow_flags2 = np.zeros(set1['nx'], dtype=bool)
                            for m in range(set1['nx']):
                                for l in range(n_segs):
                                    if (set1['north_lim'][m] <= baseseg_n[l] and
                                        set1['south_lim'][m] >= baseseg_s[l]):
                                        shadow_flags2[m] = True
                                        break
                            
                            loc2 = np.where(~shadow_flags2)[0]
                            if len(loc2) > 0 and len(loc2) < set1['nx']:
                                set1['north_lim'] = [set1['north_lim'][idx] for idx in loc2]
                                set1['south_lim'] = [set1['south_lim'][idx] for idx in loc2]
                                set1['nx'] = len(loc2)
                            
                            # Add remaining segments from previous cell
                            if set1['nx'] > 0:
                                n_segs += set1['nx']
                                baseseg_n = np.append(baseseg_n, set1['north_lim'])
                                baseseg_s = np.append(baseseg_s, set1['south_lim'])
            
            # Compare with right neighbors
            if not no_boundary:
                for off in range(1, offset_right + 1):
                    jj = j + off
                    if jj < Nx:
                        if cell[k][jj]['nx'] != 0:
                            set1 = {
                                'nx': cell[k][jj]['nx'],
                                'north_lim': cell[k][jj]['north_lim'].copy(),
                                'south_lim': cell[k][jj]['south_lim'].copy()
                            }
                            
                            shadow_flags = np.zeros(n_segs, dtype=bool)
                            for m in range(n_segs):
                                for l in range(set1['nx']):
                                    if (set1['north_lim'][l] >= baseseg_n[m] and
                                        set1['south_lim'][l] <= baseseg_s[m]):
                                        shadow_flags[m] = True
                                        break
                            
                            loc = np.where(~shadow_flags)[0]
                            if len(loc) == 0:
                                no_boundary = True
                                n_segs = 0
                                baseseg_n = np.array([])
                                baseseg_s = np.array([])
                            elif len(loc) < n_segs:
                                baseseg_n = baseseg_n[loc]
                                baseseg_s = baseseg_s[loc]
                                n_segs = len(baseseg_n)
                            
                            if not no_boundary:
                                shadow_flags2 = np.zeros(set1['nx'], dtype=bool)
                                for m in range(set1['nx']):
                                    for l in range(n_segs):
                                        if (set1['north_lim'][m] <= baseseg_n[l] and
                                            set1['south_lim'][m] >= baseseg_s[l]):
                                            shadow_flags2[m] = True
                                            break
                                
                                loc2 = np.where(~shadow_flags2)[0]
                                if len(loc2) > 0 and len(loc2) < set1['nx']:
                                    set1['north_lim'] = [set1['north_lim'][idx] for idx in loc2]
                                    set1['south_lim'] = [set1['south_lim'][idx] for idx in loc2]
                                    set1['nx'] = len(loc2)
                                
                                if set1['nx'] > 0:
                                    n_segs += set1['nx']
                                    baseseg_n = np.append(baseseg_n, set1['north_lim'])
                                    baseseg_s = np.append(baseseg_s, set1['south_lim'])
            
            # Build obstruction grid from total set of segments
            if not no_boundary:
                # MATLAB: sx(k,j) is initialized to 0, so we start from 0
                sx[k, j] = 0.0
                
                if n_segs == 1:
                    sx[k, j] = baseseg_n[0] - baseseg_s[0]
                else:
                    # Remove overlapping segments
                    ind_segs = 0
                    indseg_n = []
                    indseg_s = []
                    
                    # Convert to list for easier manipulation
                    baseseg_n_list = baseseg_n.tolist() if isinstance(baseseg_n, np.ndarray) else list(baseseg_n)
                    baseseg_s_list = baseseg_s.tolist() if isinstance(baseseg_s, np.ndarray) else list(baseseg_s)
                    n_segs = len(baseseg_n_list)
                    
                    while n_segs > 0:
                        overlap_found = False
                        if n_segs > 1:
                            for l in range(1, n_segs):
                                if baseseg_n_list[0] >= baseseg_s_list[l] and baseseg_s_list[0] <= baseseg_n_list[l]:
                                    # Overlap found, merge
                                    baseseg_n_list[0] = max(baseseg_n_list[0], baseseg_n_list[l])
                                    baseseg_s_list[0] = min(baseseg_s_list[0], baseseg_s_list[l])
                                    overlap_found = True
                                    # Remove segment l
                                    if l == n_segs - 1:
                                        n_segs -= 1
                                    else:
                                        for m in range(l + 1, n_segs):
                                            baseseg_n_list[m - 1] = baseseg_n_list[m]
                                            baseseg_s_list[m - 1] = baseseg_s_list[m]
                                        n_segs -= 1
                                    break
                        
                        if n_segs == 1:
                            ind_segs += 1
                            indseg_n.append(baseseg_n_list[0])
                            indseg_s.append(baseseg_s_list[0])
                            n_segs = 0
                        else:
                            if not overlap_found:
                                ind_segs += 1
                                indseg_n.append(baseseg_n_list[0])
                                indseg_s.append(baseseg_s_list[0])
                                for l in range(1, n_segs):
                                    baseseg_n_list[l - 1] = baseseg_n_list[l]
                                    baseseg_s_list[l - 1] = baseseg_s_list[l]
                                n_segs -= 1
                    
                    # Compute obstruction values from independent segments
                    # MATLAB: for l = 1:ind_segs, sx(k,j) = sx(k,j) + (indseg_n(l)-indseg_s(l)); end
                    for l in range(ind_segs):
                        sx[k, j] += (indseg_n[l] - indseg_s[l])
                    
                    # Clamp to [0, 1] range (MATLAB doesn't explicitly clamp, but values should be in [0,1])
                    sx[k, j] = max(0.0, min(1.0, sx[k, j]))
            
            # Record value before neighbor check (regardless of no_boundary)
            sx_before_neighbor[k, j] = sx[k, j]
            if sx[k, j] > 0:
                cells_with_sx_before += 1
            elif cell[k][j]['nx'] > 0:
                # Cell has boundary segments but sx=0 (likely due to shadow removal or no_boundary)
                cells_with_nx_but_no_sx += 1
        
        # Computing y obstruction (similar to x)
        if cell[k][j]['ny'] != 0:
            # MATLAB: n_segs = cell(k,j).ny;
            # MATLAB: baseseg_n = cell(k,j).east_lim;
            # MATLAB: baseseg_s = cell(k,j).west_lim;
            n_segs = cell[k][j]['ny']
            baseseg_n = np.array(cell[k][j]['east_lim'])
            baseseg_s = np.array(cell[k][j]['west_lim'])
            
            no_boundary = False
            
            # Compare with bottom neighbors
            for off in range(1, offset_left + 1):
                kk = k - off
                if kk >= 0:
                    if cell[kk][j]['ny'] != 0:
                        set1 = {
                            'ny': cell[kk][j]['ny'],
                            'east_lim': cell[kk][j]['east_lim'].copy(),
                            'west_lim': cell[kk][j]['west_lim'].copy()
                        }
                        
                        shadow_flags = np.zeros(n_segs, dtype=bool)
                        for m in range(n_segs):
                            for l in range(set1['ny']):
                                if (set1['east_lim'][l] >= baseseg_n[m] and
                                    set1['west_lim'][l] <= baseseg_s[m]):
                                    shadow_flags[m] = True
                                    break
                        
                        loc = np.where(~shadow_flags)[0]
                        if len(loc) == 0:
                            no_boundary = True
                            n_segs = 0
                            baseseg_n = np.array([])
                            baseseg_s = np.array([])
                        elif len(loc) < n_segs:
                            baseseg_n = baseseg_n[loc]
                            baseseg_s = baseseg_s[loc]
                            n_segs = len(baseseg_n)
                        
                        if not no_boundary:
                            shadow_flags2 = np.zeros(set1['ny'], dtype=bool)
                            for m in range(set1['ny']):
                                for l in range(n_segs):
                                    if (set1['east_lim'][m] <= baseseg_n[l] and
                                        set1['west_lim'][m] >= baseseg_s[l]):
                                        shadow_flags2[m] = True
                                        break
                            
                            loc2 = np.where(~shadow_flags2)[0]
                            if len(loc2) > 0 and len(loc2) < set1['ny']:
                                set1['east_lim'] = [set1['east_lim'][idx] for idx in loc2]
                                set1['west_lim'] = [set1['west_lim'][idx] for idx in loc2]
                                set1['ny'] = len(loc2)
                            
                            if set1['ny'] > 0:
                                n_segs += set1['ny']
                                baseseg_n = np.append(baseseg_n, set1['east_lim'])
                                baseseg_s = np.append(baseseg_s, set1['west_lim'])
            
            # Compare with top neighbors
            if not no_boundary:
                for off in range(1, offset_right + 1):
                    kk = k + off
                    if kk < Ny:
                        if cell[kk][j]['ny'] != 0:
                            set1 = {
                                'ny': cell[kk][j]['ny'],
                                'east_lim': cell[kk][j]['east_lim'].copy(),
                                'west_lim': cell[kk][j]['west_lim'].copy()
                            }
                            
                            shadow_flags = np.zeros(n_segs, dtype=bool)
                            for m in range(n_segs):
                                for l in range(set1['ny']):
                                    if (set1['east_lim'][l] >= baseseg_n[m] and
                                        set1['west_lim'][l] <= baseseg_s[m]):
                                        shadow_flags[m] = True
                                        break
                            
                            loc = np.where(~shadow_flags)[0]
                            if len(loc) == 0:
                                no_boundary = True
                                n_segs = 0
                                baseseg_n = np.array([])
                                baseseg_s = np.array([])
                            elif len(loc) < n_segs:
                                baseseg_n = baseseg_n[loc]
                                baseseg_s = baseseg_s[loc]
                                n_segs = len(baseseg_n)
                            
                            if not no_boundary:
                                shadow_flags2 = np.zeros(set1['ny'], dtype=bool)
                                for m in range(set1['ny']):
                                    for l in range(n_segs):
                                        if (set1['east_lim'][m] <= baseseg_n[l] and
                                            set1['west_lim'][m] >= baseseg_s[l]):
                                            shadow_flags2[m] = True
                                            break
                                
                                loc2 = np.where(~shadow_flags2)[0]
                                if len(loc2) > 0 and len(loc2) < set1['ny']:
                                    set1['east_lim'] = [set1['east_lim'][idx] for idx in loc2]
                                    set1['west_lim'] = [set1['west_lim'][idx] for idx in loc2]
                                    set1['ny'] = len(loc2)
                                
                                if set1['ny'] > 0:
                                    n_segs += set1['ny']
                                    baseseg_n = np.append(baseseg_n, set1['east_lim'])
                                    baseseg_s = np.append(baseseg_s, set1['west_lim'])
            
            # Build obstruction grid
            if not no_boundary:
                # MATLAB: sy(k,j) is initialized to 0, so we start from 0
                sy[k, j] = 0.0
                
                if n_segs == 1:
                    sy[k, j] = baseseg_n[0] - baseseg_s[0]
                else:
                    ind_segs = 0
                    indseg_n = []
                    indseg_s = []
                    
                    # Convert to list for easier manipulation
                    baseseg_n_list = baseseg_n.tolist() if isinstance(baseseg_n, np.ndarray) else list(baseseg_n)
                    baseseg_s_list = baseseg_s.tolist() if isinstance(baseseg_s, np.ndarray) else list(baseseg_s)
                    n_segs = len(baseseg_n_list)
                    
                    while n_segs > 0:
                        overlap_found = False
                        if n_segs > 1:
                            for l in range(1, n_segs):
                                if baseseg_n_list[0] >= baseseg_s_list[l] and baseseg_s_list[0] <= baseseg_n_list[l]:
                                    baseseg_n_list[0] = max(baseseg_n_list[0], baseseg_n_list[l])
                                    baseseg_s_list[0] = min(baseseg_s_list[0], baseseg_s_list[l])
                                    overlap_found = True
                                    if l == n_segs - 1:
                                        n_segs -= 1
                                    else:
                                        for m in range(l + 1, n_segs):
                                            baseseg_n_list[m - 1] = baseseg_n_list[m]
                                            baseseg_s_list[m - 1] = baseseg_s_list[m]
                                        n_segs -= 1
                                    break
                        
                        if n_segs == 1:
                            ind_segs += 1
                            indseg_n.append(baseseg_n_list[0])
                            indseg_s.append(baseseg_s_list[0])
                            n_segs = 0
                        else:
                            if not overlap_found:
                                ind_segs += 1
                                indseg_n.append(baseseg_n_list[0])
                                indseg_s.append(baseseg_s_list[0])
                                for l in range(1, n_segs):
                                    baseseg_n_list[l - 1] = baseseg_n_list[l]
                                    baseseg_s_list[l - 1] = baseseg_s_list[l]
                                n_segs -= 1
                    
                    # MATLAB: for l = 1:ind_segs, sy(k,j) = sy(k,j) + indseg_n(l)-indseg_s(l); end
                    for l in range(ind_segs):
                        sy[k, j] += (indseg_n[l] - indseg_s[l])
                    
                    # Clamp to [0, 1] range
                    sy[k, j] = max(0.0, min(1.0, sy[k, j]))
            
            # Record value before neighbor check (regardless of no_boundary)
            sy_before_neighbor[k, j] = sy[k, j]
            if sy[k, j] > 0:
                cells_with_sy_before += 1
            elif cell[k][j]['ny'] > 0:
                # Cell has boundary segments but sy=0 (likely due to shadow removal or no_boundary)
                cells_with_ny_but_no_sy += 1
        
        # Setting the obstruction grid to zero if neighboring cells are dry
        # MATLAB: if (j < Nx && mask(k,j+1) == 0), sx(k,j) = 0; end
        # MATLAB: if (j > 1 && mask(k,j-1) == 0), sx(k,j) = 0; end
        # MATLAB: if (k < Ny && mask(k+1,j) == 0), sy(k,j) = 0; end
        # MATLAB: if (k > 1 && mask(k-1,j) == 0), sy(k,j) = 0; end
        if j < Nx - 1 and mask[k, j + 1] == 0:
            sx[k, j] = 0
        if j > 0 and mask[k, j - 1] == 0:
            sx[k, j] = 0
        if k < Ny - 1 and mask[k + 1, j] == 0:
            sy[k, j] = 0
        if k > 0 and mask[k - 1, j] == 0:
            sy[k, j] = 0
    
    # Debug: Print statistics about obstruction values
    sx_nonzero = sx[sx > 0]
    sy_nonzero = sy[sy > 0]
    sx_before_nonzero = sx_before_neighbor[sx_before_neighbor > 0]
    sy_before_nonzero = sy_before_neighbor[sy_before_neighbor > 0]
    total_wet = np.sum(mask != 0)
    total_cells = Nx * Ny
    
    # Count how many were zeroed by neighbor check
    sx_zeroed_by_neighbor = np.sum((sx_before_neighbor > 0) & (sx == 0))
    sy_zeroed_by_neighbor = np.sum((sy_before_neighbor > 0) & (sy == 0))
    
    
    return sx, sy
