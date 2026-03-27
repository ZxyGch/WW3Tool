"""
设置模块 - UI部分
包含设置页面的UI创建
"""
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

from .settings_service import SettingsServiceMixin

class SettingsMixin(SettingsServiceMixin):
    """Settings功能模块"""

    def _create_settings_page(self, force_language_code=None):
        """创建设置页面"""
        try:

            
            # 按钮样式：使用主题适配的样式
            button_style = self._get_button_style()

            # 输入框样式：使用主题适配的样式
            input_style = self._get_input_style()

            # 下拉框样式：使用主题适配的样式
            combo_style = self._get_combo_style()

            # 创建设置页面容器
            settings_content = QWidget()
            settings_content.setStyleSheet("QWidget { background-color: transparent; }")
            settings_layout = QVBoxLayout(settings_content)
            settings_layout.setContentsMargins(0, 0, 0, 10)  # 左边距和上边距、右边距设为0，只保留下边距
            settings_layout.setSpacing(15)

            # 加载当前配置
            current_config = load_config()

            # 导入翻译函数
            from setting.language_manager import tr
            
            # === 界面设置（放在最前面） ===
            language_card = HeaderCardWidget(settings_content)
            language_card.setTitle(tr("interface_settings", "界面设置"))
            language_card.setStyleSheet("""
                HeaderCardWidget QLabel {
                    font-weight: normal;
                    margin-left: 0px;
                    padding-left: 0px;
                }
            """)
            language_card.headerLayout.setContentsMargins(11, 10, 11, 12)
            language_card_layout = QVBoxLayout()
            language_card_layout.setSpacing(5)
            language_card_layout.setContentsMargins(0, 0, 0, 0)

            # 语言选择
            language_row = QHBoxLayout()
            language_label = QLabel(tr("language_select", "语言:"))
            language_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            language_row.addWidget(language_label)
            
            # 导入语言管理模块（如果还没有导入）
            from setting.language_manager import get_supported_languages, set_language
            
            # 获取支持的语言
            supported_languages = get_supported_languages()
            self.settings_language_combo = ComboBox()
            
            # 添加语言选项（显示语言名称）
            for lang_code, lang_name in supported_languages.items():
                self.settings_language_combo.addItem(lang_name, lang_code)
            
            # 先标记为未初始化，防止设置索引时触发信号
            if not hasattr(self, '_language_combo_initialized'):
                self._language_combo_initialized = False
            
            # 先断开信号，设置索引后再连接
            try:
                self.settings_language_combo.currentIndexChanged.disconnect()
            except:
                pass  # 如果信号未连接，忽略错误
            
            # 设置当前语言
            # 如果提供了强制语言代码，使用它；否则从配置读取
            if force_language_code:
                current_lang = force_language_code
            else:
                current_lang = current_config.get("LANGUAGE", "zh_CN")
            
            # 验证语言代码是否有效
            if current_lang not in supported_languages:
                current_lang = "zh_CN"  # 如果无效，使用默认值
            
            # 查找对应的索引（手动遍历，更可靠）
            current_index = -1
            for i in range(self.settings_language_combo.count()):
                item_data = self.settings_language_combo.itemData(i)
                # 使用字符串比较，确保类型一致
                if str(item_data) == str(current_lang):
                    current_index = i
                    break
            
            if current_index >= 0:
                self.settings_language_combo.setCurrentIndex(current_index)
            else:
                # 如果找不到，尝试通过文本查找
                lang_name = supported_languages.get(current_lang, tr("simplified_chinese", "简体中文"))
                current_index = self.settings_language_combo.findText(lang_name)
                if current_index >= 0:
                    self.settings_language_combo.setCurrentIndex(current_index)
                else:
                    # 如果还是找不到，根据语言代码选择（zh_CN=0, en_US=1）
                    if current_lang == "en_US":
                        # 确保有至少2个选项
                        if self.settings_language_combo.count() >= 2:
                            self.settings_language_combo.setCurrentIndex(1)
                        else:
                            self.settings_language_combo.setCurrentIndex(0)
                    else:
                        # 默认选择第一个（中文）
                        self.settings_language_combo.setCurrentIndex(0)
            
            self.settings_language_combo.setStyleSheet(combo_style)
            
            # 设置完索引后再连接信号（确保索引已经设置完成）
            self.settings_language_combo.currentIndexChanged.connect(self._on_language_changed)
            
            # 延迟标记为已初始化，确保索引设置完成后再允许触发
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(300, lambda: setattr(self, '_language_combo_initialized', True))
            
            # 让ComboBox占满剩余宽度，并设置相同的最小宽度以确保对齐
            combo_min_width = 200  # 设置一个合理的最小宽度
            self.settings_language_combo.setMinimumWidth(combo_min_width)
            language_row.addWidget(self.settings_language_combo, 1)  # 拉伸因子为1，占满剩余空间
            language_card_layout.addLayout(language_row)

            # 主题选择（暂时隐藏，默认跟随系统）
            show_theme_option = False
            if show_theme_option:
                theme_row = QHBoxLayout()
                theme_label = QLabel(tr("theme_select", "界面主题:"))
                theme_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                theme_row.addWidget(theme_label)
                
                # 创建主题选择下拉框
                self.settings_theme_combo = ComboBox()
                
                # 添加主题选项
                self.settings_theme_combo.addItem(tr("theme_light", "明亮"))
                self.settings_theme_combo.setItemData(
                    self.settings_theme_combo.count() - 1,
                    "LIGHT"
                )
                self.settings_theme_combo.addItem(tr("theme_dark", "黑暗"))
                self.settings_theme_combo.setItemData(
                    self.settings_theme_combo.count() - 1,
                    "DARK"
                )
                self.settings_theme_combo.addItem(tr("theme_auto", "跟随系统"))
                self.settings_theme_combo.setItemData(
                    self.settings_theme_combo.count() - 1,
                    "AUTO"
                )
                
                # 先断开信号，设置索引后再连接
                try:
                    self.settings_theme_combo.currentIndexChanged.disconnect()
                except:
                    pass  # 如果信号未连接，忽略错误
                
                # 设置当前主题
                theme_str = current_config.get("THEME", "AUTO")
                # 验证主题值是否有效
                if theme_str not in ["LIGHT", "DARK", "AUTO"]:
                    theme_str = "AUTO"  # 如果无效，使用默认值（跟随系统）
                
                # 查找对应的索引
                current_theme_index = -1
                for i in range(self.settings_theme_combo.count()):
                    item_data = self.settings_theme_combo.itemData(i)
                    if str(item_data) == theme_str:
                        current_theme_index = i
                        break
                
                if current_theme_index >= 0:
                    self.settings_theme_combo.setCurrentIndex(current_theme_index)
                else:
                    # 默认选择跟随系统
                    self.settings_theme_combo.setCurrentIndex(2)
                
                self.settings_theme_combo.setStyleSheet(combo_style)
                self.settings_theme_combo.setMinimumWidth(combo_min_width)  # 设置相同的最小宽度
                
                # 设置完索引后再连接信号
                self.settings_theme_combo.currentIndexChanged.connect(self._on_theme_combo_changed)
                
                # 让ComboBox占满剩余宽度
                theme_row.addWidget(self.settings_theme_combo, 1)  # 拉伸因子为1，占满剩余空间
                language_card_layout.addLayout(theme_row)

            # 运行方式选择
            run_mode_row = QHBoxLayout()
            run_mode_label = QLabel(tr("run_mode_select", "运行方式:"))
            run_mode_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            run_mode_row.addWidget(run_mode_label)
            
            # 创建运行方式选择下拉框
            self.settings_run_mode_combo = ComboBox()
            
            # 添加运行方式选项
            self.settings_run_mode_combo.addItem(tr("run_mode_local", "本地运行"))
            self.settings_run_mode_combo.setItemData(
                self.settings_run_mode_combo.count() - 1,
                "local"
            )
            self.settings_run_mode_combo.addItem(tr("run_mode_server", "服务器运行"))
            self.settings_run_mode_combo.setItemData(
                self.settings_run_mode_combo.count() - 1,
                "server"
            )
            self.settings_run_mode_combo.addItem(tr("run_mode_both", "本地+服务器运行"))
            self.settings_run_mode_combo.setItemData(
                self.settings_run_mode_combo.count() - 1,
                "both"
            )
            
            # 先断开信号，设置索引后再连接
            try:
                self.settings_run_mode_combo.currentIndexChanged.disconnect()
            except:
                pass  # 如果信号未连接，忽略错误
            
            # 设置当前运行方式
            run_mode = current_config.get("RUN_MODE", "both")
            # 验证运行方式值是否有效
            if run_mode not in ["local", "server", "both"]:
                run_mode = "both"  # 如果无效，使用默认值（本地+服务器运行）
            
            # 查找对应的索引
            current_run_mode_index = -1
            for i in range(self.settings_run_mode_combo.count()):
                item_data = self.settings_run_mode_combo.itemData(i)
                if str(item_data) == run_mode:
                    current_run_mode_index = i
                    break
            
            if current_run_mode_index >= 0:
                self.settings_run_mode_combo.setCurrentIndex(current_run_mode_index)
            else:
                # 默认选择本地+服务器运行（索引2）
                self.settings_run_mode_combo.setCurrentIndex(2)
            
            self.settings_run_mode_combo.setStyleSheet(combo_style)
            self.settings_run_mode_combo.setMinimumWidth(combo_min_width)  # 设置相同的最小宽度
            
            # 设置完索引后再连接信号（运行方式改变时更新界面可见性）
            self.settings_run_mode_combo.currentIndexChanged.connect(self._on_run_mode_changed)
            
            # 让ComboBox占满剩余宽度
            run_mode_row.addWidget(self.settings_run_mode_combo, 1)  # 拉伸因子为1，占满剩余空间
            language_card_layout.addLayout(run_mode_row)

            language_card.viewLayout.setContentsMargins(11, 10, 11, 12)
            language_card.viewLayout.addLayout(language_card_layout)
            settings_layout.addWidget(language_card)
            
            # === 强迫场选择设置 ===
            forcing_field_card = HeaderCardWidget(settings_content)
            forcing_field_card.setTitle(tr("forcing_field_settings", "强迫场选择"))
            forcing_field_card.setStyleSheet("""
                HeaderCardWidget QLabel {
                    font-weight: normal;
                    margin-left: 0px;
                    padding-left: 0px;
                }
            """)
            forcing_field_card.headerLayout.setContentsMargins(11, 10, 11, 12)
            forcing_field_card_layout = QVBoxLayout()
            forcing_field_card_layout.setSpacing(5)
            forcing_field_card_layout.setContentsMargins(0, 0, 0, 0)
            
            # 自动关联场开关
            auto_associate_row = QHBoxLayout()
            auto_associate_label = QLabel(tr("auto_associate_fields", "自动关联场:"))
            auto_associate_row.addWidget(auto_associate_label)
            
            auto_associate_value = current_config.get("FORCING_FIELD_AUTO_ASSOCIATE", True)
            if SwitchButton is not None:
                self.settings_auto_associate_switch = SwitchButton()
                self.settings_auto_associate_switch.setSpacing(0)
                self.settings_auto_associate_switch.setChecked(bool(auto_associate_value))
                self.settings_auto_associate_switch.setOnText("")
                self.settings_auto_associate_switch.setOffText("")
            else:
                # 如果 SwitchButton 不可用，使用 QCheckBox
                self.settings_auto_associate_switch = QtWidgets.QCheckBox()
                self.settings_auto_associate_switch.setChecked(bool(auto_associate_value))
            
            self.settings_auto_associate_switch.setStyleSheet("""
                    SwitchButton {
                        margin: 0px !important;
                        margin-right: 5px !important;
                        padding: 0px !important;
                        padding-right: 0px !important;
                        max-width: none;
                    }
                """)

            auto_associate_row.addStretch()
            auto_associate_row.addWidget(self.settings_auto_associate_switch, 0)
            auto_associate_row.setContentsMargins(0, 0, 0, 0)
            
            if SwitchButton is not None and hasattr(self.settings_auto_associate_switch, 'checkedChanged'):
                self.settings_auto_associate_switch.checkedChanged.connect(self._save_settings)
            elif hasattr(self.settings_auto_associate_switch, 'stateChanged'):
                self.settings_auto_associate_switch.stateChanged.connect(self._save_settings)
            
            forcing_field_card_layout.addLayout(auto_associate_row)
            
            # 文件处理方式
            file_process_row = QHBoxLayout()
            file_process_label = QLabel(tr("file_process_mode", "文件处理方式:"))
            file_process_row.addWidget(file_process_label)
            
            self.settings_file_process_combo = ComboBox()
            self.settings_file_process_combo.addItem(tr("copy", "复制"), "copy")
            self.settings_file_process_combo.addItem(tr("move", "剪切"), "move")
            
            # 从配置中读取文件处理方式
            file_process_mode = current_config.get("FORCING_FIELD_FILE_PROCESS_MODE", "copy")
            if file_process_mode == "move":
                self.settings_file_process_combo.setCurrentIndex(1)
            else:
                self.settings_file_process_combo.setCurrentIndex(0)
            
            self.settings_file_process_combo.setStyleSheet(combo_style)
            self.settings_file_process_combo.currentIndexChanged.connect(self._save_settings)
            
            file_process_row.addWidget(self.settings_file_process_combo, 1)
            forcing_field_card_layout.addLayout(file_process_row)
            
            forcing_field_card.viewLayout.setContentsMargins(11, 10, 11, 12)
            forcing_field_card.viewLayout.addLayout(forcing_field_card_layout)
            settings_layout.addWidget(forcing_field_card)
            
            # === 路径设置 ===
            matlab_card = HeaderCardWidget(settings_content)
            matlab_card.setTitle(tr("path_settings", "路径设置"))
            self.matlab_card = matlab_card  # 保存引用以便后续更新
            matlab_card.setStyleSheet("""
                HeaderCardWidget QLabel {
                    font-weight: normal;
                    margin-left: 0px;
                    padding-left: 0px;
                }
            """)
            matlab_card.headerLayout.setContentsMargins(11, 10, 11, 12)
            matlab_card_layout = QVBoxLayout()
            matlab_card_layout.setSpacing(5)
            matlab_card_layout.setContentsMargins(0, 0, 0, 0)

            workdir_label = QLabel(tr("workdir_path", "默认工作目录:"))
            self.workdir_label = workdir_label  # 保存引用以便后续更新
            matlab_card_layout.addWidget(workdir_label)
            workdir_row = QHBoxLayout()
            self.settings_workdir_edit = LineEdit()
            workdir_path = current_config.get("DEFAULT_WORKDIR", "").strip()
            if workdir_path:
                workdir_path = os.path.normpath(workdir_path)  # 规范化路径（Windows 上会转换为反斜杠格式）
            self.settings_workdir_edit.setText(workdir_path)
            self.settings_workdir_edit.setStyleSheet(input_style)
            workdir_row.addWidget(self.settings_workdir_edit, 1)
            self.settings_workdir_edit.setPlaceholderText(f"{tr('default_path', '默认路径')}：WW3Tool/workSpace")
            btn_choose_workdir = PrimaryPushButton(tr("select", "选择"))
            btn_choose_workdir.setStyleSheet(button_style)
            btn_choose_workdir.clicked.connect(lambda: self._choose_workdir_path())
            workdir_row.addWidget(btn_choose_workdir)
            matlab_card_layout.addLayout(workdir_row)

            forcing_field_dir_label = QLabel(tr("forcing_field_dir_path", "默认打开的强迫场文件的目录:"))
            self.forcing_field_dir_label = forcing_field_dir_label  # 保存引用以便后续更新
            matlab_card_layout.addWidget(forcing_field_dir_label)
            forcing_field_dir_row = QHBoxLayout()
            self.settings_forcing_field_dir_edit = LineEdit()
            self.settings_forcing_field_dir_edit.setPlaceholderText(f"{tr('default_path', '默认路径')}：WW3Tool/public/forcing")
            forcing_field_dir_path = current_config.get("FORCING_FIELD_DIR_PATH", "").strip()
            # 如果配置为空，输入框显示为空（不显示默认路径）
            if forcing_field_dir_path:
                forcing_field_dir_path = os.path.normpath(forcing_field_dir_path)  # 规范化路径（Windows 上会转换为反斜杠格式）
            self.settings_forcing_field_dir_edit.setText(forcing_field_dir_path)
            self.settings_forcing_field_dir_edit.setStyleSheet(input_style)
            forcing_field_dir_row.addWidget(self.settings_forcing_field_dir_edit, 1)
            btn_choose_forcing_field_dir = PrimaryPushButton(tr("select", "选择"))
            btn_choose_forcing_field_dir.setStyleSheet(button_style)
            btn_choose_forcing_field_dir.clicked.connect(lambda: self._choose_forcing_field_dir_path())
            forcing_field_dir_row.addWidget(btn_choose_forcing_field_dir)
            matlab_card_layout.addLayout(forcing_field_dir_row)

            ww3_config_label = QLabel(tr("ww3_config_path", "WW3 配置文件:"))
            self.ww3_config_label = ww3_config_label  # 保存引用以便后续更新
            matlab_card_layout.addWidget(ww3_config_label)
            ww3_config_row = QHBoxLayout()
            self.settings_ww3_config_edit = LineEdit()
            self.settings_ww3_config_edit.setPlaceholderText(f"{tr('default_path', '默认路径')}：WW3Tool/public/ww3")
            self.settings_ww3_config_edit.setReadOnly(True)  # 只读，仅用于显示
            ww3_config_path = current_config.get("WW3_CONFIG_PATH", "").strip()
            # 如果配置为空，输入框显示为空（不显示默认路径）
            if ww3_config_path:
                ww3_config_path = os.path.normpath(ww3_config_path)  # 规范化路径（Windows 上会转换为反斜杠格式）
            self.settings_ww3_config_edit.setText(ww3_config_path)
            self.settings_ww3_config_edit.setStyleSheet(input_style)
            ww3_config_row.addWidget(self.settings_ww3_config_edit, 1)
            btn_open_ww3_config = PrimaryPushButton(tr("open", "打开"))
            btn_open_ww3_config.setStyleSheet(button_style)
            btn_open_ww3_config.clicked.connect(lambda: self._open_ww3_config_path())
            ww3_config_row.addWidget(btn_open_ww3_config)
            matlab_card_layout.addLayout(ww3_config_row)

            ww3bin_label = QLabel(tr("ww3bin_path", "默认 WW3BIN 路径:"))
            self.ww3bin_label = ww3bin_label  # 保存引用以便后续更新
            matlab_card_layout.addWidget(ww3bin_label)
            ww3bin_row = QHBoxLayout()
            self.settings_ww3bin_edit = LineEdit()
            self.settings_ww3bin_edit.setPlaceholderText(tr("ww3bin_empty_hide_local", "为空则隐藏本地执行"))
            ww3bin_path = current_config.get("WW3BIN_PATH", "").strip()
            if ww3bin_path:
                ww3bin_path = os.path.normpath(ww3bin_path)  # 规范化路径（Windows 上会转换为反斜杠格式）
            self.settings_ww3bin_edit.setText(ww3bin_path)
            self.settings_ww3bin_edit.setStyleSheet(input_style)
            ww3bin_row.addWidget(self.settings_ww3bin_edit, 1)
            btn_choose_ww3bin = PrimaryPushButton(tr("select", "选择"))
            btn_choose_ww3bin.setStyleSheet(button_style)
            btn_choose_ww3bin.clicked.connect(lambda: self._choose_ww3bin_path())
            ww3bin_row.addWidget(btn_choose_ww3bin)
            matlab_card_layout.addLayout(ww3bin_row)

            jason_label = QLabel(tr("jason_path", "默认 JASON 数据路径:"))
            self.jason_label = jason_label  # 保存引用以便后续更新
            matlab_card_layout.addWidget(jason_label)
            jason_row = QHBoxLayout()
            self.settings_jason_edit = LineEdit()
            jason_path = current_config.get("JASON_PATH", "").strip()
            if jason_path:
                jason_path = os.path.normpath(jason_path)  # 规范化路径（Windows 上会转换为反斜杠格式）
            self.settings_jason_edit.setText(jason_path)
            self.settings_jason_edit.setStyleSheet(input_style)
            jason_row.addWidget(self.settings_jason_edit, 1)
            btn_choose_jason = PrimaryPushButton(tr("select", "选择"))
            btn_choose_jason.setStyleSheet(button_style)
            btn_choose_jason.clicked.connect(lambda: self._choose_jason_path())
            jason_row.addWidget(btn_choose_jason)
            matlab_card_layout.addLayout(jason_row)

            # 地图地理特征显示开关
            map_feature_row = QHBoxLayout()
            map_feature_label = QLabel(tr("show_land_coastline", "显示陆地和海岸线:"))
            self.settings_show_land_coastline_checkbox = QtWidgets.QCheckBox()
            show_land_coast = current_config.get("SHOW_LAND_COASTLINE", True)
            # 处理字符串类型的配置值（JSON 可能将布尔值保存为字符串）
            if isinstance(show_land_coast, str):
                show_land_coast = show_land_coast.lower() in ('true', '1', 'yes')
            self.settings_show_land_coastline_checkbox.setChecked(bool(show_land_coast))
            self.settings_show_land_coastline_checkbox.setToolTip(tr("hide_land_coastline_tooltip", "关闭此选项将不在生成的地图上显示陆地和海岸线，只显示数据本身"))
            map_feature_row.addWidget(map_feature_label)
            map_feature_row.addWidget(self.settings_show_land_coastline_checkbox)
            map_feature_row.addStretch()  # 添加弹性空间，让复选框靠左
            #matlab_card_layout.addLayout(map_feature_row)

            matlab_card.viewLayout.setContentsMargins(11, 10, 11, 12)
            matlab_card.viewLayout.addLayout(matlab_card_layout)
            settings_layout.addWidget(matlab_card)

            # === Gridgen 配置 ===
            grid_card = HeaderCardWidget(settings_content)
            grid_card.setTitle(tr("gridgen_config", "Gridgen 配置"))
            grid_card.setStyleSheet("""
                HeaderCardWidget QLabel {
                    font-weight: normal;
                    margin-left: 0px;
                    padding-left: 0px;
                }
            """)
            grid_card.headerLayout.setContentsMargins(11, 10, 11, 12)
            grid_card_layout = QVBoxLayout()
            grid_card_layout.setSpacing(5)
            grid_card_layout.setContentsMargins(0, 0, 0, 0)

            # 路径设置（MATLAB、Reference Data）- 放在最上面
            matlab_label = QLabel(tr("matlab_path", "MATLAB 路径:"))
            self.matlab_label = matlab_label  # 保存引用以便后续更新
            grid_card_layout.addWidget(matlab_label)
            matlab_row = QHBoxLayout()
            self.settings_matlab_edit = LineEdit()
            self.settings_matlab_edit.setPlaceholderText(tr("matlab_not_necessary", "MATALAB 不是必要的，也不推荐使用"))
            matlab_path = current_config.get("MATLAB_PATH", "").strip()
            if matlab_path:
                matlab_path = os.path.normpath(matlab_path)  # 规范化路径（Windows 上会转换为反斜杠格式）
            self.settings_matlab_edit.setText(matlab_path)
            self.settings_matlab_edit.setStyleSheet(input_style)
            matlab_row.addWidget(self.settings_matlab_edit, 1)
            btn_choose_matlab = PrimaryPushButton(tr("select", "选择"))
            btn_choose_matlab.setStyleSheet(button_style)
            btn_choose_matlab.clicked.connect(lambda: self._choose_matlab_path())
            matlab_row.addWidget(btn_choose_matlab)
            grid_card_layout.addLayout(matlab_row)

            reference_data_label = QLabel(tr("reference_data_path", "Reference Data 路径:"))
            self.reference_data_label = reference_data_label  # 保存引用以便后续更新
            grid_card_layout.addWidget(reference_data_label)
            reference_data_row = QHBoxLayout()
            self.settings_reference_data_edit = LineEdit()
            self.settings_reference_data_edit.setPlaceholderText(f"{tr('default_path', '默认路径')}：WW3Tool/WW3-Grid-Generator/reference_data")
            reference_data_path = current_config.get("REFERENCE_DATA_PATH", "").strip()
            if not reference_data_path:
                reference_data_path = ""
            else:
                reference_data_path = os.path.normpath(reference_data_path)
            self.settings_reference_data_edit.setText(reference_data_path)
            self.settings_reference_data_edit.setStyleSheet(input_style)
            reference_data_row.addWidget(self.settings_reference_data_edit, 1)
            btn_choose_reference_data = PrimaryPushButton(tr("select", "选择"))
            btn_choose_reference_data.setStyleSheet(button_style)
            btn_choose_reference_data.clicked.connect(lambda: self._choose_reference_data_path())
            reference_data_row.addWidget(btn_choose_reference_data)
            grid_card_layout.addLayout(reference_data_row)

            # 使用网格布局确保输入框左右对齐
            grid_params_layout = QGridLayout()
            grid_params_layout.setColumnStretch(1, 1)  # 让输入框列可以拉伸，但不固定宽度
            grid_params_layout.setSpacing(5)

            # GRIDGEN 版本选择（放在网格参数的第一个位置）
            gridgen_version_label = QLabel(tr("gridgen_version", "GRIDGEN 版本:"))
            self.settings_gridgen_version_combo = ComboBox()
            self.settings_gridgen_version_combo.addItems(["Python","MATLAB"])
            current_version = current_config.get("GRIDGEN_VERSION", "MATLAB")
            index = self.settings_gridgen_version_combo.findText(current_version)
            if index >= 0:
                self.settings_gridgen_version_combo.setCurrentIndex(index)
            self.settings_gridgen_version_combo.setStyleSheet(combo_style)
            grid_params_layout.addWidget(gridgen_version_label, 0, 0)
            grid_params_layout.addWidget(self.settings_gridgen_version_combo, 0, 1)

            # DX
            dx_label = QLabel(tr("default_dx", "默认普通网格DX:"))
            self.settings_dx_edit = LineEdit()
            self.settings_dx_edit.setText(current_config.get("DX", ""))
            self.settings_dx_edit.setStyleSheet(input_style)
            grid_params_layout.addWidget(dx_label, 1, 0)
            grid_params_layout.addWidget(self.settings_dx_edit, 1, 1)

            # DY
            dy_label = QLabel(tr("default_dy", "默认普通网格DY:"))
            self.settings_dy_edit = LineEdit()
            self.settings_dy_edit.setText(current_config.get("DY", ""))
            self.settings_dy_edit.setStyleSheet(input_style)
            grid_params_layout.addWidget(dy_label, 2, 0)
            grid_params_layout.addWidget(self.settings_dy_edit, 2, 1)

            # 嵌套收缩系数
            nested_coeff_label = QLabel(tr("nested_coeff", "嵌套网格收缩系数:"))
            self.settings_nested_coeff_edit = LineEdit()
            self.settings_nested_coeff_edit.setText(current_config.get("NESTED_CONTRACTION_COEFFICIENT", "3"))
            self.settings_nested_coeff_edit.setStyleSheet(input_style)
            self.settings_nested_coeff_edit.setPlaceholderText(tr("nested_coeff_recommended", "推荐 3 或 2"))
            grid_params_layout.addWidget(nested_coeff_label, 3, 0)
            grid_params_layout.addWidget(self.settings_nested_coeff_edit, 3, 1)

            # 默认嵌套外网格 DX
            nested_outer_dx_label = QLabel(tr("nested_outer_dx", "默认嵌套外网格DX:"))
            self.settings_nested_outer_dx_edit = LineEdit()
            self.settings_nested_outer_dx_edit.setText(current_config.get("NESTED_OUTER_DX", "0.05"))
            self.settings_nested_outer_dx_edit.setStyleSheet(input_style)
            grid_params_layout.addWidget(nested_outer_dx_label, 4, 0)
            grid_params_layout.addWidget(self.settings_nested_outer_dx_edit, 4, 1)

            # 默认嵌套外网格 DY
            nested_outer_dy_label = QLabel(tr("nested_outer_dy", "默认嵌套外网格DY:"))
            self.settings_nested_outer_dy_edit = LineEdit()
            self.settings_nested_outer_dy_edit.setText(current_config.get("NESTED_OUTER_DY", "0.05"))
            self.settings_nested_outer_dy_edit.setStyleSheet(input_style)
            grid_params_layout.addWidget(nested_outer_dy_label, 5, 0)
            grid_params_layout.addWidget(self.settings_nested_outer_dy_edit, 5, 1)

            # 水深数据
            bathymetry_label = QLabel(tr("bathymetry", "水深数据:"))
            self.settings_bathymetry_combo = ComboBox()
            self.settings_bathymetry_combo.addItems(["GEBCO", "ETOP1", "ETOP2"])
            current_bathymetry = current_config.get("BATHYMETRY", "GEBCO")
            index = self.settings_bathymetry_combo.findText(current_bathymetry)
            if index >= 0:
                self.settings_bathymetry_combo.setCurrentIndex(index)
            else:
                self.settings_bathymetry_combo.setCurrentIndex(0)
            self.settings_bathymetry_combo.setStyleSheet(combo_style)
            grid_params_layout.addWidget(bathymetry_label, 6, 0)
            grid_params_layout.addWidget(self.settings_bathymetry_combo, 6, 1)

            # 海岸边界精度
            coastline_label = QLabel(tr("coastline_precision", "海岸边界精度:"))
            self.settings_coastline_combo = ComboBox()
            self.settings_coastline_combo.addItems([
                tr("coastline_highest", "最高"),
                tr("coastline_high", "高"),
                tr("coastline_medium", "中"),
                tr("coastline_low", "低"),
                tr("coastline_coarse", "粗")
            ])
            # 获取当前语言下的默认值
            default_coastline = tr("coastline_highest", "最高")
            # 从配置读取的值可能是中文或英文，需要匹配当前语言的选项
            saved_coastline = current_config.get("COASTLINE_PRECISION", "")
            
            # 如果保存的值是中文，需要转换为当前语言的对应值
            # 中文到索引的映射：最高=0, 高=1, 中=2, 低=3
            coastline_map_zh = {
                tr("coastline_highest", "最高"): 0,
                tr("coastline_high", "高"): 1,
                tr("coastline_medium", "中"): 2,
                tr("coastline_low", "低"): 3,
                tr("coastline_coarse", "粗"): 4
            }
            coastline_map_en = {
                "Highest": 0,
                "High": 1,
                "Medium": 2,
                "Low": 3,
                "Coarse": 4
            }
            coastline_map_code = {
                "full": 0,
                "high": 1,
                "inter": 2,
                "low": 3,
                "coarse": 4
            }
            
            if saved_coastline in coastline_map_code:
                index = coastline_map_code[saved_coastline]
                self.settings_coastline_combo.setCurrentIndex(index)
            elif saved_coastline in coastline_map_zh:
                # 保存的是中文，直接使用索引
                index = coastline_map_zh[saved_coastline]
                self.settings_coastline_combo.setCurrentIndex(index)
            elif saved_coastline in coastline_map_en:
                # 保存的是英文，直接使用索引
                index = coastline_map_en[saved_coastline]
                self.settings_coastline_combo.setCurrentIndex(index)
            else:
                # 尝试通过文本查找（可能已经切换了语言）
                index = self.settings_coastline_combo.findText(saved_coastline)
                if index >= 0:
                    self.settings_coastline_combo.setCurrentIndex(index)
                else:
                    # 如果找不到，默认选择第一个（最高）
                    self.settings_coastline_combo.setCurrentIndex(0)
            self.settings_coastline_combo.setStyleSheet(combo_style)
            grid_params_layout.addWidget(coastline_label, 7, 0)
            grid_params_layout.addWidget(self.settings_coastline_combo, 7, 1)

            grid_card_layout.addLayout(grid_params_layout)

            grid_card.viewLayout.setContentsMargins(11, 10, 11, 12)
            grid_card.viewLayout.addLayout(grid_card_layout)
            settings_layout.addWidget(grid_card)

            # === 非结构化三角网格（unstructured_generator/grid.json）===
            unst_mesh_card = HeaderCardWidget(settings_content)
            self.unst_mesh_card = unst_mesh_card
            unst_mesh_card.setTitle(tr("unst_mesh_config_card", "非结构化三角网格配置"))
            unst_mesh_card.setStyleSheet("""
                HeaderCardWidget QLabel {
                    font-weight: normal;
                    margin-left: 0px;
                    padding-left: 0px;
                }
            """)
            unst_mesh_card.headerLayout.setContentsMargins(11, 10, 11, 12)
            unst_mesh_layout = QVBoxLayout()
            unst_mesh_layout.setSpacing(5)
            unst_mesh_layout.setContentsMargins(0, 0, 0, 0)
            unst_grid = QGridLayout()
            unst_grid.setColumnStretch(1, 1)
            unst_grid.setSpacing(5)

            unst_cfg = load_unst_msh_gen_config()
            sp = unst_cfg.get("spacing", {})
            reg = unst_cfg.get("regional", {})
            d0 = UNST_MSH_GEN_CONFIG_DEFAULTS

            def _row(line: int, label_widget, edit_widget, col_span_edit=1):
                unst_grid.addWidget(label_widget, line, 0)
                unst_grid.addWidget(edit_widget, line, 1, 1, col_span_edit)

            self.unst_l_spacing_hmax = QLabel(tr("unst_spacing_hmax", "深水尺度（km）:"))
            self.settings_unst_spacing_hmax_edit = LineEdit()
            self.settings_unst_spacing_hmax_edit.setText(str(sp.get("hmax", d0["spacing"]["hmax"])))
            self.settings_unst_spacing_hmax_edit.setStyleSheet(input_style)
            _row(0, self.unst_l_spacing_hmax, self.settings_unst_spacing_hmax_edit)

            self.unst_l_spacing_hshr = QLabel(tr("unst_spacing_hshr", "近岸尺度（km）:"))
            self.settings_unst_spacing_hshr_edit = LineEdit()
            self.settings_unst_spacing_hshr_edit.setText(str(sp.get("hshr", d0["spacing"]["hshr"])))
            self.settings_unst_spacing_hshr_edit.setStyleSheet(input_style)
            _row(1, self.unst_l_spacing_hshr, self.settings_unst_spacing_hshr_edit)

            self.unst_l_spacing_dhdx = QLabel(tr("unst_spacing_dhdx", "水深梯度:"))
            self.settings_unst_spacing_dhdx_edit = LineEdit()
            self.settings_unst_spacing_dhdx_edit.setText(str(sp.get("dhdx", d0["spacing"]["dhdx"])))
            self.settings_unst_spacing_dhdx_edit.setStyleSheet(input_style)
            _row(2, self.unst_l_spacing_dhdx, self.settings_unst_spacing_dhdx_edit)

            self.unst_l_spacing_nwav = QLabel(tr("unst_spacing_nwav", "浅水按波长加密:"))
            self.settings_unst_spacing_nwav_edit = LineEdit()
            self.settings_unst_spacing_nwav_edit.setText(str(sp.get("nwav", d0["spacing"]["nwav"])))
            self.settings_unst_spacing_nwav_edit.setStyleSheet(input_style)
            _row(3, self.unst_l_spacing_nwav, self.settings_unst_spacing_nwav_edit)

            self.unst_l_spacing_deep_threshold = QLabel(
                tr("unst_spacing_deep_threshold", "深水阈值（m）:")
            )
            self.settings_unst_spacing_deep_threshold_edit = LineEdit()
            self.settings_unst_spacing_deep_threshold_edit.setText(
                str(sp.get("deep_ocean_threshold_m", d0["spacing"]["deep_ocean_threshold_m"]))
            )
            self.settings_unst_spacing_deep_threshold_edit.setStyleSheet(input_style)
            _row(4, self.unst_l_spacing_deep_threshold, self.settings_unst_spacing_deep_threshold_edit)

            self.unst_l_reg_margin = QLabel(tr("unst_regional_margin_deg", "区域外扩边距（度）:"))
            self.settings_unst_regional_margin_deg_edit = LineEdit()
            self.settings_unst_regional_margin_deg_edit.setText(str(reg.get("margin_deg", d0["regional"]["margin_deg"])))
            self.settings_unst_regional_margin_deg_edit.setStyleSheet(input_style)
            _row(5, self.unst_l_reg_margin, self.settings_unst_regional_margin_deg_edit)

            self.unst_l_reg_edge_seg = QLabel(tr("unst_regional_edge_segments", "矩形边界折线段数:"))
            self.settings_unst_regional_edge_segments_edit = LineEdit()
            self.settings_unst_regional_edge_segments_edit.setText(str(reg.get("edge_segments", d0["regional"]["edge_segments"])))
            self.settings_unst_regional_edge_segments_edit.setStyleSheet(input_style)
            _row(6, self.unst_l_reg_edge_seg, self.settings_unst_regional_edge_segments_edit)

            unst_mesh_layout.addLayout(unst_grid)

            unst_mesh_card.viewLayout.setContentsMargins(11, 10, 11, 12)
            unst_mesh_card.viewLayout.addLayout(unst_mesh_layout)
            settings_layout.addWidget(unst_mesh_card)

            # === SMC 网格（smc_generator/grid.json）===
            smc_mesh_card = HeaderCardWidget(settings_content)
            self.smc_mesh_card = smc_mesh_card
            smc_mesh_card.setTitle(tr("settings_smc_config_card", "SMC 网格配置"))
            smc_mesh_card.setStyleSheet("""
                HeaderCardWidget QLabel {
                    font-weight: normal;
                    margin-left: 0px;
                    padding-left: 0px;
                }
            """)
            smc_mesh_card.headerLayout.setContentsMargins(11, 10, 11, 12)
            smc_mesh_layout = QVBoxLayout()
            smc_mesh_layout.setSpacing(5)
            smc_mesh_layout.setContentsMargins(0, 0, 0, 0)
            smc_gr = QGridLayout()
            smc_gr.setColumnStretch(1, 1)
            smc_gr.setSpacing(5)

            smc_cfg = load_smc_grid_json_for_settings()
            sinp = smc_cfg.get("input") or {}
            sgr = smc_cfg.get("grid") or {}
            sphy = smc_cfg.get("physics") or {}
            sbnd = smc_cfg.get("boundary") or {}

            def _smc_row(line: int, label_widget, field_widget, col_span=1):
                smc_gr.addWidget(label_widget, line, 0)
                smc_gr.addWidget(field_widget, line, 1, 1, col_span)

            _sr = 0
            self.settings_smc_l_bathy_file = QLabel(tr("settings_smc_bathy_file", "水深数据:"))
            self.settings_smc_bathy_combo = ComboBox()
            self.settings_smc_bathy_combo.addItems(
                [
                    tr("settings_smc_bathy_etopo1", "ETOPO1"),
                    tr("settings_smc_bathy_etopo2", "ETOPO2"),
                    tr("settings_smc_bathy_gebco", "GEBCO"),
                ]
            )
            self.settings_smc_bathy_combo.setCurrentIndex(
                smc_bathymetry_combo_index_from_path(sinp.get("bathymetry_file"))
            )
            self.settings_smc_bathy_combo.setToolTip(
                tr(
                    "settings_smc_bathy_tip",
                    "数据来自 reference_data；保存后 grid.json 内为相对 smc_generator 的路径。",
                )
            )
            self.settings_smc_bathy_combo.setStyleSheet(combo_style)
            _smc_row(_sr, self.settings_smc_l_bathy_file, self.settings_smc_bathy_combo)
            _sr += 1

            self.settings_smc_l_convention = QLabel(tr("settings_smc_bathy_convention", "水深约定:"))
            self.settings_smc_convention_combo = ComboBox()
            self.settings_smc_convention_combo.addItems(
                [
                    tr("settings_smc_convention_elevation", "高程（海面向下为正）"),
                    tr("settings_smc_convention_depth", "水深（向下为正）"),
                ]
            )
            _bc = str(sinp.get("bathy_convention", "elevation")).lower()
            self.settings_smc_convention_combo.setCurrentIndex(
                1 if _bc in ("depth", "depth_positive_down", "positive_down") else 0
            )
            self.settings_smc_convention_combo.setStyleSheet(combo_style)
            _smc_row(_sr, self.settings_smc_l_convention, self.settings_smc_convention_combo)
            _sr += 1

            self.settings_smc_l_n_levels = QLabel(tr("settings_smc_n_levels", "细化层数:"))
            self.settings_smc_n_levels_edit = LineEdit()
            self.settings_smc_n_levels_edit.setText(str(sgr.get("n_levels", 2)))
            self.settings_smc_n_levels_edit.setStyleSheet(input_style)
            _smc_row(_sr, self.settings_smc_l_n_levels, self.settings_smc_n_levels_edit)
            _sr += 1

            self.settings_smc_l_wlevel = QLabel(tr("settings_smc_wlevel", "参考水位:"))
            self.settings_smc_wlevel_edit = LineEdit()
            self.settings_smc_wlevel_edit.setText(str(sphy.get("wlevel", 0.0)))
            self.settings_smc_wlevel_edit.setStyleSheet(input_style)
            _smc_row(_sr, self.settings_smc_l_wlevel, self.settings_smc_wlevel_edit)
            _sr += 1

            self.settings_smc_l_depmin = QLabel(tr("settings_smc_depmin", "最小水深:"))
            self.settings_smc_depmin_edit = LineEdit()
            self.settings_smc_depmin_edit.setText(str(sphy.get("depmin", 0.0)))
            self.settings_smc_depmin_edit.setStyleSheet(input_style)
            _smc_row(_sr, self.settings_smc_l_depmin, self.settings_smc_depmin_edit)
            _sr += 1

            self.settings_smc_l_dshalw = QLabel(tr("settings_smc_dshalw", "浅水截断:"))
            self.settings_smc_dshalw_edit = LineEdit()
            self.settings_smc_dshalw_edit.setText(str(sphy.get("dshalw", -150.0)))
            self.settings_smc_dshalw_edit.setStyleSheet(input_style)
            _smc_row(_sr, self.settings_smc_l_dshalw, self.settings_smc_dshalw_edit)
            _sr += 1

            self.settings_smc_l_boundary = QLabel(tr("settings_smc_boundary", "开边界:"))
            if SwitchButton is not None:
                self.settings_smc_boundary_generate_switch = SwitchButton()
                self.settings_smc_boundary_generate_switch.setSpacing(0)
                self.settings_smc_boundary_generate_switch.setChecked(
                    bool(sbnd.get("generate_boundary_cells", True))
                )
                self.settings_smc_boundary_generate_switch.setOnText("")
                self.settings_smc_boundary_generate_switch.setOffText("")
            else:
                self.settings_smc_boundary_generate_switch = QtWidgets.QCheckBox()
                self.settings_smc_boundary_generate_switch.setChecked(
                    bool(sbnd.get("generate_boundary_cells", True))
                )
            if SwitchButton is not None:
                self.settings_smc_boundary_generate_switch.setStyleSheet("""
                    SwitchButton {
                        margin: 0px !important;
                        margin-right: 5px !important;
                        padding: 0px !important;
                        padding-right: 0px !important;
                        max-width: none;
                    }
                """)
            _smc_row(_sr, self.settings_smc_l_boundary, self.settings_smc_boundary_generate_switch)
            _sr += 1

            self.settings_smc_l_msea = QLabel(tr("settings_smc_msea", "海陆类型:"))
            self.settings_smc_msea_edit = LineEdit()
            self.settings_smc_msea_edit.setText(str(sbnd.get("msea", 1)))
            self.settings_smc_msea_edit.setStyleSheet(input_style)
            _smc_row(_sr, self.settings_smc_l_msea, self.settings_smc_msea_edit)

            smc_mesh_layout.addLayout(smc_gr)
            smc_mesh_card.viewLayout.setContentsMargins(11, 10, 11, 12)
            smc_mesh_card.viewLayout.addLayout(smc_mesh_layout)
            settings_layout.addWidget(smc_mesh_card)

            # === Slurm 配置 ===
            compute_card = HeaderCardWidget(settings_content)
            compute_card.setTitle(tr("slurm_config", "Slurm 配置"))
            compute_card.setStyleSheet("""
                HeaderCardWidget QLabel {
                    font-weight: normal;
                    margin-left: 0px;
                    padding-left: 0px;
                }
            """)
            compute_card.headerLayout.setContentsMargins(11, 10, 11, 12)
            compute_card_layout = QVBoxLayout()
            compute_card_layout.setSpacing(5)
            compute_card_layout.setContentsMargins(0, 0, 0, 0)

            # 使用网格布局确保输入框左右对齐
            compute_params_layout = QGridLayout()
            compute_params_layout.setColumnStretch(1, 1)  # 让输入框列可以拉伸，但不固定宽度
            compute_params_layout.setSpacing(5)

            # 核数
            kernel_label = QLabel(tr("default_kernel", "默认核数:"))
            self.settings_kernel_edit = LineEdit()
            self.settings_kernel_edit.setText(current_config.get("KERNEL_NUM", ""))
            self.settings_kernel_edit.setStyleSheet(input_style)
            compute_params_layout.addWidget(kernel_label, 0, 0)
            compute_params_layout.addWidget(self.settings_kernel_edit, 0, 1)

            # 节点数
            node_label = QLabel(tr("default_node", "默认节点数:"))
            self.settings_node_edit = LineEdit()
            self.settings_node_edit.setText(current_config.get("NODE_NUM", ""))
            self.settings_node_edit.setStyleSheet(input_style)
            compute_params_layout.addWidget(node_label, 1, 0)
            compute_params_layout.addWidget(self.settings_node_edit, 1, 1)

            compute_card_layout.addLayout(compute_params_layout)

            # CPU 管理按钮
            self.settings_cpu_manage_button = PrimaryPushButton(tr("cpu_manage", "CPU 管理"))
            self.settings_cpu_manage_button.clicked.connect(self._manage_cpu_group)
            self.settings_cpu_manage_button.setStyleSheet(button_style)
            compute_card_layout.addWidget(self.settings_cpu_manage_button)

            compute_card.viewLayout.setContentsMargins(11, 10, 11, 12)
            compute_card.viewLayout.addLayout(compute_card_layout)
            settings_layout.addWidget(compute_card)

            # === WW3 配置 ===
            ww3_config_card = HeaderCardWidget(settings_content)
            ww3_config_card.setTitle(tr("ww3_config_card", "WW3 配置"))
            ww3_config_card.setStyleSheet("""
                HeaderCardWidget QLabel {
                    font-weight: normal;
                    margin-left: 0px;
                    padding-left: 0px;
                }
            """)
            ww3_config_card.headerLayout.setContentsMargins(11, 10, 11, 12)
            ww3_config_card_layout = QVBoxLayout()
            ww3_config_card_layout.setSpacing(5)
            ww3_config_card_layout.setContentsMargins(0, 0, 0, 0)

            ww3_config_layout = QGridLayout()
            ww3_config_layout.setColumnStretch(1, 1)
            ww3_config_layout.setSpacing(5)

            # 计算精度
            compute_prec_label = QLabel(tr("default_compute_precision", "默认计算精度:"))
            self.settings_compute_precision_edit = LineEdit()
            self.settings_compute_precision_edit.setText(current_config.get("COMPUTE_PRECISION", ""))
            self.settings_compute_precision_edit.setStyleSheet(input_style)
            ww3_config_layout.addWidget(compute_prec_label, 0, 0)
            ww3_config_layout.addWidget(self.settings_compute_precision_edit, 0, 1)

            # 输出精度
            output_prec_label = QLabel(tr("default_output_precision", "默认输出精度:"))
            self.settings_output_precision_edit = LineEdit()
            self.settings_output_precision_edit.setText(current_config.get("OUTPUT_PRECISION", ""))
            self.settings_output_precision_edit.setStyleSheet(input_style)
            ww3_config_layout.addWidget(output_prec_label, 1, 0)
            ww3_config_layout.addWidget(self.settings_output_precision_edit, 1, 1)

            # 文件分割
            file_split_label = QLabel(tr("file_split", "文件分割:"))
            self.settings_file_split_combo = ComboBox()
            self.settings_file_split_combo.addItems([
                tr("file_split_none", "无日期"),
                tr("file_split_hour", "小时"),
                tr("file_split_day", "天"),
                tr("file_split_month", "月"),
                tr("file_split_year", "年")
            ])
            saved_file_split = current_config.get("FILE_SPLIT", "")
            # 文件分割映射：无日期=0, 小时=1, 天=2, 月=3, 年=4
            # 对应的值：0(无日期), 10(小时), 8(日), 6(月), 4(年)
            file_split_map_zh = {
                tr("file_split_none", "无日期"): 0,
                tr("file_split_hour", "小时"): 1,
                tr("file_split_day", "天"): 2,
                tr("file_split_month", "月"): 3,
                tr("file_split_year", "年"): 4
            }
            file_split_map_en = {"None": 0, "Hour": 1, "Day": 2, "Month": 3, "Year": 4}
            file_split_map_num = {"0": 0, "10": 1, "8": 2, "6": 3, "4": 4}
            
            if saved_file_split in file_split_map_zh:
                index = file_split_map_zh[saved_file_split]
                self.settings_file_split_combo.setCurrentIndex(index)
            elif saved_file_split in file_split_map_en:
                index = file_split_map_en[saved_file_split]
                self.settings_file_split_combo.setCurrentIndex(index)
            elif isinstance(saved_file_split, (int, float)) and str(int(saved_file_split)) in file_split_map_num:
                self.settings_file_split_combo.setCurrentIndex(file_split_map_num[str(int(saved_file_split))])
            elif isinstance(saved_file_split, str) and saved_file_split in file_split_map_num:
                self.settings_file_split_combo.setCurrentIndex(file_split_map_num[saved_file_split])
            else:
                # 尝试通过文本查找
                index = self.settings_file_split_combo.findText(saved_file_split)
                if index >= 0:
                    self.settings_file_split_combo.setCurrentIndex(index)
                else:
                    # 默认选择年（索引4）
                    self.settings_file_split_combo.setCurrentIndex(4)
            self.settings_file_split_combo.setStyleSheet(combo_style)
            ww3_config_layout.addWidget(file_split_label, 2, 0)
            ww3_config_layout.addWidget(self.settings_file_split_combo, 2, 1)
            self.settings_file_split_combo.currentIndexChanged.connect(self._on_file_split_changed)

            ww3_config_card_layout.addLayout(ww3_config_layout)
            ww3_config_card.viewLayout.setContentsMargins(11, 10, 11, 12)
            ww3_config_card.viewLayout.addLayout(ww3_config_card_layout)
            settings_layout.addWidget(ww3_config_card)

            # === 频谱参数设置 ===
            spectrum_card = HeaderCardWidget(settings_content)
            spectrum_card.setTitle(tr("spectrum_config", "频谱参数"))
            spectrum_card.setStyleSheet("""
                HeaderCardWidget QLabel {
                    font-weight: normal;
                    margin-left: 0px;
                    padding-left: 0px;
                }
            """)
            spectrum_card.headerLayout.setContentsMargins(11, 10, 11, 12)
            spectrum_card_layout = QVBoxLayout()
            spectrum_card_layout.setSpacing(5)
            spectrum_card_layout.setContentsMargins(0, 0, 0, 0)

            # 使用网格布局确保输入框左右对齐
            spectrum_params_layout = QGridLayout()
            spectrum_params_layout.setColumnStretch(1, 1)  # 让输入框列可以拉伸，但不固定宽度
            spectrum_params_layout.setSpacing(5)

            # 先从 ww3_grid.nml 读取频谱参数，如果读取不到则使用 config.json 的默认值
            spectrum_params = self._read_spectrum_from_nml()
            if spectrum_params is None:
                # 如果读取不到，使用 config.json 的默认值
                spectrum_params = {
                    "FREQ_INC": current_config.get("FREQ_INC", "1.1"),
                    "FREQ_START": current_config.get("FREQ_START", "0.04118"),
                    "FREQ_NUM": current_config.get("FREQ_NUM", "32"),
                    "DIR_NUM": current_config.get("DIR_NUM", "24"),
                }

            # 频率增量
            freq_inc_label = QLabel(tr("freq_inc", "频率增量:"))
            self.settings_freq_inc_edit = LineEdit()
            self.settings_freq_inc_edit.setText(spectrum_params.get("FREQ_INC", "1.1"))
            self.settings_freq_inc_edit.setStyleSheet(input_style)
            spectrum_params_layout.addWidget(freq_inc_label, 0, 0)
            spectrum_params_layout.addWidget(self.settings_freq_inc_edit, 0, 1)

            # 起始频率
            freq_start_label = QLabel(tr("freq_start", "起始频率:"))
            self.settings_freq_start_edit = LineEdit()
            self.settings_freq_start_edit.setText(spectrum_params.get("FREQ_START", "0.04118"))
            self.settings_freq_start_edit.setStyleSheet(input_style)
            spectrum_params_layout.addWidget(freq_start_label, 1, 0)
            spectrum_params_layout.addWidget(self.settings_freq_start_edit, 1, 1)

            # 频率数量
            freq_num_label = QLabel(tr("freq_num", "频率数量:"))
            self.settings_freq_num_edit = LineEdit()
            self.settings_freq_num_edit.setText(spectrum_params.get("FREQ_NUM", "32"))
            self.settings_freq_num_edit.setStyleSheet(input_style)
            spectrum_params_layout.addWidget(freq_num_label, 2, 0)
            spectrum_params_layout.addWidget(self.settings_freq_num_edit, 2, 1)

            # 方向离散数
            dir_num_label = QLabel(tr("direction_discrete", "方向离散数:"))
            self.settings_dir_num_edit = LineEdit()
            self.settings_dir_num_edit.setText(spectrum_params.get("DIR_NUM", "24"))
            self.settings_dir_num_edit.setStyleSheet(input_style)
            spectrum_params_layout.addWidget(dir_num_label, 3, 0)
            spectrum_params_layout.addWidget(self.settings_dir_num_edit, 3, 1)

            spectrum_card_layout.addLayout(spectrum_params_layout)

            # 恢复默认值按钮
            reset_spectrum_button = PrimaryPushButton(tr("reset_defaults", "恢复默认值"))
            reset_spectrum_button.setStyleSheet(button_style)
            reset_spectrum_button.clicked.connect(self._reset_spectrum_defaults)
            spectrum_card_layout.addWidget(reset_spectrum_button)

            spectrum_card.viewLayout.setContentsMargins(11, 10, 11, 12)
            spectrum_card.viewLayout.addLayout(spectrum_card_layout)
            settings_layout.addWidget(spectrum_card)

            # === 数值积分时间步长参数设置 ===
            timesteps_card = HeaderCardWidget(settings_content)
            timesteps_card.setTitle(tr("timesteps_params", "数值积分时间步长参数"))
            timesteps_card.setStyleSheet("""
                HeaderCardWidget QLabel {
                    font-weight: normal;
                    margin-left: 0px;
                    padding-left: 0px;
                }
            """)
            timesteps_card.headerLayout.setContentsMargins(11, 10, 11, 12)
            timesteps_card_layout = QVBoxLayout()
            timesteps_card_layout.setSpacing(5)
            timesteps_card_layout.setContentsMargins(0, 0, 0, 0)

            # 使用网格布局确保输入框左右对齐
            timesteps_params_layout = QGridLayout()
            timesteps_params_layout.setColumnStretch(1, 1)  # 让输入框列可以拉伸，但不固定宽度
            timesteps_params_layout.setSpacing(5)

            # 最大全局时间步长
            dtmax_label = QLabel(tr("max_global_timestep", "最大全局时间步长:"))
            self.settings_dtmax_edit = LineEdit()
            self.settings_dtmax_edit.setText(current_config.get("DTMAX", "900"))
            self.settings_dtmax_edit.setStyleSheet(input_style)
            timesteps_params_layout.addWidget(dtmax_label, 0, 0)
            timesteps_params_layout.addWidget(self.settings_dtmax_edit, 0, 1)

            # x-y方向最大CFL时间步长
            dtxy_label = QLabel(tr("spatial_timestep", "空间时间步长:"))
            self.settings_dtxy_edit = LineEdit()
            self.settings_dtxy_edit.setText(current_config.get("DTXY", "320"))
            self.settings_dtxy_edit.setStyleSheet(input_style)
            timesteps_params_layout.addWidget(dtxy_label, 1, 0)
            timesteps_params_layout.addWidget(self.settings_dtxy_edit, 1, 1)

            # k-th方向最大CFL时间步长
            dtkth_label = QLabel(tr("spectral_timestep", "谱空间时间步长:"))
            self.settings_dtkth_edit = LineEdit()
            self.settings_dtkth_edit.setText(current_config.get("DTKTH", "300"))
            self.settings_dtkth_edit.setStyleSheet(input_style)
            timesteps_params_layout.addWidget(dtkth_label, 2, 0)
            timesteps_params_layout.addWidget(self.settings_dtkth_edit, 2, 1)

            # 最小源项时间步长
            dtmin_label = QLabel(tr("min_source_timestep", "最小源项时间步长:"))
            self.settings_dtmin_edit = LineEdit()
            self.settings_dtmin_edit.setText(current_config.get("DTMIN", "15"))
            self.settings_dtmin_edit.setStyleSheet(input_style)
            timesteps_params_layout.addWidget(dtmin_label, 3, 0)
            timesteps_params_layout.addWidget(self.settings_dtmin_edit, 3, 1)

            timesteps_card_layout.addLayout(timesteps_params_layout)

            # 恢复默认值按钮
            reset_timesteps_button = PrimaryPushButton(tr("reset_defaults", "恢复默认值"))
            reset_timesteps_button.setStyleSheet(button_style)
            reset_timesteps_button.clicked.connect(self._reset_timesteps_defaults)
            timesteps_card_layout.addWidget(reset_timesteps_button)

            timesteps_card.viewLayout.setContentsMargins(11, 10, 11, 12)
            timesteps_card.viewLayout.addLayout(timesteps_card_layout)
            settings_layout.addWidget(timesteps_card)

            # === 近岸配置 ===
            nearshore_card = HeaderCardWidget(settings_content)
            nearshore_card.setTitle(tr("nearshore_config", "近岸配置"))
            nearshore_card.setStyleSheet("""
                HeaderCardWidget QLabel {
                    font-weight: normal;
                    margin-left: 0px;
                    padding-left: 0px;
                }
            """)
            nearshore_card.headerLayout.setContentsMargins(11, 10, 11, 12)
            nearshore_card_layout = QVBoxLayout()
            nearshore_card_layout.setSpacing(5)
            nearshore_card_layout.setContentsMargins(0, 0, 0, 0)

            # 使用网格布局确保输入框左右对齐
            nearshore_params_layout = QGridLayout()
            nearshore_params_layout.setColumnStretch(1, 1)  # 让输入框列可以拉伸，但不固定宽度
            nearshore_params_layout.setSpacing(5)

            # 先从 ww3_grid.nml 读取近岸配置参数，如果读取不到则使用 config.json 的默认值
            nearshore_params = self._read_nearshore_from_nml()
            if nearshore_params is None:
                # 如果读取不到，使用 config.json 的默认值
                nearshore_params = {
                    "GRID_ZLIM": current_config.get("GRID_ZLIM", "-0.1"),
                    "GRID_DMIN": current_config.get("GRID_DMIN", "2.5"),
                }

            # 海岸线限制深度
            zlim_label = QLabel(tr("coastline_limit_depth", "海岸线限制深度 (米):"))
            self.settings_zlim_edit = LineEdit()
            self.settings_zlim_edit.setText(nearshore_params.get("GRID_ZLIM", "-0.1"))
            self.settings_zlim_edit.setStyleSheet(input_style)
            nearshore_params_layout.addWidget(zlim_label, 0, 0)
            nearshore_params_layout.addWidget(self.settings_zlim_edit, 0, 1)

            # 绝对最小水深
            dmin_label = QLabel(tr("min_water_depth", "绝对最小水深 (米):"))
            self.settings_dmin_edit = LineEdit()
            self.settings_dmin_edit.setText(nearshore_params.get("GRID_DMIN", "2.5"))
            self.settings_dmin_edit.setStyleSheet(input_style)
            nearshore_params_layout.addWidget(dmin_label, 1, 0)
            nearshore_params_layout.addWidget(self.settings_dmin_edit, 1, 1)

            nearshore_card_layout.addLayout(nearshore_params_layout)

            # 恢复默认值按钮
            reset_nearshore_button = PrimaryPushButton(tr("reset_defaults", "恢复默认值"))
            reset_nearshore_button.setStyleSheet(button_style)
            reset_nearshore_button.clicked.connect(self._reset_nearshore_defaults)
            nearshore_card_layout.addWidget(reset_nearshore_button)

            nearshore_card.viewLayout.setContentsMargins(11, 10, 11, 12)
            nearshore_card.viewLayout.addLayout(nearshore_card_layout)
            settings_layout.addWidget(nearshore_card)

            # === 谱分区输出 ===
            spectral_output_card = HeaderCardWidget(settings_content)
            spectral_output_card.setTitle(tr("spectral_output_title", "谱分区输出"))
            
            spectral_output_card.headerLayout.setContentsMargins(11, 10, 11, 12)
            spectral_output_card_layout = QVBoxLayout()
            spectral_output_card_layout.setContentsMargins(0, 0, 0, 0)

            # 定义变量选项（变量名, 显示名称）
            # 按分组组织变量
            output_vars_options = [
                # 1. 强迫场 (Forcing)
                ("DPT", tr("var_dpt", "水深 (DPT)")),
                ("CUR", tr("var_cur", "海流 (CUR)")),
                ("WND", tr("var_wnd", "风速 (WND)")),
                ("AST", tr("var_ast", "海气温差 (AST)")),
                ("WLV", tr("var_wlv", "水位 (WLV)")),
                ("ICE", tr("var_ice", "冰浓度 (ICE)")),
                ("IBG", tr("var_ibg", "冰山阻尼 (IBG)")),
                ("D50", tr("var_d50", "泥沙粒径 (D50)")),
                ("IC1", tr("var_ic1", "冰厚度 (IC1)")),
                ("IC5", tr("var_ic5", "碎冰直径 (IC5)")),
                # 2. 标准参数 (Standard)
                ("HS", tr("var_hs", "有效波高 (HS)")),
                ("LM", tr("var_lm", "平均波长 (LM)")),
                ("T02", tr("var_t02", "平均周期 (T02)")),
                ("T0M1", tr("var_t0m1", "平均周期 (T0M1)")),
                ("T01", tr("var_t01", "平均周期 (T01)")),
                ("FP", tr("var_fp", "峰值频率 (FP)")),
                ("DIR", tr("var_dir", "平均波向 (DIR)")),
                ("SPR", tr("var_spr", "方向散布 (SPR)")),
                ("DP", tr("var_dp", "峰值波向 (DP)")),
                ("HIG", tr("var_hig", "次重力波高 (HIG)")),
                # 3. 谱参数 (Spectral)
                ("EF", tr("var_ef", "频率谱 (EF)")),
                ("TH1M", tr("var_th1m", "平均方向 (TH1M)")),
                ("STH1M", tr("var_sth1m", "方向分布 (STH1M)")),
                ("TH2M", tr("var_th2m", "平均方向 (TH2M)")),
                ("STH2M", tr("var_sth2m", "方向分布 (STH2M)")),
                ("WN", tr("var_wn", "波数 (WN)")),
                # 4. 谱分区 (Partition)
                ("PHS", tr("var_phs", "分区波高 (PHS)")),
                ("PTP", tr("var_ptp", "分区峰值周期 (PTP)")),
                ("PLP", tr("var_plp", "分区波长 (PLP)")),
                ("PDIR", tr("var_pdir", "分区平均波向 (PDIR)")),
                ("PSPR", tr("var_pspr", "分区方向分布 (PSPR)")),
                ("PWS", tr("var_pws", "分区风海分数 (PWS)")),
                ("PDP", tr("var_pdp", "分区峰值波向 (PDP)")),
                ("PQP", tr("var_pqp", "分区Goda参数 (PQP)")),
                ("PPE", tr("var_ppe", "分区增强因子 (PPE)")),
                ("PGW", tr("var_pgw", "分区频率宽度 (PGW)")),
                ("PSW", tr("var_psw", "分区谱宽度 (PSW)")),
                ("PTM10", tr("var_ptm10", "分区能量周期 (PTM10)")),
                ("PT01", tr("var_pt01", "分区周期 (PT01)")),
                ("PT02", tr("var_pt02", "分区周期 (PT02)")),
                ("PEP", tr("var_pep", "分区峰值密度 (PEP)")),
                ("TWS", tr("var_tws", "总风海分数 (TWS)")),
                ("PNR", tr("var_pnr", "分区数量 (PNR)")),
                # 5. 大气交互 (Air-Sea)
                ("UST", tr("var_ust", "摩擦速度 (UST)")),
                ("CHA", tr("var_cha", "Charnock参数 (CHA)")),
                ("CGE", tr("var_cge", "能量通量 (CGE)")),
                ("FAW", tr("var_faw", "海气能量通量 (FAW)")),
                ("TAW", tr("var_taw", "净波浪应力 (TAW)")),
                ("TWA", tr("var_twa", "负向波浪应力 (TWA)")),
                ("WCC", tr("var_wcc", "白帽覆盖率 (WCC)")),
                ("WCF", tr("var_wcf", "白帽厚度 (WCF)")),
                ("WCH", tr("var_wch", "平均破碎高度 (WCH)")),
                ("WCM", tr("var_wcm", "白帽动量 (WCM)")),
                ("FWS", tr("var_fws", "风海平均周期 (FWS)")),
                # 6. 海洋交互 (Ocean)
                ("SXY", tr("var_sxy", "辐射应力 (SXY)")),
                ("TWO", tr("var_two", "动量通量 (TWO)")),
                ("BHD", tr("var_bhd", "Bernoulli头 (BHD)")),
                ("FOC", tr("var_foc", "能量通量 (FOC)")),
                ("TUS", tr("var_tus", "Stokes输运 (TUS)")),
                ("USS", tr("var_uss", "Stokes漂移 (USS)")),
                ("P2S", tr("var_p2s", "二阶和压力 (P2S)")),
                ("USF", tr("var_usf", "Stokes谱 (USF)")),
                ("P2L", tr("var_p2l", "微地震源 (P2L)")),
                ("TWI", tr("var_twi", "冰应力 (TWI)")),
                ("FIC", tr("var_fic", "冰能量通量 (FIC)")),
                ("USP", tr("var_usp", "分区Stokes漂移 (USP)")),
                ("TOC", tr("var_toc", "总海洋动量 (TOC)")),
                # 7. 底层参数 (Bottom)
                ("ABR", tr("var_abr", "底层位移振幅 (ABR)")),
                ("UBR", tr("var_ubr", "底层速度 (UBR)")),
                ("BED", tr("var_bed", "底形 (BED)")),
                ("FBB", tr("var_fbb", "底摩擦能流 (FBB)")),
                ("TBB", tr("var_tbb", "底摩擦应力 (TBB)")),
                # 8. 衍生谱参数 (Derived)
                ("MSS", tr("var_mss", "均方斜率 (MSS)")),
                ("MSC", tr("var_msc", "尾部水平 (MSC)")),
                ("MSD", tr("var_msd", "斜率方向 (MSD)")),
                ("MCD", tr("var_mcd", "尾部斜率方向 (MCD)")),
                ("QP", tr("var_qp", "峰值参数 (QP)")),
                ("QKK", tr("var_qkk", "波数峰值 (QKK)")),
                ("SKW", tr("var_skw", "偏度 (SKW)")),
                ("EMB", tr("var_emb", "跟踪器偏差 (EMB)")),
                # 9. 数值诊断 (Diagnostic)
                ("DTD", tr("var_dtd", "动态步长 (DTD)")),
                ("FC", tr("var_fc", "截止频率 (FC)")),
                ("CFX", tr("var_cfx", "CFL数 (CFX)")),
                ("CFD", tr("var_cfd", "CFL数 (CFD)")),
                ("CFK", tr("var_cfk", "CFL数 (CFK)")),
            ]
            
            # 存储复选框的字典
            self.output_vars_checkboxes = {}
            
            # 默认选中的变量
            default_selected = ["HS", "DIR", "FP", "T02", "WND", "PHS", "PTP", "PDIR", "PWS", "PNR", "TWS"]
            
            for var_code, var_name in output_vars_options:
                # 创建水平布局容器，让文字在左，选择框在右
                checkbox_row_layout = QHBoxLayout()
                checkbox_row_layout.setContentsMargins(0, 0, 0, 0)
                checkbox_row_layout.setSpacing(10)

                
                # 创建文字标签（放在左边）
                checkbox_label = QLabel(var_name)
                
                # 创建 CheckBox（只显示选择框，不显示文字）
                checkbox = CheckBox("")
                checkbox.setChecked(var_code in default_selected)
                
                # 不设置任何样式表，完全保留选择框的默认样式
                # 通过固定宽度来限制 CheckBox 只显示选择框部分
                from PyQt6.QtWidgets import QSizePolicy
                # 先让 CheckBox 计算默认大小，然后设置固定宽度
                checkbox.adjustSize()
                # 设置固定宽度，只保留选择框的宽度（大约 18-20px）
                checkbox.setFixedWidth(0)
                checkbox.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                

                # 将标签和选择框添加到布局，标签靠左，选择框靠右
                checkbox_row_layout.addWidget(checkbox_label)
                checkbox_row_layout.addStretch()  # 添加弹性空间，让选择框靠右
                checkbox_row_layout.addWidget(checkbox, 0)  # 选择框不拉伸
                
                # 创建容器 widget
                checkbox_row_widget = QWidget()
                checkbox_row_widget.setLayout(checkbox_row_layout)
                # 设置尺寸策略，让容器占满宽度
               
                checkbox_row_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                
                spectral_output_card_layout.addWidget(checkbox_row_widget)
                self.output_vars_checkboxes[var_code] = checkbox
            
            # 方案管理区域
            # 方案名称输入框（标签和输入框一行）
            scheme_name_layout = QHBoxLayout()
            scheme_name_layout.setSpacing(5)
            scheme_name_label = QLabel(tr("scheme_name_label", "方案名称："))
            scheme_name_layout.addWidget(scheme_name_label)
            
            self.output_vars_scheme_name_edit = LineEdit()
            self.output_vars_scheme_name_edit.setText(tr("default_scheme", "默认方案"))
            self.output_vars_scheme_name_edit.setStyleSheet(input_style)
            self.output_vars_scheme_name_edit.setPlaceholderText(tr("scheme_name_placeholder", "输入方案名称"))
            scheme_name_layout.addWidget(self.output_vars_scheme_name_edit)
            spectral_output_card_layout.addLayout(scheme_name_layout)
            
            # 当前方案下拉选择框（标签和下拉框一行）
            current_scheme_layout = QHBoxLayout()
            current_scheme_layout.setSpacing(5)
            current_scheme_label = QLabel(tr("current_scheme", "当前方案："))
            current_scheme_layout.addWidget(current_scheme_label)
            
            self.output_vars_scheme_combo = ComboBox()
            self.output_vars_scheme_combo.setStyleSheet(combo_style)
            self.output_vars_scheme_combo.currentTextChanged.connect(self._on_scheme_changed)
            current_scheme_layout.addWidget(self.output_vars_scheme_combo, 1)  # 设置拉伸因子为1，让下拉框展开
            spectral_output_card_layout.addLayout(current_scheme_layout)
            
            # 确认按钮（单独一行）
            confirm_output_vars_button = PrimaryPushButton(tr("confirm_output_vars", "确认"))
            confirm_output_vars_button.setStyleSheet(button_style)
            confirm_output_vars_button.clicked.connect(self._save_output_vars_config)
            spectral_output_card_layout.addWidget(confirm_output_vars_button)
            
            # 删除方案按钮（在确认按钮下面）
            delete_scheme_button = PrimaryPushButton(tr("delete_scheme", "删除方案"))
            delete_scheme_button.setStyleSheet(button_style)
            delete_scheme_button.clicked.connect(self._delete_output_vars_scheme)
            spectral_output_card_layout.addWidget(delete_scheme_button)
            
            spectral_output_card.viewLayout.setContentsMargins(11, 10, 11, 12)
            spectral_output_card.viewLayout.addLayout(spectral_output_card_layout)
            settings_layout.addWidget(spectral_output_card)
            
            # 初始化方案列表
            preserve_scheme = getattr(self, "_pending_output_scheme_selection", None)
            self._load_output_vars_schemes(preserve_selection=preserve_scheme)
            
            # 读取输出变量配置（语言切换时不读取）
            if force_language_code is None:
                self._load_output_vars_config()
            else:
                pending_vars = getattr(self, "_pending_output_vars_selection", None)
                if pending_vars is not None:
                    for var_code, checkbox in self.output_vars_checkboxes.items():
                        checkbox.setChecked(var_code in pending_vars)
                pending_scheme_name = getattr(self, "_pending_output_scheme_name", None)
                if pending_scheme_name and hasattr(self, "output_vars_scheme_name_edit"):
                    self.output_vars_scheme_name_edit.setText(pending_scheme_name)

            # 清理临时缓存
            if hasattr(self, "_pending_output_vars_selection"):
                self._pending_output_vars_selection = None
            if hasattr(self, "_pending_output_scheme_selection"):
                self._pending_output_scheme_selection = None
            if hasattr(self, "_pending_output_scheme_name"):
                self._pending_output_scheme_name = None

            # === 服务器连接设置 ===
            server_card = HeaderCardWidget(settings_content)
            server_card.setTitle(tr("server_connection", "服务器连接"))
            server_card.setStyleSheet("""
                HeaderCardWidget QLabel {
                    font-weight: normal;
                    margin-left: 0px;
                    padding-left: 0px;
                }
            """)
            server_card.headerLayout.setContentsMargins(11, 10, 11, 12)
            server_card_layout = QVBoxLayout()
            server_card_layout.setSpacing(5)
            server_card_layout.setContentsMargins(0, 0, 0, 0)

            # 使用网格布局确保输入框左右对齐
            server_params_layout = QGridLayout()
            server_params_layout.setColumnStretch(1, 1)  # 让输入框列可以拉伸，但不固定宽度
            server_params_layout.setSpacing(5)

            # 服务器地址
            host_label = QLabel(tr("default_server_host", "服务器地址:"))
            self.settings_server_host_edit = LineEdit()
            self.settings_server_host_edit.setText(current_config.get("SERVER_HOST", ""))
            self.settings_server_host_edit.setStyleSheet(input_style)
            server_params_layout.addWidget(host_label, 0, 0)
            server_params_layout.addWidget(self.settings_server_host_edit, 0, 1)

            # 端口
            port_label = QLabel(tr("default_port", "端口:"))
            self.settings_server_port_edit = LineEdit()
            self.settings_server_port_edit.setText(current_config.get("SERVER_PORT", ""))
            self.settings_server_port_edit.setStyleSheet(input_style)
            server_params_layout.addWidget(port_label, 1, 0)
            server_params_layout.addWidget(self.settings_server_port_edit, 1, 1)

            # 用户名
            user_label = QLabel(tr("default_username", "用户名:"))
            self.settings_server_user_edit = LineEdit()
            self.settings_server_user_edit.setText(current_config.get("SERVER_USER", ""))
            self.settings_server_user_edit.setStyleSheet(input_style)
            server_params_layout.addWidget(user_label, 2, 0)
            server_params_layout.addWidget(self.settings_server_user_edit, 2, 1)

            # 密码
            password_label = QLabel(tr("default_password", "密码:"))
            self.settings_server_password_edit = LineEdit()
            self.settings_server_password_edit.setText(current_config.get("SERVER_PASSWORD", ""))
            self.settings_server_password_edit.setEchoMode(LineEdit.EchoMode.Password)
            self.settings_server_password_edit.setStyleSheet(input_style)
            server_params_layout.addWidget(password_label, 3, 0)
            server_params_layout.addWidget(self.settings_server_password_edit, 3, 1)

            # 服务器路径
            server_path_label = QLabel(tr("default_server_path", "服务器工作目录:"))
            self.settings_server_path_edit = LineEdit()
            self.settings_server_path_edit.setText(current_config.get("SERVER_PATH", ""))
            self.settings_server_path_edit.setStyleSheet(input_style)
            server_params_layout.addWidget(server_path_label, 4, 0)
            server_params_layout.addWidget(self.settings_server_path_edit, 4, 1)

            server_card_layout.addLayout(server_params_layout)

            server_card.viewLayout.setContentsMargins(11, 10, 11, 12)
            server_card.viewLayout.addLayout(server_card_layout)
            settings_layout.addWidget(server_card)

            # === ST 版本管理 ===
            st_version_card = HeaderCardWidget(settings_content)
            st_version_card.setTitle(tr("st_version_config", "ST 版本管理"))
            st_version_card.setStyleSheet("""
                HeaderCardWidget QLabel {
                    font-weight: normal;
                    margin-left: 0px;
                    padding-left: 0px;
                }
            """)
            st_version_card.headerLayout.setContentsMargins(11, 10, 11, 12)
            st_version_card_layout = QVBoxLayout()
            st_version_card_layout.setSpacing(10)
            st_version_card_layout.setContentsMargins(0, 0, 0, 0)

            # ST 版本列表表格（参考 demo.py 的样式）
            self.st_version_table = TableWidget()
            self.st_version_table.setColumnCount(2)
            # 隐藏水平表头
            self.st_version_table.horizontalHeader().setVisible(False)
            # 设置列宽：ST名称列固定宽度，路径列自动拉伸
            header = self.st_version_table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)  # ST名称列固定宽度
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # 路径列自动拉伸
            self.st_version_table.setColumnWidth(0, 100)  # 设置ST名称列宽度为100像素
            self.st_version_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)  # 整行选择
            self.st_version_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)  # 禁止直接编辑
            # 去除边框
            self.st_version_table.setBorderVisible(False)
            self.st_version_table.setWordWrap(False)
            # 隐藏垂直表头
            self.st_version_table.verticalHeader().setVisible(False)
            # 设置外边距为0
            self.st_version_table.setContentsMargins(0, 0, 0, 0)

            # 加载 ST 版本列表
            st_versions = current_config.get("ST_VERSIONS", [])
            if isinstance(st_versions, list):
                self.st_version_table.setRowCount(len(st_versions))
                for i, version in enumerate(st_versions):
                    if isinstance(version, dict) and "name" in version and "path" in version:
                        name_item = QTableWidgetItem(version["name"])
                        name_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)  # 左对齐
                        path_item = QTableWidgetItem(version["path"])
                        path_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)  # 左对齐
                        self.st_version_table.setItem(i, 0, name_item)
                        self.st_version_table.setItem(i, 1, path_item)

            # 根据内容行数动态设置高度，完全展开显示所有内容
            row_count = self.st_version_table.rowCount()
            # 设置行高自动调整
            vertical_header = self.st_version_table.verticalHeader()
            vertical_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            # 隐藏垂直滚动条，强制显示所有行
            self.st_version_table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            # 计算实际高度：每行高度 + 边距
            if row_count > 0:
                # 先调整行高以适应内容
                self.st_version_table.resizeRowsToContents()
                # 计算总高度：所有行高之和 + 边距
                total_height = 0
                for i in range(row_count):
                    total_height += self.st_version_table.rowHeight(i)
                content_height = max(200, total_height + 20)  # 加上边距
            else:
                content_height = 200  # 至少200px
            self.st_version_table.setMinimumHeight(content_height)
            self.st_version_table.setMaximumHeight(16777215)  # 不限制最大高度，完全展开
            # 设置大小策略：允许垂直方向扩展
            from PyQt6.QtWidgets import QSizePolicy
            size_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            self.st_version_table.setSizePolicy(size_policy)

            st_version_card_layout.addWidget(self.st_version_table)

            # 按钮区域
            st_version_buttons_layout = QHBoxLayout()
            st_version_buttons_layout.setSpacing(10)

            btn_add_st = PrimaryPushButton(tr("new", "新增"))
            btn_add_st.setStyleSheet(button_style)
            btn_add_st.clicked.connect(self._add_st_version)
            st_version_buttons_layout.addWidget(btn_add_st, 1)  # 添加拉伸因子，平分宽度

            btn_edit_st = PrimaryPushButton(tr("edit", "修改"))
            btn_edit_st.setStyleSheet(button_style)
            btn_edit_st.clicked.connect(self._edit_st_version)
            st_version_buttons_layout.addWidget(btn_edit_st, 1)  # 添加拉伸因子，平分宽度

            btn_delete_st = PrimaryPushButton(tr("delete", "删除"))
            btn_delete_st.setStyleSheet(button_style)
            btn_delete_st.clicked.connect(self._delete_st_version)
            st_version_buttons_layout.addWidget(btn_delete_st, 1)  # 添加拉伸因子，平分宽度

            btn_set_default_st = PrimaryPushButton(tr("default", "默认"))
            btn_set_default_st.setStyleSheet(button_style)
            btn_set_default_st.clicked.connect(self._set_default_st_version)
            st_version_buttons_layout.addWidget(btn_set_default_st, 1)  # 添加拉伸因子，平分宽度

            st_version_card_layout.addLayout(st_version_buttons_layout)

            # 恢复横向内边距
            st_version_card.viewLayout.setContentsMargins(11, 10, 11, 12)
            st_version_card.viewLayout.addLayout(st_version_card_layout)
            settings_layout.addWidget(st_version_card)

            # === 联系我 ===
            contact_card = HeaderCardWidget(settings_content)
            contact_card.setTitle(tr("contact_me", "联系我"))
            contact_card.setStyleSheet("""
                HeaderCardWidget QLabel {
                    font-weight: normal;
                    margin-left: 0px;
                    padding-left: 0px;
                }
            """)
            contact_card.headerLayout.setContentsMargins(11, 10, 11, 12)
            contact_card_layout = QVBoxLayout()
            contact_card_layout.setSpacing(10)
            contact_card_layout.setContentsMargins(0, 0, 0, 0)

            # 使用主题适配的样式（用于地址框）
            from qfluentwidgets import isDarkTheme
            is_dark = isDarkTheme()
            if is_dark:
                address_style = """
                    QLabel {
                        background-color: #2D2D2D;
                        border: 1px solid #404040;
                        border-radius: 4px;
                        padding: 6px 10px;
                        color: #0078D4;
                    }
                """
            else:
                address_style = """
                    QLabel {
                        background-color: #FFFFFF;
                        border: 1px solid #D0D0D0;
                        border-radius: 4px;
                        padding: 6px 10px;
                        color: #0078D4;
                    }
                """
            
            # GitHub 地址（一行显示）
            github_row = QHBoxLayout()
            github_row.setContentsMargins(0, 0, 0, 0)
            github_row.setSpacing(10)
            github_label = QLabel("GitHub:")
            
            github_label.setMinimumWidth(60)  # 设置标签最小宽度，确保对齐
            github_row.addWidget(github_label)
            
            github_value_label = QLabel('<a href="https://github.com/ZxyGch/WW3Tool">https://github.com/ZxyGch/WW3Tool</a>')
            github_value_label.setStyleSheet(address_style)
            github_value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse)
            github_value_label.setOpenExternalLinks(True)
            github_row.addWidget(github_value_label, 1)  # 添加拉伸因子，让地址框占满剩余空间
            contact_card_layout.addLayout(github_row)

            # 邮箱地址（一行显示）
            email_row = QHBoxLayout()
            email_row.setContentsMargins(0, 0, 0, 0)
            email_row.setSpacing(10)
            email_label = QLabel(tr("email", "邮箱") + ":")
            
            email_label.setMinimumWidth(60)  # 设置标签最小宽度，确保对齐
            email_row.addWidget(email_label)
            
            email_value_label = QLabel('<a href="mailto:atomgoto@gmail.com">atomgoto@gmail.com</a>')
            email_value_label.setStyleSheet(address_style)
            email_value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse)
            email_value_label.setOpenExternalLinks(True)
            email_row.addWidget(email_value_label, 1)  # 添加拉伸因子，让地址框占满剩余空间
            contact_card_layout.addLayout(email_row)

            contact_card.viewLayout.setContentsMargins(11, 10, 11, 12)
            contact_card.viewLayout.addLayout(contact_card_layout)
            settings_layout.addWidget(contact_card)

            # 添加弹性空间
            settings_layout.addStretch()

            # 为所有输入控件添加自动保存信号连接
            self._connect_settings_auto_save()

            # 创建滚动区域（不显示滚动条）
            settings_scroll_area = QtWidgets.QScrollArea()
            settings_scroll_area.setWidgetResizable(True)
            settings_scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            settings_scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            settings_scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            settings_scroll_area.setStyleSheet("""
                QScrollArea {
                    background-color: transparent;
                    border: none;
                    margin: 0px;
                    padding: 0px;
                }
            """)
            settings_scroll_area.setWidget(settings_content)

            return settings_scroll_area
        except Exception as e:
            # 如果 log_text 还未初始化，使用 print 输出错误
            error_msg = f"❌ 创建设置页面失败：{e}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            # 返回一个空的 widget 作为占位
            placeholder = QWidget()
            placeholder.setStyleSheet("QWidget { background-color: transparent; }")
            return placeholder
