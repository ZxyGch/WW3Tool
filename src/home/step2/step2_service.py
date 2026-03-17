"""
第二步：生成网格模块 - 业务逻辑部分
包含所有业务逻辑函数（从 ui.py 拆分出来）
"""
import os
import sys
import json
import glob
import shutil
import re
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
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QGridLayout, QHBoxLayout, QWidget, QSizePolicy, QDialog, QScrollArea, QFrame
from PyQt6.QtGui import QPixmap, QDesktopServices
from qfluentwidgets import PrimaryPushButton, LineEdit, ComboBox, InfoBar, MessageBoxBase
from setting.language_manager import tr
from setting.config import DX, DY, LONGITUDE_WEST, LONGITUDE_EAST, LATITUDE_SORTH, LATITUDE_NORTH, MATLAB_PATH, load_config


# reference_data 目录下必须存在的文件（生成网格前检测）
REFERENCE_DATA_REQUIRED_FILES = [
    "coastal_bound_coarse.mat",
    "coastal_bound_full.mat",
    "coastal_bound_high.mat",
    "coastal_bound_inter.mat",
    "coastal_bound_low.mat",
    "optional_coastal_polygons.mat",
    "user_polygons.flag",
    "etopo1.nc",
    "etopo2.nc",
    "gebco.nc",
]

# reference_data 手动下载说明链接与路径提示
REFERENCE_DATA_YDRAY_URL = "https://ydray.com/get/t/u17737629592553JcSjd881f85029a1qm"
REFERENCE_DATA_ONEDRIVE_URL = "https://tiangongeducn-my.sharepoint.com/:u:/g/personal/1911650207_tiangong_edu_cn/IQBGfWxOrWNlQphTeWCh-7AjAR-dtNWp7guSVhiyUH4dCW8?e=BdDBqQ"
REFERENCE_DATA_BAIDU_URL = "https://pan.baidu.com/s/1ec8DMcv8bp6MzNnFBkbAPA?pwd=ktch"


class _ReferenceDataMissingDialog(MessageBoxBase):
    """reference_data 缺失提示弹窗：提示下载或手动放置到指定路径"""

    def __init__(self, parent, ref_dir, missing_list, on_download_clicked=None):
        super().__init__(parent)
        self._on_download_clicked = on_download_clicked
        self.setWindowTitle(tr("step2_ref_data_missing_title", "缺失 reference_data 文件"))
        self.hideYesButton()
        self.hideCancelButton()
        self.buttonLayout.parent().setVisible(False)

        msg1 = tr(
            "step2_ref_data_missing_msg1",
            "生成网格需要 reference_data 文件夹及指定文件，当前缺失或路径不存在。"
        )
        label1 = QLabel(msg1)
        label1.setWordWrap(True)
        self.viewLayout.addWidget(label1)

        button_style = parent._get_button_style() if hasattr(parent, "_get_button_style") else ""
        self.btn_download = PrimaryPushButton(tr("step2_ref_data_ok", "下载"))
        self.btn_download.setStyleSheet(button_style)
        self.btn_download.clicked.connect(self._on_download)
        self.viewLayout.addWidget(self.btn_download)

        msg2 = tr(
            "step2_ref_data_missing_msg2",
            "If download is slow or fails, you can download manually using the buttons below."
        )
        manual_hint = tr(
            "step2_ref_data_manual_hint",
            "After manual download, place the extracted files in the path below."
        )
        label2 = QLabel(f"{msg2}\n\n{manual_hint}")
        label2.setWordWrap(True)
        # 允许选择和复制文字
        label2.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.viewLayout.addWidget(label2)

        # 固定展示可复制的参考数据路径
        ref_path_label = QLabel("/Users/zxy/ocean/WW3Tool/gridgen/reference_data")
        ref_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        ref_path_label.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace; margin-bottom: 8px;"
        )
        self.viewLayout.addWidget(ref_path_label)

        self.btn_ydray = PrimaryPushButton(tr("step2_ref_data_open_ydray", "打开 YDRAY 下载链接"))
        self.btn_ydray.setStyleSheet(button_style)
        self.btn_ydray.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REFERENCE_DATA_YDRAY_URL)))
        self.viewLayout.addWidget(self.btn_ydray)

        self.btn_onedrive = PrimaryPushButton(tr("step2_ref_data_open_onedrive", "打开 OneDrive 下载链接"))
        self.btn_onedrive.setStyleSheet(button_style)
        self.btn_onedrive.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REFERENCE_DATA_ONEDRIVE_URL)))
        self.viewLayout.addWidget(self.btn_onedrive)
        self.btn_baidu = PrimaryPushButton(tr("step2_ref_data_open_baidu", "打开百度网盘下载链接"))
        self.btn_baidu.setStyleSheet(button_style)
        self.btn_baidu.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REFERENCE_DATA_BAIDU_URL)))
        self.viewLayout.addWidget(self.btn_baidu)
        self.btn_cancel = PrimaryPushButton(tr("step2_ref_data_cancel", "取消"))
        self.btn_cancel.setStyleSheet(button_style)
        self.btn_cancel.clicked.connect(self.reject)
        self.viewLayout.addWidget(self.btn_cancel)

    def _on_download(self):
        if callable(self._on_download_clicked):
            self._on_download_clicked()
        self.accept()


