"""
二维谱服务模块
包含站点读取、站点地图显示、图片查看等逻辑
"""
import os
import glob
import re
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.collections import LineCollection
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from netCDF4 import Dataset
from PyQt6 import QtCore
from PyQt6.QtWidgets import QTableWidgetItem, QFileDialog, QWidget, QSizePolicy, QHBoxLayout
from qfluentwidgets import InfoBar
from setting.language_manager import tr
from home.step3.step3_service import _PointSelectMapDialog


def _matplotlib_sans_priority_for_chinese_maps(app_self=None):
    """供地图类 Figure 使用：优先可显示中文的 sans-serif，避免仅依赖 Qt 字体名与 matplotlib 不一致。"""
    import platform
    from matplotlib import font_manager

    available = {f.name for f in font_manager.fontManager.ttflist}

    system = platform.system()
    if system == "Windows":
        cjk_candidates = [
            "Microsoft YaHei",
            "Microsoft YaHei UI",
            "SimHei",
            "SimSun",
            "KaiTi",
            "FangSong",
        ]
    elif system == "Darwin":
        cjk_candidates = [
            "PingFang SC",
            "PingFang TC",
            "Hiragino Sans GB",
            "STSong",
            "STHeiti",
            "Heiti SC",
            "Songti SC",
            "Arial Unicode MS",
        ]
    else:
        cjk_candidates = [
            "Noto Sans CJK SC",
            "Noto Sans CJK JP",
            "Source Han Sans SC",
            "WenQuanYi Micro Hei",
            "WenQuanYi Zen Hei",
            "Noto Sans CJK HK",
            "Droid Sans Fallback",
        ]

    picks = [name for name in cjk_candidates if name in available]

    picker = getattr(app_self, "_pick_ui_font_for_matplotlib", None) if app_self is not None else None
    if callable(picker):
        ui_font = picker()
        if ui_font and ui_font not in picks:
            picks.append(ui_font)

    if "DejaVu Sans" not in picks:
        picks.append("DejaVu Sans")

    return picks


