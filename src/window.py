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
from qfluentwidgets import FluentWindow, PrimaryPushButton, LineEdit, TextEdit, InfoBar, setTheme, Theme, PlainTextEdit
from qfluentwidgets import NavigationItemPosition, NavigationWidget, FluentIcon, HeaderCardWidget, ComboBox, TableWidget, CheckBox
from PyQt6.QtGui import QColor, QIcon
from qfluentwidgets import MessageBoxBase

from PyQt6.QtWidgets import QTableWidgetItem, QHeaderView, QScrollArea, QListWidget, QListWidgetItem
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPoint, pyqtSignal
from setting.language_manager import tr

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
QCheckBox = QtWidgets.QCheckBox
QGroupBox = QtWidgets.QGroupBox
QScrollArea = QtWidgets.QScrollArea

from setting.config import *
from setting.language_manager import tr
from plot.workers import _match_ww3_jason3_worker, _run_jason3_swh_worker, _make_wave_maps_worker, _make_contour_maps_worker, _generate_all_spectrum_worker, _generate_selected_spectrum_worker

from public.style import Style
from public.log import Log
from plot.file_tool import FileOpsMixin
from home.step1.step1_ui import HomeStepOneCard
from home.home_step_two_card import HomeStepTwoCard

from tool.window_jason3 import Jason3Mixin
from home.modify_ww3_nml import ModifyWW3NML
from setting.settings import SettingsMixin
from public.navigation_button import NavigationMixin

from home.home_step_three_card import HomeStepThreeCard
from home.home_step_four_card import HomeStepFourCard
from home.home_local_run import HomeLocalRun
from home.home_step_five_card import HomeStepFiveCard
from home.step6.step6_ui import HomeStepSixCard
from plot.plot import PlotMixin


