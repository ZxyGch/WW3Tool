"""JASON-3 卫星有效波高验证 Worker — WW3 模式结果与 Jason-3 沿轨数据匹配与绘图。

在独立子进程中读取 WW3 输出 NetCDF 与本地 Jason-3 L2 产品，按时空窗口进行
最近邻匹配，计算偏差/RMSE/相关系数，并生成 SWH 对比散点图与空间分布图。

[EN] [EN] JASON-3 satellite significant wave height validation worker — match and plot WW3 model results against Jason-3 along-track data.

Reads WW3 output NetCDF and local Jason-3 L2 products in a separate subprocess, performs nearest-neighbor matching by space-time window, computes bias/RMSE/correlation, and generates SWH comparison scatter plots and spatial distribution maps.
"""

import os
import re
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from netCDF4 import Dataset, num2date
from datetime import datetime, timedelta
from ...support.translations import tr
from .photo_output import SUBDIR_JASON3_FIT, SUBDIR_JASON3_SATELLITE, prepare_photo_subdir
from .workers_utils import (
    ww3_resolve_lon_lat_names,
    ww3_hs_collocation_flat,
)

JASON3_FILE_PREFIXES = ("JA3_GPN_", "JA3_IPN_", "JA3_OPN_")
JASON3_MAX_REASONABLE_SWH = 12.0


def jason3_swh_output_path(result_folder: str, start_str: str, end_str: str, lon_lat) -> str:
    
    # [EN] [EN] Output path for Jason-3 SWH plots (including time range and lon/lat).
    """Jason-3 SWH 图输出路径（含时间范围与经纬度）。"""
    lon_min, lon_max, lat_min, lat_max = [float(v) for v in lon_lat[:4]]
    from .photo_output import photo_subdir

    photo_folder = photo_subdir(result_folder, SUBDIR_JASON3_SATELLITE)
    filename = (
        f"Jason3_SWH_{start_str}_{end_str}_"
        f"lon{lon_min:.2f}_{lon_max:.2f}_lat{lat_min:.2f}_{lat_max:.2f}.png"
    )
    return os.path.join(photo_folder, filename)


def _read_jason3_track_arrays(path: str):
    
    # [EN] [EN] Read Jason-3 along-track latitude, longitude and SWH; raise an exception if the file is corrupted/truncated.
    """读取 Jason-3 沿轨经纬度与 SWH；文件损坏/截断时抛出异常。"""
    with Dataset(path) as ds:
        lat_tmp = ds["data_01/latitude"][:].astype(float)
        lon_tmp = ds["data_01/longitude"][:].astype(float)
        swh_tmp = ds["data_01/ku/swh_ocean"][:].astype(float)
    return lat_tmp, lon_tmp, swh_tmp


def _jason3_open_error_message(path: str, error: Exception) -> str:
    text = str(error).lower()
    name = os.path.basename(path)
    if "truncated" in text or "eof" in text or "hdf5" in text or "superblock" in text:
        return tr(
            "plotting_jason_file_truncated",
            "⚠️ Jason-3 文件不完整（下载中断），已跳过：{file}，请重新下载该文件",
        ).format(file=name)
    return tr(
        "plotting_jason_skip_invalid",
        "⚠️ 跳过无效的 Jason-3 文件：{path} -> {error}",
    ).format(path=path, error=error)


def _read_jason3_wind_array(data_group, ku_group):
    
    # [EN] [EN] Read Jason-3 wind-speed variables, compatible with field names from different product versions.
    """读取 Jason-3 风速变量，兼容不同产品版本的字段命名。"""
    if 'wind_speed_alt_mle3' in ku_group.variables:
        return ku_group.variables['wind_speed_alt_mle3'][:].astype(float)
    if 'wind_speed_alt' in ku_group.variables:
        return ku_group.variables['wind_speed_alt'][:].astype(float)
    if 'wind_speed_alt_adaptive' in ku_group.variables:
        return ku_group.variables['wind_speed_alt_adaptive'][:].astype(float)
    if 'rad_wind_speed' in data_group.variables:
        return data_group.variables['rad_wind_speed'][:].astype(float)
    if 'wind_speed_mod_u' in data_group.variables and 'wind_speed_mod_v' in data_group.variables:
        wind_u = data_group.variables['wind_speed_mod_u'][:].astype(float)
        wind_v = data_group.variables['wind_speed_mod_v'][:].astype(float)
        return np.sqrt(wind_u ** 2 + wind_v ** 2)
    return None


