#!/usr/bin/env python3
"""Pure-Python SMC cell-face generator compatible with ``SMCGSideMP``.

The original implementation is ``SMCGTools/F90SMC/SMCGSideMP.f90``.  This
module keeps its one-based cell identifiers, boundary-cell convention, polar
connections, row order, and fixed-width ``ISide.d`` / ``JSide.d`` formats.
"""

from __future__ import annotations

import argparse
import math
import shlex
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class SideInput:
    grid_name: str
    ncl: int
    nfc: int
    levels: int
    nlon: int
    nlat: int
    npol: int
    cell_file: Path


@dataclass(frozen=True)
class SideResult:
    iside: np.ndarray
    jside: np.ndarray
    global_cells: int
    arctic_cells: int = 0
    arctic_boundary_cells: int = 0
    global_boundary_index: int = 0


def read_side_input(path: str | Path) -> SideInput:
    """Read the four-line input format accepted by ``SMCGSideMP``."""
    input_path = Path(path).expanduser().resolve()
    lines = [line.strip() for line in input_path.read_text(encoding="utf-8").splitlines()]
    if len(lines) < 4:
        raise ValueError(f"SMCGSide input requires four lines: {input_path}")
    grid_name = lines[0].split()[0]
    ncl, nfc, levels = (int(value) for value in lines[1].split()[:3])
    nlon, nlat, npol = (int(value) for value in lines[2].split()[:3])
    tokens = shlex.split(lines[3])
    if not tokens:
        raise ValueError(f"Missing cell file in SMCGSide input: {input_path}")
    cell_file = Path(tokens[0]).expanduser()
    if not cell_file.is_absolute():
        cell_file = (input_path.parent / cell_file).resolve()
    return SideInput(grid_name, ncl, nfc, levels, nlon, nlat, npol, cell_file)


def _read_cells(path: Path, levels: int, npol: int) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    with path.open("r", encoding="utf-8") as handle:
        header = [int(value) for value in handle.readline().split()]
    if npol > 0:
        if len(header) < 3:
            raise ValueError(f"Arctic cell header requires NArc NArB NGLB: {path}")
        narc, narb, nglb = header[:3]
        count = narc
        metadata = (nglb, narc, narb, nglb)
    else:
        if len(header) < 2:
            raise ValueError(f"Cell header requires NGLo and level counts: {path}")
        count = header[0]
        if len(header[1:]) != levels:
            raise ValueError(
                f"Cell header has {len(header[1:])} level counts, expected {levels}: {path}"
            )
        metadata = (count, 0, 0, 0)
    cells = np.loadtxt(path, dtype=np.int64, skiprows=1, max_rows=count)
    cells = np.atleast_2d(cells)
    if cells.shape != (count, 5):
        raise ValueError(f"Expected {count} rows with five cell columns, got {cells.shape}: {path}")
    if np.any(cells[:, 2:4] <= 0):
        raise ValueError(f"SMC cell widths and heights must be positive: {path}")
    return np.ascontiguousarray(cells), metadata


def _boundary_cell_id(size: int) -> int:
    if size <= 0:
        raise ValueError(f"Boundary face size must be positive, got {size}")
    return -int(math.log(float(size)) / math.log(2.0) + 0.01)


def _group_edges(coordinates: np.ndarray) -> dict[int, list[int]]:
    groups: dict[int, list[int]] = {}
    for index, coordinate in enumerate(coordinates):
        groups.setdefault(int(coordinate), []).append(index)
    return groups


def _overlapping_pairs(
    cells: np.ndarray,
    first: list[int],
    second: list[int],
    *,
    start_column: int,
    size_column: int,
) -> list[tuple[int, int]]:
    """Pair two non-overlapping interval partitions along one shared edge."""
    first = sorted(first, key=lambda index: (int(cells[index, start_column]), index))
    second = sorted(second, key=lambda index: (int(cells[index, start_column]), index))
    pairs: list[tuple[int, int]] = []
    i = j = 0
    while i < len(first) and j < len(second):
        left = first[i]
        right = second[j]
        left_start = int(cells[left, start_column])
        right_start = int(cells[right, start_column])
        left_stop = left_start + int(cells[left, size_column])
        right_stop = right_start + int(cells[right, size_column])
        if left_stop <= right_start:
            i += 1
            continue
        if right_stop <= left_start:
            j += 1
            continue
        if (
            left_start >= right_start and left_stop <= right_stop
        ) or (
            right_start >= left_start and right_stop <= left_stop
        ):
            pairs.append((left, right))
        if left_stop <= right_stop:
            i += 1
        if right_stop <= left_stop:
            j += 1
    return pairs


def _mark_coverage(length: int, origin: int, faces: list[list[int]], *, axis: int) -> np.ndarray:
    covered = np.zeros(length, dtype=np.bool_)
    for face in faces:
        start = int(face[axis]) - origin
        stop = start + int(face[2])
        if start < 0 or stop > length:
            raise ValueError(
                f"Face [{start}, {stop}) lies outside cell side [0, {length})"
            )
        covered[start:stop] = True
    return covered


