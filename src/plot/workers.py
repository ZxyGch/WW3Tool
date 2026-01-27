import os
import re
import glob
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib import colorbar
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from matplotlib import cm
from netCDF4 import Dataset, num2date
import netCDF4 as nc
from datetime import datetime, timedelta
import cv2
from setting.language_manager import tr
try:
    import wavespectra
    from wavespectra import SpecArray
    HAS_WAVESPECTRA = True
except ImportError:
    HAS_WAVESPECTRA = False

def _match_ww3_jason3_worker(ww3_file, jason3_path, out_folder, log_queue, result_queue, max_dist_deg=0.125, time_window_hours=0.5):
    """在子进程中执行匹配计算的独立函数"""
    try:
        # 在子进程中加载当前语言设置
        from setting.config import load_config
        from setting.language_manager import load_language
        config = load_config()
        language_code = config.get("LANGUAGE", "zh_CN")
        load_language(language_code)
        
        def log(msg):
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
            
            # 检查经度变量
            if 'longitude' not in nc.variables:
                error_msg = tr("plotting_missing_longitude_variable", "❌ 文件中没有 'longitude' 变量。可用变量: {vars}").format(vars=', '.join(available_vars))
                log(error_msg)
                log_queue.put("__DONE__")
                result_queue.put(None)
                return
            ww3_lon = nc.variables['longitude'][:].astype(float)
            
            # 检查纬度变量
            if 'latitude' not in nc.variables:
                error_msg = tr("plotting_missing_latitude_variable", "❌ 文件中没有 'latitude' 变量。可用变量: {vars}").format(vars=', '.join(available_vars))
                log(error_msg)
                log_queue.put("__DONE__")
                result_queue.put(None)
                return
            ww3_lat = nc.variables['latitude'][:].astype(float)
            
            # 检查时间变量
            if 'time' not in nc.variables:
                error_msg = tr("plotting_missing_time_variable", "❌ 文件中没有 'time' 变量。可用变量: {vars}").format(vars=', '.join(available_vars))
                log(error_msg)
                log_queue.put("__DONE__")
                result_queue.put(None)
                return
            time_ww3 = nc.variables['time'][:].astype(float)
            
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
            
            ww3_swh = nc.variables[wave_height_var][:].astype(float)

        ww3_lon = ((ww3_lon + 180.0) % 360.0) - 180.0
        ww3_swh[(ww3_swh < 0) | (ww3_swh > 50)] = np.nan

        log(f"WW3 lon range: [{ww3_lon.min():.2f}, {ww3_lon.max():.2f}]")
        log(f"WW3 lat range: [{ww3_lat.min():.2f}, {ww3_lat.max():.2f}]")
        log(f"WW3 time steps: {len(time_ww3)}")

        nx = len(ww3_lon)
        ny = len(ww3_lat)
        lon_grid, lat_grid = np.meshgrid(ww3_lon, ww3_lat, indexing='xy')
        lon1 = lon_grid.ravel()
        lat1 = lat_grid.ravel()

        reference_date = datetime(1990, 1, 1, 0, 0, 0)
        timesec = [reference_date + timedelta(days=float(t)) for t in time_ww3]
        T = np.array([dt.strftime('%Y%m%d%H%M%S') for dt in timesec])
        log(f"WW3 time range: {timesec[0]} to {timesec[-1]}")

        lon_lat = [ww3_lon.min(), ww3_lon.max(), ww3_lat.min(), ww3_lat.max()]
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
                # 支持 JA3_GPN_ 和 JA3_IPN_ 两种格式
                pattern_gpn = f"JA3_GPN_*{year}{month}{day}_*.nc"
                pattern_ipn = f"JA3_IPN_*{year}{month}{day}_*.nc"
                ncfiles = list(jasonpath.glob(pattern_gpn)) + list(jasonpath.glob(pattern_ipn))
            else:
                # 支持 JA3_GPN_ 和 JA3_IPN_ 两种格式
                all_files = list(jasonpath.glob('JA3_GPN_*.nc')) + list(jasonpath.glob('JA3_IPN_*.nc'))
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
                        wind_tmp = data_group.variables['wind_speed_alt_mle3'][:].astype(float)
                        ku_group = data_group.groups['ku']
                        swh_tmp = ku_group.variables['swh_ocean'][:].astype(float)
                        longitude_tmp = ((longitude_tmp + 180.0) % 360.0) - 180.0
                        idx_spatial = ((longitude_tmp >= lon_lat[0]) & (longitude_tmp <= lon_lat[1]) &
                                       (latitude_tmp >= lon_lat[2]) & (latitude_tmp <= lon_lat[3]))
                        if np.sum(idx_spatial) == 0:
                            continue
                        latitude_tmp = latitude_tmp[idx_spatial]
                        longitude_tmp = longitude_tmp[idx_spatial]
                        wind_tmp = wind_tmp[idx_spatial]
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
                        wind_tmp = wind_tmp[idx_time]
                        swh_tmp = swh_tmp[idx_time]
                        time_tmp = time_tmp[idx_time]
                        invalid_values = [0, 32767, 9999, 65535]
                        valid_idx = (~np.isnan(swh_tmp) &
                                     ~np.isnan(wind_tmp) &
                                     ~np.isin(swh_tmp, invalid_values) &
                                     ~np.isin(wind_tmp, invalid_values))
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

            ww3_swh1 = ww3_swh[i, :, :].ravel()
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

        log('============================================================')
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

                # 保存到 photo 文件夹
                photo_folder = os.path.join(out_folder, 'photo')
                os.makedirs(photo_folder, exist_ok=True)
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
    """在子进程中执行 Jason-3 SWH 绘图计算的独立函数"""
    try:
        # 在子进程中加载当前语言设置
        from setting.config import load_config
        from setting.language_manager import load_language
        config = load_config()
        language_code = config.get("LANGUAGE", "zh_CN")
        load_language(language_code)
        
        def log(msg):
            """发送日志到队列"""
            try:
                log_queue.put(msg)
            except:
                pass
        
        log(tr("plotting_jason_processing_start", "🔄 开始处理 Jason-3 数据 ..."))
        
        # 解析时间（开始时间 00:00:00，结束时间 23:59:59）
        start_str, end_str = time_range
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
        
        # 找到时间范围内的文件（包括GDR和IGDR）
        time_pattern = r"(\d{8}_\d{6})_(\d{8}_\d{6})"
        nc_files_gdr = [f for f in os.listdir(jason_folder) if f.startswith("JA3_GPN_") and f.endswith(".nc")]
        nc_files_igdr = [f for f in os.listdir(jason_folder) if f.startswith("JA3_IPN_") and f.endswith(".nc")]
        nc_files = nc_files_gdr + nc_files_igdr
        
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
                with Dataset(path) as ds:
                    lat_tmp = ds["data_01/latitude"][:].astype(float)
                    lon_tmp = ds["data_01/longitude"][:].astype(float)
                    swh_tmp = ds["data_01/ku/swh_ocean"][:].astype(float)
            except Exception as e:
                log(tr("plotting_jason_skip_invalid", "⚠️ 跳过无效的 Jason-3 文件：{path} -> {error}").format(path=path, error=e))
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
            mask2 = (~np.isnan(swh_tmp)) & (swh_tmp != 0)
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
        
        log(tr("plotting_jason_read_success", "Jason-3 数据读取成功"))
        
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
        
        # 绘图，保存到 photo 文件夹
        photo_folder = os.path.join(out_folder, 'photo')
        os.makedirs(photo_folder, exist_ok=True)
        out_file = os.path.join(photo_folder, f"Jason3_SWH_{start_str}_{end_str}.png")
        
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


