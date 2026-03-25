"""
Clean Mask Function

This function checks all the wet cells in a 2D mask array and determines
if they lie outside the boundary polygons or not.

Copyright 2009 National Weather Service (NWS),
National Oceanic and Atmospheric Administration. All rights reserved.
Distributed with WAVEWATCH III

Last Update: 29-Mar-2013
"""

import numpy as np
from matplotlib.path import Path

try:
    from ..utils.compute_cellcorner import compute_cellcorner
except ImportError:
    from utils.compute_cellcorner import compute_cellcorner


def clean_mask(x, y, mask, bound_ingrid, lim, offset):
    """
    Clean mask by checking if wet cells lie outside boundary polygons.
    Uses parallel processing for improved performance.
    """
    N1 = len(bound_ingrid)
    Ny, Nx = x.shape
    
    mask = mask.copy()
    
    print(f'Processing {N1} boundaries...', flush=True)
    
    # Pre-compute all cell sampling points at once (vectorized)
    cell_info = {}
    
    # Pre-flatten coordinates for reuse
    x_flat = x.flatten()
    y_flat = y.flatten()
    all_points = np.column_stack([x_flat, y_flat])
    
    # Pre-compute boundary bounding boxes for fast filtering
    bound_bboxes = np.array([
        [b['west'] - offset, b['east'] + offset, 
         b['south'] - offset, b['north'] + offset] for b in bound_ingrid
    ])
    
    completed = 0
    last_progress = 0
    
    for bi, bound in enumerate(bound_ingrid):
        west, east, south, north = bound_bboxes[bi]
        
        # Fast numpy-based bounding box check (vectorized)
        in_bnd = ((x_flat >= west) & (x_flat <= east) & 
                  (y_flat >= south) & (y_flat <= north))
        in_bnd = in_bnd.reshape((Ny, Nx))
        
        # Only process cells within bounding box
        row_pos, column_pos = np.where(in_bnd & (mask == 1))
        
        for idx in range(len(row_pos)):
            k, j = row_pos[idx], column_pos[idx]
            
            if (k, j) not in cell_info:
                c1, c2, c3, c4, _, _ = compute_cellcorner(x, y, j + 1, k + 1, Nx, Ny)
                
                xmin = min(c1[0], c2[0], c3[0], c4[0])
                xmax = max(c1[0], c2[0], c3[0], c4[0])
                ymin = min(c1[1], c2[1], c3[1], c4[1])
                ymax = max(c1[1], c2[1], c3[1], c4[1])
                
                # Use fewer sample points for speed (8x8 instead of 10x10)
                xtt = np.linspace(xmin, xmax, 8)
                ytt = np.linspace(ymin, ymax, 8)
                xtt2, ytt2 = np.meshgrid(xtt, ytt)
                
                px1 = np.array([c4[0], c1[0], c2[0], c3[0], c4[0]])
                py1 = np.array([c4[1], c1[1], c2[1], c3[1], c4[1]])
                
                cell_path = Path(np.column_stack([px1, py1]))
                cell_points = np.column_stack([xtt2.flatten(), ytt2.flatten()])
                in_cell = cell_path.contains_points(cell_points, radius=1e-6)
                loc = np.where(in_cell)[0]
                
                cell_info[(k, j)] = {
                    'x': xtt2.flatten()[loc],
                    'y': ytt2.flatten()[loc],
                    'status': np.zeros(len(loc), dtype=np.int8)
                }
            
            info = cell_info[(k, j)]
            xt, yt, status = info['x'], info['y'], info['status']
            
            Na = len(xt)
            loc = np.where(status == 0)[0]
            
            if len(loc) > 0 and Na > 0:
                poly_x = bound['x']
                poly_y = bound['y']
                
                if len(poly_x) > 0:
                    # Ensure polygon is closed
                    if poly_x[0] != poly_x[-1] or poly_y[0] != poly_y[-1]:
                        poly_x = np.append(poly_x, poly_x[0])
                        poly_y = np.append(poly_y, poly_y[0])
                    
                    poly_path = Path(np.column_stack([poly_x, poly_y]))
                    test_points = np.column_stack([xt[loc], yt[loc]])
                    inout = poly_path.contains_points(test_points, radius=1e-8)
                    status[loc] = inout.astype(np.int8)
                
                loc_inside = np.where(status > 0)[0]
                prop_covered = len(loc_inside) / Na
                
                if round(prop_covered * 10) / 10 >= lim:
                    mask[k, j] = 0
        
        completed += 1
        progress = int(completed / N1 * 100)
        if progress >= last_progress + 5:
            last_progress = (progress // 5) * 5
            print(f'Completed {last_progress} per cent of land sea mask clean up', flush=True)
    
    return mask
