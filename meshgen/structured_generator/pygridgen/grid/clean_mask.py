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
    from ..utils.compute_cellcorner import compute_cellcorner_grid
    from ..utils.parallel import chunk_ranges, describe_cpu_budget, resolve_workers, run_parallel
except ImportError:
    from utils.compute_cellcorner import compute_cellcorner_grid
    from utils.parallel import chunk_ranges, describe_cpu_budget, resolve_workers, run_parallel

# Sample points per cell edge (8x8 grid inside each cell).
_NSAMP = 8

# Below this cell size the 1e-6 containment radius is no longer small compared
# with the cell, so the analytic "rectangle contains its own sample grid"
# shortcut is not taken and matplotlib decides per cell.
_MIN_RECT_SIZE = 1e-3

_BAND_STATE = {}


def _cell_geometry(x, y):
    """Per-cell bounding boxes plus a flag for cells that are plain rectangles."""
    corners = compute_cellcorner_grid(x, y)
    cx = np.stack([corners['c1x'], corners['c2x'], corners['c3x'], corners['c4x']])
    cy = np.stack([corners['c1y'], corners['c2y'], corners['c3y'], corners['c4y']])
    xmin, xmax = cx.min(axis=0), cx.max(axis=0)
    ymin, ymax = cy.min(axis=0), cy.max(axis=0)

    # Axis-aligned, positively oriented rectangle: c4 = (xmin, ymin),
    # c1 = (xmax, ymin), c2 = (xmax, ymax), c3 = (xmin, ymax).  Every point of
    # such a cell's own sample grid is inside it, so the per-cell
    # ``contains_points`` filter can be skipped.
    is_rect = (
        (corners['c4x'] == xmin) & (corners['c3x'] == xmin)
        & (corners['c1x'] == xmax) & (corners['c2x'] == xmax)
        & (corners['c4y'] == ymin) & (corners['c1y'] == ymin)
        & (corners['c2y'] == ymax) & (corners['c3y'] == ymax)
        & ((xmax - xmin) > _MIN_RECT_SIZE) & ((ymax - ymin) > _MIN_RECT_SIZE)
    )
    return xmin, xmax, ymin, ymax, is_rect, corners


def _sample_points(xmin, xmax, ymin, ymax, is_rect, corners, rows, cols):
    """Sample points of the given cells, as a ragged (flat values + counts).

    Mirrors the per-cell construction it replaces: an ``_NSAMP`` x ``_NSAMP``
    grid spanning the cell bounding box, keeping only the points inside the
    cell polygon.
    """
    n = len(rows)
    x0 = xmin[rows, cols]
    x1 = xmax[rows, cols]
    y0 = ymin[rows, cols]
    y1 = ymax[rows, cols]

    # Same values np.linspace(x0, x1, _NSAMP) would produce, done for all cells.
    steps = np.arange(_NSAMP)
    xs = x0[:, None] + ((x1 - x0) / (_NSAMP - 1))[:, None] * steps
    ys = y0[:, None] + ((y1 - y0) / (_NSAMP - 1))[:, None] * steps
    xs[:, -1] = x1
    ys[:, -1] = y1

    # meshgrid(xtt, ytt).flatten() ordering: index = row * _NSAMP + col
    px = np.tile(xs, (1, _NSAMP))
    py = np.repeat(ys, _NSAMP, axis=1)

    rect = is_rect[rows, cols]
    counts = np.full(n, _NSAMP * _NSAMP, dtype=np.int64)
    if np.all(rect):
        return px.ravel(), py.ravel(), counts
    if corners is None:
        raise ValueError('cell corner rings are required for non-rectangular cells')

    out_x = []
    out_y = []
    for i in range(n):
        if rect[i]:
            out_x.append(px[i])
            out_y.append(py[i])
            continue
        k, j = rows[i], cols[i]
        ring_x = np.array([corners['c4x'][k, j], corners['c1x'][k, j],
                           corners['c2x'][k, j], corners['c3x'][k, j],
                           corners['c4x'][k, j]])
        ring_y = np.array([corners['c4y'][k, j], corners['c1y'][k, j],
                           corners['c2y'][k, j], corners['c3y'][k, j],
                           corners['c4y'][k, j]])
        inside = Path(np.column_stack([ring_x, ring_y])).contains_points(
            np.column_stack([px[i], py[i]]), radius=1e-6)
        out_x.append(px[i][inside])
        out_y.append(py[i][inside])
        counts[i] = int(inside.sum())

    return (np.concatenate(out_x) if n else np.empty(0),
            np.concatenate(out_y) if n else np.empty(0),
            counts)


