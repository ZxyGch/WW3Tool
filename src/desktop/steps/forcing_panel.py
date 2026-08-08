"""Step 2 panel for selecting forcing fields."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import QGridLayout, QLabel, QSizePolicy, QWidget
from qfluentwidgets import ComboBox, LineEdit, PrimaryPushButton

from ..components.combo_box import left_align_combo_text
from ..components.header_card import create_header_card
from ..components.right_aligned_controls import create_right_aligned_check_box
from workflows.support.translations import tr


class ForcingStepPanel:
    """Own Step 2 widgets while the window coordinates processing actions."""

    def __init__(
        self,
        parent: QWidget,
        *,
        create_button: Callable[[str, Callable[..., object]], PrimaryPushButton],
        input_style: Callable[[], str],
        combo_style: Callable[[], str],
        browse_path: Callable[[str, bool], None],
        clear_path: Callable[[str], None],
        open_mapping: Callable[[str], None],
        show_file_info: Callable[[], None],
        crop_import: Callable[[], None],
        direct_import: Callable[[], None],
        load_intersection: Callable[[], None],
        use_grid_bounds: Callable[[], None],
        view_map: Callable[[], None],
        mode_changed: Callable[[], None],
    ) -> None:
        self._input_style = input_style
        self.paths: dict[str, LineEdit] = {}
        self.path_buttons: dict[str, PrimaryPushButton] = {}
        self.clear_buttons: dict[str, PrimaryPushButton] = {}
        self.mapping_buttons: dict[str, PrimaryPushButton] = {}
        self.range_fields: dict[str, LineEdit] = {}
        group, layout = create_header_card(parent, tr("step2_title", "第二步：选择强迫场文件"), include_vbox_style=True)
        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 0)
        for row, label, key, button_text in (
            (0, tr("step2_label_wind", "风场："), "wind", tr("step2_choose_wind", "选择风场")),
            (1, tr("step2_label_current", "流场："), "current", tr("step2_choose_current", "选择流场")),
            (2, tr("step2_label_level", "水位场："), "level", tr("step2_choose_level", "选择水位场")),
            (3, tr("step2_label_ice", "海冰场："), "ice", tr("step2_choose_ice", "选择海冰场")),
        ):
            self._add_path_button_pair(
                grid, row, label, key, button_text, create_button, browse_path, clear_path, open_mapping
            )
        layout.addLayout(grid)

        self.mode = ComboBox(parent)
        self.mode.setStyleSheet(combo_style())
        for label, value in (
            (tr("step2_mode_copy_full", "复制"), "copy"),
            (tr("step2_mode_move_full", "剪切"), "move"),
        ):
            self.mode.addItem(label)
            self.mode.setItemData(self.mode.count() - 1, value)
        left_align_combo_text(self.mode)
        self.mode.currentIndexChanged.connect(lambda *_: mode_changed())
        range_grid = QGridLayout()
        range_grid.setHorizontalSpacing(8)
        range_grid.setVerticalSpacing(8)
        range_grid.setColumnStretch(1, 1)
        range_grid.setColumnStretch(3, 1)
        range_grid.addWidget(QLabel(tr("step2_process_mode", "导入模式：")), 0, 0)
        range_grid.addWidget(self.mode, 0, 1, 1, 3)
        self._add_range_pair(
            range_grid,
            1,
            tr("step2_time_range", "时间："),
            "time_start",
            "time_end",
            placeholder=tr("step2_date_placeholder", "YYYYMMDD"),
        )
        self._add_range_pair(
            range_grid,
            2,
            tr("step2_lat_range", "纬度："),
            "lat_south",
            "lat_north",
            start_placeholder=tr("step2_lat_south_placeholder", "-40"),
            end_placeholder=tr("step2_lat_north_placeholder", "20"),
        )
        self._add_range_pair(
            range_grid,
            3,
            tr("step2_lon_range", "经度："),
            "lon_west",
            "lon_east",
            start_placeholder=tr("step2_lon_west_placeholder", "-30"),
            end_placeholder=tr("step2_lon_east_placeholder", "110"),
        )
        layout.addLayout(range_grid)
        # 使用网格范围和读取公共范围在同一行
        button_row = QGridLayout()
        button_row.setSpacing(10)
        self.use_grid_bounds_button = create_button(
            tr("step2_use_grid_bounds", "使用网格范围"),
            use_grid_bounds,
        )
        self.load_intersection_button = create_button(
            tr("step2_load_intersection", "读取公共范围"),
            load_intersection,
        )
        button_row.addWidget(self.use_grid_bounds_button, 0, 0)
        button_row.addWidget(self.load_intersection_button, 0, 1)
        layout.addLayout(button_row)

        self.map_button = create_button(tr("step2_view_map", "查看地图"), view_map)
        layout.addWidget(self.map_button)

        self.crop_import_button = create_button(
            tr("step2_confirm_crop_import", "确认裁剪并导入"),
            crop_import,
        )
        layout.addWidget(self.crop_import_button)

        self.direct_import_button = create_button(
            tr("step2_direct_import", "直接导入，不进行裁剪"),
            direct_import,
        )
        layout.addWidget(self.direct_import_button)
        self.set_range_editable(True)

        self.auto_associate = create_right_aligned_check_box(parent)
        self.auto_associate.setChecked(True)
        self.auto_associate.hide()
        self.status = QLabel(tr("status_waiting", "等待执行"))
        self.status.hide()

        info_button = create_button(tr("step2_view_field_files_info", "查看所有场文件信息"), show_file_info)
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

    def apply_clear_button_style(self, style: str) -> None:
        for button in self.clear_buttons.values():
            button.setStyleSheet(_clear_button_style(style))

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
            self.range_fields["time_start"].setText(_date_yyyymmdd(time_range[0]))
            self.range_fields["time_end"].setText(_date_yyyymmdd(time_range[1]))
        if bbox and (overwrite_editable or not self.range_fields["lon_west"].text().strip()):
            west, east, south, north = [float(v) for v in bbox]
            self.range_fields["lon_west"].setText(f"{west:.6g}")
            self.range_fields["lon_east"].setText(f"{east:.6g}")
            self.range_fields["lat_south"].setText(f"{south:.6g}")
            self.range_fields["lat_north"].setText(f"{north:.6g}")

    def clear_range_values(self) -> None:
        for field in self.range_fields.values():
            field.clear()

    def _add_path_button_pair(
        self,
        grid: QGridLayout,
        row: int,
        label: str,
        key: str,
        button_text: str,
        create_button: Callable[[str, Callable[..., object]], PrimaryPushButton],
        browse_path: Callable[[str, bool], None],
        clear_path: Callable[[str], None],
        open_mapping: Callable[[str], None],
    ) -> None:
        field = LineEdit()
        field.setClearButtonEnabled(True)
        field.hide()
        button = create_button(button_text, lambda _checked=False: browse_path(key, False))
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        clear_button = create_button("×", lambda _checked=False: clear_path(key))
        clear_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        font = clear_button.font()
        font.setPointSize(max(font.pointSize() + 4, 16))
        clear_button.setFont(font)
        clear_button.setStyleSheet(_clear_button_style(clear_button.styleSheet()))
        side = max(button.sizeHint().height(), clear_button.sizeHint().height())
        clear_button.setFixedSize(side, side)
        clear_button.setToolTip(tr("step2_clear_forcing_selection", "清除选择"))
        # 铅笔按钮：打开变量映射/服务器路径编辑弹窗，位于清除按钮左侧
        # [EN] Pencil button: opens the variable mapping / server path dialog,
        # positioned to the left of the clear button.
        mapping_button = create_button("✏️", lambda _checked=False: open_mapping(key))
        mapping_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        mapping_button.setFixedSize(side, side)
        mapping_button.setToolTip(tr("step2_variable_mapping_tip", "变量映射与服务器路径（经度/纬度/时间/分量）"))
        grid.addWidget(QLabel(label), row, 0)
        grid.addWidget(button, row, 1)
        grid.addWidget(mapping_button, row, 2)
        grid.addWidget(clear_button, row, 3)
        self.paths[key] = field
        self.path_buttons[key] = button
        self.clear_buttons[key] = clear_button
        self.mapping_buttons[key] = mapping_button

    def _add_range_pair(
        self,
        grid: QGridLayout,
        row: int,
        label: str,
        start_key: str,
        end_key: str,
        *,
        placeholder: str = "",
        start_placeholder: str = "",
        end_placeholder: str = "",
    ) -> None:
        grid.addWidget(QLabel(label), row, 0)
        start = self._new_range_field(placeholder=start_placeholder or placeholder)
        end = self._new_range_field(placeholder=end_placeholder or placeholder)
        grid.addWidget(start, row, 1)
        grid.addWidget(QLabel(tr("range_separator", "至")), row, 2)
        grid.addWidget(end, row, 3)
        self.range_fields[start_key] = start
        self.range_fields[end_key] = end

    def _new_range_field(self, *, placeholder: str = "") -> LineEdit:
        field = LineEdit()
        field.setStyleSheet(self._input_style())
        field.setReadOnly(False)
        field.setClearButtonEnabled(True)
        if placeholder:
            field.setPlaceholderText(placeholder)
        field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return field


def _date_yyyymmdd(value: object) -> str:
    text = str(value or "").strip()
    digits = "".join(ch for ch in text[:10] if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else text


def _clear_button_style(style: str) -> str:
    return style.replace("padding: 8px 16px;", "padding: 0px;")
