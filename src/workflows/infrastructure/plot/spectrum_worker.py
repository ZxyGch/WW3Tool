"""二维方向谱图生成 Worker — 从 WW3 谱输出 NetCDF 绘制极坐标谱图。

在独立子进程中读取 ``ww3*spec*nc`` 文件，支持首帧预览、全站点批量生成及
按站点名/时间步筛选生成；可选 wavespectra 库增强谱分析。
"""

import os
import re
import glob
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from matplotlib import cm
from netCDF4 import num2date
import netCDF4 as nc
from datetime import datetime
from ...support.translations import tr
try:
    import wavespectra
    from wavespectra import SpecArray
    HAS_WAVESPECTRA = True
except ImportError:
    HAS_WAVESPECTRA = False

USE_WAVESPECTRA_NORMALIZED_PLOT = True

from .workers_utils import _pick_station_lon_lat, _decode_station_names


def _find_spectrum_files(selected_folder, spec_file=None):
    """Return the selected spectrum file, or all WW3 spectrum files in stable order."""
    if spec_file and os.path.exists(spec_file):
        return [spec_file]
    return sorted(glob.glob(os.path.join(selected_folder, "ww3*spec*nc")))


def _as_python_datetime(value):
    """Convert netCDF4/cftime datetime-like values to ``datetime`` for formatting."""
    if isinstance(value, datetime):
        return value
    return datetime(
        value.year, value.month, value.day,
        getattr(value, "hour", 0),
        getattr(value, "minute", 0),
        getattr(value, "second", 0),
        getattr(value, "microsecond", 0),
    )


def _decode_time_values(time_values, time_var):
    """Decode a WW3 time variable using its NetCDF units/calendar metadata."""
    units = getattr(time_var, "units", None)
    calendar = getattr(time_var, "calendar", "standard")
    if not units:
        raise ValueError("二维谱 time 变量缺少 units 属性，无法解析时间")

    decoded = num2date(
        time_values,
        units=units,
        calendar=calendar,
        only_use_cftime_datetimes=False,
        only_use_python_datetimes=False,
    )
    return [_as_python_datetime(item) for item in decoded]


def _ww3_direction_to_radians(direction_deg):
    """WW3 spectrum direction is 'to direction', origin East, trigonometric order."""
    return np.deg2rad(direction_deg)


def _direction_label_position(angle_deg, radius):
    theta_rad = _ww3_direction_to_radians(angle_deg)
    return radius * np.cos(theta_rad), radius * np.sin(theta_rad)


def _is_normalized_plot_mode(plot_mode):
    mode = str(plot_mode or "").strip()
    mode_lower = mode.lower()
    return (
        mode == "最大值归一化"
        or mode == tr("plotting_plot_mode_normalized", "最大值归一化")
        or mode_lower in {"normalized", "max normalized", "maximum normalized"}
    )


def _prepare_spectrum_plot_values(E_interp, threshold, plot_mode):
    """Return data, threshold and colorbar label for actual/normalized spectrum plots."""
    data = np.array(E_interp, dtype=float, copy=True)
    try:
        threshold_value = float(threshold if threshold is not None else 0.0)
    except (TypeError, ValueError):
        threshold_value = 0.0
    threshold_value = max(0.0, threshold_value)

    if not _is_normalized_plot_mode(plot_mode):
        return data, threshold_value, "Energy Density (m²/Hz/deg)"

    finite = data[np.isfinite(data)]
    max_value = float(np.nanmax(finite)) if finite.size else 0.0
    if max_value > 0:
        data = data / max_value
    else:
        data = np.nan_to_num(data, nan=0.0)
    return data, min(threshold_value, 1.0), "Normalized Energy Density"


