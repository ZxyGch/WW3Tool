#!/usr/bin/env python3
"""
Generate SMC grid data files from grid.json (or path via --config / --grid).

Final outputs in output_dir (smcellgen/smcellbdy write to a temp stem, then rename):

- grid_cell.dat — SMC MCELS (from *Cels.dat)
- grid_iside.dat / grid_jside.dat — ISIDE / JSIDE (SMCGTools ``SMCGSideMP`` + count step)
- grid_subtr.dat — SUBTR (zero obstruction); ``ww3_grid`` opens after MCELS/ISIDE/JSIDE
- grid_boundary.dat — BUNDY only when ``NBISMC > 0`` is intended: regional domain and
  boundary strip generation enabled; use ``boundary.n_bismc: 0`` to skip the file even
  when regional.
- grid_arctic_cells.dat — MBARC (from *BArc.dat) when ``grid.arctic`` is true;
  grid_aisid.dat / grid_ajsid.dat — AISID / AJSID from a second SMCGSideMP run on the
  Arctic cell file (same toolchain as ISIDE/JSIDE).
- grid.json (in ``output_dir``) — copy of the config file passed to ``--grid``/``--config``

If ``SMCGSideMP`` is missing, the script tries **auto-build** with ``gfortran -O2 -fopenmp``
(see ``output.smcgside_auto_build``, ``output.gfortran``, env ``FC`` / ``PATH``).
Override the binary with env ``SMCGSIDE_MP`` or ``output.smcgside_executable`` in grid.json.
Face generation is slow on multi-million-cell grids; the script sets ``OMP_NUM_THREADS`` for
``SMCGSideMP`` (default ``min(cpu_count(), 32)``), override with ``output.smcgside_omp_threads``.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

OUT_CELL_NAME = "grid_cell.dat"
OUT_BOUNDARY_NAME = "grid_boundary.dat"
OUT_ARCTIC_NAME = "grid_arctic_cells.dat"
OUT_SUBTR_NAME = "grid_subtr.dat"
OUT_ISIDE_NAME = "grid_iside.dat"
OUT_JSIDE_NAME = "grid_jside.dat"
OUT_AISID_NAME = "grid_aisid.dat"
OUT_AJSID_NAME = "grid_ajsid.dat"
OUT_RUN_INFO_NAME = "grid.json"
WORK_STEM_NAME = "_smc_generate_tmp"

# SMCGSideMP.f90 limits: command-line InpFile & READ(CelFile) are LEN=80; first-line SMCGrid LEN=16.
SMCGSIDE_INP_BASENAME = "smcside.in"
SMCGSIDE_STEM_GLOBAL = "SMCSideG"
SMCGSIDE_STEM_ARCTIC = "SMCSideA"

import numpy as np


def write_grid_subtr_for_ww3(cell_path: Path, out_path: Path) -> None:
    """Write ``grid_subtr.dat`` for WAVEWATCH III SMCG (SUBTR namelist).

    Same header + one column layout as ``SMC61250Obstr.py``: ``NCObst`` cells, ``JObs`` = 1,
    obstruction 0--100 per cell (0 = no blocking).
    """
    cel = np.genfromtxt(cell_path, dtype=int, skip_header=1)
    ncel = int(cel.shape[0])
    hdrline = f"{ncel:8d} {1:5d}"
    zeros = np.zeros(ncel, dtype=int)
    np.savetxt(out_path, zeros, fmt="%4d", header=hdrline, comments="")


def _read_text_header_line(path: Path) -> str:
    with path.open("r", encoding="utf-8") as f:
        return f.readline().rstrip("\n")


def _load_int_table(path: Path, *, skip_header: int = 1) -> np.ndarray:
    arr = np.genfromtxt(path, dtype=np.int64, skip_header=skip_header)
    if arr.size == 0:
        raise SystemExit(f"Expected integer table with at least one row: {path}")
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    return np.ascontiguousarray(arr)


def _write_int_table(path: Path, header_line: str, data: np.ndarray) -> None:
    if data.ndim != 2:
        raise SystemExit(f"Expected 2D integer table for {path}, got shape {data.shape}")
    fmt = " ".join(["%d"] * int(data.shape[1]))
    np.savetxt(path, data, fmt=fmt, header=header_line, comments="")


def _regional_active_rect_from_cells(
    cell_path: Path,
    *,
    origin_lon: float,
    origin_lat: float,
    dlon: float,
    dlat: float,
) -> dict[str, float | int]:
    """Tight WW3 RECT derived from actual regional SMC cell occupancy."""
    cel = _load_int_table(cell_path)
    if cel.shape[1] < 4:
        raise SystemExit(f"Unexpected SMC cell shape in {cell_path}: {cel.shape}")
    i0 = cel[:, 0].astype(np.int64, copy=False)
    j0 = cel[:, 1].astype(np.int64, copy=False)
    di = cel[:, 2].astype(np.int64, copy=False)
    dj = cel[:, 3].astype(np.int64, copy=False)
    min_i = int(np.min(i0))
    min_j = int(np.min(j0))
    max_i = int(np.max(i0 + di))
    max_j = int(np.max(j0 + dj))
    nx = max_i - min_i
    ny = max_j - min_j
    if nx <= 0 or ny <= 0:
        raise SystemExit(
            f"Regional SMC active RECT is empty after scanning {cell_path}: nx={nx}, ny={ny}"
        )
    return {
        "shift_i": min_i,
        "shift_j": min_j,
        "nx": nx,
        "ny": ny,
        "sx": float(dlon),
        "sy": float(dlat),
        "x0": float(origin_lon + min_i * dlon),
        "y0": float(origin_lat + min_j * dlat),
    }


def _rebase_smc_ij_file(path: Path, *, shift_i: int, shift_j: int) -> None:
    """Shift first two integer columns to a local RECT origin, preserving header counts."""
    if shift_i == 0 and shift_j == 0:
        return
    header_line = _read_text_header_line(path)
    data = _load_int_table(path)
    if data.shape[1] < 2:
        raise SystemExit(f"Expected at least two columns in {path}, got {data.shape}")
    data[:, 0] -= int(shift_i)
    data[:, 1] -= int(shift_j)
    if np.min(data[:, 0]) < 0 or np.min(data[:, 1]) < 0:
        raise SystemExit(f"Negative rebased SMC indices written to {path}")
    _write_int_table(path, header_line, data)


def _parse_cell_header_counts(cell_path: Path) -> tuple[int, list[int]]:
    """First header line: NGLo then NRLCel(1..MRL) as written by smcellgen (global/regional Cels)."""
    with cell_path.open("r", encoding="utf-8") as f:
        line = f.readline()
    parts = [int(x) for x in line.split()]
    if len(parts) < 2:
        raise SystemExit(f"Invalid SMC cell header (need at least two integers): {cell_path}")
    return parts[0], parts[1:]


def _parse_arctic_cell_header_nglo(cell_path: Path) -> int:
    """Arctic BArc.dat header: NArc, NArB, NGLB (see SMCGSideMP READCELL)."""
    with cell_path.open("r", encoding="utf-8") as f:
        line = f.readline()
    parts = [int(x) for x in line.split()]
    if len(parts) < 1:
        raise SystemExit(f"Invalid Arctic cell header: {cell_path}")
    return parts[0]


def _side_allocation_bounds(nglo: int) -> tuple[int, int]:
    """NCL / NFC lower bounds for SMCGSideMP (array sizes; must cover cells and faces)."""
    ncl = max(nglo + 4096, int(nglo * 1.02) + 512)
    nfc = max(nglo * 4 + 1_000_000, int(nglo * 3) + 2_000_000, 300_000)
    return ncl, nfc


def _fmt_isd_row(row: np.ndarray) -> str:
    return (
        f"{int(row[0]):7d}{int(row[1]):6d}{int(row[2]):5d}"
        f"{int(row[3]):8d}{int(row[4]):8d}{int(row[5]):8d}{int(row[6]):8d}\n"
    )


def _fmt_jsd_row(row: np.ndarray) -> str:
    return (
        f"{int(row[0]):7d}{int(row[1]):6d}{int(row[2]):5d}"
        f"{int(row[3]):8d}{int(row[4]):8d}{int(row[5]):8d}{int(row[6]):8d}{int(row[7]):4d}\n"
    )


def _countijsd_write_dat(iside_d: Path, jside_d: Path, out_iside: Path, out_jside: Path) -> None:
    """Same as SMCGTools/Linuxs/countijsd6lv: sort faces, prepend size-count header line."""
    isd = np.atleast_2d(np.loadtxt(iside_d, dtype=np.int64))
    jsd = np.atleast_2d(np.loadtxt(jside_d, dtype=np.int64))
    if isd.shape[1] != 7:
        raise SystemExit(f"Unexpected ISIDE shape in {iside_d}: {isd.shape}")
    if jsd.shape[1] != 8:
        raise SystemExit(f"Unexpected JSIDE shape in {jside_d}: {jsd.shape}")

    oi = np.lexsort((isd[:, 0], isd[:, 1], isd[:, 2]))
    isd_s = isd[oi]
    ys_i = isd_s[:, 2].astype(np.int64, copy=False)
    nut = int(ys_i.size)
    nu2 = int(np.sum(ys_i == 2))
    nu4 = int(np.sum(ys_i == 4))
    nu8 = int(np.sum(ys_i == 8))
    nu16 = int(np.sum(ys_i == 16))
    nu32 = int(np.sum(ys_i == 32))
    n1a = int(np.sum((ys_i == 1) | (ys_i == 16)))
    nu1 = n1a - nu16

    oj = np.lexsort((jsd[:, 0], jsd[:, 1], jsd[:, 7]))
    jsd_s = jsd[oj]
    yv = jsd_s[:, 7].astype(np.int64, copy=False)
    nvt = int(yv.size)
    nv2 = int(np.sum(yv == 2))
    nv4 = int(np.sum(yv == 4))
    nv8 = int(np.sum(yv == 8))
    nv16 = int(np.sum(yv == 16))
    nv32 = int(np.sum(yv == 32))
    m1a = int(np.sum((yv == 1) | (yv == 16)))
    nv1 = m1a - nv16

    hdr_i = " " + " ".join(str(x) for x in (nut, nu1, nu2, nu4, nu8, nu16, nu32)) + "\n"
    hdr_j = " " + " ".join(str(x) for x in (nvt, nv1, nv2, nv4, nv8, nv16, nv32)) + "\n"

    with out_iside.open("w", encoding="utf-8") as f:
        f.write(hdr_i)
        for r in isd_s:
            f.write(_fmt_isd_row(r))
    with out_jside.open("w", encoding="utf-8") as f:
        f.write(hdr_j)
        for r in jsd_s:
            f.write(_fmt_jsd_row(r))


def _cell_path_for_smcgside(cel_abs: Path, out_dir: Path) -> str:
    """Paths in SMCGSideMP's input must fit CHARACTER(LEN=80); prefer relative when cells live in out_dir."""
    cel_r = cel_abs.resolve()
    out_r = out_dir.resolve()
    try:
        spec = cel_r.relative_to(out_r).as_posix()
    except ValueError:
        spec = cel_r.as_posix()
    if len(spec) > 80:
        raise SystemExit(
            "SMCGSideMP Fortran input allows at most 80 characters for the cell file path.\n"
            f"Current path ({len(spec)} chars): {spec}\n"
            "Use a shorter output.output_dir or place the grid under the output directory."
        )
    return spec


