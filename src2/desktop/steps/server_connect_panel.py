"""第五步：连接服务器 面板（主页步骤区）。"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget
from qfluentwidgets import LineEdit, PrimaryPushButton

from ..components.header_card import create_header_card
from workflows.support.translations import tr

_TITLE_KEY = "step6_title"
_TITLE_DEFAULT = "第五步：连接服务器"


class ServerConnectPanel:
    """连接服务器 + 查看任务队列 + 取消任务。连接参数取自设置页 SERVER_*。"""

    def __init__(
        self,
        parent: QWidget,
        *,
        create_button: Callable[[str, Callable[..., object]], PrimaryPushButton],
        input_style: Callable[[], str],
        connect: Callable[[], None],
        queue: Callable[[], None],
        cancel: Callable[[], None],
    ) -> None:
        self._group, layout = create_header_card(parent, f"{tr(_TITLE_KEY, _TITLE_DEFAULT)}  {tr('step6_not_connected', '[未连接]')}")
        self.connect_button = create_button(tr("step6_connect", "连接服务器"), connect)
        layout.addWidget(self.connect_button)

        # 连接成功后才显示「查看任务队列」与「取消任务」。
        self.queue_button = create_button(tr("step7_view_queue", "查看任务队列"), queue)
        layout.addWidget(self.queue_button)

        self._cancel_widget = QWidget()
        cancel_row = QHBoxLayout(self._cancel_widget)
        cancel_row.setContentsMargins(0, 0, 0, 0)
        cancel_row.setSpacing(8)
        cancel_row.addWidget(QLabel(tr("queue_jobid", "任务 ID:")))
        self.job_edit = LineEdit()
        self.job_edit.setStyleSheet(input_style())
        self.job_edit.setPlaceholderText(tr("enter_jobid_placeholder", "SLURM 任务号"))
        cancel_row.addWidget(self.job_edit, 1)
        cancel_row.addWidget(create_button(tr("cancel_task", "取消任务"), cancel))
        layout.addWidget(self._cancel_widget)

        self._group.viewLayout.setContentsMargins(11, 10, 11, 12)
        self._group.viewLayout.addLayout(layout)
        self.widget = self._group
        self.set_connected(False)

    def job_id(self) -> str:
        return self.job_edit.text().strip()

    def set_connected(self, connected: bool) -> None:
        status = tr("step6_connected", "[已连接]") if connected else tr("step6_not_connected", "[未连接]")
        try:
            self._group.setTitle(f"{tr(_TITLE_KEY, _TITLE_DEFAULT)}  {status}")
        except Exception:
            pass
        self.queue_button.setVisible(connected)
        self._cancel_widget.setVisible(connected)
