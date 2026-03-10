"""
第三步：计算模式模块 - UI部分
包含UI创建（计算模式选择、谱空间逐点计算点位表格、航迹模式点位表格等）
"""
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QLabel, QVBoxLayout, QHBoxLayout, QGridLayout,
    QWidget, QSizePolicy, QTableWidgetItem, QHeaderView, QScrollArea,
)
from qfluentwidgets import PrimaryPushButton, ComboBox, TableWidget, InfoBar
from setting.language_manager import tr
from ..utils import create_header_card
from .step3_service import StepThreeServiceMixin


class HomeStepThreeCard(StepThreeServiceMixin):
    """第三步：计算模式 Mixin"""

    def create_step_3_card(self, content_widget, content_layout):
        """创建第三步：计算模式的 UI"""
        # 使用通用函数创建卡片
        step3_calc_mode_card, step3_calc_mode_card_layout = create_header_card(
            content_widget,
            tr("step3_title", "第三步：计算模式")
        )

        combo_style = self._get_combo_style()
        calc_mode_grid = QGridLayout()
        calc_mode_grid.setSpacing(10)
        calc_mode_grid.setColumnStretch(0, 0)
        calc_mode_grid.setColumnStretch(1, 1)

        calc_mode_label = QLabel(tr("step3_calc_mode", "计算模式："))
        calc_mode_grid.addWidget(calc_mode_label, 0, 0)
        self.calc_mode_combo = ComboBox()
        self.calc_mode_combo.addItems([
            tr("step3_region_scale", "区域尺度计算"),
            tr("step3_spectral_point", "谱空间逐点计算"),
            tr("step3_track_mode", "航迹模式")
        ])
        self.calc_mode_combo.setCurrentText(tr("step3_region_scale", "区域尺度计算"))
        self.calc_mode_var = tr("step3_region_scale", "区域尺度计算")
        self.calc_mode_combo.currentTextChanged.connect(self._set_calc_mode)
        self.calc_mode_combo.setStyleSheet(combo_style)

        def _set_calc_mode_combo_alignment():
            try:
                if hasattr(self.calc_mode_combo, 'lineEdit'):
                    line_edit = self.calc_mode_combo.lineEdit()
                    if line_edit:
                        line_edit.setAlignment(Qt.AlignmentFlag.AlignLeft)
            except Exception:
                pass
        QtCore.QTimer.singleShot(10, _set_calc_mode_combo_alignment)
        calc_mode_grid.addWidget(self.calc_mode_combo, 0, 1)
        step3_calc_mode_card_layout.addLayout(calc_mode_grid)

        self.spectral_points_widget = QWidget()
        self.spectral_points_widget.setContentsMargins(0, 0, 0, 0)
        spectral_points_layout = QVBoxLayout()
        spectral_points_layout.setContentsMargins(0, 0, 0, 0)

        self.spectral_points_table = TableWidget()
        self.spectral_points_table.setContentsMargins(0, 0, 0, 0)
        self.spectral_points_table.setColumnCount(3)
        self.spectral_points_table.horizontalHeader().setVisible(False)
        header = self.spectral_points_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.spectral_points_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.spectral_points_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.spectral_points_table.setBorderVisible(False)
        self.spectral_points_table.setWordWrap(False)
        self.spectral_points_table.verticalHeader().setVisible(False)

        self.spectral_points_table.insertRow(0)
        header_lon_item = QTableWidgetItem(tr("step3_longitude", "经度"))
        header_lon_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        header_lat_item = QTableWidgetItem(tr("step3_latitude", "纬度"))
        header_lat_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)
        header_name_item = QTableWidgetItem(tr("step3_name", "名称"))
        header_name_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)
        header_lon_item.setData(QtCore.Qt.ItemDataRole.UserRole, "header")
        header_lat_item.setData(QtCore.Qt.ItemDataRole.UserRole, "header")
        header_name_item.setData(QtCore.Qt.ItemDataRole.UserRole, "header")
        self.spectral_points_table.setItem(0, 0, header_lon_item)
        self.spectral_points_table.setItem(0, 1, header_lat_item)
        self.spectral_points_table.setItem(0, 2, header_name_item)

        row_count = self.spectral_points_table.rowCount()
        vertical_header = self.spectral_points_table.verticalHeader()
        vertical_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.spectral_points_table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        if row_count > 0:
            self.spectral_points_table.resizeRowsToContents()
            total_height = sum(self.spectral_points_table.rowHeight(i) for i in range(row_count))
            content_height = max(200, total_height + 20)
        else:
            content_height = 200
        self.spectral_points_table.setMinimumHeight(content_height)
        self.spectral_points_table.setMaximumHeight(16777215)
        self.spectral_points_table.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred))
        spectral_points_layout.addWidget(self.spectral_points_table)

        button_style = self._get_button_style()
        spectral_points_buttons_layout = QHBoxLayout()
        spectral_points_buttons_layout.setSpacing(10)
        btn_add_point = PrimaryPushButton(tr("new", "新增"))
        btn_add_point.setStyleSheet(button_style)
        btn_add_point.clicked.connect(self._add_spectral_point)
        spectral_points_buttons_layout.addWidget(btn_add_point, 1)
        btn_edit_point = PrimaryPushButton(tr("edit", "修改"))
        btn_edit_point.setStyleSheet(button_style)
        btn_edit_point.clicked.connect(self._edit_spectral_point)
        spectral_points_buttons_layout.addWidget(btn_edit_point, 1)
        btn_delete_point = PrimaryPushButton(tr("delete", "删除"))
        btn_delete_point.setStyleSheet(button_style)
        btn_delete_point.clicked.connect(self._delete_spectral_point)
        spectral_points_buttons_layout.addWidget(btn_delete_point, 1)
        spectral_points_layout.addLayout(spectral_points_buttons_layout)
        btn_select_points = PrimaryPushButton(tr("step3_select_on_map", "在地图上选点"))
        btn_select_points.setStyleSheet(button_style)
        btn_select_points.clicked.connect(self._select_points_on_map)
        spectral_points_layout.addWidget(btn_select_points)
        btn_import_points = PrimaryPushButton(tr("step3_import_points", "从 points.list 导入"))
        btn_import_points.setStyleSheet(button_style)
        btn_import_points.clicked.connect(self._import_points_from_file)
        spectral_points_layout.addWidget(btn_import_points)
        self.spectral_points_widget.setLayout(spectral_points_layout)
        self.spectral_points_widget.setVisible(False)
        step3_calc_mode_card_layout.addWidget(self.spectral_points_widget)

        self.track_points_widget = QWidget()
        self.track_points_widget.setContentsMargins(0, 0, 0, 0)
        track_points_layout = QVBoxLayout()
        track_points_layout.setContentsMargins(0, 0, 0, 0)

        self.track_points_table = TableWidget()
        self.track_points_table.setContentsMargins(0, 0, 0, 0)
        self.track_points_table.setColumnCount(4)
        self.track_points_table.horizontalHeader().setVisible(False)
        track_header = self.track_points_table.horizontalHeader()
        track_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        track_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        track_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        track_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.track_points_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.track_points_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.track_points_table.setBorderVisible(False)
        self.track_points_table.setWordWrap(False)
        self.track_points_table.verticalHeader().setVisible(False)

        self.track_points_table.insertRow(0)
        track_header_time_item = QTableWidgetItem(tr("step3_time", "时间"))
        track_header_time_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        track_header_lon_item = QTableWidgetItem(tr("step3_longitude", "经度"))
        track_header_lon_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        track_header_lat_item = QTableWidgetItem(tr("step3_latitude", "纬度"))
        track_header_lat_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        track_header_name_item = QTableWidgetItem(tr("step3_name", "名称"))
        track_header_name_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        track_header_time_item.setData(QtCore.Qt.ItemDataRole.UserRole, "header")
        track_header_lon_item.setData(QtCore.Qt.ItemDataRole.UserRole, "header")
        track_header_lat_item.setData(QtCore.Qt.ItemDataRole.UserRole, "header")
        track_header_name_item.setData(QtCore.Qt.ItemDataRole.UserRole, "header")
        self.track_points_table.setItem(0, 0, track_header_time_item)
        self.track_points_table.setItem(0, 1, track_header_lon_item)
        self.track_points_table.setItem(0, 2, track_header_lat_item)
        self.track_points_table.setItem(0, 3, track_header_name_item)

        track_row_count = self.track_points_table.rowCount()
        track_vertical_header = self.track_points_table.verticalHeader()
        track_vertical_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.track_points_table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        if track_row_count > 0:
            self.track_points_table.resizeRowsToContents()
            track_total_height = sum(self.track_points_table.rowHeight(i) for i in range(track_row_count))
            track_content_height = max(200, track_total_height + 20)
        else:
            track_content_height = 200
        self.track_points_table.setMinimumHeight(track_content_height)
        self.track_points_table.setMaximumHeight(16777215)
        self.track_points_table.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred))
        track_points_layout.addWidget(self.track_points_table)

        track_points_buttons_layout = QHBoxLayout()
        track_points_buttons_layout.setSpacing(10)
        btn_add_track_point = PrimaryPushButton(tr("new", "新增"))
        btn_add_track_point.setStyleSheet(button_style)
        btn_add_track_point.clicked.connect(self._add_track_point)
        track_points_buttons_layout.addWidget(btn_add_track_point, 1)
        btn_edit_track_point = PrimaryPushButton(tr("edit", "修改"))
        btn_edit_track_point.setStyleSheet(button_style)
        btn_edit_track_point.clicked.connect(self._edit_track_point)
        track_points_buttons_layout.addWidget(btn_edit_track_point, 1)
        btn_delete_track_point = PrimaryPushButton(tr("delete", "删除"))
        btn_delete_track_point.setStyleSheet(button_style)
        btn_delete_track_point.clicked.connect(self._delete_track_point)
        track_points_buttons_layout.addWidget(btn_delete_track_point, 1)
        track_points_layout.addLayout(track_points_buttons_layout)
        btn_select_track_points = PrimaryPushButton(tr("step3_select_on_map", "在地图上选点"))
        btn_select_track_points.setStyleSheet(button_style)
        btn_select_track_points.clicked.connect(self._select_track_points_on_map)
        track_points_layout.addWidget(btn_select_track_points)
        btn_import_track_file = PrimaryPushButton(tr("step3_import_track_file", "从 track_i.ww3 读取"))
        btn_import_track_file.setStyleSheet(button_style)
        btn_import_track_file.clicked.connect(self._import_track_from_file_dialog)
        track_points_layout.addWidget(btn_import_track_file)
        self.track_points_widget.setLayout(track_points_layout)
        self.track_points_widget.setVisible(False)
        step3_calc_mode_card_layout.addWidget(self.track_points_widget)

        step3_calc_mode_card.viewLayout.setContentsMargins(11, 10, 11, 12)
        step3_calc_mode_card.viewLayout.addLayout(step3_calc_mode_card_layout)
        content_layout.addWidget(step3_calc_mode_card)

    def _set_calc_mode(self, calc_mode, skip_block_check=False):
        """设置计算模式
        Args:
            calc_mode: 计算模式文本
            skip_block_check: 是否跳过阻止检查（用于自动切换时）
        """
        if not skip_block_check and self._should_block_calc_mode_switch():
            if hasattr(self, 'calc_mode_combo') and hasattr(self, 'calc_mode_var'):
                self.calc_mode_combo.blockSignals(True)
                self.calc_mode_combo.setCurrentText(self.calc_mode_var)
                self.calc_mode_combo.blockSignals(False)
                if hasattr(self, 'log'):
                    InfoBar.warning(
                            title="",
                            content=tr("calc_mode_switch_blocked", "检测到 track_i.ww3 或 points.list 文件，不允许切换计算模式"),
                            duration=3000,
                            parent=self
                        )
            return

        self.calc_mode_var = calc_mode
        spectral_text = tr("step3_spectral_point", "谱空间逐点计算")
        track_text = tr("step3_track_mode", "航迹模式")
        if hasattr(self, 'spectral_points_widget'):
            if calc_mode == spectral_text or calc_mode == "谱空间逐点计算":
                self.spectral_points_widget.setVisible(True)
            else:
                self.spectral_points_widget.setVisible(False)

        if hasattr(self, 'track_points_widget'):
            if calc_mode == track_text or calc_mode == "航迹模式":
                self.track_points_widget.setVisible(True)
                if hasattr(self, '_import_track_from_file') and hasattr(self, 'selected_folder') and self.selected_folder:
                    if not hasattr(self, '_track_file_auto_imported'):
                        def auto_import():
                            if hasattr(self, 'track_points_table'):
                                self._import_track_from_file("")
                                self._track_file_auto_imported = True
                        QtCore.QTimer.singleShot(500, auto_import)
            else:
                self.track_points_widget.setVisible(False)
                if hasattr(self, '_track_file_auto_imported'):
                    self._track_file_auto_imported = False
