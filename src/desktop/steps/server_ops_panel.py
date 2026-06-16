"""第六步：服务器操作 面板（主页步骤区）。

[EN] Step 6: Server operations panel (home step area).
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget
from qfluentwidgets import LineEdit, PrimaryPushButton

from ..components.header_card import create_header_card
from workflows.support.translations import tr


class ServerOpsPanel:
    # [EN] Server operations: view files/queue, upload, submit, check, clear, download results/log, exec command.
    """服务器操作：查看文件/队列、上传、提交、检查、清空、下载结果/log、执行命令。"""

    def __init__(
        self,
        parent: QWidget,
        *,
        create_button: Callable[[str, Callable[..., object]], PrimaryPushButton],
        input_style: Callable[[], str],
        list_files: Callable[[], None],
        queue: Callable[[], None],
        upload: Callable[[], None],
        check_idle_resources: Callable[[], None],
        upload_nml: Callable[[], None],
        submit: Callable[[], None],
        check: Callable[[], None],
        clear: Callable[[], None],
        download_results: Callable[[], None],
        download_log: Callable[[], None],
        exec_command: Callable[[], None],
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

        # [EN] Row 1: View directory + Clear directory
        # 第一行：查看目录 + 清空目录
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(create_button(tr("step7_list_files", "查看文件列表"), list_files))
        row1.addWidget(create_button(tr("step7_clear", "清空文件夹"), clear))
        layout.addLayout(row1)

        # [EN] Row 2: Upload directory + Submit task
        # 第二行：上传目录 + 提交任务
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(create_button(tr("step7_upload", "上传工作目录文件夹到服务器"), upload))
        row2.addWidget(create_button(tr("step7_submit", "提交计算任务"), submit))
        layout.addLayout(row2)

        # [EN] Row 3: Slurm idle resources + upload NML files
        # 第三行：检查 Slurm 空闲资源 + 上传 NML 文件
        row3_extra = QHBoxLayout()
        row3_extra.setSpacing(8)
        row3_extra.addWidget(create_button(tr("step7_check_idle_resources", "检查空闲 Node/CPU"), check_idle_resources))
        row3_extra.addWidget(create_button(tr("step7_upload_nml", "上传 NML 到服务器"), upload_nml))
        layout.addLayout(row3_extra)

        # [EN] Row 4: View queue + Check task
        # 第四行：查看任务队列 + 检查任务
        row3 = QHBoxLayout()
        row3.setSpacing(8)
        row3.addWidget(create_button(tr("step7_view_queue", "查看任务队列"), queue))
        row3.addWidget(create_button(tr("step7_check", "检查是否已完成"), check))
        layout.addLayout(row3)

        # [EN] Row 5: Download results + Download log
        # 第五行：下载结果 + 下载日志
        row4 = QHBoxLayout()
        row4.setSpacing(8)
        row4.addWidget(create_button(tr("step7_download", "下载结果文件到本地"), download_results))
        row4.addWidget(create_button(tr("step7_download_log", "下载 log 文件"), download_log))
        layout.addLayout(row4)

        # [EN] Row 6: Execute remote command
        # 第六行：执行远程命令
        cmd_row = QHBoxLayout()
        cmd_row.setSpacing(8)
        self.cmd_edit = LineEdit()
        self.cmd_edit.setStyleSheet(input_style())
        self.cmd_edit.setPlaceholderText(tr("step7_cmd_placeholder", "输入远程命令..."))
        self.cmd_edit.returnPressed.connect(exec_command)
        cmd_row.addWidget(self.cmd_edit, 1)
        cmd_row.addWidget(create_button(tr("step7_exec_cmd", "执行"), exec_command))
        layout.addLayout(cmd_row)

        group.viewLayout.setContentsMargins(11, 10, 11, 12)
        group.viewLayout.addLayout(layout)
        self.widget = group

    def set_server_path(self, path: str) -> None:
        self.path_edit.setText(path or "")

    def remote_dir(self) -> str:
        return self.path_edit.text().strip()
