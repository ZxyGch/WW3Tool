"""第五步：连接服务器 面板（主页步骤区）。

连接后内嵌显示集群作业运行情况和任务队列，仿照 src 旧版实现。

[EN] Step 5: Connect to server panel (home step area).
After connecting, embedded cluster job overview and task queue are displayed, following the src legacy implementation.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
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
from workflows.application.remote_ops import (
    format_slurm_memory_mb,
    suggest_slurm_config,
    suggest_slurm_mem_for_partition,
)
from workflows.support.translations import tr

_TITLE_KEY = "step6_title"
_TITLE_DEFAULT = "第五步：连接服务器"


def _idle_memory_text(row: dict) -> str:
    """Return the available node memory in Slurm's compact unit notation."""
    for key in ("free_mem_mb", "total_mem_mb"):
        try:
            value = int(row.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return format_slurm_memory_mb(value)
    return "-"


class ServerConnectPanel:
    # [EN] Connect to server + cluster jobs + task queue.
    """连接服务器 + 集群作业 + 任务队列。"""

    def __init__(
        self,
        parent: QWidget,
        *,
        create_button: Callable[[str, Callable[..., object]], PrimaryPushButton],
        input_style: Callable[[], str],
        combo_style: Callable[[], str],
        connect: Callable[[], None],
        confirm_slurm: Callable[[], None],
        node_status: Callable[[], None],
        log: Callable[[str], None] | None = None,
    ) -> None:
        self._input_style = input_style
        self._combo_style = combo_style
        self._log = log or (lambda _message: None)
        self._slurm_mem_user_edited = False
        self._idle_signature: tuple = ()
        self._idle_rows: list[dict] = []
        self._partition_mem_mb: dict[str, int] = {}
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



        self._idle_title = self._build_section_title(
            tr("step6_idle_resources", "空闲资源")
        )
        layout.addWidget(self._idle_title)
        self._idle_table = EdgeAlignedTableWidget()
        self._idle_table.setColumnCount(4)
        self._idle_table.setHorizontalHeaderLabels(
            [
                tr("idle_col_cpu", "分区"),
                tr("idle_col_node_names", "节点名"),
                tr("idle_col_cores", "可用核数"),
                tr("idle_col_free_memory", "节点空闲内存"),
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
        for col in range(4):
            idle_hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        idle_hdr.setMinimumSectionSize(36)
        self._idle_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._idle_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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
        self._server_st_versions: dict[str, str] = {}
        self.st_combo.setStyleSheet(combo_style())
        left_align_combo_text(self.st_combo)
        self.st_label = self._field_label(tr("step4_st_version", "ST 版本："))
        slurm_grid.addWidget(self.st_label, 0, 0)
        slurm_grid.addWidget(self.st_combo, 0, 1)
        self._text_line(slurm_grid, 1, tr("step5_slurm_job_name", "作业名："), "slurm_job_name")
        self.cpu_combo = ComboBox()
        self.cpu_combo.setPlaceholderText(tr("cpu_no_partition", "未从服务器解析到分区"))
        self.cpu_combo.setStyleSheet(combo_style())
        left_align_combo_text(self.cpu_combo)
        self.cpu_combo.currentTextChanged.connect(self._on_cpu_partition_changed)
        self.cpu_label = self._field_label(tr("step4_server_cpu", "分区："))
        slurm_grid.addWidget(self.cpu_label, 2, 0)
        slurm_grid.addWidget(self.cpu_combo, 2, 1)
        self._display_line(slurm_grid, 3, tr("step4_total_cores", "总核数:"), "slurm_cores")
        self._display_line(slurm_grid, 4, tr("step4_node_num", "节点数:"), "slurm_nodes")
        self._text_line(slurm_grid, 5, tr("step4_slurm_nodelist", "指定节点："), "slurm_nodelist")
        self._text_line(slurm_grid, 6, tr("step4_slurm_time", "最长运行时间："), "slurm_time")
        self._text_line(slurm_grid, 7, tr("step5_slurm_mem", "内存："), "slurm_mem")
        self._mark_optional_slurm_fields("slurm_nodelist", "slurm_time", "slurm_mem")
        self.fields["slurm_mem"].textEdited.connect(self._on_slurm_mem_user_edited)
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
        self.recommend_slurm_button = create_button(
            tr("step6_recommend_slurm_config", "推荐配置"),
            self._apply_recommended_slurm_config,
        )
        confirm_slurm_layout.addWidget(self.recommend_slurm_button)
        self.node_status_button = create_button(
            tr("step6_node_status", "查看节点状态"),
            node_status,
        )
        confirm_slurm_layout.addWidget(self.node_status_button)
        layout.addWidget(self._confirm_slurm_widget)

        self._group.viewLayout.addLayout(layout)
        self.widget = self._group
        self.set_connected(False)

    # [EN] ── Public API ──────────────────────────────────────────────────────────
    # ── 公共接口 ──────────────────────────────────────────────────────────

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
        self._idle_title.setVisible(connected)
        self._idle_table.setVisible(connected)
        self._slurm_title.setVisible(connected)
        self._slurm_form.setVisible(connected)
        self._confirm_slurm_widget.setVisible(connected)
        if connected and self._idle_table.rowCount() == 0:
            self.update_idle_resources([])
        if not connected:
            self._hide_idle_and_slurm()

    def update_idle_resources(self, rows: list) -> None:
        """Update idle resource table. rows: [{cpu, node, nodes, cores, max_cores_per_node}, ...]."""
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
            node_name = str(row.get("node") or row.get("node_name") or "").strip()
            valid.append(
                {
                    "cpu": cpu,
                    "nodes": nodes,
                    "node_name": node_name,
                    "cores": cores,
                    "max_cores_per_node": max_per_node,
                    "free_mem_mb": row.get("free_mem_mb"),
                    "total_mem_mb": row.get("total_mem_mb"),
                }
            )
        valid.sort(key=lambda item: item["cores"], reverse=True)
        signature = tuple(
            (
                row["cpu"],
                row["node_name"],
                row["cores"],
                row["max_cores_per_node"],
                row.get("free_mem_mb"),
                row.get("total_mem_mb"),
            )
            for row in valid
        )
        if signature == self._idle_signature:
            self._apply_suggested_slurm_mem()
            return
        self._idle_signature = signature
        self._idle_rows = valid

        self._idle_table.setUpdatesEnabled(False)
        try:
            header_labels = [
                tr("idle_col_cpu", "分区"),
                tr("idle_col_node_names", "节点名"),
                tr("idle_col_cores", "可用核数"),
                tr("idle_col_free_memory", "节点空闲内存"),
            ]
            self._idle_table.setRowCount(len(valid) + 1)
            for col, text in enumerate(header_labels):
                item = QTableWidgetItem(text)
                if col == 0:
                    align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                elif col == 3:
                    align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                else:
                    align = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
                item.setTextAlignment(align)
                self._idle_table.setItem(0, col, item)

            aligns = [
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            ]
            for row_index, row in enumerate(valid, start=1):
                values = [
                    row["cpu"],
                    row.get("node_name", ""),
                    row["cores"],
                    _idle_memory_text(row),
                ]
                for col, (value, align) in enumerate(zip(values, aligns)):
                    item = QTableWidgetItem(str(value))
                    item.setTextAlignment(align)
                    self._idle_table.setItem(row_index, col, item)
            self._idle_table.expand_to_contents(minimum_height=52, extra_height=6)
        finally:
            self._idle_table.setUpdatesEnabled(True)
        self._apply_suggested_slurm_mem()

    def _on_cpu_partition_changed(self, _text: str) -> None:
        # 切换分区时重新自动填写该分区最大可用内存
        # [EN] When switching partitions, re-auto-fill the maximum available memory for that partition.
        self._slurm_mem_user_edited = False
        self._apply_suggested_slurm_mem()

    def _on_slurm_mem_user_edited(self, _text: str) -> None:
        self._slurm_mem_user_edited = True

    def _apply_suggested_slurm_mem(self) -> None:
        """根据当前分区空闲资源或分区节点内存上限，自动填写最大可用内存（不覆盖用户手改值）。

        [EN] Automatically fill in the maximum available memory based on the current partition's idle
        resources or the partition node memory limit (does not overwrite user-edited values).
        """
        if "slurm_mem" not in self.fields:
            return
        if self._slurm_mem_user_edited:
            return
        partition = self.cpu_combo.currentText().strip()
        suggested = suggest_slurm_mem_for_partition(
            self.idle_resources(),
            partition,
            partition_mem=self._partition_mem_mb,
        )
        if not suggested:
            return
        self.fields["slurm_mem"].setText(suggested)

    def apply_suggested_slurm_mem(self) -> None:
        """供外部在刷新服务器状态后再次尝试填写内存。

        [EN] For external callers to retry filling the memory after refreshing server status.
        """
        self._apply_suggested_slurm_mem()

    def update_partition_memory(self, mapping: dict | None) -> None:
        """缓存各分区节点内存上限（MB），供无空闲节点时填写 Slurm 内存。

        [EN] Cache the per-partition node memory limit (MB) for filling Slurm memory when no idle
        nodes are available.
        """
        self._partition_mem_mb = {
            str(key).strip(): int(value)
            for key, value in (mapping or {}).items()
            if str(key).strip() and isinstance(value, int) and value > 0
        }

    def idle_resources(self) -> list[dict]:
        return list(getattr(self, "_idle_rows", []))

    def render_slurm(self, config: PipelineConfig) -> None:
        self._without_stealing_focus(self._render_slurm_impl, config)

    def _render_slurm_impl(self, config: PipelineConfig) -> None:
        self.fields["slurm_job_name"].setText(str(config.slurm.job_name or config.workdir.path.name))
        self.fields["slurm_cores"].setText(str(config.slurm.cores))
        self.fields["slurm_nodes"].setText(str(config.slurm.nodes))
        self.fields["slurm_nodelist"].setText(str(config.slurm.nodelist or ""))
        self.fields["slurm_time"].setText(str(config.slurm.time or ""))
        self.fields["slurm_mem"].setText(str(config.slurm.mem or ""))
        self._slurm_mem_user_edited = False
        self._server_st_versions = dict(config.slurm.server_st_versions)
        self._replace_combo_items(
            self.st_combo,
            list(self._server_st_versions),
            config.slurm.server_st or config.ww3.st,
        )
        self._default_partition = str(config.slurm.partition or "").strip()
        self._replace_combo_items(self.cpu_combo, [self._default_partition] if self._default_partition else [], self._default_partition)

    def ww3_overrides(self) -> dict[str, str]:
        return {}

    def slurm_overrides(self) -> dict[str, object]:
        from workflows.domain.named_path_preset_yaml import serialize_named_path_preset_block

        selected = self.st_combo.currentText().strip()
        return {
            "job_name": self.fields["slurm_job_name"].text().strip(),
            "partition": self.cpu_combo.currentText().strip(),
            "cores": self.fields["slurm_cores"].text().strip(),
            "nodes": self.fields["slurm_nodes"].text().strip(),
            "nodelist": self.fields["slurm_nodelist"].text().strip(),
            "time": self.fields["slurm_time"].text().strip(),
            "mem": self.fields["slurm_mem"].text().strip(),
            "server_st": serialize_named_path_preset_block(selected, self._server_st_versions),
        }

    def _apply_recommended_slurm_config(self) -> None:
        """从空闲资源自动选分区，并填入 1 节点 + 单节点最大可用核数 + 最大可用内存。

        [EN] Automatically select a partition from idle resources and fill in 1 node + the maximum
        available cores per node + the maximum available memory.
        """
        suggestion = suggest_slurm_config(self.idle_resources(), partition_mem=self._partition_mem_mb)
        if not suggestion:
            self._log(
                tr(
                    "step6_recommend_slurm_empty",
                    "⚠️ 当前没有可用的空闲资源，请先连接服务器并等待空闲资源刷新",
                )
            )
            return
        self.apply_slurm_resources(
            cpu=str(suggestion["partition"]),
            cores=int(suggestion["cores"]),
            nodes=int(suggestion["nodes"]),
            mem=str(suggestion.get("mem") or ""),
            clear_nodelist=True,
        )
        mem_text = str(suggestion.get("mem") or "").strip() or tr("step6_recommend_slurm_mem_unknown", "未获取")
        self._log(
            tr(
                "step6_recommend_slurm_applied",
                "✅ 已自动选取分区 {partition}：{nodes} 节点，{cores} 核，内存 {mem}",
            ).format(
                partition=suggestion["partition"],
                nodes=suggestion["nodes"],
                cores=suggestion["cores"],
                mem=mem_text,
            )
        )

    def apply_slurm_resources(
        self,
        *,
        cpu: str,
        cores: int,
        nodes: int,
        mem: str | None = None,
        clear_nodelist: bool = False,
    ) -> None:
        cpu = str(cpu).strip()
        if cpu:
            items = [self.cpu_combo.itemText(i) for i in range(self.cpu_combo.count())]
            if cpu not in items:
                self.cpu_combo.addItem(cpu)
            self.cpu_combo.setCurrentText(cpu)
        self.fields["slurm_cores"].setText(str(max(1, int(cores))))
        self.fields["slurm_nodes"].setText(str(max(1, int(nodes))))
        if mem is not None:
            self.fields["slurm_mem"].setText(str(mem).strip())
            self._slurm_mem_user_edited = False
        if clear_nodelist:
            self.fields["slurm_nodelist"].setText("")

    def replace_cpu_options_if_changed(self, values: list[str]) -> None:
        self._without_stealing_focus(self._replace_cpu_options_if_changed_impl, values)

    def _replace_cpu_options_if_changed_impl(self, values: list[str]) -> None:
        server_values = [str(value).strip() for value in values if str(value).strip()]
        if not server_values:
            # 服务器连不上或未解析到分区：回退到默认分区
            # [EN] Server unreachable or no partitions parsed: fall back to the default partition.
            default_partition = getattr(self, "_default_partition", "")
            target = [default_partition] if default_partition else []
            current = [self.cpu_combo.itemText(i) for i in range(self.cpu_combo.count())]
            if current != target:
                self.cpu_combo.clear()
                if default_partition:
                    self.cpu_combo.addItem(default_partition)
                    self.cpu_combo.setCurrentText(default_partition)
            return
        deduped = list(dict.fromkeys(server_values))
        current = [self.cpu_combo.itemText(i) for i in range(self.cpu_combo.count())]
        if current == deduped:
            return
        selected = self.cpu_combo.currentText().strip()
        self.cpu_combo.clear()
        self.cpu_combo.addItems(deduped)
        # 解析到的分区中若含默认分区则优先选中；否则保留原选择，再否则取第一个
        # [EN] If the parsed partitions include the default, select it first; otherwise keep the
        # previous selection, or fall back to the first available partition.
        default_partition = getattr(self, "_default_partition", "")
        if default_partition and default_partition in deduped:
            self.cpu_combo.setCurrentText(default_partition)
        elif selected in deduped:
            self.cpu_combo.setCurrentText(selected)
        else:
            self.cpu_combo.setCurrentText(deduped[0])
        self._apply_suggested_slurm_mem()

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

    def _hide_idle_and_slurm(self) -> None:
        self._idle_title.setVisible(False)
        self._idle_table.setVisible(False)
        self._idle_table.setRowCount(0)
        self._idle_rows = []
        self._idle_signature = ()
        self._slurm_title.setVisible(False)
        self._slurm_form.setVisible(False)
        self._confirm_slurm_widget.setVisible(False)

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

    def _mark_optional_slurm_fields(self, *keys: str) -> None:
        hint = tr("slurm_optional_placeholder", "非必填")
        for key in keys:
            field = self.fields.get(key)
            label = self.field_labels.get(key)
            if field is not None:
                field.setPlaceholderText(hint)
                field.setToolTip(hint)
            if label is not None:
                label.setToolTip(hint)

    @staticmethod
    def _replace_combo_items(combo: ComboBox, values: list[str], selected: str) -> None:
        next_values = [str(value) for value in values if str(value)]
        if selected and selected not in next_values:
            next_values = [*next_values, selected]
        combo.clear()
        combo.addItems(next_values)
        combo.setCurrentText(selected)

    @staticmethod
    def _without_stealing_focus(fn, *args, **kwargs) -> None:
        app = QApplication.instance()
        focus_before = app.focusWidget() if app is not None else None
        fn(*args, **kwargs)
        if focus_before is None:
            return
        current = app.focusWidget() if app is not None else None
        if current is not focus_before:
            try:
                focus_before.setFocus()
            except RuntimeError:
                pass
