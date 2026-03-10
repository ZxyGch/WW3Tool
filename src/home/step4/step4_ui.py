"""
第四步：配置WW3运行参数模块 - UI部分
包含UI创建（强迫场选择、Slurm配置、WAVEWATCH配置、输出方案等）
"""
import os
import json
import glob
from netCDF4 import Dataset
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QGridLayout, QHBoxLayout, QWidget, QSizePolicy
from qfluentwidgets import PrimaryPushButton, LineEdit, ComboBox, CheckBox
from setting.language_manager import tr
from setting.config import load_config, ST_OPTIONS, CPU_GROUP, DEFAULT_CPU, KERNEL_NUM, NODE_NUM, DEFAULT_CONFIG
from ..utils import create_header_card
from .step4_service import StepFourServiceMixin


class HomeStepFourCard(StepFourServiceMixin):
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

        # 从配置读取默认计算/输出精度（设置页 WW3 配置）
        _cfg = load_config()
        _compute_prec = str(_cfg.get("COMPUTE_PRECISION", DEFAULT_CONFIG.get("COMPUTE_PRECISION", "1800")))
        _output_prec = str(_cfg.get("OUTPUT_PRECISION", DEFAULT_CONFIG.get("OUTPUT_PRECISION", "3600")))

        # 外网格计算精度
        outer_precision_grid.addWidget(QLabel(tr("step4_compute_precision", "计算精度 (秒):")), outer_precision_row, 0)
        self.shel_step_edit = LineEdit()
        self.shel_step_edit.setText(_compute_prec)
        self.shel_step_edit.setStyleSheet(input_style)
        outer_precision_grid.addWidget(self.shel_step_edit, outer_precision_row, 1)
        outer_precision_row += 1

        # 外网格输出精度
        outer_precision_grid.addWidget(QLabel(tr("step4_output_precision", "输出精度 (秒):")), outer_precision_row, 0)
        self.output_precision_edit = LineEdit()
        self.output_precision_edit.setText(_output_prec)
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
        self.inner_shel_step_edit.setText(_compute_prec)
        self.inner_shel_step_edit.setStyleSheet(input_style)
        inner_precision_grid.addWidget(self.inner_shel_step_edit, inner_precision_row, 1)
        inner_precision_row += 1

        # 内网格输出精度
        inner_precision_grid.addWidget(QLabel(tr("step4_output_precision", "输出精度 (秒):")), inner_precision_row, 0)
        self.inner_output_precision_edit = LineEdit()
        self.inner_output_precision_edit.setText(_output_prec)
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
