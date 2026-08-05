"""集群监控页：左侧 个人任务队列 + 空闲资源 两张卡片，右侧 日志(1/5) + 全集群任务列表(4/5)。

打开页面自动连接 SSH；断开后每秒自动尝试重连；列表每秒刷新。
左侧 = 集群作业表（sacct -a 所有用户）+ 空闲资源列表（与主页第五步样式一致）；
右侧 = 其他用户任务详细列表（run_cluster_jobs_log）+ 日志（1/5）。

[EN] Cluster monitor page: left = cluster jobs table + idle resources cards;
right = other-users job detail list (run_cluster_jobs_log) + log (1/5).
Auto-connects on open and auto-reconnects every second when SSH drops.
"""

from __future__ import annotations

from PyQt6.QtCore import QSize, QTimer, Qt
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
from qfluentwidgets.common.style_sheet import addStyleSheet
from qfluentwidgets.components.widgets.scroll_bar import SmoothScrollDelegate
from workflows.application.remote_ops import (
    _acquire,
    _fetch_cluster_active_jobs,
    _resolve_remote_username,
    run_server_status,
)
from workflows.support.logging import CoreLogger
from workflows.support.translations import tr

# 卡片固定开销：头部(48) + 分隔线(1) + viewLayout 上下边距(10+12) + 边框(2)。
# HeaderCardWidget 的 sizeHint 不反映内容高度，需显式按内容设置卡片高度。
_CARD_EXTRA = 48 + 1 + 10 + 12 + 2

# 日志卡最大高度：log 内容区 100（约 4-5 行）+ 头部 48 + 分隔线 1 + viewLayout 边距 22 + 边框 2。
# 自适应：内容少时卡片矮，内容多时不超过此值；窗口拉高时高度留给任务列表。
class _ContentSizedScrollArea(NoHScrollArea):
    """QScrollArea 的 sizeHint 默认是视口建议（≈(256,192)），布局据此分配高度
    会导致内容被压缩/溢出。这里让 sizeHint 反映所承载内容的实际大小。"""

    def sizeHint(self) -> QSize:
        widget = self.widget()
        if widget is not None:
            return widget.sizeHint() + QSize(0, 2 * self.frameWidth())
        return super().sizeHint()


def _section_title(parent: QWidget, text: str) -> QWidget:
    """带两侧分隔线的区块标题（样式同主页第五步）。"""
    container = QWidget(parent)
    h = QHBoxLayout(container)
    h.setContentsMargins(0, 6, 0, 4)
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
    # 固定为内容固有高度：默认 Preferred 策略会在卡片布局里被拉伸，
    # 造成标题上下出现大间距
    container.setFixedHeight(container.sizeHint().height())
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
        self._table.expand_to_contents(extra_height=6, max_row_height=32)
        self._card, card_layout = create_header_card(
            self, tr("cm_cluster_jobs", "集群作业（所有用户）")
        )
        card_layout.setSpacing(4)
        card_layout.addWidget(self._table)
        # [EN] Mount the returned layout into the card body (required for display).
        # 必须把返回的 layout 挂进卡片 body，否则表格永远不会显示。
        self._card.viewLayout.setContentsMargins(11, 10, 11, 12)
        self._card.viewLayout.addLayout(card_layout)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._card)
        self._signature: tuple = ()
        self._struct_signature: tuple = ()
        self._refresh_card_height()

    def _refresh_card_height(self) -> None:
        """卡片高度跟随表格内容，避免表格溢出卡片（HeaderCardWidget sizeHint 失真）。"""
        self._card.setFixedHeight(self._table.height() + _CARD_EXTRA)
        # 内容高度变化后显式激活祖先布局：QScrollArea 的 widget 高度由
        # setWidgetResizable 管理，不激活时 sizeHint 变化不会向上传播
        w: QWidget = self
        while w is not None:
            lay = w.layout()
            if lay is not None:
                lay.activate()
            w = w.parentWidget()

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
            self._table.expand_to_contents(extra_height=6, max_row_height=32)
            self._refresh_card_height()
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
            self._table.expand_to_contents(minimum_height=60, extra_height=6, max_row_height=32)
            self._table.resizeColumnToContents(3)
            self._table.setColumnWidth(3, max(self._table.columnWidth(3), 112))
            self._refresh_card_height()
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
        self._table.setRowCount(0)
        self._table.expand_to_contents(extra_height=6, max_row_height=32)
        self._card, card_layout = create_header_card(
            self, tr("cm_idle_resources", "空闲资源")
        )
        card_layout.setSpacing(4)
        card_layout.addWidget(self._table)
        self._card.viewLayout.setContentsMargins(11, 10, 11, 12)
        self._card.viewLayout.addLayout(card_layout)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._card)
        self._signature: tuple = ()
        self._rows: list[dict] = []
        self._refresh_card_height()

    def _refresh_card_height(self) -> None:
        """卡片高度跟随表格内容，避免表格溢出卡片（HeaderCardWidget sizeHint 失真）。"""
        self._card.setFixedHeight(self._table.height() + _CARD_EXTRA)
        # 内容高度变化后显式激活祖先布局：QScrollArea 的 widget 高度由
        # setWidgetResizable 管理，不激活时 sizeHint 变化不会向上传播
        w: QWidget = self
        while w is not None:
            lay = w.layout()
            if lay is not None:
                lay.activate()
            w = w.parentWidget()

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
                self._table.expand_to_contents(extra_height=6, max_row_height=32)
                self._refresh_card_height()
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
            self._table.expand_to_contents(minimum_height=52, extra_height=6, max_row_height=32)
            self._refresh_card_height()
        finally:
            self._table.setUpdatesEnabled(True)