def _missing_runs(covered: np.ndarray) -> list[tuple[int, int]]:
    missing = ~covered
    if not np.any(missing):
        return []
    edges = np.diff(np.r_[False, missing, False].astype(np.int8))
    starts = np.flatnonzero(edges == 1)
    stops = np.flatnonzero(edges == -1)
    return [(int(start), int(stop - start)) for start, stop in zip(starts, stops)]


def _internal_faces(cells: np.ndarray, nregular: int, nlon: int) -> tuple[list[list[int]], list[list[int]]]:
    regular = cells[:nregular]
    west_groups = _group_edges(regular[:, 0])
    east_coordinates = (regular[:, 0] + regular[:, 2]) % nlon
    east_groups = _group_edges(east_coordinates)
    south_groups = _group_edges(regular[:, 1])
    north_groups = _group_edges(regular[:, 1] + regular[:, 3])
    iside: list[list[int]] = []
    jside: list[list[int]] = []

    u_pairs: list[tuple[int, int]] = []
    for coordinate, left_cells in east_groups.items():
        u_pairs.extend(
            _overlapping_pairs(
                regular,
                left_cells,
                west_groups.get(coordinate, []),
                start_column=1,
                size_column=3,
            )
        )
    for left, right in sorted(u_pairs):
        east = int(east_coordinates[left])
        y = max(int(regular[left, 1]), int(regular[right, 1]))
        height = min(int(regular[left, 3]), int(regular[right, 3]))
        iside.append([east, y, height, 0, left + 1, right + 1, 0])

    v_pairs: list[tuple[int, int]] = []
    for coordinate, lower_cells in north_groups.items():
        v_pairs.extend(
            _overlapping_pairs(
                regular,
                lower_cells,
                south_groups.get(coordinate, []),
                start_column=0,
                size_column=2,
            )
        )
    for lower, upper in sorted(v_pairs):
        north = int(regular[lower, 1] + regular[lower, 3])
        x = max(int(regular[lower, 0]), int(regular[upper, 0]))
        width = min(int(regular[lower, 2]), int(regular[upper, 2]))
        height = min(int(regular[lower, 3]), int(regular[upper, 3]))
        jside.append([x, north, width, 0, lower + 1, upper + 1, 0, height])
    return iside, jside


def _append_u_boundaries(cells: np.ndarray, nregular: int, nlon: int, faces: list[list[int]]) -> None:
    west_faces: dict[int, list[list[int]]] = {}
    east_faces: dict[int, list[list[int]]] = {}
    for face in faces:
        east_faces.setdefault(face[4], []).append(face)
        west_faces.setdefault(face[5], []).append(face)

    for cell_index in range(nregular):
        cell_id = cell_index + 1
        x, y, width, height = (int(value) for value in cells[cell_index, :4])
        east = x + width
        if east >= nlon:
            east -= nlon
        west_covered = _mark_coverage(height, y, west_faces.get(cell_id, []), axis=1)
        east_covered = _mark_coverage(height, y, east_faces.get(cell_id, []), axis=1)

        west_runs = _missing_runs(west_covered)
        east_runs = _missing_runs(east_covered)
        if len(west_runs) == 1 and west_runs[0] == (0, height):
            faces.append([x, y, height, 0, _boundary_cell_id(height), cell_id, 0])
            west_runs = []
        if len(east_runs) == 1 and east_runs[0] == (0, height):
            faces.append([east, y, height, 0, cell_id, _boundary_cell_id(height), 0])
            east_runs = []
        for offset, size in west_runs:
            faces.append([x, y + offset, size, 0, _boundary_cell_id(size), cell_id, 0])
        for offset, size in east_runs:
            faces.append([east, y + offset, size, 0, cell_id, _boundary_cell_id(size), 0])


def _polar_cell_ids(cells: np.ndarray, npol: int) -> tuple[int, int]:
    if npol == 0:
        return 0, 0
    if npol == 1:
        return len(cells), 0
    if npol == 2:
        last = len(cells)
        if cells[-1, 1] > cells[-2, 1]:
            return last, last - 1
        return last - 1, last
    raise ValueError(f"SMCGSide supports zero, one, or two polar cells, got {npol}")


