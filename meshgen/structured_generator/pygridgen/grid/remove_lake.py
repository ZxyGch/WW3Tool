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
from scipy import ndimage

# 4-connectivity, matching the prev/next x and y neighbours of the original
# flood fill.
_STRUCTURE = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool)


def _first_seen(labels, n_labels):
    """Flat index at which each label first appears in row-major order."""
    flat = labels.ravel()
    nz = flat > 0
    first = np.full(n_labels + 1, flat.size, dtype=np.int64)
    # Writing back to front leaves the earliest position of each label.
    first[flat[nz][::-1]] = np.arange(flat.size, dtype=np.int64)[nz][::-1]
    return first


def _merge_wraparound(labels, n_labels):
    """Union labels joined across the periodic longitude seam.

    Returns a mapping ``old label -> new label`` where the new labels are
    numbered by first appearance in row-major order, exactly as the original
    sequential flood fill numbered its water bodies.
    """
    parent = list(range(n_labels + 1))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    west = labels[:, 0]
    east = labels[:, -1]
    seam = np.where((west > 0) & (east > 0))[0]
    for row in seam:
        union(int(west[row]), int(east[row]))

    first = _first_seen(labels, n_labels)
    mapping = np.zeros(n_labels + 1, dtype=np.int64)
    next_id = 0
    for old in np.argsort(first[1:], kind='stable') + 1:
        root = find(int(old))
        if mapping[root] == 0:
            next_id += 1
            mapping[root] = next_id
        mapping[old] = mapping[root]
    return mapping, next_id


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
    mask = np.asarray(mask)
    wet = mask == 1

    # Connected-component labelling replaces the original cell-by-cell flood
    # fill; scipy numbers components by first appearance in row-major order,
    # which is the order the flood fill used, so the IDs are the same.
    labels, n_labels = ndimage.label(wet, structure=_STRUCTURE)

    if igl == 1 and n_labels > 0 and labels.shape[1] > 1:
        mapping, n_labels = _merge_wraparound(labels, n_labels)
        labels = mapping[labels]

    mask_map = np.where(wet, labels, -1).astype(mask.dtype, copy=False)

    counts = np.bincount(labels.ravel(), minlength=n_labels + 1)
    N1 = {}
    for body in range(1, n_labels + 1):
        N1[body] = int(counts[body])
        print(f'{N1[body]} Wet cells set to flag id {body}', flush=True)

    mask_mod = mask.copy()

    if lake_tol < 0:
        # Keep only the largest water body
        if len(N1) > 0:
            pos = max(N1, key=N1.get)
            drop = [i for i in range(1, n_labels + 1) if i != pos]
        else:
            drop = []
    else:
        # Remove water bodies smaller than lake_tol
        drop = [i for i in range(1, n_labels + 1) if N1[i] < lake_tol]

    if drop:
        mask_mod[np.isin(labels, drop)] = 0
        for i in drop:
            print(f'Masking out cells with flag set to {i}', flush=True)

    return mask_mod, mask_map
