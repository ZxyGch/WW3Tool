"""Step 1 panel for selecting forcing fields."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QWidget
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
        confirm_crop: Callable[[], None],
        mode_changed: Callable[[], None],
    ) -> None:
        self.paths: dict[str, LineEdit] = {}
        self.path_buttons: dict[str, PrimaryPushButton] = {}
        self.range_fields: dict[str, LineEdit] = {}
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
        for label, value in (
            (tr("step1_mode_copy_full", "完整复制"), "copy"),
            (tr("step1_mode_move_full", "完整剪切"), "move"),
            (tr("step1_mode_crop", "范围裁剪"), "crop"),
        ):
            self.mode.addItem(label)
            self.mode.setItemData(self.mode.count() - 1, value)
        left_align_combo_text(self.mode)
        self.mode.currentIndexChanged.connect(lambda *_: mode_changed())
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel(tr("step1_process_mode", "导入方式：")))
        mode_row.addWidget(self.mode, 1)
        layout.addLayout(mode_row)

        range_grid = QGridLayout()
        range_grid.setHorizontalSpacing(8)
        range_grid.setVerticalSpacing(8)
        range_grid.setColumnStretch(1, 1)
        range_grid.setColumnStretch(3, 1)
        self._add_range_field(range_grid, 0, 0, tr("step1_time_start", "开始时间："), "time_start")
        self._add_range_field(range_grid, 0, 2, tr("step1_time_end", "结束时间："), "time_end")
        self._add_range_field(range_grid, 1, 0, tr("step1_lon_west", "西边界："), "lon_west")
        self._add_range_field(range_grid, 1, 2, tr("step1_lon_east", "东边界："), "lon_east")
        self._add_range_field(range_grid, 2, 0, tr("step1_lat_south", "南边界："), "lat_south")
        self._add_range_field(range_grid, 2, 2, tr("step1_lat_north", "北边界："), "lat_north")
        layout.addLayout(range_grid)

        self.confirm_crop_button = create_button(
            tr("step1_confirm_crop_import", "确认裁剪并导入"),
            confirm_crop,
        )
        self.confirm_crop_button.hide()
        layout.addWidget(self.confirm_crop_button)

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

    def process_mode_value(self) -> str:
        data = self.mode.itemData(self.mode.currentIndex())
        return str(data or "copy")

    def set_process_mode(self, value: str) -> None:
        for index in range(self.mode.count()):
            if str(self.mode.itemData(index)) == value:
                self.mode.setCurrentIndex(index)
                return
        self.mode.setCurrentIndex(0)

    def set_range_editable(self, editable: bool) -> None:
        for field in self.range_fields.values():
            field.setReadOnly(not editable)
            field.setClearButtonEnabled(editable)
        self.confirm_crop_button.setVisible(editable)

    def crop_time_range(self) -> list[str]:
        return [
            self.range_fields["time_start"].text().strip(),
            self.range_fields["time_end"].text().strip(),
        ]

    def crop_bbox(self) -> list[float]:
        return [
            float(self.range_fields["lon_west"].text().strip()),
            float(self.range_fields["lon_east"].text().strip()),
            float(self.range_fields["lat_south"].text().strip()),
            float(self.range_fields["lat_north"].text().strip()),
        ]

    def set_range_values(
        self,
        *,
        time_range: tuple[str, str] | list[str] | None = None,
        bbox: tuple[float, float, float, float] | list[float] | None = None,
        overwrite_editable: bool = False,
    ) -> None:
        if time_range and (overwrite_editable or not self.range_fields["time_start"].text().strip()):
            self.range_fields["time_start"].setText(str(time_range[0]))
            self.range_fields["time_end"].setText(str(time_range[1]))
        if bbox and (overwrite_editable or not self.range_fields["lon_west"].text().strip()):
            west, east, south, north = [float(v) for v in bbox]
            self.range_fields["lon_west"].setText(f"{west:.6g}")
            self.range_fields["lon_east"].setText(f"{east:.6g}")
            self.range_fields["lat_south"].setText(f"{south:.6g}")
            self.range_fields["lat_north"].setText(f"{north:.6g}")

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

    def _add_range_field(self, grid: QGridLayout, row: int, col: int, label: str, key: str) -> None:
        field = LineEdit()
        field.setReadOnly(True)
        field.setClearButtonEnabled(False)
        field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        grid.addWidget(QLabel(label), row, col)
        grid.addWidget(field, row, col + 1)
        self.range_fields[key] = field
