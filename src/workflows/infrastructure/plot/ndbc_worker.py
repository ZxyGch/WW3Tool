"""NDBC 浮标观测对比 Worker — WW3 模式结果与 NOAA NDBC 站点数据匹配与下载。

在独立子进程中读取 WW3 输出、解析/下载 NDBC stdmet 或 realtime 观测，
按空间距离与时间窗口匹配有效波高，生成时间序列对比图与统计指标。
纯 Python 实现，无 GUI 依赖。

[EN] [EN] NDBC buoy observation comparison worker — match and download NOAA NDBC station data against WW3 model results.

Reads WW3 output in a separate subprocess, parses/downloads NDBC stdmet or realtime observations, matches significant wave height by spatial distance and time window, and generates time-series comparison plots and statistics.
Pure Python implementation, no GUI dependency.
"""

import glob
import json
import os
import platform
import warnings
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from multiprocessing import Process, Queue

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import requests
from matplotlib import font_manager
from netCDF4 import Dataset, num2date

from ..runtime_config import load_config
from ...support.translations import tr


NDBC_ACTIVE_STATIONS_URL = "https://www.ndbc.noaa.gov/activestations.xml"
NDBC_HISTORICAL_STDMET_BASE_URL = "https://www.ndbc.noaa.gov/data/historical/stdmet/"
NDBC_REALTIME_BASE_URL = "https://www.ndbc.noaa.gov/data/realtime2/"
NDBC_REQUEST_TIMEOUT = (20, 120)
NDBC_REALTIME_LOOKBACK_DAYS = 45


def _ndbc_log(log_queue, message, update=False):
    
    # [EN] [EN] Send an NDBC worker message to the log queue; use an in-place update prefix when ``update=True``.
    """向日志队列发送 NDBC Worker 消息；``update=True`` 时使用原地更新前缀。"""
    try:
        if update:
            log_queue.put(("__UPDATE__", message))
        else:
            log_queue.put(message)
    except Exception:
        pass


def _configure_ndbc_map_fonts():
    
    # [EN] [EN] Prefer an available Chinese font for NDBC maps to reduce cartopy/matplotlib missing-glyph warnings.
    """为 NDBC 地图优先选择可用中文字体，减少 cartopy/matplotlib 缺字告警。"""
    try:
        system = platform.system()
        if system == "Windows":
            candidates = ["Microsoft YaHei", "SimHei", "SimSun", "KaiTi"]
        elif system == "Darwin":
            candidates = ["PingFang SC", "STHeiti", "Arial Unicode MS", "Heiti SC"]
        else:
            candidates = ["WenQuanYi Micro Hei", "WenQuanYi Zen Hei", "Noto Sans CJK SC", "Droid Sans Fallback"]

        available_fonts = {font.name for font in font_manager.fontManager.ttflist}
        chosen = next((font for font in candidates if font in available_fonts), None)
        if chosen:
            plt.rcParams["font.sans-serif"] = [chosen]
            plt.rcParams["axes.unicode_minus"] = False
        else:
            warnings.filterwarnings("ignore", category=UserWarning, module="cartopy")
    except Exception:
        warnings.filterwarnings("ignore", category=UserWarning, module="cartopy")


def _ndbc_haversine_distance(lat1, lon1, lat2, lon2):
    
    # [EN] [EN] Compute the great-circle distance between two points and convert it to approximate degrees of longitude (used as spatial matching threshold).
    """计算两点间大圆距离并转换为近似经度度数（用于空间匹配阈值）。"""
    lat1_rad = np.radians(lat1)
    lon1_rad = np.radians(lon1)
    lat2_rad = np.radians(lat2)
    lon2_rad = np.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    return (6371.0 * c) / 111.0


def _parse_ndbc_time_range(time_range):
    
    # [EN] [EN] Parse a ``(YYYYMMDD, YYYYMMDD)`` tuple into start/end ``datetime`` objects.
    """将 ``(YYYYMMDD, YYYYMMDD)`` 元组解析为 ``datetime`` 起止对象。"""
    start_str, end_str = time_range
    start_dt = datetime.strptime(start_str, "%Y%m%d")
    end_dt = datetime.strptime(end_str, "%Y%m%d")
    return start_dt, end_dt