def _write_side_mp_input(
    path: Path,
    smc_grid_name: str,
    ncl: int,
    nfc: int,
    mrl: int,
    nlon: int,
    nlat: int,
    npol: int,
    cel_abs: Path,
    out_dir: Path,
) -> None:
    if len(smc_grid_name) > 16:
        raise SystemExit(
            f"SMCGSideMP grid name must be <= 16 characters (Fortran SMCGrid): {smc_grid_name!r}"
        )
    if not re.fullmatch(r"[A-Za-z0-9_]+", smc_grid_name):
        raise SystemExit(f"SMC grid stem must be alphanumeric/underscore: {smc_grid_name!r}")
    cel_spec = _cell_path_for_smcgside(cel_abs, out_dir)
    txt = (
        f"{smc_grid_name}\n"
        f" {ncl:8d} {nfc:8d} {mrl:8d}\n"
        f" {nlon:8d} {nlat:8d} {npol:8d}\n"
        f"'{cel_spec}'\n"
    )
    path.write_text(txt, encoding="utf-8")


def _find_smcgside_executable(script_dir: Path, output_cfg: dict[str, Any]) -> Path | None:
    candidates: list[Path] = []
    for key in ("smcgside_executable", "SMCGSideMP"):
        v = output_cfg.get(key)
        if isinstance(v, str) and v.strip():
            p = Path(v.strip())
            if not p.is_absolute():
                p = (script_dir / p).resolve()
            candidates.append(p)
    envp = os.environ.get("SMCGSIDE_MP", "").strip()
    if envp:
        candidates.append(Path(envp))
    pdir = script_dir / "SMCGTools" / "F90SMC"
    for name in ("SMCGSideMP", "SMCGSideMP.exe"):
        candidates.append(pdir / name)
    for p in candidates:
        if p.is_file():
            return p
    return None


