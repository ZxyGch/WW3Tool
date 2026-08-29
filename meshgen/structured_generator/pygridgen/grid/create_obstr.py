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

import numpy as np
from matplotlib.path import Path

try:
    from ..utils.compute_cellcorner import cellcorner_polygons, compute_cellcorner_grid
    from ..utils.parallel import (cap_workers_for_memory, describe_cpu_budget,
                                  resolve_workers, run_parallel, worker_baseline_bytes)
except ImportError:
    from utils.compute_cellcorner import cellcorner_polygons, compute_cellcorner_grid
    from utils.parallel import (cap_workers_for_memory, describe_cpu_budget,
                                resolve_workers, run_parallel, worker_baseline_bytes)


# Boundary data shared by every worker.  Sent once per worker through the pool
# initializer instead of riding along with each batch -- at a few million cells
# the per-task copies dominated everything else this routine does.
_BOUND_STATE = {}


def _init_bound_state(state):
    _BOUND_STATE.clear()
    _BOUND_STATE.update(state)
    try:
        from ..utils.parallel import limit_worker_threads
    except ImportError:
        from utils.parallel import limit_worker_threads
    limit_worker_threads()


_CELL_FIELDS = ('px', 'py', 'angle', 'width', 'height')


class _CellRow:
    """One row of :class:`_CellGrid`; materialises records on first touch."""

    __slots__ = ('_store', '_k')

    def __init__(self, store, k):
        self._store = store
        self._k = k

    def __getitem__(self, j):
        key = (self._k, j)
        rec = self._store.get(key)
        if rec is None:
            rec = {'px': None, 'py': None, 'angle': None, 'width': None,
                   'height': None, 'nx': 0, 'ny': 0, 'south_lim': [],
                   'north_lim': [], 'east_lim': [], 'west_lim': [],
                   'bndx': [], 'bndy': []}
            self._store[key] = rec
        return rec


class _CellGrid:
    """``cell[k][j]`` storage that only allocates the cells actually used.

    The obstruction bookkeeping touches coastal cells and their immediate
    neighbours, not the whole grid, so a dense list of dicts spent gigabytes on
    records that stayed empty.
    """

    __slots__ = ('_store',)

    def __init__(self):
        self._store = {}

    def __getitem__(self, k):
        return _CellRow(self._store, k)



def _clamped_ratio(value, extent):
    """``value / extent`` clamped to [0, 1], with a zero-extent cell giving 0.

    A cell can have zero width or height when the grid is one row or one
    column across, or when consecutive coordinates repeat.  Dividing by that
    raised divide-by-zero / overflow / invalid flags, and the flags were then
    reported against the *next* matmul, which made the warning point at a line
    that had nothing to do with it.  The clamp also turned the resulting
    infinities into an arbitrary 0.0 or 1.0; a cell with no extent cannot be
    partially blocked, so 0.0 is the answer that means something.
    """
    if not extent or not np.isfinite(extent):
        return 0.0
    ratio = value / extent
    if not np.isfinite(ratio):
        return 0.0
    return float(max(0.0, min(1.0, ratio)))


def _process_wet_cell_batch(cell_batch):
    """Process a batch of wet cells (for parallel processing with reduced overhead)."""
    bnd_x = _BOUND_STATE['bnd_x']
    bnd_y = _BOUND_STATE['bnd_y']
    bnd_indx = _BOUND_STATE['bnd_indx']
    bound_dict = _BOUND_STATE['bound_dict']
    bound_bboxes = _BOUND_STATE['bound_bboxes']

    ks, js, pxs, pys, angles, widths, heights, bounds = cell_batch
    results = []
    
    for idx in range(len(ks)):
        k = int(ks[idx])
        j = int(js[idx])
        angle = angles[idx]
        px = pxs[idx]
        py = pys[idx]
        x0 = px[0]
        y0 = py[0]
        cell_width = widths[idx]
        cell_height = heights[idx]
        
        cell_min_x, cell_max_x, cell_min_y, cell_max_y = bounds[idx]
        
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
                
                # numpy's (N,2) @ (2,2) path raises divide-by-zero, overflow,
                # underflow and invalid flags on perfectly ordinary input --
                # its SIMD kernel reads past the end of the buffer and the
                # garbage lanes, though discarded from the result, still set
                # the FPU flags.  Verified on real data: inputs finite, output
                # finite and correct.  Silencing it here rather than rewriting
                # the product by hand, because the hand-rolled form differs
                # from BLAS by an ulp and would move the written bathymetry.
                with np.errstate(divide='ignore', over='ignore',
                                 under='ignore', invalid='ignore'):
                    tmp = np.column_stack([xt - x0, yt - y0]) @ RM
                xt = tmp[:, 0]
                yt = tmp[:, 1]
                
                south_limit = _clamped_ratio(np.min(yt), cell_height)
                north_limit = _clamped_ratio(np.max(yt), cell_height)
                west_limit = _clamped_ratio(np.min(xt), cell_width)
                east_limit = _clamped_ratio(np.max(xt), cell_width)
                
                cell_results.append({
                    'indx_bnd': int(indx_bnd),
                    'south_lim': south_limit,
                    'north_lim': north_limit,
                    'west_lim': west_limit,
                    'east_lim': east_limit
                })
        
        results.append((k, j, Nbnds, cell_results))
    
    return results



