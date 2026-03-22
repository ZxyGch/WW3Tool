"""波高填色图与等值线图 Worker"""

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
from .workers_utils import (
    ww3_resolve_lon_lat_names,
    ww3_prepare_lon_lat_1d,
    ww3_is_pointwise_grid,
    ww3_try_pointwise_timeseries,
    ww3_try_mesh_triangles,
    remove_tricontourf_artist,
)


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
        available_vars = list(ds.variables.keys())
        lon_name, lat_name = ww3_resolve_lon_lat_names(ds)
        if not lon_name or not lat_name:
            log(
                tr(
                    "plotting_missing_lon_lat_variables",
                    "❌ 无法识别经度/纬度变量（需 longitude/lon、latitude/lat 等）。可用变量: {vars}",
                ).format(vars=", ".join(available_vars))
            )
            ds.close()
            log_queue.put("__DONE__")
            result_queue.put([])
            return

        WW3_time_var = ds.variables["time"]

        # 时间
        try:
            WW3_datetime = num2date(WW3_time_var[:], WW3_time_var.units)
            WW3_datetime = np.array([datetime.utcfromtimestamp(dt.timestamp()) for dt in WW3_datetime])
        except Exception:
            ref = datetime(1990, 1, 1)
            WW3_datetime = np.array([ref + timedelta(days=float(t)) for t in WW3_time_var[:]])
        nt = len(WW3_datetime)

        WW3_lon = np.array(ds.variables[lon_name][:])
        WW3_lat = np.array(ds.variables[lat_name][:])
        try:
            WW3_lon, WW3_lat = ww3_prepare_lon_lat_1d(WW3_lon, WW3_lat, nt)
        except Exception as e:
            log(
                tr(
                    "plotting_lon_lat_prepare_failed",
                    "❌ 经纬度坐标形状无法解析: {error}",
                ).format(error=e)
            )
            ds.close()
            log_queue.put("__DONE__")
            result_queue.put([])
            return

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
            raw_var = ds.variables['hs']
            raw = np.array(raw_var[:])
            # 处理 NetCDF 缺测值（_FillValue 如 9.96921e+36 在 float32 下仍为 finite）
            _fv = getattr(raw_var, '_FillValue', None)
            if _fv is not None:
                fv = float(np.asarray(_fv).flat[0])
                raw = np.where(np.abs(raw.astype(float) - fv) < 1e30, np.nan, raw)
            raw = np.where(raw > 1e30, np.nan, raw)  # CF 常见大值缺测
            raw = np.where(raw > 1e10, np.nan, raw)
            varlabel = 'Total Hs (m)'; prefix='hs'
        elif v == 2:
            if 'phs0' not in ds.variables:
                log(tr("plotting_missing_phs0_variable", "❌ 文件中没有 'phs0' 变量。可用变量: {vars}").format(vars=', '.join(available_vars)))
                ds.close()
                log_queue.put("__DONE__")
                result_queue.put([])
                return
            raw_var = ds.variables['phs0']
            raw = np.array(raw_var[:])
            _fv = getattr(raw_var, '_FillValue', None)
            if _fv is not None:
                fv = float(np.asarray(_fv).flat[0])
                raw = np.where(np.abs(raw.astype(float) - fv) < 1e30, np.nan, raw)
            raw = np.where(raw > 1e30, np.nan, raw)
            raw = np.where(raw > 1e10, np.nan, raw)
            varlabel = 'Wind Sea Hs (m)'; prefix='phs0'
        else:
            if 'phs1' not in ds.variables:
                log(tr("plotting_missing_phs1_variable", "❌ 文件中没有 'phs1' 变量。可用变量: {vars}").format(vars=', '.join(available_vars)))
                ds.close()
                log_queue.put("__DONE__")
                result_queue.put([])
                return
            raw_var = ds.variables['phs1']
            raw = np.array(raw_var[:])
            _fv = getattr(raw_var, '_FillValue', None)
            if _fv is not None:
                fv = float(np.asarray(_fv).flat[0])
                raw = np.where(np.abs(raw.astype(float) - fv) < 1e30, np.nan, raw)
            raw = np.where(raw > 1e30, np.nan, raw)
            raw = np.where(raw > 1e10, np.nan, raw)
            varlabel = 'Swell Hs (m)'; prefix='phs1'

        # 非结构网格 / SMC：hs 为 (time, node) 或 (node, time)；关闭文件前检测并读取三角连通表
        is_pointwise, Hs_pw = ww3_is_pointwise_grid(WW3_lon, WW3_lat, raw, nt)
        n_points_full = int(np.asarray(WW3_lon).ravel().size)
        mesh_tri_global = ww3_try_mesh_triangles(ds, n_points_full) if is_pointwise else None

        u_raw_wind = np.array(ds.variables["u10"][:]) if "u10" in ds.variables else None
        v_raw_wind = np.array(ds.variables["v10"][:]) if "v10" in ds.variables else None

        ds.close()

        u10_data = None
        v10_data = None
        u10_pw = None
        v10_pw = None
        if not is_pointwise:
            if u_raw_wind is not None:
                u_raw = u_raw_wind
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
            if v_raw_wind is not None:
                v_raw = v_raw_wind
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
        else:
            if u_raw_wind is not None:
                u10_pw = ww3_try_pointwise_timeseries(u_raw_wind, nt, n_points_full)
                if u10_pw is not None:
                    u10_pw = u10_pw.astype(float)
                    u10_pw[u10_pw > 1e10] = np.nan
            if v_raw_wind is not None:
                v10_pw = ww3_try_pointwise_timeseries(v_raw_wind, nt, n_points_full)
                if v10_pw is not None:
                    v10_pw = v10_pw.astype(float)
                    v10_pw[v10_pw > 1e10] = np.nan

        # 若全部为缺测值，提前退出
        if np.isfinite(raw).sum() == 0:
            log(tr("plotting_all_missing", "❌ 文件中所有格点均为缺测值，请检查 WW3 输出或模拟设置"))
            log_queue.put("__DONE__")
            result_queue.put([])
            return

        # ------------------------
        # 点序列网格（非结构 UNST / SMC 等）：已在上文 ww3_is_pointwise_grid 判定
        # ------------------------
        WW3_lon = np.asarray(WW3_lon).squeeze()
        WW3_lat = np.asarray(WW3_lat).squeeze()
        npoints = len(WW3_lon) if WW3_lon.ndim == 1 else WW3_lon.size
        mesh_tri_use = mesh_tri_global
        if is_pointwise:
            log(
                tr(
                    "plotting_unst_pointwise_detected",
                    "📐 检测到非结构/点序列网格 ({n} 个节点)，维度 (time×node) 或 (node×time) 已对齐",
                ).format(n=npoints)
            )
            if generate_video:
                log(tr("plotting_smc_video_skip", "⚠️ SMC 网格暂不支持视频生成，将仅输出图片"))
                generate_video = False

        # ------------------------
        # 数据维度整理
        # ------------------------
        if is_pointwise:
            Hs = np.asarray(Hs_pw, dtype=float)
            Hs[Hs > 1e10] = np.nan
            SMC_SUBSAMPLE = 50000
            if npoints > SMC_SUBSAMPLE:
                rng = np.random.default_rng(42)
                idx = rng.choice(npoints, SMC_SUBSAMPLE, replace=False)
                idx = np.sort(idx)
                WW3_lon = WW3_lon[idx]
                WW3_lat = WW3_lat[idx]
                Hs = Hs[:, idx]
                mesh_tri_use = None
                if u10_pw is not None:
                    u10_pw = u10_pw[:, idx]
                if v10_pw is not None:
                    v10_pw = v10_pw[:, idx]
                npoints = SMC_SUBSAMPLE
                log(tr("plotting_smc_subsampled", "📐 为加速绘图，抽样至 {n} 个格点").format(n=SMC_SUBSAMPLE))
        else:
            shape = raw.shape
            time_axes = [i for i, s in enumerate(shape) if s == nt]
            time_axis = time_axes[0] if time_axes else 2

            if time_axis == 0:
                Hs = raw.transpose(1, 2, 0)
            elif time_axis == 1:
                Hs = raw.transpose(0, 2, 1)
            elif time_axis == 2:
                if raw.shape[:2] == (len(WW3_lat), len(WW3_lon)):
                    Hs = raw
                else:
                    Hs = raw.transpose(1, 0, 2)
            else:
                Hs = raw

        # ------------------------
        # 区域范围（先基于文件，再收缩到有数据的范围）
        # ------------------------
        if is_pointwise:
            lon_min, lon_max = float(np.nanmin(WW3_lon)), float(np.nanmax(WW3_lon))
            lat_min, lat_max = float(np.nanmin(WW3_lat)), float(np.nanmax(WW3_lat))
            Hs_all = Hs.astype(float)
            Hs_all[Hs_all > 1e10] = np.nan
            pct = np.nanpercentile(Hs_all, CLIM_PCT)
            vmin, vmax = 0, float(pct) if np.isfinite(pct) else 5.0
        else:
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
        if not is_pointwise and not show_land_coastline:
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
        # meshgrid 只创建一次（使用收缩后的范围）- 仅规则网格
        # ------------------------
        if not is_pointwise:
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

        # 创建绘图对象：规则网格用 pcolormesh，点序列网格用 tricontourf（在循环内绘制）
        if is_pointwise:
            from matplotlib.tri import Triangulation

            lon_full = WW3_lon.astype(np.float64)
            lat_full = WW3_lat.astype(np.float64)
            tri = None
            Hs_smc = None
            if mesh_tri_use is not None:
                try:
                    tri = Triangulation(lon_full, lat_full, triangles=mesh_tri_use)
                    Hs_smc = Hs
                except Exception as e:
                    log(
                        tr(
                            "plotting_tri_mesh_fallback",
                            "⚠️ NetCDF 三角连通无法用于绘图，改用 Delaunay: {error}",
                        ).format(error=e)
                    )
                    tri = None
            if tri is None:
                smc_valid = (
                    np.isfinite(WW3_lon)
                    & np.isfinite(WW3_lat)
                    & (np.abs(WW3_lon) <= 360)
                    & (np.abs(WW3_lat) <= 90)
                )
                lon_tri = WW3_lon[smc_valid].astype(np.float64)
                lat_tri = WW3_lat[smc_valid].astype(np.float64)
                tri = Triangulation(lon_tri, lat_tri)
                Hs_smc = Hs[:, smc_valid]
            pcm = None
            sm = plt.cm.ScalarMappable(cmap=cm.turbo, norm=plt.Normalize(vmin=vmin, vmax=vmax))
            sm.set_array([])
            cb = fig.colorbar(sm, ax=ax, orientation='horizontal', fraction=0.05, pad=0.06, aspect=40)
            cb.set_label(varlabel)
        else:
            def _calc_edges(arr):
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

        smc_tcf = None  # SMC 时保存上一帧的 tricontourf，用于移除
        for idx, (tid, t_target) in enumerate(zip(target_ids, targets)):
            # 每10张图片更新一次进度
            if (idx + 1) % 10 == 0 or idx == 0:
                progress_pct = int((idx + 1) / total * 100)
                if generate_video:
                    log(tr("plotting_progress_frames", "📊 进度: {current}/{total} ({percent}%) - 已处理 {processed} 帧").format(current=idx + 1, total=total, percent=progress_pct, processed=num))
                else:
                    log(tr("plotting_progress_images", "📊 进度: {current}/{total} ({percent}%) - 已生成 {generated} 张图片").format(current=idx + 1, total=total, percent=progress_pct, generated=num))

            if is_pointwise:
                Hs_now = Hs_smc[tid, :].astype(float)
                Hs_now[Hs_now > 1e10] = np.nan
            else:
                Hs_now = Hs[np.ix_(lat_idx, lon_idx, [tid])][:,:,0].astype(float)
                Hs_now[Hs_now>1e10] = np.nan

            # 如果有效数据比例过低，跳过这一帧，避免大片空白
            valid_mask = np.isfinite(Hs_now)
            valid_ratio = valid_mask.sum() / valid_mask.size if valid_mask.size > 0 else 0
            if valid_ratio < 0.02:
                log(tr("plotting_skip_frame_low_data", "⚠️  时刻 {time} 有效数据仅 {ratio}% ，跳过绘制以避免空白").format(time=t_target, ratio=f"{valid_ratio*100:.1f}"))  # type: ignore[name-defined]
                continue

            if is_pointwise:
                # 移除上一帧的 tricontourf（兼容无 .collections 的 matplotlib）
                remove_tricontourf_artist(smc_tcf)
                Hs_plot = np.where(np.isfinite(Hs_now), Hs_now, vmin)
                smc_tcf = ax.tricontourf(tri, Hs_plot, levels=20, transform=ccrs.PlateCarree(),
                                         cmap=cm.turbo, vmin=vmin, vmax=vmax)
            else:
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
                if is_pointwise and u10_pw is not None:
                    u_now = u10_pw[tid]
                    v_now = v10_pw[tid] if v10_pw is not None else np.zeros_like(u_now)
                    wind_speed_now = np.sqrt(u_now ** 2 + v_now ** 2)
                    if np.nanmax(wind_speed_now) - np.nanmin(wind_speed_now) < 1e-6:
                        ws = float(np.nanmean(wind_speed_now))
                        wind_info = f" | Wind {ws:.1f} m/s (uniform)"
                elif u10_data is not None and not is_pointwise:
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
        available_vars = list(ds.variables.keys())
        lon_name, lat_name = ww3_resolve_lon_lat_names(ds)
        if not lon_name or not lat_name:
            log(
                tr(
                    "plotting_missing_lon_lat_variables",
                    "❌ 无法识别经度/纬度变量（需 longitude/lon、latitude/lat 等）。可用变量: {vars}",
                ).format(vars=", ".join(available_vars))
            )
            ds.close()
            log_queue.put("__DONE__")
            result_queue.put([])
            return

        WW3_time_var = ds.variables["time"]
        try:
            WW3_datetime = num2date(WW3_time_var[:], WW3_time_var.units)
            WW3_datetime = np.array([datetime.utcfromtimestamp(dt.timestamp()) for dt in WW3_datetime])
        except Exception:
            ref = datetime(1990, 1, 1)
            WW3_datetime = np.array([ref + timedelta(days=float(t)) for t in WW3_time_var[:]])
        nt = len(WW3_datetime)

        WW3_lon = np.array(ds.variables[lon_name][:])
        WW3_lat = np.array(ds.variables[lat_name][:])
        try:
            WW3_lon, WW3_lat = ww3_prepare_lon_lat_1d(WW3_lon, WW3_lat, nt)
        except Exception as e:
            log(
                tr(
                    "plotting_lon_lat_prepare_failed",
                    "❌ 经纬度坐标形状无法解析: {error}",
                ).format(error=e)
            )
            ds.close()
            log_queue.put("__DONE__")
            result_queue.put([])
            return

        # 读取波高数据（含 NetCDF _FillValue 处理）
        raw_var = ds.variables["hs"]
        raw = np.array(raw_var[:])
        _fv = getattr(raw_var, "_FillValue", None)
        if _fv is not None:
            fv = float(np.asarray(_fv).flat[0])
            raw = np.where(np.abs(raw.astype(float) - fv) < 1e30, np.nan, raw)
        raw = np.where(raw > 1e30, np.nan, raw)
        raw = np.where(raw > 1e10, np.nan, raw)
        varlabel = "Total Hs (m)"
        prefix = "contour_hs"

        if np.isfinite(raw).sum() == 0:
            log(tr("plotting_all_missing", "❌ 文件中所有格点均为缺测值，请检查 WW3 输出或模拟设置"))
            ds.close()
            log_queue.put("__DONE__")
            result_queue.put([])
            return

        is_pointwise, Hs_pw = ww3_is_pointwise_grid(WW3_lon, WW3_lat, raw, nt)
        n_points_full = int(np.asarray(WW3_lon).ravel().size)
        mesh_tri_global = ww3_try_mesh_triangles(ds, n_points_full) if is_pointwise else None

        u_raw_wind = np.array(ds.variables["u10"][:]) if "u10" in ds.variables else None
        v_raw_wind = np.array(ds.variables["v10"][:]) if "v10" in ds.variables else None

        ds.close()

        u10_data = None
        v10_data = None
        u10_pw = None
        v10_pw = None
        if not is_pointwise:
            if u_raw_wind is not None:
                u_raw = u_raw_wind
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
            if v_raw_wind is not None:
                v_raw = v_raw_wind
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
        else:
            if u_raw_wind is not None:
                u10_pw = ww3_try_pointwise_timeseries(u_raw_wind, nt, n_points_full)
                if u10_pw is not None:
                    u10_pw = u10_pw.astype(float)
                    u10_pw[u10_pw > 1e10] = np.nan
            if v_raw_wind is not None:
                v10_pw = ww3_try_pointwise_timeseries(v_raw_wind, nt, n_points_full)
                if v10_pw is not None:
                    v10_pw = v10_pw.astype(float)
                    v10_pw[v10_pw > 1e10] = np.nan

        WW3_lon = np.asarray(WW3_lon).squeeze()
        WW3_lat = np.asarray(WW3_lat).squeeze()
        npoints = len(WW3_lon) if WW3_lon.ndim == 1 else WW3_lon.size
        mesh_tri_use = mesh_tri_global
        if is_pointwise:
            log(
                tr(
                    "plotting_unst_pointwise_detected",
                    "📐 检测到非结构/点序列网格 ({n} 个节点)，维度 (time×node) 或 (node×time) 已对齐",
                ).format(n=npoints)
            )
            Hs = np.asarray(Hs_pw, dtype=float)
            Hs[Hs > 1e10] = np.nan
            SMC_SUBSAMPLE = 50000
            if npoints > SMC_SUBSAMPLE:
                rng = np.random.default_rng(42)
                idx = rng.choice(npoints, SMC_SUBSAMPLE, replace=False)
                idx = np.sort(idx)
                WW3_lon = WW3_lon[idx]
                WW3_lat = WW3_lat[idx]
                Hs = Hs[:, idx]
                mesh_tri_use = None
                if u10_pw is not None:
                    u10_pw = u10_pw[:, idx]
                if v10_pw is not None:
                    v10_pw = v10_pw[:, idx]
                npoints = SMC_SUBSAMPLE
                log(tr("plotting_smc_subsampled", "📐 为加速绘图，抽样至 {n} 个格点").format(n=SMC_SUBSAMPLE))
        else:
            shape = raw.shape
            time_axes = [i for i, s in enumerate(shape) if s == nt]
            time_axis = time_axes[0] if time_axes else 2
            if time_axis == 0:
                Hs = raw.transpose(1, 2, 0)
            elif time_axis == 1:
                Hs = raw.transpose(0, 2, 1)
            elif time_axis == 2:
                if raw.shape[:2] == (len(WW3_lat), len(WW3_lon)):
                    Hs = raw
                else:
                    Hs = raw.transpose(1, 0, 2)
            else:
                Hs = raw
        
        # 区域范围（先基于文件，再收缩到有数据的范围）
        if is_pointwise:
            lon_min, lon_max = float(np.nanmin(WW3_lon)), float(np.nanmax(WW3_lon))
            lat_min, lat_max = float(np.nanmin(WW3_lat)), float(np.nanmax(WW3_lat))
            Hs_all = Hs.astype(float)
            Hs_all[Hs_all > 1e10] = np.nan
            pct = np.nanpercentile(Hs_all, CLIM_PCT)
            vmin, vmax = 0, float(pct) if np.isfinite(pct) else 5.0
        else:
            lon_min, lon_max = WW3_lon.min(), WW3_lon.max()
            lat_min, lat_max = WW3_lat.min(), WW3_lat.max()
            lon_idx = np.where((WW3_lon>=lon_min)&(WW3_lon<=lon_max))[0]
            lat_idx = np.where((WW3_lat>=lat_min)&(WW3_lat<=lat_max))[0]
            lon_sub, lat_sub = WW3_lon[lon_idx], WW3_lat[lat_idx]
            Hs_all = Hs[np.ix_(lat_idx, lon_idx, range(Hs.shape[2]))].astype(float)
            Hs_all[Hs_all>1e10] = np.nan
            vmin, vmax = 0, np.nanpercentile(Hs_all, CLIM_PCT)
        
        # 如果显示陆地和海岸线，则不进行数据范围收缩（保持完整的地图范围）
        # 收缩到有数据的经纬度范围，避免无数据区域造成空白
        if not is_pointwise and not show_land_coastline:
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
   
        # 创建网格（使用与波高图相同的UPSAMPLE_FACTOR）- 仅规则网格
        if not is_pointwise:
            if UPSAMPLE_FACTOR > 1:
                lon_plot_1d = np.linspace(lon_sub[0], lon_sub[-1], len(lon_sub)*UPSAMPLE_FACTOR)
                lat_plot_1d = np.linspace(lat_sub[0], lat_sub[-1], len(lat_sub)*UPSAMPLE_FACTOR)
            else:
                lon_plot_1d = lon_sub
                lat_plot_1d = lat_sub
            LON_plot_base, LAT_plot_base = np.meshgrid(lon_plot_1d, lat_plot_1d)
            tri_contour = None
            Hs_contour_smc = None
        else:
            from matplotlib.tri import Triangulation

            lon_full = WW3_lon.astype(np.float64)
            lat_full = WW3_lat.astype(np.float64)
            tri_contour = None
            Hs_contour_smc = None
            if mesh_tri_use is not None:
                try:
                    tri_contour = Triangulation(lon_full, lat_full, triangles=mesh_tri_use)
                    Hs_contour_smc = Hs
                except Exception as e:
                    log(
                        tr(
                            "plotting_tri_mesh_fallback",
                            "⚠️ NetCDF 三角连通无法用于绘图，改用 Delaunay: {error}",
                        ).format(error=e)
                    )
                    tri_contour = None
            if tri_contour is None:
                smc_valid = (
                    np.isfinite(WW3_lon)
                    & np.isfinite(WW3_lat)
                    & (np.abs(WW3_lon) <= 360)
                    & (np.abs(WW3_lat) <= 90)
                )
                lon_tri = WW3_lon[smc_valid].astype(np.float64)
                lat_tri = WW3_lat[smc_valid].astype(np.float64)
                tri_contour = Triangulation(lon_tri, lat_tri)
                Hs_contour_smc = Hs[:, smc_valid]
        
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
            
            if is_pointwise:
                Hs_now_raw = Hs_contour_smc[tid, :].astype(float)
            else:
                Hs_now_raw = Hs[np.ix_(lat_idx, lon_idx, [tid])][:,:,0].astype(float)
            Hs_now_raw[Hs_now_raw>1e10] = np.nan
            
            # 如果有效数据比例过低，跳过
            valid_mask = np.isfinite(Hs_now_raw)
            valid_ratio = valid_mask.sum() / valid_mask.size if valid_mask.size > 0 else 0
            if valid_ratio < 0.02:
                continue
            
            if is_pointwise:
                Hs_now = Hs_now_raw
            else:
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
            
            # 绘制波高图作为底图
            if is_pointwise:
                Hs_plot = np.where(np.isfinite(Hs_now), Hs_now, vmin)
                pcm = ax.tricontourf(tri_contour, Hs_plot, levels=20,
                                     transform=ccrs.PlateCarree(),
                                     cmap=cm.turbo, vmin=vmin, vmax=vmax,
                                     zorder=1)
            else:
                LON_plot, LAT_plot = LON_plot_base, LAT_plot_base
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
            if is_pointwise:
                cs = ax.tricontour(tri_contour, Hs_plot, levels=contour_levels,
                                   transform=ccrs.PlateCarree(), colors='black', linewidths=0.8,
                                   zorder=3)
            else:
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
                if is_pointwise and u10_pw is not None:
                    u_now = u10_pw[tid]
                    v_now = v10_pw[tid] if v10_pw is not None else np.zeros_like(u_now)
                    wind_speed_now = np.sqrt(u_now ** 2 + v_now ** 2)
                    if np.nanmax(wind_speed_now) - np.nanmin(wind_speed_now) < 1e-6:
                        ws = float(np.nanmean(wind_speed_now))
                        wind_info = f" | Wind {ws:.1f} m/s (uniform)"
                elif u10_data is not None and not is_pointwise:
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
