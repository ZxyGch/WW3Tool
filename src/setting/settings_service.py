"""设置模块 - 业务逻辑部分
包含所有设置相关的业务逻辑函数"""
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
from qfluentwidgets import NavigationItemPosition, NavigationWidget, FluentIcon, HeaderCardWidget, ComboBox, TableWidget, CheckBox

from qfluentwidgets import SwitchButton

from PyQt6.QtGui import QColor, QIcon
from qfluentwidgets import MessageBoxBase
from PyQt6.QtWidgets import QTableWidgetItem, QHeaderView, QScrollArea
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

class SettingsServiceMixin:
    """设置相关的业务逻辑 Mixin"""

    @staticmethod
    def _unst_parse_float(text, fallback):
        try:
            return float(str(text).strip())
        except (ValueError, TypeError):
            return fallback

    @staticmethod
    def _unst_parse_int(text, fallback):
        try:
            return int(float(str(text).strip()))
        except (ValueError, TypeError):
            return fallback

    def _save_unst_msh_gen_config_from_ui(self):
        """将设置页中的非结构网格项写入 unstructured_generator/grid.json（不改动 Domain/Regional 经纬度边角）。"""
        if not hasattr(self, "settings_unst_spacing_hmax_edit"):
            return
        from setting.config import save_unst_msh_gen_config, load_unst_msh_gen_config

        cur = load_unst_msh_gen_config()
        sp0 = cur["spacing"]
        rg0 = cur["regional"]
        hmax_v = self._unst_parse_float(self.settings_unst_spacing_hmax_edit.text(), sp0["hmax"])
        hshr_v = self._unst_parse_float(self.settings_unst_spacing_hshr_edit.text(), sp0["hshr"])
        deep_threshold_v = abs(
            self._unst_parse_float(
                self.settings_unst_spacing_deep_threshold_edit.text(),
                sp0.get("deep_ocean_threshold_m", 4000.0),
            )
        )
        updates = {
            "spacing": {
                "hmax": hmax_v,
                "hshr": hshr_v,
                "hmin": hshr_v,
                "nwav": self._unst_parse_int(self.settings_unst_spacing_nwav_edit.text(), sp0["nwav"]),
                "dhdx": self._unst_parse_float(self.settings_unst_spacing_dhdx_edit.text(), sp0["dhdx"]),
                "deep_ocean_threshold_m": deep_threshold_v,
            },
            "mesh_settings": {
                "hfun_hmax": hmax_v,
            },
            "regional": {
                "margin_deg": self._unst_parse_float(self.settings_unst_regional_margin_deg_edit.text(), rg0["margin_deg"]),
                "edge_segments": self._unst_parse_int(self.settings_unst_regional_edge_segments_edit.text(), rg0["edge_segments"]),
            },
        }
        save_unst_msh_gen_config(updates)

    def _choose_matlab_path(self):
        """选择 MATLAB 路径"""
        start = self.settings_matlab_edit.text().strip() if hasattr(self, 'settings_matlab_edit') else ""
        if not start or not os.path.exists(start):
            if platform.system() == "Windows":
                start = "C:\\Program Files"
            else:
                start = "/Applications"

        # 规范化起始路径（Windows 上会转换为反斜杠格式）
        start = os.path.normpath(start)

        if platform.system() == "Windows":
            path, _ = QFileDialog.getOpenFileName(
                self,
                "选择 MATLAB 可执行文件",
                start,
                "Executable Files (*.exe);;All Files (*)"
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "选择 MATLAB 可执行文件",
                start,
                "All Files (*)"
            )

        if path:
            # 规范化返回的路径（Windows 上会转换为反斜杠格式）
            path = os.path.normpath(path)
            self.settings_matlab_edit.setText(path)


    def _choose_reference_data_path(self):
        """选择 Reference Data 路径"""
        start = self.settings_reference_data_edit.text().strip() if hasattr(self, 'settings_reference_data_edit') else ""
        if not start or not os.path.exists(start):
            from setting.config import get_project_gridgen_path

            default_path = os.path.join(get_project_gridgen_path(), "reference_data")
            if os.path.exists(default_path):
                start = default_path
            else:
                # 如果默认路径也不存在，使用当前用户的主目录
                start = os.path.expanduser("~")

        # 规范化起始路径（Windows 上会转换为反斜杠格式）
        start = os.path.normpath(start)

        path = QFileDialog.getExistingDirectory(
            self,
            "选择 Reference Data 目录",
            start,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
        )

        if path:
            # 规范化返回的路径（Windows 上会转换为反斜杠格式）
            path = os.path.normpath(path)
            self.settings_reference_data_edit.setText(path)


    def _choose_ww3bin_path(self):
        """选择 WW3BIN 路径"""
        start = self.settings_ww3bin_edit.text().strip() if hasattr(self, 'settings_ww3bin_edit') else ""
        if not start or not os.path.exists(start):
            start = os.path.expanduser("~")

        # 规范化起始路径（Windows 上会转换为反斜杠格式）
        start = os.path.normpath(start)

        path = QFileDialog.getExistingDirectory(
            self,
            "选择 WW3BIN 目录",
            start,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
        )

        if path:
            # 规范化返回的路径（Windows 上会转换为反斜杠格式）
            path = os.path.normpath(path)
            self.settings_ww3bin_edit.setText(path)

    def _open_ww3_config_path(self):
        """打开 WW3 配置文件目录"""
        try:
            # 获取配置的路径，如果为空则使用默认路径
            ww3_config_path = self.settings_ww3_config_edit.text().strip() if hasattr(self, 'settings_ww3_config_edit') else ""
            
            # 如果为空，使用默认路径 ./public/ww3（相对于项目根目录）
            if not ww3_config_path:
                # __file__ 是 main/setting/settings.py，需要回到项目根目录
                script_dir = os.path.dirname(os.path.abspath(__file__))  # main
                project_root = os.path.dirname(script_dir)  # 项目根目录
                ww3_config_path = os.path.normpath(os.path.join(project_root, "public", "ww3"))
            else:
                ww3_config_path = os.path.normpath(ww3_config_path)
            
            # 如果目录不存在，创建它
            if not os.path.exists(ww3_config_path):
                try:
                    os.makedirs(ww3_config_path, exist_ok=True)
                except Exception as e:
                    InfoBar.warning(
                        title="提示",
                        content=f"无法创建目录：{ww3_config_path}\n{str(e)}",
                        duration=3000,
                        parent=self
                    )
                    return
            
            # 使用系统默认方式打开文件夹
            system = platform.system().lower()
            if "windows" in system:
                os.startfile(ww3_config_path)
            elif "darwin" in system:  # macOS
                subprocess.run(["open", ww3_config_path])
            else:  # Linux
                subprocess.run(["xdg-open", ww3_config_path])
        except Exception as e:
            InfoBar.error(
                title="错误",
                content=f"打开目录失败：{e}",
                duration=3000,
                parent=self
            )

    def _choose_forcing_field_dir_path(self):
        """选择强迫场文件目录"""
        start = self.settings_forcing_field_dir_edit.text().strip() if hasattr(self, 'settings_forcing_field_dir_edit') else ""
        if not start or not os.path.exists(start):
            # 如果为空或不存在，使用默认路径
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            start = os.path.normpath(os.path.join(script_dir, "public", "forcing"))
            # 如果默认路径也不存在，使用用户主目录
            if not os.path.exists(start):
                start = os.path.expanduser("~")

        # 规范化起始路径（Windows 上会转换为反斜杠格式）
        start = os.path.normpath(start)

        path = QFileDialog.getExistingDirectory(
            self,
            "选择强迫场文件目录",
            start,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
        )

        if path:
            # 规范化返回的路径（Windows 上会转换为反斜杠格式）
            path = os.path.normpath(path)
            self.settings_forcing_field_dir_edit.setText(path)


    def _choose_jason_path(self):
        """选择 JASON 数据路径"""
        start = self.settings_jason_edit.text().strip() if hasattr(self, 'settings_jason_edit') else ""
        if not start or not os.path.exists(start):
            start = os.path.expanduser("~")

        # 规范化起始路径（Windows 上会转换为反斜杠格式）
        start = os.path.normpath(start)

        path = QFileDialog.getExistingDirectory(
            self,
            "选择 JASON 数据目录",
            start,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
        )

        if path:
            # 规范化返回的路径（Windows 上会转换为反斜杠格式）
            path = os.path.normpath(path)
            self.settings_jason_edit.setText(path)



    def _choose_workdir_path(self):
        """选择默认工作目录路径"""
        start = self.settings_workdir_edit.text().strip() if hasattr(self, 'settings_workdir_edit') else ""
        if not start or not os.path.exists(start):
            start = os.path.expanduser("~")

        # 规范化起始路径（Windows 上会转换为反斜杠格式）
        start = os.path.normpath(start)

        path = QFileDialog.getExistingDirectory(
            self,
            "选择默认工作目录",
            start,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
        )

        if path:
            # 规范化返回的路径（Windows 上会转换为反斜杠格式）
            path = os.path.normpath(path)
            self.settings_workdir_edit.setText(path)


    def _connect_settings_auto_save(self):
        """为所有设置输入控件连接自动保存信号"""
        # LineEdit 控件：使用 textChanged 信号
        line_edits = [
            self.settings_matlab_edit,
            self.settings_ww3bin_edit,
            self.settings_jason_edit,
            self.settings_workdir_edit,
            self.settings_dx_edit,
            self.settings_dy_edit,
            self.settings_nested_coeff_edit,
            self.settings_nested_outer_dx_edit,
            self.settings_nested_outer_dy_edit,
            self.settings_kernel_edit,
            self.settings_node_edit,
            self.settings_compute_precision_edit,
            self.settings_output_precision_edit,
            self.settings_server_host_edit,
            self.settings_server_port_edit,
            self.settings_server_user_edit,
            self.settings_server_password_edit,
            self.settings_server_path_edit,
        ]
        # 添加 reference_data_edit（如果存在）
        if hasattr(self, 'settings_reference_data_edit'):
            line_edits.append(self.settings_reference_data_edit)
        _unst_edits = [
            "settings_unst_spacing_hmax_edit",
            "settings_unst_spacing_hshr_edit",
            "settings_unst_spacing_nwav_edit",
            "settings_unst_spacing_dhdx_edit",
            "settings_unst_spacing_deep_threshold_edit",
            "settings_unst_regional_margin_deg_edit",
            "settings_unst_regional_edge_segments_edit",
        ]
        for _name in _unst_edits:
            if hasattr(self, _name):
                line_edits.append(getattr(self, _name))
        for line_edit in line_edits:
            if hasattr(line_edit, 'textChanged'):
                line_edit.textChanged.connect(self._save_settings)

        # ComboBox 控件：使用 currentTextChanged 信号
        if hasattr(self, 'settings_gridgen_version_combo') and hasattr(self.settings_gridgen_version_combo, 'currentTextChanged'):
            self.settings_gridgen_version_combo.currentTextChanged.connect(self._save_settings)
        if hasattr(self, 'settings_bathymetry_combo') and hasattr(self.settings_bathymetry_combo, 'currentTextChanged'):
            self.settings_bathymetry_combo.currentTextChanged.connect(self._save_settings)
        if hasattr(self, 'settings_coastline_combo') and hasattr(self.settings_coastline_combo, 'currentTextChanged'):
            self.settings_coastline_combo.currentTextChanged.connect(self._save_settings)
        # 语言选择框不自动保存，需要手动保存（因为切换语言会刷新界面）

        # CheckBox 控件：使用 stateChanged 信号
        if hasattr(self, 'settings_show_land_coastline_checkbox') and hasattr(self.settings_show_land_coastline_checkbox, 'stateChanged'):
            self.settings_show_land_coastline_checkbox.stateChanged.connect(self._save_settings)
        # SwitchButton 控件：使用 checkedChanged 信号
        # QCheckBox 控件：使用 stateChanged 信号
        # TextEdit 控件：使用 textChanged 信号

        # 频谱参数输入框：只更新 nml 文件，不保存到 config
        if hasattr(self, 'settings_freq_inc_edit') and hasattr(self.settings_freq_inc_edit, 'textChanged'):
            self.settings_freq_inc_edit.textChanged.connect(self._update_spectrum_nml_only)
        if hasattr(self, 'settings_freq_start_edit') and hasattr(self.settings_freq_start_edit, 'textChanged'):
            self.settings_freq_start_edit.textChanged.connect(self._update_spectrum_nml_only)
        if hasattr(self, 'settings_freq_num_edit') and hasattr(self.settings_freq_num_edit, 'textChanged'):
            self.settings_freq_num_edit.textChanged.connect(self._update_spectrum_nml_only)
        if hasattr(self, 'settings_dir_num_edit') and hasattr(self.settings_dir_num_edit, 'textChanged'):
            self.settings_dir_num_edit.textChanged.connect(self._update_spectrum_nml_only)

        # 时间步长参数输入框：只更新 nml 文件，不保存到 config
        if hasattr(self, 'settings_dtmax_edit') and hasattr(self.settings_dtmax_edit, 'textChanged'):
            self.settings_dtmax_edit.textChanged.connect(self._update_timesteps_nml_only)
        if hasattr(self, 'settings_dtxy_edit') and hasattr(self.settings_dtxy_edit, 'textChanged'):
            self.settings_dtxy_edit.textChanged.connect(self._update_timesteps_nml_only)
        if hasattr(self, 'settings_dtkth_edit') and hasattr(self.settings_dtkth_edit, 'textChanged'):
            self.settings_dtkth_edit.textChanged.connect(self._update_timesteps_nml_only)
        if hasattr(self, 'settings_dtmin_edit') and hasattr(self.settings_dtmin_edit, 'textChanged'):
            self.settings_dtmin_edit.textChanged.connect(self._update_timesteps_nml_only)
        
        # 近岸配置输入框：只更新 nml 文件，不保存到 config
        if hasattr(self, 'settings_zlim_edit') and hasattr(self.settings_zlim_edit, 'textChanged'):
            self.settings_zlim_edit.textChanged.connect(self._update_nearshore_nml_only)
        if hasattr(self, 'settings_dmin_edit') and hasattr(self.settings_dmin_edit, 'textChanged'):
            self.settings_dmin_edit.textChanged.connect(self._update_nearshore_nml_only)


    def _save_settings_immediate(self, lang_code=None):
        """立即保存语言设置（用于语言切换时）"""
        try:
            from setting.config import load_config, save_config
            config = load_config()
            
            # 如果提供了语言代码，直接使用
            if lang_code:
                config["LANGUAGE"] = lang_code
            elif hasattr(self, 'settings_language_combo') and self.settings_language_combo.currentData():
                config["LANGUAGE"] = self.settings_language_combo.currentData()
            
            # 保存配置
            if save_config(config):
                # 确保配置已写入文件
                import time
                time.sleep(0.1)  # 短暂延迟，确保文件写入完成
                if hasattr(self, 'log'):
                    self.log(tr("language_saved", "✅ 已保存语言设置: {lang_code}").format(lang_code=lang_code))
            else:
                if hasattr(self, 'log'):
                    self.log(tr("language_save_failed", "❌ 保存语言设置失败"))
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            if hasattr(self, 'log'):
                self.log(tr("language_save_failed_error", "❌ 保存语言设置失败：{e}").format(e=e))

    def _get_theme_from_combo(self):
        """从主题下拉框获取当前选中的主题值"""
        if not hasattr(self, 'settings_theme_combo') or self.settings_theme_combo is None:
            return "AUTO"
        
        # 优先使用 currentData()
        theme_data = self.settings_theme_combo.currentData()
        if theme_data is not None:
            return str(theme_data)
        
        # 如果 currentData() 返回 None，通过索引获取
        current_index = self.settings_theme_combo.currentIndex()
        if current_index >= 0 and current_index < self.settings_theme_combo.count():
            theme_data = self.settings_theme_combo.itemData(current_index)
            if theme_data is not None:
                return str(theme_data)
        
        # 如果 currentData 无效，尝试从当前显示文本反推主题代码
        try:
            from setting.language_manager import tr
            current_text = self.settings_theme_combo.currentText()
            if current_text == tr("theme_light", "明亮"):
                return "LIGHT"
            if current_text == tr("theme_dark", "黑暗"):
                return "DARK"
            if current_text == tr("theme_auto", "跟随系统"):
                return "AUTO"
        except Exception:
            pass
        
        # 最后兜底：使用索引映射（与添加顺序一致）
        try:
            index_map = {0: "LIGHT", 1: "DARK", 2: "AUTO"}
            current_index = self.settings_theme_combo.currentIndex()
            if current_index in index_map:
                return index_map[current_index]
        except Exception:
            pass
        
        # 如果都获取不到，返回默认值
        return "AUTO"
    
    def _get_run_mode_from_combo(self):
        """从运行方式下拉框获取当前选中的运行方式值"""
        if not hasattr(self, 'settings_run_mode_combo') or self.settings_run_mode_combo is None:
            return "both"
        
        # 优先使用 currentData()
        run_mode_data = self.settings_run_mode_combo.currentData()
        if run_mode_data is not None:
            return str(run_mode_data)
        
        # 如果 currentData() 返回 None，通过索引获取
        current_index = self.settings_run_mode_combo.currentIndex()
        if current_index >= 0 and current_index < self.settings_run_mode_combo.count():
            run_mode_data = self.settings_run_mode_combo.itemData(current_index)
            if run_mode_data is not None:
                return str(run_mode_data)
        
        # 如果都获取不到，返回默认值
        return "both"

    def _save_settings(self):
        """保存设置到配置文件"""
        try:
            # 加载当前配置（在保存前重新加载，确保获取最新值）
            from setting.config import load_config, DEFAULT_CONFIG
            _config = load_config()
            
            # 确保 _config 包含所有默认配置的键（合并默认配置）
            merged_config = DEFAULT_CONFIG.copy()
            merged_config.update(_config)
            _config = merged_config
            
            # 主题和运行方式将在 config.update() 中直接从 ComboBox 获取值
            # 收集所有设置值
            reference_data_path = self.settings_reference_data_edit.text().strip() if hasattr(self, 'settings_reference_data_edit') else ""
            # 如果 reference_data 路径为空，保存为空字符串（不保存默认路径）
            # 实际使用时会在代码中处理默认值
            if reference_data_path:
                reference_data_path = os.path.normpath(reference_data_path)  # 规范化路径（Windows 上会转换为反斜杠格式）
            else:
                reference_data_path = ""  # 保存为空字符串

            # 规范化所有路径（Windows 上会转换为反斜杠格式）
            matlab_path = os.path.normpath(self.settings_matlab_edit.text().strip()) if self.settings_matlab_edit.text().strip() else ""
            jason_path = os.path.normpath(self.settings_jason_edit.text().strip()) if self.settings_jason_edit.text().strip() else ""
            workdir_path = os.path.normpath(self.settings_workdir_edit.text().strip()) if self.settings_workdir_edit.text().strip() else ""
            ww3bin_path = os.path.normpath(self.settings_ww3bin_edit.text().strip()) if self.settings_ww3bin_edit.text().strip() else ""
            forcing_field_dir_path = os.path.normpath(self.settings_forcing_field_dir_edit.text().strip()) if hasattr(self, 'settings_forcing_field_dir_edit') and self.settings_forcing_field_dir_edit.text().strip() else ""
            ww3_config_path = os.path.normpath(self.settings_ww3_config_edit.text().strip()) if hasattr(self, 'settings_ww3_config_edit') and self.settings_ww3_config_edit.text().strip() else ""
            # 基于现有配置更新，而不是创建新字典（保留所有现有键，包括默认配置中的新键）
            # 先合并默认配置，确保包含所有键（包括新添加的 THEME 和 RUN_MODE）
            config = DEFAULT_CONFIG.copy()
            config.update(_config)
            
            # 更新需要保存的设置
            config.update({
                "MATLAB_PATH": matlab_path,
                "GRIDGEN_PATH": "",
                "REFERENCE_DATA_PATH": reference_data_path,
                "GRIDGEN_VERSION": self.settings_gridgen_version_combo.currentText() if hasattr(self, 'settings_gridgen_version_combo') else "MATLAB",
                "DX": self.settings_dx_edit.text().strip(),
                "DY": self.settings_dy_edit.text().strip(),
                "NESTED_CONTRACTION_COEFFICIENT": self.settings_nested_coeff_edit.text().strip(),
                "NESTED_OUTER_DX": self.settings_nested_outer_dx_edit.text().strip(),
                "NESTED_OUTER_DY": self.settings_nested_outer_dy_edit.text().strip(),
                "BATHYMETRY": self.settings_bathymetry_combo.currentText() if hasattr(self, 'settings_bathymetry_combo') else "GEBCO",
                # 保存海岸线精度时，保存为索引对应的中文值（用于兼容性）
                # 这样即使切换语言，也能正确加载
                "COASTLINE_PRECISION": (
                    {0: "full", 1: "high", 2: "inter", 3: "low", 4: "coarse"}.get(
                        self.settings_coastline_combo.currentIndex() if hasattr(self, 'settings_coastline_combo') else 0,
                        "full"
                    )
                ),
                "JASON_PATH": jason_path,
                "DEFAULT_WORKDIR": workdir_path,
                "CPU_GROUP": getattr(self, '_cpu_group_list', None) if hasattr(self, '_cpu_group_list') else _config.get("CPU_GROUP", ["CPU6240R", "CPU6336Y"]),
                "KERNEL_NUM": self.settings_kernel_edit.text().strip(),
                "NODE_NUM": self.settings_node_edit.text().strip(),
                "COMPUTE_PRECISION": self.settings_compute_precision_edit.text().strip(),
                "OUTPUT_PRECISION": self.settings_output_precision_edit.text().strip(),
                "FILE_SPLIT": (
                    {0: tr("file_split_none", "无日期"), 1: tr("file_split_hour", "小时"), 
                     2: tr("file_split_day", "天"), 3: tr("file_split_month", "月"), 
                     4: tr("file_split_year", "年")}.get(
                        self.settings_file_split_combo.currentIndex() if hasattr(self, 'settings_file_split_combo') else 4,
                        tr("file_split_year", "年")
                    )
                ),
                "LANGUAGE": self.settings_language_combo.currentData() if hasattr(self, 'settings_language_combo') and self.settings_language_combo.currentData() is not None else _config.get("LANGUAGE", "zh_CN"),
                "THEME": "AUTO",
                "RUN_MODE": self._get_run_mode_from_combo() if hasattr(self, 'settings_run_mode_combo') else _config.get("RUN_MODE", "both"),
                "ST_OPTIONS": ["ST2", "ST4", "ST6", "ST6a", "ST6b"],  # 保持固定选项
                # 频谱参数不保存到 config，只保留默认值
                "FREQ_INC": DEFAULT_CONFIG.get("FREQ_INC", "1.1"),
                "FREQ_START": DEFAULT_CONFIG.get("FREQ_START", "0.04118"),
                "FREQ_NUM": DEFAULT_CONFIG.get("FREQ_NUM", "32"),
                "DIR_NUM": DEFAULT_CONFIG.get("DIR_NUM", "24"),
                # 时间步长参数不保存到 config，只保留默认值
                "DTMAX": DEFAULT_CONFIG.get("DTMAX", "900"),
                "DTXY": DEFAULT_CONFIG.get("DTXY", "320"),
                "DTKTH": DEFAULT_CONFIG.get("DTKTH", "300"),
                "DTMIN": DEFAULT_CONFIG.get("DTMIN", "15"),
                # 近岸配置参数保存到 config
                "GRID_ZLIM": self.settings_zlim_edit.text().strip() if hasattr(self, 'settings_zlim_edit') else "-0.1",
                "GRID_DMIN": self.settings_dmin_edit.text().strip() if hasattr(self, 'settings_dmin_edit') else "2.5",
                "DTMAX": DEFAULT_CONFIG.get("DTMAX", "900"),
                "DTXY": DEFAULT_CONFIG.get("DTXY", "320"),
                "DTKTH": DEFAULT_CONFIG.get("DTKTH", "300"),
                "DTMIN": DEFAULT_CONFIG.get("DTMIN", "15"),
                "WW3BIN_PATH": ww3bin_path,
                "FORCING_FIELD_DIR_PATH": forcing_field_dir_path,
                "WW3_CONFIG_PATH": ww3_config_path,
                "SERVER_HOST": self.settings_server_host_edit.text().strip(),
                "SERVER_PORT": self.settings_server_port_edit.text().strip(),
                "SERVER_USER": self.settings_server_user_edit.text().strip(),
                "SERVER_PASSWORD": self.settings_server_password_edit.text().strip(),
                "SERVER_PATH": self.settings_server_path_edit.text().strip(),
                "ST_VERSIONS": self._get_st_versions_from_table(),
                "SHOW_LAND_COASTLINE": self.settings_show_land_coastline_checkbox.isChecked() if hasattr(self, 'settings_show_land_coastline_checkbox') else True,
                "FORCING_FIELD_FILE_PROCESS_MODE": (
                    self.settings_file_process_combo.currentData() 
                    if hasattr(self, 'settings_file_process_combo') and self.settings_file_process_combo.currentData() is not None
                    else ("move" if hasattr(self, 'settings_file_process_combo') and self.settings_file_process_combo.currentIndex() == 1 else "copy")
                ) if hasattr(self, 'settings_file_process_combo') else "copy",
                "FORCING_FIELD_AUTO_ASSOCIATE": self.settings_auto_associate_switch.isChecked() if hasattr(self, 'settings_auto_associate_switch') else True,
            })
            
            # 确保 THEME 和 RUN_MODE 一定存在（双重保险）
            if "THEME" not in config or not config["THEME"]:
                config["THEME"] = "AUTO"
            if "RUN_MODE" not in config or not config["RUN_MODE"]:
                config["RUN_MODE"] = _config.get("RUN_MODE", "both")
            
            # 确保这两个键的值是字符串类型
            config["THEME"] = str(config.get("THEME", "AUTO"))
            config["RUN_MODE"] = str(config.get("RUN_MODE", "both"))

            # 保存配置（自动保存，不显示成功提示）
            if save_config(config):
                # 重新加载配置并更新全局变量
                reload_config()

                try:
                    self._save_unst_msh_gen_config_from_ui()
                except Exception:
                    pass

                # 更新 public/ww3 和当前工作目录的 ww3_ounf.nml（只更新 FIELD%TIMESPLIT）
                try:
                    from setting.config import load_config
                    current_config = load_config()
                    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                    public_ww3_dir = current_config.get("PUBLIC_WW3_PATH", os.path.join(project_root, "public", "ww3"))
                    self._update_ww3_ounf_timesplit_in_dir(public_ww3_dir)

                    selected_folder = getattr(self, "selected_folder", None)
                    if selected_folder and os.path.isdir(selected_folder):
                        self._update_ww3_ounf_timesplit_in_dir(selected_folder)
                        coarse_dir = os.path.join(selected_folder, "coarse")
                        fine_dir = os.path.join(selected_folder, "fine")
                        if os.path.isdir(coarse_dir) and os.path.isdir(fine_dir):
                            self._update_ww3_ounf_timesplit_in_dir(coarse_dir)
                            self._update_ww3_ounf_timesplit_in_dir(fine_dir)
                except Exception:
                    pass

                # 立即更新主页中的输入框显示
                # 路径相关
                if hasattr(self, 'ww3_bin_edit') and self.ww3_bin_edit:
                    self.ww3_bin_edit.setText(WW3BIN_PATH)
                if hasattr(self, 'jason_folder_edit') and self.jason_folder_edit:
                    self.jason_folder_edit.setText(JASON_PATH)

                # 网格参数相关
                if hasattr(self, 'dx_edit') and self.dx_edit:
                    self.dx_edit.setText(DX)
                if hasattr(self, 'dy_edit') and self.dy_edit:
                    self.dy_edit.setText(DY)
                if hasattr(self, 'lat_south_edit') and self.lat_south_edit:
                    self.lat_south_edit.setText(LATITUDE_SORTH)
                if hasattr(self, 'lat_north_edit') and self.lat_north_edit:
                    self.lat_north_edit.setText(LATITUDE_NORTH)
                if hasattr(self, 'lon_west_edit') and self.lon_west_edit:
                    self.lon_west_edit.setText(LONGITUDE_WEST)
                if hasattr(self, 'lon_east_edit') and self.lon_east_edit:
                    self.lon_east_edit.setText(LONGITUDE_EAST)

                # CPU 和计算参数相关
                if hasattr(self, 'cpu_combo') and self.cpu_combo:
                    # 更新 CPU 选项列表
                    self.cpu_combo.clear()
                    self.cpu_combo.addItems(CPU_GROUP)
                    # 设置当前选中的 CPU
                    index = self.cpu_combo.findText(DEFAULT_CPU)
                    if index >= 0:
                        self.cpu_combo.setCurrentIndex(index)
                    else:
                        # 如果找不到，设置为第一个
                        if self.cpu_combo.count() > 0:
                            self.cpu_combo.setCurrentIndex(0)

                if hasattr(self, 'num_n_edit') and self.num_n_edit:
                    self.num_n_edit.setText(KERNEL_NUM)
                if hasattr(self, 'num_N_edit') and self.num_N_edit:
                    self.num_N_edit.setText(NODE_NUM)
                # 使用 load_config() 获取刚保存的精度值（避免 import 的 COMPUTE_PRECISION/OUTPUT_PRECISION 仍为旧值）
                _cfg = load_config()
                if hasattr(self, 'shel_step_edit') and self.shel_step_edit:
                    self.shel_step_edit.setText(str(_cfg.get("COMPUTE_PRECISION", DEFAULT_CONFIG.get("COMPUTE_PRECISION", "1800"))))
                if hasattr(self, 'output_precision_edit') and self.output_precision_edit:
                    self.output_precision_edit.setText(str(_cfg.get("OUTPUT_PRECISION", DEFAULT_CONFIG.get("OUTPUT_PRECISION", "3600"))))
                if hasattr(self, 'inner_shel_step_edit') and self.inner_shel_step_edit:
                    self.inner_shel_step_edit.setText(str(_cfg.get("COMPUTE_PRECISION", DEFAULT_CONFIG.get("COMPUTE_PRECISION", "1800"))))
                if hasattr(self, 'inner_output_precision_edit') and self.inner_output_precision_edit:
                    self.inner_output_precision_edit.setText(str(_cfg.get("OUTPUT_PRECISION", DEFAULT_CONFIG.get("OUTPUT_PRECISION", "3600"))))
            else:
                InfoBar.error(
                    title="保存失败",
                    content="无法保存配置文件",
                    duration=3000,
                    parent=self
                )
                if hasattr(self, 'log'):
                    self.log(tr("env_vars_save_failed", "❌ 保存环境变量设置失败"))
        except Exception as e:
            InfoBar.error(
                title="保存失败",
                content=f"保存设置时出错：{str(e)}",
                duration=3000,
                parent=self
            )
            self.log(tr("env_vars_save_failed_error", "❌ 保存环境变量设置失败：{e}").format(e=e))
            import traceback
            traceback.print_exc()


    def _on_file_split_changed(self, index):
        """文件分割切换后立即更新 ww3_ounf.nml"""
        try:
            from setting.config import load_config, save_config, DEFAULT_CONFIG, reload_config
            config = load_config()
            merged_config = DEFAULT_CONFIG.copy()
            merged_config.update(config)

            file_split_value = {
                0: tr("file_split_none", "无日期"),
                1: tr("file_split_hour", "小时"),
                2: tr("file_split_day", "天"),
                3: tr("file_split_month", "月"),
                4: tr("file_split_year", "年")
            }.get(index, tr("file_split_year", "年"))

            merged_config["FILE_SPLIT"] = file_split_value
            if save_config(merged_config):
                reload_config()

            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            public_ww3_dir = merged_config.get("PUBLIC_WW3_PATH", os.path.join(project_root, "public", "ww3"))
            self._update_ww3_ounf_timesplit_in_dir(public_ww3_dir)
            self._update_ww3_ounp_timesplit_in_dir(public_ww3_dir)
            self._update_ww3_trnc_timesplit_in_dir(public_ww3_dir)

            selected_folder = getattr(self, "selected_folder", None)
            if selected_folder and os.path.isdir(selected_folder):
                self._update_ww3_ounf_timesplit_in_dir(selected_folder)
                self._update_ww3_ounp_timesplit_in_dir(selected_folder)
                self._update_ww3_trnc_timesplit_in_dir(selected_folder)
                coarse_dir = os.path.join(selected_folder, "coarse")
                fine_dir = os.path.join(selected_folder, "fine")
                if os.path.isdir(coarse_dir) and os.path.isdir(fine_dir):
                    self._update_ww3_ounf_timesplit_in_dir(coarse_dir)
                    self._update_ww3_ounf_timesplit_in_dir(fine_dir)
                    self._update_ww3_ounp_timesplit_in_dir(coarse_dir)
                    self._update_ww3_ounp_timesplit_in_dir(fine_dir)
                    self._update_ww3_trnc_timesplit_in_dir(coarse_dir)
                    self._update_ww3_trnc_timesplit_in_dir(fine_dir)
        except Exception:
            return


    def _reset_spectrum_defaults(self):
        """恢复频谱参数默认值（从 config 读取）"""
        try:
            current_config = load_config()
            self.settings_freq_inc_edit.setText(current_config.get("FREQ_INC", "1.1"))
            self.settings_freq_start_edit.setText(current_config.get("FREQ_START", "0.04118"))
            self.settings_freq_num_edit.setText(current_config.get("FREQ_NUM", "32"))
            self.settings_dir_num_edit.setText(current_config.get("DIR_NUM", "24"))
            # 恢复默认值后，更新 nml 文件
            self._update_spectrum_nml_only()
        except Exception as e:
            import traceback
            traceback.print_exc()


    def _read_spectrum_from_nml(self):
        """从 ww3_grid.nml 读取频谱参数"""
        try:
            nml_path = os.path.join(PUBLIC_DIR, "ww3", "ww3_grid.nml")
            if not os.path.exists(nml_path):
                return None
            
            # 读取文件
            with open(nml_path, "r", encoding="utf-8") as f:
                nml_lines = f.readlines()
            
            spectrum_params = {}
            in_spectrum = False
            
            for line in nml_lines:
                if "&SPECTRUM_NML" in line:
                    in_spectrum = True
                    continue
                
                if in_spectrum:
                    # 遇到结束符号 / 则结束 SPECTRUM_NML 块
                    if "/" in line:
                        break
                    
                    # 检查是否为注释行（以 ! 开头，去除前导空格后）
                    line_stripped = line.lstrip()
                    is_comment = line_stripped.startswith('!')
                    
                    # 只读取非注释行
                    if not is_comment:
                        # 解析 SPECTRUM%XFR
                        if "SPECTRUM%XFR" in line and "=" in line:
                            match = re.search(r'SPECTRUM%XFR\s*=\s*([0-9.]+)', line)
                            if match:
                                spectrum_params["FREQ_INC"] = match.group(1)
                        
                        # 解析 SPECTRUM%FREQ1
                        if "SPECTRUM%FREQ1" in line and "=" in line:
                            match = re.search(r'SPECTRUM%FREQ1\s*=\s*([0-9.]+)', line)
                            if match:
                                spectrum_params["FREQ_START"] = match.group(1)
                        
                        # 解析 SPECTRUM%NK
                        if "SPECTRUM%NK" in line and "=" in line:
                            match = re.search(r'SPECTRUM%NK\s*=\s*([0-9]+)', line)
                            if match:
                                spectrum_params["FREQ_NUM"] = match.group(1)
                        
                        # 解析 SPECTRUM%NTH
                        if "SPECTRUM%NTH" in line and "=" in line:
                            match = re.search(r'SPECTRUM%NTH\s*=\s*([0-9]+)', line)
                            if match:
                                spectrum_params["DIR_NUM"] = match.group(1)
            
            return spectrum_params if spectrum_params else None
        except Exception as e:
            import traceback
            traceback.print_exc()
            return None

    def _read_nearshore_from_nml(self):
        """从 ww3_grid.nml 读取近岸配置参数"""
        try:
            nml_path = os.path.join(PUBLIC_DIR, "ww3", "ww3_grid.nml")
            if not os.path.exists(nml_path):
                return None
            
            # 读取文件
            with open(nml_path, "r", encoding="utf-8") as f:
                nml_lines = f.readlines()
            
            nearshore_params = {}
            in_grid_nml = False
            
            for line in nml_lines:
                if "&GRID_NML" in line.upper():
                    in_grid_nml = True
                    continue
                
                if in_grid_nml:
                    # 遇到结束符号 / 则结束 GRID_NML 块
                    if "/" in line:
                        break
                    
                    # 检查是否为注释行（以 ! 开头，去除前导空格后）
                    line_stripped = line.lstrip()
                    is_comment = line_stripped.startswith('!')
                    
                    # 只读取非注释行
                    if not is_comment:
                        # 解析 GRID%ZLIM（支持负数）
                        if "GRID%ZLIM" in line.upper() and "=" in line:
                            match = re.search(r'GRID%ZLIM\s*=\s*(-?\d+\.?\d*)', line, re.IGNORECASE)
                            if match:
                                nearshore_params["GRID_ZLIM"] = match.group(1)
                        
                        # 解析 GRID%DMIN
                        if "GRID%DMIN" in line.upper() and "=" in line:
                            match = re.search(r'GRID%DMIN\s*=\s*(\d+\.?\d*)', line, re.IGNORECASE)
                            if match:
                                nearshore_params["GRID_DMIN"] = match.group(1)
            
            return nearshore_params if nearshore_params else None
        except Exception as e:
            import traceback
            traceback.print_exc()
            return None

    def _update_spectrum_nml_only(self):
        """只更新 nml 文件，不保存到 config"""
        try:
            # 从输入框读取当前值
            config = {
                "FREQ_INC": self.settings_freq_inc_edit.text().strip() if hasattr(self, 'settings_freq_inc_edit') else "1.1",
                "FREQ_START": self.settings_freq_start_edit.text().strip() if hasattr(self, 'settings_freq_start_edit') else "0.04118",
                "FREQ_NUM": self.settings_freq_num_edit.text().strip() if hasattr(self, 'settings_freq_num_edit') else "32",
                "DIR_NUM": self.settings_dir_num_edit.text().strip() if hasattr(self, 'settings_dir_num_edit') else "24",
            }
            # 只更新 nml 文件
            self._update_ww3_grid_nml_spectrum(config)
        except Exception as e:
            import traceback
            traceback.print_exc()


    def _reset_timesteps_defaults(self):
        """恢复时间步长参数默认值（从 config 读取）"""
        try:
            current_config = load_config()
            self.settings_dtmax_edit.setText(current_config.get("DTMAX", "900"))
            self.settings_dtxy_edit.setText(current_config.get("DTXY", "320"))
            self.settings_dtkth_edit.setText(current_config.get("DTKTH", "300"))
            self.settings_dtmin_edit.setText(current_config.get("DTMIN", "15"))
            # 恢复默认值后，更新 nml 文件
            self._update_timesteps_nml_only()
        except Exception as e:
            import traceback
            traceback.print_exc()

    def _reset_nearshore_defaults(self):
        """恢复近岸配置默认值（从 config 读取）"""
        try:
            current_config = load_config()
            self.settings_zlim_edit.setText(current_config.get("GRID_ZLIM", "-0.1"))
            self.settings_dmin_edit.setText(current_config.get("GRID_DMIN", "2.5"))
            # 恢复默认值后，更新 nml 文件
            self._update_nearshore_nml_only()
        except Exception as e:
            import traceback
            traceback.print_exc()

    def _update_nearshore_nml_only(self):
        """只更新 nml 文件，不保存到 config"""
        try:
            # 从输入框读取当前值
            config = {
                "GRID_ZLIM": self.settings_zlim_edit.text().strip() if hasattr(self, 'settings_zlim_edit') else "-0.1",
                "GRID_DMIN": self.settings_dmin_edit.text().strip() if hasattr(self, 'settings_dmin_edit') else "2.5",
            }
            # 只更新 nml 文件
            self._update_ww3_grid_nml_nearshore(config)
        except Exception as e:
            import traceback
            traceback.print_exc()

    def _update_ww3_grid_nml_nearshore(self, config):
        """更新 ww3_grid.nml 中的 GRID_NML 部分（GRID%ZLIM 和 GRID%DMIN）"""
        try:
            # 读取近岸配置参数
            zlim = config.get("GRID_ZLIM", "-0.1")
            dmin = config.get("GRID_DMIN", "2.5")

            for nml_path in self._get_ww3_grid_nml_paths():
                with open(nml_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                new_lines = []
                in_grid_nml = False

                for line in lines:
                    # 检查是否进入 GRID_NML 块
                    if "&GRID_NML" in line.upper():
                        in_grid_nml = True
                        new_lines.append(line)
                        continue

                    if in_grid_nml:
                        # 遇到结束符号 / 则结束 GRID_NML 块
                        if "/" in line:
                            in_grid_nml = False
                            new_lines.append(line)
                            continue

                        # 检查是否为注释行（以 ! 开头，去除前导空格后）
                        line_stripped = line.lstrip()
                        is_comment = line_stripped.startswith('!')

                        # 只替换非注释行
                        if not is_comment:
                            if "GRID%ZLIM" in line and "=" in line:
                                new_lines.append(f"  GRID%ZLIM         =  {zlim}\n")
                                continue
                            if "GRID%DMIN" in line and "=" in line:
                                new_lines.append(f"  GRID%DMIN         =  {dmin}\n")
                                continue

                        # 非 GRID_NML 或未匹配参数，保持原行
                        new_lines.append(line)
                    else:
                        new_lines.append(line)

                with open(nml_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
        except Exception as e:
            import traceback
            traceback.print_exc()


    def _update_timesteps_nml_only(self):
        """只更新 nml 文件，不保存到 config"""
        try:
            # 从输入框读取当前值
            config = {
                "DTMAX": self.settings_dtmax_edit.text().strip() if hasattr(self, 'settings_dtmax_edit') else "900",
                "DTXY": self.settings_dtxy_edit.text().strip() if hasattr(self, 'settings_dtxy_edit') else "320",
                "DTKTH": self.settings_dtkth_edit.text().strip() if hasattr(self, 'settings_dtkth_edit') else "300",
                "DTMIN": self.settings_dtmin_edit.text().strip() if hasattr(self, 'settings_dtmin_edit') else "15",
            }
            # 只更新 nml 文件
            self._update_ww3_grid_nml_timesteps(config)
        except Exception as e:
            import traceback
            traceback.print_exc()


    def _update_ww3_grid_nml_spectrum(self, config):
        """更新 ww3_grid.nml 中的 SPECTRUM_NML 部分"""
        try:
            # 读取频谱参数
            freq_inc = config.get("FREQ_INC", "1.1")
            freq_start = config.get("FREQ_START", "0.04118")
            freq_num = config.get("FREQ_NUM", "32")
            dir_num = config.get("DIR_NUM", "24")

            for nml_path in self._get_ww3_grid_nml_paths():
                # 读取文件
                with open(nml_path, "r", encoding="utf-8") as f:
                    nml_lines = f.readlines()

                new_lines = []
                in_spectrum = False

                for line in nml_lines:
                    if "&SPECTRUM_NML" in line:
                        in_spectrum = True
                        new_lines.append(line)
                        continue

                    if in_spectrum:
                        # 遇到结束符号 / 则结束 SPECTRUM_NML 块
                        if "/" in line:
                            in_spectrum = False
                            new_lines.append(line)
                            continue

                        # 替换参数
                        if "SPECTRUM%XFR" in line:
                            new_lines.append(f"  SPECTRUM%XFR       =  {freq_inc}\n")
                            continue
                        if "SPECTRUM%FREQ1" in line:
                            new_lines.append(f"  SPECTRUM%FREQ1     =  {freq_start}\n")
                            continue
                        if "SPECTRUM%NK" in line:
                            new_lines.append(f"  SPECTRUM%NK        =  {freq_num}\n")
                            continue
                        if "SPECTRUM%NTH" in line:
                            new_lines.append(f"  SPECTRUM%NTH       =  {dir_num}\n")
                            continue

                    # 非 SPECTRUM_NML 或未匹配参数，保持原行
                    new_lines.append(line)

                # 写回文件
                with open(nml_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
        except Exception as e:
            import traceback
            traceback.print_exc()


    def _update_ww3_grid_nml_timesteps(self, config):
        """更新 ww3_grid.nml 中的 TIMESTEPS_NML 部分"""
        try:
            # 读取时间步长参数
            dtmax = config.get("DTMAX", "900")
            dtxy = config.get("DTXY", "320")
            dtkth = config.get("DTKTH", "300")
            dtmin = config.get("DTMIN", "15")

            for nml_path in self._get_ww3_grid_nml_paths():
                # 读取文件
                with open(nml_path, "r", encoding="utf-8") as f:
                    nml_lines = f.readlines()

                new_lines = []
                in_timesteps = False

                for line in nml_lines:
                    if "&TIMESTEPS_NML" in line:
                        in_timesteps = True
                        new_lines.append(line)
                        continue

                    if in_timesteps:
                        # 遇到结束符号 / 则结束 TIMESTEPS_NML 块
                        if "/" in line:
                            in_timesteps = False
                            new_lines.append(line)
                            continue

                        # 替换参数
                        if "TIMESTEPS%DTMAX" in line:
                            new_lines.append(f"  TIMESTEPS%DTMAX        =  {dtmax}\n")
                            continue
                        if "TIMESTEPS%DTXY" in line:
                            new_lines.append(f"  TIMESTEPS%DTXY         =  {dtxy}\n")
                            continue
                        if "TIMESTEPS%DTKTH" in line:
                            new_lines.append(f"  TIMESTEPS%DTKTH        =  {dtkth}\n")
                            continue
                        if "TIMESTEPS%DTMIN" in line:
                            new_lines.append(f"  TIMESTEPS%DTMIN        =  {dtmin}\n")
                            continue

                    # 非 TIMESTEPS_NML 或未匹配参数，保持原行
                    new_lines.append(line)

                # 写回文件
                with open(nml_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
        except Exception as e:
            import traceback
            traceback.print_exc()

    def _get_ww3_grid_nml_paths(self):
        """返回需要同步更新的 ww3_grid.nml 路径列表（public + 当前工作目录）"""
        paths = []
        try:
            public_path = os.path.join(PUBLIC_DIR, "ww3", "ww3_grid.nml")
            if os.path.isfile(public_path):
                paths.append(public_path)

            selected_folder = getattr(self, "selected_folder", None)
            if selected_folder and os.path.isdir(selected_folder):
                work_path = os.path.join(selected_folder, "ww3_grid.nml")
                if os.path.isfile(work_path):
                    paths.append(work_path)

                coarse_dir = os.path.join(selected_folder, "coarse")
                fine_dir = os.path.join(selected_folder, "fine")
                if os.path.isdir(coarse_dir):
                    coarse_path = os.path.join(coarse_dir, "ww3_grid.nml")
                    if os.path.isfile(coarse_path):
                        paths.append(coarse_path)
                if os.path.isdir(fine_dir):
                    fine_path = os.path.join(fine_dir, "ww3_grid.nml")
                    if os.path.isfile(fine_path):
                        paths.append(fine_path)
        except Exception:
            return paths
        return paths


    def _get_st_versions_from_table(self):
        """从表格中获取 ST 版本列表"""
        versions = []
        for i in range(self.st_version_table.rowCount()):
            name_item = self.st_version_table.item(i, 0)
            path_item = self.st_version_table.item(i, 1)
            if name_item and path_item:
                name = name_item.text().strip()
                path = path_item.text().strip()
                if name and path:
                    versions.append({"name": name, "path": path})
        return versions


    def _add_st_version(self):
        """新增 ST 版本"""
        from qfluentwidgets import MessageBoxBase

        class StVersionDialog(MessageBoxBase):
            def __init__(self, parent=None):
                super().__init__(parent)
                from setting.language_manager import tr
                self.setWindowTitle(tr("st_version_add_title", "新增 ST 版本"))
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
                    # 如果没有父窗口，创建一个临时方法来获取样式
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

                # 使用网格布局确保输入框左右对齐
                from PyQt6.QtWidgets import QGridLayout
                grid_layout = QGridLayout()
                grid_layout.setColumnStretch(0, 0)  # 标签列不拉伸
                grid_layout.setColumnStretch(1, 1)  # 输入框列拉伸
                grid_layout.setSpacing(10)

                # 版本名称行
                from setting.language_manager import tr
                name_label = QLabel(tr("st_version_name", "版本名称:"))
                name_edit = LineEdit()
                name_edit.setMinimumWidth(300)  # 增加输入框宽度
                name_edit.setStyleSheet(input_style)
                grid_layout.addWidget(name_label, 0, 0)
                grid_layout.addWidget(name_edit, 0, 1)

                # 路径行
                path_label = QLabel(tr("st_version_path", "路径:"))
                path_edit = LineEdit()
                path_edit.setMinimumWidth(300)  # 增加输入框宽度
                path_edit.setStyleSheet(input_style)
                grid_layout.addWidget(path_label, 1, 0)
                grid_layout.addWidget(path_edit, 1, 1)

                dialog_layout.addLayout(grid_layout)

                self.viewLayout.addLayout(dialog_layout)

                # 保存输入框引用
                self.name_edit = name_edit
                self.path_edit = path_edit

        dialog = StVersionDialog(self)

        if dialog.exec():
            name = dialog.name_edit.text().strip()
            path = dialog.path_edit.text().strip()
            if name and path:
                # 检查名称是否已存在
                for i in range(self.st_version_table.rowCount()):
                    existing_name = self.st_version_table.item(i, 0)
                    if existing_name and existing_name.text().strip() == name:
                        from setting.language_manager import tr
                        InfoBar.warning(
                            title=tr("add_failed", "添加失败"),
                            content=tr("version_name_exists", "版本名称 '{name}' 已存在").format(name=name),
                            duration=3000,
                            parent=self
                        )
                        return

                # 检查路径是否已存在
                for i in range(self.st_version_table.rowCount()):
                    existing_path = self.st_version_table.item(i, 1)
                    if existing_path and existing_path.text().strip() == path:
                        from setting.language_manager import tr
                        InfoBar.warning(
                            title=tr("add_failed", "添加失败"),
                            content=tr("path_exists", "路径 '{path}' 已被其他版本使用").format(path=path),
                            duration=3000,
                            parent=self
                        )
                        return

                # 添加到表格
                row = self.st_version_table.rowCount()
                self.st_version_table.insertRow(row)
                name_item = QTableWidgetItem(name)
                name_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)  # 左对齐
                path_item = QTableWidgetItem(path)
                path_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)  # 左对齐
                self.st_version_table.setItem(row, 0, name_item)
                self.st_version_table.setItem(row, 1, path_item)

                from setting.language_manager import tr
                InfoBar.success(
                    title=tr("add_success", "添加成功"),
                    content=tr("version_added", "已添加 ST 版本 '{name}'").format(name=name),
                    duration=2000,
                    parent=self
                )
                # 自动保存设置
                self._save_settings()
            else:
                from setting.language_manager import tr
                InfoBar.warning(
                    title=tr("add_failed", "添加失败"),
                    content=tr("name_path_empty", "版本名称和路径不能为空"),
                    duration=3000,
                    parent=self
                )


    def _edit_st_version(self):
        """修改 ST 版本"""
        current_row = self.st_version_table.currentRow()
        if current_row < 0:
            from setting.language_manager import tr
            InfoBar.warning(
                title=tr("edit_failed", "修改失败"),
                content=tr("select_version_first", "请先选择要修改的 ST 版本"),
                duration=3000,
                parent=self
            )
            return

        from qfluentwidgets import MessageBoxBase

        # 获取当前值
        name_item = self.st_version_table.item(current_row, 0)
        path_item = self.st_version_table.item(current_row, 1)
        if not name_item or not path_item:
            return

        old_name = name_item.text().strip()
        old_path = path_item.text().strip()

        class StVersionEditDialog(MessageBoxBase):
            def __init__(self, parent=None, old_name="", old_path=""):
                super().__init__(parent)
                from setting.language_manager import tr
                self.setWindowTitle(tr("st_version_edit_title", "修改 ST 版本"))
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
                    # 如果没有父窗口，创建一个临时方法来获取样式
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

                # 使用网格布局确保输入框左右对齐
                from PyQt6.QtWidgets import QGridLayout
                grid_layout = QGridLayout()
                grid_layout.setColumnStretch(0, 0)  # 标签列不拉伸
                grid_layout.setColumnStretch(1, 1)  # 输入框列拉伸
                grid_layout.setSpacing(10)

                # 版本名称行
                from setting.language_manager import tr
                name_label = QLabel(tr("st_version_name", "版本名称:"))
                name_edit = LineEdit()
                name_edit.setText(old_name)
                name_edit.setMinimumWidth(300)  # 增加输入框宽度
                name_edit.setStyleSheet(input_style)
                grid_layout.addWidget(name_label, 0, 0)
                grid_layout.addWidget(name_edit, 0, 1)

                # 路径行
                path_label = QLabel(tr("st_version_path", "路径:"))
                path_edit = LineEdit()
                path_edit.setText(old_path)
                path_edit.setMinimumWidth(300)  # 增加输入框宽度
                path_edit.setStyleSheet(input_style)
                grid_layout.addWidget(path_label, 1, 0)
                grid_layout.addWidget(path_edit, 1, 1)

                dialog_layout.addLayout(grid_layout)

                self.viewLayout.addLayout(dialog_layout)

                # 保存输入框引用
                self.name_edit = name_edit
                self.path_edit = path_edit

        dialog = StVersionEditDialog(self, old_name, old_path)

        if dialog.exec():
            name = dialog.name_edit.text().strip()
            path = dialog.path_edit.text().strip()
            if name and path:
                # 检查名称是否已存在（排除当前行）
                for i in range(self.st_version_table.rowCount()):
                    if i == current_row:
                        continue
                    existing_name = self.st_version_table.item(i, 0)
                    if existing_name and existing_name.text().strip() == name:
                        from setting.language_manager import tr
                        InfoBar.warning(
                            title=tr("edit_failed", "修改失败"),
                            content=tr("version_name_exists", "版本名称 '{name}' 已存在").format(name=name),
                            duration=3000,
                            parent=self
                        )
                        return

                # 更新表格
                name_item = QTableWidgetItem(name)
                name_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)  # 左对齐
                path_item = QTableWidgetItem(path)
                path_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)  # 左对齐
                self.st_version_table.setItem(current_row, 0, name_item)
                self.st_version_table.setItem(current_row, 1, path_item)

                from setting.language_manager import tr
                InfoBar.success(
                    title=tr("edit_success", "修改成功"),
                    content=tr("version_modified", "已修改 ST 版本 '{name}'").format(name=name),
                    duration=2000,
                    parent=self
                )
                # 自动保存设置
                self._save_settings()
            else:
                from setting.language_manager import tr
                InfoBar.warning(
                    title=tr("edit_failed", "修改失败"),
                    content=tr("name_path_empty", "版本名称和路径不能为空"),
                    duration=3000,
                    parent=self
                )


    def _delete_st_version(self):
        """删除 ST 版本"""
        current_row = self.st_version_table.currentRow()
        if current_row < 0:
            from setting.language_manager import tr
            InfoBar.warning(
                title=tr("delete_failed", "删除失败"),
                content=tr("select_delete_first", "请先选择要删除的 ST 版本"),
                duration=3000,
                parent=self
            )
            return

        name_item = self.st_version_table.item(current_row, 0)
        if not name_item:
            return

        name = name_item.text().strip()

        from qfluentwidgets import MessageBox
        from setting.language_manager import tr

        msg_box = MessageBox(
            tr("confirm", "确定"),
            tr("confirm_delete", "确定要删除 ST 版本 '{name}' 吗？").format(name=name),
            self
        )
        if msg_box.exec():
            self.st_version_table.removeRow(current_row)
            InfoBar.success(
                title=tr("delete_success", "删除成功"),
                content=tr("version_deleted", "已删除 ST 版本 '{name}'").format(name=name),
                duration=2000,
                parent=self
            )
            # 自动保存设置
            self._save_settings()


    def _set_default_st_version(self):
        """将选中的 ST 版本设置为默认（移到最前面）"""
        current_row = self.st_version_table.currentRow()
        if current_row < 0:
            InfoBar.warning(
                title="设置失败",
                content="请先选择要设置为默认的 ST 版本",
                duration=3000,
                parent=self
            )
            return

        if current_row == 0:
            InfoBar.info(
                title="提示",
                content="该 ST 版本已经是默认版本",
                duration=2000,
                parent=self
            )
            return

        # 获取当前行的数据
        name_item = self.st_version_table.item(current_row, 0)
        path_item = self.st_version_table.item(current_row, 1)
        if not name_item or not path_item:
            return

        name = name_item.text().strip()
        path = path_item.text().strip()

        # 删除当前行
        self.st_version_table.removeRow(current_row)

        # 在第一行插入
        self.st_version_table.insertRow(0)
        name_item_new = QTableWidgetItem(name)
        name_item_new.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)  # 左对齐
        path_item_new = QTableWidgetItem(path)
        path_item_new.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)  # 左对齐
        self.st_version_table.setItem(0, 0, name_item_new)
        self.st_version_table.setItem(0, 1, path_item_new)

        # 选中第一行
        self.st_version_table.selectRow(0)

        from setting.language_manager import tr
        InfoBar.success(
            title=tr("set_default_success", "设置成功"),
            content=tr("set_default_content", "已将 ST 版本 '{name}' 设置为默认版本").format(name=name),
            duration=2000,
            parent=self
        )
        # 自动保存设置
        self._save_settings()

    def _on_language_changed(self, index):
        """语言切换处理函数"""
        try:
            # 防止初始化时触发
            if not hasattr(self, '_language_combo_initialized') or not self._language_combo_initialized:
                return
            
            from setting.language_manager import set_language, load_language
            
            # 获取选中的语言代码
            if not hasattr(self, 'settings_language_combo'):
                return
                
            lang_code = self.settings_language_combo.currentData()
            if not lang_code:
                # 如果 currentData() 返回 None，尝试从 currentText() 获取
                current_text = self.settings_language_combo.currentText()
                from setting.language_manager import get_supported_languages
                supported_languages = get_supported_languages()
                # 反向查找语言代码
                for code, name in supported_languages.items():
                    if name == current_text:
                        lang_code = code
                        break
                
                if not lang_code:
                    return
            
            # 设置语言
            set_language(lang_code)
            load_language(lang_code)
            
            # 保存语言设置（直接保存，不等待自动保存）
            self._save_settings_immediate(lang_code)
            
            # 重新创建整个设置页面以应用新语言
            # 注意：重新创建页面时会重新加载配置，此时应该已经保存了新的语言设置
            if hasattr(self, 'left_stacked'):
                # 找到设置页面的索引（设置页面通常是索引1）
                settings_index = 1  # 根据window.py，设置页面是索引1
                
                # 验证是否是设置页面
                if settings_index < self.left_stacked.count():
                    old_widget = self.left_stacked.widget(settings_index)
                    if old_widget:
                        # 保存当前滚动位置
                        scroll_position = 0
                        if isinstance(old_widget, QtWidgets.QScrollArea):
                            scroll_position = old_widget.verticalScrollBar().value()
                        
                        # 重新创建设置页面（此时语言已经切换，新页面会使用新语言）
                        # 临时禁用初始化标志，防止重新创建时触发语言切换
                        old_init_flag = getattr(self, '_language_combo_initialized', False)
                        self._language_combo_initialized = False

                        # 缓存当前输出变量选择与方案，避免语言切换触发读取
                        self._pending_output_vars_selection = None
                        if hasattr(self, 'output_vars_checkboxes') and self.output_vars_checkboxes:
                            self._pending_output_vars_selection = [
                                var_code
                                for var_code, checkbox in self.output_vars_checkboxes.items()
                                if checkbox.isChecked()
                            ]
                        self._pending_output_scheme_selection = None
                        if hasattr(self, 'output_vars_scheme_combo'):
                            self._pending_output_scheme_selection = self.output_vars_scheme_combo.currentText()
                        self._pending_output_scheme_name = None
                        if hasattr(self, 'output_vars_scheme_name_edit'):
                            self._pending_output_scheme_name = self.output_vars_scheme_name_edit.text()
                        
                        # 临时保存当前语言代码，确保重新创建页面时使用正确的语言
                        # 因为重新创建页面时会重新加载配置，而配置可能还没有完全更新
                        # 所以直接传递语言代码给创建函数
                        new_settings_widget = self._create_settings_page(force_language_code=lang_code)
                        
                        if new_settings_widget:
                            # 替换页面
                            self.left_stacked.removeWidget(old_widget)
                            self.left_stacked.insertWidget(settings_index, new_settings_widget)
                            
                            # 恢复初始化标志（延迟恢复，确保新页面的ComboBox已经设置完成）
                            from PyQt6.QtCore import QTimer
                            def restore_flag():
                                self._language_combo_initialized = old_init_flag
                            QTimer.singleShot(500, restore_flag)
                            
                            # 如果当前显示的是设置页面，切换到新页面
                            if self.left_stacked.currentIndex() == settings_index:
                                self.left_stacked.setCurrentIndex(settings_index)
                                # 恢复滚动位置
                                if isinstance(new_settings_widget, QtWidgets.QScrollArea):
                                    new_settings_widget.verticalScrollBar().setValue(scroll_position)
                            
                            # 更新窗口标题
                            if hasattr(self, 'setWindowTitle'):
                                from setting.language_manager import tr
                                self.setWindowTitle(tr("app_title", "海浪模式 WAVEWATCH III 可视化运行软件"))
                            
                            # 更新导航按钮文本（科研绘图）
                            if hasattr(self, 'navigationInterface'):
                                try:
                                    # 尝试更新科研绘图按钮的文本
                                    from setting.language_manager import tr
                                    plot_text = tr("plotting_research_plotting", "科研绘图")
                                    # 查找并更新导航项
                                    for i in range(self.navigationInterface.widget.count()):
                                        item = self.navigationInterface.widget.item(i)
                                        if hasattr(item, 'routeKey') and item.routeKey == 'plot':
                                            if hasattr(item, 'setText'):
                                                item.setText(plot_text)
                                            break
                                except Exception:
                                    pass  # 如果更新失败，忽略错误
                            
                            if hasattr(self, 'log'):
                                from setting.language_manager import tr
                                self.log(tr("language_switched", "✅ 已切换语言为: {lang_code}").format(lang_code=lang_code))
                                # 显示重启提示
                                InfoBar.warning(
                                    title=tr("language_changed_restart_title", "语言切换"),
                                    content=tr("language_changed_restart", "语言已切换，请重启客户端以使更改生效"),
                                    duration=5000,
                                    parent=self
                                )
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            if hasattr(self, 'log'):
                self.log(tr("language_switch_failed", "❌ 语言切换失败：{e}").format(e=e))

    def _on_theme_combo_changed(self, index):
        """主题切换处理函数（设置页下拉框）"""
        try:
            # 获取选中的主题
            if not hasattr(self, 'settings_theme_combo'):
                return

            theme_str = self._get_theme_from_combo()
            
            # 导入主题相关模块
            from qfluentwidgets import setTheme, Theme
            from PyQt6.QtCore import QTimer
            
            # 将字符串转换为 Theme 枚举
            if theme_str == "LIGHT":
                theme = Theme.LIGHT
            elif theme_str == "DARK":
                theme = Theme.DARK
            else:
                theme = Theme.AUTO
            
            # 先保存主题设置（确保配置已更新）
            self._save_settings_immediate_theme(theme_str)

            # 延迟应用主题，避免在下拉框弹出时触发 Qt 崩溃
            def apply_theme():
                try:
                    setTheme(theme)
                    if hasattr(self, '_update_theme_state'):
                        self._update_theme_state()
                except Exception as e:
                    print(f"[ERROR] apply_theme failed: {e}")

            QTimer.singleShot(0, apply_theme)

            # 延迟更新样式，确保主题已应用
            def update_styles():
                try:
                    # 再次更新主题状态，确保同步
                    if hasattr(self, '_update_theme_state'):
                        self._update_theme_state()
                    if hasattr(self, '_update_all_styles'):
                        self._update_all_styles()
                    # 强制刷新界面
                    if hasattr(self, 'update'):
                        self.update()
                    if hasattr(self, 'repaint'):
                        self.repaint()
                except Exception as e:
                    print(f"[ERROR] update_styles failed: {e}")

            QTimer.singleShot(50, update_styles)
            QTimer.singleShot(200, update_styles)  # 二次更新确保生效
            
            if hasattr(self, 'log'):
                theme_names = {
                    "LIGHT": tr("theme_light", "明亮"),
                    "DARK": tr("theme_dark", "黑暗"),
                    "AUTO": tr("theme_auto", "跟随系统")
                }
                self.log(tr("theme_switched", "✅ 已切换主题为: {theme}").format(theme=theme_names.get(theme_str, tr("unknown", "未知"))))
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            if hasattr(self, 'log'):
                self.log(tr("theme_switch_failed", "❌ 主题切换失败：{e}").format(e=e))

    def _on_run_mode_changed(self, index):
        """运行方式切换处理函数"""
        try:
            # 获取选中的运行方式
            if not hasattr(self, 'settings_run_mode_combo'):
                return
            
            # 优先使用 currentData()，如果返回 None，则通过索引获取
            run_mode = self.settings_run_mode_combo.currentData()
            if run_mode is None:
                # 如果 currentData() 返回 None，通过索引获取
                current_index = self.settings_run_mode_combo.currentIndex()
                if current_index >= 0 and current_index < self.settings_run_mode_combo.count():
                    run_mode = self.settings_run_mode_combo.itemData(current_index)
                if run_mode is None:
                    return  # 如果还是 None，则返回
            
            # 确保是字符串类型
            run_mode = str(run_mode)
            
            # 保存运行方式设置
            self._save_settings_immediate_run_mode(run_mode)
            
            # 更新界面可见性
            if hasattr(self, '_update_run_mode_visibility'):
                self._update_run_mode_visibility()
            
            if hasattr(self, 'log'):
                run_mode_names = {
                    "local": tr("run_mode_local", "本地运行"),
                    "server": tr("run_mode_server", "服务器运行"),
                    "both": tr("run_mode_both", "本地+服务器运行")
                }
                self.log(tr("run_mode_switched", "✅ 已切换运行方式为: {mode}").format(mode=run_mode_names.get(run_mode, tr("unknown", "未知"))))
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            if hasattr(self, 'log'):
                self.log(tr("run_mode_switch_failed", "❌ 运行方式切换失败：{e}").format(e=e))

    def _save_settings_immediate_run_mode(self, run_mode=None):
        """立即保存运行方式设置（用于运行方式切换时）"""
        try:
            from setting.config import load_config, save_config, DEFAULT_CONFIG
            config = load_config()
            
            # 确保配置包含所有默认键（双重保险）
            merged_config = DEFAULT_CONFIG.copy()
            merged_config.update(config)
            config = merged_config
            
            # 如果提供了运行方式代码，直接使用
            if run_mode:
                config["RUN_MODE"] = run_mode
            elif hasattr(self, 'settings_run_mode_combo') and self.settings_run_mode_combo.currentData():
                config["RUN_MODE"] = self.settings_run_mode_combo.currentData()
            else:
                config["RUN_MODE"] = "both"  # 默认值
            
            # 确保值是字符串
            config["RUN_MODE"] = str(config["RUN_MODE"])
            
            save_config(config)

           
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            if hasattr(self, 'log'):
                self.log(tr("run_mode_save_failed_error", "❌ 保存运行方式设置失败：{e}").format(e=e))

    def _save_settings_immediate_theme(self, theme_str=None):
        """立即保存主题设置（用于主题切换时）"""
        try:
            from setting.config import load_config, save_config, DEFAULT_CONFIG
            config = load_config()
            
            # 确保配置包含所有默认键（双重保险）
            merged_config = DEFAULT_CONFIG.copy()
            merged_config.update(config)
            config = merged_config
            
            # 如果提供了主题代码，直接使用
            if theme_str:
                config["THEME"] = theme_str
            else:
                config["THEME"] = self._get_theme_from_combo()
            
            # 确保值是字符串
            config["THEME"] = str(config["THEME"])
            
            # 保存配置
            if save_config(config):
                # 确保配置已写入文件
                import time
                time.sleep(0.1)  # 短暂延迟，确保文件写入完成
                if hasattr(self, 'log'):
                    self.log(tr("theme_saved", "✅ 已保存主题设置: {theme}").format(theme=config['THEME']))
            else:
                if hasattr(self, 'log'):
                    self.log(tr("theme_save_failed", "❌ 保存主题设置失败"))
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            if hasattr(self, 'log'):
                self.log(tr("theme_save_failed_error", "❌ 保存主题设置失败：{e}").format(e=e))

    def _update_settings_texts(self):
        """更新设置页面的文本（根据当前语言）"""
        try:
            from setting.language_manager import tr
            
            # 更新路径设置卡片标题
            if hasattr(self, 'matlab_card'):
                self.matlab_card.setTitle(tr("path_settings", "路径设置"))
            
            # 更新各个标签文本
            labels_to_update = [
                ("matlab_label", "matlab_path", "MATLAB 路径:"),
                ("reference_data_label", "reference_data_path", "Reference Data 路径:"),
                ("ww3bin_label", "ww3bin_path", "默认 WW3BIN 路径:"),
                ("forcing_field_dir_label", "forcing_field_dir_path", "默认打开的强迫场文件的目录:"),
                ("ww3_config_label", "ww3_config_path", "WW3 配置文件:"),
                ("jason_label", "jason_path", "默认 JASON 数据路径:"),
                ("workdir_label", "workdir_path", "默认工作目录:"),
            ]
            
            for attr_name, tr_key, default in labels_to_update:
                if hasattr(self, attr_name):
                    label = getattr(self, attr_name)
                    if label:
                        label.setText(tr(tr_key, default))

            if hasattr(self, "unst_mesh_card"):
                self.unst_mesh_card.setTitle(tr("unst_mesh_config_card", "非结构化三角网格配置"))
            _unst_lbls = [
                ("unst_l_spacing_hmax", "unst_spacing_hmax", "深水尺度（km）"),
                ("unst_l_spacing_hshr", "unst_spacing_hshr", "近岸尺度（km）"),
                ("unst_l_spacing_dhdx", "unst_spacing_dhdx", "水深梯度"),
                ("unst_l_spacing_nwav", "unst_spacing_nwav", "浅水按波长加密（填 0 关闭）"),
                ("unst_l_spacing_deep_threshold", "unst_spacing_deep_threshold", "深水阈值（m）"),
                ("unst_l_reg_margin", "unst_regional_margin_deg", "区域外扩边距（度）"),
                ("unst_l_reg_edge_seg", "unst_regional_edge_segments", "矩形边界折线段数（越大越光顺）"),
            ]
            for attr_name, tr_key, default in _unst_lbls:
                if hasattr(self, attr_name):
                    lb = getattr(self, attr_name)
                    if lb:
                        lb.setText(tr(tr_key, default))
            
            # 更新其他卡片标题和标签
            # 注意：这里只更新设置页面中可以直接访问的控件
            # 对于嵌套在卡片中的控件，需要更复杂的逻辑
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            if hasattr(self, 'log'):
                self.log(tr("settings_text_update_failed", "❌ 更新设置页面文本失败：{e}").format(e=e))

    def _manage_cpu_group(self):
        """管理 CPU 组"""
        from qfluentwidgets import MessageBoxBase
        from setting.config import load_config

        class CpuGroupDialog(MessageBoxBase):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle(tr("cpu_management", "CPU 管理"))
                # 设置按钮文本
                if hasattr(self, 'yesButton') and self.yesButton:
                    self.yesButton.setText(tr("confirm", "确定"))
                if hasattr(self, 'cancelButton') and self.cancelButton:
                    self.cancelButton.setText(tr("cancel", "取消"))

                dialog_layout = QVBoxLayout()
                dialog_layout.setSpacing(10)

                # 使用主题适配的样式
                if parent and hasattr(parent, '_update_textedit_style'):
                    text_edit_style_fn = parent._update_textedit_style
                else:
                    text_edit_style_fn = None

                # CPU 列表标签
                cpu_label = QLabel(tr("cpu_list_label", "CPU 列表（每行一个）："))
                dialog_layout.addWidget(cpu_label)

                # CPU 列表输入框
                self.cpu_text_edit = TextEdit()
                self.cpu_text_edit.setPlaceholderText(tr("cpu_input_placeholder", "输入 CPU 名称，每行一个..."))
                # 使用主题适配的样式
                if text_edit_style_fn:
                    text_edit_style_fn(self.cpu_text_edit)
                # 从配置中读取 CPU_GROUP
                _config = load_config()
                cpu_group = _config.get("CPU_GROUP", ["CPU6240R", "CPU6336Y"])
                cpu_text = "\n".join(cpu_group)
                self.cpu_text_edit.setPlainText(cpu_text)
                # 根据内容行数动态设置高度
                line_count = len(cpu_group) if cpu_group else 1
                content_height = max(150, line_count * 25 + 20)  # 每行约25px，加上边距
                self.cpu_text_edit.setMinimumHeight(content_height)
                self.cpu_text_edit.setMaximumHeight(16777215)  # 不限制最大高度
                dialog_layout.addWidget(self.cpu_text_edit)

                self.viewLayout.addLayout(dialog_layout)

        dialog = CpuGroupDialog(self)

        if dialog.exec():
            # 获取文本内容
            cpu_text = dialog.cpu_text_edit.toPlainText().strip()
            # 按行分割，去除空行
            cpu_list = [line.strip() for line in cpu_text.split('\n') if line.strip()]
            if cpu_list:
                # 保存到实例变量
                self._cpu_group_list = cpu_list
                # 自动保存设置
                self._save_settings()
                if hasattr(self, 'log'):
                    self.log(tr("cpu_list_saved", "✓ 已保存 {count} 个 CPU: {cpus}").format(count=len(cpu_list), cpus=', '.join(cpu_list)))
            else:
                if hasattr(self, 'log'):
                    self.log(tr("cpu_list_empty", "❌ CPU 列表不能为空"))


    def _load_output_vars_config(self):
        """读取输出变量配置（从 ww3_shel.nml 和 ww3_ounf.nml）"""
        from setting.language_manager import tr
        
        # 获取 public/ww3 目录路径（在项目根目录下）
        config = load_config()
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        public_ww3_dir = config.get("PUBLIC_WW3_PATH", os.path.join(project_root, "public", "ww3"))
        
        ww3_shel_path = os.path.join(public_ww3_dir, "ww3_shel.nml")
        ww3_ounf_path = os.path.join(public_ww3_dir, "ww3_ounf.nml")
        
        selected_vars = []
        
        # 优先读取 ww3_shel.nml
        if os.path.exists(ww3_shel_path):
            try:
                with open(ww3_shel_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                for line in lines:
                    # 检查是否为注释行
                    line_stripped = line.lstrip()
                    is_comment = line_stripped.startswith('!')
                    
                    # 查找 TYPE%FIELD%LIST 行（非注释行，不区分大小写，允许空格变化）
                    if not is_comment and re.search(r'TYPE%FIELD%LIST', line, re.IGNORECASE) and "=" in line:
                        # 提取引号内的内容
                        match = re.search(r"['\"]([^'\"]+)['\"]", line)
                        if match:
                            var_list_str = match.group(1)
                            selected_vars = [v.strip() for v in var_list_str.split() if v.strip()]
                            break
            except Exception as e:
                if hasattr(self, 'log'):
                    self.log(tr("read_ww3_shel_failed", "❌ 读取 ww3_shel.nml 失败：{e}").format(e=e))
        else:
            if hasattr(self, 'log'):
                self.log(tr("file_not_exists", "⚠️ 文件不存在：{path}").format(path=ww3_shel_path))
        
        # 如果 ww3_shel.nml 没有找到，尝试读取 ww3_ounf.nml
        if not selected_vars and os.path.exists(ww3_ounf_path):
            try:
                with open(ww3_ounf_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                for line in lines:
                    # 检查是否为注释行
                    line_stripped = line.lstrip()
                    is_comment = line_stripped.startswith('!')
                    
                    # 查找 FIELD%LIST 行（非注释行，不区分大小写，允许空格变化）
                    if not is_comment and re.search(r'FIELD%LIST', line, re.IGNORECASE) and "=" in line:
                        # 提取引号内的内容
                        match = re.search(r"['\"]([^'\"]+)['\"]", line)
                        if match:
                            var_list_str = match.group(1)
                            selected_vars = [v.strip() for v in var_list_str.split() if v.strip()]
                            break
            except Exception as e:
                if hasattr(self, 'log'):
                    self.log(tr("read_ww3_ounf_failed", "❌ 读取 ww3_ounf.nml 失败：{e}").format(e=e))
        elif not selected_vars:
            if hasattr(self, 'log'):
                self.log(tr("file_not_exists", "⚠️ 文件不存在：{path}").format(path=ww3_ounf_path))
        
        # 更新复选框状态
        if hasattr(self, 'output_vars_checkboxes') and self.output_vars_checkboxes:
            if selected_vars:
                # 如果读取到了配置，使用配置的值更新所有复选框
                for var_code, checkbox in self.output_vars_checkboxes.items():
                    checkbox.setChecked(var_code in selected_vars)
                if hasattr(self, 'log'):
                    self.log(tr("output_vars_read_from_config", "✅ 已从配置文件读取输出变量：{vars}").format(vars=' '.join(selected_vars)))
            else:
                # 如果没有读取到配置，保持默认选中状态（已经在创建时设置）
                if hasattr(self, 'log'):
                    self.log(tr("output_vars_not_in_config", "⚠️ 未从配置文件中读取到输出变量，使用默认选中状态"))
        else:
            # 如果复选框还没有创建，记录警告
            if hasattr(self, 'log'):
                self.log(tr("output_vars_checkboxes_not_created", "⚠️ 输出变量复选框尚未创建，无法更新状态"))


    def _save_output_vars_config(self):
        """保存输出变量配置到 ww3_shel.nml 和 ww3_ounf.nml，并管理方案"""
        from setting.language_manager import tr
        
        if not hasattr(self, 'output_vars_checkboxes'):
            return

        # 获取选中的变量
        selected_vars = [var_code for var_code, checkbox in self.output_vars_checkboxes.items() if checkbox.isChecked()]
        
        if not selected_vars:
            if hasattr(self, 'log'):
                self.log(tr("output_vars_empty", "❌ 请至少选择一个输出变量"))
            return
        
        # 获取方案名称
        scheme_name = ""
        if hasattr(self, 'output_vars_scheme_name_edit'):
            scheme_name = self.output_vars_scheme_name_edit.text().strip()
            if not scheme_name:
                scheme_name = tr("default_scheme", "默认方案")
        
        # 检查是否是新方案
        is_new_scheme = True
        if hasattr(self, 'output_vars_scheme_combo'):
            current_scheme = self.output_vars_scheme_combo.currentText()
            if scheme_name == current_scheme and current_scheme:
                is_new_scheme = False
        
        # 保存方案（新建或覆盖已有方案）
        self._save_output_vars_scheme(scheme_name, selected_vars)
        if is_new_scheme and hasattr(self, 'log'):
            self.log(tr("scheme_saved", "✅ 已保存新方案：{name}").format(name=scheme_name))
        
        # 生成变量列表字符串，仅保存到配置文件
        var_list_str = ' '.join(selected_vars)
        if hasattr(self, 'log'):
            self.log(tr("output_vars_saved", "✅ 已保存输出变量配置：{vars}").format(vars=var_list_str))


    def _load_output_vars_schemes(self, preserve_selection=None):
        """加载输出变量方案列表
        
        Args:
            preserve_selection: 如果提供，刷新后保持选择该方案；否则默认选择"默认方案"
        """
        from setting.language_manager import tr
        
        # 从配置文件加载方案
        config = load_config()
        schemes = config.get("OUTPUT_VARS_SCHEMES", {})
        
        # 默认方案的变量列表
        default_scheme_vars = ["HS", "DIR", "FP", "T02", "WND", "PHS", "PTP", "PDIR", "PWS", "PNR", "TWS"]
        default_scheme_name = tr("default_scheme", "默认方案")
        
        # 如果没有方案或默认方案不存在，创建默认方案
        if not schemes or default_scheme_name not in schemes:
            schemes[default_scheme_name] = default_scheme_vars
            config["OUTPUT_VARS_SCHEMES"] = schemes
            
            # 保存配置
            from setting.config import CONFIG_FILE
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
            except Exception as e:
                if hasattr(self, 'log'):
                    self.log(tr("save_default_scheme_failed", "❌ 保存默认方案失败：{e}").format(e=e))
        
        # 更新下拉框
        if hasattr(self, 'output_vars_scheme_combo'):
            # 保存当前选择（如果未指定要保留的选择）
            if preserve_selection is None:
                preserve_selection = self.output_vars_scheme_combo.currentText()
            
            # 临时断开信号连接，避免在刷新时触发更新
            self.output_vars_scheme_combo.blockSignals(True)
            self.output_vars_scheme_combo.clear()
            scheme_names = sorted(schemes.keys())
            for scheme_name in scheme_names:
                self.output_vars_scheme_combo.addItem(scheme_name)
            
            # 如果指定了要保留的选择且该方案存在，则选择它；否则默认选择"默认方案"
            if preserve_selection and preserve_selection in scheme_names:
                index = scheme_names.index(preserve_selection)
                self.output_vars_scheme_combo.setCurrentIndex(index)
                # 验证选择是否正确
                if self.output_vars_scheme_combo.currentText() != preserve_selection:
                    self.output_vars_scheme_combo.setCurrentText(preserve_selection)
            else:
                # 选择默认方案
                default_index = self.output_vars_scheme_combo.findText(default_scheme_name)
                if default_index >= 0:
                    self.output_vars_scheme_combo.setCurrentIndex(default_index)
                elif self.output_vars_scheme_combo.count() > 0:
                    self.output_vars_scheme_combo.setCurrentIndex(0)
            
            # 恢复信号连接
            self.output_vars_scheme_combo.blockSignals(False)
            
            # 加载当前选中的方案
            if self.output_vars_scheme_combo.count() > 0:
                self._on_scheme_changed(self.output_vars_scheme_combo.currentText())


    def _update_ww3_ounf_timesplit_in_dir(self, target_dir):
        """更新指定目录下 ww3_ounf.nml 的 FIELD%TIMESPLIT"""
        if not target_dir or not isinstance(target_dir, str):
            return

        nml_path = os.path.join(target_dir, "ww3_ounf.nml")
        if not os.path.exists(nml_path):
            return

        from setting.config import load_config
        config = load_config()
        file_split = config.get("FILE_SPLIT", tr("file_split_year", "年"))

        # 0 (无日期), 4(年), 6(月), 8(日), 10(小时)
        file_split_value_map = {
            tr("file_split_none", "无日期"): 0,
            tr("file_split_year", "年"): 4,
            tr("file_split_month", "月"): 6,
            tr("file_split_day", "天"): 8,
            tr("file_split_hour", "小时"): 10
        }
        file_split_value_map_en = {"None": 0, "Year": 4, "Month": 6, "Day": 8, "Hour": 10}

        if isinstance(file_split, (int, float)):
            timesplit_value = int(file_split)
        else:
            timesplit_value = file_split_value_map.get(
                file_split,
                file_split_value_map_en.get(file_split, 4)
            )

        try:
            with open(nml_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            timesplit_found = False
            for line in lines:
                line_stripped = line.lstrip()
                is_comment = line_stripped.startswith('!')
                if not is_comment and "FIELD%TIMESPLIT" in line:
                    new_lines.append(f"  FIELD%TIMESPLIT        =  {timesplit_value}\n")
                    timesplit_found = True
                    continue
                new_lines.append(line)

            if not timesplit_found:
                in_field_nml = False
                insert_index = -1
                for i, line in enumerate(new_lines):
                    if "&FIELD_NML" in line.upper():
                        in_field_nml = True
                    if in_field_nml and re.match(r'^\s*/\s*$', line) and not line.strip().startswith("!"):
                        insert_index = i
                        break
                if insert_index > 0:
                    new_lines.insert(insert_index, f"  FIELD%TIMESPLIT        =  {timesplit_value}\n")

            with open(nml_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except Exception:
            return


    def _update_ww3_ounp_timesplit_in_dir(self, target_dir):
        """更新指定目录下 ww3_ounp.nml 的 POINT%TIMESPLIT"""
        if not target_dir or not isinstance(target_dir, str):
            return

        nml_path = os.path.join(target_dir, "ww3_ounp.nml")
        if not os.path.exists(nml_path):
            return

        from setting.config import load_config
        config = load_config()
        file_split = config.get("FILE_SPLIT", tr("file_split_year", "年"))

        # 0 (无日期), 4(年), 6(月), 8(日), 10(小时)
        file_split_value_map = {
            tr("file_split_none", "无日期"): 0,
            tr("file_split_year", "年"): 4,
            tr("file_split_month", "月"): 6,
            tr("file_split_day", "天"): 8,
            tr("file_split_hour", "小时"): 10
        }
        file_split_value_map_en = {"None": 0, "Year": 4, "Month": 6, "Day": 8, "Hour": 10}

        if isinstance(file_split, (int, float)):
            timesplit_value = int(file_split)
        else:
            timesplit_value = file_split_value_map.get(
                file_split,
                file_split_value_map_en.get(file_split, 4)
            )

        try:
            with open(nml_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            timesplit_found = False
            for line in lines:
                line_stripped = line.lstrip()
                is_comment = line_stripped.startswith('!')
                if not is_comment and "POINT%TIMESPLIT" in line:
                    new_lines.append(f"  POINT%TIMESPLIT        =  {timesplit_value}\n")
                    timesplit_found = True
                    continue
                new_lines.append(line)

            if not timesplit_found:
                in_point_nml = False
                insert_index = -1
                for i, line in enumerate(new_lines):
                    if "&POINT_NML" in line.upper():
                        in_point_nml = True
                    if in_point_nml and re.match(r'^\s*/\s*$', line) and not line.strip().startswith("!"):
                        insert_index = i
                        break
                if insert_index > 0:
                    new_lines.insert(insert_index, f"  POINT%TIMESPLIT        =  {timesplit_value}\n")

            with open(nml_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except Exception:
            return


    def _update_ww3_trnc_timesplit_in_dir(self, target_dir):
        """更新指定目录下 ww3_trnc.nml 的 TRACK%TIMESPLIT"""
        if not target_dir or not isinstance(target_dir, str):
            return

        nml_path = os.path.join(target_dir, "ww3_trnc.nml")
        if not os.path.exists(nml_path):
            return

        from setting.config import load_config
        config = load_config()
        file_split = config.get("FILE_SPLIT", tr("file_split_year", "年"))

        # 0 (无日期), 4(年), 6(月), 8(日), 10(小时)
        file_split_value_map = {
            tr("file_split_none", "无日期"): 0,
            tr("file_split_year", "年"): 4,
            tr("file_split_month", "月"): 6,
            tr("file_split_day", "天"): 8,
            tr("file_split_hour", "小时"): 10
        }
        file_split_value_map_en = {"None": 0, "Year": 4, "Month": 6, "Day": 8, "Hour": 10}

        if isinstance(file_split, (int, float)):
            timesplit_value = int(file_split)
        else:
            timesplit_value = file_split_value_map.get(
                file_split,
                file_split_value_map_en.get(file_split, 4)
            )

        try:
            with open(nml_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            timesplit_found = False
            for line in lines:
                line_stripped = line.lstrip()
                is_comment = line_stripped.startswith('!')
                if not is_comment and "TRACK%TIMESPLIT" in line:
                    new_lines.append(f"  TRACK%TIMESPLIT        =  {timesplit_value}\n")
                    timesplit_found = True
                    continue
                new_lines.append(line)

            if not timesplit_found:
                in_track_nml = False
                insert_index = -1
                for i, line in enumerate(new_lines):
                    if "&TRACK_NML" in line.upper():
                        in_track_nml = True
                    if in_track_nml and re.match(r'^\s*/\s*$', line) and not line.strip().startswith("!"):
                        insert_index = i
                        break
                if insert_index > 0:
                    new_lines.insert(insert_index, f"  TRACK%TIMESPLIT        =  {timesplit_value}\n")

            with open(nml_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except Exception:
            return


    def _save_output_vars_scheme(self, scheme_name, selected_vars):
        """保存输出变量方案到配置文件"""
        config = load_config()
        
        if "OUTPUT_VARS_SCHEMES" not in config:
            config["OUTPUT_VARS_SCHEMES"] = {}
        
        config["OUTPUT_VARS_SCHEMES"][scheme_name] = selected_vars
        
        # 保存配置（使用 config.py 中的配置路径）
        from setting.config import CONFIG_FILE
        config_path = CONFIG_FILE
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            # 重新加载方案列表，并保持选择新保存的方案
            self._load_output_vars_schemes(preserve_selection=scheme_name)
            
            # 更新输入框为当前方案名称
            if hasattr(self, 'output_vars_scheme_name_edit'):
                self.output_vars_scheme_name_edit.setText(scheme_name)
            
            # 更新主窗口第四步的下拉选择框，并切换到新保存的方案
            # 使用 QTimer 延迟执行，确保配置文件已保存
            if hasattr(self, '_load_output_schemes_to_combo'):
                from PyQt6 import QtCore
                QtCore.QTimer.singleShot(100, lambda: self._load_output_schemes_to_combo(preserve_selection=scheme_name))
        except Exception as e:
            if hasattr(self, 'log'):
                self.log(tr("save_scheme_failed", "❌ 保存方案失败：{e}").format(e=e))


    def _on_scheme_changed(self, scheme_name):
        """方案切换时的回调"""
        from setting.language_manager import tr
        
        if not scheme_name or not hasattr(self, 'output_vars_checkboxes'):
            return
        
        # 从配置文件加载方案
        config = load_config()
        schemes = config.get("OUTPUT_VARS_SCHEMES", {})
        
        if scheme_name in schemes:
            selected_vars = schemes[scheme_name]
            
            # 更新复选框状态
            for var_code, checkbox in self.output_vars_checkboxes.items():
                checkbox.setChecked(var_code in selected_vars)
            
            # 更新输入框
            if hasattr(self, 'output_vars_scheme_name_edit'):
                self.output_vars_scheme_name_edit.setText(scheme_name)


    def _delete_output_vars_scheme(self):
        """删除当前选中的方案"""
        from setting.language_manager import tr
        
        if not hasattr(self, 'output_vars_scheme_combo'):
            return
        
        scheme_name = self.output_vars_scheme_combo.currentText()
        if not scheme_name:
            if hasattr(self, 'log'):
                self.log(tr("no_scheme_selected", "❌ 请先选择一个方案"))
            return
        
        # 检查方案数量，确保至少有一个方案（无论是否是默认方案）
        config = load_config()
        schemes = config.get("OUTPUT_VARS_SCHEMES", {})
        if len(schemes) <= 1:
            if hasattr(self, 'log'):
                self.log(tr("cannot_delete_last_scheme", "❌ 至少需要保留一个方案"))
            return
        
        # 从配置文件删除方案
        if "OUTPUT_VARS_SCHEMES" in config and scheme_name in config["OUTPUT_VARS_SCHEMES"]:
            del config["OUTPUT_VARS_SCHEMES"][scheme_name]
            
            # 保存配置（使用 config.py 中的配置路径）
            from setting.config import CONFIG_FILE
            config_path = CONFIG_FILE
            try:
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                
                # 重新加载方案列表
                # 如果删除的不是当前选择的方案，保持当前选择；否则选择默认方案
                if hasattr(self, 'output_vars_scheme_combo'):
                    current_selection = self.output_vars_scheme_combo.currentText()
                    # 如果当前选择的就是被删除的方案，则选择默认方案
                    if current_selection == scheme_name:
                        from setting.language_manager import tr
                        default_scheme_name = tr("default_scheme", "默认方案")
                        self._load_output_vars_schemes(preserve_selection=default_scheme_name)
                    else:
                        # 否则保持当前选择
                        self._load_output_vars_schemes(preserve_selection=current_selection)
                else:
                    self._load_output_vars_schemes()
                
                # 更新主窗口第四步的下拉选择框
                # 如果删除的不是当前选择的方案，保持当前选择；否则选择默认方案
                if hasattr(self, '_load_output_schemes_to_combo'):
                    if hasattr(self, 'output_scheme_combo'):
                        current_selection = self.output_scheme_combo.currentText()
                        # 如果当前选择的就是被删除的方案，则选择默认方案
                        if current_selection == scheme_name:
                            from setting.language_manager import tr
                            default_scheme_name = tr("default_scheme", "默认方案")
                            self._load_output_schemes_to_combo(preserve_selection=default_scheme_name)
                        else:
                            # 否则保持当前选择
                            self._load_output_schemes_to_combo(preserve_selection=current_selection)
                    else:
                        self._load_output_schemes_to_combo()
                
                if hasattr(self, 'log'):
                    self.log(tr("scheme_deleted", "✅ 已删除方案：{name}").format(name=scheme_name))
            except Exception as e:
                if hasattr(self, 'log'):
                    self.log(tr("delete_scheme_failed", "❌ 删除方案失败：{e}").format(e=e))
