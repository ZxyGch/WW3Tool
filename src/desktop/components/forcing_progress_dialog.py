"""Progress feedback displayed while forcing files are prepared."""

from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from qfluentwidgets import MessageBoxBase, themeColor
from workflows.support.translations import tr


class _RotatingSpinner(QtWidgets.QWidget):
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

        accent = themeColor()
        if not accent or not accent.isValid():
            accent = self.palette().color(QtGui.QPalette.ColorRole.Highlight)
        arc_pen = QtGui.QPen(accent, self._thickness)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        painter.drawArc(rect, int(-self._angle * 16), int(110 * 16))


class ForcingProgressDialog(MessageBoxBase):
    """Legacy-aligned wait dialog for Step 2 file preparation."""

    def __init__(self, parent, message: str | None = None) -> None:
        super().__init__(parent)
        message = message or tr("please_wait", "请稍候...")
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

        layout.addWidget(_RotatingSpinner(container, diameter=56), alignment=Qt.AlignmentFlag.AlignCenter)

        title = QtWidgets.QLabel(tr("forcing_progress_title", "正在处理强迫场文件..."))
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