def _match_ww3_jason3_worker(ww3_file, jason3_path, out_folder, log_queue, result_queue, max_dist_deg=0.125, time_window_hours=0.5):
    """在子进程中执行 WW3 与 Jason-3 沿轨 SWH 时空匹配与统计。

    参数
    ----
    ww3_file : str
        WW3 场输出 NetCDF 路径。
    jason3_path : str
        Jason-3 产品文件或目录。
    out_folder : str
        对比图与统计结果输出目录。
    log_queue / result_queue : multiprocessing.Queue
        日志与结果回传队列。
    max_dist_deg : float
        空间匹配最大距离（度）。
    time_window_hours : float
        时间匹配半窗宽（小时）。

    返回
    ----
    经 ``result_queue`` 发送 ``{'bias', 'rmse', 'corr', 'count'}`` 字典。
    
    [EN] [EN] Perform WW3 and Jason-3 along-track SWH space-time matching and statistics in a subprocess.
    
    Parameters
    ----------
    ww3_file : str
        Path to WW3 field output NetCDF.
    jason3_path : str
        Jason-3 product file or directory.
    out_folder : str
        Output directory for comparison plots and statistics.
    log_queue / result_queue : multiprocessing.Queue
        Log and result back-channel queues.
    max_dist_deg : float
        Maximum spatial matching distance (degrees).
    time_window_hours : float
        Half-width of the time matching window (hours).
    
    Returns
    -------
    Sends a ``{'bias', 'rmse', 'corr', 'count'}`` dict via ``result_queue``.
    """
    try:
        def log(msg):
            
            # [EN] [EN] Send a log message to the queue.
            """发送日志到队列"""
            try:
                log_queue.put(msg)
            except:
                pass

        log(tr("plotting_start_matching_worker", "🔄 开始匹配 WW3 和 Jason-3 数据（在子进程中执行，这可能需要一些时间，请稍候...）"))
        log("Reading WW3 data...")

        with Dataset(ww3_file, 'r') as nc:
            # 检查必需的变量是否存在
            available_vars = list(nc.variables.keys())

            lon_name, lat_name = ww3_resolve_lon_lat_names(nc)
            if not lon_name or not lat_name:
                error_msg = tr(
                    "plotting_missing_lon_lat_variables",
                    "❌ 无法识别经度/纬度变量（需 longitude/lon、latitude/lat 等）。可用变量: {vars}",
                ).format(vars=", ".join(available_vars))
                log(error_msg)
                log_queue.put("__DONE__")
                result_queue.put(None)
                return
            ww3_lon = nc.variables[lon_name][:]
            ww3_lat = nc.variables[lat_name][:]

            # 检查时间变量
            if 'time' not in nc.variables:
                error_msg = tr("plotting_missing_time_variable", "❌ 文件中没有 'time' 变量。可用变量: {vars}").format(vars=', '.join(available_vars))
                log(error_msg)
                log_queue.put("__DONE__")
                result_queue.put(None)
                return
            time_var_obj = nc.variables['time']
            time_ww3 = time_var_obj[:].astype(float)

            # 检查波高变量（尝试多个可能的变量名）
            wave_height_var = None
            possible_vars = ['hs', 'swh', 'wave_height', 'HS', 'SWH']
            for var_name in possible_vars:
                if var_name in nc.variables:
                    wave_height_var = var_name
                    break

            if wave_height_var is None:
                error_msg = tr("plotting_missing_hs_variable_jason", "❌ 文件中没有找到波高变量（尝试了: {tried}）。可用变量: {vars}").format(
                    tried=', '.join(possible_vars),
                    vars=', '.join(available_vars)
                )
                log(error_msg)
                log_queue.put("__DONE__")
                result_queue.put(None)
                return

            ww3_swh = nc.variables[wave_height_var][:]

        ww3_lon = np.asarray(ww3_lon, dtype=float)
        ww3_lat = np.asarray(ww3_lat, dtype=float)
        ww3_lon = ((ww3_lon + 180.0) % 360.0) - 180.0

        nt = len(time_ww3)
        try:
            lon1, lat1, hs_nt_n, lon_lat = ww3_hs_collocation_flat(nt, ww3_lon, ww3_lat, ww3_swh)
        except Exception as e:
            log(
                tr(
                    "plotting_jason3_ww3_grid_prepare_failed",
                    "❌ WW3 波高/经纬度维数无法用于 Jason 匹配（支持规则网格或非结构 time×node）：{err}",
                ).format(err=e)
            )
            log_queue.put("__DONE__")
            result_queue.put(None)
            return

        hs_nt_n = np.asarray(hs_nt_n, dtype=float)
        hs_nt_n[(hs_nt_n < 0) | (hs_nt_n > 50)] = np.nan

        log(f"WW3 lon range: [{lon_lat[0]:.2f}, {lon_lat[1]:.2f}]")
        log(f"WW3 lat range: [{lon_lat[2]:.2f}, {lon_lat[3]:.2f}]")
        log(f"WW3 time steps: {len(time_ww3)}")
        log(f"WW3 collocation points per step: {hs_nt_n.shape[1]}")

        _units = getattr(time_var_obj, 'units', 'days since 1990-01-01')
        _cal = getattr(time_var_obj, 'calendar', 'standard')
        _decoded = num2date(time_ww3, _units, calendar=_cal,
                            only_use_cftime_datetimes=False, only_use_python_datetimes=False)
        timesec = [
            datetime(dt.year, dt.month, dt.day,
                     getattr(dt, "hour", 0), getattr(dt, "minute", 0),
                     getattr(dt, "second", 0))
            for dt in _decoded
        ]
        T = np.array([dt.strftime('%Y%m%d%H%M%S') for dt in timesec])
        log(f"WW3 time range: {timesec[0]} to {timesec[-1]}")

        log(f"Matching region: lon[{lon_lat[0]}, {lon_lat[1]}], lat[{lon_lat[2]}, {lon_lat[3]}]")

        swh_jason3 = []
        swh_ww3 = []

        log(tr("plotting_processing_timesteps", "🔄 处理 {count} 个时间步，这可能需要一些时间...").format(count=len(T)))
        total_matched = 0

        # 动态调整更新频率
        update_interval = max(1, len(T) // 50)
        if update_interval < 10:
            update_interval = 10
        elif update_interval > 50:
            update_interval = 50

        # 导入必要的函数（在子进程中重新导入）
        from pathlib import Path

        def haversine_distance(lat1, lon1, lat2, lon2):
            
            # [EN] [EN] Compute the distance (degrees) between two points.
            """计算两点间的距离（度）"""
            lat1_rad = np.radians(lat1)
            lon1_rad = np.radians(lon1)
            lat2_rad = np.radians(lat2)
            lon2_rad = np.radians(lon2)
            dlat = lat2_rad - lat1_rad
            dlon = lon2_rad - lon1_rad
            a = np.sin(dlat / 2) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2) ** 2
            c = 2 * np.arcsin(np.sqrt(a))
            R = 6371.0
            distance_km = R * c
            distance_deg = distance_km / 111.0
            return distance_deg

        def read_jason3_chen(lon_lat, timeinput, jasonpath):
            
            # [EN] [EN] Read Jason-3 data (Chen method) - subprocess version.
            """读取 Jason-3 数据（Chen 方法）- 子进程版本"""
            jasonpath = Path(jasonpath)
            timeinput = np.array(timeinput)
            if timeinput.ndim == 2:
                start_dt = datetime(*timeinput[0, :6].astype(int))
                end_dt = datetime(*timeinput[1, :6].astype(int))
            else:
                start_dt = datetime(int(timeinput[0]), int(timeinput[1]), int(timeinput[2]), 0, 0, 0)
                end_dt = start_dt + timedelta(days=1)

            if not jasonpath.exists():
                return {
                    'ja_time': np.array([]),
                    'longitude': np.array([]),
                    'latitude': np.array([]),
                    'wind': np.array([]),
                    'swh': np.array([])
                }

            ncfiles = []
            if timeinput.ndim == 1:
                year = f"{int(timeinput[0]):04d}"
                month = f"{int(timeinput[1]):02d}"
                day = f"{int(timeinput[2]):02d}"
                # 支持 JA3_GPN_ / JA3_IPN_ / JA3_OPN_ 三种格式
                pattern_gpn = f"JA3_GPN_*{year}{month}{day}_*.nc"
                pattern_ipn = f"JA3_IPN_*{year}{month}{day}_*.nc"
                pattern_opn = f"JA3_OPN_*{year}{month}{day}_*.nc"
                ncfiles = list(jasonpath.glob(pattern_gpn)) + list(jasonpath.glob(pattern_ipn)) + list(jasonpath.glob(pattern_opn))
            else:
                # 支持 JA3_GPN_ / JA3_IPN_ / JA3_OPN_ 三种格式
                all_files = (
                    list(jasonpath.glob('JA3_GPN_*.nc')) +
                    list(jasonpath.glob('JA3_IPN_*.nc')) +
                    list(jasonpath.glob('JA3_OPN_*.nc'))
                )
                pattern = re.compile(r'(\d{8}_\d{6})_(\d{8}_\d{6})')
                start_dt = datetime(*timeinput[0, :6].astype(int))
                end_dt = datetime(*timeinput[1, :6].astype(int))
                for filepath in all_files:
                    fname = filepath.name
                    match = pattern.search(fname)
                    if not match:
                        continue
                    file_start = datetime.strptime(match.group(1), '%Y%m%d_%H%M%S')
                    file_end = datetime.strptime(match.group(2), '%Y%m%d_%H%M%S')
                    if file_end >= start_dt and file_start <= end_dt:
                        ncfiles.append(filepath)

            if not ncfiles:
                return {
                    'ja_time': np.array([]),
                    'longitude': np.array([]),
                    'latitude': np.array([]),
                    'wind': np.array([]),
                    'swh': np.array([])
                }

            ncfiles = list(set(ncfiles))
            ncfiles.sort()

            longitude_list = []
            latitude_list = []
            wind_list = []
            swh_list = []
            time_list = []

            for filepath in ncfiles:
                try:
                    with Dataset(filepath, 'r') as nc:
                        data_group = nc.groups['data_01']
                        latitude_tmp = data_group.variables['latitude'][:].astype(float)
                        longitude_tmp = data_group.variables['longitude'][:].astype(float)
                        time_tmp = data_group.variables['time'][:].astype(float)
                        ku_group = data_group.groups['ku']
                        swh_tmp = ku_group.variables['swh_ocean'][:].astype(float)
                        wind_tmp = _read_jason3_wind_array(data_group, ku_group)
                        has_wind = wind_tmp is not None
                        longitude_tmp = ((longitude_tmp + 180.0) % 360.0) - 180.0
                        idx_spatial = ((longitude_tmp >= lon_lat[0]) & (longitude_tmp <= lon_lat[1]) &
                                       (latitude_tmp >= lon_lat[2]) & (latitude_tmp <= lon_lat[3]))
                        if np.sum(idx_spatial) == 0:
                            continue
                        latitude_tmp = latitude_tmp[idx_spatial]
                        longitude_tmp = longitude_tmp[idx_spatial]
                        swh_tmp = swh_tmp[idx_spatial]
                        time_tmp = time_tmp[idx_spatial]
                        time_tmp = time_tmp / (24 * 60 * 60)
                        ref_date = datetime(2000, 1, 1)
                        start_days = (start_dt - ref_date).total_seconds() / (24 * 60 * 60)
                        end_days = (end_dt - ref_date).total_seconds() / (24 * 60 * 60)
                        idx_time = (time_tmp >= start_days) & (time_tmp <= end_days)
                        if np.sum(idx_time) == 0:
                            continue
                        latitude_tmp = latitude_tmp[idx_time]
                        longitude_tmp = longitude_tmp[idx_time]
                        swh_tmp = swh_tmp[idx_time]
                        time_tmp = time_tmp[idx_time]
                        if has_wind:
                            wind_tmp = wind_tmp[idx_spatial]
                            wind_tmp = wind_tmp[idx_time]
                        else:
                            wind_tmp = np.full(swh_tmp.shape, np.nan, dtype=float)
                        invalid_values = [0, 32767, 9999, 65535]
                        valid_idx = (~np.isnan(swh_tmp) &
                                     (swh_tmp > 0) &
                                     (swh_tmp <= JASON3_MAX_REASONABLE_SWH) &
                                     ~np.isin(swh_tmp, invalid_values))
                        if has_wind:
                            valid_idx &= (~np.isnan(wind_tmp) & ~np.isin(wind_tmp, invalid_values))
                        if np.sum(valid_idx) == 0:
                            continue
                        latitude_tmp = latitude_tmp[valid_idx]
                        longitude_tmp = longitude_tmp[valid_idx]
                        wind_tmp = wind_tmp[valid_idx]
                        swh_tmp = swh_tmp[valid_idx]
                        time_tmp = time_tmp[valid_idx]
                        if len(latitude_tmp) > 0:
                            latitude_list.append(latitude_tmp)
                            longitude_list.append(longitude_tmp)
                            wind_list.append(wind_tmp)
                            swh_list.append(swh_tmp)
                            time_list.append(time_tmp)
                except Exception:
                    continue

            if not latitude_list:
                return {
                    'ja_time': np.array([]),
                    'longitude': np.array([]),
                    'latitude': np.array([]),
                    'wind': np.array([]),
                    'swh': np.array([])
                }

            latitude = np.concatenate(latitude_list)
            longitude = np.concatenate(longitude_list)
            wind = np.concatenate(wind_list)
            swh = np.concatenate(swh_list)
            time_days = np.concatenate(time_list)

            reference_date = datetime(2000, 1, 1)
            ja_time = np.zeros((len(time_days), 6))
            for i, days in enumerate(time_days):
                dt = reference_date + timedelta(days=float(days))
                ja_time[i] = [dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second]

            return {
                'ja_time': ja_time,
                'longitude': longitude,
                'latitude': latitude,
                'wind': wind,
                'swh': swh
            }

        for i in range(len(T)):
            # 动态调整更新频率，减少日志更新
            if (i + 1) % update_interval == 0 or i == 0:
                progress_pct = int((i + 1) / len(T) * 100)
                log(tr("plotting_matching_progress", "📊 进度: {current}/{total} ({percent}%) - 已匹配 {matched} 个点").format(current=i + 1, total=len(T), percent=progress_pct, matched=total_matched))

            ww3_swh1 = hs_nt_n[i, :]
            year = int(T[i][0:4])
            month = int(T[i][4:6])
            day = int(T[i][6:8])
            hour = int(T[i][8:10])

            window = time_window_hours
            timeinput = np.zeros((2, 6))
            start_dt = datetime(year, month, day, hour, 0, 0) - timedelta(hours=window)
            end_dt = datetime(year, month, day, hour, 0, 0) + timedelta(hours=window)
            timeinput[0, :] = [start_dt.year, start_dt.month, start_dt.day, start_dt.hour, start_dt.minute,
                               start_dt.second]
            timeinput[1, :] = [end_dt.year, end_dt.month, end_dt.day, end_dt.hour, end_dt.minute, end_dt.second]

            jason3 = read_jason3_chen(lon_lat, timeinput, jason3_path)
            j3_lat = jason3['latitude']
            j3_lon = jason3['longitude']
            j3_swh = jason3['swh']

            if len(j3_lat) == 0:
                continue

            valid_mask = ~np.isnan(ww3_swh1)
            valid_indices = np.where(valid_mask)[0]

            if len(valid_indices) == 0:
                continue

            for j in valid_indices:
                distances = haversine_distance(lat1[j], lon1[j], j3_lat, j3_lon)
                min_dist = np.min(distances)
                if min_dist < max_dist_deg:
                    index = np.argmin(distances)
                    swh_jason3.append(j3_swh[index])
                    swh_ww3.append(ww3_swh1[j])
                    total_matched += 1

        swh_jason3 = np.array(swh_jason3)
        swh_ww3 = np.array(swh_ww3)

        log('======================================================================')
        log('Matching completed!')
        log(f'Total matched points: {len(swh_jason3)}')

        os.makedirs(out_folder, exist_ok=True)

        if len(swh_jason3) > 0:
            x = swh_jason3
            y = swh_ww3
            diff = np.abs(y - x)
            valid = (~np.isnan(x)) & (~np.isnan(y))
            xv = x[valid]
            yv = y[valid]
            dv = diff[valid]
            cutoff = 30
            idx = dv <= cutoff
            xf = xv[idx]
            yf = yv[idx]
            if len(xf) == 0 or len(yf) == 0:
                xf = xv
                yf = yv

            bias = float(np.nanmean(yf - xf)) if len(yf) > 0 else np.nan
            rmse = float(np.sqrt(np.nanmean((yf - xf) ** 2))) if len(yf) > 0 else np.nan
            corr = float(np.corrcoef(xf, yf)[0, 1]) if (
                        len(xf) > 1 and np.nanstd(xf) > 0 and np.nanstd(yf) > 0) else np.nan

            np.savez(os.path.join(out_folder, 'matching_results.npz'), swh_jason3=swh_jason3, swh_ww3=swh_ww3)
            log(f"Results saved to {os.path.join(out_folder, 'matching_results.npz')}")

            try:
                # 切换到 Agg 后端
                original_backend = matplotlib.get_backend()
                matplotlib.use("Agg")

                max_val = float(np.nanmax(np.concatenate([xf, yf]))) if len(xf) > 0 else 10.0
                upper = max(1.0, max_val * 1.02)
                fig = plt.figure(figsize=(8, 8), dpi=300)
                plt.scatter(xf, yf, s=8, c='royalblue', alpha=0.6)
                plt.xlabel('Jason-3 (m)')
                plt.ylabel('WW3 (m)')
                plt.title('Linear fit of simulation and observation')
                plt.xlim([0, upper])
                plt.ylim([0, upper])
                plt.plot([0, upper], [0, upper], 'k--', linewidth=1.5)
                r_text = f"R = {corr:.3f}" if np.isfinite(corr) else "R = N/A"
                txt = f"{r_text}\nBias = {bias:.3f}\nRMSE = {rmse:.3f}"
                plt.text(0.05 * upper, 0.95 * upper, txt, va='top')
                plt.grid(False)
                plt.tight_layout()

                photo_folder = prepare_photo_subdir(out_folder, SUBDIR_JASON3_FIT)
                out_png = os.path.join(photo_folder, 'ww3_jason3_comparison.png')
                plt.savefig(out_png, dpi=300, bbox_inches='tight')
                plt.close(fig)

                matplotlib.use(original_backend)
            except ImportError:
                log('Matplotlib not available, skipping plots')

            result = {'bias': bias, 'rmse': rmse, 'corr': corr, 'count': len(swh_jason3)}
        else:
            log('No matching points found. Please check:')
            log('  1. Jason-3 data temporal coverage')
            log('  2. Jason-3 data spatial coverage in the region')
            log('  3. Time window settings')
            result = {'bias': None, 'rmse': None, 'corr': None, 'count': 0}

        # 发送完成信号和结果
        log_queue.put("__DONE__")
        result_queue.put(result)

    except Exception as e:
        import traceback
        error_msg = tr("plotting_worker_process_failed", "❌ 子进程处理失败：{error}\n{details}").format(error=e, details=traceback.format_exc())
        try:
            log_queue.put(error_msg)
            log_queue.put("__DONE__")
        except:
            pass
        result_queue.put({'bias': None, 'rmse': None, 'corr': None, 'count': 0})


