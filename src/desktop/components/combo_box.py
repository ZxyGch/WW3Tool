"""Presentation helpers shared by desktop combo boxes."""

from __future__ import annotations

from collections.abc import Iterable

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QWidget
from qfluentwidgets import ComboBox

from workflows.domain.parameter_catalog import canonical_file_split
from workflows.support.translations import tr


def add_labeled_combo_items(combo: ComboBox, items: Iterable[tuple[str, str]]) -> None:
    """qfluentwidgets ``addItem(text, icon, userData)`` 第二参是 icon，枚举值必须用 ``userData=``。

    [EN] In qfluentwidgets, ``addItem(text, icon, userData)`` treats the second
    parameter as icon; enum values must be passed with ``userData=``.
    """
    for label, value in items:
        combo.addItem(label, userData=value)


def combo_selected_user_data(combo: ComboBox) -> str:
    """读取当前项 ``userData``；缺失时回退 ``currentText``。

    [EN] Read the current item's ``userData``; fall back to ``currentText`` when missing.
    """
    data = combo.itemData(combo.currentIndex())
    if data is not None and str(data).strip():
        return str(data).strip()
    return combo.currentText().strip()


def file_split_combo_items() -> list[tuple[str, str]]:
    """``ww3.file_split`` 下拉项：展示文案 + 规范枚举值。

    [EN] Drop-down items for ``ww3.file_split``: display text + canonical enum value.
    """
    return [
        (tr("file_split_single", "单文件"), "single"),
        (tr("file_split_hour", "小时"), "hour"),
        (tr("file_split_day", "天"), "day"),
        (tr("file_split_month", "月"), "month"),
        (tr("file_split_year", "年"), "year"),
    ]


def current_file_split_from_combo(combo: ComboBox, *, default: str = "year") -> str:
    """从下拉框读出规范的 ``ww3.file_split`` 枚举值。

    [EN] Read the canonical ``ww3.file_split`` enum value from the combo box.
    """
    return canonical_file_split(combo_selected_user_data(combo), default=default)


def select_file_split_combo(combo: ComboBox, value: object, *, default: str = "year") -> None:
    """按规范值选中 file_split 项；兼容旧值 ``none`` 与误存的展示文案。

    [EN] Select the file_split item by canonical value; compatible with the legacy
    value ``none`` and mistakenly stored display text.
    """
    selected = canonical_file_split(value, default=default)
    for index in range(combo.count()):
        data = combo.itemData(index)
        if str(data or "").strip().lower() == selected:
            combo.setCurrentIndex(index)
            return
    label_by_value = {item_value: item_label for item_label, item_value in file_split_combo_items()}
    target_label = label_by_value.get(selected)
    if target_label:
        for index in range(combo.count()):
            if combo.itemText(index) == target_label:
                combo.setCurrentIndex(index)
                return
    if combo.count():
        combo.setCurrentIndex(0)


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