def _append_v_boundaries(cells: np.ndarray, nregular: int, npol: int, faces: list[list[int]]) -> None:
    south_faces: dict[int, list[list[int]]] = {}
    north_faces: dict[int, list[list[int]]] = {}
    for face in faces:
        north_faces.setdefault(face[4], []).append(face)
        south_faces.setdefault(face[5], []).append(face)
    north_pole, south_pole = _polar_cell_ids(cells, npol)

    for cell_index in range(nregular):
        cell_id = cell_index + 1
        x, y, width, height = (int(value) for value in cells[cell_index, :4])
        north = y + height
        south_covered = _mark_coverage(width, x, south_faces.get(cell_id, []), axis=0)
        north_covered = _mark_coverage(width, x, north_faces.get(cell_id, []), axis=0)
        south_runs = _missing_runs(south_covered)
        north_runs = _missing_runs(north_covered)

        if len(south_runs) == 1 and south_runs[0] == (0, width):
            lower = _boundary_cell_id(width)
            if south_pole and int(cells[south_pole - 1, 1] + cells[south_pole - 1, 3]) == y:
                lower = south_pole
            faces.append([x, y, width, 0, lower, cell_id, 0, height])
            south_runs = []
        if len(north_runs) == 1 and north_runs[0] == (0, width):
            upper = _boundary_cell_id(width)
            if north_pole and north == int(cells[north_pole - 1, 1]):
                upper = north_pole
            faces.append([x, north, width, 0, cell_id, upper, 0, height])
            north_runs = []
        for offset, size in south_runs:
            faces.append([x + offset, y, size, 0, _boundary_cell_id(size), cell_id, 0, height])
        for offset, size in north_runs:
            faces.append([x + offset, north, size, 0, cell_id, _boundary_cell_id(size), 0, height])


def _fill_second_neighbors(
    faces: list[list[int]], *, coordinate_axis: int, polar_floor: int = 0
) -> None:
    by_right: dict[int, list[list[int]]] = {}
    by_left: dict[int, list[list[int]]] = {}
    for face in faces:
        by_left.setdefault(face[4], []).append(face)
        by_right.setdefault(face[5], []).append(face)

    for face in faces:
        left, right = face[4], face[5]
        face_start = face[coordinate_axis]
        face_end = face_start + face[2]
        if left <= 0 or left > polar_floor > 0:
            face[3] = left
        else:
            face[3] = left
            for candidate in by_right.get(left, ()):
                candidate_start = candidate[coordinate_axis]
                candidate_end = candidate_start + candidate[2]
                if face_start == candidate_start or face_end == candidate_end:
                    face[3] = candidate[4]
        if right <= 0 or right > polar_floor > 0:
            face[6] = right
        else:
            face[6] = right
            for candidate in by_left.get(right, ()):
                candidate_start = candidate[coordinate_axis]
                candidate_end = candidate_start + candidate[2]
                if face_start == candidate_start or face_end == candidate_end:
                    face[6] = candidate[5]


def generate_sides(cells: np.ndarray, *, nlon: int, npol: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Generate raw Fortran-compatible ISIDE and JSIDE arrays."""
    cells = np.asarray(cells, dtype=np.int64)
    if cells.ndim != 2 or cells.shape[1] != 5:
        raise ValueError(f"Expected an (N, 5) SMC cell array, got {cells.shape}")
    nregular = len(cells) - npol
    if nregular <= 0:
        raise ValueError("SMC grid must contain at least one non-polar cell")
    iside, jside = _internal_faces(cells, nregular, int(nlon))
    _append_u_boundaries(cells, nregular, int(nlon), iside)
    _append_v_boundaries(cells, nregular, int(npol), jside)
    _fill_second_neighbors(iside, coordinate_axis=1)
    _fill_second_neighbors(jside, coordinate_axis=0, polar_floor=nregular)
    return np.asarray(iside, dtype=np.int64), np.asarray(jside, dtype=np.int64)


_ISIDE_FORMAT = ["%7d", "%6d", "%5d", "%8d", "%8d", "%8d", "%8d"]
_JSIDE_FORMAT = ["%7d", "%6d", "%5d", "%8d", "%8d", "%8d", "%8d", "%4d"]


def write_raw_sides(grid_name: str, directory: str | Path, iside: np.ndarray, jside: np.ndarray) -> None:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    np.savetxt(root / f"{grid_name}ISide.d", iside, fmt=_ISIDE_FORMAT, delimiter="")
    np.savetxt(root / f"{grid_name}JSide.d", jside, fmt=_JSIDE_FORMAT, delimiter="")


def generate_side_files(
    cell_file: str | Path,
    *,
    grid_name: str,
    output_dir: str | Path,
    levels: int,
    nlon: int,
    npol: int = 0,
) -> SideResult:
    """Generate raw side files directly from an SMC cell file."""
    cell_path = Path(cell_file).expanduser().resolve()
    cells, metadata = _read_cells(cell_path, int(levels), int(npol))
    iside, jside = generate_sides(cells, nlon=int(nlon), npol=int(npol))
    write_raw_sides(grid_name, output_dir, iside, jside)
    nglo, narc, narb, nglb = metadata
    return SideResult(iside, jside, nglo, narc, narb, nglb)


def generate_from_input(path: str | Path) -> SideResult:
    config = read_side_input(path)
    return generate_side_files(
        config.cell_file,
        grid_name=config.grid_name,
        output_dir=Path(path).expanduser().resolve().parent,
        levels=config.levels,
        nlon=config.nlon,
        npol=config.npol,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate SMC ISIDE/JSIDE arrays in pure Python")
    parser.add_argument("input", help="SMCGSide four-line input file")
    args = parser.parse_args(argv)
    started = time.monotonic()
    result = generate_from_input(args.input)
    print(
        f"Python SMCGSide completed: {len(result.iside)} U-faces, "
        f"{len(result.jside)} V-faces in {time.monotonic() - started:.2f}s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
