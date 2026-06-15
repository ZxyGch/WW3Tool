"""工具子界面：清理工作目录与强迫场文件合并。

作为 FluentWindow 左侧堆叠的一页，右侧共享日志常驻。删除逻辑为纯函数（无 Qt），
界面按钮经构造注入的回调交由窗口执行（确认对话框 + 日志）。
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import CheckBox, LineEdit, PrimaryPushButton, TableWidget

from ..background_runner import BackgroundRunner
from ..components.header_card import create_header_card
from ..components.scroll_area import NoHScrollArea
from ..components import styles
from workflows.infrastructure.forcing.merge_service import (
    MergeAnalysis,
    analyze_merge_inputs,
    merge_forcing_netcdf,
)
from workflows.support.translations import tr


class ToolsInterface(QWidget):
    """常用工具页：清理工作目录 + 合并强迫场。"""

    _merge_log_received = pyqtSignal(str)
    _merge_progress_received = pyqtSignal(int, str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        clean_all: Callable[[], None],
        clean_run: Callable[[], None],
        log: Callable[[str], None] | None = None,
        get_forcing_dir: Callable[[], str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("tools_interface")
        self._log = log
        self._get_forcing_dir = get_forcing_dir or (lambda: "")
        self._merge_paths: list[str] = []
        self._merge_analysis: MergeAnalysis | None = None
        self._last_logged_progress = -10
        self._runner = BackgroundRunner(self)
        self._merge_progress_received.connect(
            self._on_merge_progress,
            Qt.ConnectionType.QueuedConnection,
        )
        if self._log:
            self._merge_log_received.connect(self._log, Qt.ConnectionType.QueuedConnection)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = NoHScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        content = QWidget()
        content.setStyleSheet("QWidget { background: transparent; }")
        vbox = QVBoxLayout(content)
        vbox.setContentsMargins(0, 0, 0, 10)
        vbox.setSpacing(14)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        # ── 清理工作目录卡片 ──
        group, layout = create_header_card(content, tr("tools_clean_workdir_card_title", "清理工作目录"))
        layout.addWidget(self._button(tr("tools_clean_workdir_all", "清空所有文件"), clean_all))
        layout.addWidget(self._button(tr("tools_clean_workdir_run_files", "清空运行文件 (.ww3 .log .bin)"), clean_run))
        group.viewLayout.setContentsMargins(11, 10, 11, 12)
        group.viewLayout.addLayout(layout)
        vbox.addWidget(group)

        # ── 合并强迫场卡片 ──
        merge_group, merge_layout = create_header_card(
            content, tr("tools_merge_forcing_card_title", "合并强迫场文件"),
        )
        self._build_merge_form(merge_layout)
        merge_group.viewLayout.setContentsMargins(11, 10, 11, 12)
        merge_group.viewLayout.addLayout(merge_layout)
        vbox.addWidget(merge_group)

        vbox.addStretch(1)

    @staticmethod
    def _button(text: str, handler: Callable[[], None]) -> PrimaryPushButton:
        button = PrimaryPushButton(text)
        button.setStyleSheet(styles.button_style())
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.clicked.connect(handler)
        return button

    @staticmethod
    def _small_button(text: str, handler: Callable[[], None]) -> PrimaryPushButton:
        button = PrimaryPushButton(text)
        button.setStyleSheet(styles.button_style())
        button.clicked.connect(handler)
        return button

    def _build_merge_form(self, layout: QVBoxLayout) -> None:
        layout.setSpacing(5)
        self._merge_table = TableWidget()
        self._merge_table.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._merge_table.setColumnCount(3)
        self._merge_table.horizontalHeader().setVisible(False)
        self._merge_table.verticalHeader().setVisible(False)
        self._merge_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._merge_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._merge_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._merge_table.setBorderVisible(False)
        self._merge_table.setWordWrap(False)
        self._merge_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._merge_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header = self._merge_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._merge_table.setColumnWidth(0, 160)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._set_merge_table_header()
        self._resize_merge_table()
        layout.addWidget(self._merge_table)

        file_buttons = QHBoxLayout()
        file_buttons.setSpacing(8)
        file_buttons.addWidget(self._small_button(tr("merge_inline_add", "添加文件"), self._add_merge_files), 1)
        file_buttons.addWidget(
            self._small_button(tr("merge_inline_remove", "移除选中"), self._remove_merge_files), 1
        )
        file_buttons.addWidget(self._small_button(tr("merge_inline_clear", "清空"), self._clear_merge_files), 1)
        layout.addLayout(file_buttons)

        output_row = QHBoxLayout()
        output_row.setSpacing(8)
        self._merge_output = LineEdit()
        self._merge_output.setReadOnly(True)
        self._merge_output.setPlaceholderText(tr("merge_inline_output_placeholder", "请选择输出文件"))
        self._merge_output.setStyleSheet(styles.input_style())
        output_row.addWidget(self._merge_output, 1)
        output_row.addWidget(self._small_button(tr("merge_inline_browse", "输出路径"), self._choose_merge_output))
        layout.addLayout(output_row)

        fast_label = QLabel(tr("merge_inline_fast", "快速合并（不压缩，文件更大）"))
        fast_label.setStyleSheet(styles.label_style())
        fast_label.mousePressEvent = lambda _event: self._merge_fast.toggle()
        self._merge_fast = CheckBox("")
        self._merge_fast.setChecked(False)
        fast_row = QHBoxLayout()
        fast_row.addWidget(fast_label)
        fast_row.addStretch(1)
        fast_row.addWidget(self._merge_fast)
        layout.addLayout(fast_row)

        self._merge_progress = QProgressBar()
        self._merge_progress.setRange(0, 100)
        self._merge_progress.setValue(0)
        self._merge_progress.setTextVisible(True)
        self._merge_progress.hide()
        layout.addWidget(self._merge_progress)

        self._merge_button = self._button(tr("merge_inline_start", "开始合并"), self._start_merge)
        self._merge_button.setEnabled(False)
        layout.addWidget(self._merge_button)

    def _set_merge_busy(self, busy: bool) -> None:
        self._merge_button.setEnabled(
            not busy and bool(self._merge_analysis and self._merge_analysis.valid and self._merge_output.text())
        )

    def _add_merge_files(self) -> None:
        start = str(Path(self._merge_paths[0]).parent) if self._merge_paths else self._get_forcing_dir()
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            tr("tools_merge_select_title", "选择强迫场文件（可多选）"),
            start,
            "NetCDF (*.nc *.nc4);;All Files (*)",
        )
        if not paths:
            return
        self._merge_paths = list(dict.fromkeys([*self._merge_paths, *paths]))
        if not self._merge_output.text():
            self._merge_output.setText(self._default_merge_output(self._merge_paths[0]))
        self._analyze_merge_files()

    def _remove_merge_files(self) -> None:
        rows = {index.row() for index in self._merge_table.selectedIndexes()}
        data_rows = {row - 1 for row in rows if row >= 1}
        if not data_rows:
            return
        self._merge_paths = [path for index, path in enumerate(self._merge_paths) if index not in data_rows]
        self._analyze_merge_files()

    def _clear_merge_files(self) -> None:
        self._merge_paths.clear()
        self._merge_analysis = None
        self._merge_table.setRowCount(1)
        self._set_merge_table_header()
        self._resize_merge_table()
        self._merge_output.clear()
        self._merge_progress.hide()
        self._merge_progress.setValue(0)
        self._merge_button.setEnabled(False)

    def _choose_merge_output(self) -> None:
        start = self._merge_output.text().strip()
        if not start and self._merge_paths:
            start = self._default_merge_output(self._merge_paths[0])
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("tools_merge_save_title", "保存合并后的文件"),
            start,
            "NetCDF (*.nc)",
        )
        if path:
            if not path.lower().endswith((".nc", ".nc4")):
                path += ".nc"
            self._merge_output.setText(path)
            self._set_merge_busy(False)

    @staticmethod
    def _default_merge_output(first_path: str) -> str:
        directory = Path(first_path).parent
        candidate = directory / "merged_forcing.nc"
        number = 2
        while candidate.exists():
            candidate = directory / f"merged_forcing_{number}.nc"
            number += 1
        return str(candidate)

    def _analyze_merge_files(self) -> None:
        self._merge_analysis = None
        self._merge_table.setRowCount(1)
        self._set_merge_table_header()
        self._resize_merge_table()
        if not self._merge_paths:
            self._clear_merge_files()
            return
        paths = tuple(self._merge_paths)
        self._set_merge_busy(True)
        self._runner.run(lambda: (paths, analyze_merge_inputs(paths)), self._on_merge_analysis_done)

    def _on_merge_analysis_done(self, result: object) -> None:
        if isinstance(result, dict):
            self._merge_log_received.emit(str(result.get("error", tr("tools_merge_failed", "合并失败"))))
            self._merge_button.setEnabled(False)
            return
        if not isinstance(result, tuple) or len(result) != 2:
            return
        analyzed_paths, analysis = result
        if tuple(self._merge_paths) != analyzed_paths:
            return
        if not isinstance(analysis, MergeAnalysis):
            return
        self._merge_analysis = analysis
        self._merge_table.setRowCount(1)
        self._set_merge_table_header()
        for info in analysis.files:
            row = self._merge_table.rowCount()
            self._merge_table.insertRow(row)
            values = (info.filename, info.forcing_fields, info.time_range)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(info.error or info.path)
                self._merge_table.setItem(row, column, item)
        self._resize_merge_table()
        if not analysis.valid:
            self._merge_log_received.emit(
                tr("tools_merge_failed", "合并失败：{error}").format(
                    error="\n".join(analysis.errors)
                )
            )
        elif self._log:
            self._merge_log_received.emit(
                tr("merge_inline_valid", "校验通过：{strategy}，共 {steps} 个时间步").format(
                    strategy=analysis.strategy,
                    steps=analysis.time_steps,
                )
            )
        self._set_merge_busy(False)

    def _set_merge_table_header(self) -> None:
        if self._merge_table.rowCount() == 0:
            self._merge_table.insertRow(0)
        for column, title in enumerate(
            (
                tr("merge_inline_col_filename", "文件"),
                tr("merge_inline_col_fields", "强迫场"),
                tr("merge_inline_col_time", "时间范围"),
            )
        ):
            item = QTableWidgetItem(title)
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            item.setData(Qt.ItemDataRole.UserRole, "header")
            self._merge_table.setItem(0, column, item)

    def _resize_merge_table(self) -> None:
        self._merge_table.resizeRowsToContents()
        height = sum(self._merge_table.rowHeight(row) for row in range(self._merge_table.rowCount()))
        self._merge_table.setFixedHeight(height + 2 * self._merge_table.frameWidth() + 2)

    def _start_merge(self) -> None:
        if not self._merge_analysis or not self._merge_analysis.valid:
            return
        output = self._merge_output.text().strip()
        if not output:
            return
        paths = tuple(self._merge_paths)
        compress = not self._merge_fast.isChecked()
        self._set_merge_busy(True)
        self._last_logged_progress = -10
        self._merge_progress.setValue(0)
        self._merge_progress.show()
        merging_message = tr("merge_inline_merging", "正在合并，请稍候...")
        self._merge_log_received.emit(merging_message)
        self._runner.run(
            lambda: merge_forcing_netcdf(
                paths,
                output,
                log=self._merge_log_received.emit,
                progress=self._merge_progress_received.emit,
                compress=compress,
            ),
            self._on_merge_done,
        )

    def _on_merge_progress(self, value: int, message: str) -> None:
        value = max(0, min(100, int(value)))
        self._merge_progress.setValue(value)
        progress_bucket = value // 10 * 10
        if progress_bucket > self._last_logged_progress or value == 100:
            self._last_logged_progress = progress_bucket
            self._merge_log_received.emit(f"{value}% {message}")

    def _on_merge_done(self, result: object) -> None:
        if isinstance(result, dict):
            error = str(result.get("error", tr("tools_merge_failed", "合并失败")))
            self._merge_log_received.emit(
                tr("tools_merge_failed", "合并失败：{error}").format(error=error)
            )
            self._set_merge_busy(False)
            return
        self._set_merge_busy(False)


# ── 删除逻辑（纯函数，无 Qt）────────────────────────────────────────────────


def should_remove_run_artifact(filename: str) -> bool:
    """运行产物：``.log`` / ``.bin`` / ``.ww3``（保留 grid.ww3）。"""
    lower = filename.lower()
    if lower.endswith(".log") or lower.endswith(".bin"):
        return True
    if lower.endswith(".ww3"):
        return lower != "grid.ww3"
    return False


def delete_all_under(workdir: str) -> tuple[int, list[str]]:
    """删除 workdir 下所有文件与空子目录（不删 workdir 本身）。"""
    errors: list[str] = []
    removed = 0
    for root, dirs, files in os.walk(workdir, topdown=False, followlinks=False):
        for name in files:
            path = os.path.join(root, name)
            try:
                os.remove(path)
                removed += 1
            except OSError as exc:
                errors.append(f"{path}: {exc}")
        for name in dirs:
            path = os.path.join(root, name)
            try:
                os.rmdir(path)
            except OSError as exc:
                errors.append(f"{path}: {exc}")
    return removed, errors


def delete_run_artifacts_under(workdir: str) -> tuple[int, list[str]]:
    """删除 workdir 下的运行产物（.ww3 除 grid.ww3 / .log / .bin）。"""
    errors: list[str] = []
    removed = 0
    for root, _dirs, files in os.walk(workdir, topdown=True, followlinks=False):
        for name in files:
            if not should_remove_run_artifact(name):
                continue
            path = os.path.join(root, name)
            try:
                os.remove(path)
                removed += 1
            except OSError as exc:
                errors.append(f"{path}: {exc}")
    return removed, errors