def _find_ndbc_metadata_file(local_folder, time_range):
    
    # [EN] [EN] Find NDBC station metadata JSON in the local folder (exact match or latest ``ndbc_stations_*.json``).
    """在本地目录查找 NDBC 站点元数据 JSON（精确匹配或最新 ``ndbc_stations_*.json``）。"""
    exact_path = os.path.join(local_folder, f"ndbc_stations_{time_range[0]}_{time_range[1]}.json")
    if os.path.exists(exact_path):
        return exact_path
    pattern = os.path.join(local_folder, "ndbc_stations_*.json")
    matches = sorted(glob.glob(pattern), reverse=True)
    return matches[0] if matches else None


def _load_ndbc_stations_from_folder(local_folder, lon_lat, time_range):
    
    # [EN] [EN] Load the list of NDBC stations in the specified region (prefer local cache, otherwise request NOAA active-stations XML).
    """加载指定区域内的 NDBC 站点列表（优先本地缓存，否则请求 NOAA 活跃站点 XML）。"""
    if local_folder and os.path.isdir(local_folder):
        metadata_path = _find_ndbc_metadata_file(local_folder, time_range)
        if metadata_path:
            try:
                with open(metadata_path, "r", encoding="utf-8") as file_obj:
                    stations = json.load(file_obj)
                filtered = _filter_ndbc_stations(stations, lon_lat)
                if filtered:
                    return filtered
            except Exception:
                pass

        pattern = os.path.join(local_folder, "ndbc_stations_*.json")
        for path in sorted(glob.glob(pattern), reverse=True):
            try:
                with open(path, "r", encoding="utf-8") as file_obj:
                    stations = json.load(file_obj)
                filtered = _filter_ndbc_stations(stations, lon_lat)
                if filtered:
                    return filtered
            except Exception:
                continue

    response = requests.get(NDBC_ACTIVE_STATIONS_URL, timeout=NDBC_REQUEST_TIMEOUT)
    response.raise_for_status()
    stations = _parse_ndbc_station_elements(response.content)
    return _filter_ndbc_stations(stations, lon_lat)


def _parse_ndbc_station_file(file_path, start_dt, end_dt):
    
    # [EN] [EN] Parse NDBC stdmet text/compressed file and extract WVHT (significant wave height) observations within the time window.
    """解析 NDBC stdmet 文本/压缩文件，提取时间窗内的 WVHT（有效波高）观测序列。"""
    import gzip

    open_func = gzip.open if file_path.endswith(".gz") else open
    valid_missing = {"99", "99.0", "99.00", "999", "999.0", "999.00", "9999", "9999.0", "MM"}
    observations = []
    header = None

    with open_func(file_path, "rt", encoding="utf-8", errors="ignore") as file_obj:
        for raw_line in file_obj:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#YY"):
                header = line.split()
                continue
            if line.startswith("#") or not header:
                continue

            parts = line.split()
            if len(parts) < len(header):
                continue

            row = dict(zip(header, parts))
            wvht_str = row.get("WVHT", "")
            if wvht_str in valid_missing:
                continue

            try:
                obs_time = datetime(
                    int(row["#YY"]),
                    int(row["MM"]),
                    int(row["DD"]),
                    int(row["hh"]),
                    int(row["mm"]),
                )
                wvht_val = float(wvht_str)
            except Exception:
                continue

            if not (start_dt <= obs_time <= end_dt):
                continue
            if not np.isfinite(wvht_val) or wvht_val <= 0 or wvht_val > 30:
                continue

            observations.append((obs_time, wvht_val))

    return observations