def _generate_first_spectrum_worker(selected_folder, log_queue, result_queue, energy_threshold=0.01, spec_file=None, plot_mode="最大值归一化"):
    """在子进程中生成第一张二维方向谱图（快速预览，参考 plot_matlab.py 逻辑）。"""
    try:
        def log(msg):
            """发送日志到队列"""
            try:
                log_queue.put(msg)
            except:
                pass

        log(tr("plotting_start_first_spectrum", "🔄 开始生成第一张二维谱图（在子进程中执行）..."))

        spec_files = _find_spectrum_files(selected_folder, spec_file)

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
                # WW3 efth units: m²·s·rad⁻¹ == m²/Hz/rad -> convert to m²/Hz/deg for plotting
                efth = ds.variables['efth'][:] * (np.pi / 180.0)
                time_var = ds.variables['time']
                time = time_var[:].data
                time_dt = _decode_time_values(time, time_var)

                # 读取站点信息
                lon = ds.variables['longitude'][:].data
                lat = ds.variables['latitude'][:].data
                nStation = len(ds.dimensions['station'])

            # 精简日志：不输出读取统计

            # 选择第一个时间步和第一个站点
            itime = 0
            istation = 0

            # 获取数据 (time, station, frequency, direction)
            # efth converted to m²/Hz/deg for plotting
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
            theta_deg_full_rad = _ww3_direction_to_radians(theta_deg_full)
            Theta, R = np.meshgrid(theta_deg_full_rad, freq)
            X = R * np.cos(Theta)
            Y = R * np.sin(Theta)

            # 绘制二维谱
            fig = plt.figure(figsize=(8, 7.5), facecolor='white')
            ax = fig.add_axes([0.08, 0.08, 0.68, 0.84])

            # 计算数据范围；归一化模式下阈值表示最大能量的比例
            E_plot, threshold, cbar_label = _prepare_spectrum_plot_values(
                E_interp,
                energy_threshold,
                plot_mode,
            )
            data_min = np.nanmin(E_plot)
            data_max = np.nanmax(E_plot)

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
                if abs(value) < 1e-12:
                    return '0'
                if abs(value) < 0.01:
                    return f'{value:.2e}'
                return f'{value:.2f}'

            # 绘制等高线填充图
            levels = 200
            cmap = plt.get_cmap('jet')
            cmap.set_under('white')

            # 若整体低于阈值，显示完整图；否则低于阈值显示为白色
            show_full = data_max <= threshold
            if show_full:
                vmin_actual = data_min
                vmax_actual = data_max
            else:
                vmin_actual = min(threshold, data_max)
                vmax_actual = data_max
                if vmin_actual >= vmax_actual:
                    vmin_actual = 0.0
                    if vmax_actual <= vmin_actual:
                        vmax_actual = max(1e-10, abs(data_max))

            try:
                # 使用 extend='min' 让低于阈值区域显示为白色
                pcm = ax.contourf(X, Y, E_plot.T, levels=levels, cmap=cmap,
                                vmin=vmin_actual, vmax=vmax_actual, extend='min')
            except ValueError as e:
                # 捕获 minvalue must be less than or equal to maxvalue 错误
                error_msg = str(e).lower()
                if "minvalue" in error_msg or "maxvalue" in error_msg or "vmin" in error_msg or "vmax" in error_msg:
                    log(tr("plotting_threshold_range_error", "⚠️ 检测到阈值范围错误：{error}，自动将最低能量密度调整为 0").format(error=e))
                    threshold = 0.0
                    vmin_actual = 0.0
                    vmax_actual = max(data_max, 1e-10)  # 确保最大值大于0
                    pcm = ax.contourf(X, Y, E_plot.T, levels=levels, cmap=cmap,
                                    vmin=vmin_actual, vmax=vmax_actual, extend='min')
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

            norm = matplotlib.colors.Normalize(vmin=vmin_actual, vmax=vmax_actual)
            sm = matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap)
            sm.set_array([])
            cb = plt.colorbar(sm, ax=ax, fraction=0.03, pad=0.1, ticks=cbar_ticks)
            cb.set_ticklabels(tick_labels)
            cb.set_label(cbar_label, fontsize=9)
            cb.ax.tick_params(labelsize=9)

            # 标题
            lon_val, lat_val = _pick_station_lon_lat(lon, lat, istation, nStation)
            title_str = f'Lon: {lon_val:.2f}°, Lat: {lat_val:.2f}°            {time_dt[itime].strftime("%Y-%m-%d %H:%M:%S")}'
            ax.set_title(title_str, fontsize=10, pad=10)

            # 极坐标方向标注
            dirs = np.arange(0, 360, 30)
            rmax = np.max(freq)

            # 绘制径向轴
            for ang in dirs:
                theta_rad = _ww3_direction_to_radians(ang)
                ax.plot([0, rmax * np.cos(theta_rad)],
                       [0, rmax * np.sin(theta_rad)],
                       color='black', linewidth=0.5, alpha=0.5, linestyle='--')

            # 角度标签
            angle_labels = []
            for ang in dirs:
                x_pos, y_pos = _direction_label_position(ang, rmax * 1.12)
                label = f'{int(ang)}°'
                angle_labels.append((x_pos, y_pos, label))

            # 频率同心圆
            freq_target = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
            freq_max = np.max(freq)
            freq_plot = freq_target[freq_target <= freq_max]

            th = np.linspace(0, 2 * np.pi, 360)
            for i, rr in enumerate(freq_plot):
                ax.plot(rr * np.cos(th), rr * np.sin(th), 'k', linewidth=0.5, linestyle=':', alpha=0.5)
                ax.text(0, rr * 1.03, f'{rr:.2f}',
                        ha='center', va='bottom', fontsize=6, color='black', alpha=0.5)

            # 外圈
            ax.plot(freq_max * np.cos(th), freq_max * np.sin(th), 'k-', linewidth=1.0, alpha=0.8, zorder=1)

            # 在文字位置绘制白色圆形背景和文字
            for x_pos, y_pos, label in angle_labels:
                circle_radius = 0.02 * freq_max
                circle = plt.Circle((x_pos, y_pos), circle_radius, facecolor='white',
                                   edgecolor='none', zorder=2)
                ax.add_patch(circle)
                ax.text(x_pos, y_pos, label, fontsize=10, ha='center', va='center', zorder=3)

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
    """在子进程中为所有站点、按时间步长筛选生成二维方向谱图序列。"""
    station_name_var = None
    try:
        def log(msg):
            """发送日志到队列"""
            try:
                log_queue.put(msg)
            except:
                pass

        # 精简日志：不输出开始提示

        spec_files = _find_spectrum_files(selected_folder, spec_file)

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
                # WW3 efth units: m²·s·rad⁻¹ == m²/Hz/rad -> convert to m²/Hz/deg for plotting
                efth = ds.variables['efth'][:] * (np.pi / 180.0)
                time_var = ds.variables['time']
                time = time_var[:].data
                time_dt = _decode_time_values(time, time_var)

                # 读取站点信息
                lon = ds.variables['longitude'][:].data
                lat = ds.variables['latitude'][:].data
                nStation = len(ds.dimensions['station'])
                nTime = len(time)
                station_name_var = ds.variables['station_name'][:] if 'station_name' in ds.variables else None

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

            from .photo_output import SUBDIR_DIRECTIONAL_SPECTRUM, prepare_photo_subdir

            photo_folder = prepare_photo_subdir(selected_folder, SUBDIR_DIRECTIONAL_SPECTRUM)

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
                if abs(value) < 1e-12:
                    return '0'
                if abs(value) < 0.01:
                    return f'{value:.2e}'
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
                theta_deg_full_rad = _ww3_direction_to_radians(theta_deg_full)
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

                if (
                    is_normalized
                    and USE_WAVESPECTRA_NORMALIZED_PLOT
                    and HAS_WAVESPECTRA
                    and E_original is not None
                    and freq_orig is not None
                    and dir_orig is not None
                ):
                    # 使用 wavespectra 框架绘制归一化图（参考 plot_directional_spectrum.py）
                    import xarray as xr

                    # 创建 xarray DataArray（wavespectra 需要）
                    # E_original 应该是 (frequency, direction) 形状
                    # wavespectra 期望 (freq, dir) 坐标
                    E_wavespectra = np.array(E_original, dtype=float, copy=True)
                    finite = E_wavespectra[np.isfinite(E_wavespectra)]
                    max_value = float(np.nanmax(finite)) if finite.size else 0.0
                    if max_value > 0:
                        E_wavespectra = E_wavespectra / max_value
                    else:
                        E_wavespectra = np.nan_to_num(E_wavespectra, nan=0.0)

                    efth_da = xr.DataArray(
                        E_wavespectra,  # (freq, dir), max-normalized before wavespectra plotting
                        dims=['freq', 'dir'],
                        coords={'freq': freq_orig, 'dir': dir_orig},
                        name='efth'
                    )

                    # 转换为 SpecArray
                    spec_array = SpecArray(efth_da)

                    # 计算数据范围，用于生成颜色条刻度
                    data_min = float(np.nanmin(E_wavespectra))
                    data_max = float(np.nanmax(E_wavespectra))

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

                    ax.set_theta_zero_location('E')
                    ax.set_theta_direction(1)

                    angles_deg = np.arange(0, 360, 30)
                    label_texts = [f'{int(angle)}°' for angle in angles_deg]
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
                    try:
                        plt.tight_layout()
                    except Exception:
                        pass
                    plt.savefig(output_file, dpi=400, bbox_inches='tight',
                                facecolor='white', edgecolor='none', pad_inches=0.1)
                    plt.close(fig)

                else:
                    # 手动绘制方法；归一化模式直接对插值后的二维谱除以最大值。
                    E_plot, adjusted_threshold, cbar_label = _prepare_spectrum_plot_values(
                        E_interp,
                        threshold,
                        plot_mode,
                    )
                    data_min = np.nanmin(E_plot)
                    data_max = np.nanmax(E_plot)

                    # 检查阈值：若整体低于阈值则显示完整图
                    show_full = data_max <= adjusted_threshold
                    if show_full:
                        vmin_actual = data_min
                        vmax_actual = data_max
                        extend_mode = 'neither'
                    else:
                        vmin_actual = min(adjusted_threshold, data_max)
                        vmax_actual = data_max
                        extend_mode = 'min'
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
                        pcm = ax.contourf(X, Y, E_plot.T, levels=levels, cmap=cmap,
                                        vmin=vmin_actual, vmax=vmax_actual, extend=extend_mode)
                    except ValueError as e:
                        error_msg = str(e).lower()
                        if "minvalue" in error_msg or "maxvalue" in error_msg or "vmin" in error_msg or "vmax" in error_msg:
                            adjusted_threshold = 0.0
                            vmin_actual = 0.0
                            vmax_actual = max(data_max, 1e-10)
                            pcm = ax.contourf(X, Y, E_plot.T, levels=levels, cmap=cmap,
                                            vmin=vmin_actual, vmax=vmax_actual, extend=extend_mode)
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

                    norm = matplotlib.colors.Normalize(vmin=vmin_actual, vmax=vmax_actual)
                    sm = matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap)
                    sm.set_array([])
                    cb = plt.colorbar(sm, ax=ax, fraction=0.03, pad=0.1, ticks=cbar_ticks)
                    cb.set_ticklabels(tick_labels)
                    cb.set_label(cbar_label, fontsize=9)
                    cb.ax.tick_params(labelsize=9)

                    # 标题
                    title_str = f'Lon: {lon_val:.2f}°, Lat: {lat_val:.2f}°            {time_str}'
                    ax.set_title(title_str, fontsize=10, pad=10)

                    # 极坐标方向标注
                    dirs = np.arange(0, 360, 30)
                    rmax = np.max(freq)

                    # 绘制径向轴
                    for ang in dirs:
                        theta_rad = _ww3_direction_to_radians(ang)
                        ax.plot([0, rmax * np.cos(theta_rad)],
                               [0, rmax * np.sin(theta_rad)],
                               color='black', linewidth=0.5, alpha=0.5, linestyle='--')

                    # 角度标签
                    angle_labels = []
                    for ang in dirs:
                        x_pos, y_pos = _direction_label_position(ang, rmax * 1.12)
                        label = f'{int(ang)}°'
                        angle_labels.append((x_pos, y_pos, label))

                    # 频率同心圆
                    freq_target = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
                    freq_max = np.max(freq)
                    freq_plot = freq_target[freq_target <= freq_max]

                    th = np.linspace(0, 2 * np.pi, 360)
                    for i, rr in enumerate(freq_plot):
                        ax.plot(rr * np.cos(th), rr * np.sin(th), 'k', linewidth=0.5, linestyle=':', alpha=0.5)
                        ax.text(0, rr * 1.03, f'{rr:.2f}',
                                ha='center', va='bottom', fontsize=6, color='black', alpha=0.5)

                    # 外圈
                    ax.plot(freq_max * np.cos(th), freq_max * np.sin(th), 'k-', linewidth=1.0, alpha=0.8, zorder=1)

                    # 在文字位置绘制白色圆形背景和文字
                    for x_pos, y_pos, label in angle_labels:
                        circle_radius = 0.02 * freq_max
                        circle = plt.Circle((x_pos, y_pos), circle_radius, facecolor='white',
                                           edgecolor='none', zorder=2)
                        ax.add_patch(circle)
                        ax.text(x_pos, y_pos, label, fontsize=10, ha='center', va='center', zorder=3)

                    # 调整颜色条高度
                    ax_pos = ax.get_position()
                    cbar_pos = cb.ax.get_position()
                    cb.ax.set_position([cbar_pos.x0, ax_pos.y0, cbar_pos.width, ax_pos.height])

                    # 保存图片
                    plt.savefig(output_file, dpi=400, bbox_inches='tight',
                                facecolor='white', edgecolor='none', pad_inches=0.1)
                    plt.close(fig)

            # 优先使用文件中的站点名称，避免 UI 排序/编辑导致错位
            file_station_names = _decode_station_names(station_name_var, nStation)
            if file_station_names and any(file_station_names):
                station_name_list = file_station_names
            elif station_names and len(station_names) >= nStation:
                station_name_list = station_names
            else:
                station_name_list = [f"station_{i+1:03d}" for i in range(nStation)]

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
                        lon_val, lat_val = _pick_station_lon_lat(lon, lat, istation, nStation)
                        time_str = time_dt[itime].strftime("%Y-%m-%d %H:%M:%S")

                        # 获取站点名称（如果提供了站点名称列表）
                        station_name = _sanitize_filename(station_name_list[istation])

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
    """在子进程中为单个指定站点、按时间步长筛选生成二维方向谱图序列。"""
    station_name_var = None
    try:
        def log(msg):
            """发送日志到队列"""
            try:
                log_queue.put(msg)
            except:
                pass

        log(tr("plotting_start_selected_spectrum", "🔄 开始生成选中站点的二维谱图（站点索引：{index}，时间步长：{hours}小时，在子进程中执行）...").format(index=station_index, hours=time_step_hours))

        spec_files = _find_spectrum_files(selected_folder, spec_file)

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
                # WW3 efth units: m²·s·rad⁻¹ == m²/Hz/rad -> convert to m²/Hz/deg for plotting
                efth = ds.variables['efth'][:] * (np.pi / 180.0)
                time_var = ds.variables['time']
                time = time_var[:].data
                time_dt = _decode_time_values(time, time_var)

                # 读取站点信息
                lon = ds.variables['longitude'][:].data
                lat = ds.variables['latitude'][:].data
                nStation = len(ds.dimensions['station'])
                nTime = len(time)
                station_name_var = ds.variables['station_name'][:] if 'station_name' in ds.variables else None

            # 检查站点索引是否有效
            if station_index < 0 or station_index >= nStation:
                log(tr("plotting_invalid_station_index", "❌ 站点索引 {index} 无效，文件中共有 {total} 个站点").format(index=station_index, total=nStation))
                log_queue.put("__DONE__")
                result_queue.put(None)
                return

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

            from .photo_output import SUBDIR_DIRECTIONAL_SPECTRUM, prepare_photo_subdir

            photo_folder = prepare_photo_subdir(selected_folder, SUBDIR_DIRECTIONAL_SPECTRUM)

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
                if abs(value) < 1e-12:
                    return '0'
                if abs(value) < 0.01:
                    return f'{value:.2e}'
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
                theta_deg_full_rad = _ww3_direction_to_radians(theta_deg_full)
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

                if (
                    is_normalized
                    and USE_WAVESPECTRA_NORMALIZED_PLOT
                    and HAS_WAVESPECTRA
                    and E_original is not None
                    and freq_orig is not None
                    and dir_orig is not None
                ):
                    # 使用 wavespectra 框架绘制归一化图（参考 plot_directional_spectrum.py）
                    import xarray as xr

                    # 创建 xarray DataArray（wavespectra 需要）
                    E_wavespectra = np.array(E_original, dtype=float, copy=True)
                    finite = E_wavespectra[np.isfinite(E_wavespectra)]
                    max_value = float(np.nanmax(finite)) if finite.size else 0.0
                    if max_value > 0:
                        E_wavespectra = E_wavespectra / max_value
                    else:
                        E_wavespectra = np.nan_to_num(E_wavespectra, nan=0.0)

                    efth_da = xr.DataArray(
                        E_wavespectra,  # (freq, dir), max-normalized before wavespectra plotting
                        dims=['freq', 'dir'],
                        coords={'freq': freq_orig, 'dir': dir_orig},
                        name='efth'
                    )

                    # 转换为 SpecArray
                    spec_array = SpecArray(efth_da)

                    # 计算数据范围，用于生成颜色条刻度
                    data_min = float(np.nanmin(E_wavespectra))
                    data_max = float(np.nanmax(E_wavespectra))

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

                    ax.set_theta_zero_location('E')
                    ax.set_theta_direction(1)

                    angles_deg = np.arange(0, 360, 30)
                    label_texts = [f'{int(angle)}°' for angle in angles_deg]
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
                    try:
                        plt.tight_layout()
                    except Exception:
                        pass
                    plt.savefig(output_file, dpi=400, bbox_inches='tight',
                                facecolor='white', edgecolor='none', pad_inches=0.1)
                    plt.close(fig)

                else:
                    # 手动绘制方法；归一化模式直接对插值后的二维谱除以最大值。
                    E_plot, adjusted_threshold, cbar_label = _prepare_spectrum_plot_values(
                        E_interp,
                        threshold,
                        plot_mode,
                    )
                    data_min = np.nanmin(E_plot)
                    data_max = np.nanmax(E_plot)

                    show_full = data_max <= adjusted_threshold
                    if show_full:
                        vmin_actual = data_min
                        vmax_actual = data_max
                    else:
                        vmin_actual = min(adjusted_threshold, data_max)
                        vmax_actual = data_max
                        if vmin_actual >= vmax_actual:
                            vmin_actual = 0.0
                            if vmax_actual <= vmin_actual:
                                vmax_actual = max(1e-10, abs(data_max))

                    fig = plt.figure(figsize=(8, 7.5), facecolor='white')
                    ax = fig.add_axes([0.08, 0.08, 0.68, 0.84])

                    # 必须 extend='min' 才能让 set_under('white') 生效
                    levels = 200
                    cmap = plt.get_cmap('jet')
                    cmap.set_under('white')

                    try:
                        pcm = ax.contourf(X, Y, E_plot.T, levels=levels, cmap=cmap,
                                        vmin=vmin_actual, vmax=vmax_actual, extend='min')
                    except ValueError as e:
                        error_msg = str(e).lower()
                        if "minvalue" in error_msg or "maxvalue" in error_msg or "vmin" in error_msg or "vmax" in error_msg:
                            adjusted_threshold = 0.0
                            vmin_actual = 0.0
                            vmax_actual = max(data_max, 1e-10)
                            pcm = ax.contourf(X, Y, E_plot.T, levels=levels, cmap=cmap,
                                            vmin=vmin_actual, vmax=vmax_actual, extend='min')
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

                    norm = matplotlib.colors.Normalize(vmin=vmin_actual, vmax=vmax_actual)
                    sm = matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap)
                    sm.set_array([])
                    cb = plt.colorbar(sm, ax=ax, fraction=0.03, pad=0.1, ticks=cbar_ticks)
                    cb.set_ticklabels(tick_labels)
                    cb.set_label(cbar_label, fontsize=9)
                    cb.ax.tick_params(labelsize=9)

                    title_str = f'Lon: {lon_val:.2f}°, Lat: {lat_val:.2f}°            {time_str}'
                    ax.set_title(title_str, fontsize=10, pad=10)

                    dirs = np.arange(0, 360, 30)
                    rmax = np.max(freq)

                    for ang in dirs:
                        theta_rad = _ww3_direction_to_radians(ang)
                        ax.plot([0, rmax * np.cos(theta_rad)],
                               [0, rmax * np.sin(theta_rad)],
                               color='black', linewidth=0.5, alpha=0.5, linestyle='--')

                    angle_labels = []
                    for ang in dirs:
                        x_pos, y_pos = _direction_label_position(ang, rmax * 1.12)
                        label = f'{int(ang)}°'
                        angle_labels.append((x_pos, y_pos, label))

                    freq_target = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
                    freq_max = np.max(freq)
                    freq_plot = freq_target[freq_target <= freq_max]

                    th = np.linspace(0, 2 * np.pi, 360)
                    for i, rr in enumerate(freq_plot):
                        ax.plot(rr * np.cos(th), rr * np.sin(th), 'k', linewidth=0.5, linestyle=':', alpha=0.5)
                        ax.text(0, rr * 1.03, f'{rr:.2f}',
                                ha='center', va='bottom', fontsize=6, color='black', alpha=0.5)

                    ax.plot(freq_max * np.cos(th), freq_max * np.sin(th), 'k-', linewidth=1.0, alpha=0.8, zorder=1)

                    for x_pos, y_pos, label in angle_labels:
                        circle_radius = 0.02 * freq_max
                        circle = plt.Circle((x_pos, y_pos), circle_radius, facecolor='white',
                                           edgecolor='none', zorder=2)
                        ax.add_patch(circle)
                        ax.text(x_pos, y_pos, label, fontsize=10, ha='center', va='center', zorder=3)

                    ax_pos = ax.get_position()
                    cbar_pos = cb.ax.get_position()
                    cb.ax.set_position([cbar_pos.x0, ax_pos.y0, cbar_pos.width, ax_pos.height])

                    plt.savefig(output_file, dpi=400, bbox_inches='tight',
                                facecolor='white', edgecolor='none', pad_inches=0.1)
                    plt.close(fig)

            # 获取站点信息
            lon_val, lat_val = _pick_station_lon_lat(lon, lat, station_index, nStation)

            file_station_names = _decode_station_names(station_name_var, nStation)
            if file_station_names and any(file_station_names):
                station_name = file_station_names[station_index]
            elif station_name:
                station_name = station_name
            else:
                station_name = f"station_{station_index+1:03d}"

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
                    sanitized_name = _sanitize_filename(station_name)

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
                        log(tr("plotting_progress_all_spectrum", "📊 进度：{current}/{total} ({success} 成功)").format(
                            current=current_count, total=total_count, success=success_count,
                        ))

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
