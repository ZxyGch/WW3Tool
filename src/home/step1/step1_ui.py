"""
第一步：选择强迫场文件模块
包含UI创建（函数逻辑已拆分到 function.py）
"""
from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QGridLayout
from qfluentwidgets import PrimaryPushButton
from setting.language_manager import tr
from .function import StepOneFunctionsMixin
from ..utils import create_header_card


class HomeStepOneCard(StepOneFunctionsMixin):
    """第一步：选择强迫场文件 Mixin"""

    def _create_field_button_pair(self, grid_layout, row, label_text, button_attr_name, button_text, click_handler):
        """
        创建字段按钮对（标签 + 按钮）
        
        参数:
            grid_layout: 网格布局对象
            row: 行号
            label_text: 标签文本
            button_attr_name: 按钮属性名（如 'btn_choose_wind_file'）
            button_text: 按钮文本
            click_handler: 点击处理函数
        """
        # 创建标签
        label = QLabel(label_text)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.setStyleSheet("padding-right: 0px;")
        
        # 创建按钮
        button = PrimaryPushButton(button_text)
        button.setStyleSheet(self._get_button_style())
        button.clicked.connect(click_handler)
        button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                            QtWidgets.QSizePolicy.Policy.Fixed)
        
        # 添加到布局
        grid_layout.addWidget(label, row, 0)
        grid_layout.addWidget(button, row, 1)
        
        # 保存按钮引用到实例
        setattr(self, button_attr_name, button)

    def create_step_1_card(self, content_widget, content_layout):
        """创建第一步：选择强迫场文件的UI"""
        # 使用通用函数创建卡片（第一步需要额外的 QVBoxLayout 样式）
        step1_card, step1_card_layout = create_header_card(
            content_widget,
            tr("step1_title", "第一步：选择风场文件"),
            include_vbox_style=True
        )

        # 使用网格布局确保按钮左对齐
        fields_grid = QtWidgets.QGridLayout()
        fields_grid.setSpacing(10)
        fields_grid.setColumnStretch(1, 1)  # 第二列（按钮列）可拉伸

        # 使用通用方法创建所有字段按钮
        self._create_field_button_pair(
            fields_grid, 0,
            tr("step1_label_wind", "风场："),
            "btn_choose_wind_file",
            tr("step1_choose_wind", "选择风场"),
            lambda: self.choose_wind_field_file()
        )
        
        self._create_field_button_pair(
            fields_grid, 1,
            tr("step1_label_current", "流场："),
            "btn_choose_current_file",
            tr("step1_choose_current", "选择流场"),
            lambda: self.choose_current_field_file()
        )
        
        self._create_field_button_pair(
            fields_grid, 2,
            tr("step1_label_level", "水位场："),
            "btn_choose_level_file",
            tr("step1_choose_level", "选择水位场"),
            lambda: self.choose_level_field_file()
        )
        
        self._create_field_button_pair(
            fields_grid, 3,
            tr("step1_label_ice", "海冰场："),
            "btn_choose_ice_file_home",
            tr("step1_choose_ice", "选择海冰场"),
            lambda: self.choose_ice_field_file()
        )

        step1_card_layout.addLayout(fields_grid)

        # 查看所有场文件信息按钮
        self.btn_view_field_files_info = PrimaryPushButton(tr("step1_view_field_files_info", "查看所有场文件信息"))
        self.btn_view_field_files_info.setStyleSheet(self._get_button_style())
        self.btn_view_field_files_info.clicked.connect(lambda: self.view_all_field_files_info())
        step1_card_layout.addWidget(self.btn_view_field_files_info)

        # 添加布局到第一步内容区
        step1_card.viewLayout.setContentsMargins(11, 10, 11, 12)

        step1_card.viewLayout.addLayout(step1_card_layout)
        content_layout.addWidget(step1_card)

        # _detect_and_fill_forcing_fields 不在此处调用：create_step_1_card 在 MainWindow.__init__ 中执行，
        # 此时 selected_folder 尚为空，函数会直接 return。检测由 main.py（启动选完目录后）和
        # window_navigation（打开/选择工作目录时）在设置 selected_folder 之后调用。
