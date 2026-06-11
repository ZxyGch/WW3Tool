"""Step 4 panel for WAVEWATCH and scheduler parameters."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget, QSizePolicy
from qfluentwidgets import ComboBox, LineEdit, PrimaryPushButton

# Step 4 可选「频谱参数 / 数值积分时间步长」分组（由设置页开关控制是否显示）。
_SPECTRUM_SPECS = [
    ("SPECTRUM%XFR", "set_freq_inc", "频率增量："),
    ("SPECTRUM%FREQ1", "set_freq_start", "起始频率："),
    ("SPECTRUM%NK", "set_freq_num", "频率数量："),
    ("SPECTRUM%NTH", "set_dir_num", "方向离散数："),
]
_TIMESTEP_SPECS = [
    ("TIMESTEPS%DTMAX", "set_dtmax", "最大全局时间步长："),
    ("TIMESTEPS%DTXY", "set_dtxy", "空间时间步长："),
    ("TIMESTEPS%DTKTH", "set_dtkth", "谱空间时间步长："),
    ("TIMESTEPS%DTMIN", "set_dtmin", "最小源项时间步长："),
]

from ..components.combo_box import left_align_combo_text
from ..components.header_card import create_header_card
from ..components import styles
from ..components.validators import date_yyyymmdd_validator, int_validator
from workflows.domain.config_models import PipelineConfig
from workflows.infrastructure import runtime_config
from workflows.support.translations import tr


class WW3StepPanel:
    """Own WW3/Slurm controls and their config conversion."""

    def __init__(
        self,
        parent: QWidget,
        *,
        create_button: Callable[[str, Callable[..., object]], PrimaryPushButton],
        input_style: Callable[[], str],
        combo_style: Callable[[], str],
        section_title: Callable[[str], QWidget],
        load_time_range: Callable[[], None],
        auto_configure_timesteps: Callable[[], None],
        run_pipeline: Callable[[], None],
    ) -> None:
        self._input_style = input_style
        self.fields: dict[str, LineEdit] = {}
        self.field_labels: dict[str, QLabel] = {}
        self._spectrum_hideables: list[QWidget] = []
        self._timesteps_hideables: list[QWidget] = []
        self._slurm_hideables: list[QWidget] = []
        group, layout = create_header_card(parent, tr("step4_title", "第四步：配置WW3运行参数"))
        slurm_title = section_title(tr("step4_slurm_config", "Slurm 配置"))
        layout.addWidget(slurm_title)
        self._slurm_hideables.append(slurm_title)
        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        self.st_combo = ComboBox()
        self.st_combo.setStyleSheet(combo_style())
        left_align_combo_text(self.st_combo)
        self.st_label = self._field_label(tr("step4_st_version", "ST 版本："))
        grid.addWidget(self.st_label, 0, 0)
        grid.addWidget(self.st_combo, 0, 1)
        self.cpu_combo = ComboBox()
        self.cpu_combo.addItems(_cpu_group_options())
        self.cpu_combo.setStyleSheet(combo_style())
        left_align_combo_text(self.cpu_combo)
        self.cpu_label = self._field_label(tr("step4_server_cpu", "服务器 CPU："))
        grid.addWidget(self.cpu_label, 1, 0)
        grid.addWidget(self.cpu_combo, 1, 1)
        self._display_line(grid, 2, 0, tr("step4_total_cores", "总核数:"), "slurm_cores")
        self._display_line(grid, 3, 0, tr("step4_node_num", "节点数:"), "slurm_nodes")
        self._slurm_hideables.extend(
            [
                self.st_label,
                self.st_combo,
                self.cpu_label,
                self.cpu_combo,
                self.field_labels["slurm_cores"],
                self.fields["slurm_cores"],
                self.field_labels["slurm_nodes"],
                self.fields["slurm_nodes"],
            ]
        )
        layout.addLayout(grid)

        layout.addWidget(section_title(tr("step4_wavewatch_config", "WAVEWATCH 配置")))
        wave_grid = QGridLayout()
        wave_grid.setSpacing(10)
        wave_grid.setColumnStretch(0, 0)
        wave_grid.setColumnStretch(1, 1)
        self._display_line(wave_grid, 0, 0, tr("step4_compute_precision", "计算精度 (秒):"), "ww3_compute")
        self._display_line(wave_grid, 1, 0, tr("step4_output_precision", "输出精度 (秒):"), "ww3_output")
        self._display_line(wave_grid, 2, 0, tr("step4_start_date", "起始日期:"), "ww3_start")
        self._display_line(wave_grid, 3, 0, tr("step4_end_date", "结束日期:"), "ww3_end")
        self.output_scheme_combo = ComboBox()
        self.output_scheme_combo.setStyleSheet(combo_style())
        left_align_combo_text(self.output_scheme_combo)
        self.output_scheme_label = self._field_label(tr("step4_output_scheme", "谱分区输出："))
        wave_grid.addWidget(self.output_scheme_label, 4, 0)
        wave_grid.addWidget(self.output_scheme_combo, 4, 1)
        layout.addLayout(wave_grid)

        # 可选分组：与 wave_grid 相同，直接 addWidget/addLayout（勿再包一层 QWidget）。
        self._spectrum_fields = self._build_param_section(
            layout, section_title, tr("spectrum_config", "频谱参数"), _SPECTRUM_SPECS, self._spectrum_hideables
        )
        self._timesteps_fields = self._build_param_section(
            layout,
            section_title,
            tr("timesteps_params", "数值积分时间步长参数"),
            _TIMESTEP_SPECS,
            self._timesteps_hideables,
        )
        self.auto_timesteps_button = create_button(
            tr("step4_auto_timesteps", "按 CFL 推荐时间步长"),
            auto_configure_timesteps,
        )
        layout.addWidget(self.auto_timesteps_button)
        self._timesteps_hideables.append(self.auto_timesteps_button)

        self.load_time_button = create_button(tr("step4_load_time_from_wind_nc", "从 wind.nc 读取时间范围"), load_time_range)
        layout.addWidget(self.load_time_button)
        self.run_button = create_button(tr("step4_confirm_params", "确认参数"), run_pipeline)
        layout.addWidget(self.run_button)
        self.status = QLabel(tr("status_waiting", "等待执行"))
        self.status.hide()
        group.viewLayout.setContentsMargins(11, 10, 11, 12)
        group.viewLayout.addLayout(layout)
        self.widget = group
        cfg = runtime_config.load_config()
        self.set_step4_sections_visible(
            bool(cfg.get("STEP4_SHOW_SPECTRUM", False)),
            bool(cfg.get("STEP4_SHOW_TIMESTEPS", False)),
        )
        QTimer.singleShot(100, lambda: self._align_control_columns(grid, wave_grid))

    def render(self, config: PipelineConfig) -> None:
        ww3 = config.ww3
        self.set_value("ww3_start", ww3.start_date)
        self.set_value("ww3_end", ww3.end_date)
        self.set_value("ww3_compute", ww3.compute_precision)
        self.set_value("ww3_output", ww3.output_precision)
        self.set_value("slurm_cores", config.slurm.cores)
        self.set_value("slurm_nodes", config.slurm.nodes)
        self._replace_combo_items(self.st_combo, list(config.presets.st), ww3.st)
        self._replace_combo_items(self.output_scheme_combo, list(config.presets.output_scheme), ww3.output_scheme)
        self._replace_combo_items(self.cpu_combo, _cpu_group_options(), config.slurm.cpu)
        params = config.ww3_grid.parameters
        for grid_key, edit in {**self._spectrum_fields, **self._timesteps_fields}.items():
            edit.setText(str(params.get(grid_key, "")))

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(styles.label_style())
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        return label

    @staticmethod
    def _expand_field(widget: QWidget) -> None:
        widget.setMinimumWidth(0)
        widget.setMaximumWidth(16777215)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    @staticmethod
    def _style_line_edit(edit: LineEdit, style: str) -> None:
        edit.setProperty("transparent", False)
        edit.setStyleSheet(style)
        edit.setMinimumHeight(33)

    def _build_param_section(
        self,
        parent_layout: QVBoxLayout,
        section_title: Callable[[str], QWidget],
        title: str,
        specs: list[tuple[str, str, str]],
        hideables: list[QWidget],
    ) -> dict[str, LineEdit]:
        """小节标题 + 字段网格（标题样式与 Slurm / WAVEWATCH 相同）。"""
        title_widget = section_title(title)
        parent_layout.addWidget(title_widget)
        hideables.append(title_widget)

        param_grid = QGridLayout()
        param_grid.setSpacing(10)
        param_grid.setColumnStretch(0, 0)
        param_grid.setColumnStretch(1, 1)
        fields: dict[str, LineEdit] = {}
        for row, (grid_key, label_key, label_default) in enumerate(specs):
            label = self._field_label(tr(label_key, label_default))
            edit = LineEdit()
            self._style_line_edit(edit, self._input_style())
            self._expand_field(edit)
            param_grid.addWidget(label, row, 0)
            param_grid.addWidget(edit, row, 1)
            fields[grid_key] = edit
            hideables.extend((label, edit))
        parent_layout.addLayout(param_grid)
        return fields

    def set_step4_sections_visible(self, show_spectrum: bool, show_timesteps: bool) -> None:
        """按设置页开关显隐 Step 4 的频谱/时间步分组。"""
        self._show_spectrum = bool(show_spectrum)
        self._show_timesteps = bool(show_timesteps)
        for widget in self._spectrum_hideables:
            widget.setVisible(self._show_spectrum)
        for widget in self._timesteps_hideables:
            widget.setVisible(self._show_timesteps)
        if hasattr(self, "widget"):
            self.widget.updateGeometry()

    def set_slurm_visible(self, visible: bool) -> None:
        """按运行方式显隐 Slurm 配置（本地模式隐藏）。"""
        for widget in self._slurm_hideables:
            widget.setVisible(visible)
        if hasattr(self, "widget"):
            self.widget.updateGeometry()

    def set_timestep_values(self, values: dict[str, object]) -> None:
        for key, value in values.items():
            edit = self._timesteps_fields.get(key)
            if edit is not None:
                edit.setText(str(value))

    def spectrum_freq1_text(self) -> str:
        edit = self._spectrum_fields.get("SPECTRUM%FREQ1")
        return edit.text().strip() if edit is not None else ""

    def ww3_grid_overrides(self) -> dict[str, str]:
        """仅当某分组可见时，将其字段作为 ww3_grid 覆盖（表单优先于 config.json）。"""
        out: dict[str, str] = {}
        if getattr(self, "_show_spectrum", False):
            out.update({k: e.text().strip() for k, e in self._spectrum_fields.items() if e.text().strip()})
        if getattr(self, "_show_timesteps", False):
            out.update({k: e.text().strip() for k, e in self._timesteps_fields.items() if e.text().strip()})
        return out

    def ww3_overrides(self) -> dict[str, str]:
        return {
            "start_date": self.fields["ww3_start"].text().strip(),
            "end_date": self.fields["ww3_end"].text().strip(),
            "compute_precision": self.fields["ww3_compute"].text().strip(),
            "output_precision": self.fields["ww3_output"].text().strip(),
            "output_scheme": self.output_scheme_combo.currentText().strip(),
            "st": self.st_combo.currentText().strip(),
        }

    def slurm_overrides(self) -> dict[str, str]:
        return {
            "cpu": self.cpu_combo.currentText().strip(),
            "cores": self.fields["slurm_cores"].text().strip(),
            "nodes": self.fields["slurm_nodes"].text().strip(),
        }

    def set_value(self, key: str, value: object) -> None:
        self.fields[key].setText(str(value))

    def _display_line(self, grid: QGridLayout, row: int, column: int, label: str, key: str) -> None:
        field = LineEdit()
        self._style_line_edit(field, self._input_style())
        self._expand_field(field)
        if key in {"slurm_cores", "slurm_nodes", "ww3_compute", "ww3_output"}:
            field.setValidator(int_validator(1))
        elif key in {"ww3_start", "ww3_end"}:
            field.setValidator(date_yyyymmdd_validator())
        field_label = self._field_label(label)
        grid.addWidget(field_label, row, column)
        grid.addWidget(field, row, column + 1)
        self.fields[key] = field
        self.field_labels[key] = field_label

    def _align_control_columns(self, *grids: QGridLayout) -> None:
        """仅对齐 Slurm / WAVEWATCH 主表单的标签列宽。"""
        labels = [
            self.st_label,
            self.cpu_label,
            self.field_labels["slurm_cores"],
            self.field_labels["slurm_nodes"],
            self.field_labels["ww3_compute"],
            self.field_labels["ww3_output"],
            self.field_labels["ww3_start"],
            self.field_labels["ww3_end"],
            self.output_scheme_label,
        ]
        for label in labels:
            label.update()
        label_width = max(label.sizeHint().width() for label in labels)
        for label in labels:
            label.setMinimumWidth(label_width)
            label.setMaximumWidth(label_width)
        for grid in grids:
            grid.setColumnMinimumWidth(0, label_width)

    @staticmethod
    def _replace_combo_items(combo: ComboBox, values: list[str], selected: str) -> None:
        if selected and selected not in values:
            values = [*values, selected]
        combo.clear()
        combo.addItems(values)
        combo.setCurrentText(selected)


def _cpu_group_options() -> list[str]:
    config = runtime_config.load_config()
    values = config.get("CPU_GROUP", runtime_config.DEFAULT_CONFIG["CPU_GROUP"])
    options = [str(item).strip() for item in values if str(item).strip()] if isinstance(values, list) else []
    return options or list(runtime_config.DEFAULT_CONFIG["CPU_GROUP"])