def _cells_near_boundaries(cell_min_x, cell_max_x, cell_min_y, cell_max_y,
                           margin, bnd_x, bnd_y):
    """Boolean grid marking cells whose padded box could hold a boundary point.

    The per-cell test in the worker compares the cell box against *every*
    boundary point, which on a fine grid is millions of cells times hundreds of
    thousands of points.  Binning the points first and asking a summed-area
    table whether any bin in range is occupied answers the same question for
    all cells at once, and only ever over-selects, so the exact per-cell test
    that follows is unchanged.
    """
    if bnd_x.size == 0:
        return np.zeros(cell_min_x.shape, dtype=bool)

    span = max(float(np.max(cell_max_x - cell_min_x)),
               float(np.max(cell_max_y - cell_min_y)))
    bin_size = max(span * 4.0, 1e-9)

    ox = float(min(np.min(cell_min_x), np.min(bnd_x))) - bin_size
    oy = float(min(np.min(cell_min_y), np.min(bnd_y))) - bin_size
    hx = float(max(np.max(cell_max_x), np.max(bnd_x))) + bin_size
    hy = float(max(np.max(cell_max_y), np.max(bnd_y))) + bin_size

    n_bx = int((hx - ox) / bin_size) + 2
    n_by = int((hy - oy) / bin_size) + 2

    occ = np.zeros((n_by, n_bx), dtype=np.int32)
    pbx = np.clip(((bnd_x - ox) / bin_size).astype(np.int64), 0, n_bx - 1)
    pby = np.clip(((bnd_y - oy) / bin_size).astype(np.int64), 0, n_by - 1)
    occ[pby, pbx] = 1

    sat = np.zeros((n_by + 1, n_bx + 1), dtype=np.int64)
    np.cumsum(np.cumsum(occ, axis=0, dtype=np.int64), axis=1, out=sat[1:, 1:])

    bx0 = np.clip(((cell_min_x - margin - ox) / bin_size).astype(np.int64), 0, n_bx - 1)
    bx1 = np.clip(((cell_max_x + margin - ox) / bin_size).astype(np.int64), 0, n_bx - 1)
    by0 = np.clip(((cell_min_y - margin - oy) / bin_size).astype(np.int64), 0, n_by - 1)
    by1 = np.clip(((cell_max_y + margin - oy) / bin_size).astype(np.int64), 0, n_by - 1)

    hits = (sat[by1 + 1, bx1 + 1] - sat[by0, bx1 + 1]
            - sat[by1 + 1, bx0] + sat[by0, bx0])
    return hits > 0


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
    
    # Sparse cell structure: records appear only where they are written to.
    cell = _CellGrid()
    
    cell_bnd = np.zeros_like(mask)
    
    loc_wet = np.where(mask != 0)
    N_wet = len(loc_wet[0])
    Nb = Nx * Ny
    
    print(f' Total Number of cells = {Nb}', flush=True)
    print(f'   Number of wet cells = {N_wet}', flush=True)
    
    # Cell geometry for the whole grid in one vectorised pass.
    corners = compute_cellcorner_grid(x, y)
    cell_px, cell_py = cellcorner_polygons(corners)
    cell_angle = np.arctan2(corners['c1y'] - corners['c4y'],
                            corners['c1x'] - corners['c4x'])
    cell_width = corners['width']
    cell_height = corners['height']

    # A cell with no extent cannot hold a partial obstruction, so it silently
    # contributes nothing.  That is almost always a grid that is one row or one
    # column across, or one with repeated coordinates -- worth saying out loud
    # rather than returning an all-zero obstruction field.
    degenerate = int(np.count_nonzero((cell_width == 0) | (cell_height == 0)))
    if degenerate:
        print(f'  Warning: {degenerate} of {cell_width.size} cells have zero width '
              f'or height; they get no obstruction.\n'
              f'           Check DX / DY against the domain — a grid one row or '
              f'one column across does this.', flush=True)
    del corners
    
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
    
    # Per-cell bounding boxes, straight from the corner arrays.
    print('Pre-computing cell bounding boxes for fast filtering...', flush=True)
    cell_min_x = cell_px.min(axis=2)
    cell_max_x = cell_px.max(axis=2)
    cell_min_y = cell_py.min(axis=2)
    cell_max_y = cell_py.max(axis=2)
    
    # Loop through the wet cells and determine the boundaries that are within
    print('Loop through the wet cells to identify boundaries', flush=True)
    
    # Skip the cells that provably hold no boundary point.
    margin = np.maximum(cell_width, cell_height) * 0.1
    near = _cells_near_boundaries(cell_min_x, cell_max_x, cell_min_y, cell_max_y,
                                  margin, bnd_x, bnd_y)
    work_k, work_j = np.where((mask != 0) & near)
    N_work = len(work_k)
    print(f'   Wet cells to test against boundaries = {N_work}', flush=True)
    
    n_workers = resolve_workers(N_work, min_chunk=2_500)
    # The polygon points go to every worker, so the pool width has to answer
    # to the memory budget as well as to the core count.
    per_worker = (worker_baseline_bytes()
                  + int(bnd_x.nbytes + bnd_y.nbytes + bnd_indx.nbytes) * 2)
    n_workers = cap_workers_for_memory(n_workers, per_worker, 'obstruction grids')
    batch_size = max(50, N_work // max(1, n_workers * 8))
    print(f'  Using {n_workers} worker(s), batch size {batch_size}; '
          f'{describe_cpu_budget()}; ~{per_worker / (1 << 20):.0f} MiB per worker',
          flush=True)
    
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
    work_bounds = np.stack([cell_min_x[work_k, work_j], cell_max_x[work_k, work_j],
                            cell_min_y[work_k, work_j], cell_max_y[work_k, work_j]],
                           axis=1)
    work_px = cell_px[work_k, work_j]
    work_py = cell_py[work_k, work_j]
    work_angle = cell_angle[work_k, work_j]
    work_width = cell_width[work_k, work_j]
    work_height = cell_height[work_k, work_j]
    
    cell_batches = [
        (work_k[a:b], work_j[a:b], work_px[a:b], work_py[a:b], work_angle[a:b],
         work_width[a:b], work_height[a:b], work_bounds[a:b])
        for a, b in ((i, min(i + batch_size, N_work))
                     for i in range(0, N_work, batch_size))
    ]
    
    print(f'  Created {len(cell_batches)} batches, starting parallel processing...', flush=True)
    
    # Process batches in parallel
    completed = 0
    last_progress = 0
    
    bound_state = {
        'bnd_x': bnd_x, 'bnd_y': bnd_y, 'bnd_indx': bnd_indx,
        'bound_dict': bound_dict, 'bound_bboxes': bound_bboxes,
    }
    print(f'  Dispatching {len(cell_batches)} batches to {n_workers} worker(s)...',
          flush=True)
    all_results = run_parallel(_process_wet_cell_batch, cell_batches, n_workers,
                               initializer=_init_bound_state,
                               initargs=(bound_state,))
    print('  Collecting results...', flush=True)

    for batch_results in all_results:
        for k, j, Nbnds, results in batch_results:
            cell_bnd[k, j] = Nbnds

            for result in results:
                indx_bnd = result['indx_bnd']
                rec = cell[k][j]

                # Store x-direction boundary
                rec['nx'] = rec['nx'] + 1
                rec['south_lim'].append(result['south_lim'])
                rec['north_lim'].append(result['north_lim'])
                rec['bndx'].append(indx_bnd)

                # Store y-direction boundary
                rec['ny'] = rec['ny'] + 1
                rec['east_lim'].append(result['east_lim'])
                rec['west_lim'].append(result['west_lim'])
                rec['bndy'].append(indx_bnd)

            completed += 1
            progress = int(completed / max(1, N_work) * 100)
            if progress >= last_progress + 5:
                last_progress = (progress // 5) * 5
                print(f' Completed {last_progress} per cent', flush=True)

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
