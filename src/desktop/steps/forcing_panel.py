"""Step 1 panel for selecting forcing fields."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import QGridLayout, QLabel, QSizePolicy, QWidget
from qfluentwidgets import ComboBox, LineEdit, PrimaryPushButton

from ..components.combo_box import left_align_combo_text
from ..components.header_card import create_header_card
from ..components.right_aligned_controls import create_right_aligned_check_box
from workflows.support.translations import tr


class ForcingStepPanel:
    """Own Step 1 widgets while the window coordinates processing actions."""

    def __init__(
        self,
        parent: QWidget,
        *,
        create_button: Callable[[str, Callable[..., object]], PrimaryPushButton],
        browse_path: Callable[[str, bool], None],
        show_file_info: Callable[[], None],
    ) -> None:
        self.paths: dict[str, LineEdit] = {}
        self.path_buttons: dict[str, PrimaryPushButton] = {}
        group, layout = create_header_card(parent, tr("step1_title", "第一步：选择强迫场文件"), include_vbox_style=True)
        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        for row, label, key, button_text in (
            (0, tr("step1_label_wind", "风场："), "wind", tr("step1_choose_wind", "选择风场")),
            (1, tr("step1_label_current", "流场："), "current", tr("step1_choose_current", "选择流场")),
            (2, tr("step1_label_level", "水位场："), "level", tr("step1_choose_level", "选择水位场")),
            (3, tr("step1_label_ice", "海冰场："), "ice", tr("step1_choose_ice", "选择海冰场")),
        ):
            self._add_path_button_pair(grid, row, label, key, button_text, create_button, browse_path)
        layout.addLayout(grid)

        self.mode = ComboBox(parent)
        self.mode.addItems([tr("copy", "复制"), tr("move", "移动")])
        left_align_combo_text(self.mode)
        self.mode.hide()
        self.auto_associate = create_right_aligned_check_box(parent)
        self.auto_associate.setChecked(True)
        self.auto_associate.hide()
        self.status = QLabel(tr("status_waiting", "等待执行"))
        self.status.hide()

        info_button = create_button(tr("step1_view_field_files_info", "查看所有场文件信息"), show_file_info)
        layout.addWidget(info_button)
        group.viewLayout.setContentsMargins(11, 10, 11, 12)
        group.viewLayout.addLayout(layout)
        self.widget = group

    def _add_path_button_pair(
        self,
        grid: QGridLayout,
        row: int,
        label: str,
        key: str,
        button_text: str,
        create_button: Callable[[str, Callable[..., object]], PrimaryPushButton],
        browse_path: Callable[[str, bool], None],
    ) -> None:
        field = LineEdit()
        field.setClearButtonEnabled(True)
        field.hide()
        button = create_button(button_text, lambda _checked=False: browse_path(key, False))
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        grid.addWidget(QLabel(label), row, 0)
        grid.addWidget(button, row, 1)
        self.paths[key] = field
        self.path_buttons[key] = button