class _GlobalGridConfirmDialog(MessageBoxBase):
    """全球范围确认弹窗（使用 MessageBoxBase 样式）"""

    def __init__(self, parent, title, message):
        super().__init__(parent)
        self._confirmed = False

        self.setWindowTitle(title)
        self.hideYesButton()
        self.hideCancelButton()
        self.buttonLayout.parent().setVisible(False)

        label = QLabel(message)
        label.setWordWrap(True)
        self.viewLayout.addWidget(label)

        button_style = parent._get_button_style() if hasattr(parent, '_get_button_style') else ""

        self.btn_confirm = PrimaryPushButton(tr("step2_global_grid_confirm_button", "确定"))
        self.btn_confirm.setStyleSheet(button_style)
        self.btn_confirm.clicked.connect(self._on_confirm)
        self.viewLayout.addWidget(self.btn_confirm)

        self.btn_cancel = PrimaryPushButton(tr("step2_global_grid_cancel_button", "取消"))
        self.btn_cancel.setStyleSheet(button_style)
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.viewLayout.addWidget(self.btn_cancel)

    def _on_confirm(self):
        self._confirmed = True
        self.accept()

    def _on_cancel(self):
        self._confirmed = False
        self.reject()

    @property
    def confirmed(self):
        return self._confirmed


