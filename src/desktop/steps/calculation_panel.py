"""Step 3 panel：计算模式选择 + 谱点/航迹点位编辑。

三种模式：区域尺度计算（无需点位）、谱空间逐点计算（谱点表）、航迹模式（航迹表）。
表格样式对齐 src：表头作为第 0 行、隐藏 Qt 列头、无边框、无竖向表头与滚动条、
按内容自适应高度；按钮为「新增 / 修改 / 删除」一行 + 整宽「导入」。
点位通过 :class:`PointEditDialog` 录入/编辑，或从文件导入（:mod:`point_io`），
均按当前网格包围盒（``bounds_provider``）校验。``points()`` / ``track_points()``
供窗口注入运行配置与（在第四步确认参数时）写回 params.yml。

[EN] Step 3 panel: calculation mode selection + spectral/track point editing.

Three modes: region-scale calculation (no points needed), spectral point-by-point
calculation (spectral point table), and track mode (track table). Table styling
follows src: headers as row 0, Qt column headers hidden, no borders, no vertical
headers or scrollbars, height auto-fits content; buttons are "Add / Edit / Delete"
in one row + full-width "Import". Points are entered/edited via
:class:`PointEditDialog` or imported from files (:mod:`point_io`), all validated
against the current grid bounding box (``bounds_provider``). ``points()`` /
``track_points()`` are used by the window to inject run configuration and write
back to params.yml (when confirming parameters in step 4).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import ComboBox

from ..components.combo_box import left_align_combo_text
from ..components.header_card import create_header_card
from ..components.point_edit_dialog import PointEditDialog
from ..components.table_widget import EdgeAlignedTableWidget
from . import point_io
from workflows.domain.config_models import CalcConfig
from workflows.support.translations import tr

_MODES = ["region", "spectral_point", "track"]
_LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
_CENTER = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
# [EN] Table headers for each table type: (title, alignment). Matches src step3_ui.
# 每种表格的表头：(标题, 对齐)。与 src step3_ui 一致。
_HEADER_KEYS = {
    "spectral": [("step3_longitude", "经度", _LEFT), ("step3_latitude", "纬度", _CENTER), ("step3_name", "名称", _CENTER)],
    "track": [
        ("step3_time", "时间", _LEFT),
        ("step3_longitude", "经度", _LEFT),
        ("step3_latitude", "纬度", _LEFT),
        ("step3_name", "名称", _LEFT),
    ],
}
_IMPORT_KEYS = {
    "spectral": ("step3_import_points", "从 points.list 导入"),
    "track": ("step3_import_track_file", "从 track_i.ww3 读取"),
}


class CalculationStepPanel:
    """Own calculation mode presentation, point tables and form conversion."""

    def __init__(
        self,
        parent: QWidget,
        *,
        create_button: Callable[[str, Callable[..., object]], object],
        combo_style: Callable[[], str],
        input_style: Callable[[], str] | None = None,
        button_style: Callable[[], str] | None = None,
        bounds_provider: Callable[[], dict | None] | None = None,
        notify: Callable[[str], None] | None = None,
    ) -> None:
        self._input_style = input_style or (lambda: "")
        self._button_style = button_style or (lambda: "")
        self._bounds_provider = bounds_provider or (lambda: None)
        self._notify = notify or (lambda _msg: None)
        group, layout = create_header_card(parent, tr("step3_title", "第三步：计算模式"))

        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        self.mode_combo = ComboBox()
        self.mode_combo.addItems(
            [
                tr("step3_region_scale", "区域尺度计算"),
                tr("step3_spectral_point", "谱空间逐点计算"),
                tr("step3_track_mode", "航迹模式"),
            ]
        )
        self.mode_combo.setStyleSheet(combo_style())
        left_align_combo_text(self.mode_combo)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        grid.addWidget(QLabel(tr("step3_calc_mode", "计算模式：")), 0, 0)
        grid.addWidget(self.mode_combo, 0, 1)
        layout.addLayout(grid)

        self.spectral_widget, self.spectral_table = self._build_points_block(create_button, "spectral")
        layout.addWidget(self.spectral_widget)
        self.track_widget, self.track_table = self._build_points_block(create_button, "track")
        layout.addWidget(self.track_widget)

        self.spectral_widget.hide()
        self.track_widget.hide()
        group.viewLayout.setContentsMargins(11, 10, 11, 12)
        group.viewLayout.addLayout(layout)
        self.widget = group

    # ── construction helpers ────────────────────────────────────────────────

    def _build_points_block(
        self, create_button: Callable[[str, Callable[..., object]], object], kind: str
    ) -> tuple[QWidget, EdgeAlignedTableWidget]:
        block = QWidget()
        block.setContentsMargins(0, 0, 0, 0)
        block_layout = QVBoxLayout(block)
        block_layout.setContentsMargins(0, 0, 0, 0)
        block_layout.setSpacing(10)

        headers = self._headers(kind)
        table = EdgeAlignedTableWidget()
        table.setContentsMargins(0, 0, 0, 0)
        table.setColumnCount(len(headers))
        table.horizontalHeader().setVisible(False)
        header = table.horizontalHeader()
        for col in range(len(headers)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setBorderVisible(False)
        table.setWordWrap(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._set_header_row(table, kind)
        block_layout.addWidget(table)
        self._resize_table_to_content(table)

        crud_row = QHBoxLayout()
        crud_row.setSpacing(10)
        crud_row.addWidget(create_button(tr("new", "新增"), lambda: self._add(kind)), 1)
        crud_row.addWidget(create_button(tr("edit", "修改"), lambda: self._edit(kind)), 1)
        crud_row.addWidget(create_button(tr("delete", "删除"), lambda: self._delete(kind)), 1)
        block_layout.addLayout(crud_row)
        block_layout.addWidget(create_button(tr("step3_select_on_map", "在地图上选点"), lambda: self._select_on_map(kind)))
        import_key, import_default = _IMPORT_KEYS[kind]
        block_layout.addWidget(create_button(tr(import_key, import_default), lambda: self._import(kind)))
        return block, table

    def _set_header_row(self, table: EdgeAlignedTableWidget, kind: str) -> None:
        # [EN] Write header cells in row 0 (matching src: hide Qt column headers, use first row as header).
        """在第 0 行写入表头单元格（与 src 一致：隐藏 Qt 列头，用首行作表头）。"""
        if table.rowCount() == 0:
            table.insertRow(0)
        for col, (title, _align) in enumerate(self._headers(kind)):
            item = _centered_item(title)
            item.setData(Qt.ItemDataRole.UserRole, "header")
            table.setItem(0, col, item)

    # ── public API ──────────────────────────────────────────────────────────

    @property
    def mode(self) -> str:
        return _MODES[self.mode_combo.currentIndex()]

    def points(self) -> list[dict]:
        return [
            {"lon": lon, "lat": lat, "name": name}
            for lon, lat, name in self._read_rows(self.spectral_table, numeric=(0, 1))
        ]

    def track_points(self) -> list[dict]:
        return [
            {"datetime": dt, "lon": lon, "lat": lat, "name": name}
            for dt, lon, lat, name in self._read_rows(self.track_table, numeric=(1, 2))
        ]

    def render(self, calc: CalcConfig) -> None:
        self.mode_combo.blockSignals(True)
        try:
            self.mode_combo.setCurrentIndex({"region": 0, "spectral_point": 1, "track": 2}.get(calc.mode, 0))
        finally:
            self.mode_combo.blockSignals(False)
        self._fill_table(self.spectral_table, "spectral", [[p.lon, p.lat, p.name] for p in calc.points])
        self._fill_table(
            self.track_table, "track", [[p.datetime, p.lon, p.lat, p.name] for p in calc.track_points]
        )
        self._on_mode_changed()

    # ── table CRUD ────────────────────────────────────────────────────────────

    def _add(self, kind: str) -> None:
        dialog = PointEditDialog(
            self.widget.window(),
            kind=kind,
            bounds=self._bounds_provider(),
            input_style=self._input_style(),
            default_name=str(self._count(kind)),
        )
        if dialog.exec() and dialog.value is not None:
            if self._is_duplicate(kind, dialog.value):
                self._notify(tr("step3_duplicate_point", "⚠️ 点位重复（名称或坐标已存在），已跳过"))
            else:
                self._append_point(kind, dialog.value)

    def _edit(self, kind: str) -> None:
        row = self._selected_data_row(kind)
        if row is None:
            self._notify(tr("step3_please_select_point", "请先选择要修改的点位"))
            return
        initial = self._row_to_point(kind, row)
        dialog = PointEditDialog(
            self.widget.window(),
            kind=kind,
            initial=initial,
            bounds=self._bounds_provider(),
            input_style=self._input_style(),
        )
        if dialog.exec() and dialog.value is not None:
            if self._is_duplicate(kind, dialog.value, exclude_row=row):
                self._notify(tr("step3_duplicate_point", "⚠️ 点位重复（名称或坐标已存在），已跳过"))
            else:
                self._write_row(kind, row, dialog.value)

    def _select_on_map(self, kind: str) -> None:
        bounds = self._bounds_provider()
        if not bounds:
            self._notify(tr("step3_cannot_read_map_range_generate_grid", "无法读取网格范围，请先在第二步生成网格"))
            return
        try:
            from ..components.map_point_picker_dialog import MapPointPickerDialog
        except ImportError as exc:
            self._notify(tr("step3_map_picker_unavailable", "地图选点不可用（缺少 matplotlib/cartopy）：{error}").format(error=exc))
            return
        existing = self.points() if kind == "spectral" else self.track_points()
        try:
            dialog = MapPointPickerDialog(
                self.widget.window(),
                bounds=bounds,
                existing_points=existing,
                button_style=self._button_style(),
            )
        except ImportError as exc:
            self._notify(tr("step3_map_picker_unavailable", "地图选点不可用（缺少 matplotlib/cartopy）：{error}").format(error=exc))
            return
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._replace_points_from_map(kind, dialog.result_points)

    def _replace_points_from_map(self, kind: str, points: list[dict]) -> None:
        """用地图选点结果覆盖当前点位表（含删除已有/新增）。"""
        table = self._table(kind)
        rows: list[list] = []
        for p in points:
            if kind == "track":
                rows.append([p.get("datetime", ""), p["lon"], p["lat"], p.get("name", "")])
            else:
                rows.append([p["lon"], p["lat"], p.get("name", "")])
        self._fill_table(table, kind, rows)

    def _delete(self, kind: str) -> None:
        row = self._selected_data_row(kind)
        if row is None:
            self._notify(tr("step3_please_select_point_to_delete", "请先选择要删除的点位"))
            return
        table = self._table(kind)
        table.removeRow(row)
        self._resize_table_to_content(table)

    def _import(self, kind: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self.widget,
            tr("step3_select_point_file", "选择点位文件"),
            "",
            tr("file_filter_text_all", "文本文件 (*.txt *.dat *.csv *.list *.ww3);;所有文件 (*)"),
        )
        if not path:
            return
        bounds = self._bounds_provider()
        try:
            if kind == "track":
                imported, warnings = point_io.parse_track_points_file(path, bounds=bounds)
            else:
                imported, warnings = point_io.parse_spectral_points_file(path, bounds=bounds)
        except OSError as exc:
            self._notify(tr("step3_read_file_failed", "读取文件失败：{error}").format(error=exc))
            return
        skipped = 0
        for point in imported:
            if self._is_duplicate(kind, point):
                skipped += 1
            else:
                self._append_point(kind, point)
        for warning in warnings:
            self._notify(f"⚠️ {warning}")
        if skipped:
            self._notify(tr("step3_points_imported_skipped_dup", "已从 {file} 导入 {count} 个点位，跳过 {skipped} 个重复点").format(file=Path(path).name, count=len(imported) - skipped, skipped=skipped))
        else:
            self._notify(tr("step3_points_imported_from_file", "已从 {file} 导入 {count} 个点位").format(file=Path(path).name, count=len(imported)))

    @staticmethod
    def _headers(kind: str) -> list[tuple[str, Qt.AlignmentFlag]]:
        return [(tr(key, default), align) for key, default, align in _HEADER_KEYS[kind]]

    # ── helpers ─────────────────────────────────────────────────────────────

    def _table(self, kind: str) -> EdgeAlignedTableWidget:
        return self.track_table if kind == "track" else self.spectral_table

    def _selected_data_row(self, kind: str) -> int | None:
        # [EN] Currently selected data row (row 0 is header, returns ``None`` for no valid selection).
        """当前选中数据行（第 0 行为表头，返回 ``None`` 表示无有效选择）。"""
        row = self._table(kind).currentRow()
        return row if row >= 1 else None

    def _append_point(self, kind: str, point: dict) -> None:
        table = self._table(kind)
        row = table.rowCount()
        table.insertRow(row)
        self._write_row(kind, row, point)
        self._resize_table_to_content(table)

    def _is_duplicate(self, kind: str, point: dict, *, exclude_row: int | None = None) -> bool:
        # [EN] Check if a point with the same coordinates or name already exists.
        """检查是否存在相同坐标或名称的点位，可选排除某行（用于编辑场景）。"""
        table = self._table(kind)
        new_lon = point.get("lon")
        new_lat = point.get("lat")
        new_name = str(point.get("name", "")).strip()
        for row in range(1, table.rowCount()):
            if exclude_row is not None and row == exclude_row:
                continue
            try:
                lon_item = table.item(row, 0 if kind == "spectral" else 1)
                lat_item = table.item(row, 1 if kind == "spectral" else 2)
                name_item = table.item(row, 2 if kind == "spectral" else 3)
                lon = float(lon_item.text()) if lon_item else None
                lat = float(lat_item.text()) if lat_item else None
                name = name_item.text().strip() if name_item else ""
            except (ValueError, TypeError):
                continue
            # [EN] Match by coordinates or by name.
            # 按坐标或名称匹配
            if new_lon is not None and new_lat is not None and lon == new_lon and lat == new_lat:
                return True
            if new_name and name and name == new_name:
                return True
        return False

    def _count(self, kind: str) -> int:
        return max(0, self._table(kind).rowCount() - 1)

    def _resize_table_to_content(self, table: EdgeAlignedTableWidget) -> None:
        # [EN] Fix table height to total row height so it fully expands with no scrollbar.
        """将表格高度固定为所有行的总高，使其完全展开、不出现滚动条。"""
        table.expand_to_contents()

    def _write_row(self, kind: str, row: int, point: dict) -> None:
        if kind == "track":
            values = [point.get("datetime", ""), _fmt(point["lon"]), _fmt(point["lat"]), point.get("name", "")]
        else:
            values = [_fmt(point["lon"]), _fmt(point["lat"]), point.get("name", "")]
        table = self._table(kind)
        for col, value in enumerate(values):
            table.setItem(row, col, _centered_item(str(value)))

    def _row_to_point(self, kind: str, row: int) -> dict:
        table = self._table(kind)

        def cell(col: int) -> str:
            item = table.item(row, col)
            return item.text() if item is not None else ""

        if kind == "track":
            return {
                "datetime": cell(0),
                "lon": _to_float(cell(1)),
                "lat": _to_float(cell(2)),
                "name": cell(3),
            }
        return {"lon": _to_float(cell(0)), "lat": _to_float(cell(1)), "name": cell(2)}

    def _read_rows(self, table: EdgeAlignedTableWidget, *, numeric: tuple[int, ...]) -> list[list]:
        rows: list[list] = []
        for row in range(1, table.rowCount()):  # [EN] Row 0 is the header
            # 第 0 行是表头
            cells: list = []
            ok = True
            for col in range(table.columnCount()):
                item = table.item(row, col)
                text = item.text().strip() if item is not None else ""
                if col in numeric:
                    try:
                        cells.append(float(text))
                    except ValueError:
                        ok = False
                        break
                else:
                    cells.append(text)
            if ok:
                rows.append(cells)
        return rows

    def _fill_table(self, table: EdgeAlignedTableWidget, kind: str, rows: list[list]) -> None:
        table.setRowCount(0)
        self._set_header_row(table, kind)
        for row_values in rows:
            row = table.rowCount()
            table.insertRow(row)
            for col, value in enumerate(row_values):
                text = _fmt(value) if isinstance(value, (int, float)) else str(value)
                table.setItem(row, col, _centered_item(text))
        self._resize_table_to_content(table)

    def _on_mode_changed(self) -> None:
        mode = self.mode
        self.spectral_widget.setVisible(mode == "spectral_point")
        self.track_widget.setVisible(mode == "track")


def _centered_item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    return item


def _fmt(value) -> str:
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def _to_float(text: str) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0