def _make_wave_maps_worker(selected_folder, time_step_hours, log_queue, result_queue,
                           FIGSIZE=(16,12), DPI=300, UPSAMPLE_FACTOR=3, CLIM_PCT=99.0,
                           CARTOPY_COAST_RES='10m', v=1, output_folder=None, show_land_coastline=True,
                           manual_wind=None, generate_video=False, wave_height_file=None):
    """在子进程中执行生成波浪图计算的独立函数"""
    try:
        # 在子进程中加载当前语言设置
        try:
            from setting.config import load_config
            from setting.language_manager import load_language
            config = load_config()
            language_code = config.get("LANGUAGE", "zh_CN")
            load_language(language_code)
        except Exception:
            # 如果加载失败，使用默认语言
            pass
        
        def log(msg):
            """发送日志到队列"""
            try:
                log_queue.put(msg)
            except:
                pass
        
        video_text = tr("step8_generate_start_video", " + 视频") if generate_video else ""
        log(tr("step8_generate_start", "🔄 开始生成结果图片{video}（在子进程中执行）...").format(video=video_text))
        
        # ------------------------
        # 读取数据
        # ------------------------
        # 优先使用指定的波高文件，否则自动查找
        if wave_height_file and os.path.exists(wave_height_file):
            ncfile = wave_height_file
            
        else:
            # 尝试多种文件匹配模式
            # 优先查找 ww3.*.nc 文件（排除 spec 文件）
            nc_files = glob.glob(os.path.join(selected_folder, "ww3.*.nc"))
            # 排除 spec 文件
            nc_files = [f for f in nc_files if "spec" not in os.path.basename(f).lower()]
            
            if not nc_files:
                # 尝试不带点的模式
                nc_files = glob.glob(os.path.join(selected_folder, "ww3*.nc"))
                # 排除 spec 文件
                nc_files = [f for f in nc_files if "spec" not in os.path.basename(f).lower()]
            
            if not nc_files:
                log(tr("step8_no_wave_file", "❌ 文件夹中没有找到波高文件（已排除谱文件）"))
                log_queue.put("__DONE__")
                result_queue.put([])
                return
            
            ncfile = nc_files[0]
            log(tr("plotting_auto_found_wave_file", "📂 自动找到波高文件: {file}").format(file=os.path.basename(ncfile)))

        # 如果指定了输出文件夹，使用它；否则使用 selected_folder/photo
        if output_folder:
            photo_folder = os.path.join(output_folder, "photo")
        else:
            photo_folder = os.path.join(selected_folder, "photo")

        # 按需求选择性清理：生成图片时仅清理波高图，生成视频时仅清理视频文件
        if os.path.exists(photo_folder):
            if generate_video:
                clean_patterns = ["*.mp4", "*.avi", "*.mov", "*.gif"]
            else:
                # 只清除波高图相关的文件（hs_*.png, phs0_*.png, phs1_*.png）
                clean_patterns = ["hs_*.png", "phs0_*.png", "phs1_*.png"]
            for pat in clean_patterns:
                for f in glob.glob(os.path.join(photo_folder, pat)):
                    try: 
                        os.remove(f)
                    except: 
                        pass
        os.makedirs(photo_folder, exist_ok=True)

        ds = nc.Dataset(ncfile)
        WW3_lon = np.array(ds.variables['longitude'][:])
        WW3_lat = np.array(ds.variables['latitude'][:])
        WW3_time_var = ds.variables['time']

        # 时间
        try:
            WW3_datetime = num2date(WW3_time_var[:], WW3_time_var.units)
            WW3_datetime = np.array([datetime.utcfromtimestamp(dt.timestamp()) for dt in WW3_datetime])
        except:
            ref = datetime(1990,1,1)
            WW3_datetime = np.array([ref + timedelta(days=float(t)) for t in WW3_time_var[:]])

        # 检查可用的变量
        available_vars = list(ds.variables.keys())
 
        # 变量选择（检查变量是否存在）
        if v == 1:
            if 'hs' not in ds.variables:
                log(tr("plotting_missing_hs_variable", "❌ 文件中没有 'hs' 变量。可用变量: {vars}").format(vars=', '.join(available_vars)))
                ds.close()
                log_queue.put("__DONE__")
                result_queue.put([])
                return
            raw = np.array(ds.variables['hs'][:])
            varlabel = 'Total Hs (m)'; prefix='hs'
        elif v == 2:
            if 'phs0' not in ds.variables:
                log(tr("plotting_missing_phs0_variable", "❌ 文件中没有 'phs0' 变量。可用变量: {vars}").format(vars=', '.join(available_vars)))
                ds.close()
                log_queue.put("__DONE__")
                result_queue.put([])
                return
            raw = np.array(ds.variables['phs0'][:])
            varlabel = 'Wind Sea Hs (m)'; prefix='phs0'
        else:
            if 'phs1' not in ds.variables:
                log(tr("plotting_missing_phs1_variable", "❌ 文件中没有 'phs1' 变量。可用变量: {vars}").format(vars=', '.join(available_vars)))
                ds.close()
                log_queue.put("__DONE__")
                result_queue.put([])
                return
            raw = np.array(ds.variables['phs1'][:])
            varlabel = 'Swell Hs (m)'; prefix='phs1'

        # 可选：读取风场（用于显示统一风速）
        u10_data = None
        v10_data = None
        if 'u10' in ds.variables:
            u_raw = np.array(ds.variables['u10'][:])
            time_axes_u = [i for i, s in enumerate(u_raw.shape) if s == len(WW3_datetime)]
            time_axis_u = time_axes_u[0] if time_axes_u else 0
            if time_axis_u == 0:
                u10_data = u_raw.transpose(1, 2, 0)
            elif time_axis_u == 1:
                u10_data = u_raw.transpose(0, 2, 1)
            elif time_axis_u == 2:
                if u_raw.shape[:2] == (len(WW3_lat), len(WW3_lon)):
                    u10_data = u_raw
                else:
                    u10_data = u_raw.transpose(1, 0, 2)
            else:
                u10_data = u_raw
            u10_data = u10_data.astype(float)
            u10_data[u10_data > 1e10] = np.nan

        if 'v10' in ds.variables:
            v_raw = np.array(ds.variables['v10'][:])
            time_axes_v = [i for i, s in enumerate(v_raw.shape) if s == len(WW3_datetime)]
            time_axis_v = time_axes_v[0] if time_axes_v else 0
            if time_axis_v == 0:
                v10_data = v_raw.transpose(1, 2, 0)
            elif time_axis_v == 1:
                v10_data = v_raw.transpose(0, 2, 1)
            elif time_axis_v == 2:
                if v_raw.shape[:2] == (len(WW3_lat), len(WW3_lon)):
                    v10_data = v_raw
                else:
                    v10_data = v_raw.transpose(1, 0, 2)
            else:
                v10_data = v_raw
            v10_data = v10_data.astype(float)
            v10_data[v10_data > 1e10] = np.nan

        ds.close()

        # ------------------------
        # 数据维度整理
        # ------------------------
        shape = raw.shape
        nt = len(WW3_datetime)
        time_axes = [i for i,s in enumerate(shape) if s==nt]
        time_axis = time_axes[0] if time_axes else 2

        if time_axis==0:
            Hs = raw.transpose(1,2,0)
        elif time_axis==1:
            Hs = raw.transpose(0,2,1)
        elif time_axis==2:
            if raw.shape[:2] == (len(WW3_lat), len(WW3_lon)):
                Hs = raw
            else:
                Hs = raw.transpose(1,0,2)
        else:
            Hs = raw

        # ------------------------
        # 区域范围（先基于文件，再收缩到有数据的范围）
        # ------------------------
        lon_min, lon_max = WW3_lon.min(), WW3_lon.max()
        lat_min, lat_max = WW3_lat.min(), WW3_lat.max()
        lon_idx = np.where((WW3_lon>=lon_min)&(WW3_lon<=lon_max))[0]
        lat_idx = np.where((WW3_lat>=lat_min)&(WW3_lat<=lat_max))[0]
        lon_sub, lat_sub = WW3_lon[lon_idx], WW3_lat[lat_idx]

        # ------------------------
        # 全局波高范围
        # ------------------------
        Hs_all = Hs[np.ix_(lat_idx, lon_idx, range(Hs.shape[2]))].astype(float)
        Hs_all[Hs_all>1e10] = np.nan
        vmin, vmax = 0, np.nanpercentile(Hs_all, CLIM_PCT)

        # 如果显示陆地和海岸线，则不进行数据范围收缩（保持完整的地图范围）
        # 收缩到有数据的经纬度范围，避免无数据区域造成空白
        if not show_land_coastline:
            valid_all = np.isfinite(Hs_all)
            try:
                lat_has = valid_all.any(axis=(1,2))
                lon_has = valid_all.any(axis=(0,2))
                if lat_has.any():
                    lat_valid_min = lat_sub[lat_has].min()
                    lat_valid_max = lat_sub[lat_has].max()
                    lat_min, lat_max = lat_valid_min, lat_valid_max
                    lat_idx = np.where((WW3_lat>=lat_min)&(WW3_lat<=lat_max))[0]
                    lat_sub = WW3_lat[lat_idx]
                if lon_has.any():
                    lon_valid_min = lon_sub[lon_has].min()
                    lon_valid_max = lon_sub[lon_has].max()
                    lon_min, lon_max = lon_valid_min, lon_valid_max
                    lon_idx = np.where((WW3_lon>=lon_min)&(WW3_lon<=lon_max))[0]
                    lon_sub = WW3_lon[lon_idx]
                log(tr("plotting_data_range_shrink", "🧭 数据范围收缩: lon [{lon_min}, {lon_max}], lat [{lat_min}, {lat_max}]").format(lon_min=f"{lon_min:.3f}", lon_max=f"{lon_max:.3f}", lat_min=f"{lat_min:.3f}", lat_max=f"{lat_max:.3f}"))
            except Exception as e:
                log(tr("plotting_data_range_shrink_failed", "⚠️ 数据范围收缩失败，使用原始范围: {error}").format(error=e))


        # ------------------------
        # meshgrid 只创建一次（使用收缩后的范围）
        # ------------------------
        if UPSAMPLE_FACTOR > 1:
            lon_plot_1d = np.linspace(lon_sub[0], lon_sub[-1], len(lon_sub)*UPSAMPLE_FACTOR)
            lat_plot_1d = np.linspace(lat_sub[0], lat_sub[-1], len(lat_sub)*UPSAMPLE_FACTOR)
        else:
            lon_plot_1d = lon_sub
            lat_plot_1d = lat_sub
        LON_plot, LAT_plot = np.meshgrid(lon_plot_1d, lat_plot_1d)

        # ------------------------
        # 生成目标时间并预计算最近索引
        # ------------------------
        start_time, end_time = WW3_datetime[0], WW3_datetime[-1]
        targets = []
        t = start_time
        while t <= end_time:
            targets.append(t)
            t += timedelta(hours=time_step_hours)

        # 将 datetime 转成秒，加速 abs 比较
        dt_seconds = np.array([(dt - start_time).total_seconds() for dt in WW3_datetime])

        target_ids = []
        for tar in targets:
            tar_sec = (tar - start_time).total_seconds()
            tid = int(np.argmin(np.abs(dt_seconds - tar_sec)))
            target_ids.append(tid)

        # ======================================================
        #               图框架只创建一次（最关键）
        # ======================================================
        # 保存原来的后端，切换到 Agg 用于生成图片
        original_backend = matplotlib.get_backend()
        matplotlib.use("Agg")  # 关闭 GUI 加速

        fig = plt.figure(figsize=FIGSIZE)
        # 整体稍微增加内边距，留出一点空白框
        fig.subplots_adjust(left=0.04, right=0.96, top=0.92, bottom=0.12)
        ax = plt.axes(projection=ccrs.PlateCarree())
        # 收紧轴区域，尽量贴近边框
        ax.set_position([0.05, 0.18, 0.90, 0.70])
        ax.margins(0)
        ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())

        # 根据配置决定是否显示陆地和海岸线
        if show_land_coastline:
            land = cfeature.NaturalEarthFeature('physical','land',CARTOPY_COAST_RES)
            ax.add_feature(land, facecolor='0.92')
            ax.coastlines(CARTOPY_COAST_RES, linewidth=0.6)
        
        # 添加坐标轴刻度（显示经纬度），无论是否显示陆地和海岸线
        # 根据范围自动选择合适的刻度间隔，并检测重叠
        lon_range = lon_max - lon_min
        lat_range = lat_max - lat_min
        
        # 选择合适的刻度间隔（度）
        def get_initial_step(range_val):
            if range_val <= 0.5:
                return 0.1
            elif range_val <= 1.0:
                return 0.2
            elif range_val <= 2.0:
                return 0.5
            elif range_val <= 5.0:
                return 1.0
            else:
                return 2.0
        
        lon_step = get_initial_step(lon_range)
        lat_step = get_initial_step(lat_range)
        
        # 生成刻度位置并检测重叠，自动调整间隔
        def generate_ticks_with_overlap_check(val_min, val_max, initial_step, max_ticks=12):
            step = initial_step
            max_iterations = 15
            iteration = 0
            
            # 定义更精细的间隔序列
            step_sequence = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0]
            
            while iteration < max_iterations:
                ticks = np.arange(np.floor(val_min / step) * step,
                                 np.ceil(val_max / step) * step + step/2,
                                 step)
                ticks = ticks[(ticks >= val_min) & (ticks <= val_max)]
                
                # 确保包含边界
                if len(ticks) == 0 or ticks[0] > val_min:
                    ticks = np.concatenate([[val_min], ticks])
                if len(ticks) == 0 or ticks[-1] < val_max:
                    ticks = np.concatenate([ticks, [val_max]])
                
                ticks = np.unique(ticks)
                
                # 检测重叠：如果刻度数量过多，增大间隔
                if len(ticks) > max_ticks:
                    # 在间隔序列中找到下一个更大的间隔
                    current_idx = -1
                    for i, s in enumerate(step_sequence):
                        if step <= s:
                            current_idx = i
                            break
                    
                    if current_idx >= 0 and current_idx < len(step_sequence) - 1:
                        # 使用序列中的下一个间隔
                        step = step_sequence[current_idx + 1]
                    else:
                        # 如果超出序列，按比例增大（更小的增量）
                        step *= 1.5
                    iteration += 1
                else:
                    break
            
            return ticks, step
        
        lon_ticks, lon_step = generate_ticks_with_overlap_check(lon_min, lon_max, lon_step)
        lat_ticks, lat_step = generate_ticks_with_overlap_check(lat_min, lat_max, lat_step)

        # 直接设置刻度和标签，保证边界刻度显示
        ax.set_xticks(lon_ticks)
        ax.set_yticks(lat_ticks)
        ax.tick_params(axis='both', which='both', bottom=True, top=False, left=True, right=False,
                       labelbottom=True, labelleft=True, labelsize=10)
        
        # 格式化为经纬度标签
        def format_lon_lat(vals, is_lon=True):
            labels = []
            for v in vals:
                if is_lon:
                    if v >= 0:
                        labels.append(f"{v:.2f}°E")
                    else:
                        labels.append(f"{abs(v):.2f}°W")
                else:
                    if v >= 0:
                        labels.append(f"{v:.2f}°N")
                    else:
                        labels.append(f"{abs(v):.2f}°S")
            return labels
        
        ax.set_xticklabels(format_lon_lat(lon_ticks, is_lon=True))
        ax.set_yticklabels(format_lon_lat(lat_ticks, is_lon=False))

        from matplotlib.ticker import FixedLocator
        gl = ax.gridlines(crs=ccrs.PlateCarree(),
                          linewidth=0.5, color='gray', alpha=0.4, linestyle='--',
                          draw_labels=False)
        gl.xlocator = FixedLocator(lon_ticks)
        gl.ylocator = FixedLocator(lat_ticks)

        # 创建一次 pcolormesh（使用网格边界，避免可视范围内出现空白边缘）
        def _calc_edges(arr):
            # arr 为单调数组
            mid = (arr[:-1] + arr[1:]) / 2.0
            first = arr[0] - (arr[1] - arr[0]) / 2.0
            last = arr[-1] + (arr[-1] - arr[-2]) / 2.0
            return np.concatenate([[first], mid, [last]])

        lon_edges = _calc_edges(lon_plot_1d)
        lat_edges = _calc_edges(lat_plot_1d)

        Hs_init = np.zeros((len(lat_plot_1d), len(lon_plot_1d)))
        pcm = ax.pcolormesh(lon_edges, lat_edges, Hs_init,
                            transform=ccrs.PlateCarree(),
                            shading='auto', cmap=cm.turbo,
                            vmin=vmin, vmax=vmax)

        # 紧凑的颜色条，避免额外留白
        # 将颜色条与主图拉开距离，避免过于贴近
        cb = fig.colorbar(pcm, ax=ax, orientation='horizontal', fraction=0.05, pad=0.06, aspect=40)
        cb.set_label(varlabel)

        # ======================================================
        #               循环输出（只更新数据 + 存图）
        # ======================================================
        saved_files = []
        hs_frames = []      # 已插值到展示网格的波高帧
        frame_times = []    # 对应的时间戳
        wind_infos = []     # 对应帧的风速描述，供视频标题使用
        num = 0
        total = len(targets)

        for idx, (tid, t_target) in enumerate(zip(target_ids, targets)):
            # 每10张图片更新一次进度
            if (idx + 1) % 10 == 0 or idx == 0:
                progress_pct = int((idx + 1) / total * 100)
                if generate_video:
                    log(tr("plotting_progress_frames", "📊 进度: {current}/{total} ({percent}%) - 已处理 {processed} 帧").format(current=idx + 1, total=total, percent=progress_pct, processed=num))
                else:
                    log(tr("plotting_progress_images", "📊 进度: {current}/{total} ({percent}%) - 已生成 {generated} 张图片").format(current=idx + 1, total=total, percent=progress_pct, generated=num))

            Hs_now = Hs[np.ix_(lat_idx, lon_idx, [tid])][:,:,0].astype(float)
            Hs_now[Hs_now>1e10] = np.nan

            # 如果有效数据比例过低，跳过这一帧，避免大片空白
            valid_mask = np.isfinite(Hs_now)
            valid_ratio = valid_mask.sum() / valid_mask.size if valid_mask.size > 0 else 0
            if valid_ratio < 0.02:
                log(tr("plotting_skip_frame_low_data", "⚠️  时刻 {time} 有效数据仅 {ratio}% ，跳过绘制以避免空白").format(time=t_target, ratio=f"{valid_ratio*100:.1f}"))  # type: ignore[name-defined]
                continue

            # 不再根据有效数据调整 extent，保持固定轴范围，避免掩码尺寸不匹配

            # 如果有效数据比例过低，跳过这一帧，避免大片空白
            valid_mask = np.isfinite(Hs_now)
            valid_ratio = valid_mask.sum() / valid_mask.size if valid_mask.size > 0 else 0
            if valid_ratio < 0.02:
                log(tr("plotting_skip_frame_low_data", "⚠️  时刻 {time} 有效数据仅 {ratio}% ，跳过绘制以避免空白").format(time=t_target, ratio=f"{valid_ratio*100:.1f}"))  # type: ignore[name-defined]
                continue

            # 保持固定轴范围，不再按有效范围动态调整，避免掩码尺寸不匹配

            # 超快速上采样（cv2 比 scipy 快 5～20 倍）
            if UPSAMPLE_FACTOR > 1:
                Hs_now = cv2.resize(Hs_now, (len(lon_plot_1d), len(lat_plot_1d)),
                                    interpolation=cv2.INTER_LINEAR)

            # 更新 pcolormesh 数据（关键加速）
            pcm.set_array(Hs_now.ravel())

            # 标题更新：若输入风速，则在原有信息后追加风速；否则保持原逻辑
            time_str = t_target.strftime('%Y-%m-%d %H:%M UTC')
            wind_info = ""
            if manual_wind is not None:
                wind_info = f" | Wind {manual_wind:.1f} m/s"
            else:
                if u10_data is not None:
                    u_now = u10_data[np.ix_(lat_idx, lon_idx, [tid])][:, :, 0]
                    if v10_data is not None:
                        v_now = v10_data[np.ix_(lat_idx, lon_idx, [tid])][:, :, 0]
                    else:
                        v_now = 0.0
                    wind_speed_now = np.sqrt(u_now ** 2 + v_now ** 2)
                    if np.nanmax(wind_speed_now) - np.nanmin(wind_speed_now) < 1e-6:
                        ws = float(np.nanmean(wind_speed_now))
                        wind_info = f" | Wind {ws:.1f} m/s (uniform)"
            title_text = f"{varlabel}  {time_str}{wind_info}"
            ax.set_title(title_text, fontsize=14)
            if generate_video:
                hs_frames.append(Hs_now.copy())
                frame_times.append(t_target)
                wind_infos.append(wind_info)
                num += 1  # 生成视频时也要计数

            if not generate_video:
                outname=os.path.join(photo_folder,f"{prefix}_{t_target.strftime('%Y%m%d_%H%M')}.png")
                plt.savefig(outname, dpi=DPI, bbox_inches='tight')
                saved_files.append(outname)
                num += 1
        # 生成连续变化视频（插值过渡帧，避免生硬跳变）
        if generate_video:
            try:
                import matplotlib.animation as animation
                if not animation.writers.is_available("ffmpeg"):
                    log(tr("plotting_ffmpeg_not_found", "⚠️ 未找到 ffmpeg，无法生成视频。请安装 ffmpeg 或将其加入 PATH。"))
                elif len(hs_frames) == 0:
                    log(tr("plotting_no_valid_frames", "⚠️ 无有效波高帧，无法生成视频。"))
                else:
                    video_path = os.path.join(photo_folder, f"{prefix}_anim.mp4")
                    writer = animation.FFMpegWriter(fps=5, metadata={"artist": "WW3Tool"})
                    steps_per_interval = 5  # 每两个时间步之间插值帧数（不含下一关键帧）
                    with writer.saving(fig, video_path, DPI):
                        for i in range(len(hs_frames) - 1):
                            frame_a = hs_frames[i]
                            frame_b = hs_frames[i + 1]
                            t_a = frame_times[i]
                            t_b = frame_times[i + 1]
                            wind_info_a = wind_infos[i] if i < len(wind_infos) else ""
                            # 当前关键帧
                            pcm.set_array(frame_a.ravel())
                            ax.set_title(f"{varlabel}  {t_a.strftime('%H:%M UTC')}{wind_info_a}", fontsize=14)
                            writer.grab_frame()
                            # 插值帧
                            for s in range(1, steps_per_interval):
                                alpha = s / steps_per_interval
                                interp = frame_a * (1 - alpha) + frame_b * alpha
                                pcm.set_array(interp.ravel())
                                t_interp = t_a + (t_b - t_a) * alpha
                                ax.set_title(f"{varlabel}  {t_interp.strftime('%H:%M UTC')}{wind_info_a}", fontsize=14)
                                writer.grab_frame()
                        # 最后一帧
                        pcm.set_array(hs_frames[-1].ravel())
                        wind_last = wind_infos[-1] if len(wind_infos) > 0 else ""
                        ax.set_title(f"{varlabel}  {frame_times[-1].strftime('%H:%M UTC')}{wind_last}", fontsize=14)
                        writer.grab_frame()
                    log(tr("plotting_video_generated", "✅ 波高变化视频已生成：{path}").format(path=video_path))
            except Exception as e:
                log(tr("plotting_video_generation_failed", "⚠️ 波高视频生成失败：{error}").format(error=e))

        if generate_video:
            log(tr("plotting_video_frames_complete", "✅ 生成视频帧完成，共 {count} 帧").format(count=num))
        else:
            log(tr("plotting_result_complete", "✅ 生成结果图片完成，共 {count} 张").format(count=num))
        plt.close(fig)
        
        # 恢复原来的后端
        matplotlib.use(original_backend)
        
        # 发送完成信号和结果
        log_queue.put("__DONE__")
        result_queue.put(saved_files)
        
    except Exception as e:
        import traceback
        error_msg = tr("plotting_worker_process_failed", "❌ 子进程处理失败：{error}\n{details}").format(error=e, details=traceback.format_exc())
        try:
            log_queue.put(error_msg)
            log_queue.put("__DONE__")
        except:
            pass
        result_queue.put([])


