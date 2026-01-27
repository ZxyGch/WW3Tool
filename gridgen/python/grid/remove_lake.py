"""
Remove Lake Function

This routine groups wet cells into independent water bodies with all
the wet cells connected to each other sharing the same unique ID.

Copyright 2009 National Weather Service (NWS),
National Oceanic and Atmospheric Administration. All rights reserved.
Distributed with WAVEWATCH III

Last Update: 23-Oct-2012
"""

import numpy as np


def remove_lake(mask, lake_tol, igl):
    """
    Remove small lakes or keep only the largest water body.
    
    Parameters
    ----------
    mask : ndarray
        Input 2D land/sea mask (1=wet, 0=dry)
    lake_tol : float
        Tolerance value that determines all the wet cells corresponding to
        a particular wet body should be flagged dry or not.
        - If positive: all water bodies having less than this value of total
          wet cells will be flagged dry
        - If 0: output and input masks are unchanged
        - If negative: all but the largest water body is flagged dry
    igl : int
        Switch to determine if the grid is global or regional.
        - 0: regional (not connected) grids
        - 1: global (connected) grids
    
    Returns
    -------
    mask_mod : ndarray
        Modified 2D land/sea mask based on the value of lake_tol
    mask_map : ndarray
        2D array that has a value of -1 for all land (dry) cells and
        unique IDs for wet cells that are part of a water body.
    """
    Ny, Nx = mask.shape
    
    # Initialize. Start by setting all dry cells to -1 and unmarked wet cells
    # to 0. Wet cells corresponding to the first water body are flagged as 1
    # and in increasing order thereafter
    last_mask = 1
    mask_map = mask - 1
    
    # Determine all the unmarked wet cells
    loc = np.where(mask_map == 0)
    
    # Initialize while loop if there are unmarked wet cells
    new_mask = len(loc[0]) > 0
    
    N1 = {}  # Dictionary to store cell counts for each water body
    
    # This loop continues till all the wet cells have been marked
    while new_mask:
        # Go to the first unmarked wet cell and specify it with a new ID
        row, col = np.where(mask_map == 0)
        if len(row) == 0:
            break
        row = row[0]
        col = col[0]
        mask_map[row, col] = last_mask
        
        # Initialize the neighbor flag and put the cell in the neighbor list
        no_near = False
        near_x = [col]
        near_y = [row]
        
        # Loop through till no neighbors can be found
        while not no_near:
            # Loop through all elements in neighbor list
            N = len(near_x)
            found_mask = 0
            neighbor_flag = np.zeros(N, dtype=int)
            
            for i in range(N):
                # For each cell determine the neighboring cells
                # If a global grid, account for wrap around effect in the x direction
                this_level = 0
                
                # Previous x neighbor
                if near_x[i] == 0:
                    if igl == 1:
                        prevx = Nx - 1
                    else:
                        prevx = near_x[i]
                else:
                    prevx = near_x[i] - 1
                
                # Previous y neighbor
                if near_y[i] == 0:
                    prevy = near_y[i]
                else:
                    prevy = near_y[i] - 1
                
                # Next x neighbor
                if near_x[i] == Nx - 1:
                    if igl == 1:
                        nextx = 0
                    else:
                        nextx = near_x[i]
                else:
                    nextx = near_x[i] + 1
                
                # Next y neighbor
                if near_y[i] == Ny - 1:
                    nexty = near_y[i]
                else:
                    nexty = near_y[i] + 1
                
                # Determine if neighboring cells are unmarked wet cells
                # If yes then mark them with the same ID for the water body
                # and add this cell to the list of neighboring cells
                
                if mask_map[near_y[i], prevx] == 0:
                    mask_map[near_y[i], prevx] = last_mask
                    near_x.append(prevx)
                    near_y.append(near_y[i])
                    found_mask = 1
                    neighbor_flag = np.append(neighbor_flag, 0)
                    this_level = 1
                
                if mask_map[near_y[i], nextx] == 0:
                    mask_map[near_y[i], nextx] = last_mask
                    near_x.append(nextx)
                    near_y.append(near_y[i])
                    found_mask = 1
                    neighbor_flag = np.append(neighbor_flag, 0)
                    this_level = 1
                
                if mask_map[prevy, near_x[i]] == 0:
                    mask_map[prevy, near_x[i]] = last_mask
                    near_y.append(prevy)
                    near_x.append(near_x[i])
                    found_mask = 1
                    neighbor_flag = np.append(neighbor_flag, 0)
                    this_level = 1
                
                if mask_map[nexty, near_x[i]] == 0:
                    mask_map[nexty, near_x[i]] = last_mask
                    near_y.append(nexty)
                    near_x.append(near_x[i])
                    found_mask = 1
                    neighbor_flag = np.append(neighbor_flag, 0)
                    this_level = 1
                
                # No new unmarked neighboring wet cell found for this cell
                if this_level == 0:
                    neighbor_flag[i] = 1
            
            # Check if a new unmarked neighboring wet cell was found
            if found_mask == 0:
                # No new neighboring cells found. Set flag to exit the loop
                no_near = True
                loc = np.where(mask_map == last_mask)
                N1[last_mask] = len(loc[0])
                print(f'{N1[last_mask]} Wet cells set to flag id {last_mask}', flush=True)
            else:
                # One or more new neighboring wet cells were found
                # Adjust the neighboring cell list to remove cells where all
                # the neighboring cells are either dry or marked, and repeat
                # the loop through the neighboring cell list
                x1 = near_x.copy()
                y1 = near_y.copy()
                loc = np.where(neighbor_flag == 0)[0]
                near_x = [x1[j] for j in loc]
                near_y = [y1[j] for j in loc]
        
        # Check to see if there are any more unmarked wet cells
        # If yes then increment the water body ID. If not then
        # set the new_mask flag to False to exit the while new_mask loop
        loc = np.where(mask_map == 0)
        if len(loc[0]) > 0:
            last_mask = last_mask + 1
        else:
            new_mask = False
    
    # Modify mask based on lake_tol value
    mask_mod = mask.copy()
    
    if lake_tol < 0:
        # Keep only the largest water body
        if len(N1) > 0:
            pos = max(N1, key=N1.get)
            for i in range(1, last_mask + 1):
                if i != pos:
                    loc = mask_map == i
                    mask_mod[loc] = 0
                    print(f'Masking out cells with flag set to {i}', flush=True)
    else:
        # Remove water bodies smaller than lake_tol
        for i in range(1, last_mask + 1):
            if i in N1 and N1[i] < lake_tol:
                loc = mask_map == i
                mask_mod[loc] = 0
                print(f'Masking out cells with flag set to {i}', flush=True)
    
    return mask_mod, mask_map

