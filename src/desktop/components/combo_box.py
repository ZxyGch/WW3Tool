"""Presentation helpers shared by desktop combo boxes."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QWidget


def left_align_combo_text(combo: QWidget) -> None:
    """Keep combo display text aligned with the left-side form fields."""

    def apply_alignment() -> None:
        line_edit_factory = getattr(combo, "lineEdit", None)
        if callable(line_edit_factory):
            line_edit = line_edit_factory()
            if line_edit is not None:
                line_edit.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        if "text-align: left" not in combo.styleSheet():
            combo.setStyleSheet(
                f"{combo.styleSheet()}\n"
                "QComboBox, ComboBox, EditableComboBox { text-align: left; }\n"
            )

    apply_alignment()
    QTimer.singleShot(0, apply_alignment)
