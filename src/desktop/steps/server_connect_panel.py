"""第五步：连接服务器 面板（主页步骤区）。

连接后内嵌显示集群作业运行情况和任务队列，仿照 src 旧版实现。

[EN] Step 5: Connect to server panel (home step area).
After connecting, embedded cluster job overview and task queue are displayed, following the src legacy implementation.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import ComboBox, LineEdit, PrimaryPushButton

from ..components import styles
from ..components.combo_box import left_align_combo_text
from ..components.header_card import create_header_card
from ..components.table_widget import EdgeAlignedTableWidget
from ..components.validators import int_validator
from workflows.domain.config_models import PipelineConfig
from workflows.support.translations import tr

_TITLE_KEY = "step6_title"
_TITLE_DEFAULT = "第五步：连接服务器"

# [EN] ── Task state mapping ────────────────────────────────────────────────────────
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
    # [EN] Connect to server + cluster jobs + task queue + cancel task.
    """连接服务器 + 集群作业 + 任务队列 + 取消任务。"""

    def __init__(
        self,
        parent: QWidget,
        *,
        create_button: Callable[[str, Callable[..., object]], PrimaryPushButton],
        input_style: Callable[[], str],
        combo_style: Callable[[], str],
        connect: Callable[[], None],
        confirm_slurm: Callable[[], None],
        inject_ntfy: Callable[[], None],
        watch_job_ntfy: Callable[[], None],
        node_status: Callable[[], None],
        cancel: Callable[[], None],
    ) -> None:
        self._input_style = input_style
        self._combo_style = combo_style
        self.fields: dict[str, LineEdit] = {}
        self.field_labels: dict[str, QLabel] = {}

        self._group, layout = create_header_card(
            parent,
            f"{tr(_TITLE_KEY, _TITLE_DEFAULT)}  {tr('step6_not_connected', '[未连接]')}",
        )
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        self._group.viewLayout.setContentsMargins(11, 10, 11, 12)

        # [EN] ── Connect button ────────────────────────────────────────────────────
        # ── 连接按钮 ────────────────────────────────────────────────────
        self.connect_button = create_button(tr("step6_connect", "连接服务器"), connect)
        layout.addWidget(self.connect_button)

        # [EN] ── Cluster jobs title ────────────────────────────────────────────
        # ── 集群作业标题 ────────────────────────────────────────────
        self._cpu_title = self._build_section_title(
            tr("step6_cluster_jobs", "集群作业")
        )
        layout.addWidget(self._cpu_title)

        # [EN] ── Cluster jobs table ────────────────────────────────────────────
        # ── 集群作业表格 ────────────────────────────────────────────
        self._cpu_table = EdgeAlignedTableWidget()
        self._cpu_table.setColumnCount(4)
        self._cpu_table.setHorizontalHeaderLabels(
            [tr("cluster_col_user", "用户"), tr("cluster_col_cpus", "CPU数"),
             tr("cluster_col_nodes", "节点"), tr("cluster_col_elapsed", "时间")]
        )
        self._cpu_table.horizontalHeader().setVisible(False)
        self._cpu_table.verticalHeader().setVisible(False)
        self._cpu_table.setBorderVisible(False)
        self._cpu_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._cpu_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._cpu_table.setWordWrap(False)
        hdr = self._cpu_table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setMinimumSectionSize(42)
        vhdr = self._cpu_table.verticalHeader()
        vhdr.setVisible(False)
        vhdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._cpu_table.setContentsMargins(0, 0, 0, 0)
        self._cpu_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._cpu_table.setRowCount(0)
        self._cpu_table.setVisible(False)
        layout.addWidget(self._cpu_table)

        # [EN] ── Task queue title ────────────────────────────────────────────────
        # ── 任务队列标题 ────────────────────────────────────────────────
        self._queue_title = self._build_section_title(
            tr("step6_queue_ranking", "任务队列 占用排行")
        )
        layout.addWidget(self._queue_title)

        # [EN] ── Task queue container (dynamically add cards)────────────────────────────────
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

        # [EN] ── Cancel task section ────────────────────────────────────────────────
        # ── 取消任务区域 ────────────────────────────────────────────────
        self._cancel_widget = QWidget()
        cancel_row = QHBoxLayout(self._cancel_widget)
        cancel_row.setContentsMargins(0, 10, 0, 0)
        cancel_row.setSpacing(8)
        self.job_edit = LineEdit()
        self.job_edit.setStyleSheet(input_style())
        self.job_edit.setPlaceholderText(tr("enter_jobid_placeholder", "SLURM 任务号"))
        cancel_row.addWidget(self.job_edit, 1)
        cancel_row.addWidget(create_button(tr("step6_watch_job_ntfy", "监听此任务"), watch_job_ntfy))
        cancel_row.addWidget(create_button(tr("cancel_task", "取消任务"), cancel))
        layout.addWidget(self._cancel_widget)

        self._idle_title = self._build_section_title(
            tr("step6_idle_resources", "空闲资源")
        )
        layout.addWidget(self._idle_title)
        self._idle_table = EdgeAlignedTableWidget()
        self._idle_table.setColumnCount(3)
        self._idle_table.setHorizontalHeaderLabels(
            [
                tr("idle_col_cpu", "CPU"),
                tr("idle_col_nodes", "节点数"),
                tr("idle_col_cores", "核数"),
            ]
        )
        self._idle_table.horizontalHeader().setVisible(False)
        self._idle_table.verticalHeader().setVisible(False)
        self._idle_table.setBorderVisible(False)
        self._idle_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._idle_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._idle_table.setWordWrap(False)
        idle_hdr = self._idle_table.horizontalHeader()
        idle_hdr.setStretchLastSection(False)
        for col in range(3):
            idle_hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        idle_hdr.setMinimumSectionSize(36)
        self._idle_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(self._idle_table)

        self._slurm_title = self._build_section_title(
            tr("step4_slurm_config", "Slurm 配置")
        )
        layout.addWidget(self._slurm_title)
        self._slurm_form = QWidget()
        slurm_grid = QGridLayout(self._slurm_form)
        slurm_grid.setContentsMargins(0, 0, 0, 0)
        slurm_grid.setSpacing(10)
        slurm_grid.setColumnStretch(0, 0)
        slurm_grid.setColumnStretch(1, 1)
        self.st_combo = ComboBox()
        self.st_combo.setStyleSheet(combo_style())
        left_align_combo_text(self.st_combo)
        self.st_label = self._field_label(tr("step4_st_version", "ST 版本："))
        slurm_grid.addWidget(self.st_label, 0, 0)
        slurm_grid.addWidget(self.st_combo, 0, 1)
        self._text_line(slurm_grid, 1, tr("step5_slurm_job_name", "作业名："), "slurm_job_name")
        self.cpu_combo = ComboBox()
        self.cpu_combo.setStyleSheet(combo_style())
        left_align_combo_text(self.cpu_combo)
        self.cpu_label = self._field_label(tr("step4_server_cpu", "服务器 CPU："))
        slurm_grid.addWidget(self.cpu_label, 2, 0)
        slurm_grid.addWidget(self.cpu_combo, 2, 1)
        self._display_line(slurm_grid, 3, tr("step4_total_cores", "总核数:"), "slurm_cores")
        self._display_line(slurm_grid, 4, tr("step4_node_num", "节点数:"), "slurm_nodes")
        layout.addWidget(self._slurm_form)

        self._confirm_slurm_widget = QWidget()
        confirm_slurm_layout = QVBoxLayout(self._confirm_slurm_widget)
        confirm_slurm_layout.setContentsMargins(0, 8, 0, 0)
        confirm_slurm_layout.setSpacing(8)
        self.confirm_slurm_button = create_button(
            tr("step6_confirm_slurm", "确认 Slurm 配置"),
            confirm_slurm,
        )
        confirm_slurm_layout.addWidget(self.confirm_slurm_button)
        self.inject_ntfy_button = create_button(
            tr("step6_inject_ntfy", "常驻 ntfy 监听"),
            inject_ntfy,
        )
        confirm_slurm_layout.addWidget(self.inject_ntfy_button)
        self.node_status_button = create_button(
            tr("step6_node_status", "查看节点状态"),
            node_status,
        )
        confirm_slurm_layout.addWidget(self.node_status_button)
        layout.addWidget(self._confirm_slurm_widget)

        self._group.viewLayout.addLayout(layout)
        self.widget = self._group
        self.set_connected(False)
        self.update_idle_resources([])

    # [EN] ── Public API ──────────────────────────────────────────────────────────
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
        self._cancel_widget.setVisible(False)  # [EN] Visibility controlled by update_queue_table
        # 由 update_queue_table 控制显隐
        self._idle_title.setVisible(connected)
        self._idle_table.setVisible(connected)
        self._slurm_title.setVisible(connected)
        self._slurm_form.setVisible(connected)
        self._confirm_slurm_widget.setVisible(connected)
        if connected and self._idle_table.rowCount() == 0:
            self.update_idle_resources([])
        if not connected:
            self._hide_cpu_and_queue()

    def update_cpu_table(self, rows: list) -> None:
        # [EN] Update cluster jobs table. rows: [[user, cpus, nodes, elapsed], ...]
        """更新集群作业表格。rows: [[user, cpus, nodes, elapsed], ...]"""
        valid = []
        for row in rows:
            parts = [str(p) for p in row] if isinstance(row, (list, tuple)) else str(row).split()
            if len(parts) >= 4:
                valid.append(parts[:4])
        if not valid:
            self._cpu_table.setRowCount(0)
            self._cpu_title.setVisible(False)
            self._cpu_table.setVisible(False)
            return

        # [EN] Manual header row (row 0) + data rows, matching original style
        # 手动表头行（第 0 行）+ 数据行，与原有风格一致
        header_labels = [
            tr("cluster_col_user", "用户"),
            tr("cluster_col_cpus", "CPU数"),
            tr("cluster_col_nodes", "节点"),
            tr("cluster_col_elapsed", "时间"),
        ]
        self._cpu_table.setRowCount(len(valid) + 1)
        for col, text in enumerate(header_labels):
            item = QTableWidgetItem(text)
            # [EN] User header left-aligned, others centered
            # User 表头靠左，其余居中
            if col == 0:
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
            else:
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
                )
            self._cpu_table.setItem(0, col, item)

        # [EN] Column alignment: User(left), CPUs(center), Nodes(center), Time(right)
        # 列对齐：用户(左), CPU数(居中), 节点(居中), 时间(右)
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
                self._cpu_table.setItem(i, col, item)

        self._cpu_table.expand_to_contents(minimum_height=60, extra_height=6)
        self._cpu_table.resizeColumnToContents(3)
        self._cpu_table.setColumnWidth(3, max(self._cpu_table.columnWidth(3), 112))
        self._cpu_title.setVisible(True)
        self._cpu_table.setVisible(True)

    def update_idle_resources(self, rows: list) -> None:
        """Update idle resource table. rows: [{cpu, nodes, cores, max_cores_per_node}, ...]."""
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
                max_per_node = int(row.get("max_cores_per_node") or 0)
            except (TypeError, ValueError):
                continue
            if nodes <= 0 or cores <= 0:
                continue
            valid.append(
                {
                    "cpu": cpu,
                    "nodes": nodes,
                    "cores": cores,
                    "max_cores_per_node": max_per_node,
                }
            )
        valid.sort(key=lambda item: item["cores"], reverse=True)
        self._idle_rows = valid

        header_labels = [
            tr("idle_col_cpu", "CPU"),
            tr("idle_col_nodes", "节点数"),
            tr("idle_col_cores", "核数"),
        ]
        self._idle_table.setRowCount(len(valid) + 1)
        for col, text in enumerate(header_labels):
            item = QTableWidgetItem(text)
            if col == 0:
                align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            elif col == 2:
                align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            else:
                align = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
            item.setTextAlignment(align)
            self._idle_table.setItem(0, col, item)

        aligns = [
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        ]
        for row_index, row in enumerate(valid, start=1):
            values = [row["cpu"], row["nodes"], row["cores"]]
            for col, (value, align) in enumerate(zip(values, aligns)):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(align)
                self._idle_table.setItem(row_index, col, item)
        self._idle_table.expand_to_contents(minimum_height=52, extra_height=6)

    def idle_resources(self) -> list[dict]:
        return list(getattr(self, "_idle_rows", []))

    def render_slurm(self, config: PipelineConfig) -> None:
        self.fields["slurm_job_name"].setText(str(config.slurm.job_name or config.workdir.path.name))
        self.fields["slurm_cores"].setText(str(config.slurm.cores))
        self.fields["slurm_nodes"].setText(str(config.slurm.nodes))
        self._replace_combo_items(self.st_combo, list(config.presets.server_st), config.slurm.server_st or config.ww3.st)
        self._replace_combo_items(self.cpu_combo, config.slurm.cpu_group, config.slurm.cpu)

    def ww3_overrides(self) -> dict[str, str]:
        return {}

    def slurm_overrides(self) -> dict[str, str]:
        return {
            "job_name": self.fields["slurm_job_name"].text().strip(),
            "cpu": self.cpu_combo.currentText().strip(),
            "cores": self.fields["slurm_cores"].text().strip(),
            "nodes": self.fields["slurm_nodes"].text().strip(),
            "server_st": self.st_combo.currentText().strip(),
        }

    def apply_slurm_resources(self, *, cpu: str, cores: int, nodes: int) -> None:
        cpu = str(cpu).strip()
        if cpu:
            items = [self.cpu_combo.itemText(i) for i in range(self.cpu_combo.count())]
            if cpu not in items:
                self.cpu_combo.addItem(cpu)
            self.cpu_combo.setCurrentText(cpu)
        self.fields["slurm_cores"].setText(str(max(1, int(cores))))
        self.fields["slurm_nodes"].setText(str(max(1, int(nodes))))

    def replace_cpu_options_if_changed(self, values: list[str]) -> None:
        server_values = [str(value).strip() for value in values if str(value).strip()]
        if not server_values:
            return
        deduped = list(dict.fromkeys(server_values))
        current = [self.cpu_combo.itemText(i) for i in range(self.cpu_combo.count())]
        if current == deduped:
            return
        selected = self.cpu_combo.currentText().strip()
        self.cpu_combo.clear()
        self.cpu_combo.addItems(deduped)
        self.cpu_combo.setCurrentText(selected if selected in deduped else deduped[0])

    def update_queue_table(self, lines: list) -> None:
        # [EN] Update task queue display. lines: squeue output lines.
        """更新任务队列显示。lines: squeue 输出行列表。"""
        tasks = self._parse_squeue_lines(lines)
        if not tasks:
            self._clear_queue_display()
            self._queue_title.setVisible(False)
            self._cancel_widget.setVisible(False)
            return

        # [EN] Check whether to rebuild cards
        # 检查是否需要重建卡片
        existing_count = self._queue_layout.count()
        if existing_count != len(tasks):
            self._rebuild_queue_cards(tasks)
        else:
            self._update_existing_queue_cards(tasks)

        self._queue_title.setVisible(True)
        self._queue_container.setVisible(True)
        self._cancel_widget.setVisible(True)

    # [EN] ── Internal methods ──────────────────────────────────────────────────────────
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
        self._idle_title.setVisible(False)
        self._idle_table.setVisible(False)
        self._slurm_title.setVisible(False)
        self._slurm_form.setVisible(False)
        self._confirm_slurm_widget.setVisible(False)
        self._idle_table.setRowCount(0)
        self._idle_rows = []

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(styles.label_style())
        label.setWordWrap(True)
        label.setMinimumHeight(28)
        label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        return label

    @staticmethod
    def _expand_field(widget: QWidget) -> None:
        widget.setMinimumWidth(0)
        widget.setMaximumWidth(16777215)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _display_line(self, grid: QGridLayout, row: int, label: str, key: str) -> None:
        self._text_line(grid, row, label, key, integer=True)

    def _text_line(self, grid: QGridLayout, row: int, label: str, key: str, *, integer: bool = False) -> None:
        field = LineEdit()
        field.setProperty("transparent", False)
        field.setStyleSheet(self._input_style())
        field.setMinimumHeight(33)
        if integer:
            field.setValidator(int_validator(1))
        self._expand_field(field)
        field_label = self._field_label(label)
        grid.addWidget(field_label, row, 0)
        grid.addWidget(field, row, 1)
        self.fields[key] = field
        self.field_labels[key] = field_label

    @staticmethod
    def _replace_combo_items(combo: ComboBox, values: list[str], selected: str) -> None:
        next_values = [str(value) for value in values if str(value)]
        if selected and selected not in next_values:
            next_values = [*next_values, selected]
        combo.clear()
        combo.addItems(next_values)
        combo.setCurrentText(selected)

    def _parse_squeue_lines(self, lines: list) -> list[dict]:
        # [EN] Parse squeue lines, return list of task dicts.
        """解析 squeue 行，返回任务字典列表。"""
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

    def _create_task_card(self, task: dict) -> EdgeAlignedTableWidget:
        fields = [
            (tr("queue_jobid", "JobID:"), task.get("jobid", "")),
            (tr("queue_cpu", "CPU:"), task.get("partition", "")),
            (tr("queue_job_name", "作业名:"), task.get("name", "")),
            (tr("queue_status", "状态:"), task.get("state", "")),
            (tr("queue_runtime", "已运行:"), task.get("time", "")),
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

    def _update_existing_queue_cards(self, tasks: list[dict]) -> None:
        # [EN] Only update existing card contents, without rebuilding.
        """仅更新已有卡片的内容，不重建。"""
        fields_keys = ["jobid", "partition", "name", "state", "time", "nodes", "cpus", "nodelist"]
        labels = [
            tr("queue_jobid", "JobID:"),
            tr("queue_cpu", "CPU:"),
            tr("queue_job_name", "作业名:"),
            tr("queue_status", "状态:"),
            tr("queue_runtime", "已运行:"),
            tr("queue_node_num", "节点数:"),
            tr("queue_cpus", "核数:"),
            tr("queue_node_list", "节点列表:"),
        ]
        for i in range(min(self._queue_layout.count(), len(tasks))):
            item = self._queue_layout.itemAt(i)
            widget = item.widget() if item else None
            if not isinstance(widget, EdgeAlignedTableWidget):
                continue
            task = tasks[i]
            for row, (lbl, key) in enumerate(zip(labels, fields_keys)):
                lbl_item = widget.item(row, 0)
                if lbl_item:
                    lbl_item.setText(lbl)
                val_item = widget.item(row, 1)
                if val_item:
                    val_item.setText(str(task.get(key, "")))
            widget.expand_to_contents(minimum_height=80, extra_height=10)

    def _clear_queue_display(self) -> None:
        while self._queue_layout.count() > 0:
            item = self._queue_layout.takeAt(0)
            if item:
                w = item.widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()
