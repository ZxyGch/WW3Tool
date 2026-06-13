"""绘图 Worker 公共辅助函数（无 GUI 依赖）。

[EN] Plotting Worker common helper functions (no GUI dependency).

提供 WW3 NetCDF 输出文件的坐标解析、点序列/结构化网格判定、有效波高展平、
三角网连通性读取、matplotlib 三角填色图清理，以及谱图站点名解码等通用工具。
被 ``jason3_worker``、``wave_map_worker``、``spectrum_worker`` 等模块复用。

[EN] Provides coordinate parsing, pointwise/structured grid detection, significant wave height
flattening, triangle mesh connectivity reading, matplotlib tricontourf cleanup, and spectral
station name decoding for WW3 NetCDF output files. Reused by ``jason3_worker``,
``wave_map_worker``, ``spectrum_worker``, and other modules.
"""
import numpy as np


def remove_tricontourf_artist(tcf):
    """移除上一帧 ``tricontourf`` / ``tricontour`` 的绘图结果。

    [EN] Remove the previous frame's ``tricontourf`` / ``tricontour`` drawing result.

    matplotlib 3.8+ 中 ``TriContourSet`` 可能不再暴露 ``.collections``，应优先用 ``.remove()``。

    [EN] In matplotlib 3.8+, ``TriContourSet`` may no longer expose ``.collections``;
    prefer ``.remove()`` instead.
    """
    if tcf is None:
        return
    cols = getattr(tcf, "collections", None)
    if cols is None:
        cols = getattr(tcf, "_collections", None)
    if cols is not None:
        for c in list(cols):
            try:
                if c is not None and hasattr(c, "remove"):
                    c.remove()
            except Exception:
                pass
        return
    rem = getattr(tcf, "remove", None)
    if callable(rem):
        try:
            rem()
        except Exception:
            pass


def ww3_resolve_lon_lat_names(ds):
    """从 NetCDF 中解析经度/纬度变量名（WW3 非结构场可能仍为 longitude/latitude，也可能为 lon/lat）。

    [EN] Resolve longitude/latitude variable names from NetCDF (WW3 unstructured fields may use
    longitude/latitude or lon/lat).
    """
    keys = set(ds.variables.keys())
    lon_candidates = (
        "longitude",
        "lon",
        "LONGITUDE",
        "LON",
        "Longitude",
        "x_lam",
    )
    lat_candidates = (
        "latitude",
        "lat",
        "LATITUDE",
        "LAT",
        "Latitude",
        "y_phi",
    )
    lon_name = next((c for c in lon_candidates if c in keys), None)
    lat_name = next((c for c in lat_candidates if c in keys), None)
    return lon_name, lat_name


def ww3_prepare_lon_lat_1d(lon, lat, nt_time):
    """将坐标压成与场变量一致的 1D 节点序列。

    [EN] Squeeze coordinates into a 1D node sequence consistent with the field variable.
    """
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    lon = np.squeeze(lon)
    lat = np.squeeze(lat)
    if lon.ndim == 1 and lat.ndim == 1:
        return lon, lat
    if lon.shape != lat.shape:
        raise ValueError("longitude and latitude shape mismatch")
    if lon.ndim == 2:
        r, c = lon.shape
        if nt_time is not None:
            if r == nt_time and c != nt_time:
                return lon[0].ravel(), lat[0].ravel()
            if c == nt_time and r != nt_time:
                return lon[:, 0].ravel(), lat[:, 0].ravel()
            if r == nt_time == c:
                return lon[0].ravel(), lat[0].ravel()
        return lon.ravel(), lat.ravel()
    return lon.ravel(), lat.ravel()


def ww3_try_pointwise_timeseries(raw, nt, n_nodes):
    """若 raw 为点序列场 (time×node 或 node×time)，返回形状 (nt, n_nodes) 的数组，否则 None。

    [EN] If raw is a pointwise field (time x node or node x time), return an array of shape (nt, n_nodes); otherwise None.
    """
    a = np.asarray(raw, dtype=float)
    a = np.squeeze(a)
    if a.ndim != 2 or nt <= 0 or n_nodes <= 0:
        return None
    s0, s1 = a.shape
    if s0 == nt and s1 == n_nodes:
        return a
    if s1 == nt and s0 == n_nodes:
        return a.T
    return None


