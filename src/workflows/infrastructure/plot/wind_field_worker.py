"""风场填色图与箭头/风旗可视化 Worker — 从风场 NetCDF 生成 10m 风场空间分布图。

在独立子进程中读取风场 NetCDF（支持 u10/v10、wndewd/wndnwd、uwnd/vwnd 等命名），
使用 cartopy 投影绘制 RdYlBu_r 离散分级填色等值线图（跨帧统一色阶），可选叠加
箭头或风旗，并支持 cv2 上采样以提高背景分辨率。

结果 PNG 序列输出至 ``{selected_folder}/photo/wind_field/wind_{timestamp}.png``，
路径列表经 ``result_queue`` 回传。
"""

import os
import glob
import platform
from datetime import timedelta

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib import cm
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from netCDF4 import Dataset, num2date

from ...support.translations import tr
from .photo_output import SUBDIR_WIND_FIELD, prepare_photo_subdir


def _make_wind_field_worker(
    data_nc_path,
    selected_folder,
    time_step_hours,
    flag_type,
    density_step,
    log_queue,
    result_queue,
):
    """在子进程中按时间步长生成 10m 风场填色图序列。

    Parameters
    ----------
    data_nc_path : str
        风场 NetCDF 文件路径。
    selected_folder : str
        结果输出根目录（图片保存至其下 ``photo/wind_field/`` 子目录）。
    time_step_hours : float
        输出时间间隔（小时）。
    flag_type : str
        叠加标志类型：``"箭头"`` / ``"风旗"`` / ``"无"``（或对应翻译文本）。
    density_step : int
        箭头/风旗稀疏化步长；``None`` 时自动推算。
    log_queue : queue-like
        日志队列，``put(msg)`` 发送进度，完成后 ``put("__DONE__")``。
    result_queue : queue-like
        结果队列，``put(saved_paths)`` 回传生成的 PNG 路径列表。
    """
    try:
        def log(msg):
            """Send a log message to the queue."""
            try:
                log_queue.put(msg)
            except Exception:
                pass

        # ------------------------------------------------------------------
        # Switch to non-GUI backend before any figure work
        # ------------------------------------------------------------------
        original_backend = matplotlib.get_backend()
        matplotlib.use("Agg")

        try:
            system = platform.system()
            if system == "Linux":
                plt.rcParams["font.sans-serif"] = [
                    "DejaVu Sans", "Liberation Sans", "Noto Sans",
                    "Arial", "Droid Sans Fallback",
                ]
                plt.rcParams["axes.unicode_minus"] = False
        except Exception:
            pass

        log(tr("wind_field_worker_start", "\U0001f504 开始生成风场图（在子进程中执行）..."))

        # ------------------------------------------------------------------
        # Open dataset and resolve variable names
        # ------------------------------------------------------------------
        with Dataset(data_nc_path, "r") as ds:

            def _pick_var_name(candidates):
                for name in candidates:
                    if name in ds.variables:
                        return name
                return None

            # Coordinate & time variables
            lon_name = _pick_var_name([
                "longitude", "lon", "LONGITUDE", "LON", "Longitude",
            ])
            lat_name = _pick_var_name([
                "latitude", "lat", "LATITUDE", "LAT", "Latitude",
            ])
            time_name = _pick_var_name([
                "valid_time", "time", "Time", "TIME", "t", "MT", "mt",
            ])

            if not lon_name or not lat_name or not time_name:
                missing = []
                if not lon_name:
                    missing.append(tr("longitude", "经度"))
                if not lat_name:
                    missing.append(tr("latitude", "纬度"))
                if not time_name:
                    missing.append(tr("time", "时间"))
                raise KeyError(
                    tr("missing_variables", "缺少变量：{vars}").format(
                        vars=", ".join(missing)
                    )
                )

            longitude = np.array(ds.variables[lon_name][:])
            latitude = np.array(ds.variables[lat_name][:])
            time_var = ds.variables[time_name]
            time_values = np.array(time_var[:])

            # Wind component variables (multiple naming conventions)
            u10_name = _pick_var_name([
                "u10", "U10", "wndewd", "WNDEWD", "eastward_wind",
                "u", "uwnd", "UWND", "uwnd10m", "UWND10M",
            ])
            v10_name = _pick_var_name([
                "v10", "V10", "wndnwd", "WNDNWD", "northward_wind",
                "v", "vwnd", "VWND", "vwnd10m", "VWND10M",
            ])

            if not u10_name:
                raise KeyError(
                    tr("missing_eastward_wind",
                       "缺少东向风变量（u10/wndewd/uwnd）")
                )
            if not v10_name:
                raise KeyError(
                    tr("missing_northward_wind",
                       "缺少北向风变量（v10/wndnwd/vwnd）")
                )

            u10 = np.array(ds.variables[u10_name][:])
            v10 = np.array(ds.variables[v10_name][:])

            # -- time parsing -----------------------------------------------
            if time_values.size == 0:
                log(tr("wind_time_dimension_empty",
                       "\u26a0\ufe0f 时间维度为空，无法生成风场图"))
                log_queue.put("__DONE__")
                result_queue.put([])
                return

            times_dt = None
            try:
                units = getattr(time_var, "units", None)
                calendar = getattr(time_var, "calendar", "standard")
                if units:
                    times_dt = num2date(time_values, units, calendar=calendar)
            except Exception as e:
                log(tr("wind_time_parse_failed",
                       "\u26a0\ufe0f 时间解析失败，改用索引：{error}").format(error=e))
                times_dt = None

        # ------------------------------------------------------------------
        # Select time indices based on step_hours
        # ------------------------------------------------------------------
        step_hours = time_step_hours
        indices = []
        if times_dt is not None and len(times_dt) > 0:
            last = None
            for i, t in enumerate(times_dt):
                if last is None or (t - last) >= timedelta(hours=step_hours) - timedelta(seconds=1):
                    indices.append(i)
                    last = t
        else:
            step_guess = 1
            if len(time_values) > 1:
                try:
                    dt_seconds = float(time_values[1] - time_values[0])
                    if dt_seconds > 0:
                        step_guess = max(
                            1, int(round((step_hours * 3600) / dt_seconds))
                        )
                except Exception:
                    step_guess = 1
            indices = list(range(0, len(time_values), step_guess))

        if not indices:
            indices = [0]

        # ------------------------------------------------------------------
        # Prepare output directory
        # ------------------------------------------------------------------
        try:
            output_dir = prepare_photo_subdir(selected_folder, SUBDIR_WIND_FIELD)
        except Exception as e:
            log(tr("wind_clean_output_dir_failed",
                   "\u274c 清理输出目录失败: {error}").format(error=e))
            log_queue.put("__DONE__")
            result_queue.put([])
            return

        # ------------------------------------------------------------------
        # Spatial extent & meshgrid
        # ------------------------------------------------------------------
        lon_min, lon_max = float(np.min(longitude)), float(np.max(longitude))
        lat_min, lat_max = float(np.min(latitude)), float(np.max(latitude))
        extent = [lon_min, lon_max, lat_min, lat_max]

        lon2d, lat2d = np.meshgrid(longitude, latitude)

        # Arrow / barb density step
        density = density_step
        if density is not None:
            q_step = max(1, int(density))
        else:
            grid_size = max(len(longitude), len(latitude))
            if grid_size > 300:
                q_step = max(1, int(grid_size / 400))
            elif grid_size > 150:
                q_step = max(1, int(grid_size / 350))
            elif grid_size > 80:
                q_step = max(1, int(grid_size / 300))
            else:
                q_step = max(1, int(grid_size / 250))
            q_step = max(q_step, 3)

        # ------------------------------------------------------------------
        # 全局离散颜色分级（RdYlBu_r 配色，跨帧一致，仿 animate_arriving_swell）
        # [EN] Global discrete color levels (RdYlBu_r), consistent across frames.
        # ------------------------------------------------------------------
        speed_all = np.sqrt(
            np.asarray(u10, dtype=float) ** 2 + np.asarray(v10, dtype=float) ** 2
        )
        if np.any(np.isfinite(speed_all)):
            p_lo = float(np.nanpercentile(speed_all, 2))
            p_hi = float(np.nanpercentile(speed_all, 98))
        else:
            p_lo, p_hi = 0.0, 1.0
        _rng = max(p_hi - p_lo, 1.0)
        # 选“整”步长，使填色约 60 档（很细，接近连续）[EN] nice step → ~60 bands
        level_step = next(
            (s for s in (0.1, 0.2, 0.25, 0.5, 1.0, 2.0) if _rng / s <= 60), 2.0
        )
        g_lo = max(0.0, np.floor(p_lo / level_step) * level_step)
        g_hi = np.ceil(p_hi / level_step) * level_step
        if g_hi <= g_lo:
            g_hi = g_lo + level_step
        fill_levels = np.arange(g_lo, g_hi + level_step / 2.0, level_step)
        # 等值线分级独立取粗（约 6–8 条），避免细填色下标注拥挤
        # [EN] coarser, label-friendly line levels (~6-8 lines) independent of fill
        line_step = max(level_step, next(
            (s for s in (1.0, 2.0, 2.5, 5.0, 10.0) if _rng / s <= 8), 10.0
        ))
        line_levels = np.arange(g_lo, g_hi + line_step / 2.0, line_step)
        line_fmt = "%.1f" if line_step < 1.0 else "%.0f"
        wind_cmap = cm.get_cmap("RdYlBu_r")

        saved_paths = []
        UPSAMPLE_FACTOR = 3

        # ------------------------------------------------------------------
        # Main loop over selected time indices
        # ------------------------------------------------------------------
        total = len(indices)
        for progress_idx, idx in enumerate(indices):
            if (progress_idx + 1) % 10 == 0 or progress_idx == 0:
                pct = int((progress_idx + 1) / total * 100)
                log(
                    tr("wind_field_progress",
                       "\U0001f4ca 进度: {current}/{total} ({percent}%)")
                    .format(current=progress_idx + 1, total=total, percent=pct)
                )

            u = u10[idx]
            v = v10[idx]
            speed = np.sqrt(u ** 2 + v ** 2)

            # -- cv2 upsampling for higher-resolution background ------------
            if UPSAMPLE_FACTOR > 1:
                try:
                    import cv2
                    speed_upsampled = cv2.resize(
                        speed,
                        (len(longitude) * UPSAMPLE_FACTOR,
                         len(latitude) * UPSAMPLE_FACTOR),
                        interpolation=cv2.INTER_LINEAR,
                    )
                    lon_upsampled = np.linspace(
                        longitude.min(), longitude.max(),
                        len(longitude) * UPSAMPLE_FACTOR,
                    )
                    lat_upsampled = np.linspace(
                        latitude.min(), latitude.max(),
                        len(latitude) * UPSAMPLE_FACTOR,
                    )
                    lon2d_upsampled, lat2d_upsampled = np.meshgrid(
                        lon_upsampled, lat_upsampled
                    )
                    speed_plot = speed_upsampled
                    lon2d_plot = lon2d_upsampled
                    lat2d_plot = lat2d_upsampled
                except ImportError:
                    speed_plot = speed
                    lon2d_plot = lon2d
                    lat2d_plot = lat2d
            else:
                speed_plot = speed
                lon2d_plot = lon2d
                lat2d_plot = lat2d

            # -- Build figure -----------------------------------------------
            fig = plt.figure(figsize=(10, 8), dpi=150, facecolor="white")
            ax = plt.axes(projection=ccrs.PlateCarree())
            ax.set_extent(extent, crs=ccrs.PlateCarree())
            ax.set_facecolor("white")
            ax.set_axis_off()
            ax.coastlines(resolution="50m", linewidth=0.5)
            ax.add_feature(cfeature.OCEAN, facecolor="#a4d6ff")
            ax.add_feature(cfeature.LAND, facecolor="#e6e6e6")

            # -- Filled contours (RdYlBu_r, discrete levels) ----------------
            filled = ax.contourf(
                lon2d_plot, lat2d_plot, speed_plot,
                levels=fill_levels,
                cmap=wind_cmap,
                extend="both",
                transform=ccrs.PlateCarree(),
            )

            # Coarser contour lines for gradient readability
            contour_lines = ax.contour(
                lon2d_plot, lat2d_plot, speed_plot,
                levels=line_levels,
                colors="#303030",
                linewidths=0.5,
                alpha=0.6,
                transform=ccrs.PlateCarree(),
            )
            ax.clabel(contour_lines, inline=True, fontsize=7, fmt=line_fmt)

            # -- Optional arrows / barbs ------------------------------------
            from ...application.plot_wind_field import (
                WIND_FLAG_ARROW,
                WIND_FLAG_BARB,
                normalize_wind_flag_type,
            )

            flag = normalize_wind_flag_type(flag_type)
            if flag == WIND_FLAG_ARROW:
                ax.quiver(
                    lon2d[::q_step, ::q_step],
                    lat2d[::q_step, ::q_step],
                    u[::q_step, ::q_step],
                    v[::q_step, ::q_step],
                    color="black",
                    scale=400,
                    transform=ccrs.PlateCarree(),
                )
            elif flag == WIND_FLAG_BARB:
                ax.barbs(
                    lon2d[::q_step, ::q_step],
                    lat2d[::q_step, ::q_step],
                    u[::q_step, ::q_step],
                    v[::q_step, ::q_step],
                    length=5,
                    transform=ccrs.PlateCarree(),
                )
            # flag == WIND_FLAG_NONE or anything else: no overlay

            # -- Colorbar & title -------------------------------------------
            cbar = fig.colorbar(
                filled, ax=ax,
                orientation="vertical",
                fraction=0.046,
                pad=0.04,
            )
            cbar.set_label("Wind speed (m/s)")

            if times_dt is not None and len(times_dt) > idx:
                ts_label = times_dt[idx].strftime("%Y%m%d_%H%M%S")
                title_time = times_dt[idx].strftime("%Y-%m-%d %H:%M")
            else:
                ts_label = f"idx{idx:03d}"
                title_time = f"Index {idx}"

            ax.set_title(f"10m Wind Field ({title_time})")
            fig.subplots_adjust(left=0, right=1, top=0.95, bottom=0)
            fig.tight_layout(pad=0.1)

            out_path = os.path.join(output_dir, f"wind_{ts_label}.png")
            fig.savefig(
                out_path,
                dpi=250,
                bbox_inches="tight",
                pad_inches=0.05,
                facecolor="white",
                edgecolor="none",
            )
            saved_paths.append(out_path)
            plt.close(fig)

        # ------------------------------------------------------------------
        # Summary & completion
        # ------------------------------------------------------------------
        if saved_paths:
            log(
                tr("plotting_wind_field_generated",
                   "\u2705 已生成 {count} 张风场图，保存在 {path}")
                .format(count=len(saved_paths), path=output_dir)
            )
        else:
            log(tr("wind_no_images_generated",
                   "\u26a0\ufe0f 未生成风场图，检查数据是否为空"))

    except Exception as e:
        import traceback
        error_msg = tr("wind_generation_failed",
                       "\u274c 生成风场图失败: {error}").format(error=e)
        try:
            log_queue.put(error_msg)
            log_queue.put(traceback.format_exc())
        except Exception:
            pass
        saved_paths = []

    finally:
        try:
            matplotlib.use(original_backend)
        except Exception:
            pass

    log_queue.put("__DONE__")
    result_queue.put(saved_paths)
