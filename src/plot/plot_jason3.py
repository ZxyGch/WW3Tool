"""
Jason-3 卫星观测数据模块
包含 Jason-3 卫星观测数据的 UI 创建和逻辑
"""

import os
import sys
import glob
import re
import platform
import subprocess
from multiprocessing import Process, Queue
from datetime import datetime
import numpy as np
import matplotlib
matplotlib.use('QtAgg')
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from netCDF4 import Dataset, num2date
from PIL import Image

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import QEvent, Qt
from qfluentwidgets import (
    PrimaryPushButton, LineEdit, HeaderCardWidget, InfoBar
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFileDialog, QDialog, QScrollArea, QSizePolicy
)
from PyQt6.QtGui import QPixmap

from setting.config import load_config, JASON_PATH, ensure_project_data_dir
from setting.language_manager import tr
from .workers import _run_jason3_swh_worker, _match_ww3_jason3_worker
from .workers_jason3 import JASON3_MAX_REASONABLE_SWH


class Jason3PlotMixin:
    """Jason-3 卫星观测数据功能 Mixin"""

    def _ensure_jason_folder_path(self):
        path = ensure_project_data_dir("JASON_PATH", "jason3")
        if hasattr(self, "jason_folder_edit") and self.jason_folder_edit:
            self.jason_folder_edit.setText(path)
        return path
    
    def _create_jason3_ui(self, plot_content_widget, plot_content_layout, button_style, input_style):
        """创建 Jason-3 卫星观测数据 UI"""
        # 第八步：卫星观测数据
        step9_card = HeaderCardWidget(plot_content_widget)
        step9_card.setTitle(tr("plotting_satellite_data", "JASON 3 拟合"))
        step9_card.setStyleSheet("""
            HeaderCardWidget QLabel {
                font-weight: normal;
                margin-left: 0px;
                padding-left: 0px;
            }
        """)
        step9_card.headerLayout.setContentsMargins(11, 10, 11, 12)
        step9_card_layout = QVBoxLayout()
        step9_card_layout.setSpacing(10)
        step9_card_layout.setContentsMargins(0, 0, 0, 0)

        # 从配置文件加载默认值
        current_config = load_config()
        LONGITUDE_WEST = current_config.get("LONGITUDE_WEST", "")
        LONGITUDE_EAST = current_config.get("LONGITUDE_EAST", "")
        LATITUDE_SORTH = current_config.get("LATITUDE_SORTH", "")
        LATITUDE_NORTH = current_config.get("LATITUDE_NORTH", "")
        JASON_PATH = ensure_project_data_dir("JASON_PATH", "jason3")

        # 经纬度输入区域
        geo_frame = QWidget()
        geo_layout = QGridLayout(geo_frame)
        geo_layout.setSpacing(10)
        geo_layout.setContentsMargins(0, 0, 0, 0)

        # 保存已存在的输入框的值（如果存在）
        saved_values = {}
        if hasattr(self, 'lon_west_step9_edit') and self.lon_west_step9_edit is not None:
            saved_values['lon_west'] = self.lon_west_step9_edit.text()
        if hasattr(self, 'lon_east_step9_edit') and self.lon_east_step9_edit is not None:
            saved_values['lon_east'] = self.lon_east_step9_edit.text()
        if hasattr(self, 'lat_south_step9_edit') and self.lat_south_step9_edit is not None:
            saved_values['lat_south'] = self.lat_south_step9_edit.text()
        if hasattr(self, 'lat_north_step9_edit') and self.lat_north_step9_edit is not None:
            saved_values['lat_north'] = self.lat_north_step9_edit.text()

        # 如果输入框已存在且有父窗口，先从旧布局中移除
        for attr_name in ['lon_west_step9_edit', 'lon_east_step9_edit', 'lat_south_step9_edit', 'lat_north_step9_edit']:
            if hasattr(self, attr_name):
                widget = getattr(self, attr_name)
                if widget is not None and widget.parent() is not None:
                    old_parent = widget.parent()
                    if old_parent != geo_frame:
                        old_layout = old_parent.layout()
                        if old_layout:
                            old_layout.removeWidget(widget)

        # 创建或获取输入框
        # 西经
        lon_west_label = QLabel(tr("step2_lon_west", "西经:"))
        geo_layout.addWidget(lon_west_label, 0, 0)
        if not hasattr(self, 'lon_west_step9_edit') or self.lon_west_step9_edit is None:
            self.lon_west_step9_edit = LineEdit()
        self.lon_west_step9_edit.setStyleSheet(input_style)
        # 如果有保存的值，使用保存的值；否则使用默认值
        if 'lon_west' in saved_values:
            self.lon_west_step9_edit.setText(saved_values['lon_west'])
        else:
            self.lon_west_step9_edit.setText(LONGITUDE_WEST if LONGITUDE_WEST else "")
        geo_layout.addWidget(self.lon_west_step9_edit, 0, 1)

        # 东经
        lon_east_label = QLabel(tr("step2_lon_east", "东经:"))
        geo_layout.addWidget(lon_east_label, 0, 2)
        if not hasattr(self, 'lon_east_step9_edit') or self.lon_east_step9_edit is None:
            self.lon_east_step9_edit = LineEdit()
        self.lon_east_step9_edit.setStyleSheet(input_style)
        if 'lon_east' in saved_values:
            self.lon_east_step9_edit.setText(saved_values['lon_east'])
        else:
            self.lon_east_step9_edit.setText(LONGITUDE_EAST if LONGITUDE_EAST else "")
        geo_layout.addWidget(self.lon_east_step9_edit, 0, 3)

        # 南纬
        lat_south_label = QLabel(tr("step2_lat_south", "南纬:"))
        geo_layout.addWidget(lat_south_label, 1, 0)
        if not hasattr(self, 'lat_south_step9_edit') or self.lat_south_step9_edit is None:
            self.lat_south_step9_edit = LineEdit()
        self.lat_south_step9_edit.setStyleSheet(input_style)
        if 'lat_south' in saved_values:
            self.lat_south_step9_edit.setText(saved_values['lat_south'])
        else:
            self.lat_south_step9_edit.setText(LATITUDE_SORTH if LATITUDE_SORTH else "")
        geo_layout.addWidget(self.lat_south_step9_edit, 1, 1)

        # 北纬
        lat_north_label = QLabel(tr("step2_lat_north", "北纬:"))
        geo_layout.addWidget(lat_north_label, 1, 2)
        if not hasattr(self, 'lat_north_step9_edit') or self.lat_north_step9_edit is None:
            self.lat_north_step9_edit = LineEdit()
        self.lat_north_step9_edit.setStyleSheet(input_style)
        if 'lat_north' in saved_values:
            self.lat_north_step9_edit.setText(saved_values['lat_north'])
        else:
            self.lat_north_step9_edit.setText(LATITUDE_NORTH if LATITUDE_NORTH else "")
        geo_layout.addWidget(self.lat_north_step9_edit, 1, 3)

        # 开始时间（添加到同一布局的第2行，与经纬度对齐）
        start_label = QLabel(tr("plotting_start", "开始:"))
        geo_layout.addWidget(start_label, 2, 0)
        if not hasattr(self, 'shel_start_step9_edit'):
            self.shel_start_step9_edit = LineEdit()
            self.shel_start_step9_edit.setPlaceholderText("20250101")
        self.shel_start_step9_edit.setStyleSheet(input_style)
        # 如果输入框已有父窗口且不是当前布局，先移除
        if self.shel_start_step9_edit.parent() is not None and self.shel_start_step9_edit.parent() != geo_frame:
            old_parent = self.shel_start_step9_edit.parent()
            old_layout = old_parent.layout()
            if old_layout:
                old_layout.removeWidget(self.shel_start_step9_edit)
        geo_layout.addWidget(self.shel_start_step9_edit, 2, 1)

        # 结束时间
        end_label = QLabel(tr("plotting_end", "结束:"))
        geo_layout.addWidget(end_label, 2, 2)
        if not hasattr(self, 'shel_end_step9_edit'):
            self.shel_end_step9_edit = LineEdit()
            self.shel_end_step9_edit.setPlaceholderText("20250101")
        self.shel_end_step9_edit.setStyleSheet(input_style)
        # 如果输入框已有父窗口且不是当前布局，先移除
        if self.shel_end_step9_edit.parent() is not None and self.shel_end_step9_edit.parent() != geo_frame:
            old_parent = self.shel_end_step9_edit.parent()
            old_layout = old_parent.layout()
            if old_layout:
                old_layout.removeWidget(self.shel_end_step9_edit)
        geo_layout.addWidget(self.shel_end_step9_edit, 2, 3)

        # 设置列宽比例
        geo_layout.setColumnStretch(1, 1)
        geo_layout.setColumnStretch(3, 1)

        step9_card_layout.addWidget(geo_frame)

        # 文件夹选择区域
        folder_frame = QWidget()
        folder_layout = QGridLayout(folder_frame)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(10)
        folder_layout.setColumnStretch(1, 1)

        if not hasattr(self, 'jason_folder_edit'):
            self.jason_folder_edit = LineEdit()
            self.jason_folder_edit.setText(JASON_PATH)
        elif not self.jason_folder_edit.text().strip() or not os.path.isdir(self.jason_folder_edit.text().strip()):
            self.jason_folder_edit.setText(JASON_PATH)
        self.jason_folder_edit.setStyleSheet(input_style)
        folder_layout.addWidget(self.jason_folder_edit, 0, 1)

        choose_folder_button = PrimaryPushButton(tr("plotting_jason3_select", "JASON 3 选择"))
        choose_folder_button.setStyleSheet(button_style)
        choose_folder_button.clicked.connect(self.choose_jason_folder)
        folder_layout.addWidget(choose_folder_button, 0, 2)

        folder_layout.setSpacing(5)
        step9_card_layout.addWidget(folder_frame)

        # 选择文件按钮（与绘图页按钮逻辑一致）
        if not hasattr(self, 'btn_choose_jason3_wind_file'):
            self.btn_choose_jason3_wind_file = PrimaryPushButton(tr("step1_choose_wind", "选择风场文件"))
            self.btn_choose_jason3_wind_file.setStyleSheet(button_style)
            self.btn_choose_jason3_wind_file.clicked.connect(self._choose_jason3_wind_file)
        if not hasattr(self, 'btn_choose_jason3_wave_file'):
            self.btn_choose_jason3_wave_file = PrimaryPushButton(tr("plotting_choose_wave_height", "选择波高文件"))
            self.btn_choose_jason3_wave_file.setStyleSheet(button_style)
            self.btn_choose_jason3_wave_file.clicked.connect(self._choose_jason3_wave_file)

        # 读取范围按钮
        load_from_data_button = PrimaryPushButton(tr("step2_load_from_nc", "从 wind.nc 读取范围"))
        load_from_data_button.setStyleSheet(button_style)
        load_from_data_button.clicked.connect(lambda: self.load_latlon_from_nc_step9("wind.nc"))

        load_from_ww3_button = PrimaryPushButton(tr("step2_load_from_ww3", "从模拟结果读取范围"))
        load_from_ww3_button.setStyleSheet(button_style)
        load_from_ww3_button.clicked.connect(lambda: self.load_latlon_from_nc_step9("ww3.*.nc"))

        # 同行布局：风场文件 + 从 wind.nc 读取范围
        for btn in (self.btn_choose_jason3_wind_file, load_from_data_button):
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
           
        wind_button_row = QHBoxLayout()
        wind_button_row.setSpacing(10)
        wind_button_row.addWidget(self.btn_choose_jason3_wind_file, 1)
        wind_button_row.addWidget(load_from_data_button, 1)
        step9_card_layout.addLayout(wind_button_row)

        # 同行布局：波高文件 + 从模拟结果读取范围
        for btn in (self.btn_choose_jason3_wave_file, load_from_ww3_button):
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
           
        wave_button_row = QHBoxLayout()
        wave_button_row.setSpacing(10)
        wave_button_row.addWidget(self.btn_choose_jason3_wave_file, 1)
        wave_button_row.addWidget(load_from_ww3_button, 1)
        step9_card_layout.addLayout(wave_button_row)

        if not hasattr(self, 'btn_download_jason3'):
            self.btn_download_jason3 = PrimaryPushButton(tr("plotting_download_jason3", "下载 JASON 3 数据"))
            self.btn_download_jason3.setStyleSheet(button_style)
            self.btn_download_jason3.clicked.connect(self.download_jason3_range)
        step9_card_layout.addWidget(self.btn_download_jason3)

        # 查看卫星观测图按钮
        if not hasattr(self, 'btn_view_satellite'):
            self.btn_view_satellite = PrimaryPushButton(tr("plotting_view_satellite", "查看卫星观测图"))
            self.btn_view_satellite.setStyleSheet(button_style)
            self.btn_view_satellite.clicked.connect(self.run_jason3_swh)
        step9_card_layout.addWidget(self.btn_view_satellite)

        # 查看拟合图按钮
        if not hasattr(self, 'btn_view_fit'):
            self.btn_view_fit = PrimaryPushButton(tr("plotting_view_fit", "查看拟合图"))
            self.btn_view_fit.setStyleSheet(button_style)
            self.btn_view_fit.clicked.connect(self.view_matching_fit)
        step9_card_layout.addWidget(self.btn_view_fit)

        # 设置内容区内边距
        step9_card.viewLayout.setContentsMargins(11, 10, 11, 12)
        step9_card.viewLayout.addLayout(step9_card_layout)
        plot_content_layout.addWidget(step9_card)

    def choose_jason_folder(self):
        """选择 Jason-3 数据文件夹"""
        start_path = self.jason_folder_edit.text().strip() if hasattr(self, 'jason_folder_edit') else JASON_PATH
        if not os.path.exists(start_path):
            start_path = self._ensure_jason_folder_path()

        folder = QFileDialog.getExistingDirectory(
            self,
            tr("plotting_choose_jason_folder", "选择 Jason-3 数据文件夹"),
            start_path,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
        )

        if folder:
            self.jason_folder_edit.setText(folder)
            self.log(tr("plotting_jason_folder_selected", "✅ 已选择 Jason-3 数据文件夹：{folder}").format(folder=folder))

    def _choose_jason3_wind_file(self):
        """选择风场文件（仅打开文件选择对话框，不进行自动检测）
        
        注意：自动检测逻辑仅在切换到科研绘图界面时执行（show_plot_page 中），
        不在文件选择弹窗时执行。
        """
        if hasattr(self, 'choose_wind_field_file_plot'):
            self.choose_wind_field_file_plot()
        if hasattr(self, 'selected_origin_file') and self.selected_origin_file and hasattr(self, 'btn_choose_jason3_wind_file'):
            file_name = os.path.basename(self.selected_origin_file)
            display_name = file_name[:27] + "..." if len(file_name) > 30 else file_name
            self.btn_choose_jason3_wind_file.setText(display_name)
            if hasattr(self, '_set_plot_button_filled'):
                self._set_plot_button_filled(self.btn_choose_jason3_wind_file, True)

    def _choose_jason3_wave_file(self):
        """选择波高文件（仅打开文件选择对话框，不进行自动检测）
        
        注意：自动检测逻辑仅在切换到科研绘图界面时执行（show_plot_page 中），
        不在文件选择弹窗时执行。
        """
        if hasattr(self, 'choose_wave_height_file'):
            self.choose_wave_height_file()
        if hasattr(self, 'selected_wave_height_file') and self.selected_wave_height_file and hasattr(self, 'btn_choose_jason3_wave_file'):
            file_name = os.path.basename(self.selected_wave_height_file)
            display_name = file_name[:27] + "..." if len(file_name) > 30 else file_name
            self.btn_choose_jason3_wave_file.setText(display_name)
            if hasattr(self, '_set_plot_button_filled'):
                self._set_plot_button_filled(self.btn_choose_jason3_wave_file, True)

    def load_latlon_from_nc_step9(self, file_name="wind.nc"):
        """读取 NC 文件并填入第九步的经纬度输入框，支持通配符"""
        # 检查 file_name 参数类型
        if not isinstance(file_name, str):
            file_name = "wind.nc"

        if not self.selected_folder:
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return

        # 检查是否是嵌套网格模式，且要读取的是 ww3.*.nc 文件
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == tr("step2_grid_type_nested", "嵌套网格"))
        is_ww3_file = ("ww3" in file_name.lower() or "*" in file_name)

        # 确定数据源文件夹
        if is_nested_grid and is_ww3_file:
            # 嵌套模式：从 fine 文件夹读取 ww3.*.nc 文件
            fine_dir = os.path.join(self.selected_folder, "fine")
            if not os.path.isdir(fine_dir):
                self.log(tr("plotting_fine_folder_not_found", "❌ 未找到 fine 文件夹，请先生成嵌套网格"))
                return
            data_folder = fine_dir
        else:
            # 普通模式或读取 wind.nc：从工作目录读取
            data_folder = self.selected_folder

        # 拼接完整路径
        pattern = os.path.join(data_folder, file_name)

        # 支持通配符查找
        nc_files = glob.glob(pattern)
        if not nc_files:
            self.log(tr("plotting_file_not_found_in_folder", "❌ 未找到匹配的文件：{file}（在 {folder} 中）").format(file=file_name, folder=data_folder))
            return

        data_nc_path = nc_files[0]  # 取第一个匹配文件
        try:
            ds = Dataset(data_nc_path)
            lon = ds.variables['longitude'][:]
            lat = ds.variables['latitude'][:]
            ds.close()

            # 检查输入框是否存在
            if not hasattr(self, 'lon_west_step9_edit') or self.lon_west_step9_edit is None:
                self.log(tr("plotting_inputs_not_created", "❌ 输入框尚未创建，请先打开科研绘图页面"))
                return
            if not hasattr(self, 'lon_east_step9_edit') or self.lon_east_step9_edit is None:
                self.log(tr("plotting_inputs_not_created", "❌ 输入框尚未创建，请先打开科研绘图页面"))
                return
            if not hasattr(self, 'lat_south_step9_edit') or self.lat_south_step9_edit is None:
                self.log(tr("plotting_inputs_not_created", "❌ 输入框尚未创建，请先打开科研绘图页面"))
                return
            if not hasattr(self, 'lat_north_step9_edit') or self.lat_north_step9_edit is None:
                self.log(tr("plotting_inputs_not_created", "❌ 输入框尚未创建，请先打开科研绘图页面"))
                return

            # 计算经纬度范围
            lon_min_val = f"{float(lon.min()):.2f}"
            lon_max_val = f"{float(lon.max()):.2f}"
            lat_min_val = f"{float(lat.min()):.2f}"
            lat_max_val = f"{float(lat.max()):.2f}"

            # 直接设置值
            self.lon_west_step9_edit.setText(lon_min_val)
            self.lon_east_step9_edit.setText(lon_max_val)
            self.lat_south_step9_edit.setText(lat_min_val)
            self.lat_north_step9_edit.setText(lat_max_val)

            # 强制刷新显示
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()

            # 如果文件中有时间信息，也尝试读取时间范围
            try:
                ds = Dataset(data_nc_path)
                if 'time' in ds.variables:
                    time_var = ds.variables['time']
                    try:
                        times = num2date(time_var[:], time_var.units)
                        start_time = times[0]
                        end_time = times[-1]
                        if hasattr(start_time, 'strftime'):
                            start_str = start_time.strftime("%Y%m%d")
                            end_str = end_time.strftime("%Y%m%d")
                            self.shel_start_step9_edit.setText(start_str)
                            self.shel_end_step9_edit.setText(end_str)
                    except:
                        pass
                ds.close()
            except:
                pass

            self.log(tr("step2_auto_load_range", "✅ 已从 {filename} 自动加载经纬度范围。").format(filename=os.path.basename(data_nc_path)))
        except Exception as e:
            self.log(tr("plotting_read_file_failed", "❌ 读取 {file} 失败: {error}").format(file=os.path.basename(data_nc_path), error=e))

    def run_jason3_swh(self):
        """运行 Jason-3 SWH 绘图"""
        if not self.selected_folder:
            self.log(tr("plotting_no_valid_folder", "❌ 本地未选择有效的目标文件夹。"))
            return

        # 获取参数
        try:
            lon_west = float(self.lon_west_step9_edit.text().strip())
            lon_east = float(self.lon_east_step9_edit.text().strip())
            lat_south = float(self.lat_south_step9_edit.text().strip())
            lat_north = float(self.lat_north_step9_edit.text().strip())
        except ValueError:
            self.log(tr("plotting_fill_lonlat_range", "❌ 请正确填写经纬度范围"))
            return

        start_str = self.shel_start_step9_edit.text().strip()
        end_str = self.shel_end_step9_edit.text().strip()
        if not start_str or not end_str:
            self.log(tr("plotting_fill_time_range", "❌ 请填写开始和结束时间（格式：YYYYMMDD）"))
            return

        jason_folder = self.jason_folder_edit.text().strip()
        if not jason_folder or not os.path.isdir(jason_folder):
            jason_folder = self._ensure_jason_folder_path()

        lon_lat = [lon_west, lon_east, lat_south, lat_north]
        time_range = [start_str, end_str]

        # 禁用按钮，防止重复点击
        self.btn_view_satellite.setEnabled(False)
        self.btn_view_satellite.setText(tr("step8_generating", "生成中..."))

        # 在子进程中执行计算操作（使用 multiprocessing 避免 GIL 限制，性能更好）
        self._run_jason3_swh_process(lon_lat, time_range, jason_folder)

    def _run_jason3_swh_process(self, lon_lat, time_range, jason_folder, retry_count=0, max_retries=3):
        """在子进程中执行 Jason-3 SWH 绘图操作"""
        # 创建队列用于子进程和主进程之间的通信
        log_queue = Queue()
        result_queue = Queue()

        # 启动子进程
        process = Process(
            target=_run_jason3_swh_worker,
            args=(lon_lat, time_range, jason_folder, self.selected_folder, log_queue, result_queue)
        )
        process.start()

        # 在主线程中监听日志队列并更新UI
        def _poll_logs():
            try:
                # 非阻塞检查队列
                done = False
                # 先处理所有消息
                pending_messages = []
                while True:
                    try:
                        msg = log_queue.get_nowait()

                        if msg == "__DONE__":
                            done = True
                            break
                        # 其他消息先暂存
                        pending_messages.append(msg)
                    except Exception:
                        break

                # 处理暂存的消息
                for msg in pending_messages:
                    self.log_signal.emit(msg)

                # 检查进程是否完成
                if not done and process.is_alive():
                    # 继续轮询
                    QtCore.QTimer.singleShot(100, _poll_logs)  # 每100ms检查一次
                else:
                    # 进程完成，获取最后的结果
                    if not done:
                        # 如果还没收到完成信号，再尝试获取一次
                        try:
                            while True:
                                try:
                                    msg = log_queue.get_nowait()
                                    if msg == "__DONE__":
                                        done = True
                                        break
                                    if msg != "__DONE__":
                                        self.log_signal.emit(msg)
                                except:
                                    break
                        except:
                            pass

                    # 等待进程结束
                    process.join(timeout=5)

                    # 获取结果
                    try:
                        result = result_queue.get(timeout=2)
                        if result and os.path.exists(result):
                            self.log_signal.emit(tr("plotting_jason_process_completed", "✅ 处理完成，输出文件：{path}").format(path=result))
                            # 使用信号在主线程中打开图片（系统默认应用）
                            self.show_image_signal.emit(result, "open")
                            # 恢复按钮状态
                            QtCore.QTimer.singleShot(0, self._restore_view_satellite_button)
                        else:
                            self.log_signal.emit(tr("plotting_jason_process_failed", "❌ 处理失败或未找到数据"))
                            if result:
                                self.log_signal.emit(tr("plotting_file_path", "   文件路径：{path}").format(path=result))
                            QtCore.QTimer.singleShot(0, self._restore_view_satellite_button)
                    except Exception as e:
                        self.log_signal.emit(tr("plotting_get_result_failed", "❌ 获取结果失败：{error}").format(error=e))
                        QtCore.QTimer.singleShot(0, self._restore_view_satellite_button)
            except Exception as e:
                import traceback
                self.log_signal.emit(tr("plotting_listen_process_failed", "❌ 监听子进程失败：{error}").format(error=e))
                self.log_signal.emit(tr("plotting_detailed_error", "详细错误：{error}").format(error=traceback.format_exc()))
                QtCore.QTimer.singleShot(0, self._restore_view_satellite_button)

        # 立即开始轮询（不等待，确保能及时收到消息）
        _poll_logs()

    def _restore_view_satellite_button(self):
        """恢复查看卫星观测图按钮状态（在主线程中执行）"""
        if hasattr(self, 'btn_view_satellite'):
            self.btn_view_satellite.setEnabled(True)
            self.btn_view_satellite.setText(tr("plotting_view_satellite", "查看卫星观测图"))

    def _run_jason3_swh_impl(self, lon_lat, time_range, jason_folder, out_folder,
                             FIGSIZE=(14, 10), DPI=300, UPSAMPLE_FACTOR=5, CLIM_PCT=99):
        """Jason-3 SWH 绘图实现"""
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
            self.log_signal.emit(tr("plotting_lon_range_error", "⚠️ 检测到经度范围顺序错误，已自动修正：lon[{min}:{max}]").format(min=lon_min, max=lon_max))

        # 确保 lat_min < lat_max（对于负纬度，lat_min 应该更负）
        if lat_min > lat_max:
            lat_min, lat_max = lat_max, lat_min
            self.log_signal.emit(tr("plotting_lat_range_error", "⚠️ 检测到纬度范围顺序错误，已自动修正：lat[{min}:{max}]").format(min=lat_min, max=lat_max))

        self.log_signal.emit("\n" + tr("plotting_jason_searching_files", "=========== Jason-3: Searching Files ==========="))

        # 再次扫描本地文件，找到时间范围内的文件
        time_pattern = r"(\d{8}_\d{6})_(\d{8}_\d{6})"
        nc_files = [
            f for f in os.listdir(jason_folder)
            if f.endswith(".nc") and f.startswith(("JA3_GPN_", "JA3_IPN_", "JA3_OPN_"))
        ]

        valid_files = []
        for f in nc_files:
            m = re.search(time_pattern, f)
            if not m:
                continue
            t1 = datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
            t2 = datetime.strptime(m.group(2), "%Y%m%d_%H%M%S")
            if t2 >= start_dt and t1 <= end_dt:
                valid_files.append(f)

        valid_files = sorted(valid_files)
        if not valid_files:
            self.log_signal.emit(tr("plotting_jason_no_files_in_range", "❌ 未找到符合时间范围的 Jason-3 文件"))
            return None

        self.log_signal.emit(tr("plotting_jason_files_found", "找到 {count} 个文件").format(count=len(valid_files)))

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
                self.log_signal.emit(tr("plotting_jason_skip_invalid", "⚠️ 跳过无效的 Jason-3 文件：{path} -> {error}").format(path=path, error=e))
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
            if len(lat_tmp) > 0:
                self.log_signal.emit(tr("plotting_jason_file_info", "📊 文件 {file}: 共 {count} 个数据点").format(file=os.path.basename(path), count=len(lat_tmp)))
                self.log_signal.emit(tr("plotting_jason_data_range", "   数据范围（转换后）: lon[{lon_min}:{lon_max}], lat[{lat_min}:{lat_max}]").format(lon_min=f"{lon_tmp.min():.2f}", lon_max=f"{lon_tmp.max():.2f}", lat_min=f"{lat_tmp.min():.2f}", lat_max=f"{lat_tmp.max():.2f}"))
                self.log_signal.emit(tr("plotting_jason_filter_range", "   筛选范围: lon[{lon_min}:{lon_max}], lat[{lat_min}:{lat_max}]").format(lon_min=lon_min, lon_max=lon_max, lat_min=lat_min, lat_max=lat_max))

            # 经纬度筛选
            # 对于经度，直接使用范围筛选即可，因为经度值已经在 -180 到 180 度范围内
            # 只有当筛选范围跨越 180 度经线时（从西经到东经），才需要特殊处理
            if lon_min < 0 and lon_max > 0:
                # 筛选范围跨越 180 度经线（从西经到东经），使用 OR 逻辑
                # 例如：lon[-10:10] 应该匹配西经 -10 到 -180 度，以及东经 0 到 10 度
                lon_mask = (lon_tmp >= lon_min) | (lon_tmp <= lon_max)
            else:
                # 正常情况，筛选范围不跨越 180 度经线，直接使用范围筛选
                # 例如：lon[110:130] 只匹配东经 110-130 度
                # 例如：lon[-130:-110] 只匹配西经 -130 到 -110 度
                lon_mask = (lon_tmp >= lon_min) & (lon_tmp <= lon_max)

            lat_mask = (lat_tmp >= lat_min) & (lat_tmp <= lat_max)
            mask = lon_mask & lat_mask

            # 调试：显示筛选情况
            if len(lat_tmp) > 0:
                lon_in_range = np.sum(lon_mask)
                lat_in_range = np.sum(lat_mask)
                both_in_range = np.sum(mask)
                self.log_signal.emit(tr("plotting_jason_lon_filter", "   经度筛选: {in_range}/{total} 个数据点在范围内").format(in_range=lon_in_range, total=len(lon_tmp)))
                self.log_signal.emit(tr("plotting_jason_lat_filter", "   纬度筛选: {in_range}/{total} 个数据点在范围内").format(in_range=lat_in_range, total=len(lat_tmp)))
                self.log_signal.emit(tr("plotting_jason_after_filter_count", "   筛选后: {count} 个数据点").format(count=both_in_range))

                # 如果筛选后没有数据，显示更详细的信息
                if both_in_range == 0 and lon_in_range > 0 and lat_in_range > 0:
                    # 显示经度在范围内的数据点的纬度范围
                    lon_in_range_lats = lat_tmp[lon_mask]
                    if len(lon_in_range_lats) > 0:
                        self.log_signal.emit(tr("plotting_jason_lon_range_lat", "   经度在范围内的数据点的纬度范围: [{lat_min}:{lat_max}]").format(lat_min=f"{lon_in_range_lats.min():.2f}", lat_max=f"{lon_in_range_lats.max():.2f}"))

                    # 显示纬度在范围内的数据点的经度范围
                    lat_in_range_lons = lon_tmp[lat_mask]
                    if len(lat_in_range_lons) > 0:
                        self.log_signal.emit(tr("plotting_jason_lat_range_lon", "   纬度在范围内的数据点的经度范围: [{lon_min}:{lon_max}]").format(lon_min=f"{lat_in_range_lons.min():.2f}", lon_max=f"{lat_in_range_lons.max():.2f}"))

            lat_tmp = lat_tmp[mask]
            lon_tmp = lon_tmp[mask]
            swh_tmp = swh_tmp[mask]

            # 去除无效值
            mask2 = (~np.isnan(swh_tmp)) & (swh_tmp > 0) & (swh_tmp <= JASON3_MAX_REASONABLE_SWH)
            lat_tmp = lat_tmp[mask2]
            lon_tmp = lon_tmp[mask2]
            swh_tmp = swh_tmp[mask2]

            if len(lat_tmp) > 0:
                self.log_signal.emit(tr("plotting_jason_after_filter", "   去除无效值后: {count} 个有效数据点").format(count=len(lat_tmp)))

            latitude.extend(lat_tmp)
            longitude.extend(lon_tmp)
            swh.extend(swh_tmp)

        if len(swh) == 0:
            self.log_signal.emit(tr("plotting_jason_no_data_in_region", "❌ 该区域无 Jason-3 数据"))
            return None

        longitude = np.array(longitude)
        latitude = np.array(latitude)
        # 处理 masked array，转换为普通数组并处理 NaN
        swh = np.ma.filled(np.array(swh), np.nan)  # 将 masked 值转换为 nan

        self.log_signal.emit(tr("plotting_jason_read_success", "Jason-3 数据读取成功"))

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

        self.log_signal.emit(tr("plotting_jason_output_success", "✅ 输出成功: {path}").format(path=out_file))

        return out_file

    def view_matching_fit(self):
        """查看拟合图（参考生成网格的实现方式，避免阻塞UI）"""
        if not self.selected_folder:
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return

        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == tr("step2_grid_type_nested", "嵌套网格"))

        # 确定数据源文件夹和输出文件夹
        if is_nested_grid:
            # 嵌套模式：从 fine 文件夹读取数据，输出到工作目录
            fine_dir = os.path.join(self.selected_folder, "fine")
            if not os.path.isdir(fine_dir):
                self.log(tr("plotting_fine_folder_not_found", "❌ 未找到 fine 文件夹，请先生成嵌套网格"))
                return
            data_folder = fine_dir
            output_folder = self.selected_folder
        else:
            # 普通模式：从工作目录读取数据，输出到工作目录
            data_folder = self.selected_folder
            output_folder = self.selected_folder

        # 先检查图片是否已存在（在 photo 文件夹中）
        photo_folder = os.path.join(output_folder, 'photo')
        out_png = os.path.join(photo_folder, 'ww3_jason3_comparison.png')
        if os.path.exists(out_png):
            # 图片已存在，直接用系统默认应用打开
            self.log(tr("plotting_fit_image_exists", "📊 发现已存在的拟合图，正在打开..."))
            self.show_fit_image_signal.emit(out_png, tr("plotting_fit_title", "拟合图：WW3 vs Jason-3"))
            return

        # 图片不存在，需要重新计算
        # 优先查找 ww3.*.nc 文件（排除 spec 文件）
        ww3_files = glob.glob(os.path.join(data_folder, "ww3.*.nc"))
        # 排除 spec 文件
        ww3_files = [f for f in ww3_files if "spec" not in os.path.basename(f).lower()]
        
        if not ww3_files:
            # 回退到查找 ww3*.nc（排除 spec）
            ww3_files = glob.glob(os.path.join(data_folder, "ww3*.nc"))
            # 排除 spec 文件
            ww3_files = [f for f in ww3_files if "spec" not in os.path.basename(f).lower()]
        
        if not ww3_files:
            self.log(tr("plotting_no_ww3_files", "❌ {folder} 文件夹中没有找到波高文件（已排除谱文件）").format(folder=data_folder))
            return

        ww3_file = ww3_files[0]

        jason_folder = self.jason_folder_edit.text().strip()
        if not jason_folder or not os.path.isdir(jason_folder):
            jason_folder = self._ensure_jason_folder_path()

        # 禁用按钮，防止重复点击
        self.btn_view_fit.setEnabled(False)
        self.btn_view_fit.setText(tr("plotting_calculating", "计算中..."))

        # 在子进程中执行计算操作（使用 multiprocessing 避免 GIL 限制，性能更好）
        self._run_view_fit_process(ww3_file, jason_folder, output_folder)

    def _run_view_fit_process(self, ww3_file, jason_folder, output_folder=None):
        """在子进程中执行拟合图计算操作（使用 multiprocessing 避免 GIL 限制）"""
        # 如果没有指定输出文件夹，使用工作目录
        if output_folder is None:
            output_folder = self.selected_folder

        # 创建队列用于子进程和主进程之间的通信
        log_queue = Queue()
        result_queue = Queue()

        # 启动子进程
        process = Process(
            target=_match_ww3_jason3_worker,
            args=(ww3_file, jason_folder, output_folder, log_queue, result_queue)
        )
        process.start()

        # 在主线程中监听日志队列并更新UI
        def _poll_logs():
            try:
                # 非阻塞检查队列
                done = False
                while True:
                    try:
                        msg = log_queue.get_nowait()
                        if msg == "__DONE__":
                            done = True
                            break
                        self.log_signal.emit(msg)
                    except:
                        break

                # 检查进程是否完成
                if not done and process.is_alive():
                    # 继续轮询
                    QtCore.QTimer.singleShot(100, _poll_logs)  # 每100ms检查一次
                else:
                    # 进程完成，获取最后的结果
                    if not done:
                        # 如果还没收到完成信号，再尝试获取一次
                        try:
                            while True:
                                try:
                                    msg = log_queue.get_nowait()
                                    if msg == "__DONE__":
                                        done = True
                                        break
                                    if msg != "__DONE__":
                                        self.log_signal.emit(msg)
                                except:
                                    break
                        except:
                            pass

                    # 等待进程结束
                    process.join(timeout=5)

                    # 获取结果
                    try:
                        stats = result_queue.get(timeout=2)
                        photo_folder = os.path.join(output_folder, 'photo')
                        out_png = os.path.join(photo_folder, 'ww3_jason3_comparison.png')

                        if stats and stats.get("count", 0) > 0 and os.path.exists(out_png):
                            bias_val = stats.get('bias', 'N/A')
                            rmse_val = stats.get('rmse', 'N/A')
                            corr_val = stats.get('corr', 'N/A')
                            if bias_val != 'N/A' and rmse_val != 'N/A' and corr_val != 'N/A':
                                self.log_signal.emit(tr("plotting_matching_completed", "✅ 匹配完成，共 {count} 个匹配点").format(count=stats.get('count', 0)))
                                self.log_signal.emit(tr("plotting_matching_stats", "   Bias: {bias:.3f}, RMSE: {rmse:.3f}, R: {corr:.3f}").format(bias=bias_val, rmse=rmse_val, corr=corr_val))
                            else:
                                self.log_signal.emit(tr("plotting_matching_completed", "✅ 匹配完成，共 {count} 个匹配点").format(count=stats.get('count', 0)))
                                self.log_signal.emit(f"   Bias: {bias_val}, RMSE: {rmse_val}, R: {corr_val}")
                            # 使用信号在主线程中用系统默认应用打开图片
                            self.show_fit_image_signal.emit(out_png, tr("plotting_fit_title", "拟合图：WW3 vs Jason-3"))
                        else:
                            self.log_signal.emit(tr("plotting_no_matching_points", "❌ 未匹配到有效点或图像不存在"))
                            self.log_signal.emit(tr("plotting_cannot_display_fit", "⚠️ 未匹配到有效点或图像不存在，无法显示拟合图"))
                    except Exception as e:
                        self.log_signal.emit(tr("plotting_get_result_failed", "❌ 获取结果失败：{error}").format(error=e))

                    # 恢复按钮状态
                    QtCore.QTimer.singleShot(0, self._restore_view_fit_button)
            except Exception as e:
                import traceback
                self.log_signal.emit(tr("plotting_listen_process_failed", "❌ 监听子进程失败：{error}").format(error=e))
                self.log_signal.emit(tr("plotting_detailed_error", "详细错误：{error}").format(error=traceback.format_exc()))
                QtCore.QTimer.singleShot(0, self._restore_view_fit_button)

        # 开始轮询
        QtCore.QTimer.singleShot(100, _poll_logs)

    def _run_view_fit_thread(self, ww3_file, jason_folder):
        """在后台线程中执行拟合图计算操作（保留作为备用）"""
        try:
            self.log_signal.emit(tr("plotting_start_matching", "🔄 开始匹配 WW3 和 Jason-3 数据（这可能需要一些时间，请稍候...）"))
            stats = self.match_ww3_jason3(ww3_file=ww3_file, jason3_path=jason_folder, out_folder=self.selected_folder)
            photo_folder = os.path.join(self.selected_folder, 'photo')
            out_png = os.path.join(photo_folder, 'ww3_jason3_comparison.png')

            if stats and stats.get("count", 0) > 0 and os.path.exists(out_png):
                bias_val = stats.get('bias', 'N/A')
                rmse_val = stats.get('rmse', 'N/A')
                corr_val = stats.get('corr', 'N/A')
                if bias_val != 'N/A' and rmse_val != 'N/A' and corr_val != 'N/A':
                    self.log_signal.emit(tr("plotting_matching_completed", "✅ 匹配完成，共 {count} 个匹配点").format(count=stats.get('count', 0)))
                    self.log_signal.emit(tr("plotting_matching_stats", "   Bias: {bias:.3f}, RMSE: {rmse:.3f}, R: {corr:.3f}").format(bias=bias_val, rmse=rmse_val, corr=corr_val))
                else:
                    self.log_signal.emit(tr("plotting_matching_completed", "✅ 匹配完成，共 {count} 个匹配点").format(count=stats.get('count', 0)))
                    self.log_signal.emit(f"   Bias: {bias_val}, RMSE: {rmse_val}, R: {corr_val}")
                # 使用信号在主线程中显示图片（Qt窗口）
                self.show_fit_image_signal.emit(out_png, tr("plotting_fit_title", "拟合图：WW3 vs Jason-3"))
            else:
                self.log_signal.emit("❌ 未匹配到有效点或图像不存在")
                self.log_signal.emit("⚠️ 未匹配到有效点或图像不存在，无法显示拟合图")
        except Exception as e:
            import traceback
            self.log_signal.emit(tr("plotting_process_failed", "❌ 处理失败：{error}").format(error=e))
            self.log_signal.emit(tr("plotting_detailed_error", "详细错误：{error}").format(error=traceback.format_exc()))
        finally:
            # 无论成功或失败，都恢复按钮状态（需要在主线程中执行）
            QtCore.QTimer.singleShot(0, self._restore_view_fit_button)

    def _restore_view_fit_button(self):
        """恢复查看拟合图按钮状态（在主线程中执行）"""
        if hasattr(self, 'btn_view_fit'):
            self.btn_view_fit.setEnabled(True)
            self.btn_view_fit.setText(tr("plotting_view_fit", "查看拟合图"))

    def _show_fit_image(self, image_path, window_title=None):
        """在窗口中显示图片（通过信号调用，在主线程中执行）"""
        try:
            # 如果路径为空，不显示
            if not image_path or not image_path.strip():
                return

            if not os.path.exists(image_path):
                self.log(tr("plotting_image_not_exists", "❌ 图片文件不存在：{path}").format(path=image_path))
                InfoBar.warning(
                    title=tr("plotting_error", "错误"),
                    content=tr("plotting_image_not_exists_basename", "图片文件不存在：{file}").format(file=os.path.basename(image_path)),
                    duration=3000,
                    parent=self
                )
                return

            # 如果没有指定标题，根据文件名判断
            if window_title is None:
                if "Jason3" in os.path.basename(image_path) or "jason" in os.path.basename(image_path).lower():
                    window_title = tr("plotting_satellite_image_title", "卫星观测图：Jason-3 SWH")
                elif "comparison" in os.path.basename(image_path).lower() or "fit" in os.path.basename(image_path).lower():
                    window_title = tr("plotting_fit_title", "拟合图：WW3 vs Jason-3")
                else:
                    window_title = tr("plotting_view_image", "图片查看")

            # 加载原始图片
            img_orig = Image.open(image_path)
            # 确保是 RGB 模式
            if img_orig.mode != 'RGB':
                img_orig = img_orig.convert('RGB')
            sw, sh = img_orig.size

            # 创建对话框窗口
            fit_window = QDialog(self)
            fit_window.setWindowTitle(window_title)
            fit_window.resize(min(sw + 40, 1600), min(sh + 40, 1200))

            # 创建布局
            layout = QVBoxLayout(fit_window)
            layout.setContentsMargins(0, 0, 0, 0)

            # 创建滚动区域
            scroll_area = QScrollArea(fit_window)
            scroll_area.setWidgetResizable(True)
            scroll_area.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

            # 创建标签用于显示图片
            img_label = QLabel()
            img_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            img_label.setScaledContents(False)  # 不自动缩放，手动控制

            # 将图片转换为 QPixmap 的辅助函数
            def pil_to_pixmap(img):
                """将 PIL Image 转换为 QPixmap"""
                from io import BytesIO
                buffer = BytesIO()
                img.save(buffer, format='PNG')
                buffer.seek(0)
                pixmap = QPixmap()
                pixmap.loadFromData(buffer.getvalue())
                return pixmap

            # 将图片转换为 QPixmap
            def update_image_size():
                """根据窗口大小更新图片显示"""
                if not fit_window.isVisible():
                    return

                # 获取可用大小
                available_width = scroll_area.viewport().width() - 20
                available_height = scroll_area.viewport().height() - 20

                if available_width <= 0 or available_height <= 0:
                    # 如果尺寸无效，使用原始尺寸
                    pixmap = pil_to_pixmap(img_orig)
                    img_label.setPixmap(pixmap)
                    img_label.setFixedSize(sw, sh)
                    return

                # 计算缩放比例
                scale = min(available_width / sw, available_height / sh)
                new_width = max(1, int(sw * scale))
                new_height = max(1, int(sh * scale))

                # 使用 PIL 高质量缩放
                img_resized = img_orig.resize((new_width, new_height), Image.Resampling.LANCZOS)

                # 转换为 QPixmap
                pixmap = pil_to_pixmap(img_resized)

                # 设置图片
                img_label.setPixmap(pixmap)
                img_label.setFixedSize(new_width, new_height)

            # 先设置一个初始图片（使用原始尺寸或缩小的尺寸）
            initial_width = min(sw, 1200)
            initial_height = min(sh, 900)
            if sw > 1200 or sh > 900:
                scale = min(1200 / sw, 900 / sh)
                initial_width = int(sw * scale)
                initial_height = int(sh * scale)

            img_initial = img_orig.resize((initial_width, initial_height), Image.Resampling.LANCZOS)
            pixmap_initial = pil_to_pixmap(img_initial)
            img_label.setPixmap(pixmap_initial)
            img_label.setFixedSize(initial_width, initial_height)

            # 设置标签为滚动区域的子部件
            scroll_area.setWidget(img_label)
            layout.addWidget(scroll_area)

            # 创建自定义事件过滤器类
            class ResizeFilter(QtCore.QObject):
                def __init__(self, update_func):
                    super().__init__()
                    self.update_func = update_func

                def eventFilter(self, obj, event):
                    if event.type() == QEvent.Type.Resize:
                        QtCore.QTimer.singleShot(50, self.update_func)
                    return super().eventFilter(obj, event)

            # 安装事件过滤器
            resize_filter = ResizeFilter(update_image_size)
            scroll_area.viewport().installEventFilter(resize_filter)
            fit_window.installEventFilter(resize_filter)

            # 先显示窗口，然后更新图片
            fit_window.show()
            fit_window.raise_()  # 确保窗口在最前面
            fit_window.activateWindow()  # 激活窗口
            # 使用多个延迟确保窗口完全显示后再更新图片
            QtCore.QTimer.singleShot(100, lambda: fit_window.update())
            QtCore.QTimer.singleShot(200, update_image_size)

            # 执行对话框（模态显示）
            fit_window.exec()

        except Exception as e:
            import traceback
            error_msg = tr("plotting_display_fit_failed", "❌ 显示拟合图失败：{error}\n{details}").format(error=e, details=traceback.format_exc())
            self.log(error_msg)
            # 如果窗口显示失败，回退到用系统默认应用打开
            try:
                self.open_image_file(image_path)
            except:
                pass
