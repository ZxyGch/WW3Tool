"""
绘图 Worker 公共辅助函数
"""
import numpy as np


def _pick_station_lon_lat(lon, lat, station_index, n_station=None):
    """Pick station lon/lat robustly across dim orders."""
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
    """Decode station_name variable to list of strings."""
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
