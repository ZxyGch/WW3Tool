"""
NDBC observation comparison UI module.
"""

import glob
import json
import os
import platform
import re
import warnings
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from multiprocessing import Process, Queue

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib
matplotlib.use('QtAgg')
import matplotlib.pyplot as plt
import numpy as np
import requests
from matplotlib import font_manager
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from netCDF4 import Dataset, num2date
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import HeaderCardWidget, InfoBar, LineEdit, MessageBoxBase, PrimaryPushButton

from setting.config import load_config, ensure_project_data_dir
from setting.language_manager import load_language, tr


NDBC_ACTIVE_STATIONS_URL = "https://www.ndbc.noaa.gov/activestations.xml"
NDBC_HISTORICAL_STDMET_BASE_URL = "https://www.ndbc.noaa.gov/data/historical/stdmet/"
NDBC_REALTIME_BASE_URL = "https://www.ndbc.noaa.gov/data/realtime2/"
NDBC_REQUEST_TIMEOUT = (20, 120)
NDBC_REALTIME_LOOKBACK_DAYS = 45


class _NDBCMapDialog(MessageBoxBase):
    """NDBC map dialog shell aligned with Step 3 map window style."""

    def __init__(self, parent, *, content_aspect_wh: float | None = None):
        super().__init__(parent)
        self.setWindowTitle("")
        self._content_aspect_wh = float(content_aspect_wh) if content_aspect_wh and content_aspect_wh > 0 else 1.25
        if platform.system() == "Darwin":
            self.setStyleSheet("font-family: 'PingFang SC';")
        self.hideYesButton()
        self.hideCancelButton()
        self.buttonLayout.parent().setVisible(False)
        self._content_host = QWidget()
        self._content_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._content_layout = QVBoxLayout(self._content_host)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self.viewLayout.addWidget(self._content_host, 1)

        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self._close_dialog)

        if hasattr(self, "setClosableOnMaskClicked"):
            self.setClosableOnMaskClicked(True)

    def set_main_widget(self, content_widget: QWidget):
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        content_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._content_layout.addWidget(content_widget, 1)

    def _close_dialog(self):
        QtWidgets.QDialog.done(self, int(QtWidgets.QDialog.DialogCode.Rejected))

    def _avail_rect(self):
        parent = self.parentWidget()
        ratio_w, ratio_h = 0.88, 0.88
        if parent is not None and parent.isVisible():
            pr = parent.frameGeometry()
            return int(pr.width() * ratio_w), int(pr.height() * ratio_h)
        screen = QtWidgets.QApplication.primaryScreen()
        ag = screen.availableGeometry() if screen is not None else None
        if ag is not None:
            return int(ag.width() * 0.86), int(ag.height() * 0.88)
        return 1240, 920

    def showEvent(self, event):
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self._fit_to_parent_window)

    def _fit_to_parent_window(self):
        avail_w, avail_h = self._avail_rect()
        min_w, min_h = 960, 640
        max_w, max_h = 1920, 1080
        aspect = float(np.clip(self._content_aspect_wh, 0.3, 14.0))
        if avail_w / max(avail_h, 1) > aspect:
            dialog_h = avail_h
            dialog_w = int(round(dialog_h * aspect))
        else:
            dialog_w = avail_w
            dialog_h = int(round(dialog_w / aspect))
        dialog_w = max(min_w, min(dialog_w, max_w))
        dialog_h = max(min_h, min(dialog_h, max_h))
        card = getattr(self, "widget", None)
        if card is not None:
            card.setFixedSize(dialog_w, dialog_h)
            card.updateGeometry()
        else:
            self.resize(dialog_w, dialog_h)


def _ndbc_log(log_queue, message, update=False):
    try:
        if update:
            log_queue.put(("__UPDATE__", message))
        else:
            log_queue.put(message)
    except Exception:
        pass


def _configure_ndbc_map_fonts():
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
    start_str, end_str = time_range
    start_dt = datetime.strptime(start_str, "%Y%m%d")
    end_dt = datetime.strptime(end_str, "%Y%m%d")
    return start_dt, end_dt


def _find_ndbc_metadata_file(local_folder, time_range):
    exact_path = os.path.join(local_folder, f"ndbc_stations_{time_range[0]}_{time_range[1]}.json")
    if os.path.exists(exact_path):
        return exact_path
    pattern = os.path.join(local_folder, "ndbc_stations_*.json")
    matches = sorted(glob.glob(pattern), reverse=True)
    return matches[0] if matches else None


def _load_ndbc_stations_from_folder(local_folder, lon_lat, time_range):
    metadata_path = _find_ndbc_metadata_file(local_folder, time_range)
    if metadata_path:
        try:
            with open(metadata_path, "r", encoding="utf-8") as file_obj:
                stations = json.load(file_obj)
            return _filter_ndbc_stations(stations, lon_lat)
        except Exception:
            pass

    response = requests.get(NDBC_ACTIVE_STATIONS_URL, timeout=NDBC_REQUEST_TIMEOUT)
    response.raise_for_status()
    stations = _parse_ndbc_station_elements(response.content)
    return _filter_ndbc_stations(stations, lon_lat)


