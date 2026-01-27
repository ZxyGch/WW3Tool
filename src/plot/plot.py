"""
科研绘图界面模块
包含所有绘图相关的 UI 和逻辑
"""

import os
import sys
import glob
import subprocess
import platform
import re
import threading
import multiprocessing
from multiprocessing import Process, Queue
from datetime import datetime, timedelta
import numpy as np
import matplotlib
matplotlib.use('QtAgg')
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib import cm
from netCDF4 import Dataset, num2date
import netCDF4 as nc
from PIL import Image

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import QEvent, Qt
from qfluentwidgets import (
    PrimaryPushButton, LineEdit, HeaderCardWidget, ComboBox, TableWidget,
    InfoBar
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QTableWidgetItem, QHeaderView, QScrollArea, QDialog, QSizePolicy, QFileDialog
)
from PyQt6.QtGui import QPixmap

from setting.config import *
from setting.language_manager import tr
from .workers import (
    _make_wave_maps_worker,
    _make_contour_maps_worker
)
from .plot_wind import WindFieldPlotMixin
from .plot_spectrum import SpectrumPlotMixin
from .plot_wave_height import WaveHeightPlotMixin
from .plot_jason3 import Jason3PlotMixin

# 在 Windows 上需要设置启动方法
if hasattr(multiprocessing, 'set_start_method'):
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass


