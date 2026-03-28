"""
第二步：生成网格模块 - 业务逻辑部分
包含所有业务逻辑函数（从 ui.py 拆分出来）
"""
import copy
import os
import sys
import json
import glob
import shutil
import tempfile
import re
import subprocess
import threading
import platform
import warnings
import numpy as np
from netCDF4 import Dataset

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt, QMetaObject, pyqtSlot, QProcess
from PyQt6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QGridLayout,
    QHBoxLayout,
    QWidget,
    QSizePolicy,
    QDialog,
    QScrollArea,
    QFrame,
    QApplication,
    QStackedWidget,
    QProgressBar,
)
from PyQt6.QtGui import QPixmap, QShortcut, QKeySequence
from qfluentwidgets import PrimaryPushButton, LineEdit, ComboBox, InfoBar, MessageBoxBase
from setting.language_manager import tr
from setting.config import (
    DX,
    DY,
    LONGITUDE_WEST,
    LONGITUDE_EAST,
    LATITUDE_SORTH,
    LATITUDE_NORTH,
    MATLAB_PATH,
    load_config,
    get_project_gridgen_path,
)
from .grid_viz_worker import VIZ_PREFIX, cache_is_current, cached_image_paths, smc_run_metadata_path
from .rect_grid_desc_parse import parse_rect_grid_description, rect_lon_lat_mesh
from .structured_grid_paths import (
    structured_grid_desc_basenames_to_copy,
    structured_grid_desc_path,
)


REGION_MAP_WORKER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "region_map_worker.py")

# Subprocess PIPE text mode defaults to locale encoding (e.g. GBK on Chinese Windows).
# Grid tools and Python print() often emit UTF-8 → decode errors in reader threads without this.
_SUBPROCESS_IO_ENCODING = "utf-8"
_SUBPROCESS_IO_ERRORS = "replace"


def _structured_grid_mask_path(folder: str):
    """Prefer ``grid.mask_nobound``; if missing, use ``grid.mask`` if present."""
    p = os.path.join(folder, "grid.mask_nobound")
    if os.path.isfile(p):
        return p
    p2 = os.path.join(folder, "grid.mask")
    return p2 if os.path.isfile(p2) else None


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


def _flatten_nested_reference_data_dir(ref_dir: str, log_emit=None) -> None:
    """
    If layout is ``reference_data/reference_data/...``, move inner files up to ``ref_dir``.
    ``log_emit`` is optional ``callable(str)`` (e.g. log_signal.emit).
    """
    inner = os.path.join(ref_dir, "reference_data")
    if not os.path.isdir(inner):
        return
    if log_emit:
        log_emit(
            tr(
                "step2_ref_data_flatten",
                "正在修正嵌套的 reference_data 目录（reference_data/reference_data）…",
            )
        )
    for name in list(os.listdir(inner)):
        src = os.path.join(inner, name)
        dst = os.path.join(ref_dir, name)
        if os.path.exists(dst):
            if os.path.isdir(dst) and os.path.isdir(src):
                for sub in list(os.listdir(src)):
                    shutil.move(
                        os.path.join(src, sub),
                        os.path.join(dst, sub),
                    )
                try:
                    os.rmdir(src)
                except OSError:
                    shutil.rmtree(src)
            else:
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                else:
                    os.remove(dst)
                shutil.move(src, dst)
        else:
            shutil.move(src, dst)
    try:
        os.rmdir(inner)
    except OSError:
        pass


class _ReferenceDataMissingDialog(MessageBoxBase):
    """reference_data 缺失提示弹窗：可一键从 GitHub 下载到默认目录"""

    def __init__(self, parent, on_download_clicked=None):
        super().__init__(parent)
        self._on_download_clicked = on_download_clicked
        self.setWindowTitle(tr("step2_ref_data_missing_title", "reference_data 缺失"))
        self.hideYesButton()
        self.hideCancelButton()
        self.buttonLayout.parent().setVisible(False)

        msg1 = tr(
            "step2_ref_data_missing_msg1",
            "生成网格需要 reference_data 数据，当前缺失",
        )
        label1 = QLabel(msg1)
        label1.setWordWrap(True)
        label1.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        _ref_msg_min_w = 440
        label1.setMinimumWidth(_ref_msg_min_w)
        self.viewLayout.addWidget(label1)

        button_style = parent._get_button_style() if hasattr(parent, "_get_button_style") else ""
        self.btn_download = PrimaryPushButton(tr("step2_ref_data_ok", "下载"))
        self.btn_download.setStyleSheet(button_style)
        self.btn_download.clicked.connect(self._on_download)
        self.viewLayout.addWidget(self.btn_download)

        self.btn_cancel = PrimaryPushButton(tr("step2_ref_data_cancel", "取消"))
        self.btn_cancel.setStyleSheet(button_style)
        self.btn_cancel.clicked.connect(self.reject)
        self.viewLayout.addWidget(self.btn_cancel)

        # MessageBoxBase 默认内容区偏窄，中英文说明易被挤成细长条
        _ref_dlg_min_w = max(_ref_msg_min_w + 80, 520)
        self.setMinimumWidth(_ref_dlg_min_w)
        card = getattr(self, "widget", None)
        if card is not None:
            card.setMinimumWidth(_ref_dlg_min_w)

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


