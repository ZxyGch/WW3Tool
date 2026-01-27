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
import sys
import os
# 添加 main 目录到 Python 路径，以便导入 setting 和 plot 模块
main_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if main_dir not in sys.path:
    sys.path.insert(0, main_dir)
from setting.config import *
from plot.workers import _match_ww3_jason3_worker, _run_jason3_swh_worker, _make_wave_maps_worker

class Style:
    """Ui Style功能模块"""

    def _setup_theme_monitor(self):
        """设置系统主题变化监听"""
        try:
            setup_success = False
            if not hasattr(self, '_theme_mode'):
                self._theme_mode = "AUTO"

            # 方法1: 使用 qfluentwidgets 的 qconfig.themeChanged 信号
            try:
                from qfluentwidgets import qconfig
                if hasattr(qconfig, 'themeChanged'):
                    qconfig.themeChanged.connect(self._on_theme_changed)
                    setup_success = True
                else:
                    self.log("⚠️ qconfig 没有 themeChanged 信号")
            except ImportError as e:
                self.log(f"⚠️ 无法导入 qconfig: {e}")
            except Exception as e:
                self.log(f"⚠️ qconfig 设置失败: {e}")

            # 方法2: 同时监听 QApplication 的 paletteChanged 信号（备用）
            try:
                app = QApplication.instance()
                if app and hasattr(app, 'paletteChanged'):
                    app.paletteChanged.connect(self._on_palette_changed)
                    setup_success = True
                else:
                    self.log("⚠️ QApplication 没有 paletteChanged 信号")
            except Exception as e:
                self.log(f"⚠️ paletteChanged 设置失败: {e}")

            # 方法3: 使用定时器定期检查主题变化（作为最后的备用方案）
            try:
                self._theme_check_timer = QtCore.QTimer()
                self._theme_check_timer.timeout.connect(self._check_theme_change)
                self._theme_check_timer.start(1000)  # 每秒检查一次
                setup_success = True
            except Exception as e:
                self.log(f"⚠️ 定时器设置失败: {e}")

            # 初始化主题状态
            self._update_theme_state()
            # 不再输出主题状态日志，保持静默
            current_theme = "深色" if self._dark else "浅色"

            # 确保所有组件都有正确的样式（延迟执行，确保所有组件都已创建）
            QtCore.QTimer.singleShot(1000, lambda: self._update_all_styles())

            if not setup_success:
                self.log("❌ 所有主题监听方法都设置失败")
        except Exception as e:
            # 如果监听失败，输出错误信息
            self.log(f"❌ 设置主题监听失败: {e}")
            import traceback
            self.log(traceback.format_exc())


    def _update_theme_state(self):
        """更新当前主题状态"""
        try:
            from qfluentwidgets import isDarkTheme
            self._dark = isDarkTheme()
            self._last_theme_state = self._dark
        except:
            pass


    def _on_theme_changed(self, theme):
        """当 qconfig 主题变化时调用"""
        try:
            from qfluentwidgets import isDarkTheme
            current_dark = isDarkTheme()

            # 检查主题是否真的改变了
            if self._last_theme_state is not None and current_dark != self._last_theme_state:
                # 主题已改变，更新所有样式
                self._dark = current_dark
                self._last_theme_state = current_dark

                # 先调用 setTheme 来切换背景色
                QtCore.QTimer.singleShot(0, lambda: self._sync_fluent_theme(current_dark))

                # 立即更新我们的自定义样式（避免默认样式闪现）
                self._update_all_styles()
            else:
                # 即使主题没变，也更新一次样式（确保同步）
                # 但不要每次都更新，避免卡顿
                if not hasattr(self, '_last_style_update_time') or time.time() - self._last_style_update_time > 2:
                    self._dark = current_dark
                    self._last_theme_state = current_dark
                    self._last_style_update_time = time.time()
                    QtCore.QTimer.singleShot(50, lambda: self._update_all_styles())
        except Exception as e:
            self.log(f"❌ _on_theme_changed 出错: {e}")
            import traceback
            self.log(traceback.format_exc())


    def _on_palette_changed(self, palette):
        """当系统调色板变化时调用（备用方法）"""
        try:
            # 使用调色板检测主题（最可靠的方法）
            app = QApplication.instance()
            if app:
                # 获取窗口背景色来判断主题
                window_color = app.palette().color(app.palette().ColorRole.Window)
                brightness = window_color.red() * 0.299 + window_color.green() * 0.587 + window_color.blue() * 0.114
                current_dark = brightness < 128  # 亮度小于128认为是深色

                # 检查主题是否真的改变了
                if self._last_theme_state is not None and current_dark != self._last_theme_state:
                    self._dark = current_dark
                    self._last_theme_state = current_dark

                    # 先调用 setTheme 来切换背景色
                    QtCore.QTimer.singleShot(0, lambda: self._sync_fluent_theme(current_dark))

                    # 立即更新我们的自定义样式（避免默认样式闪现）
                    self._update_all_styles()
        except Exception as e:
            self.log(f"❌ _on_palette_changed 出错: {e}")
            import traceback
            self.log(traceback.format_exc())


    def _sync_fluent_theme(self, is_dark):
        """同步 qfluentwidgets 主题（用于切换背景色，然后立即重新应用自定义样式）"""
        try:
            from qfluentwidgets import setTheme, Theme
            # 调用 setTheme 来切换背景色
            setTheme(Theme.DARK if is_dark else Theme.LIGHT)

            # 清除 stackedWidget 和 main_interface 的手动背景色设置，让 setTheme() 的样式生效
            # 同时确保没有边框
            try:
                if hasattr(self, 'stackedWidget') and self.stackedWidget:
                    current_style = self.stackedWidget.styleSheet()
                    if current_style:
                        import re
                        # 移除背景色和边框
                        new_style = re.sub(r'background-color:\s*[^;]+;?', '', current_style)
                        new_style = re.sub(r'border[^:]*:\s*[^;]+;?', '', new_style)
                        if new_style.strip():
                            self.stackedWidget.setStyleSheet(new_style.strip() + "; border: none;")
                        else:
                            self.stackedWidget.setStyleSheet("border: none;")
                    else:
                        self.stackedWidget.setStyleSheet("border: none;")

                main_interface = self.findChild(QWidget, "main_interface")
                if main_interface:
                    current_style = main_interface.styleSheet()
                    if current_style and "background-color:" in current_style and "background-color: transparent" not in current_style:
                        import re
                        # 移除背景色和边框
                        new_style = re.sub(r'background-color:\s*[^;]+;?', '', current_style)
                        new_style = re.sub(r'border[^:]*:\s*[^;]+;?', '', new_style)
                        if new_style.strip():
                            main_interface.setStyleSheet(new_style.strip() + "; border: none;")
                        else:
                            main_interface.setStyleSheet("border: none;")
                    elif not current_style:
                        main_interface.setStyleSheet("border: none;")
            except:
                pass

            # 立即重新应用我们的自定义样式，确保不被覆盖
            QtCore.QTimer.singleShot(50, lambda: self._update_all_styles())
        except:
            pass


    def _check_theme_change(self):
        """定期检查主题是否变化（备用方法）"""
        try:
            # 使用调色板检测（最可靠的方法）
            app = QApplication.instance()
            if not app:
                return

            window_color = app.palette().color(app.palette().ColorRole.Window)
            brightness = window_color.red() * 0.299 + window_color.green() * 0.587 + window_color.blue() * 0.114
            current_dark = brightness < 128

            # 如果还没有初始化状态，先初始化
            if self._last_theme_state is None:
                self._dark = current_dark
                self._last_theme_state = current_dark
                return

            # 检查主题是否真的改变了
            if current_dark != self._last_theme_state:
                self.log(f"🔄 检测到系统主题变化（定时检查）: {'深色' if current_dark else '浅色'} -> 开始更新样式...")
                self._dark = current_dark
                self._last_theme_state = current_dark

                # 先调用 setTheme 来切换背景色
                QtCore.QTimer.singleShot(0, lambda: self._sync_fluent_theme(current_dark))

                # 立即更新我们的自定义样式（避免默认样式闪现）
                self._update_all_styles()
            # 注意：这里不输出日志，避免每秒都输出日志
        except Exception as e:
            # 只在出错时输出日志（限制频率）
            if not hasattr(self, '_check_error_count'):
                self._check_error_count = 0
            self._check_error_count += 1
            if self._check_error_count <= 3:  # 只输出前3次错误
                try:
                    self.log(f"⚠️ 定时检查主题变化时出错: {e}")
                except:
                    pass  # 如果 log 也失败，静默处理


    def _get_button_style(self):
        """根据当前主题获取按钮样式"""
        # 使用 self._dark 而不是 isDarkTheme()，确保使用正确的主题状态
        # 如果 _dark 还未初始化，使用 isDarkTheme() 作为后备
        if not hasattr(self, '_dark'):
            try:
                from qfluentwidgets import isDarkTheme
                is_dark = isDarkTheme()
            except:
                is_dark = False
        else:
            is_dark = self._dark

        if is_dark:
            # 黑暗模式样式
            return """
                PrimaryPushButton {
                    background-color: #2D2D2D;
                    border: 1px solid #404040;
                    border-radius: 4px;
                    min-height: 20px;
                    padding: 8px 16px;
                    color: #FFFFFF;
                }
                PrimaryPushButton:hover {
                    background-color: #3D3D3D;
                }
                PrimaryPushButton:pressed {
                    background-color: #353535;
                }
                PrimaryPushButton:disabled {
                    background-color: #1D1D1D;
                    border: 1px solid #2D2D2D;
                    color: #666666;
                }
                PrimaryPushButton[filled="true"] {
                    color: #2E6BD9;
                }
            """
        else:
            # 浅色模式样式
            return """
                PrimaryPushButton {
                    background-color: #F5F5F5;
                    border: 1px solid #E0E0E0;
                    border-radius: 4px;
                    min-height: 20px;
                    padding: 8px 16px;
                }
                PrimaryPushButton:hover {
                    background-color: #EEEEEE;
                }
                PrimaryPushButton:pressed {
                    background-color: #E8E8E8;
                }
                PrimaryPushButton:disabled {
                    background-color: #E0E0E0;
                    color: #999999;
                }
                PrimaryPushButton[filled="true"] {
                    color: #2E6BD9;
                }
            """


    def _get_input_style(self):
        """根据当前主题获取输入框样式"""
        # 使用 self._dark 而不是 isDarkTheme()，确保使用正确的主题状态
        # 如果 _dark 还未初始化，使用 isDarkTheme() 作为后备
        if not hasattr(self, '_dark'):
            try:
                from qfluentwidgets import isDarkTheme
                is_dark = isDarkTheme()
            except:
                is_dark = False
        else:
            is_dark = self._dark

        if is_dark:
            # 黑暗模式样式
            return """
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
            # 浅色模式样式
            return """
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


    def _get_combo_style(self):
        """根据当前主题获取下拉框样式"""
        # 使用 self._dark 而不是 isDarkTheme()，确保使用正确的主题状态
        # 如果 _dark 还未初始化，使用 isDarkTheme() 作为后备
        if not hasattr(self, '_dark'):
            try:
                from qfluentwidgets import isDarkTheme
                is_dark = isDarkTheme()
            except:
                is_dark = False
        else:
            is_dark = self._dark

        if is_dark:
            # 黑暗模式样式
            return """
                ComboBox {
                    background-color: #2D2D2D;
                    border: 1px solid #404040;
                    border-radius: 4px;
                    padding: 4px 8px;
                    padding-left: 8px;
                    color: #FFFFFF;
                    text-align: left;
                }
                ComboBox:focus {
                    border: 1px solid #404040;
                }
                ComboBox::drop-down {
                    border: none;
                }
                ComboBox QAbstractItemView {
                    background-color: #2D2D2D;
                    border: 1px solid #404040;
                    color: #FFFFFF;
                    text-align: left;
                }
                ComboBox::item {
                    text-align: left;
                    padding-left: 8px;
                }
                ComboBox::item:selected {
                    background-color: #404040;
                }
            """
        else:
            # 浅色模式样式
            return """
                ComboBox {
                    background-color: #FFFFFF;
                    border: 1px solid #D0D0D0;
                    border-radius: 4px;
                    padding: 4px 8px;
                    padding-left: 8px;
                    color: #000000;
                    text-align: left;
                }
                ComboBox:focus {
                    border: 1px solid #D0D0D0;
                }
                ComboBox::drop-down {
                    border: none;
                }
                ComboBox QAbstractItemView {
                    background-color: #FFFFFF;
                    border: 1px solid #D0D0D0;
                    color: #000000;
                    text-align: left;
                }
                ComboBox::item {
                    text-align: left;
                    padding-left: 0px;
                }
                ComboBox::item:selected {
                    background-color: #E0E0E0;
                }
            """


    def _update_textedit_style(self, text_edit):
        """根据当前主题更新TextEdit的样式"""
        if not text_edit:
            return

        # 使用 self._dark 而不是 isDarkTheme()，确保使用正确的主题状态
        # 如果 _dark 还未初始化，使用 isDarkTheme() 作为后备
        if not hasattr(self, '_dark'):
            try:
                from qfluentwidgets import isDarkTheme
                is_dark = isDarkTheme()
            except:
                is_dark = False
        else:
            is_dark = self._dark

        if is_dark:
            # 黑暗模式：使用灰色边框和深灰色背景（与 HeaderCardWidget 一致）
            border_color = "#404040"
            bg_color = "#2d2d2d"  # 深灰色背景，与 HeaderCardWidget 在深色主题下的背景色一致
        else:
            # 浅色模式：使用浅灰色边框和浅灰色背景（与 HeaderCardWidget 一致）
            border_color = "#D0D0D0"
            bg_color = "transparent"  # 浅灰色背景，与 HeaderCardWidget 在浅色主题下的背景色一致

        text_edit.setStyleSheet(f"""
            PlainTextEdit {{
                border: 0.5px solid {border_color} !important;
                border-radius: 4px;
                background-color: {bg_color};
                padding-left: 2px;
            }}
            PlainTextEdit:focus {{
                border: 0.5px solid {border_color} !important;
                padding-left: 2px;
            }}
            PlainTextEdit:hover {{
                border: 0.5px solid {border_color} !important;
                padding-left: 2px;
            }}
        """)


    def _update_separator_style(self, separator):
        """根据当前主题更新分割线的样式"""
        if not separator:
            return

        # 使用 self._dark 而不是 isDarkTheme()，确保使用正确的主题状态
        # 如果 _dark 还未初始化，使用 isDarkTheme() 作为后备
        if not hasattr(self, '_dark'):
            try:
                from qfluentwidgets import isDarkTheme
                is_dark = isDarkTheme()
            except:
                is_dark = False
        else:
            is_dark = self._dark

        if is_dark:
            # 黑暗模式：使用深灰色
            separator_color = "#404040"
        else:
            # 浅色模式：使用浅灰色
            separator_color = "#D0D0D0"

        # 设置样式，只设置背景色，高度和宽度由代码控制
        # 添加高度和宽度限制，防止溢出
        # 强制高度为1px，确保不会因为样式表导致高度异常
        separator.setStyleSheet(f"""
            QWidget {{
                background-color: {separator_color};
                margin-left:1.1px;
                margin-right:1.1px;
            }}
        """)



    def _update_all_styles(self):
        """更新所有组件的样式以匹配当前主题（优化版本，只更新必要的组件）"""
        try:
            # 防止频繁调用和重复调用
            if hasattr(self, '_updating_styles') and self._updating_styles:
                return
            self._updating_styles = True

            # 使用定时器延迟执行，避免阻塞UI（但延迟很短，减少闪烁）
            if hasattr(self, '_style_update_timer') and self._style_update_timer.isActive():
                return

            # 确保主题状态是最新的
            self._update_theme_state()

            # 不输出日志，减少延迟（如果需要调试可以取消注释）
            # self.log("🎨 开始更新所有组件样式...")

            # 获取当前主题的自定义样式（这些是我们的自定义样式，不是 qfluentwidgets 的默认样式）
            button_style = self._get_button_style()
            input_style = self._get_input_style()
            combo_style = self._get_combo_style()

            # 确保样式不为空
            if not button_style or not input_style or not combo_style:
                self.log("⚠️ 样式获取失败，跳过更新")
                self._updating_styles = False
                return

            # 导入必要的类用于类型检查
            from qfluentwidgets import PrimaryPushButton, LineEdit, ComboBox, TextEdit

            updated_count = {'buttons': 0, 'inputs': 0, 'combos': 0, 'textedits': 0}
            updated_widgets = set()  # 用于去重，避免重复更新

            def update_widget_style(widget):
                """更新单个组件的样式（不递归）"""
                if widget is None:
                    return

                widget_id = id(widget)
                if widget_id in updated_widgets:
                    return

                try:
                    # 检查是否是 PrimaryPushButton
                    if isinstance(widget, PrimaryPushButton):
                        # 获取现有样式（如果有的话，可能是从 QSS 文件加载的）
                        existing_style = widget.styleSheet()
                        # 如果现有样式包含我们的样式标记，说明已经设置过，需要合并
                        # 否则直接设置新样式
                        if existing_style and 'PrimaryPushButton' in existing_style:
                            # 合并样式：保留现有样式，但用新样式覆盖 PrimaryPushButton 部分
                            # 简单处理：直接设置新样式（因为我们的样式是完整的）
                            widget.setStyleSheet(button_style)
                        else:
                            # 直接设置新样式
                            widget.setStyleSheet(button_style)
                        updated_count['buttons'] += 1
                        updated_widgets.add(widget_id)
                    # 检查是否是 LineEdit
                    elif isinstance(widget, LineEdit):
                        existing_style = widget.styleSheet()
                        if existing_style and 'LineEdit' in existing_style:
                            widget.setStyleSheet(input_style)
                        else:
                            widget.setStyleSheet(input_style)
                        updated_count['inputs'] += 1
                        updated_widgets.add(widget_id)
                    # 检查是否是 ComboBox
                    elif isinstance(widget, ComboBox):
                        existing_style = widget.styleSheet()
                        if existing_style and 'ComboBox' in existing_style:
                            widget.setStyleSheet(combo_style)
                        else:
                            widget.setStyleSheet(combo_style)
                        updated_count['combos'] += 1
                        updated_widgets.add(widget_id)
                        # 更新下拉框文本对齐
                        from PyQt6.QtCore import Qt
                        def _update_alignment():
                            try:
                                if hasattr(widget, 'lineEdit') and widget.lineEdit():
                                    widget.lineEdit().setAlignment(Qt.AlignmentFlag.AlignLeft)
                            except:
                                pass
                        QtCore.QTimer.singleShot(10, _update_alignment)
                    # 检查是否是 TextEdit
                    elif isinstance(widget, TextEdit):
                        self._update_textedit_style(widget)
                        updated_count['textedits'] += 1
                        updated_widgets.add(widget_id)
                except Exception:
                    # 静默处理错误
                    pass

            # 方法1: 限制查找范围，只查找主要容器内的组件（避免查找所有组件）
            try:
                # 限制查找深度和数量，避免卡顿
                max_widgets_per_type = 200  # 每种类型最多查找200个组件

                # 直接查找，但限制数量
                buttons = self.findChildren(PrimaryPushButton)[:max_widgets_per_type]
                inputs = self.findChildren(LineEdit)[:max_widgets_per_type]
                combos = self.findChildren(ComboBox)[:max_widgets_per_type]
                textedits = self.findChildren(TextEdit)[:max_widgets_per_type]

                # 批量更新（使用去重机制）
                for widget in buttons:
                    update_widget_style(widget)
                for widget in inputs:
                    update_widget_style(widget)
                for widget in combos:
                    update_widget_style(widget)
                for widget in textedits:
                    update_widget_style(widget)
            except Exception as e:
                self.log(f"⚠️ 查找组件时出错: {e}")

            # 方法2: 遍历主要属性（作为补充）
            important_attrs = [
                'log_text', 'connect_button_container',
                # 添加其他重要的属性名
            ]
            for attr_name in important_attrs:
                try:
                    widget = getattr(self, attr_name, None)
                    if widget:
                        update_widget_style(widget)
                except:
                    pass

            # 更新分割线样式
            for attr_name in dir(self):
                if 'separator' in attr_name.lower():
                    try:
                        widget = getattr(self, attr_name, None)
                        if widget and isinstance(widget, QWidget):
                            self._update_separator_style(widget)
                    except:
                        pass

            # 更新 connect_button_container 等特殊容器
            if hasattr(self, 'connect_button_container') and self.connect_button_container:
                self.connect_button_container.setStyleSheet(input_style)

            # 更新日志边框样式
            if hasattr(self, '_update_log_border_style'):
                self._update_log_border_style()

            # 确保内容区的背景色正确（setTheme() 可能没有完全设置）
            try:
                # 不手动设置背景色，让 setTheme() 处理
                # 但需要确保没有其他样式覆盖背景色
                # 移除之前可能错误设置的背景色样式
                if hasattr(self, 'stackedWidget') and self.stackedWidget:
                    current_style = self.stackedWidget.styleSheet()
                    # 如果之前手动设置了背景色，移除它，让 setTheme() 的样式生效
                    if current_style and "background-color:" in current_style:
                        # 移除手动设置的背景色，保留其他样式
                        import re
                        new_style = re.sub(r'background-color:\s*[^;]+;?', '', current_style)
                        if new_style.strip():
                            self.stackedWidget.setStyleSheet(new_style.strip())
                        else:
                            self.stackedWidget.setStyleSheet("")

                # 同样处理 main_interface
                main_interface = self.findChild(QWidget, "main_interface")
                if main_interface:
                    current_style = main_interface.styleSheet()
                    if current_style and "background-color:" in current_style and "background-color: transparent" not in current_style:
                        # 移除手动设置的背景色
                        import re
                        new_style = re.sub(r'background-color:\s*[^;]+;?', '', current_style)
                        if new_style.strip():
                            main_interface.setStyleSheet(new_style.strip())
                        else:
                            main_interface.setStyleSheet("")
            except:
                pass

            # 强制刷新UI（立即刷新，减少闪烁）
            self.update()
            QApplication.processEvents()  # 立即处理事件，不延迟

            # 再次强制应用样式，确保覆盖任何默认样式（延迟执行，重新获取样式以确保使用最新主题）
            QtCore.QTimer.singleShot(100, lambda: self._force_apply_styles())

            # 不输出日志，减少延迟（如果需要调试可以取消注释）
            # self.log(f"✅ 样式更新完成: 按钮={updated_count['buttons']}, 输入框={updated_count['inputs']}, 下拉框={updated_count['combos']}, 文本区={updated_count['textedits']}")

            # 清除更新标志（延迟清除，避免立即重复调用）
            QtCore.QTimer.singleShot(500, lambda: setattr(self, '_updating_styles', False))
        except Exception as e:
            self.log(f"❌ 更新样式时出错: {e}")
            import traceback
            self.log(traceback.format_exc())
            self._updating_styles = False


    def _force_apply_styles(self):
        """强制应用样式，确保覆盖任何默认样式（重新获取样式以确保使用最新主题）"""
        try:
            # 确保主题状态是最新的
            self._update_theme_state()

            # 重新获取样式（使用最新主题状态）
            button_style = self._get_button_style()
            input_style = self._get_input_style()
            combo_style = self._get_combo_style()

            from qfluentwidgets import PrimaryPushButton, LineEdit, ComboBox
            updated_widgets = set()

            # 再次查找并应用样式
            buttons = self.findChildren(PrimaryPushButton)[:200]
            inputs = self.findChildren(LineEdit)[:200]
            combos = self.findChildren(ComboBox)[:200]

            for widget in buttons:
                widget_id = id(widget)
                if widget_id not in updated_widgets:
                    widget.setStyleSheet(button_style)
                    updated_widgets.add(widget_id)

            for widget in inputs:
                widget_id = id(widget)
                if widget_id not in updated_widgets:
                    widget.setStyleSheet(input_style)
                    updated_widgets.add(widget_id)

            for widget in combos:
                widget_id = id(widget)
                if widget_id not in updated_widgets:
                    widget.setStyleSheet(combo_style)
                    updated_widgets.add(widget_id)

            # 确保内容区没有边框
            try:
                if hasattr(self, 'stackedWidget') and self.stackedWidget:
                    current_style = self.stackedWidget.styleSheet()
                    if current_style:
                        import re
                        # 移除边框
                        new_style = re.sub(r'border[^:]*:\s*[^;]+;?', '', current_style)
                        if "border: none" not in new_style:
                            new_style = new_style.strip() + "; border: none;"
                        self.stackedWidget.setStyleSheet(new_style.strip())
                    else:
                        self.stackedWidget.setStyleSheet("border: none;")

                main_interface = self.findChild(QWidget, "main_interface")
                if main_interface:
                    current_style = main_interface.styleSheet()
                    if current_style:
                        import re
                        # 移除边框
                        new_style = re.sub(r'border[^:]*:\s*[^;]+;?', '', current_style)
                        if "border: none" not in new_style:
                            new_style = new_style.strip() + "; border: none;"
                        main_interface.setStyleSheet(new_style.strip())
                    else:
                        main_interface.setStyleSheet("border: none;")
            except:
                pass

            # 强制刷新
            self.update()
            QApplication.processEvents()
        except Exception:
            pass


    def _load_qss_stylesheet(self):
        """加载 QSS 样式表（包含标题栏按钮样式，参考 demo.py）"""
        try:
            from qfluentwidgets import isDarkTheme
            color = 'dark' if isDarkTheme() else 'light'
            qss_path = os.path.join(os.path.dirname(__file__), f'resource/{color}/demo.qss')
            if os.path.exists(qss_path):
                with open(qss_path, encoding='utf-8') as f:
                    qss_content = f.read()
                    # 追加到现有样式表，而不是覆盖
                    current_style = self.styleSheet()
                    if current_style:
                        self.setStyleSheet(current_style + "\n" + qss_content)
                    else:
                        self.setStyleSheet(qss_content)
        except Exception as e:
            # 如果加载失败，不影响程序运行
            pass





    def _set_splitter_ratio(self):
        """设置分割器的比例（左侧1/3，右侧2/3）"""
        # 设置主分割器（左右）
        if hasattr(self, 'main_container') and isinstance(self.main_container, QSplitter):
            sizes = self.main_container.sizes()
            if len(sizes) == 2 and sum(sizes) > 0:
                # 计算目标大小：左侧1/3，右侧2/3
                total = sum(sizes)
                target_left = total // 3
                target_right = total - target_left
                self.main_container.setSizes([target_left, target_right])


    def _update_log_border_style(self):
        """根据当前主题更新日志区域的边框样式"""
        self._update_textedit_style(self.log_text)


