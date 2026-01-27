"""
二维谱绘图模块
包含二维谱相关的 UI 和逻辑
"""
import os
import glob

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QLabel, QHeaderView, QTableWidgetItem
from qfluentwidgets import HeaderCardWidget, PrimaryPushButton, LineEdit, ComboBox, TableWidget

from setting.language_manager import tr
from .workers import _generate_all_spectrum_worker, _generate_selected_spectrum_worker
from .plot_spectrum_service import SpectrumServiceMixin


class SpectrumPlotMixin(SpectrumServiceMixin):
    """二维谱绘图功能模块"""

    def _create_spectrum_ui(self, plot_content_widget, plot_content_layout, button_style, input_style):
        """创建二维谱绘图卡片"""
        spectrum_card = HeaderCardWidget(plot_content_widget)
        spectrum_card.setTitle(tr("plotting_spectrum_2d", "海浪二维方向谱绘图"))
        spectrum_card.setStyleSheet("""
            HeaderCardWidget QLabel {
                font-weight: normal;
                margin-left: 0px;
                padding-left: 0px;
            }
        """)
        spectrum_card.headerLayout.setContentsMargins(11, 10, 11, 12)
        spectrum_card_layout = QVBoxLayout()
        spectrum_card_layout.setSpacing(10)
        spectrum_card_layout.setContentsMargins(0, 0, 0, 0)

        # 站点列表表格（类似谱空间计算的表格样式）- 放在最上面
        if not hasattr(self, 'spectrum_stations_table'):
            self.spectrum_stations_table = TableWidget()
            self.spectrum_stations_table.setContentsMargins(0, 0, 0, 0)
            self.spectrum_stations_table.setColumnCount(3)
            # 隐藏水平表头，将表头作为第一行数据
            self.spectrum_stations_table.horizontalHeader().setVisible(False)
            # 设置列宽
            header = self.spectrum_stations_table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            self.spectrum_stations_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
            self.spectrum_stations_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
            self.spectrum_stations_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            self.spectrum_stations_table.setBorderVisible(False)
            self.spectrum_stations_table.setWordWrap(False)
            self.spectrum_stations_table.verticalHeader().setVisible(False)

            # 添加表头作为第一行数据
            self.spectrum_stations_table.insertRow(0)
            header_lon_item = QTableWidgetItem(tr("plotting_table_lon", "经度"))
            header_lon_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            header_lat_item = QTableWidgetItem(tr("plotting_table_lat", "纬度"))
            header_lat_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            header_name_item = QTableWidgetItem(tr("plotting_table_name", "名称"))
            header_name_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            # 标记为表头行
            header_lon_item.setData(QtCore.Qt.ItemDataRole.UserRole, "header")
            header_lat_item.setData(QtCore.Qt.ItemDataRole.UserRole, "header")
            header_name_item.setData(QtCore.Qt.ItemDataRole.UserRole, "header")
            self.spectrum_stations_table.setItem(0, 0, header_lon_item)
            self.spectrum_stations_table.setItem(0, 1, header_lat_item)
            self.spectrum_stations_table.setItem(0, 2, header_name_item)

            # 设置表格高度策略
            from PyQt6.QtWidgets import QSizePolicy
            size_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.spectrum_stations_table.setSizePolicy(size_policy)
            self.spectrum_stations_table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

            # 重写鼠标按下事件，在点击时检查是否点击已选中的行
            original_mouse_press = self.spectrum_stations_table.mousePressEvent

            def custom_mouse_press_event(event):
                item = self.spectrum_stations_table.itemAt(event.pos())
                if item is not None:
                    row = item.row()
                    if row == 0:
                        self.spectrum_stations_table.clearSelection()
                        event.accept()
                        return

                    selected_items = self.spectrum_stations_table.selectedItems()
                    if selected_items:
                        selected_row = selected_items[0].row()
                        if row == selected_row:
                            self.spectrum_stations_table.clearSelection()
                            event.accept()
                            return

                original_mouse_press(event)

            self.spectrum_stations_table.mousePressEvent = custom_mouse_press_event

        # 根据是否选择了二维谱文件来控制表格的显示
        if hasattr(self, 'selected_spectrum_file') and self.selected_spectrum_file and os.path.exists(self.selected_spectrum_file):
            self.spectrum_stations_table.setVisible(True)
        else:
            self.spectrum_stations_table.setVisible(False)

        spectrum_card_layout.addWidget(self.spectrum_stations_table)

        # 使用网格布局确保输入框左右对齐且占满宽度
        spectrum_params_grid = QGridLayout()
        spectrum_params_grid.setColumnStretch(1, 1)
        spectrum_params_grid.setSpacing(5)

        energy_threshold_label = QLabel(tr("plotting_energy_threshold", "最低能量密度："))
        if not hasattr(self, 'energy_threshold_edit'):
            self.energy_threshold_edit = LineEdit()
            self.energy_threshold_edit.setText("0.01")
        self.energy_threshold_edit.setPlaceholderText(tr("plotting_energy_threshold_example", "例如 0.01"))
        self.energy_threshold_edit.setStyleSheet(input_style)
        spectrum_params_grid.addWidget(energy_threshold_label, 0, 0)
        spectrum_params_grid.addWidget(self.energy_threshold_edit, 0, 1)

        spectrum_step_label = QLabel(tr("plotting_spectrum_timestep", "时间步长 (小时):"))
        if not hasattr(self, 'spectrum_timestep_edit'):
            self.spectrum_timestep_edit = LineEdit()
            self.spectrum_timestep_edit.setText("24")
        else:
            if not self.spectrum_timestep_edit.text().strip():
                self.spectrum_timestep_edit.setText("24")
        self.spectrum_timestep_edit.setPlaceholderText(
            tr("plotting_default_hours", "默认 {value} 小时").format(value="24")
        )
        self.spectrum_timestep_edit.setStyleSheet(input_style)
        spectrum_params_grid.addWidget(spectrum_step_label, 1, 0)
        spectrum_params_grid.addWidget(self.spectrum_timestep_edit, 1, 1)

        spectrum_mode_label = QLabel(tr("plotting_plot_mode", "绘制方式:"))
        if not hasattr(self, 'spectrum_mode_combo'):
            self.spectrum_mode_combo = ComboBox()
            self.spectrum_mode_combo.addItems([
                tr("plotting_plot_mode_normalized", "最大值归一化"),
                tr("plotting_plot_mode_actual", "实际值")
            ])
            self.spectrum_mode_combo.setCurrentText(tr("plotting_plot_mode_actual", "实际值"))
        self.spectrum_mode_combo.setStyleSheet(input_style)
        spectrum_params_grid.addWidget(spectrum_mode_label, 2, 0)
        spectrum_params_grid.addWidget(self.spectrum_mode_combo, 2, 1)

        spectrum_card_layout.addLayout(spectrum_params_grid)

        if not hasattr(self, 'btn_choose_spectrum_file'):
            self.btn_choose_spectrum_file = PrimaryPushButton(tr("plotting_choose_spectrum", "选择二维谱文件"))
            self.btn_choose_spectrum_file.setStyleSheet(button_style)
            self.btn_choose_spectrum_file.clicked.connect(lambda: self.choose_spectrum_file())
        spectrum_card_layout.addWidget(self.btn_choose_spectrum_file)

        if not hasattr(self, 'btn_show_spectrum_stations_on_map'):
            self.btn_show_spectrum_stations_on_map = PrimaryPushButton(tr("plotting_show_on_map", "显示在地图上"))
            self.btn_show_spectrum_stations_on_map.setStyleSheet(button_style)
            self.btn_show_spectrum_stations_on_map.clicked.connect(self.show_spectrum_stations_on_map)
        spectrum_card_layout.addWidget(self.btn_show_spectrum_stations_on_map)

        if hasattr(self, 'selected_folder') and self.selected_folder:
            spec_files = glob.glob(os.path.join(self.selected_folder, "ww3*spec*nc"))
            if spec_files:
                file_name = os.path.basename(spec_files[0])
                if len(file_name) > 30:
                    display_name = file_name[:27] + "..."
                else:
                    display_name = file_name
                self.btn_choose_spectrum_file.setText(display_name)
                if hasattr(self, '_set_plot_button_filled'):
                    self._set_plot_button_filled(self.btn_choose_spectrum_file, True)
                if not hasattr(self, 'selected_spectrum_file') or not self.selected_spectrum_file:
                    self.selected_spectrum_file = spec_files[0]
                self._load_spectrum_stations(spec_files[0])
                if hasattr(self, 'spectrum_stations_table'):
                    self.spectrum_stations_table.setVisible(True)

        if not hasattr(self, 'generate_all_spectrum_button'):
            self.generate_all_spectrum_button = PrimaryPushButton(tr("plotting_generate_all_spectrum", "生成所有二维谱图"))
            self.generate_all_spectrum_button.setStyleSheet(button_style)
            self.generate_all_spectrum_button.clicked.connect(self.generate_all_spectrum)
        spectrum_card_layout.addWidget(self.generate_all_spectrum_button)

        if not hasattr(self, 'generate_selected_spectrum_button'):
            self.generate_selected_spectrum_button = PrimaryPushButton(
                tr("plotting_generate_selected_spectrum", "生成选中站点的二维谱图")
            )
            self.generate_selected_spectrum_button.setStyleSheet(button_style)
            self.generate_selected_spectrum_button.clicked.connect(self.generate_selected_spectrum)
        spectrum_card_layout.addWidget(self.generate_selected_spectrum_button)

        if not hasattr(self, 'view_spectrum_button'):
            self.view_spectrum_button = PrimaryPushButton(tr("plotting_view_images", "查看图片"))
            self.view_spectrum_button.setStyleSheet(button_style)
            self.view_spectrum_button.clicked.connect(lambda: self.view_spectrum_images())
        spectrum_card_layout.addWidget(self.view_spectrum_button)

        spectrum_card.viewLayout.setContentsMargins(11, 10, 11, 12)
        spectrum_card.viewLayout.addLayout(spectrum_card_layout)
        plot_content_layout.addWidget(spectrum_card)

    def generate_all_spectrum(self):
        """生成所有二维谱图（使用子进程执行）"""
        if hasattr(self, 'generate_all_spectrum_button'):
            self.generate_all_spectrum_button.setEnabled(False)
            self.generate_all_spectrum_button.setText(tr("step8_generating", "生成中..."))

        if not self.selected_folder:
            self.log_signal.emit(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            self._restore_generate_all_spectrum_button()
            return

        try:
            energy_threshold = float(self.energy_threshold_edit.text().strip())
            if energy_threshold < 0:
                self.log_signal.emit(tr("plotting_energy_threshold_error", "⚠️ 最低能量密度不能为负数，使用默认值 0.01"))
                energy_threshold = 0.01
        except (ValueError, AttributeError):
            energy_threshold = 0.01
            self.log_signal.emit(tr("plotting_energy_threshold_read_error", "⚠️ 无法读取最低能量密度，使用默认值 0.01"))

        try:
            time_step_hours = float(self.spectrum_timestep_edit.text().strip())
            if time_step_hours <= 0:
                self.log_signal.emit(tr("plotting_timestep_must_positive", "⚠️ 时间步长必须大于0，使用默认值 24"))
                time_step_hours = 24
        except (ValueError, AttributeError):
            time_step_hours = 24
            self.log_signal.emit(tr("plotting_timestep_read_error_24", "⚠️ 无法读取时间步长，使用默认值 24 小时"))

        normalized_text = tr("plotting_plot_mode_normalized", "最大值归一化")
        actual_text = tr("plotting_plot_mode_actual", "实际值")
        plot_mode = tr("plotting_plot_mode_normalized", "最大值归一化")
        if hasattr(self, 'spectrum_mode_combo'):
            current_text = self.spectrum_mode_combo.currentText()
            if current_text == normalized_text:
                plot_mode = tr("plotting_plot_mode_normalized", "最大值归一化")
            elif current_text == actual_text:
                plot_mode = tr("plotting_plot_mode_actual", "实际值")
            else:
                plot_mode = current_text

        spec_file = None
        if hasattr(self, 'selected_spectrum_file') and self.selected_spectrum_file and os.path.exists(self.selected_spectrum_file):
            spec_file = self.selected_spectrum_file
        else:
            spec_files = glob.glob(os.path.join(self.selected_folder, "ww3*spec*nc"))
            if spec_files:
                spec_file = spec_files[0]
            else:
                self.log_signal.emit(tr("plotting_spectrum_file_not_found", "❌ 未找到二维谱文件，请先选择文件"))
                self._restore_generate_all_spectrum_button()
                return

        station_names = []
        if hasattr(self, 'spectrum_stations_table'):
            n_rows = self.spectrum_stations_table.rowCount()
            for row in range(1, n_rows):
                name_item = self.spectrum_stations_table.item(row, 2)
                if name_item:
                    station_names.append(name_item.text().strip())
                else:
                    station_names.append(f"{row-1}")

        self._run_generate_all_spectrum_process(energy_threshold, spec_file, time_step_hours, plot_mode, station_names)

    def _run_generate_all_spectrum_process(self, energy_threshold=0.01, spec_file=None, time_step_hours=24, plot_mode=None, station_names=None):
        """在子进程中执行生成所有二维谱图操作"""
        from multiprocessing import Process, Queue
        if plot_mode is None:
            plot_mode = tr("plotting_plot_mode_normalized", "最大值归一化")

        log_queue = Queue()
        result_queue = Queue()

        process = Process(
            target=_generate_all_spectrum_worker,
            args=(self.selected_folder, log_queue, result_queue, energy_threshold, spec_file, time_step_hours, plot_mode, station_names)
        )
        process.start()

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

                if done:
                    process.join(timeout=1)
                    try:
                        result = result_queue.get_nowait()
                        if result:
                            self.log_signal.emit(tr("plotting_all_spectrum_saved", "✅ 所有二维谱图已保存到：{path}").format(path=result))
                        else:
                            self.log_signal.emit(tr("plotting_generate_all_spectrum_failed", "❌ 生成所有二维谱图失败"))
                    except Exception as e:
                        self.log_signal.emit(tr("plotting_get_result_failed", "❌ 获取结果失败：{error}").format(error=e))
                    finally:
                        QtCore.QTimer.singleShot(0, self._restore_generate_all_spectrum_button)
                else:
                    QtCore.QTimer.singleShot(100, _poll_logs)
            except Exception as e:
                import traceback
                self.log_signal.emit(tr("plotting_listen_process_failed", "❌ 监听子进程失败：{error}").format(error=e))
                self.log_signal.emit(traceback.format_exc())
                QtCore.QTimer.singleShot(0, self._restore_generate_all_spectrum_button)

        _poll_logs()

    def _restore_generate_all_spectrum_button(self):
        """恢复生成所有二维谱图按钮状态"""
        if hasattr(self, 'generate_all_spectrum_button'):
            self.generate_all_spectrum_button.setEnabled(True)
            self.generate_all_spectrum_button.setText(tr("plotting_generate_all_spectrum", "生成所有二维谱图"))

    def generate_selected_spectrum(self):
        """生成选中站点的二维谱图（使用子进程执行）"""
        if hasattr(self, 'generate_selected_spectrum_button'):
            self.generate_selected_spectrum_button.setEnabled(False)
            self.generate_selected_spectrum_button.setText(tr("step8_generating", "生成中..."))

        if not self.selected_folder:
            self.log_signal.emit(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            self._restore_generate_selected_spectrum_button()
            return

        selected_items = self.spectrum_stations_table.selectedItems()
        if not selected_items:
            self.log_signal.emit(tr("plotting_select_station_first", "❌ 请先选择一个站点"))
            self._restore_generate_selected_spectrum_button()
            return

        selected_row = selected_items[0].row()
        if selected_row == 0:
            self.log_signal.emit(tr("plotting_cannot_select_header", "❌ 不能选择表头行，请选择数据行"))
            self._restore_generate_selected_spectrum_button()
            return

        try:
            energy_threshold = float(self.energy_threshold_edit.text().strip())
            if energy_threshold < 0:
                self.log_signal.emit(tr("plotting_energy_threshold_error", "⚠️ 最低能量密度不能为负数，使用默认值 0.01"))
                energy_threshold = 0.01
        except (ValueError, AttributeError):
            energy_threshold = 0.01
            self.log_signal.emit(tr("plotting_energy_threshold_read_error", "⚠️ 无法读取最低能量密度，使用默认值 0.01"))

        try:
            time_step_hours = float(self.spectrum_timestep_edit.text().strip())
            if time_step_hours <= 0:
                self.log_signal.emit(tr("plotting_timestep_must_positive", "⚠️ 时间步长必须大于0，使用默认值 24"))
                time_step_hours = 24
        except (ValueError, AttributeError):
            time_step_hours = 24
            self.log_signal.emit(tr("plotting_timestep_read_error_24", "⚠️ 无法读取时间步长，使用默认值 24 小时"))

        normalized_text = tr("plotting_plot_mode_normalized", "最大值归一化")
        actual_text = tr("plotting_plot_mode_actual", "实际值")
        plot_mode = tr("plotting_plot_mode_normalized", "最大值归一化")
        if hasattr(self, 'spectrum_mode_combo'):
            current_text = self.spectrum_mode_combo.currentText()
            if current_text == normalized_text:
                plot_mode = tr("plotting_plot_mode_normalized", "最大值归一化")
            elif current_text == actual_text:
                plot_mode = tr("plotting_plot_mode_actual", "实际值")
            else:
                plot_mode = current_text

        spec_file = None
        if hasattr(self, 'selected_spectrum_file') and self.selected_spectrum_file and os.path.exists(self.selected_spectrum_file):
            spec_file = self.selected_spectrum_file
        else:
            spec_files = glob.glob(os.path.join(self.selected_folder, "ww3*spec*nc"))
            if spec_files:
                spec_file = spec_files[0]
            else:
                self.log_signal.emit(tr("plotting_spectrum_file_not_found", "❌ 未找到二维谱文件，请先选择文件"))
                self._restore_generate_selected_spectrum_button()
                return

        station_name = None
        if hasattr(self, 'spectrum_stations_table'):
            name_item = self.spectrum_stations_table.item(selected_row, 2)
            if name_item:
                station_name = name_item.text().strip()
        if not station_name:
            station_name = f"{selected_row-1}"

        station_index = selected_row - 1
        self._run_generate_selected_spectrum_process(
            energy_threshold, spec_file, time_step_hours, station_index, plot_mode, station_name
        )

    def _run_generate_selected_spectrum_process(self, energy_threshold=0.01, spec_file=None, time_step_hours=24, station_index=0, plot_mode=None, station_name=None):
        """在子进程中执行生成选中站点二维谱图操作"""
        from multiprocessing import Process, Queue
        if plot_mode is None:
            plot_mode = tr("plotting_plot_mode_normalized", "最大值归一化")

        log_queue = Queue()
        result_queue = Queue()

        process = Process(
            target=_generate_selected_spectrum_worker,
            args=(self.selected_folder, log_queue, result_queue, energy_threshold, spec_file, time_step_hours, station_index, plot_mode, station_name)
        )
        process.start()

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

                if done:
                    process.join(timeout=1)
                    try:
                        result = result_queue.get_nowait()
                        if result:
                            self.log_signal.emit(tr("plotting_selected_spectrum_saved", "✅ 选中站点的二维谱图已保存到：{path}").format(path=result))
                        else:
                            self.log_signal.emit(tr("plotting_generate_selected_spectrum_failed", "❌ 生成选中站点的二维谱图失败"))
                    except Exception as e:
                        self.log_signal.emit(tr("plotting_get_result_failed", "❌ 获取结果失败：{error}").format(error=e))
                    finally:
                        QtCore.QTimer.singleShot(0, self._restore_generate_selected_spectrum_button)
                else:
                    QtCore.QTimer.singleShot(100, _poll_logs)
            except Exception as e:
                import traceback
                self.log_signal.emit(tr("plotting_listen_process_failed", "❌ 监听子进程失败：{error}").format(error=e))
                self.log_signal.emit(traceback.format_exc())
                QtCore.QTimer.singleShot(0, self._restore_generate_selected_spectrum_button)

        _poll_logs()

    def _restore_generate_selected_spectrum_button(self):
        """恢复生成选中站点二维谱图按钮状态"""
        if hasattr(self, 'generate_selected_spectrum_button'):
            self.generate_selected_spectrum_button.setEnabled(True)
            self.generate_selected_spectrum_button.setText(tr("plotting_generate_selected_spectrum", "生成选中站点的二维谱图"))
