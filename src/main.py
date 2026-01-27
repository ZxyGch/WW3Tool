import sys
import os

# 确保 main 目录在 Python 路径中
main_dir = os.path.dirname(os.path.abspath(__file__))
if main_dir not in sys.path:
    sys.path.insert(0, main_dir)

from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QDialog
from setting.language_manager import load_language_from_config

# 导入配置
from setting.config import reload_config

# 导入UI组件
from public.work_folder_dialog import WorkFolderDialog

# 导入主窗口
from window import MainWindow

# 重新加载配置以确保全局变量已初始化
reload_config()

if __name__ == '__main__':
    
    app = QApplication(sys.argv)
    
    # 设置应用程序图标
    icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public", "resource", "logo.png")
    
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # 先创建一个默认的主窗口
    main_window = MainWindow()
    main_window.resize(1200, 760)
    main_window.show()

    
    # 然后显示文件夹选择对话框（非模态，允许拖动主窗口）
    folder_dialog = WorkFolderDialog(parent=main_window, is_startup=True)
    folder_dialog.show()

        # 使用循环等待对话框关闭，同时处理事件（允许拖动主窗口）
    while folder_dialog.isVisible():
        app.processEvents()
        QtWidgets.QApplication.processEvents()
   
    main_window._initialize_work_directory(folder_dialog.selected_folder)
    
    # 直接进入事件循环，让对话框和主窗口都能正常响应事件（包括窗口移动）
    # 对话框关闭后会自动触发 finished 信号，初始化工作目录，然后继续运行
    sys.exit(app.exec())