class StepTwoServiceMixin:
    """第二步相关的业务逻辑 Mixin"""
    
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
            if hasattr(self, "_set_step2_grid_type"):
                self._set_step2_grid_type(nested_text, skip_block_check=True)
            else:
                # 保持向后兼容：仅更新状态
                from ..utils import HomeState
                HomeState.set_grid_type(nested_text)
                self.grid_type_var = nested_text
                if hasattr(self, "_update_step4_wavewatch_title"):
                    self._update_step4_wavewatch_title()
            self.log(tr("step3_detect_nested_folders", "🔄 检测到coarse和fine文件夹，已自动切换到嵌套网格模式"))
        else:
            # 自动切换回普通网格模式
            normal_text = tr("step2_grid_type_normal", "普通网格")
            self.grid_type_combo.blockSignals(True)
            self.grid_type_combo.setCurrentText(normal_text)
            self.grid_type_combo.blockSignals(False)
            if hasattr(self, "_set_step2_grid_type"):
                self._set_step2_grid_type(normal_text)




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
            # __file__ 是 main/home/step2/step2_service.py，需要回到项目根目录
            script_dir = os.path.dirname(os.path.abspath(__file__))  # main/home/step2
            home_dir = os.path.dirname(script_dir)  # main/home
            main_dir = os.path.dirname(home_dir)  # main
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

    def _check_reference_data(self):
        """检测 reference_data 目录及必需文件是否存在。返回 (是否通过, 缺失文件列表, 参考数据目录路径)。"""
        ref_dir = self._get_reference_data_path()
        if not ref_dir or not os.path.isdir(ref_dir):
            return False, list(REFERENCE_DATA_REQUIRED_FILES), ref_dir or ""
        missing = [
            f for f in REFERENCE_DATA_REQUIRED_FILES
            if not os.path.isfile(os.path.join(ref_dir, f))
        ]
        return len(missing) == 0, missing, ref_dir

    def _run_get_reference_data(self):
        """在后台线程中执行 gridgen/get_reference_data.py 下载参考数据，实时输出到 log，完成后在主线程提示。"""
        ref_dir = self._get_reference_data_path()
        gridgen_dir = os.path.dirname(ref_dir) if ref_dir else self._get_gridgen_path()
        script_path = os.path.join(gridgen_dir, "get_reference_data.py")
        if not os.path.isfile(script_path):
            QtCore.QTimer.singleShot(0, lambda: self._show_ref_data_result(False, tr("step2_ref_data_script_not_found", "未找到 get_reference_data.py：{path}").format(path=script_path)))
            return

        log_signal = getattr(self, "log_signal", None)

        def _run():
            try:
                proc = subprocess.Popen(
                    [sys.executable, "-u", script_path],
                    cwd=gridgen_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                if log_signal:
                    log_signal.emit(tr("step2_ref_data_started", "正在执行 get_reference_data.py 下载参考数据…"))
                for line in proc.stdout:
                    line = line.rstrip()
                    if line and log_signal:
                        log_signal.emit(line)
                proc.wait()
                ok = proc.returncode == 0
                msg = tr("step2_ref_data_done", "下载完成") if ok else tr("step2_ref_data_failed", "下载失败，返回码：{code}").format(code=proc.returncode)
            except subprocess.TimeoutExpired:
                ok = False
                msg = tr("step2_ref_data_timeout", "下载超时")
            except Exception as e:
                ok = False
                msg = str(e)
            QtCore.QTimer.singleShot(0, lambda: self._show_ref_data_result(ok, msg))

        threading.Thread(target=_run, daemon=True).start()
        try:
            InfoBar.info(
                title=tr("tip", "提示"),
                content=tr("step2_ref_data_started", "正在执行 get_reference_data.py 下载参考数据…"),
                duration=3000,
                parent=self,
            )
        except Exception:
            pass

    def _show_ref_data_result(self, success, message):
        """在主线程显示 reference_data 下载结果（日志 + InfoBar）。"""
        if hasattr(self, "log_signal") and self.log_signal:
            if success:
                self.log_signal.emit(tr("step2_ref_data_done", "✅ reference_data 下载完成"))
            else:
                self.log_signal.emit(tr("step2_ref_data_failed_log", "❌ reference_data 下载失败：{msg}").format(msg=message))
        try:
            if success:
                InfoBar.success(
                    title=tr("tip", "提示"),
                    content=tr("step2_ref_data_done_toast", "reference_data 下载完成，可重新点击「生成网格」"),
                    duration=4000,
                    parent=self,
                )
            else:
                InfoBar.warning(
                    title=tr("tip", "提示"),
                    content=message[:200] + ("…" if len(message) > 200 else ""),
                    duration=5000,
                    parent=self,
                )
        except Exception:
            pass

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
        
        for _ in range(5):
            if os.path.exists(grid_bot_path) and os.path.exists(grid_meta_path):
                break
            time.sleep(1.0)
        
        if not os.path.exists(grid_bot_path):
            return False, tr("step2_grid_bot_not_exists", "grid.bot 文件不存在")
        
        if not os.path.exists(grid_meta_path):
            return False, tr("step2_grid_meta_not_exists", "grid.meta 文件不存在，无法验证")
        
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
        
        for retry in range(max_retries):
            try:
                if retry > 0:
                    time.sleep(retry_delay)
                
                data = []
                with open(grid_bot_path, 'r') as fid:
                    for line in fid:
                        line = line.strip()
                        if line:
                            values = [int(x) for x in line.split()]
                            if len(values) > 0:
                                data.append(values)
                
                if len(data) < Ny:
                    if retry < max_retries - 1:
                        continue
                    return False, tr("step2_grid_bot_rows_insufficient", "grid.bot 文件行数不足: 实际 {actual} 行，预期 {expected} 行（可能是 dxdy > 0.05 导致的文件写入不完整）").format(actual=len(data), expected=Ny)
                
                for i, row in enumerate(data[:Ny]):
                    if len(row) != Nx:
                        if retry < max_retries - 1:
                            break
                        return False, tr("step2_grid_bot_cols_incorrect", "grid.bot 第 {row} 行列数不正确: 实际 {actual} 列，预期 {expected} 列").format(row=i+1, actual=len(row), expected=Nx)
                else:
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

    def _maybe_prompt_global_grid(self):
        """当网格范围接近全球时，询问是否按全球范围生成"""
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        is_nested = self._is_nested_grid(grid_type)

        def _get_float(edit, fallback):
            try:
                text = edit.text().strip()
                return float(text) if text else float(fallback)
            except Exception:
                return float(fallback)

        try:
            dx_value = _get_float(self.dx_edit, DX if DX else 0.05)
            dy_value = _get_float(self.dy_edit, DY if DY else 0.05)
            lon_west = _get_float(self.lon_west_edit, LONGITUDE_WEST if LONGITUDE_WEST else -180.0)
            lon_east = _get_float(self.lon_east_edit, LONGITUDE_EAST if LONGITUDE_EAST else 180.0)
            lat_south = _get_float(self.lat_south_edit, LATITUDE_SORTH if LATITUDE_SORTH else -90.0)
            lat_north = _get_float(self.lat_north_edit, LATITUDE_NORTH if LATITUDE_NORTH else 90.0)
        except Exception:
            return

        if self._is_global_range(lon_west, lon_east, lat_south, lat_north):
            return

        if not self._is_near_global_range(lon_west, lon_east, lat_south, lat_north, dx_value, dy_value):
            return

        title = tr("step2_global_grid_title", "确认全球范围网格")
        message = tr(
            "step2_global_grid_prompt",
            "检测到网格范围非常接近全球范围。\n是否按全球范围生成（经度 -180~180，纬度 -90~90）？"
        )
        dialog = _GlobalGridConfirmDialog(self, title, message)
        dialog.exec()
        if not dialog.confirmed:
            return

        self.lon_west_edit.setText("-180")
        self.lon_east_edit.setText("180")
        self.lat_south_edit.setText("-90")
        self.lat_north_edit.setText("90")

        if is_nested:
            self.log(tr("step2_global_grid_outer_only", "✅ 已将外网格范围调整为全球范围"))
        else:
            self.log(tr("step2_global_grid_applied", "✅ 已将网格范围调整为全球范围"))

    def _is_near_global_range(self, lon_west, lon_east, lat_south, lat_north, dx_value, dy_value):
        """判断范围是否非常接近全球范围"""
        lon_min = min(lon_west, lon_east)
        lon_max = max(lon_west, lon_east)
        lat_min = min(lat_south, lat_north)
        lat_max = max(lat_south, lat_north)
        tol = max(0.5, abs(dx_value), abs(dy_value))
        lon_range = lon_max - lon_min
        lon_close = lon_range >= 360 - tol * 2
        lat_close = lat_min <= -90 + tol and lat_max >= 90 - tol
        return lon_close and lat_close

    def _is_global_range(self, lon_west, lon_east, lat_south, lat_north):
        """判断是否为全球范围网格"""
        lon_min = min(lon_west, lon_east)
        lon_max = max(lon_west, lon_east)
        lat_min = min(lat_south, lat_north)
        lat_max = max(lat_south, lat_north)
        tol = 1e-3
        in_180 = abs(lon_min + 180) <= tol and abs(lon_max - 180) <= tol
        in_360 = abs(lon_min - 0) <= tol and abs(lon_max - 360) <= tol
        lat_ok = abs(lat_min + 90) <= tol and abs(lat_max - 90) <= tol
        return lat_ok and (in_180 or in_360)

    def _update_matlab_grid_nml(
        self,
        matlab_bin_dir,
        output_dir,
        ref_dir,
        ref_grid,
        boundary,
        dx_value,
        dy_value,
        lon_west,
        lon_east,
        lat_south,
        lat_north,
        is_global
    ):
        """更新 MATLAB gridgen 的 grid.nml 参数"""
        if not matlab_bin_dir:
            return
        grid_nml_path = os.path.join(matlab_bin_dir, "bin", "grid.nml")
        if not os.path.exists(grid_nml_path):
            return

        def to_posix(path_value):
            return os.path.abspath(os.path.normpath(path_value)).replace("\\", "/")

        replacements = {
            "BIN_DIR": f"'{to_posix(os.path.join(matlab_bin_dir, 'bin'))}'",
            "REF_DIR": f"'{to_posix(ref_dir)}'",
            "DATA_DIR": f"'{to_posix(output_dir)}'",
            "REF_GRID": f"'{ref_grid}'",
            "BOUNDARY": f"'{boundary}'",
            "DX": f"{dx_value}",
            "DY": f"{dy_value}",
            "LON_WEST": f"{lon_west}",
            "LON_EAST": f"{lon_east}",
            "LAT_SOUTH": f"{lat_south}",
            "LAT_NORTH": f"{lat_north}",
            "IS_GLOBAL": f"{1 if is_global else 0}",
            "IS_GLOBALB": f"{1 if is_global else 0}",
        }

        with open(grid_nml_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_lines = []
        for line in lines:
            line_stripped = line.lstrip()
            if line_stripped.startswith("$") or line_stripped.startswith("!"):
                new_lines.append(line)
                continue
            updated = False
            for key, value in replacements.items():
                if re.match(rf"^\s*{re.escape(key)}\s*=", line):
                    new_lines.append(f"  {key} = {value}\n")
                    updated = True
                    break
            if not updated:
                new_lines.append(line)

        with open(grid_nml_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    def apply_and_create_grid(self):
        """应用配置并生成网格（合并两步为一步）- 在后台线程中执行"""
        ok, missing_list, ref_dir = self._check_reference_data()
        if not ok:
            dlg = _ReferenceDataMissingDialog(self, ref_dir, missing_list, on_download_clicked=self._run_get_reference_data)
            dlg.exec()
            return
        self._maybe_prompt_global_grid()
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
            is_global = self._is_global_range(lon_west, lon_east, lat_south, lat_north)
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

            # 规范化输出目录（强制绝对路径，避免相对路径导致输出位置错误）
            output_dir_norm = os.path.abspath(os.path.normpath(output_dir))

            if gridgen_version == "Python":
                # 规范化 Python 版本路径
                python_version_path_norm = os.path.normpath(python_version_path)

            self.log_signal.emit(tr("step2_params", "   参数: dx={dx}, dy={dy}").format(dx=dx_value, dy=dy_value))
            self.log_signal.emit(tr("step2_lon_range", "   经度范围: [{min}, {max}]").format(min=lon_west, max=lon_east))
            self.log_signal.emit(tr("step2_lat_range", "   纬度范围: [{min}, {max}]").format(min=lat_south, max=lat_north))

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
            
            # 转换海岸边界精度
            full_text = tr("step2_coastline_precision_full", "最高")
            high_text = tr("step2_coastline_precision_high", "高")
            inter_text = tr("step2_coastline_precision_inter", "中")
            low_text = tr("step2_coastline_precision_low", "低")
            coarse_text = tr("coastline_coarse", "粗")
            coastline_map = {
                full_text: "full",
                high_text: "high",
                inter_text: "inter",
                low_text: "low",
                coarse_text: "coarse",
                "最高": "full",
                "高": "high",
                "中": "inter",
                "低": "low",
                "粗": "coarse",
                "Highest": "full",
                "High": "high",
                "Medium": "inter",
                "Low": "low",
                "Coarse": "coarse",
                "full": "full",
                "high": "high",
                "inter": "inter",
                "low": "low",
                "coarse": "coarse"
            }
            boundary = coastline_map.get(str(coastline_precision_config), "full")
            
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
            IS_GLOBAL={1 if is_global else 0},
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
                
                # 转换海岸边界精度
                full_text = tr("step2_coastline_precision_full", "最高")
                high_text = tr("step2_coastline_precision_high", "高")
                inter_text = tr("step2_coastline_precision_inter", "中")
                low_text = tr("step2_coastline_precision_low", "低")
                coarse_text = tr("coastline_coarse", "粗")
                coastline_map = {
                    full_text: "full",
                    "最高": "full",
                    high_text: "high",
                    "高": "high",
                    inter_text: "inter",
                    "中": "inter",
                    low_text: "low",
                    "低": "low",
                    coarse_text: "coarse",
                    "粗": "coarse",
                    "full": "full",
                    "high": "high",
                    "inter": "inter",
                    "low": "low",
                    "coarse": "coarse",
                }
                boundary = coastline_map.get(coastline_precision_config, "full")
                
                boundary_file = os.path.join(ref_dir, f"coastal_bound_{boundary}.mat")
                if not os.path.exists(boundary_file):
                    self.log_signal.emit(
                        tr(
                            "step2_boundary_file_missing",
                            "❌ 未找到边界文件：{path}（精度: {boundary}），请先准备对应的 coastal_bound_*.mat 或降低精度"
                        ).format(path=boundary_file, boundary=boundary)
                    )
                    return False

                # 构建 MATLAB 命令
                matlab_bin_dir = matlab_bin_dir_norm.replace('\\', '/') if matlab_bin_dir_norm else None
                matlab_bin_scripts = None
                if matlab_bin_dir_norm:
                    matlab_bin_scripts = os.path.join(matlab_bin_dir_norm, "bin")
                matlab_bin_scripts_posix = matlab_bin_scripts.replace('\\', '/') if matlab_bin_scripts else None
                matlab_out_dir = output_dir_norm.replace('\\', '/')

                # 同步 grid.nml 参数（MATLAB 版本）
                try:
                    self._update_matlab_grid_nml(
                        matlab_bin_dir_norm,
                        output_dir_norm,
                        ref_dir,
                        ref_grid,
                        boundary,
                        dx_value,
                        dy_value,
                        lon_west,
                        lon_east,
                        lat_south,
                        lat_north,
                        is_global
                    )
                except Exception as e:
                    self.log_signal.emit(tr("step2_update_grid_nml_failed", "⚠️ 更新 grid.nml 失败: {error}").format(error=e))
                
                matlab_cmd = (
                    f"warning('off', 'all'); "
                    f"feature('DefaultCharacterSet', 'UTF8'); "
                    f"addpath('{matlab_bin_scripts_posix}'); "
                    f"cd('{matlab_bin_scripts_posix}'); "
                    f"create_grid('grid.nml');"
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
                lines = fid.readlines()

            grid_line_idx = None
            gtype = None
            for i, line in enumerate(lines):
                stripped = line.strip()
                if not stripped or stripped.startswith("$"):
                    continue
                tokens = stripped.replace("'", "").replace('"', "").split()
                if not tokens:
                    continue
                if tokens[0].upper() in ("RECT", "CURV"):
                    gtype = tokens[0].upper()
                    grid_line_idx = i
                    break

            if grid_line_idx is None:
                self.log(tr("step2_read_meta_failed", "❌ 读取 grid.meta 文件失败"))
                return None, None

            if gtype != "RECT":
                self.log(tr("step2_unsupported_grid_type", "❌ 不支持的网格类型: {gtype}").format(gtype=gtype))
                return None, None

            if grid_line_idx + 3 >= len(lines):
                self.log(tr("step2_read_meta_failed", "❌ 读取 grid.meta 文件失败"))
                return None, None

            # 第一行：Nx Ny
            values = lines[grid_line_idx + 1].split()
            Nx = int(float(values[0]))
            Ny = int(float(values[1]))

            # 第二行：dx dy scale
            values = lines[grid_line_idx + 2].split()
            dx = float(values[0])
            dy = float(values[1])
            scale = float(values[2])
            dx = dx / scale
            dy = dy / scale

            # 第三行：lons lats scale
            values = lines[grid_line_idx + 3].split()
            lons = float(values[0])
            lats = float(values[1])
            scale = float(values[2])

            # 生成经纬度数组
            lon1d = lons / scale + np.arange(Nx) * dx
            lat1d = lats / scale + np.arange(Ny) * dy

            lon, lat = np.meshgrid(lon1d, lat1d)
            return lon, lat
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
