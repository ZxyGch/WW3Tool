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



def _wrap_lon(xt, x0):
    """Vectorised counterpart of the ``abs(xt - x0) > 270`` date-line fixup."""
    d = xt - x0
    return np.where(np.abs(d) > 270, xt - 360.0 * np.sign(d), xt)


def compute_cellcorner_grid(x, y):
    """Compute the corners of *every* cell of a 2D grid in one shot.

    Same geometry as :func:`compute_cellcorner`, but the interior of the grid
    is evaluated with array operations instead of one Python call per cell.
    Only the one-cell-wide frame (where the reflection formulas kick in) still
    goes through :func:`compute_cellcorner`, so the result is identical to the
    per-cell loop it replaces.

    Parameters
    ----------
    x, y : ndarray
        2D arrays (Ny, Nx) of cell centre longitudes / latitudes.

    Returns
    -------
    dict
        ``c1x``/``c1y`` … ``c4x``/``c4y``, ``width`` and ``height``, each a
        (Ny, Nx) float64 array. Corner order matches
        :func:`compute_cellcorner` (c1 bottom-right, c2 top-right,
        c3 top-left, c4 bottom-left).
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    Ny, Nx = x.shape

    out = {name: np.empty((Ny, Nx), dtype=float)
           for name in ('c1x', 'c1y', 'c2x', 'c2y', 'c3x', 'c3y', 'c4x', 'c4y',
                        'width', 'height')}

    if Ny > 2 and Nx > 2:
        x0 = x[1:-1, 1:-1]
        y0 = y[1:-1, 1:-1]

        # c1 bottom-right (k-1, j+1), c2 top-right (k+1, j+1),
        # c3 top-left (k+1, j-1),     c4 bottom-left (k-1, j-1)
        out['c1x'][1:-1, 1:-1] = 0.5 * (_wrap_lon(x[:-2, 2:], x0) + x0)
        out['c1y'][1:-1, 1:-1] = 0.5 * (y[:-2, 2:] + y0)
        out['c2x'][1:-1, 1:-1] = 0.5 * (_wrap_lon(x[2:, 2:], x0) + x0)
        out['c2y'][1:-1, 1:-1] = 0.5 * (y[2:, 2:] + y0)
        out['c3x'][1:-1, 1:-1] = 0.5 * (_wrap_lon(x[2:, :-2], x0) + x0)
        out['c3y'][1:-1, 1:-1] = 0.5 * (y[2:, :-2] + y0)
        out['c4x'][1:-1, 1:-1] = 0.5 * (_wrap_lon(x[:-2, :-2], x0) + x0)
        out['c4y'][1:-1, 1:-1] = 0.5 * (y[:-2, :-2] + y0)

        interior = (slice(1, -1), slice(1, -1))
        out['width'][interior] = np.sqrt(
            (out['c1x'][interior] - out['c4x'][interior]) ** 2
            + (out['c1y'][interior] - out['c4y'][interior]) ** 2)
        out['height'][interior] = np.sqrt(
            (out['c2x'][interior] - out['c1x'][interior]) ** 2
            + (out['c2y'][interior] - out['c1y'][interior]) ** 2)

        border = [(k, j) for k in range(Ny) for j in (0, Nx - 1)]
        border += [(k, j) for k in (0, Ny - 1) for j in range(1, Nx - 1)]
    else:
        border = [(k, j) for k in range(Ny) for j in range(Nx)]

    for k, j in border:
        c1, c2, c3, c4, wdth, hgt = compute_cellcorner(x, y, j + 1, k + 1, Nx, Ny)
        out['c1x'][k, j], out['c1y'][k, j] = c1[0], c1[1]
        out['c2x'][k, j], out['c2y'][k, j] = c2[0], c2[1]
        out['c3x'][k, j], out['c3y'][k, j] = c3[0], c3[1]
        out['c4x'][k, j], out['c4y'][k, j] = c4[0], c4[1]
        out['width'][k, j] = wdth
        out['height'][k, j] = hgt

    return out


def cellcorner_polygons(corners):
    """Stack the corner arrays into per-cell closed polygons.

    Returns ``px``/``py`` of shape (Ny, Nx, 5) ordered ``[c4, c1, c2, c3, c4]``
    — the same ring the per-cell code builds by hand.
    """
    px = np.stack([corners['c4x'], corners['c1x'], corners['c2x'],
                   corners['c3x'], corners['c4x']], axis=-1)
    py = np.stack([corners['c4y'], corners['c1y'], corners['c2y'],
                   corners['c3y'], corners['c4y']], axis=-1)
    return px, py