def _run_jason3_swh_worker(lon_lat, time_range, jason_folder, out_folder, log_queue, result_queue,
                           FIGSIZE=(14, 10), DPI=300, UPSAMPLE_FACTOR=5, CLIM_PCT=99):
    """在子进程中绘制 Jason-3 沿轨 SWH 空间分布图（不依赖 WW3 匹配）。

    根据给定经纬度范围与时间窗筛选本地 Jason-3 文件，生成填色/散点对比图并
    通过 ``result_queue`` 回传输出路径列表。
    
    [EN] [EN] Plot Jason-3 along-track SWH spatial distribution in a subprocess (does not depend on WW3 matching).
    
    Filters local Jason-3 files by the given lon/lat range and time window, generates filled/scatter comparison maps, and returns the output path list via ``result_queue``.
    """
    try:
        def log(msg):
            
            # [EN] [EN] Send a log message to the queue.
            """发送日志到队列"""
            try:
                log_queue.put(msg)
            except:
                pass

        # 解析时间（开始时间 00:00:00，结束时间 23:59:59）
        start_str, end_str = time_range

        log(tr("plotting_jason_processing_start", "🔄 开始处理 Jason-3 数据 ..."))
        timeinput = [
            [int(start_str[0:4]), int(start_str[4:6]), int(start_str[6:8]), 0, 0, 0],
            [int(end_str[0:4]), int(end_str[4:6]), int(end_str[6:8]), 23, 59, 59]
        ]
        start_dt = datetime(*timeinput[0])
        end_dt = datetime(*timeinput[1])

        lon_min, lon_max, lat_min, lat_max = lon_lat

        # 确保 lon_min < lon_max（对于负经度，lon_min 应该更负）
        if lon_min > lon_max:
            lon_min, lon_max = lon_max, lon_min
            log(tr("plotting_lon_range_error", "⚠️ 检测到经度范围顺序错误，已自动修正：lon[{min}:{max}]").format(min=lon_min, max=lon_max))

        # 确保 lat_min < lat_max（对于负纬度，lat_min 应该更负）
        if lat_min > lat_max:
            lat_min, lat_max = lat_max, lat_min
            log(tr("plotting_lat_range_error", "⚠️ 检测到纬度范围顺序错误，已自动修正：lat[{min}:{max}]").format(min=lat_min, max=lat_max))

        log("\n" + tr("plotting_jason_searching_files", "=========== Jason-3: Searching Files ==========="))

        # 找到时间范围内的文件（包括 GDR / IGDR / OGDR）
        time_pattern = r"(\d{8}_\d{6})_(\d{8}_\d{6})"
        nc_files = [
            f for f in os.listdir(jason_folder)
            if f.endswith(".nc") and f.startswith(JASON3_FILE_PREFIXES)
        ]

        valid_files = []
        local_file_ranges = []

        for f in nc_files:
            m = re.search(time_pattern, f)
            if not m:
                continue
            t1 = datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
            t2 = datetime.strptime(m.group(2), "%Y%m%d_%H%M%S")
            if t2 >= start_dt and t1 <= end_dt:
                valid_files.append(f)
                local_file_ranges.append((t1, t2))

        valid_files = sorted(valid_files)
        if not valid_files:
            log(tr("plotting_jason_no_files_in_range", "❌ 未找到符合时间范围的 Jason-3 文件"))
            log_queue.put("__DONE__")
            result_queue.put(None)
            return

        log(tr("plotting_jason_files_found", "找到 {count} 个文件").format(count=len(valid_files)))

        # 检查是否有缺失的天数
        # 只检测边缘日期（开始日期和结束日期），中间日期默认认为完整
        missing_days = []
        start_date = start_dt.date()
        end_date = end_dt.date()


        # 只检查开始日期和结束日期
        dates_to_check = [start_date]
        if end_date != start_date:
            dates_to_check.append(end_date)

        for current_date in dates_to_check:
            # 检查这一天是否有数据文件覆盖
            # 使用更严格的条件：文件必须覆盖这一天的至少一部分时间（不仅仅是日期重叠）
            has_data = False
            day_start = datetime.combine(current_date, datetime.min.time())
            day_end = datetime.combine(current_date, datetime.max.time())

            # 检查这一天是否有文件覆盖，以及是否有连续的文件覆盖到这一天结束
            day_covered_ranges = []
            for file_start, file_end in local_file_ranges:
                # 检查文件时间范围是否与这一天有重叠
                if file_end >= day_start and file_start <= day_end:
                    day_covered_ranges.append((file_start, file_end))

            if day_covered_ranges:
                # 找到覆盖这一天的所有文件，检查是否连续覆盖到这一天结束
                # 排序文件时间范围
                day_covered_ranges.sort(key=lambda x: x[0])

                # 检查是否覆盖到这一天结束（允许有小的间隙，比如几分钟）
                max_end_time = max(f_end for _, f_end in day_covered_ranges)
                day_noon = datetime.combine(current_date, datetime.min.time().replace(hour=12))
                day_evening = datetime.combine(current_date, datetime.min.time().replace(hour=18))

                # 如果文件结束时间在当天 12 点之前，检查是否有后续文件继续覆盖
                if max_end_time < day_noon:
                    # 检查是否有文件从 max_end_time 之后开始，继续覆盖这一天
                    has_continuation = False
                    for f_start, f_end in local_file_ranges:
                        # 允许最多 30 分钟的间隙（文件之间可能有小的间隙）
                        gap_threshold = timedelta(minutes=30)
                        if f_start <= max_end_time + gap_threshold and f_end > max_end_time:
                            has_continuation = True
                            break

                    if not has_continuation:
                        missing_days.append(current_date)
                        has_data = True  # 设置 has_data = True 避免在后续 if not has_data 中重复添加
                    else:
                        has_data = True
                elif max_end_time < day_evening:
                    # 文件结束时间在 12-18 点之间，检查是否有后续文件
                    has_continuation = False
                    for f_start, f_end in local_file_ranges:
                        gap_threshold = timedelta(minutes=30)
                        if f_start <= max_end_time + gap_threshold and f_end > max_end_time:
                            has_continuation = True
                            break

                    if has_continuation:
                        has_data = True
                    else:
                        # 没有后续文件，但已经覆盖到下午，认为基本完整
                        has_data = True
                else:
                    # 文件结束时间在 18 点之后，认为数据完整
                    has_data = True

            if not has_data:
                missing_days.append(current_date)

        # 去重缺失日期列表（避免重复）
        missing_days = list(set(missing_days))
        missing_days.sort()  # 排序以便于查看

        # 如果发现缺失日期，直接记录提示（不触发下载）
        if missing_days:
            missing_days_str = [d.strftime('%Y%m%d') for d in missing_days]
            log(tr("plotting_jason_missing_days_found", "⚠️ 发现 {count} 个缺失的天数：{days}").format(count=len(missing_days), days=', '.join(missing_days_str)))

        # 读取数据
        longitude = []
        latitude = []
        swh = []

        # 收集所有文件的原始数据范围（筛选前）
        all_lon_min = []
        all_lon_max = []
        all_lat_min = []
        all_lat_max = []

        for fname in valid_files:
            path = os.path.join(jason_folder, fname)

            # 某些文件可能不是有效的 NetCDF（例如早期下载到的 HTML 登录页面），需要跳过
            try:
                lat_tmp, lon_tmp, swh_tmp = _read_jason3_track_arrays(path)
            except Exception as e:
                log(_jason3_open_error_message(path, e))
                continue

            # 将经度从 0-360 度转换为 -180 到 180 度
            lon_tmp = np.where(lon_tmp > 180, lon_tmp - 360, lon_tmp)

            # 确保 lon_tmp 和 lat_tmp 是一维数组且长度相同
            lon_tmp = lon_tmp.flatten()
            lat_tmp = lat_tmp.flatten()
            swh_tmp = swh_tmp.flatten()

            # 确保长度一致
            min_len = min(len(lon_tmp), len(lat_tmp), len(swh_tmp))
            if min_len < len(lon_tmp):
                lon_tmp = lon_tmp[:min_len]
            if min_len < len(lat_tmp):
                lat_tmp = lat_tmp[:min_len]
            if min_len < len(swh_tmp):
                swh_tmp = swh_tmp[:min_len]

            # 收集原始数据范围（筛选前）
            if len(lat_tmp) > 0:
                all_lon_min.append(lon_tmp.min())
                all_lon_max.append(lon_tmp.max())
                all_lat_min.append(lat_tmp.min())
                all_lat_max.append(lat_tmp.max())

            # 调试：显示文件中的数据范围

            # =========================
            # 正确的经纬度筛选（统一到 [-180, 180] 后）
            # =========================

            # 经度筛选
            if lon_min <= lon_max:
                # 普通情况：不跨 180° 经线
                lon_mask = (lon_tmp >= lon_min) & (lon_tmp <= lon_max)
            else:
                # 跨 180° 经线（例如 170 → -170）
                lon_mask = (lon_tmp >= lon_min) | (lon_tmp <= lon_max)

            # 纬度筛选（永远是简单区间）
            lat_mask = (lat_tmp >= lat_min) & (lat_tmp <= lat_max)

            # 联合掩码
            mask = lon_mask & lat_mask

            lat_tmp = lat_tmp[mask]
            lon_tmp = lon_tmp[mask]
            swh_tmp = swh_tmp[mask]

            if len(lat_tmp) > 0:
                log(tr("plotting_jason_before_filter", "   去除无效值前: {count} 个数据点").format(count=len(lat_tmp)))

            # 去除无效值
            mask2 = (~np.isnan(swh_tmp)) & (swh_tmp > 0) & (swh_tmp <= JASON3_MAX_REASONABLE_SWH)
            lat_tmp = lat_tmp[mask2]
            lon_tmp = lon_tmp[mask2]
            swh_tmp = swh_tmp[mask2]

            if len(lat_tmp) > 0:
                log(tr("plotting_jason_after_filter", "   去除无效值后: {count} 个有效数据点").format(count=len(lat_tmp)))

            latitude.extend(lat_tmp)
            longitude.extend(lon_tmp)
            swh.extend(swh_tmp)

        if len(swh) == 0:
            log(tr("plotting_jason_no_data_in_region", "❌ 该区域无 Jason-3 数据"))
            # 即使没有有效数据点，也检查是否有缺失日期（可能因为缺少某些日期的数据）
            # 重新检查缺失日期（只检查边缘日期）
            missing_days_retry = []
            start_date = start_dt.date()
            end_date = end_dt.date()

            # 只检查开始日期和结束日期
            dates_to_check = [start_date]
            if end_date != start_date:
                dates_to_check.append(end_date)

            for current_date in dates_to_check:
                has_file = False
                for file_start, file_end in local_file_ranges:
                    if file_end.date() >= current_date and file_start.date() <= current_date:
                        has_file = True
                        break

                if not has_file:
                    missing_days_retry.append(current_date)

            # 如果有缺失日期，仅记录提示（不触发下载）
            if missing_days_retry:
                missing_days_str = [d.strftime('%Y%m%d') for d in missing_days_retry]
                log(tr("plotting_jason_files_found_but_missing_days", "⚠️ 虽然找到文件，但检测到 {count} 个缺失的天数：{days}").format(count=len(missing_days_retry), days=', '.join(missing_days_str)))

            # 如果没有缺失日期，说明文件存在但数据点不在区域内
            log(tr("plotting_jason_no_valid_points", "⚠️ 文件存在，但该区域无有效数据点（可能是 Jason-3 轨道未经过该区域）"))
            log_queue.put("__DONE__")
            result_queue.put(None)
            return

        longitude = np.array(longitude)
        latitude = np.array(latitude)
        # 处理 masked array，转换为普通数组并处理 NaN
        swh = np.ma.filled(np.array(swh), np.nan)

        log(tr("plotting_jason_read_success", "✅ Jason-3 数据读取成功"))

        # 网格化 - 使用用户输入的筛选范围生成网格（与旧代码保持一致）
        lon_grid = np.linspace(lon_min, lon_max, int((lon_max - lon_min) * UPSAMPLE_FACTOR))
        lat_grid = np.linspace(lat_min, lat_max, int((lat_max - lat_min) * UPSAMPLE_FACTOR))

        SWH_grid = np.full((len(lat_grid), len(lon_grid)), np.nan)

        lon_idx = np.searchsorted(lon_grid, longitude)
        lat_idx = np.searchsorted(lat_grid, latitude)
        lon_idx[lon_idx >= len(lon_grid)] = len(lon_grid) - 1
        lat_idx[lat_idx >= len(lat_grid)] = len(lat_grid) - 1

        for xi, yi, val in zip(lon_idx, lat_idx, swh):
            SWH_grid[yi, xi] = val

        # 色阶
        vmax = np.nanpercentile(SWH_grid, CLIM_PCT)
        vmin = 0

        photo_folder = prepare_photo_subdir(out_folder, SUBDIR_JASON3_SATELLITE)
        out_file = jason3_swh_output_path(out_folder, start_str, end_str, lon_lat)

        # 切换到 Agg 后端用于生成图片
        original_backend = matplotlib.get_backend()
        matplotlib.use("Agg")

        fig = plt.figure(figsize=FIGSIZE)
        ax = plt.axes(projection=ccrs.PlateCarree())
        # 使用用户输入的筛选范围设置 extent（与旧代码保持一致）
        ax.set_extent([lon_min, lon_max, lat_min, lat_max])

        ax.add_feature(cfeature.LAND, facecolor='0.92')
        ax.coastlines('10m', lw=0.6)

        pcm = ax.pcolormesh(
            lon_grid, lat_grid, SWH_grid,
            cmap="turbo",
            shading="auto",
            vmin=vmin,
            vmax=vmax,
            transform=ccrs.PlateCarree()
        )

        cb = plt.colorbar(pcm, pad=0.02)
        cb.set_label("SWH (m)")

        ax.set_title(f"Jason-3 SWH  ({start_str} ~ {end_str})", fontsize=14)

        plt.savefig(out_file, dpi=DPI, bbox_inches="tight")
        plt.close(fig)

        # 恢复后端
        matplotlib.use(original_backend)

        log(tr("plotting_jason_output_success", "✅ 输出成功: {path}").format(path=out_file))

        # 发送完成信号和结果
        log_queue.put("__DONE__")
        result_queue.put(out_file)

    except Exception as e:
        import traceback
        error_msg = tr("plotting_worker_process_failed", "❌ 子进程处理失败：{error}\n{details}").format(error=e, details=traceback.format_exc())
        try:
            log_queue.put(error_msg)
            log_queue.put("__DONE__")
        except:
            pass
        result_queue.put(None)