class MainWindow(FluentWindow, Style, Log, FileOpsMixin, HomeStepOneCard, HomeStepTwoCard, Jason3Mixin, ModifyWW3NML, SettingsMixin, NavigationMixin, HomeStepThreeCard, HomeStepFourCard, HomeLocalRun, HomeStepFiveCard, HomeStepSixCard, PlotMixin):
    # 定义信号用于从后台线程更新 UI
    log_signal = QtCore.Signal(str)
    log_update_last_line_signal = QtCore.Signal(str)  # 用于更新日志最后一行
    status_signal = QtCore.Signal(str)
    update_cpu_table_signal = QtCore.Signal(list)  # 用于更新 CPU 表格
    update_queue_table_signal = QtCore.Signal(list, str)  # 用于更新任务队列表格 (task_lines, time_cn)
    show_image_signal = QtCore.Signal(str, str)  # 用于显示图片 (image_path, window_title)
    show_fit_image_signal = QtCore.Signal(str, str)  # 用于在Qt窗口中显示拟合图 (image_path, window_title)
    add_image_to_drawer_signal = QtCore.Signal(str, int, int)  # 用于在抽屉中添加图片 (image_path, width, height)
    images_loading_complete_signal = QtCore.Signal()  # 图片加载完成信号
    show_info_bar_signal = QtCore.Signal(str, str, str)  # 用于显示 InfoBar (type, title, content)


    def __init__(self):
        super().__init__()


        # 在方法开始处加载配置，避免后续使用时的 UnboundLocalError
        from setting.config import load_config
        current_config = load_config()

        LONGITUDE_WEST = current_config.get("LONGITUDE_WEST", "")
        LONGITUDE_EAST = current_config.get("LONGITUDE_EAST", "")
        LATITUDE_SORTH = current_config.get("LATITUDE_SORTH", "")
        LATITUDE_NORTH = current_config.get("LATITUDE_NORTH", "")
        JASON_PATH = current_config.get("JASON_PATH", "")

        # 主题默认跟随系统
        theme_config = "AUTO"
        self._theme_mode = "AUTO"
        # 将字符串转换为 Theme 枚举
        if theme_config == "LIGHT":
            theme = Theme.LIGHT
        elif theme_config == "DARK":
            theme = Theme.DARK
        else:
            theme = Theme.AUTO
        setTheme(theme)



        # 尽早初始化主题状态，避免后续调用样式函数时出错
        try:
            from qfluentwidgets import isDarkTheme
            self._dark = isDarkTheme()
        except:
            self._dark = False

        self._last_theme_state = None  # 用于跟踪上次的主题状态

        # 隐藏自带的标题栏按钮（主要是为了隐藏 MacOS 的按钮，自带的没有适配好）
        self.setSystemTitleBarButtonVisible(False)


        # 显示 Win11 样式的标题栏按钮
        self.titleBar.minBtn.show()
        self.titleBar.maxBtn.show()
        self.titleBar.closeBtn.show()


        # 隐藏自带的返回按钮
        self.navigationInterface.setReturnButtonVisible(False)


        # 设置主题色为蓝色
        from qfluentwidgets import setThemeColor
        setThemeColor(QColor(0, 120, 212))  # 使用蓝色 RGB 值


        # 设置窗口标题
        self.setWindowTitle(tr("app_title", "海浪模式 WAVEWATCH III 可视化运行软件"))


        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public", "resource", "logo.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))


        # 连接信号到槽函数 - 使用 QueuedConnection 确保跨线程安全
        self.log_signal.connect(self.log, Qt.ConnectionType.QueuedConnection)
        self.add_image_to_drawer_signal.connect(self._add_single_image_to_drawer, Qt.ConnectionType.QueuedConnection)
        self.images_loading_complete_signal.connect(self._on_images_loading_complete, Qt.ConnectionType.QueuedConnection)
        self.show_info_bar_signal.connect(self._show_info_bar, Qt.ConnectionType.QueuedConnection)

        # 监听系统主题变化（延迟设置，确保 log 方法可用）
        # QtCore.QTimer.singleShot(500, self._setup_theme_monitor)
        self._setup_theme_monitor()
        self.log_update_last_line_signal.connect(self.log_update_last_line, Qt.ConnectionType.QueuedConnection)
        self.status_signal.connect(self._set_conn_status_safe)
        self.update_cpu_table_signal.connect(self._update_cpu_table)
        self.update_queue_table_signal.connect(self._update_queue_table)
        self.show_image_signal.connect(lambda path, title: self.open_image_file(path) if path else None)
        self.show_fit_image_signal.connect(lambda path, title: self.open_image_file(path) if path else None)


        self.selected_folder = ""


        # 创建主容器，使用 QSplitter 来管理左右两部分
        main_splitter = QSplitter(QtCore.Qt.Orientation.Horizontal)
        
        # 分割线样式
        main_splitter.setStyleSheet("""
        QSplitter::handle:horizontal {
            background-color: #64AADE;
            border-width: 2px;
            border-radius: 0.8px;
            margin: 330px 2px;
        }
        QSplitter::handle:horizontal:hover {
            background-color: #909090;
        }
        """)
        


        # 左侧内容区域（占1/3），使用 QStackedWidget 切换主页、科研绘图、设置页面
        left_content = QWidget()
        left_content.setStyleSheet("QWidget { background-color: transparent; }")
        left_layout = QVBoxLayout(left_content)

        # 设置边距，右侧添加边距用于分隔条
        left_layout.setContentsMargins(0, 0, 5, 10)  # 右边距10px，下边距20px
        left_layout.setSpacing(0)  # 无间距

        # 创建堆叠窗口用于切换主页和设置页面
        self.left_stacked = QStackedWidget()
        self.left_stacked.setStyleSheet("QStackedWidget { background-color: transparent; }")

        # === 主页内容 ===
        # 创建内容容器 - 使用简单的从上到下布局
        content_widget = QWidget()
        content_widget.setStyleSheet("QWidget { background-color: transparent; margin: 0px; padding: 0px; }")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)  # 取消默认边距
        content_layout.setSpacing(10)  # 卡片间距
        content_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)  # 对齐到顶部

        # 创建滚动区域
        left_scroll_area = QtWidgets.QScrollArea()
        left_scroll_area.setWidgetResizable(True)
        left_scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        left_scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
                margin: 0px;
                padding: 0px;
            }
            QScrollArea > QWidget > QWidget {
                margin: 0px;
                padding: 0px;
            }
        """)
        left_scroll_area.setWidget(content_widget)

        # 将主页添加到堆叠窗口（索引0）
        self.left_stacked.addWidget(left_scroll_area)

        # === 设置页面 ===
        settings_widget = self._create_settings_page()
        self.left_stacked.addWidget(settings_widget)  # 索引1：设置页面


        # === 绘图页面 ===
        plot_widget = self._create_plot_page()
        self.left_stacked.addWidget(plot_widget)  # 索引2：绘图页面


        # === 工具页面 ===
        tools_widget = self._create_tools_page()
        self.left_stacked.addWidget(tools_widget)  # 索引3：工具页面


        # 默认显示主页
        self.left_stacked.setCurrentIndex(0)

        # 添加到布局
        left_layout.addWidget(self.left_stacked)

        # 第一步：选择强迫场文件（UI 与按钮逻辑在 HomeStepOneCard）
        self.create_step_1_card(content_widget, content_layout)

        # 第二步：生成网格
        self.create_step_2_card(content_widget, content_layout)

        # 第三步：计算模式（UI 与逻辑在 HomeStepThreeCard）
        self.create_step_3_card(content_widget, content_layout)

        # 第四步：配置WW3运行参数（UI 与逻辑在 HomeStepFourCard）
        self.create_step_4_card(content_widget, content_layout)

        # 本地运行（UI 与逻辑在 HomeLocalRun）
        self.create_step_5_card(content_widget, content_layout)

        # 第五步：连接服务器（UI 与逻辑在 HomeStepFiveCard）
        self.create_step_5_server_card(content_widget, content_layout)

        # 第六步：服务器操作（UI 与逻辑在 HomeStepSixCard）
        self.create_step_6_card(content_widget, content_layout)

        # 第七步已删除（波高图绘制功能已移至绘图页面）
        # 注意：第七步（波高图绘制）已移至绘图页面，主页不再显示

        # 初始化服务器连接相关变量
        self.ssh = None
        self._last_conn_args = None
        self._heartbeat_timer = None
        self._queue_timer = None
        self._queue_running = False
        self._connection_lost = False  # 标记连接是否已断开，用于防止重复日志

        # 注意：left_scroll_area 已经在第 371 行设置了 widget，并在第 374 行添加到了 left_stacked
        # left_stacked 已经在第 415 行添加到了 left_layout，所以这里不需要再次添加

        # 右侧日志区域（占2/3），带滚动条
        right_log_frame = QWidget()
        right_log_layout = QVBoxLayout(right_log_frame)
        right_log_layout.setContentsMargins(5, 1, 10, 11)  # 上边距设为0

        # 日志文本区域（PlainTextEdit 自带滚动条）
        self.log_text = PlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # 使用主题适配的边框样式
        self._update_log_border_style()
        # PlainTextEdit 自带滚动条，确保滚动条始终可见

        right_log_layout.addWidget(self.log_text, 1)  # 设置拉伸因子

        # 添加到分割器
        main_splitter.addWidget(left_content)
        main_splitter.addWidget(right_log_frame)

        # 设置比例：左侧1，右侧2（即1:2的比例，左侧占1/3，右侧占2/3）
        main_splitter.setStretchFactor(0, 1)  # 左侧权重1
        main_splitter.setStretchFactor(1, 2)  # 右侧权重2

        # 设置初始大小比例（1:2），确保左侧占1/3，右侧占2/3
        # 使用setSizes来设置初始大小（像素值），这里使用相对值，splitter会自动按比例分配
        # 如果窗口宽度是1200，则左侧400，右侧800
        # 但为了确保比例正确，我们在窗口显示后通过QTimer设置
        def set_splitter_ratio():
            if hasattr(self, 'width') and self.width() > 0:
                total_width = self.width()
                left_width = total_width // 3
                right_width = total_width - left_width
                main_splitter.setSizes([left_width, right_width])
        
        # 延迟设置，确保窗口已经显示
        QtCore.QTimer.singleShot(0, set_splitter_ratio)
        QtCore.QTimer.singleShot(100, set_splitter_ratio)

        main_container = main_splitter


        # 保存main_splitter的引用，以便后续使用
        self.main_splitter = main_splitter
        
        # 创建主界面 Widget（包含左侧切换区域和右侧固定日志区域），设置全局唯一的对象名
        # 这样右侧日志可以一直保持显示，只有左侧内容在主页和设置之间切换（通过 left_stacked）
        main_interface = QWidget()
        main_interface.setObjectName("main_interface")  # 设置全局唯一的对象名
        main_interface_layout = QVBoxLayout(main_interface)
        main_interface_layout.setContentsMargins(0, 0, 0, 0)
        main_interface_layout.addWidget(main_container)  # 包含左侧和右侧的完整布局
        
        # 创建侧边抽屉（覆盖在主界面之上）
        self._create_test_drawer(main_interface)

        # 使用 addSubInterface 注册主界面（必须在添加到窗口之前）
        # 只注册一个主界面，包含完整的布局（左侧切换+右侧固定日志）
        # 左侧内容的切换通过 left_stacked 来实现，不通过 FluentWindow 的路由系统
        # 保存路由键，用于后续处理（routeKey 通过 objectName 自动设置）
        self.main_interface_route_key = "main_interface"
       
        # 主页按钮放在最上面
       
        self.addSubInterface(main_interface, FluentIcon.HOME, tr("home", "主页"), NavigationItemPosition.TOP)
        
        # 连接导航信号，处理主页按钮点击
        if hasattr(self, '_connect_navigation_signals'):
            QtCore.QTimer.singleShot(150, self._connect_navigation_signals)
        
        # 连接 stackedWidget 的信号，确保切换到 main_interface 时调用 show_home
        if hasattr(self, 'stackedWidget') and self.stackedWidget:
            self.stackedWidget.currentChanged.connect(self._on_stacked_widget_changed)
        
        # 延迟添加所有导航按钮，确保导航界面完全初始化
        QtCore.QTimer.singleShot(100, self._add_all_navigation_buttons)
        
        # 根据运行方式更新界面可见性
        QtCore.QTimer.singleShot(200, self._update_run_mode_visibility)
    
        self._software_copyright = tr("software_copyright", "本软件由上海海洋大学宫楚恒于 2025 年 9 月开发，师兄韩梓琪帮助，导师魏永亮")

        self.log(self._software_copyright)


    def _update_run_mode_visibility(self):
        """根据运行方式更新界面组件的可见性"""
        try:
            from setting.config import load_config
            current_config = load_config()
            run_mode = current_config.get("RUN_MODE", "both")
            
            # 如果选择本地运行，隐藏第六步、slurm配置、wavewatch配置标签
            if run_mode == "local":
                # 显示第五步（本地运行）
                if hasattr(self, 'step5_card') and self.step5_card:
                    self.step5_card.setVisible(True)
                # 隐藏第六步（服务器连接）和第七步（服务器操作）
                if hasattr(self, 'step6_card') and self.step6_card:
                    self.step6_card.setVisible(False)
                if hasattr(self, 'step7_card') and self.step7_card:
                    self.step7_card.setVisible(False)
                # 隐藏 Slurm 配置相关
                if hasattr(self, 'slurm_title_container') and self.slurm_title_container:
                    self.slurm_title_container.setVisible(False)
                if hasattr(self, 'st_label') and self.st_label:
                    self.st_label.setVisible(False)
                if hasattr(self, 'st_combo') and self.st_combo:
                    self.st_combo.setVisible(False)
                if hasattr(self, 'cpu_label') and self.cpu_label:
                    self.cpu_label.setVisible(False)
                if hasattr(self, 'cpu_combo') and self.cpu_combo:
                    self.cpu_combo.setVisible(False)
                if hasattr(self, 'num_n_label') and self.num_n_label:
                    self.num_n_label.setVisible(False)
                if hasattr(self, 'num_n_edit') and self.num_n_edit:
                    self.num_n_edit.setVisible(False)
                if hasattr(self, 'num_N_label') and self.num_N_label:
                    self.num_N_label.setVisible(False)
                if hasattr(self, 'num_N_edit') and self.num_N_edit:
                    self.num_N_edit.setVisible(False)
                # WAVEWATCH 配置标签由网格类型控制，这里不处理
            
            # 如果只选择服务器运行，隐藏第五步（本地运行）
            elif run_mode == "server":
                if hasattr(self, 'step5_card') and self.step5_card:
                    self.step5_card.setVisible(False)
                # 显示第六步和第七步
                if hasattr(self, 'step6_card') and self.step6_card:
                    self.step6_card.setVisible(True)
                if hasattr(self, 'step7_card') and self.step7_card:
                    self.step7_card.setVisible(True)
                # 显示 Slurm 配置相关
                if hasattr(self, 'slurm_title_container') and self.slurm_title_container:
                    self.slurm_title_container.setVisible(True)
                if hasattr(self, 'st_label') and self.st_label:
                    self.st_label.setVisible(True)
                if hasattr(self, 'st_combo') and self.st_combo:
                    self.st_combo.setVisible(True)
                if hasattr(self, 'cpu_label') and self.cpu_label:
                    self.cpu_label.setVisible(True)
                if hasattr(self, 'cpu_combo') and self.cpu_combo:
                    self.cpu_combo.setVisible(True)
                if hasattr(self, 'num_n_label') and self.num_n_label:
                    self.num_n_label.setVisible(True)
                if hasattr(self, 'num_n_edit') and self.num_n_edit:
                    self.num_n_edit.setVisible(True)
                if hasattr(self, 'num_N_label') and self.num_N_label:
                    self.num_N_label.setVisible(True)
                if hasattr(self, 'num_N_edit') and self.num_N_edit:
                    self.num_N_edit.setVisible(True)
                # 显示 WAVEWATCH 配置标签（根据网格类型）
                if hasattr(self, 'wavewatch_title_container') and self.wavewatch_title_container:
                    # 保持原有的可见性逻辑（根据网格类型）
                    pass
            
            # 如果选择本地+服务器运行，显示所有
            else:  # both
                if hasattr(self, 'step5_card') and self.step5_card:
                    self.step5_card.setVisible(True)
                if hasattr(self, 'step6_card') and self.step6_card:
                    self.step6_card.setVisible(True)
                if hasattr(self, 'step7_card') and self.step7_card:
                    self.step7_card.setVisible(True)
                # 显示 Slurm 配置相关
                if hasattr(self, 'slurm_title_container') and self.slurm_title_container:
                    self.slurm_title_container.setVisible(True)
                if hasattr(self, 'st_label') and self.st_label:
                    self.st_label.setVisible(True)
                if hasattr(self, 'st_combo') and self.st_combo:
                    self.st_combo.setVisible(True)
                if hasattr(self, 'cpu_label') and self.cpu_label:
                    self.cpu_label.setVisible(True)
                if hasattr(self, 'cpu_combo') and self.cpu_combo:
                    self.cpu_combo.setVisible(True)
                if hasattr(self, 'num_n_label') and self.num_n_label:
                    self.num_n_label.setVisible(True)
                if hasattr(self, 'num_n_edit') and self.num_n_edit:
                    self.num_n_edit.setVisible(True)
                if hasattr(self, 'num_N_label') and self.num_N_label:
                    self.num_N_label.setVisible(True)
                if hasattr(self, 'num_N_edit') and self.num_N_edit:
                    self.num_N_edit.setVisible(True)
                # WAVEWATCH 配置标签保持原有逻辑
        except Exception as e:
            if hasattr(self, 'log'):
                self.log(f"❌ 更新运行方式可见性失败：{e}")
    
    def _create_tools_page(self):
        """创建常用工具页面（只包含左侧内容，右侧日志区域由主页共享）"""
       
        from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
        
        # 创建工具页面容器
        tools_content = QWidget()
        tools_content.setStyleSheet("QWidget { background-color: transparent; }")
        tools_layout = QVBoxLayout(tools_content)
        tools_layout.setContentsMargins(0, 0, 0, 10)
        tools_layout.setSpacing(15)
        
        # 创建滚动区域
        tools_scroll_area = QtWidgets.QScrollArea()
        tools_scroll_area.setWidgetResizable(True)
        tools_scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tools_scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tools_scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        tools_scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
                margin: 0px;
                padding: 0px;
            }
            QScrollArea > QWidget > QWidget {
                margin: 0px;
                padding: 0px;
            }
        """)
        
        # 创建内容容器
        tools_content_widget = QWidget()
        tools_content_widget.setStyleSheet("QWidget { background-color: transparent; }")
        tools_content_layout = QVBoxLayout(tools_content_widget)
        tools_content_layout.setContentsMargins(0, 0, 0, 10)
        tools_content_layout.setSpacing(8)
        tools_content_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        
        # 添加一个标题
        tools_title = QLabel(tr("tools", "常用工具"))
        tools_title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px;")
        tools_content_layout.addWidget(tools_title)
        
        # 这里可以添加工具按钮或内容
        # 暂时添加一个占位标签
        tools_placeholder = QLabel(tr("tools_placeholder", "工具内容将显示在这里"))
        tools_placeholder.setStyleSheet("padding: 20px; color: #888888;")
        tools_content_layout.addWidget(tools_placeholder)
        
        tools_scroll_area.setWidget(tools_content_widget)
        tools_layout.addWidget(tools_scroll_area)
        
        return tools_content

    def _initialize_work_directory(self, selected_folder):
        """
        初始化工作目录相关的所有设置和检测
        包括：更新标题、检测强迫场、检测网格模式、检测计算模式等
        """
        import os
        from setting.config import SERVER_PATH, add_recent_workdir
        from setting.language_manager import tr
        
        # 更新主窗口的工作目录（强制使用绝对路径，避免相对路径导致 gridgen 输出错误）
        old_folder = getattr(self, 'selected_folder', None)
        if isinstance(selected_folder, str) and selected_folder.strip():
            selected_folder = os.path.abspath(os.path.normpath(selected_folder.strip()))
        self.selected_folder = selected_folder
        
        # 如果工作目录切换了，重置检测标记，允许重新检测
        if old_folder != selected_folder:
            if hasattr(self, '_points_list_processing'):
                self._points_list_processing = False
            if hasattr(self, '_last_points_list_folder'):
                self._last_points_list_folder = None
            if hasattr(self, '_track_mode_processing'):
                self._track_mode_processing = False
            if hasattr(self, '_last_track_mode_folder'):
                self._last_track_mode_folder = None
        
        self._update_window_title()
        

        # 输出工作目录设置日志
        self.log(tr("current_workdir", "📂 当前工作目录：{path}").format(path=selected_folder))
        
        # 切换工作目录时先清理旧强迫场选择，避免残留
        if old_folder != selected_folder:
            for attr in ("selected_origin_file", "selected_current_file", "selected_level_file", "selected_ice_file"):
                if hasattr(self, attr):
                    setattr(self, attr, None)

        # 检测并更新强迫场按钮（风场、流场、水位场、海冰场）
        if hasattr(self, '_detect_and_fill_forcing_fields'):
            self._detect_and_fill_forcing_fields()
        
        # 同步第四步强迫场复选框显示状态（避免旧目录残留）
        if hasattr(self, '_update_forcing_fields_display'):
            try:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, self._update_forcing_fields_display)
            except Exception:
                pass
        
        # 检测并自动切换到嵌套网格模式（如果存在coarse和fine文件夹）
        if hasattr(self, '_check_and_switch_to_nested_grid'):
            self._check_and_switch_to_nested_grid()
        
        # 检测并自动切换到航迹模式（如果存在track_i.ww3文件）
        if hasattr(self, '_check_and_switch_to_track_mode'):
            self._check_and_switch_to_track_mode()
        
        # 检测并自动切换到谱空间逐点计算模式（如果存在points.list文件）
        # 自动检测不输出日志
        if hasattr(self, '_check_and_load_points_list'):
            self._check_and_load_points_list(silent=True)
        
        # 自动读取网格文件范围和精度，填充到第二步的输入框
        if hasattr(self, '_load_grid_info_to_step2'):
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(500, self._load_grid_info_to_step2)

        # 自动读取 ww3_shel.nml 的 TYPE%FIELD%LIST，更新谱分区输出方案
        if hasattr(self, '_load_output_scheme_from_ww3_shel'):
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(600, self._load_output_scheme_from_ww3_shel)
        
        # 列出目录内的所有文件
        if hasattr(self, '_list_directory_contents'):
            self._list_directory_contents(selected_folder)
        
        # 保存到最近打开的工作目录
        add_recent_workdir(selected_folder)
        
        # 更新服务器路径输入框，使用当前文件夹作为末尾路径
        if hasattr(self, 'ssh_dest_edit') and self.selected_folder:
            folder_name = os.path.basename(self.selected_folder)
            self.ssh_dest_edit.setText(f"{SERVER_PATH}{folder_name}")
        
        # 自动读取 server.sh 文件并设置 slurm 参数
        if hasattr(self, '_load_slurm_params_from_server_sh'):
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(100, self._load_slurm_params_from_server_sh)
        
        # 检测并更新波高文件按钮文本（静默，不显示日志）
        if hasattr(self, '_update_wave_height_file_buttons'):
            self._update_wave_height_file_buttons()
        
    def _show_info_bar(self, info_type, title, content):
        """显示 InfoBar 消息（通过信号调用，在主线程中执行）"""
        try:
            if info_type == "success":
                InfoBar.success(
                    title=title,
                    content=content,
                    duration=3000,
                    parent=self
                )
            elif info_type == "warning":
                InfoBar.warning(
                    title=title,
                    content=content,
                    duration=3000,
                    parent=self
                )
            elif info_type == "error":
                InfoBar.error(
                    title=title,
                    content=content,
                    duration=3000,
                    parent=self
                )
            else:  # info or default
                InfoBar.info(
                    title=title,
                    content=content,
                    duration=3000,
                    parent=self
                )
        except Exception as e:
            # 如果显示 InfoBar 失败，至少记录到日志
            try:
                self.log(f"⚠️ 显示提示信息失败：{e}")
            except:
                pass