def _match_ww3_ndbc_worker(
    ww3_file,
    ndbc_folder,
    out_folder,
    lon_lat,
    time_range,
    log_queue,
    result_queue,
    max_dist_deg=0.25,
    time_window_minutes=30,
):
    """在子进程中执行 WW3 与 NDBC 浮标 SWH 时空匹配、统计与对比图生成。

    读取 WW3 输出 NetCDF，加载区域内 NDBC 站点观测，按距离与时间窗配对，
    计算 bias/RMSE/相关系数并保存时间序列对比图。
    
    [EN] [EN] Perform WW3 and NDBC buoy SWH space-time matching, statistics and comparison-plot generation in a subprocess.
    
    Reads WW3 output NetCDF, loads NDBC station observations in the region, pairs them by distance and time window, computes bias/RMSE/correlation, and saves time-series comparison plots.
    """
    try:
        from .workers_utils import ww3_hs_collocation_flat, ww3_resolve_lon_lat_names

        def log(message):
            try:
                log_queue.put(message)
            except Exception:
                pass

        log(tr("plotting_start_matching_ndbc", "🔄 开始匹配 WW3 和 NDBC 数据（在子进程中执行，这可能需要一些时间，请稍候...）"))
        log("Reading WW3 data...")

        with Dataset(ww3_file, "r") as nc:
            available_vars = list(nc.variables.keys())
            lon_name, lat_name = ww3_resolve_lon_lat_names(nc)
            if not lon_name or not lat_name:
                log(
                    tr(
                        "plotting_missing_lon_lat_variables",
                        "❌ 无法识别经度/纬度变量（需 longitude/lon、latitude/lat 等）。可用变量: {vars}",
                    ).format(vars=", ".join(available_vars))
                )
                result_queue.put(None)
                log_queue.put("__DONE__")
                return

            ww3_lon = nc.variables[lon_name][:]
            ww3_lat = nc.variables[lat_name][:]
            ww3_time_var = nc.variables["time"]
            time_ww3 = ww3_time_var[:].astype(float)

            wave_height_var = None
            for var_name in ["hs", "swh", "wave_height", "HS", "SWH"]:
                if var_name in nc.variables:
                    wave_height_var = var_name
                    break
            if wave_height_var is None:
                log(
                    tr(
                        "plotting_missing_hs_variable_jason",
                        "❌ 文件中没有找到波高变量（尝试了: {tried}）。可用变量: {vars}",
                    ).format(tried=", ".join(["hs", "swh", "wave_height", "HS", "SWH"]), vars=", ".join(available_vars))
                )
                result_queue.put(None)
                log_queue.put("__DONE__")
                return
            ww3_swh = nc.variables[wave_height_var][:]

        ww3_lon = np.asarray(ww3_lon, dtype=float)
        ww3_lat = np.asarray(ww3_lat, dtype=float)
        ww3_lon = ((ww3_lon + 180.0) % 360.0) - 180.0

        nt = len(time_ww3)
        lon1, lat1, hs_nt_n, ww3_bounds = ww3_hs_collocation_flat(nt, ww3_lon, ww3_lat, ww3_swh)
        hs_nt_n = np.asarray(hs_nt_n, dtype=float)
        hs_nt_n[(hs_nt_n < 0) | (hs_nt_n > 50)] = np.nan

        _units = getattr(ww3_time_var, 'units', 'days since 1990-01-01')
        _cal = getattr(ww3_time_var, 'calendar', 'standard')
        _decoded = num2date(time_ww3, _units, calendar=_cal,
                            only_use_cftime_datetimes=False, only_use_python_datetimes=False)
        ww3_times = np.array([
            datetime(dt.year, dt.month, dt.day,
                     getattr(dt, "hour", 0), getattr(dt, "minute", 0),
                     getattr(dt, "second", 0))
            for dt in _decoded
        ], dtype=object)

        log(f"WW3 lon range: [{ww3_bounds[0]:.2f}, {ww3_bounds[1]:.2f}]")
        log(f"WW3 lat range: [{ww3_bounds[2]:.2f}, {ww3_bounds[3]:.2f}]")
        log(f"WW3 time steps: {len(ww3_times)}")
        log(f"WW3 collocation points per step: {hs_nt_n.shape[1]}")
        log(f"WW3 time range: {ww3_times[0]} to {ww3_times[-1]}")

        start_dt, end_dt = _parse_ndbc_time_range(time_range)
        end_dt = end_dt + timedelta(hours=23, minutes=59, seconds=59)

        stations = _load_ndbc_stations_from_folder(ndbc_folder, lon_lat, time_range)
        if not stations:
            log(tr("plotting_ndbc_no_station_in_range", "⚠️ 当前经纬度范围内没有找到 NDBC 活跃站点。"))
            result_queue.put({"bias": None, "rmse": None, "corr": None, "count": 0})
            log_queue.put("__DONE__")
            return

        log(tr("plotting_ndbc_station_selected", "✅ 范围内找到 {count} 个 NDBC 站点").format(count=len(stations)))

        matched_ndbc = []
        matched_ww3 = []
        matched_station_ids = []
        station_match_count = 0
        max_time_delta = timedelta(minutes=time_window_minutes)

        for station in stations:
            station_id = station.get("id", "").strip()
            if not station_id:
                continue

            station_files = []
            for year in range(start_dt.year, end_dt.year + 1):
                hist_path = os.path.join(ndbc_folder, f"{station_id}h{year}.txt.gz")
                if os.path.exists(hist_path):
                    station_files.append(hist_path)
            realtime_path = os.path.join(ndbc_folder, f"{station_id}.txt")
            if os.path.exists(realtime_path):
                station_files.append(realtime_path)

            if not station_files:
                continue

            station_lon = float(station["lon"])
            station_lat = float(station["lat"])
            spatial_distances = _ndbc_haversine_distance(station_lat, station_lon, lat1, lon1)
            node_index = int(np.argmin(spatial_distances))
            node_dist = float(np.min(spatial_distances))
            if node_dist > max_dist_deg:
                continue

            station_obs = []
            for station_file in station_files:
                station_obs.extend(_parse_ndbc_station_file(station_file, start_dt, end_dt))
            if not station_obs:
                continue

            station_obs.sort(key=lambda item: item[0])
            station_matches = 0

            for obs_time, obs_wvht in station_obs:
                time_deltas_sec = np.array([abs((t - obs_time).total_seconds()) for t in ww3_times], dtype=float)
                model_time_index = int(np.argmin(time_deltas_sec))
                if time_deltas_sec[model_time_index] > max_time_delta.total_seconds():
                    continue

                model_hs = hs_nt_n[model_time_index, node_index]
                if not np.isfinite(model_hs):
                    continue

                matched_ndbc.append(float(obs_wvht))
                matched_ww3.append(float(model_hs))
                matched_station_ids.append(station_id)
                station_matches += 1

            if station_matches > 0:
                station_match_count += 1
                log(
                    tr("plotting_ndbc_station_match_count", "📍 站点 {station} 匹配到 {count} 个点").format(
                        station=station_id,
                        count=station_matches,
                    )
                )

        matched_ndbc = np.asarray(matched_ndbc, dtype=float)
        matched_ww3 = np.asarray(matched_ww3, dtype=float)

        log("=" * 70)
        log(tr("plotting_matching_completed_simple", "Matching completed!"))
        log(tr("plotting_ndbc_total_station_match_count", "Matched stations: {count}").format(count=station_match_count))
        log(tr("plotting_ndbc_total_points", "Total matched points: {count}").format(count=len(matched_ndbc)))

        from .photo_output import SUBDIR_NDBC_FIT, prepare_photo_subdir

        os.makedirs(out_folder, exist_ok=True)
        photo_folder = prepare_photo_subdir(out_folder, SUBDIR_NDBC_FIT)

        if len(matched_ndbc) == 0:
            log(tr("plotting_no_matching_points_ndbc", "No matching NDBC points found. Please check station data or time range."))
            result_queue.put({"bias": None, "rmse": None, "corr": None, "count": 0})
            log_queue.put("__DONE__")
            return

        valid = (~np.isnan(matched_ndbc)) & (~np.isnan(matched_ww3))
        x = matched_ndbc[valid]
        y = matched_ww3[valid]
        bias = float(np.nanmean(y - x)) if len(y) > 0 else np.nan
        rmse = float(np.sqrt(np.nanmean((y - x) ** 2))) if len(y) > 0 else np.nan
        corr = float(np.corrcoef(x, y)[0, 1]) if (len(x) > 1 and np.nanstd(x) > 0 and np.nanstd(y) > 0) else np.nan

        np.savez(
            os.path.join(out_folder, "ndbc_matching_results.npz"),
            swh_ndbc=matched_ndbc,
            swh_ww3=matched_ww3,
            station_ids=np.asarray(matched_station_ids, dtype=object),
        )

        original_backend = matplotlib.get_backend()
        matplotlib.use("Agg")
        try:
            max_val = float(np.nanmax(np.concatenate([x, y]))) if len(x) > 0 else 10.0
            upper = max(1.0, max_val * 1.02)
            fig = plt.figure(figsize=(8, 8), dpi=300)
            plt.scatter(x, y, s=8, c="seagreen", alpha=0.6)
            plt.xlabel("NDBC (m)")
            plt.ylabel("WW3 (m)")
            plt.title("Linear fit of simulation and buoy observation")
            plt.xlim([0, upper])
            plt.ylim([0, upper])
            plt.plot([0, upper], [0, upper], "k--", linewidth=1.5)
            r_text = f"R = {corr:.3f}" if np.isfinite(corr) else "R = N/A"
            txt = f"{r_text}\nBias = {bias:.3f}\nRMSE = {rmse:.3f}"
            plt.text(0.05 * upper, 0.95 * upper, txt, va="top")
            plt.grid(False)
            plt.tight_layout()
            out_png = os.path.join(photo_folder, "ww3_ndbc_comparison.png")
            plt.savefig(out_png, dpi=300, bbox_inches="tight")
            plt.close(fig)
        finally:
            matplotlib.use(original_backend)

        result_queue.put({"bias": bias, "rmse": rmse, "corr": corr, "count": len(matched_ndbc)})
    except Exception as exc:
        try:
            log_queue.put(tr("plotting_process_failed", "❌ 处理失败：{error}").format(error=exc))
        except Exception:
            pass
        result_queue.put(None)
    finally:
        try:
            log_queue.put("__DONE__")
        except Exception:
            pass


