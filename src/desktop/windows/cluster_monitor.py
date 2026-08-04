"""集群监控页：左侧 个人任务队列 + 空闲资源 两张卡片，右侧 日志(1/5) + 全集群任务列表(4/5)。

打开页面自动连接 SSH；断开后每秒自动尝试重连；三个列表每秒刷新。
集群任务列表显示集群上所有用户的任务（sacct -a），个人任务队列与空闲资源列表
与主页第五步样式一致。

[EN] Cluster monitor page: left = my task queue + idle resources cards, right =
log (1/5) + cluster jobs for all users (4/5). Auto-connects on open and
auto-reconnects every second when SSH drops; all lists refresh every second.
"""

from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..components.header_card import create_header_card
from ..components.table_widget import EdgeAlignedTableWidget
from workflows.application.remote_ops import run_server_status
from workflows.support.translations import tr

# ── 任务状态映射（与主页第五步一致）────────────────────────────────────────────
# [EN] Task state mapping (same as Step 5 on the home page).
_STATE_MAP = {
    "RUNNING": ("queue_status_running", "运行中"),
    "PENDING": ("queue_status_pending", "等待中"),
    "COMPLETING": ("queue_status_completing", "完成中"),
    "CONFIGURING": ("queue_status_configuring", "配置中"),
    "SUSPENDED": ("queue_status_suspended", "挂起"),
}
_ACTIVE_STATES = {"RUNNING", "PENDING", "COMPLETING", "CONFIGURING", "SUSPENDED"}


def _section_title(parent: QWidget, text: str) -> QWidget:
    """带两侧分隔线的区块标题（样式同主页第五步）。"""
    container = QWidget(parent)
    h = QHBoxLayout(container)
    h.setContentsMargins(0, 10, 0, 6)
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


