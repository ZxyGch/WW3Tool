"""
第五步：连接服务器模块
包含连接服务器相关的 UI 和逻辑
"""
import os
import threading
import locale
import socket
import time
from datetime import datetime
import paramiko
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy, QHeaderView, QTableWidgetItem
from qfluentwidgets import PrimaryPushButton, TableWidget, LineEdit
from setting.language_manager import tr
from setting.config import SERVER_HOST, SERVER_PORT, SERVER_USER, SERVER_PASSWORD, load_config
from .utils import create_header_card


class HomeStepFiveCard:
    """第五步：连接服务器 Mixin"""
    
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

    def _set_conn_status_safe(self, text):
        """在主线程更新连接状态"""
        try:
            old_text = ""
            if hasattr(self, 'step6_card') and self.step6_card:
                # 从标题中提取旧状态
                try:
                    # title可能是属性而不是方法
                    if hasattr(self.step6_card, 'title'):
                        if callable(self.step6_card.title):
                            current_title = self.step6_card.title()
                        else:
                            current_title = self.step6_card.title
                        if isinstance(current_title, str) and "[" in current_title and "]" in current_title:
                            old_text = current_title.split("[")[1].split("]")[0]
                except Exception:
                    # 静默失败，不显示错误日志
                    pass

            # 更新标题栏中的状态（在标题中使用HTML富文本让状态靠右显示）
           
            if hasattr(self, 'step6_card') and self.step6_card:
                connected_text = tr("connected", "已连接")
                # 检查文本是否匹配（支持中英文）
                is_connected = (text == connected_text or text.startswith(connected_text))
                status_color = "#00AA00" if is_connected else "#FF0000"
                status_text = f"[{text}]"
                # 使用QLabel的富文本功能让状态靠右显示
                title_text = tr("step6_title", "第五步：连接服务器")
                new_title = f'{title_text} <span style="float: right; color: {status_color};">{status_text}</span>'
                self.step6_card.setTitle(new_title)
        except Exception:
            # 静默失败，不显示错误日志
            pass

    def _clear_cpu_frame(self):
        """清空CPU占用排行显示区域"""
        if hasattr(self, 'cpu_table') and self.cpu_table:
            self.cpu_table.setRowCount(0)

    def _update_cpu_table(self, rows):
        """在主线程中更新 CPU 表格（槽函数）"""
        try:
            if not hasattr(self, 'cpu_table') or not self.cpu_table:
                self.log("❌ CPU table 不存在")
                return

            # 过滤有效行（跳过表头）
            valid_rows = []
            for row in rows:
                # 支持既有字符串行，也支持 [pid, user, cpu] 列表
                if isinstance(row, (list, tuple)):
                    parts = [str(p) for p in row]
                else:
                    row_stripped = str(row).strip()
                    if not row_stripped or row_stripped.startswith('PID') or 'USER' in row_stripped or '%CPU' in row_stripped:
                        continue
                    parts = row_stripped.split(None, 2)
                if len(parts) >= 3:
                    try:
                        int(parts[0])
                        valid_rows.append(parts)
                    except ValueError:
                        continue

            if len(valid_rows) == 0:
                self.log("⚠️ 没有有效的进程数据")
                self._clear_cpu_frame()
                return

            # 先清空表格
            self._clear_cpu_frame()

            # 设置行数（包含表头行）
            self.cpu_table.setRowCount(len(valid_rows) + 1)

            # 第一行：表头（作为数据行）
            header_item0 = QTableWidgetItem("PID")
            header_item0.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            header_item1 = QTableWidgetItem("USER")
            header_item1.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)
            header_item2 = QTableWidgetItem("CPU%")
            header_item2.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            self.cpu_table.setItem(0, 0, header_item0)
            self.cpu_table.setItem(0, 1, header_item1)
            self.cpu_table.setItem(0, 2, header_item2)

            # 填充数据（从第二行开始）
            for i, parts in enumerate(valid_rows):
                pid, user, cpu = parts[0], parts[1], parts[2]

                item0 = QTableWidgetItem(str(pid))
                item0.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                item1 = QTableWidgetItem(str(user))
                item1.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)
                item2 = QTableWidgetItem(str(cpu))
                item2.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
                self.cpu_table.setItem(i + 1, 0, item0)
                self.cpu_table.setItem(i + 1, 1, item1)
                self.cpu_table.setItem(i + 1, 2, item2)

            # 自动调整行高以适应内容
            self.cpu_table.resizeRowsToContents()

            # 根据行数动态调整表格高度
            row_count = self.cpu_table.rowCount()
            if row_count > 0:
                total_height = 0
                for i in range(row_count):
                    total_height += self.cpu_table.rowHeight(i)
                content_height = max(80, total_height + 6)
            else:
                content_height = 80
            self.cpu_table.setMinimumHeight(content_height)
            self.cpu_table.setMaximumHeight(16777215)

            # 显示表格和标题
            if hasattr(self, 'cpu_table_container') and self.cpu_table_container:
                self.cpu_table_container.setVisible(True)
            if hasattr(self, 'cpu_title_container') and self.cpu_title_container:
                self.cpu_title_container.setVisible(True)
                self.cpu_title_container.setMinimumHeight(0)
                self.cpu_title_container.setMaximumHeight(16777215)
            self.cpu_table.setVisible(True)

            # 刷新
            self.cpu_table.update()
            self.cpu_table.repaint()
            QtWidgets.QApplication.processEvents()
        except Exception as update_err:
            self.log(f"❌ 更新 CPU table 时出错: {update_err}")
            import traceback
            self.log(traceback.format_exc())

    def _clear_queue_table(self):
        """清空任务队列表格（原版逻辑）"""
        if not hasattr(self, 'queue_tasks_layout') or not self.queue_tasks_layout:
            return
        if not hasattr(self, 'queue_container') or not self.queue_container:
            return

        # 隐藏任务队列标签
        if hasattr(self, 'queue_title_container') and self.queue_title_container:
            self.queue_title_container.setVisible(False)
            self.queue_title_container.setMaximumHeight(0)
            self.queue_title_container.setMinimumHeight(0)

        # 隐藏任务队列容器
        if hasattr(self, 'queue_container') and self.queue_container:
            self.queue_container.setVisible(False)
            self.queue_container.setMaximumHeight(0)
            self.queue_container.setMinimumHeight(0)

        # 隐藏取消任务区域
        if hasattr(self, 'cancel_frame') and self.cancel_frame:
            self.cancel_frame.setVisible(False)

        self.queue_container.setUpdatesEnabled(False)
        widgets_to_delete = []
        while self.queue_tasks_layout.count() > 0:
            item = self.queue_tasks_layout.takeAt(0)
            if item:
                widget = item.widget()
                if widget:
                    widgets_to_delete.append(widget)
                    self.queue_tasks_layout.removeWidget(widget)
                    widget.setParent(None)
        for widget in widgets_to_delete:
            widget.deleteLater()
        QtWidgets.QApplication.processEvents()
        QtWidgets.QApplication.processEvents()
        self.queue_container.setMaximumHeight(16777215)
        self.queue_container.setMinimumHeight(0)
        self.queue_container.setUpdatesEnabled(True)

        if hasattr(self, 'queue_separator') and self.queue_separator:
            if self.queue_separator.isVisible():
                self.queue_separator.setVisible(False)
                self.queue_separator.setFixedHeight(0)
                self.queue_separator.setMaximumHeight(0)
                self.queue_separator.setMinimumHeight(0)

    def _update_queue_table(self, task_lines, time_cn):
        """在主线程中更新任务队列表格（原版逻辑）"""
        try:
            if not hasattr(self, 'queue_container') or not self.queue_container:
                return

            if not task_lines or len(task_lines) == 0:
                self._clear_queue_table()
                return

            STATE_MAP = {
                "RUNNING": tr("queue_status_running", "运行中"),
                "PENDING": tr("queue_status_pending", "等待中"),
                "COMPLETI": tr("queue_status_completed", "已完成"),
                "COMPLETING": tr("queue_status_completing", "完成中"),
                "CONFIGURING": tr("queue_status_configuring", "配置中"),
                "SUSPENDED": tr("queue_status_suspended", "挂起"),
                "CANCELLED": tr("queue_status_cancelled", "已取消"),
                "FAILED": tr("queue_status_failed", "失败"),
                "TIMEOUT": tr("queue_status_timeout", "超时"),
            }

            valid_tasks = []
            active_states = {"RUNNING", "PENDING", "COMPLETING", "CONFIGURING", "SUSPENDED"}
            for ln in task_lines:
                if not ln or not ln.strip():
                    continue
                parts = ln.split()
                if len(parts) < 9:
                    continue
                try:
                    jobid, partition, name, state, time_val, nodes, nodelist = (
                        parts[0], parts[1], parts[2], parts[4], parts[5], parts[7], " ".join(parts[8:])
                    )
                    if state not in active_states:
                        continue
                    state_cn = STATE_MAP.get(state, state)
                    valid_tasks.append({
                        'JobID': jobid,
                        'CPU': partition,
                        '作业名': name,
                        '状态': state_cn,
                        '已运行': time_val,
                        '节点数': nodes,
                        '节点列表': nodelist
                    })
                except (IndexError, ValueError):
                    continue

            if len(valid_tasks) == 0:
                self._clear_queue_table()
                if hasattr(self, 'queue_title_container') and self.queue_title_container:
                    self.queue_title_container.setVisible(False)
                    self.queue_title_container.setMaximumHeight(0)
                    self.queue_title_container.setMinimumHeight(0)
                return

            from PyQt6.QtWidgets import QSizePolicy
            existing_tables = []
            existing_separators = []
            for i in range(self.queue_tasks_layout.count()):
                item = self.queue_tasks_layout.itemAt(i)
                if item:
                    widget = item.widget()
                    if widget:
                        if isinstance(widget, TableWidget):
                            existing_tables.append(widget)
                        elif isinstance(widget, QWidget) and widget.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Fixed:
                            existing_separators.append(widget)

            need_rebuild = False
            if len(existing_tables) != len(valid_tasks):
                need_rebuild = True
            else:
                for idx, task in enumerate(valid_tasks):
                    if idx >= len(existing_tables):
                        need_rebuild = True
                        break
                    task_table = existing_tables[idx]
                    id_item = task_table.item(0, 1)
                    if not id_item or id_item.text() != str(task.get('JobID', '')):
                        need_rebuild = True
                        break

            if not need_rebuild:
                self.queue_container.setUpdatesEnabled(False)
                for idx, task in enumerate(valid_tasks):
                    task_table = existing_tables[idx]
                    task_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
                    task_table.horizontalHeader().setStretchLastSection(True)
                    task_table.setWordWrap(True)
                    fields = [
                        (tr("queue_jobid", "JobID:"), task.get('JobID', '')),
                        (tr("queue_cpu", "CPU:"), task.get('CPU', '')),
                        (tr("queue_job_name", "作业名:"), task.get('作业名', '')),
                        (tr("queue_status", "状态:"), task.get('状态', '')),
                        (tr("queue_runtime", "已运行:"), task.get('已运行', '')),
                        (tr("queue_node_num", "节点数:"), task.get('节点数', '')),
                        (tr("queue_node_list", "节点列表:"), task.get('节点列表', ''))
                    ]
                    row_idx = 0
                    for label, value in fields:
                        label_item = task_table.item(row_idx, 0)
                        if label_item:
                            label_item.setText(label)
                        else:
                            label_item = QTableWidgetItem(label)
                            label_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                            task_table.setItem(row_idx, 0, label_item)
                        value_item = task_table.item(row_idx, 1)
                        if value_item:
                            value_item.setText(str(value))
                        else:
                            value_item = QTableWidgetItem(str(value))
                            value_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
                            task_table.setItem(row_idx, 1, value_item)
                        row_idx += 1

                    task_table.resizeRowsToContents()
                    row_count = task_table.rowCount()
                    if row_count > 0:
                        total_height = 0
                        for i in range(row_count):
                            total_height += task_table.rowHeight(i)
                        content_height = max(100, total_height + 10)
                    else:
                        content_height = 100
                    task_table.setMinimumHeight(content_height)
                    task_table.setMaximumHeight(16777215)

                total_items = self.queue_tasks_layout.count()
                expected_items = len(valid_tasks) * 2 - 1
                if total_items > expected_items:
                    items_to_remove = total_items - expected_items
                    for _ in range(items_to_remove):
                        last_item = self.queue_tasks_layout.takeAt(self.queue_tasks_layout.count() - 1)
                        if last_item:
                            widget = last_item.widget()
                            if widget:
                                widget.setParent(None)
                                widget.deleteLater()
                self.queue_container.setUpdatesEnabled(True)
            else:
                self.queue_container.setUpdatesEnabled(False)
                widgets_to_delete = []
                while self.queue_tasks_layout.count() > 0:
                    item = self.queue_tasks_layout.takeAt(0)
                    if item:
                        widget = item.widget()
                        if widget:
                            widgets_to_delete.append(widget)
                            self.queue_tasks_layout.removeWidget(widget)
                            widget.setParent(None)
                for widget in widgets_to_delete:
                    widget.deleteLater()

                for idx, task in enumerate(valid_tasks):
                    task_table = TableWidget()
                    task_table.setColumnCount(2)
                    task_table.setHorizontalHeaderLabels([tr("queue_label", "字段"), tr("queue_value", "值")])
                    task_table.horizontalHeader().setVisible(False)
                    task_table.horizontalHeader().setStretchLastSection(True)
                    task_table.verticalHeader().setVisible(False)
                    task_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
                    task_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
                    task_table.setBorderVisible(False)
                    task_table.setWordWrap(True)
                    task_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
                    task_table.setRowCount(7)

                    fields = [
                        (tr("queue_jobid", "JobID:"), task.get('JobID', '')),
                        (tr("queue_cpu", "CPU:"), task.get('CPU', '')),
                        (tr("queue_job_name", "作业名:"), task.get('作业名', '')),
                        (tr("queue_status", "状态:"), task.get('状态', '')),
                        (tr("queue_runtime", "已运行:"), task.get('已运行', '')),
                        (tr("queue_node_num", "节点数:"), task.get('节点数', '')),
                        (tr("queue_node_list", "节点列表:"), task.get('节点列表', ''))
                    ]
                    for row_idx, (label, value) in enumerate(fields):
                        label_item = QTableWidgetItem(label)
                        label_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                        value_item = QTableWidgetItem(str(value))
                        value_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
                        task_table.setItem(row_idx, 0, label_item)
                        task_table.setItem(row_idx, 1, value_item)

                    task_table.resizeRowsToContents()
                    total_height = sum(task_table.rowHeight(i) for i in range(task_table.rowCount()))
                    task_table.setMinimumHeight(max(100, total_height + 10))
                    task_table.setMaximumHeight(16777215)

                    self.queue_tasks_layout.addWidget(task_table)

                    if idx < len(valid_tasks) - 1:
                        sep = QWidget()
                        sep.setFixedHeight(1)
                        sep.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                        self._update_separator_style(sep)
                        self.queue_tasks_layout.addWidget(sep)

                self.queue_container.setUpdatesEnabled(True)

            has_tasks = len(valid_tasks) > 0
            if hasattr(self, 'queue_title_container') and self.queue_title_container:
                self.queue_title_container.setVisible(has_tasks)
                self.queue_title_container.setMaximumHeight(16777215 if has_tasks else 0)
                self.queue_title_container.setMinimumHeight(0)
            if hasattr(self, 'queue_container') and self.queue_container:
                self.queue_container.setVisible(has_tasks)
                self.queue_container.setMaximumHeight(16777215 if has_tasks else 0)
                self.queue_container.setMinimumHeight(0)
            if hasattr(self, 'queue_separator') and self.queue_separator:
                # 取消任务区域上方不显示分割线
                self.queue_separator.setVisible(False)
                self.queue_separator.setMaximumHeight(0)
                self.queue_separator.setMinimumHeight(0)

            # 显示/隐藏取消任务区域（与原版一致）
            if hasattr(self, 'cancel_frame') and self.cancel_frame:
                self.cancel_frame.setVisible(has_tasks)
            QtWidgets.QApplication.processEvents()
        except Exception as e:
            self.log(f"❌ 更新任务队列表格失败: {e}")
            import traceback
            self.log(traceback.format_exc())

    def connect_server(self):
        """连接服务器"""
        try:
            # 从配置中读取服务器连接信息
            current_config = load_config()
            host = current_config.get("SERVER_HOST", SERVER_HOST or "")
            port = int(current_config.get("SERVER_PORT", SERVER_PORT or "22"))
            username = current_config.get("SERVER_USER", SERVER_USER or "")
            password = current_config.get("SERVER_PASSWORD", SERVER_PASSWORD or "")
            
            if not host or not username:
                self.log("❌ 请先在设置中配置服务器地址和用户名")
                self.status_signal.emit(tr("step6_not_connected", "未连接"))
                return
            
            # 禁用连接按钮
            if hasattr(self, 'btn_connect'):
                self.btn_connect.setEnabled(False)
            
            # 在后台线程中连接
            def connect_in_thread():
                try:
                    self.log(f"🔄 正在连接服务器 {host}:{port}...")
                    
                    # 创建 SSH 客户端
                    ssh = paramiko.SSHClient()
                    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    
                    # 连接服务器
                    ssh.connect(
                        hostname=host,
                        port=port,
                        username=username,
                        password=password,
                        timeout=10
                    )
                    
                    # 保存连接
                    self.ssh = ssh
                    self._last_conn_args = (host, port, username, password)
                    
                    # 更新状态
                    self.status_signal.emit(tr("connected", "已连接"))
                    self.log_signal.emit(tr("connect_success_log", "✅ 连接服务器成功"))
                    
                    # 启用相关按钮（切回主线程）
                    try:
                        QtCore.QMetaObject.invokeMethod(
                            self,
                            "_enable_server_buttons",
                            QtCore.Qt.ConnectionType.QueuedConnection
                        )
                    except Exception as invoke_error:
                        self.log_signal.emit(f"⚠️ 启用按钮失败（已连接）：{invoke_error}")
                    
                    # 启动心跳检测和队列更新（切回主线程）
                    if hasattr(self, '_start_heartbeat'):
                        try:
                            QtCore.QMetaObject.invokeMethod(
                                self,
                                "_start_heartbeat",
                                QtCore.Qt.ConnectionType.QueuedConnection
                            )
                        except Exception as invoke_error:
                            self.log_signal.emit(f"⚠️ 启动心跳失败（已连接）：{invoke_error}")
                    if hasattr(self, '_start_queue_timer'):
                        try:
                            QtCore.QMetaObject.invokeMethod(
                                self,
                                "_start_queue_timer",
                                QtCore.Qt.ConnectionType.QueuedConnection
                            )
                        except Exception as invoke_error:
                            self.log_signal.emit(f"⚠️ 启动队列刷新失败（已连接）：{invoke_error}")
                    
                except Exception as e:
                    self.log_signal.emit(f"❌ 连接服务器失败：{e}")
                    self.status_signal.emit(tr("step6_not_connected", "未连接"))
                    self.ssh = None
                    QtCore.QTimer.singleShot(0, self._hide_cpu_and_queue)
                    QtCore.QTimer.singleShot(0, self._show_connect_button)
                    QtCore.QTimer.singleShot(0, self._stop_queue_polling)
                    QtCore.QTimer.singleShot(0, self._disable_server_buttons)
                finally:
                    # 重新启用连接按钮
                    if hasattr(self, 'btn_connect'):
                        try:
                            QtCore.QMetaObject.invokeMethod(
                                self,
                                "set_btn_connect_enabled_true",
                                QtCore.Qt.ConnectionType.QueuedConnection
                            )
                        except Exception:
                            pass
            
            # 启动连接线程
            threading.Thread(target=connect_in_thread, daemon=True).start()
            
        except Exception as e:
            self.log(f"❌ 连接服务器出错：{e}")
            self.status_signal.emit(tr("step6_not_connected", "未连接"))
            if hasattr(self, 'btn_connect'):
                self.btn_connect.setEnabled(True)

    @QtCore.pyqtSlot()
    def _enable_server_buttons(self):
        """启用服务器相关按钮"""
        try:
            # 连接成功后隐藏连接按钮
            self._hide_connect_button()

            # 连接成功后先显示 CPU/队列容器（与原版一致）
            try:
                if hasattr(self, 'cpu_table') and self.cpu_table:
                    self.cpu_table.setVisible(True)
                    self.cpu_table.show()
                    self.cpu_table.update()
                if hasattr(self, 'cpu_title_container') and self.cpu_title_container:
                    self.cpu_title_container.setVisible(True)
                    self.cpu_title_container.setMaximumHeight(16777215)
                    self.cpu_title_container.setMinimumHeight(0)
                if hasattr(self, 'cpu_table_container') and self.cpu_table_container:
                    self.cpu_table_container.setVisible(True)
                    self.cpu_table_container.setMaximumHeight(16777215)
                    self.cpu_table_container.setMinimumHeight(0)
                    self.cpu_table_container.setContentsMargins(0, 0, 0, 0)
                    container_layout = self.cpu_table_container.layout()
                    if container_layout:
                        container_layout.setContentsMargins(10, 0, 10, 0)
                if hasattr(self, 'queue_title_container') and self.queue_title_container:
                    self.queue_title_container.setVisible(False)
                    self.queue_title_container.setMaximumHeight(0)
                    self.queue_title_container.setMinimumHeight(0)
                if hasattr(self, 'queue_container') and self.queue_container:
                    self.queue_container.setVisible(False)
                    self.queue_container.setMaximumHeight(0)
                    self.queue_container.setMinimumHeight(0)
                if hasattr(self, 'queue_separator') and self.queue_separator:
                    self.queue_separator.setVisible(False)
                    self.queue_separator.setMaximumHeight(0)
                    self.queue_separator.setMinimumHeight(0)
                QtWidgets.QApplication.processEvents()
            except Exception:
                pass

            # 启用第六步的按钮（如果存在）
            if hasattr(self, 'ls_button'):
                self.ls_button.setEnabled(True)
            if hasattr(self, 'queue_button'):
                self.queue_button.setEnabled(True)
            if hasattr(self, 'upload_button'):
                self.upload_button.setEnabled(True)
            if hasattr(self, 'exec_button'):
                self.exec_button.setEnabled(True)
            if hasattr(self, 'check_button'):
                self.check_button.setEnabled(True)
            if hasattr(self, 'clear_folder_button'):
                self.clear_folder_button.setEnabled(True)
            if hasattr(self, 'download_button'):
                self.download_button.setEnabled(True)
            if hasattr(self, 'download_log_button'):
                self.download_log_button.setEnabled(True)
            
            # 延迟启动队列监控（与原版一致）
            try:
                def start_monitoring():
                    if not self.ssh and self._last_conn_args:
                        host, port_i, user, pwd = self._last_conn_args
                        try:
                            self.ssh = paramiko.SSHClient()
                            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                            self.ssh.connect(
                                hostname=host,
                                port=port_i,
                                username=user,
                                password=pwd,
                                look_for_keys=False,
                                allow_agent=False,
                                timeout=15,
                                banner_timeout=200
                            )
                        except Exception:
                            QtCore.QTimer.singleShot(1000, start_monitoring)
                            return
                    self._start_queue_timer()
                QtCore.QTimer.singleShot(500, start_monitoring)
            except Exception:
                pass
        except Exception:
            pass

    def _disable_server_buttons(self):
        """断开连接时禁用第六步按钮"""
        try:
            if hasattr(self, 'ls_button'):
                self.ls_button.setEnabled(False)
            if hasattr(self, 'queue_button'):
                self.queue_button.setEnabled(False)
            if hasattr(self, 'upload_button'):
                self.upload_button.setEnabled(False)
            if hasattr(self, 'exec_button'):
                self.exec_button.setEnabled(False)
            if hasattr(self, 'check_button'):
                self.check_button.setEnabled(False)
            if hasattr(self, 'clear_folder_button'):
                self.clear_folder_button.setEnabled(False)
            if hasattr(self, 'download_button'):
                self.download_button.setEnabled(False)
            if hasattr(self, 'download_log_button'):
                self.download_log_button.setEnabled(False)
        except Exception:
            pass

    def cancel_remote_job(self):
        """取消远程任务"""
        try:
            # 检查是否已连接
            if not hasattr(self, 'ssh') or self.ssh is None:
                self.log(tr("cancel_task_not_connected", "⚠️ 当前未连接服务器，无法取消任务。"))
                return
            
            # 获取 JobID
            if not hasattr(self, 'cancel_jobid_edit') or not self.cancel_jobid_edit:
                self.log("❌ 无法获取任务ID输入框")
                return
            
            jobid = self.cancel_jobid_edit.text().strip()
            if not jobid:
                self.log("❌ 请输入要取消的任务ID")
                return
            
            # 在后台线程中执行取消命令
            def cancel_in_thread():
                try:
                    self.log_signal.emit(f"🔄 正在取消任务 {jobid}...")
                    
                    # 执行 scancel 命令
                    stdin, stdout, stderr = self.ssh.exec_command(f"scancel {jobid}")
                    exit_status = stdout.channel.recv_exit_status()
                    
                    if exit_status == 0:
                        self.log_signal.emit(f"✅ 已成功取消任务 {jobid}")
                        # 清空输入框
                        QtCore.QTimer.singleShot(0, lambda: self.cancel_jobid_edit.clear())
                    else:
                        error_msg = stderr.read().decode('utf-8', errors='ignore').strip()
                        if error_msg:
                            self.log_signal.emit(f"❌ 取消任务失败：{error_msg}")
                        else:
                            self.log_signal.emit(f"❌ 取消任务失败（返回码：{exit_status}）")
                    
                except Exception as e:
                    self.log_signal.emit(f"❌ 取消任务出错：{e}")
            
            # 启动取消线程
            threading.Thread(target=cancel_in_thread, daemon=True).start()
            
        except Exception as e:
            self.log(f"❌ 取消任务出错：{e}")

    @QtCore.pyqtSlot()
    def set_btn_connect_enabled_true(self):
        """主线程中恢复连接按钮可用"""
        try:
            if hasattr(self, 'btn_connect') and self.btn_connect:
                self.btn_connect.setEnabled(True)
        except Exception:
            pass

    @QtCore.pyqtSlot()
    def _start_heartbeat(self):
        """启动 SSH 心跳检测（定时检查连接状态）"""
        try:
            if not hasattr(self, "_heartbeat_timer") or self._heartbeat_timer is None:
                self._heartbeat_timer = QtCore.QTimer(self)
                self._heartbeat_timer.timeout.connect(self._check_ssh_heartbeat)
            if not self._heartbeat_timer.isActive():
                self._heartbeat_timer.start(8000)
            self._check_ssh_heartbeat()
        except Exception:
            pass

    def _stop_heartbeat(self):
        """停止 SSH 心跳检测"""
        try:
            if hasattr(self, "_heartbeat_timer") and self._heartbeat_timer:
                self._heartbeat_timer.stop()
        except Exception:
            pass

    @QtCore.pyqtSlot()
    def _start_queue_timer(self):
        """启动任务队列轮询（原版逻辑）"""
        try:
            self._start_queue_polling()
        except Exception:
            pass

    def _stop_queue_timer(self):
        """停止 CPU/队列自动刷新定时器"""
        try:
            self._stop_queue_polling()
        except Exception:
            pass

    def _check_ssh_heartbeat(self):
        """检查 SSH 连接是否存活，并更新 UI"""
        try:
            is_alive = False
            if hasattr(self, "_is_ssh_alive"):
                is_alive = self._is_ssh_alive(self.ssh)
            else:
                if self.ssh is not None:
                    transport = self.ssh.get_transport()
                    is_alive = transport is not None and transport.is_active()

            if not is_alive:
                if not getattr(self, "_connection_lost", False):
                    self._connection_lost = True
                    self.status_signal.emit(tr("step6_not_connected", "未连接"))
                    self._hide_cpu_and_queue()
                    self._show_connect_button()
            else:
                if getattr(self, "_connection_lost", False):
                    self._connection_lost = False
                    self.status_signal.emit(tr("connected", "已连接"))
                    self._update_cpu_and_queue()
                    self._hide_connect_button()
        except Exception:
            pass

    def _update_cpu_and_queue(self):
        """拉取 CPU 排行和任务队列，并更新 UI"""
        if getattr(self, "_queue_running", False):
            return
        self._queue_running = True

        def _worker():
            try:
                if not self.ssh or (hasattr(self, "_is_ssh_alive") and not self._is_ssh_alive(self.ssh)):
                    self._hide_cpu_and_queue()
                    return

                cpu_data = self._fetch_remote_cpu_ranking()
                if cpu_data is not None:
                    self.update_cpu_table_signal.emit(cpu_data)

                queue_lines = self._fetch_remote_queue_lines()
                time_cn = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.update_queue_table_signal.emit(queue_lines or [], time_cn)
            finally:
                self._queue_running = False

        threading.Thread(target=_worker, daemon=True).start()

    def server_show_top5_by_ps(self):
        """通过 ps 获取 CPU 占用最高的前 5 个进程（原版逻辑）"""
        if not self.ssh or not self._queue_running:
            self._clear_cpu_frame()
            return

        def _worker():
            if not self.ssh or not self._queue_running:
                return
            try:
                cmd = "ps -eo pid,user,pcpu --sort=-pcpu | head -n 6"
                stdin, stdout, stderr = self.ssh.exec_command(cmd, timeout=5)
                out = stdout.read().decode('utf-8', errors='ignore')
                err = stderr.read().decode('utf-8', errors='ignore')

                if not self._queue_running:
                    return

                if err.strip():
                    self.log_signal.emit(f"⚠️ CPU 命令错误输出:\n{err}")
                    QtCore.QTimer.singleShot(0, lambda: self._clear_cpu_frame())
                    return

                lines = [ln for ln in out.splitlines() if ln.strip()]
                if len(lines) <= 1:
                    self.log_signal.emit("⚠️ 数据行数不足，无法显示")
                    QtCore.QTimer.singleShot(0, lambda: self._clear_cpu_frame())
                    return

                rows = lines[1:6]
                self.update_cpu_table_signal.emit(rows)
            except (paramiko.ssh_exception.ChannelException,
                    paramiko.ssh_exception.SSHException,
                    paramiko.ssh_exception.NoValidConnectionsError,
                    EOFError, OSError, socket.error, socket.timeout) as e:
                if not self._connection_lost:
                    self._connection_lost = True
                    err_msg = str(e)
                    self.log_signal.emit(tr("server_connection_disconnected", "⚠️ 服务器连接已断开: {error}").format(error=err_msg))
                self._queue_running = False
                if hasattr(self, 'ssh') and self.ssh:
                    try:
                        self.ssh.close()
                    except:
                        pass
                    self.ssh = None
                self.status_signal.emit(tr("not_connected_disconnected", "未连接(连接断开)"))
                try:
                    QtCore.QMetaObject.invokeMethod(self, "_hide_cpu_and_queue", QtCore.Qt.ConnectionType.QueuedConnection)
                    QtCore.QMetaObject.invokeMethod(self, "_show_connect_button", QtCore.Qt.ConnectionType.QueuedConnection)
                    QtCore.QMetaObject.invokeMethod(self, "_disable_server_buttons", QtCore.Qt.ConnectionType.QueuedConnection)
                except Exception:
                    pass
                QtCore.QTimer.singleShot(0, lambda: self._stop_queue_polling())
                QtCore.QTimer.singleShot(0, lambda: self._clear_cpu_frame())
            except Exception as e:
                if not self._queue_running:
                    return
                err_msg = str(e)
                self.log_signal.emit(f"❌ 获取 CPU 占用排行失败: {err_msg}")
                import traceback
                self.log_signal.emit(traceback.format_exc())
                QtCore.QTimer.singleShot(0, lambda: self._clear_cpu_frame())

        threading.Thread(target=_worker, daemon=True).start()

    def _queue_poll_once(self):
        """轮询服务器作业队列 (squeue -l)，原版逻辑"""
        if not self.ssh or not self._queue_running:
            return

        def _worker():
            if not self.ssh or not self._queue_running:
                return
            try:
                try:
                    locale.setlocale(locale.LC_TIME, 'zh_CN.UTF-8')
                except Exception:
                    pass

                stdin, stdout, stderr = self.ssh.exec_command("squeue -l", get_pty=True, timeout=5)
                stdout_text = stdout.read().decode("utf-8", errors="ignore")
                stderr_text = stderr.read().decode("utf-8", errors="ignore")

                if not self._queue_running:
                    return

                if stderr_text.strip():
                    self.log_signal.emit(f"⚠️ 任务队列命令错误输出:\n{stderr_text}")

                if not stdout_text.strip() and not stderr_text.strip():
                    self.log_signal.emit("⚠️ 任务队列输出为空")
                    QtCore.QTimer.singleShot(0, lambda: self._update_queue_table([], ""))
                    return

                lines = [ln for ln in stdout_text.splitlines() if ln.strip()]
                if len(lines) <= 2:
                    QtCore.QTimer.singleShot(0, lambda: self._update_queue_table([], ""))
                    return

                time_line = lines[0]
                task_lines = lines[2:]

                # 如果只有表头/分割线，没有任务行，直接清空队列
                has_task_line = False
                for ln in task_lines:
                    if len(ln.split()) >= 9:
                        has_task_line = True
                        break
                if not has_task_line:
                    QtCore.QTimer.singleShot(0, lambda: self._update_queue_table([], time_cn))
                    return

                try:
                    try:
                        locale.setlocale(locale.LC_TIME, 'C')
                    except:
                        pass
                    server_time = time.strptime(time_line, "%a %b %d %H:%M:%S %Y")
                    try:
                        locale.setlocale(locale.LC_TIME, 'zh_CN.UTF-8')
                    except:
                        pass
                    time_cn = time.strftime("%Y年%m月%d日 %H:%M:%S", server_time)
                except Exception:
                    time_cn = time_line

                self.update_queue_table_signal.emit(task_lines, time_cn)
            except (paramiko.ssh_exception.ChannelException,
                    paramiko.ssh_exception.SSHException,
                    paramiko.ssh_exception.NoValidConnectionsError,
                    EOFError, OSError, socket.error, socket.timeout) as e:
                if not self._connection_lost:
                    self._connection_lost = True
                    err_msg = str(e)
                    self.log_signal.emit(tr("server_connection_disconnected", "⚠️ 服务器连接已断开: {error}").format(error=err_msg))
                self._queue_running = False
                if hasattr(self, 'ssh') and self.ssh:
                    try:
                        self.ssh.close()
                    except:
                        pass
                    self.ssh = None
                self.status_signal.emit(tr("not_connected_disconnected", "未连接(连接断开)"))
                try:
                    QtCore.QMetaObject.invokeMethod(self, "_hide_cpu_and_queue", QtCore.Qt.ConnectionType.QueuedConnection)
                    QtCore.QMetaObject.invokeMethod(self, "_show_connect_button", QtCore.Qt.ConnectionType.QueuedConnection)
                    QtCore.QMetaObject.invokeMethod(self, "_disable_server_buttons", QtCore.Qt.ConnectionType.QueuedConnection)
                except Exception:
                    pass
                QtCore.QTimer.singleShot(0, lambda: self._stop_queue_polling())
            except Exception as e:
                if not self._queue_running:
                    return
                err_msg = str(e)
                self.log_signal.emit(f"❌ 获取任务队列失败: {err_msg}")
                import traceback
                self.log_signal.emit(traceback.format_exc())

        threading.Thread(target=_worker, daemon=True).start()

    def _start_queue_polling(self):
        """启动任务队列轮询（原版逻辑）"""
        if self._queue_running:
            return
        self._queue_running = True
        self._connection_lost = False
        if self.ssh:
            self._queue_poll_once()
            self.server_show_top5_by_ps()
        self._schedule_queue_next()

    def _schedule_queue_next(self):
        """安排下一次任务队列轮询（原版逻辑）"""
        if not self._queue_running:
            return

        def _tick():
            if self._queue_running and self.ssh:
                try:
                    self._queue_poll_once()
                    self.server_show_top5_by_ps()
                    if self._queue_running:
                        self._schedule_queue_next()
                except Exception as e:
                    if self._queue_running:
                        self.log(f"⚠️ 刷新监控数据时出错: {e}")
                        self._schedule_queue_next()
            elif not self._queue_running:
                return
            elif not self.ssh:
                self._queue_running = False
                return

        if self._queue_timer is not None:
            try:
                self._queue_timer.stop()
            except Exception:
                pass
        self._queue_timer = QtCore.QTimer()
        self._queue_timer.timeout.connect(_tick)
        self._queue_timer.setSingleShot(True)
        self._queue_timer.start(1000)

    def _stop_queue_polling(self):
        """停止任务队列轮询（原版逻辑）"""
        self._queue_running = False
        self._connection_lost = False
        if self._queue_timer is not None:
            try:
                self._queue_timer.stop()
            except Exception:
                pass
            self._queue_timer = None

    def _fetch_remote_cpu_ranking(self):
        """获取远程 CPU 排行数据，返回 [[pid, user, cpu], ...]"""
        try:
            cmd = "ps -eo pid,user,%cpu --sort=-%cpu | head -n 6"
            stdin, stdout, stderr = self.ssh.exec_command(cmd, get_pty=True, timeout=10)
            output = stdout.read().decode("utf-8", errors="ignore").strip()
            err = stderr.read().decode("utf-8", errors="ignore").strip()
            if err:
                return []
            lines = [line for line in output.splitlines() if line.strip()]
            if not lines:
                return []
            # 去掉表头
            data_lines = lines[1:] if len(lines) > 1 else []
            cpu_data = []
            for line in data_lines:
                parts = line.split()
                if len(parts) >= 3:
                    pid, user, cpu_percent = parts[0], parts[1], parts[2]
                    cpu_data.append([pid, user, cpu_percent])
            return cpu_data
        except Exception:
            return []

    def _fetch_remote_queue_lines(self):
        """获取远程任务队列信息，返回字符串列表"""
        try:
            # 使用稳定的格式输出，避免表格对齐导致解析异常
            cmd = "squeue -o '%i %u %T %M %D %R' -h"
            stdin, stdout, stderr = self.ssh.exec_command(cmd, get_pty=True, timeout=10)
            output = stdout.read().decode("utf-8", errors="ignore").strip()
            err = stderr.read().decode("utf-8", errors="ignore").strip()
            if err or not output:
                return []
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            return lines
        except Exception:
            return []

    @QtCore.pyqtSlot()
    def _hide_cpu_and_queue(self):
        """隐藏 CPU 排行和任务队列 UI"""
        try:
            if hasattr(self, "cpu_table") and self.cpu_table:
                self.cpu_table.setVisible(False)
            if hasattr(self, "cpu_table_container") and self.cpu_table_container:
                self.cpu_table_container.setVisible(False)
            if hasattr(self, "cpu_title_container") and self.cpu_title_container:
                self.cpu_title_container.setVisible(False)

            if hasattr(self, "queue_container") and self.queue_container:
                self.queue_container.setVisible(False)
                self.queue_container.setMaximumHeight(0)
                self.queue_container.setMinimumHeight(0)
            if hasattr(self, "queue_title_container") and self.queue_title_container:
                self.queue_title_container.setVisible(False)
            if hasattr(self, "queue_separator") and self.queue_separator:
                self.queue_separator.setVisible(False)
                self.queue_separator.setMaximumHeight(0)
                self.queue_separator.setMinimumHeight(0)
            if hasattr(self, "cancel_frame") and self.cancel_frame:
                self.cancel_frame.setVisible(False)
        except Exception:
            pass

    def _show_queue_section(self):
        """显示任务队列区域（标题/分隔线/容器）"""
        try:
            if hasattr(self, 'queue_container') and self.queue_container:
                self.queue_container.setVisible(True)
                self.queue_container.setMaximumHeight(16777215)
                # 设定一个基础高度，避免布局高度塌缩
                self.queue_container.setMinimumHeight(120)
            if hasattr(self, 'queue_title_container') and self.queue_title_container:
                self.queue_title_container.setVisible(True)
                self.queue_title_container.setMinimumHeight(0)
                self.queue_title_container.setMaximumHeight(16777215)
            if hasattr(self, 'queue_separator') and self.queue_separator:
                self.queue_separator.setVisible(True)
                self.queue_separator.setMaximumHeight(1)
                self.queue_separator.setMinimumHeight(1)
        except Exception:
            pass

    @QtCore.pyqtSlot()
    def _show_connect_button(self):
        """断开连接时显示连接按钮"""
        try:
            if hasattr(self, "connect_button_container") and self.connect_button_container:
                self.connect_button_container.setVisible(True)
            elif hasattr(self, "btn_connect") and self.btn_connect:
                self.btn_connect.setVisible(True)
        except Exception:
            pass

    def _hide_connect_button(self):
        """连接成功后隐藏连接按钮"""
        try:
            if hasattr(self, "connect_button_container") and self.connect_button_container:
                self.connect_button_container.setVisible(False)
            elif hasattr(self, "btn_connect") and self.btn_connect:
                self.btn_connect.setVisible(False)
        except Exception:
            pass
