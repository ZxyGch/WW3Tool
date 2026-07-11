"""本地运行面板（主页步骤区）：执行 local.sh 与 ww3_ounf/ounp/trnc。

[EN] Local run panel (home step area): execute local.sh and ww3_ounf/ounp/trnc.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import ComboBox, PrimaryPushButton

from ..components.combo_box import left_align_combo_text
from ..components.header_card import create_header_card
from ..components import styles
from workflows.infrastructure import runtime_config
from workflows.support.translations import tr


class LocalRunPanel:
    # [EN] Local run controls: ST version dropdown + run/stop + ounf/ounp/trnc.
    """本地运行控件：ST 版本下拉框 + 运行/停止 + ounf/ounp/trnc。

    [EN] Local run controls: ST version dropdown + run/stop + ounf/ounp/trnc.
    """

    def __init__(
        self,
        parent: QWidget,
        *,
        create_button: Callable[[str, Callable[..., object]], PrimaryPushButton],
        input_style: Callable[[], str],
        local_run: Callable[[], None],
        stop: Callable[[], None],
    ) -> None:
        group, _ = create_header_card(parent, tr("step5_local_title", "本地运行"))
        group.viewLayout.setContentsMargins(11, 10, 11, 12)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setSpacing(10)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        group.viewLayout.addWidget(self._content)

        # [EN] Check if local ST versions are configured
        # 检查是否已配置本地 ST 版本
        # [EN] Check whether local ST versions have been configured.
        self._local_st_versions = self._load_local_st_versions()
        self.st_combo: ComboBox | None = None
        self._st_row_widget: QWidget | None = None

        self._ensure_st_row()
        self.refresh_st_versions()

        self.local_run_button = create_button(tr("step5_local_run", "本地运行"), local_run)
        self.stop_button = create_button(tr("step5_stop_shel", "停止执行"), stop)
        self._content_layout.addWidget(self.local_run_button)
        self._content_layout.addWidget(self.stop_button)
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
        self._content_layout.addWidget(row_widget)

    def refresh_st_versions(self) -> None:
        versions = self._load_local_st_versions()
        self._local_st_versions = versions
        if versions:
            self._ensure_st_row()
            if self._st_row_widget is not None:
                self._st_row_widget.show()
            current = self.st_combo.currentText().strip() if self.st_combo is not None else ""
            names = [version["name"] for version in versions]
            default_name = str(runtime_config.load_full_config().get("DEFAULT_LOCAL_ST", "") or "")
            selected = current if current in names else (default_name if default_name in names else names[0])
            if self.st_combo is not None:
                self.st_combo.blockSignals(True)
                self.st_combo.clear()
                self.st_combo.addItems(names)
                self.st_combo.setCurrentText(selected)
                self.st_combo.setEnabled(True)
                self.st_combo.blockSignals(False)
        else:
            self._ensure_st_row()
            if self._st_row_widget is not None:
                self._st_row_widget.show()
            if self.st_combo is not None:
                self.st_combo.blockSignals(True)
                self.st_combo.clear()
                self.st_combo.addItem(tr("step5_local_st_not_configured", "未配置本地 ST"))
                self.st_combo.setEnabled(False)
                self.st_combo.blockSignals(False)

    @staticmethod
    def _load_local_st_versions() -> list[dict[str, str]]:
        """从 runtime_config 读取已配置的本地 ST 版本列表。

        [EN] Read the configured local ST version list from runtime_config.
        """
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

    def bin_dir(self) -> str:
        # [EN] If using ST version dropdown, look up the path from config
        # 如果使用 ST 版本下拉框，从配置中查找路径
        # [EN] If the ST version dropdown is used, look up the executable path from config.
        if self.st_combo is not None and self._local_st_versions:
            selected = self.st_combo.currentText().strip()
            for ver in self._local_st_versions:
                if ver["name"] == selected:
                    return ver["path"]
            return ""
        return ""