def ww3_is_pointwise_grid(lon1d, lat1d, raw, nt):
    """判断是否为单索引网格（非结构三角形节点、SMC seapoint 等）。

    [EN] Determine if this is a single-index grid (unstructured triangle nodes, SMC seapoints, etc.).
    """
    lon1d = np.asarray(lon1d).ravel()
    lat1d = np.asarray(lat1d).ravel()
    if lon1d.ndim != 1 or lat1d.ndim != 1 or len(lon1d) != len(lat1d):
        return False, None
    n = len(lon1d)
    Hs = ww3_try_pointwise_timeseries(raw, nt, n)
    if Hs is None:
        return False, None
    return True, Hs


def ww3_swh_to_float_array(arr):
    """NetCDF / numpy masked → float ndarray，缺测填 nan。

    [EN] Convert NetCDF / numpy masked array to float ndarray, filling missing values with NaN.
    """
    if arr is None:
        return None
    a = np.asanyarray(arr)
    if isinstance(a, np.ma.MaskedArray):
        return np.ma.filled(a.astype(np.float64), np.nan)
    return np.asarray(a, dtype=np.float64)


def ww3_hs_collocation_flat(nt, lon, lat, swh_raw):
    """为 Jason 等卫星逐点匹配准备展平场：每时刻一行 ``hs[t, :]``，与 ``lon1/lat1`` 同序。

    [EN] Prepare a flattened field for satellite point-by-point matching (e.g. Jason):
    one row per timestep ``hs[t, :]``, in the same order as ``lon1/lat1``.
    """
    if nt <= 0:
        raise ValueError("nt must be positive")
    swh = ww3_swh_to_float_array(swh_raw)
    lon = np.asarray(lon, dtype=np.float64)
    lat = np.asarray(lat, dtype=np.float64)
    lon, lat = ww3_prepare_lon_lat_1d(lon, lat, nt)
    is_pw, hs_pw = ww3_is_pointwise_grid(lon, lat, swh, nt)
    if is_pw:
        lon1 = np.asarray(lon, dtype=np.float64).ravel()
        lat1 = np.asarray(lat, dtype=np.float64).ravel()
        hs_nt_n = np.asarray(hs_pw, dtype=np.float64)
        lon_lat = [
            float(np.nanmin(lon1)),
            float(np.nanmax(lon1)),
            float(np.nanmin(lat1)),
            float(np.nanmax(lat1)),
        ]
        if hs_nt_n.shape != (nt, len(lon1)):
            raise ValueError(f"pointwise hs shape {hs_nt_n.shape} != ({nt}, {len(lon1)})")
        return lon1, lat1, hs_nt_n, lon_lat

    lon = np.asarray(lon).squeeze()
    lat = np.asarray(lat).squeeze()
    if lon.ndim != 1 or lat.ndim != 1:
        raise ValueError("structured WW3 grid expects 1-D longitude and latitude")
    nx, ny = len(lon), len(lat)
    lon_grid, lat_grid = np.meshgrid(lon, lat, indexing="xy")
    lon1 = lon_grid.ravel().astype(np.float64)
    lat1 = lat_grid.ravel().astype(np.float64)
    lon_lat = [float(lon.min()), float(lon.max()), float(lat.min()), float(lat.max())]
    raw = np.asarray(swh, dtype=np.float64)
    raw = np.squeeze(raw)
    if raw.ndim != 3:
        raise ValueError(
            f"expected 3-D hs for structured grid (got ndim={raw.ndim}, shape={raw.shape}); "
            "for unstructured output use 2-D (time, node)"
        )
    shape = raw.shape
    time_axes = [i for i, s in enumerate(shape) if s == nt]
    time_axis = time_axes[0] if time_axes else 2
    if time_axis == 0:
        hs_w = raw.transpose(1, 2, 0)
    elif time_axis == 1:
        hs_w = raw.transpose(0, 2, 1)
    elif time_axis == 2:
        if raw.shape[:2] == (ny, nx):
            hs_w = raw
        elif raw.shape[:2] == (nx, ny):
            hs_w = raw.transpose(1, 0, 2)
        else:
            hs_w = raw.transpose(1, 0, 2)
    else:
        hs_w = raw
    if hs_w.ndim != 3 or hs_w.shape[2] != nt:
        raise ValueError(
            f"time dimension mismatch: nt={nt}, raw.shape={raw.shape}, hs_w.shape={getattr(hs_w, 'shape', None)}"
        )
    nsp = hs_w.shape[0] * hs_w.shape[1]
    if nsp != len(lon1):
        raise ValueError(
            f"hs grid size {nsp} ({hs_w.shape[0]}×{hs_w.shape[1]}) != mesh size {len(lon1)} (ny={ny}, nx={nx})"
        )
    hs_nt_n = np.moveaxis(hs_w, 2, 0).reshape(nt, nsp)
    return lon1, lat1, hs_nt_n, lon_lat