class OthersJobsTable(QWidget):
    """其他用户/本人任务详细表格（结构化数据，非文本日志）。"""

    # 任务多时表格限高、内部滚动，避免把页面拉成“巨大背景”
    _TABLE_MAX_HEIGHT = 360

    # 最小可读宽度（px）：包含 Fluent 表格的文本留白，避免短文本也显示为省略号。
    _COL_MIN_WIDTH = {
        1: 64,   # JobID
        2: 64,   # 分区
        3: 84,   # 作业名
        4: 76,   # 状态
        5: 92,   # 运行时间
        6: 56,   # 节点
        7: 56,   # 核数
    }

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
        self._card, card_layout = create_header_card(self, "")
        # 卡片宽/高显式 Expanding：占满右侧 5:1 区域，表格空行区在表格内部
        # （标准表格样式），不再按内容收缩成内容宽/内容高。
        self._card.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        card_layout.setSpacing(4)
        self._others_table = self._make_table(expand_v=True)
        card_layout.addWidget(self._others_table)
        self._my_jobs_title = _section_title(self, tr("cm_my_jobs", "本人任务"))
        card_layout.addWidget(self._my_jobs_title)
        self._mine_table = self._make_table(expand_v=False)
        card_layout.addWidget(self._mine_table, 0)
        # 底部弹簧吸收剩余空间：上方（others 表 / My Jobs）保持紧凑排列，
        # 避免 QVBoxLayout 把多余空间分散到各 item 之间（造成大间距）
        card_layout.addStretch(1)
        # 隐藏标题行，仅保留卡片背景（与左侧卡片同款）
        self._card.headerView.setVisible(False)
        self._card.separator.setVisible(False)
        self._card.viewLayout.setContentsMargins(11, 10, 11, 12)
        self._card.viewLayout.addLayout(card_layout)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._card)
        self._others_sig: tuple = ()
        self._others_struct: tuple = ()
        self._mine_sig: tuple = ()
        self._mine_struct: tuple = ()
        self._refresh_card_height()

    def _refresh_card_height(self) -> None:
        """卡片高度交给布局撑满（不再按内容 setFixedHeight）：
        表格占满 5:1 区域高度，空行区在表格内部。"""
        w: QWidget = self
        while w is not None:
            lay = w.layout()
            if lay is not None:
                lay.activate()
            w = w.parentWidget()

    @staticmethod
    def _make_table(expand_v: bool = True) -> EdgeAlignedTableWidget:
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
        # 收紧 Fluent 默认的水平内边距；列宽由 sizeHintForColumn 计算，
        # 文字仍完整显示，同时避免八列因为累积留白而无谓横向滚动。
        addStyleSheet(table, "QTableView::item { padding-left: 2px; padding-right: 2px; }")
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        hdr = table.horizontalHeader()
        hdr.setStretchLastSection(False)
        # 列宽完全由 _apply_col_widths 控制，避免布局后回退到最小值。
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        for col in range(1, 8):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
        hdr.setMinimumSectionSize(1)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        vpolicy = QSizePolicy.Policy.Expanding if expand_v else QSizePolicy.Policy.Maximum
        table.setSizePolicy(QSizePolicy.Policy.Expanding, vpolicy)
        # qfluentwidgets 用自定义浮动滚动条接管原生滚动条（原生恒 AlwaysOff），
        # 需经 SmoothScrollDelegate 开启滚动显示；横向始终关闭。
        table.scrollDelagate.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        if expand_v:
            table.scrollDelagate.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setRowCount(0)
        # 统一行高 32px：内容高计算与渲染一致（qfluentwidgets 默认行高 ~39px，
        # 会造成“内容高算小、实际渲染更高”而出现无谓滚动条）
        table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        table.verticalHeader().setDefaultSectionSize(32)
        return table

    def update_others_jobs(self, jobs: list, me: str) -> None:
        """jobs: _fetch_cluster_active_jobs 的结构化任务字典列表。"""
        me = str(me or "")
        others = [j for j in jobs or [] if str(j.get("user", "")) != me]
        mine = [j for j in jobs or [] if str(j.get("user", "")) == me]
        # 本人无任务时隐藏标题与表格，避免大片空白
        has_mine = bool(mine)
        self._my_jobs_title.setVisible(has_mine)
        self._mine_table.setVisible(has_mine)
        self._update_table(self._others_table, others, "others")
        self._update_table(self._mine_table, mine, "mine")
        self._refresh_card_height()
        # 数据更新后立即通知窗口重算右侧高度/列宽，不依赖外部调用时机
        # (避免 viewport 未就绪/回调链路中断时列表保持内容高)
        self._schedule_column_layout()
        self._notify_parent_height_refresh()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._schedule_column_layout()

    def _schedule_column_layout(self) -> None:
        """在 Qt 完成当前布局后，再按最终 viewport 宽度设置列宽。"""
        if getattr(self, "_column_layout_pending", False):
            return
        self._column_layout_pending = True
        QTimer.singleShot(0, self._apply_columns_after_layout)

    def _apply_columns_after_layout(self) -> None:
        self._column_layout_pending = False
        for table in (self._others_table, self._mine_table):
            if table.isVisible() and table.rowCount() > 0:
                self._apply_col_widths(table)

    def _notify_parent_height_refresh(self) -> None:
        """向上查找 ClusterMonitorInterface 并触发右侧高度重算(幂等)。"""
        w: QWidget = self.parentWidget()
        while w is not None:
            refresh = getattr(w, "_refresh_others_height", None)
            if refresh is not None:
                try:
                    refresh()
                except Exception:
                    pass
                return
            w = w.parentWidget()

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
            table.scrollDelagate.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            if key == "others":
                # 空表也紧凑：高度 = 表头 + 边距，My Jobs 紧跟其后
                table.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
                )
                table.setFixedHeight(33)
            self._refresh_card_height()
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
            # 列宽分配（其他列上限 / 用户列展开 / 超宽压缩）
            self._apply_col_widths(table)
        finally:
            table.setUpdatesEnabled(True)
        if key == "others":
            # 内容少时高度=内容高（紧凑，My Jobs 紧跟其后）；
            # 内容多时高度=可用区域高，表内滚动（高度由 _fit_others_height 计算）
            # 第 0 行是表头数据行（QHeaderView 已隐藏），行高统一 32
            content_h = table.rowCount() * 32 + 6
            table.setProperty("_content_h", content_h)
            QTimer.singleShot(0, self._fit_others_height)
        else:
            # My Jobs 保持内容高（不撑满 5:1 区域），避免表格内大块空行区
            table.setMaximumHeight(16777215)
            table.expand_to_contents(extra_height=6, max_row_height=32)
        self._refresh_card_height()

    def _fit_others_height(self) -> None:
        """others 表高度 = min(内容高, 可用区域高)：
        内容少时紧凑（My Jobs 紧跟其后，无大间距）；
        内容多时取可用高度并在表内滚动（不撑大页面）。"""
        if not hasattr(self, "_card"):
            return
        ot = self._others_table
        content_h = int(ot.property("_content_h") or 0)
        # 先激活祖先布局，保证 card_layout.geometry() 是最终几何
        w: QWidget = self
        while w is not None:
            lay = w.layout()
            if lay is not None:
                lay.activate()
            w = w.parentWidget()
        avail = 300
        vl = self._card.viewLayout
        if vl.count():
            lay = vl.itemAt(0).layout()
            if lay is not None:
                title_h = (
                    self._my_jobs_title.sizeHint().height()
                    if self._my_jobs_title.isVisible()
                    else 0
                )
                mt_h = (
                    self._mine_table.sizeHint().height()
                    if self._mine_table.isVisible()
                    else 0
                )
                avail = (
                    lay.geometry().height()
                    - title_h
                    - mt_h
                    - lay.spacing() * 3
                )
        h = max(min(content_h, avail), 40) if content_h > 0 else 40
        # 高度策略 Maximum：不参与剩余空间争抢（Expanding 会把受限后的
        # 多余空间分散到各 item 之间，造成“My Jobs 上方大间距”）；
        # 高度由 setFixedHeight 精确控制。
        ot.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        ot.setFixedHeight(h)
        if content_h > h:
            ot.scrollDelagate.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
        else:
            ot.scrollDelagate.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
        self._refresh_card_height()

    def _apply_col_widths(self, table: EdgeAlignedTableWidget) -> None:
        """按 Fluent 委托的真实 size hint 设置列宽。

        ``QFontMetrics`` 只会得到文字本身的宽度，未包含 Qt/Fluent
        在单元格内预留的边距，导致有空白时文字仍显示省略号。
        ``sizeHintForColumn`` 已包含该组件的最终绘制空间，因此能在
        保持列紧凑的同时完整显示表头和内容。
        """
        targets = {
            col: max(table.sizeHintForColumn(col), OthersJobsTable._COL_MIN_WIDTH[col])
            for col in range(1, 8)
        }
        user_w = max(table.sizeHintForColumn(0), 64)

        def apply_widths() -> None:
            table.setColumnWidth(0, user_w)
            for col in range(1, 8):
                table.setColumnWidth(col, targets[col])

        avail = max(table.viewport().width(), table.width())
        if avail < 200:
            # SSH 数据可能早于布局到达；先按真实内容宽度设置，布局完成后重算。
            apply_widths()
            QTimer.singleShot(0, lambda: self._apply_col_widths(table))
            return

        apply_widths()
        total = user_w + sum(targets.values())
        table.scrollDelagate.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if total > avail
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

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
        left.setStyleSheet("background: transparent;")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 5, 10)
        left_layout.setSpacing(0)
        left_scroll = _ContentSizedScrollArea()
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
        left_scroll.viewport().setAutoFillBackground(False)
        left_scroll.viewport().setStyleSheet("background: transparent;")
        left_content = QWidget()
        left_content_layout = QVBoxLayout(left_content)
        left_content_layout.setContentsMargins(0, 0, 0, 0)
        left_content_layout.setSpacing(10)
        self._cluster_jobs_panel = ClusterJobsTable(left_content)
        self._idle_panel = IdleResourcesTable(left_content)
        # 卡片保持内容紧凑高度，下方留给页面底色（与主页一致）；
        # 不要用 stretch 拉高卡片——会把表格强制拉伸出大片空白。
        left_content_layout.addWidget(self._cluster_jobs_panel)
        left_content_layout.addWidget(self._idle_panel)
        left_content_layout.addStretch(1)
        left_scroll.setWidget(left_content)
        left_layout.addWidget(left_scroll, 1)

        # ── 右侧：他人任务 + 本人任务 + 日志（可滚动）────────────────────
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(5, 1, 10, 11)
        right_layout.setSpacing(6)
        self._others_jobs_panel = OthersJobsTable(right_container)
        # 右侧布局 5:1：任务列表占 5 份、日志区占 1 份（日志 = 内容区 1/6）
        right_layout.addWidget(self._others_jobs_panel, 5)
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
        log_card, log_layout = create_header_card(right_container, "")
        # 同右卡：宽/高显式 Expanding，日志区高度 = 内容区 1/6（布局分配）
        log_card.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        log_layout.setSpacing(4)
        log_layout.addWidget(self._log)
        log_card.headerView.setVisible(False)
        log_card.separator.setVisible(False)
        log_card.viewLayout.setContentsMargins(11, 10, 11, 12)
        log_card.viewLayout.addLayout(log_layout)
        # 右侧布局 5:1：任务列表占 5 份、日志区占 1 份（日志内部滚动）
        right_layout.addWidget(log_card, 1)
        right_scroll = _ContentSizedScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_scroll.setStyleSheet(
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
        right_scroll.viewport().setAutoFillBackground(False)
        right_scroll.viewport().setStyleSheet("background: transparent;")
        # 与主页日志区一致的悬浮细滚动条（qfluentwidgets SmoothScrollBar）
        SmoothScrollDelegate(right_scroll)
        right_scroll.setWidget(right_container)
        right = right_scroll

        splitter.addWidget(left)
        splitter.addWidget(right)
        # 左侧资源区 33%、右侧任务/日志区 67%（与主页布局一致）
        splitter.setStretchFactor(0, 33)
        splitter.setStretchFactor(1, 67)
        # splitter 高度占满页面：表格空行区在表格内部，左右内容超高各自滚动
        splitter.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        page_scroll = _ContentSizedScrollArea()
        page_scroll.setWidgetResizable(True)
        page_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        page_scroll.setStyleSheet(
            "QScrollArea { background-color: transparent; border: none; }"
        )
        page_scroll.viewport().setAutoFillBackground(False)
        page_scroll.viewport().setStyleSheet("background: transparent;")
        page_container = QWidget()
        page_layout = QVBoxLayout(page_container)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(splitter, 1)  # splitter 占满整个页面高度
        page_scroll.setWidget(page_container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page_scroll)
        self._splitter = splitter

        def _apply_sizes() -> None:
            try:
                splitter.setSizes([400, 800])
                self._refresh_others_height()
            except RuntimeError:
                pass

        QTimer.singleShot(0, _apply_sizes)

    def _refresh_splitter_height(self) -> None:
        """splitter 高度由页面布局撑满窗口（不再按内容 setFixedHeight）：
        表格空行区在表格内部，内容超高由左右滚动区各自滚动。"""
        if not hasattr(self, "_splitter"):
            return
        lay = self.layout()
        if lay is not None:
            lay.activate()

    def _refresh_others_height(self) -> None:
        """数据/宽度变化后刷新卡片高度与列宽。

        表格高度跟随内容（紧凑），不再强制拉高到 6:1——拉高会在表格内产生
        大片空行、把 My Jobs 标题推到下方，且内容不超出时也会撑出滚动条。
        """
        if not hasattr(self, "_splitter"):
            return
        self._refresh_splitter_height()
        op = self._others_jobs_panel
        op._refresh_card_height()
        # 窗口宽度变化后重算列宽（窄窗口按比例压缩，避免横向滚动/列消失）
        op._apply_col_widths(op._others_table)
        if op._mine_table.isVisible():
            op._apply_col_widths(op._mine_table)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._refresh_others_height()

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
        # 页面每次显示都重算右侧列表列宽，弥补首次布局未就绪的场景
        self._refresh_others_height()

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
        # 静默连接：内部日志抑制，结果由 _on_connect_done 统一写一条
        self._runner.run(
            lambda: self._remote_vm.connect_test(cfg),
            self._on_connect_done,
        )

    def _on_connect_done(self, result: object) -> None:
        self._reconnecting = False
        if bool(getattr(result, "success", False)):
            self._append_log(tr("cm_reconnect_ok", "✔ 已连接服务器"))
        else:
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
        self._others_jobs_panel.update_others_jobs(jobs or [], me or "")
        self._refresh_others_height()

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