class _ScaledMapLabel(QLabel):
    """高分辨率地图缩放到可用区域（保持宽高比、居中），避免滚动条。"""

    def __init__(self, full_pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._full = full_pixmap
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(1, 1)
        self.setScaledContents(False)

    def sizeHint(self):
        return QtCore.QSize(320, 240)

    def minimumSizeHint(self):
        return QtCore.QSize(1, 1)

    def _device_pixel_ratio(self) -> float:
        wh = self.window().windowHandle()
        if wh is not None:
            return float(wh.devicePixelRatio())
        scr = self.screen()
        if scr is not None:
            return float(scr.devicePixelRatio())
        return 1.0

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_scale()

    def showEvent(self, event):
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self._apply_scale)

    def _apply_scale(self):
        if self._full is None or self._full.isNull():
            return
        r = self.contentsRect()
        if r.width() < 2 or r.height() < 2:
            return
        dpr = max(1.0, self._device_pixel_ratio())
        tw = max(2, int(round(r.width() * dpr)))
        th = max(2, int(round(r.height() * dpr)))
        scaled = self._full.scaled(
            QtCore.QSize(tw, th),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(dpr)
        QLabel.setPixmap(self, scaled)


class _RegionMapDialog(MessageBoxBase):
    """第二步「查看地图」：先显示加载，再显示子进程生成的地图；Esc/点遮罩关闭。"""

    def __init__(self, parent, *, map_aspect_wh: float | None = None):
        super().__init__(parent)
        self.setWindowTitle("")
        self._map_aspect_wh = float(map_aspect_wh) if map_aspect_wh and map_aspect_wh > 0 else 4.0 / 3.0
        self._kill_external_cb = None
        self.hideYesButton()
        self.hideCancelButton()
        self.buttonLayout.parent().setVisible(False)

        self._stack = QStackedWidget()
        self._stack.setMinimumSize(320, 240)
        self._stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        loading_w = QWidget()
        loading_layout = QVBoxLayout(loading_w)
        loading_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._loading_label = QLabel(tr("step2_region_map_loading", "正在生成地图…"))
        self._loading_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._loading_label.setWordWrap(True)
        loading_layout.addWidget(self._loading_label)
        self._loading_bar = QProgressBar()
        self._loading_bar.setRange(0, 0)
        self._loading_bar.setFixedWidth(280)
        loading_layout.addWidget(self._loading_bar, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(loading_w)

        self._content_host = QWidget()
        self._content_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._content_layout = QVBoxLayout(self._content_host)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._stack.addWidget(self._content_host)
        self._stack.setCurrentIndex(0)

        self.viewLayout.addWidget(self._stack, 1)

        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self._close_dialog)

        if hasattr(self, "setClosableOnMaskClicked"):
            self.setClosableOnMaskClicked(True)

    def set_kill_callback(self, cb):
        self._kill_external_cb = cb

    def show_map_content(self, map_widget: QWidget):
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        map_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._content_layout.addWidget(map_widget, 1)
        self._stack.setCurrentIndex(1)
        if isinstance(map_widget, _ScaledMapLabel):
            QtCore.QTimer.singleShot(0, map_widget._apply_scale)
        QtCore.QTimer.singleShot(0, self._refine_region_map_card_size)

    def showEvent(self, event):
        super().showEvent(event)
        self._region_map_refine_pass = 0
        QtCore.QTimer.singleShot(0, self._fit_to_parent_window)

    def reject(self):
        """遮罩点击会调 reject；绕过 MaskDialogBase.done 渐隐以防 exec 不返回。"""
        if callable(self._kill_external_cb):
            self._kill_external_cb()
            self._kill_external_cb = None
        QDialog.done(self, int(QDialog.DialogCode.Rejected))

    def _close_dialog(self):
        if callable(self._kill_external_cb):
            self._kill_external_cb()
            self._kill_external_cb = None
        QDialog.done(self, int(QDialog.DialogCode.Accepted))

    def closeEvent(self, event):
        if callable(self._kill_external_cb):
            self._kill_external_cb()
            self._kill_external_cb = None
        super().closeEvent(event)

    def _region_map_avail_rect(self):
        """主窗口可用区域（逻辑像素），用于嵌入地图卡片。"""
        parent = self.parentWidget()
        ratio_w, ratio_h = 0.90, 0.82
        if parent is not None and parent.isVisible():
            pr = parent.frameGeometry()
            return int(pr.width() * ratio_w), int(pr.height() * ratio_h)
        screen = QApplication.primaryScreen()
        ag = screen.availableGeometry() if screen is not None else None
        if ag is not None:
            return int(ag.width() * 0.88), int(ag.height() * 0.82)
        return 1000, 760

    def _fit_to_parent_window(self):
        """卡片先按可用区域与地图纵横比占位；标题栏与边距会吃掉高度，再由 _refine 按实际内容区修正。"""
        avail_w, avail_h = self._region_map_avail_rect()
        min_w, min_h = 400, 300
        max_w, max_h = 1920, 1080
        a = float(np.clip(self._map_aspect_wh, 0.2, 14.0))
        if avail_w / max(avail_h, 1) > a:
            dh = avail_h
            dw = int(round(dh * a))
        else:
            dw = avail_w
            dh = int(round(dw / a))

        dw = max(min_w, min(dw, max_w))
        dh = max(min_h, min(dh, max_h))
        card = getattr(self, "widget", None)
        if card is not None:
            card.setFixedSize(dw, dh)
            card.updateGeometry()
        else:
            self.resize(dw, dh)
        QtCore.QTimer.singleShot(0, self._refine_region_map_card_size)

    def _refine_region_map_card_size(self):
        """按 MessageBox 标题栏与边距，使 _stack 可视区宽高比与地图 PNG 一致，消除上下/左右大块留白。"""
        card = getattr(self, "widget", None)
        if card is None:
            return
        self._region_map_refine_pass = getattr(self, "_region_map_refine_pass", 0) + 1
        if self._region_map_refine_pass > 5:
            return

        avail_w, avail_h = self._region_map_avail_rect()
        min_w, min_h = 400, 300
        max_w, max_h = 1920, 1080
        a = float(np.clip(self._map_aspect_wh, 0.2, 14.0))

        cw = max(0, card.width() - self._stack.width())
        ch = max(0, card.height() - self._stack.height())
        iw_max = max(80, avail_w - cw)
        ih_max = max(80, avail_h - ch)

        if iw_max / max(ih_max, 1) > a:
            ih = ih_max
            iw = min(iw_max, int(round(ih * a)))
        else:
            iw = iw_max
            ih = min(ih_max, int(round(iw / max(a, 1e-6))))

        dw = max(min_w, min(iw + cw, max_w))
        dh = max(min_h, min(ih + ch, max_h))

        if abs(dw - card.width()) > 1 or abs(dh - card.height()) > 1:
            card.setFixedSize(dw, dh)
            card.updateGeometry()
            QtCore.QTimer.singleShot(0, self._refine_region_map_card_size)


class StepTwoServiceMixin:
    """第二步相关的业务逻辑 Mixin"""

    def _cleanup_region_map_temp_files(self):
        for p in getattr(self, "_region_map_temp_paths", None) or []:
            try:
                if p and os.path.isfile(p):
                    os.remove(p)
            except OSError:
                pass

    def _kill_region_map_process(self):
        p = getattr(self, "_region_map_proc", None)
        if p is not None and p.state() != QProcess.ProcessState.NotRunning:
            p.kill()
            p.waitForFinished(3000)
        self._region_map_proc = None

    def _on_region_map_process_finished(self, exit_code, exit_status):
        dlg = getattr(self, "_region_map_dialog", None)
        png_path = getattr(self, "_region_map_out_png", None)
        proc = self.sender()
        err_txt = ""
        if proc is not None:
            err_txt = bytes(proc.readAllStandardError()).decode("utf-8", errors="replace").strip()
        self._region_map_proc = None

        if dlg is None:
            self._cleanup_region_map_temp_files()
            return

        if exit_code != 0:
            self._cleanup_region_map_temp_files()
            msg = err_txt or tr("step2_region_map_render_failed", "地图渲染失败")
            if len(msg) > 800:
                msg = msg[:800] + "…"
            InfoBar.warning(
                title=tr("step2_region_map_error_title", "查看地图"),
                content=msg,
                duration=5000,
                parent=self,
            )
            dlg.reject()
            return

        if not png_path or not os.path.isfile(png_path):
            self._cleanup_region_map_temp_files()
            InfoBar.warning(
                title=tr("step2_region_map_error_title", "查看地图"),
                content=tr("step2_region_map_png_missing", "未生成地图图片"),
                duration=4000,
                parent=self,
            )
            dlg.reject()
            return

        pm = QPixmap(png_path)
        if pm.isNull():
            self._cleanup_region_map_temp_files()
            InfoBar.warning(
                title=tr("step2_region_map_error_title", "查看地图"),
                content=tr("step2_region_map_png_invalid", "无法加载地图图片"),
                duration=4000,
                parent=self,
            )
            dlg.reject()
            return

        map_lbl = _ScaledMapLabel(pm)
        dlg.show_map_content(map_lbl)

        ctx = getattr(self, "_region_map_log_ctx", None) or {}
        if ctx.get("is_nested"):
            self.log(tr("step2_nested_map_displayed", "📍 已显示嵌套网格地图"))
            self.log(
                tr(
                    "step2_outer_grid_range",
                    "   外网格: 经度 [{lon_min}, {lon_max}], 纬度 [{lat_min}, {lat_max}]",
                ).format(
                    lon_min=f"{ctx['outer_lon_min']:.2f}",
                    lon_max=f"{ctx['outer_lon_max']:.2f}",
                    lat_min=f"{ctx['outer_lat_min']:.2f}",
                    lat_max=f"{ctx['outer_lat_max']:.2f}",
                )
            )
            self.log(
                tr(
                    "step2_inner_grid_range",
                    "   内网格: 经度 [{lon_min}, {lon_max}], 纬度 [{lat_min}, {lat_max}]",
                ).format(
                    lon_min=f"{ctx['inner_lon_min']:.2f}",
                    lon_max=f"{ctx['inner_lon_max']:.2f}",
                    lat_min=f"{ctx['inner_lat_min']:.2f}",
                    lat_max=f"{ctx['inner_lat_max']:.2f}",
                )
            )
        else:
            self.log(
                tr(
                    "step2_map_range_displayed",
                    "📍 已显示地图范围: 经度 [{lon_min}, {lon_max}], 纬度 [{lat_min}, {lat_max}]",
                ).format(
                    lon_min=f"{ctx['outer_lon_min']:.2f}",
                    lon_max=f"{ctx['outer_lon_max']:.2f}",
                    lat_min=f"{ctx['outer_lat_min']:.2f}",
                    lat_max=f"{ctx['outer_lat_max']:.2f}",
                )
            )
    
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

    @staticmethod
    def _parse_grid_ww3_lon_lat_bounds(ww3_path):
        """从 Gmsh 文本格式 grid.ww3 的 $Nodes 段读取结点经纬度包围盒。"""
        try:
            lons = []
            lats = []
            with open(ww3_path, encoding="utf-8", errors="ignore") as f:
                in_nodes = False
                n_expected = None
                n_read = 0
                for raw in f:
                    line = raw.strip()
                    if line == "$Nodes":
                        in_nodes = True
                        n_expected = None
                        n_read = 0
                        continue
                    if in_nodes and line == "$EndNodes":
                        break
                    if not in_nodes:
                        continue
                    if n_expected is None:
                        parts = line.split()
                        if not parts:
                            continue
                        try:
                            n_expected = int(parts[0])
                        except ValueError:
                            n_expected = 0
                        continue
                    if n_read >= n_expected:
                        break
                    parts = line.split()
                    if len(parts) >= 3:
                        try:
                            lons.append(float(parts[1]))
                            lats.append(float(parts[2]))
                            n_read += 1
                        except ValueError:
                            pass
            if not lons:
                return None
            return {
                "lon_min": min(lons),
                "lon_max": max(lons),
                "lat_min": min(lats),
                "lat_max": max(lats),
            }
        except Exception:
            return None

    @staticmethod
    def _format_unst_num_for_edit(v):
        try:
            x = float(v)
        except (TypeError, ValueError):
            return None
        s = f"{x:.8f}".rstrip("0").rstrip(".")
        return s if s else "0"

    def _step2_apply_unstructured_from_grid_ww3(self, ww3_path):
        """检测到 grid.ww3：切到非结构网格、普通网格类型，并填充经纬度与 spacing（优先 unst_msh_gen_config.json）。"""
        if not hasattr(self, "mesh_type_combo"):
            return
        utext = tr("step2_mesh_type_unstructured", "非结构网格")
        normal_text = tr("step2_grid_type_normal", "普通网格")

        if hasattr(self, "_set_step2_grid_type"):
            self._set_step2_grid_type(normal_text, skip_block_check=True)

        self.mesh_type_combo.blockSignals(True)
        self.mesh_type_combo.setCurrentText(utext)
        self.mesh_type_combo.blockSignals(False)
        self.mesh_type_var = utext

        if hasattr(self, "unst_spacing_widget"):
            self.unst_spacing_widget.setVisible(True)
        if hasattr(self, "_update_step2_grid_type_row_visibility"):
            self._update_step2_grid_type_row_visibility()
        if hasattr(self, "_update_step2_dx_dy_visibility"):
            self._update_step2_dx_dy_visibility()
        if hasattr(self, "_refresh_step2_mesh_type_combo_enabled"):
            self._refresh_step2_mesh_type_combo_enabled()

        folder = self.selected_folder
        cfg_path = os.path.join(folder, "unst_msh_gen_config.json")
        reg = None
        spacing = None
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, encoding="utf-8") as cf:
                    cj = json.load(cf)
                r0 = cj.get("regional")
                reg = r0 if isinstance(r0, dict) else None
                sp0 = cj.get("spacing")
                spacing = sp0 if isinstance(sp0, dict) else None
            except Exception:
                reg = None
                spacing = None

        if spacing and hasattr(self, "unst_hmax_edit"):
            for key, edit_attr in (
                ("hmax", "unst_hmax_edit"),
                ("hshr", "unst_hshr_edit"),
                ("dhdx", "unst_dhdx_edit"),
            ):
                if key in spacing:
                    s = self._format_unst_num_for_edit(spacing[key])
                    if s is not None:
                        getattr(self, edit_attr).setText(s)

        lon_w = lon_e = lat_s = lat_n = None
        if reg and all(k in reg for k in ("lon_min", "lon_max", "lat_min", "lat_max")):
            try:
                lon_w = float(reg["lon_min"])
                lon_e = float(reg["lon_max"])
                lat_s = float(reg["lat_min"])
                lat_n = float(reg["lat_max"])
            except (TypeError, ValueError):
                lon_w = lon_e = lat_s = lat_n = None

        if lon_w is None:
            b = self._parse_grid_ww3_lon_lat_bounds(ww3_path)
            if b:
                lon_w, lon_e = b["lon_min"], b["lon_max"]
                lat_s, lat_n = b["lat_min"], b["lat_max"]

        if lon_w is not None and hasattr(self, "lon_west_edit"):
            self.lon_west_edit.setText(f"{lon_w:.4f}")
            self.lon_east_edit.setText(f"{lon_e:.4f}")
            self.lat_south_edit.setText(f"{lat_s:.4f}")
            self.lat_north_edit.setText(f"{lat_n:.4f}")

        if hasattr(self, "log"):
            self.log(tr("step2_unst_auto_from_ww3", "📐 检测到 grid.ww3，已切换为非结构网格并读取范围与参数"))

    @staticmethod
    def _folder_has_any_dat_files(folder: str) -> bool:
        try:
            for name in os.listdir(folder):
                if name.startswith("."):
                    continue
                p = os.path.join(folder, name)
                if os.path.isfile(p) and name.lower().endswith(".dat"):
                    return True
        except OSError:
            pass
        return False

    @staticmethod
    def _is_step2_smc_grid_json_doc(doc: object) -> bool:
        """与 smc_generator 输入一致的平铺 grid.json（可读取范围与 physics）。"""
        if not isinstance(doc, dict):
            return False
        inp = doc.get("input")
        grid = doc.get("grid")
        if not isinstance(inp, dict) or not isinstance(grid, dict):
            return False
        if not str(inp.get("bathymetry_file") or "").strip():
            return False
        return "n_levels" in grid

    @staticmethod
    def _normalize_step2_smc_config_root(doc: object) -> dict | None:
        """平铺配置，或旧版运行元数据外层下嵌套的 ``grid_json``。"""
        if StepTwoServiceMixin._is_step2_smc_grid_json_doc(doc):
            return doc  # type: ignore[arg-type]
        if not isinstance(doc, dict):
            return None
        inner = doc.get("grid_json")
        if isinstance(inner, dict) and StepTwoServiceMixin._is_step2_smc_grid_json_doc(inner):
            return inner
        return None

    @staticmethod
    def _folder_triggers_smc_autoload(folder: str) -> bool:
        """存在 SMC 主产物 grid_cell.dat，或目录内任一 .dat 文件。"""
        try:
            cell = os.path.join(folder, "grid_cell.dat")
            if os.path.isfile(cell) and os.path.getsize(cell) > 0:
                return True
        except OSError:
            pass
        return StepTwoServiceMixin._folder_has_any_dat_files(folder)

    @staticmethod
    def _smc_regional_bounds_from_grid_dict(grid: dict) -> tuple[float, float, float, float] | None:
        b = grid.get("regional_bounds")
        if not isinstance(b, dict):
            return None

        def _pick(keys: list[str]) -> float | None:
            for k in keys:
                v = b.get(k)
                if v is None:
                    continue
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
            return None

        lon_w = _pick(["west_lon", "xstart", "lon_min", "min_lon"])
        lat_s = _pick(["south_lat", "ystart", "lat_min", "min_lat"])
        lon_e = _pick(["east_lon", "xend", "lon_max", "max_lon"])
        lat_n = _pick(["north_lat", "yend", "lat_max", "max_lat"])
        if lon_w is None or lat_s is None or lon_e is None or lat_n is None:
            return None
        return lon_w, lon_e, lat_s, lat_n

    def _step2_apply_smc_from_grid_json(self, gj: dict) -> None:
        """切换第二步为 SMC，并按 grid.json 填写外框范围与 SMC 三参数。"""
        smc_text = tr("step2_mesh_type_smc", "SMC 网格")
        if hasattr(self, "mesh_type_combo"):
            self.mesh_type_combo.blockSignals(True)
            idx = -1
            for i in range(self.mesh_type_combo.count()):
                try:
                    if self.mesh_type_combo.itemText(i) == smc_text:
                        idx = i
                        break
                except Exception:
                    continue
            if idx >= 0:
                self.mesh_type_combo.setCurrentIndex(idx)
            elif self.mesh_type_combo.count() > 2:
                # 顺序：矩形、曲线、SMC、非结构（与 create_step_2_card 一致）
                self.mesh_type_combo.setCurrentIndex(2)
            else:
                self.mesh_type_combo.setCurrentText(smc_text)
            self.mesh_type_combo.blockSignals(False)
        if hasattr(self, "_set_step2_mesh_type"):
            self._set_step2_mesh_type(smc_text)

        grid = gj.get("grid") or {}
        phy = gj.get("physics") or {}

        if bool(grid.get("global", False)):
            lon_w, lon_e, lat_s, lat_n = -180.0, 180.0, -90.0, 90.0
        else:
            ext = self._smc_regional_bounds_from_grid_dict(grid)
            if ext is not None:
                lon_w, lon_e, lat_s, lat_n = ext
            else:
                lon_w = lon_e = lat_s = lat_n = None

        if (
            lon_w is not None
            and hasattr(self, "lon_west_edit")
            and hasattr(self, "lon_east_edit")
            and hasattr(self, "lat_south_edit")
            and hasattr(self, "lat_north_edit")
        ):
            self.lon_west_edit.setText(f"{lon_w:.4f}")
            self.lon_east_edit.setText(f"{lon_e:.4f}")
            self.lat_south_edit.setText(f"{lat_s:.4f}")
            self.lat_north_edit.setText(f"{lat_n:.4f}")

        try:
            nlv = int(grid.get("n_levels", 2))
        except (TypeError, ValueError):
            nlv = 2
        if hasattr(self, "smc_n_levels_edit"):
            self.smc_n_levels_edit.setText(str(nlv))

        depmin = phy.get("depmin", 0.0)
        dshalw = phy.get("dshalw", -150.0)
        try:
            depmin_f = float(depmin)
        except (TypeError, ValueError):
            depmin_f = 0.0
        try:
            dshalw_f = float(dshalw)
        except (TypeError, ValueError):
            dshalw_f = -150.0
        if hasattr(self, "smc_depmin_edit"):
            self.smc_depmin_edit.setText(f"{depmin_f:g}")
        if hasattr(self, "smc_dshalw_edit"):
            self.smc_dshalw_edit.setText(f"{dshalw_f:g}")

    def _try_apply_smc_workspace_from_folder(self) -> bool:
        """目录含 grid_cell.dat 或 .dat 文件，且 grid.json 可解析为 SMC 配置时，切换 SMC 并填充第二步。"""
        folder = self.selected_folder
        if not folder or not os.path.isdir(folder):
            return False
        if not self._folder_triggers_smc_autoload(folder):
            return False
        gj_path = os.path.join(folder, "grid.json")
        if not os.path.isfile(gj_path) or os.path.getsize(gj_path) <= 0:
            return False
        try:
            with open(gj_path, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return False
        gj = self._normalize_step2_smc_config_root(raw)
        if not gj:
            return False
        self._step2_apply_smc_from_grid_json(gj)
        if hasattr(self, "log"):
            self.log(
                tr(
                    "step2_smc_auto_from_workspace",
                    "📐 检测到工作目录中的 .dat 与 SMC 配置 grid.json，已切换为 SMC 网格并读取范围与参数",
                )
            )
        return True

    def _load_grid_info_to_step2(self):
        """读取当前工作目录的网格文件范围和精度，填充到第二步的输入框"""
        if not self.selected_folder:
            return

        ww3_path = os.path.join(self.selected_folder, "grid.ww3")
        if os.path.isfile(ww3_path) and os.path.getsize(ww3_path) > 0:
            self._step2_apply_unstructured_from_grid_ww3(ww3_path)
            return

        if self._try_apply_smc_workspace_from_folder():
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
            # 普通网格模式：读取 grid.nml（WW3 描述）或旧版 ww3_grid.nml.* / grid.meta
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

            if not chinese_font:
                warnings.filterwarnings('ignore', category=UserWarning, module='cartopy')
        except Exception:
            warnings.filterwarnings('ignore', category=UserWarning, module='cartopy')

        # 计算显示范围与纵横比；实际绘图在子进程 region_map_worker 中执行（Agg），避免阻塞 UI
        original_display_lon_max = display_lon_max
        original_display_lon_min = display_lon_min

        original_lon_max = outer_lon_max if not is_nested else max(outer_lon_max, inner_lon_max)
        original_lon_min = outer_lon_min if not is_nested else min(outer_lon_min, inner_lon_min)

        if original_lon_min > 180 and original_lon_max > 180:
            original_lon_max = original_lon_max - 360
            original_lon_min = original_lon_min - 360
            display_lon_max = display_lon_max - 360
            display_lon_min = display_lon_min - 360
        elif original_lon_max > 180 and original_lon_min <= 180:
            original_lon_max = 180.0
            margin = 2.0
            display_lon_max = min(180.0 + margin, 182.0)

        if display_lon_min < 0 or display_lon_max < 0 or original_lon_min < 0 or original_lon_max < 0:
            central_lon = 180
        else:
            central_lon = 0
            if original_display_lon_max > 180:
                margin = original_display_lon_max - original_lon_max
                display_lon_max = min(180.0 + margin, 185.0)
            elif original_lon_max >= 179:
                margin = original_display_lon_max - original_lon_max
                display_lon_max = min(180.0, original_lon_max + margin)

        lat_center = (display_lat_min + display_lat_max) / 2.0
        lon_span = max(float(display_lon_max - display_lon_min), 1e-6)
        lat_span = max(float(display_lat_max - display_lat_min), 1e-6)
        cos_ref = max(abs(np.cos(np.radians(lat_center))), 0.08)
        map_aspect_wh = float(np.clip((lon_span * cos_ref) / lat_span, 0.2, 14.0))

        # 略小英寸尺寸可明显减少像素量、加快子进程渲染；界面侧会按比例放大
        fig_base = 8.0
        fig_min_side = 3.5
        if map_aspect_wh >= 1.0:
            fig_w = max(fig_base, fig_min_side * map_aspect_wh)
            fig_h = fig_w / map_aspect_wh
        else:
            fig_h = max(fig_base, fig_min_side / map_aspect_wh)
            fig_w = fig_h * map_aspect_wh

        scr = self.screen()
        dpr = float(scr.devicePixelRatio()) if scr is not None else 1.0
        # 导出 DPI 随屏幕缩放；上限略降以缩短 savefig 时间，界面仍按 devicePixelRatio 缩放
        map_dpi = int(round(100 * max(1.0, dpr)))
        map_dpi = min(max(map_dpi, 96), 200)

        cfg = {
            "display_extent": [display_lon_min, display_lon_max, display_lat_min, display_lat_max],
            "central_longitude": central_lon,
            "is_nested": bool(is_nested),
            "outer_rect": [outer_lon_min, outer_lon_max, outer_lat_min, outer_lat_max],
            "fig_width_in": float(fig_w),
            "fig_height_in": float(fig_h),
            "dpi": map_dpi,
        }
        if is_nested:
            cfg["inner_rect"] = [inner_lon_min, inner_lon_max, inner_lat_min, inner_lat_max]
            cfg["label_outer"] = tr("step3_outer_grid_label", "外网格")
            cfg["label_inner"] = tr("step3_inner_grid_label", "内网格")
        else:
            cfg["label_single"] = tr("step2_map_range_label", "网格范围")
        if chinese_font:
            cfg["chinese_font"] = chinese_font

        if not os.path.isfile(REGION_MAP_WORKER_SCRIPT):
            InfoBar.warning(
                title=tr("step2_region_map_error_title", "查看地图"),
                content=tr("step2_region_map_worker_missing", "未找到 region_map_worker.py"),
                duration=4000,
                parent=self,
            )
            return

        cfg_fd, cfg_path = tempfile.mkstemp(suffix=".json", prefix="ww3tool_region_map_")
        png_fd, png_path = tempfile.mkstemp(suffix=".png", prefix="ww3tool_region_map_")
        os.close(cfg_fd)
        os.close(png_fd)
        try:
            with open(cfg_path, "w", encoding="utf-8") as cf:
                json.dump(cfg, cf, ensure_ascii=False, indent=0)
        except Exception as e:
            for p in (cfg_path, png_path):
                try:
                    if os.path.isfile(p):
                        os.remove(p)
                except OSError:
                    pass
            InfoBar.warning(
                title=tr("step2_region_map_error_title", "查看地图"),
                content=str(e),
                duration=4000,
                parent=self,
            )
            return

        self._region_map_temp_paths = [cfg_path, png_path]
        self._region_map_out_png = png_path
        self._region_map_log_ctx = {
            "is_nested": is_nested,
            "outer_lon_min": outer_lon_min,
            "outer_lon_max": outer_lon_max,
            "outer_lat_min": outer_lat_min,
            "outer_lat_max": outer_lat_max,
            "inner_lon_min": inner_lon_min,
            "inner_lon_max": inner_lon_max,
            "inner_lat_min": inner_lat_min,
            "inner_lat_max": inner_lat_max,
        }

        map_window = _RegionMapDialog(self, map_aspect_wh=map_aspect_wh)
        self._region_map_dialog = map_window

        def _kill():
            self._kill_region_map_process()

        map_window.set_kill_callback(_kill)

        proc = QProcess(self)
        self._region_map_proc = proc
        proc.finished.connect(self._on_region_map_process_finished)
        proc.start(sys.executable, [REGION_MAP_WORKER_SCRIPT, cfg_path, png_path])

        try:
            map_window.exec()
        finally:
            self._cleanup_region_map_temp_files()
            self._region_map_dialog = None
            self._region_map_proc = None
            self._region_map_out_png = None
            self._region_map_temp_paths = []
            self._region_map_log_ctx = None

    # ========== 工具函数 ==========
    def _is_nested_grid(self, grid_type):
        """检查是否为嵌套网格（支持翻译后的文本）"""
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        return grid_type == nested_text or grid_type == "嵌套网格"

    # ========== 辅助函数（路径、缓存相关）==========
    def _get_gridgen_path(self):
        """WW3-Grid-Generator 根目录（reference_data、unst_msh_gen、cache 等与设置无关）。"""
        return get_project_gridgen_path()

    def _get_gridgen_bin_path(self):
        """MATLAB gridgen 根目录：…/structured_generator/gridgen（含 bin/ 与 create_grid.m）。"""
        gridgen_path = self._get_gridgen_path()
        return (
            os.path.normpath(
                os.path.join(gridgen_path, "structured_generator", "gridgen")
            )
            if gridgen_path
            else None
        )

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
                # 如果是相对路径，相对于项目 WW3-Grid-Generator 根目录
                ref_dir = os.path.join(gridgen_path, ref_data_path)
        else:
            # 如果配置为空，使用默认路径
            ref_dir = os.path.join(gridgen_path, "reference_data")
        
        # 如果路径不存在，尝试备用路径
        if not os.path.exists(ref_dir) and gridgen_path:
            ref_dir = os.path.join(gridgen_path, "reference_data")
        
        # 规范化路径
        ref_dir = os.path.normpath(os.path.abspath(ref_dir))
        return ref_dir

    def _resolve_path_via_reference_data_setting(self, anchor_dir: str, rel_path: str):
        """
        解析相对 anchor_dir 的路径；若文件不存在且相对路径指向仓库默认的 reference_data
        （如 ../reference_data/*.nc），再尝试 REFERENCE_DATA_PATH 下的同名文件。
        """
        rel_path = str(rel_path or "").strip()
        if not rel_path:
            return None
        if os.path.isabs(rel_path):
            p = os.path.normpath(rel_path)
            return p if os.path.isfile(p) else None
        primary = os.path.normpath(os.path.join(os.path.abspath(anchor_dir), rel_path))
        if os.path.isfile(primary):
            return primary
        if "reference_data" in rel_path.replace("\\", "/").split("/"):
            alt = os.path.normpath(
                os.path.join(self._get_reference_data_path(), os.path.basename(rel_path))
            )
            if os.path.isfile(alt):
                return alt
        return None

    def _get_unstructured_generator_dir(self):
        """WW3-Grid-Generator/unstructured_generator（create_grid.py / unst_msh_gen / jigsaw-python）。"""
        return os.path.normpath(os.path.join(self._get_gridgen_path(), "unstructured_generator"))

    def _get_unstructured_unst_msh_gen_dir(self):
        return os.path.normpath(os.path.join(self._get_unstructured_generator_dir(), "unst_msh_gen"))

    def _get_unstructured_jigsaw_root(self):
        return os.path.normpath(os.path.join(self._get_unstructured_generator_dir(), "jigsaw-python"))

    def _get_smc_generator_dir(self):
        """WW3-Grid-Generator/smc_generator（create_grid.py、PySMCs）。"""
        return os.path.normpath(os.path.join(self._get_gridgen_path(), "smc_generator"))

    @staticmethod
    def _unst_jigsaw_shared_lib_basename():
        """jigsaw-python 安装后动态库文件名（与 jigsawpy/libsaw.py 一致）。"""
        s = platform.system()
        if s == "Windows":
            return "jigsaw.dll"
        if s == "Darwin":
            return "libjigsaw.dylib"
        return "libjigsaw.so"

    def _unst_jigsaw_lib_path(self, jig_root):
        """jig_root 为 jigsaw-python 根目录（内含 jigsawpy/）。"""
        return os.path.join(
            jig_root,
            "jigsawpy",
            "_lib",
            self._unst_jigsaw_shared_lib_basename(),
        )

    def _is_jigsaw_library_built(self, jig_root):
        """JIGSAW 是否已编译到 jigsawpy/_lib（jigsawpy 通过 ctypes 加载该库）。"""
        p = self._unst_jigsaw_lib_path(jig_root)
        try:
            return os.path.isfile(p) and os.path.getsize(p) > 0
        except OSError:
            return False

    def _ensure_jigsaw_built(self, jig_root):
        """若无动态库则在 jigsaw-python 目录执行 build.py（cmake）；成功返回 True。"""
        if self._is_jigsaw_library_built(jig_root):
            return True
        build_py = os.path.join(jig_root, "build.py")
        ext_src = os.path.join(jig_root, "external", "jigsaw")
        if not os.path.isfile(build_py):
            self.log_signal.emit(
                tr(
                    "step2_jigsaw_build_script_missing",
                    "❌ 未找到 JIGSAW 编译脚本：{path}",
                ).format(path=build_py)
            )
            return False
        if not os.path.isdir(ext_src):
            self.log_signal.emit(
                tr(
                    "step2_jigsaw_external_missing",
                    "❌ 未找到 JIGSAW 源码目录：{path}（请确认 jigsaw-python 子模块/目录完整）",
                ).format(path=ext_src)
            )
            return False
        if not shutil.which("cmake"):
            self.log_signal.emit(
                tr(
                    "step2_jigsaw_cmake_missing_log",
                    "❌ 未在 PATH 中找到 cmake，无法自动编译 JIGSAW。请安装 CMake 或 Xcode Command Line Tools（macOS）后重试。",
                )
            )
            return False
        self.log_signal.emit(
            tr(
                "step2_jigsaw_building",
                "🔧 未检测到 JIGSAW 动态库（{lib}），正在 jigsaw-python 下执行 build.py 编译（可能需要数分钟）…",
            ).format(lib=self._unst_jigsaw_shared_lib_basename())
        )
        argv = [sys.executable, "-u", "build.py"]
        bt = (os.environ.get("WW3TOOL_JIGSAW_CMAKE_BUILD_TYPE") or "").strip()
        if bt:
            argv.extend(["--cmake-build-type", bt])
            self.log_signal.emit(
                tr(
                    "step2_jigsaw_build_type_env",
                    "   使用环境变量 WW3TOOL_JIGSAW_CMAKE_BUILD_TYPE={bt}（例如 macOS 可试 Debug）",
                ).format(bt=bt)
            )
        try:
            ret = self._stream_subprocess_to_log(argv, cwd=jig_root, env=os.environ.copy())
        except Exception as e:
            self.log_signal.emit(
                tr(
                    "step2_jigsaw_build_exception",
                    "❌ JIGSAW 编译过程异常：{err}",
                ).format(err=e)
            )
            return False
        if ret != 0:
            self.log_signal.emit(
                tr(
                    "step2_jigsaw_build_failed_code",
                    "❌ JIGSAW 编译失败，退出码：{code}。可在终端进入 jigsaw-python 目录手动执行：python3 build.py",
                ).format(code=ret)
            )
            return False
        if not self._is_jigsaw_library_built(jig_root):
            self.log_signal.emit(
                tr(
                    "step2_jigsaw_build_no_lib",
                    "❌ 编译结束仍未找到 {lib}，请检查 jigsaw-python/build.py 输出或手动编译。",
                ).format(lib=self._unst_jigsaw_shared_lib_basename())
            )
            return False
        self.log_signal.emit(tr("step2_jigsaw_build_ok", "✅ JIGSAW 动态库已就绪。"))
        return True

    def _is_step2_unstructured_mesh(self):
        """当前第二步是否选择「非结构网格」。"""
        ut = tr("step2_mesh_type_unstructured", "非结构网格")
        return getattr(self, "mesh_type_var", "") == ut

    def _is_step2_smc_mesh(self):
        """当前第二步是否选择「SMC 网格」。"""
        st = tr("step2_mesh_type_smc", "SMC 网格")
        return getattr(self, "mesh_type_var", "") == st

    def _get_smc_bathy_path(self):
        """
        SMC create_grid 所需规则经纬网格水深 NetCDF 路径。
        优先 public/config.json 的 SMC_BATHYMETRY_FILE；其次 smc_generator/grid.json 中 input.bathymetry_file；
        再否则 reference_data 中 etopo2/gebco/etopo1。
        """
        cfg = load_config()
        custom = (cfg.get("SMC_BATHYMETRY_FILE") or "").strip()
        gridgen_root = self._get_gridgen_path()
        if custom:
            path = custom if os.path.isabs(custom) else os.path.normpath(os.path.join(gridgen_root, custom))
            return path if os.path.isfile(path) else None
        smc_dir = self._get_smc_generator_dir()
        tpl = os.path.join(smc_dir, "grid.json")
        if os.path.isfile(tpl):
            try:
                with open(tpl, encoding="utf-8") as f:
                    raw = json.load(f)
                inp = raw.get("input") or {}
                rel = str(inp.get("bathymetry_file") or "").strip()
                if rel:
                    p = (
                        rel
                        if os.path.isabs(rel)
                        else self._resolve_path_via_reference_data_setting(smc_dir, rel)
                    )
                    if p and os.path.isfile(p):
                        return p
            except Exception:
                pass
        ref_dir = self._get_reference_data_path()
        for name in ("etopo2.nc", "gebco.nc", "etopo1.nc"):
            p = os.path.join(ref_dir, name)
            if os.path.isfile(p):
                return p
        return None

    def _check_smc_prerequisites(self):
        """SMC 生成前检查（目录、PySMCs、Python 依赖、水深文件）。返回 (ok, err_msg)。"""
        smc_dir = self._get_smc_generator_dir()
        if not os.path.isdir(smc_dir):
            return False, tr(
                "step2_smc_dir_missing",
                "未找到 smc_generator：{path}",
            ).format(path=smc_dir)
        create_py = os.path.join(smc_dir, "create_grid.py")
        if not os.path.isfile(create_py):
            return False, tr("step2_smc_incomplete", "smc_generator 缺少 create_grid.py")
        pys_a = os.path.join(smc_dir, "PySMCs", "smcellgen.py")
        pys_b = os.path.join(smc_dir, "SMCGTools", "PySMCs", "smcellgen.py")
        if not (os.path.isfile(pys_a) or os.path.isfile(pys_b)):
            return False, tr("step2_smc_pysmcs_missing", "smc_generator 缺少 PySMCs（smcellgen.py）")
        try:
            r = subprocess.run(
                [sys.executable, "-c", "import netCDF4, pandas"],
                capture_output=True,
                text=True,
                encoding=_SUBPROCESS_IO_ENCODING,
                errors=_SUBPROCESS_IO_ERRORS,
                timeout=60,
            )
        except Exception as e:
            return False, tr("step2_smc_dep_check_failed", "检测 SMC 依赖失败：{err}").format(err=e)
        if r.returncode != 0:
            err_hint = (r.stderr or r.stdout or "").strip()
            if err_hint:
                err_hint = err_hint.splitlines()[-1][:240]
            base = tr(
                "step2_smc_deps_missing",
                "当前 Python 需安装 netCDF4、pandas。请在终端执行：{cmd}",
            ).format(cmd=f"{sys.executable} -m pip install netCDF4 pandas")
            if err_hint:
                return False, f"{base}\n({err_hint})"
            return False, base
        bathy = self._get_smc_bathy_path()
        if not bathy:
            return False, tr(
                "step2_smc_bathy_missing",
                "未找到 SMC 水深 NetCDF。请安装 reference_data（含 etopo2.nc 等），或在 public/config.json 中设置 SMC_BATHYMETRY_FILE。",
            )
        return True, ""

    def _get_step2_wind_nc_bounds(self):
        """读取工作目录 wind*.nc 的经纬范围，返回 (lon_lo, lon_hi, lat_lo, lat_hi) 或 None。"""
        folder = str(getattr(self, "selected_folder", "") or "").strip()
        if not folder:
            return None
        wind_files = glob.glob(os.path.join(folder, "*wind*.nc"))
        if not wind_files:
            p = os.path.join(folder, "wind.nc")
            if os.path.isfile(p):
                wind_files = [p]
        if not wind_files:
            return None

        preferred = os.path.join(folder, "wind.nc")
        nc_path = preferred if preferred in wind_files else sorted(wind_files)[0]
        try:
            with Dataset(nc_path, "r") as ds:
                lon_var = None
                lat_var = None
                for lon_name in ("longitude", "lon", "Longitude", "LON"):
                    if lon_name in ds.variables:
                        lon_var = ds.variables[lon_name]
                        break
                for lat_name in ("latitude", "lat", "Latitude", "LAT"):
                    if lat_name in ds.variables:
                        lat_var = ds.variables[lat_name]
                        break
                if lon_var is None or lat_var is None:
                    return None
                lon = np.asarray(lon_var[:], dtype=float)
                lat = np.asarray(lat_var[:], dtype=float)
                lon = lon[np.isfinite(lon)]
                lat = lat[np.isfinite(lat)]
                if lon.size == 0 or lat.size == 0:
                    return None
                return float(np.min(lon)), float(np.max(lon)), float(np.min(lat)), float(np.max(lat))
        except Exception:
            return None

    def _build_smc_step2_grid_dict(self, lon_west, lon_east, lat_south, lat_north, output_dir):
        """根据界面参数与工作目录构造 smc_generator/create_grid.py 所用 grid.json 体。"""
        smc_dir = self._get_smc_generator_dir()
        tpl_path = os.path.join(smc_dir, "grid.json")
        if os.path.isfile(tpl_path):
            with open(tpl_path, encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {}
        grid_json = copy.deepcopy(data) if data else {}

        def _read_int_default(edit_attr, default):
            ed = getattr(self, edit_attr, None)
            if ed is None:
                return int(default)
            t = ed.text().strip()
            return int(t) if t else int(default)

        def _read_float_default(edit_attr, default):
            ed = getattr(self, edit_attr, None)
            if ed is None:
                return float(default)
            t = ed.text().strip()
            return float(t) if t else float(default)

        try:
            n_levels = _read_int_default("smc_n_levels_edit", 2)
        except Exception:
            raise ValueError("n_levels") from None
        depmin = _read_float_default("smc_depmin_edit", 0.0)
        dshalw = _read_float_default("smc_dshalw_edit", -150.0)

        bathy = self._get_smc_bathy_path()
        if not bathy:
            raise FileNotFoundError("smc bathymetry")

        is_global = self._is_global_range(lon_west, lon_east, lat_south, lat_north)
        lon_lo, lon_hi = min(lon_west, lon_east), max(lon_west, lon_east)
        lat_lo, lat_hi = min(lat_south, lat_north), max(lat_south, lat_north)
        if not is_global:
            wind_bounds = self._get_step2_wind_nc_bounds()
            if wind_bounds is not None:
                w_lon_lo, w_lon_hi, w_lat_lo, w_lat_hi = wind_bounds
                if min(lon_hi, w_lon_hi) <= max(lon_lo, w_lon_lo) or min(lat_hi, w_lat_hi) <= max(lat_lo, w_lat_lo):
                    raise ValueError(
                        tr(
                            "step2_smc_wind_no_overlap",
                            "SMC 区域与风场无有效交集，请先同步 Step1 风场范围与 Step2 区域范围。",
                        )
                    )
                if (
                    lon_lo < w_lon_lo
                    or lon_hi > w_lon_hi
                    or lat_lo < w_lat_lo
                    or lat_hi > w_lat_hi
                ):
                    if hasattr(self, "log_signal"):
                        self.log_signal.emit(
                            tr(
                                "step2_smc_bounds_exceed_wind",
                                "⚠️ SMC 区域超出风场覆盖：SMC lon [{sl:.4f},{sr:.4f}] lat [{sb:.4f},{st:.4f}]，"
                                "wind lon [{wl:.4f},{wr:.4f}] lat [{wb:.4f},{wt:.4f}]。"
                                "最终是否允许将由 create_grid.py 的区域约束策略决定。",
                            ).format(
                                sl=lon_lo,
                                sr=lon_hi,
                                sb=lat_lo,
                                st=lat_hi,
                                wl=w_lon_lo,
                                wr=w_lon_hi,
                                wb=w_lat_lo,
                                wt=w_lat_hi,
                            )
                        )
        out_abs = os.path.abspath(os.path.normpath(output_dir))

        grid_json.setdefault("input", {})
        grid_json["input"]["bathymetry_file"] = os.path.abspath(os.path.normpath(bathy))

        grid_json.setdefault("grid", {})
        grid_json["grid"]["name"] = str(grid_json["grid"].get("name") or "grid")
        grid_json["grid"]["n_levels"] = int(n_levels)
        grid_json["grid"]["global"] = bool(is_global)
        grid_json["grid"].setdefault("arctic", False)
        grid_json["grid"].setdefault("glb_arc_lat", 84.4)
        if "origin" not in grid_json["grid"] or not isinstance(grid_json["grid"]["origin"], dict):
            grid_json["grid"]["origin"] = {"lon0": 0.0, "lat0": -90.0}
        if not is_global:
            grid_json["grid"]["regional_bounds"] = {
                "west_lon": float(lon_lo),
                "south_lat": float(lat_lo),
                "east_lon": float(lon_hi),
                "north_lat": float(lat_hi),
            }
            # 与 smcellgen 中 x0lon/y0lat 对齐；若保留模板 (0,-90)，格块索引换算到经纬度
            # 易与区域角点不一致，导致可视化 set_extent 裁切后「只见岸线不见网」。
            grid_json["grid"]["origin"] = {"lon0": float(lon_lo), "lat0": float(lat_lo)}
        else:
            grid_json["grid"].pop("regional_bounds", None)

        grid_json.setdefault("physics", {})
        grid_json["physics"]["wlevel"] = float(grid_json["physics"].get("wlevel", 0.0))
        grid_json["physics"]["depmin"] = float(depmin)
        grid_json["physics"]["dshalw"] = float(dshalw)

        grid_json.setdefault("boundary", {})
        _b = grid_json["boundary"]
        gen_bdy = bool(_b.get("generate_boundary_cells", True))
        msea = int(_b.get("msea", 1))
        grid_json["boundary"]["generate_boundary_cells"] = bool(gen_bdy and not is_global)
        grid_json["boundary"]["msea"] = int(msea)

        grid_json.setdefault("output", {})
        grid_json["output"]["output_dir"] = out_abs
        grid_json["output"].setdefault("file_prefix", "")

        return grid_json

    def _run_smc_mesh_generation(self, lon_west, lon_east, lat_south, lat_north):
        """调用 smc_generator/create_grid.py；grid.json 中 output_dir 为当前工作目录。"""
        output_dir = os.path.abspath(os.path.normpath(self.selected_folder))
        os.makedirs(output_dir, exist_ok=True)
        smc_dir = self._get_smc_generator_dir()
        create_py = os.path.join(smc_dir, "create_grid.py")

        try:
            grid_dict = self._build_smc_step2_grid_dict(
                lon_west, lon_east, lat_south, lat_north, output_dir
            )
        except ValueError as e:
            self.log_signal.emit(
                tr("step2_smc_config_invalid", "❌ SMC 参数无效（例如 n_levels/msea 需为整数）：{err}").format(err=e)
            )
            return False

        cache_key = self._get_smc_mesh_cache_key(grid_dict)
        cached = self._check_smc_mesh_cache(cache_key)
        if cached:
            try:
                self._load_smc_mesh_from_cache(cached, output_dir)
                self.log_signal.emit(tr("step2_cache_found", "✅ 找到匹配的网格缓存，直接使用缓存的网格"))
                return True
            except Exception as e:
                self.log_signal.emit(
                    tr("step2_unst_cache_copy_failed", "❌ 从缓存复制失败：{err}").format(err=e)
                )
                return False

        tmpdir = tempfile.mkdtemp(prefix="ww3tool_smc_")
        tmpdir = os.path.normpath(os.path.abspath(tmpdir))
        grid_path = os.path.join(tmpdir, "ww3tool_step2_smc_grid.json")

        try:
            with open(grid_path, "w", encoding="utf-8") as f:
                json.dump(grid_dict, f, indent=2, ensure_ascii=False)
                f.write("\n")
        except Exception as e:
            shutil.rmtree(tmpdir, ignore_errors=True)
            self.log_signal.emit(
                tr("step2_smc_config_write_failed", "❌ SMC 配置写入失败：{err}").format(err=e)
            )
            return False

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        argv = [sys.executable, "-u", create_py, "--grid", grid_path]

        ret = 1
        try:
            try:
                ret = self._stream_subprocess_to_log(argv, cwd=smc_dir, env=env)
            except Exception as e:
                self.log_signal.emit(
                    tr("step2_python_error", "❌ 执行 Python 版 gridgen 出错: {error}").format(error=e)
                )
                import traceback

                for line in traceback.format_exc().splitlines():
                    self.log_signal.emit(line)
                ret = 1

            if ret != 0:
                self.log_signal.emit(
                    tr("step2_python_failed", "❌ Python 版 gridgen 执行失败，返回码: {code}").format(code=ret)
                )
                return False

            cell_dat = os.path.join(output_dir, "grid_cell.dat")
            if not (os.path.isfile(cell_dat) and os.path.getsize(cell_dat) > 0):
                self.log_signal.emit(tr("step2_smc_no_cell_file", "❌ 未找到有效的 grid_cell.dat"))
                return False
            try:
                self._save_smc_mesh_to_cache(cache_key, output_dir)
                self.log_signal.emit(
                    tr("step2_cache_saved", "✅ 已保存网格到缓存（{key}...）").format(key=cache_key[:8])
                )
            except Exception as cache_error:
                self.log_signal.emit(
                    tr("step2_cache_save_failed", "⚠️ 保存缓存失败: {error}").format(error=cache_error)
                )
            self.log_signal.emit(
                tr("step2_smc_mesh_complete", "✅ SMC 网格生成完成（文件已写入当前工作目录）")
            )
            return True
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _get_unst_dem_file(self):
        """
        解析非结构网格所需的 DEM（NetCDF，需含 lon/lat/bed_elevation 等，见 unst_msh_gen）。
        优先 public/config.json 的 UNST_DEM_FILE；否则使用 unstructured_generator/grid.json 中 DataFiles.dem_file（相对路径相对 unstructured_generator/）。
        """
        cfg = load_config()
        custom = (cfg.get("UNST_DEM_FILE") or "").strip()
        gridgen_root = self._get_gridgen_path()
        if custom:
            path = custom if os.path.isabs(custom) else os.path.normpath(os.path.join(gridgen_root, custom))
            return path if os.path.isfile(path) else None
        ug_dir = self._get_unstructured_generator_dir()
        dem_rel = ""
        try:
            gj_path = os.path.join(ug_dir, "grid.json")
            if os.path.isfile(gj_path):
                with open(gj_path, encoding="utf-8") as f:
                    raw = json.load(f)
                df = raw.get("DataFiles") or raw.get("data") or {}
                dem_rel = df.get("dem_file") or ""
            if not str(dem_rel).strip():
                from setting.config import load_unst_msh_gen_config

                dem_rel = (load_unst_msh_gen_config().get("data") or {}).get("dem_file") or ""
            dem_rel = str(dem_rel).strip()
            if not dem_rel:
                return None
            if os.path.isabs(dem_rel):
                return dem_rel if os.path.isfile(dem_rel) else None
            abs_dem = self._resolve_path_via_reference_data_setting(ug_dir, dem_rel)
            return abs_dem if abs_dem else None
        except Exception:
            return None

    def _check_unst_mesh_prerequisites(self):
        """非结构网格生成前的环境检查。返回 (ok, err_msg)。"""
        ug_dir = self._get_unstructured_generator_dir()
        if not os.path.isdir(ug_dir):
            return False, tr(
                "step2_unst_dir_missing",
                "unstructured_generator not found: {path} (check WW3-Grid-Generator/unstructured_generator).",
            ).format(path=ug_dir)
        create_py = os.path.join(ug_dir, "create_grid.py")
        if not os.path.isfile(create_py):
            return False, tr(
                "step2_unst_incomplete",
                "unstructured_generator 不完整，缺少：{name}",
            ).format(name="create_grid.py")
        unst_dir = self._get_unstructured_unst_msh_gen_dir()
        if not os.path.isdir(unst_dir):
            return False, tr(
                "step2_unst_incomplete",
                "unstructured_generator 不完整，缺少目录：unst_msh_gen",
            )
        for name in ("ocn_ww3.py", "spacing.py"):
            p = os.path.join(unst_dir, name)
            if not os.path.isfile(p):
                return False, tr(
                    "step2_unst_incomplete",
                    "unst_msh_gen 不完整，缺少：{name}",
                ).format(name=name)
        dem = self._get_unst_dem_file()
        if not dem:
            return False, tr(
                "step2_unst_dem_missing",
                "未找到非结构网格 DEM（NetCDF）。请在 public/config.json 中设置 UNST_DEM_FILE 为绝对路径，"
                "或编辑 unstructured_generator/grid.json 中 DataFiles.dem_file，并将 DEM 放到相对路径所指位置。",
            )
        # 与 WW3-Grid-Generator/structured_generator/pygridgen 相同：子进程用 sys.executable，须在该环境中装好 scikit-image
        try:
            r = subprocess.run(
                [sys.executable, "-c", "import skimage.filters, skimage.measure"],
                capture_output=True,
                text=True,
                encoding=_SUBPROCESS_IO_ENCODING,
                errors=_SUBPROCESS_IO_ERRORS,
                timeout=60,
            )
        except Exception as e:
            return False, tr(
                "step2_unst_skimage_check_failed",
                "检测 scikit-image 失败：{err}",
            ).format(err=e)
        if r.returncode != 0:
            return False, tr(
                "step2_unst_skimage_missing",
                "当前用于生成网格的 Python 未安装 scikit-image（unst_msh_gen/spacing.py 需要）。\n"
                "请在终端执行（与启动本程序的解释器一致）：\n{cmd}",
            ).format(cmd=f"{sys.executable} -m pip install scikit-image")
        # JIGSAW：使用 unstructured_generator/jigsaw-python
        jig_root = self._get_unstructured_jigsaw_root()
        if not self._is_jigsaw_library_built(jig_root):
            if not shutil.which("cmake"):
                return False, tr(
                    "step2_jigsaw_cmake_required",
                    "未检测到 JIGSAW 动态库（{lib}），且系统 PATH 中无 cmake，无法在生成时自动编译。\n"
                    "请安装 CMake（Windows/Linux）或 Xcode Command Line Tools（macOS：xcode-select --install），\n"
                    "或先在目录 jigsaw-python 下手动执行：python3 build.py",
                ).format(lib=self._unst_jigsaw_shared_lib_basename())
        return True, ""

    def _build_unst_msh_gen_config_dict(self, lon_west, lon_east, lat_south, lat_north, is_global):
        """基于 unstructured_generator/grid.json（经 load_unst_msh_gen_config）与界面 spacing/范围生成运行用 JSON 对象。"""
        from setting.config import load_unst_msh_gen_config

        raw = copy.deepcopy(load_unst_msh_gen_config())

        def _f(edit, default):
            try:
                t = edit.text().strip()
                return float(t) if t else float(default)
            except Exception:
                return float(default)

        def _f_attr(attr, default):
            ed = getattr(self, attr, None)
            return _f(ed, default) if ed is not None else float(default)

        hmax = _f_attr("unst_hmax_edit", raw.get("spacing", {}).get("hmax", 100.0))
        hshr = _f_attr("unst_hshr_edit", raw.get("spacing", {}).get("hshr", 20.0))
        dhdx = _f_attr("unst_dhdx_edit", raw.get("spacing", {}).get("dhdx", 0.05))
        deep_threshold_m = _f_attr(
            "unst_deep_threshold_edit",
            raw.get("spacing", {}).get("deep_ocean_threshold_m", 4000.0),
        )
        hmin = hshr

        spacing = dict(raw.get("spacing") or {})
        spacing["hmax"] = hmax
        spacing["hmin"] = hmin
        spacing["hshr"] = hshr
        spacing["dhdx"] = dhdx
        spacing["deep_ocean_threshold_m"] = abs(float(deep_threshold_m))
        raw["spacing"] = spacing

        mesh_s = dict(raw.get("mesh_settings") or {})
        mesh_s["hfun_hmax"] = float(hmax)
        raw["mesh_settings"] = mesh_s

        data = dict(raw.get("data") or {})
        dem = self._get_unst_dem_file()
        if not dem:
            raise FileNotFoundError("unst DEM")
        data["dem_file"] = dem
        raw["data"] = data

        lon_lo, lon_hi = min(lon_west, lon_east), max(lon_west, lon_east)
        lat_lo, lat_hi = min(lat_south, lat_north), max(lat_south, lat_north)
        if is_global:
            raw.pop("regional", None)
        else:
            reg = dict(raw.get("regional") or {})
            reg["lon_min"] = float(lon_lo)
            reg["lon_max"] = float(lon_hi)
            reg["lat_min"] = float(lat_lo)
            reg["lat_max"] = float(lat_hi)
            reg["margin_deg"] = float(reg.get("margin_deg", 1.0))
            reg["edge_segments"] = int(reg.get("edge_segments", 64))
            mid_lon = 0.5 * (lon_lo + lon_hi)
            mid_lat = 0.5 * (lat_lo + lat_hi)
            reg["stereo_lon"] = float(mid_lon)
            reg["stereo_lat"] = float(mid_lat)
            raw["regional"] = reg
        return raw

    def _build_unstructured_step2_grid_dict(
        self, cfg_obj, is_global, tmp_dir, unst_abs, jig_abs, ww3_publish_dir=None
    ):
        """
        生成 unstructured_generator/create_grid.py 使用的 grid.json 体（与仓库内 grid.json  schema 一致）。
        ww3_publish_dir：grid.ww3 输出目录；Step2 传当前工作目录（selected_folder），避免沿用模板里的 "output"。
        """
        tpl_path = os.path.join(self._get_unstructured_generator_dir(), "grid.json")
        if os.path.isfile(tpl_path):
            with open(tpl_path, encoding="utf-8") as f:
                grid = json.load(f)
        else:
            grid = {}
        grid = copy.deepcopy(grid) if grid else {}

        mesh_ws = os.path.join(tmp_dir, "mesh_workspace")
        os.makedirs(mesh_ws, exist_ok=True)

        sp = cfg_obj.get("spacing") or {}
        ms = cfg_obj.get("mesh_settings") or {}
        cmd = cfg_obj.get("command_line_args") or {}
        data = cfg_obj.get("data") or {}

        grid.setdefault("Workflow", {})
        grid["Workflow"]["run_window_mask"] = False
        grid["Workflow"]["unst_msh_gen_dir"] = unst_abs
        grid["Workflow"]["jigsaw_python_root"] = jig_abs
        grid["Workflow"].setdefault("resolved_config_name", ".grid_run.ini")

        grid.setdefault("Output", {})
        grid["Output"]["mesh_workspace_dir"] = mesh_ws
        publish_base = ww3_publish_dir if ww3_publish_dir else tmp_dir
        grid["Output"]["ww3_publish_dir"] = os.path.normpath(os.path.abspath(publish_base))
        grid["Output"]["ww3_publish_basename"] = "grid.ww3"

        grid.setdefault("Spacing", {})
        grid["Spacing"].update(
            {
                "hmax": float(sp.get("hmax", 100.0)),
                "hshr": float(sp.get("hshr", 20.0)),
                "hmin": float(sp.get("hmin", sp.get("hshr", 20.0))),
                "nwav": int(sp.get("nwav", 400)),
                "dhdx": float(sp.get("dhdx", 0.05)),
                "deep_ocean_threshold_m": float(sp.get("deep_ocean_threshold_m", 4000.0)),
            }
        )

        grid.setdefault("MeshSettings", {})
        grid["MeshSettings"]["hfun_hmax"] = float(ms.get("hfun_hmax", sp.get("hmax", 100.0)))
        grid["MeshSettings"]["mesh_file"] = "grid.msh"
        grid["MeshSettings"]["ww3_mesh_file"] = "grid.ww3"

        grid.setdefault("CommandLineArgs", {})
        grid["CommandLineArgs"]["black_sea"] = int(cmd.get("black_sea", 3))
        grid["CommandLineArgs"]["mask_file"] = ""

        grid.setdefault("DataFiles", {})
        grid["DataFiles"]["dem_file"] = data.get("dem_file") or ""

        lon_lo, lon_hi, lat_lo, lat_hi = -180.0, 180.0, -90.0, 90.0
        if not is_global:
            reg = cfg_obj.get("regional") or {}
            lon_lo = float(reg.get("lon_min", -180))
            lon_hi = float(reg.get("lon_max", 180))
            lat_lo = float(reg.get("lat_min", -90))
            lat_hi = float(reg.get("lat_max", 90))
            grid["Regional"] = {
                "lon_min": lon_lo,
                "lon_max": lon_hi,
                "lat_min": lat_lo,
                "lat_max": lat_hi,
                "margin_deg": float(reg.get("margin_deg", 1.0)),
                "edge_segments": int(reg.get("edge_segments", 64)),
                "stereo_lon": float(reg.get("stereo_lon", 0.5 * (lon_lo + lon_hi))),
                "stereo_lat": float(reg.get("stereo_lat", 0.5 * (lat_lo + lat_hi))),
            }
        else:
            grid.pop("Regional", None)

        grid.setdefault("Domain", {})
        grid["Domain"]["clip_to_bounds"] = False
        grid["Domain"]["west_lon"] = lon_lo
        grid["Domain"]["east_lon"] = lon_hi
        grid["Domain"]["south_lat"] = lat_lo
        grid["Domain"]["north_lat"] = lat_hi

        grid.setdefault("Zoom", {})
        grid["Zoom"]["zoom_auto_center"] = True
        grid["Zoom"]["zoom_lon_deg"] = float(0.5 * (lon_lo + lon_hi))
        grid["Zoom"]["zoom_lat_deg"] = float(0.5 * (lat_lo + lat_hi))

        return grid

    def _stream_subprocess_to_log(self, argv, cwd, env):
        """运行子进程并将 stdout/stderr 打到 log_signal，返回 returncode。"""
        from queue import Queue, Empty

        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding=_SUBPROCESS_IO_ENCODING,
            errors=_SUBPROCESS_IO_ERRORS,
            bufsize=1,
            env=env,
        )
        output_queue = Queue()
        read_finished = threading.Event()

        def read_output_thread():
            # NOTE:
            # readline() may hold data until '\n' or EOF when upstream output is
            # partially buffered. Reading char-by-char avoids "all logs show up
            # at the end" behavior for long-running generators.
            # 仅去掉 \r/\n，不要用 strip()：否则会吃掉用于横幅等格式的行尾空格。
            def _put_line(raw: str) -> None:
                s = raw.rstrip("\r\n")
                if s.strip():
                    output_queue.put(s)

            if proc.stdout is None:
                read_finished.set()
                return
            try:
                buf = ""
                while True:
                    ch = proc.stdout.read(1)
                    if ch == "":
                        break
                    if ch == "\r":
                        if buf.strip():
                            _put_line(buf)
                        buf = ""
                        continue
                    if ch == "\n":
                        if buf.strip():
                            _put_line(buf)
                        buf = ""
                        continue
                    buf += ch
                if buf.strip():
                    _put_line(buf)
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
        return proc.returncode

    def _run_unstructured_mesh_generation(self, lon_west, lon_east, lat_south, lat_north):
        """通过 WW3-Grid-Generator/unstructured_generator/create_grid.py 生成非结构网格，将 grid.ww3 复制到工作目录。"""
        output_dir = os.path.abspath(os.path.normpath(self.selected_folder))
        os.makedirs(output_dir, exist_ok=True)
        ug_dir = self._get_unstructured_generator_dir()
        jig_root = self._get_unstructured_jigsaw_root()
        unst_abs = os.path.normpath(os.path.abspath(self._get_unstructured_unst_msh_gen_dir()))
        if not self._ensure_jigsaw_built(jig_root):
            return False
        is_global = self._is_global_range(lon_west, lon_east, lat_south, lat_north)

        try:
            cfg_obj = self._build_unst_msh_gen_config_dict(
                lon_west, lon_east, lat_south, lat_north, is_global
            )
        except Exception as e:
            self.log_signal.emit(
                tr("step2_unst_config_build_failed", "❌ 非结构网格配置生成失败：{err}").format(err=e)
            )
            return False

        cfg_name = "unst_msh_gen_config.json"
        cache_key = self._get_unst_mesh_cache_key(cfg_obj, is_global)
        unst_cache_dir = self._check_unst_mesh_cache(cache_key)

        sp = cfg_obj.get("spacing") or {}
        self.log_signal.emit(
            tr(
                "step2_unst_params",
                "   参数: hmax={hmax}, hmin={hmin}, hshr={hshr}, dhdx={dhdx}, deep={deep}m",
            ).format(
                hmax=sp.get("hmax", ""),
                hmin=sp.get("hmin", ""),
                hshr=sp.get("hshr", ""),
                dhdx=sp.get("dhdx", ""),
                deep=sp.get("deep_ocean_threshold_m", ""),
            )
        )
        self.log_signal.emit(
            tr("step2_lon_range", "   经度范围: [{min}, {max}]").format(min=lon_west, max=lon_east)
        )
        self.log_signal.emit(
            tr("step2_lat_range", "   纬度范围: [{min}, {max}]").format(min=lat_south, max=lat_north)
        )

        if unst_cache_dir:
            self.log_signal.emit(
                tr(
                    "step2_unst_cache_found",
                    "✅ 找到匹配的非结构网格缓存，已复制 grid.ww3 与配置到工作目录。",
                )
            )
            try:
                self._load_unst_mesh_from_cache(unst_cache_dir, output_dir)
                cfg_out = os.path.join(output_dir, cfg_name)
                with open(cfg_out, "w", encoding="utf-8") as f:
                    json.dump(cfg_obj, f, indent=2, ensure_ascii=False)
                    f.write("\n")
            except Exception as e:
                self.log_signal.emit(
                    tr("step2_unst_cache_copy_failed", "❌ 从缓存复制失败：{err}").format(err=e)
                )
                return False
            return True

        self.log_signal.emit(tr("step2_cache_not_found", "🔄 未找到匹配的缓存，开始生成新网格..."))

        tmpdir = tempfile.mkdtemp(prefix="ww3tool_unst_")
        tmpdir = os.path.normpath(os.path.abspath(tmpdir))
        cfg_path = os.path.join(tmpdir, cfg_name)
        grid_path = os.path.join(tmpdir, "ww3tool_step2_grid.json")
        create_grid_py = os.path.join(ug_dir, "create_grid.py")
        try:
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg_obj, f, indent=2)
                f.write("\n")
            grid_dict = self._build_unstructured_step2_grid_dict(
                cfg_obj,
                is_global,
                tmpdir,
                unst_abs,
                os.path.normpath(os.path.abspath(jig_root)),
                ww3_publish_dir=output_dir,
            )
            with open(grid_path, "w", encoding="utf-8") as f:
                json.dump(grid_dict, f, indent=2, ensure_ascii=False)
                f.write("\n")
        except Exception as e:
            shutil.rmtree(tmpdir, ignore_errors=True)
            self.log_signal.emit(
                tr("step2_unst_config_write_failed", "❌ 无法写入配置文件：{path} — {err}").format(
                    path=grid_path, err=e
                )
            )
            return False

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        argv = [sys.executable, "-u", create_grid_py, "--grid", grid_path]

        ret = 1
        try:
            try:
                ret = self._stream_subprocess_to_log(argv, cwd=ug_dir, env=env)
            except Exception as e:
                self.log_signal.emit(tr("step2_python_error", "❌ 执行 Python 版 gridgen 出错: {error}").format(error=e))
                import traceback

                for line in traceback.format_exc().splitlines():
                    self.log_signal.emit(line)
                ret = 1

            if ret != 0:
                self.log_signal.emit(
                    tr("step2_python_failed", "❌ Python 版 gridgen 执行失败，返回码: {code}").format(code=ret)
                )
                return False

            # create_grid 已将 ww3_publish_dir 设为 output_dir 时，grid.ww3 直接写在工作目录
            src_ww3 = os.path.join(output_dir, "grid.ww3")
            dst_ww3 = os.path.join(output_dir, "grid.ww3")
            if not (os.path.isfile(src_ww3) and os.path.getsize(src_ww3) > 0):
                src_ww3 = os.path.join(tmpdir, "grid.ww3")
            if os.path.isfile(src_ww3) and os.path.getsize(src_ww3) > 0:
                if os.path.normpath(os.path.abspath(src_ww3)) != os.path.normpath(
                    os.path.abspath(dst_ww3)
                ):
                    shutil.copy2(src_ww3, dst_ww3)
                try:
                    shutil.copy2(cfg_path, os.path.join(output_dir, cfg_name))
                except Exception:
                    pass
                try:
                    self._save_unst_mesh_to_cache(cache_key, src_ww3, cfg_obj)
                    self.log_signal.emit(
                        tr(
                            "step2_unst_cache_saved",
                            "✅ 已保存非结构网格到缓存（键 {key}…）",
                        ).format(key=cache_key[:12])
                    )
                except Exception as cache_error:
                    self.log_signal.emit(
                        tr("step2_cache_save_failed", "⚠️ 保存缓存失败: {error}").format(error=cache_error)
                    )
                self.log_signal.emit(
                    tr("step2_unst_mesh_complete", "✅ 非结构化三角网格生成完成！")
                )
                return True

            msh_path = os.path.join(tmpdir, "grid.msh")
            if os.path.isfile(msh_path) and os.path.getsize(msh_path) > 0:
                self.log_signal.emit(tr("step2_grid_create_failed", "错误：网格创建失败"))
                return False

            self.log_signal.emit(tr("step2_grid_create_failed", "错误：网格创建失败"))
            return False
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _check_reference_data(self):
        """检测 reference_data 目录及必需文件是否存在。返回 (是否通过, 缺失文件列表, 参考数据目录路径)。"""
        ref_dir = self._get_reference_data_path()
        if not ref_dir or not os.path.isdir(ref_dir):
            return False, list(REFERENCE_DATA_REQUIRED_FILES), ref_dir or ""
        _flatten_nested_reference_data_dir(ref_dir)
        missing = [
            f for f in REFERENCE_DATA_REQUIRED_FILES
            if not os.path.isfile(os.path.join(ref_dir, f))
        ]
        return len(missing) == 0, missing, ref_dir

    def _run_get_reference_data(self):
        """在 WW3-Grid-Generator 下执行 ``get_reference_data.py``，日志为脚本原始英文输出（含百分比）。"""
        gridgen = self._get_gridgen_path()
        ref_dir = self._get_reference_data_path()
        log_signal = getattr(self, "log_signal", None)

        if not gridgen:
            QtCore.QTimer.singleShot(
                0,
                lambda: self._show_ref_data_result(
                    False,
                    "Cannot find WW3-Grid-Generator path.",
                ),
            )
            return

        script_path = os.path.join(gridgen, "get_reference_data.py")
        if not os.path.isfile(script_path):
            QtCore.QTimer.singleShot(
                0,
                lambda: self._show_ref_data_result(
                    False,
                    f"get_reference_data.py not found: {script_path}",
                ),
            )
            return

        default_ref = os.path.normpath(os.path.join(gridgen, "reference_data"))
        argv = [sys.executable, "-u", script_path]
        if ref_dir and os.path.normpath(os.path.abspath(ref_dir)) != default_ref:
            argv.extend(["--ref-dir", os.path.abspath(ref_dir)])

        def _run():
            ok = False
            msg = ""
            try:
                env = os.environ.copy()
                proc = subprocess.Popen(
                    argv,
                    cwd=gridgen,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding=_SUBPROCESS_IO_ENCODING,
                    errors=_SUBPROCESS_IO_ERRORS,
                    bufsize=1,
                    env=env,
                    close_fds=True,
                )
                if proc.stdout is not None:
                    for line in iter(proc.stdout.readline, ""):
                        if not line:
                            break
                        s = line.rstrip("\r\n")
                        if log_signal:
                            log_signal.emit(s)
                proc.wait()
                code = proc.returncode if proc.returncode is not None else -1
                ok = code == 0
                msg = "" if ok else f"exit code {code}"
            except Exception as e:
                ok = False
                msg = str(e)
            QtCore.QTimer.singleShot(0, lambda o=ok, m=msg: self._show_ref_data_result(o, m))

        threading.Thread(target=_run, daemon=True).start()
        try:
            InfoBar.info(
                title="Info",
                content="Running get_reference_data.py — see log for progress.",
                duration=3500,
                parent=self,
            )
        except Exception:
            pass

    def _show_ref_data_result(self, success, message):
        """在主线程提示结果；详细过程已由 get_reference_data.py 打印到日志。"""
        if hasattr(self, "log_signal") and self.log_signal and not success and message:
            self.log_signal.emit(f"❌ reference_data: {message}")
        try:
            if success:
                InfoBar.success(
                    title="Info",
                    content="reference_data is ready. You can click Generate Grid again.",
                    duration=4000,
                    parent=self,
                )
            else:
                InfoBar.warning(
                    title="Info",
                    content=message[:200] + ("…" if len(message) > 200 else ""),
                    duration=5000,
                    parent=self,
                )
        except Exception:
            pass

    def _get_grid_cache_dir(self):
        """获取网格缓存目录（WW3-Grid-Generator/cache）"""
        gridgen_path = self._get_gridgen_path()
        gridgen_cache_dir = os.path.join(gridgen_path, "cache")
        os.makedirs(gridgen_cache_dir, exist_ok=True)
        return gridgen_cache_dir

    def _get_grid_cache_key(self, dx_value, dy_value, lon_west, lon_east, lat_south, lat_north, ref_dir, bathymetry=None, coastline_precision=None, gridgen_backend=None):
        """生成网格参数的缓存键（哈希值）。Python 与 MATLAB gridgen 使用不同后端键，缓存互不共用。"""
        import hashlib
        # 如果参数未提供，从配置中读取
        if bathymetry is None or coastline_precision is None:
            config = load_config()
            if bathymetry is None:
                bathymetry = config.get("BATHYMETRY", "GEBCO")
            if coastline_precision is None:
                coastline_precision = config.get("COASTLINE_PRECISION", tr("step2_coastline_precision_full", "最高"))
        if gridgen_backend is None:
            config = load_config()
            gv = config.get("GRIDGEN_VERSION", "MATLAB")
            gridgen_backend = "python" if gv == "Python" else "matlab"
        else:
            gridgen_backend = str(gridgen_backend).strip().lower()
            if gridgen_backend not in ("python", "matlab"):
                gridgen_backend = "matlab"
        # 将所有参数转换为可序列化的格式
        params = {
            'dx': float(dx_value),
            'dy': float(dy_value),
            'lon_range': [float(lon_west), float(lon_east)],
            'lat_range': [float(lat_south), float(lat_north)],
            'ref_dir': os.path.normpath(os.path.abspath(ref_dir)).replace("\\", "/"),
            'bathymetry': str(bathymetry),
            'coastline_precision': str(coastline_precision),
            'gridgen_backend': gridgen_backend,
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
            req = ["grid.bot", "grid.obst"]
            if not all(os.path.exists(os.path.join(cache_path, f)) for f in req):
                return None
            if structured_grid_desc_path(cache_path) is None:
                return None
            if _structured_grid_mask_path(cache_path):
                return cache_path
        return None

    def _save_grid_to_cache(self, cache_key, source_dir, dx_value=None, dy_value=None,
                           lon_west=None, lon_east=None, lat_south=None, lat_north=None, ref_dir=None, bathymetry=None, coastline_precision=None,
                           gridgen_backend=None):
        """将生成的网格保存到缓存"""
        cache_dir = self._get_grid_cache_dir()
        cache_path = os.path.join(cache_dir, cache_key)

        # 如果缓存目录已存在，先删除
        if os.path.exists(cache_path):
            shutil.rmtree(cache_path)

        # 创建缓存目录
        os.makedirs(cache_path, exist_ok=True)

        # 复制网格文件到缓存（掩膜统一存为 grid.mask_nobound）
        for f in ["grid.bot", "grid.obst"]:
            src = os.path.join(source_dir, f)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(cache_path, f))
        for bn in structured_grid_desc_basenames_to_copy(source_dir):
            src = os.path.join(source_dir, bn)
            shutil.copy2(src, os.path.join(cache_path, bn))
        mask_src = os.path.join(source_dir, "grid.mask_nobound")
        if not os.path.exists(mask_src):
            mask_src = os.path.join(source_dir, "grid.mask")
        if os.path.exists(mask_src):
            shutil.copy2(mask_src, os.path.join(cache_path, "grid.mask_nobound"))

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
                'coastline_precision': coastline_precision,
                'gridgen_backend': gridgen_backend,
            }
        }
        params_file = os.path.join(cache_path, 'params.json')
        with open(params_file, 'w', encoding='utf-8') as pf:
            json.dump(params_data, pf, indent=2, ensure_ascii=False)

    def _load_grid_from_cache(self, cache_path, output_dir):
        """从缓存加载网格文件到输出目录"""
        for f in ["grid.bot", "grid.obst"]:
            src = os.path.join(cache_path, f)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(output_dir, f))
        for bn in structured_grid_desc_basenames_to_copy(cache_path):
            src = os.path.join(cache_path, bn)
            shutil.copy2(src, os.path.join(output_dir, bn))
        m_src = os.path.join(cache_path, "grid.mask_nobound")
        if not os.path.exists(m_src):
            m_src = os.path.join(cache_path, "grid.mask")
        if os.path.exists(m_src):
            shutil.copy2(m_src, os.path.join(output_dir, "grid.mask_nobound"))

    def _get_unst_mesh_cache_key(self, cfg_obj: dict, is_global: bool) -> str:
        """非结构网格缓存键：完整配置 + DEM 文件签名（mtime/size），避免 DEM 更新仍误命中。"""
        import hashlib

        dem_path = (cfg_obj.get("data") or {}).get("dem_file") or ""
        dem_path = os.path.normpath(os.path.abspath(str(dem_path)))
        dem_sig = [0, 0]
        if os.path.isfile(dem_path):
            st = os.stat(dem_path)
            dem_sig = [int(st.st_mtime_ns), int(st.st_size)]
        bundle = {
            "cfg": cfg_obj,
            "dem_path": dem_path.replace("\\", "/"),
            "dem_sig": dem_sig,
            "is_global": bool(is_global),
        }
        try:
            params_str = json.dumps(bundle, sort_keys=True, separators=(",", ":"))
        except TypeError:
            params_str = json.dumps(bundle, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(params_str.encode("utf-8")).hexdigest()

    def _check_unst_mesh_cache(self, cache_key: str):
        """若存在有效 grid.ww3 则返回缓存目录路径，否则 None。"""
        if not cache_key:
            return None
        base = os.path.join(self._get_grid_cache_dir(), "unst", cache_key)
        ww3 = os.path.join(base, "grid.ww3")
        if os.path.isfile(ww3) and os.path.getsize(ww3) > 0:
            return base
        return None

    def _save_unst_mesh_to_cache(self, cache_key: str, src_grid_ww3: str, cfg_obj: dict) -> None:
        base = os.path.join(self._get_grid_cache_dir(), "unst", cache_key)
        if os.path.isdir(base):
            shutil.rmtree(base)
        os.makedirs(base, exist_ok=True)
        shutil.copy2(src_grid_ww3, os.path.join(base, "grid.ww3"))
        meta = {"cache_key": cache_key, "cfg": cfg_obj}
        with open(os.path.join(base, "params.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

    def _load_unst_mesh_from_cache(self, cache_path: str, output_dir: str) -> None:
        shutil.copy2(os.path.join(cache_path, "grid.ww3"), os.path.join(output_dir, "grid.ww3"))

    def _get_smc_mesh_cache_key(self, grid_dict: dict) -> str:
        """SMC 缓存键：完整 grid 配置（不含 output_dir）+ 水深文件 mtime/size。"""
        import hashlib
        import copy

        b = copy.deepcopy(grid_dict)
        out = dict(b.get("output") or {})
        out.pop("output_dir", None)
        b["output"] = out
        inp = dict(b.get("input") or {})
        bp = str(inp.get("bathymetry_file") or "").strip()
        bp_abs = os.path.normpath(os.path.abspath(bp)) if bp else ""
        sig: list[int] = [0, 0]
        if bp_abs and os.path.isfile(bp_abs):
            st = os.stat(bp_abs)
            sig = [int(st.st_mtime_ns), int(st.st_size)]
        inp["bathymetry_file"] = bp_abs.replace("\\", "/")
        b["input"] = inp
        bundle = {"grid_body": b, "bathy_sig": sig}
        try:
            params_str = json.dumps(bundle, sort_keys=True, separators=(",", ":"), default=str)
        except TypeError:
            params_str = json.dumps(bundle, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(params_str.encode("utf-8")).hexdigest()

    def _check_smc_mesh_cache(self, cache_key: str) -> str | None:
        """若存在有效 SMC 产物则返回缓存目录，否则 None。"""
        if not cache_key:
            return None
        base = os.path.join(self._get_grid_cache_dir(), "smc", cache_key)
        cell = os.path.join(base, "grid_cell.dat")
        meta = os.path.join(base, "grid.json")
        iside = os.path.join(base, "grid_iside.dat")
        jside = os.path.join(base, "grid_jside.dat")
        subtr = os.path.join(base, "grid_subtr.dat")
        if (
            os.path.isfile(cell)
            and os.path.getsize(cell) > 0
            and os.path.isfile(meta)
            and os.path.getsize(meta) > 0
            and os.path.isfile(iside)
            and os.path.getsize(iside) > 0
            and os.path.isfile(jside)
            and os.path.getsize(jside) > 0
            and os.path.isfile(subtr)
            and os.path.getsize(subtr) > 0
        ):
            return base
        return None

    def _save_smc_mesh_to_cache(self, cache_key: str, output_dir: str) -> None:
        base = os.path.join(self._get_grid_cache_dir(), "smc", cache_key)
        if os.path.isdir(base):
            shutil.rmtree(base)
        os.makedirs(base, exist_ok=True)
        smc_files = (
            "grid_cell.dat",
            "grid.json",
            "grid_subtr.dat",
            "grid_iside.dat",
            "grid_jside.dat",
            "grid_boundary.dat",
            "grid_arctic_cells.dat",
            "grid_aisid.dat",
            "grid_ajsid.dat",
        )
        for name in smc_files:
            src = os.path.join(output_dir, name)
            if os.path.isfile(src) and os.path.getsize(src) > 0:
                shutil.copy2(src, os.path.join(base, name))
        params_data = {"cache_key": cache_key, "kind": "smc"}
        with open(os.path.join(base, "params.json"), "w", encoding="utf-8") as pf:
            json.dump(params_data, pf, indent=2, ensure_ascii=False)

    def _load_smc_mesh_from_cache(self, cache_path: str, output_dir: str) -> None:
        smc_files = (
            "grid_cell.dat",
            "grid.json",
            "grid_subtr.dat",
            "grid_iside.dat",
            "grid_jside.dat",
            "grid_boundary.dat",
            "grid_arctic_cells.dat",
            "grid_aisid.dat",
            "grid_ajsid.dat",
        )
        # Avoid stale mixed-version artifacts (old side/subtr + new cells).
        for name in smc_files:
            dst = os.path.join(output_dir, name)
            try:
                if os.path.isfile(dst):
                    os.remove(dst)
            except OSError:
                pass
        for name in smc_files:
            src = os.path.join(cache_path, name)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(output_dir, name))

    def _validate_grid_files(self, output_dir, max_retries=3, retry_delay=1.0):
        """验证生成的网格文件是否完整，如果文件不完整则等待并重试"""
        import time
        
        grid_bot_path = os.path.join(output_dir, "grid.bot")
        grid_desc_path = None
        for _ in range(5):
            grid_desc_path = structured_grid_desc_path(output_dir)
            if os.path.exists(grid_bot_path) and grid_desc_path:
                break
            time.sleep(1.0)
        grid_desc_path = grid_desc_path or structured_grid_desc_path(output_dir)

        if not os.path.exists(grid_bot_path):
            return False, tr("step2_grid_bot_not_exists", "grid.bot 文件不存在")

        if not grid_desc_path:
            return False, tr("step2_grid_meta_not_exists", "未找到 WW3 网格描述文件（grid.nml / ww3_grid.nml.* / grid.meta），无法验证")

        Nx, Ny = None, None
        try:
            d = parse_rect_grid_description(grid_desc_path)
            if d:
                Nx, Ny = d["nx"], d["ny"]
        except Exception as e:
            return False, tr("step2_read_grid_meta_failed", "读取网格描述文件失败: {error}").format(error=e)

        if Nx is None or Ny is None:
            return False, tr("step2_cannot_read_nx_ny", "无法从网格描述文件读取 Nx, Ny")
        
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
        """更新 MATLAB gridgen 的 grid.nml（写入 gridgen/grid.nml，供顶层 create_grid.m 使用）。"""
        if not matlab_bin_dir:
            return
        grid_nml_path = os.path.join(matlab_bin_dir, "grid.nml")
        bin_grid_nml = os.path.join(matlab_bin_dir, "bin", "grid.nml")
        if not os.path.exists(grid_nml_path):
            if not os.path.exists(bin_grid_nml):
                return
            shutil.copy2(bin_grid_nml, grid_nml_path)

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
        if self._is_step2_unstructured_mesh():
            # 与其他网格类型一致：先处理 reference_data（目录/缺文件），再进入 DEM/JIGSAW 等 InfoBar。
            # 若用户已配置可解析的 DEM（含 UNST_DEM_FILE），即使未装齐 REFERENCE_DATA_REQUIRED_FILES 也允许继续。
            ref_ok, _missing_list, _ref_dir = self._check_reference_data()
            dem_resolved = self._get_unst_dem_file()
            if not ref_ok and not dem_resolved:
                dlg = _ReferenceDataMissingDialog(self, on_download_clicked=self._run_get_reference_data)
                dlg.exec()
                return
            unst_ok, unst_err = self._check_unst_mesh_prerequisites()
            if not unst_ok:
                try:
                    InfoBar.warning(
                        title=tr("tip", "提示"),
                        content=unst_err,
                        duration=6000,
                        parent=self,
                    )
                except Exception:
                    pass
                return
        elif self._is_step2_smc_mesh():
            ok, _missing_list, _ref_dir = self._check_reference_data()
            if not ok:
                dlg = _ReferenceDataMissingDialog(self, on_download_clicked=self._run_get_reference_data)
                dlg.exec()
                return
            smc_ok, smc_err = self._check_smc_prerequisites()
            if not smc_ok:
                try:
                    InfoBar.warning(
                        title=tr("tip", "提示"),
                        content=smc_err,
                        duration=8000,
                        parent=self,
                    )
                except Exception:
                    pass
                return
        else:
            ok, _missing_list, _ref_dir = self._check_reference_data()
            if not ok:
                dlg = _ReferenceDataMissingDialog(self, on_download_clicked=self._run_get_reference_data)
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
        if hasattr(self, "_refresh_step2_mesh_type_combo_enabled"):
            self._refresh_step2_mesh_type_combo_enabled()

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

        # 非结构网格：WW3-Grid-Generator/unstructured_generator/create_grid.py（内调 unst_msh_gen / jigsaw-python）
        if self._is_step2_unstructured_mesh():
            try:
                lon_w = float(self.lon_west_edit.text().strip())
                lon_e = float(self.lon_east_edit.text().strip())
                lat_s = float(self.lat_south_edit.text().strip())
                lat_n = float(self.lat_north_edit.text().strip())
            except (ValueError, AttributeError):
                self.log_signal.emit(
                    tr("step2_unst_latlon_invalid", "❌ 经纬度格式无效，请输入有效数字。")
                )
                return
            self._run_unstructured_mesh_generation(lon_w, lon_e, lat_s, lat_n)
            return

        # SMC 网格：smc_generator/create_grid.py，产物写入当前工作目录
        if self._is_step2_smc_mesh():
            if is_nested:
                self.log_signal.emit(
                    tr(
                        "step2_smc_nested_not_supported",
                        "❌ SMC 网格不支持嵌套模式，请将「类型」设为普通网格。",
                    )
                )
                return
            try:
                lon_w = float(self.lon_west_edit.text().strip())
                lon_e = float(self.lon_east_edit.text().strip())
                lat_s = float(self.lat_south_edit.text().strip())
                lat_n = float(self.lat_north_edit.text().strip())
            except (ValueError, AttributeError):
                self.log_signal.emit(
                    tr("step2_unst_latlon_invalid", "❌ 经纬度格式无效，请输入有效数字。")
                )
                return
            self._run_smc_mesh_generation(lon_w, lon_e, lat_s, lat_n)
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
                python_version_path = os.path.join(
                    gridgen_path, "structured_generator", "pygridgen"
                )
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
            
            gridgen_backend = "python" if gridgen_version == "Python" else "matlab"
            # 检查缓存（使用原始配置值；按 gridgen 后端区分缓存）
            cache_key = self._get_grid_cache_key(
                dx_value, dy_value, lon_west, lon_east, lat_south, lat_north, ref_dir,
                bathymetry_config, coastline_precision_config, gridgen_backend
            )
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
                        encoding=_SUBPROCESS_IO_ENCODING,
                        errors=_SUBPROCESS_IO_ERRORS,
                        bufsize=1,
                        env=env
                    )
                    
                    from queue import Queue, Empty
                    output_queue = Queue()
                    read_finished = threading.Event()
                    
                    def read_output_thread():
                        try:
                            for line in iter(proc.stdout.readline, ''):
                                line_clean = line.rstrip("\r\n")
                                if line_clean.strip():
                                    output_queue.put(line_clean)
                            remaining = proc.stdout.read()
                            if remaining:
                                for l in remaining.splitlines():
                                    if l.strip():
                                        output_queue.put(l)
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
                            self._save_grid_to_cache(
                                cache_key, output_dir_norm, dx_value, dy_value,
                                lon_west, lon_east, lat_south, lat_north, ref_dir, bathymetry_config, coastline_precision_config,
                                gridgen_backend,
                            )
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

                # 构建 MATLAB 命令：在 gridgen 根目录执行 create_grid.m（启动器会 cd 到 bin 再调 bin/create_grid）
                matlab_run_dir = (
                    os.path.normpath(matlab_bin_dir_norm) if matlab_bin_dir_norm else None
                )
                matlab_run_dir_posix = matlab_run_dir.replace("\\", "/") if matlab_run_dir else None

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
                
                if not matlab_run_dir or not os.path.isfile(
                    os.path.join(matlab_run_dir, "create_grid.m")
                ):
                    self.log_signal.emit(
                        tr(
                            "step2_matlab_run_launcher_missing",
                            "❌ 未找到 MATLAB 启动脚本：{path}/create_grid.m",
                        ).format(path=matlab_run_dir or "")
                    )
                    return False

                matlab_cmd = (
                    f"warning('off', 'all'); "
                    f"feature('DefaultCharacterSet', 'UTF8'); "
                    f"cd('{matlab_run_dir_posix}'); "
                    f"create_grid;"
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
                    text=True,
                    encoding=_SUBPROCESS_IO_ENCODING,
                    errors=_SUBPROCESS_IO_ERRORS,
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
                        self._save_grid_to_cache(
                            cache_key, output_dir_norm, dx_value, dy_value,
                            lon_west, lon_east, lat_south, lat_north, ref_dir, bathymetry_config, coastline_precision_config,
                            gridgen_backend,
                        )
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

    @staticmethod
    def _grid_viz_package_src_dir():
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    def _emit_grid_viz_log(self, msg: str) -> None:
        sig = getattr(self, "log_signal", None)
        if sig is not None:
            sig.emit(msg)

    def _prepare_visualize_grid_busy(self, viz_name: str) -> None:
        """开始后台可视化：日志 + 禁用按钮（与「生成网格」一致）。"""
        self.log(
            tr(
                "step2_grid_viz_worker_start",
                "🖼️ {name}：子进程生成网格图中…",
            ).format(name=viz_name)
        )
        if hasattr(self, "btn_visualize_grid"):
            self.btn_visualize_grid.setEnabled(False)
            self.btn_visualize_grid.setText(tr("step8_generating", "生成中..."))

    def _restore_visualize_grid_button(self) -> None:
        if hasattr(self, "btn_visualize_grid"):
            self.btn_visualize_grid.setEnabled(True)
            self.btn_visualize_grid.setText(tr("step2_visualize_grid", "网格可视化"))

    def _start_grid_viz_background(self, target, args: tuple, viz_name: str) -> None:
        self._prepare_visualize_grid_busy(viz_name)

        def _run():
            try:
                target(*args)
            finally:
                QtCore.QTimer.singleShot(0, self._restore_visualize_grid_button)

        threading.Thread(target=_run, daemon=True).start()

    def _grid_viz_spawn_worker(self, grid_dir_abs: str, mode: str, log_fn=None) -> dict:
        src = self._grid_viz_package_src_dir()
        env = os.environ.copy()
        prev = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = src + (os.pathsep + prev if prev else "")
        cmd = [
            sys.executable,
            "-u",
            "-m",
            "home.step2.grid_viz_worker",
            "--mode",
            mode,
            "--grid-dir",
            grid_dir_abs,
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding=_SUBPROCESS_IO_ENCODING,
            errors=_SUBPROCESS_IO_ERRORS,
            bufsize=1,
            env=env,
        )
        result_json = None
        if proc.stdout:
            for raw in iter(proc.stdout.readline, ""):
                line = raw.rstrip()
                if line.startswith(f"{VIZ_PREFIX}\t"):
                    parts = line.split("\t", 2)
                    if len(parts) >= 3 and parts[1] == "LOG":
                        if log_fn and parts[2].strip():
                            log_fn(parts[2])
                        continue
                    if len(parts) >= 3 and parts[1] == "RESULT":
                        result_json = parts[2]
            proc.stdout.close()
        proc.wait()
        if result_json:
            try:
                return json.loads(result_json)
            except json.JSONDecodeError:
                return {
                    "ok": False,
                    "error": "invalid RESULT json from grid viz worker",
                    "images": [],
                    "photo_dir": "",
                }
        return {
            "ok": False,
            "error": f"grid viz worker exit {proc.returncode}",
            "images": [],
            "photo_dir": "",
        }

    def _grid_viz_run_one(self, grid_dir: str, mode: str, grid_name: str) -> dict:
        """在后台线程中调用：缓存命中则跳过子进程。"""
        grid_dir_abs = os.path.abspath(os.path.normpath(grid_dir))
        if cache_is_current(grid_dir_abs, mode):
            photo_dir = os.path.join(grid_dir_abs, "photo", "grid")
            paths = [p for p in cached_image_paths(grid_dir_abs, mode) if os.path.isfile(p)]
            return {"ok": True, "skipped": True, "images": paths, "photo_dir": photo_dir}
        return self._grid_viz_spawn_worker(grid_dir_abs, mode, log_fn=self._emit_grid_viz_log)

    def _grid_viz_show_on_main(self, image_paths, grid_name: str, photo_dir: str, *, from_cache: bool = False) -> None:
        existing = [p for p in image_paths if os.path.isfile(p)]
        if not existing:
            self.log(tr("step2_grid_viz_no_images", "❌ 未找到可视化图片。"))
            return
        try:
            self._show_images_in_drawer(existing)
        except AttributeError:
            suffix = f" - {grid_name}" if grid_name else ""
            self._show_images_window(existing, title_suffix=suffix)
        if not from_cache:
            self.log(tr("step2_grid_viz_done", "✅ 网格可视化已生成。"))

    def _schedule_grid_viz_show_on_main(
        self, imgs, grid_name: str, photo_dir: str, *, from_cache: bool = False
    ) -> None:
        """从后台线程调用：切回主线程再打开抽屉（避免 QTimer 在非 GUI 线程失效）。"""
        self._grid_viz_pending_show = (imgs, grid_name, photo_dir, from_cache)
        QMetaObject.invokeMethod(
            self,
            "_grid_viz_flush_pending_show",
            Qt.ConnectionType.QueuedConnection,
        )

    @pyqtSlot()
    def _grid_viz_flush_pending_show(self):
        p = getattr(self, "_grid_viz_pending_show", None)
        if not p:
            return
        imgs, gname, pdir, from_cache = (p + (False,))[:4]
        self._grid_viz_show_on_main(imgs, gname, pdir, from_cache=from_cache)
        self._grid_viz_pending_show = None

    def _schedule_grid_viz_show_nested(self, imgs, work_root: str, *, from_cache: bool = False) -> None:
        self._grid_viz_pending_nested = (imgs, work_root, from_cache)
        QMetaObject.invokeMethod(
            self,
            "_grid_viz_flush_pending_nested",
            Qt.ConnectionType.QueuedConnection,
        )

    @pyqtSlot()
    def _grid_viz_flush_pending_nested(self):
        p = getattr(self, "_grid_viz_pending_nested", None)
        if not p:
            return
        imgs, work_root, from_cache = (p + (False,))[:3]
        self._grid_viz_show_nested_done(imgs, work_root, from_cache=from_cache)
        self._grid_viz_pending_nested = None

    def _grid_viz_thread_single(self, grid_dir_abs: str, mode: str, grid_name: str) -> None:
        try:
            res = self._grid_viz_run_one(grid_dir_abs, mode, grid_name)
            if not res.get("ok"):
                err = res.get("error") or "unknown"
                self._emit_grid_viz_log(
                    tr(
                        "step2_visualization_failed",
                        "❌ {grid_name}可视化网格文件失败: {error}",
                    ).format(grid_name=grid_name, error=err)
                )
                return
            imgs = res.get("images") or []
            pdir = res.get("photo_dir") or os.path.join(grid_dir_abs, "photo", "grid")
            from_cache = bool(res.get("skipped"))
            if from_cache:
                self._emit_grid_viz_log(
                    tr("step2_grid_viz_cache_hit", "📎 {name}：网格未变，使用已缓存的图片。").format(
                        name=grid_name
                    )
                )
            self._schedule_grid_viz_show_on_main(imgs, grid_name, pdir, from_cache=from_cache)
        except Exception as e:
            self._emit_grid_viz_log(
                tr(
                    "step2_visualization_failed",
                    "❌ {grid_name}可视化网格文件失败: {error}",
                ).format(grid_name=grid_name, error=e)
            )

    def _grid_viz_show_nested_done(self, image_paths, _work_root: str, *, from_cache: bool = False) -> None:
        existing = [p for p in image_paths if os.path.isfile(p)]
        if not existing:
            self.log(tr("step2_grid_viz_no_images", "❌ 未找到可视化图片。"))
            return
        try:
            self._show_images_in_drawer(existing)
        except AttributeError:
            self._show_images_window(existing, title_suffix="")
        if not from_cache:
            self.log(tr("step2_grid_viz_done", "✅ 网格可视化已生成。"))

    def _grid_viz_thread_nested(self, coarse_dir: str, fine_dir: str, work_root: str) -> None:
        try:
            n1 = tr("step2_outer_grid_title", "外网格（coarse）")
            n2 = tr("step2_inner_grid_title", "内网格（fine）")
            r1 = self._grid_viz_run_one(coarse_dir, "structured", n1)
            if not r1.get("ok"):
                self._emit_grid_viz_log(
                    tr(
                        "step2_visualization_failed",
                        "❌ {grid_name}可视化网格文件失败: {error}",
                    ).format(grid_name=n1, error=r1.get("error", "unknown"))
                )
                return
            r2 = self._grid_viz_run_one(fine_dir, "structured", n2)
            if not r2.get("ok"):
                self._emit_grid_viz_log(
                    tr(
                        "step2_visualization_failed",
                        "❌ {grid_name}可视化网格文件失败: {error}",
                    ).format(grid_name=n2, error=r2.get("error", "unknown"))
                )
                return
            imgs = (r1.get("images") or []) + (r2.get("images") or [])
            both_cached = bool(r1.get("skipped")) and bool(r2.get("skipped"))
            if both_cached:
                self._emit_grid_viz_log(
                    tr("step2_grid_viz_cache_hit", "📎 {name}：网格未变，使用已缓存的图片。").format(
                        name=tr("step2_nested_grid_label", "嵌套网格")
                    )
                )
            self._schedule_grid_viz_show_nested(imgs, work_root, from_cache=both_cached)
        except Exception as e:
            self._emit_grid_viz_log(
                tr(
                    "step2_visualization_failed",
                    "❌ {grid_name}可视化网格文件失败: {error}",
                ).format(grid_name=tr("step2_nested_grid_label", "嵌套网格"), error=e)
            )

    def visualize_grid_files(self):
        """可视化网格：子进程绘图 + photo/grid 缓存；含 bathymetry 与网格结构图。"""
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            self.log(tr("step2_please_select_folder", "❌ 请先选择或创建文件夹！"))
            return

        grid_type = getattr(self, "grid_type_var", tr("step2_grid_type_normal", "普通网格"))

        if self._is_nested_grid(grid_type):
            coarse_dir = os.path.join(self.selected_folder, "coarse")
            fine_dir = os.path.join(self.selected_folder, "fine")
            if not os.path.isdir(coarse_dir) or not os.path.isdir(fine_dir):
                self.log(tr("step2_coarse_fine_not_found", "❌ 未找到 coarse 或 fine 文件夹，请先生成嵌套网格"))
                return
            for sub, gname in (
                (coarse_dir, tr("step2_outer_grid_title", "外网格（coarse）")),
                (fine_dir, tr("step2_inner_grid_title", "内网格（fine）")),
            ):
                mp = _structured_grid_mask_path(sub)
                desc = structured_grid_desc_path(sub)
                gf = {
                    "meta": desc,
                    "bot": os.path.join(sub, "grid.bot"),
                    "mask": mp,
                    "obst": os.path.join(sub, "grid.obst"),
                }
                missing = [k for k, p in gf.items() if p is None or not os.path.isfile(p)]
                if missing:
                    miss = ", ".join(
                        ("grid.nml / ww3_grid.nml.* / grid.meta" if m == "meta" else f"grid.{m}")
                        for m in missing
                    )
                    self.log(
                        tr(
                            "step2_grid_missing_files",
                            "❌ {grid_name}缺少必要的网格文件: {missing_files}",
                        ).format(grid_name=gname, missing_files=miss)
                    )
                    self.log(tr("step2_please_generate_grid", "   请先执行生成网格操作"))
                    return
            wr = os.path.abspath(self.selected_folder)
            self._start_grid_viz_background(
                self._grid_viz_thread_nested,
                (os.path.abspath(coarse_dir), os.path.abspath(fine_dir), wr),
                tr("step2_nested_grid_label", "嵌套网格"),
            )
            return

        if self._is_step2_smc_mesh():
            cell_p = os.path.join(self.selected_folder, "grid_cell.dat")
            run_p = smc_run_metadata_path(self.selected_folder)
            if not os.path.isfile(cell_p) or not run_p:
                self.log(
                    tr(
                        "step2_smc_viz_missing_files",
                        "❌ 未找到 grid_cell.dat 或 SMC 运行元数据 grid.json，请先生成 SMC 网格。",
                    )
                )
                return
            grid_dir_abs = os.path.abspath(self.selected_folder)
            gname = tr("step2_mesh_type_smc", "SMC 网格")
            if cache_is_current(grid_dir_abs, "smc"):
                paths = [p for p in cached_image_paths(grid_dir_abs, "smc") if os.path.isfile(p)]
                if paths:
                    pdir = os.path.join(grid_dir_abs, "photo", "grid")
                    self.log(
                        tr(
                            "step2_grid_viz_cache_hit",
                            "📎 {name}：网格未变，使用已缓存的图片。",
                        ).format(name=gname)
                    )
                    self._grid_viz_show_on_main(paths, gname, pdir, from_cache=True)
                    return
            self._start_grid_viz_background(
                self._grid_viz_thread_single,
                (grid_dir_abs, "smc", gname),
                gname,
            )
            return

        ww3_path = os.path.join(self.selected_folder, "grid.ww3")
        desc_path = structured_grid_desc_path(self.selected_folder)
        use_unst_viz = self._is_step2_unstructured_mesh() or (
            os.path.isfile(ww3_path) and not desc_path
        )
        if use_unst_viz:
            if not os.path.isfile(ww3_path):
                self.log(
                    tr(
                        "step2_unst_ww3_missing_viz",
                        "❌ 未找到 grid.ww3，请先生成非结构网格",
                    )
                )
                return
            grid_dir_abs = os.path.abspath(self.selected_folder)
            gname = tr("step2_grid_type_normal", "普通网格")
            if cache_is_current(grid_dir_abs, "unst"):
                paths = [p for p in cached_image_paths(grid_dir_abs, "unst") if os.path.isfile(p)]
                if paths:
                    pdir = os.path.join(grid_dir_abs, "photo", "grid")
                    self.log(
                        tr(
                            "step2_grid_viz_cache_hit",
                            "📎 {name}：网格未变，使用已缓存的图片。",
                        ).format(name=gname)
                    )
                    self._grid_viz_show_on_main(paths, gname, pdir, from_cache=True)
                    return
            self._start_grid_viz_background(
                self._grid_viz_thread_single,
                (grid_dir_abs, "unst", gname),
                gname,
            )
            return

        mp = _structured_grid_mask_path(self.selected_folder)
        desc_p = structured_grid_desc_path(self.selected_folder)
        gf = {
            "meta": desc_p,
            "bot": os.path.join(self.selected_folder, "grid.bot"),
            "mask": mp,
            "obst": os.path.join(self.selected_folder, "grid.obst"),
        }
        missing = [k for k, p in gf.items() if p is None or not os.path.isfile(p)]
        if missing:
            miss = ", ".join(
                ("grid.nml / ww3_grid.nml.* / grid.meta" if m == "meta" else f"grid.{m}")
                for m in missing
            )
            self.log(
                tr(
                    "step2_grid_missing_files",
                    "❌ {grid_name}缺少必要的网格文件: {missing_files}",
                ).format(
                    grid_name=tr("step2_grid_type_normal", "普通网格"),
                    missing_files=miss,
                )
            )
            self.log(tr("step2_please_generate_grid", "   请先执行生成网格操作"))
            return

        grid_dir_abs = os.path.abspath(self.selected_folder)
        gname = tr("step2_grid_type_normal", "普通网格")
        if cache_is_current(grid_dir_abs, "structured"):
            paths = [p for p in cached_image_paths(grid_dir_abs, "structured") if os.path.isfile(p)]
            if paths:
                pdir = os.path.join(grid_dir_abs, "photo", "grid")
                self.log(
                    tr(
                        "step2_grid_viz_cache_hit",
                        "📎 {name}：网格未变，使用已缓存的图片。",
                    ).format(name=gname)
                )
                self._grid_viz_show_on_main(paths, gname, pdir, from_cache=True)
                return
        self._start_grid_viz_background(
            self._grid_viz_thread_single,
            (grid_dir_abs, "structured", gname),
            gname,
        )

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
        """读取 grid.nml（&RECT_NML）或旧版 ASCII，返回经纬度数组"""
        try:
            lon, lat = rect_lon_lat_mesh(fname)
            if lon is None:
                self.log(tr("step2_read_meta_failed", "❌ 读取 grid.meta 文件失败"))
                return None, None
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
