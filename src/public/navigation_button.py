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
from qfluentwidgets import NavigationItemPosition, NavigationWidget, FluentIcon, HeaderCardWidget, ComboBox, TableWidget
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
from public.work_folder_dialog import WorkFolderDialog
from plot.workers import _match_ww3_jason3_worker, _run_jason3_swh_worker, _make_wave_maps_worker

class NavigationMixin:
    """Navigation功能模块"""

    def _update_window_title(self):
        """更新窗口标题，包含工作目录"""
        from setting.language_manager import tr
        
        base_title = tr("app_title", "海浪模式 WAVEWATCH III 可视化运行软件")
        if self.selected_folder and isinstance(self.selected_folder, str) and self.selected_folder.strip():
            try:
                folder_path = os.path.abspath(self.selected_folder)
                # 将工作目录添加到标题中，使用分隔符
                title = f"{base_title}  |  {tr('work_directory', '工作目录')}: {folder_path}"
            except (TypeError, ValueError) as e:
                title = f"{base_title}  |  {tr('work_directory', '工作目录')}: {tr('invalid_path', '无效路径')}"
        else:
            title = f"{base_title}  |  {tr('work_directory', '工作目录')}: {tr('not_selected', '未选择')}"
        
        self.setWindowTitle(title)



    def update_folder_display(self, new_folder):
        """更新工作目录并更新窗口标题"""
        if not isinstance(new_folder, str):
            from setting.language_manager import tr
            self.log(tr("invalid_folder_path_type", "❌ 无效的文件夹路径类型: {type}").format(type=type(new_folder)))
            return
        self.selected_folder = new_folder
        self._update_window_title()

        # 更新服务器路径
        if hasattr(self, 'ssh_dest_edit') and self.selected_folder:
            folder_name = os.path.basename(self.selected_folder)
            self.ssh_dest_edit.setText(f"{SERVER_PATH}{folder_name}")


    def _connect_navigation_signals(self):
        """连接导航接口的信号，处理主页按钮点击"""
        try:
            # 方法1: 监听导航接口的当前项变化
            if hasattr(self.navigationInterface, 'currentItemChanged'):
                self.navigationInterface.currentItemChanged.connect(self._on_navigation_item_changed)

            # 方法2: 监听导航接口的显示项变化
            if hasattr(self.navigationInterface, 'displayModeChanged'):
                self.navigationInterface.displayModeChanged.connect(self._on_navigation_display_changed)

            # 方法3: 直接查找主页按钮并绑定点击事件
            self._bind_home_button_click()
        except Exception as e:
            import traceback
            traceback.print_exc()


    def _bind_home_button_click(self):
        """直接查找主页按钮并绑定点击事件"""
        try:
            # 查找所有导航项
            if hasattr(self.navigationInterface, 'items'):
                items = self.navigationInterface.items()
                for item in items:
                    # 检查是否是主页按钮
                    if hasattr(item, 'routeKey') and item.routeKey == self.main_interface_route_key:
                        # 绑定点击事件
                        if hasattr(item, 'clicked'):
                            item.clicked.connect(self.show_home)
                        elif hasattr(item, 'click'):
                            item.click.connect(self.show_home)
            # 或者通过路由键查找
            if hasattr(self.navigationInterface, 'widget'):
                home_widget = self.navigationInterface.widget(self.main_interface_route_key)
                if home_widget:
                    # 查找按钮并绑定
                    for btn in home_widget.findChildren(QtWidgets.QWidget):
                        if hasattr(btn, 'clicked'):
                            btn.clicked.connect(self.show_home)
        except Exception as e:
            pass


    def _on_navigation_item_changed(self, item):
        """当导航项改变时调用"""
        try:
            # 如果切换到主页界面（main_interface），调用 show_home
            route_key = None
            if hasattr(item, 'routeKey'):
                route_key = item.routeKey
            elif hasattr(item, 'objectName'):
                route_key = item.objectName()

            if route_key == self.main_interface_route_key:
                self.show_home()
        except Exception as e:
            pass


    def _on_navigation_display_changed(self, mode):
        """当导航显示模式改变时调用"""
        # 如果侧边栏试图展开，立即折叠回去
        # 检查侧边栏宽度，如果大于48像素（折叠状态），则折叠回去
        if hasattr(self, 'navigationInterface') and self.navigationInterface:
            nav_width = self.navigationInterface.width()
            if nav_width > 48:  # 如果宽度大于折叠状态的48像素，说明展开了
                if hasattr(self.navigationInterface, 'collapse'):
                    self.navigationInterface.collapse(useAni=False)


    def _on_stacked_widget_changed(self, index):
        """当 stackedWidget 的当前界面改变时调用"""
        try:
            # 如果切换到主页界面（main_interface），调用 show_home
            if hasattr(self, 'stackedWidget') and self.stackedWidget:
                current_widget = self.stackedWidget.widget(index)
                if current_widget and hasattr(current_widget, 'objectName'):
                    if current_widget.objectName() == 'main_interface':
                        self.show_home()
        except Exception as e:
            pass




    def show_folder_dialog(self):
        """显示文件夹选择对话框"""
        dialog = WorkFolderDialog(self, is_startup=False, current_folder=self.selected_folder)
        # 重要：在调用 exec() 之前，确保 finished 信号没有连接任何槽函数
        # 因为我们在 dialog.exec() 返回后会手动调用 _initialize_work_directory
        # 如果 finished 信号被连接，hide() 时会触发，导致重复调用
        try:
            dialog.finished.disconnect()  # 断开所有连接（如果有的话）
        except TypeError:
            # 如果没有连接，忽略错误
            pass
        
        result = dialog.exec()
        
        # exec() 返回后，再次确保信号已断开（防止在 exec() 期间被连接）
        try:
            dialog.finished.disconnect()
        except TypeError:
            pass

        # 无论返回值如何，都检查 selected_folder（因为 dialog.exec() 可能返回 0 而不是 1）
        if dialog.selected_folder:
            # 检查对话框返回的 selected_folder
            from setting.language_manager import tr
            if not dialog.selected_folder:
                self.log(tr("dialog_folder_path_empty", "❌ 对话框返回的文件夹路径为空"))
                return

            if not isinstance(dialog.selected_folder, str):
                self.log(tr("dialog_folder_path_invalid_type", "❌ 无效的文件夹路径类型: {type}, 值: {value}").format(type=type(dialog.selected_folder), value=dialog.selected_folder))
                return

            if not dialog.selected_folder.strip():
                self.log(tr("dialog_folder_path_empty_string", "❌ 对话框返回的文件夹路径为空字符串"))
                return

            # 更新工作目录
            old_folder = self.selected_folder
            new_folder = os.path.abspath(os.path.normpath(dialog.selected_folder.strip()))
            self.selected_folder = new_folder
            
            # 如果工作目录切换了，重置检测标记，允许重新检测
            if old_folder != new_folder:
                if hasattr(self, '_points_list_processing'):
                    self._points_list_processing = False
                if hasattr(self, '_last_points_list_folder'):
                    self._last_points_list_folder = None
                if hasattr(self, '_track_mode_processing'):
                    self._track_mode_processing = False
                if hasattr(self, '_last_track_mode_folder'):
                    self._last_track_mode_folder = None
            
            # 清除之前选择的所有强迫场文件（如果存在）
            if hasattr(self, 'selected_origin_file'):
                self.selected_origin_file = None
            if hasattr(self, 'selected_current_file'):
                self.selected_current_file = None
            if hasattr(self, 'selected_level_file'):
                self.selected_level_file = None
            if hasattr(self, 'selected_ice_file'):
                self.selected_ice_file = None
            
            # 记录工作目录选择（仅在切换时显示）
            from setting.language_manager import tr
            if old_folder != new_folder:
                self.log("\n"+"="*70)
                self.log(tr("workdir_switched", "📌 工作目录已切换为: {folder}").format(folder=new_folder))
            
            # 使用统一的初始化函数，避免重复逻辑和重复输出日志
            if hasattr(self, '_initialize_work_directory'):
                # 注意：_initialize_work_directory 会输出 current_workdir 日志并调用 _list_directory_contents
                # 所以这里不需要再次调用
                self._initialize_work_directory(self.selected_folder)
            else:
                # 如果没有 _initialize_work_directory，使用原有逻辑
                # 更新标题栏显示
                self.update_folder_display(self.selected_folder)

                # 检测并更新强迫场按钮（流场、水位场、海冰场）
                if hasattr(self, '_detect_and_fill_forcing_fields'):
                    self._detect_and_fill_forcing_fields()

                # 检测并自动切换到嵌套网格模式（如果存在coarse和fine文件夹）
                self._check_and_switch_to_nested_grid()

                # 检测并自动切换到航迹模式（如果存在track_i.ww3文件）
                self._check_and_switch_to_track_mode()

                # 检测并自动切换到谱空间逐点计算模式（如果存在points.list文件）
                self._check_and_load_points_list()
                
                # 自动读取网格文件范围和精度，填充到第二步的输入框（延迟执行，确保 UI 元素已初始化）
                if hasattr(self, '_load_grid_info_to_step2'):
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(500, self._load_grid_info_to_step2)

                # 列出目录内的所有文件
                self._list_directory_contents(self.selected_folder)

                # 保存到最近打开的工作目录
                from setting.config import add_recent_workdir
                add_recent_workdir(self.selected_folder)

                # 更新服务器路径
                if hasattr(self, 'ssh_dest_edit') and self.selected_folder:
                    folder_name = os.path.basename(self.selected_folder)
                    self.ssh_dest_edit.setText(f"{SERVER_PATH}{folder_name}")
                
                # 检测并更新风场文件按钮文本（静默，不显示日志）
                self._update_wind_field_buttons()
                
                # 检测并自动填充强迫场文件（符合规范的文件名）
                if hasattr(self, '_detect_and_fill_forcing_fields'):
                    self._detect_and_fill_forcing_fields()
                
                # 检测并更新二维谱文件按钮文本（静默，不显示日志）
                self._update_spectrum_file_button()
                
                # 检测并更新波高文件按钮文本（静默，不显示日志）
                self._update_wave_height_file_buttons()




    def _add_settings_button(self):
        """添加设置按钮到侧边栏底部"""
        from setting.language_manager import tr
        self.navigationInterface.addItem(
            routeKey='settings',
            icon=FluentIcon.SETTING,
            text=tr("settings", "设置"),
            onClick=self.show_settings,
            position=NavigationItemPosition.BOTTOM
        )    
  



    def _add_clear_log_button(self):
        """添加清空日志按钮到侧边栏底部（与设置按钮一起）"""
        from setting.language_manager import tr
        # 方法1: 尝试使用 addItem 添加导航项
        try:
            # 尝试使用 DELETE 或 CLEAR 图标，如果不存在则使用其他图标
            clear_icon = getattr(FluentIcon, 'DELETE', None) or getattr(FluentIcon, 'CLEAR', None) or getattr(FluentIcon, 'REMOVE', None) or FluentIcon.DELETE
            self.navigationInterface.addItem(
                routeKey='clear-log',
                icon=clear_icon,
                text=tr("clear_log", "清空日志"),
                onClick=self.clear_log,
                position=NavigationItemPosition.BOTTOM
            )
            return
        except Exception as e:
            pass

        # 方法2: 如果 addItem 不可用，尝试使用 addSubItem
        try:
            if hasattr(self.navigationInterface, 'addSubItem'):
                clear_icon = getattr(FluentIcon, 'DELETE', None) or getattr(FluentIcon, 'CLEAR', None) or getattr(FluentIcon, 'REMOVE', None) or FluentIcon.DELETE
                self.navigationInterface.addSubItem(
                    routeKey='clear-log',
                    icon=clear_icon,
                    text=tr("clear_log", "清空日志"),
                    onClick=self.clear_log,
                    position=NavigationItemPosition.BOTTOM
                )
        except:
            from setting.language_manager import tr
            print(tr("cannot_add_clear_log_button", "无法添加清空日志按钮，请检查 qfluentwidgets 版本"))


    def _add_open_workdir_button(self):
        """添加打开工作目录按钮到侧边栏顶部（主页按钮下面第二个）"""
        from setting.language_manager import tr
        # 方法1: 尝试使用 addItem 添加导航项
        try:
            # 使用 FOLDER 图标
            folder_icon = getattr(FluentIcon, 'LINK', None) or getattr(FluentIcon, 'FOLDER_OPEN', None) or getattr(FluentIcon, 'DOCUMENT', None) or FluentIcon.FOLDER
            self.navigationInterface.addItem(
                routeKey='open-workdir',
                icon=folder_icon,
                text=tr("open_workdir", "打开工作目录"),
                onClick=self.open_workdir,
                position=NavigationItemPosition.TOP
            )
            return
        except Exception as e:
            pass


    def _add_choose_workdir_button(self):
        """添加选择工作目录按钮到侧边栏顶部（主页按钮下面第三个）"""
        from setting.language_manager import tr
        # 方法1: 尝试使用 addItem 添加导航项
        try:
            # 使用 FOLDER_ADD 图标
            folder_add_icon = getattr(FluentIcon, 'FOLDER_ADD', None) or getattr(FluentIcon, 'FOLDER', None) or FluentIcon.DOCUMENT
            self.navigationInterface.addItem(
                routeKey='choose-workdir',
                icon=folder_add_icon,
                text=tr("choose_workdir", "选择工作目录"),
                onClick=self.show_folder_dialog,
                position=NavigationItemPosition.TOP
            )
            return
        except Exception as e:
            pass

        # 方法2: 如果 addItem 不可用，尝试使用 addSubItem


    def _add_plot_button(self):
        """添加科研绘图按钮到侧边栏顶部（主页按钮下面第一个）"""
        try:
            # 使用 IOT 图标
            try:
                iot_icon = FluentIcon.IOT
            except AttributeError:
                # 如果 IOT 不存在，使用备用图标
                iot_icon = getattr(FluentIcon, 'CHART', None) or getattr(FluentIcon, 'GRAPH', None) or FluentIcon.DOCUMENT
            from setting.language_manager import tr
            self.navigationInterface.addItem(
                routeKey='plot',
                icon=iot_icon,
                text=tr("plotting_research_plotting", "科研绘图"),
                onClick=self.show_plot_page,
                position=NavigationItemPosition.TOP
            )
            return
        except Exception as e:
            pass

    def show_plot_page(self):
        """切换到绘图页面（只切换左侧区域，右侧日志保持不变）"""
        try:
            # 只切换左侧的 left_stacked，右侧日志保持不变
            if hasattr(self, 'left_stacked') and self.left_stacked:
                # 绘图页面是索引2（索引0是主页，索引1是设置页面）
                if self.left_stacked.count() >= 3:
                    self.left_stacked.setCurrentIndex(2)  # 切换到绘图页面（索引2）
            
            # 检测并更新风场文件按钮文本（静默，不显示日志）
            self._update_wind_field_buttons()
            
            # 检测并更新二维谱文件按钮文本（静默，不显示日志）
            self._update_spectrum_file_button()
            
            # 检测并更新波高文件按钮文本（静默，不显示日志）
            self._update_wave_height_file_buttons()

            # 检测并更新 JASON3 风场/波高按钮文本（静默，不显示日志）
            self._update_jason3_file_buttons()
        except Exception as e:
            import traceback
            traceback.print_exc()

    def _add_tools_button(self):
        """添加常用工具按钮到侧边栏顶部"""
        try:
            from setting.language_manager import tr
            self.navigationInterface.addItem(
                routeKey='tools',
                icon=FluentIcon.DEVELOPER_TOOLS,
                text=tr("tools", "常用工具"),
                onClick=self.show_tools_page,
                position=NavigationItemPosition.TOP
            )
        except Exception as e:
            pass
    
    def show_tools_page(self):
        """切换到工具页面（只切换左侧区域，右侧日志保持不变）"""
        try:
            # 只切换左侧的 left_stacked，右侧日志保持不变
            if hasattr(self, 'left_stacked') and self.left_stacked:
                # 工具页面是索引3（索引0是主页，索引1是设置页面，索引2是绘图页面）
                if self.left_stacked.count() > 3:
                    self.left_stacked.setCurrentIndex(3)  # 切换到工具页面（索引3）
        except Exception as e:
            import traceback
            traceback.print_exc()

    def _add_all_navigation_buttons(self):
        """添加所有导航按钮到侧边栏（按指定顺序）"""
        # 按钮顺序：主页、打开工作目录、选择工作目录、科研绘图、常用工具、设置、清除日志
        # 注意：主页按钮已经在 addSubInterface 中添加，这里只添加其他按钮
        
        # 1. 打开工作目录
        if hasattr(self, '_add_open_workdir_button'):
            self._add_open_workdir_button()
        
        # 2. 选择工作目录
        if hasattr(self, '_add_choose_workdir_button'):
            self._add_choose_workdir_button()
        
        # 3. 科研绘图
        if hasattr(self, '_add_plot_button'):
            self._add_plot_button()
        
        # 4. 常用工具
        self._add_tools_button()
        
        # 5. 设置（底部）
        if hasattr(self, '_add_settings_button'):
            self._add_settings_button()
        
        # 6. 清除日志（底部）
        if hasattr(self, '_add_clear_log_button'):
            self._add_clear_log_button()






    def show_settings(self):
        """显示设置页面"""
        try:
            # 只切换左侧的 left_stacked，右侧日志保持不变
            if hasattr(self, 'left_stacked') and self.left_stacked:
                if self.left_stacked.count() >= 2:
                    self.left_stacked.setCurrentIndex(1)  # 切换到设置页面（索引1）
        except Exception as e:
            import traceback
            traceback.print_exc()


    def _update_wind_field_buttons(self):
        """检测并更新风场文件按钮文本（静默，不显示日志）"""
        try:
            if hasattr(self, 'selected_folder') and self.selected_folder:
                import os
                import glob
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
                    
                    # 更新按钮文本（step1 + plot + home）
                    if hasattr(self, '_set_wind_file_button_text'):
                        self._set_wind_file_button_text(display_name, filled=True)
                    else:
                        if hasattr(self, 'btn_choose_wind_file_home') and self.btn_choose_wind_file_home:
                            self.btn_choose_wind_file_home.setText(display_name)
                        if hasattr(self, 'btn_choose_wind_file') and self.btn_choose_wind_file:
                            self.btn_choose_wind_file.setText(display_name)
                        if hasattr(self, 'btn_choose_wind_file_plot') and self.btn_choose_wind_file_plot:
                            self.btn_choose_wind_file_plot.setText(display_name)
                    
                    # 同时更新 selected_origin_file，以便生成风场图时使用
                    if not hasattr(self, 'selected_origin_file') or not self.selected_origin_file:
                        self.selected_origin_file = data_nc_path
                else:
                    # 如果工作目录中不存在 wind.nc 或 wind_*.nc，清除风场文件相关状态
                    # 重置按钮文本为默认值
                    from setting.language_manager import tr
                    default_text = tr("step1_choose_wind", "选择风场文件")
                    if hasattr(self, '_set_wind_file_button_text'):
                        self._set_wind_file_button_text(default_text, filled=False)
                    else:
                        if hasattr(self, 'btn_choose_wind_file_home') and self.btn_choose_wind_file_home:
                            self.btn_choose_wind_file_home.setText(default_text)
                        if hasattr(self, 'btn_choose_wind_file') and self.btn_choose_wind_file:
                            self.btn_choose_wind_file.setText(default_text)
                        if hasattr(self, 'btn_choose_wind_file_plot') and self.btn_choose_wind_file_plot:
                            self.btn_choose_wind_file_plot.setText(default_text)
                    
                    # 清除 selected_origin_file（如果它指向的是旧工作目录的文件）
                    if hasattr(self, 'selected_origin_file') and self.selected_origin_file:
                        # 检查 selected_origin_file 是否在当前工作目录中
                        if not os.path.exists(self.selected_origin_file) or \
                           (os.path.dirname(os.path.abspath(self.selected_origin_file)) != 
                            os.path.abspath(self.selected_folder)):
                            self.selected_origin_file = None
            else:
                # 如果没有工作目录，清除风场文件相关状态
                from setting.language_manager import tr
                default_text = tr("step1_choose_wind", "选择风场文件")
                if hasattr(self, '_set_wind_file_button_text'):
                    self._set_wind_file_button_text(default_text, filled=False)
                else:
                    if hasattr(self, 'btn_choose_wind_file_home') and self.btn_choose_wind_file_home:
                        self.btn_choose_wind_file_home.setText(default_text)
                    if hasattr(self, 'btn_choose_wind_file') and self.btn_choose_wind_file:
                        self.btn_choose_wind_file.setText(default_text)
                    if hasattr(self, 'btn_choose_wind_file_plot') and self.btn_choose_wind_file_plot:
                        self.btn_choose_wind_file_plot.setText(default_text)
                
                if hasattr(self, 'selected_origin_file'):
                    self.selected_origin_file = None
        except Exception:
            pass  # 静默处理错误

    def _update_spectrum_file_button(self):
        """检测并更新二维谱文件按钮文本（静默，不显示日志）"""
        try:
            if hasattr(self, 'selected_folder') and self.selected_folder:
                import os
                import glob
                spec_files = glob.glob(os.path.join(self.selected_folder, "ww3*spec*nc"))
                if spec_files:
                    file_name = os.path.basename(spec_files[0])
                    if len(file_name) > 30:
                        display_name = file_name[:27] + "..."
                    else:
                        display_name = file_name
                    
                    # 更新科研绘图页面按钮
                    if hasattr(self, 'btn_choose_spectrum_file') and self.btn_choose_spectrum_file:
                        self.btn_choose_spectrum_file.setText(display_name)
                        if hasattr(self, '_set_plot_button_filled'):
                            self._set_plot_button_filled(self.btn_choose_spectrum_file, True)
                    
                    # 同时更新 selected_spectrum_file，以便生成二维谱图时使用
                    if not hasattr(self, 'selected_spectrum_file') or not self.selected_spectrum_file:
                        self.selected_spectrum_file = spec_files[0]
                    
                    # 读取站点信息
                    if hasattr(self, '_load_spectrum_stations'):
                        self._load_spectrum_stations(spec_files[0])
                    # 显示点列表表格
                    if hasattr(self, 'spectrum_stations_table'):
                        self.spectrum_stations_table.setVisible(True)
        except Exception:
            pass  # 静默处理错误

    def _update_wave_height_file_buttons(self):
        """检测并更新波高文件按钮文本（静默，不显示日志）"""
        try:
            if hasattr(self, 'selected_folder') and self.selected_folder:
                import os
                import glob
                # 查找 ww3*.nc 文件（排除 spec 文件）
                wave_files = glob.glob(os.path.join(self.selected_folder, "ww3*.nc"))
                # 排除 spec 文件
                wave_files = [f for f in wave_files if "spec" not in os.path.basename(f).lower()]
                if wave_files:
                    file_name = os.path.basename(wave_files[0])
                    if len(file_name) > 30:
                        display_name = file_name[:27] + "..."
                    else:
                        display_name = file_name
                    
                    # 更新主页按钮
                    if hasattr(self, 'btn_choose_wave_height_file_home') and self.btn_choose_wave_height_file_home:
                        self.btn_choose_wave_height_file_home.setText(display_name)
                    
                    # 更新科研绘图页面按钮
                    if hasattr(self, 'btn_choose_wave_height_file') and self.btn_choose_wave_height_file:
                        self.btn_choose_wave_height_file.setText(display_name)
                        if hasattr(self, '_set_plot_button_filled'):
                            self._set_plot_button_filled(self.btn_choose_wave_height_file, True)
                    
                    # 同时更新 selected_wave_height_file，以便生成波高图时使用
                    if not hasattr(self, 'selected_wave_height_file') or not self.selected_wave_height_file:
                        self.selected_wave_height_file = wave_files[0]
        except Exception:
            pass  # 静默处理错误

    def _update_jason3_file_buttons(self):
        """检测并更新 JASON3 风场/波高文件按钮文本（静默，不显示日志）"""
        try:
            import os
            import glob
            from setting.language_manager import tr

            # 风场按钮
            wind_path = None
            if hasattr(self, 'selected_folder') and self.selected_folder:
                if getattr(self, 'selected_origin_file', None) and os.path.exists(self.selected_origin_file):
                    wind_path = self.selected_origin_file
                else:
                    default_wind = os.path.join(self.selected_folder, "wind.nc")
                    if os.path.exists(default_wind):
                        wind_path = default_wind
                    else:
                        wind_candidates = glob.glob(os.path.join(self.selected_folder, "wind_*.nc"))
                        if wind_candidates:
                            wind_path = sorted(wind_candidates)[0]

            if wind_path:
                self.selected_origin_file = wind_path
                if hasattr(self, 'btn_choose_jason3_wind_file') and self.btn_choose_jason3_wind_file:
                    file_name = os.path.basename(wind_path)
                    display_name = file_name[:27] + "..." if len(file_name) > 30 else file_name
                    self.btn_choose_jason3_wind_file.setText(display_name)
                    if hasattr(self, '_set_plot_button_filled'):
                        self._set_plot_button_filled(self.btn_choose_jason3_wind_file, True)
            else:
                if hasattr(self, 'btn_choose_jason3_wind_file') and self.btn_choose_jason3_wind_file:
                    default_text = tr("step1_choose_wind", "选择风场文件")
                    self.btn_choose_jason3_wind_file.setText(default_text)
                    if hasattr(self, '_set_plot_button_filled'):
                        self._set_plot_button_filled(self.btn_choose_jason3_wind_file, False)

            # 波高按钮
            wave_path = None
            if hasattr(self, 'selected_folder') and self.selected_folder:
                if getattr(self, 'selected_wave_height_file', None) and os.path.exists(self.selected_wave_height_file):
                    wave_path = self.selected_wave_height_file
                else:
                    wave_candidates = glob.glob(os.path.join(self.selected_folder, "ww3*.nc"))
                    wave_candidates = [p for p in wave_candidates if "spec" not in os.path.basename(p).lower()]
                    if wave_candidates:
                        wave_path = sorted(wave_candidates)[0]

            if wave_path:
                self.selected_wave_height_file = wave_path
                if hasattr(self, 'btn_choose_jason3_wave_file') and self.btn_choose_jason3_wave_file:
                    file_name = os.path.basename(wave_path)
                    display_name = file_name[:27] + "..." if len(file_name) > 30 else file_name
                    self.btn_choose_jason3_wave_file.setText(display_name)
                    if hasattr(self, '_set_plot_button_filled'):
                        self._set_plot_button_filled(self.btn_choose_jason3_wave_file, True)
            else:
                if hasattr(self, 'btn_choose_jason3_wave_file') and self.btn_choose_jason3_wave_file:
                    default_text = tr("plotting_choose_wave_height", "选择波高文件")
                    self.btn_choose_jason3_wave_file.setText(default_text)
                    if hasattr(self, '_set_plot_button_filled'):
                        self._set_plot_button_filled(self.btn_choose_jason3_wave_file, False)
        except Exception:
            pass  # 静默处理错误

    def show_home(self):
        """显示主页"""
        try:
            # 首先确保 stackedWidget 切换到 main_interface
            if hasattr(self, 'stackedWidget') and self.stackedWidget:
                # 查找 main_interface 的索引
                for i in range(self.stackedWidget.count()):
                    widget = self.stackedWidget.widget(i)
                    if widget and hasattr(widget, 'objectName') and widget.objectName() == 'main_interface':
                        self.stackedWidget.setCurrentIndex(i)
                        break
            
            # 然后切换左侧的 left_stacked，右侧日志保持不变
            if hasattr(self, 'left_stacked') and self.left_stacked:
                if self.left_stacked.count() >= 1:
                    self.left_stacked.setCurrentIndex(0)  # 切换到主页（索引0）
            
            # 检测并更新风场文件按钮文本（静默，不显示日志）
            self._update_wind_field_buttons()
            
            # 检测并更新波高文件按钮文本（静默，不显示日志）
            self._update_wave_height_file_buttons()
        except Exception as e:
            import traceback
            traceback.print_exc()

    def open_workdir(self):
        """打开当前工作目录"""
        from setting.language_manager import tr
        try:
            if not self.selected_folder or not isinstance(self.selected_folder, str):
                InfoBar.warning(
                    title=tr("tip", "提示"),
                    content=tr("workdir_not_set", "工作目录未设置"),
                    duration=2000,
                    parent=self
                )
                return

            if not os.path.exists(self.selected_folder):
                InfoBar.warning(
                    title=tr("tip", "提示"),
                    content=tr("workdir_not_exists", "工作目录不存在：{path}").format(path=self.selected_folder),
                    duration=2000,
                    parent=self
                )
                return

            # 判断是否切换了工作目录
            if not hasattr(self, '_last_opened_workdir'):
                self._last_opened_workdir = None
            
            # 规范化路径进行比较
            current_folder = os.path.normpath(self.selected_folder)
            last_folder = os.path.normpath(self._last_opened_workdir) if self._last_opened_workdir else None
            
            is_switched = last_folder is not None and current_folder != last_folder

            # 使用系统默认方式打开文件夹
            system = platform.system().lower()
            if "windows" in system:
                os.startfile(self.selected_folder)
            elif "darwin" in system:  # macOS
                subprocess.run(["open", self.selected_folder])
            else:  # Linux
                subprocess.run(["xdg-open", self.selected_folder])

            # 更新上次打开的工作目录
            self._last_opened_workdir = self.selected_folder
        except Exception as e:
            from setting.language_manager import tr
            self.log(tr("open_workdir_failed", "❌ 打开工作目录失败：{error}").format(error=e))
            InfoBar.error(
                title=tr("error", "错误"),
                content=tr("open_workdir_failed", "打开工作目录失败：{error}").format(error=e),
                duration=3000,
                parent=self
            )

    def _list_directory_contents(self, directory_path, indent="", in_photo_dir=False):
        """列出目录内容，过滤隐藏文件，显示修改时间，photo目录下显示所有文件"""
        from setting.language_manager import tr
        try:
            if not os.path.exists(directory_path):
                self.log(tr("directory_not_exists", "⚠️ 目录不存在：{path}").format(path=directory_path))
                return

            files = os.listdir(directory_path)
            if not files:
                if indent == "":  # 只在顶层目录为空时显示
                    from setting.language_manager import tr
                    self.log(tr("workdir_empty", "📁 当前工作目录为空"))
                return

            # 判断是否是 photo 目录或其子目录
            is_photo_dir_now = os.path.basename(directory_path) == "photo" or in_photo_dir

            # 过滤文件：排除以 . 开头的文件（photo 目录及其子目录除外）
            filtered_files = []
            for file in files:
                # photo 目录及其子目录下显示所有文件，其他目录过滤掉隐藏文件
                if is_photo_dir_now or not file.startswith('.'):
                    filtered_files.append(file)


            if indent == "":  # 只在顶层显示标题
                from setting.language_manager import tr
                self.log(tr("workdir_contents", "📁 工作目录内容（共 {count} 项）：").format(count=len(filtered_files)))

            # 按名称排序
            files_sorted = sorted(filtered_files)

            for file in files_sorted:
                file_path = os.path.join(directory_path, file)
                try:
                    # 获取修改时间
                    mtime = os.path.getmtime(file_path)
                    from datetime import datetime
                    mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

                    if os.path.isdir(file_path):
                        self.log(f"{indent}  📂 {file}/ ({mtime_str})")
                        # 如果是 photo 目录或其子目录，递归显示其内容
                        if file == "photo" or is_photo_dir_now:
                            self._list_directory_contents(file_path, indent + "    ", in_photo_dir=True)
                    else:
                        # 显示文件大小和修改时间
                        try:
                            size = os.path.getsize(file_path)
                            if size < 1024:
                                size_str = f"{size} B"
                            elif size < 1024 * 1024:
                                size_str = f"{size / 1024:.2f} KB"
                            elif size < 1024 * 1024 * 1024:
                                size_str = f"{size / (1024 * 1024):.2f} MB"
                            else:
                                size_str = f"{size / (1024 * 1024 * 1024):.2f} GB"
                            self.log(f"{indent}  📄 {file} ({size_str}, {mtime_str})")
                        except Exception:
                            self.log(f"{indent}  📄 {file} ({mtime_str})")
                except Exception as e:
                    # 如果获取信息失败，至少显示文件名
                    if os.path.isdir(file_path):
                        self.log(f"{indent}  📂 {file}/")
                    else:
                        self.log(f"{indent}  📄 {file}")
        except Exception as e:
            from setting.language_manager import tr
            self.log(tr("cannot_list_directory", "⚠️ 无法列出目录内容：{error}").format(error=e))

    def show_current_directory_files(self):
        """显示当前工作目录的文件"""
        from setting.language_manager import tr
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            InfoBar.warning(
                title=tr("tip", "提示"),
                content=tr("workdir_not_set", "工作目录未设置"),
                duration=2000,
                parent=self
            )
            return

        if not os.path.exists(self.selected_folder):
            InfoBar.warning(
                title=tr("tip", "提示"),
                content=tr("workdir_not_exists", "工作目录不存在：{path}").format(path=self.selected_folder),
                duration=2000,
                parent=self
            )
            return

        # 显示目录内容
        from setting.language_manager import tr
        self.log("=" * 70)
        self.log(tr("current_workdir", "📂 当前工作目录：{path}").format(path=self.selected_folder))
        self._list_directory_contents(self.selected_folder)
        self.log("=" * 70)


