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
    from ..utils.parallel import (cap_workers_for_memory, chunk_ranges, describe_cpu_budget,
                                  resolve_workers, run_parallel, shared_state_bytes,
                                  worker_baseline_bytes)
except ImportError:
    from utils.compute_cellcorner import compute_cellcorner_grid
    from utils.parallel import (cap_workers_for_memory, chunk_ranges, describe_cpu_budget,
                                resolve_workers, run_parallel, shared_state_bytes,
                                  worker_baseline_bytes)

# Sample points per cell edge (8x8 grid inside each cell).
_NSAMP = 8

# Below this cell size the 1e-6 containment radius is no longer small compared
# with the cell, so the analytic "rectangle contains its own sample grid"
# shortcut is not taken and matplotlib decides per cell.
_MIN_RECT_SIZE = 1e-3

_BAND_STATE = {}

# Per band cell: the seven float64 grids and the is_rect flag that travel
# with a task, plus the uint64/uint64/int16/bool state the worker builds.
_BAND_BYTES_PER_CELL = 7 * 8 + 1 + (8 + 8 + 2 + 1)


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


_ALL_BITS = np.uint64(0xFFFFFFFFFFFFFFFF)
_BIT_INDEX = np.arange(_NSAMP * _NSAMP, dtype=np.uint64)
_BIT_COL = (_BIT_INDEX % np.uint64(_NSAMP)).astype(np.int64)
_BIT_ROW = (_BIT_INDEX // np.uint64(_NSAMP)).astype(np.int64)


def _popcount(masks):
    """Bits set per element of a uint64 array."""
    if hasattr(np, 'bitwise_count'):
        return np.bitwise_count(masks).astype(np.int64)
    bytes_view = masks.astype('<u8').view(np.uint8).reshape(-1, 8)
    return np.unpackbits(bytes_view, axis=1).sum(axis=1).astype(np.int64)


def _bit_coords(x0, x1, y0, y1, bits):
    """Coordinates of sample point *bits* of the cells with the given boxes.

    Same values the ``linspace``-per-cell construction produced, addressed by
    the flat ``row * _NSAMP + col`` index the bitmasks are keyed on.  The last
    row and column are pinned to the box edge exactly, as ``linspace`` does.
    """
    col = _BIT_COL[bits]
    row = _BIT_ROW[bits]
    last = _NSAMP - 1
    xv = np.where(col == last, x1, x0 + (x1 - x0) / last * col)
    yv = np.where(row == last, y1, y0 + (y1 - y0) / last * row)
    return xv, yv


def _cell_point_masks(xmin, xmax, ymin, ymax, is_rect, corners, rows, cols):
    """Which of a cell's ``_NSAMP**2`` sample points fall inside the cell.

    Returned as one uint64 per cell.  A plain rectangle contains its whole
    sample grid, so only the rare non-rectangular cell needs matplotlib.
    """
    n = len(rows)
    masks = np.full(n, _ALL_BITS, dtype=np.uint64)
    if n == 0:
        return masks

    rect = is_rect[rows, cols]
    if np.all(rect):
        return masks
    if corners is None:
        raise ValueError('cell corner rings are required for non-rectangular cells')

    x0 = xmin[rows, cols]
    x1 = xmax[rows, cols]
    y0 = ymin[rows, cols]
    y1 = ymax[rows, cols]
    shifts = _BIT_INDEX
    for i in np.flatnonzero(~rect):
        k, j = rows[i], cols[i]
        px, py = _bit_coords(x0[i], x1[i], y0[i], y1[i],
                             np.arange(_NSAMP * _NSAMP))
        ring_x = np.array([corners['c4x'][k, j], corners['c1x'][k, j],
                           corners['c2x'][k, j], corners['c3x'][k, j],
                           corners['c4x'][k, j]])
        ring_y = np.array([corners['c4y'][k, j], corners['c1y'][k, j],
                           corners['c2y'][k, j], corners['c3y'][k, j],
                           corners['c4y'][k, j]])
        inside = Path(np.column_stack([ring_x, ring_y])).contains_points(
            np.column_stack([px, py]), radius=1e-6)
        masks[i] = np.bitwise_or.reduce(
            np.where(inside, np.uint64(1) << shifts, np.uint64(0)))
    return masks


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

    Per-cell state is two uint64 bitmasks over the cell's sample grid rather
    than the sample coordinates themselves: 17 bytes a cell instead of the
    ~1 KB that storing 64 coordinate pairs costs, which is what used to make
    peak memory scale as a kilobyte per coastal cell.  The coordinates are
    cheap to recompute from the cell's bounding box for the points that still
    need testing.
    """
    r0, r1, x, y, band_mask, xmin, xmax, ymin, ymax, is_rect, corners = task
    st = _BAND_STATE
    bounds = st['bounds']
    bboxes = st['bboxes']
    lim = st['lim']

    band_mask = band_mask.copy()
    n_rows, n_cols = band_mask.shape

    # Dense over the band, and small: 8 + 8 + 2 + 1 bytes a cell.
    cell_full = np.zeros((n_rows, n_cols), dtype=np.uint64)   # points inside the cell
    cell_hit = np.zeros((n_rows, n_cols), dtype=np.uint64)    # points inside some polygon
    cell_cnt = np.zeros((n_rows, n_cols), dtype=np.int16)
    cell_seen = np.zeros((n_rows, n_cols), dtype=bool)

    # Row / column extents, so a polygon only ever scans the rows and columns
    # its bounding box can reach instead of the whole band.
    row_ymin = y.min(axis=1)
    row_ymax = y.max(axis=1)
    col_xmin = x.min(axis=0)
    col_xmax = x.max(axis=0)

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

        fresh = ~cell_seen[rows, cols]
        if np.any(fresh):
            f_rows = rows[fresh]
            f_cols = cols[fresh]
            masks = _cell_point_masks(xmin, xmax, ymin, ymax, is_rect, corners,
                                      f_rows, f_cols)
            cell_full[f_rows, f_cols] = masks
            cell_cnt[f_rows, f_cols] = _popcount(masks)
            cell_seen[f_rows, f_cols] = True

        counts = cell_cnt[rows, cols]
        alive = counts > 0
        if not np.all(alive):
            rows, cols, counts = rows[alive], cols[alive], counts[alive]
            if rows.size == 0:
                continue

        todo = cell_full[rows, cols] & ~cell_hit[rows, cols]
        owner, bits = np.nonzero(
            (todo[:, None] >> _BIT_INDEX) & np.uint64(1))
        if owner.size:
            xv, yv = _bit_coords(xmin[rows, cols][owner], xmax[rows, cols][owner],
                                 ymin[rows, cols][owner], ymax[rows, cols][owner],
                                 bits)
            inout = poly_path.contains_points(np.column_stack([xv, yv]), radius=1e-8)
            if np.any(inout):
                hit_owner = owner[inout]
                hit_bits = bits[inout].astype(np.uint64)
                # Several points of one cell can land in the same polygon, so
                # OR the per-point bits together per cell before merging.
                add = np.zeros(len(rows), dtype=np.uint64)
                np.bitwise_or.at(add, hit_owner, np.uint64(1) << hit_bits)
                cell_hit[rows, cols] |= add

        prop = _popcount(cell_hit[rows, cols]) / counts
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

    # Each worker gets its own copy of the polygons, so a wide pool multiplies
    # the one big thing this stage holds.  Let the memory budget, not the core
    # count, decide how wide it may be.
    state_bytes = sum(np.asarray(b['x']).nbytes + np.asarray(b['y']).nbytes
                      for b in bound_ingrid)
    band_cells = -(-Ny // max(1, n_workers * 4)) * Nx
    # Polygons ride the initializer (shared under fork); the band slices are
    # pickled per task on every platform.
    per_worker = (worker_baseline_bytes() + shared_state_bytes(state_bytes)
                  + band_cells * _BAND_BYTES_PER_CELL)
    if workers is None:
        n_workers = cap_workers_for_memory(n_workers, per_worker, 'land-sea mask clean up')
    print(f'  Land-sea mask clean up on {n_workers} worker(s); {describe_cpu_budget()}; '
          f'~{per_worker / (1 << 20):.0f} MiB per worker',
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