import os, re, ftplib, time, threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor


def _make_contour_maps_worker(selected_folder, time_step_hours, log_queue, result_queue,
                               FIGSIZE=(16,12), DPI=300, UPSAMPLE_FACTOR=3, CLIM_PCT=99.0,
                               CARTOPY_COAST_RES='10m', output_folder=None, show_land_coastline=True,
                               manual_wind=None, wave_height_file=None):
    """在子进程中执行生成等高线图计算的独立函数"""
    try:
        # 在子进程中加载当前语言设置
        try:
            from setting.config import load_config
            from setting.language_manager import load_language, tr
            config = load_config()
            language_code = config.get("LANGUAGE", "zh_CN")
            load_language(language_code)
        except Exception:
            # 如果加载失败，使用默认语言
            from setting.language_manager import tr
            pass
        
        def log(msg):
            """发送日志到队列"""
            try:
                log_queue.put(msg)
            except:
                pass
        
        log(tr("plotting_start_contour", "🔄 开始生成等高线图（在子进程中执行）..."))
        
        # 导入配置读取函数（需要在子进程中重新导入）
        try:
            from setting.config import load_config
        except:
            def load_config():
                return {}
        
        # 如果指定了输出文件夹，使用它；否则使用 selected_folder/photo
        if output_folder:
            photo_folder = os.path.join(output_folder, "photo")
        else:
            photo_folder = os.path.join(selected_folder, "photo")
        
        # 清理旧的等高线图文件
        if os.path.exists(photo_folder):
            for f in glob.glob(os.path.join(photo_folder, "contour_hs_*.png")):
                try: 
                    os.remove(f)
                except: 
                    pass
        os.makedirs(photo_folder, exist_ok=True)
        
        # 读取数据：优先使用传入的文件，否则自动查找
        if wave_height_file and os.path.exists(wave_height_file):
            ncfile = wave_height_file
        else:
            # 自动查找 ww3*.nc 文件（排除 spec）
            nc_files = glob.glob(os.path.join(selected_folder, "ww3*.nc"))
            # 排除 spec 文件
            nc_files = [f for f in nc_files if "spec" not in os.path.basename(f).lower()]
            if not nc_files:
                # 回退到查找 ww3.*.nc（带点）
                nc_files = glob.glob(os.path.join(selected_folder, "ww3.*.nc"))
            if not nc_files:
                # 最后回退到查找所有 .nc 文件
                nc_files = glob.glob(os.path.join(selected_folder, "*.nc"))
            if not nc_files:
                log(tr("plotting_no_nc_files", "❌ 当前目录中没有 nc 文件"))
                log_queue.put("__DONE__")
                result_queue.put([])
                return
            ncfile = nc_files[0]
        ds = nc.Dataset(ncfile)
        WW3_lon = np.array(ds.variables['longitude'][:])
        WW3_lat = np.array(ds.variables['latitude'][:])
        WW3_time_var = ds.variables['time']
        
        # 时间
        try:
            WW3_datetime = num2date(WW3_time_var[:], WW3_time_var.units)
            WW3_datetime = np.array([datetime.utcfromtimestamp(dt.timestamp()) for dt in WW3_datetime])
        except:
            ref = datetime(1990,1,1)
            WW3_datetime = np.array([ref + timedelta(days=float(t)) for t in WW3_time_var[:]])
        
        # 读取波高数据
        raw = np.array(ds.variables['hs'][:])
        varlabel = 'Total Hs (m)'
        prefix = 'contour_hs'
        
        # 读取风场数据
        u10_data = None
        v10_data = None
        if 'u10' in ds.variables:
            u_raw = np.array(ds.variables['u10'][:])
            time_axes_u = [i for i, s in enumerate(u_raw.shape) if s == len(WW3_datetime)]
            time_axis_u = time_axes_u[0] if time_axes_u else 0
            if time_axis_u == 0:
                u10_data = u_raw.transpose(1, 2, 0)
            elif time_axis_u == 1:
                u10_data = u_raw.transpose(0, 2, 1)
            elif time_axis_u == 2:
                if u_raw.shape[:2] == (len(WW3_lat), len(WW3_lon)):
                    u10_data = u_raw
                else:
                    u10_data = u_raw.transpose(1, 0, 2)
            else:
                u10_data = u_raw
            u10_data = u10_data.astype(float)
            u10_data[u10_data > 1e10] = np.nan
        
        if 'v10' in ds.variables:
            v_raw = np.array(ds.variables['v10'][:])
            time_axes_v = [i for i, s in enumerate(v_raw.shape) if s == len(WW3_datetime)]
            time_axis_v = time_axes_v[0] if time_axes_v else 0
            if time_axis_v == 0:
                v10_data = v_raw.transpose(1, 2, 0)
            elif time_axis_v == 1:
                v10_data = v_raw.transpose(0, 2, 1)
            elif time_axis_v == 2:
                if v_raw.shape[:2] == (len(WW3_lat), len(WW3_lon)):
                    v10_data = v_raw
                else:
                    v10_data = v_raw.transpose(1, 0, 2)
            else:
                v10_data = v_raw
            v10_data = v10_data.astype(float)
            v10_data[v10_data > 1e10] = np.nan
        
        ds.close()
        
        # 数据维度整理
        shape = raw.shape
        nt = len(WW3_datetime)
        time_axes = [i for i,s in enumerate(shape) if s==nt]
        time_axis = time_axes[0] if time_axes else 2
        
        if time_axis==0:
            Hs = raw.transpose(1,2,0)
        elif time_axis==1:
            Hs = raw.transpose(0,2,1)
        elif time_axis==2:
            if raw.shape[:2] == (len(WW3_lat), len(WW3_lon)):
                Hs = raw
            else:
                Hs = raw.transpose(1,0,2)
        else:
            Hs = raw
        
        # 区域范围（先基于文件，再收缩到有数据的范围）
        lon_min, lon_max = WW3_lon.min(), WW3_lon.max()
        lat_min, lat_max = WW3_lat.min(), WW3_lat.max()
        lon_idx = np.where((WW3_lon>=lon_min)&(WW3_lon<=lon_max))[0]
        lat_idx = np.where((WW3_lat>=lat_min)&(WW3_lat<=lat_max))[0]
        lon_sub, lat_sub = WW3_lon[lon_idx], WW3_lat[lat_idx]
        
        # 全局波高范围（使用与波高图相同的CLIM_PCT）
        Hs_all = Hs[np.ix_(lat_idx, lon_idx, range(Hs.shape[2]))].astype(float)
        Hs_all[Hs_all>1e10] = np.nan
        vmin, vmax = 0, np.nanpercentile(Hs_all, CLIM_PCT)
        
        # 如果显示陆地和海岸线，则不进行数据范围收缩（保持完整的地图范围）
        # 收缩到有数据的经纬度范围，避免无数据区域造成空白
        if not show_land_coastline:
            valid_all = np.isfinite(Hs_all)
            try:
                lat_has = valid_all.any(axis=(1,2))
                lon_has = valid_all.any(axis=(0,2))
                if lat_has.any():
                    lat_valid_min = lat_sub[lat_has].min()
                    lat_valid_max = lat_sub[lat_has].max()
                    lat_min, lat_max = lat_valid_min, lat_valid_max
                    lat_idx = np.where((WW3_lat>=lat_min)&(WW3_lat<=lat_max))[0]
                    lat_sub = WW3_lat[lat_idx]
                if lon_has.any():
                    lon_valid_min = lon_sub[lon_has].min()
                    lon_valid_max = lon_sub[lon_has].max()
                    lon_min, lon_max = lon_valid_min, lon_valid_max
                    lon_idx = np.where((WW3_lon>=lon_min)&(WW3_lon<=lon_max))[0]
                    lon_sub = WW3_lon[lon_idx]
                log(tr("plotting_data_range_shrink", "🧭 数据范围收缩: lon [{lon_min}, {lon_max}], lat [{lat_min}, {lat_max}]").format(lon_min=f"{lon_min:.3f}", lon_max=f"{lon_max:.3f}", lat_min=f"{lat_min:.3f}", lat_max=f"{lat_max:.3f}"))
            except Exception as e:
                log(tr("plotting_data_range_shrink_failed", "⚠️ 数据范围收缩失败，使用原始范围: {error}").format(error=e))
   
        # 创建网格（使用与波高图相同的UPSAMPLE_FACTOR）
        if UPSAMPLE_FACTOR > 1:
            lon_plot_1d = np.linspace(lon_sub[0], lon_sub[-1], len(lon_sub)*UPSAMPLE_FACTOR)
            lat_plot_1d = np.linspace(lat_sub[0], lat_sub[-1], len(lat_sub)*UPSAMPLE_FACTOR)
        else:
            lon_plot_1d = lon_sub
            lat_plot_1d = lat_sub
        LON_plot_base, LAT_plot_base = np.meshgrid(lon_plot_1d, lat_plot_1d)
        
        # 生成目标时间
        start_time, end_time = WW3_datetime[0], WW3_datetime[-1]
        targets = []
        t = start_time
        while t <= end_time:
            targets.append(t)
            t += timedelta(hours=time_step_hours)
        
        # 将 datetime 转成秒，加速 abs 比较
        dt_seconds = np.array([(dt - start_time).total_seconds() for dt in WW3_datetime])
        
        target_ids = []
        for tar in targets:
            tar_sec = (tar - start_time).total_seconds()
            tid = int(np.argmin(np.abs(dt_seconds - tar_sec)))
            target_ids.append(tid)
        
        # 创建图框架
        original_backend = matplotlib.get_backend()
        matplotlib.use("Agg")
        
        saved_files = []
        num = 0
        total = len(targets)
        
        # 坐标轴刻度生成函数（与主窗口中的相同）
        def get_initial_step(range_val):
            if range_val <= 0.5:
                return 0.1
            elif range_val <= 1.0:
                return 0.2
            elif range_val <= 2.0:
                return 0.5
            elif range_val <= 5.0:
                return 1.0
            else:
                return 2.0
        
        def generate_ticks_with_overlap_check(val_min, val_max, initial_step, max_ticks=12):
            step = initial_step
            max_iterations = 15
            iteration = 0
            step_sequence = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0]
            
            while iteration < max_iterations:
                ticks = np.arange(np.floor(val_min / step) * step,
                                 np.ceil(val_max / step) * step + step/2,
                                 step)
                ticks = ticks[(ticks >= val_min) & (ticks <= val_max)]
                
                if len(ticks) == 0 or ticks[0] > val_min:
                    ticks = np.concatenate([[val_min], ticks])
                if len(ticks) == 0 or ticks[-1] < val_max:
                    ticks = np.concatenate([ticks, [val_max]])
                
                ticks = np.unique(ticks)
                
                if len(ticks) > max_ticks:
                    current_idx = -1
                    for i, s in enumerate(step_sequence):
                        if step <= s:
                            current_idx = i
                            break
                    
                    if current_idx >= 0 and current_idx < len(step_sequence) - 1:
                        step = step_sequence[current_idx + 1]
                    else:
                        step *= 1.5
                    iteration += 1
                else:
                    break
            
            return ticks, step
        
        for idx, (tid, t_target) in enumerate(zip(target_ids, targets)):
            if (idx + 1) % 10 == 0 or idx == 0:
                progress_pct = int((idx + 1) / total * 100)
                log(tr("plotting_progress_contour", "📊 进度: {current}/{total} ({percent}%) - 已生成 {generated} 张等高线图").format(current=idx + 1, total=total, percent=progress_pct, generated=num))
            
            Hs_now_raw = Hs[np.ix_(lat_idx, lon_idx, [tid])][:,:,0].astype(float)
            Hs_now_raw[Hs_now_raw>1e10] = np.nan
            
            # 如果有效数据比例过低，跳过
            valid_mask = np.isfinite(Hs_now_raw)
            valid_ratio = valid_mask.sum() / valid_mask.size if valid_mask.size > 0 else 0
            if valid_ratio < 0.02:
                continue
            
            # 对数据进行插值（使用与波高图相同的UPSAMPLE_FACTOR）
            if UPSAMPLE_FACTOR > 1:
                from scipy.ndimage import zoom as sp_zoom
                Hs_now = sp_zoom(Hs_now_raw, UPSAMPLE_FACTOR, order=1, mode='nearest')
            else:
                Hs_now = Hs_now_raw
            
            fig = plt.figure(figsize=FIGSIZE)
            ax = plt.axes(projection=ccrs.PlateCarree())
            ax.margins(0)
            ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())
            
            # 添加坐标轴刻度
            lon_range = lon_max - lon_min
            lat_range = lat_max - lat_min
            lon_step = get_initial_step(lon_range)
            lat_step = get_initial_step(lat_range)
            lon_ticks, lon_step = generate_ticks_with_overlap_check(lon_min, lon_max, lon_step)
            lat_ticks, lat_step = generate_ticks_with_overlap_check(lat_min, lat_max, lat_step)
            
            ax.set_xticks(lon_ticks)
            ax.set_yticks(lat_ticks)
            ax.tick_params(axis='both', which='both', bottom=True, top=False, left=True, right=False,
                           labelbottom=True, labelleft=True, labelsize=10)
            
            def format_lon_lat(vals, is_lon=True):
                labels = []
                for v in vals:
                    if is_lon:
                        if v >= 0:
                            labels.append(f"{v:.2f}°E")
                        else:
                            labels.append(f"{abs(v):.2f}°W")
                    else:
                        if v >= 0:
                            labels.append(f"{v:.2f}°N")
                        else:
                            labels.append(f"{abs(v):.2f}°S")
                return labels
            
            ax.set_xticklabels(format_lon_lat(lon_ticks, is_lon=True))
            ax.set_yticklabels(format_lon_lat(lat_ticks, is_lon=False))
            
            from matplotlib.ticker import FixedLocator
            gl = ax.gridlines(crs=ccrs.PlateCarree(),
                              linewidth=0.5, color='gray', alpha=0.4, linestyle='--',
                              draw_labels=False)
            gl.xlocator = FixedLocator(lon_ticks)
            gl.ylocator = FixedLocator(lat_ticks)
            
            LON_plot, LAT_plot = LON_plot_base, LAT_plot_base
            
            # 绘制波高图作为底图
            pcm = ax.pcolormesh(LON_plot, LAT_plot, Hs_now,
                                transform=ccrs.PlateCarree(),
                                shading='auto', cmap=cm.turbo,
                                vmin=vmin, vmax=vmax,
                                zorder=1)
            
            # 添加陆地和海岸线（如果启用）
            if show_land_coastline:
                land = cfeature.NaturalEarthFeature('physical','land',CARTOPY_COAST_RES)
                ax.add_feature(land, facecolor='0.92', zorder=2)
                ax.coastlines(CARTOPY_COAST_RES, linewidth=0.6, zorder=2)
            
            # 绘制等高线
            if vmax < 0.5:
                step = 0.02
                vmin_rounded = np.floor(vmin * 50) / 50
                vmax_rounded = np.ceil(vmax * 50) / 50
            elif vmax < 3.0:
                step = 0.1
                vmin_rounded = np.floor(vmin * 10) / 10
                vmax_rounded = np.ceil(vmax * 10) / 10
            else:
                step = 0.5
                vmin_rounded = np.floor(vmin * 2) / 2
                vmax_rounded = np.ceil(vmax * 2) / 2
            contour_levels_all = np.arange(vmin_rounded, vmax_rounded + step/2, step)
            contour_levels = contour_levels_all[contour_levels_all <= vmax]
            cs = ax.contour(LON_plot, LAT_plot, Hs_now, levels=contour_levels,
                            transform=ccrs.PlateCarree(), colors='black', linewidths=0.8,
                            zorder=3)
            
            if vmax < 0.5:
                label_fmt = '%.2f'
                decimal_places = 2
            else:
                label_fmt = '%.1f'
                decimal_places = 1
            
            ax.clabel(cs, inline=True, fontsize=8, fmt=label_fmt)
            
            # 添加颜色条
            cb = plt.colorbar(pcm, ax=ax, orientation='horizontal', fraction=0.05, pad=0.06, aspect=40)
            cb_ticks = list(contour_levels)
            if len(cb_ticks) > 0:
                last_contour_level = cb_ticks[-1]
                vmax_rounded = round(vmax, decimal_places)
                last_level_rounded = round(last_contour_level, decimal_places)
                if vmax_rounded != last_level_rounded:
                    cb_ticks.append(vmax)
            elif vmax not in cb_ticks:
                cb_ticks.append(vmax)
            cb_ticks = sorted(cb_ticks)
            cb.set_ticks(cb_ticks)
            from matplotlib.ticker import FormatStrFormatter
            cb.ax.xaxis.set_major_formatter(FormatStrFormatter(label_fmt))
            cb.set_label(varlabel)
            
            # 标题
            time_str = t_target.strftime('%Y-%m-%d %H:%M UTC')
            wind_info = ""
            if manual_wind is not None:
                wind_info = f" | Wind {manual_wind:.1f} m/s"
            else:
                if u10_data is not None:
                    u_now = u10_data[np.ix_(lat_idx, lon_idx, [tid])][:, :, 0]
                    if v10_data is not None:
                        v_now = v10_data[np.ix_(lat_idx, lon_idx, [tid])][:, :, 0]
                    else:
                        v_now = 0.0
                    wind_speed_now = np.sqrt(u_now ** 2 + v_now ** 2)
                    if np.nanmax(wind_speed_now) - np.nanmin(wind_speed_now) < 1e-6:
                        ws = float(np.nanmean(wind_speed_now))
                        wind_info = f" | Wind {ws:.1f} m/s (uniform)"
            title_text = f"{varlabel} Contour  {time_str}{wind_info}"
            ax.set_title(title_text, fontsize=14)
            
            outname = os.path.join(photo_folder, f"{prefix}_{t_target.strftime('%Y%m%d_%H%M')}.png")
            plt.savefig(outname, dpi=DPI, bbox_inches='tight')
            plt.close(fig)
            saved_files.append(outname)
            num += 1
        
        matplotlib.use(original_backend)
        
        log(tr("plotting_contour_complete", "✅ 生成等高线图完成，共 {count} 张").format(count=num))
        result_queue.put(saved_files)
        log_queue.put("__DONE__")
        
    except Exception as e:
        import traceback
        log_queue.put(tr("plotting_contour_failed", "❌ 生成等高线图失败：{error}").format(error=e))
        log_queue.put(traceback.format_exc())
        result_queue.put([])
        log_queue.put("__DONE__")


