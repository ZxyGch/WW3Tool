"""Step 1 panel for grid parameters and grid-related actions."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import CheckBox, ComboBox, LineEdit, PrimaryPushButton

from ..components.combo_box import left_align_combo_text
from ..components.globe_picker_dialog import GlobePickerDialog
from ..components.bounds_map_preview import BoundsMapPreview
from ..components.header_card import create_header_card
from ..components.validators import double_validator, int_validator
from workflows.domain.config_models import GridConfig, GridRegion
from workflows.domain.grid_bounds import GLOBAL_LAT, GLOBAL_LON, is_near_global_bounds
from workflows.domain.grid_spacing_recommendation import recommend_grid_params
from workflows.support.translations import tr


def _contract(bounds: list[float], factor: float) -> list[float]:
    """把 [min,max] 区间按 factor 向中心收缩（factor>1 收紧）。

    [EN] Shrink the [min,max] range toward its center by ``factor`` (``factor>1``
    tightens the range).
    """
    center = (bounds[0] + bounds[1]) / 2
    half = abs(bounds[1] - bounds[0]) / (2 * factor)
    return [center - half, center + half]


class _LevelCard(QWidget):
    """一层（level1…levelN）嵌套网格的输入卡片：dx/dy、经纬度边界、
    可选积分步/输出步。增删由面板底部的统一按钮控制。

    [EN] Input card for one nested level (level1…levelN): dx/dy, lon/lat bounds,
    and optional integration/output steps. Adding/removing levels is controlled by
    the unified buttons at the bottom of the panel.
    """

    def __init__(
        self,
        *,
        input_style: Callable[[], str],
        on_changed: Callable[[], None],
    ) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._input_style = input_style
        self.fields: dict[str, LineEdit] = {}

        root = QVBoxLayout(self)
        # 左右不内缩，使卡片字段与上方 level0 网格参数左右对齐；仅留上下间距
        # [EN] No left/right margins so card fields align with the level0 grid fields
        # above; only top/bottom spacing is kept.
        root.setContentsMargins(0, 6, 0, 6)
        root.setSpacing(8)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-weight: 600;")
        root.addWidget(self.title_label)

        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        self._line(grid, 0, 0, tr("step1_dx", "DX:"), "dx", on_changed)
        self._line(grid, 0, 2, tr("step1_dy", "DY:"), "dy", on_changed)
        self._range_pair(grid, 1, tr("step1_lat_south", "纬度："), "lat_south", "lat_north", on_changed)
        self._range_pair(grid, 2, tr("step1_lon_west", "经度："), "lon_west", "lon_east", on_changed)
        root.addLayout(grid)

    def _line(self, grid: QGridLayout, row: int, col: int, label: str, key: str,
              on_changed: Callable[[], None]) -> None:
        field = LineEdit()
        field.setStyleSheet(self._input_style())
        if "lat_" in key:
            field.setValidator(double_validator(-90.0, 90.0))
        elif "lon_" in key:
            field.setValidator(double_validator(-360.0, 360.0))
        elif key in ("dx", "dy"):
            field.setValidator(double_validator(0.0, 1.0e6))
        field.textChanged.connect(on_changed)
        grid.addWidget(QLabel(label), row, col)
        grid.addWidget(field, row, col + 1)
        self.fields[key] = field

    def _range_pair(
        self,
        grid: QGridLayout,
        row: int,
        label: str,
        start_key: str,
        end_key: str,
        on_changed: Callable[[], None],
    ) -> None:
        grid.addWidget(QLabel(label), row, 0)
        start = self._range_field(start_key, on_changed)
        end = self._range_field(end_key, on_changed)
        grid.addWidget(start, row, 1)
        grid.addWidget(QLabel(tr("range_separator", "至")), row, 2)
        grid.addWidget(end, row, 3)
        self.fields[start_key] = start
        self.fields[end_key] = end

    def _range_field(self, key: str, on_changed: Callable[[], None]) -> LineEdit:
        field = LineEdit()
        field.setStyleSheet(self._input_style())
        if "lat_" in key:
            field.setValidator(double_validator(-90.0, 90.0))
        elif "lon_" in key:
            field.setValidator(double_validator(-360.0, 360.0))
        field.textChanged.connect(on_changed)
        return field

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)

    def to_override(self) -> dict[str, object]:
        data: dict[str, object] = {
            "dx": self.fields["dx"].text().strip(),
            "dy": self.fields["dy"].text().strip(),
            "lon": [self.fields["lon_west"].text().strip(), self.fields["lon_east"].text().strip()],
            "lat": [self.fields["lat_south"].text().strip(), self.fields["lat_north"].text().strip()],
        }
        return data

    def set_from_region(self, region: GridRegion) -> None:
        self.fields["dx"].setText(f"{region.dx:g}" if region.dx is not None else "")
        self.fields["dy"].setText(f"{region.dy:g}" if region.dy is not None else "")
        if region.lon:
            self.fields["lon_west"].setText(f"{region.lon[0]:.4f}")
            self.fields["lon_east"].setText(f"{region.lon[1]:.4f}")
        if region.lat:
            self.fields["lat_south"].setText(f"{region.lat[0]:.4f}")
            self.fields["lat_north"].setText(f"{region.lat[1]:.4f}")

    def region_floats(self):
        """返回 (dx, dy, lon, lat) 浮点；任一字段无法解析时返回 None（供校验/套娃用）。

        [EN] Return (dx, dy, lon, lat) as floats; return ``None`` if any field cannot
        be parsed (used for validation / nesting).
        """
        try:
            return (
                float(self.fields["dx"].text()),
                float(self.fields["dy"].text()),
                [float(self.fields["lon_west"].text()), float(self.fields["lon_east"].text())],
                [float(self.fields["lat_south"].text()), float(self.fields["lat_north"].text())],
            )
        except ValueError:
            return None


class GridStepPanel:
    """Own grid controls, presentation rules and form value conversion.

    嵌套模式下：``grid_*`` 一组字段代表 level0（最粗 / 主域），其余 level1…levelN
    用可增删的 ``_LevelCard`` 卡片表示。``overrides()`` 统一回传 ``levels`` 列表。
    """

    def __init__(
        self,
        parent: QWidget,
        *,
        create_button: Callable[[str, Callable[..., object]], PrimaryPushButton],
        input_style: Callable[[], str],
        combo_style: Callable[[], str],
        section_title: Callable[[str], QWidget],
        nested_factor: Callable[[], float],
        generate_grid: Callable[[], None],
        visualize_grid: Callable[[], None],
        recommend_params: Callable[[], None],
    ) -> None:
        self._input_style = input_style
        self._nested_factor = nested_factor
        self.fields: dict[str, LineEdit] = {}
        self.field_labels: dict[str, QLabel] = {}
        self.level_cards: list[_LevelCard] = []
        group, layout = create_header_card(parent, tr("step1_title", "第一步：生成网格"))

        type_grid = QGridLayout()
        type_grid.setContentsMargins(0, 0, 0, 0)
        type_grid.setSpacing(10)
        type_grid.setColumnStretch(1, 1)
        self.grid_type_combo = ComboBox()
        self.grid_type_combo.addItems(
            [tr("step1_grid_type_normal", "普通网格"), tr("step1_grid_type_nested", "嵌套网格")]
        )
        self.grid_type_combo.setStyleSheet(combo_style())
        left_align_combo_text(self.grid_type_combo)
        self.grid_type_combo.currentIndexChanged.connect(self._on_grid_type_changed)
        self.mesh_type_combo = ComboBox()
        self.mesh_type_combo.addItems(
            [
                tr("step1_mesh_type_structured", "矩形网格"),
                tr("step1_mesh_type_smc", "SMC 网格"),
                tr("step1_mesh_type_unstructured", "非结构网格"),
            ]
        )
        self.mesh_type_combo.setStyleSheet(combo_style())
        left_align_combo_text(self.mesh_type_combo)
        self.mesh_type_combo.currentIndexChanged.connect(self._on_mesh_type_changed)
        self.grid_type_label = QLabel(tr("step1_grid_type", "类型："))
        self.mesh_type_label = QLabel(tr("step1_mesh_type", "网格："))
        type_grid.addWidget(self.grid_type_label, 0, 0)
        type_grid.addWidget(self.grid_type_combo, 0, 1)
        type_grid.addWidget(self.mesh_type_label, 1, 0)
        type_grid.addWidget(self.mesh_type_combo, 1, 1)

        # level0（最粗 / 主域）参数块
        # [EN] Level0 (coarsest / master domain) parameter block.
        self.outer_grid_title = section_title(tr("step1_level0_params", "level0（最粗）网格参数"))
        self.outer_grid_title.hide()
        layout.addWidget(self.outer_grid_title)
        self.bounds_preview = BoundsMapPreview(parent)
        layout.addWidget(self.bounds_preview)
        outer_grid = QGridLayout()
        outer_grid.setSpacing(10)
        outer_grid.setColumnStretch(1, 1)
        outer_grid.setColumnStretch(3, 1)
        self._display_line(outer_grid, 0, 0, tr("step1_dx", "DX:"), "grid_dx")
        self._display_line(outer_grid, 0, 2, tr("step1_dy", "DY:"), "grid_dy")
        self._display_pair(outer_grid, 1, tr("step1_lat_south", "纬度："), "grid_lat_south", "grid_lat_north")
        self._display_pair(outer_grid, 2, tr("step1_lon_west", "经度："), "grid_lon_west", "grid_lon_east")
        layout.addLayout(outer_grid)
        self.bounds_preview.bind_fields(
            west=self.fields["grid_lon_west"],
            east=self.fields["grid_lon_east"],
            south=self.fields["grid_lat_south"],
            north=self.fields["grid_lat_north"],
        )

        # level1…levelN：可增删层卡片列表
        # [EN] level1…levelN: list of addable/removable level cards.
        self.levels_widget = QWidget()
        self.levels_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        levels_layout = QVBoxLayout(self.levels_widget)
        levels_layout.setContentsMargins(0, 0, 0, 0)
        levels_layout.setSpacing(8)
        levels_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        levels_layout.addWidget(section_title(tr("step1_nested_levels", "其余嵌套层（细 → 最细）")))
        self._cards_container = QWidget()
        self._cards_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(8)
        self._cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        levels_layout.addWidget(self._cards_container)
        self.levels_hint = QLabel("")
        self.levels_hint.setWordWrap(True)
        self.levels_hint.setStyleSheet("color: #c0392b;")
        self.levels_hint.hide()
        levels_layout.addWidget(self.levels_hint)
        self.levels_widget.hide()
        layout.addWidget(self.levels_widget)

        self._align_left_control_columns(outer_grid, type_grid)
        layout.addLayout(type_grid)

        # SMC 内联参数（选择 SMC 网格时显示）
        # [EN] SMC inline parameters (shown when SMC mesh is selected).
        self.smc_params_widget = QWidget()
        smc_layout = QGridLayout(self.smc_params_widget)
        smc_layout.setContentsMargins(0, 0, 0, 0)
        smc_layout.setSpacing(10)
        smc_layout.setColumnStretch(1, 1)
        self._smc_n_levels = self._smc_field(smc_layout, 0, tr("step1_smc_n_levels", "细化层数："), "2", integer=True)
        self.smc_params_widget.hide()
        layout.addWidget(self.smc_params_widget)

        # 非结构网格内联参数（选择非结构网格时显示）
        # [EN] Unstructured-mesh inline parameters (shown when unstructured mesh is selected).
        self.unst_params_widget = QWidget()
        unst_layout = QGridLayout(self.unst_params_widget)
        unst_layout.setContentsMargins(0, 0, 0, 0)
        unst_layout.setSpacing(10)
        unst_layout.setColumnStretch(1, 1)
        self._unst_hmax = self._smc_field(unst_layout, 0, tr("step1_unst_spacing_hmax", "深水尺度 (km)："), "100.0")
        self._unst_hmin = self._smc_field(unst_layout, 1, tr("step1_unst_spacing_hmin", "最小尺度 (km)："), "2.0")
        self._unst_hshr = self._smc_field(unst_layout, 2, tr("step1_unst_spacing_hshr", "近岸尺度 (km)："), "20.0")
        self._unst_dhdx = self._smc_field(unst_layout, 3, tr("step1_unst_spacing_dhdx", "水深梯度："), "0.05")
        self._unst_deep_threshold = self._smc_field(unst_layout, 4, tr("step1_unst_spacing_deep_threshold", "深水阈值 (m)："), "4000")
        self.unst_params_widget.hide()
        layout.addWidget(self.unst_params_widget)

        self.skip_grid = CheckBox(tr("step1_skip_grid", "跳过网格生成（使用工作目录中已有网格）"))
        self.skip_grid.hide()
        layout.addWidget(self.skip_grid)
        self.add_level_button = create_button(tr("step1_add_level", "添加一层"), self._add_level)
        self.add_level_button.hide()
        self.delete_level_button = create_button(tr("step1_delete_level", "删除末层"), self._delete_last_level)
        self.delete_level_button.hide()
        self.telescope_button = create_button(tr("step1_auto_telescope", "按收缩系数自动套娃"), self._auto_telescope)
        self.telescope_button.hide()
        self.recommend_button = create_button(tr("step1_recommend_params", "推荐参数"), recommend_params)
        self.grid_button = create_button(tr("step1_create_grid", "生成网格"), generate_grid)
        self.visualize_button = create_button(tr("step1_visualize_grid", "网格可视化"), visualize_grid)
        self.globe_button = create_button(tr("step1_globe_picker", "选择地图区域"), self._open_globe_picker)
        # 添加/删除层并排一行（嵌套模式）
        # [EN] Add/delete level buttons in one row (nested mode).
        level_btn_row = QHBoxLayout()
        level_btn_row.setContentsMargins(0, 0, 0, 0)
        level_btn_row.setSpacing(10)
        level_btn_row.addWidget(self.add_level_button)
        level_btn_row.addWidget(self.delete_level_button)
        layout.addLayout(level_btn_row)
        layout.addWidget(self.telescope_button)
        for button in (
            self.recommend_button,
            self.grid_button,
            self.visualize_button,
            self.globe_button,
        ):
            layout.addWidget(button)
        self.action_buttons = [
            self.add_level_button,
            self.delete_level_button,
            self.telescope_button,
            self.recommend_button,
            self.grid_button,
            self.visualize_button,
            self.globe_button,
        ]
        group.viewLayout.setContentsMargins(11, 10, 11, 12)
        group.viewLayout.addLayout(layout)
        self.widget = group

    @property
    def is_nested(self) -> bool:
        if self.mesh_type_combo.currentIndex() != 0:
            return False
        return self.grid_type_combo.currentIndex() == 1

    def render(self, grid: GridConfig) -> None:
        # 阻止 combo 信号级联，避免 handler 在 render 过程中重置值和可见性
        # [EN] Block combo signal cascades so handlers don't reset values/visibility during render.
        self.grid_type_combo.blockSignals(True)
        self.mesh_type_combo.blockSignals(True)
        try:
            # level0 / 主网格 ← grid.outer（= nested_levels[0]）
            # [EN] level0 / master grid ← grid.outer (= nested_levels[0]).
            self.set_value("grid_dx", f"{grid.outer.dx:g}")
            self.set_value("grid_dy", f"{grid.outer.dy:g}")
            self.set_value("grid_lon_west", f"{grid.outer.lon[0]:.4f}")
            self.set_value("grid_lon_east", f"{grid.outer.lon[1]:.4f}")
            self.set_value("grid_lat_south", f"{grid.outer.lat[0]:.4f}")
            self.set_value("grid_lat_north", f"{grid.outer.lat[1]:.4f}")
            self.grid_type_combo.setCurrentIndex(1 if grid.grid_type == "nested" else 0)
            self.mesh_type_combo.setCurrentIndex({"structured": 0, "smc": 1, "unstructured": 2}.get(grid.mesh_type, 0))
            if grid.smc is not None:
                if grid.smc.n_levels is not None:
                    self._smc_n_levels.setText(str(grid.smc.n_levels))
            if grid.unstructured is not None:
                if grid.unstructured.hmax is not None:
                    self._unst_hmax.setText(str(grid.unstructured.hmax))
                if grid.unstructured.hmin is not None:
                    self._unst_hmin.setText(str(grid.unstructured.hmin))
                if grid.unstructured.hshr is not None:
                    self._unst_hshr.setText(str(grid.unstructured.hshr))
                if grid.unstructured.dhdx is not None:
                    self._unst_dhdx.setText(str(grid.unstructured.dhdx))
                if grid.unstructured.deep_ocean_threshold_m is not None:
                    self._unst_deep_threshold.setText(str(grid.unstructured.deep_ocean_threshold_m))
            # 重建 level1…levelN 卡片
            # [EN] Rebuild level1…levelN cards.
            self._clear_cards()
            for region in (grid.nested_levels or [])[1:]:
                card = self._make_card()
                card.set_from_region(region)
                self.level_cards.append(card)
                self._cards_layout.addWidget(card)
            self._renumber_cards()
        finally:
            self.grid_type_combo.blockSignals(False)
            self.mesh_type_combo.blockSignals(False)
        # 所有值设置完毕后再应用可见性状态
        # [EN] Apply visibility states only after all values have been set.
        self._on_grid_type_changed()
        self._on_mesh_type_changed()
        self._validate_levels()

    def overrides(self) -> dict[str, object]:
        mesh_type = ["structured", "smc", "unstructured"][self.mesh_type_combo.currentIndex()]
        if self.is_nested:
            level0 = self._region_overrides("grid")
            levels = [level0] + [card.to_override() for card in self.level_cards]
        else:
            levels = [self._region_overrides("grid")]
        result: dict[str, object] = {
            "mesh_type": mesh_type,
            "grid_type": "nested" if self.is_nested else "normal",
            "levels": levels,
        }
        if mesh_type == "smc":
            result["smc"] = {
                "n_levels": self._smc_n_levels.text().strip(),
            }
        if mesh_type == "unstructured":
            result["unstructured"] = {
                "hmax": self._unst_hmax.text().strip(),
                "hmin": self._unst_hmin.text().strip(),
                "hshr": self._unst_hshr.text().strip(),
                "dhdx": self._unst_dhdx.text().strip(),
                "deep_ocean_threshold_m": self._unst_deep_threshold.text().strip(),
            }
        return result

    def apply_recommendations(self) -> tuple[bool, str]:
        """Fill spacing/resolution fields with span-based recommendations for the
        currently selected mesh type. Delegates the (UI-independent) computation to
        ``recommend_grid_params``. Returns (ok, human-readable summary)."""
        try:
            lon = [
                float(self.fields["grid_lon_west"].text().strip()),
                float(self.fields["grid_lon_east"].text().strip()),
            ]
            lat = [
                float(self.fields["grid_lat_south"].text().strip()),
                float(self.fields["grid_lat_north"].text().strip()),
            ]
        except ValueError:
            return False, ""

        mesh_type = ["structured", "smc", "unstructured"][self.mesh_type_combo.currentIndex()]
        rec = recommend_grid_params(mesh_type, lon, lat)
        if rec is None:
            return False, ""

        if mesh_type == "unstructured":
            self._unst_hmax.setText(rec.values["hmax"])
            self._unst_hmin.setText(rec.values["hmin"])
            self._unst_hshr.setText(rec.values["hshr"])
            self._unst_dhdx.setText(rec.values["dhdx"])
            mesh_name = tr("step1_mesh_type_unstructured", "非结构网格")
        elif mesh_type == "smc":
            self._smc_n_levels.setText(rec.values["n_levels"])
            mesh_name = tr("step1_mesh_type_smc", "SMC 网格")
        else:
            self.set_value("grid_dx", rec.values["dx"])
            self.set_value("grid_dy", rec.values["dy"])
            mesh_name = tr("step1_mesh_type_structured", "矩形网格")

        summary = tr("step1_recommend_body", "{mesh}（跨度≈{span} km）：{params}").format(
            mesh=mesh_name, span=int(rec.span_km), params=rec.values_text()
        )
        return True, summary

    def cfl_spacing_m(self) -> tuple[float | None, str]:
        """CFL 所需的最小网格尺度（米），按当前网格类型从对应输入框取值。

        结构化/SMC 用 level0（grid_*）的基准格距 DX/DY 与纬度；非结构化用近岸最小尺度
        ``hmin``。嵌套模式下若有更细层，取最细层的 dx 作为限制尺度。
        [EN] Min grid spacing (m) for CFL, by mesh type."""
        from workflows.domain.timestep_recommendation import cfl_spacing_meters

        idx = self.mesh_type_combo.currentIndex()  # 0 结构化, 1 SMC, 2 非结构化
        # [EN] 0 = structured, 1 = SMC, 2 = unstructured.
        if idx == 2:  # unstructured
            try:
                hmin = float(self._unst_hmin.text().strip())
            except ValueError:
                return None, "need_hmin"
            return cfl_spacing_meters("unstructured", hmin_km=hmin)
        # 结构化 / SMC：度制基准格距 + 纬度
        # [EN] Structured / SMC: degree-based base spacing + latitude.
        try:
            dx = float(self.fields["grid_dx"].text().strip())
            dy = float(self.fields["grid_dy"].text().strip())
            lat_s = float(self.fields["grid_lat_south"].text().strip())
            lat_n = float(self.fields["grid_lat_north"].text().strip())
        except ValueError:
            return None, "need_grid"
        # 嵌套时用最细层的 dx/dy（CFL 由最细网格决定）
        # [EN] For nested grids use the finest-level dx/dy (CFL is governed by the finest grid).
        if self.is_nested and self.level_cards:
            finest = self.level_cards[-1].region_floats()
            if finest is not None:
                dx, dy = finest[0], finest[1]
        return cfl_spacing_meters(
            "smc" if idx == 1 else "structured",
            dx_deg=dx,
            dy_deg=dy,
            lat_deg=(lat_s + lat_n) / 2.0,
        )

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
            raise ValueError(tr("step1_lon_lat_must_be_number_general", "网格经纬度与步长必须是数字")) from exc

    def set_bounds(self, prefix: str, lon: tuple[float, float], lat: tuple[float, float]) -> None:
        self.set_value(f"{prefix}_lon_west", f"{lon[0]:.4f}")
        self.set_value(f"{prefix}_lon_east", f"{lon[1]:.4f}")
        self.set_value(f"{prefix}_lat_south", f"{lat[0]:.4f}")
        self.set_value(f"{prefix}_lat_north", f"{lat[1]:.4f}")

    def _open_globe_picker(self) -> None:
        """打开 3D 地球选择器，用户选取矩形范围后自动填入经纬度。"""
        dialog = GlobePickerDialog(self.widget.window())
        if dialog.exec() != GlobePickerDialog.DialogCode.Accepted:
            return
        bounds = dialog.get_bounds()
        if bounds is None:
            return
        west, east, south, north = bounds
        self.set_bounds("grid", (west, east), (south, north))
        from qfluentwidgets import InfoBar
        InfoBar.success(
            title=tr("step1_globe_picker", "选择地图区域"),
            content=f"已选择区域：经度 {west:.2f} ~ {east:.2f}°，纬度 {south:.2f} ~ {north:.2f}°",
            duration=4000,
            parent=self.widget.window(),
        )

    def outer_lon_lat(self) -> tuple[list[float], list[float]] | None:
        """Return level0 lon/lat as float lists, or None when invalid."""
        base = self._grid_region_floats()
        if base is None:
            return None
        _, _, lon, lat = base
        return lon, lat

    def needs_global_alignment_prompt(self) -> bool:
        """True when level0 bounds are very close to, but not exactly, global."""
        bounds = self.outer_lon_lat()
        if bounds is None:
            return False
        lon, lat = bounds
        return is_near_global_bounds(lon, lat)

    def apply_global_bounds(self, *, outer_only: bool = True) -> None:
        """Snap level0 (and optionally all nested levels) to the global domain."""
        self.set_bounds("grid", GLOBAL_LON, GLOBAL_LAT)
        if outer_only:
            return
        for card in self.level_cards:
            rf = card.region_floats()
            if rf is None:
                continue
            dx, dy, _, _ = rf
            card.set_from_region(
                GridRegion(dx=dx, dy=dy, lon=list(GLOBAL_LON), lat=list(GLOBAL_LAT))
            )

    def set_region_bounds(self, prefix: str, region: GridRegion) -> None:
        self.set_bounds(prefix, (region.lon[0], region.lon[1]), (region.lat[0], region.lat[1]))

    def set_value(self, key: str, value: object) -> None:
        self.fields[key].setText(str(value))

    # ── 层卡片管理 ──────────────────────────────────────────────
    # [EN] Level-card management.

    def _make_card(self) -> _LevelCard:
        return _LevelCard(
            input_style=self._input_style,
            on_changed=self._validate_levels,
        )

    def _add_level(self) -> None:
        card = self._make_card()
        base = self._last_level_floats()
        if base is not None:
            dx, dy, lon, lat = base
            factor = self._safe_factor()
            card.set_from_region(GridRegion(
                dx=dx / 2.0, dy=dy / 2.0,
                lon=_contract(lon, factor), lat=_contract(lat, factor),
            ))
        self.level_cards.append(card)
        self._cards_layout.addWidget(card)
        self._renumber_cards()
        self._validate_levels()

    def _delete_last_level(self) -> None:
        # 删最后一层；至少保留 level0 + 1 层（即 ≥1 张卡），不允许删光
        # [EN] Delete the last level; keep at least level0 + 1 level (i.e. ≥1 card).
        if len(self.level_cards) <= 1:
            return
        card = self.level_cards.pop()
        self._cards_layout.removeWidget(card)
        card.deleteLater()
        self._renumber_cards()
        self._validate_levels()

    def _clear_cards(self) -> None:
        for card in self.level_cards:
            self._cards_layout.removeWidget(card)
            card.deleteLater()
        self.level_cards = []

    def _renumber_cards(self) -> None:
        n_cards = len(self.level_cards)
        for i, card in enumerate(self.level_cards):
            idx = i + 1  # level0 是主域块，卡片从 level1 起
            # [EN] level0 is the master-domain block; cards start from level1.
            if i == n_cards - 1:
                card.set_title(tr("step1_level_finest", "level{i}（最细）").format(i=idx))
            else:
                card.set_title(tr("step1_level_n", "level{i}").format(i=idx))
        # 仅剩 1 层时禁止删除（保证嵌套至少 2 层）
        # [EN] Disable delete when only one level remains (nested needs at least 2 levels).
        self.delete_level_button.setEnabled(n_cards > 1)

    def _last_level_floats(self):
        if self.level_cards:
            return self.level_cards[-1].region_floats()
        return self._grid_region_floats()

    def _grid_region_floats(self):
        try:
            return (
                float(self.fields["grid_dx"].text()),
                float(self.fields["grid_dy"].text()),
                [float(self.fields["grid_lon_west"].text()), float(self.fields["grid_lon_east"].text())],
                [float(self.fields["grid_lat_south"].text()), float(self.fields["grid_lat_north"].text())],
            )
        except ValueError:
            return None

    def _safe_factor(self) -> float:
        try:
            factor = self._nested_factor()
            return factor if factor and factor > 0 else 1.3
        except Exception:
            return 1.3

    def _auto_telescope(self) -> None:
        """从 level0（主域）起，按收缩系数逐层往里算范围、dx 逐层减半，批量填好各层。

        [EN] Starting from level0 (master domain), shrink the range by the contraction
        factor and halve dx for each successive level, filling all levels in batch.
        """
        base = self._grid_region_floats()
        if base is None:
            return
        _, _, cur_lon, cur_lat = base
        cur_dx, cur_dy = base[0], base[1]
        factor = self._safe_factor()
        for card in self.level_cards:
            cur_lon = _contract(cur_lon, factor)
            cur_lat = _contract(cur_lat, factor)
            cur_dx /= 2.0
            cur_dy /= 2.0
            card.set_from_region(GridRegion(dx=cur_dx, dy=cur_dy, lon=cur_lon, lat=cur_lat))
        self._validate_levels()

    def _validate_levels(self) -> None:
        """实时校验：逐层 dx 递减 + 套娃 + 层数 ≤ 99；违例在卡片下方红字提示。

        [EN] Real-time validation: each finer level must have smaller dx, each level
        must be nested inside the previous one, and total levels ≤ 99. Violations are
        shown in red text below the cards.
        """
        if not self.is_nested:
            self.levels_hint.hide()
            return
        regions = []
        base = self._grid_region_floats()
        if base is not None:
            regions.append(("level0", base))
        for i, card in enumerate(self.level_cards):
            rf = card.region_floats()
            if rf is not None:
                regions.append((f"level{i + 1}", rf))
        msgs: list[str] = []
        for k in range(1, len(regions)):
            pn, (pdx, pdy, plon, plat) = regions[k - 1]
            cn, (cdx, cdy, clon, clat) = regions[k]
            if not (cdx < pdx and cdy < pdy):
                msgs.append(tr("step1_level_dx_warn", "{c} 的 dx/dy 必须比 {p} 更细").format(c=cn, p=pn))
            if not (plon[0] <= clon[0] and clon[1] <= plon[1]
                    and plat[0] <= clat[0] and clat[1] <= plat[1]):
                msgs.append(tr("step1_level_contain_warn", "{c} 必须完全落在 {p} 范围内").format(c=cn, p=pn))
        if 1 + len(self.level_cards) > 99:
            msgs.append(tr("step1_level_max_warn", "嵌套层数不能超过 99"))
        hint = "  ".join(msgs)
        self.levels_hint.setText(hint)
        self.levels_hint.setVisible(bool(hint))

    # ── 内部辅助 ────────────────────────────────────────────────
    # [EN] Internal helpers.

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
        elif key.endswith("_compute") or key.endswith("_output"):
            field.setValidator(double_validator(0.0, 1.0e7))
        field_label = QLabel(label)
        grid.addWidget(field_label, row, column)
        grid.addWidget(field, row, column + 1)
        self.fields[key] = field
        self.field_labels[key] = field_label

    def _display_pair(self, grid: QGridLayout, row: int, label: str, start_key: str, end_key: str) -> None:
        field_label = QLabel(label)
        start = self._display_field(start_key)
        end = self._display_field(end_key)
        grid.addWidget(field_label, row, 0)
        grid.addWidget(start, row, 1)
        grid.addWidget(QLabel(tr("range_separator", "至")), row, 2)
        grid.addWidget(end, row, 3)
        self.fields[start_key] = start
        self.fields[end_key] = end
        self.field_labels[start_key] = field_label

    def _display_field(self, key: str) -> LineEdit:
        field = LineEdit()
        field.setStyleSheet(self._input_style())
        if "_lat_" in key:
            field.setValidator(double_validator(-90.0, 90.0))
        elif "_lon_" in key:
            field.setValidator(double_validator(-360.0, 360.0))
        return field

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
            self.grid_type_label,
            self.mesh_type_label,
        ]
        width = max(label.sizeHint().width() for label in left_labels)
        for label in left_labels:
            label.setFixedWidth(width)
        for grid in grids:
            grid.setColumnMinimumWidth(0, width)

    def _nested_ui_visible(self) -> bool:
        """嵌套层编辑区：仅矩形网格 + 嵌套类型时显示。"""
        return self.is_nested and self.mesh_type_combo.currentIndex() == 0

    def _on_grid_type_changed(self) -> None:
        show_nested = self._nested_ui_visible()
        self.outer_grid_title.setVisible(show_nested)
        self.levels_widget.setVisible(show_nested)
        self.telescope_button.setVisible(show_nested)
        self.add_level_button.setVisible(show_nested)
        self.delete_level_button.setVisible(show_nested)
        if self.is_nested and show_nested:
            if not self.level_cards:
                self._add_level()
            self._renumber_cards()
            self._validate_levels()
        elif not self.is_nested:
            self.levels_hint.hide()

    def _on_mesh_type_changed(self) -> None:
        idx = self.mesh_type_combo.currentIndex()
        structured = idx == 0
        smc = idx == 1
        unstructured = idx == 2
        self.grid_type_label.setVisible(structured)
        self.grid_type_combo.setVisible(structured)
        if not structured:
            self.grid_type_combo.blockSignals(True)
            self.grid_type_combo.setCurrentIndex(0)
            self.grid_type_combo.blockSignals(False)
        # DX/DY 在 SMC 和非结构下隐藏
        for key in ("grid_dx", "grid_dy"):
            self.fields[key].setVisible(structured)
            self.field_labels[key].setVisible(structured)
        self.smc_params_widget.setVisible(smc)
        self.unst_params_widget.setVisible(unstructured)
        self._on_grid_type_changed()
