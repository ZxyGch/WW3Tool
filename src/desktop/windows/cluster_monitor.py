"""集群监控页：左侧 个人任务队列 + 空闲资源 两张卡片，右侧 日志(1/5) + 全集群任务列表(4/5)。

打开页面自动连接 SSH；断开后每秒自动尝试重连；列表每秒刷新。
左侧 = 集群作业表（sacct -a 所有用户）+ 空闲资源列表（与主页第五步样式一致）；
右侧 = 其他用户任务详细列表（run_cluster_jobs_log）+ 日志（1/5）。

[EN] Cluster monitor page: left = cluster jobs table + idle resources cards;
right = other-users job detail list (run_cluster_jobs_log) + log (1/5).
Auto-connects on open and auto-reconnects every second when SSH drops.
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
from ..components.scroll_area import NoHScrollArea
from ..components.table_widget import EdgeAlignedTableWidget
from workflows.application.remote_ops import (
    _acquire,
    _fetch_cluster_active_jobs,
    _resolve_remote_username,
    run_server_status,
)
from workflows.support.logging import CoreLogger
from workflows.support.translations import tr

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
        self._card, card_layout = create_header_card(
            self, tr("cm_cluster_jobs", "集群作业（所有用户）")
        )
        card_layout.setSpacing(4)
        card_layout.addWidget(self._table)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._card)
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


class IdleResourcesTable(QWidget):
    """空闲资源列表（sinfo，样式同主页第五步）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
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
        self._card, card_layout = create_header_card(
            self, tr("cm_idle_resources", "空闲资源")
        )
        card_layout.setSpacing(4)
        card_layout.addWidget(self._table)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._card)
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


