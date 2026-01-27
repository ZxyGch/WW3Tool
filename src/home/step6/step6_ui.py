"""
第六步：服务器操作模块
包含UI创建（函数逻辑已拆分到 step6_service.py）
"""
import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from qfluentwidgets import PrimaryPushButton, LineEdit
from setting.language_manager import tr
from setting.config import SERVER_PATH
from .step6_service import StepSixFunctionsMixin
from ..utils import create_header_card


class HomeStepSixCard(StepSixFunctionsMixin):
    """第六步：服务器操作 Mixin"""

    def create_step_6_card(self, content_widget, content_layout):
        """创建第六步：服务器操作的UI"""
        # 使用通用函数创建卡片
        step6_card, step6_card_layout = create_header_card(
            content_widget,
            tr("step7_title", "第六步：服务器操作")
        )
        self.step7_card = step6_card  # 保存引用以便控制可见性

        # 按钮样式：使用主题适配的样式
        button_style = self._get_button_style()

        # 输入框样式：使用主题适配的样式
        input_style = self._get_input_style()

        # 服务器路径输入
        path_frame = QWidget()
        path_layout = QHBoxLayout(path_frame)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(5)
        path_label = QLabel(tr("step7_server_path", "服务器路径:"))
        path_layout.addWidget(path_label)
        self.ssh_dest_edit = LineEdit()
        if self.selected_folder:
            folder_name = os.path.basename(self.selected_folder)
            self.ssh_dest_edit.setText(f"{SERVER_PATH}{folder_name}")
        else:
            self.ssh_dest_edit.setText(SERVER_PATH)
        self.ssh_dest_edit.setStyleSheet(input_style)
        path_layout.addWidget(self.ssh_dest_edit)
        step6_card_layout.addWidget(path_frame)

        # 查看文件列表按钮（单独一行）
        self.ls_button = PrimaryPushButton(tr("step7_view_files", "查看文件列表"))
        self.ls_button.setStyleSheet(button_style)
        self.ls_button.setEnabled(False)  # 默认禁用，连接后启用
        self.ls_button.clicked.connect(lambda: self.show_remote_file_list())
        step6_card_layout.addWidget(self.ls_button)

        # 查看任务队列按钮（单独一行）
        self.queue_button = PrimaryPushButton(tr("step7_view_queue", "查看任务队列"))
        self.queue_button.setStyleSheet(button_style)
        self.queue_button.setEnabled(False)  # 默认禁用，连接后启用
        self.queue_button.clicked.connect(lambda: self.view_task_queue())
        step6_card_layout.addWidget(self.queue_button)

        # 上传文件夹按钮
        self.upload_button = PrimaryPushButton(tr("step7_upload", "上传工作目录文件夹到服务器"))
        self.upload_button.setStyleSheet(button_style)
        self.upload_button.setEnabled(False)  # 默认禁用，连接后启用
        self.upload_button.clicked.connect(lambda: self.upload_folder())
        step6_card_layout.addWidget(self.upload_button)

        # 提交计算任务按钮
        self.exec_button = PrimaryPushButton(tr("step7_submit", "提交计算任务"))
        self.exec_button.setStyleSheet(button_style)
        self.exec_button.setEnabled(False)  # 默认禁用，连接后启用
        self.exec_button.clicked.connect(lambda: self.execute_remote_script("submit"))
        step6_card_layout.addWidget(self.exec_button)

        # 检查结果按钮（单独一行）
        self.check_button = PrimaryPushButton(tr("step7_check", "检查是否已完成"))
        self.check_button.setStyleSheet(button_style)
        self.check_button.setEnabled(False)  # 默认禁用，连接后启用
        self.check_button.clicked.connect(lambda: self.check_remote_completion())
        step6_card_layout.addWidget(self.check_button)

        # 清空文件夹按钮（单独一行）
        self.clear_folder_button = PrimaryPushButton(tr("step7_clear", "清空文件夹"))
        self.clear_folder_button.setStyleSheet(button_style)
        self.clear_folder_button.setEnabled(False)  # 默认禁用，连接后启用
        self.clear_folder_button.clicked.connect(lambda: self.clear_remote_folder())
        step6_card_layout.addWidget(self.clear_folder_button)

        # 下载结果按钮（单独一行）
        self.download_button = PrimaryPushButton(tr("step7_download", "下载结果文件到本地"))
        self.download_button.setStyleSheet(button_style)
        self.download_button.setEnabled(False)  # 默认禁用，连接后启用
        self.download_button.clicked.connect(lambda: self.download_remote_nc())
        step6_card_layout.addWidget(self.download_button)

        # 下载 log 文件按钮（单独一行）
        self.download_log_button = PrimaryPushButton(tr("step7_download_log", "下载 log 文件"))
        self.download_log_button.setStyleSheet(button_style)
        self.download_log_button.setEnabled(False)  # 默认禁用，连接后启用
        self.download_log_button.clicked.connect(lambda: self.download_remote_log())
        step6_card_layout.addWidget(self.download_log_button)

        # 设置内容区内边距
        step6_card.viewLayout.setContentsMargins(11, 10, 11, 12)
        step6_card.viewLayout.addLayout(step6_card_layout)
        content_layout.addWidget(step6_card)
