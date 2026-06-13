"""第五步：连接服务器 面板（主页步骤区）。

连接后内嵌显示 CPU 占用排行和任务队列，仿照 src 旧版实现。
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import LineEdit, PrimaryPushButton, TableWidget

from ..components.header_card import create_header_card
from workflows.support.translations import tr

_TITLE_KEY = "step6_title"
_TITLE_DEFAULT = "第五步：连接服务器"

# ── 任务状态映射 ────────────────────────────────────────────────────────
_STATE_MAP = {
    "RUNNING": ("queue_status_running", "运行中"),
    "PENDING": ("queue_status_pending", "等待中"),
    "COMPLETING": ("queue_status_completing", "完成中"),
    "CONFIGURING": ("queue_status_configuring", "配置中"),
    "SUSPENDED": ("queue_status_suspended", "挂起"),
}
_ACTIVE_STATES = {"RUNNING", "PENDING", "COMPLETING", "CONFIGURING", "SUSPENDED"}


class ServerConnectPanel:
    """连接服务器 + CPU 排行 + 任务队列 + 取消任务。"""

    def __init__(
        self,
        parent: QWidget,
        *,
        create_button: Callable[[str, Callable[..., object]], PrimaryPushButton],
        input_style: Callable[[], str],
        connect: Callable[[], None],
        cancel: Callable[[], None],
    ) -> None:
        self._group, layout = create_header_card(
            parent,
            f"{tr(_TITLE_KEY, _TITLE_DEFAULT)}  {tr('step6_not_connected', '[未连接]')}",
        )
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        self._group.viewLayout.setContentsMargins(11, 10, 11, 12)

        # ── 连接按钮 ────────────────────────────────────────────────────
        self.connect_button = create_button(tr("step6_connect", "连接服务器"), connect)
        layout.addWidget(self.connect_button)

        # ── CPU 占用排行标题 ────────────────────────────────────────────
        self._cpu_title = self._build_section_title(
            tr("step6_cpu_ranking", "CPU 占用排行")
        )
        layout.addWidget(self._cpu_title)

        # ── CPU 占用排行表格 ────────────────────────────────────────────
        self._cpu_table = TableWidget()
        self._cpu_table.setColumnCount(3)
        self._cpu_table.setHorizontalHeaderLabels(["PID", "USER", "CPU%"])
        self._cpu_table.horizontalHeader().setVisible(False)
        self._cpu_table.verticalHeader().setVisible(False)
        self._cpu_table.setBorderVisible(False)
        self._cpu_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._cpu_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._cpu_table.setWordWrap(False)
        hdr = self._cpu_table.horizontalHeader()
        hdr.setStretchLastSection(True)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        vhdr = self._cpu_table.verticalHeader()
        vhdr.setVisible(False)
        vhdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._cpu_table.setContentsMargins(0, 0, 0, 0)
        self._cpu_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        self._cpu_table.setRowCount(0)
        self._cpu_table.setVisible(False)
        layout.addWidget(self._cpu_table)

        # ── 任务队列标题 ────────────────────────────────────────────────
        self._queue_title = self._build_section_title(
            tr("step6_queue_ranking", "任务队列 占用排行")
        )
        layout.addWidget(self._queue_title)

        # ── 任务队列容器（动态添加卡片）────────────────────────────────
        self._queue_container = QWidget()
        self._queue_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        self._queue_layout = QVBoxLayout(self._queue_container)
        self._queue_layout.setContentsMargins(0, 0, 0, 0)
        self._queue_layout.setSpacing(8)
        self._queue_container.setVisible(False)
        layout.addWidget(self._queue_container)

        # ── 取消任务区域 ────────────────────────────────────────────────
        self._cancel_widget = QWidget()
        cancel_row = QHBoxLayout(self._cancel_widget)
        cancel_row.setContentsMargins(0, 10, 0, 0)
        cancel_row.setSpacing(8)
        cancel_row.addWidget(QLabel(tr("queue_jobid", "任务 ID:")))
        self.job_edit = LineEdit()
        self.job_edit.setStyleSheet(input_style())
        self.job_edit.setPlaceholderText(tr("enter_jobid_placeholder", "SLURM 任务号"))
        cancel_row.addWidget(self.job_edit, 1)
        cancel_row.addWidget(create_button(tr("cancel_task", "取消任务"), cancel))
        layout.addWidget(self._cancel_widget)

        self._group.viewLayout.addLayout(layout)
        self.widget = self._group
        self.set_connected(False)

    # ── 公共接口 ──────────────────────────────────────────────────────────

    def job_id(self) -> str:
        return self.job_edit.text().strip()

    def set_connected(self, connected: bool) -> None:
        status = (
            tr("step6_connected", "[已连接]")
            if connected
            else tr("step6_not_connected", "[未连接]")
        )
        try:
            self._group.setTitle(f"{tr(_TITLE_KEY, _TITLE_DEFAULT)}  {status}")
        except Exception:
            pass
        self.connect_button.setVisible(not connected)
        self._cancel_widget.setVisible(False)  # 由 update_queue_table 控制显隐
        if not connected:
            self._hide_cpu_and_queue()

    def update_cpu_table(self, rows: list) -> None:
        """更新 CPU 排行表格。rows: [[pid, user, cpu%], ...]"""
        valid = []
        for row in rows:
            parts = [str(p) for p in row] if isinstance(row, (list, tuple)) else str(row).split()
            if len(parts) >= 3:
                try:
                    int(parts[0])
                    valid.append(parts[:3])
                except ValueError:
                    continue
        if not valid:
            self._cpu_table.setRowCount(0)
            self._cpu_title.setVisible(False)
            self._cpu_table.setVisible(False)
            return

        # 表头 + 数据行
        self._cpu_table.setRowCount(len(valid) + 1)
        for col, text in enumerate(["PID", "USER", "CPU%"]):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            self._cpu_table.setItem(0, col, item)

        for i, parts in enumerate(valid, start=1):
            aligns = [
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            ]
            for col, (text, align) in enumerate(zip(parts, aligns)):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(align)
                self._cpu_table.setItem(i, col, item)

        self._cpu_table.resizeRowsToContents()
        # 动态高度
        total_h = sum(self._cpu_table.rowHeight(r) for r in range(self._cpu_table.rowCount()))
        self._cpu_table.setMinimumHeight(max(60, total_h + 6))
        self._cpu_table.setMaximumHeight(16777215)
        self._cpu_title.setVisible(True)
        self._cpu_table.setVisible(True)

    def update_queue_table(self, lines: list) -> None:
        """更新任务队列显示。lines: squeue 输出行列表。"""
        tasks = self._parse_squeue_lines(lines)
        if not tasks:
            self._clear_queue_display()
            self._cancel_widget.setVisible(False)
            return

        # 检查是否需要重建卡片
        existing_count = self._queue_layout.count()
        if existing_count != len(tasks):
            self._rebuild_queue_cards(tasks)
        else:
            self._update_existing_queue_cards(tasks)

        self._queue_title.setVisible(True)
        self._queue_container.setVisible(True)
        self._cancel_widget.setVisible(True)

    # ── 内部方法 ──────────────────────────────────────────────────────────

    def _build_section_title(self, text: str) -> QWidget:
        container = QWidget()
        container.setVisible(False)
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 12, 0, 6)
        h.setSpacing(10)
        line_l = QFrame()
        line_l.setFrameShape(QFrame.Shape.HLine)
        line_l.setFixedHeight(1)
        line_l.setStyleSheet("background-color: #888888; border: none;")
        label = QLabel(text)
        label.setStyleSheet("font-weight: normal; font-size: 14px;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        line_r = QFrame()
        line_r.setFrameShape(QFrame.Shape.HLine)
        line_r.setFixedHeight(1)
        line_r.setStyleSheet("background-color: #888888; border: none;")
        h.addWidget(line_l, 1)
        h.addWidget(label)
        h.addWidget(line_r, 1)
        return container

    def _hide_cpu_and_queue(self) -> None:
        self._cpu_title.setVisible(False)
        self._cpu_table.setVisible(False)
        self._cpu_table.setRowCount(0)
        self._queue_title.setVisible(False)
        self._queue_container.setVisible(False)
        self._clear_queue_display()

    def _parse_squeue_lines(self, lines: list) -> list[dict]:
        """解析 squeue 行，返回任务字典列表。"""
        tasks = []
        for ln in lines:
            if not ln or not ln.strip():
                continue
            parts = ln.split()
            if len(parts) < 7:
                continue
            state = parts[3]
            if state not in _ACTIVE_STATES:
                continue
            state_key, state_default = _STATE_MAP.get(state, (None, state))
            state_text = tr(state_key, state_default) if state_key else state
            tasks.append(
                {
                    "jobid": parts[0],
                    "partition": parts[1],
                    "name": parts[2],
                    "state": state_text,
                    "time": parts[4],
                    "nodes": parts[5],
                    "nodelist": " ".join(parts[6:]),
                }
            )
        return tasks

    def _rebuild_queue_cards(self, tasks: list[dict]) -> None:
        self._clear_queue_display()
        for idx, task in enumerate(tasks):
            card = self._create_task_card(task)
            self._queue_layout.addWidget(card)
            if idx < len(tasks) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.HLine)
                sep.setFixedHeight(1)
                sep.setStyleSheet("background-color: rgba(128,128,128,0.3);")
                self._queue_layout.addWidget(sep)

    def _create_task_card(self, task: dict) -> TableWidget:
        fields = [
            (tr("queue_jobid", "JobID:"), task.get("jobid", "")),
            (tr("queue_cpu", "CPU:"), task.get("partition", "")),
            (tr("queue_job_name", "作业名:"), task.get("name", "")),
            (tr("queue_status", "状态:"), task.get("state", "")),
            (tr("queue_runtime", "已运行:"), task.get("time", "")),
            (tr("queue_node_num", "节点数:"), task.get("nodes", "")),
            (tr("queue_node_list", "节点列表:"), task.get("nodelist", "")),
        ]
        table = TableWidget()
        table.setColumnCount(2)
        table.setRowCount(len(fields))
        table.horizontalHeader().setVisible(False)
        table.verticalHeader().setVisible(False)
        table.setBorderVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setWordWrap(True)
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setStretchLastSection(True)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        for row, (label, value) in enumerate(fields):
            lbl_item = QTableWidgetItem(label)
            lbl_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            val_item = QTableWidgetItem(str(value))
            val_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(row, 0, lbl_item)
            table.setItem(row, 1, val_item)

        table.resizeRowsToContents()
        total_h = sum(table.rowHeight(r) for r in range(table.rowCount()))
        table.setMinimumHeight(max(80, total_h + 10))
        table.setMaximumHeight(16777215)
        return table

    def _update_existing_queue_cards(self, tasks: list[dict]) -> None:
        """仅更新已有卡片的内容，不重建。"""
        fields_keys = ["jobid", "partition", "name", "state", "time", "nodes", "nodelist"]
        labels = [
            tr("queue_jobid", "JobID:"),
            tr("queue_cpu", "CPU:"),
            tr("queue_job_name", "作业名:"),
            tr("queue_status", "状态:"),
            tr("queue_runtime", "已运行:"),
            tr("queue_node_num", "节点数:"),
            tr("queue_node_list", "节点列表:"),
        ]
        for i in range(min(self._queue_layout.count(), len(tasks))):
            item = self._queue_layout.itemAt(i)
            widget = item.widget() if item else None
            if not isinstance(widget, TableWidget):
                continue
            task = tasks[i]
            for row, (lbl, key) in enumerate(zip(labels, fields_keys)):
                lbl_item = widget.item(row, 0)
                if lbl_item:
                    lbl_item.setText(lbl)
                val_item = widget.item(row, 1)
                if val_item:
                    val_item.setText(str(task.get(key, "")))
            widget.resizeRowsToContents()

    def _clear_queue_display(self) -> None:
        while self._queue_layout.count() > 0:
            item = self._queue_layout.takeAt(0)
            if item:
                w = item.widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()
