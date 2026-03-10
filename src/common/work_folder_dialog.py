import os
import sys
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QLabel, QVBoxLayout, QHBoxLayout
from qfluentwidgets import PrimaryPushButton, LineEdit, InfoBar, setTheme, Theme, NavigationWidget, MessageBoxBase
import sys
import os
# 添加 main 目录到 Python 路径，以便导入 setting 和 plot 模块
main_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if main_dir not in sys.path:
    sys.path.insert(0, main_dir)
from setting.config import load_config, DEFAULT_CONFIG, get_recent_workdirs, add_recent_workdir, get_default_workdir
from setting.language_manager import tr

QWidget = QtWidgets.QWidget
QFileDialog = QtWidgets.QFileDialog

class WorkFolderDialog(MessageBoxBase):
    """文件夹选择对话框，可用于启动时或主窗口中"""
    # 定义信号：当对话框关闭时发出
    finished = pyqtSignal()
    
    def __init__(self, parent=None, is_startup=False, current_folder=None):
        super().__init__(parent)
        self.is_startup = is_startup  # 标记是否是启动时的对话框
        self.current_folder = current_folder  # 当前工作目录
        self.selected_folder = None  # 初始化选中的文件夹路径
        self.success_message = None  # 初始化成功消息
        self._finished_emitted = False  # 防止重复发出 finished 信号
        
        # 根据场景设置模态类型：启动时使用非模态（允许移动主窗口），其他场景使用应用程序模态

        
        # 隐藏默认的 yes 和 cancel 按钮
        self.hideYesButton()
        self.hideCancelButton()
        
        # 隐藏 buttonLayout 区域（按钮下方的区域）
        self.buttonLayout.parent().setVisible(False)
            
        
        button_style = parent._get_button_style()
    
        input_style = parent._get_input_style()

    
        # 使用 viewLayout 放置内容
        # 文件夹名称输入区域（标签和输入框在同一行）
        
        name_group = QHBoxLayout()
        name_label = QLabel(tr("workdir_dialog_new_name", "新工作目录名称："))
        name_group.addWidget(name_label)
        
        import datetime
        self.name_edit = LineEdit()
        self.name_edit.setText(datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
        self.name_edit.setPlaceholderText(tr("workdir_dialog_name_placeholder", "输入工作目录名称"))
        # 确保输入框样式正确应用
        self.name_edit.setStyleSheet(input_style)
        self.name_edit.setMinimumWidth(200)  # 设置输入框的最小宽度
        name_group.addWidget(self.name_edit, 1)  # 设置拉伸因子，让输入框占据剩余空间
        self.viewLayout.addLayout(name_group)
        
        # 显示最近打开的工作目录（启动时和侧边栏选择文件夹时都显示）
        self._add_recent_workdirs_section()
        
        
        # 在 viewLayout 内部放置两个按钮（与输入框在同一区域）
        
        self.btn_create = PrimaryPushButton(tr("workdir_dialog_create", "创建新工作目录"))
        self.btn_create.setStyleSheet(button_style)

        # 直接连接点击事件
        self.btn_create.clicked.connect(self.create_new)
        self.viewLayout.addWidget(self.btn_create)
        
        self.btn_choose = PrimaryPushButton(tr("workdir_dialog_choose", "选择已有工作目录"))
        self.btn_choose.setStyleSheet(button_style)

        # 直接连接点击事件
        self.btn_choose.clicked.connect(self.choose_existing)
        self.viewLayout.addWidget(self.btn_choose)
        
        # 启动对话框也提供"取消"按钮；启动时按取消则退出客户端
        self.btn_cancel = PrimaryPushButton(tr("cancel", "取消"))
        self.btn_cancel.setStyleSheet(button_style)
        self.btn_cancel.clicked.connect(self.cancel_dialog)
        self.viewLayout.addWidget(self.btn_cancel)
    
    def hide(self):
        """重写 hide 方法，在隐藏时发出信号"""
        super().hide()
        if self._finished_emitted:
            return
        self._finished_emitted = True
        self.finished.emit()

    def _add_recent_workdirs_section(self):
        """添加最近打开的工作目录显示区域"""
        recent_dirs = get_recent_workdirs()
        
        if not recent_dirs:
            return
        
        # 添加分隔线和标题
        separator = QWidget()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: rgba(128, 128, 128, 0.3);")
        self.viewLayout.addWidget(separator)
        
        
        recent_label = QLabel(tr("workdir_dialog_recent", "最近打开的工作目录："))
        recent_label.setStyleSheet("font-weight: normal; margin-top: 8px; margin-bottom: 4px;")
        self.viewLayout.addWidget(recent_label)
        
        # 检查是否有重名的目录（basename相同）
        dir_names = [os.path.basename(d) for d in recent_dirs]
        name_counts = {}
        for name in dir_names:
            name_counts[name] = name_counts.get(name, 0) + 1
        has_duplicate_names = any(count > 1 for count in name_counts.values())
        
        # 为每个最近打开的目录创建可点击的容器
        for dir_path in recent_dirs:
            dir_name = os.path.basename(dir_path)
            
            # 创建容器，设置圆角灰色背景和边框
            dir_container = QWidget()
            dir_container.setCursor(Qt.CursorShape.PointingHandCursor)
            dir_container.setToolTip(dir_path)  # 鼠标悬停时显示完整路径
            
            # 设置容器样式（圆角灰色背景，带边框）
            dir_container.setStyleSheet("""
                QWidget {
                    background-color: rgba(128, 128, 128, 0.1);
                    border: 1px solid rgba(128, 128, 128, 0.3);
                    border-radius: 6px;
                    padding: 8px 12px;
                }
            """)
            
            # 创建水平布局
            dir_layout = QHBoxLayout(dir_container)
            dir_layout.setContentsMargins(0, 0, 0, 0)
            dir_layout.setSpacing(8)
            
            # 图标标签（靠左）
            icon_label = QLabel("📁")
            icon_label.setStyleSheet("font-size: 13px; border: none; background: transparent;")
            dir_layout.addWidget(icon_label)
            
            # 文件名标签（靠右）
            if has_duplicate_names:
                # 如果有重名，直接显示绝对路径
                dir_label = QLabel(dir_path)
            else:
                # 如果没有重名，只显示文件名
                dir_label = QLabel(dir_name)
            
            dir_label.setStyleSheet("font-size: 13px; border: none; background: transparent;")  # 使用默认文本颜色，不设置蓝色，无边框，无背景
            dir_label.setWordWrap(False)
            
            # 添加弹性空间，使文件名靠右显示
            dir_layout.addStretch()
            dir_layout.addWidget(dir_label)
            
            # 添加点击事件到容器
            def make_click_handler(path):
                def handle_click(event):
                    # 确保事件被正确处理
                    if event.button() == Qt.MouseButton.LeftButton:
                        if os.path.exists(path):
                            normalized_path = os.path.abspath(os.path.normpath(path))
                            
                            self.selected_folder = normalized_path
                            self.success_message = (
                                tr("workdir_dialog_choose_success", "选择成功"),
                                tr("workdir_dialog_choose_success_content", "已选择文件夹：{path}").format(path=normalized_path)
                            )
                            # 获取主窗口的 log 方法（如果存在）
                            log_func = None
                            if self.parent() and hasattr(self.parent(), 'log'):
                                log_func = self.parent().log
                               
                            self.hide()
                        else:
                            
                            InfoBar.warning(
                                title=tr("workdir_dialog_not_exists", "目录不存在"),
                                content=tr("workdir_dialog_not_exists_content", "目录已不存在：{path}").format(path=path),
                                duration=2000,
                                parent=self
                            )
                    self.hide()
                return handle_click
            
            # 使用自定义的 mousePressEvent
            dir_container.mousePressEvent = make_click_handler(dir_path)
            
            # 确保容器可以接收鼠标事件
            dir_container.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, False)
            # 确保容器可以接收鼠标事件
            dir_container.setMouseTracking(True)
            
            self.viewLayout.addWidget(dir_container)
     
    
    def cancel_dialog(self):
        """取消按钮的处理函数：启动弹窗点击取消则直接退出客户端"""

        if self.is_startup:
            # 启动阶段，用户点击取消则直接退出应用
            try:
                QtWidgets.QApplication.quit()
            finally:
                # 强制退出，防止窗口未能及时关闭
                import os, sys
                os._exit(0)
        else:
            # 非启动场景，仅关闭弹窗
            self.hide()
    
    def create_new(self):
        """创建新文件夹"""
        
        name = self.name_edit.text().strip()
        if not name:
            InfoBar.warning(
                title=tr("workdir_dialog_tip", "提示"),
                content=tr("workdir_dialog_enter_name", "请输入文件夹名称"),
                duration=2000,
                parent=self
            )
            return
        
        # 使用专门的方法获取默认工作目录（会自动处理目录不存在的情况）
        parent_dir = get_default_workdir(create_if_not_exists=True)
        
        if not parent_dir:
            InfoBar.error(
                title=tr("workdir_dialog_create_failed", "创建失败"),
                content=tr("workdir_dialog_cannot_create", "无法创建默认工作目录"),
                duration=3000,
                parent=self
            )
            return   
        
        new_dir = os.path.join(parent_dir, name)
        
        if os.path.exists(new_dir):
            
            InfoBar.error(
                title=tr("workdir_dialog_exists", "文件夹已存在"),
                content=tr("workdir_dialog_exists_content", "文件夹已存在，无法创建：{path}").format(path=new_dir),
                duration=3000,
                parent=self
            )
            return
        
        try:
            os.makedirs(new_dir, exist_ok=False)
            # 确保 new_dir 是字符串类型
            if isinstance(new_dir, str) and new_dir.strip():
                
                self.selected_folder = os.path.abspath(os.path.normpath(new_dir.strip()))  # 规范化为绝对路径
                self.success_message = (
                    tr("workdir_dialog_create_success", "创建成功"),
                    tr("workdir_dialog_create_success_content", "文件夹已成功创建：{path}").format(path=self.selected_folder)
                )

                add_recent_workdir(self.selected_folder)
                
                # 直接关闭对话框，消息将在对话框关闭后显示
                self.hide()
            else:
                
                InfoBar.error(
                    title=tr("workdir_dialog_create_failed", "创建失败"),
                    content=tr("workdir_dialog_invalid_path", "无效的文件夹路径：{path}").format(path=new_dir),
                    duration=3000,
                    parent=self
                )
        except Exception as e:
            
            InfoBar.error(
                title=tr("workdir_dialog_create_failed", "创建失败"),
                content=tr("workdir_dialog_create_error", "创建文件夹失败：{error}").format(error=str(e)),
                duration=3000,
                parent=self
            )

    def choose_existing(self):
        """选择已有文件夹"""
        # 使用专门的方法获取默认工作目录（选择已有目录时不需要创建）
        start = get_default_workdir(create_if_not_exists=False)
        
        # 如果获取失败，使用当前工作目录
        if not start:
            start = os.getcwd()

        d = QFileDialog.getExistingDirectory(
            self,
            tr("workdir_dialog_select_title", "选择已有文件夹"),
            start,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
        )
        
        if d and isinstance(d, str) and d.strip():
            self.selected_folder = os.path.abspath(os.path.normpath(d.strip()))  # 规范化为绝对路径

            add_recent_workdir(self.selected_folder)

            InfoBar.success(
                title=tr("workdir_dialog_choose_success", "选择成功"),
                content=tr("workdir_dialog_choose_success_content", "已选择文件夹：{path}").format(path=self.selected_folder),
                duration=2000,
                parent=self.parent()
            )

            self.hide()
