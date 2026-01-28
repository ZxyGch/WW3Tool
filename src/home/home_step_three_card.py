import sys
import os
import json
import time
import numpy as np
import glob
import subprocess
import shutil
import threading
import multiprocessing
import requests
from base64 import b64encode
# 在 Windows 上需要设置启动方法
if hasattr(multiprocessing, 'set_start_method'):
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass  # 如果已经设置过，忽略错误
from multiprocessing import Process, Queue
import socket
import paramiko
import locale
import matplotlib
matplotlib.use('QtAgg')  # 使用 Qt 后端（兼容 PyQt6）
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib import cm
from netCDF4 import Dataset, num2date
import netCDF4 as nc
from datetime import datetime, timedelta
from PIL import Image
import platform
import re
import cv2
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import QEvent, Qt
QSplitter = QtWidgets.QSplitter
from qfluentwidgets import FluentWindow, PrimaryPushButton, LineEdit, TextEdit, InfoBar, setTheme, Theme
from qfluentwidgets import NavigationItemPosition, NavigationWidget, FluentIcon, ComboBox, TableWidget
from PyQt6.QtGui import QColor, QIcon
from qfluentwidgets import MessageBoxBase
from PyQt6.QtWidgets import QTableWidgetItem, QHeaderView, QScrollArea, QSizePolicy
from PyQt6.QtGui import QPixmap
QApplication = QtWidgets.QApplication
QWidget = QtWidgets.QWidget
QVBoxLayout = QtWidgets.QVBoxLayout
QHBoxLayout = QtWidgets.QHBoxLayout
QStackedWidget = QtWidgets.QStackedWidget
QFileDialog = QtWidgets.QFileDialog
QDialog = QtWidgets.QDialog
QLabel = QtWidgets.QLabel
QGridLayout = QtWidgets.QGridLayout
QRadioButton = QtWidgets.QRadioButton
QButtonGroup = QtWidgets.QButtonGroup
QSpinBox = QtWidgets.QSpinBox
from setting.config import *
from plot.workers import _match_ww3_jason3_worker, _run_jason3_swh_worker, _make_wave_maps_worker
from setting.language_manager import tr
from .utils import create_header_card