def _parse_ndbc_station_elements(xml_bytes):
    
    # [EN] [EN] Parse NOAA ``activestations.xml`` byte content and return a list of station metadata dicts.
    """解析 NOAA ``activestations.xml`` 字节内容，返回站点元数据字典列表。"""
    root = ET.fromstring(xml_bytes)
    stations = []
    for elem in root.iter():
        tag = elem.tag.split("}")[-1]
        if tag != "station":
            continue

        station_id = (elem.attrib.get("id") or "").strip().upper()
        if not station_id:
            continue

        try:
            lat = float(elem.attrib.get("lat", "nan"))
            lon = float(elem.attrib.get("lon", "nan"))
        except ValueError:
            continue

        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue

        stations.append(
            {
                "id": station_id,
                "lat": lat,
                "lon": lon,
                "name": (elem.attrib.get("name") or "").strip(),
                "owner": (elem.attrib.get("owner") or "").strip(),
                "type": (elem.attrib.get("type") or "").strip(),
                "pgm": (elem.attrib.get("pgm") or "").strip(),
                "met": (elem.attrib.get("met") or "").strip().lower(),
            }
        )
    return stations


def _filter_ndbc_stations(stations, lon_lat):
    
    # [EN] [EN] Filter NDBC stations by a ``(lon_min, lon_max, lat_min, lat_max)`` bounding box (supports crossing the date line).
    """按 ``(lon_min, lon_max, lat_min, lat_max)`` 边界框筛选 NDBC 站点（支持跨日期线）。"""
    lon_min, lon_max, lat_min, lat_max = lon_lat
    filtered = []
    for station in stations:
        lon = station["lon"]
        lat = station["lat"]
        lon_ok = (lon_min <= lon <= lon_max) if lon_min <= lon_max else (lon >= lon_min or lon <= lon_max)
        lat_ok = lat_min <= lat <= lat_max
        if lon_ok and lat_ok:
            filtered.append(station)
    return filtered