def _generate_first_spectrum_worker(selected_folder, log_queue, result_queue, energy_threshold=0.01, spec_file=None):
    """生成第一张二维谱图的 worker 函数（参考 plot_matlab.py）"""
    try:
        def log(msg):
            """发送日志到队列"""
            try:
                log_queue.put(msg)
            except:
                pass
        
        log(tr("plotting_start_first_spectrum", "🔄 开始生成第一张二维谱图（在子进程中执行）..."))
        
        # 如果指定了文件，使用指定的文件；否则查找 ww3*spec*nc 格式的文件
        if spec_file and os.path.exists(spec_file):
            spec_files = [spec_file]
        else:
            spec_files = glob.glob(os.path.join(selected_folder, "ww3*spec*nc"))
        
        if not spec_files:
            log(tr("plotting_spectrum_file_not_found", "❌ 未找到二维谱文件，请先选择文件"))
            log_queue.put("__DONE__")
            result_queue.put(None)
            return
        
        spec_file = spec_files[0]
        
        # 切换到 Agg 后端用于生成图片
        original_backend = matplotlib.get_backend()
        matplotlib.use("Agg")
        
        try:
            # 读取 NetCDF 文件
            with nc.Dataset(spec_file, 'r') as ds:
                freq = ds.variables['frequency'][:].data  # Hz
                dir_orig = ds.variables['direction'][:].data  # degree
                efth = ds.variables['efth'][:]  # m^2
                time = ds.variables['time'][:].data
                
                # 读取站点信息
                lon = ds.variables['longitude'][:].data
                lat = ds.variables['latitude'][:].data
                nStation = len(ds.dimensions['station'])
            
            # 精简日志：不输出读取统计
            
            # 转换时间
            t0 = datetime(1990, 1, 1, 0, 0, 0)
            time_dt = [t0 + timedelta(days=float(t)) for t in time]
            
            # 选择第一个时间步和第一个站点
            itime = 0
            istation = 0
            
            # 获取数据 (time, station, frequency, direction)
            E = efth[itime, istation, :, :]  # 获取 (frequency, direction)
            E = E.T  # 转置为 (direction, frequency) 以匹配 MATLAB
            
            log(tr("plotting_processing_station", "📊 处理站点 {station}，时间：{time}").format(station=istation + 1, time=time_dt[itime].strftime('%Y-%m-%d %H:%M:%S')))
            
            # 方向维标准化 + 周期插值
            dir0 = dir_orig.copy()
            dir0 = np.mod(dir0, 360)
            idx = np.argsort(dir0)
            dir_sort = dir0[idx]
            E_sort = E[idx, :]
            
            # 周期闭合
            dir_ext = np.concatenate([dir_sort, [dir_sort[0] + 360]])
            n_freq = len(freq)
            
            # 高分辨率方向 - 0.5度间隔
            theta_deg_full = np.linspace(0, 360, 721)
            
            E_interp = np.zeros((len(theta_deg_full), n_freq))
            
            from scipy.interpolate import PchipInterpolator
            for i in range(n_freq):
                E_ext = np.concatenate([E_sort[:, i], [E_sort[0, i]]])
                interp_func = PchipInterpolator(dir_ext, E_ext, extrapolate=False)
                E_interp[:, i] = interp_func(theta_deg_full)
            
            # 极坐标 → 笛卡尔坐标
            theta_deg_full_rad = np.deg2rad(90 - theta_deg_full)
            Theta, R = np.meshgrid(theta_deg_full_rad, freq)
            X = R * np.cos(Theta)
            Y = R * np.sin(Theta)
            
            # 绘制二维谱
            fig = plt.figure(figsize=(8, 7.5), facecolor='white')
            ax = fig.add_axes([0.08, 0.08, 0.68, 0.84])
            
            # 计算数据范围
            data_min = np.nanmin(E_interp)
            data_max = np.nanmax(E_interp)
            
            # 使用传入的阈值：能量密度低于阈值的显示为白色
            threshold = float(energy_threshold)
            
            # 检查阈值是否大于最大值，如果是则自动调整为0（防止 minvalue > maxvalue 错误）
            original_threshold = threshold
            if threshold > data_max:
                log(tr("plotting_threshold_too_high", "⚠️ 最低能量密度 ({threshold}) 大于数据最大值 ({max})，自动调整为 0").format(threshold=threshold, max=f"{data_max:.6f}"))
                threshold = 0.0
            
            # 生成刻度值的函数
            def generate_ticks(min_val, max_val):
                range_val = max_val - min_val
                if range_val <= 0:
                    return np.array([min_val, max_val])
                
                rough_step = range_val / 6
                if rough_step > 0:
                    magnitude = 10 ** np.floor(np.log10(rough_step))
                    normalized = rough_step / magnitude
                    
                    if normalized <= 0.5:
                        step = 0.5 * magnitude
                    elif normalized <= 1:
                        step = 1 * magnitude
                    elif normalized <= 2:
                        step = 2 * magnitude
                    elif normalized <= 5:
                        step = 5 * magnitude
                    else:
                        step = 10 * magnitude
                else:
                    step = 0.1
                
                start = np.floor(min_val / step) * step
                ticks = []
                current = start
                while current <= max_val + step * 0.01:
                    ticks.append(current)
                    current += step
                
                filtered_ticks = []
                for tick in ticks:
                    tick_str = f"{tick:.10f}"
                    digits = [c for c in tick_str if c.isdigit()]
                    if len(digits) > 0:
                        last_digit = digits[-1]
                        if last_digit == '0' or last_digit == '5':
                            filtered_ticks.append(tick)
                            continue
                    
                    if abs(tick - round(tick)) < 1e-10:
                        int_val = int(round(tick))
                        if int_val % 10 == 0 or int_val % 10 == 5:
                            filtered_ticks.append(tick)
                
                if len(filtered_ticks) == 0:
                    filtered_ticks = ticks
                
                filtered_ticks = sorted(set(filtered_ticks))
                if filtered_ticks[0] > min_val:
                    filtered_ticks.insert(0, min_val)
                if filtered_ticks[-1] < max_val:
                    filtered_ticks.append(max_val)
                
                return np.array(filtered_ticks)
            
            # 格式化刻度标签
            def format_tick_label(value):
                if abs(value) < 0.01:
                    return f'{value:.2e}'
                else:
                    return f'{value:.2f}'
            
            # 绘制等高线填充图
            levels = 200
            cmap = plt.get_cmap('jet')
            cmap.set_under('white')
            
            # 确保 vmin <= vmax（防止 minvalue > maxvalue 错误）
            vmin_actual = min(threshold, data_max)
            vmax_actual = data_max
            if vmin_actual >= vmax_actual:
                # 如果阈值大于等于最大值，使用0作为最小值
                log(tr("plotting_threshold_ge_max", "⚠️ 阈值 ({threshold}) >= 最大值 ({max})，使用 0 作为最小值").format(threshold=threshold, max=f"{data_max:.6f}"))
                vmin_actual = 0.0
                if vmax_actual <= vmin_actual:
                    # 如果所有数据都是0或nan，稍微调整范围
                    vmax_actual = max(1e-10, abs(data_max))
            
            try:
                pcm = ax.contourf(X, Y, E_interp.T, levels=levels, cmap=cmap, 
                                vmin=vmin_actual, vmax=vmax_actual, extend='neither')
            except ValueError as e:
                # 捕获 minvalue must be less than or equal to maxvalue 错误
                error_msg = str(e).lower()
                if "minvalue" in error_msg or "maxvalue" in error_msg or "vmin" in error_msg or "vmax" in error_msg:
                    log(tr("plotting_threshold_range_error", "⚠️ 检测到阈值范围错误：{error}，自动将最低能量密度调整为 0").format(error=e))
                    threshold = 0.0
                    vmin_actual = 0.0
                    vmax_actual = max(data_max, 1e-10)  # 确保最大值大于0
                    pcm = ax.contourf(X, Y, E_interp.T, levels=levels, cmap=cmap, 
                                    vmin=vmin_actual, vmax=vmax_actual, extend='neither')
                else:
                    raise
            ax.set_aspect('equal')
            ax.axis('off')
            
            # 颜色条
            # 使用调整后的阈值和最大值
            cbar_min = vmin_actual
            cbar_max = vmax_actual
            cbar_ticks = generate_ticks(cbar_min, cbar_max)
            if cbar_min not in cbar_ticks:
                cbar_ticks = np.concatenate([[cbar_min], cbar_ticks])
                cbar_ticks = np.sort(cbar_ticks)
            
            if len(cbar_ticks) > 1:
                cbar_ticks = cbar_ticks[:-1]
            
            cbar_ticks = cbar_ticks[cbar_ticks >= cbar_min]
            tick_labels = [format_tick_label(tick) for tick in cbar_ticks]
            
            cb = plt.colorbar(pcm, ax=ax, fraction=0.03, pad=0.1, ticks=cbar_ticks)
            cb.set_ticklabels(tick_labels)
            cb.set_label('Energy Density (m²/hz/deg)', fontsize=9)
            cb.ax.tick_params(labelsize=9)
            
            # 标题
            lon_val = lon[istation, 0] if lon.ndim > 1 else lon[istation]
            lat_val = lat[istation, 0] if lat.ndim > 1 else lat[istation]
            title_str = f'Lon: {lon_val:.2f}°, Lat: {lat_val:.2f}°            {time_dt[itime].strftime("%Y-%m-%d %H:%M:%S")}'
            ax.set_title(title_str, fontsize=10, pad=10)
            
            # 极坐标方向标注
            dirs = np.arange(0, 360, 30)
            rmax = np.max(freq)
            
            # 绘制径向轴
            for ang in dirs:
                theta_rad = np.deg2rad(90 - ang)
                ax.plot([0, rmax * np.cos(theta_rad)], 
                       [0, rmax * np.sin(theta_rad)],
                       color='black', linewidth=0.5, alpha=0.5, linestyle='--')
            
            # 角度标签
            angle_labels = []
            for ang in dirs:
                x_pos = rmax * 1.12 * np.cos(np.deg2rad(90 - ang))
                y_pos = rmax * 1.12 * np.sin(np.deg2rad(90 - ang))
                label = f'{int(ang)}°'
                angle_labels.append((x_pos, y_pos, label))
            
            # 频率同心圆
            freq_target = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
            freq_max = np.max(freq)
            freq_plot = freq_target[freq_target <= freq_max]
            
            th = np.linspace(0, 2 * np.pi, 360)
            for i, rr in enumerate(freq_plot):
                ax.plot(rr * np.cos(th), rr * np.sin(th), 'k:', linewidth=0.5, linestyle='--', alpha=0.5)
                ax.text(0, rr * 1.03, f'{rr:.2f}',
                        ha='center', va='bottom', fontsize=6, color='black', alpha=0.5)
            
            # 外圈
            ax.plot(freq_max * np.cos(th), freq_max * np.sin(th), 'k-', linewidth=1.0, alpha=0.8, zorder=1)
            
            # 在文字位置绘制白色圆形背景和文字
            for x_pos, y_pos, label in angle_labels:
                circle_radius = 0.02 * freq_max
                circle = plt.Circle((x_pos, y_pos), circle_radius, color='white', 
                                   edgecolor='none', zorder=2)
                ax.add_patch(circle)
                ax.text(x_pos, y_pos, label, fontsize=10, ha='center', va='center', zorder=3)
            
            plt.tight_layout()
            
            # 调整颜色条高度
            ax_pos = ax.get_position()
            cbar_pos = cb.ax.get_position()
            cb.ax.set_position([cbar_pos.x0, ax_pos.y0, cbar_pos.width, ax_pos.height])
            
            # 保存图片
            photo_folder = os.path.join(selected_folder, 'photo')
            os.makedirs(photo_folder, exist_ok=True)
            output_file = os.path.join(photo_folder, 'spectrum_first.png')
            plt.savefig(output_file, dpi=400, bbox_inches='tight', 
                        facecolor='white', edgecolor='none', pad_inches=0.1)
            plt.close(fig)
            
            log(tr("plotting_spectrum_saved", "✅ 二维谱图已保存：{path}").format(path=output_file))
            result_queue.put(output_file)
            
        finally:
            # 恢复后端
            matplotlib.use(original_backend)
        
        log_queue.put("__DONE__")
        
    except Exception as e:
        import traceback
        log_queue.put(tr("plotting_generate_spectrum_failed", "❌ 生成二维谱图失败：{error}").format(error=e))
        log_queue.put(traceback.format_exc())
        result_queue.put(None)
        log_queue.put("__DONE__")