def _ragged_indices(offsets, counts):
    """Flat indices of the concatenated ranges ``[off, off + cnt)``."""
    total = int(counts.sum())
    if total == 0:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)
    starts = np.cumsum(counts) - counts
    owner = np.repeat(np.arange(len(counts)), counts)
    within = np.arange(total) - np.repeat(starts, counts)
    return np.repeat(offsets, counts) + within, owner


def _closed_polygon(bound):
    poly_x = np.asarray(bound['x'])
    poly_y = np.asarray(bound['y'])
    if len(poly_x) == 0:
        return None
    if poly_x[0] != poly_x[-1] or poly_y[0] != poly_y[-1]:
        poly_x = np.append(poly_x, poly_x[0])
        poly_y = np.append(poly_y, poly_y[0])
    return Path(np.column_stack([poly_x, poly_y]))


def _clean_band(task):
    """Clean one horizontal band of the grid against every relevant polygon.

    Bands partition the cells, and a cell's outcome depends only on that cell
    and the polygons, so splitting this way gives exactly the result of the
    single-pass loop.  Only the band's own slice of the grid travels with the
    task; the polygons, which every band needs, come from the pool initializer.
    """
    r0, r1, x, y, band_mask, xmin, xmax, ymin, ymax, is_rect, corners = task
    st = _BAND_STATE
    bounds = st['bounds']
    bboxes = st['bboxes']
    lim = st['lim']

    band_mask = band_mask.copy()

    n_rows, n_cols = band_mask.shape
    cell_id = np.full((n_rows, n_cols), -1, dtype=np.int64)

    # Row / column extents, so a polygon only ever scans the rows and columns
    # its bounding box can reach instead of the whole band.
    row_ymin = y.min(axis=1)
    row_ymax = y.max(axis=1)
    col_xmin = x.min(axis=0)
    col_xmax = x.max(axis=0)

    # Ragged pool of per-cell sample points, grown by doubling.
    cap = 1 << 12
    pool_x = np.empty(cap)
    pool_y = np.empty(cap)
    pool_hit = np.zeros(cap, dtype=bool)
    used = 0
    cell_off = np.empty(0, dtype=np.int64)
    cell_n = np.empty(0, dtype=np.int64)
    cell_in = np.empty(0, dtype=np.int64)

    for bi, bound in enumerate(bounds):
        west, east, south, north = bboxes[bi]

        rows_hit = np.flatnonzero((row_ymax >= south) & (row_ymin <= north))
        if rows_hit.size == 0:
            continue
        cols_hit = np.flatnonzero((col_xmax >= west) & (col_xmin <= east))
        if cols_hit.size == 0:
            continue
        ra, rb = int(rows_hit[0]), int(rows_hit[-1]) + 1
        ca, cb = int(cols_hit[0]), int(cols_hit[-1]) + 1

        sub_x = x[ra:rb, ca:cb]
        sub_y = y[ra:rb, ca:cb]
        in_bnd = ((sub_x >= west) & (sub_x <= east)
                  & (sub_y >= south) & (sub_y <= north)
                  & (band_mask[ra:rb, ca:cb] == 1))
        rows, cols = np.where(in_bnd)
        if rows.size == 0:
            continue
        rows = rows + ra
        cols = cols + ca

        poly_path = _closed_polygon(bound)
        if poly_path is None:
            continue

        ids = cell_id[rows, cols]
        fresh = ids < 0
        if np.any(fresh):
            f_rows = rows[fresh]
            f_cols = cols[fresh]
            new_x, new_y, new_counts = _sample_points(
                xmin, xmax, ymin, ymax, is_rect, corners, f_rows, f_cols)

            need = used + int(new_counts.sum())
            if need > cap:
                while cap < need:
                    cap *= 2
                pool_x = np.resize(pool_x, cap)
                pool_y = np.resize(pool_y, cap)
                grown = np.zeros(cap, dtype=bool)
                grown[:used] = pool_hit[:used]
                pool_hit = grown
            pool_x[used:need] = new_x
            pool_y[used:need] = new_y
            pool_hit[used:need] = False

            new_off = used + np.cumsum(new_counts) - new_counts
            new_ids = len(cell_off) + np.arange(len(f_rows))
            cell_id[f_rows, f_cols] = new_ids
            cell_off = np.concatenate([cell_off, new_off])
            cell_n = np.concatenate([cell_n, new_counts])
            cell_in = np.concatenate([cell_in, np.zeros(len(f_rows), dtype=np.int64)])
            used = need
            ids = cell_id[rows, cols]

        counts = cell_n[ids]
        alive = counts > 0
        if not np.all(alive):
            rows, cols, ids, counts = rows[alive], cols[alive], ids[alive], counts[alive]
            if ids.size == 0:
                continue

        flat, owner = _ragged_indices(cell_off[ids], counts)
        untested = ~pool_hit[flat]
        flat = flat[untested]
        owner = owner[untested]

        if flat.size:
            inout = poly_path.contains_points(
                np.column_stack([pool_x[flat], pool_y[flat]]), radius=1e-8)
            hit_flat = flat[inout]
            pool_hit[hit_flat] = True
            cell_in[ids] += np.bincount(owner[inout], minlength=len(ids))

        prop = cell_in[ids] / counts
        drown = (np.round(prop * 10) / 10) >= lim
        if np.any(drown):
            band_mask[rows[drown], cols[drown]] = 0

    return r0, r1, band_mask


