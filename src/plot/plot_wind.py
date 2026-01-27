"""
风场绘图模块
包含风场绘图的 UI 创建和逻辑
"""

import os
import glob
import threading
import platform
from datetime import timedelta
import numpy as np
import matplotlib
matplotlib.use('QtAgg')
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from netCDF4 import Dataset, num2date
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt
from qfluentwidgets import (
    PrimaryPushButton, LineEdit, HeaderCardWidget, ComboBox, InfoBar
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QSizePolicy
)

from setting.config import WIND_FIELD_TIME_STEP
from setting.language_manager import tr


class WindFieldPlotMixin:
    """风场绘图功能 Mixin"""
    
    def _create_wind_field_ui(self, plot_content_widget, plot_content_layout, button_style, input_style):
        """创建风场绘图 UI"""
        # 风场绘图块
        wind_field_card = HeaderCardWidget(plot_content_widget)
        wind_field_card.setTitle(tr("plotting_wind_field", "风场绘图"))
        wind_field_card.setStyleSheet("""
            HeaderCardWidget QLabel {
                font-weight: normal;
                margin-left: 0px;
                padding-left: 0px;
            }
        """)
        wind_field_card.headerLayout.setContentsMargins(11, 10, 11, 12)
        wind_field_card_layout = QVBoxLayout()
        wind_field_card_layout.setSpacing(10)
        wind_field_card_layout.setContentsMargins(0, 0, 0, 0)

        # 使用网格布局确保输入框和选择框左右对齐且占满宽度
        wind_params_grid = QGridLayout()
        wind_params_grid.setColumnStretch(1, 1)
        wind_params_grid.setSpacing(5)

        # 风场时间步长输入
        wind_step_label = QLabel(tr("plotting_wind_timestep", "时间步长 (小时):"))
        if not hasattr(self, 'wind_field_timestep_edit'):
            self.wind_field_timestep_edit = LineEdit()
            # 从配置读取默认值，如果没有则使用 "24"
            default_wind_step = str(WIND_FIELD_TIME_STEP) if WIND_FIELD_TIME_STEP else "24"
            self.wind_field_timestep_edit.setText(default_wind_step)
        else:
            # 如果输入框已存在，确保显示当前配置值
            default_wind_step = str(WIND_FIELD_TIME_STEP) if WIND_FIELD_TIME_STEP else "24"
            if not self.wind_field_timestep_edit.text().strip():
                self.wind_field_timestep_edit.setText(default_wind_step)
        # 设置占位符文本
        placeholder_value = str(WIND_FIELD_TIME_STEP) if WIND_FIELD_TIME_STEP else "24"
        self.wind_field_timestep_edit.setPlaceholderText(tr("plotting_default_hours", "默认 {value} 小时").format(value=placeholder_value))
        self.wind_field_timestep_edit.setStyleSheet(input_style)
        wind_params_grid.addWidget(wind_step_label, 0, 0)
        wind_params_grid.addWidget(self.wind_field_timestep_edit, 0, 1)

        # 风向标志类型选择下拉框
        wind_flag_label = QLabel(tr("plotting_wind_flag", "风向标志:"))
        if not hasattr(self, 'wind_field_flag_combo'):
            self.wind_field_flag_combo = ComboBox()
            self.wind_field_flag_combo.addItems([
                tr("plotting_wind_flag_arrow", "箭头"),
                tr("plotting_wind_flag_flag", "风旗"),
                tr("plotting_wind_flag_none", "无")
            ])
            self.wind_field_flag_combo.setCurrentText(tr("plotting_wind_flag_arrow", "箭头"))  # 默认选择箭头
        self.wind_field_flag_combo.setStyleSheet(input_style)
        wind_params_grid.addWidget(wind_flag_label, 1, 0)
        wind_params_grid.addWidget(self.wind_field_flag_combo, 1, 1)

        # 风向标志密度输入（步长）
        wind_flag_density_label = QLabel(tr("plotting_wind_flag_density", "标志密度 (步长):"))
        if not hasattr(self, "wind_field_flag_density_edit"):
            self.wind_field_flag_density_edit = LineEdit()
            self.wind_field_flag_density_edit.setText("10")
        self.wind_field_flag_density_edit.setPlaceholderText(
            tr("plotting_wind_flag_density_placeholder", "自动")
        )
        self.wind_field_flag_density_edit.setStyleSheet(input_style)
        wind_params_grid.addWidget(wind_flag_density_label, 2, 0)
        wind_params_grid.addWidget(self.wind_field_flag_density_edit, 2, 1)

        wind_field_card_layout.addLayout(wind_params_grid)

        # 选择风场文件按钮（只选择，不转换）- 放在标志选择框下面
        # 注意：不能复用 step1 的按钮实例，否则会被布局重新父子化导致消失
        if not hasattr(self, 'btn_choose_wind_file_plot'):
            self.btn_choose_wind_file_plot = PrimaryPushButton(tr("step1_choose_wind", "选择风场文件"))
            self.btn_choose_wind_file_plot.setStyleSheet(button_style)
            # 绘图场景仅选择文件，不做复制/转换
            self.btn_choose_wind_file_plot.clicked.connect(self.choose_wind_field_file_plot)
        wind_field_card_layout.addWidget(self.btn_choose_wind_file_plot)

        # 初始化时自动检测并更新按钮（会在 _update_wind_file_button 中处理）

        # 生成风场图按钮
        if not hasattr(self, 'generate_field_button'):
            self.generate_field_button = PrimaryPushButton(tr("plotting_generate_wind", "生成风场图"))
            self.generate_field_button.setStyleSheet(button_style)
            self.generate_field_button.clicked.connect(lambda: self.generate_wind_field_maps())
        wind_field_card_layout.addWidget(self.generate_field_button)

        # 查看风场图按钮
        if not hasattr(self, 'view_field_button'):
            self.view_field_button = PrimaryPushButton(tr("plotting_view_wind", "查看风场图"))
            self.view_field_button.setStyleSheet(button_style)
            self.view_field_button.clicked.connect(lambda: self.view_wind_field_images())
        wind_field_card_layout.addWidget(self.view_field_button)

        # 设置内容区内边距
        wind_field_card.viewLayout.setContentsMargins(11, 10, 11, 12)
        wind_field_card.viewLayout.addLayout(wind_field_card_layout)
        plot_content_layout.addWidget(wind_field_card)
        
        # 初始化时自动检测并更新按钮
        self._update_wind_file_button()

    
    def _update_wind_file_button(self):
        """更新风场文件按钮文本（自动检测 wind.nc 或 wind_*.nc）"""
        if not hasattr(self, 'btn_choose_wind_file') and not hasattr(self, 'btn_choose_wind_file_plot'):
            return
        
        # 如果没有 selected_origin_file，则自动检测工作目录中的文件
        if not hasattr(self, 'selected_folder') or not self.selected_folder:
            return
        
        # 优先检查 wind.nc
        data_nc_path = os.path.join(self.selected_folder, "wind.nc")
        if not os.path.exists(data_nc_path):
            # 如果 wind.nc 不存在，查找 wind_*.nc 文件
            wind_pattern = os.path.join(self.selected_folder, "wind_*.nc")
            wind_files = glob.glob(wind_pattern)
            if wind_files:
                # 如果有多个，按字母顺序选择第一个
                data_nc_path = sorted(wind_files)[0]
        
        if os.path.exists(data_nc_path):
            file_name = os.path.basename(data_nc_path)
            if len(file_name) > 30:
                display_name = file_name[:27] + "..."
            else:
                display_name = file_name
            self._set_wind_file_button_text(display_name, filled=True)
            # 强制更新按钮显示
            if hasattr(self, 'btn_choose_wind_file_plot'):
                self.btn_choose_wind_file_plot.update()
            # 同时更新 selected_origin_file，以便生成风场图时使用
            if not hasattr(self, 'selected_origin_file') or not self.selected_origin_file:
                self.selected_origin_file = data_nc_path

    def _set_wind_file_button_text(self, display_name: str, filled: bool = False):
        """同步更新 step1 和 plot 的风场按钮文本"""
        if hasattr(self, 'btn_choose_wind_file'):
            if hasattr(self, '_set_home_forcing_button_text'):
                self._set_home_forcing_button_text(self.btn_choose_wind_file, display_name, filled=filled)
            else:
                self.btn_choose_wind_file.setText(display_name)
        if hasattr(self, 'btn_choose_wind_file_plot'):
            self.btn_choose_wind_file_plot.setText(display_name)
            try:
                self.btn_choose_wind_file_plot.setProperty("filled", filled)
                if hasattr(self, '_get_button_style'):
                    self.btn_choose_wind_file_plot.setStyleSheet(self._get_button_style())
                self.btn_choose_wind_file_plot.style().unpolish(self.btn_choose_wind_file_plot)
                self.btn_choose_wind_file_plot.style().polish(self.btn_choose_wind_file_plot)
            except Exception:
                pass

    def choose_wind_field_file_plot(self):
        """绘图场景选择风场文件（不复制、不转换）"""
        default_dir = os.getcwd()
        if hasattr(self, 'selected_origin_file') and self.selected_origin_file:
            try:
                default_dir = os.path.dirname(self.selected_origin_file)
            except Exception:
                pass

        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            tr("wind_file_dialog_title", "选择风场文件"),
            default_dir,
            tr("wind_file_filter", "NetCDF 文件 (*.nc);;所有文件 (*.*)")
        )
        if not file_path:
            return

        self.selected_origin_file = file_path
        file_name = os.path.basename(file_path)
        display_name = file_name[:27] + "..." if len(file_name) > 30 else file_name
        self._set_wind_file_button_text(display_name, filled=True)

    def _restore_wind_field_button(self):
        """恢复生成风场图按钮状态"""
        if hasattr(self, "generate_field_button"):
            self.generate_field_button.setEnabled(True)
            self.generate_field_button.setText(tr("plotting_generate_wind", "生成风场图"))

    def generate_wind_field_maps(self, time_step_hours=6):
        """生成风场图（默认 24 小时间隔），保存到 photo/field 并弹窗预览"""
        if not self.selected_folder:
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return

        # 优先读取输入框时间步长
        if hasattr(self, "wind_field_timestep_edit") and self.wind_field_timestep_edit:
            try:
                user_step_text = self.wind_field_timestep_edit.text().strip()
                if user_step_text:  # 如果输入框不为空
                    user_step = float(user_step_text)
                    if user_step > 0:
                        time_step_hours = user_step
                else:
                    self.log(tr("wind_timestep_empty", "⚠️ 风场时间步长输入框为空，已使用默认值"))
            except ValueError:
                self.log(tr("wind_timestep_parse_failed", "⚠️ 无法解析时间步长 '{text}'，已使用默认值 {default}").format(text=self.wind_field_timestep_edit.text(), default=time_step_hours))
            except Exception as e:
                self.log(tr("wind_timestep_read_error", "⚠️ 读取时间步长出错: {error}，已使用默认值 {default}").format(error=e, default=time_step_hours))
        else:
            self.log(tr("wind_timestep_input_not_found", "ℹ️ 未找到风场时间步长输入框，使用默认值 {default} 小时").format(default=time_step_hours))

        # 优先使用选择的风场文件，如果没有选择则使用转换后的 wind.nc
        if hasattr(self, 'selected_origin_file') and self.selected_origin_file and os.path.exists(self.selected_origin_file):
            data_nc_path = self.selected_origin_file
        else:
            data_nc_path = os.path.join(self.selected_folder, "wind.nc")
            if not os.path.exists(data_nc_path):
                self.log(tr("wind_file_not_found", "❌ 未找到风场文件，请先选择风场文件或完成转换"))
                return
            self.log(tr("wind_file_using_default", "📂 使用默认风场文件"))

        if hasattr(self, "generate_field_button"):
            self.generate_field_button.setEnabled(False)
            self.generate_field_button.setText(tr("step8_generating", "生成中..."))

        # 读取标志类型选择
        flag_type = tr("plotting_wind_flag_arrow", "箭头")  # 默认值
        if hasattr(self, "wind_field_flag_combo") and self.wind_field_flag_combo:
            flag_type = self.wind_field_flag_combo.currentText()

        # 读取标志密度（步长）
        density_step = None
        if hasattr(self, "wind_field_flag_density_edit") and self.wind_field_flag_density_edit:
            density_text = self.wind_field_flag_density_edit.text().strip()
            if density_text:
                try:
                    density_step = max(1, int(float(density_text)))
                except ValueError:
                    self.log(tr("plotting_wind_flag_density_invalid",
                                "⚠️ 标志密度无效，已使用自动值").format(value=density_text))
                    density_step = None
            else:
                density_step = 10
        
        # 将 time_step_hours、flag_type、density_step 作为参数传递给内部函数
        def _worker(step_hours=time_step_hours, flag=flag_type, density=density_step):
            # 在后台线程中使用非 GUI 后端，避免警告
            original_backend = matplotlib.get_backend()
            matplotlib.use('Agg')  # 使用非 GUI 后端
            try:
                system = platform.system()
                if system == 'Linux':
                    plt.rcParams['font.sans-serif'] = [
                        'DejaVu Sans', 'Liberation Sans', 'Noto Sans', 'Arial', 'Droid Sans Fallback'
                    ]
                    plt.rcParams['axes.unicode_minus'] = False
            except Exception:
                pass
            try:
                with Dataset(data_nc_path, "r") as ds:
                    def _pick_var_name(candidates):
                        for name in candidates:
                            if name in ds.variables:
                                return name
                        return None

                    # 支持更多变量名变体，包括 CFSR 和 CCMP 格式
                    lon_name = _pick_var_name(["longitude", "lon", "LONGITUDE", "LON", "Longitude", "longitude"])
                    lat_name = _pick_var_name(["latitude", "lat", "LATITUDE", "LAT", "Latitude", "latitude"])
                    time_name = _pick_var_name(["valid_time", "time", "Time", "TIME", "t", "MT", "mt", "time"])

                    if not lon_name or not lat_name or not time_name:
                        missing = []
                        if not lon_name:
                            missing.append(tr("longitude", "经度"))
                        if not lat_name:
                            missing.append(tr("latitude", "纬度"))
                        if not time_name:
                            missing.append(tr("time", "时间"))
                        raise KeyError(tr("missing_variables", "缺少变量：{vars}").format(vars=', '.join(missing)))

                    longitude = np.array(ds.variables[lon_name][:])
                    latitude = np.array(ds.variables[lat_name][:])
                    time_var = ds.variables[time_name]
                    time_values = np.array(time_var[:])
                    
                    # 支持多种格式的风场变量名：
                    # - 标准格式：u10/v10
                    # - CFSR 格式：wndewd/wndnwd
                    # - CCMP 格式：uwnd/vwnd, uwnd10m/vwnd10m
                    u10_name = _pick_var_name(["u10", "U10", "wndewd", "WNDEWD", "eastward_wind", "u", "uwnd", "UWND", "uwnd10m", "UWND10M"])
                    v10_name = _pick_var_name(["v10", "V10", "wndnwd", "WNDNWD", "northward_wind", "v", "vwnd", "VWND", "vwnd10m", "VWND10M"])
                    
                    if not u10_name:
                        raise KeyError(tr("missing_eastward_wind", "缺少东向风变量（u10/wndewd/uwnd）"))
                    if not v10_name:
                        raise KeyError(tr("missing_northward_wind", "缺少北向风变量（v10/wndnwd/vwnd）"))
                    
                    u10 = np.array(ds.variables[u10_name][:])
                    v10 = np.array(ds.variables[v10_name][:])

                    if time_values.size == 0:
                        self.log_signal.emit(tr("wind_time_dimension_empty", "⚠️ 时间维度为空，无法生成风场图"))
                        return

                    times_dt = None
                    try:
                        units = getattr(time_var, "units", None)
                        calendar = getattr(time_var, "calendar", "standard")
                        if units:
                            times_dt = num2date(time_values, units, calendar=calendar)
                    except Exception as e:
                        self.log_signal.emit(tr("wind_time_parse_failed", "⚠️ 时间解析失败，改用索引：{error}").format(error=e))
                        times_dt = None

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
                                    step_guess = max(1, int(round((step_hours * 3600) / dt_seconds)))
                            except Exception:
                                step_guess = 1
                        indices = list(range(0, len(time_values), step_guess))

                    if not indices:
                        indices = [0]

                    output_dir = os.path.join(self.selected_folder, "photo", "field")
                    # 清空旧文件，再创建目录
                    try:
                        if os.path.exists(output_dir):
                            for f in glob.glob(os.path.join(output_dir, "*")):
                                try:
                                    os.remove(f)
                                except Exception:
                                    pass
                        os.makedirs(output_dir, exist_ok=True)
                    except Exception as e:
                        self.log_signal.emit(tr("wind_clean_output_dir_failed", "❌ 清理输出目录失败: {error}").format(error=e))
                        QtCore.QTimer.singleShot(0, self._restore_wind_field_button)
                        return

                    lon_min, lon_max = float(np.min(longitude)), float(np.max(longitude))
                    lat_min, lat_max = float(np.min(latitude)), float(np.max(latitude))
                    # 不添加边距，只显示数据范围
                    extent = [lon_min, lon_max, lat_min, lat_max]

                    lon2d, lat2d = np.meshgrid(longitude, latitude)
                    # 计算箭头/风旗密度（步长）
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

                    saved_paths = []
                    # 上采样因子，提高背景风速图的精度
                    UPSAMPLE_FACTOR = 3
                    
                    for idx in indices:
                        u = u10[idx]
                        v = v10[idx]
                        speed = np.sqrt(u ** 2 + v ** 2)

                        # 对风速数据进行上采样，提高显示精度
                        if UPSAMPLE_FACTOR > 1:
                            try:
                                import cv2
                                # 使用 cv2 进行双线性插值上采样
                                speed_upsampled = cv2.resize(
                                    speed, 
                                    (len(longitude) * UPSAMPLE_FACTOR, len(latitude) * UPSAMPLE_FACTOR),
                                    interpolation=cv2.INTER_LINEAR
                                )
                                # 对经纬度网格也进行上采样
                                lon_upsampled = np.linspace(longitude.min(), longitude.max(), len(longitude) * UPSAMPLE_FACTOR)
                                lat_upsampled = np.linspace(latitude.min(), latitude.max(), len(latitude) * UPSAMPLE_FACTOR)
                                lon2d_upsampled, lat2d_upsampled = np.meshgrid(lon_upsampled, lat_upsampled)
                                speed_plot = speed_upsampled
                                lon2d_plot = lon2d_upsampled
                                lat2d_plot = lat2d_upsampled
                            except ImportError:
                                # 如果没有 cv2，使用原始数据
                                speed_plot = speed
                                lon2d_plot = lon2d
                                lat2d_plot = lat2d
                        else:
                            speed_plot = speed
                            lon2d_plot = lon2d
                            lat2d_plot = lat2d

                        fig = plt.figure(figsize=(10, 8), dpi=150, facecolor='white')
                        ax = plt.axes(projection=ccrs.PlateCarree())
                        # 只显示风场数据覆盖的区域，不显示范围外的地图
                        ax.set_extent(extent, crs=ccrs.PlateCarree())
                        # 设置背景颜色为白色
                        ax.set_facecolor('white')
                        # 移除坐标轴，避免显示范围外的内容
                        ax.set_axis_off()
                        # 只添加数据范围内的海岸线
                        ax.coastlines(resolution="50m", linewidth=0.5)
                        # 只添加数据范围内的陆地和海洋特征
                        # 注意：cartopy 的 add_feature 会自动裁剪到 extent 范围
                        ax.add_feature(cfeature.OCEAN, facecolor="#a4d6ff")
                        ax.add_feature(cfeature.LAND, facecolor="#e6e6e6")

                        # 绘制等速色块图（等速图色块）
                        from matplotlib import cm
                        try:
                            speed_min = float(np.nanmin(speed_plot))
                            speed_max = float(np.nanmax(speed_plot))
                        except Exception:
                            speed_min, speed_max = 0.0, 0.0
                        if speed_max <= speed_min:
                            speed_max = speed_min + 1.0
                        levels = np.linspace(speed_min, speed_max, 10)
                        filled = ax.contourf(
                            lon2d_plot,
                            lat2d_plot,
                            speed_plot,
                            levels=levels,
                            cmap=cm.get_cmap("RdBu_r"),
                            transform=ccrs.PlateCarree()
                        )
                        # 叠加细的等值线便于识别梯度（可读性更好）
                        contour_lines = ax.contour(
                            lon2d_plot,
                            lat2d_plot,
                            speed_plot,
                            levels=levels,
                            colors="black",
                            linewidths=0.4,
                            alpha=0.5,
                            transform=ccrs.PlateCarree()
                        )
                        ax.clabel(contour_lines, inline=True, fontsize=7, fmt="%.1f")

                        # 根据标志类型选择绘制方式
                        arrow_text = tr("plotting_wind_flag_arrow", "箭头")
                        flag_text = tr("plotting_wind_flag_flag", "风旗")
                        if flag == arrow_text or flag == tr("plotting_wind_flag_arrow", "箭头"):
                            # 箭头使用黑色
                            ax.quiver(
                                lon2d[::q_step, ::q_step], lat2d[::q_step, ::q_step],
                                u[::q_step, ::q_step], v[::q_step, ::q_step],
                                color="black", scale=400, transform=ccrs.PlateCarree()
                            )
                        elif flag == flag_text or flag == tr("plotting_wind_flag_flag", "风旗"):
                            # 风旗（风羽）使用 barbs
                            ax.barbs(
                                lon2d[::q_step, ::q_step], lat2d[::q_step, ::q_step],
                                u[::q_step, ::q_step], v[::q_step, ::q_step],
                                length=5, transform=ccrs.PlateCarree()
                            )
                        # 如果选择"无"，则不绘制任何标志

                        cbar = fig.colorbar(filled, ax=ax, orientation="vertical", fraction=0.046, pad=0.04)
                        cbar.set_label("Wind speed (m/s)")

                        if times_dt is not None and len(times_dt) > idx:
                            ts_label = times_dt[idx].strftime("%Y%m%d_%H%M%S")
                            title_time = times_dt[idx].strftime("%Y-%m-%d %H:%M")
                        else:
                            ts_label = f"idx{idx:03d}"
                            title_time = f"Index {idx}"

                        ax.set_title(f"10m Wind Field ({title_time})")
                        # 调整布局，确保只显示数据范围
                        fig.subplots_adjust(left=0, right=1, top=0.95, bottom=0)
                        # 使用 tight_layout 和 bbox_inches='tight' 来裁剪图片，只保留数据范围内的内容
                        fig.tight_layout(pad=0.1)
                        
                        # 使用 bbox_inches='tight' 裁剪图片，只保留数据范围内的内容
                        out_path = os.path.join(output_dir, f"wind_{ts_label}.png")
                        fig.savefig(out_path, dpi=250, bbox_inches='tight', pad_inches=0.05, facecolor='white', edgecolor='none')
                        saved_paths.append(out_path)
                        plt.close(fig)

                    if saved_paths:
                        self.log_signal.emit(tr("plotting_wind_field_generated", "✅ 已生成 {count} 张风场图，保存在 {path}").format(count=len(saved_paths), path=output_dir))
                        last_path = saved_paths[-1]
                        QtCore.QTimer.singleShot(0, lambda path=last_path: self.open_image_file(path))
                    else:
                        self.log_signal.emit(tr("wind_no_images_generated", "⚠️ 未生成风场图，检查数据是否为空"))
            except Exception as e:
                self.log_signal.emit(tr("wind_generation_failed", "❌ 生成风场图失败: {error}").format(error=e))
            finally:
                # 恢复原来的后端（如果需要）
                try:
                    matplotlib.use(original_backend)
                except:
                    pass
                QtCore.QTimer.singleShot(0, self._restore_wind_field_button)

        threading.Thread(target=_worker, daemon=True).start()

    def view_wind_field_images(self):
        """查看已生成的风场图（在右侧抽屉中显示）"""
        if not self.selected_folder:
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return
        photo_dir = os.path.join(self.selected_folder, "photo", "field")
        if not os.path.exists(photo_dir):
            self.log(tr("wind_field_dir_not_found", "❌ 未找到风场图目录，请先生成风场图"))
            return
        images = sorted(glob.glob(os.path.join(photo_dir, "*.png")))
        if not images:
            self.log(tr("wind_no_images_in_dir", "❌ 目录中没有风场图，请先生成"))
            return

        # 在抽屉中显示图片
        if hasattr(self, '_show_images_in_drawer'):
            self._show_images_in_drawer(images)
        else:
            self.log(tr("drawer_not_initialized", "❌ 抽屉功能未初始化"))
