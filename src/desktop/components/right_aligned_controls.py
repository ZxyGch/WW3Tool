"""Shared right-aligned Fluent selection controls."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QCheckBox, QStyle, QStyleOptionButton, QWidget
from qfluentwidgets import CheckBox, IndicatorPosition, SwitchButton
from qfluentwidgets.components.widgets.check_box import CheckBoxIcon


class RightAlignedCheckBox(CheckBox):
    """Empty-text checkbox with a complete border aligned to the right edge."""

    def paintEvent(self, event) -> None:
        QCheckBox.paintEvent(self, event)
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)

        option = QStyleOptionButton()
        option.initFrom(self)
        rect = self.style().subElementRect(
            QStyle.SubElement.SE_CheckBoxIndicator, option, self
        ).adjusted(0, 0, -1, 0)

        painter.setPen(self._borderColor())
        painter.setBrush(self._backgroundColor())
        painter.drawRoundedRect(rect, 4.5, 4.5)
        if not self.isEnabled():
            painter.setOpacity(0.8)
        if self.checkState() == Qt.CheckState.Checked:
            CheckBoxIcon.ACCEPT.render(painter, rect)
        elif self.checkState() == Qt.CheckState.PartiallyChecked:
            CheckBoxIcon.PARTIAL_ACCEPT.render(painter, rect)


def create_right_aligned_check_box(parent: QWidget | None = None) -> RightAlignedCheckBox:
    """Create a configured right-aligned checkbox without overriding Fluent's dispatcher."""
    check = RightAlignedCheckBox("", parent)
    check.setFixedWidth(29)
    check.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    return check


class RightAlignedSwitchButton(SwitchButton):
    """Text-free Fluent switch whose indicator reaches the widget's right edge."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, indicatorPos=IndicatorPosition.RIGHT)
        self.setSpacing(0)
        self.setOnText("")
        self.setOffText("")
        self.hBox.setContentsMargins(0, 0, 0, 0)
