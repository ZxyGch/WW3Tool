"""本地运行面板（主页步骤区）：执行 local.sh 与 ww3_ounf/ounp/trnc。"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QWidget
from qfluentwidgets import LineEdit, PrimaryPushButton

from ..components.header_card import create_header_card
from workflows.infrastructure import runtime_config
from workflows.support.translations import tr


class LocalRunPanel:
    """本地运行控件：WW3 bin 路径 + 运行/停止 + ounf/ounp/trnc。"""

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

        bin_row = QHBoxLayout()
        bin_row.setSpacing(8)
        bin_row.addWidget(QLabel(tr("step5_ww3bin_path", "WW3 bin 路径:")))
        self.bin_edit = LineEdit()
        self.bin_edit.setStyleSheet(input_style())
        self.bin_edit.setText(_default_bin())
        self.bin_edit.setPlaceholderText(tr("step5_path_placeholder", "为空则使用系统 PATH"))
        bin_row.addWidget(self.bin_edit, 1)
        choose = create_button(tr("select", "选择"), self._choose_bin)
        bin_row.addWidget(choose)
        layout.addLayout(bin_row)

        self.local_run_button = create_button(tr("step5_local_run", "本地运行"), local_run)
        self.stop_button = create_button(tr("step5_stop_shel", "停止执行"), stop)
        layout.addWidget(self.local_run_button)
        layout.addWidget(self.stop_button)

        group.viewLayout.setContentsMargins(11, 10, 11, 12)
        group.viewLayout.addLayout(layout)
        self.widget = group

    def _choose_bin(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self.widget, tr("step5_choose_ww3bin", "选择 WW3 bin 目录"), self.bin_edit.text().strip() or ""
        )
        if path:
            self.bin_edit.setText(path)

    def bin_dir(self) -> str:
        return self.bin_edit.text().strip()


def _default_bin() -> str:
    try:
        return str(runtime_config.load_config().get("WW3BIN_PATH", "") or "")
    except Exception:
        return ""
