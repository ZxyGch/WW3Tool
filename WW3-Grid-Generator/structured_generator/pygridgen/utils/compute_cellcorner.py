"""
Compute cell corners for a given grid cell.

This function determines the corners of a particular cell at the jth row and kth column,
given the 2D position matrices x and y.
"""

import numpy as np


def compute_cellcorner(x, y, j, k, Nx, Ny):
    """
    Compute the corners of a grid cell.
    
    Parameters
    ----------
    x : ndarray
        2D array specifying the longitudes of each cell
    y : ndarray
        2D array specifying the latitudes of each cell
    j : int
        Column index (0-based, but MATLAB uses 1-based)
    k : int
        Row index (0-based, but MATLAB uses 1-based)
    Nx : int
        Number of columns
    Ny : int
        Number of rows
    
    Returns
    -------
    c1, c2, c3, c4 : tuple
        Corners of the cell as [x, y] coordinates
        c1: bottom-right
        c2: top-right
        c3: top-left
        c4: bottom-left
    wdth : float
        Cell width
    hgt : float
        Cell height
    """
    # Convert to 0-based indexing (MATLAB uses 1-based)
    j_idx = j - 1
    k_idx = k - 1
    
    x0 = x[k_idx, j_idx]
    c1 = []
    c2 = []
    c3 = []
    c4 = []
    
    # Internal points
    if (j > 1 and j < Nx and k > 1 and k < Ny):
        # Bottom-right corner (c1)
        xt = x[k_idx-1, j_idx+1]
        if abs(xt - x0) > 270:
            xt = xt - 360 * np.sign(xt - x0)
        c1 = [0.5 * (xt + x0), 0.5 * (y[k_idx-1, j_idx+1] + y[k_idx, j_idx])]
        
        # Top-right corner (c2)
        xt = x[k_idx+1, j_idx+1]
        if abs(xt - x0) > 270:
            xt = xt - 360 * np.sign(xt - x0)
        c2 = [0.5 * (xt + x0), 0.5 * (y[k_idx+1, j_idx+1] + y[k_idx, j_idx])]
        
        # Top-left corner (c3)
        xt = x[k_idx+1, j_idx-1]
        if abs(xt - x0) > 270:
            xt = xt - 360 * np.sign(xt - x0)
        c3 = [0.5 * (xt + x0), 0.5 * (y[k_idx+1, j_idx-1] + y[k_idx, j_idx])]
        
        # Bottom-left corner (c4)
        xt = x[k_idx-1, j_idx-1]
        if abs(xt - x0) > 270:
            xt = xt - 360 * np.sign(xt - x0)
        c4 = [0.5 * (xt + x0), 0.5 * (y[k_idx-1, j_idx-1] + y[k_idx, j_idx])]
    
    # Edge cases (left, right, top, bottom)
    elif j == 1:  # Left edge
        if k == 1:  # Bottom-left corner
            if Ny > 1 and k_idx+1 < Ny and j_idx+1 < Nx:
                xt = x[k_idx+1, j_idx+1]
                if abs(xt - x0) > 270:
                    xt = xt - 360 * np.sign(xt - x0)
                c2 = [0.5 * (xt + x0), 0.5 * (y[k_idx+1, j_idx+1] + y[k_idx, j_idx])]
            else:
                # Single row/column case: use reflection
                if j_idx+1 < Nx:
                    xt = x[k_idx, j_idx+1]
                else:
                    xt = x0
                if abs(xt - x0) > 270:
                    xt = xt - 360 * np.sign(xt - x0)
                c2 = [0.5 * (xt + x0), y[k_idx, j_idx]]
            c4 = [2*x0 - c2[0], 2*y[k_idx, j_idx] - c2[1]]
            c3 = [x0 - (c2[1] - y[k_idx, j_idx]), y[k_idx, j_idx] + (c2[0] - x[k_idx, j_idx])]
            c1 = [2*x0 - c3[0], 2*y[k_idx, j_idx] - c3[1]]
        elif k == Ny:  # Top-left corner
            if Ny > 1 and k_idx-1 >= 0 and j_idx+1 < Nx:
                xt = x[k_idx-1, j_idx+1]
                if abs(xt - x0) > 270:
                    xt = xt - 360 * np.sign(xt - x0)
                c1 = [0.5 * (xt + x0), 0.5 * (y[k_idx-1, j_idx+1] + y[k_idx, j_idx])]
            else:
                # Single row/column case: use reflection
                if j_idx+1 < Nx:
                    xt = x[k_idx, j_idx+1]
                else:
                    xt = x0
                if abs(xt - x0) > 270:
                    xt = xt - 360 * np.sign(xt - x0)
                c1 = [0.5 * (xt + x0), y[k_idx, j_idx]]
            c3 = [2*x0 - c1[0], 2*y[k_idx, j_idx] - c1[1]]
            c2 = [x0 - (y[k_idx, j_idx] - c1[1]), y[k_idx, j_idx] + (x0 - c1[0])]
            c4 = [2*x0 - c2[0], 2*y[k_idx, j_idx] - c2[1]]
        else:  # Left edge middle
            if Ny > 1 and k_idx-1 >= 0 and j_idx+1 < Nx:
                xt = x[k_idx-1, j_idx+1]
                if abs(xt - x0) > 270:
                    xt = xt - 360 * np.sign(xt - x0)
                c1 = [0.5 * (xt + x0), 0.5 * (y[k_idx-1, j_idx+1] + y[k_idx, j_idx])]
            else:
                if j_idx+1 < Nx:
                    xt = x[k_idx, j_idx+1]
                else:
                    xt = x0
                if abs(xt - x0) > 270:
                    xt = xt - 360 * np.sign(xt - x0)
                c1 = [0.5 * (xt + x0), y[k_idx, j_idx]]
            if Ny > 1 and k_idx+1 < Ny and j_idx+1 < Nx:
                xt = x[k_idx+1, j_idx+1]
                if abs(xt - x0) > 270:
                    xt = xt - 360 * np.sign(xt - x0)
                c2 = [0.5 * (xt + x0), 0.5 * (y[k_idx+1, j_idx+1] + y[k_idx, j_idx])]
            else:
                if j_idx+1 < Nx:
                    xt = x[k_idx, j_idx+1]
                else:
                    xt = x0
                if abs(xt - x0) > 270:
                    xt = xt - 360 * np.sign(xt - x0)
                c2 = [0.5 * (xt + x0), y[k_idx, j_idx]]
            c3 = [2*x0 - c1[0], 2*y[k_idx, j_idx] - c1[1]]
            c4 = [2*x0 - c2[0], 2*y[k_idx, j_idx] - c2[1]]
    
    elif j == Nx:  # Right edge
        if k == 1:  # Bottom-right corner
            if Ny > 1 and k_idx+1 < Ny and j_idx-1 >= 0:
                xt = x[k_idx+1, j_idx-1]
                if abs(xt - x0) > 270:
                    xt = xt - 360 * np.sign(xt - x0)
                c3 = [0.5 * (xt + x0), 0.5 * (y[k_idx+1, j_idx-1] + y[k_idx, j_idx])]
            else:
                if j_idx-1 >= 0:
                    xt = x[k_idx, j_idx-1]
                else:
                    xt = x0
                if abs(xt - x0) > 270:
                    xt = xt - 360 * np.sign(xt - x0)
                c3 = [0.5 * (xt + x0), y[k_idx, j_idx]]
            c2 = [x0 - (c3[1] - y[k_idx, j_idx]), y[k_idx, j_idx] + (c3[0] - x0)]
            c1 = [2*x0 - c3[0], 2*y[k_idx, j_idx] - c3[1]]
            c4 = [2*x0 - c2[0], 2*y[k_idx, j_idx] - c2[1]]
        elif k == Ny:  # Top-right corner
            if Ny > 1 and k_idx-1 >= 0 and j_idx-1 >= 0:
                xt = x[k_idx-1, j_idx-1]
                if abs(xt - x0) > 270:
                    xt = xt - 360 * np.sign(xt - x0)
                c4 = [0.5 * (xt + x0), 0.5 * (y[k_idx-1, j_idx-1] + y[k_idx, j_idx])]
            else:
                if j_idx-1 >= 0:
                    xt = x[k_idx, j_idx-1]
                else:
                    xt = x0
                if abs(xt - x0) > 270:
                    xt = xt - 360 * np.sign(xt - x0)
                c4 = [0.5 * (xt + x0), y[k_idx, j_idx]]
            c3 = [x0 - (c4[1] - y[k_idx, j_idx]), y[k_idx, j_idx] + (c4[0] - x0)]
            c1 = [2*x0 - c3[0], 2*y[k_idx, j_idx] - c3[1]]
            c2 = [2*x0 - c4[0], 2*y[k_idx, j_idx] - c4[1]]
        else:  # Right edge middle
            if Ny > 1 and k_idx+1 < Ny and j_idx-1 >= 0:
                xt = x[k_idx+1, j_idx-1]
                if abs(xt - x0) > 270:
                    xt = xt - 360 * np.sign(xt - x0)
                c3 = [0.5 * (xt + x0), 0.5 * (y[k_idx+1, j_idx-1] + y[k_idx, j_idx])]
            else:
                if j_idx-1 >= 0:
                    xt = x[k_idx, j_idx-1]
                else:
                    xt = x0
                if abs(xt - x0) > 270:
                    xt = xt - 360 * np.sign(xt - x0)
                c3 = [0.5 * (xt + x0), y[k_idx, j_idx]]
            if Ny > 1 and k_idx-1 >= 0 and j_idx-1 >= 0:
                xt = x[k_idx-1, j_idx-1]
                if abs(xt - x0) > 270:
                    xt = xt - 360 * np.sign(xt - x0)
                c4 = [0.5 * (xt + x0), 0.5 * (y[k_idx-1, j_idx-1] + y[k_idx, j_idx])]
            else:
                if j_idx-1 >= 0:
                    xt = x[k_idx, j_idx-1]
                else:
                    xt = x0
                if abs(xt - x0) > 270:
                    xt = xt - 360 * np.sign(xt - x0)
                c4 = [0.5 * (xt + x0), y[k_idx, j_idx]]
            c1 = [2*x0 - c3[0], 2*y[k_idx, j_idx] - c3[1]]
            c2 = [2*x0 - c4[0], 2*y[k_idx, j_idx] - c4[1]]
    
    elif k == 1:  # Bottom edge
        # Check if we can access k_idx+1 (i.e., if Ny > 1)
        if Ny > 1 and k_idx+1 < Ny:
            xt = x[k_idx+1, j_idx+1]
            if abs(xt - x0) > 270:
                xt = xt - 360 * np.sign(xt - x0)
            c2 = [0.5 * (xt + x0), 0.5 * (y[k_idx+1, j_idx+1] + y[k_idx, j_idx])]
            xt = x[k_idx+1, j_idx-1]
            if abs(xt - x0) > 270:
                xt = xt - 360 * np.sign(xt - x0)
            c3 = [0.5 * (xt + x0), 0.5 * (y[k_idx+1, j_idx-1] + y[k_idx, j_idx])]
        else:
            # Single row case: use reflection
            if j_idx+1 < Nx:
                xt = x[k_idx, j_idx+1]
            else:
                xt = x0
            if abs(xt - x0) > 270:
                xt = xt - 360 * np.sign(xt - x0)
            c2 = [0.5 * (xt + x0), y[k_idx, j_idx]]
            if j_idx-1 >= 0:
                xt = x[k_idx, j_idx-1]
            else:
                xt = x0
            if abs(xt - x0) > 270:
                xt = xt - 360 * np.sign(xt - x0)
            c3 = [0.5 * (xt + x0), y[k_idx, j_idx]]
        c4 = [2*x0 - c2[0], 2*y[k_idx, j_idx] - c2[1]]
        c1 = [2*x0 - c3[0], 2*y[k_idx, j_idx] - c3[1]]
    
    elif k == Ny:  # Top edge
        # Check if we can access k_idx-1 (i.e., if Ny > 1)
        if Ny > 1 and k_idx-1 >= 0:
            xt = x[k_idx-1, j_idx-1]
            if abs(xt - x0) > 270:
                xt = xt - 360 * np.sign(xt - x0)
            c4 = [0.5 * (xt + x0), 0.5 * (y[k_idx-1, j_idx-1] + y[k_idx, j_idx])]
            xt = x[k_idx-1, j_idx+1]
            if abs(xt - x0) > 270:
                xt = xt - 360 * np.sign(xt - x0)
            c1 = [0.5 * (xt + x0), 0.5 * (y[k_idx-1, j_idx+1] + y[k_idx, j_idx])]
        else:
            # Single row case: use reflection
            if j_idx-1 >= 0:
                xt = x[k_idx, j_idx-1]
            else:
                xt = x0
            if abs(xt - x0) > 270:
                xt = xt - 360 * np.sign(xt - x0)
            c4 = [0.5 * (xt + x0), y[k_idx, j_idx]]
            if j_idx+1 < Nx:
                xt = x[k_idx, j_idx+1]
            else:
                xt = x0
            if abs(xt - x0) > 270:
                xt = xt - 360 * np.sign(xt - x0)
            c1 = [0.5 * (xt + x0), y[k_idx, j_idx]]
        c2 = [2*x0 - c4[0], 2*y[k_idx, j_idx] - c4[1]]
        c3 = [2*x0 - c1[0], 2*y[k_idx, j_idx] - c1[1]]
    
    # Calculate width and height
    wdth = np.sqrt((c1[0] - c4[0])**2 + (c1[1] - c4[1])**2)
    hgt = np.sqrt((c2[0] - c1[0])**2 + (c2[1] - c1[1])**2)
    
    return c1, c2, c3, c4, wdth, hgt

