"""
第四步：配置WW3运行参数模块
包含UI创建和按钮逻辑（强迫场选择、Slurm配置、WAVEWATCH配置、输出方案等）
"""
import os
import json
import re
import glob
import shutil
from netCDF4 import Dataset, num2date
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QGridLayout, QHBoxLayout, QWidget, QSizePolicy
from qfluentwidgets import PrimaryPushButton, LineEdit, ComboBox, CheckBox
from setting.language_manager import tr
from setting.config import load_config, ST_OPTIONS, CPU_GROUP, DEFAULT_CPU, KERNEL_NUM, NODE_NUM, COMPUTE_PRECISION, OUTPUT_PRECISION
from .utils import create_header_card


class HomeStepFourCard:
    """第四步：配置WW3运行参数 Mixin"""

    def create_step_4_card(self, content_widget, content_layout):
        """创建第四步：配置WW3运行参数的UI"""
        # 使用通用函数创建卡片
        step4_card, step4_card_layout = create_header_card(
            content_widget,
            tr("step4_title", "第四步：配置WW3运行参数")
        )

        # 输入框样式：使用主题适配的样式
        input_style = self._get_input_style()

        # 下拉选择框样式：使用主题适配的样式
        combo_style = self._get_combo_style()

        # 使用 QGridLayout 统一对齐，确保所有输入框和选择框宽度一致
        step4_grid = QGridLayout()
        step4_grid.setSpacing(10)
        step4_grid.setColumnStretch(0, 0)  # 标签列不拉伸
        step4_grid.setColumnStretch(1, 1)  # 输入框列拉伸

        row = 0

        # 强迫场选择区域（如果选择了除了风场以外的强迫场才显示）
        # 强迫场标签（样式和Slurm 配置一样）
        forcing_field_title_container = QWidget()
        forcing_field_title_layout = QHBoxLayout()
        forcing_field_title_layout.setContentsMargins(0, 0, 0, 0)
        forcing_field_title_layout.setSpacing(10)
        
        # 左侧横线
        forcing_field_line_left = QtWidgets.QFrame()
        forcing_field_line_left.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        forcing_field_line_left.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        forcing_field_line_left.setFixedHeight(1)
        forcing_field_line_left.setMinimumHeight(1)
        forcing_field_line_left.setMaximumHeight(1)
        forcing_field_line_left.setStyleSheet("background-color: #888888; border: none;")
        forcing_field_title_layout.addWidget(forcing_field_line_left)
        
        # 标题标签（居中）
        forcing_field_title = QLabel(tr("step4_forcing_fields", "强迫场"))
        forcing_field_title.setStyleSheet("font-weight: normal; font-size: 14px;")
        forcing_field_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        forcing_field_title_layout.addWidget(forcing_field_title)
        
        # 右侧横线
        forcing_field_line_right = QtWidgets.QFrame()
        forcing_field_line_right.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        forcing_field_line_right.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        forcing_field_line_right.setFixedHeight(1)
        forcing_field_line_right.setMinimumHeight(1)
        forcing_field_line_right.setMaximumHeight(1)
        forcing_field_line_right.setStyleSheet("background-color: #888888; border: none;")
        forcing_field_title_layout.addWidget(forcing_field_line_right)
        
        # 设置横线可伸缩
        forcing_field_title_layout.setStretch(0, 1)  # 左侧横线
        forcing_field_title_layout.setStretch(2, 1)  # 右侧横线
        
        forcing_field_title_container.setLayout(forcing_field_title_layout)
        
        # 强迫场复选框容器
        forcing_field_checkbox_layout = QVBoxLayout()
        forcing_field_checkbox_layout.setContentsMargins(0, 0, 0, 0)
        forcing_field_checkbox_layout.setSpacing(5)
        
        # 存储复选框的字典
        self.forcing_field_checkboxes = {}
        
        # 强迫场选项（包括风场，风场不可取消）
        forcing_field_options = [
            ("wind", tr("step4_forcing_field_wind", "风场")),
            ("current", tr("step4_forcing_field_current", "流场")),
            ("level", tr("step4_forcing_field_level", "水位场")),
            ("ice", tr("step4_forcing_field_ice", "海冰场")),
        ]
        
        for field_key, field_name in forcing_field_options:
            # 创建水平布局容器，让文字在左，选择框在右
            checkbox_row_layout = QHBoxLayout()
            checkbox_row_layout.setContentsMargins(0, 0, 0, 0)
            checkbox_row_layout.setSpacing(10)
            
            # 创建文字标签（放在左边）
            checkbox_label = QLabel(field_name)
            
            # 创建 CheckBox（只显示选择框，不显示文字）
            checkbox = CheckBox("")
            checkbox.setChecked(False)  # 初始未选中，根据实际选择的文件更新
            
            # 风场checkbox保持启用状态，但通过事件拦截来防止取消选中
            if field_key == 'wind':
                # 存储风场checkbox的引用，以便在其他地方使用
                wind_checkbox = checkbox
                
                # 创建一个方法来检查是否有风场文件
                def has_wind_file():
                    try:
                        if hasattr(self, 'selected_origin_file') and self.selected_origin_file:
                            import os
                            if os.path.exists(str(self.selected_origin_file)):
                                return True
                    except:
                        pass
                    return False
                
                # 拦截所有鼠标事件，完全阻止在有风场文件时的点击操作
                def mousePressEvent_handler(event):
                    # 如果有风场文件且当前已选中，完全阻止鼠标点击事件（防止取消选中）
                    if has_wind_file() and checkbox.isChecked():
                        event.ignore()
                        return
                    # 如果没有风场文件，或未选中（不应该发生），允许正常操作
                    CheckBox.mousePressEvent(checkbox, event)
                
                def mouseReleaseEvent_handler(event):
                    # 如果有风场文件且当前已选中，完全阻止鼠标释放事件（防止取消选中）
                    if has_wind_file() and checkbox.isChecked():
                        event.ignore()
                        return
                    # 如果没有风场文件，或未选中（不应该发生），允许正常操作
                    CheckBox.mouseReleaseEvent(checkbox, event)
                
                def mouseMoveEvent_handler(event):
                    # 如果有风场文件且当前已选中，完全阻止鼠标移动事件（防止可能的拖拽取消选中）
                    if has_wind_file() and checkbox.isChecked():
                        event.ignore()
                        return
                    # 如果没有风场文件，或未选中（不应该发生），允许正常操作
                    CheckBox.mouseMoveEvent(checkbox, event)
                
                # 替换鼠标事件处理
                checkbox.mousePressEvent = mousePressEvent_handler
                checkbox.mouseReleaseEvent = mouseReleaseEvent_handler
                checkbox.mouseMoveEvent = mouseMoveEvent_handler
                
                # 拦截stateChanged信号作为最关键的保险
                def prevent_uncheck(state):
                    # 如果有风场文件，绝对不允许取消选中
                    if has_wind_file():
                        if state == 0:  # 0表示未选中状态
                            checkbox.blockSignals(True)
                            checkbox.setChecked(True)
                            checkbox.blockSignals(False)
                checkbox.stateChanged.connect(prevent_uncheck)
                
                # 定期检查并确保风场checkbox在有文件时始终选中
                def ensure_wind_checked():
                    if has_wind_file() and not checkbox.isChecked():
                        checkbox.blockSignals(True)
                        checkbox.setChecked(True)
                        checkbox.blockSignals(False)
                
                # 将检查函数存储到checkbox中，以便在更新函数中调用
                checkbox._ensure_wind_checked = ensure_wind_checked
            
            # 不设置任何样式表，完全保留选择框的默认样式
            # 通过固定宽度来限制 CheckBox 只显示选择框部分
            # 先让 CheckBox 计算默认大小，然后设置固定宽度
            checkbox.adjustSize()
            # 设置固定宽度，只保留选择框的宽度（大约 18-20px）
            checkbox.setFixedWidth(0)
            checkbox.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            
            # 将标签和选择框添加到布局，标签靠左，选择框靠右
            checkbox_row_layout.addWidget(checkbox_label)
            checkbox_row_layout.addStretch()  # 添加弹性空间，让选择框靠右
            checkbox_row_layout.addWidget(checkbox, 0)  # 选择框不拉伸
            
            # 创建容器 widget
            checkbox_row_widget = QWidget()
            checkbox_row_widget.setLayout(checkbox_row_layout)
            checkbox_row_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            checkbox_row_widget.setVisible(False)  # 初始隐藏，只有选择相应场时才显示
            
            # 存储复选框和容器
            self.forcing_field_checkboxes[field_key] = {
                'checkbox': checkbox,
                'widget': checkbox_row_widget
            }
            
            forcing_field_checkbox_layout.addWidget(checkbox_row_widget)
        
        # 初始隐藏整个强迫场区域，只有在选择了任何强迫场时才显示
        self.forcing_field_widget = QWidget()
        forcing_field_widget_layout = QVBoxLayout()
        forcing_field_widget_layout.setContentsMargins(0, 0, 0, 0)
        forcing_field_widget_layout.setSpacing(5)
        forcing_field_widget_layout.addWidget(forcing_field_title_container)
        forcing_field_widget_layout.addLayout(forcing_field_checkbox_layout)
        self.forcing_field_widget.setLayout(forcing_field_widget_layout)
        self.forcing_field_widget.setVisible(False)  # 初始隐藏
        
        step4_card_layout.addWidget(self.forcing_field_widget)
        
        # 更新强迫场显示的函数
        def _update_forcing_fields_display():
            try:
                # 确保属性存在
                if not hasattr(self, 'selected_origin_file'):
                    self.selected_origin_file = None
                if not hasattr(self, 'selected_current_file'):
                    self.selected_current_file = None
                if not hasattr(self, 'selected_level_file'):
                    self.selected_level_file = None
                if not hasattr(self, 'selected_ice_file'):
                    self.selected_ice_file = None
                
                # 检查是否选择了强迫场（包括风场）
                has_wind = self.selected_origin_file is not None and str(self.selected_origin_file).strip() != ""
                has_current = self.selected_current_file is not None and str(self.selected_current_file).strip() != ""
                has_ssh = self.selected_level_file is not None and str(self.selected_level_file).strip() != ""
                has_ice = self.selected_ice_file is not None and str(self.selected_ice_file).strip() != ""
                
                # 检查文件是否存在
                if has_wind:
                    if not os.path.exists(self.selected_origin_file):
                        has_wind = False
                if has_current:
                    if not os.path.exists(self.selected_current_file):
                        has_current = False
                if has_ssh:
                    if not os.path.exists(self.selected_level_file):
                        has_ssh = False
                if has_ice:
                    if not os.path.exists(self.selected_ice_file):
                        has_ice = False
                
                # 如果只有风场，隐藏整个强迫场区域
                # 如果有风场和其他强迫场，或者没有风场但有其他强迫场，则显示整个区域
                has_other_fields = has_current or has_ssh or has_ice
                
                if has_wind and not has_other_fields:
                    # 只有风场，隐藏整个强迫场区域
                    if hasattr(self, 'forcing_field_widget'):
                        self.forcing_field_widget.setVisible(False)
                elif has_wind or has_current or has_ssh or has_ice:
                    # 有风场和其他强迫场，或者没有风场但有其他强迫场，显示整个区域
                    if hasattr(self, 'forcing_field_widget'):
                        self.forcing_field_widget.setVisible(True)
                    
                    # 更新各个复选框的显示状态
                    if hasattr(self, 'forcing_field_checkboxes'):
                        # 风场：选中但不能取消
                        if 'wind' in self.forcing_field_checkboxes:
                            wind_checkbox = self.forcing_field_checkboxes['wind']['checkbox']
                            self.forcing_field_checkboxes['wind']['widget'].setVisible(has_wind)
                            # 如果有风场文件，强制选中并确保不能被取消
                            if has_wind:
                                wind_checkbox.blockSignals(True)
                                wind_checkbox.setChecked(True)
                                wind_checkbox.blockSignals(False)
                                wind_checkbox.setEnabled(True)  # 保持启用状态（不显示为灰色）
                                # 调用确保选中的函数（防止意外取消选中）
                                if hasattr(wind_checkbox, '_ensure_wind_checked'):
                                    wind_checkbox._ensure_wind_checked()
                            else:
                                # 如果没有风场文件，允许正常操作
                                wind_checkbox.setChecked(False)
                        
                        if 'current' in self.forcing_field_checkboxes:
                            self.forcing_field_checkboxes['current']['widget'].setVisible(has_current)
                            self.forcing_field_checkboxes['current']['checkbox'].setChecked(has_current)
                        
                        if 'level' in self.forcing_field_checkboxes:
                            self.forcing_field_checkboxes['level']['widget'].setVisible(has_ssh)
                            self.forcing_field_checkboxes['level']['checkbox'].setChecked(has_ssh)
                        
                        if 'ice' in self.forcing_field_checkboxes:
                            self.forcing_field_checkboxes['ice']['widget'].setVisible(has_ice)
                            self.forcing_field_checkboxes['ice']['checkbox'].setChecked(has_ice)
                else:
                    # 如果没有选择任何强迫场，隐藏整个区域
                    if hasattr(self, 'forcing_field_widget'):
                        self.forcing_field_widget.setVisible(False)
            except Exception as e:
                # 调试用：打印异常信息
                import traceback
                traceback.print_exc()
                pass
        
        # 在添加到布局后执行更新，确保属性已初始化
        QtCore.QTimer.singleShot(200, _update_forcing_fields_display)
        
        # 保存更新函数以便后续调用
        self._update_forcing_fields_display = _update_forcing_fields_display

        # Slurm 配置标签（样式和外网格参数一样）
        slurm_title_container = QWidget()
        slurm_title_layout = QHBoxLayout()
        slurm_title_layout.setContentsMargins(0, 0, 0, 0)
        slurm_title_layout.setSpacing(10)
        
        # 左侧横线
        slurm_line_left = QtWidgets.QFrame()
        slurm_line_left.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        slurm_line_left.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        slurm_line_left.setFixedHeight(1)
        slurm_line_left.setMinimumHeight(1)
        slurm_line_left.setMaximumHeight(1)
        slurm_line_left.setStyleSheet("background-color: #888888; border: none;")
        slurm_title_layout.addWidget(slurm_line_left)
        
        # 标题标签（居中）
        slurm_title = QLabel(tr("step4_slurm_config", "Slurm 配置"))
        slurm_title.setStyleSheet("font-weight: normal; font-size: 14px;")
        slurm_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        slurm_title_layout.addWidget(slurm_title)
        
        # 右侧横线
        slurm_line_right = QtWidgets.QFrame()
        slurm_line_right.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        slurm_line_right.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        slurm_line_right.setFixedHeight(1)
        slurm_line_right.setMinimumHeight(1)
        slurm_line_right.setMaximumHeight(1)
        slurm_line_right.setStyleSheet("background-color: #888888; border: none;")
        slurm_title_layout.addWidget(slurm_line_right)
        
        # 设置横线可伸缩
        slurm_title_layout.setStretch(0, 1)  # 左侧横线
        slurm_title_layout.setStretch(2, 1)  # 右侧横线
        
        self.slurm_title_container = slurm_title_container  # 保存引用以便控制可见性
        slurm_title_container.setLayout(slurm_title_layout)
        step4_grid.addWidget(slurm_title_container, row, 0, 1, 2)  # 跨两列
        row += 1

        # ST 版本选择（下拉框）
        st_label = QLabel(tr("step4_st_version", "ST 版本："))
        self.st_label = st_label  # 保存引用以便控制可见性
        step4_grid.addWidget(st_label, row, 0)
        self.st_combo = ComboBox()
        # 从配置文件中读取 ST 版本名称列表
        st_versions = load_config().get("ST_VERSIONS", [])
        if st_versions and isinstance(st_versions, list) and len(st_versions) > 0:
            # 从 ST_VERSIONS 中提取名称列表
            st_names = [v.get("name", "") for v in st_versions if isinstance(v, dict) and "name" in v]
            st_names = [name for name in st_names if name]  # 过滤空名称
            if st_names:
                self.st_combo.addItems(st_names)
                self.st_combo.setCurrentText(st_names[0])
                self.st_var = st_names[0]
            else:
                # 如果没有有效的 ST 版本，使用默认选项
                self.st_combo.addItems(ST_OPTIONS)
                self.st_combo.setCurrentText("ST2")
                self.st_var = "ST2"
        else:
            # 如果配置文件中没有 ST_VERSIONS，使用默认选项
            self.st_combo.addItems(ST_OPTIONS)
            self.st_combo.setCurrentText("ST2")
            self.st_var = "ST2"
        self.st_combo.currentTextChanged.connect(self._set_st)
        self.st_combo.setStyleSheet(combo_style)
        # 设置文本左对齐（延迟设置，确保样式已应用）
        def _set_st_combo_alignment():
            try:
                if hasattr(self.st_combo, 'lineEdit'):
                    line_edit = self.st_combo.lineEdit()
                    if line_edit:
                        line_edit.setAlignment(Qt.AlignmentFlag.AlignLeft)
            except:
                pass
        QtCore.QTimer.singleShot(10, _set_st_combo_alignment)
        step4_grid.addWidget(self.st_combo, row, 1)
        row += 1

        # CPU 选择（下拉框）
        cpu_label = QLabel(tr("step4_server_cpu", "服务器 CPU："))
        self.cpu_label = cpu_label  # 保存引用以便控制可见性
        step4_grid.addWidget(cpu_label, row, 0)
        self.cpu_combo = ComboBox()
        self.cpu_combo.addItems(CPU_GROUP)
        self.cpu_combo.setCurrentText(DEFAULT_CPU)
        self.cpu_var = DEFAULT_CPU
        self.cpu_combo.currentTextChanged.connect(self._set_cpu)
        self.cpu_combo.setStyleSheet(combo_style)
        # 设置文本左对齐（延迟设置，确保样式已应用）
        def _set_cpu_combo_alignment():
            try:
                if hasattr(self.cpu_combo, 'lineEdit'):
                    line_edit = self.cpu_combo.lineEdit()
                    if line_edit:
                        line_edit.setAlignment(Qt.AlignmentFlag.AlignLeft)
            except:
                pass
        QtCore.QTimer.singleShot(10, _set_cpu_combo_alignment)
        step4_grid.addWidget(self.cpu_combo, row, 1)
        row += 1

        # 总核数
        num_n_label = QLabel(tr("step4_total_cores", "总核数:"))
        self.num_n_label = num_n_label  # 保存引用以便控制可见性
        step4_grid.addWidget(num_n_label, row, 0)
        self.num_n_edit = LineEdit()
        self.num_n_edit.setText(KERNEL_NUM)
        self.num_n_edit.setStyleSheet(input_style)
        step4_grid.addWidget(self.num_n_edit, row, 1)
        row += 1

        # 节点数
        num_N_label = QLabel(tr("step4_node_num", "节点数:"))
        self.num_N_label = num_N_label  # 保存引用以便控制可见性
        step4_grid.addWidget(num_N_label, row, 0)
        self.num_N_edit = LineEdit()
        self.num_N_edit.setText(NODE_NUM)
        self.num_N_edit.setStyleSheet(input_style)
        step4_grid.addWidget(self.num_N_edit, row, 1)
        row += 1

        # WAVEWATCH 配置标签（样式和外网格参数一样）
        wavewatch_title_container = QWidget()
        wavewatch_title_layout = QHBoxLayout()
        wavewatch_title_layout.setContentsMargins(0, 0, 0, 0)
        wavewatch_title_layout.setSpacing(10)
        
        # 左侧横线
        wavewatch_line_left = QtWidgets.QFrame()
        wavewatch_line_left.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        wavewatch_line_left.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        wavewatch_line_left.setFixedHeight(1)
        wavewatch_line_left.setMinimumHeight(1)
        wavewatch_line_left.setMaximumHeight(1)
        wavewatch_line_left.setStyleSheet("background-color: #888888; border: none;")
        wavewatch_title_layout.addWidget(wavewatch_line_left)
        
        # 标题标签（居中）
        wavewatch_title = QLabel(tr("step4_wavewatch_config", "WAVEWATCH 配置"))
        wavewatch_title.setStyleSheet("font-weight: normal; font-size: 14px;")
        wavewatch_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wavewatch_title_layout.addWidget(wavewatch_title)
        
        # 右侧横线
        wavewatch_line_right = QtWidgets.QFrame()
        wavewatch_line_right.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        wavewatch_line_right.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        wavewatch_line_right.setFixedHeight(1)
        wavewatch_line_right.setMinimumHeight(1)
        wavewatch_line_right.setMaximumHeight(1)
        wavewatch_line_right.setStyleSheet("background-color: #888888; border: none;")
        wavewatch_title_layout.addWidget(wavewatch_line_right)
        
        # 设置横线可伸缩
        wavewatch_title_layout.setStretch(0, 1)  # 左侧横线
        wavewatch_title_layout.setStretch(2, 1)  # 右侧横线
        
        self.wavewatch_title_container = wavewatch_title_container  # 保存引用以便控制可见性
        self.wavewatch_title = wavewatch_title  # 保存标签引用以便修改内容
        wavewatch_title_container.setLayout(wavewatch_title_layout)
        # 初始更新标签文本（默认普通网格）
        self._update_wavewatch_title()
        step4_grid.addWidget(wavewatch_title_container, row, 0, 1, 2)  # 跨两列
        row += 1



        # 对齐 step4_grid 的列（确保标签列宽度一致）
        def _align_step4_grid_columns():
            try:
                max_width = 0
                # 查找 step4_grid 中所有标签的最大宽度（跳过标签容器）
                for i in range(step4_grid.rowCount()):
                    item = step4_grid.itemAtPosition(i, 0)
                    if item and item.widget():
                        widget = item.widget()
                        # 只处理标签（QLabel），跳过标签容器（QWidget）
                        if isinstance(widget, QLabel):
                            widget.update()  # 确保已渲染
                            width = widget.sizeHint().width()
                            if width > max_width:
                                max_width = width
                
                # 如果找到了最大宽度，设置 step4_grid 第一列的最小宽度
                if max_width > 0:
                    step4_grid.setColumnMinimumWidth(0, max_width)
            except Exception as e:
                pass
        
        QtCore.QTimer.singleShot(100, _align_step4_grid_columns)
        
        # 先将 step4_grid 添加到布局（包含服务器 CPU、总核数、节点数、ST 版本）
        step4_card_layout.addLayout(step4_grid)

        # 外网格精度参数容器（普通网格时显示，嵌套网格时也显示）
        self.outer_precision_widget = QWidget()
        outer_precision_layout = QVBoxLayout()
        outer_precision_layout.setSpacing(10)
        outer_precision_layout.setContentsMargins(0, 0, 0, 0)

        # 外网格精度参数小标题（嵌套网格时显示，普通网格时隐藏）
        

        # 外网格精度参数网格
        outer_precision_grid = QGridLayout()
        outer_precision_grid.setSpacing(10)
        outer_precision_grid.setColumnStretch(0, 0)
        outer_precision_grid.setColumnStretch(1, 1)

        outer_precision_row = 0

        # 外网格计算精度
        outer_precision_grid.addWidget(QLabel(tr("step4_compute_precision", "计算精度 (秒):")), outer_precision_row, 0)
        self.shel_step_edit = LineEdit()
        self.shel_step_edit.setText(COMPUTE_PRECISION)
        self.shel_step_edit.setStyleSheet(input_style)
        outer_precision_grid.addWidget(self.shel_step_edit, outer_precision_row, 1)
        outer_precision_row += 1

        # 外网格输出精度
        outer_precision_grid.addWidget(QLabel(tr("step4_output_precision", "输出精度 (秒):")), outer_precision_row, 0)
        self.output_precision_edit = LineEdit()
        self.output_precision_edit.setText(OUTPUT_PRECISION)
        self.output_precision_edit.setStyleSheet(input_style)
        outer_precision_grid.addWidget(self.output_precision_edit, outer_precision_row, 1)

        outer_precision_layout.addLayout(outer_precision_grid)
        self.outer_precision_widget.setLayout(outer_precision_layout)
        
        # 延迟设置列最小宽度，确保与 step4_grid 对齐
        def _align_outer_precision_grid_columns():
            try:
                # 获取 step4_grid 中第一列的最大宽度（标签列）
                if step4_grid.count() > 0:
                    max_width = 0
                    # 遍历 step4_grid 中的所有标签，找到最大宽度（跳过标签容器）
                    for row in range(step4_grid.rowCount()):
                        item = step4_grid.itemAtPosition(row, 0)
                        if item and item.widget():
                            widget = item.widget()
                            # 只处理标签（QLabel），跳过标签容器（QWidget）
                            if isinstance(widget, QLabel):
                                widget.update()  # 确保已渲染
                                hint_width = widget.sizeHint().width()
                                if hint_width > max_width:
                                    max_width = hint_width
                    # 如果找到了最大宽度，设置 outer_precision_grid 第一列的最小宽度
                    # 这样标签列对齐后，输入框列也会自动对齐
                    if max_width > 0:
                        outer_precision_grid.setColumnMinimumWidth(0, max_width)
            except Exception:
                pass
        
        QtCore.QTimer.singleShot(100, _align_outer_precision_grid_columns)
        step4_card_layout.addWidget(self.outer_precision_widget)

        # 内网格精度参数容器（嵌套网格时显示，普通网格时隐藏）
        self.inner_precision_widget = QWidget()
        inner_precision_layout = QVBoxLayout()
        inner_precision_layout.setSpacing(10)
        inner_precision_layout.setContentsMargins(0, 0, 0, 0)

        # 内网格精度参数小标题
        inner_precision_title_container = QWidget()
        inner_precision_title_layout = QHBoxLayout()
        inner_precision_title_layout.setContentsMargins(0, 0, 0, 0)
        inner_precision_title_layout.setSpacing(10)
        
        # 左侧横线
        inner_precision_line_left = QtWidgets.QFrame()
        inner_precision_line_left.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        inner_precision_line_left.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        inner_precision_line_left.setFixedHeight(1)
        inner_precision_line_left.setMinimumHeight(1)
        inner_precision_line_left.setMaximumHeight(1)
        inner_precision_line_left.setStyleSheet("background-color: #888888; border: none;")
        inner_precision_title_layout.addWidget(inner_precision_line_left)
        
        # 标题标签（居中）
        inner_precision_title = QLabel(tr("step4_inner_params", "内网格参数"))
        inner_precision_title.setStyleSheet("font-weight: normal; font-size: 14px;")
        inner_precision_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner_precision_title_layout.addWidget(inner_precision_title)
        
        # 右侧横线
        inner_precision_line_right = QtWidgets.QFrame()
        inner_precision_line_right.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        inner_precision_line_right.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        inner_precision_line_right.setFixedHeight(1)
        inner_precision_line_right.setMinimumHeight(1)
        inner_precision_line_right.setMaximumHeight(1)
        inner_precision_line_right.setStyleSheet("background-color: #888888; border: none;")
        inner_precision_title_layout.addWidget(inner_precision_line_right)
        
        # 设置横线可伸缩
        inner_precision_title_layout.setStretch(0, 1)  # 左侧横线
        inner_precision_title_layout.setStretch(2, 1)  # 右侧横线
        
        inner_precision_title_container.setLayout(inner_precision_title_layout)
        inner_precision_layout.addWidget(inner_precision_title_container)

        # 内网格精度参数网格
        inner_precision_grid = QGridLayout()
        inner_precision_grid.setSpacing(10)
        inner_precision_grid.setColumnStretch(0, 0)
        inner_precision_grid.setColumnStretch(1, 1)

        inner_precision_row = 0

        # 内网格计算精度
        inner_precision_grid.addWidget(QLabel(tr("step4_compute_precision", "计算精度 (秒):")), inner_precision_row, 0)
        self.inner_shel_step_edit = LineEdit()
        self.inner_shel_step_edit.setText(COMPUTE_PRECISION)
        self.inner_shel_step_edit.setStyleSheet(input_style)
        inner_precision_grid.addWidget(self.inner_shel_step_edit, inner_precision_row, 1)
        inner_precision_row += 1

        # 内网格输出精度
        inner_precision_grid.addWidget(QLabel(tr("step4_output_precision", "输出精度 (秒):")), inner_precision_row, 0)
        self.inner_output_precision_edit = LineEdit()
        self.inner_output_precision_edit.setText(OUTPUT_PRECISION)
        self.inner_output_precision_edit.setStyleSheet(input_style)
        inner_precision_grid.addWidget(self.inner_output_precision_edit, inner_precision_row, 1)

        inner_precision_layout.addLayout(inner_precision_grid)

        self.inner_precision_widget.setLayout(inner_precision_layout)
        
        # 延迟设置列最小宽度，确保与 step4_grid 对齐
        def _align_inner_precision_grid_columns():
            try:
                # 获取 step4_grid 中第一列的最大宽度（标签列）
                if step4_grid.count() > 0:
                    max_width = 0
                    # 遍历 step4_grid 中的所有标签，找到最大宽度（跳过标签容器）
                    for row in range(step4_grid.rowCount()):
                        item = step4_grid.itemAtPosition(row, 0)
                        if item and item.widget():
                            widget = item.widget()
                            # 只处理标签（QLabel），跳过标签容器（QWidget）
                            if isinstance(widget, QLabel):
                                widget.update()  # 确保已渲染
                                hint_width = widget.sizeHint().width()
                                if hint_width > max_width:
                                    max_width = hint_width
                    # 如果找到了最大宽度，设置 inner_precision_grid 第一列的最小宽度
                    # 这样标签列对齐后，输入框列也会自动对齐
                    if max_width > 0:
                        inner_precision_grid.setColumnMinimumWidth(0, max_width)
            except Exception:
                pass
        
        QtCore.QTimer.singleShot(100, _align_inner_precision_grid_columns)
        self.inner_precision_widget.setVisible(False)  # 初始隐藏
        step4_card_layout.addWidget(self.inner_precision_widget)

        # 继续使用新的网格布局添加其他字段（起始日期、结束日期）
        # 使用与 step4_grid 相同的列拉伸设置，确保宽度一致
        date_grid = QGridLayout()
        date_grid.setSpacing(10)
        date_grid.setColumnStretch(0, 0)  # 标签列不拉伸
        date_grid.setColumnStretch(1, 1)  # 输入框列拉伸
        
        date_row = 0

        # 起始日期
        date_grid.addWidget(QLabel(tr("step4_start_date", "起始日期:")), date_row, 0)
        self.shel_start_edit = LineEdit()
        self.shel_start_edit.setText("20250101")
        self.shel_start_edit.setStyleSheet(input_style)
        date_grid.addWidget(self.shel_start_edit, date_row, 1)
        date_row += 1

        # 结束日期
        date_grid.addWidget(QLabel(tr("step4_end_date", "结束日期:")), date_row, 0)
        self.shel_end_edit = LineEdit()
        self.shel_end_edit.setText("20250101")
        self.shel_end_edit.setStyleSheet(input_style)
        date_grid.addWidget(self.shel_end_edit, date_row, 1)

        # 延迟设置列最小宽度，确保与 step4_grid 对齐
        def _align_date_grid_columns():
            try:
                # 获取 step4_grid 中第一列的最大宽度（标签列）
                if step4_grid.count() > 0:
                    max_width = 0
                    # 遍历 step4_grid 中的所有标签，找到最大宽度（跳过标签容器）
                    for row in range(step4_grid.rowCount()):
                        item = step4_grid.itemAtPosition(row, 0)
                        if item and item.widget():
                            widget = item.widget()
                            # 只处理标签（QLabel），跳过标签容器（QWidget）
                            if isinstance(widget, QLabel):
                                widget.update()  # 确保已渲染
                                hint_width = widget.sizeHint().width()
                                if hint_width > max_width:
                                    max_width = hint_width
                    # 如果找到了最大宽度，设置 date_grid 第一列的最小宽度
                    # 这样标签列对齐后，输入框列也会自动对齐
                    if max_width > 0:
                        date_grid.setColumnMinimumWidth(0, max_width)
            except Exception:
                pass
        
        QtCore.QTimer.singleShot(100, _align_date_grid_columns)
        step4_card_layout.addLayout(date_grid)

        # 谱分区输出方案选择
        output_scheme_grid = QGridLayout()
        output_scheme_grid.setSpacing(10)
        output_scheme_grid.setColumnStretch(0, 0)  # 标签列不拉伸
        output_scheme_grid.setColumnStretch(1, 1)  # 输入框列拉伸
        
        # 谱分区输出方案标签和下拉框
        output_scheme_label = QLabel(tr("step4_output_scheme", "谱分区输出方案："))
        output_scheme_grid.addWidget(output_scheme_label, 0, 0)
        
        self.output_scheme_combo = ComboBox()
        # 加载方案列表
        self._load_output_schemes_to_combo()
        self.output_scheme_combo.currentTextChanged.connect(self._on_output_scheme_changed)
        self.output_scheme_combo.setStyleSheet(combo_style)
        # 设置文本左对齐（延迟设置，确保样式已应用）
        def _set_output_scheme_combo_alignment():
            try:
                if hasattr(self.output_scheme_combo, 'lineEdit'):
                    line_edit = self.output_scheme_combo.lineEdit()
                    if line_edit:
                        line_edit.setAlignment(Qt.AlignmentFlag.AlignLeft)
            except:
                pass
        QtCore.QTimer.singleShot(10, _set_output_scheme_combo_alignment)
        output_scheme_grid.addWidget(self.output_scheme_combo, 0, 1)
        # 确保创建后尝试从 ww3_shel.nml 同步方案
        try:
            QtCore.QTimer.singleShot(100, self._load_output_scheme_from_ww3_shel)
        except Exception:
            pass
        
        # 延迟设置列最小宽度，确保与 step4_grid 对齐（在添加到布局后执行）
        def _align_output_scheme_grid_columns():
            try:
                # 获取 step4_grid 中第一列的最大宽度（标签列）
                if step4_grid.count() > 0:
                    max_width = 0
                    # 遍历 step4_grid 中的所有标签，找到最大宽度（跳过标签容器）
                    for row in range(step4_grid.rowCount()):
                        item = step4_grid.itemAtPosition(row, 0)
                        if item and item.widget():
                            widget = item.widget()
                            # 只处理标签（QLabel），跳过标签容器（QWidget）
                            if isinstance(widget, QLabel):
                                widget.update()  # 确保已渲染
                                hint_width = widget.sizeHint().width()
                                if hint_width > max_width:
                                    max_width = hint_width
                    # 如果找到了最大宽度，设置 output_scheme_grid 第一列的最小宽度
                    # 这样标签列对齐后，ComboBox 列也会自动对齐
                    if max_width > 0:
                        output_scheme_grid.setColumnMinimumWidth(0, max_width)
            except Exception:
                pass
        
        step4_card_layout.addLayout(output_scheme_grid)
        
        # 在添加到布局后执行对齐，确保 step4_grid 已经完成对齐
        QtCore.QTimer.singleShot(150, _align_output_scheme_grid_columns)

        # 从风场文件读取时间范围按钮
        btn_load_time = PrimaryPushButton(tr("step4_load_time_from_wind_nc", "从 wind.nc 读取时间范围"))
        btn_load_time.setStyleSheet(self._get_button_style())
        btn_load_time.clicked.connect(lambda: self.load_time_from_nc())
        step4_card_layout.addWidget(btn_load_time)

        # 应用参数按钮
        btn_apply_params = PrimaryPushButton(tr("step4_confirm_params", "确认参数"))
        btn_apply_params.setStyleSheet(self._get_button_style())
        btn_apply_params.clicked.connect(self.modify_ww3_file)
        step4_card_layout.addWidget(btn_apply_params)

        # 设置内容区内边距
        step4_card.viewLayout.setContentsMargins(11, 10, 11, 12)
        step4_card.viewLayout.addLayout(step4_card_layout)
        content_layout.addWidget(step4_card)

    def _load_output_schemes_to_combo(self, preserve_selection=None):
        """加载输出变量方案列表到下拉框
        
        Args:
            preserve_selection: 如果提供，刷新后保持选择该方案；否则默认选择"默认方案"
        """
        if not hasattr(self, 'output_scheme_combo'):
            return
        
        # 保存当前选择（如果未指定要保留的选择）
        if preserve_selection is None:
            preserve_selection = self.output_scheme_combo.currentText()
        
        # 从配置文件加载方案
        config = load_config()
        schemes = config.get("OUTPUT_VARS_SCHEMES", {})
        
        # 默认方案的变量列表
        default_scheme_name = tr("default_scheme", "默认方案")
        
        # 如果没有方案或默认方案不存在，创建默认方案
        if not schemes or default_scheme_name not in schemes:
            default_scheme_vars = ["HS", "DIR", "FP", "T02", "WND", "PHS", "PTP", "PDIR", "PWS", "PNR", "TWS"]
            schemes[default_scheme_name] = default_scheme_vars
            config["OUTPUT_VARS_SCHEMES"] = schemes
            
            # 保存配置
            from setting.config import CONFIG_FILE
            try:
                with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=4)
            except Exception as e:
                if hasattr(self, 'log'):
                    self.log(tr("step4_default_scheme_save_failed", "⚠️ 保存默认方案失败：{error}").format(error=e))
        
        # 清空下拉框并添加方案名称
        # 临时断开信号连接，避免在刷新时触发更新配置
        self.output_scheme_combo.blockSignals(True)
        self.output_scheme_combo.clear()
        scheme_names = list(schemes.keys())
        if scheme_names:
            self.output_scheme_combo.addItems(scheme_names)
            # 如果指定了要保留的选择且该方案存在，则选择它；否则默认选择"默认方案"
            if preserve_selection and preserve_selection in scheme_names:
                # 确保选择正确的方案
                index = scheme_names.index(preserve_selection)
                self.output_scheme_combo.setCurrentIndex(index)
                # 验证选择是否正确
                if self.output_scheme_combo.currentText() != preserve_selection:
                    self.output_scheme_combo.setCurrentText(preserve_selection)
            elif default_scheme_name in scheme_names:
                self.output_scheme_combo.setCurrentText(default_scheme_name)
            else:
                self.output_scheme_combo.setCurrentIndex(0)
        # 恢复信号连接
        self.output_scheme_combo.blockSignals(False)

        # 刷新完成后再同步一次（确保列表已就绪）
        try:
            QtCore.QTimer.singleShot(0, self._load_output_scheme_from_ww3_shel)
        except Exception:
            pass

    def _load_output_scheme_from_ww3_shel(self):
        """从当前工作目录的 ww3_shel.nml 读取 TYPE%FIELD%LIST 并设置方案"""
        if not hasattr(self, 'selected_folder') or not self.selected_folder:
            return
        if not hasattr(self, 'output_scheme_combo'):
            return

        # 查找 ww3_shel.nml（优先工作目录，其次 coarse/fine）
        candidates = [
            os.path.join(self.selected_folder, "ww3_shel.nml"),
            os.path.join(self.selected_folder, "coarse", "ww3_shel.nml"),
            os.path.join(self.selected_folder, "fine", "ww3_shel.nml"),
        ]
        shel_path = next((p for p in candidates if os.path.exists(p)), None)
        if not shel_path:
            return

        try:
            with open(shel_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            in_output_type = False
            type_field_list = None
            for line in lines:
                line_stripped = line.strip()
                if line_stripped.startswith("!"):
                    continue
                if "&OUTPUT_TYPE_NML" in line_stripped:
                    in_output_type = True
                    continue
                if in_output_type and line_stripped.startswith("/"):
                    break
                if in_output_type and "TYPE%FIELD%LIST" in line_stripped and "=" in line_stripped:
                    match = re.search(r"TYPE%FIELD%LIST\s*=\s*['\"]([^'\"]+)['\"]", line, re.IGNORECASE)
                    if match:
                        type_field_list = match.group(1)
                        break

            if not type_field_list:
                return

            # 归一化为大写列表
            target_vars = [v.strip().upper() for v in type_field_list.split() if v.strip()]
            if not target_vars:
                return

            config = load_config()
            schemes = config.get("OUTPUT_VARS_SCHEMES", {})
            matched_scheme = None
            for scheme_name, vars_list in schemes.items():
                if not vars_list:
                    continue
                scheme_vars = [str(v).strip().upper() for v in vars_list if str(v).strip()]
                if sorted(scheme_vars) == sorted(target_vars):
                    matched_scheme = scheme_name
                    break
            
            if matched_scheme:
                self.output_scheme_combo.blockSignals(True)
                self.output_scheme_combo.setCurrentText(matched_scheme)
                self.output_scheme_combo.blockSignals(False)
        except Exception:
            # 静默失败，避免打扰用户
            pass
    
    def _on_output_scheme_changed(self, scheme_name):
        """当选择输出变量方案时，更新配置文件"""
        import re
        
        if not scheme_name:
            return
        
        # 从配置文件加载方案
        config = load_config()
        schemes = config.get("OUTPUT_VARS_SCHEMES", {})
        
        if scheme_name not in schemes:
            if hasattr(self, 'log'):
                self.log(tr("no_scheme_selected", "❌ 请先选择一个方案"))
            return
        
        # 获取选中方案的变量列表
        selected_vars = schemes[scheme_name]
        if not selected_vars:
            if hasattr(self, 'log'):
                self.log(tr("output_vars_empty", "❌ 请至少选择一个输出变量"))
            return
        
        # 生成变量列表字符串
        var_list_str = ' '.join(selected_vars)
        
        # 获取 public/ww3 目录路径（在项目根目录下）
        # __file__ is main/home/home_step_four_card.py; public is under project root
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        public_ww3_dir = config.get("PUBLIC_WW3_PATH", os.path.join(project_root, "public", "ww3"))
        
        ww3_shel_path = os.path.join(public_ww3_dir, "ww3_shel.nml")
        ww3_ounf_path = os.path.join(public_ww3_dir, "ww3_ounf.nml")
        
        success_count = 0
        error_messages = []
        
        # 更新 ww3_shel.nml
        if not os.path.exists(ww3_shel_path):
            error_messages.append(tr("step4_file_not_found", "文件不存在: {path}").format(path=ww3_shel_path))
        else:
            try:
                with open(ww3_shel_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                new_lines = []
                modified = False
                
                for line in lines:
                    # 检查是否为注释行
                    line_stripped = line.lstrip()
                    is_comment = line_stripped.startswith('!')
                    
                    # 查找并替换 TYPE%FIELD%LIST 行（非注释行）
                    if not is_comment and re.search(r'TYPE%FIELD%LIST', line, re.IGNORECASE) and "=" in line:
                        # 替换为新的变量列表
                        new_lines.append(f"  TYPE%FIELD%LIST       = '{var_list_str}'\n")
                        modified = True
                    else:
                        new_lines.append(line)
                
                if modified:
                    with open(ww3_shel_path, "w", encoding="utf-8") as f:
                        f.writelines(new_lines)
                    success_count += 1
                else:
                    error_messages.append(tr("step4_ww3_shel_type_field_list_missing", "ww3_shel.nml 中未找到 TYPE%FIELD%LIST 配置行"))
            except Exception as e:
                error_messages.append(tr("step4_ww3_shel_update_failed", "更新 ww3_shel.nml 失败：{error}").format(error=str(e)))
        
        # 更新 ww3_ounf.nml
        if not os.path.exists(ww3_ounf_path):
            error_messages.append(tr("step4_file_not_found", "文件不存在: {path}").format(path=ww3_ounf_path))
        else:
            try:
                with open(ww3_ounf_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                new_lines = []
                modified = False
                
                for line in lines:
                    # 检查是否为注释行
                    line_stripped = line.lstrip()
                    is_comment = line_stripped.startswith('!')
                    
                    # 查找并替换 FIELD%LIST 行（非注释行）
                    if not is_comment and re.search(r'FIELD%LIST', line, re.IGNORECASE) and "=" in line:
                        # 替换为新的变量列表
                        new_lines.append(f"  FIELD%LIST             =  '{var_list_str}'\n")
                        modified = True
                    else:
                        new_lines.append(line)
                
                if modified:
                    with open(ww3_ounf_path, "w", encoding="utf-8") as f:
                        f.writelines(new_lines)
                    success_count += 1
                else:
                    error_messages.append(tr("step4_ww3_ounf_field_list_missing", "ww3_ounf.nml 中未找到 FIELD%LIST 配置行"))
            except Exception as e:
                error_messages.append(tr("step4_ww3_ounf_update_failed", "更新 ww3_ounf.nml 失败：{error}").format(error=str(e)))
        
        # 不在这里显示日志，只在确认参数时显示
        # 如果更新失败，记录错误但不显示日志
        if success_count == 0 and error_messages:
            # 静默记录错误，不显示给用户
            pass
    
    def _update_wavewatch_title(self):
        """更新 WAVEWATCH 配置标签文本和嵌套网格相关的 UI（根据网格类型）"""
        from .utils import HomeState
        is_nested = HomeState.is_nested_grid()

        if hasattr(self, 'wavewatch_title') and self.wavewatch_title:
            if is_nested:
                # 嵌套网格时，显示"外网格参数"
                self.wavewatch_title.setText(tr("step4_outer_params", "外网格参数"))
            else:
                # 普通网格时，显示"WAVEWATCH 配置"
                self.wavewatch_title.setText(tr("step4_wavewatch_config", "WAVEWATCH 配置"))

        # 更新嵌套网格相关的 UI 可见性
        if hasattr(self, 'outer_precision_title_container'):
            # 外网格参数标题：嵌套网格时显示，普通网格时隐藏
            self.outer_precision_title_container.setVisible(is_nested)

        if hasattr(self, 'inner_precision_widget'):
            # 内网格精度参数：嵌套网格时显示，普通网格时隐藏
            self.inner_precision_widget.setVisible(is_nested)

    def load_time_from_nc(self, file_name="wind.nc"):
        """从风场文件中读取时间范围并更新 GUI 起止日期"""
        # 严格的类型和值检查
        if not hasattr(self, 'selected_folder'):
            self.log(tr("step4_selected_folder_missing", "❌ selected_folder 属性不存在！"))
            return

        if self.selected_folder is None:
            self.log(tr("step4_workdir_missing", "❌ 当前工作目录不存在！"))
            return

        if not isinstance(self.selected_folder, str):
            self.log(tr("step4_selected_folder_type_error", "❌ selected_folder 类型错误: {type}, 值: {value}").format(type=type(self.selected_folder), value=repr(self.selected_folder)))
            self.log(tr("step4_workdir_missing", "❌ 当前工作目录不存在！"))
            return

        if not self.selected_folder.strip():
            self.log(tr("step4_workdir_path_empty", "❌ 工作目录路径为空！"))
            return

        # 查找工作目录中包含 wind 的文件（可能是 wind.nc 或 wind_current_ssh_ice.nc 等）
        wind_files = glob.glob(os.path.join(self.selected_folder, "*wind*.nc"))
        
        if not wind_files:
            # 如果找不到包含 wind 的文件，尝试使用 wind.nc
            data_nc_path = os.path.join(self.selected_folder, "wind.nc")
            if not os.path.exists(data_nc_path):
                self.log(tr("step4_wind_nc_not_found", "❌ 未找到风场文件（工作目录中不存在包含 'wind' 的 .nc 文件）"))
                return
        else:
            # 如果有多个，优先选择 wind.nc，否则选择第一个
            wind_nc_path = os.path.join(self.selected_folder, "wind.nc")
            if wind_nc_path in wind_files:
                data_nc_path = wind_nc_path
            else:
                data_nc_path = wind_files[0]
        
        file_name = os.path.basename(data_nc_path)

        try:
            ds = Dataset(data_nc_path)
            
            # 查找时间变量（与 view_all_field_files_info 保持一致的顺序）
            time_var = None
            time_var_name = None
            for time_name in ["time", "Time", "TIME", "valid_time", "MT", "mt", "t"]:
                if time_name in ds.variables:
                    time_var = ds.variables[time_name]
                    time_var_name = time_name
                    break
            
            if time_var is None:
                self.log(tr("step4_time_var_not_found", "❌ {file} 中未找到时间变量（尝试了: time, Time, TIME, valid_time, MT, mt, t）。").format(file=file_name))
                ds.close()
                return

            # 获取时间范围（完全按照 view_all_field_files_info 的逻辑）
            try:
                time_units = getattr(time_var, 'units', None)
                time_calendar = getattr(time_var, 'calendar', 'gregorian')
                
                if time_units:
                    times = num2date(time_var[:], time_units, calendar=time_calendar)
                    if len(times) > 0:
                        time_start = times[0]
                        time_end = times[-1]
                        # 格式化为 YYYYMMDD
                        start_str = time_start.strftime("%Y%m%d")
                        end_str = time_end.strftime("%Y%m%d")
                    else:
                        self.log(tr("step4_time_var_empty", "❌ {file} 中的时间变量为空。").format(file=file_name))
                        ds.close()
                        return
                else:
                    # 如果没有单位，无法转换
                    self.log(tr("step4_time_units_missing", "⚠️ {file} 中的时间变量没有 units 属性，无法转换时间。").format(file=file_name))
                    ds.close()
                    return
            except Exception as e:
                self.log(tr("step4_time_read_failed", "❌ 读取 {file} 时间失败：{error}").format(file=file_name, error=e))
                ds.close()
                return

            ds.close()

            self.shel_start_edit.setText(start_str)
            self.shel_end_edit.setText(end_str)

            self.log(tr("step4_time_range_loaded", "✅ 已从 {file} 读取时间范围：{start} → {end}").format(file=file_name, start=start_str, end=end_str))

        except Exception as e:
            self.log(tr("step4_time_read_failed", "❌ 读取 {file} 时间失败：{error}").format(file=file_name, error=e))

    def copy_public_files(self):
        """将 public/ww3 下的文件复制到工作文件夹"""
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            self.log(tr("step4_workdir_missing", "❌ 当前工作目录不存在！"))
            return
        self._copy_public_files_to_dir(self.selected_folder)

    def _copy_public_files_to_dir(self, target_dir, grid_label=""):
        """将 public/ww3 下的文件复制到指定目录"""
        if not target_dir or not isinstance(target_dir, str):
            return

        # 获取项目根目录下的 public/ww3 路径
        # __file__ 是 main/home/home_step_four_card.py，需要回到项目根目录
        script_dir = os.path.dirname(os.path.abspath(__file__))  # main/home
        main_dir = os.path.dirname(script_dir)  # main
        project_root = os.path.dirname(main_dir)  # 项目根目录
        src_dir = os.path.normpath(os.path.join(project_root, "public", "ww3"))
        
        if not os.path.exists(src_dir):
            self.log(tr("step4_dir_not_found", "⚠️ 未找到目录：{path}").format(path=src_dir))
            return

        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        # 使用翻译函数检查是否为嵌套网格（支持中英文）
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")

        # 检查计算模式
        calc_mode = getattr(self, 'calc_mode_var', '')
        # 优先检查 calc_mode_combo 的当前选择（这是用户界面上的实际值）
        if hasattr(self, 'calc_mode_combo') and self.calc_mode_combo:
            combo_text = self.calc_mode_combo.currentText()
            if combo_text:
                calc_mode = combo_text
        
        spectral_text = tr("step3_spectral_point", "谱空间逐点计算")
        track_text = tr("step3_track_mode", "航迹模式")
        is_spectral_mode = (calc_mode == spectral_text or calc_mode == "谱空间逐点计算")
        is_track_mode = (calc_mode == track_text or calc_mode == "航迹模式")

        # 如果是嵌套网格模式，server.sh 和 ww3_multi.nml 应该复制到工作目录而不是子文件夹
        workdir_for_special = self.selected_folder if is_nested_grid and hasattr(self, 'selected_folder') else target_dir
        # 需要复制到工作目录的文件列表（嵌套网格模式下）
        special_files = ["server.sh", "ww3_multi.nml"]

        # 根据模式决定需要跳过的文件
        skip_files = []
        # 如果不是嵌套网格模式，跳过 ww3_multi.nml
        if not is_nested_grid:
            skip_files.append("ww3_multi.nml")
        # 如果不是航迹模式，跳过 ww3_trnc.nml
        if not is_track_mode:
            skip_files.append("ww3_trnc.nml")
        # 如果不是谱空间逐点计算模式，跳过 ww3_ounp.nml
        if not is_spectral_mode:
            skip_files.append("ww3_ounp.nml")

        try:
            # 遍历 public 目录下的文件并复制
            copied = 0
            for item in os.listdir(src_dir):
                src_path = os.path.join(src_dir, item)

                # 如果是嵌套网格模式且文件是特殊文件（ww3.slurm 或 ww3_multi.nml），跳过（已在公共文件处理中复制）
                if is_nested_grid and item in special_files:
                    continue  # 跳过特殊文件，它们已在 _copy_public_special_files_to_workdir 中处理
                
                # 根据模式跳过不需要的文件
                if item in skip_files:
                    continue
                
                # 确保是文件而不是目录
                if not os.path.isfile(src_path):
                    continue
                
                dst_path = os.path.join(target_dir, item)
                shutil.copy2(src_path, dst_path)
                copied += 1
                

            if copied > 0:
                prefix = f"{grid_label} " if grid_label else ""
                # 嵌套网格模式下，特殊文件已在公共文件处理中复制，这里只显示其他文件
                self.log(f"{prefix}{tr('step4_files_copied', '✅ 已复制 {count} 个 public/ww3 文件到当前工作目录').format(count=copied)}")
            else:
                self.log(tr("step4_no_files_to_copy", "⚠️ {path} 中没有可复制的文件。").format(path=src_dir))

        except Exception as e:
            self.log(tr("step4_copy_files_failed", "❌ 复制文件时出错：{error}").format(error=e))

