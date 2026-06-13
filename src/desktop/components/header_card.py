"""Shared card factory for desktop step panels."""

from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import HeaderCardWidget


def create_header_card(
    parent: QWidget,
    title: str,
    *,
    include_vbox_style: bool = False,
) -> tuple[HeaderCardWidget, QVBoxLayout]:
    card = HeaderCardWidget(parent)
    card.setTitle(title)
    style = """
        HeaderCardWidget QLabel#headerLabel {
            font-weight: normal;
            margin-left: 0px;
            padding-left: 0px;
        }
    """
    if include_vbox_style:
        style += """
        HeaderCardWidget QVBoxLayout {
            margin: 3px;
            padding: 3px;
        }
        """
    card.setStyleSheet(style)
    card.headerLayout.setContentsMargins(11, 10, 11, 12)
    layout = QVBoxLayout()
    layout.setSpacing(10)
    layout.setContentsMargins(0, 0, 0, 0)
    return card, layout
