"""Desktop window for Step 1 forcing-file preparation."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from workflows.application.configuration import ConfigError
from workflows.support.translations import tr

from ..background_runner import BackgroundRunner
from ..components.combo_box import left_align_combo_text
from ..qt_callback_dispatcher import QtCallbackDispatcher
from ..view_models.forcing_step import ForcingStepState, ForcingStepViewModel
from ..view_models.pipeline import PipelineViewModel


class ForcingPreparationWindow(QMainWindow):
    """First desktop surface backed by the headless forcing workflow."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(tr("forcing_preparation_window_title", "WW3 预处理"))
        self.resize(920, 620)
        self._busy = False
        self._runner = BackgroundRunner(self)
        self._updates = QtCallbackDispatcher(
            on_log=self._append_log,
            on_state_change=self._render_state,
            parent=self,
        )
        self._view_model = ForcingStepViewModel(
            on_log=self._updates.post_log,
            on_state_change=self._updates.post_state,
        )
        self._pipeline_view_model = PipelineViewModel(on_log=self._append_log)
        self._params_path: Path | None = None
        self._paths: dict[str, QLineEdit] = {}
        self._build_surface()

    def _build_surface(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title = QLabel(tr("forcing_preparation_title", "强迫场准备"))
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        layout.addWidget(title)

        top_actions = QHBoxLayout()
        self._params_label = QLabel(tr("params_not_loaded", "未载入参数文件"))
        self._params_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        load_button = QPushButton(tr("load_params_file", "载入参数文件"))
        load_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        load_button.clicked.connect(self._load_parameters)
        top_actions.addWidget(load_button)
        top_actions.addWidget(self._params_label, 1)
        layout.addLayout(top_actions)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(divider)

        form = QFormLayout()
        form.setVerticalSpacing(11)
        self._add_path_row(form, tr("workdir_label", "工作目录"), "workdir", directory=True)
        self._add_path_row(form, tr("step1_field_wind", "风场"), "wind")
        self._add_path_row(form, tr("step1_field_current", "流场"), "current")
        self._add_path_row(form, tr("step1_field_level", "水位场"), "level")
        self._add_path_row(form, tr("step1_field_ice", "海冰场"), "ice")

        self._mode = QComboBox()
        self._mode.addItem(tr("copy_to_workdir", "复制到工作目录"), "copy")
        self._mode.addItem(tr("move_to_workdir", "移动到工作目录"), "move")
        left_align_combo_text(self._mode)
        form.addRow(tr("process_mode", "处理方式"), self._mode)

        self._auto_associate = QCheckBox(tr("auto_associate_fields", "自动关联同一文件中的其他强迫场"))
        self._auto_associate.setChecked(True)
        form.addRow("", self._auto_associate)
        layout.addLayout(form)

        actions = QHBoxLayout()
        self._status = QLabel(tr("status_waiting", "等待执行"))
        self._prepare_button = QPushButton(tr("prepare_forcing", "准备强迫场"))
        self._prepare_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self._prepare_button.clicked.connect(self._prepare_forcing)
        actions.addWidget(self._status, 1)
        actions.addWidget(self._prepare_button)
        layout.addLayout(actions)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText(tr("execution_log", "执行日志"))
        self._log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._log, 1)
        self.setCentralWidget(root)

    def _add_path_row(self, form: QFormLayout, label: str, key: str, *, directory: bool = False) -> None:
        field = QLineEdit()
        field.setClearButtonEnabled(True)
        browse = QToolButton()
        browse.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        browse.setToolTip(tr("choose_named_item", "选择{label}").format(label=label))
        browse.clicked.connect(lambda _checked=False: self._browse_path(key, directory))

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        row_layout.addWidget(field, 1)
        row_layout.addWidget(browse)
        self._paths[key] = field
        form.addRow(label, row)

    def _browse_path(self, key: str, directory: bool) -> None:
        start = self._paths[key].text().strip() or str(Path.home())
        if directory:
            selected = QFileDialog.getExistingDirectory(self, tr("choose_workdir", "选择工作目录"), start)
        else:
            selected, _ = QFileDialog.getOpenFileName(
                self,
                tr("choose_forcing_file", "选择强迫场文件"),
                start,
                tr("file_filter_netcdf_all", "NetCDF 文件 (*.nc *.nc4 *.cdf);;所有文件 (*)"),
            )
        if selected:
            self._paths[key].setText(selected)

    def _load_parameters(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            tr("load_params_file", "载入参数文件"),
            str(Path.cwd()),
            tr("file_filter_yaml_all", "YAML 参数文件 (*.yml *.yaml);;所有文件 (*)"),
        )
        if not selected:
            return
        try:
            config = self._view_model.load_config(selected)
        except Exception as exc:
            self._show_error(str(exc))
            return
        self._params_label.setText(selected)
        self._params_path = Path(selected).expanduser().resolve()
        self._paths["workdir"].setText(str(config.workdir.path))
        for key in ("wind", "current", "level", "ice"):
            value = getattr(config.forcing, key)
            self._paths[key].setText(str(value) if value else "")
        self._mode.setCurrentIndex(0 if config.forcing.process_mode == "copy" else 1)
        self._auto_associate.setChecked(config.forcing.auto_associate)

    def _prepare_forcing(self) -> None:
        if self._busy:
            return
        try:
            config = self._view_model.config_from_selection(
                workdir=self._paths["workdir"].text().strip(),
                wind=self._paths["wind"].text().strip(),
                current=self._paths["current"].text().strip(),
                level=self._paths["level"].text().strip(),
                ice=self._paths["ice"].text().strip(),
                process_mode=str(self._mode.currentData()),
                auto_associate=self._auto_associate.isChecked(),
            )
        except ConfigError as exc:
            self._show_error(str(exc))
            return
        self._log.clear()
        self._busy = True
        self._prepare_button.setEnabled(False)
        self._status.setText(tr("status_processing", "正在处理"))

        def task() -> ForcingStepState:
            return self._view_model.prepare(config)

        self._runner.run(task, self._on_prepare_done)

    def _on_prepare_done(self, result: object) -> None:
        self._busy = False
        state = result if isinstance(result, ForcingStepState) else self._view_model.state
        self._render_state(state)
        if state.error:
            self._show_error(state.error)
        elif state.files.existing_items() and self._params_path is not None:
            try:
                self._pipeline_view_model.save_prepared_forcing_to_params(self._params_path, state.files)
            except Exception as exc:
                self._show_error(tr("forcing_params_save_failed", "保存强迫场路径到 params.yml 失败：{error}").format(error=exc))

    def _append_log(self, message: str) -> None:
        self._log.append(message)

    def _render_state(self, state: ForcingStepState) -> None:
        self._prepare_button.setEnabled(not (self._busy or state.is_running))
        if state.is_running:
            self._status.setText(tr("status_processing", "正在处理"))
        elif state.error:
            self._status.setText(tr("status_failed", "处理失败"))
        elif state.files.wind:
            self._status.setText(tr("forcing_prepared", "强迫场已准备"))
        else:
            self._status.setText(tr("status_waiting", "等待执行"))

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, tr("params_or_execution_error", "参数或执行错误"), message)
