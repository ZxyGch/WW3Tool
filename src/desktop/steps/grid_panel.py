"""Step 2 panel for grid parameters and grid-related actions."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import CheckBox, ComboBox, LineEdit, PrimaryPushButton

from ..components.combo_box import left_align_combo_text
from ..components.header_card import create_header_card
from ..components.validators import double_validator, int_validator
from workflows.domain.config_models import GridConfig, GridRegion
from workflows.support.translations import tr


class GridStepPanel:
    """Own grid controls, presentation rules and form value conversion."""

    def __init__(
        self,
        parent: QWidget,
        *,
        create_button: Callable[[str, Callable[..., object]], PrimaryPushButton],
        input_style: Callable[[], str],
        combo_style: Callable[[], str],
        section_title: Callable[[str], QWidget],
        nested_factor: Callable[[], float],
        load_bounds: Callable[[], None],
        setup_outer_grid: Callable[[], None],
        setup_inner_grid: Callable[[], None],
        view_map: Callable[[], None],
        generate_grid: Callable[[], None],
        visualize_grid: Callable[[], None],
    ) -> None:
        self._input_style = input_style
        self._nested_factor = nested_factor
        self.fields: dict[str, LineEdit] = {}
        self.field_labels: dict[str, QLabel] = {}
        group, layout = create_header_card(parent, tr("step2_title", "第二步：生成网格"))

        self.outer_grid_title = section_title(tr("step2_outer_params", "外网格参数"))
        self.outer_grid_title.hide()
        layout.addWidget(self.outer_grid_title)
        outer_grid = QGridLayout()
        outer_grid.setSpacing(10)
        outer_grid.setColumnStretch(1, 1)
        outer_grid.setColumnStretch(3, 1)
        self._display_line(outer_grid, 0, 0, tr("step2_dx", "DX:"), "grid_dx")
        self._display_line(outer_grid, 0, 2, tr("step2_dy", "DY:"), "grid_dy")
        self._display_line(outer_grid, 1, 0, tr("step2_lon_west", "西经:"), "grid_lon_west")
        self._display_line(outer_grid, 1, 2, tr("step2_lon_east", "东经:"), "grid_lon_east")
        self._display_line(outer_grid, 2, 0, tr("step2_lat_south", "南纬:"), "grid_lat_south")
        self._display_line(outer_grid, 2, 2, tr("step2_lat_north", "北纬:"), "grid_lat_north")
        layout.addLayout(outer_grid)

        self.inner_grid_widget = QWidget()
        inner_layout = QVBoxLayout(self.inner_grid_widget)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(10)
        inner_layout.addWidget(section_title(tr("step2_inner_params", "内网格参数")))
        inner_grid = QGridLayout()
        inner_grid.setSpacing(10)
        inner_grid.setColumnStretch(1, 1)
        inner_grid.setColumnStretch(3, 1)
        self._display_line(inner_grid, 0, 0, tr("step2_dx", "DX:"), "grid_inner_dx")
        self._display_line(inner_grid, 0, 2, tr("step2_dy", "DY:"), "grid_inner_dy")
        self._display_line(inner_grid, 1, 0, tr("step2_lon_west", "西经:"), "grid_inner_lon_west")
        self._display_line(inner_grid, 1, 2, tr("step2_lon_east", "东经:"), "grid_inner_lon_east")
        self._display_line(inner_grid, 2, 0, tr("step2_lat_south", "南纬:"), "grid_inner_lat_south")
        self._display_line(inner_grid, 2, 2, tr("step2_lat_north", "北纬:"), "grid_inner_lat_north")
        inner_layout.addLayout(inner_grid)
        self.inner_grid_widget.hide()
        layout.addWidget(self.inner_grid_widget)

        type_grid = QGridLayout()
        type_grid.setContentsMargins(0, 0, 0, 0)
        type_grid.setSpacing(10)
        type_grid.setColumnStretch(1, 1)
        self.grid_type_combo = ComboBox()
        self.grid_type_combo.addItems(
            [tr("step2_grid_type_normal", "普通网格"), tr("step2_grid_type_nested", "嵌套网格")]
        )
        self.grid_type_combo.setStyleSheet(combo_style())
        left_align_combo_text(self.grid_type_combo)
        self.grid_type_combo.currentIndexChanged.connect(self._on_grid_type_changed)
        self.mesh_type_combo = ComboBox()
        self.mesh_type_combo.addItems(
            [
                tr("step2_mesh_type_structured", "矩形网格"),
                tr("step2_mesh_type_smc", "SMC 网格"),
                tr("step2_mesh_type_unstructured", "非结构网格"),
            ]
        )
        self.mesh_type_combo.setStyleSheet(combo_style())
        left_align_combo_text(self.mesh_type_combo)
        self.mesh_type_combo.currentIndexChanged.connect(self._on_mesh_type_changed)
        self.grid_type_label = QLabel(tr("step2_grid_type", "类型："))
        self.mesh_type_label = QLabel(tr("step2_mesh_type", "网格："))
        type_grid.addWidget(self.grid_type_label, 0, 0)
        type_grid.addWidget(self.grid_type_combo, 0, 1)
        type_grid.addWidget(self.mesh_type_label, 1, 0)
        type_grid.addWidget(self.mesh_type_combo, 1, 1)
        self._align_left_control_columns(outer_grid, inner_grid, type_grid)
        layout.addLayout(type_grid)

        # SMC 内联参数（选择 SMC 网格时显示）
        self.smc_params_widget = QWidget()
        smc_layout = QGridLayout(self.smc_params_widget)
        smc_layout.setContentsMargins(0, 0, 0, 0)
        smc_layout.setSpacing(10)
        smc_layout.setColumnStretch(1, 1)
        self._smc_n_levels = self._smc_field(smc_layout, 0, tr("step2_smc_n_levels", "细化层数："), "2", integer=True)
        self._smc_depmin = self._smc_field(smc_layout, 1, tr("step2_smc_depmin", "最小水深："), "0.0")
        self._smc_dshalw = self._smc_field(smc_layout, 2, tr("step2_smc_dshalw", "浅水截断："), "-150.0")
        self.smc_params_widget.hide()
        layout.addWidget(self.smc_params_widget)

        # 非结构网格内联参数（选择非结构网格时显示）
        self.unst_params_widget = QWidget()
        unst_layout = QGridLayout(self.unst_params_widget)
        unst_layout.setContentsMargins(0, 0, 0, 0)
        unst_layout.setSpacing(10)
        unst_layout.setColumnStretch(1, 1)
        self._unst_hmax = self._smc_field(unst_layout, 0, tr("step2_unst_spacing_hmax", "深水尺度 (km)："), "100.0")
        self._unst_hshr = self._smc_field(unst_layout, 1, tr("step2_unst_spacing_hshr", "近岸尺度 (km)："), "20.0")
        self._unst_dhdx = self._smc_field(unst_layout, 2, tr("step2_unst_spacing_dhdx", "水深梯度："), "0.05")
        self._unst_deep_threshold = self._smc_field(unst_layout, 3, tr("step2_unst_spacing_deep_threshold", "深水阈值 (m)："), "4000")
        self.unst_params_widget.hide()
        layout.addWidget(self.unst_params_widget)

        self.skip_grid = CheckBox(tr("step2_skip_grid", "跳过网格生成（使用工作目录中已有网格）"))
        self.skip_grid.hide()
        layout.addWidget(self.skip_grid)
        self.load_bounds_button = create_button(tr("step2_load_from_nc", "从 wind.nc 读取范围"), load_bounds)
        self.setup_outer_button = create_button(tr("step2_setup_outer_grid", "设置外网格"), setup_outer_grid)
        self.setup_outer_button.hide()
        self.setup_inner_button = create_button(tr("step2_setup_inner_grid", "设置内网格"), setup_inner_grid)
        self.setup_inner_button.hide()
        self.map_button = create_button(tr("step2_view_map", "查看地图"), view_map)
        self.grid_button = create_button(tr("step2_create_grid", "生成网格"), generate_grid)
        self.visualize_button = create_button(tr("step2_visualize_grid", "网格可视化"), visualize_grid)
        for button in (
            self.load_bounds_button,
            self.setup_outer_button,
            self.setup_inner_button,
            self.map_button,
            self.grid_button,
            self.visualize_button,
        ):
            layout.addWidget(button)
        self.action_buttons = [
            self.load_bounds_button,
            self.setup_outer_button,
            self.setup_inner_button,
            self.map_button,
            self.grid_button,
            self.visualize_button,
        ]
        group.viewLayout.setContentsMargins(11, 10, 11, 12)
        group.viewLayout.addLayout(layout)
        self.widget = group

    @property
    def is_nested(self) -> bool:
        return self.grid_type_combo.currentIndex() == 1

    def render(self, grid: GridConfig) -> None:
        self.set_value("grid_dx", f"{grid.outer.dx:.2f}")
        self.set_value("grid_dy", f"{grid.outer.dy:.2f}")
        self.set_value("grid_lon_west", f"{grid.outer.lon[0]:.4f}")
        self.set_value("grid_lon_east", f"{grid.outer.lon[1]:.4f}")
        self.set_value("grid_lat_south", f"{grid.outer.lat[0]:.4f}")
        self.set_value("grid_lat_north", f"{grid.outer.lat[1]:.4f}")
        self.grid_type_combo.setCurrentIndex(1 if grid.grid_type == "nested" else 0)
        self.mesh_type_combo.setCurrentIndex({"structured": 0, "smc": 1, "unstructured": 2}.get(grid.mesh_type, 0))
        if grid.smc is not None:
            if grid.smc.n_levels is not None:
                self._smc_n_levels.setText(str(grid.smc.n_levels))
            if grid.smc.depmin is not None:
                self._smc_depmin.setText(str(grid.smc.depmin))
            if grid.smc.dshalw is not None:
                self._smc_dshalw.setText(str(grid.smc.dshalw))
        if grid.unstructured is not None:
            if grid.unstructured.hmax is not None:
                self._unst_hmax.setText(str(grid.unstructured.hmax))
            if grid.unstructured.hshr is not None:
                self._unst_hshr.setText(str(grid.unstructured.hshr))
            if grid.unstructured.dhdx is not None:
                self._unst_dhdx.setText(str(grid.unstructured.dhdx))
            if grid.unstructured.deep_ocean_threshold_m is not None:
                self._unst_deep_threshold.setText(str(grid.unstructured.deep_ocean_threshold_m))
        if grid.inner is not None:
            self.set_value("grid_inner_dx", f"{grid.inner.dx:.2f}")
            self.set_value("grid_inner_dy", f"{grid.inner.dy:.2f}")
            self.set_value("grid_inner_lon_west", f"{grid.inner.lon[0]:.4f}")
            self.set_value("grid_inner_lon_east", f"{grid.inner.lon[1]:.4f}")
            self.set_value("grid_inner_lat_south", f"{grid.inner.lat[0]:.4f}")
            self.set_value("grid_inner_lat_north", f"{grid.inner.lat[1]:.4f}")

    def overrides(self) -> dict[str, object]:
        inner = None
        if self.is_nested and self.fields["grid_inner_dx"].text().strip():
            inner = self._region_overrides("grid_inner")
        mesh_type = ["structured", "smc", "unstructured"][self.mesh_type_combo.currentIndex()]
        result: dict[str, object] = {
            "mesh_type": mesh_type,
            "grid_type": "nested" if self.is_nested else "normal",
            "outer": self._region_overrides("grid"),
            "inner": inner,
        }
        if mesh_type == "smc":
            result["smc"] = {
                "n_levels": self._smc_n_levels.text().strip(),
                "depmin": self._smc_depmin.text().strip(),
                "dshalw": self._smc_dshalw.text().strip(),
            }
        if mesh_type == "unstructured":
            result["unstructured"] = {
                "hmax": self._unst_hmax.text().strip(),
                "hshr": self._unst_hshr.text().strip(),
                "dhdx": self._unst_dhdx.text().strip(),
                "deep_ocean_threshold_m": self._unst_deep_threshold.text().strip(),
            }
        return result

    def input_region(self, prefix: str) -> GridRegion:
        try:
            return GridRegion(
                dx=float(self.fields[f"{prefix}_dx"].text().strip()),
                dy=float(self.fields[f"{prefix}_dy"].text().strip()),
                lon=[
                    float(self.fields[f"{prefix}_lon_west"].text().strip()),
                    float(self.fields[f"{prefix}_lon_east"].text().strip()),
                ],
                lat=[
                    float(self.fields[f"{prefix}_lat_south"].text().strip()),
                    float(self.fields[f"{prefix}_lat_north"].text().strip()),
                ],
            )
        except ValueError as exc:
            raise ValueError(tr("step2_lon_lat_must_be_number_general", "网格经纬度与步长必须是数字")) from exc

    def set_bounds(self, prefix: str, lon: tuple[float, float], lat: tuple[float, float]) -> None:
        self.set_value(f"{prefix}_lon_west", f"{lon[0]:.4f}")
        self.set_value(f"{prefix}_lon_east", f"{lon[1]:.4f}")
        self.set_value(f"{prefix}_lat_south", f"{lat[0]:.4f}")
        self.set_value(f"{prefix}_lat_north", f"{lat[1]:.4f}")

    def set_region_bounds(self, prefix: str, region: GridRegion) -> None:
        self.set_bounds(prefix, (region.lon[0], region.lon[1]), (region.lat[0], region.lat[1]))

    def set_value(self, key: str, value: object) -> None:
        self.fields[key].setText(str(value))

    def _region_overrides(self, prefix: str) -> dict[str, object]:
        return {
            "dx": self.fields[f"{prefix}_dx"].text().strip(),
            "dy": self.fields[f"{prefix}_dy"].text().strip(),
            "lon": [
                self.fields[f"{prefix}_lon_west"].text().strip(),
                self.fields[f"{prefix}_lon_east"].text().strip(),
            ],
            "lat": [
                self.fields[f"{prefix}_lat_south"].text().strip(),
                self.fields[f"{prefix}_lat_north"].text().strip(),
            ],
        }

    def _display_line(self, grid: QGridLayout, row: int, column: int, label: str, key: str) -> None:
        field = LineEdit()
        field.setStyleSheet(self._input_style())
        if "_lat_" in key:
            field.setValidator(double_validator(-90.0, 90.0))
        elif "_lon_" in key:
            field.setValidator(double_validator(-360.0, 360.0))
        elif key.endswith("_dx") or key.endswith("_dy"):
            field.setValidator(double_validator(0.0, 1.0e6))
        field_label = QLabel(label)
        grid.addWidget(field_label, row, column)
        grid.addWidget(field, row, column + 1)
        self.fields[key] = field
        self.field_labels[key] = field_label

    def _smc_field(self, grid: QGridLayout, row: int, label: str, default: str, *, integer: bool = False) -> LineEdit:
        field = LineEdit()
        field.setStyleSheet(self._input_style())
        field.setText(default)
        if integer:
            field.setValidator(int_validator(1, 10))
        else:
            field.setValidator(double_validator(-1.0e6, 1.0e6))
        grid.addWidget(QLabel(label), row, 0)
        grid.addWidget(field, row, 1)
        return field

    def _align_left_control_columns(self, *grids: QGridLayout) -> None:
        left_labels = [
            self.field_labels["grid_dx"],
            self.field_labels["grid_lon_west"],
            self.field_labels["grid_lat_south"],
            self.field_labels["grid_inner_dx"],
            self.field_labels["grid_inner_lon_west"],
            self.field_labels["grid_inner_lat_south"],
            self.grid_type_label,
            self.mesh_type_label,
        ]
        width = max(label.sizeHint().width() for label in left_labels)
        for label in left_labels:
            label.setFixedWidth(width)
        for grid in grids:
            grid.setColumnMinimumWidth(0, width)

    def _on_grid_type_changed(self) -> None:
        nested = self.is_nested
        self.outer_grid_title.setVisible(nested)
        self.inner_grid_widget.setVisible(nested)
        self.setup_outer_button.setVisible(nested)
        self.setup_inner_button.setVisible(nested)
        if nested:
            self.mesh_type_combo.setCurrentIndex(0)
            self.mesh_type_combo.setEnabled(False)
            self._populate_inner_grid_defaults()
        else:
            self.mesh_type_combo.setEnabled(True)

    def _on_mesh_type_changed(self) -> None:
        idx = self.mesh_type_combo.currentIndex()
        structured = idx == 0
        smc = idx == 1
        unstructured = idx == 2
        self.grid_type_label.setVisible(structured)
        self.grid_type_combo.setVisible(structured)
        # DX/DY 在 SMC 和非结构下隐藏
        for key in ("grid_dx", "grid_dy"):
            self.fields[key].setVisible(structured)
            self.field_labels[key].setVisible(structured)
        # SMC 内联参数
        self.smc_params_widget.setVisible(smc)
        # 非结构内联参数
        self.unst_params_widget.setVisible(unstructured)
        if not structured:
            self.grid_type_combo.setCurrentIndex(0)
            self.inner_grid_widget.hide()

    def _populate_inner_grid_defaults(self) -> None:
        if self.fields["grid_inner_dx"].text().strip():
            return
        try:
            factor = self._nested_factor()
            lon = [float(self.fields["grid_lon_west"].text()), float(self.fields["grid_lon_east"].text())]
            lat = [float(self.fields["grid_lat_south"].text()), float(self.fields["grid_lat_north"].text())]

            def contracted(bounds: list[float]) -> list[float]:
                center = sum(bounds) / 2
                half = abs(bounds[1] - bounds[0]) / (2 * factor)
                return [center - half, center + half]

            inner_lon = contracted(lon)
            inner_lat = contracted(lat)
            self.set_value("grid_inner_dx", self.fields["grid_dx"].text())
            self.set_value("grid_inner_dy", self.fields["grid_dy"].text())
            self.set_value("grid_inner_lon_west", f"{inner_lon[0]:.4f}")
            self.set_value("grid_inner_lon_east", f"{inner_lon[1]:.4f}")
            self.set_value("grid_inner_lat_south", f"{inner_lat[0]:.4f}")
            self.set_value("grid_inner_lat_north", f"{inner_lat[1]:.4f}")
        except (TypeError, ValueError, ZeroDivisionError):
            return