class ClusterJobsTable(QWidget):
    """集群任务列表（所有用户，sacct -a）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(
            _section_title(self, tr("cm_cluster_jobs", "集群任务（所有用户）"))
        )
        self._table = EdgeAlignedTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(
            [
                tr("cluster_col_user", "用户"),
                tr("cluster_col_cpus", "CPU数"),
                tr("cluster_col_nodes", "节点"),
                tr("cluster_col_elapsed", "时间"),
            ]
        )
        self._table.horizontalHeader().setVisible(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setBorderVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setWordWrap(False)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        hdr = self._table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setMinimumSectionSize(42)
        vhdr = self._table.verticalHeader()
        vhdr.setVisible(False)
        vhdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._table.setRowCount(0)
        layout.addWidget(self._table, 1)
        self._signature: tuple = ()
        self._struct_signature: tuple = ()

    def update_cluster_jobs(self, rows: list) -> None:
        """rows: [[user, cpus, nodes, elapsed], ...]"""
        valid = []
        for row in rows:
            parts = [str(p) for p in row] if isinstance(row, (list, tuple)) else str(row).split()
            if len(parts) >= 4:
                valid.append(parts[:4])
        value_sig = tuple(tuple(parts) for parts in valid)
        if value_sig == self._signature:
            return
        self._signature = value_sig
        if not valid:
            self._table.setRowCount(0)
            return
        # [EN] Structure signature excludes the ever-changing elapsed column.
        # 结构签名不含每秒变化的 elapsed 列：结构不变时只更新该列，避免整表重建。
        struct_sig = tuple(tuple(parts[:3]) for parts in valid)
        if struct_sig == self._struct_signature:
            self._update_elapsed(valid)
            return
        self._struct_signature = struct_sig
        self._table.setUpdatesEnabled(False)
        try:
            header_labels = [
                tr("cluster_col_user", "用户"),
                tr("cluster_col_cpus", "核数"),
                tr("cluster_col_nodes", "节点"),
                tr("cluster_col_elapsed", "时间"),
            ]
            self._table.setRowCount(len(valid) + 1)
            for col, text in enumerate(header_labels):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                    )
                else:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
                    )
                self._table.setItem(0, col, item)
            aligns = [
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            ]
            for i, parts in enumerate(valid, start=1):
                for col, (text, align) in enumerate(zip(parts, aligns)):
                    item = QTableWidgetItem(str(text))
                    item.setTextAlignment(align)
                    self._table.setItem(i, col, item)
            self._table.expand_to_contents(minimum_height=60, extra_height=6)
            self._table.resizeColumnToContents(3)
            self._table.setColumnWidth(3, max(self._table.columnWidth(3), 112))
        finally:
            self._table.setUpdatesEnabled(True)

    def _update_elapsed(self, valid: list) -> None:
        """结构不变时仅更新时间列（第 3 列）。"""
        self._table.setUpdatesEnabled(False)
        try:
            for i, parts in enumerate(valid, start=1):
                item = self._table.item(i, 3)
                if item is not None and item.text() != str(parts[3]):
                    item.setText(str(parts[3]))
        finally:
            self._table.setUpdatesEnabled(True)


class QueueCardsPanel(QWidget):
    """个人任务队列（squeue 卡片列表，样式同主页第五步）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(
            _section_title(self, tr("cm_my_queue", "个人任务队列"))
        )
        self._cards_container = QWidget()
        self._cards_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(8)
        layout.addWidget(self._cards_container)
        self._task_tables: list[EdgeAlignedTableWidget] = []
        self._signature: tuple = ()
        self._struct_signature: tuple = ()

    def update_queue(self, lines: list) -> None:
        """lines: squeue 输出行。"""
        tasks = self._parse_squeue_lines(lines)
        value_sig = tuple(
            (
                task.get("jobid", ""),
                task.get("partition", ""),
                task.get("name", ""),
                task.get("state", ""),
                task.get("time", ""),
                task.get("nodes", ""),
                task.get("cpus", ""),
                task.get("nodelist", ""),
            )
            for task in tasks
        )
        if value_sig == self._signature:
            return
        self._signature = value_sig
        if not tasks:
            self._clear()
            return
        # [EN] Structure signature excludes the ever-changing runtime column.
        # 结构签名不含每秒变化的已运行时长列：结构不变时只更新卡片值，避免每秒重建卡片。
        struct_sig = tuple(
            (
                task.get("jobid", ""),
                task.get("partition", ""),
                task.get("name", ""),
                task.get("state", ""),
                task.get("nodes", ""),
                task.get("cpus", ""),
                task.get("nodelist", ""),
            )
            for task in tasks
        )
        if struct_sig == self._struct_signature:
            self._update_card_values(tasks)
            return
        self._struct_signature = struct_sig
        self._cards_container.setUpdatesEnabled(False)
        try:
            self._rebuild(tasks)
        finally:
            self._cards_container.setUpdatesEnabled(True)

    def _update_card_values(self, tasks: list[dict]) -> None:
        """结构不变时仅更新卡片值单元格（第 1 列）。"""
        if len(tasks) != len(self._task_tables):
            self._rebuild(tasks)
            return
        for table, task in zip(self._task_tables, tasks):
            values = [
                task.get("jobid", ""),
                task.get("name", ""),
                task.get("state", ""),
                task.get("time", ""),
                task.get("partition", ""),
                task.get("nodes", ""),
                task.get("cpus", ""),
                task.get("nodelist", ""),
            ]
            table.setUpdatesEnabled(False)
            try:
                for row, value in enumerate(values):
                    item = table.item(row, 1)
                    if item is not None and item.text() != str(value):
                        item.setText(str(value))
            finally:
                table.setUpdatesEnabled(True)

    def _parse_squeue_lines(self, lines: list) -> list[dict]:
        tasks = []
        for ln in lines:
            if not ln or not ln.strip():
                continue
            parts = ln.split()
            if len(parts) < 8:
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
                    "cpus": parts[6],
                    "nodelist": " ".join(parts[7:]),
                }
            )
        return tasks

    def _rebuild(self, tasks: list[dict]) -> None:
        self._clear()
        self._task_tables = []
        for idx, task in enumerate(tasks):
            card = self._create_task_card(task)
            self._task_tables.append(card)
            self._cards_layout.addWidget(card)
            if idx < len(tasks) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.HLine)
                sep.setFixedHeight(1)
                sep.setStyleSheet("background-color: rgba(128,128,128,0.3);")
                self._cards_layout.addWidget(sep)

    def _create_task_card(self, task: dict) -> EdgeAlignedTableWidget:
        fields = [
            (tr("queue_jobid", "JobID:"), task.get("jobid", "")),
            (tr("queue_job_name", "作业名:"), task.get("name", "")),
            (tr("queue_status", "状态:"), task.get("state", "")),
            (tr("queue_runtime", "已运行:"), task.get("time", "")),
            (tr("queue_cpu", "分区:"), task.get("partition", "")),
            (tr("queue_node_num", "节点数:"), task.get("nodes", "")),
            (tr("queue_cpus", "核数:"), task.get("cpus", "")),
            (tr("queue_node_list", "节点列表:"), task.get("nodelist", "")),
        ]
        table = EdgeAlignedTableWidget()
        table.setColumnCount(2)
        table.setRowCount(len(fields))
        table.horizontalHeader().setVisible(False)
        table.verticalHeader().setVisible(False)
        table.setBorderVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setWordWrap(True)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setStretchLastSection(True)
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
        table.expand_to_contents(minimum_height=80, extra_height=10)
        return table

    def _clear(self) -> None:
        while self._cards_layout.count() > 0:
            item = self._cards_layout.takeAt(0)
            if item:
                w = item.widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()
        self._task_tables = []


