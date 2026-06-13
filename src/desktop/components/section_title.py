"""带左右分隔线的小节标题（与 src 版 step4_ui / preprocessing 一致）。"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QWidget

from . import styles


def create_section_title(text: str) -> QWidget:
    """返回与 Slurm / WAVEWATCH 小节标题相同样式的容器。"""
    container = QWidget()
    row = QHBoxLayout(container)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)

    left = QFrame()
    left.setFrameShape(QFrame.Shape.HLine)
    left.setFixedHeight(1)
    left.setStyleSheet("background-color: #888888; border: none;")
    row.addWidget(left, 1)

    label = QLabel(text)
    label.setProperty("sectionTitle", True)
    apply_section_title_style(label)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(False)
    label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
    row.addWidget(label)

    right = QFrame()
    right.setFrameShape(QFrame.Shape.HLine)
    right.setFixedHeight(1)
    right.setStyleSheet("background-color: #888888; border: none;")
    row.addWidget(right, 1)

    row.setStretch(0, 1)
    row.setStretch(2, 1)
    return container


def apply_section_title_style(label: QLabel) -> None:
    color = "#FFFFFF" if styles.is_dark() else "#000000"
    label.setStyleSheet(f"font-weight: normal; font-size: 14px; color: {color};")
    palette = label.palette()
    palette.setColor(QPalette.ColorRole.WindowText, QColor(color))
    label.setPalette(palette)
