"""WW3 原生点谱 NetCDF 元数据与分片读取。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from ...domain.boundary_models import BoundaryStation
from ...support.netcdf_serialization import serialized_dataset
from .errors import BoundaryError


_FREQ_NAMES = ("frequency", "freq", "f", "frequencies")
_DIR_NAMES = ("direction", "dir", "theta", "directions")
_EFTH_NAMES = ("efth", "efth2d", "d2sd", "variance_density")
_LON_NAMES = ("longitude", "lon", "station_x", "x")
_LAT_NAMES = ("latitude", "lat", "station_y", "y")
_NAME_NAMES = ("station_name", "station", "name", "stations")
_TIME_NAMES = ("time", "time_utc")


@dataclass
class SpectraFileMeta:
    path: str
    n_stations: int = 0
    n_times: int = 0
    n_freq: int = 0
    n_dir: int = 0
    time_start: str | None = None
    time_end: str | None = None
    times: list[datetime] = field(default_factory=list)
    stations: list[BoundaryStation] = field(default_factory=list)
    frequencies_hz: np.ndarray | None = None
    directions_deg: np.ndarray | None = None
    efth_dims: tuple[str, ...] = ()
    freq_units: str = ""
    dir_units: str = ""
    efth_units: str = ""
    dir_long_name: str = ""
    dir_standard_name: str = ""
    layout: str = ""


def _first_var(ds, names: Iterable[str]):
    keys = {name.lower(): name for name in ds.variables}
    for candidate in names:
        hit = keys.get(candidate.lower())
        if hit is not None:
            return ds.variables[hit]
    return None


def _decode_times(var) -> list[datetime]:
    from netCDF4 import num2date

    units = getattr(var, "units", None)
    if not units:
        raise BoundaryError(
            "BOUNDARY_CONVENTION_UNKNOWN",
            "时间变量缺少 units 属性",
            context={"variable": var.name},
        )
    calendar = getattr(var, "calendar", "gregorian")
    cal = str(calendar).lower()
    if cal not in {"standard", "gregorian", "proleptic_gregorian"}:
        raise BoundaryError(
            "BOUNDARY_CONVENTION_UNKNOWN",
            f"不支持的时间历法 {calendar}，首版仅接受 gregorian/standard",
            context={"calendar": calendar},
        )
    raw = np.asarray(var[:])
    dates = num2date(raw, units=units, calendar=calendar, only_use_cftime_datetimes=False)
    out: list[datetime] = []
    for item in np.atleast_1d(dates).tolist():
        if item is None:
            raise BoundaryError("BOUNDARY_TIME_COVERAGE", "时间轴含无法解码的时刻")
        if isinstance(item, datetime):
            dt = item
        else:
            dt = datetime(
                int(item.year),
                int(item.month),
                int(item.day),
                int(getattr(item, "hour", 0)),
                int(getattr(item, "minute", 0)),
                int(getattr(item, "second", 0)),
            )
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        out.append(dt)
    return out


def _decode_names(var, n: int) -> list[str]:
    """站名解码。

    WW3 原生点谱的 ``station_name`` 是 ``(station, string16)`` 的 ``S1`` 字符数组：
    dtype.kind 同样是 ``S``，所以必须先按 ndim==2 拼接，再走一维字符串分支；
    否则 ``arr[i]`` 取到的是整行字节数组，``str()`` 会得到 ``[b'w' b'0' ...]``。
    """
    data = var[:]
    names: list[str] = []
    arr = np.asarray(data)
    # char array (station, strlen)：必须先判维数，S1 的 kind 也是 "S"
    if arr.ndim == 2:
        for row in arr[:n]:
            chars = []
            for ch in row:
                if isinstance(ch, bytes):
                    chars.append(ch.decode("utf-8", "replace"))
                elif isinstance(ch, (np.bytes_, np.str_)):
                    chars.append(bytes(ch).decode("utf-8", "replace") if isinstance(ch, np.bytes_) else str(ch))
                else:
                    chars.append(str(ch))
            names.append("".join(chars).replace("\x00", "").strip())
        while len(names) < n:
            names.append(f"station_{len(names)+1}")
        return names
    if arr.dtype.kind in {"U", "S", "O"}:
        flat = np.atleast_1d(arr)
        for i in range(n):
            if i >= flat.shape[0]:
                names.append(f"station_{i+1}")
                continue
            value = flat[i]
            if isinstance(value, bytes):
                names.append(value.decode("utf-8", "replace").replace("\x00", "").strip())
            else:
                names.append(str(value).replace("\x00", "").strip())
        return names
    return [f"station_{i+1}" for i in range(n)]


def _as_1d_positions(var, n_station: int, n_time: int) -> np.ndarray:
    arr = np.asarray(var[:], dtype=np.float64)
    if arr.ndim == 0:
        return np.full(n_station, float(arr), dtype=np.float64)
    if arr.ndim == 1:
        if arr.size == n_station:
            return arr.astype(np.float64, copy=False)
        if arr.size == 1:
            return np.full(n_station, float(arr[0]), dtype=np.float64)
    if arr.ndim == 2:
        # (time, station) or (station, time)
        if arr.shape[1] == n_station:
            first = arr[0]
            if n_time > 1 and not np.allclose(arr, first, equal_nan=True):
                raise BoundaryError(
                    "BOUNDARY_SOURCE_MISSING",
                    "站点位置随时间变化，首版不支持移动站点",
                    context={"shape": list(arr.shape)},
                )
            return np.asarray(first, dtype=np.float64)
        if arr.shape[0] == n_station:
            first = arr[:, 0]
            if arr.shape[1] > 1 and not np.allclose(arr, first[:, None], equal_nan=True):
                raise BoundaryError(
                    "BOUNDARY_SOURCE_MISSING",
                    "站点位置随时间变化，首版不支持移动站点",
                    context={"shape": list(arr.shape)},
                )
            return np.asarray(first, dtype=np.float64)
    raise BoundaryError(
        "BOUNDARY_SOURCE_MISSING",
        "无法识别站点经纬度布局",
        context={"shape": list(np.asarray(var[:]).shape)},
    )


def _efth_layout(dims: tuple[str, ...]) -> str:
    lower = tuple(d.lower() for d in dims)
    if len(lower) < 4:
        raise BoundaryError(
            "BOUNDARY_SOURCE_MISSING",
            "efth 不是完整二维谱（需要 time、station、frequency、direction）",
            context={"dims": list(dims)},
        )
    has_time = any(d in lower for d in ("time",))
    has_station = any("station" in d or d in {"site", "point"} for d in lower)
    has_freq = any(d in lower for d in ("frequency", "freq", "f"))
    has_dir = any(d in lower for d in ("direction", "dir", "theta"))
    if not (has_time and has_freq and has_dir):
        raise BoundaryError(
            "BOUNDARY_SOURCE_MISSING",
            "efth 缺少 time/frequency/direction 维",
            context={"dims": list(dims)},
        )
    if lower[0] in {"time"} and has_station:
        return "time,station,frequency,direction"
    if has_station and lower[0] not in {"time"}:
        return "station,time,frequency,direction"
    if not has_station and lower[0] == "time":
        return "time,station,frequency,direction"
    return ",".join(lower)


def inspect_spectra_file(path: str | Path) -> SpectraFileMeta:
    """只读元数据与站点坐标，不载入全部谱值。"""
    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise BoundaryError(
            "BOUNDARY_SOURCE_MISSING",
            f"谱文件不存在：{file_path}",
            context={"path": str(file_path)},
        )
    with serialized_dataset(str(file_path), "r") as ds:
        time_var = _first_var(ds, _TIME_NAMES)
        freq_var = _first_var(ds, _FREQ_NAMES)
        dir_var = _first_var(ds, _DIR_NAMES)
        efth_var = _first_var(ds, _EFTH_NAMES)
        lon_var = _first_var(ds, _LON_NAMES)
        lat_var = _first_var(ds, _LAT_NAMES)
        missing = [
            label
            for label, var in (
                ("time", time_var),
                ("frequency", freq_var),
                ("direction", dir_var),
                ("efth", efth_var),
                ("longitude", lon_var),
                ("latitude", lat_var),
            )
            if var is None
        ]
        if missing:
            extra = ""
            names = list(ds.variables)
            if any("swh" in n.lower() or "hs" == n.lower() for n in names) and efth_var is None:
                extra = "；文件像是波高/周期产品，缺少二维谱 efth"
            raise BoundaryError(
                "BOUNDARY_SOURCE_MISSING",
                f"谱文件缺少必需变量：{', '.join(missing)}{extra}",
                context={"path": str(file_path), "missing": missing, "variables": names},
            )
        times = _decode_times(time_var)
        freqs = np.asarray(freq_var[:], dtype=np.float64).reshape(-1)
        dirs = np.asarray(dir_var[:], dtype=np.float64).reshape(-1)
        dir_units = str(getattr(dir_var, "units", "") or "")
        if "rad" in dir_units.lower() and "deg" not in dir_units.lower():
            dirs = np.degrees(dirs)
            dir_units = "degree"
        layout = _efth_layout(tuple(efth_var.dimensions))
        dims = {d.lower(): len(ds.dimensions[d]) for d in efth_var.dimensions if d in ds.dimensions}
        n_time = len(times)
        n_freq = int(freqs.size)
        n_dir = int(dirs.size)
        n_station = 1
        for dim_name, size in zip(efth_var.dimensions, efth_var.shape):
            key = dim_name.lower()
            if key in {"time"} or key.startswith("time"):
                n_time = int(size)
            elif "station" in key or key in {"site", "point"}:
                n_station = int(size)
            elif key in {"frequency", "freq", "f"}:
                n_freq = int(size)
            elif key in {"direction", "dir", "theta"}:
                n_dir = int(size)
        if n_station == 1 and "station" not in ",".join(efth_var.dimensions).lower():
            # 单站点文件可以没有 station 维
            n_station = 1
        lons = _as_1d_positions(lon_var, n_station, n_time)
        lats = _as_1d_positions(lat_var, n_station, n_time)
        name_var = _first_var(ds, _NAME_NAMES)
        if name_var is not None:
            names = _decode_names(name_var, n_station)
        else:
            names = [f"station_{i+1}" for i in range(n_station)]
        stations: list[BoundaryStation] = []
        for i in range(n_station):
            stations.append(
                BoundaryStation(
                    source_id="",
                    name=names[i] or f"station_{i+1}",
                    lon=float(lons[i]),
                    lat=float(lats[i]),
                    file_paths=[str(file_path)],
                )
            )
        iso = [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in times]
        return SpectraFileMeta(
            path=str(file_path),
            n_stations=n_station,
            n_times=n_time,
            n_freq=n_freq,
            n_dir=n_dir,
            time_start=iso[0] if iso else None,
            time_end=iso[-1] if iso else None,
            times=times,
            stations=stations,
            frequencies_hz=freqs,
            directions_deg=dirs,
            efth_dims=tuple(efth_var.dimensions),
            freq_units=str(getattr(freq_var, "units", "") or ""),
            dir_units=dir_units,
            efth_units=str(getattr(efth_var, "units", "") or ""),
            dir_long_name=str(getattr(dir_var, "long_name", "") or ""),
            dir_standard_name=str(getattr(dir_var, "standard_name", "") or ""),
            layout=layout,
        )


def _efth_axis_map(dims: tuple[str, ...]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for i, name in enumerate(dims):
        n = name.lower()
        if n in {"time"} or n.startswith("time"):
            mapping["time"] = i
        elif "station" in n or n in {"site", "point"}:
            mapping["station"] = i
        elif n in {"frequency", "freq", "f"}:
            mapping["freq"] = i
        elif n in {"direction", "dir", "theta"}:
            mapping["dir"] = i
    return mapping


def _reject_missing_efth(raw, var) -> np.ndarray:
    """保留 NetCDF 缺测掩码；填充值不得当作谱能量。"""
    ma = np.ma.array(raw, copy=False)
    mask = np.ma.getmaskarray(ma)
    if np.any(mask):
        n_bad = int(np.count_nonzero(mask))
        raise BoundaryError(
            "BOUNDARY_INVALID_SPECTRA",
            f"谱值含缺测（{n_bad} 个）",
            context={"n_invalid": n_bad, "variable": getattr(var, "name", "efth")},
        )
    arr = np.array(np.ma.filled(ma, np.nan), dtype=np.float64)
    fill = getattr(var, "_FillValue", None)
    if fill is None:
        fill = getattr(var, "missing_value", None)
    if fill is not None:
        try:
            fv = np.float64(fill)
        except (TypeError, ValueError):
            fv = np.nan
        if np.isfinite(fv) and np.any(arr == fv):
            n_bad = int(np.count_nonzero(arr == fv))
            raise BoundaryError(
                "BOUNDARY_INVALID_SPECTRA",
                f"谱值含未解码填充值（{n_bad} 个）",
                context={"n_invalid": n_bad, "fill_value": float(fv)},
            )
    if not np.isfinite(arr).all():
        n_bad = int(np.size(arr) - np.isfinite(arr).sum())
        raise BoundaryError(
            "BOUNDARY_INVALID_SPECTRA",
            f"谱值含非有限值（{n_bad} 个）",
            context={"n_invalid": n_bad},
        )
    return arr


def read_station_efth(
    path: str | Path,
    station_index: int,
    *,
    time_slice: slice | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """读取一个站点的 efth，返回 (time, freq, dir, efth[time,freq,dir])。

    只切片该站点（及可选时段），禁止先把整份多站点文件载入内存。
    """
    file_path = Path(path).expanduser()
    with serialized_dataset(str(file_path), "r") as ds:
        efth_var = _first_var(ds, _EFTH_NAMES)
        freq_var = _first_var(ds, _FREQ_NAMES)
        dir_var = _first_var(ds, _DIR_NAMES)
        time_var = _first_var(ds, _TIME_NAMES)
        if efth_var is None or freq_var is None or dir_var is None or time_var is None:
            raise BoundaryError("BOUNDARY_SOURCE_MISSING", f"无法读取谱值：{file_path}")
        dims = tuple(d.lower() for d in efth_var.dimensions)
        ndim = len(efth_var.dimensions)
        mapping = _efth_axis_map(dims)
        if "time" not in mapping or "freq" not in mapping or "dir" not in mapping:
            raise BoundaryError(
                "BOUNDARY_SOURCE_MISSING",
                "efth 维度无法识别为 time/station/frequency/direction",
                context={"dims": list(efth_var.dimensions)},
            )
        has_station = "station" in mapping
        if has_station:
            n_station = int(efth_var.shape[mapping["station"]])
        else:
            n_station = 1
        if station_index < 0 or station_index >= n_station:
            raise BoundaryError(
                "BOUNDARY_SOURCE_MISSING",
                f"站点索引 {station_index} 超出范围",
                context={"path": str(file_path), "n_station": n_station},
            )
        indexers: list = [slice(None)] * ndim
        if has_station:
            indexers[mapping["station"]] = int(station_index)
        if time_slice is not None:
            indexers[mapping["time"]] = time_slice
        raw = efth_var[tuple(indexers)]
        data = _reject_missing_efth(raw, efth_var)
        dropped = [mapping["station"]] if has_station else []

        def remaining_axis(orig: int) -> int:
            return orig - sum(1 for d in dropped if d < orig)

        try:
            data = np.transpose(
                data,
                [
                    remaining_axis(mapping["time"]),
                    remaining_axis(mapping["freq"]),
                    remaining_axis(mapping["dir"]),
                ],
            )
        except Exception as exc:
            raise BoundaryError(
                "BOUNDARY_SOURCE_MISSING",
                "切片后 efth 不是 time/frequency/direction",
                context={"shape": list(np.shape(data)), "dims": list(efth_var.dimensions)},
            ) from exc
        if data.ndim != 3:
            raise BoundaryError(
                "BOUNDARY_SOURCE_MISSING",
                "切片后 efth 不是 time/frequency/direction",
                context={"shape": list(data.shape), "dims": list(efth_var.dimensions)},
            )
        freqs = np.asarray(freq_var[:], dtype=np.float64).reshape(-1)
        dirs = np.asarray(dir_var[:], dtype=np.float64).reshape(-1)
        dir_units = str(getattr(dir_var, "units", "") or "")
        if "rad" in dir_units.lower() and "deg" not in dir_units.lower():
            dirs = np.degrees(dirs)
        times = _decode_times(time_var)
        if time_slice is not None:
            times = list(times)[time_slice]
        return np.array(times, dtype=object), freqs, dirs, np.asarray(data, dtype=np.float64)


def assign_source_ids(stations: list[BoundaryStation]) -> list[BoundaryStation]:
    """为站点分配可追溯 ID；同名异址报错；同址且待合并时保留各自 ID。"""
    by_name: dict[str, list[BoundaryStation]] = {}
    for station in stations:
        by_name.setdefault(station.name, []).append(station)
    for name, group in by_name.items():
        coords = {(round(s.lon, 6), round(s.lat, 6)) for s in group}
        if len(coords) > 1:
            raise BoundaryError(
                "BOUNDARY_DUPLICATE_CONFLICT",
                f"站名 {name!r} 对应多个不同位置，禁止静默合并",
                context={
                    "name": name,
                    "locations": [{"lon": s.lon, "lat": s.lat, "files": s.file_paths} for s in group],
                },
            )
    out: list[BoundaryStation] = []
    used: dict[tuple[str, float, float], int] = {}
    seq = 1
    for station in stations:
        key = (station.name, round(station.lon, 6), round(station.lat, 6))
        if key not in used:
            used[key] = seq
            seq += 1
        ident = f"src_{used[key]:06d}"
        out.append(
            BoundaryStation(
                source_id=ident,
                name=station.name,
                lon=station.lon,
                lat=station.lat,
                file_paths=list(station.file_paths),
            )
        )
    return out
