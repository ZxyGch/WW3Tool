"""本地运行面板（主页步骤区）：执行 local.sh 与 ww3_ounf/ounp/trnc。

[EN] Local run panel (home step area): execute local.sh and ww3_ounf/ounp/trnc.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QWidget
from qfluentwidgets import ComboBox, LineEdit, PrimaryPushButton

from ..components.combo_box import left_align_combo_text
from ..components.header_card import create_header_card
from ..components import styles
from workflows.infrastructure import runtime_config
from workflows.support.translations import tr


class LocalRunPanel:
    # [EN] Local run controls: ST version dropdown (or bin path) + run/stop + ounf/ounp/trnc.
    """本地运行控件：ST 版本下拉框（或 bin 路径）+ 运行/停止 + ounf/ounp/trnc。"""

    def __init__(
        self,
        parent: QWidget,
        *,
        create_button: Callable[[str, Callable[..., object]], PrimaryPushButton],
        input_style: Callable[[], str],
        local_run: Callable[[], None],
        stop: Callable[[], None],
    ) -> None:
        group, layout = create_header_card(parent, tr("step5_local_title", "本地运行"))
        self._layout = layout
        self._create_button = create_button
        self._input_style = input_style

        # [EN] Check if local ST versions are configured
        # 检查是否已配置本地 ST 版本
        self._local_st_versions = self._load_local_st_versions()
        self.st_combo: ComboBox | None = None
        self.bin_edit: LineEdit | None = None
        self._st_row_widget: QWidget | None = None
        self._bin_row_widget: QWidget | None = None

        self._ensure_st_row()
        self._ensure_bin_row()
        self.refresh_st_versions()

        self.local_run_button = create_button(tr("step5_local_run", "本地运行"), local_run)
        self.stop_button = create_button(tr("step5_stop_shel", "停止执行"), stop)
        layout.addWidget(self.local_run_button)
        layout.addWidget(self.stop_button)

        group.viewLayout.setContentsMargins(11, 10, 11, 12)
        group.viewLayout.addLayout(layout)
        self.widget = group

    def _ensure_st_row(self) -> None:
        if self._st_row_widget is not None and self.st_combo is not None:
            return
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(QLabel(tr("step5_local_st_version", "ST 版本：")))
        self.st_combo = ComboBox()
        self.st_combo.setStyleSheet(styles.combo_style())
        left_align_combo_text(self.st_combo)
        row.addWidget(self.st_combo, 1)
        self._st_row_widget = row_widget
        self._layout.addWidget(row_widget)

    def _ensure_bin_row(self) -> None:
        if self._bin_row_widget is not None and self.bin_edit is not None:
            return
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(QLabel(tr("step5_ww3bin_path", "WW3 bin 路径:")))
        self.bin_edit = LineEdit()
        self.bin_edit.setStyleSheet(self._input_style())
        self.bin_edit.setText(_default_bin())
        self.bin_edit.setPlaceholderText(tr("step5_path_placeholder", "为空则使用系统 PATH"))
        row.addWidget(self.bin_edit, 1)
        choose = self._create_button(tr("select", "选择"), self._choose_bin)
        row.addWidget(choose)
        self._bin_row_widget = row_widget
        self._layout.addWidget(row_widget)

    def refresh_st_versions(self) -> None:
        versions = self._load_local_st_versions()
        self._local_st_versions = versions
        if versions:
            self._ensure_st_row()
            if self._st_row_widget is not None:
                self._st_row_widget.show()
            if self._bin_row_widget is not None:
                self._bin_row_widget.hide()
            current = self.st_combo.currentText().strip() if self.st_combo is not None else ""
            names = [version["name"] for version in versions]
            default_name = str(runtime_config.load_full_config().get("DEFAULT_LOCAL_ST", "") or "")
            selected = current if current in names else (default_name if default_name in names else names[0])
            if self.st_combo is not None:
                self.st_combo.blockSignals(True)
                self.st_combo.clear()
                self.st_combo.addItems(names)
                self.st_combo.setCurrentText(selected)
                self.st_combo.blockSignals(False)
        else:
            self._ensure_bin_row()
            if self._st_row_widget is not None:
                self._st_row_widget.hide()
            if self._bin_row_widget is not None:
                self._bin_row_widget.show()

    @staticmethod
    def _load_local_st_versions() -> list[dict[str, str]]:
        """从 runtime_config 读取已配置的本地 ST 版本列表。"""
        try:
            config = runtime_config.load_full_config()
            versions = config.get("LOCAL_ST_VERSIONS")
            if isinstance(versions, list) and versions:
                return [
                    {"name": str(v["name"]), "path": str(v.get("path", ""))}
                    for v in versions
                    if isinstance(v, dict) and v.get("name")
                ]
        except Exception:
            pass
        return []

    def _choose_bin(self) -> None:
        from pathlib import Path

        start = self.bin_edit.text().strip() if self.bin_edit else ""
        if not start or not Path(start).is_dir():
            # [EN] Fall back to system root directory when path does not exist
            start = str(Path.home().anchor)  # 路径不存在时回退到系统根目录
        path = QFileDialog.getExistingDirectory(
            self.widget, tr("step5_choose_ww3bin", "选择 WW3 bin 目录"), start
        )
        if path and self.bin_edit:
            self.bin_edit.setText(path)

    def bin_dir(self) -> str:
        # [EN] If using ST version dropdown, look up the path from config
        # 如果使用 ST 版本下拉框，从配置中查找路径
        if self.st_combo is not None:
            selected = self.st_combo.currentText().strip()
            for ver in self._local_st_versions:
                if ver["name"] == selected:
                    return ver["path"]
            return ""
        if self.bin_edit is not None:
            return self.bin_edit.text().strip()
        return ""


def _default_bin() -> str:
    # [EN] Default WW3 bin directory: prefer ``paths.ww3bin_path`` from params.yml, fall back to config.json.
    """默认 WW3 bin 目录：优先读 params.yml 的 ``paths.ww3bin_path``，回退到 config.json。"""
    try:
        from pathlib import Path as _Path

        from workflows.application.configuration import load_pipeline_config

        repo_params = _Path(runtime_config.PROJECT_ROOT) / "params.yml"
        if repo_params.is_file():
            cfg = load_pipeline_config(repo_params, validation_stage="plot")
            value = str(cfg.paths.ww3bin_path or "").strip()
            if value:
                return value
    except Exception:
        pass
    try:
        return str(runtime_config.load_config().get("WW3BIN_PATH", "") or "")
    except Exception:
        return ""