def ww3_try_mesh_triangles(ds, n_nodes):
    """尝试读取三角网连通性 (nelem, 3)，节点索引 0-based。

    [EN] Attempt to read triangle mesh connectivity (nelem, 3), with 0-based node indices.
    """
    if n_nodes <= 0:
        return None
    hinted = (
        "iknt",
        "tricc",
        "triangle",
        "tri",
        "nv",
        "elem",
        "element",
        "cells",
        "face",
    )
    ordered = []
    for name, v in ds.variables.items():
        if len(v.dimensions) != 2:
            continue
        lname = name.lower()
        pri = 0 if any(h in lname for h in hinted) else 1
        ordered.append((pri, name, v))
    ordered.sort(key=lambda x: (x[0], x[1]))
    for _pri, _name, v in ordered:
        sh = v.shape
        if 3 not in sh:
            continue
        try:
            data = np.asarray(v[:], dtype=np.int64)
        except Exception:
            continue
        if sh[0] == 3 and sh[1] > 3:
            tri = data.T
        elif sh[1] == 3 and sh[0] > 3:
            tri = data
        else:
            continue
        if tri.size == 0:
            continue
        tmin = int(np.min(tri))
        tmax = int(np.max(tri))
        if tmin >= 1 and tmax <= n_nodes:
            tri = tri - 1
        elif tmin < 0 or tmax >= n_nodes:
            continue
        if np.min(tri) < 0 or np.max(tri) >= n_nodes:
            continue
        return tri
    return None


def _pick_station_lon_lat(lon, lat, station_index, n_station=None):
    """从多种维序的经纬度数组中稳健提取指定站点的 (lon, lat)。

    [EN] Robustly extract the specified station's (lon, lat) from lat/lon arrays with various dimension orderings.

    兼容 0 维标量、1 维站点序列及高维数组（站点维可能在首维或末维）。

    [EN] Compatible with 0-D scalars, 1-D station sequences, and higher-dimensional arrays
    (station dimension may be first or last).
    """
    lon_arr = np.array(lon)
    lat_arr = np.array(lat)

    if lon_arr.ndim == 0:
        return float(lon_arr), float(lat_arr)

    if lon_arr.ndim == 1:
        return float(lon_arr[station_index]), float(lat_arr[station_index])

    if n_station is not None:
        if lon_arr.shape[0] == n_station:
            return float(lon_arr[station_index].reshape(-1)[0]), float(lat_arr[station_index].reshape(-1)[0])
        if lon_arr.shape[-1] == n_station:
            idx = (0,) * (lon_arr.ndim - 1) + (station_index,)
            return float(lon_arr[idx]), float(lat_arr[idx])

    if lon_arr.shape[-1] > station_index:
        idx = (0,) * (lon_arr.ndim - 1) + (station_index,)
        return float(lon_arr[idx]), float(lat_arr[idx])

    flat_idx = min(station_index, lon_arr.size - 1)
    return float(lon_arr.reshape(-1)[flat_idx]), float(lat_arr.reshape(-1)[flat_idx])


def _decode_station_names(station_name_var, n_station):
    """将 NetCDF ``station_name`` 变量解码为长度为 ``n_station`` 的字符串列表。

    [EN] Decode the NetCDF ``station_name`` variable into a string list of length ``n_station``.

    支持字符数组、字节串及整型 ASCII 编码等多种 WW3 谱输出命名格式。

    [EN] Supports character arrays, byte strings, and integer ASCII encoding among other
    WW3 spectral output naming formats.
    """
    if station_name_var is None:
        return None
    try:
        raw = np.array(station_name_var)
        if raw.ndim == 1:
            names = [str(item) for item in raw.tolist()]
        elif raw.ndim >= 2:
            names = []
            for row in raw[:n_station]:
                if row.dtype.kind in ("S", "U"):
                    if row.dtype.kind == "S":
                        name = b"".join(row.tolist()).decode("utf-8", "ignore").strip()
                    else:
                        name = "".join([str(x) for x in row.tolist()]).strip()
                else:
                    name = "".join([chr(int(x)) for x in row.tolist() if int(x) != 0]).strip()
                names.append(name)
        else:
            names = []
        cleaned = []
        for i in range(n_station):
            value = names[i].replace("\x00", "").strip() if i < len(names) else ""
            cleaned.append(value)
        return cleaned
    except Exception:
        return None
