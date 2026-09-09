"""坐标、单位、维度整理，并写出一站一文件的执行用 NetCDF。"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from ...domain.boundary_models import (
    NEG_SPECTRA_CLIP_TOL,
    NORMALIZE_ALGO_VERSION,
    SpectralDiscrete,
)
from ...support.netcdf_serialization import serialized_dataset
from .errors import BoundaryError
from .spectra_reader import SpectraFileMeta, inspect_spectra_file, read_station_efth
from .spectrum_coords import cyclic_permutation_offset, directions_match, frequencies_match


CancelFn = Callable[[], None]


def _check_cancel(cancel: CancelFn | None) -> None:
    if cancel is not None:
        cancel()


def infer_direction_convention(meta: SpectraFileMeta) -> str:
    text = " ".join([meta.dir_long_name, meta.dir_standard_name, meta.dir_units]).lower()
    # 下划线与空格都要认：ww3_ounp 写 'sea_surface_wave_to_direction'，
    # 而官方回归算例（ww3_tp2.19/2.20）的 boundary*.nc 写成
    # 'sea surface wave to direction'（空格）。只匹配下划线会把官方文件判成约定不明。
    flat = text.replace("_", " ").replace("-", " ")
    flat = " ".join(flat.split())
    if "from direction" in flat or "coming from" in flat:
        return "from_direction"
    if "to direction" in flat or "going to" in flat or "towards" in flat:
        return "to_direction"
    # WW3 原生 ounp 常见 long_name=wave direction，表示传播去向
    if "wave direction" in flat and "from" not in flat:
        return "to_direction"
    raise BoundaryError(
        "BOUNDARY_CONVENTION_UNKNOWN",
        f"方向约定不明：{meta.path}",
        context={
            "path": meta.path,
            "long_name": meta.dir_long_name,
            "standard_name": meta.dir_standard_name,
        },
        hints=["使用带 to_direction / from_direction 元数据的 WW3 原生谱"],
    )


def efth_unit_scale(units: str) -> tuple[float, str]:
    raw = (units or "").strip()
    lower = raw.lower().replace("²", "2").replace("rad-1", "rad-1")
    if not raw:
        raise BoundaryError(
            "BOUNDARY_CONVENTION_UNKNOWN",
            "efth 缺少 units，禁止猜测",
            context={"units": raw},
        )
    # ww3_ounp 的 NCVARTYPE<=3 把谱按 NINT(log10(efth+1e-12)/0.0004) 存成 NF90_SHORT，
    # units 写作 'log10(m2 s rad-1 +1E-12)'。这串里含 "rad"，若不先拦下来就会被当成
    # 线性 m2 s rad-1；netCDF4 只做线性解包，拿到的是 log10 值而不是谱。
    # 首版不支持对数打包输入，必须在这里给出可操作的报错，不能落到"谱值为负"。
    if "log10" in lower or "logarithm" in lower:
        raise BoundaryError(
            "BOUNDARY_CONVENTION_UNKNOWN",
            f"efth 是对数打包的 ww3_ounp 输出（units={raw}），首版不支持",
            context={"units": raw},
            hints=[
                "重跑 ww3_ounp 并设 FILE%NETCDF 的 NCVARTYPE=4（写 NF90_FLOAT 线性谱，"
                "units 为 'm2 s rad-1'）",
                "对数打包为 NINT(log10(efth+1e-12)/0.0004) 的 NF90_SHORT，"
                "需按 10**x-1e-12 反解，本版不做该反解",
            ],
        )
    per_deg = ("deg" in lower or "degree" in lower) and "rad" not in lower
    if per_deg:
        return 180.0 / math.pi, "m2 s rad-1"
    if "rad" in lower:
        return 1.0, "m2 s rad-1"
    raise BoundaryError(
        "BOUNDARY_CONVENTION_UNKNOWN",
        f"无法识别的 efth 单位：{raw}",
        context={"units": raw},
        hints=["首版需要每 Hz、每弧度的方差谱密度"],
    )


def drop_duplicate_360(dirs: np.ndarray, efth: np.ndarray | None) -> tuple[np.ndarray, np.ndarray | None]:
    dirs = np.asarray(dirs, dtype=np.float64).reshape(-1)
    if dirs.size >= 2:
        wrap = abs(((dirs[-1] - dirs[0] + 180.0) % 360.0) - 180.0)
        if wrap <= 1e-4:
            dirs = dirs[:-1]
            if efth is not None:
                efth = np.asarray(efth)[..., :-1]
    return dirs, efth


def align_spectral_axes(
    freqs: np.ndarray,
    dirs: np.ndarray,
    efth: np.ndarray,
    target: SpectralDiscrete,
    *,
    convention: str,
    unit_scale: float,
) -> np.ndarray:
    """把源谱对齐到目标频率/方向离散。禁止自动插值。"""
    freqs = np.asarray(freqs, dtype=np.float64).reshape(-1)
    dirs = np.asarray(dirs, dtype=np.float64).reshape(-1)
    data = np.asarray(efth, dtype=np.float64) * float(unit_scale)
    dirs, data = drop_duplicate_360(dirs, data)
    checksum = float(np.nansum(data))
    if convention == "from_direction":
        dirs = np.mod(dirs + 180.0, 360.0)
    tgt_f = np.asarray(target.frequencies_hz, dtype=np.float64)
    tgt_d = np.asarray(target.directions_deg, dtype=np.float64)
    if freqs.size != tgt_f.size:
        raise BoundaryError(
            "BOUNDARY_SPECTRAL_MISMATCH",
            f"频率档数不同：源 {freqs.size}，目标 {tgt_f.size}",
            context={"n_source": int(freqs.size), "n_target": int(tgt_f.size)},
        )
    freq_axis = -2 if data.ndim >= 2 else 0
    if frequencies_match(freqs, tgt_f):
        pass
    elif frequencies_match(freqs[::-1], tgt_f):
        freqs = freqs[::-1]
        data = np.flip(data, axis=freq_axis)
    else:
        order = np.argsort(freqs)
        if frequencies_match(freqs[order], tgt_f):
            freqs = freqs[order]
            data = np.take(data, order, axis=freq_axis)
        else:
            raise BoundaryError(
                "BOUNDARY_SPECTRAL_MISMATCH",
                "源频率与目标 SPECTRUM%FREQ1/XFR/NK 不一致，首版禁止频率插值",
                context={
                    "source": [float(v) for v in freqs[:8]],
                    "target": [float(v) for v in tgt_f[:8]],
                    "rtol": 1e-6,
                    "atol_hz": 1e-10,
                },
                hints=["将目标谱参数设为源谱，或更换与目标离散一致的源数据"],
            )
    if dirs.size != tgt_d.size:
        raise BoundaryError(
            "BOUNDARY_SPECTRAL_MISMATCH",
            f"方向档数不同：源 {dirs.size}，目标 {tgt_d.size}",
            context={"n_source": int(dirs.size), "n_target": int(tgt_d.size)},
        )
    if directions_match(dirs, tgt_d):
        pass
    else:
        offset = cyclic_permutation_offset(dirs, tgt_d)
        if offset is None:
            order = np.argsort(np.mod(dirs, 360.0))
            # sorting for display is not allowed unless it matches after cyclic shift of original
            raise BoundaryError(
                "BOUNDARY_SPECTRAL_MISMATCH",
                "源方向与目标 THOFF/NTH 离散不等价，禁止自动方向插值",
                context={
                    "source": [float(v) for v in dirs[:8]],
                    "target": [float(v) for v in tgt_d[:8]],
                    "angle_tol_deg": 1e-4,
                    "thoff": target.thoff,
                },
            )
        dirs = np.roll(dirs, -offset)
        data = np.roll(data, -offset, axis=-1)
    after = float(np.nansum(data))
    scale = max(1.0, abs(checksum))
    if abs(after - checksum) > 1e-6 * scale:
        raise BoundaryError(
            "BOUNDARY_SPECTRAL_MISMATCH",
            "方向/频率重排后积分方差不一致",
            context={"before": checksum, "after": after},
        )
    return np.asarray(data, dtype=np.float64)


def sanitize_efth(data: np.ndarray) -> tuple[np.ndarray, int, float]:
    arr = np.asarray(data, dtype=np.float64)
    if not np.isfinite(arr).all():
        n_bad = int(np.size(arr) - np.isfinite(arr).sum())
        raise BoundaryError(
            "BOUNDARY_INVALID_SPECTRA",
            f"谱值含非有限或未解码填充值（{n_bad} 个）",
            context={"n_invalid": n_bad},
        )
    neg = arr < 0
    n_neg = int(neg.sum())
    max_fix = 0.0
    if n_neg:
        worst = float(arr[neg].min())
        if worst < -NEG_SPECTRA_CLIP_TOL:
            raise BoundaryError(
                "BOUNDARY_INVALID_SPECTRA",
                f"谱值存在明显负值（最小 {worst}）",
                context={"min_value": worst, "n_negative": n_neg},
            )
        max_fix = abs(worst)
        arr = arr.copy()
        arr[neg] = 0.0
    return arr, n_neg, max_fix


def write_station_file(
    path: Path,
    *,
    name: str,
    lon: float,
    lat: float,
    times: list[datetime],
    frequencies: np.ndarray,
    directions: np.ndarray,
    efth: np.ndarray,
) -> None:
    """写出 netCDF3 classic、station=1、float32 未打包谱值。"""
    from netCDF4 import Dataset, stringtochar

    path.parent.mkdir(parents=True, exist_ok=True)
    times_utc = []
    epoch = datetime(1990, 1, 1, tzinfo=timezone.utc)
    for t in times:
        dt = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        times_utc.append((dt.astimezone(timezone.utc) - epoch).total_seconds())
    name16 = (name or "station")[:16].ljust(16)
    with serialized_dataset(str(path), "w", format="NETCDF3_CLASSIC") as ds:
        ds.createDimension("time", len(times_utc))
        ds.createDimension("station", 1)
        ds.createDimension("frequency", int(np.asarray(frequencies).size))
        ds.createDimension("direction", int(np.asarray(directions).size))
        ds.createDimension("string16", 16)
        v_time = ds.createVariable("time", "f8", ("time",))
        v_time.units = "seconds since 1990-01-01 00:00:00"
        v_time.calendar = "gregorian"
        v_time[:] = np.asarray(times_utc, dtype=np.float64)
        v_name = ds.createVariable("station_name", "S1", ("station", "string16"))
        v_name[:] = stringtochar(np.array([name16], dtype="S16"))
        v_lon = ds.createVariable("longitude", "f8", ("station",))
        v_lon.units = "degree_east"
        v_lon[:] = [float(lon)]
        v_lat = ds.createVariable("latitude", "f8", ("station",))
        v_lat.units = "degree_north"
        v_lat[:] = [float(lat)]
        v_f = ds.createVariable("frequency", "f8", ("frequency",))
        v_f.units = "s-1"
        v_f[:] = np.asarray(frequencies, dtype=np.float64)
        v_d = ds.createVariable("direction", "f8", ("direction",))
        v_d.units = "degree"
        v_d.standard_name = "sea_surface_wave_to_direction"
        v_d.long_name = "wave direction to"
        v_d[:] = np.asarray(directions, dtype=np.float64)
        v_e = ds.createVariable(
            "efth",
            "f4",
            ("time", "station", "frequency", "direction"),
            fill_value=np.float32(9.96921e36),
        )
        v_e.units = "m2 s rad-1"
        packed = np.asarray(efth, dtype=np.float32)[:, None, :, :]
        v_e[:] = packed
        ds.normalize_algo_version = NORMALIZE_ALGO_VERSION


def merge_station_time_series(
    slices: list[tuple[list[datetime], np.ndarray]],
) -> tuple[list[datetime], np.ndarray]:
    """按时间归并同一站点分片；重复时刻仅在谱值一致时去重。"""
    by_time: dict[datetime, np.ndarray] = {}
    origins: dict[datetime, int] = {}
    for idx, (times, efth) in enumerate(slices):
        for t, frame in zip(times, efth):
            key = t.astimezone(timezone.utc).replace(microsecond=0)
            if key in by_time:
                if not np.allclose(by_time[key], frame, rtol=1e-6, atol=1e-10, equal_nan=True):
                    raise BoundaryError(
                        "BOUNDARY_DUPLICATE_CONFLICT",
                        f"重复时刻 {key.strftime('%Y%m%d %H%M%S')} 的谱值冲突",
                        context={"time": key.strftime("%Y%m%d %H%M%S"), "slice": idx},
                    )
                continue
            by_time[key] = np.asarray(frame, dtype=np.float64)
            origins[key] = idx
    if not by_time:
        raise BoundaryError("BOUNDARY_TIME_COVERAGE", "站点没有有效时间样本")
    ordered = sorted(by_time)
    stacked = np.stack([by_time[t] for t in ordered], axis=0)
    return ordered, stacked


def crop_halo_indices(
    times: list[datetime],
    start: datetime,
    end: datetime,
) -> tuple[int, int]:
    """返回覆盖有效窗口的半开区间 [i0, i1)。"""
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if not times:
        raise BoundaryError("BOUNDARY_TIME_COVERAGE", "没有谱时间样本")
    stamps = [t.astimezone(timezone.utc) if t.tzinfo else t.replace(tzinfo=timezone.utc) for t in times]
    if stamps[0] > start:
        if stamps[0] != start:
            raise BoundaryError(
                "BOUNDARY_TIME_COVERAGE",
                "有效起点之前缺少谱样本，禁止外推",
                context={
                    "effective_start": start.strftime("%Y%m%d %H%M%S"),
                    "first_sample": stamps[0].strftime("%Y%m%d %H%M%S"),
                },
            )
    if stamps[-1] < end:
        if stamps[-1] != end:
            raise BoundaryError(
                "BOUNDARY_TIME_COVERAGE",
                "有效终点之后缺少谱样本，禁止外推",
                context={
                    "effective_end": end.strftime("%Y%m%d %H%M%S"),
                    "last_sample": stamps[-1].strftime("%Y%m%d %H%M%S"),
                },
            )
    i0 = 0
    for i, t in enumerate(stamps):
        if t <= start:
            i0 = i
        else:
            break
    i1 = len(stamps) - 1
    for i, t in enumerate(stamps):
        if t >= end:
            i1 = i
            break
    if stamps[i0] > start or stamps[i1] < end:
        raise BoundaryError(
            "BOUNDARY_TIME_COVERAGE",
            "裁剪后仍不能覆盖有效积分区间",
            context={
                "effective_start": start.strftime("%Y%m%d %H%M%S"),
                "effective_end": end.strftime("%Y%m%d %H%M%S"),
            },
        )
    return i0, i1 + 1


def overlap_time_indices(
    times: list[datetime],
    start: datetime,
    end: datetime,
) -> tuple[int, int]:
    """与闭区间 [start, end] 相交的半开下标。无交集返回 (0, 0)。不要求单文件覆盖整个窗口。"""
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if not times:
        return 0, 0
    i0 = None
    i1 = 0
    for i, raw in enumerate(times):
        t = raw.astimezone(timezone.utc) if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        if t < start or t > end:
            continue
        if i0 is None:
            i0 = i
        i1 = i + 1
    if i0 is None:
        return 0, 0
    return i0, i1


def crop_with_halo(
    times: list[datetime],
    efth: np.ndarray,
    start: datetime,
    end: datetime,
) -> tuple[list[datetime], np.ndarray]:
    """保留覆盖有效起点的前一个样本及有效终点的后一个样本。"""
    stamps = [t.astimezone(timezone.utc) if t.tzinfo else t.replace(tzinfo=timezone.utc) for t in times]
    i0, i1 = crop_halo_indices(times, start, end)
    return stamps[i0:i1], np.asarray(efth[i0:i1])


def assert_time_gaps(times: list[datetime], max_gap_seconds: int) -> None:
    if max_gap_seconds <= 0:
        raise BoundaryError("BOUNDARY_TIME_GAP", "max_time_gap_seconds 必须为正数")
    for a, b in zip(times, times[1:]):
        dt = (b - a).total_seconds()
        if dt <= 0:
            raise BoundaryError(
                "BOUNDARY_TIME_GAP",
                "时间轴必须严格递增",
                context={"t0": a.isoformat(), "t1": b.isoformat(), "dt": dt},
            )
        if dt > max_gap_seconds:
            raise BoundaryError(
                "BOUNDARY_TIME_GAP",
                f"相邻谱时刻间隔 {dt:.0f} s 超过 {max_gap_seconds} s",
                context={"t0": a.strftime("%Y%m%d %H%M%S"), "t1": b.strftime("%Y%m%d %H%M%S"), "dt": dt},
                hints=["补充数据或提高明确的间隔要求"],
            )


def times_identical(series: list[list[datetime]]) -> bool:
    if not series:
        return True
    ref = series[0]
    for other in series[1:]:
        if len(other) != len(ref):
            return False
        for a, b in zip(ref, other):
            if a.astimezone(timezone.utc) != b.astimezone(timezone.utc):
                return False
    return True


def variance_integral(efth: np.ndarray, frequencies: np.ndarray, directions_deg: np.ndarray) -> np.ndarray:
    """按同一频率箱宽、方向箱宽积分总方差（不依赖绝对箱宽一致性，用于相对检查）。"""
    freq = np.asarray(frequencies, dtype=np.float64).reshape(-1)
    dirs = np.asarray(directions_deg, dtype=np.float64).reshape(-1)
    data = np.asarray(efth, dtype=np.float64)
    if freq.size > 1:
        df = np.empty_like(freq)
        df[1:-1] = 0.5 * (freq[2:] - freq[:-2])
        df[0] = freq[1] - freq[0]
        df[-1] = freq[-1] - freq[-2]
    else:
        df = np.array([1.0])
    dth = 2.0 * math.pi / max(dirs.size, 1)
    return np.sum(data * df[None, :, None] * dth, axis=(1, 2))
