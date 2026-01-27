"""
第二步：生成网格模块
包含UI创建（外网格参数、内网格参数、网格类型选择、按钮等）和按钮逻辑
"""
import os
import sys
import json
import glob
import shutil
import subprocess
import threading
import platform
import warnings
import numpy as np
import matplotlib
matplotlib.use('QtAgg')
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from netCDF4 import Dataset

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QGridLayout, QHBoxLayout, QWidget, QSizePolicy, QDialog, QScrollArea, QFrame
from PyQt6.QtGui import QPixmap
from qfluentwidgets import PrimaryPushButton, LineEdit, ComboBox, InfoBar
from setting.language_manager import tr
from setting.config import DX, DY, LONGITUDE_WEST, LONGITUDE_EAST, LATITUDE_SORTH, LATITUDE_NORTH, MATLAB_PATH, load_config
from .utils import create_header_card


class HomeStepTwoCard:
    """第二步：生成网格 Mixin"""
    
    def create_step_2_card(self, content_widget, content_layout):
        """创建第二步：生成网格的UI"""
        # 使用通用函数创建卡片
        step2_card, step2_card_layout = create_header_card(
            content_widget,
            tr("step2_title", "第二步：生成网格")
        )

        # 输入框样式：使用主题适配的样式
        input_style = self._get_input_style()

        # 外网格参数容器
        self.outer_grid_widget = QWidget()
        outer_grid_layout = QVBoxLayout()
        outer_grid_layout.setSpacing(10)
        outer_grid_layout.setContentsMargins(0, 0, 0, 0)

        # 外网格参数小标题（保存为实例变量以便动态控制）
        self.outer_title_container = QWidget()
        outer_title_layout = QHBoxLayout()
        outer_title_layout.setContentsMargins(0, 0, 0, 0)
        outer_title_layout.setSpacing(10)
        
        # 左侧横线
        outer_line_left = QtWidgets.QFrame()
        outer_line_left.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        outer_line_left.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        outer_line_left.setFixedHeight(1)
        outer_line_left.setMinimumHeight(1)
        outer_line_left.setMaximumHeight(1)
        outer_line_left.setStyleSheet("background-color: #888888; border: none;")
        outer_title_layout.addWidget(outer_line_left)
        
        # 标题标签（居中）
        self.outer_title = QLabel(tr("step2_outer_params", "外网格参数"))
        self.outer_title.setStyleSheet("font-weight: normal; font-size: 14px;")
        self.outer_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer_title_layout.addWidget(self.outer_title)
        
        # 右侧横线
        outer_line_right = QtWidgets.QFrame()
        outer_line_right.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        outer_line_right.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        outer_line_right.setFixedHeight(1)
        outer_line_right.setMinimumHeight(1)
        outer_line_right.setMaximumHeight(1)
        outer_line_right.setStyleSheet("background-color: #888888; border: none;")
        outer_title_layout.addWidget(outer_line_right)
        
        # 设置横线可伸缩
        outer_title_layout.setStretch(0, 1)  # 左侧横线
        outer_title_layout.setStretch(2, 1)  # 右侧横线
        
        self.outer_title_container.setLayout(outer_title_layout)
        self.outer_title_container.setVisible(False)  # 初始隐藏，选择嵌套网格时才显示
        outer_grid_layout.addWidget(self.outer_title_container)

        # 外网格参数输入框网格
        outer_grid = QGridLayout()
        outer_grid.setSpacing(10)

        # DX, DY 输入框
        outer_grid.addWidget(QLabel(tr("step2_dx", "DX:")), 0, 0)
        self.dx_edit = LineEdit()
        # 格式化 DX 为最多2位小数
        try:
            dx_value = float(DX) if DX else 0.05
            self.dx_edit.setText(f"{dx_value:.2f}")
        except (ValueError, TypeError):
            self.dx_edit.setText("0.05")
        self.dx_edit.setStyleSheet(input_style)
        outer_grid.addWidget(self.dx_edit, 0, 1)

        outer_grid.addWidget(QLabel(tr("step2_dy", "DY:")), 0, 2)
        self.dy_edit = LineEdit()
        # 格式化 DY 为最多2位小数
        try:
            dy_value = float(DY) if DY else 0.05
            self.dy_edit.setText(f"{dy_value:.2f}")
        except (ValueError, TypeError):
            self.dy_edit.setText("0.05")
        self.dy_edit.setStyleSheet(input_style)
        outer_grid.addWidget(self.dy_edit, 0, 3)

        # 经度输入框
        outer_grid.addWidget(QLabel(tr("step2_lon_west", "西经:")), 1, 0)
        self.lon_west_edit = LineEdit()
        self.lon_west_edit.setText(LONGITUDE_WEST if LONGITUDE_WEST else "")
        self.lon_west_edit.setStyleSheet(input_style)
        outer_grid.addWidget(self.lon_west_edit, 1, 1)

        outer_grid.addWidget(QLabel(tr("step2_lon_east", "东经:")), 1, 2)
        self.lon_east_edit = LineEdit()
        self.lon_east_edit.setText(LONGITUDE_EAST if LONGITUDE_EAST else "")
        self.lon_east_edit.setStyleSheet(input_style)
        outer_grid.addWidget(self.lon_east_edit, 1, 3)

        # 纬度输入框
        outer_grid.addWidget(QLabel(tr("step2_lat_south", "南纬:")), 2, 0)
        self.lat_south_edit = LineEdit()
        self.lat_south_edit.setText(LATITUDE_SORTH if LATITUDE_SORTH else "")
        self.lat_south_edit.setStyleSheet(input_style)
        outer_grid.addWidget(self.lat_south_edit, 2, 1)

        outer_grid.addWidget(QLabel(tr("step2_lat_north", "北纬:")), 2, 2)
        self.lat_north_edit = LineEdit()
        self.lat_north_edit.setText(LATITUDE_NORTH if LATITUDE_NORTH else "")
        self.lat_north_edit.setStyleSheet(input_style)
        outer_grid.addWidget(self.lat_north_edit, 2, 3)

        outer_grid_layout.addLayout(outer_grid)
        self.outer_grid_widget.setLayout(outer_grid_layout)
        step2_card_layout.addWidget(self.outer_grid_widget)

        # 内网格参数容器（初始隐藏）
        self.inner_grid_widget = QWidget()
        inner_grid_layout = QVBoxLayout()
        inner_grid_layout.setSpacing(10)
        inner_grid_layout.setContentsMargins(0, 0, 0, 0)

        # 内网格参数小标题
        inner_title_container = QWidget()
        inner_title_layout = QHBoxLayout()
        inner_title_layout.setContentsMargins(0, 0, 0, 0)
        inner_title_layout.setSpacing(10)
        
        # 左侧横线
        inner_line_left = QtWidgets.QFrame()
        inner_line_left.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        inner_line_left.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        inner_line_left.setFixedHeight(1)
        inner_line_left.setMinimumHeight(1)
        inner_line_left.setMaximumHeight(1)
        inner_line_left.setStyleSheet("background-color: #888888; border: none;")
        inner_title_layout.addWidget(inner_line_left)
        
        # 标题标签（居中）
        inner_title = QLabel(tr("step2_inner_params", "内网格参数"))
        inner_title.setStyleSheet("font-weight: normal; font-size: 14px;")
        inner_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner_title_layout.addWidget(inner_title)
        
        # 右侧横线
        inner_line_right = QtWidgets.QFrame()
        inner_line_right.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        inner_line_right.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        inner_line_right.setFixedHeight(1)
        inner_line_right.setMinimumHeight(1)
        inner_line_right.setMaximumHeight(1)
        inner_line_right.setStyleSheet("background-color: #888888; border: none;")
        inner_title_layout.addWidget(inner_line_right)
        
        # 设置横线可伸缩
        inner_title_layout.setStretch(0, 1)  # 左侧横线
        inner_title_layout.setStretch(2, 1)  # 右侧横线
        
        inner_title_container.setLayout(inner_title_layout)
        inner_grid_layout.addWidget(inner_title_container)

        # 内网格参数输入框网格
        inner_grid = QGridLayout()
        inner_grid.setSpacing(10)

        # DX, DY 输入框
        inner_grid.addWidget(QLabel(tr("step2_dx", "DX:")), 0, 0)
        self.inner_dx_edit = LineEdit()
        # 格式化 DX 为最多2位小数
        try:
            dx_value = float(DX) if DX else 0.05
            self.inner_dx_edit.setText(f"{dx_value:.2f}")
        except (ValueError, TypeError):
            self.inner_dx_edit.setText("0.05")
        self.inner_dx_edit.setStyleSheet(input_style)
        inner_grid.addWidget(self.inner_dx_edit, 0, 1)

        inner_grid.addWidget(QLabel(tr("step2_dy", "DY:")), 0, 2)
        self.inner_dy_edit = LineEdit()
        # 格式化 DY 为最多2位小数
        try:
            dy_value = float(DY) if DY else 0.05
            self.inner_dy_edit.setText(f"{dy_value:.2f}")
        except (ValueError, TypeError):
            self.inner_dy_edit.setText("0.05")
        self.inner_dy_edit.setStyleSheet(input_style)
        inner_grid.addWidget(self.inner_dy_edit, 0, 3)

        # 经度输入框
        inner_grid.addWidget(QLabel(tr("step2_lon_west", "西经:")), 1, 0)
        self.inner_lon_west_edit = LineEdit()
        self.inner_lon_west_edit.setText(LONGITUDE_WEST if LONGITUDE_WEST else "")
        self.inner_lon_west_edit.setStyleSheet(input_style)
        inner_grid.addWidget(self.inner_lon_west_edit, 1, 1)

        inner_grid.addWidget(QLabel(tr("step2_lon_east", "东经:")), 1, 2)
        self.inner_lon_east_edit = LineEdit()
        self.inner_lon_east_edit.setText(LONGITUDE_EAST if LONGITUDE_EAST else "")
        self.inner_lon_east_edit.setStyleSheet(input_style)
        inner_grid.addWidget(self.inner_lon_east_edit, 1, 3)

        # 纬度输入框
        inner_grid.addWidget(QLabel(tr("step2_lat_south", "南纬:")), 2, 0)
        self.inner_lat_south_edit = LineEdit()
        self.inner_lat_south_edit.setText(LATITUDE_SORTH if LATITUDE_SORTH else "")
        self.inner_lat_south_edit.setStyleSheet(input_style)
        inner_grid.addWidget(self.inner_lat_south_edit, 2, 1)

        inner_grid.addWidget(QLabel(tr("step2_lat_north", "北纬:")), 2, 2)
        self.inner_lat_north_edit = LineEdit()
        self.inner_lat_north_edit.setText(LATITUDE_NORTH if LATITUDE_NORTH else "")
        self.inner_lat_north_edit.setStyleSheet(input_style)
        inner_grid.addWidget(self.inner_lat_north_edit, 2, 3)

        inner_grid_layout.addLayout(inner_grid)
        self.inner_grid_widget.setLayout(inner_grid_layout)
        self.inner_grid_widget.setVisible(False)  # 初始隐藏
        step2_card_layout.addWidget(self.inner_grid_widget)

        # 下拉选择框样式：使用主题适配的样式
        combo_style = self._get_combo_style()

        # 网格类型选择（下拉框）- 放在"从风场文件读取范围"按钮上面
        grid_type_layout = QGridLayout()
        grid_type_layout.setContentsMargins(0, 0, 0, 0)
        grid_type_layout.setSpacing(0)  # 与 outer_grid 的间距一致
        grid_type_label = QLabel(tr("step2_grid_type", "类型："))
        grid_type_layout.addWidget(grid_type_label, 0, 0)
        self.grid_type_combo = ComboBox()
        normal_text = tr("step2_grid_type_normal", "普通网格")
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        self.grid_type_combo.addItems([normal_text, nested_text])
        
        # 使用全局状态管理
        from .utils import HomeState
        # 先检查全局状态是否已有值，如果没有才使用默认值
        current_grid_type = HomeState.get_grid_type()  # 不传 default，如果未设置会返回 None
        if current_grid_type is None:
            # 全局状态为空，设置默认值为普通网格
            HomeState.set_grid_type(normal_text)
            # 先断开信号，避免触发 _set_step2_grid_type
            self.grid_type_combo.blockSignals(True)
            self.grid_type_combo.setCurrentText(normal_text)
            self.grid_type_combo.blockSignals(False)
            self.grid_type_var = normal_text
        else:
            # 全局状态已有值，使用全局状态的值
            # 先断开信号，避免触发 _set_step2_grid_type
            self.grid_type_combo.blockSignals(True)
            self.grid_type_combo.setCurrentText(current_grid_type)
            self.grid_type_combo.blockSignals(False)
            self.grid_type_var = current_grid_type
        
        self.grid_type_combo.currentTextChanged.connect(self._set_step2_grid_type)
        self.grid_type_combo.setStyleSheet(combo_style)
        # 设置尺寸策略，让选择框可以展开
        self.grid_type_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # 设置文本左对齐（延迟设置，确保样式已应用）
        def _set_grid_type_combo_alignment():
            try:
                if hasattr(self.grid_type_combo, 'lineEdit'):
                    line_edit = self.grid_type_combo.lineEdit()
                    if line_edit:
                        line_edit.setAlignment(Qt.AlignmentFlag.AlignLeft)
            except:
                pass
        QtCore.QTimer.singleShot(10, _set_grid_type_combo_alignment)
        grid_type_layout.setColumnStretch(0, 0)
        grid_type_layout.setColumnStretch(1, 1)
        grid_type_layout.addWidget(self.grid_type_combo, 0, 1)
        # 对齐网格类型与外网格输入列（南纬同列）

        step2_card_layout.addLayout(grid_type_layout)

        # 从风场文件读取范围按钮
        btn_load_from_nc = PrimaryPushButton(tr("step2_load_from_nc", "从 wind.nc 读取范围"))
        btn_load_from_nc.setStyleSheet(self._get_button_style())
        btn_load_from_nc.clicked.connect(lambda: self.load_latlon_from_nc())
        step2_card_layout.addWidget(btn_load_from_nc)

        # 设置外网格按钮（只在嵌套模式下显示）
        self.btn_setup_outer_grid = PrimaryPushButton(tr("step2_setup_outer_grid", "设置外网格"))
        self.btn_setup_outer_grid.setStyleSheet(self._get_button_style())
        self.btn_setup_outer_grid.clicked.connect(self.setup_outer_grid)
        self.btn_setup_outer_grid.setVisible(False)  # 初始隐藏
        step2_card_layout.addWidget(self.btn_setup_outer_grid)

        # 设置内网格按钮（只在嵌套模式下显示）
        self.btn_setup_inner_grid = PrimaryPushButton(tr("step2_setup_inner_grid", "设置内网格"))
        self.btn_setup_inner_grid.setStyleSheet(self._get_button_style())
        self.btn_setup_inner_grid.clicked.connect(self.setup_inner_grid)
        self.btn_setup_inner_grid.setVisible(False)  # 初始隐藏
        step2_card_layout.addWidget(self.btn_setup_inner_grid)

        # 查看地图按钮
        btn_view_map = PrimaryPushButton(tr("step2_view_map", "查看地图"))
        btn_view_map.setStyleSheet(self._get_button_style())
        btn_view_map.clicked.connect(self.view_region_map)
        step2_card_layout.addWidget(btn_view_map)

        # 生成网格按钮（保存为实例变量，以便后续禁用/启用）
        self.btn_create_grid = PrimaryPushButton(tr("step2_create_grid", "生成网格"))
        self.btn_create_grid.setStyleSheet(self._get_button_style())
        self.btn_create_grid.clicked.connect(self.apply_and_create_grid)
        step2_card_layout.addWidget(self.btn_create_grid)

        # 可视化表格按钮
        self.btn_visualize_grid = PrimaryPushButton(tr("step2_visualize_grid", "网格可视化"))
        self.btn_visualize_grid.setStyleSheet(self._get_button_style())
        self.btn_visualize_grid.clicked.connect(self.visualize_grid_files)
        step2_card_layout.addWidget(self.btn_visualize_grid)

        # 设置内容区内边距
        step2_card.viewLayout.setContentsMargins(11, 10, 11, 12)
        step2_card.viewLayout.addLayout(step2_card_layout)
        content_layout.addWidget(step2_card)

    def _set_step2_grid_type(self, grid_type, skip_block_check=False):
        """设置网格类型选择（第二步UI相关部分）"""
        # 如果存在非强迫场文件，禁止切换网格类型（仅手动切换时）
        if skip_block_check:
            pass
        else:
            try:
                from .step1.file_path_manager import FilePathManager
                if hasattr(self, "selected_folder") and self.selected_folder and os.path.isdir(self.selected_folder):
                    has_non_forcing = False
                    for name in os.listdir(self.selected_folder):
                        if name.startswith("."):
                            continue
                        path = os.path.join(self.selected_folder, name)
                        if os.path.isdir(path):
                            has_non_forcing = True
                            break
                        if name.endswith(".nc"):
                            fields = FilePathManager.parse_forcing_filename(name)
                            if fields:
                                continue
                        has_non_forcing = True
                        break
                    if has_non_forcing:
                        current_grid = getattr(self, "grid_type_var", None) or self.grid_type_combo.currentText()
                        if current_grid and current_grid != grid_type:
                            self.grid_type_combo.blockSignals(True)
                            self.grid_type_combo.setCurrentText(current_grid)
                            self.grid_type_combo.blockSignals(False)
                            try:
                                InfoBar.warning(
                                    title=tr("tip", "提示"),
                                    content=tr("step2_grid_type_switch_blocked_files", "⚠️ 检测到非强迫场文件，无法切换网格类型"),
                                    duration=3000,
                                    parent=self
                                )
                            except Exception:
                                pass
                            return
            except Exception:
                pass

        # 若目录存在嵌套网格结构，禁止切换到普通网格（仅手动切换时）
        normal_text = tr("step2_grid_type_normal", "普通网格")
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        if not skip_block_check and grid_type == normal_text and hasattr(self, "selected_folder") and self.selected_folder:
            coarse_dir = os.path.join(self.selected_folder, "coarse")
            fine_dir = os.path.join(self.selected_folder, "fine")
            if os.path.isdir(coarse_dir) and os.path.isdir(fine_dir):
                self.grid_type_combo.blockSignals(True)
                self.grid_type_combo.setCurrentText(nested_text)
                self.grid_type_combo.blockSignals(False)
                try:
                    InfoBar.warning(
                        title=tr("tip", "提示"),
                        content=tr("step2_nested_grid_forced", "⚠️ 检测到 coarse 和 fine 文件夹，不能切换为普通网格"),
                        duration=3000,
                        parent=self
                    )
                except Exception:
                    pass
                grid_type = nested_text

        # 更新全局状态
        from .utils import HomeState
        HomeState.set_grid_type(grid_type)
        # 保持向后兼容，同时设置实例变量
        self.grid_type_var = grid_type
        # 更新第四步的 WAVEWATCH 标签
        self._update_step4_wavewatch_title()
        # 根据选择显示/隐藏内网格参数和调整标题（第二步）
        if grid_type == nested_text:
            self.inner_grid_widget.setVisible(True)
            self.outer_title.setText(tr("step2_outer_params", "外网格参数"))
            self.outer_title_container.setVisible(True)
            # 显示设置外网格和设置内网格按钮
            self.btn_setup_outer_grid.setVisible(True)
            self.btn_setup_inner_grid.setVisible(True)
            
            # 应用默认嵌套外网格 DX 和 DY
            from setting.config import load_config
            config = load_config()
            nested_outer_dx = config.get("NESTED_OUTER_DX", "0.05").strip()
            nested_outer_dy = config.get("NESTED_OUTER_DY", "0.05").strip()
            
            # 格式化 DX 和 DY 为最多2位小数
            try:
                dx_value = float(nested_outer_dx) if nested_outer_dx else 0.05
                dy_value = float(nested_outer_dy) if nested_outer_dy else 0.05
                self.dx_edit.setText(f"{dx_value:.2f}")
                self.dy_edit.setText(f"{dy_value:.2f}")
            except (ValueError, TypeError):
                # 如果转换失败，使用默认值
                self.dx_edit.setText("0.05")
                self.dy_edit.setText("0.05")
        else:
            self.inner_grid_widget.setVisible(False)
            # 当选择普通网格时，隐藏"外网格参数"标题
            self.outer_title_container.setVisible(False)
            # 隐藏设置外网格和设置内网格按钮
            self.btn_setup_outer_grid.setVisible(False)
            self.btn_setup_inner_grid.setVisible(False)
    
    def _update_step4_wavewatch_title(self):
        """更新第四步的 WAVEWATCH 标签文本"""
        if hasattr(self, '_update_wavewatch_title'):
            self._update_wavewatch_title()

    def _check_and_switch_to_nested_grid(self):
        """检测工作目录中是否存在coarse和fine文件夹，如果存在则自动切换到嵌套网格模式"""
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            return

        if not os.path.exists(self.selected_folder):
            return

        coarse_dir = os.path.join(self.selected_folder, "coarse")
        fine_dir = os.path.join(self.selected_folder, "fine")

        # 检查是否存在coarse和fine两个文件夹
        if os.path.isdir(coarse_dir) and os.path.isdir(fine_dir):
            # 自动切换到嵌套网格模式
            nested_text = tr("step2_grid_type_nested", "嵌套网格")
            # 先断开信号，避免触发 _set_step2_grid_type（因为后面会手动调用）
            self.grid_type_combo.blockSignals(True)
            self.grid_type_combo.setCurrentText(nested_text)
            self.grid_type_combo.blockSignals(False)
            # 手动触发 UI 更新，确保内外网格参数显示
            self._set_step2_grid_type(nested_text, skip_block_check=True)
            self.log(tr("step3_detect_nested_folders", "🔄 检测到coarse和fine文件夹，已自动切换到嵌套网格模式"))
        else:
            # 自动切换回普通网格模式
            normal_text = tr("step2_grid_type_normal", "普通网格")
            self.grid_type_combo.blockSignals(True)
            self.grid_type_combo.setCurrentText(normal_text)
            self.grid_type_combo.blockSignals(False)
            self._set_step2_grid_type(normal_text, skip_block_check=True)




    def _load_grid_info_to_step2(self):
        """读取当前工作目录的网格文件范围和精度，填充到第二步的输入框"""
        if not self.selected_folder:
            return

        # 检查是否是嵌套网格模式（通过检查目录结构）
        coarse_dir = os.path.join(self.selected_folder, "coarse")
        fine_dir = os.path.join(self.selected_folder, "fine")
        is_nested_grid = (os.path.isdir(coarse_dir) and os.path.isdir(fine_dir))

        if is_nested_grid:
            # 嵌套网格模式：读取外网格和内网格的信息
            coarse_info = self._read_single_grid_meta_bounds(coarse_dir)
            fine_info = self._read_single_grid_meta_bounds(fine_dir)

            # 填充外网格信息
            if coarse_info:
                if 'dx' in coarse_info:
                    self.dx_edit.setText(f"{coarse_info['dx']:.2f}")
                if 'dy' in coarse_info:
                    self.dy_edit.setText(f"{coarse_info['dy']:.2f}")
                if 'lon_min' in coarse_info:
                    self.lon_west_edit.setText(f"{coarse_info['lon_min']:.4f}")
                if 'lon_max' in coarse_info:
                    self.lon_east_edit.setText(f"{coarse_info['lon_max']:.4f}")
                if 'lat_min' in coarse_info:
                    self.lat_south_edit.setText(f"{coarse_info['lat_min']:.4f}")
                if 'lat_max' in coarse_info:
                    self.lat_north_edit.setText(f"{coarse_info['lat_max']:.4f}")

            # 填充内网格信息
            if fine_info:
                if 'dx' in fine_info:
                    self.inner_dx_edit.setText(f"{fine_info['dx']:.2f}")
                if 'dy' in fine_info:
                    self.inner_dy_edit.setText(f"{fine_info['dy']:.2f}")
                if 'lon_min' in fine_info:
                    self.inner_lon_west_edit.setText(f"{fine_info['lon_min']:.4f}")
                if 'lon_max' in fine_info:
                    self.inner_lon_east_edit.setText(f"{fine_info['lon_max']:.4f}")
                if 'lat_min' in fine_info:
                    self.inner_lat_south_edit.setText(f"{fine_info['lat_min']:.4f}")
                if 'lat_max' in fine_info:
                    self.inner_lat_north_edit.setText(f"{fine_info['lat_max']:.4f}")
        else:
            # 普通网格模式：读取工作目录下的 grid.meta
            grid_info = self._read_single_grid_meta_bounds(self.selected_folder)
            if grid_info:
                if 'dx' in grid_info:
                    self.dx_edit.setText(f"{grid_info['dx']:.2f}")
                if 'dy' in grid_info:
                    self.dy_edit.setText(f"{grid_info['dy']:.2f}")
                if 'lon_min' in grid_info:
                    self.lon_west_edit.setText(f"{grid_info['lon_min']:.4f}")
                if 'lon_max' in grid_info:
                    self.lon_east_edit.setText(f"{grid_info['lon_max']:.4f}")
                if 'lat_min' in grid_info:
                    self.lat_south_edit.setText(f"{grid_info['lat_min']:.4f}")
                if 'lat_max' in grid_info:
                    self.lat_north_edit.setText(f"{grid_info['lat_max']:.4f}")

    def view_region_map(self):
        """查看区域地图"""
        # 检查是否是嵌套模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested = (grid_type == nested_text or grid_type == "嵌套网格")
        
        try:
            # 获取外网格参数
            outer_lon_min = float(self.lon_west_edit.text().strip())
            outer_lon_max = float(self.lon_east_edit.text().strip())
            outer_lat_min = float(self.lat_south_edit.text().strip())
            outer_lat_max = float(self.lat_north_edit.text().strip())
        except ValueError:
            self.log(tr("step2_lon_lat_must_be_number", "❌ 外网格经纬度必须是数字！"))
            InfoBar.warning(
                title=tr("input_error", "输入错误"),
                content=tr("step2_lon_lat_must_be_number", "❌ 外网格经纬度必须是数字！"),
                duration=3000,
                parent=self
            )
            return

        # 如果是嵌套模式，获取内网格参数
        inner_lon_min = None
        inner_lon_max = None
        inner_lat_min = None
        inner_lat_max = None
        if is_nested:
            try:
                inner_lon_min = float(self.inner_lon_west_edit.text().strip())
                inner_lon_max = float(self.inner_lon_east_edit.text().strip())
                inner_lat_min = float(self.inner_lat_south_edit.text().strip())
                inner_lat_max = float(self.inner_lat_north_edit.text().strip())
            except (ValueError, AttributeError):
                self.log(tr("step3_nested_cannot_read_inner", "⚠️ 嵌套模式下无法读取内网格经纬度，仅显示外网格"))
                is_nested = False

        # 计算显示范围（包含内外网格，并留出边距）
        if is_nested:
            # 计算包含内外网格的范围
            display_lon_min = min(outer_lon_min, inner_lon_min) - 2.0  # 留出2度边距
            display_lon_max = max(outer_lon_max, inner_lon_max) + 2.0
            display_lat_min = min(outer_lat_min, inner_lat_min) - 2.0
            display_lat_max = max(outer_lat_max, inner_lat_max) + 2.0
        else:
            # 普通模式，留出边距
            display_lon_min = outer_lon_min - 2.0
            display_lon_max = outer_lon_max + 2.0
            display_lat_min = outer_lat_min - 2.0
            display_lat_max = outer_lat_max + 2.0

        # 设置中文字体支持
        chinese_font = None
        try:
            # 尝试使用系统中文字体
            system = platform.system()
            if system == 'Windows':
                # Windows 系统常用中文字体
                chinese_fonts = ['Microsoft YaHei', 'SimHei', 'SimSun', 'KaiTi']
            elif system == 'Darwin':  # macOS
                chinese_fonts = ['PingFang SC', 'STHeiti', 'Arial Unicode MS', 'Heiti SC']
            else:  # Linux
                chinese_fonts = ['WenQuanYi Micro Hei', 'WenQuanYi Zen Hei', 'Noto Sans CJK SC', 'Droid Sans Fallback']

            # 查找可用的中文字体
            from matplotlib import font_manager
            available_fonts = [f.name for f in font_manager.fontManager.ttflist]
            for font in chinese_fonts:
                if font in available_fonts:
                    chinese_font = font
                    break

            if chinese_font:
                plt.rcParams['font.sans-serif'] = [chinese_font]
                plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
            else:
                # 如果没有找到中文字体，使用默认字体但禁用警告
                warnings.filterwarnings('ignore', category=UserWarning, module='cartopy')
        except Exception:
            # 如果设置字体失败，忽略错误继续执行
            warnings.filterwarnings('ignore', category=UserWarning, module='cartopy')

        # 创建新窗口显示地图
        map_window = QDialog(self)
        if is_nested:
            map_window.setWindowTitle(tr("step3_nested_map_title", "嵌套网格地图"))
        else:
            map_window.setWindowTitle(tr("step3_region_map_title", "指定区域地图"))
        map_window.resize(1100, 900)

        layout = QVBoxLayout(map_window)
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建 matplotlib 图形
        # 保存原始显示范围（包括边距）
        original_display_lon_max = display_lon_max
        original_display_lon_min = display_lon_min
        
        # 计算原始网格的经度范围（不包括边距）
        original_lon_max = outer_lon_max if not is_nested else max(outer_lon_max, inner_lon_max)
        original_lon_min = outer_lon_min if not is_nested else min(outer_lon_min, inner_lon_min)
        
        # 判断是否需要处理经度超过 180 的情况
        # 只有当整个范围都超过 180 时，才转换为 -180 到 180 范围
        # 如果范围跨过 180 度经线（最小值 < 180，最大值 > 180），需要特殊处理
        if original_lon_min > 180 and original_lon_max > 180:
            # 整个范围都超过 180，转换为 -180 到 180 范围
            # 例如：190 ~ 200 转换为 -170 ~ -160
            original_lon_max = original_lon_max - 360
            original_lon_min = original_lon_min - 360
            display_lon_max = display_lon_max - 360
            display_lon_min = display_lon_min - 360
        elif original_lon_max > 180 and original_lon_min <= 180:
            # 范围跨过 180 度经线（例如：110 ~ 190）
            # 严格限制显示范围，只显示到 180 度，不显示超过 180 的部分
            # 限制最大经度为 180，但保留边距（最多到 180 + 边距，但不超过 182）
            original_lon_max = 180.0
            # 计算边距（基于原始网格范围）
            grid_lon_max = outer_lon_max if not is_nested else max(outer_lon_max, inner_lon_max)
            margin = 2.0  # 固定边距为 2 度
            # 严格限制显示范围，最多显示到 180 + 边距，但不超过 182
            display_lon_max = min(180.0 + margin, 182.0)
        
        # 计算中心经纬度，用于投影
        lon_center = (display_lon_min + display_lon_max) / 2.0
        lat_center = (display_lat_min + display_lat_max) / 2.0
        
        # 判断是否需要显示美洲：只有当经度范围包含西半球（负值）时，才使用 central_longitude=180
        # 对于纯东半球范围，使用默认投影，避免经度偏移
        if display_lon_min < 0 or display_lon_max < 0 or original_lon_min < 0 or original_lon_max < 0:
            # 包含西半球，使用 Mercator 投影，central_longitude=180 使美洲显示在东边
            proj = ccrs.Mercator(central_longitude=180)
        else:
            # 纯东半球，使用 Mercator 投影（central_longitude=0），避免经度偏移
            # Mercator 投影可以减少高纬度压缩，但需要设置合适的纬度范围
            proj = ccrs.Mercator(central_longitude=0)
            # 限制显示范围，确保不显示西半球（美洲）
            # 如果显示范围（包括边距）超过 180，允许显示到 180 + 边距
            if original_display_lon_max > 180:
                # 计算边距
                margin = original_display_lon_max - original_lon_max
                # 保留边距，但限制最大显示范围为 180 + 边距（最多到 185）
                display_lon_max = min(180.0 + margin, 185.0)
            # 如果原始经度范围接近 180，稍微缩小范围，避免显示整个地球
            elif original_lon_max >= 179:
                # 如果原始范围接近 180，限制显示范围，但保留边距
                margin = original_display_lon_max - original_lon_max
                display_lon_max = min(180.0, original_lon_max + margin)
        
        fig = plt.figure(figsize=(10, 8), dpi=100)
        ax = fig.add_subplot(1, 1, 1, projection=proj)
        # 不设置 equal aspect，避免高纬度地区被压缩
        # ax.set_aspect('equal', adjustable='box')

        # 设置画图范围（显示更大的范围，包含内外网格）
        # Mercator 投影需要使用 PlateCarree 坐标系传入经纬度
        ax.set_extent([display_lon_min, display_lon_max, display_lat_min, display_lat_max], crs=ccrs.PlateCarree())

        # 添加地图特征
        ax.add_feature(cfeature.OCEAN, facecolor="#a4d6ff")  # 海色
        ax.add_feature(cfeature.LAND, facecolor="#e6e6e6")   # 陆地色
        ax.coastlines(resolution='10m', linewidth=0.5)       # 海岸线

        # 如果是嵌套模式，绘制内外网格的虚线框
        # 矩形框需要使用 PlateCarree 坐标系，cartopy 会自动转换到投影坐标系
        plate_carree = ccrs.PlateCarree()
        if is_nested:
            # 绘制外网格虚线框（红色）
            outer_rect = plt.Rectangle(
                (outer_lon_min, outer_lat_min),
                outer_lon_max - outer_lon_min,
                outer_lat_max - outer_lat_min,
                linewidth=1.0,
                edgecolor='red',
                facecolor='none',
                linestyle='--',
                transform=plate_carree,
                label=tr("step3_outer_grid_label", "外网格")
            )
            ax.add_patch(outer_rect)

            # 绘制内网格虚线框（蓝色）
            inner_rect = plt.Rectangle(
                (inner_lon_min, inner_lat_min),
                inner_lon_max - inner_lon_min,
                inner_lat_max - inner_lat_min,
                linewidth=1.0,
                edgecolor='blue',
                facecolor='none',
                linestyle='--',
                transform=plate_carree,
                label=tr("step3_inner_grid_label", "内网格")
            )
            ax.add_patch(inner_rect)
            
            # 添加图例
            ax.legend(loc='upper right', fontsize=10)
        else:
            # 普通模式，绘制外网格虚线框
            outer_rect = plt.Rectangle(
                (outer_lon_min, outer_lat_min),
                outer_lon_max - outer_lon_min,
                outer_lat_max - outer_lat_min,
                linewidth=1.0,
                edgecolor='red',
                facecolor='none',
                linestyle='--',
                transform=plate_carree,
                label=tr("step2_map_range_label", "网格范围")
            )
            ax.add_patch(outer_rect)
            ax.legend(loc='upper right', fontsize=10)

        # 添加网格线（设置字体以避免中文警告）
        gl = ax.gridlines(
            draw_labels=True,
            linewidth=0.8,
            color='gray',
            alpha=0.7,
            linestyle='--'
        )
        gl.right_labels = False
        gl.top_labels = False

        # 如果设置了中文字体，应用到网格标签
        if chinese_font:
            try:
                gl.xlabel_style = {'fontname': chinese_font}
                gl.ylabel_style = {'fontname': chinese_font}
            except:
                pass

        # 设置标题（使用已配置的字体）
        title = tr("step3_nested_map_title", "嵌套网格地图") if is_nested else tr("step3_region_map_title", "指定区域地图")
        plt.title(title, fontsize=18, fontweight="bold")

        # 创建 canvas 并添加到窗口
        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)

        # 显示窗口
        map_window.exec()

        # 清理资源
        plt.close(fig)

        if is_nested:
            self.log(tr("step2_nested_map_displayed", "📍 已显示嵌套网格地图"))
            self.log(tr("step2_outer_grid_range", "   外网格: 经度 [{lon_min}, {lon_max}], 纬度 [{lat_min}, {lat_max}]").format(lon_min=f"{outer_lon_min:.2f}", lon_max=f"{outer_lon_max:.2f}", lat_min=f"{outer_lat_min:.2f}", lat_max=f"{outer_lat_max:.2f}"))
            self.log(tr("step2_inner_grid_range", "   内网格: 经度 [{lon_min}, {lon_max}], 纬度 [{lat_min}, {lat_max}]").format(lon_min=f"{inner_lon_min:.2f}", lon_max=f"{inner_lon_max:.2f}", lat_min=f"{inner_lat_min:.2f}", lat_max=f"{inner_lat_max:.2f}"))
        else:
            self.log(tr("step2_map_range_displayed", "📍 已显示地图范围: 经度 [{lon_min}, {lon_max}], 纬度 [{lat_min}, {lat_max}]").format(lon_min=f"{outer_lon_min:.2f}", lon_max=f"{outer_lon_max:.2f}", lat_min=f"{outer_lat_min:.2f}", lat_max=f"{outer_lat_max:.2f}"))

    # ========== 工具函数 ==========
    def _is_nested_grid(self, grid_type):
        """检查是否为嵌套网格（支持翻译后的文本）"""
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        return grid_type == nested_text or grid_type == "嵌套网格"

    # ========== 辅助函数（路径、缓存相关）==========
    def _get_gridgen_path(self):
        """动态获取 GRIDGEN_PATH（从配置文件读取最新值）"""
        config = load_config()
        gridgen_path = config.get("GRIDGEN_PATH", "").strip()
        # 如果 gridgen 路径为空，使用默认值 ../gridgen（相对于项目根目录）
        if not gridgen_path:
            # __file__ 是 main/home/home_step_two_card.py，需要回到项目根目录
            script_dir = os.path.dirname(os.path.abspath(__file__))  # main/home
            main_dir = os.path.dirname(script_dir)  # main
            project_root = os.path.dirname(main_dir)  # 项目根目录
            gridgen_path = os.path.join(project_root, "gridgen")
        # 规范化路径
        return os.path.normpath(gridgen_path) if gridgen_path else gridgen_path

    def _get_gridgen_bin_path(self):
        """动态获取 GRIDGEN_BIN_PATH（根据 GRIDGEN_PATH 计算）"""
        gridgen_path = self._get_gridgen_path()
        return os.path.normpath(os.path.join(gridgen_path, "matlab")) if gridgen_path else None

    def _get_reference_data_path(self):
        """获取参考数据目录路径（优先使用配置中的路径）"""
        config = load_config()
        ref_data_path = config.get("REFERENCE_DATA_PATH", "").strip()
        gridgen_path = self._get_gridgen_path()
        gridgen_bin_path = self._get_gridgen_bin_path()
        
        if ref_data_path:
            # 如果配置的路径是绝对路径，直接使用
            if os.path.isabs(ref_data_path):
                ref_dir = ref_data_path
            else:
                # 如果是相对路径，相对于 GRIDGEN_PATH
                ref_dir = os.path.join(gridgen_path, ref_data_path)
        else:
            # 如果配置为空，使用默认路径
            ref_dir = os.path.join(gridgen_path, "reference_data")
        
        # 如果路径不存在，尝试备用路径
        if not os.path.exists(ref_dir) and gridgen_bin_path:
            ref_dir = os.path.join(gridgen_bin_path, "..", "reference_data")
        
        # 规范化路径
        ref_dir = os.path.normpath(os.path.abspath(ref_dir))
        return ref_dir

    def _get_grid_cache_dir(self):
        """获取网格缓存目录（gridgen/cache）"""
        gridgen_path = self._get_gridgen_path()
        gridgen_cache_dir = os.path.join(gridgen_path, "cache")
        os.makedirs(gridgen_cache_dir, exist_ok=True)
        return gridgen_cache_dir

    def _get_grid_cache_key(self, dx_value, dy_value, lon_west, lon_east, lat_south, lat_north, ref_dir, bathymetry=None, coastline_precision=None):
        """生成网格参数的缓存键（哈希值）"""
        import hashlib
        # 如果参数未提供，从配置中读取
        if bathymetry is None or coastline_precision is None:
            config = load_config()
            if bathymetry is None:
                bathymetry = config.get("BATHYMETRY", "GEBCO")
            if coastline_precision is None:
                coastline_precision = config.get("COASTLINE_PRECISION", tr("step2_coastline_precision_full", "最高"))
        # 将所有参数转换为可序列化的格式
        params = {
            'dx': float(dx_value),
            'dy': float(dy_value),
            'lon_range': [float(lon_west), float(lon_east)],
            'lat_range': [float(lat_south), float(lat_north)],
            'ref_dir': os.path.normpath(os.path.abspath(ref_dir)).replace("\\", "/"),
            'bathymetry': str(bathymetry),
            'coastline_precision': str(coastline_precision)
        }
        # 将参数序列化为JSON字符串（排序键以确保一致性）
        params_str = json.dumps(params, sort_keys=True, separators=(',', ':'))
        # 生成SHA256哈希值
        hash_obj = hashlib.sha256(params_str.encode('utf-8'))
        return hash_obj.hexdigest()

    def _check_grid_cache(self, cache_key):
        """检查网格缓存是否存在"""
        cache_dir = self._get_grid_cache_dir()
        cache_path = os.path.join(cache_dir, cache_key)
        # 检查缓存目录是否存在，且包含必要的文件
        if os.path.isdir(cache_path):
            required_files = ['grid.bot', 'grid.obst', 'grid.meta', 'grid.mask']
            if all(os.path.exists(os.path.join(cache_path, f)) for f in required_files):
                return cache_path
        return None

    def _save_grid_to_cache(self, cache_key, source_dir, dx_value=None, dy_value=None,
                           lon_west=None, lon_east=None, lat_south=None, lat_north=None, ref_dir=None, bathymetry=None, coastline_precision=None):
        """将生成的网格保存到缓存"""
        cache_dir = self._get_grid_cache_dir()
        cache_path = os.path.join(cache_dir, cache_key)

        # 如果缓存目录已存在，先删除
        if os.path.exists(cache_path):
            shutil.rmtree(cache_path)

        # 创建缓存目录
        os.makedirs(cache_path, exist_ok=True)

        # 复制网格文件到缓存
        grid_files = ['grid.bot', 'grid.obst', 'grid.meta', 'grid.mask']
        for f in grid_files:
            src = os.path.join(source_dir, f)
            if os.path.exists(src):
                dst = os.path.join(cache_path, f)
                shutil.copy2(src, dst)

        # 保存参数信息（包含明文参数和缓存信息）
        params_data = {
            'cache_key': cache_key,
            'source_dir': source_dir,
            'parameters': {
                'dx': dx_value,
                'dy': dy_value,
                'lon_range': [lon_west, lon_east] if lon_west is not None and lon_east is not None else None,
                'lat_range': [lat_south, lat_north] if lat_south is not None and lat_north is not None else None,
                'ref_dir': ref_dir,
                'bathymetry': bathymetry,
                'coastline_precision': coastline_precision
            }
        }
        params_file = os.path.join(cache_path, 'params.json')
        with open(params_file, 'w', encoding='utf-8') as pf:
            json.dump(params_data, pf, indent=2, ensure_ascii=False)

    def _load_grid_from_cache(self, cache_path, output_dir):
        """从缓存加载网格文件到输出目录"""
        grid_files = ['grid.bot', 'grid.obst', 'grid.meta', 'grid.mask']
        for f in grid_files:
            src = os.path.join(cache_path, f)
            if os.path.exists(src):
                dst = os.path.join(output_dir, f)
                shutil.copy2(src, dst)

    def _validate_grid_files(self, output_dir, max_retries=3, retry_delay=1.0):
        """验证生成的网格文件是否完整，如果文件不完整则等待并重试"""
        import time
        
        grid_bot_path = os.path.join(output_dir, "grid.bot")
        grid_meta_path = os.path.join(output_dir, "grid.meta")
        
        # 等待文件出现（最多等待 5 秒）
        for _ in range(5):
            if os.path.exists(grid_bot_path) and os.path.exists(grid_meta_path):
                break
            time.sleep(1.0)
        
        if not os.path.exists(grid_bot_path):
            return False, tr("step2_grid_bot_not_exists", "grid.bot 文件不存在")
        
        if not os.path.exists(grid_meta_path):
            return False, tr("step2_grid_meta_not_exists", "grid.meta 文件不存在，无法验证")
        
        # 从 grid.meta 读取 Nx, Ny
        Nx, Ny = None, None
        try:
            with open(grid_meta_path, 'r') as f:
                lines = f.readlines()
                for i, line in enumerate(lines):
                    if "'RECT'" in line or '"RECT"' in line:
                        if i + 1 < len(lines):
                            values = lines[i + 1].split()
                            if len(values) >= 2:
                                Nx = int(float(values[0]))
                                Ny = int(float(values[1]))
                                break
        except Exception as e:
            return False, tr("step2_read_grid_meta_failed", "读取 grid.meta 失败: {error}").format(error=e)
        
        if Nx is None or Ny is None:
            return False, tr("step2_cannot_read_nx_ny", "无法从 grid.meta 读取 Nx, Ny")
        
        # 验证 grid.bot 文件（带重试机制）
        for retry in range(max_retries):
            try:
                # 等待文件稳定（文件大小不再变化）
                if retry > 0:
                    time.sleep(retry_delay)
                
                data = []
                with open(grid_bot_path, 'r') as fid:
                    for line in fid:
                        line = line.strip()
                        if line:  # 跳过空行
                            values = [int(x) for x in line.split()]
                            if len(values) > 0:
                                data.append(values)
                
                if len(data) < Ny:
                    if retry < max_retries - 1:
                        # 文件可能还在写入，等待后重试
                        continue
                    return False, tr("step2_grid_bot_rows_insufficient", "grid.bot 文件行数不足: 实际 {actual} 行，预期 {expected} 行（可能是 dxdy > 0.05 导致的文件写入不完整）").format(actual=len(data), expected=Ny)
                
                # 检查前 Ny 行的列数
                for i, row in enumerate(data[:Ny]):
                    if len(row) != Nx:
                        if retry < max_retries - 1:
                            # 文件可能还在写入，等待后重试
                            break
                        return False, tr("step2_grid_bot_cols_incorrect", "grid.bot 第 {row} 行列数不正确: 实际 {actual} 列，预期 {expected} 列").format(row=i+1, actual=len(row), expected=Nx)
                else:
                    # 所有行都正确，验证通过
                    return True, tr("step2_grid_validation_passed", "网格文件验证通过: {nx}x{ny}，文件包含 {rows} 行").format(nx=Nx, ny=Ny, rows=len(data))
            except Exception as e:
                if retry < max_retries - 1:
                    continue
                return False, tr("step2_grid_bot_validation_error", "验证 grid.bot 文件时出错: {error}").format(error=e)
        
        return False, tr("step2_grid_bot_validation_failed", "grid.bot 文件验证失败（重试 {retries} 次后仍不完整）").format(retries=max_retries)

    def _scale_grid(self, lon_w, lon_e, lat_s, lat_n, dx, dy, scale=1, grid_type='outer'):
        """
        根据当前网格和放缩系数，生成缩放后的网格参数
        （步长和经纬度范围都会按 scale 缩放）

        参数
        ----
        lon_w, lon_e : float  当前网格西/东边界经度
        lat_s, lat_n : float  当前网格南/北边界纬度
        dx, dy       : float  当前网格步长
        scale        : float  放缩系数，例如 3 表示外→内 1:3
        grid_type    : str    'outer' 或 'inner'，表示当前输入网格类型

        返回
        ----
        dict : {
            'X0': 缩放后的西南角经度,
            'Y0': 缩放后的西南角纬度,
            'DX': 缩放后的步长,
            'DY': 缩放后的步长,
            'lon_w': 缩放后的西边界,
            'lon_e': 缩放后的东边界,
            'lat_s': 缩放后的南边界,
            'lat_n': 缩放后的北边界
        }
        """
        if scale <= 0:
            raise ValueError(tr("step2_scale_must_positive", "scale 必须大于0"))
        if grid_type not in ['outer','inner']:
            raise ValueError(tr("step2_grid_type_must_outer_inner", "grid_type 必须为 'outer' 或 'inner'"))

        # 当前网格中心
        lon_c = 0.5*(lon_w + lon_e)
        lat_c = 0.5*(lat_s + lat_n)

        # 当前网格半宽、半高
        half_width = 0.5*(lon_e - lon_w)
        half_height = 0.5*(lat_n - lat_s)

        if grid_type == 'outer':
            # 外网格→内网格：收缩
            new_half_width  = half_width / scale
            new_half_height = half_height / scale
            new_dx = dx / scale
            new_dy = dy / scale
        else:
            # 内网格→外网格：放大
            new_half_width  = half_width * scale
            new_half_height = half_height * scale
            new_dx = dx * scale
            new_dy = dy * scale

        # 新网格边界
        new_lon_w = lon_c - new_half_width
        new_lon_e = lon_c + new_half_width
        new_lat_s = lat_c - new_half_height
        new_lat_n = lat_c + new_half_height

        # 西南角 = 新边界西南角
        X0 = new_lon_w
        Y0 = new_lat_s

        return {
            'X0': X0,
            'Y0': Y0,
            'DX': new_dx,
            'DY': new_dy,
            'lon_w': new_lon_w,
            'lon_e': new_lon_e,
            'lat_s': new_lat_s,
            'lat_n': new_lat_n
        }

    # ========== 主要函数 ==========
    def load_latlon_from_nc(self, file_name="wind.nc"):
        """读取 NC 文件并填入经纬度输入框，支持通配符"""
        # 检查 file_name 参数类型（防止 clicked 信号传递布尔值）
        if not isinstance(file_name, str):
            # 如果 file_name 不是字符串，使用默认值
            file_name = "wind.nc"

        # 严格的类型和值检查
        if self.selected_folder is None:
            self.log(tr("step2_workdir_not_exists", "❌ 当前工作目录不存在！"))
            return

        if not isinstance(self.selected_folder, str):
            self.log(tr("step2_workdir_type_error", "❌ selected_folder 类型错误: {type}, 值: {value}").format(type=type(self.selected_folder), value=repr(self.selected_folder)))
            self.log(tr("step2_workdir_not_exists", "❌ 当前工作目录不存在！"))
            return

        if not self.selected_folder.strip():
            self.log(tr("step2_workdir_empty", "❌ 工作目录路径为空！"))
            return

        # 查找工作目录中包含 wind 的文件（可能是 wind.nc 或 wind_current_ssh_ice.nc 等）
        wind_files = glob.glob(os.path.join(self.selected_folder, "*wind*.nc"))
        
        if not wind_files:
            # 如果找不到包含 wind 的文件，尝试使用 wind.nc
            data_nc_path = os.path.join(self.selected_folder, "wind.nc")
            if not os.path.exists(data_nc_path):
                self.log(tr("step2_wind_file_not_found", "❌ 未找到风场文件（工作目录中不存在包含 'wind' 的 .nc 文件）"))
                return
        else:
            # 如果有多个，优先选择 wind.nc，否则选择第一个
            wind_nc_path = os.path.join(self.selected_folder, "wind.nc")
            if wind_nc_path in wind_files:
                data_nc_path = wind_nc_path
            else:
                data_nc_path = wind_files[0]
        
        file_name = os.path.basename(data_nc_path)
        try:
            ds = Dataset(data_nc_path)
            
            # 查找经纬度变量（支持多种变量名变体）
            lon_var = None
            lat_var = None
            
            # 查找经度变量
            for lon_name in ["longitude", "lon", "Longitude", "LON"]:
                if lon_name in ds.variables:
                    lon_var = ds.variables[lon_name]
                    break
            
            # 查找纬度变量
            for lat_name in ["latitude", "lat", "Latitude", "LAT"]:
                if lat_name in ds.variables:
                    lat_var = ds.variables[lat_name]
                    break
            
            if lon_var is None:
                self.log(tr("step2_lon_var_not_found", "❌ {file_name} 中未找到经度变量（尝试了: longitude, lon, Longitude, LON）").format(file_name=file_name))
                ds.close()
                return
            
            if lat_var is None:
                self.log(tr("step2_lat_var_not_found", "❌ {file_name} 中未找到纬度变量（尝试了: latitude, lat, Latitude, LAT）").format(file_name=file_name))
                ds.close()
                return
            
            lon = lon_var[:]
            lat = lat_var[:]
            ds.close()

            # 直接使用经纬度变量的范围
            lon_min = float(np.min(lon))
            lon_max = float(np.max(lon))
            lat_min = float(np.min(lat))
            lat_max = float(np.max(lat))

            # 更新外网格输入框
            self.lon_west_edit.setText(f"{lon_min:.2f}")
            self.lon_east_edit.setText(f"{lon_max:.2f}")
            self.lat_south_edit.setText(f"{lat_min:.2f}")
            self.lat_north_edit.setText(f"{lat_max:.2f}")

            # 如果是嵌套网格模式，同时填充内网格参数
            grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
            # 使用翻译函数检查是否为嵌套网格（支持中英文）
            nested_text = tr("step2_grid_type_nested", "嵌套网格")
            if grid_type == nested_text or grid_type == "嵌套网格":
                self.inner_lon_west_edit.setText(f"{lon_min:.2f}")
                self.inner_lon_east_edit.setText(f"{lon_max:.2f}")
                self.inner_lat_south_edit.setText(f"{lat_min:.2f}")
                self.inner_lat_north_edit.setText(f"{lat_max:.2f}")
                self.log(tr("step2_auto_load_range_both", "✅ 已从 {filename} 自动加载经纬度范围（外网格和内网格）。").format(filename=os.path.basename(data_nc_path)))
            else:
                self.log(tr("step2_auto_load_range", "✅ 已从 {filename} 自动加载经纬度范围。").format(filename=os.path.basename(data_nc_path)))
        except Exception as e:
            self.log(tr("step2_read_file_failed", "❌ 读取 {file_name} 失败: {error}").format(file_name=os.path.basename(data_nc_path), error=e))

    def setup_inner_grid(self):
        """根据嵌套收缩系数 N 设置内网格范围（基于中心点缩放）"""
        # 检查是否在嵌套模式下
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        if not self._is_nested_grid(grid_type):
            self.log(tr("step2_not_nested_mode", "❌ 当前不是嵌套网格模式"))
            return

        try:
            # 获取嵌套收缩系数 N
            config = load_config()
            n_str = config.get("NESTED_CONTRACTION_COEFFICIENT", "3").strip()
            try:
                N = float(n_str)
                if N <= 0:
                    raise ValueError(tr("step2_invalid_nested_coeff", "嵌套收缩系数必须大于0"))
            except (ValueError, TypeError):
                self.log(tr("step2_invalid_nested_coeff", "❌ 无效的嵌套收缩系数: {n_str}，请使用数字（推荐 3 或 2）").format(n_str=n_str))
                return

            # 获取外网格参数
            try:
                outer_dx = float(self.dx_edit.text().strip()) if self.dx_edit.text().strip() else float(DX)
            except (ValueError, AttributeError):
                self.log(tr("step2_cannot_read_outer_dx", "❌ 无法读取外网格 DX 参数"))
                return

            try:
                outer_dy = float(self.dy_edit.text().strip()) if self.dy_edit.text().strip() else float(DY)
            except (ValueError, AttributeError):
                self.log(tr("step2_cannot_read_outer_dy", "❌ 无法读取外网格 DY 参数"))
                return

            try:
                outer_lon_west = float(self.lon_west_edit.text().strip()) if self.lon_west_edit.text().strip() else float(LONGITUDE_WEST) if LONGITUDE_WEST else 0.0
            except (ValueError, AttributeError):
                self.log(tr("step2_cannot_read_outer_lon_west", "❌ 无法读取外网格西经参数"))
                return

            try:
                outer_lon_east = float(self.lon_east_edit.text().strip()) if self.lon_east_edit.text().strip() else float(LONGITUDE_EAST) if LONGITUDE_EAST else 0.0
            except (ValueError, AttributeError):
                self.log(tr("step2_cannot_read_outer_lon_east", "❌ 无法读取外网格东经参数"))
                return

            try:
                outer_lat_south = float(self.lat_south_edit.text().strip()) if self.lat_south_edit.text().strip() else float(LATITUDE_SORTH) if LATITUDE_SORTH else 0.0
            except (ValueError, AttributeError):
                self.log(tr("step2_cannot_read_outer_lat_south", "❌ 无法读取外网格南纬参数"))
                return

            try:
                outer_lat_north = float(self.lat_north_edit.text().strip()) if self.lat_north_edit.text().strip() else float(LATITUDE_NORTH) if LATITUDE_NORTH else 0.0
            except (ValueError, AttributeError):
                self.log(tr("step2_cannot_read_outer_lat_north", "❌ 无法读取外网格北纬参数"))
                return

            # 使用新的缩放逻辑计算内网格参数
            result = self._scale_grid(
                outer_lon_west, outer_lon_east,
                outer_lat_south, outer_lat_north,
                outer_dx, outer_dy,
                scale=N, grid_type='outer'
            )

            # 更新内网格输入框（不修改 DX 和 DY）
            self.inner_lon_west_edit.setText(f"{result['lon_w']:.2f}")
            self.inner_lon_east_edit.setText(f"{result['lon_e']:.2f}")
            self.inner_lat_south_edit.setText(f"{result['lat_s']:.2f}")
            self.inner_lat_north_edit.setText(f"{result['lat_n']:.2f}")

            self.log(tr("step2_inner_grid_set", "✅ 已根据嵌套收缩系数 N={n} 设置内网格范围（基于中心点缩放）").format(n=N))
            self.log(tr("step2_inner_grid_coords", "   内网格西经: {lon_w:.2f}, 东经: {lon_e:.2f}").format(lon_w=result['lon_w'], lon_e=result['lon_e']))
            self.log(tr("step2_inner_grid_lat", "   内网格南纬: {lat_s:.2f}, 北纬: {lat_n:.2f}").format(lat_s=result['lat_s'], lat_n=result['lat_n']))

        except Exception as e:
            self.log(tr("step2_inner_grid_set_failed", "❌ 设置内网格失败: {error}").format(error=str(e)))
            import traceback
            traceback.print_exc()

    def setup_outer_grid(self):
        """根据嵌套收缩系数 N 设置外网格范围（基于内网格中心点放大）"""
        # 检查是否在嵌套模式下
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        if not self._is_nested_grid(grid_type):
            self.log(tr("step2_not_nested_mode", "❌ 当前不是嵌套网格模式"))
            return

        try:
            # 获取嵌套收缩系数 N
            config = load_config()
            n_str = config.get("NESTED_CONTRACTION_COEFFICIENT", "3").strip()
            try:
                N = float(n_str)
                if N <= 0:
                    raise ValueError(tr("step2_invalid_nested_coeff", "嵌套收缩系数必须大于0"))
            except (ValueError, TypeError):
                self.log(tr("step2_invalid_nested_coeff", "❌ 无效的嵌套收缩系数: {n_str}，请使用数字（推荐 3 或 2）").format(n_str=n_str))
                return

            # 获取内网格参数
            try:
                inner_dx = float(self.inner_dx_edit.text().strip()) if self.inner_dx_edit.text().strip() else float(DX)
            except (ValueError, AttributeError):
                self.log(tr("step2_cannot_read_inner_dx", "❌ 无法读取内网格 DX 参数"))
                return

            try:
                inner_dy = float(self.inner_dy_edit.text().strip()) if self.inner_dy_edit.text().strip() else float(DY)
            except (ValueError, AttributeError):
                self.log(tr("step2_cannot_read_inner_dy", "❌ 无法读取内网格 DY 参数"))
                return

            try:
                inner_lon_west = float(self.inner_lon_west_edit.text().strip()) if self.inner_lon_west_edit.text().strip() else float(LONGITUDE_WEST) if LONGITUDE_WEST else 0.0
            except (ValueError, AttributeError):
                self.log(tr("step2_cannot_read_inner_lon_west", "❌ 无法读取内网格西经参数"))
                return

            try:
                inner_lon_east = float(self.inner_lon_east_edit.text().strip()) if self.inner_lon_east_edit.text().strip() else float(LONGITUDE_EAST) if LONGITUDE_EAST else 0.0
            except (ValueError, AttributeError):
                self.log(tr("step2_cannot_read_inner_lon_east", "❌ 无法读取内网格东经参数"))
                return

            try:
                inner_lat_south = float(self.inner_lat_south_edit.text().strip()) if self.inner_lat_south_edit.text().strip() else float(LATITUDE_SORTH) if LATITUDE_SORTH else 0.0
            except (ValueError, AttributeError):
                self.log(tr("step2_cannot_read_inner_lat_south", "❌ 无法读取内网格南纬参数"))
                return

            try:
                inner_lat_north = float(self.inner_lat_north_edit.text().strip()) if self.inner_lat_north_edit.text().strip() else float(LATITUDE_NORTH) if LATITUDE_NORTH else 0.0
            except (ValueError, AttributeError):
                self.log(tr("step2_cannot_read_inner_lat_north", "❌ 无法读取内网格北纬参数"))
                return

            # 使用新的缩放逻辑计算外网格参数（从内网格放大）
            result = self._scale_grid(
                inner_lon_west, inner_lon_east,
                inner_lat_south, inner_lat_north,
                inner_dx, inner_dy,
                scale=N, grid_type='inner'
            )

            # 更新外网格输入框（不修改 DX 和 DY）
            self.lon_west_edit.setText(f"{result['lon_w']:.2f}")
            self.lon_east_edit.setText(f"{result['lon_e']:.2f}")
            self.lat_south_edit.setText(f"{result['lat_s']:.2f}")
            self.lat_north_edit.setText(f"{result['lat_n']:.2f}")

            self.log(tr("step2_outer_grid_set", "✅ 已根据嵌套收缩系数 N={n} 设置外网格范围（基于内网格中心点放大）").format(n=N))
            self.log(tr("step2_outer_grid_coords", "   外网格西经: {lon_w:.2f}, 东经: {lon_e:.2f}").format(lon_w=result['lon_w'], lon_e=result['lon_e']))
            self.log(tr("step2_outer_grid_lat", "   外网格南纬: {lat_s:.2f}, 北纬: {lat_n:.2f}").format(lat_s=result['lat_s'], lat_n=result['lat_n']))

        except Exception as e:
            self.log(tr("step2_outer_grid_set_failed", "❌ 设置外网格失败: {error}").format(error=str(e)))
            import traceback
            traceback.print_exc()

    def apply_and_create_grid(self):
        """应用配置并生成网格（合并两步为一步）- 在后台线程中执行"""
        # 禁用按钮，防止重复点击
        self.btn_create_grid.setEnabled(False)
        self.btn_create_grid.setText(tr("step2_create_grid_ing", "生成网格中..."))

        # 在后台线程中执行生成网格操作
        thread = threading.Thread(target=self._run_create_grid_thread, daemon=True)
        thread.start()

    def _run_create_grid_thread(self):
        """在后台线程中执行生成网格操作"""
        try:
            self.run_create_grid()
        finally:
            # 无论成功或失败，都恢复按钮状态（需要在主线程中执行）
            QtCore.QTimer.singleShot(0, self._restore_create_grid_button)

    def _restore_create_grid_button(self):
        """恢复生成网格按钮状态（在主线程中执行）"""
        self.btn_create_grid.setEnabled(True)
        self.btn_create_grid.setText(tr("step2_create_grid", "生成网格"))

    def run_create_grid(self):
        """执行网格生成（MATLAB 或 Python 版本）并动态输出日志（在后台线程中执行）"""
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            self.log_signal.emit(tr("step2_workdir_not_exists", "❌ 当前工作目录不存在！"))
            return

        # 检查网格类型
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        is_nested = self._is_nested_grid(grid_type)

        # 经纬度不能为空（不允许空值生成网格）
        def _is_empty_edit(edit):
            try:
                return not edit.text().strip()
            except Exception:
                return True

        missing_fields = []
        if _is_empty_edit(self.lon_west_edit):
            missing_fields.append(tr("step2_lon_west", "西经:"))
        if _is_empty_edit(self.lon_east_edit):
            missing_fields.append(tr("step2_lon_east", "东经:"))
        if _is_empty_edit(self.lat_south_edit):
            missing_fields.append(tr("step2_lat_south", "南纬:"))
        if _is_empty_edit(self.lat_north_edit):
            missing_fields.append(tr("step2_lat_north", "北纬:"))

        if is_nested:
            if _is_empty_edit(self.inner_lon_west_edit):
                missing_fields.append(tr("step2_lon_west", "西经:") + tr("step2_inner_params", "内网格参数"))
            if _is_empty_edit(self.inner_lon_east_edit):
                missing_fields.append(tr("step2_lon_east", "东经:") + tr("step2_inner_params", "内网格参数"))
            if _is_empty_edit(self.inner_lat_south_edit):
                missing_fields.append(tr("step2_lat_south", "南纬:") + tr("step2_inner_params", "内网格参数"))
            if _is_empty_edit(self.inner_lat_north_edit):
                missing_fields.append(tr("step2_lat_north", "北纬:") + tr("step2_inner_params", "内网格参数"))

        if missing_fields:
            self.log_signal.emit(tr("step2_latlon_empty_blocked", "❌ 经纬度不能为空，缺少：{fields}").format(fields=", ".join(missing_fields)))
            return

        # 如果是嵌套网格，需要分别生成外网格和内网格
        if is_nested:
            # 创建coarse和fine文件夹
            coarse_dir = os.path.join(self.selected_folder, "coarse")
            fine_dir = os.path.join(self.selected_folder, "fine")
            os.makedirs(coarse_dir, exist_ok=True)
            os.makedirs(fine_dir, exist_ok=True)
            
            self.log_signal.emit("=" * 70)
            self.log_signal.emit(tr("step2_created_folders", "📁 已创建文件夹: coarse 和 fine"))

            # 生成外网格（coarse）
            self.log_signal.emit(tr("step2_start_outer_grid", "🔄 开始生成外网格（coarse）..."))

            # 获取外网格参数
            try:
                outer_dx = float(self.dx_edit.text().strip()) if self.dx_edit.text().strip() else float(DX)
            except (ValueError, AttributeError):
                outer_dx = float(DX) if DX else 0.05

            try:
                outer_dy = float(self.dy_edit.text().strip()) if self.dy_edit.text().strip() else float(DY)
            except (ValueError, AttributeError):
                outer_dy = float(DY) if DY else 0.05

            try:
                outer_lon_west = float(self.lon_west_edit.text().strip()) if self.lon_west_edit.text().strip() else float(LONGITUDE_WEST)
            except (ValueError, AttributeError):
                outer_lon_west = float(LONGITUDE_WEST) if LONGITUDE_WEST else 110.0

            try:
                outer_lon_east = float(self.lon_east_edit.text().strip()) if self.lon_east_edit.text().strip() else float(LONGITUDE_EAST)
            except (ValueError, AttributeError):
                outer_lon_east = float(LONGITUDE_EAST) if LONGITUDE_EAST else 130.0

            try:
                outer_lat_south = float(self.lat_south_edit.text().strip()) if self.lat_south_edit.text().strip() else float(LATITUDE_SORTH)
            except (ValueError, AttributeError):
                outer_lat_south = float(LATITUDE_SORTH) if LATITUDE_SORTH else 10.0

            try:
                outer_lat_north = float(self.lat_north_edit.text().strip()) if self.lat_north_edit.text().strip() else float(LATITUDE_NORTH)
            except (ValueError, AttributeError):
                outer_lat_north = float(LATITUDE_NORTH) if LATITUDE_NORTH else 30.0

            # 生成外网格
            outer_success = self._generate_single_grid(
                coarse_dir, outer_dx, outer_dy,
                outer_lon_west, outer_lon_east,
                outer_lat_south, outer_lat_north
            )

            if not outer_success:
                self.log_signal.emit(tr("step2_outer_grid_failed", "❌ 外网格生成失败！"))
                return

            # 生成内网格（fine）
            self.log_signal.emit("=" * 70)
            self.log_signal.emit(tr("step2_start_inner_grid", "🔄 开始生成内网格（fine）..."))

            # 获取内网格参数
            try:
                inner_dx = float(self.inner_dx_edit.text().strip()) if self.inner_dx_edit.text().strip() else float(DX)
            except (ValueError, AttributeError):
                inner_dx = float(DX) if DX else 0.05

            try:
                inner_dy = float(self.inner_dy_edit.text().strip()) if self.inner_dy_edit.text().strip() else float(DY)
            except (ValueError, AttributeError):
                inner_dy = float(DY) if DY else 0.05

            try:
                inner_lon_west = float(self.inner_lon_west_edit.text().strip()) if self.inner_lon_west_edit.text().strip() else float(LONGITUDE_WEST)
            except (ValueError, AttributeError):
                inner_lon_west = float(LONGITUDE_WEST) if LONGITUDE_WEST else 110.0

            try:
                inner_lon_east = float(self.inner_lon_east_edit.text().strip()) if self.inner_lon_east_edit.text().strip() else float(LONGITUDE_EAST)
            except (ValueError, AttributeError):
                inner_lon_east = float(LONGITUDE_EAST) if LONGITUDE_EAST else 130.0

            try:
                inner_lat_south = float(self.inner_lat_south_edit.text().strip()) if self.inner_lat_south_edit.text().strip() else float(LATITUDE_SORTH)
            except (ValueError, AttributeError):
                inner_lat_south = float(LATITUDE_SORTH) if LATITUDE_SORTH else 10.0

            try:
                inner_lat_north = float(self.inner_lat_north_edit.text().strip()) if self.inner_lat_north_edit.text().strip() else float(LATITUDE_NORTH)
            except (ValueError, AttributeError):
                inner_lat_north = float(LATITUDE_NORTH) if LATITUDE_NORTH else 30.0

            # 生成内网格
            inner_success = self._generate_single_grid(
                fine_dir, inner_dx, inner_dy,
                inner_lon_west, inner_lon_east,
                inner_lat_south, inner_lat_north
            )

            if not inner_success:
                self.log_signal.emit(tr("step2_inner_grid_failed", "❌ 内网格生成失败！"))
                return

            self.log_signal.emit("=" * 70)
            self.log_signal.emit(tr("step2_nested_complete", "✅ 嵌套网格生成完毕！"))
            return

        # 普通网格：使用 _generate_single_grid
        output_dir = self.selected_folder
        os.makedirs(output_dir, exist_ok=True)

        # 获取参数值（优先使用 UI 输入，否则使用全局变量）
        try:
            dx_value = float(self.dx_edit.text().strip()) if self.dx_edit.text().strip() else float(DX)
        except (ValueError, AttributeError):
            dx_value = float(DX) if DX else 0.05

        try:
            dy_value = float(self.dy_edit.text().strip()) if self.dy_edit.text().strip() else float(DY)
        except (ValueError, AttributeError):
            dy_value = float(DY) if DY else 0.05

        try:
            lon_west = float(self.lon_west_edit.text().strip()) if self.lon_west_edit.text().strip() else float(LONGITUDE_WEST)
        except (ValueError, AttributeError):
            lon_west = float(LONGITUDE_WEST) if LONGITUDE_WEST else 110.0

        try:
            lon_east = float(self.lon_east_edit.text().strip()) if self.lon_east_edit.text().strip() else float(LONGITUDE_EAST)
        except (ValueError, AttributeError):
            lon_east = float(LONGITUDE_EAST) if LONGITUDE_EAST else 130.0

        try:
            lat_south = float(self.lat_south_edit.text().strip()) if self.lat_south_edit.text().strip() else float(LATITUDE_SORTH)
        except (ValueError, AttributeError):
            lat_south = float(LATITUDE_SORTH) if LATITUDE_SORTH else 10.0

        try:
            lat_north = float(self.lat_north_edit.text().strip()) if self.lat_north_edit.text().strip() else float(LATITUDE_NORTH)
        except (ValueError, AttributeError):
            lat_north = float(LATITUDE_NORTH) if LATITUDE_NORTH else 30.0

        # 生成普通网格
        success = self._generate_single_grid(
            output_dir, dx_value, dy_value,
            lon_west, lon_east, lat_south, lat_north
        )
        
        if not success:
            self.log_signal.emit(tr("step2_grid_create_failed", "错误：网格创建失败"))

    def _generate_single_grid(self, output_dir, dx_value, dy_value, lon_west, lon_east, lat_south, lat_north):
        """生成单个网格的辅助函数（带缓存机制）"""
        try:
            # 根据 GRIDGEN 版本选择执行方式
            current_config = load_config()
            gridgen_version = current_config.get("GRIDGEN_VERSION", "MATLAB")

            # 确保输出目录存在
            os.makedirs(output_dir, exist_ok=True)

            if gridgen_version == "Python":
                # Python 版本
                gridgen_path = self._get_gridgen_path()
                python_version_path = os.path.join(gridgen_path, "python")
                if not os.path.exists(python_version_path):
                    self.log_signal.emit(tr("step2_python_dir_not_found", "❌ 未找到 Python 版本目录：{path}").format(path=python_version_path))
                    return False

            # 获取参考数据目录（从配置或默认路径）
            ref_dir = self._get_reference_data_path()

            # 规范化输出目录
            # 规范化输出目录（强制绝对路径，避免相对路径导致输出位置错误）
            output_dir_norm = os.path.abspath(os.path.normpath(output_dir))

            if gridgen_version == "Python":
                # 规范化 Python 版本路径
                python_version_path_norm = os.path.normpath(python_version_path)

            self.log_signal.emit(tr("step2_params", "   参数: dx={dx}, dy={dy}").format(dx=dx_value, dy=dy_value))
            self.log_signal.emit(tr("step2_lon_range", "   经度范围: [{min}, {max}]").format(min=lon_west, max=lon_east))
            self.log_signal.emit(tr("step2_lat_range", "   纬度范围: [{min}, {max}]").format(min=lat_south, max=lat_north))
            self.log_signal.emit(tr("step2_output_dir", "   输出目录: {dir}").format(dir=output_dir_norm))

            # 从配置中读取水深数据和海岸边界精度
            bathymetry_config = current_config.get("BATHYMETRY", "GEBCO")
            coastline_precision_config = current_config.get("COASTLINE_PRECISION", tr("step2_coastline_precision_full", "最高"))
            
            # 转换参数值格式：GEBCO/ETOP1/ETOP2 -> gebco/etopo1/etopo2
            bathymetry_map = {
                "GEBCO": "gebco",
                "ETOP1": "etopo1",
                "ETOP2": "etopo2"
            }
            ref_grid = bathymetry_map.get(bathymetry_config.upper(), "gebco")
            
            # 转换海岸边界精度：最高/高/中/低 -> full/high/inter/low
            # 支持翻译后的文本
            full_text = tr("step2_coastline_precision_full", "最高")
            high_text = tr("step2_coastline_precision_high", "高")
            inter_text = tr("step2_coastline_precision_inter", "中")
            low_text = tr("step2_coastline_precision_low", "低")
            coastline_map = {
                full_text: "full",
                "最高": "full",  # 保持向后兼容
                high_text: "high",
                "高": "high",  # 保持向后兼容
                inter_text: "inter",
                "中": "inter",  # 保持向后兼容
                low_text: "low",
                "低": "low"  # 保持向后兼容
            }
            boundary = coastline_map.get(coastline_precision_config, "full")
            
            # 检查缓存（使用原始配置值）
            cache_key = self._get_grid_cache_key(dx_value, dy_value, lon_west, lon_east, lat_south, lat_north, ref_dir, bathymetry_config, coastline_precision_config)
            cache_path = self._check_grid_cache(cache_key)

            if cache_path:
                self.log_signal.emit(tr("step2_cache_found", "✅ 找到匹配的网格缓存，直接使用缓存的网格"))
                self._load_grid_from_cache(cache_path, output_dir_norm)
                return True

            self.log_signal.emit(tr("step2_cache_not_found", "🔄 未找到匹配的缓存，开始生成新网格..."))

            if gridgen_version == "Python":
                # 确保 lat_south < lat_north（对于南纬，需要交换）
                lat_start = min(lat_south, lat_north)
                lat_end = max(lat_south, lat_north)
                
                # 构建 Python 脚本命令，使用 repr() 自动处理路径转义
                python_script = f'''
import sys
sys.path.insert(0, {repr(python_version_path_norm)})
from create_grid import create_grid
create_grid(
            dx={dx_value},
            dy={dy_value},
            lon_range=[{lon_west}, {lon_east}],
            lat_range=[{lat_start}, {lat_end}],
            out_dir={repr(output_dir_norm)},
            ref_dir={repr(ref_dir)},
            ref_grid={repr(ref_grid)},
            boundary={repr(boundary)},
        )                
        '''
                
                try:
                    env = os.environ.copy()
                    env['PYTHONUNBUFFERED'] = '1'
                    
                    proc = subprocess.Popen(
                        [sys.executable, '-u', '-c', python_script],
                        cwd=python_version_path_norm,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        env=env
                    )
                    
                    from queue import Queue, Empty
                    output_queue = Queue()
                    read_finished = threading.Event()
                    
                    def read_output_thread():
                        try:
                            for line in iter(proc.stdout.readline, ''):
                                line_stripped = line.rstrip()
                                if line_stripped:
                                    output_queue.put(line_stripped)
                            remaining = proc.stdout.read()
                            if remaining:
                                for l in remaining.splitlines():
                                    if l.strip():
                                        output_queue.put(l.strip())
                        finally:
                            read_finished.set()
                    
                    reader_thread = threading.Thread(target=read_output_thread, daemon=True)
                    reader_thread.start()
                    
                    while not read_finished.is_set() or not output_queue.empty():
                        try:
                            line = output_queue.get(timeout=0.05)
                            self.log_signal.emit(line)
                        except Empty:
                            pass
                    
                    reader_thread.join(timeout=2)
                    proc.wait()
                    ret = proc.returncode
                    
                    if ret == 0:
                        self.log_signal.emit(tr("step2_python_complete", "✅ Python 版 gridgen 执行完成！"))
                        
                        # 验证生成的文件是否完整
                        is_valid, msg = self._validate_grid_files(output_dir_norm)
                        if not is_valid:
                            self.log_signal.emit(tr("step2_grid_validation_failed", "❌ 网格文件验证失败: {msg}").format(msg=msg))
                            insufficient_rows_text = tr("step2_insufficient_rows", "行数不足")
                            if "dxdy > 0.05" in msg or insufficient_rows_text in msg or "行数不足" in msg:
                                self.log_signal.emit(tr("step2_dxdy_large_warning", "⚠️ 这可能是由于 dxdy > 0.05 导致的文件写入不完整问题"))
                                self.log_signal.emit(tr("step2_dxdy_large_suggestion", "💡 建议：请检查 create_grid 脚本是否正确处理了较大的 dxdy 值"))
                            return False
                        else:
                            self.log_signal.emit(tr("step2_grid_validation_success", "✅ {msg}").format(msg=msg))
                        
                        # 保存到缓存（使用原始配置值）
                        try:
                            self._save_grid_to_cache(cache_key, output_dir_norm, dx_value, dy_value, 
                                                    lon_west, lon_east, lat_south, lat_north, ref_dir, bathymetry_config, coastline_precision_config)
                            self.log_signal.emit(tr("step2_cache_saved", "✅ 已保存网格到缓存（{key}...）").format(key=cache_key[:8]))
                        except Exception as cache_error:
                            self.log_signal.emit(tr("step2_cache_save_failed", "⚠️ 保存缓存失败: {error}").format(error=cache_error))
                        return True
                    else:
                        self.log_signal.emit(tr("step2_python_failed", "❌ Python 版 gridgen 执行失败，返回码: {code}").format(code=ret))
                        return False
                        
                except Exception as e:
                    self.log_signal.emit(tr("step2_python_error", "❌ 执行 Python 版 gridgen 出错: {error}").format(error=e))
                    import traceback
                    error_details = traceback.format_exc()
                    for line in error_details.splitlines():
                        self.log_signal.emit(line)
                    return False
            else:
                # MATLAB 版本
                matlab_path = MATLAB_PATH
                if not os.path.exists(matlab_path):
                    self.log_signal.emit(tr("step2_matlab_not_found", "❌ 未找到 MATLAB 可执行文件：{path}").format(path=matlab_path))
                    return False
                
                self.log_signal.emit(tr("step2_start_create_grid_m", "🔄 开始执行 create_grid.m ..."))
                self.log_signal.emit(tr("step2_params", "   参数: dx={dx}, dy={dy}").format(dx=dx_value, dy=dy_value))
                self.log_signal.emit(tr("step2_lon_range", "   经度范围: [{min}, {max}]").format(min=lon_west, max=lon_east))
                self.log_signal.emit(tr("step2_lat_range", "   纬度范围: [{min}, {max}]").format(min=lat_south, max=lat_north))
                self.log_signal.emit(tr("step2_output_dir", "   输出目录: {dir}").format(dir=output_dir_norm))
                
                is_windows = platform.system() == 'Windows'
                
                # 规范化路径
                gridgen_bin_path = self._get_gridgen_bin_path()
                matlab_bin_dir_norm = os.path.normpath(gridgen_bin_path) if gridgen_bin_path else None
                output_dir_norm = os.path.abspath(os.path.normpath(output_dir))
                
                # 从配置中读取水深数据和海岸边界精度
                bathymetry_config = current_config.get("BATHYMETRY", "GEBCO")
                coastline_precision_config = current_config.get("COASTLINE_PRECISION", tr("step2_coastline_precision_full", "最高"))
                
                # 转换参数值格式：GEBCO/ETOP1/ETOP2 -> gebco/etopo1/etopo2
                bathymetry_map = {
                    "GEBCO": "gebco",
                    "ETOP1": "etopo1",
                    "ETOP2": "etopo2"
                }
                ref_grid = bathymetry_map.get(bathymetry_config.upper(), "gebco")
                
                # 转换海岸边界精度：最高/高/中/低 -> full/high/inter/low
                # 支持翻译后的文本
                full_text = tr("step2_coastline_precision_full", "最高")
                high_text = tr("step2_coastline_precision_high", "高")
                inter_text = tr("step2_coastline_precision_inter", "中")
                low_text = tr("step2_coastline_precision_low", "低")
                coastline_map = {
                    full_text: "full",
                    "最高": "full",  # 保持向后兼容
                    high_text: "high",
                    "高": "high",  # 保持向后兼容
                    inter_text: "inter",
                    "中": "inter",  # 保持向后兼容
                    low_text: "low",
                    "低": "low"  # 保持向后兼容
                }
                boundary = coastline_map.get(coastline_precision_config, "full")
                
                # 构建 MATLAB 命令，直接调用 create_grid 并传入参数
                # 注意：MATLAB 的路径需要使用正斜杠（MATLAB 在 Windows 上也支持正斜杠）
                matlab_bin_dir = matlab_bin_dir_norm.replace('\\', '/') if matlab_bin_dir_norm else None
                matlab_out_dir = output_dir_norm.replace('\\', '/')
                
                matlab_cmd = (
                    f"warning('off', 'all'); "
                    f"feature('DefaultCharacterSet', 'UTF8'); "
                    f"addpath('{matlab_bin_dir}'); "
                    f"create_grid('dx', {dx_value}, 'dy', {dy_value}, "
                    f"'lon_range', [{lon_west}, {lon_east}], "
                    f"'lat_range', [{lat_south}, {lat_north}], "
                    f"'out_dir', '{matlab_out_dir}', "
                    f"'ref_grid', '{ref_grid}', "
                    f"'boundary', '{boundary}');"
                )
                
                cmd = [matlab_path]
                if not is_windows:
                    cmd.append("-nodisplay")
                cmd.extend([
                    "-nosplash",
                    "-nodesktop",
                    "-batch",
                    matlab_cmd
                ])
                
                env = os.environ.copy()
                env['MATLAB_JAVA'] = env.get('MATLAB_JAVA', '')
                env['_JAVA_OPTIONS'] = '-Djava.awt.headless=true -XX:+UseG1GC'
                
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1,
                    env=env
                )
                
                for line in iter(proc.stdout.readline, ''):
                    line = line.rstrip()
                    if 'IEEE_UNDERFLOW_FLAG' in line or 'floating-point exceptions' in line.lower():
                        continue
                    if 'WARNING: package sun.awt.X11' in line or 'not in java.desktop' in line:
                        continue
                    # Filter MATLAB macOS IPC socket warning (harmless warning)
                    if 'Command `service` threw an exception' in line or 'Path length for IPC socket' in line:
                        continue
                    if line.strip():
                        self.log_signal.emit(line)
                
                proc.stdout.close()
                proc.wait()
                ret = proc.returncode
                
                if ret == 0:
                    self.log_signal.emit(tr("step2_matlab_complete", "✅ MATLAB 版 gridgen 执行完成！"))
                    
                    # 保存到缓存（使用原始配置值）
                    try:
                        self._save_grid_to_cache(cache_key, output_dir_norm, dx_value, dy_value, 
                                                lon_west, lon_east, lat_south, lat_north, ref_dir, bathymetry_config, coastline_precision_config)
                        self.log_signal.emit(tr("step2_cache_saved", "✅ 已保存网格到缓存（{key}...）").format(key=cache_key[:8]))
                    except Exception as cache_error:
                        self.log_signal.emit(tr("step2_cache_save_failed", "⚠️ 保存缓存失败: {error}").format(error=cache_error))
                    return True
                else:
                    self.log_signal.emit(tr("step2_matlab_failed", "❌ MATLAB 版 gridgen 执行失败，返回码: {code}").format(code=ret))
                    return False
                    
        except Exception as e:
            self.log_signal.emit(tr("step2_create_error", "❌ 生成网格时出错: {error}").format(error=e))
            import traceback
            error_details = traceback.format_exc()
            for line in error_details.splitlines():
                self.log_signal.emit(line)
            return False

    def visualize_grid_files(self):
        """可视化网格文件：读取四个文件并生成可视化图片"""
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            self.log(tr("step2_please_select_folder", "❌ 请先选择或创建文件夹！"))
            return

        # 检查网格类型
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))

        # 如果是嵌套网格，需要分别可视化外网格和内网格
        if self._is_nested_grid(grid_type):
            coarse_dir = os.path.join(self.selected_folder, "coarse")
            fine_dir = os.path.join(self.selected_folder, "fine")

            if not os.path.isdir(coarse_dir) or not os.path.isdir(fine_dir):
                self.log(tr("step2_coarse_fine_not_found", "❌ 未找到 coarse 或 fine 文件夹，请先生成嵌套网格"))
                return

            self._visualize_single_grid(coarse_dir, tr("step2_outer_grid_title", "外网格（coarse）"))

            # 可视化内网格（fine）
            self.log("")
            self._visualize_single_grid(fine_dir, tr("step2_inner_grid_title", "内网格（fine）"))

            self.log("")
            self.log("=" * 60)
            self.log(tr("step2_nested_grid_visualization_complete", "✅ 嵌套网格可视化完成！"))
            self.log("=" * 60)
            return

        # 普通网格：保持原有逻辑
        self._visualize_single_grid(self.selected_folder, tr("step2_grid_type_normal", "普通网格"))

    def _visualize_single_grid(self, grid_dir, grid_name=""):
        """可视化单个网格目录的文件"""
        photo_dir = os.path.join(grid_dir, "photo", "grid")
        os.makedirs(photo_dir, exist_ok=True)

        # 检查文件是否存在
        grid_files = {
            'meta': os.path.join(grid_dir, 'grid.meta'),
            'bot': os.path.join(grid_dir, 'grid.bot'),
            'mask': os.path.join(grid_dir, 'grid.mask'),
            'obst': os.path.join(grid_dir, 'grid.obst')
        }

        missing_files = [name for name, path in grid_files.items() if not os.path.exists(path)]
        if missing_files:
            missing_files_str = ', '.join([f'grid.{name}' for name in missing_files])
            self.log(tr("step2_grid_missing_files", "❌ {grid_name}缺少必要的网格文件: {missing_files}").format(grid_name=grid_name, missing_files=missing_files_str))
            self.log(tr("step2_please_generate_grid", "   请先执行生成网格操作"))
            return

        try:
            # 1. 读取 meta 文件获取经纬度信息
            lon, lat = self._read_ww3meta(grid_files['meta'])
            if lon is None or lat is None:
                self.log(tr("step2_read_meta_failed", "❌ 读取 grid.meta 文件失败"))
                return

            Ny, Nx = lon.shape

            # 2. 读取并可视化各个文件（参考 MATLAB create_grid.m 的实现）
            # 2.1 先读取 mask（用于标记陆地位置）
            mask = self._read_ww3file(grid_files['mask'], Nx, Ny)
            if mask is None:
                self.log(tr("step2_cannot_read_mask", "   ⚠️ 警告: 无法读取 mask 文件，将跳过陆地标记"))
                loc = None
            else:
                loc = (mask == 0)  # 陆地位置（mask == 0），参考 MATLAB: loc = m4 == 0

            # 2.2 可视化 bathymetry (grid.bot)
            # 参考 MATLAB: figure(1); loc = m4 == 0; d2 = depth; d2(loc) = NaN; pcolor(...); shading interp;
            depth = self._read_ww3file(grid_files['bot'], Nx, Ny)
            if depth is not None:
                # 转换为实际深度（除以 scale = 1000）
                depth = depth.astype(float) / 1000.0
                # 将陆地位置设为 NaN（参考 MATLAB: d2(loc) = NaN）
                if loc is not None:
                    # 检查 depth 和 loc 的形状是否匹配
                    if depth.shape == loc.shape:
                        depth[loc] = np.nan
                    else:
                        # 如果形状不匹配，只对重叠部分应用索引
                        min_rows = min(depth.shape[0], loc.shape[0])
                        min_cols = min(depth.shape[1], loc.shape[1])
                        depth[:min_rows, :min_cols][loc[:min_rows, :min_cols]] = np.nan
                        self.log(tr("step2_shape_mismatch_depth", "   ⚠️ 警告: depth 形状 {depth_shape} 与 mask 形状 {mask_shape} 不匹配，已调整").format(depth_shape=depth.shape, mask_shape=loc.shape))
                # 深度数据保持原样（负数表示海平面以下，不需要取绝对值）
                valid_depth = depth[~np.isnan(depth)]
                # 深度范围检查（静默处理）

                self._plot_grid_data(lon, lat, depth, 'Bathymetry',
                                   os.path.join(photo_dir, 'grid_bathymetry.png'),
                                   cmap='jet', shading='interp')

            # 2.3 可视化 mask (grid.mask)
            # 参考 MATLAB: figure(2); pcolor(lon, lat, m4); shading flat;
            if mask is not None:
                self._plot_grid_data(lon, lat, mask, 'Final Land-Sea Mask',
                                   os.path.join(photo_dir, 'grid_mask.png'),
                                   cmap='jet', shading='flat')

            # 2.4 可视化 obstruction (grid.obst)
            # 参考 MATLAB: figure(3/4); d2 = sx1/sy1; d2(loc) = NaN; pcolor(...); shading flat;
            sx, sy = self._read_ww3obstr(grid_files['obst'], Nx, Ny)
            if sx is not None and sy is not None:
                sx = sx.astype(float) / 100.0  # 转换为实际值（除以 scale）
                sy = sy.astype(float) / 100.0

                # 将陆地位置设为 NaN（参考 MATLAB: d2(loc) = NaN）
                if loc is not None:
                    # 检查 sx/sy 和 loc 的形状是否匹配
                    if sx.shape == loc.shape and sy.shape == loc.shape:
                        sx[loc] = np.nan
                        sy[loc] = np.nan
                    else:
                        # 如果形状不匹配，只对重叠部分应用索引
                        min_rows = min(sx.shape[0], loc.shape[0])
                        min_cols = min(sx.shape[1], loc.shape[1])
                        sx[:min_rows, :min_cols][loc[:min_rows, :min_cols]] = np.nan
                        sy[:min_rows, :min_cols][loc[:min_rows, :min_cols]] = np.nan
                        self.log(tr("step2_shape_mismatch_sx_sy", "   ⚠️ 警告: sx/sy 形状 {sx_shape} 与 mask 形状 {mask_shape} 不匹配，已调整").format(sx_shape=sx.shape, mask_shape=loc.shape))

                # X 方向障碍物
                self._plot_grid_data(lon, lat, sx, 'Sx Obstruction',
                                   os.path.join(photo_dir, 'grid_obstruction_x.png'),
                                   cmap='jet', shading='flat')

                # Y 方向障碍物
                self._plot_grid_data(lon, lat, sy, 'Sy Obstruction',
                                   os.path.join(photo_dir, 'grid_obstruction_y.png'),
                                   cmap='jet', shading='flat')

            # 显示所有生成的图片
            image_files = [
                os.path.join(photo_dir, 'grid_bathymetry.png'),
                os.path.join(photo_dir, 'grid_mask.png'),
                os.path.join(photo_dir, 'grid_obstruction_x.png'),
                os.path.join(photo_dir, 'grid_obstruction_y.png')
            ]
            # 只显示存在的图片
            existing_images = [f for f in image_files if os.path.exists(f)]
            if existing_images:
                # 使用抽屉显示图片（与风场图一致）
                try:
                    self._show_images_in_drawer(existing_images)
                except AttributeError:
                    # 如果抽屉方法不存在，回退到弹窗
                    title_suffix = f" - {grid_name}" if grid_name else ""
                    self._show_images_window(existing_images, title_suffix=title_suffix)
                self.log(tr("step2_grid_visualization_complete", "✅ {grid_name}可视化完成，图片已保存到: {photo_dir}").format(grid_name=grid_name, photo_dir=photo_dir))

        except Exception as e:
            self.log(tr("step2_visualization_failed", "❌ {grid_name}可视化网格文件失败: {error}").format(grid_name=grid_name, error=e))
            import traceback
            for line in traceback.format_exc().splitlines():
                self.log(line)

    def _show_images_window(self, image_files, title_suffix=""):
        """在一个窗口中显示多张图片"""
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("step2_grid_visualization_result", "网格可视化结果{title_suffix}").format(title_suffix=title_suffix))
        dialog.resize(1300, 950)

        # 创建滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        # 创建内容 widget
        content = QWidget()
        grid_layout = QGridLayout(content)
        grid_layout.setSpacing(10)
        grid_layout.setContentsMargins(10, 10, 10, 10)

        # 按 2 列自动布局，标题不足则回退为 Image X
        titles = ['Bathymetry', 'Land-Sea Mask', 'Sx Obstruction', 'Sy Obstruction']

        for idx, image_file in enumerate(image_files):
            row = idx // 2
            col = idx % 2

            # 创建带圆角边框的容器
            container = QFrame()
            container.setStyleSheet("""
                QFrame {
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
            """)
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(8, 8, 8, 8)
            container_layout.setSpacing(5)

            # 标题
            title_label = QLabel(titles[idx] if idx < len(titles) else f"Image {idx+1}")
            title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_label.setStyleSheet("font-weight: bold; font-size: 14px; border: none; background: transparent;")
            container_layout.addWidget(title_label)

            # 图片 - 等比例缩小（保持宽高比，不裁剪）
            img_label = QLabel()
            img_label.setStyleSheet("border: none; background: transparent;")
            pixmap = QPixmap(image_file)
            # KeepAspectRatio 保持原宽高比缩放，不会裁剪
            scaled_pixmap = pixmap.scaled(620, 450, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            img_label.setPixmap(scaled_pixmap)
            img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # 设置鼠标指针为手型，表示可点击
            img_label.setCursor(Qt.CursorShape.PointingHandCursor)
            # 添加点击事件，点击后用系统默认方式打开图片
            def make_click_handler(path):
                def handle_click(event):
                    self.open_image_file(path)
                return handle_click
            img_label.mousePressEvent = make_click_handler(image_file)
            container_layout.addWidget(img_label)

            grid_layout.addWidget(container, row, col)

        scroll.setWidget(content)

        # 主布局
        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

        dialog.exec()

    def _read_ww3meta(self, fname):
        """读取 WAVEWATCH III meta 文件，返回经纬度数组"""
        try:
            with open(fname, 'r') as fid:
                # 跳过前45行注释
                for i in range(45):
                    fid.readline()

                # 读取网格类型
                line = fid.readline().strip()
                gtype = line.split()[0].strip("'\"")

                if gtype == 'RECT':
                    # 读取网格参数
                    # 第一行：Nx Ny
                    line = fid.readline().strip()
                    values = line.split()
                    Nx = int(float(values[0]))  # 先转 float 再转 int，处理 '401' 或 '401.00' 格式
                    Ny = int(float(values[1]))

                    # 第二行：dx dy scale
                    line = fid.readline().strip()
                    values = line.split()
                    dx = float(values[0])
                    dy = float(values[1])
                    scale = float(values[2])
                    dx = dx / scale
                    dy = dy / scale

                    # 第三行：lons lats scale
                    line = fid.readline().strip()
                    values = line.split()
                    lons = float(values[0])
                    lats = float(values[1])
                    scale = float(values[2])

                    # 生成经纬度数组
                    lon1d = lons / scale + np.arange(Nx) * dx
                    lat1d = lats / scale + np.arange(Ny) * dy

                    lon, lat = np.meshgrid(lon1d, lat1d)
                    return lon, lat
                else:
                    self.log(tr("step2_unsupported_grid_type", "❌ 不支持的网格类型: {gtype}").format(gtype=gtype))
                    return None, None
        except Exception as e:
            self.log(tr("step2_read_meta_error", "❌ 读取 meta 文件失败: {error}").format(error=e))
            return None, None

    def _read_ww3file(self, fname, Nx, Ny):
        """读取 WAVEWATCH III 格式文件（bot 或 mask）"""
        try:
            data = []
            with open(fname, 'r') as fid:
                for line in fid:
                    # 解析每行的整数
                    values = [int(x) for x in line.split()]
                    if len(values) > 0:
                        data.append(values)

            if len(data) != Ny:
                self.log(tr("step2_file_rows_mismatch", "⚠️ 警告: 文件行数 ({rows}) 与预期 ({expected}) 不匹配").format(rows=len(data), expected=Ny))

            # 转换为 numpy 数组并转置（MATLAB 格式是列优先）
            arr = np.array(data[:Ny])
            if arr.shape[1] != Nx:
                self.log(tr("step2_file_cols_mismatch", "⚠️ 警告: 文件列数 ({cols}) 与预期 ({expected}) 不匹配").format(cols=arr.shape[1], expected=Nx))

            return arr
        except Exception as e:
            self.log(tr("step2_read_file_failed_fname", "❌ 读取文件 {fname} 失败: {error}").format(fname=fname, error=e))
            return None

    def _read_ww3obstr(self, fname, Nx, Ny):
        """读取 WAVEWATCH III obstruction 文件，返回 sx 和 sy"""
        try:
            data = []
            with open(fname, 'r') as fid:
                for line in fid:
                    line = line.strip()
                    if line:  # 跳过空行
                        values = [int(x) for x in line.split()]
                        if len(values) > 0:
                            data.append(values)

            # obstruction 文件包含两个 2D 数组（可能有空行分隔）
            total_rows = len(data)
            if total_rows < Ny * 2:
                self.log(tr("step2_file_rows_less", "⚠️ 警告: 文件行数 ({rows}) 少于预期 ({expected})").format(rows=total_rows, expected=Ny * 2))
                return None, None

            # 第一个数组：sx（前 Ny 行）
            sx_data = np.array(data[:Ny])
            # 第二个数组：sy（从第 Ny 行开始，跳过可能的空行）
            # 查找第二个数组的起始位置
            sy_start = Ny
            while sy_start < len(data) and len(data[sy_start]) == 0:
                sy_start += 1

            if sy_start + Ny > len(data):
                self.log(tr("step2_cannot_find_second_array", "⚠️ 警告: 无法找到第二个数组的起始位置"))
                return None, None

            sy_data = np.array(data[sy_start:sy_start+Ny])

            if sx_data.shape[1] != Nx or sy_data.shape[1] != Nx:
                self.log(tr("step2_array_cols_mismatch", "⚠️ 警告: 数组列数与预期不匹配 (sx: {sx_shape}, sy: {sy_shape}, 预期: ({ny}, {nx}))").format(sx_shape=sx_data.shape, sy_shape=sy_data.shape, ny=Ny, nx=Nx))

            return sx_data, sy_data
        except Exception as e:
            self.log(tr("step2_read_obstruction_failed", "❌ 读取 obstruction 文件失败: {error}").format(error=e))
            import traceback
            traceback.print_exc()
            return None, None

    def _plot_grid_data(self, lon, lat, data, title, output_path, cmap='jet', vmin=None, vmax=None,
                        shading='flat', use_mask=True):
        """
        绘制网格数据并保存为图片（参考 MATLAB create_grid.m 的实现）

        参数:
        - shading: 'flat' 或 'interp'（参考 MATLAB 的 shading 命令）
        - use_mask: 是否使用地图投影（False 时使用简单的 2D 绘图，更接近 MATLAB）
        """
        try:
            # 参考 MATLAB: 使用简单的 2D 绘图，不使用地图投影
            # 这样可以更接近 MATLAB 的 pcolor 效果
            fig, ax = plt.subplots(figsize=(12, 8))

            # 设置数据范围
            if vmin is None:
                vmin = np.nanmin(data)
            if vmax is None:
                vmax = np.nanmax(data)

            # 参考 MATLAB: 使用 pcolor（在 Python 中使用 pcolormesh）
            # 对于 shading='flat'，pcolormesh 需要坐标比数据大1
            # 对于 shading='interp'/'gouraud'，可以使用相同维度
            if shading == 'interp' or shading == 'gouraud':
                # 对于 bathymetry，使用插值着色（gouraud 对应 MATLAB 的 shading interp）
                im = ax.pcolormesh(lon, lat, data, cmap=cmap, vmin=vmin, vmax=vmax, shading='gouraud')
            else:
                # 对于 mask 和 obstruction，使用 flat 着色
                # 需要调整坐标：为每个维度添加一个边界点
                Ny, Nx = data.shape
                # 计算网格间距
                if Nx > 1:
                    dx = (lon[0, -1] - lon[0, 0]) / (Nx - 1)
                    lon_edges = np.linspace(lon[0, 0] - dx/2, lon[0, -1] + dx/2, Nx + 1)
                else:
                    lon_edges = np.array([lon[0, 0] - 0.025, lon[0, 0] + 0.025])

                if Ny > 1:
                    dy = (lat[-1, 0] - lat[0, 0]) / (Ny - 1)
                    lat_edges = np.linspace(lat[0, 0] - dy/2, lat[-1, 0] + dy/2, Ny + 1)
                else:
                    lat_edges = np.array([lat[0, 0] - 0.025, lat[0, 0] + 0.025])

                lon_grid, lat_grid = np.meshgrid(lon_edges, lat_edges)
                im = ax.pcolormesh(lon_grid, lat_grid, data, cmap=cmap, vmin=vmin, vmax=vmax, shading='flat')

            # 设置标题和标签（参考 MATLAB）
            ax.set_title(title, fontsize=14, fontweight='bold')
            ax.set_xlabel(tr("step2_map_longitude", "经度"), fontsize=12)
            ax.set_ylabel(tr("step2_map_latitude", "纬度"), fontsize=12)

            # 参考 MATLAB: axis equal（保持纵横比）
            ax.set_aspect('equal', adjustable='box')

            # 添加颜色条（参考 MATLAB: colorbar）
            cbar = plt.colorbar(im, ax=ax)
            cbar.set_label(title, fontsize=10)

            # 保存图片
            plt.tight_layout()
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            plt.close(fig)

        except Exception as e:
            self.log(tr("step2_draw_image_failed", "❌ 绘制图片失败 ({title}): {error}").format(title=title, error=e))
            import traceback
            traceback.print_exc()