def _parse_ndbc_station_file(file_path, start_dt, end_dt):
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
    try:
        from .workers_utils import ww3_hs_collocation_flat, ww3_resolve_lon_lat_names

        config = load_config()
        load_language(config.get("LANGUAGE", "zh_CN"))

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
            time_ww3 = nc.variables["time"][:].astype(float)

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

        ww3_ref = datetime(1990, 1, 1, 0, 0, 0)
        ww3_times = np.array([ww3_ref + timedelta(days=float(t)) for t in time_ww3], dtype=object)

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

        os.makedirs(out_folder, exist_ok=True)
        photo_folder = os.path.join(out_folder, "photo")
        os.makedirs(photo_folder, exist_ok=True)

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
    try:
        config = load_config()
        load_language(config.get("LANGUAGE", "zh_CN"))

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


class NDBCPlotMixin:
    """NDBC observation comparison UI."""

    def _ensure_ndbc_folder_path(self):
        path = ensure_project_data_dir("NDBC_PATH", "ndbc")
        if hasattr(self, "ndbc_folder_edit") and self.ndbc_folder_edit:
            self.ndbc_folder_edit.setText(path)
        return path

    def _create_ndbc_ui(self, plot_content_widget, plot_content_layout, button_style, input_style):
        current_config = load_config()
        lon_west_default = current_config.get("LONGITUDE_WEST", "")
        lon_east_default = current_config.get("LONGITUDE_EAST", "")
        lat_south_default = current_config.get("LATITUDE_SORTH", "")
        lat_north_default = current_config.get("LATITUDE_NORTH", "")
        ndbc_path_default = ensure_project_data_dir("NDBC_PATH", "ndbc")

        card = HeaderCardWidget(plot_content_widget)
        card.setTitle(tr("plotting_ndbc_data", "NDBC 拟合"))
        card.setStyleSheet("""
            HeaderCardWidget QLabel {
                font-weight: normal;
                margin-left: 0px;
                padding-left: 0px;
            }
        """)
        card.headerLayout.setContentsMargins(11, 10, 11, 12)

        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        geo_frame = QWidget()
        geo_layout = QGridLayout(geo_frame)
        geo_layout.setSpacing(10)
        geo_layout.setContentsMargins(0, 0, 0, 0)

        saved_values = {}
        for attr_name, key in (
            ("lon_west_ndbc_edit", "lon_west"),
            ("lon_east_ndbc_edit", "lon_east"),
            ("lat_south_ndbc_edit", "lat_south"),
            ("lat_north_ndbc_edit", "lat_north"),
        ):
            if hasattr(self, attr_name):
                widget = getattr(self, attr_name)
                if widget is not None:
                    saved_values[key] = widget.text()
                if widget is not None and widget.parent() is not None and widget.parent() != geo_frame:
                    old_layout = widget.parent().layout()
                    if old_layout:
                        old_layout.removeWidget(widget)

        geo_layout.addWidget(QLabel(tr("step2_lon_west", "西经:")), 0, 0)
        if not hasattr(self, "lon_west_ndbc_edit") or self.lon_west_ndbc_edit is None:
            self.lon_west_ndbc_edit = LineEdit()
        self.lon_west_ndbc_edit.setStyleSheet(input_style)
        self.lon_west_ndbc_edit.setText(saved_values.get("lon_west", lon_west_default))
        geo_layout.addWidget(self.lon_west_ndbc_edit, 0, 1)

        geo_layout.addWidget(QLabel(tr("step2_lon_east", "东经:")), 0, 2)
        if not hasattr(self, "lon_east_ndbc_edit") or self.lon_east_ndbc_edit is None:
            self.lon_east_ndbc_edit = LineEdit()
        self.lon_east_ndbc_edit.setStyleSheet(input_style)
        self.lon_east_ndbc_edit.setText(saved_values.get("lon_east", lon_east_default))
        geo_layout.addWidget(self.lon_east_ndbc_edit, 0, 3)

        geo_layout.addWidget(QLabel(tr("step2_lat_south", "南纬:")), 1, 0)
        if not hasattr(self, "lat_south_ndbc_edit") or self.lat_south_ndbc_edit is None:
            self.lat_south_ndbc_edit = LineEdit()
        self.lat_south_ndbc_edit.setStyleSheet(input_style)
        self.lat_south_ndbc_edit.setText(saved_values.get("lat_south", lat_south_default))
        geo_layout.addWidget(self.lat_south_ndbc_edit, 1, 1)

        geo_layout.addWidget(QLabel(tr("step2_lat_north", "北纬:")), 1, 2)
        if not hasattr(self, "lat_north_ndbc_edit") or self.lat_north_ndbc_edit is None:
            self.lat_north_ndbc_edit = LineEdit()
        self.lat_north_ndbc_edit.setStyleSheet(input_style)
        self.lat_north_ndbc_edit.setText(saved_values.get("lat_north", lat_north_default))
        geo_layout.addWidget(self.lat_north_ndbc_edit, 1, 3)

        geo_layout.addWidget(QLabel(tr("plotting_start", "开始:")), 2, 0)
        if not hasattr(self, "ndbc_start_edit"):
            self.ndbc_start_edit = LineEdit()
            self.ndbc_start_edit.setPlaceholderText("20250101")
        self.ndbc_start_edit.setStyleSheet(input_style)
        if self.ndbc_start_edit.parent() is not None and self.ndbc_start_edit.parent() != geo_frame:
            old_layout = self.ndbc_start_edit.parent().layout()
            if old_layout:
                old_layout.removeWidget(self.ndbc_start_edit)
        geo_layout.addWidget(self.ndbc_start_edit, 2, 1)

        geo_layout.addWidget(QLabel(tr("plotting_end", "结束:")), 2, 2)
        if not hasattr(self, "ndbc_end_edit"):
            self.ndbc_end_edit = LineEdit()
            self.ndbc_end_edit.setPlaceholderText("20250101")
        self.ndbc_end_edit.setStyleSheet(input_style)
        if self.ndbc_end_edit.parent() is not None and self.ndbc_end_edit.parent() != geo_frame:
            old_layout = self.ndbc_end_edit.parent().layout()
            if old_layout:
                old_layout.removeWidget(self.ndbc_end_edit)
        geo_layout.addWidget(self.ndbc_end_edit, 2, 3)

        geo_layout.setColumnStretch(1, 1)
        geo_layout.setColumnStretch(3, 1)
        layout.addWidget(geo_frame)

        folder_frame = QWidget()
        folder_layout = QGridLayout(folder_frame)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(10)
        folder_layout.setColumnStretch(1, 1)

        if not hasattr(self, "ndbc_folder_edit"):
            self.ndbc_folder_edit = LineEdit()
            self.ndbc_folder_edit.setText(ndbc_path_default)
        elif not self.ndbc_folder_edit.text().strip() or not os.path.isdir(self.ndbc_folder_edit.text().strip()):
            self.ndbc_folder_edit.setText(ndbc_path_default)
        self.ndbc_folder_edit.setStyleSheet(input_style)
        folder_layout.addWidget(self.ndbc_folder_edit, 0, 1)

        choose_folder_button = PrimaryPushButton(tr("plotting_ndbc_select", "NDBC 选择"))
        choose_folder_button.setStyleSheet(button_style)
        choose_folder_button.clicked.connect(self.choose_ndbc_folder)
        folder_layout.addWidget(choose_folder_button, 0, 2)
        layout.addWidget(folder_frame)

        if not hasattr(self, "btn_choose_ndbc_wind_file"):
            self.btn_choose_ndbc_wind_file = PrimaryPushButton(tr("step1_choose_wind", "选择风场文件"))
            self.btn_choose_ndbc_wind_file.setStyleSheet(button_style)
            self.btn_choose_ndbc_wind_file.clicked.connect(self._choose_ndbc_wind_file)
        if not hasattr(self, "btn_choose_ndbc_wave_file"):
            self.btn_choose_ndbc_wave_file = PrimaryPushButton(tr("plotting_choose_wave_height", "选择波高文件"))
            self.btn_choose_ndbc_wave_file.setStyleSheet(button_style)
            self.btn_choose_ndbc_wave_file.clicked.connect(self._choose_ndbc_wave_file)

        load_from_data_button = PrimaryPushButton(tr("step2_load_from_nc", "从 wind.nc 读取范围"))
        load_from_data_button.setStyleSheet(button_style)
        load_from_data_button.clicked.connect(lambda: self.load_latlon_from_nc_ndbc("wind.nc"))

        load_from_ww3_button = PrimaryPushButton(tr("step2_load_from_ww3", "从模拟结果读取范围"))
        load_from_ww3_button.setStyleSheet(button_style)
        load_from_ww3_button.clicked.connect(lambda: self.load_latlon_from_nc_ndbc("ww3.*.nc"))

        for btn in (self.btn_choose_ndbc_wind_file, load_from_data_button):
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        wind_row = QHBoxLayout()
        wind_row.setSpacing(10)
        wind_row.addWidget(self.btn_choose_ndbc_wind_file, 1)
        wind_row.addWidget(load_from_data_button, 1)
        layout.addLayout(wind_row)

        for btn in (self.btn_choose_ndbc_wave_file, load_from_ww3_button):
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        wave_row = QHBoxLayout()
        wave_row.setSpacing(10)
        wave_row.addWidget(self.btn_choose_ndbc_wave_file, 1)
        wave_row.addWidget(load_from_ww3_button, 1)
        layout.addLayout(wave_row)

        if not hasattr(self, "btn_download_ndbc"):
            self.btn_download_ndbc = PrimaryPushButton(tr("plotting_download_ndbc", "下载 NDBC 数据"))
            self.btn_download_ndbc.setStyleSheet(button_style)
            self.btn_download_ndbc.clicked.connect(self.download_ndbc_data)
        layout.addWidget(self.btn_download_ndbc)

        if not hasattr(self, "btn_view_ndbc_observation"):
            self.btn_view_ndbc_observation = PrimaryPushButton(tr("plotting_view_ndbc_observation", "查看浮标站点图"))
            self.btn_view_ndbc_observation.setStyleSheet(button_style)
            self.btn_view_ndbc_observation.clicked.connect(self.run_ndbc_observation)
        layout.addWidget(self.btn_view_ndbc_observation)

        if not hasattr(self, "btn_view_ndbc_fit"):
            self.btn_view_ndbc_fit = PrimaryPushButton(tr("plotting_view_ndbc_fit", "查看 NDBC 拟合图"))
            self.btn_view_ndbc_fit.setStyleSheet(button_style)
            self.btn_view_ndbc_fit.clicked.connect(self.view_ndbc_fit)
        layout.addWidget(self.btn_view_ndbc_fit)

        card.viewLayout.setContentsMargins(11, 10, 11, 12)
        card.viewLayout.addLayout(layout)
        plot_content_layout.addWidget(card)

        self._update_ndbc_wind_button()
        self._update_ndbc_wave_button()

    def _update_ndbc_wind_button(self):
        if not hasattr(self, "btn_choose_ndbc_wind_file"):
            return

        data_nc_path = None
        if hasattr(self, "selected_origin_file") and self.selected_origin_file and os.path.exists(self.selected_origin_file):
            data_nc_path = self.selected_origin_file
        elif hasattr(self, "selected_folder") and self.selected_folder:
            probe_path = os.path.join(self.selected_folder, "wind.nc")
            if os.path.exists(probe_path):
                data_nc_path = probe_path
            else:
                wind_files = sorted(glob.glob(os.path.join(self.selected_folder, "wind_*.nc")))
                if wind_files:
                    data_nc_path = wind_files[0]

        if not data_nc_path:
            return

        self.selected_origin_file = data_nc_path
        file_name = os.path.basename(data_nc_path)
        display_name = file_name[:27] + "..." if len(file_name) > 30 else file_name
        self.btn_choose_ndbc_wind_file.setText(display_name)
        if hasattr(self, "_set_plot_button_filled"):
            self._set_plot_button_filled(self.btn_choose_ndbc_wind_file, True)
        self.btn_choose_ndbc_wind_file.update()

    def _update_ndbc_wave_button(self):
        if not hasattr(self, "btn_choose_ndbc_wave_file"):
            return

        wave_file = None
        if hasattr(self, "selected_wave_height_file") and self.selected_wave_height_file and os.path.exists(self.selected_wave_height_file):
            wave_file = self.selected_wave_height_file
        elif hasattr(self, "selected_folder") and self.selected_folder:
            wave_files = glob.glob(os.path.join(self.selected_folder, "ww3*.nc"))
            wave_files = [f for f in wave_files if "spec" not in os.path.basename(f).lower()]
            if wave_files:
                wave_file = wave_files[0]

        if not wave_file:
            return

        self.selected_wave_height_file = os.path.normpath(wave_file)
        file_name = os.path.basename(wave_file)
        display_name = file_name[:27] + "..." if len(file_name) > 30 else file_name
        self.btn_choose_ndbc_wave_file.setText(display_name)
        if hasattr(self, "_set_plot_button_filled"):
            self._set_plot_button_filled(self.btn_choose_ndbc_wave_file, True)
        self.btn_choose_ndbc_wave_file.update()

    def choose_ndbc_folder(self):
        start_path = self.ndbc_folder_edit.text().strip() if hasattr(self, "ndbc_folder_edit") else ""
        if not os.path.exists(start_path):
            start_path = self._ensure_ndbc_folder_path()

        folder = QFileDialog.getExistingDirectory(
            self,
            tr("plotting_choose_ndbc_folder", "选择 NDBC 数据文件夹"),
            start_path,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks,
        )
        if folder:
            self.ndbc_folder_edit.setText(folder)
            self.log(tr("plotting_ndbc_folder_selected", "✅ 已选择 NDBC 数据文件夹：{folder}").format(folder=folder))

    def _choose_ndbc_wind_file(self):
        if hasattr(self, "choose_wind_field_file_plot"):
            self.choose_wind_field_file_plot()
        self._update_ndbc_wind_button()

    def _choose_ndbc_wave_file(self):
        if hasattr(self, "choose_wave_height_file"):
            self.choose_wave_height_file()
        self._update_ndbc_wave_button()

    def load_latlon_from_nc_ndbc(self, file_name="wind.nc"):
        if not isinstance(file_name, str):
            file_name = "wind.nc"
        if not self.selected_folder:
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return

        grid_type = getattr(self, "grid_type_var", tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == tr("step2_grid_type_nested", "嵌套网格"))
        is_ww3_file = ("ww3" in file_name.lower() or "*" in file_name)
        data_folder = os.path.join(self.selected_folder, "fine") if is_nested_grid and is_ww3_file else self.selected_folder

        if is_nested_grid and is_ww3_file and not os.path.isdir(data_folder):
            self.log(tr("plotting_fine_folder_not_found", "❌ 未找到 fine 文件夹，请先生成嵌套网格"))
            return

        nc_files = glob.glob(os.path.join(data_folder, file_name))
        if not nc_files:
            self.log(tr("plotting_file_not_found_in_folder", "❌ 未找到匹配的文件：{file}（在 {folder} 中）").format(file=file_name, folder=data_folder))
            return

        data_nc_path = nc_files[0]
        try:
            with Dataset(data_nc_path) as ds:
                lon = ds.variables["longitude"][:]
                lat = ds.variables["latitude"][:]

                self.lon_west_ndbc_edit.setText(f"{float(lon.min()):.2f}")
                self.lon_east_ndbc_edit.setText(f"{float(lon.max()):.2f}")
                self.lat_south_ndbc_edit.setText(f"{float(lat.min()):.2f}")
                self.lat_north_ndbc_edit.setText(f"{float(lat.max()):.2f}")

                if "time" in ds.variables:
                    time_var = ds.variables["time"]
                    try:
                        times = num2date(time_var[:], time_var.units)
                        if hasattr(times[0], "strftime"):
                            self.ndbc_start_edit.setText(times[0].strftime("%Y%m%d"))
                            self.ndbc_end_edit.setText(times[-1].strftime("%Y%m%d"))
                    except Exception:
                        pass
            self.log(tr("step2_auto_load_range", "✅ 已从 {filename} 自动加载经纬度范围。").format(filename=os.path.basename(data_nc_path)))
        except Exception as exc:
            self.log(tr("plotting_read_file_failed", "❌ 读取 {file} 失败: {error}").format(file=os.path.basename(data_nc_path), error=exc))

    def download_ndbc_data(self):
        try:
            lon_west = float(self.lon_west_ndbc_edit.text().strip())
            lon_east = float(self.lon_east_ndbc_edit.text().strip())
            lat_south = float(self.lat_south_ndbc_edit.text().strip())
            lat_north = float(self.lat_north_ndbc_edit.text().strip())
        except ValueError:
            self.log(tr("plotting_fill_lonlat_range", "❌ 请正确填写经纬度范围"))
            return

        start_str = self.ndbc_start_edit.text().strip()
        end_str = self.ndbc_end_edit.text().strip()
        if not start_str or not end_str:
            self.log(tr("plotting_fill_time_range", "❌ 请填写开始和结束时间（格式：YYYYMMDD）"))
            return
        if not re.fullmatch(r"\d{8}", start_str) or not re.fullmatch(r"\d{8}", end_str):
            self.log(tr("plotting_ndbc_invalid_time_format", "❌ 时间格式错误，请使用 YYYYMMDD。"))
            return

        try:
            start_dt = datetime.strptime(start_str, "%Y%m%d")
            end_dt = datetime.strptime(end_str, "%Y%m%d")
        except ValueError:
            self.log(tr("plotting_ndbc_invalid_time_format", "❌ 时间格式错误，请使用 YYYYMMDD。"))
            return
        if start_dt > end_dt:
            self.log(tr("plotting_ndbc_start_after_end", "❌ 开始时间不能晚于结束时间。"))
            return

        local_folder = self.ndbc_folder_edit.text().strip()
        if not local_folder:
            local_folder = self._ensure_ndbc_folder_path()
        elif not os.path.isdir(local_folder):
            local_folder = self._ensure_ndbc_folder_path()

        self.btn_download_ndbc.setEnabled(False)
        self.btn_download_ndbc.setText(tr("plotting_ndbc_downloading", "下载中..."))
        self._run_ndbc_download_process(
            [lon_west, lon_east, lat_south, lat_north],
            [start_str, end_str],
            local_folder,
        )

    def run_ndbc_observation(self):
        try:
            lon_west = float(self.lon_west_ndbc_edit.text().strip())
            lon_east = float(self.lon_east_ndbc_edit.text().strip())
            lat_south = float(self.lat_south_ndbc_edit.text().strip())
            lat_north = float(self.lat_north_ndbc_edit.text().strip())
        except ValueError:
            self.log(tr("plotting_fill_lonlat_range", "❌ 请正确填写经纬度范围"))
            return

        start_str = self.ndbc_start_edit.text().strip()
        end_str = self.ndbc_end_edit.text().strip()
        if not start_str or not end_str:
            self.log(tr("plotting_fill_time_range", "❌ 请填写开始和结束时间（格式：YYYYMMDD）"))
            return
        if not re.fullmatch(r"\d{8}", start_str) or not re.fullmatch(r"\d{8}", end_str):
            self.log(tr("plotting_ndbc_invalid_time_format", "❌ 时间格式错误，请使用 YYYYMMDD。"))
            return

        try:
            datetime.strptime(start_str, "%Y%m%d")
            datetime.strptime(end_str, "%Y%m%d")
        except ValueError:
            self.log(tr("plotting_ndbc_invalid_time_format", "❌ 时间格式错误，请使用 YYYYMMDD。"))
            return

        ndbc_folder = self.ndbc_folder_edit.text().strip() if hasattr(self, "ndbc_folder_edit") else ""
        if not ndbc_folder or not os.path.isdir(ndbc_folder):
            ndbc_folder = self._ensure_ndbc_folder_path()

        lon_lat = [lon_west, lon_east, lat_south, lat_north]
        stations = self._load_ndbc_station_points(lon_lat, [start_str, end_str], ndbc_folder)
        if not stations:
            InfoBar.warning(
                title=tr("plotting_display_failed", "显示失败"),
                content=tr("plotting_no_station_data", "没有可显示的站点数据"),
                duration=3000,
                parent=self,
            )
            self.log(tr("plotting_ndbc_no_station_in_range", "⚠️ 当前经纬度范围内没有找到 NDBC 活跃站点。"))
            return

        self._show_ndbc_station_map(stations, lon_lat)
        self.log(
            tr("plotting_ndbc_station_selected", "✅ 范围内找到 {count} 个 NDBC 站点").format(count=len(stations))
        )

    def view_ndbc_fit(self):
        if not self.selected_folder:
            self.log(tr("plotting_no_valid_folder", "❌ 本地未选择有效的目标文件夹。"))
            return

        try:
            lon_west = float(self.lon_west_ndbc_edit.text().strip())
            lon_east = float(self.lon_east_ndbc_edit.text().strip())
            lat_south = float(self.lat_south_ndbc_edit.text().strip())
            lat_north = float(self.lat_north_ndbc_edit.text().strip())
        except ValueError:
            self.log(tr("plotting_fill_lonlat_range", "❌ 请正确填写经纬度范围"))
            return

        start_str = self.ndbc_start_edit.text().strip()
        end_str = self.ndbc_end_edit.text().strip()
        if not start_str or not end_str:
            self.log(tr("plotting_fill_time_range", "❌ 请填写开始和结束时间（格式：YYYYMMDD）"))
            return
        if not re.fullmatch(r"\d{8}", start_str) or not re.fullmatch(r"\d{8}", end_str):
            self.log(tr("plotting_ndbc_invalid_time_format", "❌ 时间格式错误，请使用 YYYYMMDD。"))
            return

        try:
            start_dt = datetime.strptime(start_str, "%Y%m%d")
            end_dt = datetime.strptime(end_str, "%Y%m%d")
        except ValueError:
            self.log(tr("plotting_ndbc_invalid_time_format", "❌ 时间格式错误，请使用 YYYYMMDD。"))
            return
        if start_dt > end_dt:
            self.log(tr("plotting_ndbc_start_after_end", "❌ 开始时间不能晚于结束时间。"))
            return

        grid_type = getattr(self, "grid_type_var", tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == tr("step2_grid_type_nested", "嵌套网格"))

        if is_nested_grid:
            fine_dir = os.path.join(self.selected_folder, "fine")
            if not os.path.isdir(fine_dir):
                self.log(tr("plotting_fine_folder_not_found", "❌ 未找到 fine 文件夹，请先生成嵌套网格"))
                return
            data_folder = fine_dir
            output_folder = self.selected_folder
        else:
            data_folder = self.selected_folder
            output_folder = self.selected_folder

        ww3_files = glob.glob(os.path.join(data_folder, "ww3.*.nc"))
        ww3_files = [f for f in ww3_files if "spec" not in os.path.basename(f).lower()]
        if not ww3_files:
            ww3_files = glob.glob(os.path.join(data_folder, "ww3*.nc"))
            ww3_files = [f for f in ww3_files if "spec" not in os.path.basename(f).lower()]
        if not ww3_files:
            self.log(tr("plotting_no_ww3_files", "❌ {folder} 文件夹中没有找到波高文件（已排除谱文件）").format(folder=data_folder))
            return

        ndbc_folder = self.ndbc_folder_edit.text().strip() if hasattr(self, "ndbc_folder_edit") else ""
        if not ndbc_folder or not os.path.isdir(ndbc_folder):
            ndbc_folder = self._ensure_ndbc_folder_path()

        lon_lat = [lon_west, lon_east, lat_south, lat_north]
        time_range = [start_str, end_str]
        ww3_file = ww3_files[0]

        photo_folder = os.path.join(output_folder, "photo")
        out_png = os.path.join(photo_folder, "ww3_ndbc_comparison.png")
        if os.path.exists(out_png):
            self.log(tr("plotting_fit_image_exists", "📊 发现已存在的拟合图，正在打开..."))
            self.show_fit_image_signal.emit(out_png, tr("plotting_ndbc_fit_title", "拟合图：WW3 vs NDBC"))
            return

        self.btn_view_ndbc_fit.setEnabled(False)
        self.btn_view_ndbc_fit.setText(tr("plotting_calculating", "计算中..."))
        self._run_ndbc_fit_process(ww3_file, ndbc_folder, output_folder, lon_lat, time_range)

    def _run_ndbc_fit_process(self, ww3_file, ndbc_folder, output_folder, lon_lat, time_range):
        log_queue = Queue()
        result_queue = Queue()

        process = Process(
            target=_match_ww3_ndbc_worker,
            args=(ww3_file, ndbc_folder, output_folder, lon_lat, time_range, log_queue, result_queue),
        )
        process.start()

        def _poll_logs():
            try:
                done = False
                while True:
                    try:
                        msg = log_queue.get_nowait()
                        if msg == "__DONE__":
                            done = True
                            break
                        self.log_signal.emit(msg)
                    except Exception:
                        break

                if not done and process.is_alive():
                    QtCore.QTimer.singleShot(100, _poll_logs)
                    return

                if not done:
                    try:
                        while True:
                            try:
                                msg = log_queue.get_nowait()
                                if msg == "__DONE__":
                                    done = True
                                    break
                                self.log_signal.emit(msg)
                            except Exception:
                                break
                    except Exception:
                        pass

                process.join(timeout=5)

                try:
                    stats = result_queue.get(timeout=2)
                    photo_folder = os.path.join(output_folder, "photo")
                    out_png = os.path.join(photo_folder, "ww3_ndbc_comparison.png")
                    if stats and stats.get("count", 0) > 0 and os.path.exists(out_png):
                        bias_val = stats.get("bias", np.nan)
                        rmse_val = stats.get("rmse", np.nan)
                        corr_val = stats.get("corr", np.nan)
                        self.log_signal.emit(
                            tr("plotting_matching_completed", "✅ 匹配完成，共 {count} 个匹配点").format(
                                count=stats.get("count", 0)
                            )
                        )
                        if np.isfinite(bias_val) and np.isfinite(rmse_val) and np.isfinite(corr_val):
                            self.log_signal.emit(
                                tr("plotting_matching_stats", "   Bias: {bias:.3f}, RMSE: {rmse:.3f}, R: {corr:.3f}").format(
                                    bias=bias_val,
                                    rmse=rmse_val,
                                    corr=corr_val,
                                )
                            )
                        else:
                            self.log_signal.emit(
                                f"   Bias: {bias_val}, RMSE: {rmse_val}, R: {corr_val}"
                            )
                        self.show_fit_image_signal.emit(out_png, tr("plotting_ndbc_fit_title", "拟合图：WW3 vs NDBC"))
                    else:
                        self.log_signal.emit(tr("plotting_no_matching_points", "❌ 未匹配到有效点或图像不存在"))
                        self.log_signal.emit(
                            tr("plotting_cannot_display_fit", "⚠️ 未匹配到有效点或图像不存在，无法显示拟合图")
                        )
                except Exception as exc:
                    self.log_signal.emit(tr("plotting_get_result_failed", "❌ 获取结果失败：{error}").format(error=exc))
                finally:
                    QtCore.QTimer.singleShot(0, self._restore_view_ndbc_fit_button)
            except Exception as exc:
                import traceback

                self.log_signal.emit(tr("plotting_listen_process_failed", "❌ 监听子进程失败：{error}").format(error=exc))
                self.log_signal.emit(tr("plotting_detailed_error", "详细错误：{error}").format(error=traceback.format_exc()))
                QtCore.QTimer.singleShot(0, self._restore_view_ndbc_fit_button)

        QtCore.QTimer.singleShot(100, _poll_logs)

    def _restore_view_ndbc_fit_button(self):
        if hasattr(self, "btn_view_ndbc_fit"):
            self.btn_view_ndbc_fit.setEnabled(True)
            self.btn_view_ndbc_fit.setText(tr("plotting_view_ndbc_fit", "查看 NDBC 拟合图"))

    def _load_ndbc_station_points(self, lon_lat, time_range, local_folder):
        metadata_path = os.path.join(local_folder, f"ndbc_stations_{time_range[0]}_{time_range[1]}.json")
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, "r", encoding="utf-8") as file_obj:
                    stations = json.load(file_obj)
                return _filter_ndbc_stations(stations, lon_lat)
            except Exception:
                pass

        if os.path.isdir(local_folder):
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

        try:
            response = requests.get(NDBC_ACTIVE_STATIONS_URL, timeout=NDBC_REQUEST_TIMEOUT)
            response.raise_for_status()
            stations = _parse_ndbc_station_elements(response.content)
            return _filter_ndbc_stations(stations, lon_lat)
        except Exception as exc:
            self.log(tr("plotting_ndbc_download_process_failed", "❌ NDBC 下载失败：{error}").format(error=exc))
            return []

    def _show_ndbc_station_map(self, stations, lon_lat):
        _configure_ndbc_map_fonts()
        lon_min, lon_max, lat_min, lat_max = lon_lat
        lon_pad = max(1.0, abs(lon_max - lon_min) * 0.1)
        lat_pad = max(1.0, abs(lat_max - lat_min) * 0.1)

        fig = plt.figure(figsize=(10, 6))
        ax = plt.axes(projection=ccrs.PlateCarree())
        ax.set_extent(
            [min(lon_min, lon_max) - lon_pad, max(lon_min, lon_max) + lon_pad, min(lat_min, lat_max) - lat_pad, max(lat_min, lat_max) + lat_pad],
            crs=ccrs.PlateCarree(),
        )
        ax.add_feature(cfeature.LAND, facecolor="lightgray")
        ax.add_feature(cfeature.COASTLINE)
        ax.add_feature(cfeature.BORDERS, linestyle=":")
        gl = ax.gridlines(draw_labels=True, linestyle="--", alpha=0.5)
        gl.top_labels = False
        gl.right_labels = False

        lons = [station["lon"] for station in stations]
        lats = [station["lat"] for station in stations]
        ax.scatter(lons, lats, color="green", s=10, transform=ccrs.PlateCarree(), zorder=3)

        for station in stations:
            label = station.get("id") or station.get("name") or "-"
            ax.text(
                station["lon"],
                station["lat"],
                label,
                transform=ccrs.PlateCarree(),
                fontsize=8,
                color="black",
                zorder=4,
                ha="left",
                va="bottom",
            )
        text_labels = list(ax.texts)

        ax.set_title(tr("plotting_ndbc_station_distribution", "NDBC 浮标点位分布"), fontsize=14, fontweight="bold")
        fig.subplots_adjust(left=0.02, right=0.98, top=0.93, bottom=0.06)

        dialog = _NDBCMapDialog(self, content_aspect_wh=1.25)
        content_widget = QWidget()
        layout = QHBoxLayout(content_widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(6)

        canvas = FigureCanvas(fig)
        canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(canvas, 1)

        button_layout = QVBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(6)
        button_layout.addStretch()

        toggle_labels_btn = PrimaryPushButton(tr("plotting_hide_station_labels", "隐藏站点名称"))
        if hasattr(self, "_get_button_style"):
            toggle_labels_btn.setStyleSheet(self._get_button_style())

        labels_visible = True

        def toggle_station_labels():
            nonlocal labels_visible
            labels_visible = not labels_visible
            for text in text_labels:
                text.set_visible(labels_visible)
            toggle_labels_btn.setText(
                tr("plotting_hide_station_labels", "隐藏站点名称")
                if labels_visible
                else tr("plotting_show_station_labels", "显示站点名称")
            )
            canvas.draw_idle()

        toggle_labels_btn.clicked.connect(toggle_station_labels)
        button_layout.addWidget(toggle_labels_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        canvas.draw()
        dialog.set_main_widget(content_widget)
        dialog.exec()
        plt.close(fig)

    def _run_ndbc_download_process(self, lon_lat, time_range, local_folder):
        log_queue = Queue()
        result_queue = Queue()

        process = Process(
            target=_download_ndbc_worker,
            args=(lon_lat, time_range, local_folder, log_queue, result_queue),
        )
        process.start()

        def _poll_logs():
            try:
                done = False
                while True:
                    try:
                        message = log_queue.get_nowait()
                        if message == "__DONE__":
                            done = True
                            break
                        if isinstance(message, tuple) and len(message) == 2 and message[0] == "__UPDATE__":
                            self.log_update_last_line_signal.emit(message[1])
                        else:
                            self.log_signal.emit(message)
                    except Exception:
                        break

                if not done and process.is_alive():
                    QtCore.QTimer.singleShot(100, _poll_logs)
                    return

                if process.is_alive():
                    process.join(timeout=1)
                if process.is_alive():
                    process.terminate()
                    process.join()

                try:
                    result = result_queue.get_nowait()
                    if result.get("failed", 0) > 0:
                        self.log_signal.emit(
                            tr("plotting_ndbc_download_partial_failed", "⚠️ 部分 NDBC 文件下载失败，请查看上方日志。")
                        )
                except Exception:
                    pass
            except Exception as exc:
                self.log_signal.emit(
                    tr("plotting_ndbc_download_process_failed", "❌ NDBC 下载失败：{error}").format(error=exc)
                )
            finally:
                self._restore_ndbc_download_button()

        _poll_logs()

    def _restore_ndbc_download_button(self):
        if hasattr(self, "btn_download_ndbc"):
            self.btn_download_ndbc.setEnabled(True)
            self.btn_download_ndbc.setText(tr("plotting_download_ndbc", "下载 NDBC 数据"))
