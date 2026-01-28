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

class SettingsMixin:
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

            # 路径设置（MATLAB、GRIDGEN、Reference Data）- 放在最上面
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

            gridgen_label = QLabel(tr("gridgen_path", "GRIDGEN 路径:"))
            self.gridgen_label = gridgen_label  # 保存引用以便后续更新
            grid_card_layout.addWidget(gridgen_label)
            gridgen_row = QHBoxLayout()
            self.settings_gridgen_edit = LineEdit()
            self.settings_gridgen_edit.setPlaceholderText(f"{tr('default_path', '默认路径')}：WW3Tool/gridgen")
            gridgen_path = current_config.get("GRIDGEN_PATH", "").strip()
            # 计算默认路径（用于比较，不显示在输入框中）
            script_dir = os.path.dirname(os.path.abspath(__file__))
            default_gridgen_path = os.path.normpath(os.path.join(os.path.dirname(script_dir), "gridgen"))
            # 如果配置为空或等于默认路径，输入框显示为空（不显示默认路径）
            if not gridgen_path or os.path.normpath(gridgen_path) == default_gridgen_path:
                gridgen_path = ""  # 输入框显示为空
            else:
                gridgen_path = os.path.normpath(gridgen_path)  # 规范化路径（Windows 上会转换为反斜杠格式）
            self.settings_gridgen_edit.setText(gridgen_path)
            self.settings_gridgen_edit.setStyleSheet(input_style)
            gridgen_row.addWidget(self.settings_gridgen_edit, 1)
            btn_choose_gridgen = PrimaryPushButton(tr("select", "选择"))
            btn_choose_gridgen.setStyleSheet(button_style)
            btn_choose_gridgen.clicked.connect(lambda: self._choose_gridgen_path())
            gridgen_row.addWidget(btn_choose_gridgen)
            grid_card_layout.addLayout(gridgen_row)

            reference_data_label = QLabel(tr("reference_data_path", "Reference Data 路径:"))
            self.reference_data_label = reference_data_label  # 保存引用以便后续更新
            grid_card_layout.addWidget(reference_data_label)
            reference_data_row = QHBoxLayout()
            self.settings_reference_data_edit = LineEdit()
            self.settings_reference_data_edit.setPlaceholderText(f"{tr('default_path', '默认路径')}：WW3Tool/gridgen/reference_data")
            reference_data_path = current_config.get("REFERENCE_DATA_PATH", "").strip()
            # 计算默认路径（用于比较，不显示在输入框中）
            script_dir = os.path.dirname(os.path.abspath(__file__))
            default_gridgen_path = os.path.normpath(os.path.join(os.path.dirname(script_dir), "gridgen"))
            default_reference_data_path = os.path.join(default_gridgen_path, "reference_data")
            # 如果配置为空或等于默认路径，输入框显示为空（不显示默认路径）
            if not reference_data_path:
                reference_data_path = ""  # 输入框显示为空
            else:
                reference_data_path = os.path.normpath(reference_data_path)  # 规范化路径（Windows 上会转换为反斜杠格式）
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
                tr("coastline_low", "低")
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
                tr("coastline_low", "低"): 3
            }
            coastline_map_en = {"Highest": 0, "High": 1, "Medium": 2, "Low": 3}
            
            if saved_coastline in coastline_map_zh:
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


    def _choose_gridgen_path(self):
        """选择 GRIDGEN 路径"""
        start = self.settings_gridgen_edit.text().strip() if hasattr(self, 'settings_gridgen_edit') else ""
        if not start or not os.path.exists(start):
            # 如果配置路径不存在，优先使用默认的相对路径
            script_dir = os.path.dirname(os.path.abspath(__file__))
            default_path = os.path.join(os.path.dirname(script_dir), "gridgen")
            if os.path.exists(default_path):
                start = default_path
            else:
                # 如果默认路径也不存在，使用当前用户的主目录
                start = os.path.expanduser("~")

        # 规范化起始路径（Windows 上会转换为反斜杠格式）
        start = os.path.normpath(start)

        path = QFileDialog.getExistingDirectory(
            self,
            "选择 GRIDGEN 目录",
            start,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
        )

        if path:
            # 规范化返回的路径（Windows 上会转换为反斜杠格式，如 C:\Users\atomg）
            path = os.path.normpath(path)
            self.settings_gridgen_edit.setText(path)


    def _choose_reference_data_path(self):
        """选择 Reference Data 路径"""
        start = self.settings_reference_data_edit.text().strip() if hasattr(self, 'settings_reference_data_edit') else ""
        if not start or not os.path.exists(start):
            # 如果配置路径不存在，优先使用默认的相对路径
            script_dir = os.path.dirname(os.path.abspath(__file__))
            default_gridgen_path = os.path.join(os.path.dirname(script_dir), "gridgen")
            default_path = os.path.join(default_gridgen_path, "reference_data")
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
            self.settings_gridgen_edit,
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
            gridgen_path = self.settings_gridgen_edit.text().strip()
            # 如果 gridgen 路径为空，保存为空字符串（不保存默认路径）
            # 实际使用时会在 config.py 中处理默认值
            if gridgen_path:
                gridgen_path = os.path.normpath(gridgen_path)  # 规范化路径（Windows 上会转换为反斜杠格式）
            else:
                gridgen_path = ""  # 保存为空字符串

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
                "GRIDGEN_PATH": gridgen_path,
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
                    {0: "最高", 1: "高", 2: "中", 3: "低"}.get(
                        self.settings_coastline_combo.currentIndex() if hasattr(self, 'settings_coastline_combo') else 0,
                        "最高"
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
                if hasattr(self, 'shel_step_edit') and self.shel_step_edit:
                    self.shel_step_edit.setText(COMPUTE_PRECISION)
                if hasattr(self, 'output_precision_edit') and self.output_precision_edit:
                    self.output_precision_edit.setText(OUTPUT_PRECISION)
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
                ("gridgen_label", "gridgen_path", "GRIDGEN 路径:"),
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

