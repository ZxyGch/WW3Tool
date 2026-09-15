#!/usr/bin/env python3
"""用仓库内真实 WW3 6.07 / 7.14 可执行文件做外部边界谱小算例验收。

输出写到 gitignore 的 workSpace/boundary_ww3_verify/，不提交 .nc / nest.ww3。
ST 名称按不透明字符串使用；7.14 只用 RECT 的 ST2 构建，不宣称 ST4 RECT。

预先写下的判定门槛（物理耗散不算振幅守恒失败）：
- 单边入射：积分后半段内部最大 Hs >= 0.15 m；西侧内部应先于东侧出现能量。
- 零边界：同一内部区最大 Hs < 0.02 m，且入射内部 Hs 至少为其 5 倍。
- 输入不足：prepare 在积分前以 BOUNDARY_TIME_COVERAGE 失败。
- 边界关闭：托管 nest.ww3 归档，MASK 指回无边界掩码。
- 多站点：mapping 使用不少于 2 个 source_id。
- 两点线性：南/北源能量不同，中间目标权重落在 (0,1)。
- 时间分片：与单文件 nest 的 NBI/NK/NTH/时刻数一致。
- 热启动：后半段内部 Hs 与连续积分相对差 <= 0.25（允许 MPI/构建容差）。
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from workflows.application.boundary_preparation import prepare_boundary_inputs, run_ww3_bounc
from workflows.application.configuration import load_pipeline_config
from workflows.infrastructure.boundary.errors import BoundaryError
from workflows.infrastructure.boundary.spectra_normalizer import station_char_matrix, write_station_file
from workflows.infrastructure.boundary.spectrum_coords import target_spectral_discrete
from workflows.infrastructure.boundary.ww3_bounc_nml import read_nest_file

ROOT = REPO / "workSpace" / "boundary_ww3_verify"
START = datetime(2000, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
STOP = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
START_S = "20000101 000000"
STOP_S = "20000101 120000"

NX, NY = 13, 9
SX, SY = 0.25, 0.25
X0, Y0 = 120.0, 10.0
DEPTH = 4000.0
FREQ1, XFR, NK, NTH, THOFF = 0.08, 1.1, 10, 24, 0.0
IFREQ = 2  # ~0.0968 Hz ≈ 10.3 s
TARGET_TO_DIR = 90.0  # 传播去向：向东
HS_INCIDENT = 1.5
HS_SOUTH, HS_NORTH = 0.5, 2.0

INCIDENT_HS_MIN = 0.15
ZERO_HS_MAX = 0.02
DIR_TOL_DEG = 50.0
HOTSTART_REL_TOL = 0.25

VERSIONS = [
    {
        "label": "6.07 ST4 RECT",
        "version": "6.07",
        "st_name": "6.07 ST4 RECT",
        "bin": REPO / "WW3-6.07.1" / "model" / "exe_ST4",
        "nml": REPO / "public" / "6.07_nml",
        "switch": REPO / "WW3-6.07.1" / "model" / "exe_ST4" / "switch",
        "date_style": "split",
    },
    {
        "label": "7.14 ST2 RECT",
        "version": "7.14",
        "st_name": "7.14 ST2 RECT",
        "bin": REPO / "WW3" / "build" / "ST2" / "bin",
        "nml": REPO / "public" / "7.14_nml",
        "switch": REPO / "WW3" / "build" / "ST2" / "switch",
        "date_style": "compact",
    },
]


def log(msg: str) -> None:
    print(msg, flush=True)


def lonlat(i: int, j: int) -> tuple[float, float]:
    return X0 + (i - 1) * SX, Y0 + (j - 1) * SY


def west_ring_lonlat() -> list[tuple[int, int, float, float]]:
    """西侧活动边界：i=2，j=2..NY-1。"""
    return [(2, j, *lonlat(2, j)) for j in range(2, NY)]


def write_west_uniform(path: Path, times, freqs, dirs, frame, *, prefix: str = "w") -> None:
    stations = []
    for i, j, lon, lat in west_ring_lonlat():
        stations.append((f"{prefix}{j:02d}", lon, lat, frame))
    write_multi_station_nc(path, stations, times, freqs, dirs)


def spectrum_axes() -> tuple[np.ndarray, np.ndarray, int]:
    spec = target_spectral_discrete(FREQ1, XFR, NK, NTH, THOFF)
    freqs = np.asarray(spec.frequencies_hz, dtype=np.float64)
    dirs = np.asarray(spec.directions_deg, dtype=np.float64)
    circ = np.abs(((dirs - TARGET_TO_DIR + 180.0) % 360.0) - 180.0)
    idir = int(np.argmin(circ))
    return freqs, dirs, idir


def df_bin(freqs: np.ndarray, k: int) -> float:
    if freqs.size == 1:
        return 1.0
    if 0 < k < freqs.size - 1:
        return 0.5 * (freqs[k + 1] - freqs[k - 1])
    if k == 0:
        return float(freqs[1] - freqs[0])
    return float(freqs[-1] - freqs[-2])


def efth_for_hs(hs: float, freqs: np.ndarray, idir: int) -> np.ndarray:
    """单频单方向箱，使 4*sqrt(m0) = hs。"""
    m0 = (float(hs) / 4.0) ** 2
    dth = 2.0 * math.pi / NTH
    df = df_bin(freqs, IFREQ)
    peak = m0 / (df * dth) if df * dth > 0 else 0.0
    arr = np.zeros((NK, NTH), dtype=np.float64)
    arr[IFREQ, idir] = peak
    return arr


def sample_times(last: datetime | None = None) -> list[datetime]:
    end = last or (STOP + timedelta(hours=3))
    first = START - timedelta(hours=3)
    out = []
    t = first
    while t <= end:
        out.append(t)
        t += timedelta(hours=1)
    return out


def write_txt_grid(path: Path, value: float) -> None:
    rows = [" ".join(str(value) for _ in range(NX)) for _ in range(NY)]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def ww3_grid_nml() -> str:
    return f"""&SPECTRUM_NML
  SPECTRUM%XFR   = {XFR}
  SPECTRUM%FREQ1 = {FREQ1}
  SPECTRUM%NK    = {NK}
  SPECTRUM%NTH   = {NTH}
  SPECTRUM%THOFF = {THOFF}