class PlotMixin(SpectrumPlotMixin, WindFieldPlotMixin, WaveHeightPlotMixin, Jason3PlotMixin):
    """科研绘图功能模块"""
    
    def _create_plot_page(self):
        """创建绘图页面（只包含第七步：波高图绘制）"""
        try:
            # 按钮样式：使用主题适配的样式
            button_style = self._get_button_style()

            # 输入框样式：使用主题适配的样式
            input_style = self._get_input_style()

            # 创建绘图页面容器
            plot_content = QWidget()
            plot_content.setStyleSheet("QWidget { background-color: transparent; }")
            plot_layout = QVBoxLayout(plot_content)
            plot_layout.setContentsMargins(0, 0, 0, 10)
            plot_layout.setSpacing(15)

            # 创建滚动区域
            plot_scroll_area = QtWidgets.QScrollArea()
            plot_scroll_area.setWidgetResizable(True)
            plot_scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            plot_scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            plot_scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            plot_scroll_area.setStyleSheet("""
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
            plot_content_widget = QWidget()
            plot_content_widget.setStyleSheet("QWidget { background-color: transparent; }")
            plot_content_layout = QVBoxLayout(plot_content_widget)
            plot_content_layout.setContentsMargins(0, 0, 0, 10)
            plot_content_layout.setSpacing(8)
            plot_content_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

            # 风场绘图块 - 使用分离的模块
            self._create_wind_field_ui(plot_content_widget, plot_content_layout, button_style, input_style)

            # 海浪二维方向谱绘图块 - 使用分离的模块
            self._create_spectrum_ui(plot_content_widget, plot_content_layout, button_style, input_style)

            # 波高图绘制块 - 使用分离的模块
            self._create_wave_height_ui(plot_content_widget, plot_content_layout, button_style, input_style)

            # Jason-3 卫星观测数据块 - 使用分离的模块
            self._create_jason3_ui(plot_content_widget, plot_content_layout, button_style, input_style)

            # 设置滚动区域的内容
            plot_scroll_area.setWidget(plot_content_widget)
            plot_layout.addWidget(plot_scroll_area)

            return plot_content

        except Exception as e:
            import traceback
            error_msg = tr("plotting_create_page_failed", "❌ 创建绘图页面失败：{error}").format(error=e)
            traceback.print_exc()
            # 返回一个简单的错误提示页面
            error_widget = QWidget()
            error_layout = QVBoxLayout(error_widget)
            error_label = QLabel(error_msg)
            error_layout.addWidget(error_label)
            return error_widget



    def open_image_file(self, filepath):
        """根据系统自动打开图片文件"""
        try:
            sys_name = platform.system().lower()
            if "windows" in sys_name:
                os.startfile(filepath)
            elif "darwin" in sys_name:  # macOS
                subprocess.run(["open", filepath])
            else:
                subprocess.run(["xdg-open", filepath])
        except Exception as e:
            self.log(tr("plotting_open_image_failed", "无法打开图片: {error}").format(error=e))

    def _create_test_drawer(self, parent_widget):
        """创建测试用的侧边抽屉"""
        from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, Qt, QRect
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        
        # 创建遮罩层（用于点击外部区域关闭抽屉，但不改变背景色）
        self.drawer_mask = QWidget(parent_widget)
        self.drawer_mask.setObjectName("drawer_mask")
        # 完全透明，不改变背景色
        self.drawer_mask.setStyleSheet("""
            QWidget#drawer_mask {
                background-color: transparent;
            }
        """)
        # 点击遮罩层关闭抽屉
        self.drawer_mask.mousePressEvent = lambda e: self._toggle_test_drawer()
        self.drawer_mask.setVisible(False)
        
        # 创建抽屉容器（覆盖在父窗口之上）
        self.test_drawer = QWidget(parent_widget)
        self.test_drawer.setObjectName("test_drawer")
        
        # 设置抽屉样式（使用灰色背景色，左侧显示阴影而不是边框）
        try:
            from qfluentwidgets import isDarkTheme
            if isDarkTheme():
                # 深色主题：使用深灰色背景
                bg_color = "#2d2d2d"
            else:
                # 浅色主题：使用浅灰色背景
                bg_color = "#f5f5f5"
        except:
            bg_color = "#f5f5f5"
        
        # 抽屉背景色使用灰色，不显示边框
        self.test_drawer.setStyleSheet(f"""
            QWidget#test_drawer {{
                background-color: {bg_color};
            }}
        """)
        
        # 添加左侧阴影效果（优化：更淡、更长）
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect
        from PyQt6.QtGui import QColor
        shadow_effect = QGraphicsDropShadowEffect()
        shadow_effect.setBlurRadius(25)  # 增加模糊半径，让阴影更柔和
        shadow_effect.setXOffset(-6)  # 增加左侧阴影偏移，让阴影更长
        shadow_effect.setYOffset(0)  # Y偏移为0
        
        # 根据主题调整阴影颜色和透明度（降低透明度，让阴影更淡）
        try:
            from qfluentwidgets import isDarkTheme
            if isDarkTheme():
                # 深色主题：使用更淡的阴影
                shadow_effect.setColor(QColor(0, 0, 0, 40))  # 降低透明度，更淡
            else:
                # 浅色主题：使用更淡的阴影
                shadow_effect.setColor(QColor(0, 0, 0, 30))  # 降低透明度，更淡
        except:
            shadow_effect.setColor(QColor(0, 0, 0, 30))
        
        self.test_drawer.setGraphicsEffect(shadow_effect)
        
        # 阻止点击抽屉内部时事件传播到遮罩层
        self.test_drawer.mousePressEvent = lambda e: e.accept()
        
        # 创建抽屉内容布局（用于显示图片列表）
        drawer_layout = QVBoxLayout(self.test_drawer)
        drawer_layout.setContentsMargins(15, 0, 0, 0)  # 增大左侧边距，移除上下和右侧边距
        drawer_layout.setSpacing(0)
        
        # 创建滚动区域用于显示图片列表（隐藏滚动条，透明背景）
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # 隐藏垂直滚动条
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # 隐藏水平滚动条
        scroll_area.setStyleSheet("QScrollArea { background-color: transparent; }")
        
        # 创建图片容器（单列显示，宽度固定，无背景）
        self.drawer_image_container = QWidget()
        self.drawer_image_container.setStyleSheet("background-color: transparent;")
        self.drawer_image_layout = QVBoxLayout(self.drawer_image_container)
        self.drawer_image_layout.setContentsMargins(0, 10, 0, 20)
        self.drawer_image_layout.setSpacing(20)
        self.drawer_image_layout.addStretch()  # 底部弹性空间
        
        # 设置容器大小策略，防止横向扩展
        self.drawer_image_container.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Minimum
        )
        
        scroll_area.setWidget(self.drawer_image_container)
        drawer_layout.addWidget(scroll_area)
        
        # 初始状态：隐藏在右侧外部
        self.test_drawer.setVisible(False)
        self.test_drawer_is_open = False
        
        # 创建位置动画
        self.drawer_animation = QPropertyAnimation(self.test_drawer, b"geometry")
        self.drawer_animation.setDuration(300)  # 动画时长300ms
        self.drawer_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _toggle_test_drawer(self):
        """切换侧边抽屉的显示/隐藏"""
        if not hasattr(self, 'test_drawer'):
            return

        # 获取父窗口（main_interface）的尺寸
        parent = self.test_drawer.parent()
        if not parent:
            return

        parent_width = parent.width()
        parent_height = parent.height()
        drawer_width = parent_width // 2  # 抽屉宽度为窗口的1/2
        
        if not self.test_drawer_is_open:
            # 打开抽屉：从右侧滑入
            from PyQt6.QtCore import QRect
            start_rect = QRect(parent_width, 0, drawer_width, parent_height)
            end_rect = QRect(parent_width - drawer_width, 0, drawer_width, parent_height)
            
            # 设置遮罩层（覆盖整个父窗口）
            self.drawer_mask.setGeometry(QRect(0, 0, parent_width, parent_height))
            self.drawer_mask.setVisible(True)
            self.drawer_mask.raise_()  # 确保遮罩层在底层
            
            # 设置抽屉位置
            self.test_drawer.setGeometry(start_rect)
            self.test_drawer.setVisible(True)
            self.test_drawer.raise_()  # 确保抽屉在最上层
            
            # 遮罩层直接显示（完全透明，只用于接收点击事件）
            self.drawer_mask.setWindowOpacity(1.0)
            
            # 启动抽屉滑入动画
            self.drawer_animation.setStartValue(start_rect)
            self.drawer_animation.setEndValue(end_rect)
            self.drawer_animation.start()
            
            self.test_drawer_is_open = True
        else:
            # 关闭抽屉：滑出到右侧
            from PyQt6.QtCore import QRect
            current_rect = self.test_drawer.geometry()
            end_rect = QRect(parent_width, 0, drawer_width, parent_height)
            
            # 遮罩层直接隐藏（不需要动画）
            self.drawer_mask.setVisible(False)
            
            # 启动抽屉滑出动画
            self.drawer_animation.setStartValue(current_rect)
            self.drawer_animation.setEndValue(end_rect)
            self.drawer_animation.finished.connect(lambda: self.test_drawer.setVisible(False))
            self.drawer_animation.start()
            
            self.test_drawer_is_open = False
            
            # 清理动画完成后的连接
            def cleanup():
                try:
                    self.drawer_animation.finished.disconnect()
                except:
                    pass

            self.drawer_animation.finished.connect(cleanup)

    def _adjust_drawer_position(self):
        """调整抽屉位置以适应新的窗口大小"""
        if not hasattr(self, 'test_drawer') or not self.test_drawer_is_open:
            return

        parent = self.test_drawer.parent()
        if not parent:
            return

        parent_width = parent.width()
        parent_height = parent.height()
        drawer_width = parent_width // 2
        
        # 直接设置新位置（不带动画）
        from PyQt6.QtCore import QRect
        # 调整遮罩层大小
        self.drawer_mask.setGeometry(QRect(0, 0, parent_width, parent_height))
        # 调整抽屉位置
        self.test_drawer.setGeometry(parent_width - drawer_width, 0, drawer_width, parent_height)

    def _show_images_in_drawer(self, image_paths):
        """在抽屉中显示图片列表（单列显示）- 使用子线程加载图片以避免卡顿"""
        if not hasattr(self, 'drawer_image_layout'):
            self.log(tr("drawer_not_initialized", "❌ 抽屉功能未初始化"))
            return

        # 清除现有内容（保留底部弹性空间）
        while self.drawer_image_layout.count() > 1:  # 保留最后的 stretch
            item = self.drawer_image_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 先打开抽屉
        if not self.test_drawer_is_open:
            self._toggle_test_drawer()
        
        # 更新容器宽度以匹配抽屉宽度（防止横向滚动）
        parent = self.test_drawer.parent()
        if parent:
            drawer_actual_width = parent.width() // 2 - 30  # 减去滚动条和边距
            self.drawer_image_container.setFixedWidth(drawer_actual_width)
        else:
            drawer_actual_width = 600  # 默认值
        
        # 保存抽屉宽度供子线程使用
        self._drawer_actual_width = drawer_actual_width
        
        # 在子线程中加载图片（避免主线程卡顿）
        def _load_images_worker():
            """在子线程中加载和缩放图片"""
            from PIL import Image
            
            # 获取抽屉宽度（从实例变量中获取）
            drawer_width = getattr(self, '_drawer_actual_width', 600)
            
            for img_path in image_paths:
                try:
                    # 加载并缩放图片
                    pil_img = Image.open(img_path)
                    
                    # 计算缩放后的尺寸（保持宽高比，宽度完全匹配抽屉宽度）
                    container_padding = 16  # 左右各8px
                    image_max_width = drawer_width - container_padding
                    
                    # 图片宽度完全匹配容器宽度
                    if pil_img.width != image_max_width:
                        scale = image_max_width / pil_img.width
                        new_width = image_max_width
                        new_height = int(pil_img.height * scale)
                    else:
                        new_width = pil_img.width
                        new_height = pil_img.height
                    
                    pil_img = pil_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    
                    # 通过信号传递图片路径和缩放后的尺寸
                    # 注意：QPixmap 不能在线程间传递，所以我们在主线程中重新加载
                    self.add_image_to_drawer_signal.emit(img_path, new_width, new_height)
                    
                except Exception as e:
                        self.log_signal.emit(tr("plotting_load_image_failed", "❌ 加载图片失败 {file}: {error}").format(file=os.path.basename(img_path), error=e))
                        continue

            # 所有图片加载完成
            self.images_loading_complete_signal.emit()
        
        # 启动子线程
        load_thread = threading.Thread(target=_load_images_worker, daemon=True)
        load_thread.start()

    def _add_single_image_to_drawer(self, img_path, img_width, img_height):
        """在主线程中添加单张图片到抽屉（由信号触发）"""
        try:
            # 创建带圆角边框的容器
            from PyQt6.QtWidgets import QFrame
            container = QFrame()
            container.setStyleSheet("""
                QFrame {
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
            """)
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(15, 8, 8, 8)  # 左侧15px，其他边8px以保护圆角
            container_layout.setSpacing(5)
            
            # 在主线程中加载图片（从文件路径）
            from PyQt6.QtGui import QPixmap
            from PIL import Image
            from PIL.ImageQt import ImageQt
            
            # 重新加载并缩放图片（在主线程中进行，确保线程安全）
            pil_img = Image.open(img_path)
            container_padding = 16
            image_max_width = self._drawer_actual_width - container_padding
            
            if pil_img.width != image_max_width:
                scale = image_max_width / pil_img.width
                new_width = image_max_width
                new_height = int(pil_img.height * scale)
            else:
                new_width = pil_img.width
                new_height = pil_img.height
            
            pil_img = pil_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # 转换为 QPixmap
            qimg = ImageQt(pil_img)
            pixmap = QPixmap.fromImage(qimg)
            
            # 创建图片标签（无边框，透明背景）
            img_label = QLabel()
            img_label.setPixmap(pixmap)
            img_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            img_label.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            img_label.setStyleSheet("border: none; background: transparent;")
            
            # 点击图片打开原图
            def open_image(path=img_path):
                self.open_image_file(path)
            
            img_label.mousePressEvent = lambda e, path=img_path: open_image(path)
            
            # 添加文件名标签
            filename = os.path.basename(img_path)
            name_label = QLabel(filename)
            name_label.setStyleSheet("font-size: 12px; color: #666; border: none; background: transparent;")
            name_label.setWordWrap(True)
            name_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            
            container_layout.addWidget(img_label)
            container_layout.addWidget(name_label)
            
            # 添加到抽屉布局（使用容器而不是 image_widget）
            self.drawer_image_layout.insertWidget(self.drawer_image_layout.count() - 1, container)

        except Exception as e:
            self.log(tr("plotting_add_image_to_drawer_failed", "❌ 添加图片到抽屉失败 {file}: {error}").format(file=os.path.basename(img_path), error=e))

    def _on_images_loading_complete(self):
        """图片加载完成后的处理"""
        # 可以在这里添加加载完成的提示
        pass
