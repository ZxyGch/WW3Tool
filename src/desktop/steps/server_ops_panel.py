"""第六步：服务器操作 面板（主页步骤区）。"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget
from qfluentwidgets import LineEdit, PrimaryPushButton

from ..components.header_card import create_header_card
from workflows.support.translations import tr


class ServerOpsPanel:
    """服务器操作：查看文件/队列、上传、提交、检查、清空、下载结果/log。"""

    def __init__(
        self,
        parent: QWidget,
        *,
        create_button: Callable[[str, Callable[..., object]], PrimaryPushButton],
        input_style: Callable[[], str],
        list_files: Callable[[], None],
        queue: Callable[[], None],
        upload: Callable[[], None],
        submit: Callable[[], None],
        check: Callable[[], None],
        clear: Callable[[], None],
        download_results: Callable[[], None],
        download_log: Callable[[], None],
    ) -> None:
        group, layout = create_header_card(parent, tr("step7_title", "第六步：服务器操作"))

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        path_row.addWidget(QLabel(tr("step7_server_path", "服务器路径:")))
        self.path_edit = LineEdit()
        self.path_edit.setStyleSheet(input_style())
        self.path_edit.setPlaceholderText("/home/username/ww3_run")
        path_row.addWidget(self.path_edit, 1)
        layout.addLayout(path_row)

        for text, handler in (
            (tr("step7_list_files", "查看文件列表"), list_files),
            (tr("step7_view_queue", "查看任务队列"), queue),
            (tr("step7_upload", "上传工作目录文件夹到服务器"), upload),
            (tr("step7_submit", "提交计算任务"), submit),
            (tr("step7_check", "检查是否已完成"), check),
            (tr("step7_clear", "清空文件夹"), clear),
            (tr("step7_download", "下载结果文件到本地"), download_results),
            (tr("step7_download_log", "下载 log 文件"), download_log),
        ):
            layout.addWidget(create_button(text, handler))

        group.viewLayout.setContentsMargins(11, 10, 11, 12)
        group.viewLayout.addLayout(layout)
        self.widget = group

    def set_server_path(self, path: str) -> None:
        self.path_edit.setText(path or "")

    def remote_dir(self) -> str:
        return self.path_edit.text().strip()
