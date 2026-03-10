"""
第五步：连接服务器模块 - UI部分
包含连接服务器相关的UI创建
"""
import os
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy, QHeaderView, QTableWidgetItem
from qfluentwidgets import PrimaryPushButton, TableWidget, LineEdit
from setting.language_manager import tr
from setting.config import SERVER_HOST, SERVER_PORT, SERVER_USER, SERVER_PASSWORD, load_config
from ..utils import create_header_card
from .step5_service import StepFiveServiceMixin


class HomeStepFiveCard(StepFiveServiceMixin):
    """第五步：连接服务器"""
    
    def create_step_5_server_card(self, content_widget, content_layout):
        """创建第五步：连接服务器的UI"""
        # 使用通用函数创建卡片（需要保存引用以便更新标题）
        title = tr("step6_title", "第五步：连接服务器") + " " + tr("step6_not_connected", "[未连接]")
        step6_card, step6_card_layout = create_header_card(content_widget, title)
        self.step6_card = step6_card  # 保存引用以便更新标题
        step6_card_layout.setSpacing(0)  # 设置为0，手动控制所有间距
        # 设置左右边距，避免分割线溢出
        step6_card_layout.setContentsMargins(0, 0, 0, 0)

        step6_card.viewLayout.setContentsMargins(0, 10, 0, 12)
        step6_card.viewLayout.setSpacing(0)
        # 按钮样式：使用主题适配的样式
        button_style = self._get_button_style()

        # 输入框样式：使用主题适配的样式
        input_style = self._get_input_style()

        # 连接服务器按钮（用容器包裹，设置左右边距）
        connect_button_container = QWidget()
        connect_button_container.setStyleSheet(input_style)
        connect_button_container_layout = QHBoxLayout(connect_button_container)
        connect_button_container_layout.setContentsMargins(10, 0, 10, 0)  # 左右边距，上下边距为0
        connect_button_container_layout.setSpacing(0)

        # 确保容器本身没有额外的边距
        connect_button_container.setContentsMargins(0, 0, 0, 0)

        self.btn_connect = PrimaryPushButton(tr("step6_connect", "连接服务器"))
        self.btn_connect.setStyleSheet(button_style)
        self.btn_connect.clicked.connect(lambda: self.connect_server())
        connect_button_container_layout.addWidget(self.btn_connect)
        step6_card_layout.addWidget(connect_button_container)
        self.connect_button_container = connect_button_container
        # 按钮和表格容器之间不添加任何间距

        # CPU占用排行标题容器（样式和Slurm 配置一样）
        cpu_title_container = QWidget()
        cpu_title_container.setVisible(False)  # 初始隐藏，与表格同步显示/隐藏
        cpu_title_container.setMinimumHeight(0)
        cpu_title_container.setMaximumHeight(0)
        cpu_title_layout = QHBoxLayout()
        cpu_title_layout.setContentsMargins(13, 0,13, 10)
        cpu_title_layout.setSpacing(10)
        
        # 左侧横线
        cpu_line_left = QtWidgets.QFrame()
        cpu_line_left.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        cpu_line_left.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        cpu_line_left.setFixedHeight(1)
        cpu_line_left.setMinimumHeight(1)
        cpu_line_left.setMaximumHeight(1)
        cpu_line_left.setStyleSheet("background-color: #888888; border: none;")
        cpu_title_layout.addWidget(cpu_line_left)
        
        # 标题标签（居中）
        self.cpu_title_label = QLabel(tr("step6_cpu_ranking", "CPU 占用排行"))
        self.cpu_title_label.setStyleSheet("font-weight: normal; font-size: 14px;")
        self.cpu_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cpu_title_layout.addWidget(self.cpu_title_label)
        
        # 右侧横线
        cpu_line_right = QtWidgets.QFrame()
        cpu_line_right.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        cpu_line_right.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        cpu_line_right.setFixedHeight(1)
        cpu_line_right.setMinimumHeight(1)
        cpu_line_right.setMaximumHeight(1)
        cpu_line_right.setStyleSheet("background-color: #888888; border: none;")
        cpu_title_layout.addWidget(cpu_line_right)
        
        # 设置横线可伸缩
        cpu_title_layout.setStretch(0, 1)  # 左侧横线
        cpu_title_layout.setStretch(2, 1)  # 右侧横线
        
        cpu_title_container.setLayout(cpu_title_layout)
        self.cpu_title_container = cpu_title_container  # 保存引用以便后续控制显示
        step6_card_layout.addWidget(cpu_title_container)

        # CPU占用排行显示区域（使用 TableWidget，完全照搬 ST 版本管理表格样式）
        # 用容器包裹表格，设置左右边距
        cpu_table_container = QWidget()
        cpu_table_container.setVisible(False)  # 初始隐藏，与表格同步显示/隐藏
        # 确保隐藏的容器不占用空间

        cpu_table_container.setMinimumHeight(0)  # 同时设置最小高度为0
        # 设置尺寸策略：隐藏时不占用空间，显示时根据内容调整
        cpu_container_size_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        cpu_table_container.setSizePolicy(cpu_container_size_policy)
        # 确保容器本身没有额外的边距
        cpu_table_container.setContentsMargins(0, 0, 0, 0)
        cpu_table_container_layout = QHBoxLayout(cpu_table_container)
        cpu_table_container_layout.setContentsMargins(10, 0, 10, 0)  # 左右边距，上下边距为0
        cpu_table_container_layout.setSpacing(0)

        self.cpu_table = TableWidget()
        self.cpu_table.setColumnCount(3)
        self.cpu_table.setHorizontalHeaderLabels(['PID', 'USER', 'CPU%'])
        # 隐藏水平表头（与 ST 版本表格一致）
        self.cpu_table.horizontalHeader().setVisible(False)
        self.cpu_table.horizontalHeader().setStretchLastSection(True)  # 最后一列自动拉伸
        self.cpu_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)  # 整行选择
        self.cpu_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)  # 禁止直接编辑
        # 去除边框（与 ST 版本表格一致）
        self.cpu_table.setBorderVisible(False)
        self.cpu_table.setWordWrap(False)
        # 隐藏垂直表头（与 ST 版本表格一致）
        self.cpu_table.verticalHeader().setVisible(False)
        # 设置外边距为0（与 ST 版本表格一致）
        self.cpu_table.setContentsMargins(0, 0, 0, 10)
        self.cpu_table.setRowCount(0)
        # 设置列宽策略：自动拉伸填充
        header = self.cpu_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        # 设置行高：自动调整以适应内容（与 ST 版本表格一致）
        vertical_header = self.cpu_table.verticalHeader()
        vertical_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        # 隐藏垂直滚动条，强制显示所有行（与 ST 版本表格一致）
        self.cpu_table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # 设置大小策略：允许垂直方向扩展
        size_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        size_policy.setVerticalStretch(1)
        self.cpu_table.setSizePolicy(size_policy)
        # 初始状态为未连接，隐藏CPU表格
        self.cpu_table.setVisible(False)
        # 不设置自定义样式表，使用 TableWidget 默认样式（与 ST 版本表格一致）
        cpu_table_container_layout.addWidget(self.cpu_table)
        self.cpu_table_container = cpu_table_container  # 保存引用以便后续控制显示
        step6_card_layout.addWidget(cpu_table_container)
        # 表格和分割线之间不添加间距（布局 spacing 已为 0）

        # CPU表格下方的分割线已移除（不再需要）

        # 任务队列占用排行标题容器（使用和外网格参数一样的样式）
        queue_title_container = QWidget()
        queue_title_container.setVisible(False)  # 初始隐藏，与队列容器同步显示/隐藏
        queue_title_container.setMinimumHeight(0)
        queue_title_container.setMaximumHeight(0)
        queue_title_size_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        queue_title_container.setSizePolicy(queue_title_size_policy)
    
        queue_title_layout = QHBoxLayout(queue_title_container)
        queue_title_layout.setContentsMargins(13, 0,13, 10)
        queue_title_layout.setSpacing(10)
        
        # 左侧横线
        queue_line_left = QtWidgets.QFrame()
        queue_line_left.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        queue_line_left.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        queue_line_left.setFixedHeight(1)
        queue_line_left.setMinimumHeight(1)
        queue_line_left.setMaximumHeight(1)
        queue_line_left.setStyleSheet("background-color: #888888; border: none;")
        queue_title_layout.addWidget(queue_line_left)
        
        # 标题标签（居中）
        self.queue_title_label = QLabel(tr("step6_queue_ranking", "任务队列 占用排行"))
        self.queue_title_label.setStyleSheet("font-weight: normal; font-size: 14px;")
        self.queue_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        queue_title_layout.addWidget(self.queue_title_label)
        
        # 右侧横线
        queue_line_right = QtWidgets.QFrame()
        queue_line_right.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        queue_line_right.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        queue_line_right.setFixedHeight(1)
        queue_line_right.setMinimumHeight(1)
        queue_line_right.setMaximumHeight(1)
        queue_line_right.setStyleSheet("background-color: #888888; border: none;")
        queue_title_layout.addWidget(queue_line_right)
        
        # 设置横线可伸缩
        queue_title_layout.setStretch(0, 1)  # 左侧横线
        queue_title_layout.setStretch(2, 1)  # 右侧横线
        
        self.queue_title_container = queue_title_container  # 保存引用以便后续控制显示
        step6_card_layout.addWidget(queue_title_container)

        # 任务队列显示区域
        queue_container = QWidget()
        queue_container.setVisible(False)  # 初始隐藏
        queue_container.setMaximumHeight(0)
        queue_container.setMinimumHeight(0)
        queue_container_size_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        queue_container.setSizePolicy(queue_container_size_policy)
        queue_container_layout = QVBoxLayout(queue_container)
        queue_container_layout.setContentsMargins(0, 10, 0, 0)
        queue_container_layout.setSpacing(10)

        # 任务列表布局（直接使用，不使用滚动区域）
        self.queue_tasks_layout = QVBoxLayout()
        # 任务列表布局不需要边距，因为父容器已经有边距了
        self.queue_tasks_layout.setContentsMargins(10, 0, 10, 0)
        self.queue_tasks_layout.setSpacing(10)

        queue_container_layout.addLayout(self.queue_tasks_layout)

        self.queue_container = queue_container
        step6_card_layout.addWidget(queue_container)

        # 任务队列分割线
        queue_separator = QWidget()
        queue_separator.setFixedHeight(1)
        # 使用固定高度策略，宽度由布局控制
        queue_separator.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        # 使用主题适配的颜色
        self._update_separator_style(queue_separator)
        queue_separator.setVisible(False)
        queue_separator.setMaximumHeight(0)
        queue_separator.setMinimumHeight(0)
        self.queue_separator = queue_separator
        step6_card_layout.addWidget(queue_separator)
        step6_card_layout.addSpacing(0)

        # 取消任务区域（默认隐藏）
        # 用容器包裹取消任务区域，设置左右边距
        cancel_container = QWidget()
        cancel_container_layout = QHBoxLayout(cancel_container)
        cancel_container_layout.setContentsMargins(16, 0, 14, 0)  # 左右边距+2（从10变成12）
        cancel_container_layout.setSpacing(0)

        self.cancel_frame = QWidget()
        self.cancel_frame.setVisible(False)
        cancel_frame_layout = QHBoxLayout(self.cancel_frame)
        cancel_frame_layout.setContentsMargins(0, 10, 0, 0)
        cancel_frame_layout.setSpacing(5)

        from qfluentwidgets import LineEdit
        self.cancel_jobid_edit = LineEdit()
       
        self.cancel_jobid_edit.setPlaceholderText(tr("enter_jobid_placeholder", "请输入 JobID"))  # 添加 hint
        self.cancel_jobid_edit.setStyleSheet(input_style)  # 应用输入框样式
        cancel_frame_layout.addWidget(self.cancel_jobid_edit, 1)  # 设置拉伸因子，让输入框占据剩余空间
        btn_cancel = PrimaryPushButton(tr("cancel_task", "取消任务"))
        btn_cancel.setStyleSheet(button_style)  # 应用按钮样式
        btn_cancel.clicked.connect(lambda: self.cancel_remote_job())
        cancel_frame_layout.addWidget(btn_cancel)

        cancel_container_layout.addWidget(self.cancel_frame)
        step6_card_layout.addWidget(cancel_container)

        step6_card.viewLayout.addLayout(step6_card_layout)
        content_layout.addWidget(step6_card)
