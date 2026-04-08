"""
Passive view adapter for Step 1.
"""

from __future__ import annotations

import os
from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from qfluentwidgets import InfoBar, MessageBoxBase

from setting.config import get_forcing_field_default_dir
from setting.language_manager import tr

from .state import ForcingField, Step1State


class _RotatingLoadingSpinner(QtWidgets.QWidget):
    """Simple loading spinner without extra dependencies."""

    def __init__(self, parent=None, diameter: int = 52) -> None:
        super().__init__(parent)
        self._angle = 0
        self._thickness = 5
        self.setFixedSize(diameter, diameter)
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._advance)
        self._timer.start()

    def _advance(self) -> None:
        self._angle = (self._angle + 12) % 360
        self.update()

    def paintEvent(self, event) -> None:
        _ = event
        rect = self.rect().adjusted(6, 6, -6, -6)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        track_pen = QtGui.QPen(QtGui.QColor(220, 224, 230), self._thickness)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(rect, 0, 360 * 16)

        try:
            from qfluentwidgets import themeColor

            accent = themeColor()
        except Exception:
            accent = self.palette().color(QtGui.QPalette.ColorRole.Highlight)
        if not accent or not accent.isValid():
            accent = QtGui.QColor(0, 122, 204)
        arc_pen = QtGui.QPen(accent, self._thickness)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        painter.drawArc(rect, int(-self._angle * 16), int(110 * 16))