class IdleResourcesTable(QWidget):
    """空闲资源列表（sinfo，样式同主页第五步）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(
            _section_title(self, tr("cm_idle_resources", "空闲资源"))
        )
        self._table = EdgeAlignedTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(
            [
                tr("idle_col_cpu", "分区"),
                tr("idle_col_node_names", "节点名"),
                tr("idle_col_cores", "可用核数"),
            ]
        )
        self._table.horizontalHeader().setVisible(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setBorderVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setWordWrap(False)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        idle_hdr = self._table.horizontalHeader()
        idle_hdr.setStretchLastSection(False)
        for col in range(3):
            idle_hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        idle_hdr.setMinimumSectionSize(36)
        self._table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(self._table)
        self._signature: tuple = ()
        self._rows: list[dict] = []

    def update_idle(self, rows: list) -> None:
        valid = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            cpu = str(row.get("cpu") or row.get("partition") or "").strip()
            if not cpu:
                continue
            try:
                nodes = int(row.get("nodes") or row.get("idle_nodes") or 0)
                cores = int(row.get("cores") or row.get("idle_cores") or row.get("idle_cpus") or 0)
            except (TypeError, ValueError):
                continue
            if nodes <= 0 or cores <= 0:
                continue
            node_name = str(row.get("node") or row.get("node_name") or "").strip()
            valid.append(
                {
                    "cpu": cpu,
                    "nodes": nodes,
                    "node_name": node_name,
                    "cores": cores,
                }
            )
        valid.sort(key=lambda item: item["cores"], reverse=True)
        signature = tuple(
            (row["cpu"], row["node_name"], row["cores"]) for row in valid
        )
        if signature == self._signature:
            return
        self._signature = signature
        self._rows = valid
        self._table.setUpdatesEnabled(False)
        try:
            if not valid:
                self._table.setRowCount(0)
                return
            header_labels = [
                tr("idle_col_cpu", "分区"),
                tr("idle_col_node_names", "节点名"),
                tr("idle_col_cores", "可用核数"),
            ]
            self._table.setRowCount(len(valid) + 1)
            for col, text in enumerate(header_labels):
                item = QTableWidgetItem(text)
                if col == 0:
                    align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                elif col == 2:
                    align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                else:
                    align = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
                item.setTextAlignment(align)
                self._table.setItem(0, col, item)
            aligns = [
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            ]
            for row_index, row in enumerate(valid, start=1):
                values = [row["cpu"], row.get("node_name", ""), row["cores"]]
                for col, (value, align) in enumerate(zip(values, aligns)):
                    item = QTableWidgetItem(str(value))
                    item.setTextAlignment(align)
                    self._table.setItem(row_index, col, item)
            self._table.expand_to_contents(minimum_height=52, extra_height=6)
        finally:
            self._table.setUpdatesEnabled(True)


class ClusterMonitorInterface(QWidget):
    """集群监控主界面（FluentWindow 顶层子页面）。

    打开页面自动尝试连接 SSH；连接断开后每秒自动重连；集群任务/个人队列/
    空闲资源每秒刷新。右侧日志区占 1/5 高度，集群任务列表占 4/5。
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        remote_vm=None,
        runner=None,
        get_config=None,
        log=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("cluster_monitor_interface")
        self._remote_vm = remote_vm
        self._runner = runner
        self._get_config = get_config or (lambda: None)
        self._busy = False
        self._reconnecting = False
        self._timer: QTimer | None = None

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setStyleSheet(
            """
            QSplitter::handle:horizontal {
                background-color: #64AADE;
                border-width: 2px;
                border-radius: 0.8px;
                margin: 330px 2px;
            }
            QSplitter::handle:horizontal:hover {
                background-color: #909090;
            }
            """
        )

        # ── 左侧：个人任务队列 + 空闲资源（两张卡片）──────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 5, 10)
        left_layout.setSpacing(10)
        self._queue_panel = QueueCardsPanel(left)
        self._idle_panel = IdleResourcesTable(left)
        left_layout.addWidget(self._queue_panel)
        left_layout.addWidget(self._idle_panel)
        left_layout.addStretch(1)

        # ── 右侧：状态行 + 日志(1/5) + 集群任务列表(4/5)──────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(5, 1, 10, 11)
        right_layout.setSpacing(6)
        self._status_label = QLabel(
            tr("cm_status_disconnected", "未连接（每秒自动重连）")
        )
        self._status_label.setStyleSheet("font-weight: bold; color: #E08A00;")
        right_layout.addWidget(self._status_label)
        self._log = QTextEdit()
        mono_font = QFont(self.font())
        fallback_monos = [
            "Menlo",
            "Monaco",
            "Consolas",
            "SF Mono",
            "Courier New",
            "Liberation Mono",
            "DejaVu Sans Mono",
            "Noto Sans Mono",
        ]
        available = set(QFontDatabase.families())
        chosen = next((family for family in fallback_monos if family in available), None)
        if not chosen:
            chosen = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()
        mono_font.setFamily(chosen)
        self._log.setFont(mono_font)
        self._log.setReadOnly(True)
        self._log.setAcceptRichText(False)
        self._log.setUndoRedoEnabled(False)
        try:
            self._log.document().setMaximumBlockCount(2000)
        except Exception:
            pass
        right_layout.addWidget(self._log, 1)
        self._cluster_table = ClusterJobsTable(right)
        right_layout.addWidget(self._cluster_table, 4)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 33)
        splitter.setStretchFactor(1, 67)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)
        self._splitter = splitter

        def _apply_sizes() -> None:
            try:
                splitter.setSizes([400, 800])
            except RuntimeError:
                pass

        QTimer.singleShot(0, _apply_sizes)

    # ── 对外接口 ──────────────────────────────────────────────────────────────────

    def start_monitoring(self) -> None:
        """页面显示时调用：启动轮询；未连接则自动连接（幂等）。"""
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._tick)
            self._timer.start(1_000)
        self._tick()

    def stop_monitoring(self) -> None:
        """页面隐藏/窗口关闭时调用：停止每秒轮询与重连。"""
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._busy = False
        self._reconnecting = False

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.start_monitoring()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self.stop_monitoring()

    def _append_log(self, message: str) -> None:
        try:
            self._log.append(str(message))
        except RuntimeError:
            pass

    # ── 每秒轮询 / 自动连接 / 自动重连 ──────────────────────────────────────────

    def _tick(self) -> None:
        if self._busy or self._reconnecting:
            return
        if not self._remote_vm:
            return
        cfg = self._get_config()
        if cfg is None:
            self._set_status(disconnected=True)
            return
        if not self._remote_vm.is_connected:
            self._try_connect(cfg)
            return
        self._busy = True
        self._runner.run(
            lambda: run_server_status(cfg, client=self._remote_vm._client),
            self._on_status_done,
        )

    def _try_connect(self, cfg) -> None:
        self._reconnecting = True
        self._set_status(connecting=True)
        # 静默连接：内部日志抑制，结果由 _on_connect_done 统一写一条
        self._runner.run(
            lambda: self._remote_vm.connect_test(cfg),
            self._on_connect_done,
        )

    def _on_connect_done(self, result: object) -> None:
        self._reconnecting = False
        if bool(getattr(result, "success", False)):
            self._set_status(connected=True)
            self._append_log(tr("cm_reconnect_ok", "✔ 已连接服务器"))
        else:
            self._set_status(disconnected=True)
            error = getattr(result, "error", None) or tr("connect_failed", "连接失败")
            self._append_log(
                tr("cm_reconnect_fail", "✘ 连接失败：{error}").format(error=error)
            )

    def _on_status_done(self, result: object) -> None:
        self._busy = False
        if result is None:
            return
        data = getattr(result, "data", None)
        if isinstance(data, dict):
            self._cluster_table.update_cluster_jobs(data.get("cpu", []) or [])
            self._queue_panel.update_queue(data.get("queue", []) or [])
            self._idle_panel.update_idle(data.get("idle", []) or [])
            self._set_status(connected=True)
        if not getattr(result, "success", True):
            # [EN] Connection is dead: stay disconnected; the next tick will detect
            # is_connected=False and auto-reconnect. Do NOT close the shared client
            # here — the home page polls through the same persistent connection.
            # 连接已失效：保持未连接，下个 tick 检测 is_connected=False 后自动重连。
            # 不要在这里 close 共享连接——主页轮询也复用同一个持久化连接。
            self._set_status(disconnected=True)

    def _set_status(
        self, *, connected: bool = False, connecting: bool = False, disconnected: bool = False
    ) -> None:
        if connecting:
            text = tr("cm_status_connecting", "正在连接服务器…")
            color = "#1E90FF"
        elif connected:
            text = tr("cm_status_connected", "已连接（每秒刷新）")
            color = "#2E8B57"
        else:
            text = tr("cm_status_disconnected", "未连接（每秒自动重连）")
            color = "#E08A00"
        self._status_label.setText(text)
        self._status_label.setStyleSheet(f"font-weight: bold; color: {color};")
