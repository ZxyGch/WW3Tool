"""
波高图绘制模块
包含波高图绘制的 UI 创建和逻辑
"""

import os
import sys
import glob
import subprocess
import platform
import threading
from multiprocessing import Process, Queue
import numpy as np
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt
from qfluentwidgets import (
    PrimaryPushButton, LineEdit, HeaderCardWidget, InfoBar
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel
)

from setting.config import load_config
from setting.language_manager import tr
from .workers import _make_wave_maps_worker, _make_contour_maps_worker


class WaveHeightPlotMixin:
    """波高图绘制功能 Mixin"""
    
    def _create_wave_height_ui(self, plot_content_widget, plot_content_layout, button_style, input_style):
        """创建波高图绘制 UI"""
        # 波高图绘制卡片
        step8_card = HeaderCardWidget(plot_content_widget)
        step8_card.setTitle(tr("plotting_wave_height", "波高图绘制"))
        step8_card.setStyleSheet("""
            HeaderCardWidget QLabel {
                font-weight: normal;
                margin-left: 0px;
                padding-left: 0px;
            }
        """)
        step8_card.headerLayout.setContentsMargins(11, 10, 11, 12)
        step8_card_layout = QVBoxLayout()
        step8_card_layout.setSpacing(10)
        step8_card_layout.setContentsMargins(0, 0, 0, 0)

        # 时间步长输入
        time_step_frame = QWidget()
        time_step_layout = QHBoxLayout(time_step_frame)
        time_step_layout.setContentsMargins(0, 0, 0, 0)
        time_step_layout.setSpacing(5)

        time_step_label = QLabel(tr("plotting_time_step", "时间步长："))
        time_step_layout.addWidget(time_step_label)

        # 使用主页的 time_step_edit（如果已存在），否则创建新的
        if not hasattr(self, 'time_step_edit'):
            self.time_step_edit = LineEdit()
            self.time_step_edit.setText("6")
        self.time_step_edit.setStyleSheet(input_style)
        time_step_layout.addWidget(self.time_step_edit)

        time_step_unit_label = QLabel(tr("plotting_hour", "小时"))
        time_step_layout.addWidget(time_step_unit_label)

        step8_card_layout.addWidget(time_step_frame)

        # 选择波高文件按钮
        if not hasattr(self, 'btn_choose_wave_height_file'):
            self.btn_choose_wave_height_file = PrimaryPushButton(tr("plotting_choose_wave_height", "选择波高文件"))
            self.btn_choose_wave_height_file.setStyleSheet(button_style)
            self.btn_choose_wave_height_file.clicked.connect(lambda: self.choose_wave_height_file())
        step8_card_layout.addWidget(self.btn_choose_wave_height_file)

        # 检测当前目录是否存在 ww3*.nc 文件（排除 spec），如果存在则自动更新按钮文本（静默，不显示日志）
        if hasattr(self, 'selected_folder') and self.selected_folder:
            wave_files = glob.glob(os.path.join(self.selected_folder, "ww3*.nc"))
            # 排除 spec 文件
            wave_files = [f for f in wave_files if "spec" not in os.path.basename(f).lower()]
            if wave_files:
                file_name = os.path.basename(wave_files[0])
                if len(file_name) > 30:
                    display_name = file_name[:27] + "..."
                else:
                    display_name = file_name
                self.btn_choose_wave_height_file.setText(display_name)
                if hasattr(self, '_set_plot_button_filled'):
                    self._set_plot_button_filled(self.btn_choose_wave_height_file, True)
                # 保存选择的文件路径
                if not hasattr(self, 'selected_wave_height_file') or not self.selected_wave_height_file:
                    self.selected_wave_height_file = wave_files[0]

        # 生成波高图按钮
        if not hasattr(self, 'generate_image_button'):
            self.generate_image_button = PrimaryPushButton(tr("step8_generate", "生成波高图"))
            self.generate_image_button.setStyleSheet(button_style)
            self.generate_image_button.clicked.connect(lambda: self.make_wave_maps())
        step8_card_layout.addWidget(self.generate_image_button)

        # 生成风涌浪图按钮
        if not hasattr(self, 'generate_wind_swell_button'):
            self.generate_wind_swell_button = PrimaryPushButton(tr("plotting_generate_wind_swell", "生成风涌浪图"))
            self.generate_wind_swell_button.setStyleSheet(button_style)
            self.generate_wind_swell_button.clicked.connect(lambda: self.make_wind_swell_maps())
        step8_card_layout.addWidget(self.generate_wind_swell_button)

        # 生成等高线图按钮
        if not hasattr(self, 'generate_contour_button'):
            self.generate_contour_button = PrimaryPushButton(tr("plotting_generate_contour", "生成等高线图"))
            self.generate_contour_button.setStyleSheet(button_style)
            self.generate_contour_button.clicked.connect(self.generate_contour_maps)
        step8_card_layout.addWidget(self.generate_contour_button)

        # 生成波高视频按钮
        if not hasattr(self, 'generate_video_button'):
            self.generate_video_button = PrimaryPushButton(tr("step8_generate_video", "生成波高视频"))
            self.generate_video_button.setStyleSheet(button_style)
            self.generate_video_button.clicked.connect(lambda: self.make_wave_maps(generate_video=True))
        step8_card_layout.addWidget(self.generate_video_button)

        # 查看结果图片按钮
        if not hasattr(self, 'view_image_button'):
            self.view_image_button = PrimaryPushButton(tr("step8_view_images", "查看结果图片"))
            self.view_image_button.setStyleSheet(button_style)
            self.view_image_button.clicked.connect(lambda: self.show_wave_images())
        step8_card_layout.addWidget(self.view_image_button)

        # 打开图片文件夹按钮
        if not hasattr(self, 'open_photo_folder_button'):
            self.open_photo_folder_button = PrimaryPushButton(tr("plotting_open_photo_folder", "打开图片文件夹"))
            self.open_photo_folder_button.setStyleSheet(button_style)
            self.open_photo_folder_button.clicked.connect(lambda: self.open_photo_folder())
        step8_card_layout.addWidget(self.open_photo_folder_button)

        # 设置内容区内边距
        step8_card.viewLayout.setContentsMargins(11, 10, 11, 12)
        step8_card.viewLayout.addLayout(step8_card_layout)
        plot_content_layout.addWidget(step8_card)

    def choose_wave_height_file(self):
        """选择波高文件（只选择，不转换）"""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            tr("plotting_choose_wave_height", "选择波高文件"),
            os.getcwd() if not hasattr(self, 'selected_folder') or not self.selected_folder else self.selected_folder,
            tr("plotting_file_filter_nc", "NetCDF 文件 (*.nc);;所有文件 (*.*)")
        )

        if not file_path:
            return

        # 保存文件路径（规范化路径，在 Windows 上使用 \）
        self.selected_wave_height_file = os.path.normpath(file_path)
        normalized_file_path = os.path.normpath(file_path)
        
        # 更新按钮文本为文件名
        file_name = os.path.basename(normalized_file_path)
        # 如果文件名太长，截断并显示省略号
        if len(file_name) > 30:
            file_name = file_name[:27] + "..."
        
        # 更新科研绘图页面的按钮
        if hasattr(self, 'btn_choose_wave_height_file'):
            self.btn_choose_wave_height_file.setText(file_name)
            self._set_plot_button_filled(self.btn_choose_wave_height_file, True)
        
        # 更新主页的按钮
        if hasattr(self, 'btn_choose_wave_height_file_home'):
            self.btn_choose_wave_height_file_home.setText(file_name)

    def make_wave_maps(self, time_step_hours=None,
                       FIGSIZE=(16,12), DPI=300, UPSAMPLE_FACTOR=3, CLIM_PCT=99.0,
                       CARTOPY_COAST_RES='10m', v=1, generate_video=False):
        """生成波浪图/视频（使用子进程执行）"""
        if time_step_hours is None:
            try:
                time_step_hours = int(self.time_step_edit.text().strip())
            except (ValueError, AttributeError):
                time_step_hours = 6
                self.log(tr("plotting_timestep_read_error_6", "⚠️ 无法读取时间步长，使用默认值 6 小时"))

        # 读取手动风速（用于在结果图上展示），留空则不覆盖
        manual_wind = None
        try:
            if hasattr(self, 'manual_wind_edit'):
                txt = self.manual_wind_edit.text().strip()
                if txt != "":
                    manual_wind = float(txt)
        except Exception:
            manual_wind = None

        if not self.selected_folder:
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return []

        # 禁用对应按钮，防止重复点击
        if generate_video:
            if hasattr(self, 'generate_video_button'):
                self.generate_video_button.setEnabled(False)
                self.generate_video_button.setText(tr("step8_generating", "生成中..."))
        else:
            if hasattr(self, 'generate_image_button'):
                self.generate_image_button.setEnabled(False)
                self.generate_image_button.setText(tr("step8_generating", "生成中..."))

        # 在子进程中执行计算操作
        self._run_make_wave_maps_process(time_step_hours, FIGSIZE, DPI, UPSAMPLE_FACTOR, CLIM_PCT, CARTOPY_COAST_RES, v, manual_wind, generate_video)

    def _run_make_wave_maps_process(self, time_step_hours, FIGSIZE, DPI, UPSAMPLE_FACTOR, CLIM_PCT, CARTOPY_COAST_RES, v, manual_wind=None, generate_video=False, callback=None):
        """在子进程中执行生成波浪图操作

        Args:
            callback: 可选的回调函数，在任务完成时调用
        """
        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == tr("step2_grid_type_nested", "嵌套网格"))

        # 确定数据源文件夹和输出文件夹
        if is_nested_grid:
            # 嵌套模式：从 fine 文件夹读取数据，输出到工作目录
            fine_dir = os.path.join(self.selected_folder, "fine")
            if not os.path.isdir(fine_dir):
                self.log_signal.emit(tr("plotting_fine_folder_not_found", "❌ 未找到 fine 文件夹，请先生成嵌套网格"))
                self._restore_generate_image_button()
                return
            data_folder = fine_dir
            output_folder = self.selected_folder
        else:
            # 普通模式：从工作目录读取数据，输出到工作目录
            data_folder = self.selected_folder
            output_folder = None  # 使用默认值（data_folder/photo）

        # 读取配置：是否显示陆地和海岸线
        current_config = load_config()
        show_land_coast = current_config.get("SHOW_LAND_COASTLINE", True)
        # 处理字符串类型的配置值（JSON 可能将布尔值保存为字符串）
        if isinstance(show_land_coast, str):
            show_land_coast = show_land_coast.lower() in ('true', '1', 'yes')

        # 创建队列用于子进程和主进程之间的通信
        log_queue = Queue()
        result_queue = Queue()

        # 获取选择的波高文件（如果存在），否则自动查找 ww3*.nc（排除 spec）
        wave_height_file = None
        if hasattr(self, 'selected_wave_height_file') and self.selected_wave_height_file and os.path.exists(self.selected_wave_height_file):
            wave_height_file = self.selected_wave_height_file
        else:
            # 自动查找 ww3*.nc 文件（排除 spec）
            wave_files = glob.glob(os.path.join(data_folder, "ww3*.nc"))
            # 排除 spec 文件
            wave_files = [f for f in wave_files if "spec" not in os.path.basename(f).lower()]
            if wave_files:
                wave_height_file = wave_files[0]
                # 保存选择的文件路径
                if not hasattr(self, 'selected_wave_height_file'):
                    self.selected_wave_height_file = wave_height_file

        # 启动子进程
        process = Process(
            target=_make_wave_maps_worker,
            args=(data_folder, time_step_hours, log_queue, result_queue, FIGSIZE, DPI, UPSAMPLE_FACTOR, CLIM_PCT, CARTOPY_COAST_RES, v, output_folder, show_land_coast, manual_wind, generate_video, wave_height_file)
        )
        process.start()

        # 在主线程中监听日志队列并更新UI
        def _poll_logs():
            try:
                # 非阻塞检查队列
                done = False
                while True:
                    try:
                        msg = log_queue.get_nowait()
                        if msg == "__DONE__":
                            done = True
                            break
                        self.log_signal.emit(msg)
                    except:
                        break

                # 检查进程是否完成
                if not done and process.is_alive():
                    # 继续轮询
                    QtCore.QTimer.singleShot(100, _poll_logs)  # 每100ms检查一次
                else:
                    # 进程完成，获取最后的结果
                    if not done:
                        # 如果还没收到完成信号，再尝试获取一次
                        try:
                            while True:
                                try:
                                    msg = log_queue.get_nowait()
                                    if msg == "__DONE__":
                                        done = True
                                        break
                                    if msg != "__DONE__":
                                        self.log_signal.emit(msg)
                                except:
                                    break
                        except:
                            pass

                    # 等待进程结束
                    process.join(timeout=5)

                    # 获取结果
                    try:
                        saved_files = result_queue.get(timeout=2)
                    except Exception as e:
                        self.log_signal.emit(tr("plotting_get_result_failed", "❌ 获取结果失败：{error}").format(error=e))

                    # 恢复对应按钮状态或调用回调
                    if callback:
                        QtCore.QTimer.singleShot(0, callback)
                    else:
                        if generate_video:
                            QtCore.QTimer.singleShot(0, self._restore_generate_video_button)
                        else:
                            QtCore.QTimer.singleShot(0, self._restore_generate_image_button)
            except Exception as e:
                import traceback
                self.log_signal.emit(tr("plotting_listen_process_failed", "❌ 监听子进程失败：{error}").format(error=e))
                self.log_signal.emit(tr("plotting_detailed_error", "详细错误：{error}").format(error=traceback.format_exc()))
                if callback:
                    QtCore.QTimer.singleShot(0, callback)
                else:
                    if generate_video:
                        QtCore.QTimer.singleShot(0, self._restore_generate_video_button)
                    else:
                        QtCore.QTimer.singleShot(0, self._restore_generate_image_button)

        # 开始轮询
        QtCore.QTimer.singleShot(100, _poll_logs)

    def _restore_generate_image_button(self):
        """恢复生成结果图片按钮状态（在主线程中执行）"""
        if hasattr(self, 'generate_image_button'):
            self.generate_image_button.setEnabled(True)
            self.generate_image_button.setText(tr("step8_generate", "生成波高图"))

    def _restore_generate_video_button(self):
        """恢复生成波高视频按钮状态（在主线程中执行）"""
        if hasattr(self, 'generate_video_button'):
            self.generate_video_button.setEnabled(True)
            self.generate_video_button.setText(tr("step8_generate_video", "生成波高视频"))

    def make_wind_swell_maps(self, time_step_hours=None,
                             FIGSIZE=(16,12), DPI=300, UPSAMPLE_FACTOR=3, CLIM_PCT=99.0,
                             CARTOPY_COAST_RES='10m'):
        """生成风涌浪图（同时生成风浪图和涌浪图）"""
        if time_step_hours is None:
            try:
                time_step_hours = int(self.time_step_edit.text().strip())
            except (ValueError, AttributeError):
                time_step_hours = 6
                self.log(tr("plotting_timestep_read_error_6", "⚠️ 无法读取时间步长，使用默认值 6 小时"))

        # 读取手动风速（用于在结果图上展示），留空则不覆盖
        manual_wind = None
        try:
            if hasattr(self, 'manual_wind_edit'):
                txt = self.manual_wind_edit.text().strip()
                if txt != "":
                    manual_wind = float(txt)
        except Exception:
            manual_wind = None

        if not self.selected_folder:
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return

        # 禁用按钮，防止重复点击
        if hasattr(self, 'generate_wind_swell_button'):
            self.generate_wind_swell_button.setEnabled(False)
            self.generate_wind_swell_button.setText(tr("plotting_generating_wind_swell", "生成中..."))

        # 先生成风浪图（v=2），完成后生成涌浪图（v=3）
        self.log(tr("plotting_start_wind_swell", "🔄 开始生成风涌浪图（风浪图和涌浪图）..."))

        # 使用队列来跟踪两个任务的完成状态
        self._wind_swell_task_count = 0
        self._wind_swell_total_tasks = 2

        # 保存参数供回调使用
        self._wind_swell_params = {
            'time_step_hours': time_step_hours,
            'FIGSIZE': FIGSIZE,
            'DPI': DPI,
            'UPSAMPLE_FACTOR': UPSAMPLE_FACTOR,
            'CLIM_PCT': CLIM_PCT,
            'CARTOPY_COAST_RES': CARTOPY_COAST_RES,
            'manual_wind': manual_wind
        }

        # 生成风浪图
        self._run_make_wave_maps_process(
            time_step_hours, FIGSIZE, DPI, UPSAMPLE_FACTOR, CLIM_PCT, 
            CARTOPY_COAST_RES, v=2, manual_wind=manual_wind, generate_video=False,
            callback=self._on_wind_swell_task_complete
        )

    def _on_wind_swell_task_complete(self):
        """风涌浪图任务完成回调"""
        self._wind_swell_task_count += 1

        if self._wind_swell_task_count == 1:
            # 第一个任务（风浪图）完成，开始生成涌浪图
            params = getattr(self, '_wind_swell_params', {})

            self.log(tr("plotting_wind_completed", "✅ 风浪图生成完成，开始生成涌浪图..."))

            # 生成涌浪图
            self._run_make_wave_maps_process(
                params.get('time_step_hours', 6),
                params.get('FIGSIZE', (16, 12)),
                params.get('DPI', 300),
                params.get('UPSAMPLE_FACTOR', 3),
                params.get('CLIM_PCT', 99.0),
                params.get('CARTOPY_COAST_RES', '10m'),
                v=3,
                manual_wind=params.get('manual_wind'),
                generate_video=False,
                callback=self._on_wind_swell_task_complete
            )
        elif self._wind_swell_task_count >= 2:
            # 两个任务都完成
            self.log(tr("plotting_wind_swell_completed", "✅ 风涌浪图生成完成！"))

            # 恢复按钮状态
            if hasattr(self, 'generate_wind_swell_button'):
                self.generate_wind_swell_button.setEnabled(True)
                self.generate_wind_swell_button.setText(tr("plotting_generate_wind_swell", "生成风涌浪图"))

            # 清理临时参数
            if hasattr(self, '_wind_swell_params'):
                delattr(self, '_wind_swell_params')

    def generate_contour_maps(self):
        """生成等高线图（基于波高图的设置，使用子进程执行）"""
        # 禁用按钮
        if hasattr(self, 'generate_contour_button'):
            self.generate_contour_button.setEnabled(False)
            self.generate_contour_button.setText(tr("step8_generating", "生成中..."))

        # 读取时间步长
        try:
            time_step_hours = int(self.time_step_edit.text().strip())
        except (ValueError, AttributeError):
            time_step_hours = 6
            self.log(tr("plotting_timestep_read_error_6", "⚠️ 无法读取时间步长，使用默认值 6 小时"))

        # 读取手动风速
        manual_wind = None
        try:
            if hasattr(self, 'manual_wind_edit'):
                txt = self.manual_wind_edit.text().strip()
                if txt != "":
                    manual_wind = float(txt)
        except Exception:
            manual_wind = None

        # 使用与波高图相同的参数
        FIGSIZE = (16, 12)
        DPI = 300
        UPSAMPLE_FACTOR = 3
        CLIM_PCT = 99.0
        CARTOPY_COAST_RES = '10m'

        # 在子进程中执行计算操作
        self._run_make_contour_maps_process(time_step_hours, FIGSIZE, DPI, UPSAMPLE_FACTOR, CLIM_PCT, CARTOPY_COAST_RES, manual_wind)

    def _run_make_contour_maps_process(self, time_step_hours, FIGSIZE, DPI, UPSAMPLE_FACTOR, CLIM_PCT, CARTOPY_COAST_RES, manual_wind=None):
        """在子进程中执行生成等高线图操作"""
        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == tr("step2_grid_type_nested", "嵌套网格"))

        # 确定数据源文件夹和输出文件夹
        if is_nested_grid:
            fine_dir = os.path.join(self.selected_folder, "fine")
            if not os.path.isdir(fine_dir):
                self.log_signal.emit(tr("plotting_fine_folder_not_found", "❌ 未找到 fine 文件夹，请先生成嵌套网格"))
                self._restore_generate_contour_button()
                return
            data_folder = fine_dir
            output_folder = self.selected_folder
        else:
            data_folder = self.selected_folder
            output_folder = None  # 使用默认值（data_folder/photo）

        # 获取选择的波高文件（如果存在），否则自动查找 ww3*.nc（排除 spec）
        wave_height_file = None
        if hasattr(self, 'selected_wave_height_file') and self.selected_wave_height_file and os.path.exists(self.selected_wave_height_file):
            # 直接使用选择的文件（与 make_wave_maps 行为一致）
            wave_height_file = self.selected_wave_height_file
        else:
            # 自动查找 ww3*.nc 文件（排除 spec）
            wave_files = glob.glob(os.path.join(data_folder, "ww3*.nc"))
            # 排除 spec 文件
            wave_files = [f for f in wave_files if "spec" not in os.path.basename(f).lower()]
            if wave_files:
                wave_height_file = wave_files[0]

        # 读取配置：是否显示陆地和海岸线
        current_config = load_config()
        show_land_coast = current_config.get("SHOW_LAND_COASTLINE", True)
        if isinstance(show_land_coast, str):
            show_land_coast = show_land_coast.lower() in ('true', '1', 'yes')

        # 创建队列用于子进程和主进程之间的通信
        log_queue = Queue()
        result_queue = Queue()

        # 启动子进程
        process = Process(
            target=_make_contour_maps_worker,
            args=(data_folder, time_step_hours, log_queue, result_queue, FIGSIZE, DPI, UPSAMPLE_FACTOR, CLIM_PCT, CARTOPY_COAST_RES, output_folder, show_land_coast, manual_wind, wave_height_file)
        )
        process.start()

        # 在主线程中监听日志队列并更新UI
        def _poll_logs():
            try:
                done = False
                while True:
                    try:
                        msg = log_queue.get_nowait()
                        if msg == "__DONE__":
                            done = True
                            break
                        self.log_signal.emit(msg)
                    except:
                        break

                if not done and process.is_alive():
                    QtCore.QTimer.singleShot(100, _poll_logs)
                else:
                    if not done:
                        try:
                            while True:
                                try:
                                    msg = log_queue.get_nowait()
                                    if msg == "__DONE__":
                                        done = True
                                        break
                                    self.log_signal.emit(msg)
                                except:
                                    break
                        except:
                            pass
                    process.join(timeout=5)
                    try:
                        result = result_queue.get(timeout=2)
                        if result:
                            self.log_signal.emit(tr("plotting_generate_contour_complete", "✅ 生成等高线图完成，共 {count} 张").format(count=len(result)))
                        else:
                            self.log_signal.emit(tr("plotting_generate_contour_failed", "❌ 生成等高线图失败"))
                    except Exception as e:
                        self.log_signal.emit(tr("plotting_get_result_failed", "❌ 获取结果失败：{error}").format(error=e))
                    finally:
                        QtCore.QTimer.singleShot(0, self._restore_generate_contour_button)
            except Exception as e:
                import traceback
                self.log_signal.emit(tr("plotting_listen_process_failed", "❌ 监听子进程失败：{error}").format(error=e))
                self.log_signal.emit(tr("plotting_detailed_error", "详细错误：{error}").format(error=traceback.format_exc()))
                QtCore.QTimer.singleShot(0, self._restore_generate_contour_button)

        _poll_logs()

    def _restore_generate_contour_button(self):
        """恢复生成等高线图按钮状态"""
        if hasattr(self, 'generate_contour_button'):
            self.generate_contour_button.setEnabled(True)
            self.generate_contour_button.setText(tr("plotting_generate_contour", "生成等高线图"))

    def show_wave_images(self):
        """显示波浪图片结果 - 使用抽屉显示（与风场图和网格可视化一致）"""
        if not self.selected_folder:
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return

        photo_folder = os.path.join(self.selected_folder, "photo")
        if not os.path.exists(photo_folder):
            self.log(tr("plotting_folder_not_exists", "❌ 文件夹 {folder} 不存在").format(folder=photo_folder))
            return

        image_files = sorted([
            os.path.join(photo_folder, f)
            for f in os.listdir(photo_folder)
            if os.path.isfile(os.path.join(photo_folder, f)) and f.lower().endswith((".png", ".jpg", ".jpeg"))
        ])

        if not image_files:
            self.log(tr("step8_no_images", "❌ 没有可显示的图片"))
            return

        # 使用抽屉显示图片（与风场图和网格可视化一致）
        if hasattr(self, '_show_images_in_drawer'):
            self._show_images_in_drawer(image_files)
            self.log(tr("plotting_images_displayed", "✅ 已显示 {count} 张结果图片").format(count=len(image_files)))
        else:
            self.log(tr("drawer_not_initialized", "❌ 抽屉功能未初始化"))

    def open_photo_folder(self):
        """打开图片文件夹"""
        if not self.selected_folder:
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return
        p = os.path.join(self.selected_folder, "photo")
        if not os.path.exists(p):
            self.log(tr("plotting_folder_not_exists", "❌ 文件夹 {folder} 不存在").format(folder=p))
            return
        sys_name = platform.system().lower()
        try:
            if "windows" in sys_name:
                os.startfile(p)
            elif "darwin" in sys_name:
                subprocess.run(["open", p])
            else:
                subprocess.run(["xdg-open", p])
        except Exception as e:
            self.log(tr("plotting_open_folder_failed", "❌ 无法打开文件夹：{error}").format(error=e))

    def _make_wave_maps_impl(self, time_step_hours=None,
                       FIGSIZE=(16,12), DPI=300, UPSAMPLE_FACTOR=3, CLIM_PCT=99.0,
                       CARTOPY_COAST_RES='10m', v=1, manual_wind=None):
        """生成波浪图实现（保留作为备用）"""
        # 读取配置：是否显示陆地和海岸线
        current_config = load_config()
        show_land_coast = current_config.get("SHOW_LAND_COASTLINE", True)
        if isinstance(show_land_coast, str):
            show_land_coast = show_land_coast.lower() in ('true', '1', 'yes')
        if time_step_hours is None:
            try:
                time_step_hours = int(self.time_step_edit.text().strip())
            except (ValueError, AttributeError):
                time_step_hours = 6
                self.log(tr("plotting_timestep_read_error_6", "⚠️ 无法读取时间步长，使用默认值 6 小时"))
        
        # 读取手动风速（用于在结果图上展示），留空则不覆盖
        manual_wind = None
        try:
            if hasattr(self, 'manual_wind_edit'):
                txt = self.manual_wind_edit.text().strip()
                if txt != "":
                    manual_wind = float(txt)
        except Exception:
            manual_wind = None
        
        if not self.selected_folder:
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return []
        
        # 禁用对应按钮，防止重复点击
        if hasattr(self, 'generate_image_button'):
            self.generate_image_button.setEnabled(False)
            self.generate_image_button.setText(tr("step8_generating", "生成中..."))
        
        # 在子进程中执行计算操作
        self._run_make_wave_maps_process(time_step_hours, FIGSIZE, DPI, UPSAMPLE_FACTOR, CLIM_PCT, CARTOPY_COAST_RES, v, manual_wind, False)