class _ForcingConvertLoadingDialog(MessageBoxBase):
    """Step 1 loading dialog."""

    def __init__(self, parent, message: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("")
        self.hideYesButton()
        self.hideCancelButton()
        self.buttonLayout.parent().setVisible(False)
        if hasattr(self, "setClosableOnMaskClicked"):
            self.setClosableOnMaskClicked(True)

        container = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        spinner = _RotatingLoadingSpinner(container, diameter=56)
        layout.addWidget(spinner, alignment=Qt.AlignmentFlag.AlignCenter)

        title = QtWidgets.QLabel(tr("step1_forcing_convert_loading_title", "正在处理强迫场文件…"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)

        self._message_label = QtWidgets.QLabel(message)
        self._message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message_label.setWordWrap(True)
        self._message_label.setStyleSheet("font-size: 13px;")
        layout.addWidget(self._message_label)

        self.viewLayout.addWidget(container, 1)
        self.setMinimumWidth(420)
        self.setMinimumHeight(220)
        self.setWindowModality(QtCore.Qt.WindowModality.WindowModal)

    def set_message(self, message: str) -> None:
        self._message_label.setText(message)


class Step1ViewAdapter:
    """Passive View implementation backed by MainWindow widgets."""

    def __init__(self, window) -> None:
        self.window = window
        self._loading_dialog: Optional[_ForcingConvertLoadingDialog] = None

    def pick_file(self, kind: ForcingField) -> Optional[str]:
        title_map = {
            ForcingField.WIND: tr("wind_file_dialog_title", "选择风场文件"),
            ForcingField.CURRENT: tr("current_file_dialog_title", "选择流场文件"),
            ForcingField.LEVEL: tr("level_file_dialog_title", "选择水位场文件"),
            ForcingField.ICE: tr("ice_file_dialog_title", "选择海冰场文件"),
        }
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.window,
            title_map[kind],
            get_forcing_field_default_dir(),
            tr("wind_file_filter", "NetCDF 文件 (*.nc);;所有文件 (*.*)"),
        )
        return file_path or None

    def render_state(self, state: Step1State) -> None:
        self._render_wind_button(state)
        self._render_regular_button(
            "btn_choose_current_file",
            state.files.current,
            tr("step1_choose_current", "选择流场"),
        )
        self._render_regular_button(
            "btn_choose_level_file",
            state.files.level,
            tr("step1_choose_level", "选择水位场"),
        )
        self._render_regular_button(
            "btn_choose_ice_file_home",
            state.files.ice,
            tr("step1_choose_ice", "选择海冰场"),
        )

        if hasattr(self.window, "_update_forcing_fields_display"):
            self.window._update_forcing_fields_display()
        for method_name in ("_update_jason3_file_buttons", "_update_ndbc_file_buttons"):
            method = getattr(self.window, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass

    def show_loading(self, message: str) -> None:
        if self._loading_dialog is None:
            self._loading_dialog = _ForcingConvertLoadingDialog(self.window, message)
        else:
            self._loading_dialog.set_message(message)
        self._loading_dialog.show()
        self._loading_dialog.raise_()
        self._loading_dialog.activateWindow()
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.processEvents()

    def hide_loading(self) -> None:
        if self._loading_dialog is not None:
            self._loading_dialog.close()
            self._loading_dialog.deleteLater()
            self._loading_dialog = None

    def show_notice(self, level: str, title: str, content: str) -> None:
        notice = getattr(InfoBar, level, None) or InfoBar.info
        notice(title=title, content=content, duration=3000, parent=self.window)

    def write_lonlat_to_step2(self, bounds: dict[str, float]) -> None:
        lon_min = bounds.get("lon_min")
        lon_max = bounds.get("lon_max")
        lat_min = bounds.get("lat_min")
        lat_max = bounds.get("lat_max")
        if None in (lon_min, lon_max, lat_min, lat_max):
            return

        if hasattr(self.window, "lon_west_edit") and self.window.lon_west_edit:
            self.window.lon_west_edit.setText(f"{lon_min:.2f}")
        if hasattr(self.window, "lon_east_edit") and self.window.lon_east_edit:
            self.window.lon_east_edit.setText(f"{lon_max:.2f}")
        if hasattr(self.window, "lat_south_edit") and self.window.lat_south_edit:
            self.window.lat_south_edit.setText(f"{lat_min:.2f}")
        if hasattr(self.window, "lat_north_edit") and self.window.lat_north_edit:
            self.window.lat_north_edit.setText(f"{lat_max:.2f}")

        if getattr(self.window, "grid_type_var", None) == tr("step2_grid_type_nested", "嵌套网格"):
            if hasattr(self.window, "inner_lon_west_edit") and self.window.inner_lon_west_edit:
                self.window.inner_lon_west_edit.setText(f"{lon_min:.2f}")
            if hasattr(self.window, "inner_lon_east_edit") and self.window.inner_lon_east_edit:
                self.window.inner_lon_east_edit.setText(f"{lon_max:.2f}")
            if hasattr(self.window, "inner_lat_south_edit") and self.window.inner_lat_south_edit:
                self.window.inner_lat_south_edit.setText(f"{lat_min:.2f}")
            if hasattr(self.window, "inner_lat_north_edit") and self.window.inner_lat_north_edit:
                self.window.inner_lat_north_edit.setText(f"{lat_max:.2f}")

    def log(self, message: str, update: bool = False) -> None:
        if update and hasattr(self.window, "log_update_last_line_signal"):
            self.window.log_update_last_line_signal.emit(message)
            return
        if hasattr(self.window, "log"):
            self.window.log(message)

    def _render_wind_button(self, state: Step1State) -> None:
        display_name = self._display_name(state.files.wind, tr("step1_choose_wind", "选择风场"))
        filled = bool(state.files.wind)
        if hasattr(self.window, "_set_wind_file_button_text"):
            self.window._set_wind_file_button_text(display_name, filled=filled)
            return
        button = getattr(self.window, "btn_choose_wind_file", None)
        if button is not None and hasattr(self.window, "_set_home_forcing_button_text"):
            self.window._set_home_forcing_button_text(button, display_name, filled=filled)

    def _render_regular_button(self, button_attr: str, path: Optional[str], default_text: str) -> None:
        button = getattr(self.window, button_attr, None)
        if button is None:
            return
        display_name = self._display_name(path, default_text)
        filled = bool(path)
        if hasattr(self.window, "_set_home_forcing_button_text"):
            self.window._set_home_forcing_button_text(button, display_name, filled=filled)
        else:
            button.setText(display_name)

    @staticmethod
    def _display_name(path: Optional[str], default_text: str) -> str:
        if not path:
            return default_text
        file_name = os.path.basename(path)
        return file_name[:27] + "..." if len(file_name) > 30 else file_name