def _download_file(session, url, local_path, log_queue, label):
    
    # [EN] [EN] Stream-download a single NDBC data file locally and report progress percentage through the queue.
    """流式下载单个 NDBC 数据文件到本地，并通过队列报告进度百分比。"""
    temp_path = local_path + ".part"
    try:
        with session.get(url, stream=True, timeout=NDBC_REQUEST_TIMEOUT) as response:
            if response.status_code == 404:
                return False, "404"
            response.raise_for_status()
            total_size = int(response.headers.get("Content-Length", "0") or "0")
            transferred = 0
            last_percent = -1
            with open(temp_path, "wb") as file_obj:
                for chunk in response.iter_content(chunk_size=1024 * 128):
                    if not chunk:
                        continue
                    file_obj.write(chunk)
                    transferred += len(chunk)
                    if total_size > 0:
                        percent = int(transferred / total_size * 100)
                        if percent > last_percent:
                            last_percent = percent
                            _ndbc_log(
                                log_queue,
                                tr("plotting_ndbc_download_progress", "下载 NDBC {label} ... {percent}%").format(
                                    label=label, percent=percent
                                ),
                                update=True,
                            )
        os.replace(temp_path, local_path)
        return True, ""
    except Exception as exc:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
        return False, str(exc)


def _download_ndbc_worker(lon_lat, time_range, local_folder, log_queue, result_queue):
    
    # [EN] [EN] Batch-download NDBC observation data for the specified region and time range to a local directory in a subprocess.
    """在子进程中批量下载指定区域与时间范围内的 NDBC 观测数据到本地目录。"""
    try:
        start_dt, end_dt = _parse_ndbc_time_range(time_range)
        session = requests.Session()
        session.headers.update({"User-Agent": "WW3Tool NDBC Downloader"})

        _ndbc_log(log_queue, tr("plotting_ndbc_fetch_stations", "🔄 正在获取 NDBC 站点列表..."))
        response = session.get(NDBC_ACTIVE_STATIONS_URL, timeout=NDBC_REQUEST_TIMEOUT)
        response.raise_for_status()
        stations = _parse_ndbc_station_elements(response.content)
        _ndbc_log(log_queue, tr("plotting_ndbc_station_total", "📚 共读取到 {count} 个 NDBC 活跃站点").format(count=len(stations)))

        selected_stations = _filter_ndbc_stations(stations, lon_lat)
        if not selected_stations:
            _ndbc_log(log_queue, tr("plotting_ndbc_no_station_in_range", "⚠️ 当前经纬度范围内没有找到 NDBC 活跃站点。"))
            result_queue.put({"ok": False, "downloaded": 0, "skipped": 0, "stations": 0})
            log_queue.put("__DONE__")
            return

        os.makedirs(local_folder, exist_ok=True)
        metadata_path = os.path.join(local_folder, f"ndbc_stations_{time_range[0]}_{time_range[1]}.json")
        with open(metadata_path, "w", encoding="utf-8") as file_obj:
            json.dump(selected_stations, file_obj, ensure_ascii=False, indent=2)

        _ndbc_log(
            log_queue,
            tr("plotting_ndbc_station_selected", "✅ 范围内找到 {count} 个 NDBC 站点").format(count=len(selected_stations)),
        )

        years = list(range(start_dt.year, end_dt.year + 1))
        realtime_needed = end_dt.date() >= (datetime.now().date() - timedelta(days=NDBC_REALTIME_LOOKBACK_DAYS))

        downloaded = 0
        skipped = 0
        failed = 0

        for station in selected_stations:
            station_id = station["id"]
            _ndbc_log(
                log_queue,
                tr("plotting_ndbc_station_start", "🔎 处理站点 {station} ({name})").format(
                    station=station_id,
                    name=station.get("name") or "-",
                ),
            )

            for year in years:
                filename = f"{station_id}h{year}.txt.gz"
                local_path = os.path.join(local_folder, filename)
                if os.path.exists(local_path):
                    skipped += 1
                    continue
                url = f"{NDBC_HISTORICAL_STDMET_BASE_URL}{filename}"
                ok, error = _download_file(session, url, local_path, log_queue, filename)
                if ok:
                    downloaded += 1
                    _ndbc_log(
                        log_queue,
                        tr("plotting_ndbc_download_complete", "✅ 下载完成 {label}").format(label=filename),
                        update=True,
                    )
                elif error == "404":
                    continue
                else:
                    failed += 1
                    _ndbc_log(
                        log_queue,
                        tr("plotting_ndbc_download_failed_file", "❌ 下载 NDBC 文件失败：{label} -> {error}").format(
                            label=filename, error=error
                        ),
                    )

            if realtime_needed:
                realtime_name = f"{station_id}.txt"
                realtime_local = os.path.join(local_folder, realtime_name)
                if os.path.exists(realtime_local):
                    skipped += 1
                else:
                    realtime_url = f"{NDBC_REALTIME_BASE_URL}{realtime_name}"
                    ok, error = _download_file(session, realtime_url, realtime_local, log_queue, realtime_name)
                    if ok:
                        downloaded += 1
                        _ndbc_log(
                            log_queue,
                            tr("plotting_ndbc_download_complete", "✅ 下载完成 {label}").format(label=realtime_name),
                            update=True,
                        )
                    elif error != "404":
                        failed += 1
                        _ndbc_log(
                            log_queue,
                            tr("plotting_ndbc_download_failed_file", "❌ 下载 NDBC 文件失败：{label} -> {error}").format(
                                label=realtime_name, error=error
                            ),
                        )

        _ndbc_log(
            log_queue,
            tr(
                "plotting_ndbc_download_summary",
                "📦 NDBC 下载完成：站点 {stations} 个，新增文件 {downloaded} 个，跳过 {skipped} 个，失败 {failed} 个。",
            ).format(
                stations=len(selected_stations),
                downloaded=downloaded,
                skipped=skipped,
                failed=failed,
            ),
        )
        result_queue.put(
            {
                "ok": failed == 0,
                "downloaded": downloaded,
                "skipped": skipped,
                "failed": failed,
                "stations": len(selected_stations),
            }
        )
    except Exception as exc:
        _ndbc_log(
            log_queue,
            tr("plotting_ndbc_download_process_failed", "❌ NDBC 下载失败：{error}").format(error=exc),
        )
        result_queue.put({"ok": False, "downloaded": 0, "skipped": 0, "failed": 1, "stations": 0})
    finally:
        try:
            log_queue.put("__DONE__")
        except Exception:
            pass