def _init_band_state(state):
    _BAND_STATE.clear()
    _BAND_STATE.update(state)
    try:
        from ..utils.parallel import limit_worker_threads
    except ImportError:
        from utils.parallel import limit_worker_threads
    limit_worker_threads()


def clean_mask(x, y, mask, bound_ingrid, lim, offset, workers=None):
    """
    Clean mask by checking if wet cells lie outside boundary polygons.

    The grid is split into horizontal bands that are processed in parallel;
    each band sees every polygon, and since bands do not share cells the
    result is the same as the original single-pass loop.
    """
    N1 = len(bound_ingrid)
    mask = np.asarray(mask).copy()
    if N1 == 0:
        return mask

    Ny, Nx = x.shape
    print(f'Processing {N1} boundaries...', flush=True)

    xmin, xmax, ymin, ymax, is_rect, corners = _cell_geometry(x, y)

    bound_bboxes = np.array([
        [b['west'] - offset, b['east'] + offset,
         b['south'] - offset, b['north'] + offset] for b in bound_ingrid
    ], dtype=float)

    # Only spread across processes once there is enough work to pay back pool
    # start-up (which costs a full interpreter import on spawn platforms).
    n_workers = resolve_workers(Ny * Nx, min_chunk=20_000, requested=workers)
    n_workers = max(1, min(n_workers, Ny // 8 if Ny >= 16 else 1))
    print(f'  Land-sea mask clean up on {n_workers} worker(s); {describe_cpu_budget()}',
          flush=True)

    bands = chunk_ranges(Ny, n_workers * 4 if n_workers > 1 else 1)
    tasks = []
    for r0, r1 in bands:
        band_rect = is_rect[r0:r1]
        # The corner rings are only needed where a cell is not a plain
        # rectangle, so most bands do not carry them at all.
        band_corners = (None if bool(band_rect.all())
                        else {k: v[r0:r1] for k, v in corners.items()})
        tasks.append((r0, r1, x[r0:r1], y[r0:r1], mask[r0:r1],
                      xmin[r0:r1], xmax[r0:r1], ymin[r0:r1], ymax[r0:r1],
                      band_rect, band_corners))

    state = {
        'bounds': [{'x': np.asarray(b['x']), 'y': np.asarray(b['y'])}
                   for b in bound_ingrid],
        'bboxes': bound_bboxes, 'lim': lim,
    }

    results = run_parallel(_clean_band, tasks, n_workers,
                           initializer=_init_band_state, initargs=(state,))

    for r0, r1, band in results:
        mask[r0:r1] = band

    print('Completed 100 per cent of land sea mask clean up', flush=True)
    return mask