class OthersJobsTable(QWidget):
    """其他用户/本人任务详细表格（结构化数据，非文本日志）。"""

    _HEADERS = [
        ("cm_job_col_user", "用户"),
        ("cm_job_col_jobid", "JobID"),
        ("cm_job_col_partition", "分区"),
        ("cm_job_col_name", "作业名"),
        ("cm_job_col_state", "状态"),
        ("cm_job_col_time", "运行时间"),
        ("cm_job_col_nodes", "节点"),
        ("cm_job_col_cpus", "核数"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(
            _section_title(self, tr("cm_others_jobs", "其他用户任务（详细）"))
        )
        self._others_table = self._make_table()
        layout.addWidget(self._others_table, 2)
        layout.addWidget(_section_title(self, tr("cm_my_jobs", "本人任务")))
        self._mine_table = self._make_table()
        layout.addWidget(self._mine_table, 1)
        self._others_sig: tuple = ()
        self._others_struct: tuple = ()
        self._mine_sig: tuple = ()
        self._mine_struct: tuple = ()

    @staticmethod
    def _make_table() -> EdgeAlignedTableWidget:
        table = EdgeAlignedTableWidget()
        table.setColumnCount(8)
        table.setHorizontalHeaderLabels(
            [tr(key, default) for key, default in OthersJobsTable._HEADERS]
        )
        table.horizontalHeader().setVisible(False)
        table.verticalHeader().setVisible(False)
        table.setBorderVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setWordWrap(False)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        hdr = table.horizontalHeader()
        hdr.setStretchLastSection(False)
        for col in range(8):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setMinimumSectionSize(42)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        table.setRowCount(0)
        return table

    def update_others_jobs(self, jobs: list, me: str) -> None:
        """jobs: _fetch_cluster_active_jobs 的结构化任务字典列表。"""
        me = str(me or "")
        others = [j for j in jobs or [] if str(j.get("user", "")) != me]
        mine = [j for j in jobs or [] if str(j.get("user", "")) == me]
        self._update_table(self._others_table, others, "others")
        self._update_table(self._mine_table, mine, "mine")

    def _update_table(self, table: EdgeAlignedTableWidget, tasks: list, key: str) -> None:
        rows = [
            [
                str(t.get("user", "")),
                str(t.get("jobid", "")),
                str(t.get("partition", "")),
                str(t.get("name", "")),
                str(t.get("state", "")),
                str(t.get("time", "")),
                str(t.get("nodes", "")),
                str(t.get("cpus", "")),
            ]
            for t in tasks
        ]
        value_sig = tuple(tuple(r) for r in rows)
        struct_sig = tuple(tuple(r[:5] + r[6:]) for r in rows)  # 不含运行时间列
        sig_attr, struct_attr = f"_{key}_sig", f"_{key}_struct"
        if value_sig == getattr(self, sig_attr):
            return
        setattr(self, sig_attr, value_sig)
        if not rows:
            table.setRowCount(0)
            return
        if struct_sig == getattr(self, struct_attr):
            self._update_times(table, rows)
            return
        setattr(self, struct_attr, struct_sig)
        table.setUpdatesEnabled(False)
        try:
            table.setRowCount(len(rows) + 1)
            for col, (hkey, htext) in enumerate(OthersJobsTable._HEADERS):
                item = QTableWidgetItem(tr(hkey, htext))
                if col == 0:
                    align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                elif col in (5,):
                    align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                else:
                    align = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
                item.setTextAlignment(align)
                table.setItem(0, col, item)
            aligns = [
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            ]
            for i, parts in enumerate(rows, start=1):
                for col, (text, align) in enumerate(zip(parts, aligns)):
                    item = QTableWidgetItem(str(text))
                    item.setTextAlignment(align)
                    table.setItem(i, col, item)
            table.expand_to_contents(minimum_height=60, extra_height=6)
        finally:
            table.setUpdatesEnabled(True)

    def _update_times(self, table: EdgeAlignedTableWidget, rows: list) -> None:
        table.setUpdatesEnabled(False)
        try:
            for i, parts in enumerate(rows, start=1):
                item = table.item(i, 5)
                if item is not None and item.text() != str(parts[5]):
                    item.setText(str(parts[5]))
        finally:
            table.setUpdatesEnabled(True)


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
        self.setStyleSheet(
            "QWidget#cluster_monitor_interface { background: transparent; border: none; }"
        )
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

        # ── 左侧：个人任务队列 + 空闲资源（两张卡片，可滚动）──────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 5, 10)
        left_layout.setSpacing(0)
        left_scroll = NoHScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_scroll.setStyleSheet(
            """
            QScrollArea {
                background-color: transparent;
                border: none;
                margin: 0px;
                padding: 0px;
            }
            QScrollArea > QWidget > QWidget {
                margin: 0px;
                padding: 0px;
            }
            """
        )
        left_content = QWidget()
        left_content.setStyleSheet("QWidget { background-color: transparent; margin: 0px; padding: 0px; }")
        left_content_layout = QVBoxLayout(left_content)
        left_content_layout.setContentsMargins(0, 0, 0, 0)
        left_content_layout.setSpacing(10)
        self._cluster_jobs_panel = ClusterJobsTable(left_content)
        self._idle_panel = IdleResourcesTable(left_content)
        left_content_layout.addWidget(self._cluster_jobs_panel)
        left_content_layout.addWidget(self._idle_panel)
        left_content_layout.addStretch(1)
        left_scroll.setWidget(left_content)
        left_layout.addWidget(left_scroll)

        # ── 右侧：状态行 + 集群任务列表(4/5，上) + 日志(1/5，下)────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(5, 1, 10, 11)
        right_layout.setSpacing(6)
        self._status_label = QLabel(
            tr("cm_status_disconnected", "未连接（每秒自动重连）")
        )
        self._status_label.setStyleSheet("font-weight: bold; color: #E08A00;")
        right_layout.addWidget(self._status_label)
        self._others_jobs_panel = OthersJobsTable(right)
        right_layout.addWidget(self._others_jobs_panel, 4)
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
        self._log.setStyleSheet(self._log_style())
        right_layout.addWidget(self._log, 1)

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
        persistent = self._remote_vm._client

        def _collect(cfg):
            status = run_server_status(cfg, client=persistent)
            try:
                c, _owns = _acquire(cfg, persistent)
                me = _resolve_remote_username(cfg, c)
                jobs, _source = _fetch_cluster_active_jobs(
                    c, CoreLogger(callback=lambda _m: None)
                )
            except Exception:
                jobs, me = [], ""
            return status, (jobs, me)

        self._runner.run(
            lambda: _collect(cfg),
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
        if result is None or not isinstance(result, tuple) or len(result) != 2:
            return
        status, (jobs, me) = result
        data = getattr(status, "data", None)
        if isinstance(data, dict):
            self._cluster_jobs_panel.update_cluster_jobs(data.get("cpu", []) or [])
            self._idle_panel.update_idle(data.get("idle", []) or [])
            self._set_status(connected=True)
        self._others_jobs_panel.update_others_jobs(jobs or [], me or "")
        if not getattr(status, "success", True):
            # [EN] Connection is dead: stay disconnected; the next tick will detect
            # is_connected=False and auto-reconnect. Do NOT close the shared client
            # here — the home page polls through the same persistent connection.
            # 连接已失效：保持未连接，下个 tick 检测 is_connected=False 后自动重连。
            # 不要在这里 close 共享连接——主页轮询也复用同一个持久化连接。
            self._set_status(disconnected=True)

    def _log_style(self) -> str:
        try:
            from qfluentwidgets import isDarkTheme

            dark = bool(isDarkTheme())
        except Exception:
            dark = False
        if dark:
            return (
                "QTextEdit { background-color: #2d2d2d !important;"
                " border: 0.5px solid #404040 !important;"
                " border-radius: 4px; padding-left: 2px;"
                " color: #FFFFFF !important; }"
                " QTextEdit:focus { border: 0.5px solid #404040 !important; padding-left: 2px; }"
                " QTextEdit:hover { border: 0.5px solid #404040 !important; padding-left: 2px; }"
            )
        return (
            "QTextEdit { background-color: transparent;"
            " border: 0.5px solid #D0D0D0 !important;"
            " border-radius: 4px; padding-left: 2px;"
            " color: #000000 !important; }"
            " QTextEdit:focus { border: 0.5px solid #D0D0D0 !important; padding-left: 2px; }"
            " QTextEdit:hover { border: 0.5px solid #D0D0D0 !important; padding-left: 2px; }"
        )

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