/
&RUN_NML
  RUN%FLCX  = T
  RUN%FLCY  = T
  RUN%FLCTH = T
  RUN%FLCK  = F
  RUN%FLSOU = F
/
&TIMESTEPS_NML
  TIMESTEPS%DTMAX = 1800
  TIMESTEPS%DTXY  = 600
  TIMESTEPS%DTKTH = 600
  TIMESTEPS%DTMIN = 10
/
&GRID_NML
  GRID%NAME  = 'btest'
  GRID%NML   = 'namelists.nml'
  GRID%TYPE  = 'RECT'
  GRID%COORD = 'SPHE'
  GRID%CLOS  = 'NONE'
  GRID%ZLIM  = -0.1
  GRID%DMIN  = 2.5
/
&RECT_NML
  RECT%NX  = {NX}
  RECT%NY  = {NY}
  RECT%SX  = {SX}
  RECT%SY  = {SY}
  RECT%SF  = 1
  RECT%X0  = {X0}
  RECT%Y0  = {Y0}
  RECT%SF0 = 1
/
&DEPTH_NML
  DEPTH%SF       = -1.0
  DEPTH%FILENAME = 'grid.bot'
  DEPTH%IDLA     = 1
  DEPTH%IDFM     = 1
/
&MASK_NML
  MASK%FILENAME = 'grid.mask'
  MASK%IDLA     = 1
  MASK%IDFM     = 1
/
"""


def ww3_shel_nml(date_style: str, *, restart_stride: str = "0", restart_stop: str | None = None) -> str:
    rstop = restart_stop or STOP_S
    if date_style == "compact":
        dates = (
            f"  DATE%FIELD   = '{START_S}' '3600' '{STOP_S}'\n"
            f"  DATE%RESTART = '{START_S}' '{restart_stride}' '{rstop}'\n"
        )
    else:
        dates = (
            f"  DATE%FIELD%START    = '{START_S}'\n"
            f"  DATE%FIELD%STRIDE   = '3600'\n"
            f"  DATE%FIELD%STOP     = '{STOP_S}'\n"
            f"  DATE%POINT%STRIDE   = '0'\n"
            f"  DATE%RESTART%START  = '{START_S}'\n"
            f"  DATE%RESTART%STRIDE = '{restart_stride}'\n"
            f"  DATE%RESTART%STOP   = '{rstop}'\n"
        )
    return f"""&DOMAIN_NML
  DOMAIN%IOSTYP = 1
  DOMAIN%START  = '{START_S}'
  DOMAIN%STOP   = '{STOP_S}'
/
&INPUT_NML
  INPUT%FORCING%WINDS        = 'F'
  INPUT%FORCING%CURRENTS     = 'F'
  INPUT%FORCING%WATER_LEVELS = 'F'
  INPUT%FORCING%ICE_CONC     = 'F'
/
&OUTPUT_TYPE_NML
  TYPE%FIELD%LIST = 'HS DIR FP'
/
&OUTPUT_DATE_NML
{dates}/
"""


def ww3_ounf_nml() -> str:
    return f"""&FIELD_NML
  FIELD%TIMESTART  = '{START_S}'
  FIELD%TIMESTRIDE = '3600'
  FIELD%LIST       = 'HS DIR FP'
  FIELD%TIMESPLIT  = 0
  FIELD%TYPE       = 4
/
&FILE_NML
  FILE%NETCDF = 4