def _sanitize_filename(name):
    """清理站点名称，使其成为有效的文件名"""
    if not name:
        return ""
    # 移除或替换文件名中不允许的字符
    import re
    # 替换空格为下划线
    name = name.replace(" ", "_")
    # 移除或替换不允许的字符：/ \ : * ? " < > |
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    # 移除前后空格和下划线
    name = name.strip('_')
    # 如果清理后为空，返回默认值
    if not name:
        return "station"
    return name

def _generate_all_spectrum_worker(selected_folder, log_queue, result_queue, energy_threshold=0.01, spec_file=None, time_step_hours=24, plot_mode="最大值归一化", station_names=None):
    """生成所有二维谱图的 worker 函数（所有站点、根据时间步长筛选的时间）"""
    try:
        def log(msg):
            """发送日志到队列"""
            try:
                log_queue.put(msg)
            except:
                pass
        
        # 精简日志：不输出开始提示
        
        # 如果指定了文件，使用指定的文件；否则查找 ww3*spec*nc 格式的文件
        if spec_file and os.path.exists(spec_file):
            spec_files = [spec_file]
        else:
            spec_files = glob.glob(os.path.join(selected_folder, "ww3*spec*nc"))
        
        if not spec_files:
            log(tr("plotting_spectrum_file_not_found", "❌ 未找到二维谱文件，请先选择文件"))
            log_queue.put("__DONE__")
            result_queue.put(None)
            return
        
        spec_file = spec_files[0]
        
        # 切换到 Agg 后端用于生成图片
        original_backend = matplotlib.get_backend()
        matplotlib.use("Agg")
        
        try:
            # 读取 NetCDF 文件
            with nc.Dataset(spec_file, 'r') as ds:
                freq = ds.variables['frequency'][:].data  # Hz
                dir_orig = ds.variables['direction'][:].data  # degree
                efth = ds.variables['efth'][:]  # m^2
                time = ds.variables['time'][:].data
                
                # 读取站点信息
                lon = ds.variables['longitude'][:].data
                lat = ds.variables['latitude'][:].data
                nStation = len(ds.dimensions['station'])
                nTime = len(time)
            
            # 转换时间
            t0 = datetime(1990, 1, 1, 0, 0, 0)
            time_dt = [t0 + timedelta(days=float(t)) for t in time]
            
            # 根据时间步长筛选时间步
            time_step_hours_float = float(time_step_hours)
            selected_time_indices = []
            
            if len(time_dt) > 0:
                # 第一个时间步总是包含
                selected_time_indices.append(0)
                last_selected_time = time_dt[0]
                
                # 从第二个时间步开始，选择间隔大于等于 time_step_hours 的时间步
                for i in range(1, len(time_dt)):
                    time_diff = (time_dt[i] - last_selected_time).total_seconds() / 3600.0
                    if time_diff >= time_step_hours_float:
                        selected_time_indices.append(i)
                        last_selected_time = time_dt[i]
            
            nSelectedTime = len(selected_time_indices)
            
            if nSelectedTime == 0:
                log(tr("plotting_no_valid_timesteps", "❌ 没有符合时间步长要求的时间步"))
                log_queue.put("__DONE__")
                result_queue.put(None)
                return
            
            # 创建输出目录（保存到 photo/spectrum）
            photo_folder = os.path.join(selected_folder, 'photo', 'spectrum')
            os.makedirs(photo_folder, exist_ok=True)
            
            # 生成刻度值的函数（与第一个函数相同）
            def generate_ticks(min_val, max_val):
                range_val = max_val - min_val
                if range_val <= 0:
                    return np.array([min_val, max_val])
                
                rough_step = range_val / 6
                if rough_step > 0:
                    magnitude = 10 ** np.floor(np.log10(rough_step))
                    normalized = rough_step / magnitude
                    
                    if normalized <= 0.5:
                        step = 0.5 * magnitude
                    elif normalized <= 1:
                        step = 1 * magnitude
                    elif normalized <= 2:
                        step = 2 * magnitude
                    elif normalized <= 5:
                        step = 5 * magnitude
                    else:
                        step = 10 * magnitude
                else:
                    step = 0.1
                
                start = np.floor(min_val / step) * step
                ticks = []
                current = start
                while current <= max_val + step * 0.01:
                    ticks.append(current)
                    current += step
                
                filtered_ticks = []
                for tick in ticks:
                    tick_str = f"{tick:.10f}"
                    digits = [c for c in tick_str if c.isdigit()]
                    if len(digits) > 0:
                        last_digit = digits[-1]
                        if last_digit == '0' or last_digit == '5':
                            filtered_ticks.append(tick)
                            continue
                    
                    if abs(tick - round(tick)) < 1e-10:
                        int_val = int(round(tick))
                        if int_val % 10 == 0 or int_val % 10 == 5:
                            filtered_ticks.append(tick)
                
                if len(filtered_ticks) == 0:
                    filtered_ticks = ticks
                
                filtered_ticks = sorted(set(filtered_ticks))
                if filtered_ticks[0] > min_val:
                    filtered_ticks.insert(0, min_val)
                if filtered_ticks[-1] < max_val:
                    filtered_ticks.append(max_val)
                
                # 移除0值（如果存在，参考 plot_directional_spectrum.py）
                # 注意：对于归一化模式，0值会在 calculate_cbar_ticks 中单独处理
                filtered_ticks = [tick for tick in filtered_ticks if tick > 0]
                
                # 如果移除0后列表为空，至少保留最小值（如果大于0）
                if len(filtered_ticks) == 0 and min_val > 0:
                    filtered_ticks = [min_val]
                
                return np.array(filtered_ticks)
            
            # 格式化刻度标签
            def format_tick_label(value):
                if abs(value) < 0.01:
                    return f'{value:.2e}'
                else:
                    return f'{value:.2f}'
            
            # 计算归一化颜色条刻度值的函数（参考 plot_directional_spectrum.py）
            def calculate_cbar_ticks(data_min, data_max, generate_ticks_func):
                """
                计算颜色条的归一化刻度值（参考 plot_directional_spectrum.py）
                
                参数:
                    data_min: 数据最小值
                    data_max: 数据最大值
                    generate_ticks_func: 生成原始刻度值的函数
                
                返回:
                    cbar_ticks: 归一化后的刻度值数组（0到1之间）
                """
                # 生成原始数据的刻度值
                raw_ticks = generate_ticks_func(data_min, data_max)
                
                # 将刻度值归一化到 [0, 1] 范围（除以最大值）
                normalized_ticks = raw_ticks / data_max if data_max > 0 else raw_ticks
                
                # 计算最小值的归一化值
                min_normalized = data_min / data_max if data_max > 0 else data_min
                
                # 确保颜色条底部有足够的刻度显示
                filtered_normalized = []
                
                # 检查第一个归一化刻度值是否离底部太远
                first_normalized = normalized_ticks[0] if len(normalized_ticks) > 0 else 1.0
                
                # 如果第一个归一化刻度值大于0.1，说明底部有很大一段没有刻度
                if first_normalized > 0.1:
                    first_raw = raw_ticks[0] if len(raw_ticks) > 0 else data_max
                    bottom_range = first_raw - data_min
                    if bottom_range > 0:
                        ticks_above = len([t for t in normalized_ticks if t > first_normalized])
                        n_bottom_ticks = max(ticks_above + 2, 5)
                        
                        bottom_raw_ticks = generate_ticks_func(data_min, first_raw)
                        if len(bottom_raw_ticks) < n_bottom_ticks and bottom_range > 0:
                            bottom_raw_ticks = np.linspace(data_min, first_raw, n_bottom_ticks + 1)[1:-1]
                        
                        bottom_normalized = bottom_raw_ticks / data_max if data_max > 0 else bottom_raw_ticks
                        bottom_normalized_filtered = [t for t in bottom_normalized if t >= 0.005]
                        
                        if len(bottom_normalized_filtered) < n_bottom_ticks - 1:
                            bottom_normalized_filtered = [t for t in bottom_normalized if t > 0]
                        
                        if len(bottom_normalized_filtered) == 0 and len(bottom_normalized) > 0:
                            bottom_normalized_filtered = sorted(bottom_normalized)[:min(3, len(bottom_normalized))]
                        
                        filtered_normalized.extend(bottom_normalized_filtered)
                elif data_min > 0 and min_normalized > 0:
                    if min_normalized >= 0.01:
                        filtered_normalized.append(min_normalized)
                    elif data_max - data_min < data_max * 0.1:
                        filtered_normalized.append(min_normalized)
                
                # 使用动态阈值过滤刻度值
                if min_normalized < 0.01:
                    threshold = 0.1
                elif min_normalized < 0.05:
                    threshold = 0.05
                else:
                    threshold = 0.01
                
                for tick in normalized_ticks:
                    if tick >= threshold and tick not in filtered_normalized:
                        filtered_normalized.append(tick)
                
                if len(filtered_normalized) < 3:
                    threshold = max(0.01, threshold * 0.5)
                    existing_bottom = [t for t in filtered_normalized if t < threshold]
                    filtered_normalized = existing_bottom if existing_bottom else []
                    for tick in normalized_ticks:
                        if tick >= threshold and tick not in filtered_normalized:
                            filtered_normalized.append(tick)
                
                # 确保包含最大值（归一化后为1.0）
                if len(filtered_normalized) == 0 or (len(filtered_normalized) > 0 and filtered_normalized[-1] < 0.99):
                    if data_max > 0:
                        filtered_normalized.append(1.0)
                # 对于归一化模式，确保包含0（最小值）
                if data_min == 0.0 and (len(filtered_normalized) == 0 or filtered_normalized[0] > 0.01):
                    filtered_normalized.insert(0, 0.0)
                
                # 去重并排序
                cbar_ticks = np.array(sorted(set(filtered_normalized)))
                
                return cbar_ticks
            
            # 方向维标准化 + 周期插值（辅助函数）
            def process_spectrum_data(E, dir_orig, freq):
                """处理单个站点的谱数据"""
                dir0 = dir_orig.copy()
                dir0 = np.mod(dir0, 360)
                idx = np.argsort(dir0)
                dir_sort = dir0[idx]
                E_sort = E[idx, :]
                
                # 周期闭合
                dir_ext = np.concatenate([dir_sort, [dir_sort[0] + 360]])
                n_freq = len(freq)
                
                # 高分辨率方向 - 0.5度间隔
                theta_deg_full = np.linspace(0, 360, 721)
                
                E_interp = np.zeros((len(theta_deg_full), n_freq))
                
                from scipy.interpolate import PchipInterpolator
                for i in range(n_freq):
                    E_ext = np.concatenate([E_sort[:, i], [E_sort[0, i]]])
                    interp_func = PchipInterpolator(dir_ext, E_ext, extrapolate=False)
                    E_interp[:, i] = interp_func(theta_deg_full)
                
                # 极坐标 → 笛卡尔坐标
                theta_deg_full_rad = np.deg2rad(90 - theta_deg_full)
                Theta, R = np.meshgrid(theta_deg_full_rad, freq)
                X = R * np.cos(Theta)
                Y = R * np.sin(Theta)
                
                return X, Y, E_interp
            
            # 绘制单个二维谱图（辅助函数，归一化模式使用 wavespectra 框架）
            def plot_single_spectrum(X, Y, E_interp, threshold, lon_val, lat_val, time_str, output_file, plot_mode="最大值归一化", E_original=None, freq_orig=None, dir_orig=None):
                """绘制单个二维谱图
                
                参数:
                    X, Y: 笛卡尔坐标（用于实际值模式）
                    E_interp: 插值后的能量密度数据（用于实际值模式）
                    threshold: 能量阈值
                    lon_val, lat_val: 站点经纬度
                    time_str: 时间字符串
                    output_file: 输出文件路径
                    plot_mode: 绘制模式（"最大值归一化" 或 "实际值"）
                    E_original: 原始能量密度数据 (frequency, direction)，用于归一化模式（wavespectra）
                    freq_orig: 原始频率数组，用于归一化模式
                    dir_orig: 原始方向数组，用于归一化模式
                """
                # 检查是否为归一化模式（支持中英文翻译）
                normalized_text_zh = tr("plotting_plot_mode_normalized", "最大值归一化")
                normalized_text_en = "Max Normalized"  # 英文翻译
                is_normalized = (plot_mode == "最大值归一化" or 
                                plot_mode == normalized_text_zh or 
                                plot_mode == normalized_text_en or
                                plot_mode == "normalized")
                
                if is_normalized and HAS_WAVESPECTRA and E_original is not None and freq_orig is not None and dir_orig is not None:
                    # 使用 wavespectra 框架绘制归一化图（参考 plot_directional_spectrum.py）
                    import xarray as xr
                    
                    # 创建 xarray DataArray（wavespectra 需要）
                    # E_original 应该是 (frequency, direction) 形状
                    # wavespectra 期望 (freq, dir) 坐标
                    efth_da = xr.DataArray(
                        E_original,  # (freq, dir)
                        dims=['freq', 'dir'],
                        coords={'freq': freq_orig, 'dir': dir_orig},
                        name='efth'
                    )
                    
                    # 转换为 SpecArray
                    spec_array = SpecArray(efth_da)
                    
                    # 计算数据范围，用于生成颜色条刻度
                    data_min = float(np.nanmin(E_original))
                    data_max = float(np.nanmax(E_original))
                    
                    # 使用函数计算归一化后的颜色条刻度值
                    cbar_ticks = calculate_cbar_ticks(data_min, data_max, generate_ticks)
                    
                    # 使用 jet 颜色映射（参考文件）
                    cmap = plt.get_cmap('jet')
                    
                    # 使用 wavespectra 的 plot 方法绘制（自动归一化）
                    # 计算 rmax（最大频率）
                    rmax = np.max(freq_orig)
                    
                    # 计算频率刻度（参考文件使用 [0.04,0.1,0.25,0.59]）
                    freq_target = np.array([0.04, 0.1, 0.25, 0.59])
                    radii_ticks = freq_target[freq_target <= rmax].tolist()
                    if len(radii_ticks) == 0:
                        radii_ticks = [rmax * 0.2, rmax * 0.4, rmax * 0.6, rmax * 0.8]
                    
                    pobj = spec_array.plot(
                        figsize=(10, 10),
                        cmap=cmap,
                        rmax=rmax if rmax <= 3 else 3,
                        radii_ticks=radii_ticks if len(radii_ticks) > 0 else None
                    )
                    
                    # 获取当前图形和坐标轴
                    fig = plt.gcf()
                    ax = plt.gca()
                    
                    # 保持图像不变：0度在底部（南），顺时针方向（参考文件）
                    ax.set_theta_zero_location('S')
                    ax.set_theta_direction(-1)
                    
                    # 只修改标签文本，让0度标签显示在顶部位置（参考文件）
                    angles_deg = np.arange(0, 360, 30)
                    label_texts = []
                    for angle in angles_deg:
                        label_angle = (angle + 180) % 360
                        label_texts.append(f'{int(label_angle)}°')
                    
                    # 设置标签，保持网格位置不变（角度位置不变）
                    ax.set_thetagrids(angles_deg, labels=label_texts)
                    
                    # 设置标题，显示站点信息
                    ax.set_title(f'Lon: {lon_val:.2f}°, Lat: {lat_val:.2f}°            {time_str}', 
                                fontsize=10, pad=20)
                    
                    # 修改颜色条刻度（wavespectra 自动归一化，刻度值应该是归一化的）
                    # wavespectra 的 plot 方法会自动创建颜色条，尝试找到它
                    cb = None
                    # 方法1：从 pobj 对象获取（如果可用）
                    if hasattr(pobj, 'handles') and hasattr(pobj.handles, 'colorbar'):
                        cb = pobj.handles.colorbar
                    # 方法2：从 pobj 的 mappable 对象获取颜色条
                    if cb is None and hasattr(pobj, 'mappable'):
                        try:
                            cb = fig.colorbar(pobj.mappable, ax=ax)
                        except:
                            pass
                    # 方法3：从 figure 的所有子对象中查找（使用 hasattr 检查颜色条特征）
                    if cb is None:
                        for item in fig.axes:
                            # 颜色条通常有这些方法：set_ticks, set_ticklabels, set_label, update_normal
                            if (hasattr(item, 'set_ticks') and hasattr(item, 'set_ticklabels') and 
                                hasattr(item, 'set_label') and hasattr(item, 'update_normal')):
                                cb = item
                                break
                    # 方法4：从 figure 的所有子对象中查找（通过 get_children，检查颜色条特征）
                    if cb is None:
                        for item in fig.get_children():
                            if (hasattr(item, 'set_ticks') and hasattr(item, 'set_ticklabels') and 
                                hasattr(item, 'set_label') and hasattr(item, 'update_normal')):
                                cb = item
                                break
                    
                    # 如果找到了颜色条，修改其刻度
                    if cb is not None:
                        try:
                            # 设置归一化刻度
                            cb.set_ticks(cbar_ticks)
                            tick_labels = [format_tick_label(tick) for tick in cbar_ticks]
                            cb.set_ticklabels(tick_labels)
                            cb.set_label('Normalized Energy Density', fontsize=9)
                            if hasattr(cb, 'ax'):
                                cb.ax.tick_params(labelsize=9)
                        except Exception as e:
                            # 如果修改颜色条失败，记录但不中断执行（wavespectra 可能有自己的颜色条实现）
                            pass
                    
                    # 保存图片
                    plt.tight_layout()
                    plt.savefig(output_file, dpi=400, bbox_inches='tight', 
                                facecolor='white', edgecolor='none', pad_inches=0.1)
                    plt.close(fig)
                    
                else:
                    # 实际值模式，使用手动绘制方法（原有逻辑）
                    # 计算原始数据范围（归一化前）
                    original_data_min = np.nanmin(E_interp)
                    original_data_max = np.nanmax(E_interp)
                    
                    # 实际值模式
                    data_min = original_data_min
                    data_max = original_data_max
                    
                    # 检查阈值
                    adjusted_threshold = float(threshold)
                    if adjusted_threshold > data_max:
                        adjusted_threshold = 0.0
                    
                    # 确保 vmin <= vmax
                    vmin_actual = min(adjusted_threshold, data_max)
                    vmax_actual = data_max
                    if vmin_actual >= vmax_actual:
                        vmin_actual = 0.0
                        if vmax_actual <= vmin_actual:
                            vmax_actual = max(1e-10, abs(data_max))
                    
                    # 绘制二维谱
                    fig = plt.figure(figsize=(8, 7.5), facecolor='white')
                    ax = fig.add_axes([0.08, 0.08, 0.68, 0.84])
                    
                    levels = 200
                    cmap = plt.get_cmap('jet')
                    cmap.set_under('white')
                    
                    try:
                        pcm = ax.contourf(X, Y, E_interp.T, levels=levels, cmap=cmap, 
                                        vmin=vmin_actual, vmax=vmax_actual, extend='neither')
                    except ValueError as e:
                        error_msg = str(e).lower()
                        if "minvalue" in error_msg or "maxvalue" in error_msg or "vmin" in error_msg or "vmax" in error_msg:
                            adjusted_threshold = 0.0
                            vmin_actual = 0.0
                            vmax_actual = max(data_max, 1e-10)
                            pcm = ax.contourf(X, Y, E_interp.T, levels=levels, cmap=cmap, 
                                            vmin=vmin_actual, vmax=vmax_actual, extend='neither')
                        else:
                            raise
                    
                    ax.set_aspect('equal')
                    ax.axis('off')
                    
                    # 颜色条
                    cbar_min = vmin_actual
                    cbar_max = vmax_actual
                    cbar_ticks = generate_ticks(cbar_min, cbar_max)
                    if cbar_min not in cbar_ticks:
                        cbar_ticks = np.concatenate([[cbar_min], cbar_ticks])
                        cbar_ticks = np.sort(cbar_ticks)
                    if len(cbar_ticks) > 1:
                        cbar_ticks = cbar_ticks[:-1]
                    cbar_ticks = cbar_ticks[cbar_ticks >= cbar_min]
                    tick_labels = [format_tick_label(tick) for tick in cbar_ticks]
                    
                    cb = plt.colorbar(pcm, ax=ax, fraction=0.03, pad=0.1, ticks=cbar_ticks)
                    cb.set_ticklabels(tick_labels)
                    cb.set_label('Energy Density (m²/hz/deg)', fontsize=9)
                    cb.ax.tick_params(labelsize=9)
                    
                    # 标题
                    title_str = f'Lon: {lon_val:.2f}°, Lat: {lat_val:.2f}°            {time_str}'
                    ax.set_title(title_str, fontsize=10, pad=10)
                    
                    # 极坐标方向标注
                    dirs = np.arange(0, 360, 30)
                    rmax = np.max(freq)
                    
                    # 绘制径向轴
                    for ang in dirs:
                        theta_rad = np.deg2rad(90 - ang)
                        ax.plot([0, rmax * np.cos(theta_rad)], 
                               [0, rmax * np.sin(theta_rad)],
                               color='black', linewidth=0.5, alpha=0.5, linestyle='--')
                    
                    # 角度标签
                    angle_labels = []
                    for ang in dirs:
                        x_pos = rmax * 1.12 * np.cos(np.deg2rad(90 - ang))
                        y_pos = rmax * 1.12 * np.sin(np.deg2rad(90 - ang))
                        label = f'{int(ang)}°'
                        angle_labels.append((x_pos, y_pos, label))
                    
                    # 频率同心圆
                    freq_target = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
                    freq_max = np.max(freq)
                    freq_plot = freq_target[freq_target <= freq_max]
                    
                    th = np.linspace(0, 2 * np.pi, 360)
                    for i, rr in enumerate(freq_plot):
                        ax.plot(rr * np.cos(th), rr * np.sin(th), 'k:', linewidth=0.5, linestyle='--', alpha=0.5)
                        ax.text(0, rr * 1.03, f'{rr:.2f}',
                                ha='center', va='bottom', fontsize=6, color='black', alpha=0.5)
                    
                    # 外圈
                    ax.plot(freq_max * np.cos(th), freq_max * np.sin(th), 'k-', linewidth=1.0, alpha=0.8, zorder=1)
                    
                    # 在文字位置绘制白色圆形背景和文字
                    for x_pos, y_pos, label in angle_labels:
                        circle_radius = 0.02 * freq_max
                        circle = plt.Circle((x_pos, y_pos), circle_radius, color='white', 
                                           edgecolor='none', zorder=2)
                        ax.add_patch(circle)
                        ax.text(x_pos, y_pos, label, fontsize=10, ha='center', va='center', zorder=3)
                    
                    plt.tight_layout()
                    
                    # 调整颜色条高度
                    ax_pos = ax.get_position()
                    cbar_pos = cb.ax.get_position()
                    cb.ax.set_position([cbar_pos.x0, ax_pos.y0, cbar_pos.width, ax_pos.height])
                    
                    # 保存图片
                    plt.savefig(output_file, dpi=400, bbox_inches='tight', 
                                facecolor='white', edgecolor='none', pad_inches=0.1)
                    plt.close(fig)
            
            # 遍历所有站点和筛选后的时间步
            total_count = nStation * nSelectedTime
            current_count = 0
            success_count = 0
            
            for time_idx, itime in enumerate(selected_time_indices):
                for istation in range(nStation):
                    current_count += 1
                    
                    try:
                        # 获取数据 (time, station, frequency, direction)
                        E_original = efth[itime, istation, :, :]  # 获取 (frequency, direction)，用于 wavespectra
                        E = E_original.T  # 转置为 (direction, frequency)，用于手动绘制
                        
                        # 处理数据（用于实际值模式的手动绘制）
                        X, Y, E_interp = process_spectrum_data(E, dir_orig, freq)
                        
                        # 获取站点信息
                        lon_val = lon[istation, 0] if lon.ndim > 1 else lon[istation]
                        lat_val = lat[istation, 0] if lat.ndim > 1 else lat[istation]
                        time_str = time_dt[itime].strftime("%Y-%m-%d %H:%M:%S")
                        
                        # 获取站点名称（如果提供了站点名称列表）
                        if station_names and istation < len(station_names):
                            station_name = _sanitize_filename(station_names[istation])
                        else:
                            station_name = f"station_{istation+1:03d}"
                        
                        # 生成输出文件名（使用站点名称）
                        time_str_file = time_dt[itime].strftime("%Y%m%d_%H%M%S")
                        output_file = os.path.join(photo_folder, 
                                                  f'spectrum_{station_name}_time_{time_str_file}.png')
                        
                        # 绘制并保存（传入原始数据用于归一化模式）
                        plot_single_spectrum(X, Y, E_interp, energy_threshold, 
                                           lon_val, lat_val, time_str, output_file, plot_mode,
                                           E_original=E_original, freq_orig=freq, dir_orig=dir_orig)
                        
                        success_count += 1
                        
                        # 生成进度（每10张或最后一张）
                        if current_count % 10 == 0 or current_count == total_count:
                            log(tr("plotting_progress_all_spectrum", "📊 进度：{current}/{total} ({success} 成功)").format(current=current_count, total=total_count, success=success_count))
                    
                    except Exception as e:
                        log(tr("plotting_generate_station_timestep_failed", "❌ 生成站点 {station} 时间步 {timestep} 失败：{error}").format(station=istation+1, timestep=itime+1, error=e))
                        continue
            
            result_queue.put(photo_folder)
            
        finally:
            # 恢复后端
            matplotlib.use(original_backend)
        
        log_queue.put("__DONE__")
        
    except Exception as e:
        import traceback
        log_queue.put(tr("plotting_generate_all_spectrum_failed", "❌ 生成所有二维谱图失败：{error}").format(error=e))
        log_queue.put(traceback.format_exc())
        result_queue.put(None)
        log_queue.put("__DONE__")


