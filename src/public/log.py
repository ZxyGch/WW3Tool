import sys
import os
import json
import time
import numpy as np
import glob
import subprocess
import shutil
import threading
import multiprocessing
import requests
from base64 import b64encode
# 在 Windows 上需要设置启动方法
if hasattr(multiprocessing, 'set_start_method'):
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass  # 如果已经设置过，忽略错误
from multiprocessing import Process, Queue
import socket
import paramiko
import locale
import matplotlib
matplotlib.use('QtAgg')  # 使用 Qt 后端（兼容 PyQt6）
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib import cm
from netCDF4 import Dataset, num2date
import netCDF4 as nc
from datetime import datetime, timedelta
from PIL import Image
import platform
import re
import cv2
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import QEvent, Qt
QSplitter = QtWidgets.QSplitter
from qfluentwidgets import FluentWindow, PrimaryPushButton, LineEdit, TextEdit, InfoBar, setTheme, Theme
from qfluentwidgets import NavigationItemPosition, NavigationWidget, FluentIcon, HeaderCardWidget, ComboBox, TableWidget
from PyQt6.QtGui import QColor, QIcon
from qfluentwidgets import MessageBoxBase
from PyQt6.QtWidgets import QTableWidgetItem, QHeaderView, QScrollArea
from PyQt6.QtGui import QPixmap
QApplication = QtWidgets.QApplication
QWidget = QtWidgets.QWidget
QVBoxLayout = QtWidgets.QVBoxLayout
QHBoxLayout = QtWidgets.QHBoxLayout
QStackedWidget = QtWidgets.QStackedWidget
QFileDialog = QtWidgets.QFileDialog
QDialog = QtWidgets.QDialog
QLabel = QtWidgets.QLabel
QGridLayout = QtWidgets.QGridLayout
QRadioButton = QtWidgets.QRadioButton
QButtonGroup = QtWidgets.QButtonGroup
QSpinBox = QtWidgets.QSpinBox
import sys
import os
# 添加 main 目录到 Python 路径，以便导入 setting 和 plot 模块
main_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if main_dir not in sys.path:
    sys.path.insert(0, main_dir)
from setting.config import *
from plot.workers import _match_ww3_jason3_worker, _run_jason3_swh_worker, _make_wave_maps_worker

class Log:
    """Logging功能模块"""

    def log(self, msg):
        """写入日志到 TextEdit 控件，并自动滚动到底部（优化版本，减少UI操作）"""
        if hasattr(self, 'log_text') and self.log_text:
            # 使用 append 方法，它已经会自动滚动到底部，减少手动操作
            self.log_text.appendPlainText(str(msg))  # 确保转换为字符串
            # 注意：不要在这里调用 processEvents()，会导致无限递归
            # PyQt 的事件循环会自动处理 UI 更新
        else:
            # 如果 log_text 不存在，输出到控制台
            print(f"[LOG] {msg}")


    def log_update_last_line(self, msg):
        """更新日志的最后一行，而不是追加新行（高度优化版本，最小化UI操作）"""
        if hasattr(self, 'log_text') and self.log_text:
            # 使用 blockSignals 临时禁用信号，减少不必要的更新
            was_blocked = self.log_text.blockSignals(True)
            try:
                cursor = self.log_text.textCursor()
                # 保存当前滚动位置
                scrollbar = self.log_text.verticalScrollBar()
                was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 10

                # 移动到文档末尾
                cursor.movePosition(cursor.MoveOperation.End)
                # 移动到当前行的开头
                cursor.movePosition(cursor.MoveOperation.StartOfLine, cursor.MoveMode.KeepAnchor)
                # 如果当前行不为空，删除它
                if cursor.hasSelection():
                    cursor.removeSelectedText()
                # 插入新内容
                cursor.insertText(msg)
                # 移动到末尾
                cursor.movePosition(cursor.MoveOperation.End)
                self.log_text.setTextCursor(cursor)

                # 如果之前在底部，保持滚动到底部；否则不滚动
                if was_at_bottom:
                    scrollbar.setValue(scrollbar.maximum())
            finally:
                self.log_text.blockSignals(was_blocked)


    def clear_log(self):
        """清空日志"""
        try:
            if hasattr(self, 'log_text') and self.log_text:
                self.log_text.clear()
        except Exception as e:
            print(f"清空日志失败: {e}")


