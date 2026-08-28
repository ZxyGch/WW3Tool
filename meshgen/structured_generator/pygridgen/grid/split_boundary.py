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

try:
    from ..utils.parallel import (cap_workers_for_memory, describe_cpu_budget,
                                  resolve_workers, run_parallel, worker_baseline_bytes)
except ImportError:
    from utils.parallel import (cap_workers_for_memory, describe_cpu_budget,
                                resolve_workers, run_parallel, worker_baseline_bytes)


def _split_one(task):
    """Split a single polygon into the sub-boxes that fall inside the grid.

    Polygons are independent of one another, so this is the unit of work that
    gets spread across processes; results are reassembled in input order.
    """
    from .compute_boundary import compute_boundary

    poly, lim, min_val = task

    if not (poly['width'] > lim or poly['height'] > lim):
        return [poly]

    low = int(np.floor(poly['west']))
    high = int(np.ceil(poly['east']))
    step = max(1, int(lim)) if lim >= 1 else 1
    x_axis = np.arange(low, high + step, step, dtype=int).tolist()
    if len(x_axis) == 0:
        x_axis = [low, high]
    else:
        x_axis = sorted(set(x_axis))
    if x_axis[-1] < high:
        x_axis.append(high)

    low = int(np.floor(poly['south']))
    high = int(np.ceil(poly['north']))
    step = max(1, int(lim)) if lim >= 1 else 1
    y_axis = np.arange(low, high + step, step, dtype=int).tolist()
    if len(y_axis) == 0:
        y_axis = [low, high]
    else:
        y_axis = sorted(set(y_axis))
    if y_axis[-1] < high:
        y_axis.append(high)

    pieces = []
    for lx in range(len(x_axis) - 1):
        for ly in range(len(y_axis) - 1):
            bt, Nb = compute_boundary(
                [y_axis[ly], x_axis[lx], y_axis[ly + 1], x_axis[lx + 1]],
                [poly],
                min_val,
                poly['level'],
            )
            if Nb > 0:
                if isinstance(bt, list):
                    pieces.extend(bt)
                else:
                    pieces.append(bt)
    return pieces


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

    N = len(bound)
    if N == 0:
        return []

    # Cost is driven by the polygons that actually get subdivided and by how
    # many points they carry, not by the polygon count.
    work = sum(int(np.size(b['x'])) for b in bound
               if b['width'] > lim or b['height'] > lim)
    n_workers = resolve_workers(work, min_chunk=25_000)
    n_workers = cap_workers_for_memory(n_workers, worker_baseline_bytes() + (64 << 20),
                                       'boundary splitting')
    print(f'  Splitting {N} boundaries on {n_workers} worker(s); '
          f'{describe_cpu_budget()}', flush=True)

    tasks = [(bound[i], lim, min_val) for i in range(N)]
    results = run_parallel(_split_one, tasks, n_workers)

    bound_ingrid = []
    for pieces in results:
        bound_ingrid.extend(pieces)

    print(f'  Completed 100 per cent of {N} boundaries and split into '
          f'{len(bound_ingrid)} boundaries', flush=True)
    return bound_ingrid
