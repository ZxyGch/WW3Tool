"""
Split Boundary Function

This function splits up large boundary segments into smaller ones so
that they are more manageable.

Copyright 2009 National Weather Service (NWS),
National Oceanic and Atmospheric Administration. All rights reserved.
Distributed with WAVEWATCH III

Last Update: 23-Oct-2012
"""

import numpy as np


def split_boundary(bound, lim, min_val=None):
    """
    Split large boundary polygons into smaller manageable ones.
    
    Parameters
    ----------
    bound : list
        Data structure array (list of dicts) of boundary polygons that
        lie inside grid domain. Each dict should have keys: 'west', 'east',
        'south', 'north', 'width', 'height', 'level', and other polygon data
    lim : float
        Limiting size to determine if a polygon needs to be split
    min_val : float, optional
        Threshold defining the minimum distance between the edge of polygon
        and the inside/outside boundary. A low value reduces computation time
        but can raise errors if the grid is too coarse. Default is 4.
    
    Returns
    -------
    bound_ingrid : list
        A new data structure (list of dicts) of boundary polygons where the
        larger polygons have been split up to more manageable smaller sizes
    """
    if min_val is None:
        min_val = 4  # Default value
    
    eps = 1e-5
    
    N = len(bound)
    in_coord = 0
    bound_ingrid = []
    itmp = 0
    
    # Import compute_boundary here to avoid circular imports
    from .compute_boundary import compute_boundary
    
    import sys
    last_report_pct = -1
    large_boundary_count = 0
    
    for i in range(N):  # Loop on polygons previously obtained with compute_boundary
        # if the considered polygon is larger than the limit set by 'lim':
        if bound[i]['width'] > lim or bound[i]['height'] > lim:
            large_boundary_count += 1
            low = int(np.floor(bound[i]['west']))
            high = int(np.ceil(bound[i]['east']))
            # MATLAB: x_axis = [low:lim:high]
            # Use np.arange to handle both integer and float step sizes
            # Ensure step is at least 1 to avoid zero step error
            step = max(1, int(lim)) if lim >= 1 else 1
            x_axis = np.arange(low, high + step, step, dtype=int).tolist()
            # Ensure high is included
            if len(x_axis) == 0:
                x_axis = [low, high]
            else:
                # Remove duplicates and ensure high is included
                x_axis = sorted(list(set(x_axis)))
            if x_axis[-1] < high:
                x_axis.append(high)
            
            low = int(np.floor(bound[i]['south']))
            high = int(np.ceil(bound[i]['north']))
            # MATLAB: y_axis = [low:lim:high]
            step = max(1, int(lim)) if lim >= 1 else 1
            y_axis = np.arange(low, high + step, step, dtype=int).tolist()
            if len(y_axis) == 0:
                y_axis = [low, high]
            else:
                y_axis = sorted(list(set(y_axis)))
            if y_axis[-1] < high:
                y_axis.append(high)
            
            Nx = len(x_axis)
            Ny = len(y_axis)
            
            # Loop on each "sub-polygon" & run compute_boundary for each of
            # them; store the results in one single array bound_ingrid
            total_sub_polygons = (Nx - 1) * (Ny - 1)
            sub_polygon_count = 0
            
            for lx in range(Nx - 1):
                for ly in range(Ny - 1):
                    lat_start = y_axis[ly]
                    lon_start = x_axis[lx]
                    lat_end = y_axis[ly + 1]
                    lon_end = x_axis[lx + 1]
                    
                    # Create a single-element list with the original polygon
                    # to pass to compute_boundary
                    bt, Nb = compute_boundary(
                        [lat_start, lon_start, lat_end, lon_end],
                        [bound[i]],  # Pass as list with single element
                        min_val,
                        bound[i]['level']
                    )
                    
                    if Nb > 0:
                        # If bt is a list, extend; if single dict, append
                        if isinstance(bt, list):
                            bound_ingrid.extend(bt)
                            in_coord += Nb
                        else:
                            bound_ingrid.append(bt)
                            in_coord += 1
                    
                    sub_polygon_count += 1
                    # Output progress for large boundaries being split
                    if total_sub_polygons > 10 and sub_polygon_count % max(1, total_sub_polygons // 10) == 0:
                        print(f'  Processing large boundary {i+1}/{N}: {sub_polygon_count}/{total_sub_polygons} sub-polygons...', flush=True)
                        sys.stdout.flush()
        else:
            # if current polygon does not need subdivision
            bound_ingrid.append(bound[i])
            in_coord += 1
        
        # Report progress every 5%
        current_pct = int((i + 1) / N * 100)
        if current_pct >= last_report_pct + 5:
            last_report_pct = (current_pct // 5) * 5
            print(f'  Completed {last_report_pct} per cent of {N} boundaries and split into {in_coord} boundaries', flush=True)
            sys.stdout.flush()
    
    return bound_ingrid

