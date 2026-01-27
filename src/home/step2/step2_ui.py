"""
第二步：生成网格模块 - UI部分
包含UI创建（外网格参数、内网格参数、网格类型选择、按钮等）
"""
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QGridLayout, QHBoxLayout, QWidget, QSizePolicy
from qfluentwidgets import PrimaryPushButton, LineEdit, ComboBox
from setting.language_manager import tr
from setting.config import DX, DY, LONGITUDE_WEST, LONGITUDE_EAST, LATITUDE_SORTH, LATITUDE_NORTH
from ..utils import create_header_card
from .step2_service import StepTwoServiceMixin


class HomeStepTwoCard(StepTwoServiceMixin):
    """第二步：生成网格 Mixin"""
    
    def create_step_2_card(self, content_widget, content_layout):
        """创建第二步：生成网格的UI"""
        # 使用通用函数创建卡片
        step2_card, step2_card_layout = create_header_card(
            content_widget,
            tr("step2_title", "第二步：生成网格")
        )

        # 输入框样式：使用主题适配的样式
        input_style = self._get_input_style()

        # 外网格参数容器
        self.outer_grid_widget = QWidget()
        outer_grid_layout = QVBoxLayout()
        outer_grid_layout.setSpacing(10)
        outer_grid_layout.setContentsMargins(0, 0, 0, 0)

        # 外网格参数小标题（保存为实例变量以便动态控制）
        self.outer_title_container = QWidget()
        outer_title_layout = QHBoxLayout()
        outer_title_layout.setContentsMargins(0, 0, 0, 0)
        outer_title_layout.setSpacing(10)
        
        # 左侧横线
        outer_line_left = QtWidgets.QFrame()
        outer_line_left.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        outer_line_left.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        outer_line_left.setFixedHeight(1)
        outer_line_left.setMinimumHeight(1)
        outer_line_left.setMaximumHeight(1)
        outer_line_left.setStyleSheet("background-color: #888888; border: none;")
        outer_title_layout.addWidget(outer_line_left)
        
        # 标题标签（居中）
        self.outer_title = QLabel(tr("step2_outer_params", "外网格参数"))
        self.outer_title.setStyleSheet("font-weight: normal; font-size: 14px;")
        self.outer_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer_title_layout.addWidget(self.outer_title)
        
        # 右侧横线
        outer_line_right = QtWidgets.QFrame()
        outer_line_right.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        outer_line_right.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        outer_line_right.setFixedHeight(1)
        outer_line_right.setMinimumHeight(1)
        outer_line_right.setMaximumHeight(1)
        outer_line_right.setStyleSheet("background-color: #888888; border: none;")
        outer_title_layout.addWidget(outer_line_right)
        
        # 设置横线可伸缩
        outer_title_layout.setStretch(0, 1)  # 左侧横线
        outer_title_layout.setStretch(2, 1)  # 右侧横线
        
        self.outer_title_container.setLayout(outer_title_layout)
        self.outer_title_container.setVisible(False)  # 初始隐藏，选择嵌套网格时才显示
        outer_grid_layout.addWidget(self.outer_title_container)

        # 外网格参数输入框网格
        outer_grid = QGridLayout()
        outer_grid.setSpacing(10)

        # DX, DY 输入框
        outer_grid.addWidget(QLabel(tr("step2_dx", "DX:")), 0, 0)
        self.dx_edit = LineEdit()
        # 格式化 DX 为最多2位小数
        try:
            dx_value = float(DX) if DX else 0.05
            self.dx_edit.setText(f"{dx_value:.2f}")
        except (ValueError, TypeError):
            self.dx_edit.setText("0.05")
        self.dx_edit.setStyleSheet(input_style)
        outer_grid.addWidget(self.dx_edit, 0, 1)

        outer_grid.addWidget(QLabel(tr("step2_dy", "DY:")), 0, 2)
        self.dy_edit = LineEdit()
        # 格式化 DY 为最多2位小数
        try:
            dy_value = float(DY) if DY else 0.05
            self.dy_edit.setText(f"{dy_value:.2f}")
        except (ValueError, TypeError):
            self.dy_edit.setText("0.05")
        self.dy_edit.setStyleSheet(input_style)
        outer_grid.addWidget(self.dy_edit, 0, 3)

        # 经度输入框
        outer_grid.addWidget(QLabel(tr("step2_lon_west", "西经:")), 1, 0)
        self.lon_west_edit = LineEdit()
        self.lon_west_edit.setText(LONGITUDE_WEST if LONGITUDE_WEST else "")
        self.lon_west_edit.setStyleSheet(input_style)
        outer_grid.addWidget(self.lon_west_edit, 1, 1)

        outer_grid.addWidget(QLabel(tr("step2_lon_east", "东经:")), 1, 2)
        self.lon_east_edit = LineEdit()
        self.lon_east_edit.setText(LONGITUDE_EAST if LONGITUDE_EAST else "")
        self.lon_east_edit.setStyleSheet(input_style)
        outer_grid.addWidget(self.lon_east_edit, 1, 3)

        # 纬度输入框
        outer_grid.addWidget(QLabel(tr("step2_lat_south", "南纬:")), 2, 0)
        self.lat_south_edit = LineEdit()
        self.lat_south_edit.setText(LATITUDE_SORTH if LATITUDE_SORTH else "")
        self.lat_south_edit.setStyleSheet(input_style)
        outer_grid.addWidget(self.lat_south_edit, 2, 1)

        outer_grid.addWidget(QLabel(tr("step2_lat_north", "北纬:")), 2, 2)
        self.lat_north_edit = LineEdit()
        self.lat_north_edit.setText(LATITUDE_NORTH if LATITUDE_NORTH else "")
        self.lat_north_edit.setStyleSheet(input_style)
        outer_grid.addWidget(self.lat_north_edit, 2, 3)

        outer_grid_layout.addLayout(outer_grid)
        self.outer_grid_widget.setLayout(outer_grid_layout)
        step2_card_layout.addWidget(self.outer_grid_widget)

        # 内网格参数容器（初始隐藏）
        self.inner_grid_widget = QWidget()
        inner_grid_layout = QVBoxLayout()
        inner_grid_layout.setSpacing(10)
        inner_grid_layout.setContentsMargins(0, 0, 0, 0)

        # 内网格参数小标题
        inner_title_container = QWidget()
        inner_title_layout = QHBoxLayout()
        inner_title_layout.setContentsMargins(0, 0, 0, 0)
        inner_title_layout.setSpacing(10)
        
        # 左侧横线
        inner_line_left = QtWidgets.QFrame()
        inner_line_left.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        inner_line_left.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        inner_line_left.setFixedHeight(1)
        inner_line_left.setMinimumHeight(1)
        inner_line_left.setMaximumHeight(1)
        inner_line_left.setStyleSheet("background-color: #888888; border: none;")
        inner_title_layout.addWidget(inner_line_left)
        
        # 标题标签（居中）
        inner_title = QLabel(tr("step2_inner_params", "内网格参数"))
        inner_title.setStyleSheet("font-weight: normal; font-size: 14px;")
        inner_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner_title_layout.addWidget(inner_title)
        
        # 右侧横线
        inner_line_right = QtWidgets.QFrame()
        inner_line_right.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        inner_line_right.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        inner_line_right.setFixedHeight(1)
        inner_line_right.setMinimumHeight(1)
        inner_line_right.setMaximumHeight(1)
        inner_line_right.setStyleSheet("background-color: #888888; border: none;")
        inner_title_layout.addWidget(inner_line_right)
        
        # 设置横线可伸缩
        inner_title_layout.setStretch(0, 1)  # 左侧横线
        inner_title_layout.setStretch(2, 1)  # 右侧横线
        
        inner_title_container.setLayout(inner_title_layout)
        inner_grid_layout.addWidget(inner_title_container)

        # 内网格参数输入框网格
        inner_grid = QGridLayout()
        inner_grid.setSpacing(10)

        # DX, DY 输入框
        inner_grid.addWidget(QLabel(tr("step2_dx", "DX:")), 0, 0)
        self.inner_dx_edit = LineEdit()
        # 格式化 DX 为最多2位小数
        try:
            dx_value = float(DX) if DX else 0.05
            self.inner_dx_edit.setText(f"{dx_value:.2f}")
        except (ValueError, TypeError):
            self.inner_dx_edit.setText("0.05")
        self.inner_dx_edit.setStyleSheet(input_style)
        inner_grid.addWidget(self.inner_dx_edit, 0, 1)

        inner_grid.addWidget(QLabel(tr("step2_dy", "DY:")), 0, 2)
        self.inner_dy_edit = LineEdit()
        # 格式化 DY 为最多2位小数
        try:
            dy_value = float(DY) if DY else 0.05
            self.inner_dy_edit.setText(f"{dy_value:.2f}")
        except (ValueError, TypeError):
            self.inner_dy_edit.setText("0.05")
        self.inner_dy_edit.setStyleSheet(input_style)
        inner_grid.addWidget(self.inner_dy_edit, 0, 3)

        # 经度输入框
        inner_grid.addWidget(QLabel(tr("step2_lon_west", "西经:")), 1, 0)
        self.inner_lon_west_edit = LineEdit()
        self.inner_lon_west_edit.setText(LONGITUDE_WEST if LONGITUDE_WEST else "")
        self.inner_lon_west_edit.setStyleSheet(input_style)
        inner_grid.addWidget(self.inner_lon_west_edit, 1, 1)

        inner_grid.addWidget(QLabel(tr("step2_lon_east", "东经:")), 1, 2)
        self.inner_lon_east_edit = LineEdit()
        self.inner_lon_east_edit.setText(LONGITUDE_EAST if LONGITUDE_EAST else "")
        self.inner_lon_east_edit.setStyleSheet(input_style)
        inner_grid.addWidget(self.inner_lon_east_edit, 1, 3)

        # 纬度输入框
        inner_grid.addWidget(QLabel(tr("step2_lat_south", "南纬:")), 2, 0)
        self.inner_lat_south_edit = LineEdit()
        self.inner_lat_south_edit.setText(LATITUDE_SORTH if LATITUDE_SORTH else "")
        self.inner_lat_south_edit.setStyleSheet(input_style)
        inner_grid.addWidget(self.inner_lat_south_edit, 2, 1)

        inner_grid.addWidget(QLabel(tr("step2_lat_north", "北纬:")), 2, 2)
        self.inner_lat_north_edit = LineEdit()
        self.inner_lat_north_edit.setText(LATITUDE_NORTH if LATITUDE_NORTH else "")
        self.inner_lat_north_edit.setStyleSheet(input_style)
        inner_grid.addWidget(self.inner_lat_north_edit, 2, 3)

        inner_grid_layout.addLayout(inner_grid)
        self.inner_grid_widget.setLayout(inner_grid_layout)
        self.inner_grid_widget.setVisible(False)  # 初始隐藏
        step2_card_layout.addWidget(self.inner_grid_widget)

        # 下拉选择框样式：使用主题适配的样式
        combo_style = self._get_combo_style()

        # 网格类型选择（下拉框）- 放在"从风场文件读取范围"按钮上面
        grid_type_layout = QGridLayout()
        grid_type_layout.setSpacing(0)  # 与 outer_grid 的间距一致
        grid_type_label = QLabel(tr("step2_grid_type", "类型："))
        grid_type_layout.addWidget(grid_type_label, 0, 0)
        self.grid_type_combo = ComboBox()
        normal_text = tr("step2_grid_type_normal", "普通网格")
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        self.grid_type_combo.addItems([normal_text, nested_text])
        
        # 使用全局状态管理
        from ..utils import HomeState
        # 先检查全局状态是否已有值，如果没有才使用默认值
        current_grid_type = HomeState.get_grid_type()  # 不传 default，如果未设置会返回 None
        if current_grid_type is None:
            # 全局状态为空，设置默认值为普通网格
            HomeState.set_grid_type(normal_text)
            # 先断开信号，避免触发 _set_step2_grid_type
            self.grid_type_combo.blockSignals(True)
            self.grid_type_combo.setCurrentText(normal_text)
            self.grid_type_combo.blockSignals(False)
            self.grid_type_var = normal_text
        else:
            # 全局状态已有值，使用全局状态的值
            # 先断开信号，避免触发 _set_step2_grid_type
            self.grid_type_combo.blockSignals(True)
            self.grid_type_combo.setCurrentText(current_grid_type)
            self.grid_type_combo.blockSignals(False)
            self.grid_type_var = current_grid_type
        
        self.grid_type_combo.currentTextChanged.connect(self._set_step2_grid_type)
        self.grid_type_combo.setStyleSheet(combo_style)
        # 设置尺寸策略，让选择框可以展开
        self.grid_type_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # 设置文本左对齐（延迟设置，确保样式已应用）
        def _set_grid_type_combo_alignment():
            try:
                if hasattr(self.grid_type_combo, 'lineEdit'):
                    line_edit = self.grid_type_combo.lineEdit()
                    if line_edit:
                        line_edit.setAlignment(Qt.AlignmentFlag.AlignLeft)
            except:
                pass
        QtCore.QTimer.singleShot(10, _set_grid_type_combo_alignment)
        grid_type_layout.setColumnStretch(0, 0)
        grid_type_layout.setColumnStretch(1, 1)
        grid_type_layout.addWidget(self.grid_type_combo, 0, 1)
        step2_card_layout.addLayout(grid_type_layout)

        # 从风场文件读取范围按钮
        btn_load_from_nc = PrimaryPushButton(tr("step2_load_from_nc", "从 wind.nc 读取范围"))
        btn_load_from_nc.setStyleSheet(self._get_button_style())
        btn_load_from_nc.clicked.connect(lambda: self.load_latlon_from_nc())
        step2_card_layout.addWidget(btn_load_from_nc)

        # 设置外网格按钮（只在嵌套模式下显示）
        self.btn_setup_outer_grid = PrimaryPushButton(tr("step2_setup_outer_grid", "设置外网格"))
        self.btn_setup_outer_grid.setStyleSheet(self._get_button_style())
        self.btn_setup_outer_grid.clicked.connect(self.setup_outer_grid)
        self.btn_setup_outer_grid.setVisible(False)  # 初始隐藏
        step2_card_layout.addWidget(self.btn_setup_outer_grid)

        # 设置内网格按钮（只在嵌套模式下显示）
        self.btn_setup_inner_grid = PrimaryPushButton(tr("step2_setup_inner_grid", "设置内网格"))
        self.btn_setup_inner_grid.setStyleSheet(self._get_button_style())
        self.btn_setup_inner_grid.clicked.connect(self.setup_inner_grid)
        self.btn_setup_inner_grid.setVisible(False)  # 初始隐藏
        step2_card_layout.addWidget(self.btn_setup_inner_grid)

        # 查看地图按钮
        btn_view_map = PrimaryPushButton(tr("step2_view_map", "查看地图"))
        btn_view_map.setStyleSheet(self._get_button_style())
        btn_view_map.clicked.connect(self.view_region_map)
        step2_card_layout.addWidget(btn_view_map)

        # 生成网格按钮（保存为实例变量，以便后续禁用/启用）
        self.btn_create_grid = PrimaryPushButton(tr("step2_create_grid", "生成网格"))
        self.btn_create_grid.setStyleSheet(self._get_button_style())
        self.btn_create_grid.clicked.connect(self.apply_and_create_grid)
        step2_card_layout.addWidget(self.btn_create_grid)

        # 可视化表格按钮
        self.btn_visualize_grid = PrimaryPushButton(tr("step2_visualize_grid", "网格可视化"))
        self.btn_visualize_grid.setStyleSheet(self._get_button_style())
        self.btn_visualize_grid.clicked.connect(self.visualize_grid_files)
        step2_card_layout.addWidget(self.btn_visualize_grid)

        # 设置内容区内边距
        step2_card.viewLayout.setContentsMargins(11, 10, 11, 12)
        step2_card.viewLayout.addLayout(step2_card_layout)
        content_layout.addWidget(step2_card)

    def _set_step2_grid_type(self, grid_type, skip_block_check=False):
        """设置网格类型选择（第二步UI相关部分）"""
        import os
        from qfluentwidgets import InfoBar
        # 如果存在非强迫场文件，禁止切换网格类型（仅手动切换时）
        if skip_block_check:
            pass
        else:
            try:
                from ..step1.file_path_manager import FilePathManager
                if hasattr(self, "selected_folder") and self.selected_folder and os.path.isdir(self.selected_folder):
                    has_non_forcing = False
                    for name in os.listdir(self.selected_folder):
                        if name.startswith("."):
                            continue
                        path = os.path.join(self.selected_folder, name)
                        if os.path.isdir(path):
                            has_non_forcing = True
                            break
                        if name.endswith(".nc"):
                            fields = FilePathManager.parse_forcing_filename(name)
                            if fields:
                                continue
                        has_non_forcing = True
                        break
                    if has_non_forcing:
                        current_grid = getattr(self, "grid_type_var", None) or self.grid_type_combo.currentText()
                        if current_grid and current_grid != grid_type:
                            self.grid_type_combo.blockSignals(True)
                            self.grid_type_combo.setCurrentText(current_grid)
                            self.grid_type_combo.blockSignals(False)
                            try:
                                InfoBar.warning(
                                    title=tr("tip", "提示"),
                                    content=tr("step2_grid_type_switch_blocked_files", "⚠️ 检测到非强迫场文件，无法切换网格类型"),
                                    duration=3000,
                                    parent=self
                                )
                            except Exception:
                                pass
                            return
            except Exception:
                pass

        # 若目录存在嵌套网格结构，禁止切换到普通网格（仅手动切换时）
        normal_text = tr("step2_grid_type_normal", "普通网格")
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        if not skip_block_check and grid_type == normal_text and hasattr(self, "selected_folder") and self.selected_folder:
            coarse_dir = os.path.join(self.selected_folder, "coarse")
            fine_dir = os.path.join(self.selected_folder, "fine")
            if os.path.isdir(coarse_dir) and os.path.isdir(fine_dir):
                self.grid_type_combo.blockSignals(True)
                self.grid_type_combo.setCurrentText(nested_text)
                self.grid_type_combo.blockSignals(False)
                try:
                    InfoBar.warning(
                        title=tr("tip", "提示"),
                        content=tr("step2_nested_grid_forced", "⚠️ 检测到 coarse 和 fine 文件夹，不能切换为普通网格"),
                        duration=3000,
                        parent=self
                    )
                except Exception:
                    pass
                grid_type = nested_text

        # 更新全局状态
        from ..utils import HomeState
        HomeState.set_grid_type(grid_type)
        # 保持向后兼容，同时设置实例变量
        self.grid_type_var = grid_type
        # 更新第四步的 WAVEWATCH 标签
        self._update_step4_wavewatch_title()
        # 根据选择显示/隐藏内网格参数和调整标题（第二步）
        if grid_type == nested_text:
            self.inner_grid_widget.setVisible(True)
            self.outer_title.setText(tr("step2_outer_params", "外网格参数"))
            self.outer_title_container.setVisible(True)
            # 显示设置外网格和设置内网格按钮
            self.btn_setup_outer_grid.setVisible(True)
            self.btn_setup_inner_grid.setVisible(True)
            
            # 应用默认嵌套外网格 DX 和 DY
            from setting.config import load_config
            config = load_config()
            nested_outer_dx = config.get("NESTED_OUTER_DX", "0.05").strip()
            nested_outer_dy = config.get("NESTED_OUTER_DY", "0.05").strip()
            
            # 格式化 DX 和 DY 为最多2位小数
            try:
                dx_value = float(nested_outer_dx) if nested_outer_dx else 0.05
                dy_value = float(nested_outer_dy) if nested_outer_dy else 0.05
                self.dx_edit.setText(f"{dx_value:.2f}")
                self.dy_edit.setText(f"{dy_value:.2f}")
            except (ValueError, TypeError):
                # 如果转换失败，使用默认值
                self.dx_edit.setText("0.05")
                self.dy_edit.setText("0.05")
        else:
            self.inner_grid_widget.setVisible(False)
            # 当选择普通网格时，隐藏"外网格参数"标题
            self.outer_title_container.setVisible(False)
            # 隐藏设置外网格和设置内网格按钮
            self.btn_setup_outer_grid.setVisible(False)
            self.btn_setup_inner_grid.setVisible(False)
    
    def _update_step4_wavewatch_title(self):
        """更新第四步的 WAVEWATCH 标签文本"""
        if hasattr(self, '_update_wavewatch_title'):
            self._update_wavewatch_title()
