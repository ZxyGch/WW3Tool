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


_POLY_STATE: list = []


def _init_poly_state(polys):
    global _POLY_STATE
    _POLY_STATE = polys
    try:
        from ..utils.parallel import limit_worker_threads
    except ImportError:
        from utils.parallel import limit_worker_threads
    limit_worker_threads()


def _tile_axis(lo_val, hi_val, lim):
    """Tile edges along one axis, in the order the serial version produced."""
    low = int(np.floor(lo_val))
    high = int(np.ceil(hi_val))
    step = max(1, int(lim)) if lim >= 1 else 1
    axis = np.arange(low, high + step, step, dtype=int).tolist()
    axis = sorted(set(axis)) if axis else [low, high]
    if axis[-1] < high:
        axis.append(high)
    return axis


def _tile_boxes(poly, lim):
    """The sub-boxes a polygon is cut into, in (lx, ly) order.

    Kept separate from the clipping so the boxes can be handed out as
    individual units of work.
    """
    x_axis = _tile_axis(poly['west'], poly['east'], lim)
    y_axis = _tile_axis(poly['south'], poly['north'], lim)
    return [
        [y_axis[ly], x_axis[lx], y_axis[ly + 1], x_axis[lx + 1]]
        for lx in range(len(x_axis) - 1)
        for ly in range(len(y_axis) - 1)
    ]


def _clip_tile(task):
    """Clip one polygon against one of its sub-boxes.

    The unit of work is a *tile*, not a polygon.  Coastline data is extremely
    lopsided -- of 188617 polygons only 165 need splitting at all, and the
    single largest carries 72.9% of the work -- so handing out whole polygons
    caps the speed-up at about 1.4x however many workers are available.  The
    polygons themselves ride the pool initializer, so a tile task is just an
    index and four numbers.
    """
    from .compute_boundary import compute_boundary

    poly_index, box, min_val = task
    poly = _POLY_STATE[poly_index]
    bt, Nb = compute_boundary(box, [poly], min_val, poly['level'], quiet=True)
    if Nb <= 0:
        return []
    return list(bt) if isinstance(bt, list) else [bt]


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

    # Which polygons need cutting, and into what.  Everything else passes
    # through untouched, exactly as the serial version left it.
    plans = []
    tasks = []
    for i, poly in enumerate(bound):
        if poly['width'] > lim or poly['height'] > lim:
            boxes = _tile_boxes(poly, lim)
            plans.append((i, len(tasks), len(boxes)))
            tasks.extend((i, box, min_val) for box in boxes)
        else:
            plans.append((i, -1, 0))

    n_split = sum(1 for _, start, _ in plans if start >= 0)
    if not tasks:
        print(f'  Splitting {N} boundaries: nothing exceeds the limit', flush=True)
        return list(bound)

    # Whether a pool is worth starting is a separate question from how finely
    # the work is diced.  Keep the original measure -- points carried by the
    # polygons that actually get cut -- so small jobs stay serial instead of
    # paying for interpreter start-up; the per-tile tasks below only change
    # how evenly the work spreads once a pool exists.
    work = sum(int(np.size(b['x'])) for b in bound
               if b['width'] > lim or b['height'] > lim)
    n_workers = resolve_workers(work, min_chunk=25_000)
    n_workers = cap_workers_for_memory(n_workers, worker_baseline_bytes() + (64 << 20),
                                       'boundary splitting')
    print(f'  Splitting {n_split} of {N} boundaries into {len(tasks)} tiles '
          f'on {n_workers} worker(s); {describe_cpu_budget()}', flush=True)

    results = run_parallel(_clip_tile, tasks, n_workers,
                           initializer=_init_poly_state, initargs=(list(bound),))

    bound_ingrid = []
    for i, start, count in plans:
        if start < 0:
            bound_ingrid.append(bound[i])
            continue
        for k in range(start, start + count):
            bound_ingrid.extend(results[k])

    print(f'  Completed 100 per cent of {N} boundaries and split into '
          f'{len(bound_ingrid)} boundaries', flush=True)
    return bound_ingrid