def _generate_selected_spectrum_worker(selected_folder, log_queue, result_queue, energy_threshold=0.01, spec_file=None, time_step_hours=24, station_index=0, plot_mode="最大值归一化", station_name=None):
    """生成选中站点的二维谱图 worker 函数（单个站点、根据时间步长筛选的时间）"""
    try:
        def log(msg):
            """发送日志到队列"""
            try:
                log_queue.put(msg)
            except:
                pass
        
        log(tr("plotting_start_selected_spectrum", "🔄 开始生成选中站点的二维谱图（站点索引：{index}，时间步长：{hours}小时，在子进程中执行）...").format(index=station_index, hours=time_step_hours))
        
        # 如果指定了文件，使用指定的文件；否则查找 ww3*spec*nc 格式的文件
        if spec_file and os.path.exists(spec_file):
            spec_files = [spec_file]
        else:
            spec_files = glob.glob(os.path.join(selected_folder, "ww3*spec*nc"))
        
        if not spec_files:
            log(tr("plotting_spectrum_file_not_found", "❌ 未找到二维谱文件，请先选择文件"))
            log_queue.put("__DONE__")
            result_queue.put(None)
            return
        
        spec_file = spec_files[0]
        
        # 切换到 Agg 后端用于生成图片
        original_backend = matplotlib.get_backend()
        matplotlib.use("Agg")
        
        try:
            # 读取 NetCDF 文件
            with nc.Dataset(spec_file, 'r') as ds:
                freq = ds.variables['frequency'][:].data  # Hz
                dir_orig = ds.variables['direction'][:].data  # degree
                efth = ds.variables['efth'][:]  # m^2
                time = ds.variables['time'][:].data
                
                # 读取站点信息
                lon = ds.variables['longitude'][:].data
                lat = ds.variables['latitude'][:].data
                nStation = len(ds.dimensions['station'])
                nTime = len(time)
            
            # 检查站点索引是否有效
            if station_index < 0 or station_index >= nStation:
                log(tr("plotting_invalid_station_index", "❌ 站点索引 {index} 无效，文件中共有 {total} 个站点").format(index=station_index, total=nStation))
                log_queue.put("__DONE__")
                result_queue.put(None)
                return
            
            # 转换时间
            t0 = datetime(1990, 1, 1, 0, 0, 0)
            time_dt = [t0 + timedelta(days=float(t)) for t in time]
            
            # 根据时间步长筛选时间步
            time_step_hours_float = float(time_step_hours)
            selected_time_indices = []
            
            if len(time_dt) > 0:
                # 第一个时间步总是包含
                selected_time_indices.append(0)
                last_selected_time = time_dt[0]
                
                # 从第二个时间步开始，选择间隔大于等于 time_step_hours 的时间步
                for i in range(1, len(time_dt)):
                    time_diff = (time_dt[i] - last_selected_time).total_seconds() / 3600.0
                    if time_diff >= time_step_hours_float:
                        selected_time_indices.append(i)
                        last_selected_time = time_dt[i]
            
            nSelectedTime = len(selected_time_indices)
            
            if nSelectedTime == 0:
                log(tr("plotting_no_valid_timesteps", "❌ 没有符合时间步长要求的时间步"))
                log_queue.put("__DONE__")
                result_queue.put(None)
                return
            
            # 创建输出目录（保存到 photo/spectrum）
            photo_folder = os.path.join(selected_folder, 'photo', 'spectrum')
            os.makedirs(photo_folder, exist_ok=True)
            
            # 复用 _generate_all_spectrum_worker 中的辅助函数
            # 生成刻度值的函数
            def generate_ticks(min_val, max_val):
                range_val = max_val - min_val
                if range_val <= 0:
                    return np.array([min_val, max_val])
                
                rough_step = range_val / 6
                if rough_step > 0:
                    magnitude = 10 ** np.floor(np.log10(rough_step))
                    normalized = rough_step / magnitude
                    
                    if normalized <= 0.5:
                        step = 0.5 * magnitude
                    elif normalized <= 1:
                        step = 1 * magnitude
                    elif normalized <= 2:
                        step = 2 * magnitude
                    elif normalized <= 5:
                        step = 5 * magnitude
                    else:
                        step = 10 * magnitude
                else:
                    step = 0.1
                
                start = np.floor(min_val / step) * step
                ticks = []
                current = start
                while current <= max_val + step * 0.01:
                    ticks.append(current)
                    current += step
                
                filtered_ticks = []
                for tick in ticks:
                    tick_str = f"{tick:.10f}"
                    digits = [c for c in tick_str if c.isdigit()]
                    if len(digits) > 0:
                        last_digit = digits[-1]
                        if last_digit == '0' or last_digit == '5':
                            filtered_ticks.append(tick)
                            continue
                    
                    if abs(tick - round(tick)) < 1e-10:
                        int_val = int(round(tick))
                        if int_val % 10 == 0 or int_val % 10 == 5:
                            filtered_ticks.append(tick)
                
                if len(filtered_ticks) == 0:
                    filtered_ticks = ticks
                
                filtered_ticks = sorted(set(filtered_ticks))
                if filtered_ticks[0] > min_val:
                    filtered_ticks.insert(0, min_val)
                if filtered_ticks[-1] < max_val:
                    filtered_ticks.append(max_val)
                
                # 移除0值（如果存在，参考 plot_directional_spectrum.py）
                # 注意：对于归一化模式，0值会在 calculate_cbar_ticks 中单独处理
                filtered_ticks = [tick for tick in filtered_ticks if tick > 0]
                
                # 如果移除0后列表为空，至少保留最小值（如果大于0）
                if len(filtered_ticks) == 0 and min_val > 0:
                    filtered_ticks = [min_val]
                
                return np.array(filtered_ticks)
            
            # 格式化刻度标签
            def format_tick_label(value):
                if abs(value) < 0.01:
                    return f'{value:.2e}'
                else:
                    return f'{value:.2f}'
            
            # 计算归一化颜色条刻度值的函数（参考 plot_directional_spectrum.py）
            def calculate_cbar_ticks(data_min, data_max, generate_ticks_func):
                """
                计算颜色条的归一化刻度值（参考 plot_directional_spectrum.py）
                
                参数:
                    data_min: 数据最小值（归一化模式下应该是0）
                    data_max: 数据最大值（归一化模式下应该是1）
                    generate_ticks_func: 生成原始刻度值的函数
                
                返回:
                    cbar_ticks: 归一化后的刻度值数组（0到1之间）
                """
                # 生成原始数据的刻度值
                raw_ticks = generate_ticks_func(data_min, data_max)
                
                # 将刻度值归一化到 [0, 1] 范围（除以最大值）
                # 注意：对于归一化模式，data_min=0, data_max=1，所以归一化后值不变
                normalized_ticks = raw_ticks / data_max if data_max > 0 else raw_ticks
                
                # 计算最小值的归一化值
                min_normalized = data_min / data_max if data_max > 0 else data_min
                
                # 确保颜色条底部有足够的刻度显示
                filtered_normalized = []
                
                # 检查第一个归一化刻度值是否离底部太远
                first_normalized = normalized_ticks[0] if len(normalized_ticks) > 0 else 1.0
                
                # 如果第一个归一化刻度值大于0.1，说明底部有很大一段没有刻度
                if first_normalized > 0.1:
                    first_raw = raw_ticks[0] if len(raw_ticks) > 0 else data_max
                    bottom_range = first_raw - data_min
                    if bottom_range > 0:
                        ticks_above = len([t for t in normalized_ticks if t > first_normalized])
                        n_bottom_ticks = max(ticks_above + 2, 5)
                        
                        bottom_raw_ticks = generate_ticks_func(data_min, first_raw)
                        if len(bottom_raw_ticks) < n_bottom_ticks and bottom_range > 0:
                            bottom_raw_ticks = np.linspace(data_min, first_raw, n_bottom_ticks + 1)[1:-1]
                        
                        bottom_normalized = bottom_raw_ticks / data_max if data_max > 0 else bottom_raw_ticks
                        bottom_normalized_filtered = [t for t in bottom_normalized if t >= 0.005]
                        
                        if len(bottom_normalized_filtered) < n_bottom_ticks - 1:
                            bottom_normalized_filtered = [t for t in bottom_normalized if t > 0]
                        
                        if len(bottom_normalized_filtered) == 0 and len(bottom_normalized) > 0:
                            bottom_normalized_filtered = sorted(bottom_normalized)[:min(3, len(bottom_normalized))]
                        
                        filtered_normalized.extend(bottom_normalized_filtered)
                elif data_min > 0 and min_normalized > 0:
                    if min_normalized >= 0.01:
                        filtered_normalized.append(min_normalized)
                    elif data_max - data_min < data_max * 0.1:
                        filtered_normalized.append(min_normalized)
                
                # 使用动态阈值过滤刻度值
                if min_normalized < 0.01:
                    threshold = 0.1
                elif min_normalized < 0.05:
                    threshold = 0.05
                else:
                    threshold = 0.01
                
                for tick in normalized_ticks:
                    if tick >= threshold and tick not in filtered_normalized:
                        filtered_normalized.append(tick)
                
                if len(filtered_normalized) < 3:
                    threshold = max(0.01, threshold * 0.5)
                    existing_bottom = [t for t in filtered_normalized if t < threshold]
                    filtered_normalized = existing_bottom if existing_bottom else []
                    for tick in normalized_ticks:
                        if tick >= threshold and tick not in filtered_normalized:
                            filtered_normalized.append(tick)
                
                # 确保包含最大值（归一化后为1.0）和最小值（归一化后为0.0）
                if len(filtered_normalized) == 0 or (len(filtered_normalized) > 0 and filtered_normalized[-1] < 0.99):
                    if data_max > 0:
                        filtered_normalized.append(1.0)
                # 对于归一化模式，确保包含0（最小值）
                if data_min == 0.0 and (len(filtered_normalized) == 0 or filtered_normalized[0] > 0.01):
                    filtered_normalized.insert(0, 0.0)
                
                # 去重并排序
                cbar_ticks = np.array(sorted(set(filtered_normalized)))
                
                return cbar_ticks
            
            # 方向维标准化 + 周期插值（辅助函数）
            def process_spectrum_data(E, dir_orig, freq):
                """处理单个站点的谱数据"""
                dir0 = dir_orig.copy()
                dir0 = np.mod(dir0, 360)
                idx = np.argsort(dir0)
                dir_sort = dir0[idx]
                E_sort = E[idx, :]
                
                # 周期闭合
                dir_ext = np.concatenate([dir_sort, [dir_sort[0] + 360]])
                n_freq = len(freq)
                
                # 高分辨率方向 - 0.5度间隔
                theta_deg_full = np.linspace(0, 360, 721)
                
                E_interp = np.zeros((len(theta_deg_full), n_freq))
                
                from scipy.interpolate import PchipInterpolator
                for i in range(n_freq):
                    E_ext = np.concatenate([E_sort[:, i], [E_sort[0, i]]])
                    interp_func = PchipInterpolator(dir_ext, E_ext, extrapolate=False)
                    E_interp[:, i] = interp_func(theta_deg_full)
                
                # 极坐标 → 笛卡尔坐标
                theta_deg_full_rad = np.deg2rad(90 - theta_deg_full)
                Theta, R = np.meshgrid(theta_deg_full_rad, freq)
                X = R * np.cos(Theta)
                Y = R * np.sin(Theta)
                
                return X, Y, E_interp
            
            # 计算归一化颜色条刻度值的函数（参考 plot_directional_spectrum.py）
            def calculate_cbar_ticks(data_min, data_max, generate_ticks_func):
                """
                计算颜色条的归一化刻度值（参考 plot_directional_spectrum.py）
                
                参数:
                    data_min: 数据最小值
                    data_max: 数据最大值
                    generate_ticks_func: 生成原始刻度值的函数
                
                返回:
                    cbar_ticks: 归一化后的刻度值数组（0到1之间）
                """
                # 生成原始数据的刻度值
                raw_ticks = generate_ticks_func(data_min, data_max)
                
                # 将刻度值归一化到 [0, 1] 范围（除以最大值）
                normalized_ticks = raw_ticks / data_max if data_max > 0 else raw_ticks
                
                # 计算最小值的归一化值
                min_normalized = data_min / data_max if data_max > 0 else data_min
                
                # 确保颜色条底部有足够的刻度显示
                filtered_normalized = []
                
                # 检查第一个归一化刻度值是否离底部太远
                first_normalized = normalized_ticks[0] if len(normalized_ticks) > 0 else 1.0
                
                # 如果第一个归一化刻度值大于0.1，说明底部有很大一段没有刻度
                if first_normalized > 0.1:
                    first_raw = raw_ticks[0] if len(raw_ticks) > 0 else data_max
                    bottom_range = first_raw - data_min
                    if bottom_range > 0:
                        ticks_above = len([t for t in normalized_ticks if t > first_normalized])
                        n_bottom_ticks = max(ticks_above + 2, 5)
                        
                        bottom_raw_ticks = generate_ticks_func(data_min, first_raw)
                        if len(bottom_raw_ticks) < n_bottom_ticks and bottom_range > 0:
                            bottom_raw_ticks = np.linspace(data_min, first_raw, n_bottom_ticks + 1)[1:-1]
                        
                        bottom_normalized = bottom_raw_ticks / data_max if data_max > 0 else bottom_raw_ticks
                        bottom_normalized_filtered = [t for t in bottom_normalized if t >= 0.005]
                        
                        if len(bottom_normalized_filtered) < n_bottom_ticks - 1:
                            bottom_normalized_filtered = [t for t in bottom_normalized if t > 0]
                        
                        if len(bottom_normalized_filtered) == 0 and len(bottom_normalized) > 0:
                            bottom_normalized_filtered = sorted(bottom_normalized)[:min(3, len(bottom_normalized))]
                        
                        filtered_normalized.extend(bottom_normalized_filtered)
                elif data_min > 0 and min_normalized > 0:
                    if min_normalized >= 0.01:
                        filtered_normalized.append(min_normalized)
                    elif data_max - data_min < data_max * 0.1:
                        filtered_normalized.append(min_normalized)
                
                # 使用动态阈值过滤刻度值
                if min_normalized < 0.01:
                    threshold = 0.1
                elif min_normalized < 0.05:
                    threshold = 0.05
                else:
                    threshold = 0.01
                
                for tick in normalized_ticks:
                    if tick >= threshold and tick not in filtered_normalized:
                        filtered_normalized.append(tick)
                
                if len(filtered_normalized) < 3:
                    threshold = max(0.01, threshold * 0.5)
                    existing_bottom = [t for t in filtered_normalized if t < threshold]
                    filtered_normalized = existing_bottom if existing_bottom else []
                    for tick in normalized_ticks:
                        if tick >= threshold and tick not in filtered_normalized:
                            filtered_normalized.append(tick)
                
                # 确保包含最大值（归一化后为1.0）
                if len(filtered_normalized) == 0 or (len(filtered_normalized) > 0 and filtered_normalized[-1] < 0.99):
                    if data_max > 0:
                        filtered_normalized.append(1.0)
                
                # 去重并排序
                cbar_ticks = np.array(sorted(set(filtered_normalized)))
                
                return cbar_ticks
            
            # 绘制单个二维谱图（辅助函数）
            def plot_single_spectrum(X, Y, E_interp, threshold, lon_val, lat_val, time_str, output_file, plot_mode="最大值归一化", E_original=None, freq_orig=None, dir_orig=None):
                """绘制单个二维谱图（归一化模式使用 wavespectra 框架）"""
                # 复用 _generate_all_spectrum_worker 中的相同实现
                # 这里直接调用相同的逻辑，避免代码重复
                # 检查是否为归一化模式（支持中英文翻译）
                normalized_text_zh = tr("plotting_plot_mode_normalized", "最大值归一化")
                normalized_text_en = "Max Normalized"  # 英文翻译
                is_normalized = (plot_mode == "最大值归一化" or 
                                plot_mode == normalized_text_zh or 
                                plot_mode == normalized_text_en or
                                plot_mode == "normalized")
                
                if is_normalized and HAS_WAVESPECTRA and E_original is not None and freq_orig is not None and dir_orig is not None:
                    # 使用 wavespectra 框架绘制归一化图（参考 plot_directional_spectrum.py）
                    import xarray as xr
                    
                    # 创建 xarray DataArray（wavespectra 需要）
                    efth_da = xr.DataArray(
                        E_original,  # (freq, dir)
                        dims=['freq', 'dir'],
                        coords={'freq': freq_orig, 'dir': dir_orig},
                        name='efth'
                    )
                    
                    # 转换为 SpecArray
                    spec_array = SpecArray(efth_da)
                    
                    # 计算数据范围，用于生成颜色条刻度
                    data_min = float(np.nanmin(E_original))
                    data_max = float(np.nanmax(E_original))
                    
                    # 使用函数计算归一化后的颜色条刻度值
                    cbar_ticks = calculate_cbar_ticks(data_min, data_max, generate_ticks)
                    
                    # 使用 jet 颜色映射（参考文件）
                    cmap = plt.get_cmap('jet')
                    
                    # 使用 wavespectra 的 plot 方法绘制（自动归一化）
                    rmax = np.max(freq_orig)
                    
                    # 计算频率刻度
                    freq_target = np.array([0.04, 0.1, 0.25, 0.59])
                    radii_ticks = freq_target[freq_target <= rmax].tolist()
                    if len(radii_ticks) == 0:
                        radii_ticks = [rmax * 0.2, rmax * 0.4, rmax * 0.6, rmax * 0.8]
                    
                    pobj = spec_array.plot(
                        figsize=(10, 10),
                        cmap=cmap,
                        rmax=rmax if rmax <= 3 else 3,
                        radii_ticks=radii_ticks if len(radii_ticks) > 0 else None
                    )
                    
                    # 获取当前图形和坐标轴
                    fig = plt.gcf()
                    ax = plt.gca()
                    
                    # 保持图像不变：0度在底部（南），顺时针方向（参考文件）
                    ax.set_theta_zero_location('S')
                    ax.set_theta_direction(-1)
                    
                    # 只修改标签文本，让0度标签显示在顶部位置（参考文件）
                    angles_deg = np.arange(0, 360, 30)
                    label_texts = []
                    for angle in angles_deg:
                        label_angle = (angle + 180) % 360
                        label_texts.append(f'{int(label_angle)}°')
                    
                    # 设置标签，保持网格位置不变（角度位置不变）
                    ax.set_thetagrids(angles_deg, labels=label_texts)
                    
                    # 设置标题，显示站点信息
                    ax.set_title(f'Lon: {lon_val:.2f}°, Lat: {lat_val:.2f}°            {time_str}', 
                                fontsize=10, pad=20)
                    
                    # 修改颜色条刻度（wavespectra 自动归一化，刻度值应该是归一化的）
                    # wavespectra 的 plot 方法会自动创建颜色条，尝试找到它
                    cb = None
                    # 方法1：从 pobj 对象获取（如果可用）
                    if hasattr(pobj, 'handles') and hasattr(pobj.handles, 'colorbar'):
                        cb = pobj.handles.colorbar
                    # 方法2：从 pobj 的 mappable 对象获取颜色条
                    if cb is None and hasattr(pobj, 'mappable'):
                        try:
                            cb = fig.colorbar(pobj.mappable, ax=ax)
                        except:
                            pass
                    # 方法3：从 figure 的所有子对象中查找（使用 hasattr 检查颜色条特征）
                    if cb is None:
                        for item in fig.axes:
                            # 颜色条通常有这些方法：set_ticks, set_ticklabels, set_label, update_normal
                            if (hasattr(item, 'set_ticks') and hasattr(item, 'set_ticklabels') and 
                                hasattr(item, 'set_label') and hasattr(item, 'update_normal')):
                                cb = item
                                break
                    # 方法4：从 figure 的所有子对象中查找（通过 get_children，检查颜色条特征）
                    if cb is None:
                        for item in fig.get_children():
                            if (hasattr(item, 'set_ticks') and hasattr(item, 'set_ticklabels') and 
                                hasattr(item, 'set_label') and hasattr(item, 'update_normal')):
                                cb = item
                                break
                    
                    # 如果找到了颜色条，修改其刻度
                    if cb is not None:
                        try:
                            # 设置归一化刻度
                            cb.set_ticks(cbar_ticks)
                            tick_labels = [format_tick_label(tick) for tick in cbar_ticks]
                            cb.set_ticklabels(tick_labels)
                            cb.set_label('Normalized Energy Density', fontsize=9)
                            if hasattr(cb, 'ax'):
                                cb.ax.tick_params(labelsize=9)
                        except Exception as e:
                            # 如果修改颜色条失败，记录但不中断执行（wavespectra 可能有自己的颜色条实现）
                            pass
                    
                    # 保存图片
                    plt.tight_layout()
                    plt.savefig(output_file, dpi=400, bbox_inches='tight', 
                                facecolor='white', edgecolor='none', pad_inches=0.1)
                    plt.close(fig)
                    
                else:
                    # 实际值模式，使用手动绘制方法（原有逻辑）
                    original_data_min = np.nanmin(E_interp)
                    original_data_max = np.nanmax(E_interp)
                    
                    data_min = original_data_min
                    data_max = original_data_max
                    
                    adjusted_threshold = float(threshold)
                    if adjusted_threshold > data_max:
                        adjusted_threshold = 0.0
                    
                    vmin_actual = min(adjusted_threshold, data_max)
                    vmax_actual = data_max
                    if vmin_actual >= vmax_actual:
                        vmin_actual = 0.0
                        if vmax_actual <= vmin_actual:
                            vmax_actual = max(1e-10, abs(data_max))
                    
                    fig = plt.figure(figsize=(8, 7.5), facecolor='white')
                    ax = fig.add_axes([0.08, 0.08, 0.68, 0.84])
                    
                    levels = 200
                    cmap = plt.get_cmap('jet')
                    cmap.set_under('white')
                    
                    try:
                        pcm = ax.contourf(X, Y, E_interp.T, levels=levels, cmap=cmap, 
                                        vmin=vmin_actual, vmax=vmax_actual, extend='neither')
                    except ValueError as e:
                        error_msg = str(e).lower()
                        if "minvalue" in error_msg or "maxvalue" in error_msg or "vmin" in error_msg or "vmax" in error_msg:
                            adjusted_threshold = 0.0
                            vmin_actual = 0.0
                            vmax_actual = max(data_max, 1e-10)
                            pcm = ax.contourf(X, Y, E_interp.T, levels=levels, cmap=cmap, 
                                            vmin=vmin_actual, vmax=vmax_actual, extend='neither')
                        else:
                            raise
                    
                    ax.set_aspect('equal')
                    ax.axis('off')
                    
                    cbar_min = vmin_actual
                    cbar_max = vmax_actual
                    cbar_ticks = generate_ticks(cbar_min, cbar_max)
                    if cbar_min not in cbar_ticks:
                        cbar_ticks = np.concatenate([[cbar_min], cbar_ticks])
                        cbar_ticks = np.sort(cbar_ticks)
                    if len(cbar_ticks) > 1:
                        cbar_ticks = cbar_ticks[:-1]
                    cbar_ticks = cbar_ticks[cbar_ticks >= cbar_min]
                    tick_labels = [format_tick_label(tick) for tick in cbar_ticks]
                    
                    cb = plt.colorbar(pcm, ax=ax, fraction=0.03, pad=0.1, ticks=cbar_ticks)
                    cb.set_ticklabels(tick_labels)
                    cb.set_label('Energy Density (m²/hz/deg)', fontsize=9)
                    cb.ax.tick_params(labelsize=9)
                    
                    title_str = f'Lon: {lon_val:.2f}°, Lat: {lat_val:.2f}°            {time_str}'
                    ax.set_title(title_str, fontsize=10, pad=10)
                    
                    dirs = np.arange(0, 360, 30)
                    rmax = np.max(freq)
                    
                    for ang in dirs:
                        theta_rad = np.deg2rad(90 - ang)
                        ax.plot([0, rmax * np.cos(theta_rad)], 
                               [0, rmax * np.sin(theta_rad)],
                               color='black', linewidth=0.5, alpha=0.5, linestyle='--')
                    
                    angle_labels = []
                    for ang in dirs:
                        x_pos = rmax * 1.12 * np.cos(np.deg2rad(90 - ang))
                        y_pos = rmax * 1.12 * np.sin(np.deg2rad(90 - ang))
                        label = f'{int(ang)}°'
                        angle_labels.append((x_pos, y_pos, label))
                    
                    freq_target = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
                    freq_max = np.max(freq)
                    freq_plot = freq_target[freq_target <= freq_max]
                    
                    th = np.linspace(0, 2 * np.pi, 360)
                    for i, rr in enumerate(freq_plot):
                        ax.plot(rr * np.cos(th), rr * np.sin(th), 'k:', linewidth=0.5, linestyle='--', alpha=0.5)
                        ax.text(0, rr * 1.03, f'{rr:.2f}',
                                ha='center', va='bottom', fontsize=6, color='black', alpha=0.5)
                    
                    ax.plot(freq_max * np.cos(th), freq_max * np.sin(th), 'k-', linewidth=1.0, alpha=0.8, zorder=1)
                    
                    for x_pos, y_pos, label in angle_labels:
                        circle_radius = 0.02 * freq_max
                        circle = plt.Circle((x_pos, y_pos), circle_radius, color='white', 
                                           edgecolor='none', zorder=2)
                        ax.add_patch(circle)
                        ax.text(x_pos, y_pos, label, fontsize=10, ha='center', va='center', zorder=3)
                    
                    plt.tight_layout()
                    
                    ax_pos = ax.get_position()
                    cbar_pos = cb.ax.get_position()
                    cb.ax.set_position([cbar_pos.x0, ax_pos.y0, cbar_pos.width, ax_pos.height])
                    
                    plt.savefig(output_file, dpi=400, bbox_inches='tight', 
                                facecolor='white', edgecolor='none', pad_inches=0.1)
                    plt.close(fig)
            
            # 获取站点信息
            lon_val = lon[station_index, 0] if lon.ndim > 1 else lon[station_index]
            lat_val = lat[station_index, 0] if lat.ndim > 1 else lat[station_index]
            
            # 遍历筛选后的时间步
            total_count = nSelectedTime
            current_count = 0
            success_count = 0
            
            for time_idx, itime in enumerate(selected_time_indices):
                current_count += 1
                
                try:
                    # 获取数据 (time, station, frequency, direction)
                    E_original = efth[itime, station_index, :, :]  # 获取 (frequency, direction)，用于 wavespectra
                    E = E_original.T  # 转置为 (direction, frequency)，用于手动绘制
                    
                    # 处理数据（用于实际值模式的手动绘制）
                    X, Y, E_interp = process_spectrum_data(E, dir_orig, freq)
                    
                    # 获取时间字符串
                    time_str = time_dt[itime].strftime("%Y-%m-%d %H:%M:%S")
                    
                    # 获取站点名称（如果提供了站点名称）
                    if station_name:
                        sanitized_name = _sanitize_filename(station_name)
                    else:
                        sanitized_name = f"station_{station_index+1:03d}"
                    
                    # 生成输出文件名（使用站点名称）
                    time_str_file = time_dt[itime].strftime("%Y%m%d_%H%M%S")
                    output_file = os.path.join(photo_folder, 
                                              f'spectrum_{sanitized_name}_time_{time_str_file}.png')
                    
                    # 绘制并保存（传入原始数据用于归一化模式）
                    plot_single_spectrum(X, Y, E_interp, energy_threshold, 
                                       lon_val, lat_val, time_str, output_file, plot_mode,
                                       E_original=E_original, freq_orig=freq, dir_orig=dir_orig)
                    
                    success_count += 1
                    
                    # 每生成10张图片或完成时更新进度
                    if current_count % 10 == 0 or current_count == total_count:
                        log(f"📊 进度：{current_count}/{total_count} ({success_count} 成功)")
                
                except Exception as e:
                    log(tr("plotting_generate_timestep_failed", "❌ 生成时间步 {timestep} 失败：{error}").format(timestep=itime+1, error=e))
                    continue
            
            result_queue.put(photo_folder)
            
        finally:
            # 恢复后端
            matplotlib.use(original_backend)
        
        log_queue.put("__DONE__")
        
    except Exception as e:
        import traceback
        log_queue.put(tr("plotting_generate_selected_spectrum_failed", "❌ 生成选中站点二维谱图失败：{error}").format(error=e))
        log_queue.put(traceback.format_exc())
        result_queue.put(None)
        log_queue.put("__DONE__")