/
"""


def ww3_strt_inp(nml_dir: Path) -> str:
    src = nml_dir / "ww3_strt.inp"
    text = src.read_text(encoding="utf-8", errors="replace")
    patched, n = re.subn(r"(?m)^(\s*)3(\s*)$", r"\g<1>5\2", text, count=1)
    if n != 1:
        return "$ calm start\n    5\n$\n"
    return patched


def write_params(
    workdir: Path,
    ver: dict,
    files: list[str],
    *,
    mode: str = "external_spectra",
    method: str = "nearest",
    sides: list[str] | None = None,
    max_distance_km: float = 50.0,
    restart_mode: str = "cold",
    restart_time: str | None = None,
    restart_file: str | None = None,
    pick_latest: bool = True,
) -> Path:
    sides = sides or ["west"]
    payload = {
        "workdir": {"path": str(workdir)},
        "boundary": {
            "mode": mode,
            "source": {"format": "ww3_netcdf", "location": "local", "files": files},
            "selection": {"type": "sides", "sides": sides, "inset_cells": 1},
            "interpolation": {"method": method, "max_distance_km": max_distance_km},
            "validation": {"max_time_gap_seconds": 10800},
            "resources": {"memory_limit_mb": 1024},
        },
        "grid": {
            "mesh_type": "structured",
            "grid_type": "normal",
            "gridgen_version": "Python",
            "lon": [X0, X0 + (NX - 1) * SX],
            "lat": [Y0, Y0 + (NY - 1) * SY],
        },
        "ww3": {
            "version": ver["version"],
            "start_date": "20000101",
            "end_date": "20000101 120000",
            "output_step": 3600,
            "st": "ST4" if "ST4" in ver["st_name"] else "ST2",
            "restart": {
                "mode": restart_mode,
                "restart_time": restart_time,
                "restart_file": restart_file,
                "pick_latest_checkpoint": pick_latest,
            },
            "output_scheme": {"standard": "HS DIR FP"},
        },
        "ww3_grid": {
            "SPECTRUM%XFR": XFR,
            "SPECTRUM%FREQ1": FREQ1,
            "SPECTRUM%NK": NK,
            "SPECTRUM%NTH": NTH,
            "SPECTRUM%THOFF": THOFF,
            "TIMESTEPS%DTMAX": 1800,
            "TIMESTEPS%DTXY": 600,
            "TIMESTEPS%DTKTH": 600,
            "TIMESTEPS%DTMIN": 10,
        },
        "local_run": {
            "local_st": {
                "use": ver["st_name"],
                ver["st_name"]: str(ver["bin"]),
            }
        },
        "calc": {"mode": "region"},
    }
    path = workdir / "params.yml"
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def write_station_nc(path: Path, name: str, lon: float, lat: float, times, freqs, dirs, frame: np.ndarray) -> None:
    efth = np.repeat(frame[None, :, :], len(times), axis=0)
    write_station_file(
        path,
        name=name,
        lon=lon,
        lat=lat,
        times=list(times),
        frequencies=freqs,
        directions=dirs,
        efth=efth,
    )


def write_multi_station_nc(
    path: Path,
    stations: list[tuple[str, float, float, np.ndarray]],
    times,
    freqs,
    dirs,
) -> None:
    from netCDF4 import Dataset
    from workflows.support.netcdf_serialization import serialized_dataset

    path.parent.mkdir(parents=True, exist_ok=True)
    epoch = datetime(1990, 1, 1, tzinfo=timezone.utc)
    tsec = [(t.astimezone(timezone.utc) - epoch).total_seconds() for t in times]
    nsta = len(stations)
    with serialized_dataset(str(path), "w", format="NETCDF3_CLASSIC") as ds:
        ds.createDimension("time", len(tsec))
        ds.createDimension("station", nsta)
        ds.createDimension("frequency", freqs.size)
        ds.createDimension("direction", dirs.size)
        ds.createDimension("string16", 16)
        v_time = ds.createVariable("time", "f8", ("time",))
        v_time.units = "seconds since 1990-01-01 00:00:00"
        v_time.calendar = "gregorian"
        v_time[:] = np.asarray(tsec)
        v_name = ds.createVariable("station_name", "S1", ("station", "string16"))
        v_name[:] = station_char_matrix([item[0] for item in stations], 16)
        v_lon = ds.createVariable("longitude", "f8", ("station",))
        v_lon.units = "degree_east"
        v_lon[:] = [s[1] for s in stations]
        v_lat = ds.createVariable("latitude", "f8", ("station",))
        v_lat.units = "degree_north"
        v_lat[:] = [s[2] for s in stations]
        v_f = ds.createVariable("frequency", "f8", ("frequency",))
        v_f.units = "s-1"
        v_f[:] = freqs
        v_d = ds.createVariable("direction", "f8", ("direction",))
        v_d.units = "degree"
        v_d.standard_name = "sea_surface_wave_to_direction"
        v_d.long_name = "wave direction to"
        v_d[:] = dirs
        v_e = ds.createVariable(
            "efth",
            "f4",
            ("time", "station", "frequency", "direction"),
            fill_value=np.float32(9.96921e36),
        )
        v_e.units = "m2 s rad-1"
        packed = np.zeros((len(times), nsta, freqs.size, dirs.size), dtype=np.float32)
        for i, item in enumerate(stations):
            packed[:, i, :, :] = item[3][None, :, :]
        v_e[:] = packed


def setup_workdir(case_dir: Path, ver: dict, *, restart_stride: str = "0", restart_stop: str | None = None) -> None:
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)
    write_txt_grid(case_dir / "grid.bot", DEPTH)
    write_txt_grid(case_dir / "grid.mask", 1)
    (case_dir / "ww3_grid.nml").write_text(ww3_grid_nml(), encoding="utf-8")
    (case_dir / "ww3_shel.nml").write_text(
        ww3_shel_nml(ver["date_style"], restart_stride=restart_stride, restart_stop=restart_stop),
        encoding="utf-8",
    )
    (case_dir / "ww3_ounf.nml").write_text(ww3_ounf_nml(), encoding="utf-8")
    (case_dir / "ww3_strt.inp").write_text(ww3_strt_inp(ver["nml"]), encoding="utf-8")
    shutil.copy2(ver["nml"] / "namelists.nml", case_dir / "namelists.nml")


def run_cmd(cmd: list[str], cwd: Path, bin_dir: Path, log_path: Path) -> int:
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env.setdefault("TMPDIR", "/tmp")
    env.setdefault("OMPI_MCA_btl", "self,tcp")
    env.setdefault("OMPI_MCA_btl_vader_single_copy_mechanism", "none")
    env.pop("DYLD_INSERT_LIBRARIES", None)
    with log_path.open("ab") as fh:
        fh.write(f"\n>>> {' '.join(cmd)}\n".encode())
        fh.flush()
        proc = subprocess.run(cmd, cwd=str(cwd), env=env, stdout=fh, stderr=subprocess.STDOUT)
    return proc.returncode


def run_tool(bin_dir: Path, tool: str, cwd: Path, log_path: Path, *, mpi: bool = False) -> None:
    exe = bin_dir / tool
    if not exe.is_file():
        raise FileNotFoundError(exe)
    cmd = [str(exe)]
    if mpi:
        mpirun = shutil.which("mpirun") or "/opt/homebrew/bin/mpirun"
        cmd = [mpirun, "-np", "1", "--oversubscribe", str(exe)]
    rc = run_cmd(cmd, cwd, bin_dir, log_path)
    if rc != 0 and not mpi and tool in {"ww3_grid", "ww3_strt", "ww3_shel"}:
        log(f"  {tool} 非 MPI 退出 {rc}，改用 mpirun -np 1")
        run_tool(bin_dir, tool, cwd, log_path, mpi=True)
        return
    if rc != 0:
        tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
        raise RuntimeError(f"{tool} 失败 rc={rc}\n{tail}")


def prepare_and_bounc(workdir: Path) -> None:
    cfg = load_pipeline_config(workdir / "params.yml", validation_stage="boundary")
    result = prepare_boundary_inputs(cfg, execution_context="local", log=log)
    if not result.ok:
        raise RuntimeError(f"prepare 失败：{result.state}")
    run_tool(Path(cfg.local_run.local_st_versions[cfg.local_run.local_st]), "ww3_grid", workdir, workdir / "run.log")
    run_ww3_bounc(cfg, execution_context="local", log=log)


def integrate(workdir: Path, bin_dir: Path, *, skip_strt: bool = False) -> Path:
    log_path = workdir / "run.log"
    if not skip_strt:
        run_tool(bin_dir, "ww3_strt", workdir, log_path)
    run_tool(bin_dir, "ww3_shel", workdir, log_path, mpi=True)
    run_tool(bin_dir, "ww3_ounf", workdir, log_path)
    ncs = [
        p
        for p in workdir.glob("ww3*.nc")
        if p.is_file() and p.parent == workdir
    ]
    if not ncs:
        raise FileNotFoundError(f"{workdir} 没有场输出 NetCDF")
    return ncs[0]


def _nc_var(ds, names: tuple[str, ...]):
    keys = {k.lower(): k for k in ds.variables}
    for name in names:
        if name.lower() in keys:
            return ds.variables[keys[name.lower()]]
    return None


def read_fields(nc_path: Path) -> dict:
    from netCDF4 import Dataset, num2date

    with Dataset(str(nc_path)) as ds:
        hs_v = _nc_var(ds, ("hs", "HS"))
        dir_v = _nc_var(ds, ("dir", "DIR"))
        lon_v = _nc_var(ds, ("longitude", "lon", "x"))
        lat_v = _nc_var(ds, ("latitude", "lat", "y"))
        time_v = _nc_var(ds, ("time",))
        if hs_v is None:
            raise RuntimeError(f"{nc_path} 无 HS，变量={list(ds.variables)}")
        hs = np.ma.filled(np.ma.masked_invalid(hs_v[:]), np.nan).astype(np.float64)
        hs = np.where(np.abs(hs) > 50.0, np.nan, hs)
        direction = None
        if dir_v is not None:
            direction = np.ma.filled(np.ma.masked_invalid(dir_v[:]), np.nan).astype(np.float64)
            direction = np.where(np.abs(direction) > 1000.0, np.nan, direction)
        lon = np.asarray(lon_v[:], dtype=np.float64) if lon_v is not None else None
        lat = np.asarray(lat_v[:], dtype=np.float64) if lat_v is not None else None
        times = []
        if time_v is not None and getattr(time_v, "units", None):
            dates = num2date(time_v[:], time_v.units, getattr(time_v, "calendar", "gregorian"))
            times = [str(x) for x in np.atleast_1d(dates).tolist()]
    # 期望 (time, lat, lon) 或 (time, y, x)
    if hs.ndim == 2:
        hs = hs[None, ...]
        if direction is not None and direction.ndim == 2:
            direction = direction[None, ...]
    return {"hs": hs, "dir": direction, "lon": lon, "lat": lat, "times": times, "path": str(nc_path)}


def interior_slice(hs: np.ndarray) -> np.ndarray:
    """内部：去掉最外两圈（边界环 i=2 / NX-1）。数组轴为 (t, y, x)，x 对应 i。"""
    if hs.ndim != 3:
        raise RuntimeError(f"HS 维数 {hs.shape}")
    # 尝试 (t, ny, nx)
    if hs.shape[-1] == NX and hs.shape[-2] == NY:
        return hs[:, 2:-2, 3:-3]
    if hs.shape[-1] == NY and hs.shape[-2] == NX:
        return hs[:, 3:-3, 2:-2]
    return hs[:, 2:-2, 2:-2]


def west_east_transect(hs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """中心纬向剖面：西侧内部 vs 东侧内部，随时间。"""
    arr = hs
    if arr.shape[-1] == NX and arr.shape[-2] == NY:
        j = NY // 2
        west = arr[:, j, 3]
        east = arr[:, j, NX - 4]
        return west, east
    if arr.shape[-2] == NX:
        j = NY // 2
        west = arr[:, 3, j]
        east = arr[:, NX - 4, j]
        return west, east
    j = arr.shape[1] // 2
    return arr[:, j, 1], arr[:, j, -2]


def circular_diff(a: float, b: float) -> float:
    return abs(((a - b + 180.0) % 360.0) - 180.0)


def analyze_incident(fields: dict) -> dict:
    hs = fields["hs"]
    interior = interior_slice(hs)
    late = interior[max(0, interior.shape[0] // 2) :]
    max_hs = float(np.nanmax(late)) if np.isfinite(late).any() else 0.0
    west, east = west_east_transect(hs)
    early_n = min(4, west.size)
    west_early = float(np.nanmax(west[:early_n])) if west.size else 0.0
    east_early = float(np.nanmax(east[:early_n])) if east.size else 0.0
    mean_dir = None
    if fields["dir"] is not None:
        d = fields["dir"]
        if d.shape[-1] == NX and d.shape[-2] == NY:
            sample = d[max(0, d.shape[0] // 2) :, NY // 2, NX // 2]
        else:
            sample = d[max(0, d.shape[0] // 2) :].reshape(-1)
        sample = sample[np.isfinite(sample)]
        mean_dir = float(np.nanmean(sample)) if sample.size else None
    ok = max_hs >= INCIDENT_HS_MIN
    notes = []
    if west_early + 0.05 < east_early and max_hs < INCIDENT_HS_MIN:
        notes.append("东侧更早有能量，传播去向可能与预期相反")
    if mean_dir is not None:
        d90 = circular_diff(mean_dir, 90.0)
        d270 = circular_diff(mean_dir, 270.0)
        notes.append(f"内部平均 DIR={mean_dir:.1f}（距90° {d90:.1f}，距270° {d270:.1f}）")
        if d90 <= DIR_TOL_DEG:
            notes.append("DIR 接近去向东（90°）")
        elif d270 <= DIR_TOL_DEG:
            notes.append("DIR 接近来向东/去向西（270°），需对照 WW3 DIR 约定")
    return {
        "ok": ok,
        "max_interior_hs": max_hs,
        "west_early_hs": west_early,
        "east_early_hs": east_early,
        "mean_dir": mean_dir,
        "notes": notes,
        "shape": list(hs.shape),
        "nc": fields["path"],
    }


def analyze_zero(fields: dict, incident_hs: float) -> dict:
    interior = interior_slice(fields["hs"])
    max_hs = float(np.nanmax(interior)) if np.isfinite(interior).any() else 0.0
    ratio = incident_hs / max(max_hs, 1e-6)
    ok = max_hs < ZERO_HS_MAX and incident_hs >= INCIDENT_HS_MIN and ratio >= 5.0
    return {"ok": ok, "max_interior_hs": max_hs, "ratio_vs_incident": ratio, "nc": fields["path"]}


def load_mapping(workdir: Path) -> list[dict]:
    path = workdir / "boundary" / "mapping.csv"
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return []
    header = [h.strip() for h in lines[0].split(",")]
    rows = []
    for line in lines[1:]:
        parts = [p.strip() for p in line.split(",")]
        row = dict(zip(header, parts))
        row["ids"] = [x for x in (row.get("source_ids") or "").split("|") if x]
        row["w"] = []
        for token in (row.get("weights") or "").split("|"):
            if not token:
                continue
            try:
                row["w"].append(float(token))
            except ValueError:
                pass
        rows.append(row)
    return rows


def case_incident(ver: dict, freqs, dirs, idir, frame) -> dict:
    workdir = ROOT / ver["version"] / "incident"
    setup_workdir(workdir, ver)
    nc = workdir / "src_west.nc"
    write_west_uniform(nc, sample_times(), freqs, dirs, frame)
    write_params(workdir, ver, [str(nc)])
    prepare_and_bounc(workdir)
    out = integrate(workdir, ver["bin"])
    fields = read_fields(out)
    analysis = analyze_incident(fields)
    analysis["ww3_bounc"] = str(ver["bin"] / "ww3_bounc")
    analysis["switch"] = ver["switch"].read_text(encoding="utf-8").strip() if ver["switch"].is_file() else ""
    return {"workdir": str(workdir), **analysis}


def case_zero(ver: dict, freqs, dirs, idir, incident_hs: float) -> dict:
    workdir = ROOT / ver["version"] / "zero"
    setup_workdir(workdir, ver)
    nc = workdir / "src_zero.nc"
    write_west_uniform(nc, sample_times(), freqs, dirs, np.zeros((NK, NTH)), prefix="z")
    write_params(workdir, ver, [str(nc)])
    prepare_and_bounc(workdir)
    out = integrate(workdir, ver["bin"])
    return {"workdir": str(workdir), **analyze_zero(read_fields(out), incident_hs)}


def case_insufficient(ver: dict, freqs, dirs, frame) -> dict:
    workdir = ROOT / ver["version"] / "insufficient"
    setup_workdir(workdir, ver)
    nc = workdir / "src_short.nc"
    times = sample_times(last=datetime(2000, 1, 1, 3, 0, tzinfo=timezone.utc))
    write_west_uniform(nc, times, freqs, dirs, frame)
    write_params(workdir, ver, [str(nc)])
    cfg = load_pipeline_config(workdir / "params.yml", validation_stage="boundary")
    try:
        prepare_boundary_inputs(cfg, execution_context="local", log=log)
        return {"ok": False, "error": "prepare 未失败", "workdir": str(workdir)}
    except BoundaryError as exc:
        ok = exc.code == "BOUNDARY_TIME_COVERAGE"
        return {"ok": ok, "code": exc.code, "message": exc.message, "workdir": str(workdir)}


def case_disable(ver: dict) -> dict:
    src = ROOT / ver["version"] / "incident"
    workdir = ROOT / ver["version"] / "disable"
    if workdir.exists():
        shutil.rmtree(workdir)
    shutil.copytree(src, workdir, ignore=shutil.ignore_patterns("ww3*.nc", "out_grd.ww3", "restart*"))
    write_params(workdir, ver, [], mode="none")
    cfg = load_pipeline_config(workdir / "params.yml", validation_stage="boundary")
    result = prepare_boundary_inputs(cfg, execution_context="local", log=log)
    nml = (workdir / "ww3_grid.nml").read_text(encoding="utf-8")
    nest_gone = not (workdir / "nest.ww3").is_file()
    archived = list((workdir / "boundary" / "archive").glob("nest.*.ww3")) if (workdir / "boundary" / "archive").is_dir() else []
    mask_restored = "grid.mask_nobound" in nml or ("grid.mask" in nml and "grid.mask_boundary" not in nml)
    ok = result.ok and result.state == "disabled" and nest_gone and mask_restored
    return {
        "ok": ok,
        "state": result.state,
        "nest_gone": nest_gone,
        "archived": [str(p) for p in archived],
        "mask_restored": mask_restored,
        "workdir": str(workdir),
    }


def case_linear(ver: dict, freqs, dirs, idir) -> dict:
    workdir = ROOT / ver["version"] / "linear"
    setup_workdir(workdir, ver)
    # 源点放在西边界环南、北外侧，使环上点投影落在开线段内；距离门槛放宽为本算例几何所需。
    south = lonlat(2, 1)
    north = lonlat(2, NY)
    times = sample_times()
    f_s = workdir / "src_south.nc"
    f_n = workdir / "src_north.nc"
    write_station_nc(f_s, "south", south[0], south[1], times, freqs, dirs, efth_for_hs(HS_SOUTH, freqs, idir))
    write_station_nc(f_n, "north", north[0], north[1], times, freqs, dirs, efth_for_hs(HS_NORTH, freqs, idir))
    write_params(workdir, ver, [str(f_s), str(f_n)], method="linear", max_distance_km=300.0)
    cfg = load_pipeline_config(workdir / "params.yml", validation_stage="boundary")
    try:
        prepare_boundary_inputs(cfg, execution_context="local", log=log)
    except BoundaryError as exc:
        return {"ok": False, "code": exc.code, "message": exc.message, "workdir": str(workdir)}
    rows = load_mapping(workdir)
    ids = sorted({sid for r in rows for sid in r["ids"]})
    interior_w = [w for r in rows for w in r["w"] if 0.0 < w < 1.0]
    covered = sum(1 for r in rows if r.get("covered") in {"1", "True", "true"})
    run_tool(ver["bin"], "ww3_grid", workdir, workdir / "run.log")
    run_ww3_bounc(cfg, execution_context="local", log=log)
    nest = read_nest_file(workdir / "nest.ww3")
    mapping_ok = covered >= 3 and len(ids) >= 2 and len(interior_w) >= 1
    return {
        "ok": mapping_ok and nest.nbi > 0,
        "mapping_rows": len(rows),
        "covered": covered,
        "source_ids": ids,
        "interior_weights": interior_w[:8],
        "nbi": nest.nbi,
        "linear_indices": len(nest.mapping_indices or []),
        "workdir": str(workdir),
    }


def case_multistation(ver: dict, freqs, dirs, idir) -> dict:
    workdir = ROOT / ver["version"] / "multistation"
    setup_workdir(workdir, ver)
    times = sample_times()
    js = (2, (NY + 1) // 2, NY - 1)
    stations = []
    for j, hs in zip(js, (HS_SOUTH, HS_INCIDENT, HS_NORTH)):
        lon, lat = lonlat(2, j)
        stations.append((f"s{j:02d}", lon, lat, efth_for_hs(hs, freqs, idir)))
    nc = workdir / "src_multi.nc"
    write_multi_station_nc(nc, stations, times, freqs, dirs)
    write_params(workdir, ver, [str(nc)])
    cfg = load_pipeline_config(workdir / "params.yml", validation_stage="boundary")
    prepare_boundary_inputs(cfg, execution_context="local", log=log)
    rows = load_mapping(workdir)
    ids = sorted({sid for r in rows for sid in r["ids"]})
    names = {r.get("source_ids", "") for r in rows}
    ok = len(ids) >= 3 and all(row.get("covered") in {"1", "True", "true"} for row in rows)
    return {
        "ok": ok,
        "mapping_rows": len(rows),
        "ids": ids,
        "source_ids_raw": sorted(names),
        "workdir": str(workdir),
    }


def case_timesplit(ver: dict, freqs, dirs, frame) -> dict:
    one = ROOT / ver["version"] / "incident"
    workdir = ROOT / ver["version"] / "timesplit"
    setup_workdir(workdir, ver)
    lon, lat = lonlat(2, (NY + 1) // 2)
    mid = datetime(2000, 1, 1, 6, 0, tzinfo=timezone.utc)
    t1 = [t for t in sample_times() if t <= mid]
    t2 = [t for t in sample_times() if t >= mid]
    a = workdir / "src_a.nc"
    b = workdir / "src_b.nc"
    write_west_uniform(a, t1, freqs, dirs, frame, prefix="a")
    write_west_uniform(b, t2, freqs, dirs, frame, prefix="a")
    write_params(workdir, ver, [str(a), str(b)])
    prepare_and_bounc(workdir)
    nest_a = read_nest_file(one / "nest.ww3")
    nest_b = read_nest_file(workdir / "nest.ww3")
    ok = nest_a.nbi == nest_b.nbi and nest_a.nk == nest_b.nk and nest_a.nth == nest_b.nth and nest_a.n_records == nest_b.n_records
    return {
        "ok": ok,
        "one_file": {"nbi": nest_a.nbi, "nk": nest_a.nk, "nth": nest_a.nth, "n_times": nest_a.n_records},
        "two_files": {"nbi": nest_b.nbi, "nk": nest_b.nk, "nth": nest_b.nth, "n_times": nest_b.n_records},
        "workdir": str(workdir),
    }


def case_hotstart(ver: dict, freqs, dirs, frame, continuous_nc: str) -> dict:
    mid = "20000101 060000"
    workdir = ROOT / ver["version"] / "hotstart"
    setup_workdir(workdir, ver, restart_stride="21600", restart_stop=mid)
    nc = workdir / "src_west.nc"
    write_west_uniform(nc, sample_times(), freqs, dirs, frame)
    write_params(workdir, ver, [str(nc)])
    prepare_and_bounc(workdir)
    integrate(workdir, ver["bin"])
    dated = sorted(workdir.glob("*.restart.ww3"))
    numbered = sorted(p for p in workdir.glob("restart*.ww3") if p.name != "restart.ww3")
    plain = workdir / "restart.ww3"
    if dated:
        ckpt = dated[-1]
    elif numbered:
        ckpt = numbered[-1]
    elif plain.is_file():
        ckpt = plain
    else:
        return {"ok": False, "error": "没有 restart 文件", "workdir": str(workdir)}
    second = ROOT / ver["version"] / "hotstart_resume"
    if second.exists():
        shutil.rmtree(second)
    shutil.copytree(workdir, second, ignore=shutil.ignore_patterns("ww3*.nc", "out_grd.ww3"))
    shutil.copy2(ckpt, second / "restart.ww3")
    write_params(
        second,
        ver,
        [str(second / "src_west.nc")],
        restart_mode="restart",
        restart_time=mid,
        restart_file="restart.ww3",
        pick_latest=False,
    )
    shel = (second / "ww3_shel.nml").read_text(encoding="utf-8")
    shel = shel.replace(f"DOMAIN%START  = '{START_S}'", f"DOMAIN%START  = '{mid}'")
    (second / "ww3_shel.nml").write_text(shel, encoding="utf-8")
    cfg = load_pipeline_config(second / "params.yml", validation_stage="boundary")
    try:
        prepare_boundary_inputs(cfg, execution_context="local", log=log)
        run_tool(ver["bin"], "ww3_grid", second, second / "run.log")
        run_ww3_bounc(cfg, execution_context="local", log=log)
    except BoundaryError as exc:
        return {"ok": False, "code": exc.code, "message": exc.message, "checkpoint": str(ckpt), "workdir": str(second)}
    out = integrate(second, ver["bin"], skip_strt=True)
    cont = read_fields(Path(continuous_nc))
    hot = read_fields(out)
    h1 = interior_slice(cont["hs"])
    h2 = interior_slice(hot["hs"])
    a = float(np.nanmax(h1[-1])) if h1.size else 0.0
    b = float(np.nanmax(h2[-1])) if h2.size else 0.0
    rel = abs(a - b) / max(a, 1e-6)
    return {
        "ok": rel <= HOTSTART_REL_TOL and b >= INCIDENT_HS_MIN * 0.5,
        "continuous_last_hs": a,
        "hotstart_last_hs": b,
        "rel_diff": rel,
        "checkpoint": ckpt.name,
        "workdir": str(second),
        "n_times_hot": int(hot["hs"].shape[0]),
    }


def run_version(ver: dict, freqs, dirs, idir, frame) -> dict:
    log(f"\n======== {ver['label']}  {ver['bin']} ========")
    switch = ver["switch"].read_text(encoding="utf-8").strip() if ver["switch"].is_file() else ""
    log(f"switch: {switch}")
    for tool in ("ww3_grid", "ww3_bounc", "ww3_strt", "ww3_shel", "ww3_ounf"):
        path = ver["bin"] / tool
        if not path.is_file():
            raise FileNotFoundError(path)
        log(f"  {tool}: {path}")
    report: dict = {"label": ver["label"], "bin": str(ver["bin"]), "switch": switch, "cases": {}}

    def _run(name: str, fn):
        try:
            result = fn()
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
            if isinstance(exc, BoundaryError):
                result["code"] = exc.code
                result["message"] = exc.message
            log(f"{name} 失败：{exc}")
        report["cases"][name] = result
        extra = {k: result.get(k) for k in ("max_interior_hs", "code", "rel_diff", "nbi") if k in result}
        log(f"{name}：ok={result.get('ok')} {extra}")
        return result

    incident = _run("incident", lambda: case_incident(ver, freqs, dirs, idir, frame))
    _run("zero", lambda: case_zero(ver, freqs, dirs, idir, float(incident.get("max_interior_hs") or 0.0)))
    _run("insufficient", lambda: case_insufficient(ver, freqs, dirs, frame))
    _run("disable", lambda: case_disable(ver))
    _run("linear", lambda: case_linear(ver, freqs, dirs, idir))
    _run("multistation", lambda: case_multistation(ver, freqs, dirs, idir))
    _run("timesplit", lambda: case_timesplit(ver, freqs, dirs, frame))
    if incident.get("ok") and incident.get("nc"):
        _run("hotstart", lambda: case_hotstart(ver, freqs, dirs, frame, incident["nc"]))
    else:
        report["cases"]["hotstart"] = {"ok": False, "skipped": True, "reason": "入射未通过"}
        log("hotstart：skipped")
    report["ok"] = all(case.get("ok") for name, case in report["cases"].items() if not case.get("skipped"))
    return report


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    freqs, dirs, idir = spectrum_axes()
    frame = efth_for_hs(HS_INCIDENT, freqs, idir)
    note = {
        "thresholds": {
            "incident_hs_min": INCIDENT_HS_MIN,
            "zero_hs_max": ZERO_HS_MAX,
            "dir_tol_deg": DIR_TOL_DEG,
            "hotstart_rel_tol": HOTSTART_REL_TOL,
        },
        "grid": {"nx": NX, "ny": NY, "sx": SX, "x0": X0, "y0": Y0},
        "spectrum": {
            "freq1": FREQ1,
            "nk": NK,
            "nth": NTH,
            "ifreq": IFREQ,
            "idir": idir,
            "dir_deg": float(dirs[idir]),
            "dirs": [float(x) for x in dirs],
        },
        "binaries": [
            {
                "label": v["label"],
                "bin": str(v["bin"]),
                "switch": v["switch"].read_text(encoding="utf-8").strip() if v["switch"].is_file() else "",
            }
            for v in VERSIONS
        ],
    }
    (ROOT / "ACCEPTANCE_NOTE.json").write_text(json.dumps(note, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"目标方向箱 idir={idir} → {dirs[idir]:.2f}°（期望接近 {TARGET_TO_DIR}）")
    reports = []
    failed = False
    for ver in VERSIONS:
        try:
            reports.append(run_version(ver, freqs, dirs, idir, frame))
        except Exception as exc:
            failed = True
            reports.append({"label": ver["label"], "ok": False, "error": str(exc), "trace": traceback.format_exc()})
            log(f"{ver['label']} 异常：{exc}")
            log(traceback.format_exc())
    payload = {"note": note, "reports": reports}
    out = ROOT / "results.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    log(f"\n结果写入 {out}")
    for item in reports:
        log(f"  {item.get('label')}: ok={item.get('ok')} error={item.get('error', '')}")
        for name, case in (item.get("cases") or {}).items():
            log(f"    {name}: ok={case.get('ok')} { {k: case.get(k) for k in case if k in ('max_interior_hs', 'code', 'rel_diff', 'nbi')} }")
    return 0 if (not failed and all(r.get("ok") for r in reports)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