class HomeStepThreeCard:
    """第三步：计算模式 Mixin。含 UI 创建、选点/航迹逻辑；非第三步方法 _set_cpu、_set_st、_read_grid_meta_bounds、_read_single_grid_meta_bounds 仍保留于此。"""

    def _set_cpu(self, cpu):
        """设置 CPU 选择"""
        self.cpu_var = cpu

    def _set_st(self, st):
        """设置 ST 版本"""
        self.st_var = st

    def _set_calc_mode(self, calc_mode, skip_block_check=False):
        """设置计算模式
        Args:
            calc_mode: 计算模式文本
            skip_block_check: 是否跳过阻止检查（用于自动切换时）
        """
        # 检查是否允许切换计算模式（自动切换时跳过此检查）
        if not skip_block_check and self._should_block_calc_mode_switch():
            # 恢复之前的选择
            if hasattr(self, 'calc_mode_combo') and hasattr(self, 'calc_mode_var'):
                self.calc_mode_combo.blockSignals(True)
                self.calc_mode_combo.setCurrentText(self.calc_mode_var)
                self.calc_mode_combo.blockSignals(False)
                if hasattr(self, 'log'):
                    InfoBar.warning(
                            title="",
                            content=tr("calc_mode_switch_blocked", "检测到 track_i.ww3 或 points.list 文件，不允许切换计算模式"),
                            duration=3000,
                            parent=self
                        )
            return
        
        self.calc_mode_var = calc_mode
        # 获取翻译后的文本用于比较
        spectral_text = tr("step3_spectral_point", "谱空间逐点计算")
        track_text = tr("step3_track_mode", "航迹模式")
        # 根据计算模式显示/隐藏相应的点位管理
        if hasattr(self, 'spectral_points_widget'):
            if calc_mode == spectral_text or calc_mode == "谱空间逐点计算":
                self.spectral_points_widget.setVisible(True)
            else:
                self.spectral_points_widget.setVisible(False)
        
        if hasattr(self, 'track_points_widget'):
            if calc_mode == track_text or calc_mode == "航迹模式":
                self.track_points_widget.setVisible(True)
                # 如果切换到航迹模式，自动读取 track_i.ww3（延迟执行，确保表格已显示）
                # 只在自动切换时执行（通过 skip_block_check 参数判断）
                if hasattr(self, '_import_track_from_file') and hasattr(self, 'selected_folder') and self.selected_folder:
                    # 检查是否已经读取过（避免重复读取）
                    if not hasattr(self, '_track_file_auto_imported'):
                        def auto_import():
                            if hasattr(self, 'track_points_table'):
                                self._import_track_from_file("")
                                self._track_file_auto_imported = True
                        QtCore.QTimer.singleShot(500, auto_import)
            else:
                self.track_points_widget.setVisible(False)
                # 切换出航迹模式时，重置自动导入标记
                if hasattr(self, '_track_file_auto_imported'):
                    self._track_file_auto_imported = False

    def _read_grid_meta_bounds(self):
        """读取grid.meta文件并返回经纬度范围（支持嵌套网格模式）"""
        if not hasattr(self, 'selected_folder') or not self.selected_folder:
            return None
        
        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")
        
        if is_nested_grid:
            # 嵌套网格模式：读取 coarse 和 fine 的范围，合并为并集
            coarse_dir = os.path.join(self.selected_folder, "coarse")
            fine_dir = os.path.join(self.selected_folder, "fine")
            
            coarse_bounds = self._read_single_grid_meta_bounds(coarse_dir)
            fine_bounds = self._read_single_grid_meta_bounds(fine_dir)
            
            if not coarse_bounds and not fine_bounds:
                return None
            elif not coarse_bounds:
                return fine_bounds
            elif not fine_bounds:
                return coarse_bounds
            else:
                # 合并两个网格的范围（取并集）
                return {
                    'lon_min': min(coarse_bounds['lon_min'], fine_bounds['lon_min']),
                    'lon_max': max(coarse_bounds['lon_max'], fine_bounds['lon_max']),
                    'lat_min': min(coarse_bounds['lat_min'], fine_bounds['lat_min']),
                    'lat_max': max(coarse_bounds['lat_max'], fine_bounds['lat_max'])
                }
        else:
            # 普通网格模式：读取工作目录下的 grid.meta
            return self._read_single_grid_meta_bounds(self.selected_folder)

    def _read_single_grid_meta_bounds(self, target_dir):
        """读取指定目录下的grid.meta文件并返回经纬度范围"""
        if not target_dir or not isinstance(target_dir, str):
            return None
        
        meta_path = os.path.join(target_dir, "grid.meta")
        if not os.path.exists(meta_path):
            return None
        
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta_lines = f.readlines()
            
            # 查找 RECT 块
            target_index_meta = None
            for i, line in enumerate(meta_lines):
                if "'RECT'" in line and "T" in line and "'NONE'" in line:
                    target_index_meta = i
                    break
                elif "'RECT'" in line or '"RECT"' in line or "RECT" in line.upper():
                    stripped = line.strip()
                    if stripped.startswith("'") or stripped.startswith('"') or len(stripped.split()) <= 3:
                        target_index_meta = i
                        break
            
            if target_index_meta is None or target_index_meta + 3 >= len(meta_lines):
                return None
            
            if target_index_meta is None or target_index_meta + 3 >= len(meta_lines):
                return None
            
            # 提取三行参数
            L1 = meta_lines[target_index_meta + 1].split()
            L2 = meta_lines[target_index_meta + 2].split()
            L3 = meta_lines[target_index_meta + 3].split()
            
            NX, NY = int(L1[0]), int(L1[1])
            SX, SY, SF = float(L2[0]), float(L2[1]), float(L2[2])
            X0, Y0, SF0 = float(L3[0]), float(L3[1]), float(L3[2])
            
            # 计算经纬度范围
            # 根据WW3文档：X0, Y0是左下角坐标（度），需要除以SF0
            # SX, SY是网格增量，需要除以SF得到度
            # 经度范围：[X0/SF0, X0/SF0 + (NX-1) * SX / SF]
            # 纬度范围：[Y0/SF0, Y0/SF0 + (NY-1) * SY / SF]
            lon_min = X0 / SF0
            lon_max = lon_min + (NX - 1) * SX / SF
            lat_min = Y0 / SF0
            lat_max = lat_min + (NY - 1) * SY / SF
            
            # 计算精度（DX, DY），单位：度
            dx = SX / SF
            dy = SY / SF
            
            return {
                'lon_min': lon_min,
                'lon_max': lon_max,
                'lat_min': lat_min,
                'lat_max': lat_max,
                'dx': dx,
                'dy': dy
            }
        except Exception as e:
            return None

    def create_step_3_card(self, content_widget, content_layout):
        """创建第三步：计算模式的 UI"""
        # 使用通用函数创建卡片
        step3_calc_mode_card, step3_calc_mode_card_layout = create_header_card(
            content_widget,
            tr("step3_title", "第三步：计算模式")
        )

        combo_style = self._get_combo_style()
        calc_mode_grid = QGridLayout()
        calc_mode_grid.setSpacing(10)
        calc_mode_grid.setColumnStretch(0, 0)
        calc_mode_grid.setColumnStretch(1, 1)

        calc_mode_label = QLabel(tr("step3_calc_mode", "计算模式："))
        calc_mode_grid.addWidget(calc_mode_label, 0, 0)
        self.calc_mode_combo = ComboBox()
        self.calc_mode_combo.addItems([
            tr("step3_region_scale", "区域尺度计算"),
            tr("step3_spectral_point", "谱空间逐点计算"),
            tr("step3_track_mode", "航迹模式")
        ])
        self.calc_mode_combo.setCurrentText(tr("step3_region_scale", "区域尺度计算"))
        self.calc_mode_var = tr("step3_region_scale", "区域尺度计算")
        self.calc_mode_combo.currentTextChanged.connect(self._set_calc_mode)
        self.calc_mode_combo.setStyleSheet(combo_style)

        def _set_calc_mode_combo_alignment():
            try:
                if hasattr(self.calc_mode_combo, 'lineEdit'):
                    line_edit = self.calc_mode_combo.lineEdit()
                    if line_edit:
                        line_edit.setAlignment(Qt.AlignmentFlag.AlignLeft)
            except Exception:
                pass
        QtCore.QTimer.singleShot(10, _set_calc_mode_combo_alignment)
        calc_mode_grid.addWidget(self.calc_mode_combo, 0, 1)
        step3_calc_mode_card_layout.addLayout(calc_mode_grid)

        self.spectral_points_widget = QWidget()
        self.spectral_points_widget.setContentsMargins(0, 0, 0, 0)
        spectral_points_layout = QVBoxLayout()
        spectral_points_layout.setContentsMargins(0, 0, 0, 0)

        self.spectral_points_table = TableWidget()
        self.spectral_points_table.setContentsMargins(0, 0, 0, 0)
        self.spectral_points_table.setColumnCount(3)
        self.spectral_points_table.horizontalHeader().setVisible(False)
        header = self.spectral_points_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.spectral_points_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.spectral_points_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.spectral_points_table.setBorderVisible(False)
        self.spectral_points_table.setWordWrap(False)
        self.spectral_points_table.verticalHeader().setVisible(False)

        self.spectral_points_table.insertRow(0)
        header_lon_item = QTableWidgetItem(tr("step3_longitude", "经度"))
        header_lon_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        header_lat_item = QTableWidgetItem(tr("step3_latitude", "纬度"))
        header_lat_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)
        header_name_item = QTableWidgetItem(tr("step3_name", "名称"))
        header_name_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)
        header_lon_item.setData(QtCore.Qt.ItemDataRole.UserRole, "header")
        header_lat_item.setData(QtCore.Qt.ItemDataRole.UserRole, "header")
        header_name_item.setData(QtCore.Qt.ItemDataRole.UserRole, "header")
        self.spectral_points_table.setItem(0, 0, header_lon_item)
        self.spectral_points_table.setItem(0, 1, header_lat_item)
        self.spectral_points_table.setItem(0, 2, header_name_item)

        row_count = self.spectral_points_table.rowCount()
        vertical_header = self.spectral_points_table.verticalHeader()
        vertical_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.spectral_points_table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        if row_count > 0:
            self.spectral_points_table.resizeRowsToContents()
            total_height = sum(self.spectral_points_table.rowHeight(i) for i in range(row_count))
            content_height = max(200, total_height + 20)
        else:
            content_height = 200
        self.spectral_points_table.setMinimumHeight(content_height)
        self.spectral_points_table.setMaximumHeight(16777215)
        self.spectral_points_table.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred))
        spectral_points_layout.addWidget(self.spectral_points_table)

        button_style = self._get_button_style()
        spectral_points_buttons_layout = QHBoxLayout()
        spectral_points_buttons_layout.setSpacing(10)
        btn_add_point = PrimaryPushButton(tr("new", "新增"))
        btn_add_point.setStyleSheet(button_style)
        btn_add_point.clicked.connect(self._add_spectral_point)
        spectral_points_buttons_layout.addWidget(btn_add_point, 1)
        btn_edit_point = PrimaryPushButton(tr("edit", "修改"))
        btn_edit_point.setStyleSheet(button_style)
        btn_edit_point.clicked.connect(self._edit_spectral_point)
        spectral_points_buttons_layout.addWidget(btn_edit_point, 1)
        btn_delete_point = PrimaryPushButton(tr("delete", "删除"))
        btn_delete_point.setStyleSheet(button_style)
        btn_delete_point.clicked.connect(self._delete_spectral_point)
        spectral_points_buttons_layout.addWidget(btn_delete_point, 1)
        spectral_points_layout.addLayout(spectral_points_buttons_layout)
        btn_select_points = PrimaryPushButton(tr("step3_select_on_map", "在地图上选点"))
        btn_select_points.setStyleSheet(button_style)
        btn_select_points.clicked.connect(self._select_points_on_map)
        spectral_points_layout.addWidget(btn_select_points)
        btn_import_points = PrimaryPushButton(tr("step3_import_points", "从 points.list 导入"))
        btn_import_points.setStyleSheet(button_style)
        btn_import_points.clicked.connect(self._import_points_from_file)
        spectral_points_layout.addWidget(btn_import_points)
        self.spectral_points_widget.setLayout(spectral_points_layout)
        self.spectral_points_widget.setVisible(False)
        step3_calc_mode_card_layout.addWidget(self.spectral_points_widget)

        self.track_points_widget = QWidget()
        self.track_points_widget.setContentsMargins(0, 0, 0, 0)
        track_points_layout = QVBoxLayout()
        track_points_layout.setContentsMargins(0, 0, 0, 0)

        self.track_points_table = TableWidget()
        self.track_points_table.setContentsMargins(0, 0, 0, 0)
        self.track_points_table.setColumnCount(4)
        self.track_points_table.horizontalHeader().setVisible(False)
        track_header = self.track_points_table.horizontalHeader()
        track_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        track_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        track_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        track_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.track_points_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.track_points_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.track_points_table.setBorderVisible(False)
        self.track_points_table.setWordWrap(False)
        self.track_points_table.verticalHeader().setVisible(False)

        self.track_points_table.insertRow(0)
        track_header_time_item = QTableWidgetItem(tr("step3_time", "时间"))
        track_header_time_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        track_header_lon_item = QTableWidgetItem(tr("step3_longitude", "经度"))
        track_header_lon_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        track_header_lat_item = QTableWidgetItem(tr("step3_latitude", "纬度"))
        track_header_lat_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        track_header_name_item = QTableWidgetItem(tr("step3_name", "名称"))
        track_header_name_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        track_header_time_item.setData(QtCore.Qt.ItemDataRole.UserRole, "header")
        track_header_lon_item.setData(QtCore.Qt.ItemDataRole.UserRole, "header")
        track_header_lat_item.setData(QtCore.Qt.ItemDataRole.UserRole, "header")
        track_header_name_item.setData(QtCore.Qt.ItemDataRole.UserRole, "header")
        self.track_points_table.setItem(0, 0, track_header_time_item)
        self.track_points_table.setItem(0, 1, track_header_lon_item)
        self.track_points_table.setItem(0, 2, track_header_lat_item)
        self.track_points_table.setItem(0, 3, track_header_name_item)

        track_row_count = self.track_points_table.rowCount()
        track_vertical_header = self.track_points_table.verticalHeader()
        track_vertical_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.track_points_table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        if track_row_count > 0:
            self.track_points_table.resizeRowsToContents()
            track_total_height = sum(self.track_points_table.rowHeight(i) for i in range(track_row_count))
            track_content_height = max(200, track_total_height + 20)
        else:
            track_content_height = 200
        self.track_points_table.setMinimumHeight(track_content_height)
        self.track_points_table.setMaximumHeight(16777215)
        self.track_points_table.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred))
        track_points_layout.addWidget(self.track_points_table)

        track_points_buttons_layout = QHBoxLayout()
        track_points_buttons_layout.setSpacing(10)
        btn_add_track_point = PrimaryPushButton(tr("new", "新增"))
        btn_add_track_point.setStyleSheet(button_style)
        btn_add_track_point.clicked.connect(self._add_track_point)
        track_points_buttons_layout.addWidget(btn_add_track_point, 1)
        btn_edit_track_point = PrimaryPushButton(tr("edit", "修改"))
        btn_edit_track_point.setStyleSheet(button_style)
        btn_edit_track_point.clicked.connect(self._edit_track_point)
        track_points_buttons_layout.addWidget(btn_edit_track_point, 1)
        btn_delete_track_point = PrimaryPushButton(tr("delete", "删除"))
        btn_delete_track_point.setStyleSheet(button_style)
        btn_delete_track_point.clicked.connect(self._delete_track_point)
        track_points_buttons_layout.addWidget(btn_delete_track_point, 1)
        track_points_layout.addLayout(track_points_buttons_layout)
        btn_select_track_points = PrimaryPushButton(tr("step3_select_on_map", "在地图上选点"))
        btn_select_track_points.setStyleSheet(button_style)
        btn_select_track_points.clicked.connect(self._select_track_points_on_map)
        track_points_layout.addWidget(btn_select_track_points)
        btn_import_track_file = PrimaryPushButton(tr("step3_import_track_file", "从 track_i.ww3 读取"))
        btn_import_track_file.setStyleSheet(button_style)
        btn_import_track_file.clicked.connect(self._import_track_from_file_dialog)
        track_points_layout.addWidget(btn_import_track_file)
        self.track_points_widget.setLayout(track_points_layout)
        self.track_points_widget.setVisible(False)
        step3_calc_mode_card_layout.addWidget(self.track_points_widget)

        step3_calc_mode_card.viewLayout.setContentsMargins(11, 10, 11, 12)
        step3_calc_mode_card.viewLayout.addLayout(step3_calc_mode_card_layout)
        content_layout.addWidget(step3_calc_mode_card)

    def _add_spectral_point(self):
        """新增谱空间逐点计算点位"""
        from qfluentwidgets import MessageBoxBase

        class SpectralPointDialog(MessageBoxBase):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle(tr("step3_add_point_title", "新增点位"))
                # 设置按钮文本
                if hasattr(self, 'yesButton') and self.yesButton:
                    self.yesButton.setText(tr("confirm", "确定"))
                if hasattr(self, 'cancelButton') and self.cancelButton:
                    self.cancelButton.setText(tr("cancel", "取消"))

                dialog_layout = QVBoxLayout()
                dialog_layout.setSpacing(10)

                # 使用主题适配的样式
                if parent and hasattr(parent, '_get_input_style'):
                    input_style = parent._get_input_style()
                else:
                    from qfluentwidgets import isDarkTheme
                    is_dark = isDarkTheme()
                    if is_dark:
                        input_style = """
                            LineEdit {
                                background-color: #2D2D2D;
                                border: 1px solid #404040;
                                border-radius: 4px;
                                padding: 4px 8px;
                                color: #FFFFFF;
                            }
                            LineEdit:focus {
                                border: 1px solid #404040;
                            }
                        """
                    else:
                        input_style = """
                            LineEdit {
                                background-color: #FFFFFF;
                                border: 1px solid #D0D0D0;
                                border-radius: 4px;
                                padding: 4px 8px;
                                color: #000000;
                            }
                            LineEdit:focus {
                                border: 1px solid #D0D0D0;
                            }
                        """

                grid_layout = QGridLayout()
                grid_layout.setColumnStretch(0, 0)
                grid_layout.setColumnStretch(1, 1)
                grid_layout.setSpacing(10)

                # 经度行
                lon_label = QLabel(tr("step3_longitude", "经度") + ":")
                lon_edit = LineEdit()
                lon_edit.setPlaceholderText(tr("step3_lon_example", "例如: 120.5"))
                lon_edit.setMinimumWidth(300)
                lon_edit.setStyleSheet(input_style)
                grid_layout.addWidget(lon_label, 0, 0)
                grid_layout.addWidget(lon_edit, 0, 1)

                # 纬度行
                lat_label = QLabel(tr("step3_latitude", "纬度") + ":")
                lat_edit = LineEdit()
                lat_edit.setPlaceholderText(tr("step3_lat_example", "例如: 30.2"))
                lat_edit.setMinimumWidth(300)
                lat_edit.setStyleSheet(input_style)
                grid_layout.addWidget(lat_label, 1, 0)
                grid_layout.addWidget(lat_edit, 1, 1)

                # 名称行
                name_label = QLabel(tr("step3_name", "名称") + ":")
                name_edit = LineEdit()
                name_edit.setPlaceholderText(tr("step3_name_example", "例如: 点位1"))
                name_edit.setMinimumWidth(300)
                name_edit.setStyleSheet(input_style)
                grid_layout.addWidget(name_label, 2, 0)
                grid_layout.addWidget(name_edit, 2, 1)

                dialog_layout.addLayout(grid_layout)
                self.viewLayout.addLayout(dialog_layout)

                # 保存输入框引用
                self.lon_edit = lon_edit
                self.lat_edit = lat_edit
                self.name_edit = name_edit

        # 计算当前点的索引（表格行数 - 1，因为表头行是第0行）
        current_index = self.spectral_points_table.rowCount() - 1
        if current_index < 0:
            current_index = 0
        
        dialog = SpectralPointDialog(self)
        # 设置名称默认值为当前索引
        dialog.name_edit.setText(str(current_index))

        if dialog.exec():
            lon = dialog.lon_edit.text().strip()
            lat = dialog.lat_edit.text().strip()
            name = dialog.name_edit.text().strip()
            # 如果名称为空，使用当前索引作为默认名称
            if not name:
                name = str(current_index)
            if lon and lat and name:
                # 验证经度纬度是否为有效数字
                try:
                    lon_float = float(lon)
                    lat_float = float(lat)
                    if not (-180 <= lon_float <= 180):
                        InfoBar.warning(
                            title=tr("step3_add_failed", "添加失败"),
                            content=tr("step3_lon_range_error", "经度必须在 -180 到 180 之间"),
                            duration=3000,
                            parent=self
                        )
                        return
                    if not (-90 <= lat_float <= 90):
                        InfoBar.warning(
                            title=tr("step3_add_failed", "添加失败"),
                            content=tr("step3_lat_range_error", "纬度必须在 -90 到 90 之间"),
                            duration=3000,
                            parent=self
                        )
                        return
                except ValueError:
                    InfoBar.warning(
                        title=tr("step3_add_failed", "添加失败"),
                        content=tr("step3_lon_lat_must_be_number", "经度和纬度必须是有效数字"),
                        duration=3000,
                        parent=self
                    )
                    return
                
                # 检查点位是否在地图文件范围内
                bounds = self._read_grid_meta_bounds()
                if bounds:
                    if not (bounds['lon_min'] <= lon_float <= bounds['lon_max']):
                        InfoBar.warning(
                            title=tr("step3_add_failed", "添加失败"),
                            content=tr("step3_lon_out_of_range", "经度 {lon} 不在地图范围内 [{lon_min}, {lon_max}]").format(lon=f"{lon_float:.4f}", lon_min=f"{bounds['lon_min']:.4f}", lon_max=f"{bounds['lon_max']:.4f}"),
                            duration=3000,
                            parent=self
                        )
                        return
                    if not (bounds['lat_min'] <= lat_float <= bounds['lat_max']):
                        InfoBar.warning(
                            title=tr("step3_add_failed", "添加失败"),
                            content=tr("step3_lat_out_of_range", "纬度 {lat} 不在地图范围内 [{lat_min}, {lat_max}]").format(lat=f"{lat_float:.4f}", lat_min=f"{bounds['lat_min']:.4f}", lat_max=f"{bounds['lat_max']:.4f}"),
                            duration=3000,
                            parent=self
                        )
                        return

                # 检查名称是否已存在（跳过表头行，从第1行开始检查）
                for i in range(1, self.spectral_points_table.rowCount()):
                    existing_name = self.spectral_points_table.item(i, 2)
                    if existing_name and existing_name.text().strip() == name:
                        InfoBar.warning(
                            title=tr("step3_add_failed", "添加失败"),
                            content=tr("step3_name_exists", "名称 '{name}' 已存在").format(name=name),
                            duration=3000,
                            parent=self
                        )
                        return

                # 添加到表格（插入到表头行之后，即第1行开始）
                row = self.spectral_points_table.rowCount()
                self.spectral_points_table.insertRow(row)
                lon_item = QTableWidgetItem(lon)
                lon_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                lat_item = QTableWidgetItem(lat)
                lat_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)
                name_item = QTableWidgetItem(name)
                name_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)
                self.spectral_points_table.setItem(row, 0, lon_item)
                self.spectral_points_table.setItem(row, 1, lat_item)
                self.spectral_points_table.setItem(row, 2, name_item)

                InfoBar.success(
                    title=tr("step3_add_success", "添加成功"),
                    content=tr("step3_point_added", "已添加点位 '{name}'").format(name=name),
                    duration=2000,
                    parent=self
                )
            else:
                InfoBar.warning(
                    title=tr("step3_add_failed", "添加失败"),
                    content=tr("step3_lon_lat_name_required", "经度、纬度和名称不能为空"),
                    duration=3000,
                    parent=self
                )

    def _edit_spectral_point(self):
        """修改谱空间逐点计算点位"""
        current_row = self.spectral_points_table.currentRow()
        if current_row < 0:
            InfoBar.warning(
                title=tr("step3_edit_failed", "修改失败"),
                content=tr("step3_please_select_point", "请先选择要修改的点位"),
                duration=3000,
                parent=self
            )
            return

        # 检查是否是表头行（第0行），静默返回
        if current_row == 0:
            return

        lon_item = self.spectral_points_table.item(current_row, 0)
        lat_item = self.spectral_points_table.item(current_row, 1)
        name_item = self.spectral_points_table.item(current_row, 2)

        old_lon = lon_item.text().strip() if lon_item else ""
        old_lat = lat_item.text().strip() if lat_item else ""
        old_name = name_item.text().strip() if name_item else ""

        from qfluentwidgets import MessageBoxBase

        class SpectralPointEditDialog(MessageBoxBase):
            def __init__(self, parent=None, old_lon="", old_lat="", old_name=""):
                super().__init__(parent)
                self.setWindowTitle(tr("step3_edit_point_title", "修改点位"))
                if hasattr(self, 'yesButton') and self.yesButton:
                    self.yesButton.setText(tr("confirm", "确定"))
                if hasattr(self, 'cancelButton') and self.cancelButton:
                    self.cancelButton.setText(tr("cancel", "取消"))

                dialog_layout = QVBoxLayout()
                dialog_layout.setSpacing(10)

                if parent and hasattr(parent, '_get_input_style'):
                    input_style = parent._get_input_style()
                else:
                    from qfluentwidgets import isDarkTheme
                    is_dark = isDarkTheme()
                    if is_dark:
                        input_style = """
                            LineEdit {
                                background-color: #2D2D2D;
                                border: 1px solid #404040;
                                border-radius: 4px;
                                padding: 4px 8px;
                                color: #FFFFFF;
                            }
                            LineEdit:focus {
                                border: 1px solid #404040;
                            }
                        """
                    else:
                        input_style = """
                            LineEdit {
                                background-color: #FFFFFF;
                                border: 1px solid #D0D0D0;
                                border-radius: 4px;
                                padding: 4px 8px;
                                color: #000000;
                            }
                            LineEdit:focus {
                                border: 1px solid #D0D0D0;
                            }
                        """

                grid_layout = QGridLayout()
                grid_layout.setColumnStretch(0, 0)
                grid_layout.setColumnStretch(1, 1)
                grid_layout.setSpacing(10)

                lon_label = QLabel(tr("step3_longitude", "经度") + ":")
                lon_edit = LineEdit()
                lon_edit.setText(old_lon)
                lon_edit.setPlaceholderText(tr("lon_example", "例如: 120.5"))
                lon_edit.setMinimumWidth(300)
                lon_edit.setStyleSheet(input_style)
                grid_layout.addWidget(lon_label, 0, 0)
                grid_layout.addWidget(lon_edit, 0, 1)

                lat_label = QLabel(tr("step3_latitude", "纬度") + ":")
                lat_edit = LineEdit()
                lat_edit.setText(old_lat)
                lat_edit.setPlaceholderText(tr("lat_example", "例如: 30.2"))
                lat_edit.setMinimumWidth(300)
                lat_edit.setStyleSheet(input_style)
                grid_layout.addWidget(lat_label, 1, 0)
                grid_layout.addWidget(lat_edit, 1, 1)

                name_label = QLabel(tr("step3_name", "名称") + ":")
                name_edit = LineEdit()
                name_edit.setText(old_name)
                name_edit.setPlaceholderText(tr("point_name_example", "例如: 点位1"))
                name_edit.setMinimumWidth(300)
                name_edit.setStyleSheet(input_style)
                grid_layout.addWidget(name_label, 2, 0)
                grid_layout.addWidget(name_edit, 2, 1)

                dialog_layout.addLayout(grid_layout)
                self.viewLayout.addLayout(dialog_layout)

                self.lon_edit = lon_edit
                self.lat_edit = lat_edit
                self.name_edit = name_edit

        dialog = SpectralPointEditDialog(self, old_lon, old_lat, old_name)

        if dialog.exec():
            lon = dialog.lon_edit.text().strip()
            lat = dialog.lat_edit.text().strip()
            name = dialog.name_edit.text().strip()
            if lon and lat and name:
                # 验证经度纬度是否为有效数字
                try:
                    lon_float = float(lon)
                    lat_float = float(lat)
                    if not (-180 <= lon_float <= 180):
                        InfoBar.warning(
                            title=tr("step3_edit_failed", "修改失败"),
                            content=tr("step3_lon_range_error", "经度必须在 -180 到 180 之间"),
                            duration=3000,
                            parent=self
                        )
                        return
                    if not (-90 <= lat_float <= 90):
                        InfoBar.warning(
                            title=tr("step3_edit_failed", "修改失败"),
                            content=tr("step3_lat_range_error", "纬度必须在 -90 到 90 之间"),
                            duration=3000,
                            parent=self
                        )
                        return
                except ValueError:
                    InfoBar.warning(
                        title=tr("step3_edit_failed", "修改失败"),
                        content=tr("step3_lon_lat_must_be_number", "经度和纬度必须是有效数字"),
                        duration=3000,
                        parent=self
                    )
                    return

                # 检查名称是否已存在（排除当前行和表头行）
                for i in range(1, self.spectral_points_table.rowCount()):
                    if i == current_row:
                        continue
                    existing_name = self.spectral_points_table.item(i, 2)
                    if existing_name and existing_name.text().strip() == name:
                        InfoBar.warning(
                            title=tr("step3_edit_failed", "修改失败"),
                            content=tr("step3_name_exists", "名称 '{name}' 已存在").format(name=name),
                            duration=3000,
                            parent=self
                        )
                        return

                # 更新表格
                lon_item = QTableWidgetItem(lon)
                lon_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                lat_item = QTableWidgetItem(lat)
                lat_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)
                name_item = QTableWidgetItem(name)
                name_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)
                self.spectral_points_table.setItem(current_row, 0, lon_item)
                self.spectral_points_table.setItem(current_row, 1, lat_item)
                self.spectral_points_table.setItem(current_row, 2, name_item)

                InfoBar.success(
                    title=tr("step3_edit_success", "修改成功"),
                    content=tr("step3_point_modified", "已修改点位 '{name}'").format(name=name),
                    duration=2000,
                    parent=self
                )
            else:
                InfoBar.warning(
                    title=tr("step3_edit_failed", "修改失败"),
                    content=tr("step3_lon_lat_name_required", "经度、纬度和名称不能为空"),
                    duration=3000,
                    parent=self
                )

    def _delete_spectral_point(self):
        """删除谱空间逐点计算点位"""
        current_row = self.spectral_points_table.currentRow()
        if current_row < 0:
            InfoBar.warning(
                title=tr("step3_delete_failed", "删除失败"),
                content=tr("step3_please_select_point_to_delete", "请先选择要删除的点位"),
                duration=3000,
                parent=self
            )
            return

        # 检查是否是表头行（第0行），静默返回
        if current_row == 0:
            return

        name_item = self.spectral_points_table.item(current_row, 2)
        if not name_item:
            return

        name = name_item.text().strip()

        # 直接删除，不需要确认弹窗
        self.spectral_points_table.removeRow(current_row)
        InfoBar.success(
            title=tr("step3_delete_success", "删除成功"),
            content=tr("step3_point_deleted", "已删除点位 '{name}'").format(name=name),
            duration=2000,
            parent=self
        )

    def _show_spectral_points_map(self):
        """显示当前点组在地图上的位置"""
        # 检查是否有点位数据
        if not hasattr(self, 'spectral_points_table'):
            InfoBar.warning(
                title=tr("step3_display_failed", "显示失败"),
                content=tr("step3_table_not_exists", "表格不存在"),
                duration=3000,
                parent=self
            )
            return
        
        # 读取所有点位（跳过表头行）
        points = []
        for i in range(1, self.spectral_points_table.rowCount()):
            lon_item = self.spectral_points_table.item(i, 0)
            lat_item = self.spectral_points_table.item(i, 1)
            name_item = self.spectral_points_table.item(i, 2)
            
            if lon_item and lat_item:
                try:
                    lon = float(lon_item.text().strip())
                    lat = float(lat_item.text().strip())
                    name = name_item.text().strip() if name_item else f"点位{i}"
                    
                    # 跳过 STOPSTRING 点（不在表格和地图中显示）
                    if name.upper() == 'STOPSTRING':
                        continue
                    
                    points.append({'lon': lon, 'lat': lat, 'name': name})
                except ValueError:
                    continue
        
        if not points:
            InfoBar.warning(
                title=tr("step3_display_failed", "显示失败"),
                content=tr("step3_no_points_to_display", "没有可显示的点位数据"),
                duration=3000,
                parent=self
            )
            return
        
        # 获取地图范围
        bounds = self._read_grid_meta_bounds()
        if not bounds:
            InfoBar.warning(
                title=tr("step3_display_failed", "显示失败"),
                content=tr("step3_cannot_read_map_range", "无法读取地图范围，请确保grid.meta文件存在"),
                duration=3000,
                parent=self
            )
            return
        
        # 计算显示范围（包含所有点位和地图范围）
        lons = [p['lon'] for p in points]
        lats = [p['lat'] for p in points]
        
        lon_min = min(min(lons), bounds['lon_min'])
        lon_max = max(max(lons), bounds['lon_max'])
        lat_min = min(min(lats), bounds['lat_min'])
        lat_max = max(max(lats), bounds['lat_max'])
        
        # 添加边距
        lon_range = lon_max - lon_min
        lat_range = lat_max - lat_min
        margin_lon = max(lon_range * 0.1, 2.0)
        margin_lat = max(lat_range * 0.1, 2.0)
        
        display_lon_min = lon_min - margin_lon
        display_lon_max = lon_max + margin_lon
        display_lat_min = lat_min - margin_lat
        display_lat_max = lat_max + margin_lat
        
        # 判断投影方式
        if display_lon_min < 0 or display_lon_max < 0:
            proj = ccrs.Mercator(central_longitude=180)
        else:
            proj = ccrs.Mercator(central_longitude=0)
            if display_lon_max > 180:
                margin = display_lon_max - lon_max
                display_lon_max = min(180.0 + margin, 185.0)
            elif lon_max >= 179:
                margin = display_lon_max - lon_max
                display_lon_max = min(180.0, lon_max + margin)
        
        # 创建地图
        fig = plt.figure(figsize=(12, 10), dpi=100)
        ax = fig.add_subplot(1, 1, 1, projection=proj)
        ax.set_extent([display_lon_min, display_lon_max, display_lat_min, display_lat_max], crs=ccrs.PlateCarree())
        
        # 添加地图特征
        ax.add_feature(cfeature.OCEAN, facecolor="#a4d6ff")
        ax.add_feature(cfeature.LAND, facecolor="#f0f0f0")
        ax.coastlines(resolution='10m', linewidth=0.6)
        
        # 绘制地图范围边界
        bounds_lon = [bounds['lon_min'], bounds['lon_max'], bounds['lon_max'], bounds['lon_min'], bounds['lon_min']]
        bounds_lat = [bounds['lat_min'], bounds['lat_min'], bounds['lat_max'], bounds['lat_max'], bounds['lat_min']]
        ax.plot(bounds_lon, bounds_lat, transform=ccrs.PlateCarree(), 
                color='blue', linewidth=2, linestyle='--', label=tr("step3_map_range_label", "地图范围"))
        
        # 绘制点位
        for i, point in enumerate(points):
            ax.plot(point['lon'], point['lat'], 'ro', markersize=10, 
                   transform=ccrs.PlateCarree(), label=tr("step3_point_label", "点位") if i == 0 else '')
            # 添加点位标签
            ax.text(point['lon'], point['lat'], f"  {point['name']}", 
                   transform=ccrs.PlateCarree(), fontsize=9, 
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7))
        
        # 添加图例
        ax.legend(loc='upper right')
        
        # 添加网格线
        gl = ax.gridlines(crs=ccrs.PlateCarree(), draw_labels=True, 
                         linewidth=0.5, color='gray', alpha=0.5, linestyle='--')
        gl.top_labels = False
        gl.right_labels = False
        
        # 设置标题
        ax.set_title(f'谱空间逐点计算点位分布图（共{len(points)}个点位）', fontsize=14, fontweight='bold')
        
        # 显示地图
        plt.tight_layout()
        plt.show()

    def _select_points_on_map(self, target_table='spectral'):
        """在地图上交互式选择多个点位
        Args:
            target_table: 目标表格类型，'spectral' 表示谱空间逐点计算模式，'track' 表示航迹模式
        """
        # 确定目标表格
        if target_table == 'track':
            if not hasattr(self, 'track_points_table'):
                InfoBar.warning(
                    title=tr("step3_select_failed", "选点失败"),
                    content=tr("step3_track_table_not_initialized", "航迹模式表格未初始化"),
                    duration=3000,
                    parent=self
                )
                return
            target_table_obj = self.track_points_table
            has_time_column = True
        else:
            if not hasattr(self, 'spectral_points_table'):
                InfoBar.warning(
                    title=tr("step3_select_failed", "选点失败"),
                    content=tr("step3_spectral_table_not_initialized", "谱空间逐点计算模式表格未初始化"),
                    duration=3000,
                    parent=self
                )
                return
            target_table_obj = self.spectral_points_table
            has_time_column = False
        
        # 设置中文字体支持
        chinese_font = None
        try:
            import platform
            system = platform.system()
            if system == 'Windows':
                chinese_fonts = ['Microsoft YaHei', 'SimHei', 'SimSun', 'KaiTi']
            elif system == 'Darwin':  # macOS
                chinese_fonts = ['PingFang SC', 'STHeiti', 'Arial Unicode MS', 'Heiti SC']
            else:  # Linux
                chinese_fonts = ['WenQuanYi Micro Hei', 'WenQuanYi Zen Hei', 'Noto Sans CJK SC', 'Droid Sans Fallback']
            
            from matplotlib import font_manager
            available_fonts = [f.name for f in font_manager.fontManager.ttflist]
            for font in chinese_fonts:
                if font in available_fonts:
                    chinese_font = font
                    break
            
            if chinese_font:
                plt.rcParams['font.sans-serif'] = [chinese_font]
                plt.rcParams['axes.unicode_minus'] = False
            else:
                import warnings
                warnings.filterwarnings('ignore', category=UserWarning, module='cartopy')
        except Exception:
            import warnings
            warnings.filterwarnings('ignore', category=UserWarning, module='cartopy')
        
        # 获取地图范围
        bounds = self._read_grid_meta_bounds()
        if not bounds:
            InfoBar.warning(
                title=tr("step3_select_failed", "选点失败"),
                content=tr("step3_cannot_read_map_range", "无法读取地图范围，请确保grid.meta文件存在"),
                duration=3000,
                parent=self
            )
            return
        
        # 计算显示范围（添加边距）
        lon_range = bounds['lon_max'] - bounds['lon_min']
        lat_range = bounds['lat_max'] - bounds['lat_min']
        margin_lon = max(lon_range * 0.1, 2.0)
        margin_lat = max(lat_range * 0.1, 2.0)
        
        display_lon_min = bounds['lon_min'] - margin_lon
        display_lon_max = bounds['lon_max'] + margin_lon
        display_lat_min = bounds['lat_min'] - margin_lat
        display_lat_max = bounds['lat_max'] + margin_lat
        
        # 使用PlateCarree投影，简化坐标转换
        # 这样可以避免复杂的坐标转换问题
        proj = ccrs.PlateCarree()
        
        # 调整显示范围（如果需要）
        if display_lon_max > 180:
            margin = display_lon_max - bounds['lon_max']
            display_lon_max = min(180.0 + margin, 185.0)
        elif bounds['lon_max'] >= 179:
            margin = display_lon_max - bounds['lon_max']
            display_lon_max = min(180.0, bounds['lon_max'] + margin)
        
        # 创建地图
        fig = plt.figure(figsize=(12, 10), dpi=100)
        ax = fig.add_subplot(1, 1, 1, projection=proj)
        ax.set_extent([display_lon_min, display_lon_max, display_lat_min, display_lat_max], crs=ccrs.PlateCarree())
        
        # 添加地图特征
        ax.add_feature(cfeature.OCEAN, facecolor="#a4d6ff")
        ax.add_feature(cfeature.LAND, facecolor="#f0f0f0")
        ax.coastlines(resolution='10m', linewidth=0.6)
        
        # 绘制地图范围边界
        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")
        
        if is_nested_grid:
            # 嵌套网格模式：绘制外网格和内网格的边界
            coarse_dir = os.path.join(self.selected_folder, "coarse")
            fine_dir = os.path.join(self.selected_folder, "fine")
            
            coarse_bounds = self._read_single_grid_meta_bounds(coarse_dir)
            fine_bounds = self._read_single_grid_meta_bounds(fine_dir)
            
            # 绘制外网格边界
            if coarse_bounds:
                coarse_lon = [coarse_bounds['lon_min'], coarse_bounds['lon_max'], 
                             coarse_bounds['lon_max'], coarse_bounds['lon_min'], 
                             coarse_bounds['lon_min']]
                coarse_lat = [coarse_bounds['lat_min'], coarse_bounds['lat_min'], 
                             coarse_bounds['lat_max'], coarse_bounds['lat_max'], 
                             coarse_bounds['lat_min']]
                ax.plot(coarse_lon, coarse_lat, transform=ccrs.PlateCarree(), 
                       color='blue', linewidth=2, linestyle='--', label=tr("step3_outer_grid_range_label", "外网格范围"))
            
            # 绘制内网格边界
            if fine_bounds:
                fine_lon = [fine_bounds['lon_min'], fine_bounds['lon_max'], 
                           fine_bounds['lon_max'], fine_bounds['lon_min'], 
                           fine_bounds['lon_min']]
                fine_lat = [fine_bounds['lat_min'], fine_bounds['lat_min'], 
                           fine_bounds['lat_max'], fine_bounds['lat_max'], 
                           fine_bounds['lat_min']]
                ax.plot(fine_lon, fine_lat, transform=ccrs.PlateCarree(), 
                       color='red', linewidth=2, linestyle='--', label=tr("step3_inner_grid_range_label", "内网格范围"))
        else:
            # 普通网格模式：绘制单个网格边界
            bounds_lon = [bounds['lon_min'], bounds['lon_max'], bounds['lon_max'], bounds['lon_min'], bounds['lon_min']]
            bounds_lat = [bounds['lat_min'], bounds['lat_min'], bounds['lat_max'], bounds['lat_max'], bounds['lat_min']]
            ax.plot(bounds_lon, bounds_lat, transform=ccrs.PlateCarree(), 
                   color='blue', linewidth=2, linestyle='--', label=tr("step3_map_range_label", "地图范围"))
        
        # 存储选中的点位
        selected_points = []
        selected_markers = []
        
        # 读取已有点位（跳过表头行）
        existing_points = []
        if target_table_obj:
            for i in range(1, target_table_obj.rowCount()):
                if has_time_column:
                    # 航迹模式：列顺序 0-时间, 1-经度, 2-纬度, 3-名称
                    lon_item = target_table_obj.item(i, 1)
                    lat_item = target_table_obj.item(i, 2)
                    name_item = target_table_obj.item(i, 3)
                else:
                    # 谱空间逐点计算模式：列顺序 0-经度, 1-纬度, 2-名称
                    lon_item = target_table_obj.item(i, 0)
                    lat_item = target_table_obj.item(i, 1)
                    name_item = target_table_obj.item(i, 2)
                
                if lon_item and lat_item:
                    try:
                        lon = float(lon_item.text().strip())
                        lat = float(lat_item.text().strip())
                        name = name_item.text().strip() if name_item else f"点位{i}"
                        existing_points.append({'lon': lon, 'lat': lat, 'name': name})
                    except ValueError:
                        continue
        
        # 绘制已有点位，并保存标记和文本标签的引用
        # 先计算所有已有点位的标签位置，避免重叠（使用迭代调整算法）
        base_offset = 0.6  # 基础偏移量（度），增大以确保标签不重叠
        # 根据标签文本长度估算标签宽度（每个字符约0.15度，加上padding）
        max_label_width = max([len(p.get('name', '')) for p in existing_points], default=5) * 0.15 + 0.3
        min_label_distance = max(1.2, max_label_width)  # 标签之间的最小距离（度），至少1.2度
        
        # 第一遍：为每个点设置初始标签位置（默认右上角）
        for point in existing_points:
            lon, lat = point['lon'], point['lat']
            point['label_lon'] = lon + base_offset
            point['label_lat'] = lat + base_offset
        
        # 第二遍：迭代调整标签位置，解决重叠问题
        max_iterations = 50  # 增加迭代次数
        adjustment_factor = 0.3  # 每次调整的幅度
        
        for iteration in range(max_iterations):
            has_overlap = False
            
            for i, point in enumerate(existing_points):
                lon, lat = point['lon'], point['lat']
                current_lon = point['label_lon']
                current_lat = point['label_lat']
                
                # 检查与其他标签是否重叠
                for j, other_point in enumerate(existing_points):
                    if i == j:
                        continue
                    
                    other_lon = other_point['label_lon']
                    other_lat = other_point['label_lat']
                    
                    # 计算两个标签中心之间的距离
                    dx = current_lon - other_lon
                    dy = current_lat - other_lat
                    distance = np.sqrt(dx**2 + dy**2)
                    
                    # 如果距离太近，需要调整
                    if distance < min_label_distance:
                        has_overlap = True
                        
                        # 如果距离为0或非常小，随机选择一个方向
                        if distance < 0.01:
                            angle = np.random.uniform(0, 2 * np.pi)
                            dx = np.cos(angle)
                            dy = np.sin(angle)
                        else:
                            # 归一化方向向量
                            dx /= distance
                            dy /= distance
                        
                        # 计算需要移动的距离
                        move_distance = (min_label_distance - distance) * adjustment_factor
                        
                        # 调整当前标签位置（远离重叠的标签）
                        point['label_lon'] += dx * move_distance
                        point['label_lat'] += dy * move_distance
                        
                        # 同时也要考虑标签应该尽量靠近对应的点
                        # 计算标签到点的向量
                        to_point_dx = lon - point['label_lon']
                        to_point_dy = lat - point['label_lat']
                        to_point_dist = np.sqrt(to_point_dx**2 + to_point_dy**2)
                        
                        # 如果标签离点太远，稍微拉回来一点
                        if to_point_dist > base_offset * 3:
                            pull_back = 0.1
                            if to_point_dist > 0:
                                point['label_lon'] += to_point_dx / to_point_dist * pull_back
                                point['label_lat'] += to_point_dy / to_point_dist * pull_back
                        
                        # 确保标签位置在显示范围内
                        point['label_lon'] = max(display_lon_min, min(display_lon_max, point['label_lon']))
                        point['label_lat'] = max(display_lat_min, min(display_lat_max, point['label_lat']))
            
            # 如果没有重叠，退出循环
            if not has_overlap:
                break
        
        # 绘制已有点位和标签
        existing_markers = []
        existing_text_labels = []
        for point in existing_points:
            marker, = ax.plot(point['lon'], point['lat'], 'go', markersize=8, 
                   transform=ccrs.PlateCarree(), label=tr("step3_existing_points_label", "已有点位") if point == existing_points[0] else '')
            existing_markers.append(marker)
            
            # 计算偏移距离
            offset_dist = np.sqrt((point['label_lon'] - point['lon'])**2 + 
                                 (point['label_lat'] - point['lat'])**2)
            
            # 如果偏移较大，绘制连接线
            if offset_dist > base_offset * 0.8:
                line, = ax.plot([point['lon'], point['label_lon']], 
                               [point['lat'], point['label_lat']],
                               transform=ccrs.PlateCarree(), 
                               color='gray', linewidth=0.5, linestyle='--', alpha=0.5, zorder=1)
                point['line'] = line
            else:
                point['line'] = None
            
            # 添加标签
            text_label = ax.text(point['label_lon'], point['label_lat'], point['name'], 
                   transform=ccrs.PlateCarree(), fontsize=8, zorder=2,
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='lightgreen', alpha=0.7),
                   verticalalignment='center', horizontalalignment='left')
            existing_text_labels.append(text_label)
            # 保存标记和文本标签到点位数据中
            point['marker'] = marker
            point['text_label'] = text_label
        
        # 点击事件处理函数
        def on_click(event):
            if event.inaxes != ax:
                return
            
            # 将点击坐标转换为经纬度
            # 由于使用PlateCarree投影，event.xdata和event.ydata直接就是经纬度
            lon, lat = event.xdata, event.ydata
            
            # 验证坐标是否有效
            if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
                return
            if np.isnan(lon) or np.isnan(lat) or np.isinf(lon) or np.isinf(lat):
                return
            
            # 检查是否在地图范围内（嵌套网格模式下，检查是否在任一网格范围内）
            grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
            nested_text = tr("step2_grid_type_nested", "嵌套网格")
            is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")
            
            if is_nested_grid:
                # 嵌套网格模式：检查是否在外网格或内网格范围内
                coarse_dir = os.path.join(self.selected_folder, "coarse")
                fine_dir = os.path.join(self.selected_folder, "fine")
                
                coarse_bounds = self._read_single_grid_meta_bounds(coarse_dir)
                fine_bounds = self._read_single_grid_meta_bounds(fine_dir)
                
                in_coarse = False
                in_fine = False
                
                if coarse_bounds:
                    in_coarse = (coarse_bounds['lon_min'] <= lon <= coarse_bounds['lon_max'] and 
                               coarse_bounds['lat_min'] <= lat <= coarse_bounds['lat_max'])
                
                if fine_bounds:
                    in_fine = (fine_bounds['lon_min'] <= lon <= fine_bounds['lon_max'] and 
                              fine_bounds['lat_min'] <= lat <= fine_bounds['lat_max'])
                
                if not (in_coarse or in_fine):
                    InfoBar.warning(
                        title=tr("step3_select_failed", "选点失败"),
                        content=tr("step3_point_out_of_grid_range", "点位 ({lon}, {lat}) 不在外网格或内网格范围内").format(lon=f"{lon:.4f}", lat=f"{lat:.4f}"),
                        duration=3000,
                        parent=self
                    )
                    return
            else:
                # 普通网格模式：检查是否在网格范围内
                if not (bounds['lon_min'] <= lon <= bounds['lon_max'] and 
                       bounds['lat_min'] <= lat <= bounds['lat_max']):
                    InfoBar.warning(
                        title=tr("step3_select_failed", "选点失败"),
                        content=tr("step3_point_out_of_range", "点位 ({lon}, {lat}) 不在地图范围内").format(lon=f"{lon:.4f}", lat=f"{lat:.4f}"),
                        duration=3000,
                        parent=self
                    )
                    return
            
            # 检查是否已存在相同位置的点位
            for existing in existing_points + selected_points:
                if abs(existing['lon'] - lon) < 0.001 and abs(existing['lat'] - lat) < 0.001:
                    InfoBar.warning(
                        title=tr("step3_select_failed", "选点失败"),
                        content=tr("step3_point_already_exists", "该位置已存在点位"),
                        duration=2000,
                        parent=self
                    )
                    return
            
            # 添加到选中列表
            current_index = len(existing_points) + len(selected_points)
            
            # 在地图上绘制选中的点位（点本身位置不变）
            marker, = ax.plot(lon, lat, 'ro', markersize=12, 
                            transform=ccrs.PlateCarree(), 
                            label=tr("step3_new_selected_point", "新选点位") if len(selected_points) == 0 else '')
            selected_markers.append(marker)
            
            # 计算标签位置，避免与已有标签重叠（只调整标签位置，不改变点位置）
            # 使用迭代调整算法
            base_offset = 0.6  # 基础偏移量（度），增大以确保标签不重叠
            # 根据标签文本长度估算标签宽度
            label_text = str(current_index)
            label_width = len(label_text) * 0.15 + 0.3
            min_label_distance = max(1.2, label_width)  # 标签之间的最小距离（度），至少1.2度
            
            # 初始标签位置（右上角）
            label_lon = lon + base_offset
            label_lat = lat + base_offset
            
            # 迭代调整标签位置，避免与已有标签重叠
            max_iterations = 30
            adjustment_factor = 0.3
            
            for iteration in range(max_iterations):
                has_overlap = False
                
                # 检查是否与已有标签位置重叠
                for existing in existing_points + selected_points:
                    if 'label_lon' in existing and 'label_lat' in existing:
                        existing_label_lon = existing['label_lon']
                        existing_label_lat = existing['label_lat']
                        
                        dx = label_lon - existing_label_lon
                        dy = label_lat - existing_label_lat
                        distance = np.sqrt(dx**2 + dy**2)
                        
                        if distance < min_label_distance:
                            has_overlap = True
                            
                            # 如果距离为0或非常小，随机选择一个方向
                            if distance < 0.01:
                                angle = np.random.uniform(0, 2 * np.pi)
                                dx = np.cos(angle)
                                dy = np.sin(angle)
                            else:
                                # 归一化方向向量
                                dx /= distance
                                dy /= distance
                            
                            # 计算需要移动的距离
                            move_distance = (min_label_distance - distance) * adjustment_factor
                            
                            # 调整标签位置（远离重叠的标签）
                            label_lon += dx * move_distance
                            label_lat += dy * move_distance
                            
                            # 确保标签位置在显示范围内
                            label_lon = max(display_lon_min, min(display_lon_max, label_lon))
                            label_lat = max(display_lat_min, min(display_lat_max, label_lat))
                            
                            break
                
                # 如果没有重叠，退出循环
                if not has_overlap:
                    break
            
            # 计算偏移距离
            offset_dist = np.sqrt((label_lon - lon)**2 + (label_lat - lat)**2)
            
            # 如果偏移较大，绘制连接线
            if offset_dist > base_offset * 0.5:
                line, = ax.plot([lon, label_lon], [lat, label_lat],
                               transform=ccrs.PlateCarree(), 
                               color='gray', linewidth=0.5, linestyle='--', alpha=0.5, zorder=1)
            else:
                line = None
            
            # 添加标签（保存引用以便删除，只绘制标签，点已经在上面绘制了）
            text_label = ax.text(label_lon, label_lat, f"{current_index}", 
                   transform=ccrs.PlateCarree(), fontsize=9, zorder=2,
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7),
                   verticalalignment='center', horizontalalignment='left')
            
            # 创建点位数据，包含marker和text_label引用
            point_data = {
                'lon': lon,
                'lat': lat,
                'name': str(current_index),
                'marker': marker,
                'text_label': text_label,
                'label_lon': label_lon,
                'label_lat': label_lat,
                'line': line
            }
            selected_points.append(point_data)
            
            # 刷新地图
            fig.canvas.draw()
        
        # 绑定点击事件
        fig.canvas.mpl_connect('button_press_event', on_click)
        
        # 添加图例
        if existing_points:
            ax.legend(loc='upper right')
        
        # 添加网格线
        gl = ax.gridlines(crs=ccrs.PlateCarree(), draw_labels=True, 
                         linewidth=0.5, color='gray', alpha=0.5, linestyle='--')
        gl.top_labels = False
        gl.right_labels = False
        
        # 设置标题
        ax.set_title(tr("step3_select_on_map_subtitle", "在地图上选点（点击地图选择点位，可多选）"), fontsize=14, fontweight='bold')
        
        # 使用QDialog显示地图，确保窗口关闭后才执行后续代码
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("step3_select_on_map_title", "在地图上选点"))
        dialog.resize(1400, 900)
        
        # 使用水平布局，地图在左侧，按钮在右侧
        main_layout = QHBoxLayout(dialog)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # 将matplotlib图形嵌入到QDialog中（左侧）
        canvas = FigureCanvas(fig)
        main_layout.addWidget(canvas, 1)  # 拉伸因子为1，占据主要空间
        
        # 按钮区域（右侧）
        button_layout = QVBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()  # 顶部空白
        
        btn_confirm = PrimaryPushButton(tr("step3_confirm_add_point", "确认并添加点位"))
        btn_confirm.setStyleSheet(self._get_button_style())
        btn_confirm.clicked.connect(dialog.accept)
        button_layout.addWidget(btn_confirm)
        
        btn_cancel = PrimaryPushButton(tr("cancel", "取消"))
        btn_cancel.setStyleSheet(self._get_button_style())
        btn_cancel.clicked.connect(dialog.reject)
        button_layout.addWidget(btn_cancel)
        
        # 删除上一个点按钮（放在最后）
        def delete_last_point():
            # 优先删除当前选点会话中选中的点位
            if selected_points:
                # 删除最后一个选中的点位
                removed_point = selected_points.pop()
                # 删除对应的标记
                if 'marker' in removed_point:
                    removed_point['marker'].remove()
                # 删除对应的文本标签
                if 'text_label' in removed_point:
                    removed_point['text_label'].remove()
                # 从markers列表中删除
                if selected_markers:
                    selected_markers.pop()
                # 刷新地图
                fig.canvas.draw()
            # 如果没有选中的点位，删除表格中最后一行（跳过表头）
            elif target_table_obj.rowCount() > 1:
                # 获取最后一行（跳过表头，表头是第0行）
                last_row = target_table_obj.rowCount() - 1
                if last_row > 0:  # 确保不是表头
                    # 获取要删除的点位信息（根据表格类型确定列索引）
                    if has_time_column:
                        # 航迹模式：列顺序 0-时间, 1-经度, 2-纬度, 3-名称
                        lon_item = target_table_obj.item(last_row, 1)
                        lat_item = target_table_obj.item(last_row, 2)
                        name_item = target_table_obj.item(last_row, 3)
                    else:
                        # 谱空间逐点计算模式：列顺序 0-经度, 1-纬度, 2-名称
                        lon_item = target_table_obj.item(last_row, 0)
                        lat_item = target_table_obj.item(last_row, 1)
                        name_item = target_table_obj.item(last_row, 2)
                    
                    if lon_item and lat_item:
                        try:
                            lon = float(lon_item.text().strip())
                            lat = float(lat_item.text().strip())
                            name = name_item.text().strip() if name_item else f"点位{last_row}"
                            
                            # 从地图上删除对应的标记和文本标签
                            for i, point in enumerate(existing_points):
                                if abs(point['lon'] - lon) < 0.001 and abs(point['lat'] - lat) < 0.001:
                                    # 找到对应的点位，删除标记和文本标签
                                    if 'marker' in point:
                                        point['marker'].remove()
                                    if 'text_label' in point:
                                        point['text_label'].remove()
                                    # 从列表中删除
                                    existing_points.pop(i)
                                    if i < len(existing_markers):
                                        existing_markers.pop(i)
                                    if i < len(existing_text_labels):
                                        existing_text_labels.pop(i)
                                    break
                            
                            # 从表格中删除行
                            target_table_obj.removeRow(last_row)
                            
                            # 刷新地图
                            fig.canvas.draw()
                        except ValueError:
                            pass
        
        btn_delete_last = PrimaryPushButton(tr("step3_delete_last_point", "删除上一个点"))
        btn_delete_last.setStyleSheet(self._get_button_style())
        btn_delete_last.clicked.connect(delete_last_point)
        button_layout.addWidget(btn_delete_last)
        
        button_layout.addStretch()  # 底部空白
        
        # 创建按钮容器，设置白色背景
        button_widget = QWidget()
        button_widget.setLayout(button_layout)
        button_widget.setFixedWidth(180)  # 增加宽度以完整显示按钮文字
        button_widget.setStyleSheet("QWidget { background-color: white; }")
        main_layout.addWidget(button_widget, 0)  # 不拉伸
        
        # 显示对话框（模态），只有在点击确认时才添加点位
        result = dialog.exec()
        
        # 只有在点击确认按钮时才添加点位
        if result == QDialog.DialogCode.Accepted and selected_points:
            for point in selected_points:
                # 检查名称是否已存在
                name = point['name']
                for i in range(1, target_table_obj.rowCount()):
                    # 根据表格类型确定名称列的索引
                    name_col = 3 if has_time_column else 2
                    existing_name = target_table_obj.item(i, name_col)
                    if existing_name and existing_name.text().strip() == name:
                        # 如果名称已存在，使用下一个索引
                        current_index = target_table_obj.rowCount() - 1
                        name = str(current_index)
                        point['name'] = name
                        break
                
                # 添加到表格
                row = target_table_obj.rowCount()
                target_table_obj.insertRow(row)
                
                # 如果是航迹模式，列顺序：0-时间, 1-经度, 2-纬度, 3-名称
                if has_time_column:
                    # 获取默认时间（风场文件的第一个时间）
                    default_time = self._get_wind_nc_first_time() if hasattr(self, '_get_wind_nc_first_time') else ""
                    time_item = QTableWidgetItem(default_time)
                    time_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                    target_table_obj.setItem(row, 0, time_item)
                    lon_item = QTableWidgetItem(f"{point['lon']:.6f}")
                    lon_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                    lat_item = QTableWidgetItem(f"{point['lat']:.6f}")
                    lat_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                    name_item = QTableWidgetItem(name)
                    name_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                    target_table_obj.setItem(row, 1, lon_item)
                    target_table_obj.setItem(row, 2, lat_item)
                    target_table_obj.setItem(row, 3, name_item)
                else:
                    # 谱空间逐点计算模式，列顺序：0-经度, 1-纬度, 2-名称
                    lon_item = QTableWidgetItem(f"{point['lon']:.6f}")
                    lon_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                    lat_item = QTableWidgetItem(f"{point['lat']:.6f}")
                    lat_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)
                    name_item = QTableWidgetItem(name)
                    name_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)
                    target_table_obj.setItem(row, 0, lon_item)
                    target_table_obj.setItem(row, 1, lat_item)
                    target_table_obj.setItem(row, 2, name_item)
            
            # 更新表格高度，使其根据内容自动展开
            row_count = target_table_obj.rowCount()
            if row_count > 0:
                target_table_obj.resizeRowsToContents()
                total_height = 0
                for i in range(row_count):
                    total_height += target_table_obj.rowHeight(i)
                # 加上表头高度（如果有）
                header_height = target_table_obj.horizontalHeader().height() if target_table_obj.horizontalHeader().isVisible() else 0
                content_height = total_height + header_height + 10  # 加上一些边距
                target_table_obj.setMinimumHeight(content_height)
                # 移除最大高度限制，允许完全展开
                target_table_obj.setMaximumHeight(16777215)
            
            # 在log中显示添加成功信息
            self.log(tr("step4_points_added", "✅ 已将 {count} 个点位添加到表格").format(count=len(selected_points)))

    def _import_points_from_file(self):
        """从 points.list 文件导入点位"""
        # 选择文件
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 points.list 文件",
            self.selected_folder if hasattr(self, 'selected_folder') and self.selected_folder else os.getcwd(),
            "列表文件 (*.list);;所有文件 (*.*)"
        )
        
        if not file_path:
            return
        
        if not os.path.exists(file_path):
            InfoBar.warning(
                title=tr("step3_import_failed", "导入失败"),
                content=tr("step3_file_not_exists", "文件不存在"),
                duration=3000,
                parent=self
            )
            return
        
        # 读取并解析文件
        imported_points = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):  # 跳过空行和注释
                        continue
                    
                    # 解析格式：经度 纬度 '名称'
                    # 使用正则表达式匹配格式：数字 数字 '字符串'
                    match = re.match(r'(\S+)\s+(\S+)\s+[\'"]?([^\'"]+)[\'"]?', line)
                    if match:
                        lon_str = match.group(1)
                        lat_str = match.group(2)
                        name = match.group(3).strip().strip("'\"")  # 移除引号
                        
                        # 跳过 STOPSTRING 行
                        if name.upper() == 'STOPSTRING':
                            continue
                        
                        try:
                            lon = float(lon_str)
                            lat = float(lat_str)
                            
                            # 验证经纬度范围
                            if not (-180 <= lon <= 180):
                                self.log(tr("lon_out_of_range_skipped", "⚠️ 第 {line} 行：经度 {lon} 超出范围，已跳过").format(line=line_num, lon=lon))
                                continue
                            if not (-90 <= lat <= 90):
                                self.log(tr("lat_out_of_range_skipped", "⚠️ 第 {line} 行：纬度 {lat} 超出范围，已跳过").format(line=line_num, lat=lat))
                                continue
                            
                            imported_points.append({
                                'lon': lon,
                                'lat': lat,
                                'name': name
                            })
                        except ValueError:
                            self.log(tr("lon_lat_parse_failed_skipped", "⚠️ 第 {line} 行：无法解析经纬度，已跳过").format(line=line_num))
                            continue
                    else:
                        self.log(tr("line_format_error_skipped", "⚠️ 第 {line} 行：格式不正确，已跳过").format(line=line_num))
                        continue
        
        except Exception as e:
            InfoBar.error(
                title=tr("step3_import_failed", "导入失败"),
                content=tr("step3_read_file_error", "读取文件时出错：{error}").format(error=str(e)),
                duration=3000,
                parent=self
            )
            return
        
        if not imported_points:
            InfoBar.warning(
                title=tr("step3_import_failed", "导入失败"),
                content=tr("step3_no_valid_points_in_file", "文件中没有有效的点位数据"),
                duration=3000,
                parent=self
            )
            return
        
        # 检查地图范围（如果可用）
        bounds = self._read_grid_meta_bounds()
        if bounds:
            valid_points = []
            for point in imported_points:
                if (bounds['lon_min'] <= point['lon'] <= bounds['lon_max'] and
                    bounds['lat_min'] <= point['lat'] <= bounds['lat_max']):
                    valid_points.append(point)
                else:
                    self.log(tr("step3_point_out_of_range_skipped", "⚠️ 点位 {name} ({lon}, {lat}) 不在地图范围内，已跳过").format(name=point['name'], lon=f"{point['lon']:.4f}", lat=f"{point['lat']:.4f}"))
            
            if not valid_points:
                InfoBar.warning(
                    title=tr("step3_import_failed", "导入失败"),
                    content=tr("step3_all_points_out_of_range", "所有点位都不在地图范围内"),
                    duration=3000,
                    parent=self
                )
                return
            imported_points = valid_points
        
        # 添加到表格
        added_count = 0
        for point in imported_points:
            # 检查名称是否已存在
            name = point['name']
            name_exists = False
            for i in range(1, self.spectral_points_table.rowCount()):
                existing_name = self.spectral_points_table.item(i, 2)
                if existing_name and existing_name.text().strip() == name:
                    # 如果名称已存在，使用下一个索引
                    current_index = self.spectral_points_table.rowCount() - 1
                    name = str(current_index)
                    point['name'] = name
                    break
            
            # 检查位置是否已存在
            position_exists = False
            for i in range(1, self.spectral_points_table.rowCount()):
                lon_item = self.spectral_points_table.item(i, 0)
                lat_item = self.spectral_points_table.item(i, 1)
                if lon_item and lat_item:
                    try:
                        existing_lon = float(lon_item.text().strip())
                        existing_lat = float(lat_item.text().strip())
                        if abs(existing_lon - point['lon']) < 0.001 and abs(existing_lat - point['lat']) < 0.001:
                            position_exists = True
                            break
                    except ValueError:
                        continue
            
            if position_exists:
                self.log(tr("point_already_exists_skipped", "⚠️ 点位 {name} ({lon}, {lat}) 位置已存在，已跳过").format(name=point['name'], lon=f"{point['lon']:.4f}", lat=f"{point['lat']:.4f}"))
                continue
            
            # 添加到表格
            row = self.spectral_points_table.rowCount()
            self.spectral_points_table.insertRow(row)
            lon_item = QTableWidgetItem(f"{point['lon']:.6f}")
            lon_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            lat_item = QTableWidgetItem(f"{point['lat']:.6f}")
            lat_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)
            name_item = QTableWidgetItem(name)
            name_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)
            self.spectral_points_table.setItem(row, 0, lon_item)
            self.spectral_points_table.setItem(row, 1, lat_item)
            self.spectral_points_table.setItem(row, 2, name_item)
            added_count += 1
        
        # 更新表格高度
        row_count = self.spectral_points_table.rowCount()
        if row_count > 0:
            self.spectral_points_table.resizeRowsToContents()
            total_height = 0
            for i in range(row_count):
                total_height += self.spectral_points_table.rowHeight(i)
            header_height = self.spectral_points_table.horizontalHeader().height() if self.spectral_points_table.horizontalHeader().isVisible() else 0
            content_height = total_height + header_height + 10
            self.spectral_points_table.setMinimumHeight(content_height)
            self.spectral_points_table.setMaximumHeight(16777215)
        
        # 在log中显示导入成功信息
        self.log(tr("points_imported_from_file", "✅ 已从文件导入 {count} 个点位").format(count=added_count))

    def _check_and_load_points_list(self, silent=False):
        """检查工作目录是否存在 points.list 文件，如果存在则切换到谱空间逐点计算模式并导入点位（支持嵌套网格模式，优先检查 fine 目录）"""
        # 防止重复执行：检查是否正在处理中，以及是否已经处理过当前工作目录
        if not hasattr(self, '_points_list_processing'):
            self._points_list_processing = False
        if not hasattr(self, '_last_points_list_folder'):
            self._last_points_list_folder = None
        
        if not hasattr(self, 'selected_folder') or not self.selected_folder:
            return
        
        if not os.path.exists(self.selected_folder):
            return
        
        # 如果已经处理过当前工作目录，跳过
        if self._last_points_list_folder == self.selected_folder and self._points_list_processing:
            return
        
        # 标记为正在处理，并记录当前工作目录
        self._points_list_processing = True
        self._last_points_list_folder = self.selected_folder
        
        # 检查是否是嵌套网格模式（通过检查是否存在 coarse 和 fine 目录）
        coarse_dir = os.path.join(self.selected_folder, "coarse")
        fine_dir = os.path.join(self.selected_folder, "fine")
        is_nested_grid = (os.path.isdir(coarse_dir) and os.path.isdir(fine_dir))
        
        # 如果已经检测到 track_i.ww3，则切换到航迹模式并返回（track_i.ww3 优先级更高）
        track_file = os.path.join(self.selected_folder, "track_i.ww3")
        track_file_exists = os.path.exists(track_file)
        
        if not track_file_exists and is_nested_grid:
            track_file_coarse = os.path.join(coarse_dir, "track_i.ww3")
            track_file_fine = os.path.join(fine_dir, "track_i.ww3")
            if os.path.exists(track_file_coarse):
                track_file = track_file_coarse
                track_file_exists = True
            elif os.path.exists(track_file_fine):
                track_file = track_file_fine
                track_file_exists = True
        
        if track_file_exists:
            # 确保切换到航迹模式（如果还没有切换）
            if hasattr(self, 'calc_mode_combo'):
                track_text = tr("step3_track_mode", "航迹模式")
                current_mode = self.calc_mode_combo.currentText()
                if current_mode != track_text:
                    # 切换到航迹模式
                    self.calc_mode_combo.blockSignals(True)
                    self.calc_mode_combo.setCurrentText(track_text)
                    self.calc_mode_combo.blockSignals(False)
                    if hasattr(self, 'calc_mode_var'):
                        self.calc_mode_var = track_text
                    if hasattr(self, '_set_calc_mode'):
                        self._set_calc_mode(track_text, skip_block_check=True)
                    if not silent and hasattr(self, 'log'):
                        self.log(tr("track_file_detected", "✅ 检测到 track_i.ww3 文件，已自动切换到航迹模式"))
            # 重置处理标记
            self._points_list_processing = False
            return
        
        # 确定要检查的 points.list 文件路径
        if is_nested_grid:
            # 嵌套网格模式：优先检查 fine 目录下的 points.list
            points_list_path = os.path.join(fine_dir, "points.list")
        else:
            # 普通网格模式：检查工作目录下的 points.list
            points_list_path = os.path.join(self.selected_folder, "points.list")
        
        if not os.path.exists(points_list_path):
            # 检查 track_i.ww3 是否也不存在，如果都不存在，切换到区域计算模式
            track_file = os.path.join(self.selected_folder, "track_i.ww3")
            track_file_exists = os.path.exists(track_file)
            
            if not track_file_exists and is_nested_grid:
                track_file_coarse = os.path.join(coarse_dir, "track_i.ww3")
                track_file_fine = os.path.join(fine_dir, "track_i.ww3")
                track_file_exists = os.path.exists(track_file_coarse) or os.path.exists(track_file_fine)
            
            # 如果 track_i.ww3 和 points.list 都不存在，切换到区域计算模式
            if not track_file_exists:
                # 检查 UI 元素是否存在
                if hasattr(self, 'calc_mode_combo'):
                    region_text = tr("step3_region_scale", "区域尺度计算")
                    current_mode = self.calc_mode_combo.currentText()
                    if current_mode != region_text:
                        # 切换到区域计算模式
                        self.calc_mode_combo.blockSignals(True)
                        self.calc_mode_combo.setCurrentText(region_text)
                        self.calc_mode_combo.blockSignals(False)
                        if hasattr(self, 'calc_mode_var'):
                            self.calc_mode_var = region_text
                        if hasattr(self, '_set_calc_mode'):
                            self._set_calc_mode(region_text, skip_block_check=True)
            
            # 重置处理标记（但保留工作目录记录，避免重复检查）
            self._points_list_processing = False
            return
        
        # 检查表格是否存在（如果不存在，延迟执行，最多重试5次）
        if not hasattr(self, 'spectral_points_table'):
            # 延迟执行，等待 UI 初始化完成
            if not hasattr(self, '_points_list_check_count'):
                self._points_list_check_count = 0
            if self._points_list_check_count < 5:
                self._points_list_check_count += 1
                QtCore.QTimer.singleShot(200, lambda: self._check_and_load_points_list(silent=silent))
            else:
                # 重置计数器
                self._points_list_check_count = 0
            return
        
        # 检查计算模式下拉框是否存在（如果不存在，延迟执行，最多重试5次）
        if not hasattr(self, 'calc_mode_combo'):
            # 延迟执行，等待 UI 初始化完成
            if not hasattr(self, '_points_list_check_count'):
                self._points_list_check_count = 0
            if self._points_list_check_count < 5:
                self._points_list_check_count += 1
                QtCore.QTimer.singleShot(200, lambda: self._check_and_load_points_list(silent=silent))
            else:
                # 重置计数器
                self._points_list_check_count = 0
            return
        
        # 重置计数器（成功找到 UI 元素）
        if hasattr(self, '_points_list_check_count'):
            self._points_list_check_count = 0
        
        try:
            # 切换到"谱空间逐点计算"模式
            spectral_text = tr("step3_spectral_point", "谱空间逐点计算")
            if hasattr(self, 'calc_mode_combo'):
                self.calc_mode_combo.blockSignals(True)
                self.calc_mode_combo.setCurrentText(spectral_text)
                self.calc_mode_combo.blockSignals(False)
                if hasattr(self, 'calc_mode_var'):
                    self.calc_mode_var = spectral_text
                # 触发模式切换，显示点位管理界面（跳过阻止检查，因为这是自动切换）
                if hasattr(self, '_set_calc_mode'):
                    self._set_calc_mode(spectral_text, skip_block_check=True)
            
            # 读取并解析 points.list 文件
            imported_points = []
            with open(points_list_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):  # 跳过空行和注释
                        continue
                    
                    # 解析格式：经度 纬度 '名称'
                    match = re.match(r'(\S+)\s+(\S+)\s+[\'"]?([^\'"]+)[\'"]?', line)
                    if match:
                        lon_str = match.group(1)
                        lat_str = match.group(2)
                        name = match.group(3).strip().strip("'\"")  # 移除引号
                        
                        # 跳过 STOPSTRING 行
                        if name.upper() == 'STOPSTRING':
                            continue
                        
                        try:
                            lon = float(lon_str)
                            lat = float(lat_str)
                            
                            # 跳过 STOPSTRING 坐标（0.0 0.0）
                            if abs(lon) < 1e-6 and abs(lat) < 1e-6 and name.upper() == 'STOPSTRING':
                                continue
                            
                            # 验证经纬度范围
                            if not (-180 <= lon <= 180):
                                continue
                            if not (-90 <= lat <= 90):
                                continue
                            
                            imported_points.append({
                                'lon': lon,
                                'lat': lat,
                                'name': name
                            })
                        except ValueError:
                            continue
            
            if not imported_points:
                if not silent:
                    self.log(tr("no_valid_points_in_list", "⚠️ points.list 文件中没有有效的点位数据"))
                return
            
            # 清空表格中已有的点位（保留表头）
            current_row_count = self.spectral_points_table.rowCount()
            # 从后往前删除，避免索引问题
            for i in range(current_row_count - 1, 0, -1):  # 保留表头（第0行）
                self.spectral_points_table.removeRow(i)
            
            # 导入点位到表格
            for point in imported_points:
                row = self.spectral_points_table.rowCount()
                self.spectral_points_table.insertRow(row)
                lon_item = QTableWidgetItem(f"{point['lon']:.6f}")
                lon_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                lat_item = QTableWidgetItem(f"{point['lat']:.6f}")
                lat_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)
                name_item = QTableWidgetItem(point['name'])
                name_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)
                self.spectral_points_table.setItem(row, 0, lon_item)
                self.spectral_points_table.setItem(row, 1, lat_item)
                self.spectral_points_table.setItem(row, 2, name_item)
            
            # 更新表格高度
            row_count = self.spectral_points_table.rowCount()
            if row_count > 0:
                self.spectral_points_table.resizeRowsToContents()
                total_height = 0
                for i in range(row_count):
                    total_height += self.spectral_points_table.rowHeight(i)
                header_height = self.spectral_points_table.horizontalHeader().height() if self.spectral_points_table.horizontalHeader().isVisible() else 0
                content_height = total_height + header_height + 10
                self.spectral_points_table.setMinimumHeight(content_height)
                self.spectral_points_table.setMaximumHeight(16777215)
            
            # 只有在成功导入点位后才输出日志，避免重复
            if len(imported_points) > 0 and not silent:
                self.log(tr("points_list_detected", "✅ 检测到 points.list 文件，已自动切换到谱空间逐点计算模式并导入 {count} 个点位").format(count=len(imported_points)))
        
        except Exception as e:
            if not silent:
                self.log(tr("points_list_load_error", "⚠️ 自动加载 points.list 时出错：{error}").format(error=str(e)))
        finally:
            # 重置处理标记
            self._points_list_processing = False

    def _should_block_calc_mode_switch(self):
        """检查是否应该阻止切换计算模式（当存在 track_i.ww3 或 points.list 时）"""
        if not hasattr(self, 'selected_folder') or not self.selected_folder:
            return False
        
        if not os.path.exists(self.selected_folder):
            return False
        
        # 检查是否是嵌套网格模式
        coarse_dir = os.path.join(self.selected_folder, "coarse")
        fine_dir = os.path.join(self.selected_folder, "fine")
        is_nested_grid = (os.path.isdir(coarse_dir) and os.path.isdir(fine_dir))
        
        # 检查 track_i.ww3 文件（在工作目录、coarse 或 fine 目录）
        track_file = os.path.join(self.selected_folder, "track_i.ww3")
        if os.path.exists(track_file):
            return True
        
        if is_nested_grid:
            track_file_coarse = os.path.join(coarse_dir, "track_i.ww3")
            track_file_fine = os.path.join(fine_dir, "track_i.ww3")
            if os.path.exists(track_file_coarse) or os.path.exists(track_file_fine):
                return True
        
        # 检查 points.list 文件（在工作目录、coarse 或 fine 目录）
        points_list_path = os.path.join(self.selected_folder, "points.list")
        if os.path.exists(points_list_path):
            return True
        
        if is_nested_grid:
            points_list_coarse = os.path.join(coarse_dir, "points.list")
            points_list_fine = os.path.join(fine_dir, "points.list")
            if os.path.exists(points_list_coarse) or os.path.exists(points_list_fine):
                return True
        
        return False

    def _check_and_switch_to_track_mode(self):
        """检查工作目录是否存在 track_i.ww3 文件，如果存在则自动切换到航迹模式（支持嵌套网格模式，优先检查 fine 目录）"""
        # 防止重复执行：检查是否正在处理中，以及是否已经处理过当前工作目录
        if not hasattr(self, '_track_mode_processing'):
            self._track_mode_processing = False
        if not hasattr(self, '_last_track_mode_folder'):
            self._last_track_mode_folder = None
        
        if not hasattr(self, 'selected_folder') or not self.selected_folder:
            return
        
        if not os.path.exists(self.selected_folder):
            return
        
        # 如果已经处理过当前工作目录，跳过
        if self._last_track_mode_folder == self.selected_folder and self._track_mode_processing:
            return
        
        # 标记为正在处理，并记录当前工作目录
        self._track_mode_processing = True
        self._last_track_mode_folder = self.selected_folder
        
        # 检查是否是嵌套网格模式
        coarse_dir = os.path.join(self.selected_folder, "coarse")
        fine_dir = os.path.join(self.selected_folder, "fine")
        is_nested_grid = (os.path.isdir(coarse_dir) and os.path.isdir(fine_dir))
        
        # 确定要检查的 track_i.ww3 文件路径（优先检查工作目录，然后是 fine 目录，最后是 coarse 目录）
        track_file = os.path.join(self.selected_folder, "track_i.ww3")
        if not os.path.exists(track_file) and is_nested_grid:
            track_file_fine = os.path.join(fine_dir, "track_i.ww3")
            if os.path.exists(track_file_fine):
                track_file = track_file_fine
            else:
                track_file_coarse = os.path.join(coarse_dir, "track_i.ww3")
                if os.path.exists(track_file_coarse):
                    track_file = track_file_coarse
        
        if not os.path.exists(track_file):
            # 重置处理标记（但保留工作目录记录，避免重复检查）
            self._track_mode_processing = False
            return
        
        # 检查计算模式下拉框是否存在（如果不存在，延迟执行，最多重试5次）
        if not hasattr(self, 'calc_mode_combo'):
            # 延迟执行，等待 UI 初始化完成
            if not hasattr(self, '_track_mode_check_count'):
                self._track_mode_check_count = 0
            if self._track_mode_check_count < 5:
                self._track_mode_check_count += 1
                # 重置处理标记，允许延迟重试
                self._track_mode_processing = False
                QtCore.QTimer.singleShot(200, lambda: self._check_and_switch_to_track_mode())
            else:
                # 重置计数器和处理标记
                self._track_mode_check_count = 0
                self._track_mode_processing = False
            return
        
        # 重置计数器（成功找到下拉框）
        if hasattr(self, '_track_mode_check_count'):
            self._track_mode_check_count = 0
        
        try:
            # 切换到"航迹模式"
            track_text = tr("step3_track_mode", "航迹模式")
            if hasattr(self, 'calc_mode_combo'):
                # 先更新 calc_mode_var，确保状态一致
                if hasattr(self, 'calc_mode_var'):
                    self.calc_mode_var = track_text
                
                self.calc_mode_combo.blockSignals(True)
                self.calc_mode_combo.setCurrentText(track_text)
                self.calc_mode_combo.blockSignals(False)
                
                # 重置自动导入标记，允许自动读取
                if hasattr(self, '_track_file_auto_imported'):
                    self._track_file_auto_imported = False
                
                # 触发模式切换（跳过阻止检查，因为这是自动切换）
                if hasattr(self, '_set_calc_mode'):
                    self._set_calc_mode(track_text, skip_block_check=True)
            
            if hasattr(self, 'log'):
                self.log(tr("track_file_detected", "✅ 检测到 track_i.ww3 文件，已自动切换到航迹模式"))
            
            # 注意：自动读取 track_i.ww3 文件将在 _set_calc_mode 中执行（当表格显示后）
        except Exception as e:
            if hasattr(self, 'log'):
                self.log(tr("switch_to_track_mode_error", "❌ 切换到航迹模式时出错：{error}").format(error=e))
        finally:
            # 重置处理标记
            self._track_mode_processing = False

    def _add_track_point(self):
        """添加航迹模式点位"""
        if not hasattr(self, 'track_points_table'):
            return

        class TrackPointDialog(MessageBoxBase):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle(tr("step3_add_track_point_title", "添加航迹点位"))
                # 设置按钮文本
                if hasattr(self, 'yesButton') and self.yesButton:
                    self.yesButton.setText(tr("confirm", "确定"))
                if hasattr(self, 'cancelButton') and self.cancelButton:
                    self.cancelButton.setText(tr("cancel", "取消"))
                dialog_layout = QVBoxLayout()
                dialog_layout.setSpacing(10)
                
                grid_layout = QGridLayout()
                grid_layout.setColumnStretch(0, 0)
                grid_layout.setColumnStretch(1, 1)
                grid_layout.setSpacing(10)

                input_style = """
                    LineEdit {
                        padding: 5px;
                        border: 1px solid rgba(0, 0, 0, 0.1);
                        border-radius: 4px;
                    }
                """

                # 经度行
                lon_label = QLabel(tr("step3_longitude", "经度") + ":")
                lon_edit = LineEdit()
                lon_edit.setPlaceholderText(tr("step3_lon_example", "例如: 120.5"))
                lon_edit.setMinimumWidth(300)
                lon_edit.setStyleSheet(input_style)
                grid_layout.addWidget(lon_label, 0, 0)
                grid_layout.addWidget(lon_edit, 0, 1)

                # 纬度行
                lat_label = QLabel(tr("step3_latitude", "纬度") + ":")
                lat_edit = LineEdit()
                lat_edit.setPlaceholderText(tr("step3_lat_example", "例如: 30.2"))
                lat_edit.setMinimumWidth(300)
                lat_edit.setStyleSheet(input_style)
                grid_layout.addWidget(lat_label, 1, 0)
                grid_layout.addWidget(lat_edit, 1, 1)

                # 名称行
                name_label = QLabel(tr("step3_name", "名称") + ":")
                name_edit = LineEdit()
                name_edit.setPlaceholderText(tr("step3_name_example", "例如: 点位1"))
                name_edit.setMinimumWidth(300)
                name_edit.setStyleSheet(input_style)
                grid_layout.addWidget(name_label, 2, 0)
                grid_layout.addWidget(name_edit, 2, 1)

                # 时间行
                time_label = QLabel(tr("step3_time", "时间") + ":")
                time_edit = LineEdit()
                time_edit.setPlaceholderText(tr("time_example", "例如: 2024-01-01 00:00:00"))
                time_edit.setMinimumWidth(300)
                time_edit.setStyleSheet(input_style)
                grid_layout.addWidget(time_label, 3, 0)
                grid_layout.addWidget(time_edit, 3, 1)

                dialog_layout.addLayout(grid_layout)
                self.viewLayout.addLayout(dialog_layout)

                # 保存输入框引用
                self.lon_edit = lon_edit
                self.lat_edit = lat_edit
                self.name_edit = name_edit
                self.time_edit = time_edit

        # 计算当前点的索引（表格行数 - 1，因为表头行是第0行）
        current_index = self.track_points_table.rowCount() - 1
        if current_index < 0:
            current_index = 0
        
        dialog = TrackPointDialog(self)
        # 设置名称默认值为当前索引
        dialog.name_edit.setText(str(current_index))
        # 设置默认时间为风场文件的第一个时间
        default_time = self._get_wind_nc_first_time()
        if default_time:
            dialog.time_edit.setText(default_time)

        if dialog.exec():
            lon = dialog.lon_edit.text().strip()
            lat = dialog.lat_edit.text().strip()
            name = dialog.name_edit.text().strip()
            time_str = dialog.time_edit.text().strip()
            # 如果名称为空，使用当前索引作为默认名称
            if not name:
                name = str(current_index)
            if lon and lat and name and time_str:
                # 验证经度纬度是否为有效数字
                try:
                    lon_float = float(lon)
                    lat_float = float(lat)
                    if not (-180 <= lon_float <= 180):
                        InfoBar.warning(
                            title=tr("step3_add_failed", "添加失败"),
                            content=tr("step3_lon_range_error", "经度必须在 -180 到 180 之间"),
                            duration=3000,
                            parent=self
                        )
                        return
                    if not (-90 <= lat_float <= 90):
                        InfoBar.warning(
                            title=tr("step3_add_failed", "添加失败"),
                            content=tr("step3_lat_range_error", "纬度必须在 -90 到 90 之间"),
                            duration=3000,
                            parent=self
                        )
                        return
                except ValueError:
                    InfoBar.warning(
                        title=tr("step3_add_failed", "添加失败"),
                        content=tr("step3_lon_lat_must_be_number", "经度和纬度必须是有效数字"),
                        duration=3000,
                        parent=self
                    )
                    return
                
                # 检查点位是否在地图文件范围内
                bounds = self._read_grid_meta_bounds()
                if bounds:
                    if not (bounds['lon_min'] <= lon_float <= bounds['lon_max']):
                        InfoBar.warning(
                            title=tr("step3_add_failed", "添加失败"),
                            content=tr("step3_lon_out_of_range", "经度 {lon} 不在地图范围内 [{lon_min}, {lon_max}]").format(lon=f"{lon_float:.4f}", lon_min=f"{bounds['lon_min']:.4f}", lon_max=f"{bounds['lon_max']:.4f}"),
                            duration=3000,
                            parent=self
                        )
                        return
                    if not (bounds['lat_min'] <= lat_float <= bounds['lat_max']):
                        InfoBar.warning(
                            title=tr("step3_add_failed", "添加失败"),
                            content=tr("step3_lat_out_of_range", "纬度 {lat} 不在地图范围内 [{lat_min}, {lat_max}]").format(lat=f"{lat_float:.4f}", lat_min=f"{bounds['lat_min']:.4f}", lat_max=f"{bounds['lat_max']:.4f}"),
                            duration=3000,
                            parent=self
                        )
                        return

                # 检查名称是否已存在（跳过表头行，从第1行开始检查）
                for i in range(1, self.track_points_table.rowCount()):
                    existing_name = self.track_points_table.item(i, 3)  # 名称在第3列
                    if existing_name and existing_name.text().strip() == name:
                        InfoBar.warning(
                            title=tr("step3_add_failed", "添加失败"),
                            content=tr("step3_name_exists", "名称 '{name}' 已存在").format(name=name),
                            duration=3000,
                            parent=self
                        )
                        return

                # 添加到表格（插入到表头行之后，即第1行开始）
                # 列顺序：0-时间, 1-经度, 2-纬度, 3-名称
                row = self.track_points_table.rowCount()
                self.track_points_table.insertRow(row)
                time_item = QTableWidgetItem(time_str)
                time_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                lon_item = QTableWidgetItem(lon)
                lon_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                lat_item = QTableWidgetItem(lat)
                lat_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                name_item = QTableWidgetItem(name)
                name_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                self.track_points_table.setItem(row, 0, time_item)
                self.track_points_table.setItem(row, 1, lon_item)
                self.track_points_table.setItem(row, 2, lat_item)
                self.track_points_table.setItem(row, 3, name_item)

                InfoBar.success(
                    title=tr("step3_add_success", "添加成功"),
                    content=tr("step3_point_added", "已添加点位 '{name}'").format(name=name),
                    duration=2000,
                    parent=self
                )
            else:
                InfoBar.warning(
                    title=tr("step3_add_failed", "添加失败"),
                    content=tr("step3_lon_lat_name_time_required", "经度、纬度、名称和时间不能为空"),
                    duration=3000,
                    parent=self
                )

    def _edit_track_point(self):
        """修改航迹模式点位"""
        if not hasattr(self, 'track_points_table'):
            return
        
        current_row = self.track_points_table.currentRow()
        if current_row < 0:
            InfoBar.warning(
                title=tr("step3_edit_failed", "修改失败"),
                content=tr("step3_please_select_point", "请先选择要修改的点位"),
                duration=3000,
                parent=self
            )
            return

        # 检查是否是表头行（第0行），静默返回
        if current_row == 0:
            return

        # 列顺序：0-时间, 1-经度, 2-纬度, 3-名称
        time_item = self.track_points_table.item(current_row, 0)
        lon_item = self.track_points_table.item(current_row, 1)
        lat_item = self.track_points_table.item(current_row, 2)
        name_item = self.track_points_table.item(current_row, 3)

        old_lon = lon_item.text().strip() if lon_item else ""
        old_lat = lat_item.text().strip() if lat_item else ""
        old_name = name_item.text().strip() if name_item else ""
        old_time = time_item.text().strip() if time_item else ""

        class TrackPointEditDialog(MessageBoxBase):
            def __init__(self, parent=None, lon="", lat="", name="", time_str=""):
                super().__init__(parent)
                self.setWindowTitle(tr("step3_edit_track_point_title", "修改航迹点位"))
                # 设置按钮文本
                if hasattr(self, 'yesButton') and self.yesButton:
                    self.yesButton.setText(tr("confirm", "确定"))
                if hasattr(self, 'cancelButton') and self.cancelButton:
                    self.cancelButton.setText(tr("cancel", "取消"))
                dialog_layout = QVBoxLayout()
                dialog_layout.setSpacing(10)
                
                grid_layout = QGridLayout()
                grid_layout.setColumnStretch(0, 0)
                grid_layout.setColumnStretch(1, 1)
                grid_layout.setSpacing(10)

                input_style = """
                    LineEdit {
                        padding: 5px;
                        border: 1px solid rgba(0, 0, 0, 0.1);
                        border-radius: 4px;
                    }
                """

                # 经度行
                lon_label = QLabel(tr("step3_longitude", "经度") + ":")
                lon_edit = LineEdit()
                lon_edit.setText(lon)
                lon_edit.setMinimumWidth(300)
                lon_edit.setStyleSheet(input_style)
                grid_layout.addWidget(lon_label, 0, 0)
                grid_layout.addWidget(lon_edit, 0, 1)

                # 纬度行
                lat_label = QLabel(tr("step3_latitude", "纬度") + ":")
                lat_edit = LineEdit()
                lat_edit.setText(lat)
                lat_edit.setMinimumWidth(300)
                lat_edit.setStyleSheet(input_style)
                grid_layout.addWidget(lat_label, 1, 0)
                grid_layout.addWidget(lat_edit, 1, 1)

                # 名称行
                name_label = QLabel(tr("step3_name", "名称") + ":")
                name_edit = LineEdit()
                name_edit.setText(name)
                name_edit.setMinimumWidth(300)
                name_edit.setStyleSheet(input_style)
                grid_layout.addWidget(name_label, 2, 0)
                grid_layout.addWidget(name_edit, 2, 1)

                # 时间行
                time_label = QLabel(tr("step3_time", "时间") + ":")
                time_edit = LineEdit()
                time_edit.setText(time_str)
                time_edit.setMinimumWidth(300)
                time_edit.setStyleSheet(input_style)
                grid_layout.addWidget(time_label, 3, 0)
                grid_layout.addWidget(time_edit, 3, 1)

                dialog_layout.addLayout(grid_layout)
                self.viewLayout.addLayout(dialog_layout)

                # 保存输入框引用
                self.lon_edit = lon_edit
                self.lat_edit = lat_edit
                self.name_edit = name_edit
                self.time_edit = time_edit

        dialog = TrackPointEditDialog(self, old_lon, old_lat, old_name, old_time)

        if dialog.exec():
            lon = dialog.lon_edit.text().strip()
            lat = dialog.lat_edit.text().strip()
            name = dialog.name_edit.text().strip()
            time_str = dialog.time_edit.text().strip()
            if lon and lat and name and time_str:
                # 验证经度纬度是否为有效数字
                try:
                    lon_float = float(lon)
                    lat_float = float(lat)
                    if not (-180 <= lon_float <= 180):
                        InfoBar.warning(
                            title=tr("step3_edit_failed", "修改失败"),
                            content=tr("step3_lon_range_error", "经度必须在 -180 到 180 之间"),
                            duration=3000,
                            parent=self
                        )
                        return
                    if not (-90 <= lat_float <= 90):
                        InfoBar.warning(
                            title=tr("step3_edit_failed", "修改失败"),
                            content=tr("step3_lat_range_error", "纬度必须在 -90 到 90 之间"),
                            duration=3000,
                            parent=self
                        )
                        return
                except ValueError:
                    InfoBar.warning(
                        title=tr("step3_edit_failed", "修改失败"),
                        content=tr("step3_lon_lat_must_be_number", "经度和纬度必须是有效数字"),
                        duration=3000,
                        parent=self
                    )
                    return
                
                # 检查点位是否在地图文件范围内
                bounds = self._read_grid_meta_bounds()
                if bounds:
                    if not (bounds['lon_min'] <= lon_float <= bounds['lon_max']):
                        InfoBar.warning(
                            title=tr("step3_edit_failed", "修改失败"),
                            content=tr("step3_lon_out_of_range", "经度 {lon} 不在地图范围内 [{lon_min}, {lon_max}]").format(lon=f"{lon_float:.4f}", lon_min=f"{bounds['lon_min']:.4f}", lon_max=f"{bounds['lon_max']:.4f}"),
                            duration=3000,
                            parent=self
                        )
                        return
                    if not (bounds['lat_min'] <= lat_float <= bounds['lat_max']):
                        InfoBar.warning(
                            title=tr("step3_edit_failed", "修改失败"),
                            content=tr("step3_lat_out_of_range", "纬度 {lat} 不在地图范围内 [{lat_min}, {lat_max}]").format(lat=f"{lat_float:.4f}", lat_min=f"{bounds['lat_min']:.4f}", lat_max=f"{bounds['lat_max']:.4f}"),
                            duration=3000,
                            parent=self
                        )
                        return

                # 检查名称是否已存在（跳过表头行和当前行）
                for i in range(1, self.track_points_table.rowCount()):
                    if i == current_row:
                        continue
                    existing_name = self.track_points_table.item(i, 3)  # 名称在第3列
                    if existing_name and existing_name.text().strip() == name:
                        InfoBar.warning(
                            title=tr("step3_edit_failed", "修改失败"),
                            content=tr("step3_name_exists", "名称 '{name}' 已存在").format(name=name),
                            duration=3000,
                            parent=self
                        )
                        return

                # 更新表格（列顺序：0-时间, 1-经度, 2-纬度, 3-名称）
                time_item = QTableWidgetItem(time_str)
                time_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                lon_item = QTableWidgetItem(lon)
                lon_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                lat_item = QTableWidgetItem(lat)
                lat_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                name_item = QTableWidgetItem(name)
                name_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                self.track_points_table.setItem(current_row, 0, time_item)
                self.track_points_table.setItem(current_row, 1, lon_item)
                self.track_points_table.setItem(current_row, 2, lat_item)
                self.track_points_table.setItem(current_row, 3, name_item)

                InfoBar.success(
                    title=tr("step3_edit_success", "修改成功"),
                    content=tr("step3_point_modified", "已修改点位 '{name}'").format(name=name),
                    duration=2000,
                    parent=self
                )
            else:
                InfoBar.warning(
                    title=tr("step3_edit_failed", "修改失败"),
                    content=tr("step3_lon_lat_name_time_required", "经度、纬度、名称和时间不能为空"),
                    duration=3000,
                    parent=self
                )

    def _delete_track_point(self):
        """删除航迹模式点位"""
        if not hasattr(self, 'track_points_table'):
            return
        
        current_row = self.track_points_table.currentRow()
        if current_row < 0:
            InfoBar.warning(
                title=tr("step3_delete_failed", "删除失败"),
                content=tr("step3_please_select_point_to_delete", "请先选择要删除的点位"),
                duration=3000,
                parent=self
            )
            return

        # 检查是否是表头行（第0行），静默返回
        if current_row == 0:
            return

        # 列顺序：0-时间, 1-经度, 2-纬度, 3-名称
        name_item = self.track_points_table.item(current_row, 3)
        if not name_item:
            return

        name = name_item.text().strip()

        # 直接删除，不需要确认弹窗
        self.track_points_table.removeRow(current_row)
        InfoBar.success(
            title=tr("step3_delete_success", "删除成功"),
            content=tr("step3_point_deleted", "已删除点位 '{name}'").format(name=name),
            duration=2000,
            parent=self
        )

    def _select_track_points_on_map(self):
        """在地图上选择航迹点位（与谱空间逐点计算模式共享选点功能，但添加到航迹模式表格）"""
        # 调用共享的选点功能，但指定目标表格为航迹模式表格
        self._select_points_on_map(target_table='track')

    def _get_wind_nc_first_time(self):
        """获取风场文件的第一个时间，格式为 YYYYMMDD HHMMSS"""
        if not hasattr(self, 'selected_folder') or not self.selected_folder:
            return None
        
        wind_nc_path = os.path.join(self.selected_folder, "wind.nc")
        if not os.path.exists(wind_nc_path):
            return None
        
        try:
            from netCDF4 import Dataset, num2date
            with Dataset(wind_nc_path, 'r') as nc:
                # 查找时间变量
                time_var = None
                for var_name in nc.variables:
                    var = nc.variables[var_name]
                    if hasattr(var, 'standard_name') and 'time' in var.standard_name.lower():
                        time_var = var
                        break
                    elif var_name.lower() in ['time', 'times', 't']:
                        time_var = var
                        break
                
                if time_var is None:
                    # 尝试查找第一个维度为时间的变量
                    for var_name in nc.variables:
                        var = nc.variables[var_name]
                        if len(var.dimensions) > 0 and 'time' in var.dimensions[0].lower():
                            time_dim = nc.dimensions[var.dimensions[0]]
                            if len(time_dim) > 0:
                                # 尝试读取时间坐标
                                if 'time' in nc.variables:
                                    time_var = nc.variables['time']
                                    break
                
                if time_var is None:
                    return None
                
                # 获取第一个时间值
                first_time_value = time_var[0]
                
                # 尝试转换时间
                if hasattr(time_var, 'units'):
                    try:
                        from netCDF4 import num2date
                        time_obj = num2date(first_time_value, time_var.units, calendar=getattr(time_var, 'calendar', 'standard'))
                        # 格式化为 YYYYMMDD HHMMSS
                        return time_obj.strftime("%Y%m%d %H%M%S")
                    except:
                        # 如果转换失败，尝试直接使用数值
                        pass
                
                # 如果无法转换，返回 None
                return None
        except Exception as e:
            if hasattr(self, 'log'):
                self.log(tr("read_wind_file_time_failed", "⚠️ 读取风场文件时间失败：{error}").format(error=e))
            return None

    def _import_track_from_file_dialog(self):
        """从文件选择对话框选择 track_i.ww3 文件并导入"""
        if not hasattr(self, 'track_points_table'):
            InfoBar.warning(
                title=tr("step3_import_failed", "导入失败"),
                content=tr("step3_table_not_initialized", "表格未初始化"),
                duration=3000,
                parent=self
            )
            return
        
        # 打开文件选择对话框
        initial_dir = self.selected_folder if hasattr(self, 'selected_folder') and self.selected_folder else os.getcwd()
        track_file, _ = QFileDialog.getOpenFileName(
            self,
            "选择 track_i.ww3 文件",
            initial_dir,
            "Track文件 (*.ww3);;所有文件 (*.*)"
        )
        
        if not track_file or not track_file.strip():
            return  # 用户取消了选择
        
        if not os.path.exists(track_file):
            InfoBar.warning(
                title=tr("step3_import_failed", "导入失败"),
                content=tr("step3_file_not_exists", "文件不存在"),
                duration=3000,
                parent=self
            )
            return
        
        # 使用选择的文件路径导入
        self._import_track_from_file(track_file)

    def _import_track_from_file(self, file_path=None):
        """从 track_i.ww3 文件导入航迹点位
        Args:
            file_path: 文件路径，如果为 None 或空字符串则自动查找当前工作目录
        """
        if not hasattr(self, 'track_points_table'):
            return
        
        # 如果没有指定文件路径，自动查找当前工作目录
        if not file_path or file_path == "":
            # 自动查找 track_i.ww3 文件
            if not hasattr(self, 'selected_folder') or not self.selected_folder:
                return
            
            # 检查是否是嵌套网格模式
            coarse_dir = os.path.join(self.selected_folder, "coarse")
            fine_dir = os.path.join(self.selected_folder, "fine")
            is_nested_grid = (os.path.isdir(coarse_dir) and os.path.isdir(fine_dir))
            
            # 确定要检查的 track_i.ww3 文件路径（优先检查工作目录，然后是 fine 目录，最后是 coarse 目录）
            track_file = os.path.join(self.selected_folder, "track_i.ww3")
            if not os.path.exists(track_file) and is_nested_grid:
                track_file_fine = os.path.join(fine_dir, "track_i.ww3")
                if os.path.exists(track_file_fine):
                    track_file = track_file_fine
                else:
                    track_file_coarse = os.path.join(coarse_dir, "track_i.ww3")
                    if os.path.exists(track_file_coarse):
                        track_file = track_file_coarse
            
            if not os.path.exists(track_file):
                return  # 静默返回，不显示错误
        else:
            # 使用指定的文件路径
            track_file = file_path
            if not os.path.exists(track_file):
                InfoBar.warning(
                    title=tr("step3_import_failed", "导入失败"),
                    content=tr("step3_file_not_exists", "文件不存在"),
                    duration=3000,
                    parent=self
                )
                return
        
        try:
            imported_count = 0
            with open(track_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
                # 跳过第一行标题行 "WAVEWATCH III TRACK LOCATIONS DATA"
                for line_num, line in enumerate(lines[1:], start=2):
                    line = line.strip()
                    if not line:
                        continue
                    
                    # 解析格式：日期时间 经度 纬度 名称
                    # 例如：20250103 000000   112.5   12.0    Track1
                    parts = line.split()
                    if len(parts) < 4:
                        continue
                    
                    try:
                        date_str = parts[0]  # YYYYMMDD
                        time_str = parts[1]  # HHMMSS
                        lon_str = parts[2]
                        lat_str = parts[3]
                        name = ' '.join(parts[4:]) if len(parts) > 4 else f"Track{line_num - 1}"
                        
                        # 验证日期时间格式
                        if len(date_str) != 8 or len(time_str) != 6:
                            continue
                        
                        # 组合时间和日期：YYYYMMDD HHMMSS
                        datetime_str = f"{date_str} {time_str}"
                        
                        lon = float(lon_str)
                        lat = float(lat_str)
                        
                        # 验证经纬度范围
                        if not (-180 <= lon <= 180):
                            if hasattr(self, 'log'):
                                self.log(tr("lon_out_of_range_skipped", "⚠️ 第 {line} 行：经度 {lon} 超出范围，已跳过").format(line=line_num, lon=lon))
                            continue
                        if not (-90 <= lat <= 90):
                            if hasattr(self, 'log'):
                                self.log(tr("lat_out_of_range_skipped", "⚠️ 第 {line} 行：纬度 {lat} 超出范围，已跳过").format(line=line_num, lat=lat))
                            continue
                        
                        # 检查名称是否已存在
                        name_exists = False
                        for i in range(1, self.track_points_table.rowCount()):
                            existing_name_item = self.track_points_table.item(i, 3)
                            if existing_name_item and existing_name_item.text().strip() == name:
                                # 如果名称已存在，添加行号后缀
                                name = f"{name}_{line_num}"
                                break
                        
                        # 添加到表格（列顺序：0-时间, 1-经度, 2-纬度, 3-名称）
                        row = self.track_points_table.rowCount()
                        self.track_points_table.insertRow(row)
                        
                        time_item = QTableWidgetItem(datetime_str)
                        time_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                        lon_item = QTableWidgetItem(f"{lon:.6f}")
                        lon_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                        lat_item = QTableWidgetItem(f"{lat:.6f}")
                        lat_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                        name_item = QTableWidgetItem(name)
                        name_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                        
                        self.track_points_table.setItem(row, 0, time_item)
                        self.track_points_table.setItem(row, 1, lon_item)
                        self.track_points_table.setItem(row, 2, lat_item)
                        self.track_points_table.setItem(row, 3, name_item)
                        
                        imported_count += 1
                    except (ValueError, IndexError) as e:
                        if hasattr(self, 'log'):
                            self.log(tr("line_parse_failed_skipped", "⚠️ 第 {line} 行：解析失败，已跳过 - {error}").format(line=line_num, error=e))
                        continue
            
            # 更新表格高度
            row_count = self.track_points_table.rowCount()
            if row_count > 0:
                self.track_points_table.resizeRowsToContents()
                total_height = 0
                for i in range(row_count):
                    total_height += self.track_points_table.rowHeight(i)
                header_height = self.track_points_table.horizontalHeader().height() if self.track_points_table.horizontalHeader().isVisible() else 0
                content_height = total_height + header_height + 10
                self.track_points_table.setMinimumHeight(content_height)
                self.track_points_table.setMaximumHeight(16777215)
            
            if hasattr(self, 'log'):
                self.log(tr("track_points_imported", "✅ 已从 track_i.ww3 导入 {count} 个航迹点位").format(count=imported_count))
            InfoBar.success(
                title=tr("step3_import_success", "导入成功"),
                content=tr("step3_track_points_imported", "已导入 {count} 个航迹点位").format(count=imported_count),
                duration=2000,
                parent=self
            )
        except Exception as e:
            if hasattr(self, 'log'):
                self.log(tr("track_file_import_failed", "❌ 导入 track_i.ww3 失败：{error}").format(error=e))
            InfoBar.error(
                title=tr("step3_import_failed", "导入失败"),
                content=tr("step3_read_file_failed", "读取文件失败：{error}").format(error=e),
                duration=3000,
                parent=self
            )