def _default_smcgside_build_target(f90_dir: Path) -> Path:
    if sys.platform == "win32":
        return f90_dir / "SMCGSideMP.exe"
    return f90_dir / "SMCGSideMP"


def _find_gfortran(output_cfg: dict[str, Any]) -> str | None:
    """Resolve gfortran: output.gfortran, env FC, then PATH."""
    override = output_cfg.get("gfortran")
    if isinstance(override, str) and override.strip():
        val = override.strip()
        q = Path(val)
        if q.is_file():
            return str(q)
        w = shutil.which(val)
        if w:
            return w
    fc = os.environ.get("FC", "").strip()
    if fc:
        q = Path(fc)
        if q.is_file():
            return str(q)
        w = shutil.which(fc)
        if w:
            return w
        base = Path(fc).name
        w = shutil.which(base)
        if w:
            return w
    w = shutil.which("gfortran")
    return w


def _build_smcgside_mp(script_dir: Path, output_cfg: dict[str, Any]) -> Path:
    f90_dir = (script_dir / "SMCGTools" / "F90SMC").resolve()
    src = f90_dir / "SMCGSideMP.f90"
    if not src.is_file():
        raise SystemExit(
            "SMCGSideMP executable not found and source is missing:\n"
            f"  {src}\n"
            "Install a prebuilt binary (set SMCGSIDE_MP or output.smcgside_executable)."
        )
    gfortran = _find_gfortran(output_cfg)
    if gfortran is None:
        raise SystemExit(
            "SMCGSideMP not found; auto-build requires gfortran in PATH "
            "(or set output.gfortran / FC to the compiler).\n"
            "Example: brew install gcc   # macOS\n"
            "Or build manually:\n"
            f"  cd {f90_dir}\n"
            "  gfortran -O2 -fopenmp SMCGSideMP.f90 -o SMCGSideMP"
        )
    out_exe = _default_smcgside_build_target(f90_dir)
    cmd = [gfortran, "-O2", "-fopenmp", str(src), "-o", str(out_exe)]
    print(f"Auto-building SMCGSideMP:\n  cd {f90_dir}\n  {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=str(f90_dir), capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()
        msg = tail[-8000:] if tail else "(no compiler output)"
        raise SystemExit(
            f"gfortran failed to build SMCGSideMP (exit {proc.returncode}):\n{msg}"
        )
    if not out_exe.is_file():
        raise SystemExit(f"Build exited 0 but output missing: {out_exe}")
    print(f"SMCGSideMP built: {out_exe}", flush=True)
    return out_exe


def _ensure_smcgside_executable(script_dir: Path, output_cfg: dict[str, Any]) -> Path:
    found = _find_smcgside_executable(script_dir, output_cfg)
    if found is not None:
        return found
    if not bool(output_cfg.get("smcgside_auto_build", True)):
        raise SystemExit(
            "SMCGSideMP executable not found and output.smcgside_auto_build is false.\n"
            "Build with:\n  cd "
            + str((script_dir / "SMCGTools" / "F90SMC").resolve())
            + "\n  gfortran -O2 -fopenmp SMCGSideMP.f90 -o SMCGSideMP\n"
            "Or set SMCGSIDE_MP / output.smcgside_executable."
        )
    return _build_smcgside_mp(script_dir, output_cfg)


def _smcgside_omp_threads(output_cfg: dict[str, Any]) -> int:
    """Thread count for SMCGSideMP only (does not change the parent shell)."""
    key = output_cfg.get("smcgside_omp_threads")
    if key is not None:
        return max(1, int(key))
    cpus = os.cpu_count() or 8
    # Large SMC grids (10^6–10^7 cells) benefit from more threads; cap to reduce oversubscription.
    return max(1, min(int(cpus), 32))


def _run_smcgside_mp(
    exe: Path,
    inp_basename: str,
    work_cwd: Path,
    output_cfg: dict[str, Any],
) -> None:
    # Fortran GET_COMMAND_ARGUMENT uses CHARACTER(LEN=80); pass a short name and cwd=out_dir.
    env = os.environ.copy()
    nthr = _smcgside_omp_threads(output_cfg)
    env["OMP_NUM_THREADS"] = str(nthr)
    print(
        f"SMCGSideMP OMP_NUM_THREADS={nthr} "
        f"(set output.smcgside_omp_threads in grid.json to override).",
        flush=True,
    )
    try:
        proc = subprocess.run(
            [str(exe), inp_basename],
            cwd=str(work_cwd),
            env=env,
            timeout=None,
            check=False,
        )
    except OSError as e:
        raise SystemExit(f"Failed to execute SMCGSideMP ({exe}): {e}") from e
    if proc.returncode != 0:
        raise SystemExit(
            f"SMCGSideMP failed (exit {proc.returncode}): {exe} (see log above)"
        )


def _generate_iside_jside_pair(
    *,
    script_dir: Path,
    output_cfg: dict[str, Any],
    out_dir: Path,
    smc_stem: str,
    cell_path: Path,
    n_levels: int,
    nlon: int,
    nlat: int,
    npol: int,
    final_iside: Path,
    final_jside: Path,
) -> None:
    exe = _ensure_smcgside_executable(script_dir, output_cfg)
    if npol > 0:
        nglo = _parse_arctic_cell_header_nglo(cell_path)
        nrl: list[int] = []
    else:
        nglo, nrl = _parse_cell_header_counts(cell_path)
        if len(nrl) != n_levels:
            print(
                f"Note: cell header MRL count {len(nrl)} vs config n_levels={n_levels} "
                f"(using n_levels for side input).",
                flush=True,
            )
    ncl, nfc = _side_allocation_bounds(nglo)
    inp_path = out_dir / SMCGSIDE_INP_BASENAME
    cel_abs = cell_path.resolve()
    _write_side_mp_input(
        inp_path, smc_stem, ncl, nfc, n_levels, nlon, nlat, npol, cel_abs, out_dir
    )
    is_d = out_dir / f"{smc_stem}ISide.d"
    js_d = out_dir / f"{smc_stem}JSide.d"
    for p in (is_d, js_d):
        try:
            if p.is_file():
                p.unlink()
        except OSError:
            pass
    print(
        f"Running SMCGSideMP ({exe.name}) stem={smc_stem} inp={SMCGSIDE_INP_BASENAME} "
        f"→ {final_iside.name} / {final_jside.name}",
        flush=True,
    )
    _run_smcgside_mp(exe, SMCGSIDE_INP_BASENAME, out_dir, output_cfg)
    if not is_d.is_file() or not js_d.is_file():
        raise SystemExit(
            f"SMCGSideMP did not create expected outputs: {is_d.name} / {js_d.name}"
        )
    _countijsd_write_dat(is_d, js_d, final_iside, final_jside)
    for p in (is_d, js_d, out_dir / f"{smc_stem}Side.txt", inp_path):
        try:
            if p.is_file():
                p.unlink()
        except OSError:
            pass


def _python_externally_managed() -> bool:
    """PEP 668: Homebrew/macOS system Pythons often ship EXTERNALLY-MANAGED."""
    try:
        ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        marker = Path(sys.prefix) / "lib" / f"python{ver}" / "EXTERNALLY-MANAGED"
        return marker.is_file()
    except Exception:
        return False


def _require_dependencies(script_dir: Path) -> None:
    missing = []
    try:
        import netCDF4  # noqa: F401
    except Exception:
        missing.append("netCDF4")

    try:
        import pandas  # noqa: F401
    except Exception:
        missing.append("pandas")

    if missing:
        names = ", ".join(missing)
        install_names = " ".join(missing)
        req = script_dir / "requirements.txt"
        req_hint = (
            f"  python3 -m pip install -r {req}\n"
            if req.is_file()
            else f"  python3 -m pip install {install_names}\n"
        )
        pep = _python_externally_managed()
        extra = ""
        if pep:
            extra = (
                "\nThis interpreter is externally managed (PEP 668); "
                "`pip install` without a venv will usually fail.\n"
            )
        raise SystemExit(
            f"Missing Python dependencies: {names}.{extra}\n"
            "Create a virtual environment in smc_generator (recommended):\n"
            f"  cd {script_dir}\n"
            "  python3 -m venv .venv\n"
            "  source .venv/bin/activate\n"
            "  # Windows: .venv\\Scripts\\activate\n"
            f"{req_hint}"
            "  python3 create_grid.py\n"
        )


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_path(base: Path, value: str) -> Path:
    p = Path(value)
    if not p.is_absolute():
        p = (base / p).resolve()
    return p


def _pick_var(
    variables: dict[str, Any],
    configured: Any,
    candidates: list[str],
    label: str,
) -> str:
    if isinstance(configured, str) and configured:
        if configured not in variables:
            raise SystemExit(
                f"Configured {label} variable '{configured}' not found."
            )
        return configured

    for name in candidates:
        if name in variables:
            return name

    raise SystemExit(
        f"Could not auto-detect {label} variable. "
        f"Please set it explicitly in grid.json."
    )


def _regular_step(
    axis: np.ndarray,
    axis_name: str,
    *,
    rtol: float = 1.0e-4,
    atol: float = 1.0e-8,
) -> float:
    if axis.ndim != 1:
        raise SystemExit(f"{axis_name} axis must be 1D.")
    if axis.size < 2:
        raise SystemExit(f"{axis_name} axis length must be >= 2.")

    diffs = np.diff(axis)
    if np.any(diffs <= 0.0):
        raise SystemExit(
            f"{axis_name} axis must be strictly increasing after auto-flip."
        )
    step = float(np.median(diffs))
    if not np.all(np.isfinite(diffs)):
        raise SystemExit(f"{axis_name} axis contains non-finite values.")
    if not np.allclose(diffs, step, rtol=rtol, atol=atol):
        raise SystemExit(
            f"{axis_name} axis is not regularly spaced. "
            "SMCGTools requires regular lon/lat spacing."
        )
    return step


def _crop_bathy_for_regional_smc(
    lon: np.ndarray,
    lat: np.ndarray,
    bathy_elev: np.ndarray,
    mlvlxy0: list,
    *,
    dlon: float,
    dlat: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Crop bathy to the same i/j window ``smcellgen`` uses for regional SMC.

    Cell i/j indices are defined on the bathy index grid. Feeding full GEBCO-sized
    arrays makes ``ww3_rect`` use NX×NY ~ 180"/15" → ``ww3_grid`` appears stuck on
    an enormous RECT. Cropping keeps the WW3 base grid at regional size.
    """
    nlon = int(lon.size)
    nlat = int(lat.size)
    zlon = float(lon[0])
    zlat = float(lat[0])
    xlon = np.arange(nlon, dtype=float) * dlon + zlon
    ylat = np.arange(nlat, dtype=float) * dlat + zlat

    xstart = float(mlvlxy0[3])
    ystart = float(mlvlxy0[4])
    xend = float(mlvlxy0[5])
    yend = float(mlvlxy0[6])

    if xstart < xlon[0] or xend > xlon[-1] or ystart < ylat[0] or yend > ylat[-1]:
        raise SystemExit(
            f"Regional range [{xstart:g},{ystart:g}]–[{xend:g},{yend:g}] is outside bathy "
            f"[{xlon[0]:g},{ylat[0]:g}]–[{xlon[-1]:g},{ylat[-1]:g}]."
        )

    n_levels = int(mlvlxy0[0])
    MFct = 2 ** (n_levels - 1)
    prnlat = np.zeros(20, dtype=float)
    prnlat[10:] = np.array(
        [
            60.0,
            75.522486,
            82.819245,
            86.416678,
            88.209213,
            89.104712,
            89.552370,
            89.776188,
            89.888094,
            89.944047,
        ]
    )
    prnlat[:10] = -1.0 * prnlat[10:][::-1]

    yrngmax = max(abs(ystart), abs(yend))
    Merg = 1
    k = 10
    while yrngmax > prnlat[k] and k < 20:
        k += 1
        Merg = 2 ** (k - 10)
    MFMG = Merg * MFct

    istart = int(round((xstart - xlon[0]) / (MFMG * dlon))) * MFMG
    jstart = int(round((ystart - ylat[0]) / (MFct * dlat))) * MFct
    iexpnd = int(round((xend - xstart) / (MFMG * dlon))) * MFMG
    jexpnd = int(round((yend - ystart) / (MFct * dlat))) * MFct

    if istart - MFMG < 0:
        istart = istart + MFMG
    if jstart - MFct < 0:
        jstart = jstart + MFct

    iend = istart + iexpnd
    jend = jstart + jexpnd - MFct

    # smcellgen ``subathy`` uses lon indices [i-iFct, i+iFc2) and lat [j-MFct, j+MFc2)
    # with iFct ≤ MFMG, iFc2 = 2*iFct. Min i is ~istart → need pad ≥ MFMG; max i near iend
    # needs pad ≥ ~2*MFMG on the east. Use a tight symmetric margin (was max(256,4*MFMG),
    # which over-expanded ww3_rect and forced huge ww3_prnc forcing domains).
    pad_i = max(64, 2 * MFMG + MFct)
    pad_j = max(64, 3 * MFct)
    i_lo = max(0, istart - pad_i)
    i_hi = min(nlon, iend + pad_i)
    j_lo = max(0, jstart - pad_j)
    j_hi = min(nlat, jend + pad_j)

    if i_hi <= i_lo or j_hi <= j_lo:
        raise SystemExit(
            "Regional SMC bathy crop produced an empty window; check regional_bounds and bathy."
        )

    lon_c = lon[i_lo:i_hi].copy()
    lat_c = lat[j_lo:j_hi].copy()
    bathy_c = bathy_elev[j_lo:j_hi, i_lo:i_hi].copy()
    print(
        f"Regional SMC: bathy crop lon [{i_lo}:{i_hi}] lat [{j_lo}:{j_hi}] → "
        f"{lon_c.size}×{lat_c.size} (full {nlon}×{nlat}).",
        flush=True,
    )
    return lon_c, lat_c, bathy_c


def _to_2d_bathy(var_data: np.ndarray) -> np.ndarray:
    arr = np.asarray(var_data, dtype=float).squeeze()
    if arr.ndim != 2:
        raise SystemExit(
            f"Bathymetry variable must be 2D after squeeze, got shape {arr.shape}"
        )
    return arr


def _read_regional_bounds_policy(grid_cfg: dict[str, Any]) -> tuple[str, float]:
    """Policy for handling ww3_rect_geo outside requested regional_bounds.

    Returns:
        (mode, tolerance_deg)
        mode in {"error", "warn", "off"}
    """
    raw_mode = grid_cfg.get("regional_bounds_policy", "error")
    mode = str(raw_mode).strip().lower() if raw_mode is not None else "error"
    alias = {
        "strict": "error",
        "fail": "error",
        "warning": "warn",
        "none": "off",
        "disable": "off",
        "disabled": "off",
    }
    mode = alias.get(mode, mode)
    if mode not in {"error", "warn", "off"}:
        raise SystemExit(
            "grid.regional_bounds_policy must be one of: error, warn, off "
            "(aliases: strict/fail, warning, none/disable/disabled)."
        )
    raw_tol = grid_cfg.get("regional_bounds_tolerance_deg", 0.0)
    tol = float(raw_tol)
    if not np.isfinite(tol) or tol < 0.0:
        raise SystemExit("grid.regional_bounds_tolerance_deg must be a finite number >= 0.")
    return mode, tol


def _enforce_regional_bounds_policy(
    *,
    requested_bounds: dict[str, float] | None,
    rect_geo: dict[str, float],
    policy_mode: str,
    tolerance_deg: float,
) -> None:
    if requested_bounds is None or policy_mode == "off":
        return

    req_w = float(requested_bounds["west_lon"])
    req_e = float(requested_bounds["east_lon"])
    req_s = float(requested_bounds["south_lat"])
    req_n = float(requested_bounds["north_lat"])
    r_w = float(rect_geo["lon_west"])
    r_e = float(rect_geo["lon_east"])
    r_s = float(rect_geo["lat_south"])
    r_n = float(rect_geo["lat_north"])
    tol = float(tolerance_deg)

    dx_w = max(0.0, req_w - r_w)
    dx_e = max(0.0, r_e - req_e)
    dy_s = max(0.0, req_s - r_s)
    dy_n = max(0.0, r_n - req_n)
    exceed = (dx_w > tol) or (dx_e > tol) or (dy_s > tol) or (dy_n > tol)
    if not exceed:
        return

    fit_w = req_w + dx_w
    fit_e = req_e - dx_e
    fit_s = req_s + dy_s
    fit_n = req_n - dy_n
    accept_w = min(req_w, r_w)
    accept_e = max(req_e, r_e)
    accept_s = min(req_s, r_s)
    accept_n = max(req_n, r_n)

    msg = (
        "Regional SMC active RECT exceeded requested regional_bounds.\n"
        f"  requested lon/lat: [{req_w:.6f},{req_e:.6f}] x [{req_s:.6f},{req_n:.6f}]\n"
        f"  actual ww3_rect_geo: [{r_w:.6f},{r_e:.6f}] x [{r_s:.6f},{r_n:.6f}]\n"
        f"  exceeded (deg): west={dx_w:.6f}, east={dx_e:.6f}, south={dy_s:.6f}, north={dy_n:.6f}\n"
        f"  tolerance (deg): {tol:.6f}\n"
        "Suggested fixes:\n"
        f"  keep inside current requested envelope (try regional_bounds): "
        f"[{fit_w:.6f},{fit_e:.6f}] x [{fit_s:.6f},{fit_n:.6f}]\n"
        f"  or accept current active RECT (expand regional_bounds to): "
        f"[{accept_w:.6f},{accept_e:.6f}] x [{accept_s:.6f},{accept_n:.6f}]\n"
        "Adjust grid.origin/regional_bounds (or increase tolerance), then regenerate."
    )
    if policy_mode == "warn":
        print("WARNING: " + msg.replace("\n", "\nWARNING: "), flush=True)
        return
    raise SystemExit(msg)


def _pysmcs_dir(script_dir: Path) -> Path:
    for candidate in (script_dir / "PySMCs", script_dir / "SMCGTools" / "PySMCs"):
        if (candidate / "smcellgen.py").is_file():
            return candidate
    return script_dir / "PySMCs"


def _read_alias_float(mapping: dict[str, Any], aliases: list[str], label: str) -> float:
    for key in aliases:
        if key in mapping and mapping[key] is not None:
            return float(mapping[key])
    raise SystemExit(
        f"Missing '{label}'. Supported keys: {', '.join(aliases)}"
    )


def _print_smc_run_banner() -> None:
    """Banner line width 70；标题在等宽显示下居中（字符列）。"""
    sys.stdout.flush()
    print("=" * 70, flush=True)
    title = "SMC Grid Generation By SMCGTools"
    print(title.center(70), flush=True)
    print("=" * 70 + "\n", flush=True)


def main() -> None:
    # 重定向到管道时，尽量行缓冲，便于 GUI 实时显示子进程输出（配合 PYTHONUNBUFFERED / python -u）
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(line_buffering=True)
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="Generate SMC grid files from grid.json."
    )
    parser.add_argument(
        "-c",
        "--config",
        "--grid",
        default="grid.json",
        dest="config",
        help="Path to grid JSON (default: ./grid.json)",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    config_path = _resolve_path(script_dir, args.config)
    _print_smc_run_banner()
    config = _load_json(config_path)
    print(f"Loaded config: {config_path}", flush=True)

    _require_dependencies(script_dir)
    import netCDF4 as nc

    pysmcs_dir = _pysmcs_dir(script_dir)
    if str(pysmcs_dir) not in sys.path:
        sys.path.insert(0, str(pysmcs_dir))

    print("Importing PySMCs (smcellgen / smcellbdy)…", flush=True)
    from smcellbdy import smcellbdy
    from smcellgen import smcellgen
    print("PySMCs import done.", flush=True)

    input_cfg = config["input"]
    grid_cfg = config["grid"]
    physics_cfg = config["physics"]
    boundary_cfg = config["boundary"]
    output_cfg = config["output"]

    bathy_path = _resolve_path(config_path.parent, input_cfg["bathymetry_file"])
    if not bathy_path.exists():
        raise SystemExit(f"Bathymetry file not found: {bathy_path}")

    print(
        "Reading bathymetry NetCDF into memory (large global files may take several minutes)…",
        flush=True,
    )
    print(f"  File: {bathy_path}", flush=True)
    with nc.Dataset(str(bathy_path), "r") as ds:
        lon_var = _pick_var(
            ds.variables,
            input_cfg.get("lon_var"),
            ["lon", "longitude", "x", "LON", "XLONG"],
            "longitude",
        )
        lat_var = _pick_var(
            ds.variables,
            input_cfg.get("lat_var"),
            ["lat", "latitude", "y", "LAT", "XLAT"],
            "latitude",
        )
        bathy_var = _pick_var(
            ds.variables,
            input_cfg.get("bathy_var"),
            ["elevation", "z", "depth", "bathymetry", "Bathymetry"],
            "bathymetry",
        )

        lon = np.asarray(ds.variables[lon_var][:], dtype=float).squeeze()
        lat = np.asarray(ds.variables[lat_var][:], dtype=float).squeeze()
        bathy = _to_2d_bathy(ds.variables[bathy_var][:])

    print(
        f"Bathymetry array in memory: {bathy.shape[0]} x {bathy.shape[1]} (lat x lon).",
        flush=True,
    )

    if lon.ndim != 1 or lat.ndim != 1:
        raise SystemExit("This script supports 1D lon/lat axes only.")

    if bathy.shape == (lon.size, lat.size):
        bathy = bathy.T
    if bathy.shape != (lat.size, lon.size):
        raise SystemExit(
            f"Bathymetry shape {bathy.shape} does not match "
            f"(lat, lon)=({lat.size}, {lon.size})."
        )

    if bool(input_cfg.get("auto_flip_lat", True)) and lat[0] > lat[-1]:
        lat = lat[::-1]
        bathy = bathy[::-1, :]

    if bool(input_cfg.get("auto_flip_lon", True)) and lon[0] > lon[-1]:
        lon = lon[::-1]
        bathy = bathy[:, ::-1]

    spacing_rtol = float(input_cfg.get("coord_spacing_rtol", 1.0e-4))
    spacing_atol = float(input_cfg.get("coord_spacing_atol", 1.0e-8))
    dlon = _regular_step(
        lon,
        "Longitude",
        rtol=spacing_rtol,
        atol=spacing_atol,
    )
    dlat = _regular_step(
        lat,
        "Latitude",
        rtol=spacing_rtol,
        atol=spacing_atol,
    )
    if dlon <= 0.0 or dlat <= 0.0:
        raise SystemExit("Longitude/Latitude spacing must be positive after flipping.")

    print(
        f"Uniform grid spacing OK: dlon={dlon:g} deg, dlat={dlat:g} deg.",
        flush=True,
    )

    convention = str(input_cfg.get("bathy_convention", "elevation")).lower()
    if convention == "elevation":
        bathy_elev = bathy
    elif convention in {"depth", "depth_positive_down", "positive_down"}:
        bathy_elev = -bathy
    else:
        raise SystemExit(
            "input.bathy_convention must be one of: "
            "'elevation', 'depth', 'depth_positive_down', 'positive_down'."
        )

    depmin = float(physics_cfg.get("depmin", 0.0))
    nan_fill = float(input_cfg.get("nan_fill_value", depmin + 1.0))
    bathy_elev = np.nan_to_num(
        bathy_elev,
        nan=nan_fill,
        posinf=nan_fill,
        neginf=depmin - 1000.0,
    )

    n_levels = int(grid_cfg["n_levels"])
    global_grid = bool(grid_cfg.get("global", True))
    arctic_grid = bool(grid_cfg.get("arctic", False))
    arc_lat = float(grid_cfg.get("glb_arc_lat", 84.4))
    regional_policy_mode, regional_policy_tol = _read_regional_bounds_policy(grid_cfg)
    origin_cfg = grid_cfg["origin"]
    x0lon = _read_alias_float(origin_cfg, ["x0lon", "lon0"], "origin longitude")
    y0lat = _read_alias_float(origin_cfg, ["y0lat", "lat0"], "origin latitude")

    mlvlxy0 = [n_levels, x0lon, y0lat]
    requested_bounds: dict[str, float] | None = None
    if not global_grid:
        bounds = grid_cfg.get("regional_bounds")
        if not isinstance(bounds, dict):
            raise SystemExit(
                "regional_bounds must be set when grid.global is false."
            )
        west_lon = _read_alias_float(
            bounds,
            ["west_lon", "xstart", "lon_min", "min_lon"],
            "regional west longitude",
        )
        south_lat = _read_alias_float(
            bounds,
            ["south_lat", "ystart", "lat_min", "min_lat"],
            "regional south latitude",
        )
        east_lon = _read_alias_float(
            bounds,
            ["east_lon", "xend", "lon_max", "max_lon"],
            "regional east longitude",
        )
        north_lat = _read_alias_float(
            bounds,
            ["north_lat", "yend", "lat_max", "max_lat"],
            "regional north latitude",
        )

        mlvlxy0.extend(
            [
                west_lon,
                south_lat,
                east_lon,
                north_lat,
            ]
        )
        requested_bounds = {
            "west_lon": float(min(west_lon, east_lon)),
            "east_lon": float(max(west_lon, east_lon)),
            "south_lat": float(min(south_lat, north_lat)),
            "north_lat": float(max(south_lat, north_lat)),
        }

    if not global_grid:
        lon, lat, bathy_elev = _crop_bathy_for_regional_smc(
            lon, lat, bathy_elev, mlvlxy0, dlon=dlon, dlat=dlat
        )

    ndzlonlat = [int(lon.size), int(lat.size), float(dlon), float(dlat), float(lon[0]), float(lat[0])]

    out_dir = _resolve_path(config_path.parent, output_cfg.get("output_dir", "./output"))
    out_dir.mkdir(parents=True, exist_ok=True)
    work_stem = out_dir / WORK_STEM_NAME
    work_prefix = str(work_stem)

    cells_tmp = Path(work_prefix + "Cels.dat")
    bdys_tmp = Path(work_prefix + "Bdys.dat")
    barc_tmp = Path(work_prefix + "BArc.dat")
    final_cell = out_dir / OUT_CELL_NAME
    final_boundary = out_dir / OUT_BOUNDARY_NAME
    final_arctic = out_dir / OUT_ARCTIC_NAME
    final_iside = out_dir / OUT_ISIDE_NAME
    final_jside = out_dir / OUT_JSIDE_NAME
    final_aisid = out_dir / OUT_AISID_NAME
    final_ajsid = out_dir / OUT_AJSID_NAME
    run_info_file = out_dir / OUT_RUN_INFO_NAME

    generate_bdy = bool(boundary_cfg.get("generate_boundary_cells", True))
    nb_raw = boundary_cfg.get("n_bismc")
    if nb_raw is None:
        need_bundy = (not global_grid) and generate_bdy
    else:
        try:
            need_bundy = int(nb_raw) > 0
        except (TypeError, ValueError):
            raise SystemExit("boundary.n_bismc must be an integer when set.")
    run_smcellbdy = (not global_grid) and generate_bdy and need_bundy

    for p in (cells_tmp, bdys_tmp, barc_tmp):
        try:
            if p.is_file():
                p.unlink()
        except OSError:
            pass

    wlevel = float(physics_cfg.get("wlevel", 0.0))
    dshalw = float(physics_cfg.get("dshalw", 0.0))

    print(f"Generating cells (temp {cells_tmp.name}) → {final_cell.name}")
    smcellgen(
        bathy_elev,
        ndzlonlat,
        mlvlxy0,
        FileNm=work_prefix,
        Global=global_grid,
        Arctic=arctic_grid,
        depmin=depmin,
        dshalw=dshalw,
        wlevel=wlevel,
        GlbArcLat=arc_lat,
    )

    if not cells_tmp.is_file():
        raise SystemExit(f"Expected cell file not created: {cells_tmp}")

    msea = int(boundary_cfg.get("msea", 1))
    bdy_written = False
    if run_smcellbdy:
        print(f"Generating boundaries (temp {bdys_tmp.name}) → {final_boundary.name}")
        smcellbdy(
            bathy_elev,
            ndzlonlat,
            mlvlxy0,
            FileNm=work_prefix,
            Global=global_grid,
            Arctic=arctic_grid,
            depmin=depmin,
            dshalw=dshalw,
            wlevel=wlevel,
            msea=msea,
            GlbArcLat=arc_lat,
        )
        if not bdys_tmp.is_file():
            raise SystemExit(
                f"Expected boundary file not created: {bdys_tmp} "
                "(BUNDY required for NBISMC>0 regional runs)."
            )
        bdy_written = True

    ww3_rect = {
        "nx": int(lon.size),
        "ny": int(lat.size),
        "sx": float(dlon),
        "sy": float(dlat),
        "x0": float(lon[0]),
        "y0": float(lat[0]),
    }
    side_nlon = int(lon.size)
    side_nlat = int(lat.size)
    if not global_grid:
        ww3_rect = _regional_active_rect_from_cells(
            cells_tmp,
            origin_lon=x0lon,
            origin_lat=y0lat,
            dlon=dlon,
            dlat=dlat,
        )
        shift_i = int(ww3_rect["shift_i"])
        shift_j = int(ww3_rect["shift_j"])
        _rebase_smc_ij_file(cells_tmp, shift_i=shift_i, shift_j=shift_j)
        if bdy_written:
            _rebase_smc_ij_file(bdys_tmp, shift_i=shift_i, shift_j=shift_j)
        side_nlon = int(ww3_rect["nx"])
        side_nlat = int(ww3_rect["ny"])
        print(
            "Regional SMC: rebased MCELS/BUNDY to active RECT "
            f"shift=({shift_i},{shift_j}) size={side_nlon}×{side_nlat} "
            f"lon/lat start=({float(ww3_rect['x0']):.4f},{float(ww3_rect['y0']):.4f}).",
            flush=True,
        )

    _generate_iside_jside_pair(
        script_dir=script_dir,
        output_cfg=output_cfg,
        out_dir=out_dir,
        smc_stem=SMCGSIDE_STEM_GLOBAL,
        cell_path=cells_tmp,
        n_levels=n_levels,
        nlon=side_nlon,
        nlat=side_nlat,
        npol=0,
        final_iside=final_iside,
        final_jside=final_jside,
    )

    os.replace(cells_tmp, final_cell)

    write_grid_subtr_for_ww3(final_cell, out_dir / OUT_SUBTR_NAME)
    print(f"Wrote {OUT_SUBTR_NAME} (zero obstruction) for WW3 SMCG.", flush=True)

    arctic_written = bool(barc_tmp.is_file())
    if arctic_grid and arctic_written:
        _generate_iside_jside_pair(
            script_dir=script_dir,
            output_cfg=output_cfg,
            out_dir=out_dir,
            smc_stem=SMCGSIDE_STEM_ARCTIC,
            cell_path=barc_tmp,
            n_levels=n_levels,
            nlon=side_nlon,
            nlat=side_nlat,
            npol=1,
            final_iside=final_aisid,
            final_jside=final_ajsid,
        )
        os.replace(barc_tmp, final_arctic)
    else:
        for p in (final_arctic, final_aisid, final_ajsid):
            try:
                if p.is_file():
                    p.unlink()
            except OSError:
                pass
        if arctic_grid and not arctic_written:
            print(
                "Note: grid.arctic is true but no Arctic cell file was produced "
                f"({barc_tmp.name}); skipped MBARC / AISID / AJSID.",
                flush=True,
            )

    if need_bundy:
        if not bdy_written:
            raise SystemExit(
                "BUNDY (grid_boundary.dat) is required (NBISMC>0) but boundary "
                "generation did not run or failed. Enable boundary.generate_boundary_cells "
                "for regional grids or set boundary.n_bismc to 0."
            )
        os.replace(bdys_tmp, final_boundary)
    else:
        for p in (bdys_tmp, final_boundary):
            try:
                if p.is_file():
                    p.unlink()
            except OSError:
                pass

    run_doc = copy.deepcopy(config)
    run_doc["ww3_rect"] = dict(ww3_rect)
    run_doc["ww3_rect"].pop("shift_i", None)
    run_doc["ww3_rect"].pop("shift_j", None)
    # Geographic envelope of the actual WW3 SMC RECT after regional index rebasing. This is the
    # active base grid occupied by MCELS, not the larger bathy crop used internally for stencils.
    run_doc["ww3_rect_geo"] = {
        "lon_west": float(run_doc["ww3_rect"]["x0"]),
        "lon_east": float(
            run_doc["ww3_rect"]["x0"] + (int(run_doc["ww3_rect"]["nx"]) - 1) * run_doc["ww3_rect"]["sx"]
        ),
        "lat_south": float(run_doc["ww3_rect"]["y0"]),
        "lat_north": float(
            run_doc["ww3_rect"]["y0"] + (int(run_doc["ww3_rect"]["ny"]) - 1) * run_doc["ww3_rect"]["sy"]
        ),
    }
    if not global_grid:
        _enforce_regional_bounds_policy(
            requested_bounds=requested_bounds,
            rect_geo=run_doc["ww3_rect_geo"],
            policy_mode=regional_policy_mode,
            tolerance_deg=regional_policy_tol,
        )
    if not global_grid:
        run_doc["ww3_prnc_forcing_note"] = (
            "WAVEWATCH ww3_prnc maps forcing onto every SMC RECT base-grid point (see ww3_rect / "
            "ww3_rect_geo). For regional grids this RECT now follows the active MCELS footprint "
            "rather than the larger bathy crop used internally by smcellgen. If wind.nc is still "
            "narrower than ww3_rect_geo, extend or crop the forcing to at least this box."
        )
    with run_info_file.open("w", encoding="utf-8") as f:
        json.dump(run_doc, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(
        f"Wrote {run_info_file} (includes ww3_rect for WW3 &RECT_NML / SMCG base grid).",
        flush=True,
    )


if __name__ == "__main__":
    main()
