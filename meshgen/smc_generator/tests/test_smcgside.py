from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


GENERATOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GENERATOR_DIR))

from smcgside import generate_side_files, generate_sides


def _regular_cells() -> np.ndarray:
    return np.asarray(
        [
            [0, 0, 1, 1, 10],
            [1, 0, 1, 1, 20],
            [0, 1, 1, 1, 30],
            [1, 1, 1, 1, 40],
        ],
        dtype=np.int64,
    )


def test_regular_grid_matches_fortran_face_layout() -> None:
    iside, jside = generate_sides(_regular_cells(), nlon=2)

    np.testing.assert_array_equal(
        iside,
        np.asarray(
            [
                [1, 0, 1, 2, 1, 2, 1],
                [0, 0, 1, 1, 2, 1, 2],
                [1, 1, 1, 4, 3, 4, 3],
                [0, 1, 1, 3, 4, 3, 4],
            ],
            dtype=np.int64,
        ),
    )
    np.testing.assert_array_equal(
        jside,
        np.asarray(
            [
                [0, 1, 1, 0, 1, 3, 0, 1],
                [1, 1, 1, 0, 2, 4, 0, 1],
                [0, 0, 1, 0, 0, 1, 3, 1],
                [1, 0, 1, 0, 0, 2, 4, 1],
                [0, 2, 1, 1, 3, 0, 0, 1],
                [1, 2, 1, 2, 4, 0, 0, 1],
            ],
            dtype=np.int64,
        ),
    )


def test_north_polar_cell_replaces_north_boundary() -> None:
    cells = np.vstack((_regular_cells(), [0, 2, 2, 1, 50]))
    _, jside = generate_sides(cells, nlon=2, npol=1)

    north_faces = jside[jside[:, 1] == 2]
    np.testing.assert_array_equal(north_faces[:, 4], [3, 4])
    np.testing.assert_array_equal(north_faces[:, 5], [5, 5])


def test_direct_api_reads_cells_and_writes_raw_files(tmp_path: Path) -> None:
    cell_file = tmp_path / "grid_cell.dat"
    np.savetxt(
        cell_file,
        _regular_cells(),
        fmt="%d",
        header="4 4",
        comments="",
    )

    result = generate_side_files(
        cell_file,
        grid_name="Grid",
        output_dir=tmp_path,
        levels=1,
        nlon=2,
    )

    assert result.global_cells == 4
    np.testing.assert_array_equal(
        np.loadtxt(tmp_path / "GridISide.d", dtype=np.int64), result.iside
    )
    np.testing.assert_array_equal(
        np.loadtxt(tmp_path / "GridJSide.d", dtype=np.int64), result.jside
    )