class SpectrumServiceMixin:
    """二维谱服务功能模块"""

    def choose_spectrum_file(self):
        """选择二维谱文件（只选择，不转换）"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("plotting_choose_spectrum", "选择二维谱文件"),
            os.getcwd() if not hasattr(self, 'selected_folder') or not self.selected_folder else self.selected_folder,
            tr("plotting_file_filter_nc", "NetCDF 文件 (*.nc);;所有文件 (*.*)")
        )

        if not file_path:
            return

        # 保存文件路径（规范化路径，在 Windows 上使用 \）
        self.selected_spectrum_file = os.path.normpath(file_path)
        normalized_file_path = os.path.normpath(file_path)
        self.log(tr("plotting_spectrum_file_selected", "📂 已选择二维谱文件: {path}").format(path=normalized_file_path))

        # 更新按钮文本为文件名
        file_name = os.path.basename(normalized_file_path)
        # 如果文件名太长，截断并显示省略号
        if len(file_name) > 30:
            file_name = file_name[:27] + "..."
        
        # 更新科研绘图页面的按钮
        if hasattr(self, 'btn_choose_spectrum_file'):
            self.btn_choose_spectrum_file.setText(file_name)
            if hasattr(self, '_set_plot_button_filled'):
                self._set_plot_button_filled(self.btn_choose_spectrum_file, True)
        
        # 读取站点信息
        self._load_spectrum_stations(normalized_file_path)
        
        # 显示点列表表格
        if hasattr(self, 'spectrum_stations_table'):
            self.spectrum_stations_table.setVisible(True)

    def _load_spectrum_stations(self, spec_file_path):
        """从二维谱文件中读取站点信息并填充到表格"""
        if not hasattr(self, 'spectrum_stations_table'):
            return

        if not spec_file_path or not os.path.exists(spec_file_path):
            return

        try:
            with Dataset(spec_file_path, 'r') as ds:
                if 'longitude' in ds.variables and 'latitude' in ds.variables:
                    lon_var = ds.variables['longitude']
                    lat_var = ds.variables['latitude']
                    name_var = ds.variables['station_name'] if 'station_name' in ds.variables else None

                    if 'station' in ds.dimensions:
                        n_stations = len(ds.dimensions['station'])
                    else:
                        n_stations = len(lon_var) if hasattr(lon_var, '__len__') else 1

                    lon_dims = getattr(lon_var, 'dimensions', ())
                    lat_dims = getattr(lat_var, 'dimensions', ())

                    if 'station' in lon_dims and lon_var.ndim > 1:
                        station_axis = lon_dims.index('station')
                        lon_index = [0] * lon_var.ndim
                        lon_index[station_axis] = slice(None)
                        lon = lon_var[tuple(lon_index)]
                    else:
                        lon = lon_var[:]

                    if 'station' in lat_dims and lat_var.ndim > 1:
                        station_axis = lat_dims.index('station')
                        lat_index = [0] * lat_var.ndim
                        lat_index[station_axis] = slice(None)
                        lat = lat_var[tuple(lat_index)]
                    else:
                        lat = lat_var[:]

                    if hasattr(lon, 'data'):
                        lon = lon.data
                    if hasattr(lat, 'data'):
                        lat = lat.data

                    if not hasattr(lon, '__len__'):
                        lon = [lon]
                        lat = [lat]
                    elif len(getattr(lon, 'shape', ())) == 0:
                        lon = [float(lon)]
                        lat = [float(lat)]
                    elif getattr(lon, 'ndim', 1) > 1:
                        lon = np.array(lon).reshape(-1)
                        lat = np.array(lat).reshape(-1)
                    else:
                        lon = np.array(lon)
                        lat = np.array(lat)

                    station_names = None
                    if name_var is not None:
                        try:
                            raw_names = np.array(name_var[:])
                            station_names = []
                            for row in raw_names[:n_stations]:
                                name = b"".join(row.tolist()).decode("utf-8", "ignore").strip()
                                station_names.append(name.replace("\x00", "").strip())
                        except Exception:
                            station_names = None

                    while self.spectrum_stations_table.rowCount() > 1:
                        self.spectrum_stations_table.removeRow(1)

                    for i in range(min(n_stations, len(lon), len(lat))):
                        row = self.spectrum_stations_table.rowCount()
                        self.spectrum_stations_table.insertRow(row)

                        lon_item = QTableWidgetItem(f"{float(lon[i]):.6f}")
                        lon_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                        lat_item = QTableWidgetItem(f"{float(lat[i]):.6f}")
                        lat_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)
                        station_name = ""
                        if station_names and i < len(station_names):
                            station_name = station_names[i]
                        if not station_name:
                            station_name = f"{i}"
                        name_item = QTableWidgetItem(station_name)
                        name_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)

                        self.spectrum_stations_table.setItem(row, 0, lon_item)
                        self.spectrum_stations_table.setItem(row, 1, lat_item)
                        self.spectrum_stations_table.setItem(row, 2, name_item)

                    self.spectrum_stations_table.resizeRowsToContents()
                    total_height = 0
                    for i in range(self.spectrum_stations_table.rowCount()):
                        total_height += self.spectrum_stations_table.rowHeight(i)
                    content_height = max(200, total_height + 20)
                    self.spectrum_stations_table.setMinimumHeight(content_height)
                    self.spectrum_stations_table.setMaximumHeight(16777215)

                    self.spectrum_stations_table.setVisible(True)
        except Exception:
            pass

    def show_spectrum_stations_on_map(self):
        """显示二维谱站点在地图上的位置（只显示；与第三步主页谱点地图风格一致，无选点交互按钮栏）"""
        try:
            plt.rcParams["font.sans-serif"] = _matplotlib_sans_priority_for_chinese_maps(self)
            plt.rcParams["axes.unicode_minus"] = False
            import warnings

            warnings.filterwarnings("ignore", category=UserWarning, module="cartopy")
        except Exception:
            import warnings

            warnings.filterwarnings("ignore", category=UserWarning, module="cartopy")

        if not hasattr(self, 'spectrum_stations_table'):
            InfoBar.warning(
                title=tr("plotting_display_failed", "显示失败"),
                content=tr("plotting_table_not_exists", "表格不存在"),
                duration=3000,
                parent=self
            )
            return

        points = []
        for i in range(1, self.spectrum_stations_table.rowCount()):
            lon_item = self.spectrum_stations_table.item(i, 0)
            lat_item = self.spectrum_stations_table.item(i, 1)
            name_item = self.spectrum_stations_table.item(i, 2)

            if lon_item and lat_item:
                try:
                    lon = float(lon_item.text().strip())
                    lat = float(lat_item.text().strip())
                    name = name_item.text().strip() if name_item else f"{i}"
                    if name.upper() == "STOPSTRING":
                        continue
                    points.append({'lon': lon, 'lat': lat, 'name': name})
                except ValueError:
                    continue

        if not points:
            InfoBar.warning(
                title=tr("plotting_display_failed", "显示失败"),
                content=tr("plotting_no_station_data", "没有可显示的站点数据"),
                duration=3000,
                parent=self
            )
            return

        spectrum_file_path = None
        if hasattr(self, 'selected_spectrum_file') and self.selected_spectrum_file and os.path.exists(self.selected_spectrum_file):
            spectrum_file_path = self.selected_spectrum_file
        elif hasattr(self, 'selected_folder') and self.selected_folder:
            spec_files = glob.glob(os.path.join(self.selected_folder, "ww3*spec*nc"))
            if spec_files:
                spectrum_file_path = spec_files[0]
                if not hasattr(self, 'selected_spectrum_file') or not self.selected_spectrum_file:
                    self.selected_spectrum_file = spectrum_file_path

        if not spectrum_file_path or not os.path.exists(spectrum_file_path):
            InfoBar.error(
                title=tr("plotting_display_failed", "显示失败"),
                content=tr("plotting_spectrum_file_not_selected", "未找到二维谱文件。请先选择二维谱文件。"),
                duration=5000,
                parent=self
            )
            return

        spectrum_bounds = None
        try:
            with Dataset(spectrum_file_path, 'r') as ds:
                if 'longitude' not in ds.variables or 'latitude' not in ds.variables:
                    InfoBar.error(
                        title=tr("plotting_read_failed", "读取失败"),
                        content=tr("plotting_spectrum_missing_coords", "二维谱文件中缺少 longitude 或 latitude 变量。"),
                        duration=5000,
                        parent=self
                    )
                    return

                file_lons_full = ds.variables['longitude'][:]
                file_lats_full = ds.variables['latitude'][:]

                if hasattr(file_lons_full, 'data'):
                    file_lons = np.array(file_lons_full.data)
                    file_lats = np.array(file_lats_full.data)
                else:
                    file_lons = np.array(file_lons_full)
                    file_lats = np.array(file_lats_full)

                if file_lons.size == 1:
                    file_lons = np.array([float(file_lons.flat[0])])
                    file_lats = np.array([float(file_lats.flat[0])])
                else:
                    file_lons = file_lons.flatten()
                    file_lats = file_lats.flatten()

                min_len = min(len(file_lons), len(file_lats))
                if min_len == 0:
                    InfoBar.error(
                        title=tr("plotting_read_failed", "读取失败"),
                        content=tr("plotting_spectrum_no_valid_coords", "二维谱文件中没有有效的经纬度数据。"),
                        duration=5000,
                        parent=self
                    )
                    return

                file_lons = file_lons[:min_len]
                file_lats = file_lats[:min_len]
                file_lons = np.where(file_lons > 180, file_lons - 360, file_lons)

                file_lon_min = float(np.min(file_lons))
                file_lon_max = float(np.max(file_lons))
                file_lat_min = float(np.min(file_lats))
                file_lat_max = float(np.max(file_lats))

                spectrum_bounds = (file_lon_min, file_lon_max, file_lat_min, file_lat_max)
        except Exception:
            InfoBar.error(
                title=tr("plotting_read_failed", "读取失败"),
                content=tr("plotting_spectrum_read_range_failed", "读取二维谱文件范围失败。"),
                duration=5000,
                parent=self
            )
            return

        if not spectrum_bounds:
            InfoBar.error(
                title=tr("plotting_read_failed", "读取失败"),
                content=tr("plotting_spectrum_get_range_failed", "无法获取二维谱文件的范围。"),
                duration=5000,
                parent=self
            )
            return

        sp_lon_min, sp_lon_max, sp_lat_min, sp_lat_max = spectrum_bounds
        lons_pts = [p['lon'] for p in points]
        lats_pts = [p['lat'] for p in points]

        bounds_dict = self._read_grid_meta_bounds() if hasattr(self, "_read_grid_meta_bounds") else None
        unst_show_ctx = None
        if hasattr(self, "_needs_unstructured_triangulation_check") and self._needs_unstructured_triangulation_check():
            unst_show_ctx = (
                self._load_unstructured_ww3_pick_context()
                if hasattr(self, "_load_unstructured_ww3_pick_context")
                else None
            )

        if bounds_dict:
            lon_min_m = min(min(lons_pts), bounds_dict["lon_min"], sp_lon_min)
            lon_max_m = max(max(lons_pts), bounds_dict["lon_max"], sp_lon_max)
            lat_min_m = min(min(lats_pts), bounds_dict["lat_min"], sp_lat_min)
            lat_max_m = max(max(lats_pts), bounds_dict["lat_max"], sp_lat_max)
        else:
            lon_min_m = min(min(lons_pts), sp_lon_min)
            lon_max_m = max(max(lons_pts), sp_lon_max)
            lat_min_m = min(min(lats_pts), sp_lat_min)
            lat_max_m = max(max(lats_pts), sp_lat_max)

        lon_range_m = lon_max_m - lon_min_m
        lat_range_m = lat_max_m - lat_min_m
        margin_lon = max(lon_range_m * 0.1, 2.0)
        margin_lat = max(lat_range_m * 0.1, 2.0)
        display_lon_min = lon_min_m - margin_lon
        display_lon_max = lon_max_m + margin_lon
        display_lat_min = lat_min_m - margin_lat
        display_lat_max = lat_max_m + margin_lat

        ref_lon_max_for_wrap = lon_max_m
        # 判断投影方式（与第三步主页谱点预览一致）
        if display_lon_min < 0 or display_lon_max < 0:
            proj = ccrs.Mercator(central_longitude=180)
        else:
            proj = ccrs.Mercator(central_longitude=0)
            if display_lon_max > 180:
                mwrap = display_lon_max - ref_lon_max_for_wrap
                display_lon_max = min(180.0 + mwrap, 185.0)
            elif ref_lon_max_for_wrap >= 179:
                mwrap = display_lon_max - ref_lon_max_for_wrap
                display_lon_max = min(180.0, ref_lon_max_for_wrap + mwrap)

        fig = Figure(figsize=(12, 10), dpi=100)
        ax = fig.add_subplot(1, 1, 1, projection=proj)
        ax.set_extent([display_lon_min, display_lon_max, display_lat_min, display_lat_max], crs=ccrs.PlateCarree())

        ax.add_feature(cfeature.OCEAN, facecolor="#a4d6ff")
        ax.add_feature(cfeature.LAND, facecolor="#f0f0f0")
        ax.coastlines(resolution="10m", linewidth=0.6)

        if unst_show_ctx is not None:
            from home.step2.grid_viz_worker import unst_wireframe_segments

            segs, _ = unst_wireframe_segments(
                unst_show_ctx["xy"],
                unst_show_ctx["ect"],
                unst_show_ctx["tri_mask"],
                80000,
            )
            if segs.size:
                lc = LineCollection(
                    segs,
                    colors="steelblue",
                    linewidths=0.5,
                    alpha=0.9,
                    transform=ccrs.PlateCarree(),
                    label=tr("step3_unstructured_mesh_outline", "非结构网格"),
                )
                ax.add_collection(lc)
        elif bounds_dict:
            bounds_lon = [
                bounds_dict["lon_min"],
                bounds_dict["lon_max"],
                bounds_dict["lon_max"],
                bounds_dict["lon_min"],
                bounds_dict["lon_min"],
            ]
            bounds_lat = [
                bounds_dict["lat_min"],
                bounds_dict["lat_min"],
                bounds_dict["lat_max"],
                bounds_dict["lat_max"],
                bounds_dict["lat_min"],
            ]
            ax.plot(
                bounds_lon,
                bounds_lat,
                transform=ccrs.PlateCarree(),
                color="blue",
                linewidth=2,
                linestyle="--",
                label=tr("step3_map_range_label", "地图范围"),
            )

        for i, point in enumerate(points):
            ax.plot(
                point["lon"],
                point["lat"],
                "ro",
                markersize=10,
                transform=ccrs.PlateCarree(),
                label=tr("step3_point_label", "点位") if i == 0 else "",
            )
            ax.text(
                point["lon"],
                point["lat"],
                f"  {point['name']}",
                transform=ccrs.PlateCarree(),
                fontsize=9,
                bbox=dict(boxstyle="round,pad=0.3", facecolor="yellow", alpha=0.7),
            )

        if points:
            ax.legend(loc="upper right")

        gl = ax.gridlines(
            crs=ccrs.PlateCarree(),
            draw_labels=True,
            linewidth=0.5,
            color="gray",
            alpha=0.5,
            linestyle="--",
        )
        gl.top_labels = False
        gl.right_labels = False

        title_base = tr("plotting_spectrum_stations_distribution", "二维谱站点分布")
        ax.set_title(f'{title_base}（共{len(points)}个点位）', fontsize=14, fontweight="bold")

        fig.subplots_adjust(left=0.01, right=0.995, top=0.955, bottom=0.05)

        dialog = _PointSelectMapDialog(self, content_aspect_wh=1.2)
        content_widget = QWidget()
        main_layout = QHBoxLayout(content_widget)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(0)
        canvas = FigureCanvas(fig)
        canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout.addWidget(canvas, 1)
        dialog.set_main_widget(content_widget)
        dialog.exec()

    def view_spectrum_images(self):
        """查看已生成的二维谱图（在右侧抽屉中显示）"""
        if not self.selected_folder:
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return
        photo_dir = os.path.join(self.selected_folder, "photo", "spectrum")
        if not os.path.exists(photo_dir):
            self.log(tr("plotting_spectrum_dir_not_found", "❌ 未找到二维谱图目录，请先生成二维谱图"))
            return

        all_images = sorted(glob.glob(os.path.join(photo_dir, "*.png")))
        if not all_images:
            self.log(tr("plotting_no_spectrum_images", "❌ 目录中没有二维谱图，请先生成"))
            return

        selected_station_name = None
        if hasattr(self, 'spectrum_stations_table'):
            selected_items = self.spectrum_stations_table.selectedItems()
            if selected_items:
                selected_row = selected_items[0].row()
                if selected_row > 0:
                    name_item = self.spectrum_stations_table.item(selected_row, 2)
                    if name_item:
                        selected_station_name = name_item.text().strip()

        images = all_images
        if selected_station_name:
            sanitized_name = selected_station_name.replace(" ", "_")
            sanitized_name = re.sub(r'[<>:"/\\|?*]', '', sanitized_name)
            sanitized_name = sanitized_name.strip('_')
            if not sanitized_name:
                sanitized_name = str(selected_row - 1)

            filtered_images = []
            for img in all_images:
                img_name = os.path.basename(img)
                if f'spectrum_{sanitized_name}_time_' in img_name:
                    filtered_images.append(img)
                elif f'spectrum_station_{selected_row:03d}_time_' in img_name:
                    filtered_images.append(img)

            if filtered_images:
                images = filtered_images

        if hasattr(self, '_show_images_in_drawer'):
            self._show_images_in_drawer(images)
        else:
            self.log(tr("drawer_not_initialized", "❌ 抽屉功能未初始化"))
