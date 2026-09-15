"""Step 2 卡片：区域模型外部边界谱。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
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
from qfluentwidgets import CheckBox, ComboBox, LineEdit, PrimaryPushButton

from ..components.combo_box import left_align_combo_text
from ..components.header_card import create_header_card
from ..components.table_widget import EdgeAlignedTableWidget
from workflows.domain.config_models import BoundaryConfig, PipelineConfig
from workflows.support.translations import tr

_LABEL = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
_LABEL_TOP = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
_EXPAND = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class BoundaryStepPanel:
    """外部边界谱配置卡片。"""

    def __init__(
        self,
        parent: QWidget,
        *,
        create_button: Callable[[str, Callable[..., object]], PrimaryPushButton],
        input_style: Callable[[], str],
        combo_style: Callable[[], str],
        inspect: Callable[[], None],
        prepare: Callable[[], None],
        preview: Callable[[], None],
        copy_spectrum: Callable[[], None],
    ) -> None:
        self.widget, layout = create_header_card(
            parent,
            tr("step2_boundary_title", "外部边界谱"),
            include_vbox_style=True,
        )
        self._enabled = CheckBox(tr("step2_boundary_enable", "使用外部二维谱作为开边界"))
        layout.addWidget(self._enabled)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)

        self._location = ComboBox()
        self._location.addItems(
            [tr("step2_boundary_local", "本地文件"), tr("step2_boundary_remote", "服务器文件")]
        )
        self._location.setStyleSheet(combo_style())
        self._location.setSizePolicy(_EXPAND)
        left_align_combo_text(self._location)
        grid.addWidget(self._field_label(tr("step2_boundary_location", "来源位置：")), 0, 0, _LABEL)
        grid.addWidget(self._location, 0, 1, 1, 2)

        files_wrap = QWidget()
        files_wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        files_block = QVBoxLayout(files_wrap)
        files_block.setContentsMargins(0, 2, 0, 0)
        files_block.setSpacing(10)

        pick_row = QHBoxLayout()
        pick_row.setContentsMargins(0, 0, 0, 0)
        pick_row.setSpacing(8)
        self._add_file = create_button(tr("step2_boundary_add_file", "添加文件"), self._browse_file)
        self._add_file.setSizePolicy(_EXPAND)
        self._remove_file = create_button("×", self._remove_selected)
        self._remove_file.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        font = self._remove_file.font()
        font.setPointSize(max(font.pointSize() + 4, 16))
        self._remove_file.setFont(font)
        self._remove_file.setStyleSheet(self._remove_file.styleSheet().replace("padding: 8px 16px;", "padding: 0px;"))
        side = max(self._add_file.sizeHint().height(), self._remove_file.sizeHint().height())
        self._remove_file.setFixedSize(side, side)
        self._remove_file.setToolTip(tr("step2_boundary_remove_file", "移除所选谱文件"))
        pick_row.addWidget(self._add_file, 1)
        pick_row.addWidget(self._remove_file, 0)
        files_block.addLayout(pick_row)

        self._path_edit = LineEdit()
        self._path_edit.setStyleSheet(input_style())
        self._path_edit.setSizePolicy(_EXPAND)
        self._path_edit.setMinimumWidth(0)
        self._path_edit.setPlaceholderText(tr("step2_boundary_path_hint", "或输入路径后回车添加"))
        self._path_edit.returnPressed.connect(self._add_typed_path)
        files_block.addWidget(self._path_edit)

        self._files = EdgeAlignedTableWidget()
        self._files.setColumnCount(1)
        self._files.horizontalHeader().setVisible(False)
        self._files.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._files.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._files.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self._files.setBorderVisible(False)
        self._files.setWordWrap(False)
        self._files.verticalHeader().setVisible(False)
        self._files.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._clear_files()
        files_block.addWidget(self._files)

        grid.addWidget(self._field_label(tr("step2_boundary_files", "谱文件：")), 1, 0, _LABEL_TOP)
        grid.addWidget(files_wrap, 1, 1, 1, 2)

        self._sides: dict[str, CheckBox] = {}
        sides_row = QHBoxLayout()
        sides_row.setContentsMargins(0, 0, 0, 0)
        sides_row.setSpacing(12)
        for key, label in (
            ("west", tr("step2_boundary_west", "西")),
            ("east", tr("step2_boundary_east", "东")),
            ("south", tr("step2_boundary_south", "南")),
            ("north", tr("step2_boundary_north", "北")),
        ):
            box = CheckBox(label)
            box.setChecked(True)
            self._sides[key] = box
            sides_row.addWidget(box, 1)
        grid.addWidget(self._field_label(tr("step2_boundary_sides", "开边界：")), 2, 0, _LABEL)
        grid.addLayout(sides_row, 2, 1, 1, 2)

        self._method = ComboBox()
        self._method.addItems(
            [tr("step2_boundary_nearest", "最近邻"), tr("step2_boundary_linear", "两点线性")]
        )
        self._method.setStyleSheet(combo_style())
        self._method.setSizePolicy(_EXPAND)
        left_align_combo_text(self._method)
        self._method.setToolTip(
            tr(
                "step2_boundary_linear_hint",
                "两点线性是两个源站点之间的谱密度插值（BOUND%INTERP=2），不是面插值。投影落在线段外视为覆盖失败。",
            )
        )
        grid.addWidget(self._field_label(tr("step2_boundary_method", "空间映射：")), 3, 0, _LABEL)
        grid.addWidget(self._method, 3, 1, 1, 2)

        self._distance = LineEdit()
        self._distance.setStyleSheet(input_style())
        self._distance.setSizePolicy(_EXPAND)
        self._distance.setMinimumWidth(0)
        self._distance.setPlaceholderText(tr("step2_boundary_km_hint", "如 50"))
        grid.addWidget(self._field_label(tr("step2_boundary_max_km", "最大距离 (km)：")), 4, 0, _LABEL)
        grid.addWidget(self._distance, 4, 1, 1, 2)

        self._gap_hours = LineEdit()
        self._gap_hours.setStyleSheet(input_style())
        self._gap_hours.setSizePolicy(_EXPAND)
        self._gap_hours.setMinimumWidth(0)
        self._gap_hours.setPlaceholderText(tr("step2_boundary_gap_hint", "如 3"))
        grid.addWidget(self._field_label(tr("step2_boundary_gap_hours", "时间缺口 (h)：")), 5, 0, _LABEL)
        grid.addWidget(self._gap_hours, 5, 1, 1, 2)

        self._memory = LineEdit()
        self._memory.setStyleSheet(input_style())
        self._memory.setSizePolicy(_EXPAND)
        self._memory.setMinimumWidth(0)
        self._memory.setText("1024")
        grid.addWidget(self._field_label(tr("step2_boundary_memory", "内存预算 (MiB)：")), 6, 0, _LABEL)
        grid.addWidget(self._memory, 6, 1, 1, 2)
        layout.addLayout(grid)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setVisible(False)
        layout.addWidget(self._status)

        actions = QGridLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(10)
        actions.setColumnStretch(0, 1)
        actions.setColumnStretch(1, 1)
        self.inspect_button = create_button(tr("step2_boundary_inspect", "检查谱文件"), inspect)
        self.prepare_button = create_button(tr("step2_boundary_prepare", "准备边界"), prepare)
        self.preview_button = create_button(tr("step2_boundary_preview", "预览映射"), preview)
        self.copy_spectrum_button = create_button(
            tr("step2_boundary_copy_spectrum", "填写目标谱"), copy_spectrum
        )
        self.copy_spectrum_button.setToolTip(
            tr("step2_boundary_copy_spectrum_tip", "用源谱的频率和方向离散填写目标谱，不改 ST 与源项系数")
        )
        for button in (
            self.inspect_button,
            self.prepare_button,
            self.preview_button,
            self.copy_spectrum_button,
        ):
            button.setSizePolicy(_EXPAND)
        actions.addWidget(self.inspect_button, 0, 0)
        actions.addWidget(self.prepare_button, 0, 1)
        actions.addWidget(self.preview_button, 1, 0)
        actions.addWidget(self.copy_spectrum_button, 1, 1)
        layout.addLayout(actions)

        self.widget.viewLayout.setContentsMargins(11, 10, 11, 12)
        self.widget.viewLayout.addLayout(layout)

        self._enabled.toggled.connect(self._sync_enabled)
        self._location.currentIndexChanged.connect(self._sync_location)
        self._sync_enabled(False)

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setAlignment(_LABEL)
        return label

    def _clear_files(self) -> None:
        self._files.setRowCount(0)
        self._resize_files_table()
        self._files.setVisible(False)

    def _resize_files_table(self) -> None:
        self._files.expand_to_contents()

    def _append_file(self, path: str) -> None:
        text = str(path).strip()
        if not text or text in self.files():
            return
        row = self._files.rowCount()
        self._files.insertRow(row)
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setTextAlignment(_LABEL)
        item.setToolTip(text)
        self._files.setItem(row, 0, item)
        self._files.setVisible(True)
        self._resize_files_table()
        self._files.updateGeometry()

    def _browse_file(self) -> None:
        typed = self._path_edit.text().strip()
        if typed:
            self._add_typed_path()
            return
        if self._location.currentIndex() == 1:
            self.set_status(tr("step2_boundary_need_path", "请输入谱文件路径后再添加"))
            return
        selected, _ = QFileDialog.getOpenFileNames(
            self.widget,
            tr("step2_boundary_choose", "选择 WW3 点谱 NetCDF"),
            str(Path.home()),
            "NetCDF (*.nc *.nc4);;All (*)",
        )
        for path in selected:
            self._append_file(path)

    def _add_typed_path(self) -> None:
        path = self._path_edit.text().strip()
        if not path:
            self.set_status(tr("step2_boundary_need_path", "请输入谱文件路径后再添加"))
            return
        self._append_file(path)
        self._path_edit.clear()

    def _remove_selected(self) -> None:
        rows = sorted({index.row() for index in self._files.selectedIndexes()}, reverse=True)
        if not rows and self._files.rowCount() > 0:
            rows = [self._files.rowCount() - 1]
        for row in rows:
            self._files.removeRow(row)
        self._files.setVisible(self._files.rowCount() > 0)
        self._resize_files_table()
        self._files.updateGeometry()

    def _sync_location(self) -> None:
        remote = self._location.currentIndex() == 1
        self._path_edit.setPlaceholderText(
            tr("step2_boundary_remote_path", "服务器 POSIX 路径，回车添加")
            if remote
            else tr("step2_boundary_path_hint", "或输入路径后回车添加")
        )
        self._add_file.setText(
            tr("step2_boundary_add_path", "添加路径") if remote else tr("step2_boundary_add_file", "添加文件")
        )

    def _sync_enabled(self, checked: bool) -> None:
        for widget in (
            self._location,
            self._files,
            self._path_edit,
            self._add_file,
            self._remove_file,
            self._method,
            self._distance,
            self._gap_hours,
            self._memory,
            self.inspect_button,
            self.prepare_button,
            self.preview_button,
            self.copy_spectrum_button,
            *self._sides.values(),
        ):
            widget.setEnabled(bool(checked) and self.widget.isEnabled())
        if checked:
            self._sync_location()
        else:
            # 关闭时不再显示「当前关闭」文案（启用开关本身已表达该状态），
            # 仅清掉可能残留的检查/准备状态文本。
            # [EN] Do not show an "off" caption when disabled (the checkbox
            # already conveys it); just clear any leftover status text.
            self.set_status("")

    def set_grid_supported(self, supported: bool) -> None:
        self.widget.setEnabled(True)
        self._enabled.setEnabled(supported)
        if not supported:
            self._enabled.setChecked(False)
        self._sync_enabled(self._enabled.isChecked())
        if not supported:
            self.set_status(tr("step2_boundary_grid_unsupported", "首版仅支持单层矩形网格"))

    def set_status(self, text: str) -> None:
        self._status.setText(text)
        self._status.setVisible(bool(str(text).strip()))

    def files(self) -> list[str]:
        paths: list[str] = []
        for row in range(self._files.rowCount()):
            item = self._files.item(row, 0)
            text = item.text().strip() if item is not None else ""
            if text:
                paths.append(text)
        return paths

    def overrides(self) -> dict:
        gap_hours = self._gap_hours.text().strip()
        gap_seconds = None
        if gap_hours:
            try:
                gap_seconds = int(round(float(gap_hours) * 3600.0))
            except ValueError:
                gap_seconds = None
        distance = self._distance.text().strip()
        memory = self._memory.text().strip() or "1024"
        return {
            "mode": "external_spectra" if self._enabled.isChecked() else "none",
            "source": {
                "format": "ww3_netcdf",
                "location": "remote" if self._location.currentIndex() == 1 else "local",
                "files": self.files(),
            },
            "selection": {
                "type": "sides",
                "sides": [key for key, box in self._sides.items() if box.isChecked()]
                or ["west", "east", "south", "north"],
                "inset_cells": 1,
            },
            "interpolation": {
                "method": "linear" if self._method.currentIndex() == 1 else "nearest",
                "max_distance_km": float(distance) if distance else None,
            },
            "validation": {"max_time_gap_seconds": gap_seconds},
            "resources": {"memory_limit_mb": int(float(memory)) if memory else 1024},
        }

    def render(self, config: PipelineConfig) -> None:
        boundary: BoundaryConfig = getattr(config, "boundary", None) or BoundaryConfig()
        supported = (
            str(config.grid.mesh_type).lower() == "structured"
            and str(config.grid.grid_type).lower() == "normal"
        )
        self._enabled.blockSignals(True)
        self._enabled.setChecked(bool(boundary.enabled) and supported)
        self._enabled.blockSignals(False)
        self._location.setCurrentIndex(1 if str(boundary.source.location).lower() == "remote" else 0)
        self._clear_files()
        for path in boundary.source.files or []:
            self._append_file(str(path))
        chosen = {str(s).lower() for s in (boundary.selection.sides or [])}
        if not chosen:
            chosen = {"west", "east", "south", "north"}
        for key, box in self._sides.items():
            box.setChecked(key in chosen)
        self._method.setCurrentIndex(1 if str(boundary.interpolation.method).lower() == "linear" else 0)
        km = boundary.interpolation.max_distance_km
        self._distance.setText("" if km is None else str(km))
        gap = boundary.validation.max_time_gap_seconds
        self._gap_hours.setText("" if gap is None else str(gap / 3600.0))
        self._memory.setText(str(boundary.resources.memory_limit_mb or 1024))
        self.set_grid_supported(supported)
