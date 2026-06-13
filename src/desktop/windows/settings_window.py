"""设置子界面：编辑根目录 ``params.yml``（desktop 段 + 管线参数）与非结构/SMC 网格 JSON。

迁移自 src 设置页的核心配置卡 + ST 版本管理 + 谱分区输出方案（输出变量方案）编辑器。
持久化全部经 :class:`desktop.view_models.settings.SettingsViewModel`（转调 runtime_config）。
不含服务器 SSH、参考数据在线下载。
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CheckBox,
    ComboBox,
    InfoBar,
    LineEdit,
    MessageBoxBase,
    PrimaryPushButton,
    SwitchButton,
    TableWidget,
    TextEdit,
)

from ..components.combo_box import left_align_combo_text
from ..components.header_card import create_header_card
from ..components import styles
from ..components.validators import double_validator, int_validator
from ..view_models.settings import SettingsViewModel
from workflows.infrastructure.runtime_config import (
    RUN_MODE_VALUES,
    normalize_run_mode,
    smc_bathymetry_relpath_for_combo_index,
)
from workflows.support.translations import tr

# 谱分区输出方案的候选变量（取自 params.yml all_fields 全集）。
_OUTPUT_VAR_CODES = [
    "DPT", "CUR", "WND", "AST", "WLV", "ICE", "IBG", "D50", "IC1", "IC5",
    "HS", "LM", "T02", "T0M1", "T01", "FP", "DIR", "SPR", "DP", "HIG",
    "EF", "TH1M", "STH1M", "TH2M", "STH2M", "WN",
    "PHS", "PTP", "PLP", "PDIR", "PSPR", "PWS", "PDP", "PQP", "PPE", "PGW",
    "PSW", "PTM10", "PT01", "PT02", "PEP", "TWS", "PNR",
    "UST", "CHA", "CGE", "FAW", "TAW", "TWA", "WCC", "WCF", "WCH", "WCM", "FWS",
    "SXY", "TWO", "BHD", "FOC", "TUS", "USS", "P2S", "USF", "P2L", "TWI", "FIC", "USP", "TOC",
    "ABR", "UBR", "BED", "FBB", "TBB", "MSS", "MSC", "MSD", "MCD", "QP", "QKK", "SKW", "EMB",
    "DTD", "FC", "CFX", "CFD", "CFK",
]

_OUTPUT_VAR_LABELS = {
    "DPT": "水深 (DPT)",
    "CUR": "流速 (CUR)",
    "WND": "风速 (WND)",
    "AST": "海气温差 (AST)",
    "WLV": "水位 (WLV)",
    "ICE": "冰浓度 (ICE)",
    "IBG": "冰山阻尼 (IBG)",
    "D50": "中值沉积物粒度 (D50)",
    "IC1": "冰厚度 (IC1)",
    "IC5": "浮冰直径 (IC5)",
    "HS": "有效波高 (HS)",
    "LM": "平均波长 (LM)",
    "T02": "平均波周期 Tm0,2 (T02)",
    "T0M1": "平均波周期 Tm-1,0 (T0M1)",
    "T01": "平均波周期 Tm0,1 (T01)",
    "FP": "峰值频率 (FP)",
    "DIR": "平均波向 (DIR)",
    "SPR": "方向扩展 (SPR)",
    "DP": "峰值方向 (DP)",
    "HIG": "次重力波高 (HIG)",
    "EF": "波频率谱 (EF)",
    "TH1M": "平均波向 a1,b2 (TH1M)",
    "STH1M": "方向扩展 a1,b2 (STH1M)",
    "TH2M": "平均波向 a2,b2 (TH2M)",
    "STH2M": "方向扩展 a2,b2 (STH2M)",
    "WN": "波数 (WN)",
    "PHS": "分区波高 (PHS)",
    "PTP": "分区峰值周期 (PTP)",
    "PLP": "分区峰值波长 (PLP)",
    "PDIR": "分区平均方向 (PDIR)",
    "PSPR": "分区方向扩展 (PSPR)",
    "PWS": "分区风海分数 (PWS)",
    "PDP": "分区峰值方向 (PDP)",
    "PQP": "分区Goda峰值参数 (PQP)",
    "PPE": "分区JONSWAP峰值增强因子 (PPE)",
    "PGW": "分区高斯频率宽度 (PGW)",
    "PSW": "分区谱宽度 (PSW)",
    "PTM10": "分区平均波周期 Tm-1,0 (PTM10)",
    "PT01": "分区平均波周期 Tm0,1 (PT01)",
    "PT02": "分区平均波周期 Tm0,2 (PT02)",
    "PEP": "分区峰值谱密度 (PEP)",
    "TWS": "总风海分数 (TWS)",
    "PNR": "分区数量 (PNR)",
    "UST": "摩擦速度 (UST)",
    "CHA": "Charnock参数 (CHA)",
    "CGE": "能量通量 (CGE)",
    "FAW": "海气能量通量 (FAW)",
    "TAW": "净波浪支撑应力 (TAW)",
    "TWA": "波浪支撑应力负值部分 (TWA)",
    "WCC": "白帽覆盖率 (WCC)",
    "WCF": "白帽厚度 (WCF)",
    "WCH": "平均破碎高度 (WCH)",
    "WCM": "白帽矩 (WCM)",
    "FWS": "风海平均周期 (FWS)",
    "SXY": "辐射应力 (SXY)",
    "TWO": "波浪到海洋动量通量 (TWO)",
    "BHD": "Bernoulli头 J项 (BHD)",
    "FOC": "波浪到海洋能量通量 (FOC)",
    "TUS": "Stokes输运 (TUS)",
    "USS": "表面Stokes漂移 (USS)",
    "P2S": "二阶和压力 (P2S)",
    "USF": "表面Stokes漂移谱 (USF)",
    "P2L": "微地震源项 (P2L)",
    "TWI": "波浪到海冰应力 (TWI)",
    "FIC": "波浪到海冰能量通量 (FIC)",
    "USP": "分区表面Stokes漂移 (USP)",
    "TOC": "到海洋总动量 (TOC)",
    "ABR": "近底均方根振幅 (ABR)",
    "UBR": "近底均方根流速 (UBR)",
    "BED": "底形形态 (BED)",
    "FBB": "底摩擦能量通量 (FBB)",
    "TBB": "底摩擦动量通量 (TBB)",
    "MSS": "均方斜率 (MSS)",
    "MSC": "高频尾谱水平 (MSC)",
    "MSD": "斜率方向 (MSD)",
    "MCD": "尾部斜率方向 (MCD)",
    "QP": "Goda峰值参数 (QP)",
    "QKK": "波数 peakedness (QKK)",
    "SKW": "零斜率偏度 (SKW)",
    "EMB": "零斜率平均海面 (EMB)",
    "DTD": "平均积分步长 (DTD)",
    "FC": "截止频率 (FC)",
    "CFX": "空间平流最大CFL数 (CFX)",
    "CFD": "方向平流最大CFL数 (CFD)",
    "CFK": "波数平流最大CFL数 (CFK)",
}

_INTEGER_CONFIG_KEYS = {
    "FREQ_NUM",
    "DIR_NUM",
    "DTMAX",
    "DTXY",
    "DTKTH",
    "DTMIN",
    "KERNEL_NUM",
    "NODE_NUM",
    "COMPUTE_PRECISION",
    "OUTPUT_PRECISION",
    "SERVER_PORT",
}

_NUMERIC_CONFIG_KEYS = {
    "DX",
    "DY",
    "NESTED_CONTRACTION_COEFFICIENT",
    "NESTED_OUTER_DX",
    "NESTED_OUTER_DY",
    "MIN_DIST",
    "CUT_OFF",
    "LIM_BATHY",
    "LIM_VAL",
    "SPLIT_LIM",
    "LAKE_TOL",
    "FREQ_INC",
    "FREQ_START",
}

_INTEGER_DOTTED_KEYS = {
    "spacing.nwav",
    "regional.edge_segments",
    "grid.n_levels",
    "boundary.msea",
}

_NUMERIC_DOTTED_KEYS = {
    "spacing.hmax",
    "spacing.hshr",
    "spacing.dhdx",
    "spacing.deep_ocean_threshold_m",
    "regional.margin_deg",
    "physics.wlevel",
    "physics.depmin",
    "physics.dshalw",
}


def _file_split_items() -> list[tuple[str, str]]:
    return [
        (tr("file_split_none", "无日期"), "none"),
        (tr("file_split_hour", "小时"), "hour"),
        (tr("file_split_day", "天"), "day"),
        (tr("file_split_month", "月"), "month"),
        (tr("file_split_year", "年"), "year"),
    ]


class _NoHScrollArea(QScrollArea):
    """QScrollArea that completely disables horizontal scrolling."""

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: N802
        super().scrollContentsBy(0, dy)

    def horizontalScrollBar(self):
        bar = super().horizontalScrollBar()
        bar.setRange(0, 0)
        return bar


class SettingsInterface(QWidget):
    """设置页主界面（作为 FluentWindow 子界面）。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        view_model: SettingsViewModel | None = None,
        on_language_changed: Callable[[str], None] | None = None,
        on_run_mode_changed: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("settings_interface")
        self._vm = view_model or SettingsViewModel()
        self._on_language_changed_callback = on_language_changed
        self._on_run_mode_changed_callback = on_run_mode_changed
        self._config = self._vm.load()
        self._fields: dict[str, LineEdit] = {}
        self._combos: dict[str, ComboBox] = {}
        self._checks: dict[str, QWidget] = {}
        self._unst_fields: dict[str, LineEdit] = {}
        self._smc_fields: dict[str, QWidget] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = _NoHScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._content = QWidget()
        self._content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._content.setStyleSheet("QWidget { background: transparent; }")
        self._vbox = QVBoxLayout(self._content)
        self._vbox.setContentsMargins(0, 0, 0, 10)
        self._vbox.setSpacing(15)
        scroll.setWidget(self._content)
        outer.addWidget(scroll)

        self._build_interface_card()
        self._build_forcing_card()
        self._build_paths_card()
        self._build_gridgen_card()
        self._build_unst_card()
        self._build_smc_card()
        self._build_slurm_card()
        self._build_ww3_card()
        self._build_spectrum_card()
        self._build_timesteps_card()
        self._build_scheme_card()
        self._build_server_card()
        self._build_st_card()

        self._vbox.addStretch(1)
        self._wire_autosave()

    # ── 通用卡片/字段构建 ─────────────────────────────────────────────────────

    def _card_layout(self, title: str, *, spacing: int = 5):
        group, layout = create_header_card(self._content, title)
        layout.setSpacing(spacing)
        group.viewLayout.setContentsMargins(11, 10, 11, 12)
        group.viewLayout.addLayout(layout)
        self._vbox.addWidget(group)
        return group, layout

    def _card(self, title: str) -> QGridLayout:
        _group, layout = self._card_layout(title)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(5)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 1)
        layout.addLayout(grid)
        return grid

    def _expand_field(self, widget: QWidget) -> None:
        widget.setMinimumWidth(0)
        widget.setMaximumWidth(16777215)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _control_span(self, col: int) -> int:
        return 3 if col == 0 else 1

    def _text(self, grid: QGridLayout, row: int, col: int, label: str, key: str, store: dict | None = None) -> None:
        edit = LineEdit()
        edit.setStyleSheet(styles.input_style())
        _apply_validator(edit, key)
        edit.setText(_as_text((store or self._config).get(key) if store is None else self._nested(store, key)))
        self._expand_field(edit)
        grid.addWidget(self._label(label), row, col)
        grid.addWidget(edit, row, col + 1, 1, self._control_span(col))
        (self._fields if store is None else store)[key] = edit

    def _combo(self, grid: QGridLayout, row: int, col: int, label: str, key: str, options: list[str | tuple[str, str]]) -> None:
        combo = ComboBox()
        for option in options:
            if isinstance(option, tuple):
                combo.addItem(option[0], option[1])
            else:
                combo.addItem(option)
        combo.setStyleSheet(styles.combo_style())
        left_align_combo_text(combo)
        value = _as_text(self._config.get(key))
        selected_index = -1
        for index in range(combo.count()):
            if combo.itemData(index) == value or combo.itemText(index) == value:
                selected_index = index
                break
        if value and selected_index < 0:
            combo.addItem(value)
            selected_index = combo.count() - 1
        if selected_index >= 0:
            combo.setCurrentIndex(selected_index)
        elif combo.count():
            combo.setCurrentIndex(0)
        self._expand_field(combo)
        grid.addWidget(self._label(label), row, col)
        grid.addWidget(combo, row, col + 1, 1, self._control_span(col))
        self._combos[key] = combo

    def _check(self, grid: QGridLayout, row: int, col: int, label: str, key: str) -> None:
        check = CheckBox(label)
        check.setChecked(bool(self._config.get(key, False)))
        grid.addWidget(check, row, col, 1, 2)
        self._checks[key] = check

    def _make_switch(self) -> SwitchButton:
        switch = SwitchButton()
        switch.setSpacing(0)
        switch.setOnText("")
        switch.setOffText("")
        switch.setStyleSheet("SwitchButton { margin: 0px; padding: 0px; }")
        return switch

    def _switch_row(self, grid: QGridLayout, row: int, label: str) -> SwitchButton:
        """标签居左、开关靠右，占满整行。"""
        switch = self._make_switch()
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        row_layout.addWidget(self._label(label))
        row_layout.addStretch(1)
        row_layout.addWidget(switch)
        grid.addWidget(row_widget, row, 0, 1, 4)
        return switch

    def _step4_toggle(self, grid: QGridLayout, row: int, key: str) -> None:
        """“是否在第四步显示该分组”开关；与其它设置一样即时落盘。"""
        switch = self._switch_row(grid, row, tr("set_show_in_step4", "在第四步显示："))
        switch.setChecked(bool(self._config.get(key, False)))
        self._checks[key] = switch

    def _browse(self, grid: QGridLayout, row: int, label: str, key: str, *, directory: bool, readonly: bool = False, button_text: str | None = None) -> None:
        button_text = button_text or tr("select", "选择")
        edit = LineEdit()
        edit.setStyleSheet(styles.input_style())
        edit.setText(_as_text(self._config.get(key)))
        edit.setReadOnly(readonly)
        self._expand_field(edit)
        button = PrimaryPushButton(button_text)
        button.setStyleSheet(styles.button_style())
        button.clicked.connect(lambda: self._pick_path(edit, directory))
        grid.addWidget(self._label(label), row, 0)
        grid.addWidget(edit, row, 1, 1, 2)
        grid.addWidget(button, row, 3)
        self._fields[key] = edit

    def _label(self, text: str, *, word_wrap: bool = True) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(word_wrap)
        label.setMinimumHeight(28)
        policy = QSizePolicy.Policy.Preferred if word_wrap else QSizePolicy.Policy.Fixed
        label.setSizePolicy(QSizePolicy.Policy.Minimum, policy)
        return label

    def _path_field(
        self,
        layout: QVBoxLayout,
        label: str,
        key: str,
        *,
        directory: bool,
        readonly: bool = False,
        button_text: str | None = None,
        placeholder: str = "",
        open_existing: bool = False,
    ) -> None:
        button_text = button_text or tr("select", "选择")
        layout.addWidget(self._label(label))
        row = QHBoxLayout()
        row.setSpacing(8)
        row.setContentsMargins(0, 0, 0, 0)
        edit = LineEdit()
        edit.setStyleSheet(styles.input_style())
        edit.setReadOnly(readonly)
        self._expand_field(edit)
        if placeholder:
            edit.setPlaceholderText(placeholder)
        edit.setText(_as_text(self._config.get(key)))
        button = PrimaryPushButton(button_text)
        button.setStyleSheet(styles.button_style())
        if open_existing:
            button.clicked.connect(lambda: self._open_path(edit))
        else:
            button.clicked.connect(lambda: self._pick_path(edit, directory))
        row.addWidget(edit, 1)
        row.addWidget(button)
        layout.addLayout(row)
        self._fields[key] = edit

    def _pick_path(self, edit: LineEdit, directory: bool) -> None:
        start = edit.text().strip() or str(__import__("pathlib").Path.home())
        if directory:
            picked = QFileDialog.getExistingDirectory(self, tr("select_dir_dialog", "选择目录"), start)
        else:
            picked, _ = QFileDialog.getOpenFileName(self, tr("select_file", "选择文件"), start)
        if picked:
            edit.setText(picked)
            self._save_config_now()

    def _open_path(self, edit: LineEdit) -> None:
        path = edit.text().strip()
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ── 各卡片 ────────────────────────────────────────────────────────────────

    def _build_interface_card(self) -> None:
        grid = self._card(tr("interface_settings", "界面设置"))
        self._combo(grid, 0, 0, tr("language_select", "语言:"), "LANGUAGE", ["zh_CN", "en_US"])
        self._build_run_mode_combo(grid, 1, 0)
        self._combos["LANGUAGE"].currentTextChanged.connect(self._on_language_changed)

    def _build_run_mode_combo(self, grid: QGridLayout, row: int, col: int) -> None:
        combo = ComboBox()
        for label_key, default, value in (
            ("run_mode_local", "本地运行", "local"),
            ("run_mode_server", "服务器运行", "server"),
            ("run_mode_both", "本地+服务器运行", "both"),
        ):
            combo.addItem(tr(label_key, default))
            combo.setItemData(combo.count() - 1, value)
        combo.setStyleSheet(styles.combo_style())
        left_align_combo_text(combo)
        run_mode = normalize_run_mode(self._config.get("RUN_MODE", "both"))
        selected = -1
        for index in range(combo.count()):
            if str(combo.itemData(index)) == run_mode:
                selected = index
                break
        combo.blockSignals(True)
        combo.setCurrentIndex(selected if selected >= 0 else len(RUN_MODE_VALUES) - 1)
        combo.blockSignals(False)
        self._expand_field(combo)
        grid.addWidget(self._label(tr("run_mode_select", "运行方式:")), row, col)
        grid.addWidget(combo, row, col + 1, 1, self._control_span(col))
        self._combos["RUN_MODE"] = combo
        combo.currentIndexChanged.connect(self._on_run_mode_changed)

    def _run_mode_from_combo(self, combo: ComboBox) -> str | None:
        data = combo.currentData()
        if data is not None:
            mode = normalize_run_mode(data, default="")
            if mode:
                return mode
        index = combo.currentIndex()
        if 0 <= index < len(RUN_MODE_VALUES):
            return RUN_MODE_VALUES[index]
        return None

    def _build_forcing_card(self) -> None:
        _group, layout = self._card_layout(tr("forcing_field_settings", "强迫场选择"))
        auto_row = QHBoxLayout()
        auto_row.setContentsMargins(0, 0, 0, 0)
        auto_row.setSpacing(8)
        auto_row.addWidget(self._label(tr("set_auto_associate", "自动关联场：")))
        auto_row.addStretch(1)
        auto_switch = self._make_switch()
        auto_switch.setChecked(bool(self._config.get("FORCING_FIELD_AUTO_ASSOCIATE", True)))
        auto_row.addWidget(auto_switch)
        layout.addLayout(auto_row)
        self._checks["FORCING_FIELD_AUTO_ASSOCIATE"] = auto_switch

        process_row = QHBoxLayout()
        process_row.setContentsMargins(0, 0, 0, 0)
        process_row.setSpacing(8)
        process_row.addWidget(self._label(tr("set_process_mode_label", "文件处理方式：")))
        process_combo = ComboBox()
        process_combo.addItem(tr("copy", "复制"), "copy")
        process_combo.addItem(tr("move", "剪切"), "move")
        process_combo.setStyleSheet(styles.combo_style())
        left_align_combo_text(process_combo)
        self._expand_field(process_combo)
        mode = _as_text(self._config.get("FORCING_FIELD_FILE_PROCESS_MODE")) or "copy"
        process_combo.setCurrentIndex(1 if mode == "move" else 0)
        process_row.addWidget(process_combo, 1)
        layout.addLayout(process_row)
        self._combos["FORCING_FIELD_FILE_PROCESS_MODE"] = process_combo

    def _build_paths_card(self) -> None:
        _group, layout = self._card_layout(tr("path_settings", "路径设置"))
        self._path_field(
            layout,
            tr("set_reference_data_label", "Reference Data 路径："),
            "REFERENCE_DATA_PATH",
            directory=True,
            placeholder=tr("set_reference_data_ph", "默认路径：WW3Tool/WW3-Grid-Generator/reference_data"),
        )
        self._path_field(
            layout,
            tr("set_workdir_label", "工作目录："),
            "DEFAULT_WORKDIR",
            directory=True,
            placeholder=tr("set_workdir_ph", "默认路径：WW3Tool/workSpace"),
        )
        self._path_field(
            layout,
            tr("set_forcing_dir_label", "打开的强迫场文件目录："),
            "FORCING_FIELD_DIR_PATH",
            directory=True,
            placeholder=tr("set_forcing_dir_ph", "默认路径：WW3Tool/public/forcing"),
        )
        self._path_field(
            layout,
            tr("set_ww3_config_label", "WW3 配置文件："),
            "WW3_CONFIG_PATH",
            directory=True,
            readonly=True,
            button_text=tr("open", "打开"),
            placeholder=tr("set_ww3_config_ph", "默认路径：WW3Tool/public/ww3"),
            open_existing=True,
        )
        self._path_field(
            layout,
            tr("set_ww3bin_label", "WW3BIN 路径："),
            "WW3BIN_PATH",
            directory=True,
            placeholder=tr("set_ww3bin_ph", "为空则隐藏本地执行"),
        )
        self._path_field(layout, tr("set_jason_label", "JASON 数据路径："), "JASON_PATH", directory=True)
        self._path_field(layout, tr("set_ndbc_label", "NDBC 数据路径："), "NDBC_PATH", directory=True)

    def _build_gridgen_card(self) -> None:
        grid = self._card(tr("gridgen_config", "Gridgen 配置"))
        self._browse(grid, 0, tr("set_matlab_label", "MATLAB 路径："), "MATLAB_PATH", directory=False)
        self._combo(grid, 1, 0, tr("set_gridgen_version", "GRIDGEN 版本："), "GRIDGEN_VERSION", ["Python", "MATLAB"])
        self._text(grid, 2, 0, tr("set_dx", "普通网格DX："), "DX")
        self._text(grid, 3, 0, tr("set_dy", "普通网格DY："), "DY")
        self._text(grid, 4, 0, tr("set_nested_factor", "嵌套收缩系数："), "NESTED_CONTRACTION_COEFFICIENT")
        self._text(grid, 5, 0, tr("set_nested_dx", "嵌套外网格DX："), "NESTED_OUTER_DX")
        self._text(grid, 6, 0, tr("set_nested_dy", "嵌套外网格DY："), "NESTED_OUTER_DY")
        self._combo(grid, 7, 0, tr("set_bathymetry", "水深数据："), "BATHYMETRY", ["GEBCO", "ETOP1", "ETOP2"])
        self._combo(grid, 8, 0, tr("set_coastline_precision", "海岸边界精度："), "COASTLINE_PRECISION", ["full", "high", "inter", "low", "coarse"])
        self._text(grid, 9, 0, tr("set_min_dist", "海岸边界最小距离："), "MIN_DIST")
        self._text(grid, 10, 0, tr("set_cut_off", "湿干阈值："), "CUT_OFF")
        self._text(grid, 11, 0, tr("set_lim_bathy", "湿格比例："), "LIM_BATHY")
        self._text(grid, 12, 0, tr("set_lim_val", "边界覆盖阈值："), "LIM_VAL")
        self._text(grid, 13, 0, tr("set_split_lim", "边界切分阈值："), "SPLIT_LIM")
        self._text(grid, 14, 0, tr("set_lake_tol", "湖泊清理阈值："), "LAKE_TOL")

    def _build_spectrum_card(self) -> None:
        grid = self._card(tr("spectrum_config", "频谱参数"))
        self._text(grid, 0, 0, tr("set_freq_inc", "频率增量："), "FREQ_INC")
        self._text(grid, 1, 0, tr("set_freq_start", "起始频率："), "FREQ_START")
        self._text(grid, 2, 0, tr("set_freq_num", "频率数量："), "FREQ_NUM")
        self._text(grid, 3, 0, tr("set_dir_num", "方向离散数："), "DIR_NUM")
        self._step4_toggle(grid, 4, "STEP4_SHOW_SPECTRUM")
        self._reset_button(grid, 5, self._reset_spectrum_defaults)

    def _build_timesteps_card(self) -> None:
        grid = self._card(tr("timesteps_params", "数值积分时间步长参数"))
        self._text(grid, 0, 0, tr("set_dtmax", "最大全局时间步长："), "DTMAX")
        self._text(grid, 1, 0, tr("set_dtxy", "空间时间步长："), "DTXY")
        self._text(grid, 2, 0, tr("set_dtkth", "谱空间时间步长："), "DTKTH")
        self._text(grid, 3, 0, tr("set_dtmin", "最小源项时间步长："), "DTMIN")
        self._step4_toggle(grid, 4, "STEP4_SHOW_TIMESTEPS")
        self._reset_button(grid, 5, self._reset_timesteps_defaults)

    def _reset_button(self, grid: QGridLayout, row: int, handler: Callable[[], None]) -> None:
        button = PrimaryPushButton(tr("reset_defaults", "恢复默认值"))
        button.setStyleSheet(styles.button_style())
        button.clicked.connect(handler)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        grid.addWidget(button, row, 0, 1, 4)

    def _build_slurm_card(self) -> None:
        grid = self._card(tr("slurm_config", "Slurm 配置"))
        self._text(grid, 0, 0, tr("set_kernel_num", "核数："), "KERNEL_NUM")
        self._text(grid, 1, 0, tr("set_node_num", "节点数："), "NODE_NUM")
        button = PrimaryPushButton(tr("cpu_manage", "CPU 管理"))
        button.setStyleSheet(styles.button_style())
        button.clicked.connect(self._manage_cpu_group)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        grid.addWidget(button, 2, 0, 1, 4)

    def _build_ww3_card(self) -> None:
        grid = self._card(tr("ww3_config_card", "WW3 配置"))
        self._text(grid, 0, 0, tr("set_compute_precision", "计算精度："), "COMPUTE_PRECISION")
        self._text(grid, 1, 0, tr("set_output_precision", "输出精度："), "OUTPUT_PRECISION")
        self._combo(grid, 2, 0, tr("set_file_split", "文件分割："), "FILE_SPLIT", _file_split_items())

    def _build_server_card(self) -> None:
        grid = self._card(tr("server_connection", "服务器连接"))
        self._text(grid, 0, 0, tr("set_server_host", "服务器地址："), "SERVER_HOST")
        self._text(grid, 1, 0, tr("set_server_port", "端口："), "SERVER_PORT")
        self._text(grid, 2, 0, tr("set_server_user", "用户名："), "SERVER_USER")
        self._text(grid, 3, 0, tr("set_server_password", "密码："), "SERVER_PASSWORD")
        password = self._fields.get("SERVER_PASSWORD")
        if password is not None:
            password.setEchoMode(QLineEdit.EchoMode.Password)
        self._text(grid, 4, 0, tr("set_server_path", "服务器工作目录："), "SERVER_PATH")

    def _reset_spectrum_defaults(self) -> None:
        for key, value in {
            "FREQ_INC": "1.1",
            "FREQ_START": "0.04118",
            "FREQ_NUM": "32",
            "DIR_NUM": "24",
        }.items():
            if key in self._fields:
                self._fields[key].setText(value)
        self._save_config_now()

    def _reset_timesteps_defaults(self) -> None:
        for key, value in {
            "DTMAX": "900",
            "DTXY": "320",
            "DTKTH": "300",
            "DTMIN": "15",
        }.items():
            if key in self._fields:
                self._fields[key].setText(value)
        self._save_config_now()

    def _manage_cpu_group(self) -> None:
        dialog = _CpuGroupDialog(self.window(), _as_list(self._config.get("CPU_GROUP")))
        if not dialog.exec():
            return
        cpu_group = dialog.value
        if not cpu_group:
            InfoBar.warning(title="", content=tr("set_cpu_list_empty","CPU 列表不能为空"), duration=2000, parent=self)
            return
        updates = {"CPU_GROUP": cpu_group}
        if str(self._config.get("DEFAULT_CPU", "") or "") not in cpu_group:
            updates["DEFAULT_CPU"] = cpu_group[0]
        self._vm.save(updates)
        self._config = self._vm.load()

    def _build_unst_card(self) -> None:
        grid = self._card(tr("unst_mesh_config_card", "非结构化三角网格配置"))
        self._unst = self._vm.load_unst()
        self._unst_text(grid, 0, 0, tr("set_unst_hmax", "深水尺度（km）："), "spacing.hmax")
        self._unst_text(grid, 1, 0, tr("set_unst_hshr", "近岸尺度（km）："), "spacing.hshr")
        self._unst_text(grid, 2, 0, tr("set_unst_dhdx", "水深梯度："), "spacing.dhdx")
        self._unst_text(grid, 3, 0, tr("set_unst_nwav", "浅水按波长加密："), "spacing.nwav")
        self._unst_text(grid, 4, 0, tr("set_unst_deep_threshold", "深水阈值（m）："), "spacing.deep_ocean_threshold_m")
        self._unst_text(grid, 5, 0, tr("set_unst_margin", "区域外扩边距（度）："), "regional.margin_deg")
        self._unst_text(grid, 6, 0, tr("set_unst_edge_segments", "矩形边界折线段数："), "regional.edge_segments")

    def _build_smc_card(self) -> None:
        grid = self._card(tr("settings_smc_config_card", "SMC 网格配置"))
        self._smc = self._vm.load_smc()
        self._smc_combo(grid, 0, 0, tr("set_smc_bathymetry", "水深数据："), "input.bathymetry_file", ["ETOPO1", "ETOPO2", "GEBCO"])
        self._smc_combo(grid, 1, 0, tr("set_smc_bathy_convention", "水深约定："), "input.bathy_convention", ["elevation", "depth"])
        self._smc_text(grid, 2, 0, tr("set_smc_n_levels", "细化层数："), "grid.n_levels")
        self._smc_text(grid, 3, 0, tr("set_smc_wlevel", "参考水位："), "physics.wlevel")
        self._smc_text(grid, 4, 0, tr("set_smc_depmin", "最小水深："), "physics.depmin")
        self._smc_text(grid, 5, 0, tr("set_smc_dshalw", "浅水截断："), "physics.dshalw")
        self._smc_switch(grid, 6, 0, tr("set_smc_boundary", "开边界："), "boundary.generate_boundary_cells")
        self._smc_text(grid, 7, 0, tr("set_smc_msea", "海陆类型："), "boundary.msea")

    def _unst_text(self, grid: QGridLayout, row: int, col: int, label: str, dotted: str) -> None:
        edit = LineEdit()
        edit.setStyleSheet(styles.input_style())
        _apply_validator(edit, dotted)
        edit.setText(_as_text(_dig(self._unst, dotted)))
        self._expand_field(edit)
        grid.addWidget(self._label(label), row, col)
        grid.addWidget(edit, row, col + 1, 1, self._control_span(col))
        self._unst_fields[dotted] = edit

    def _smc_text(self, grid: QGridLayout, row: int, col: int, label: str, dotted: str) -> None:
        edit = LineEdit()
        edit.setStyleSheet(styles.input_style())
        _apply_validator(edit, dotted)
        edit.setText(_as_text(_dig(self._smc, dotted)))
        self._expand_field(edit)
        grid.addWidget(self._label(label), row, col)
        grid.addWidget(edit, row, col + 1, 1, self._control_span(col))
        self._smc_fields[dotted] = edit

    def _smc_combo(self, grid: QGridLayout, row: int, col: int, label: str, dotted: str, options: list[str]) -> None:
        combo = ComboBox()
        combo.setStyleSheet(styles.combo_style())
        left_align_combo_text(combo)
        combo.addItems(options)
        value = _as_text(_dig(self._smc, dotted))
        if dotted == "input.bathymetry_file":
            lower = value.lower()
            if "gebco" in lower:
                value = "GEBCO"
            elif "etopo1" in lower:
                value = "ETOPO1"
            else:
                value = "ETOPO2"
        if value and value not in options:
            combo.addItem(value)
        combo.setCurrentText(value or options[0])
        self._expand_field(combo)
        grid.addWidget(self._label(label), row, col)
        grid.addWidget(combo, row, col + 1, 1, self._control_span(col))
        self._smc_fields[dotted] = combo

    def _smc_switch(self, grid: QGridLayout, row: int, col: int, label: str, dotted: str) -> None:
        switch = self._switch_row(grid, row, label)
        switch.setChecked(bool(_dig(self._smc, dotted)))
        self._smc_fields[dotted] = switch

    # ── ST 版本管理 ───────────────────────────────────────────────────────────

    def _build_st_card(self) -> None:
        group, layout = create_header_card(self._content, tr("st_version_config", "ST 版本管理"))
        layout.setSpacing(5)
        self._st_table = _make_table([tr("set_st_name", "名称"), tr("set_st_path", "可执行路径")], first_column_width=96)
        layout.addWidget(self._st_table)
        row = QHBoxLayout()
        row.setSpacing(8)
        for text, handler in (
            (tr("new", "新增"), self._st_add),
            (tr("edit", "修改"), self._st_edit),
            (tr("delete", "删除"), self._st_delete),
        ):
            button = PrimaryPushButton(text)
            button.setStyleSheet(styles.button_style())
            button.clicked.connect(handler)
            row.addWidget(button, 1)
        layout.addLayout(row)
        group.viewLayout.setContentsMargins(11, 10, 11, 12)
        group.viewLayout.addLayout(layout)
        self._vbox.addWidget(group)
        self._reload_st_table()

    def _reload_st_table(self) -> None:
        versions = self._vm.st_versions()
        self._st_table.setRowCount(1)
        for version in versions:
            r = self._st_table.rowCount()
            self._st_table.insertRow(r)
            self._st_table.setItem(r, 0, QTableWidgetItem(version["name"]))
            self._st_table.setItem(r, 1, QTableWidgetItem(version.get("path", "")))
        _resize_table(self._st_table)

    def _st_rows(self) -> list[dict]:
        rows = []
        for r in range(1, self._st_table.rowCount()):
            name = self._st_table.item(r, 0)
            path = self._st_table.item(r, 1)
            if name and name.text().strip():
                rows.append({"name": name.text().strip(), "path": path.text().strip() if path else ""})
        return rows

    def _st_add(self) -> None:
        dlg = _NamePathDialog(self.window())
        if dlg.exec() and dlg.value:
            versions = self._st_rows() + [dlg.value]
            self._vm.save_st_versions(versions, self._vm.default_st())
            self._reload_st_table()

    def _st_edit(self) -> None:
        r = self._st_table.currentRow()
        if r < 1:
            return
        initial = {"name": self._st_table.item(r, 0).text(), "path": self._st_table.item(r, 1).text()}
        dlg = _NamePathDialog(self.window(), initial=initial)
        if dlg.exec() and dlg.value:
            versions = self._st_rows()
            versions[r - 1] = dlg.value
            self._vm.save_st_versions(versions, self._vm.default_st())
            self._reload_st_table()

    def _st_delete(self) -> None:
        r = self._st_table.currentRow()
        if r < 1:
            return
        versions = self._st_rows()
        del versions[r - 1]
        self._vm.save_st_versions(versions, self._vm.default_st())
        self._reload_st_table()

    # ── 谱分区输出方案 ────────────────────────────────────────────────────────

    def _build_scheme_card(self) -> None:
        group, layout = create_header_card(self._content, tr("spectral_output_title", "谱分区输出方案配置"))
        layout.setSpacing(5)
        self._schemes = self._vm.output_schemes()
        self._var_checks: dict[str, CheckBox] = {}
        for code in sorted(_OUTPUT_VAR_CODES):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(14)
            row.addWidget(
                self._label(tr(f"var_{code.lower()}", _OUTPUT_VAR_LABELS.get(code, code)), word_wrap=False)
            )
            row.addStretch(1)
            check = CheckBox("")
            check.setFixedWidth(22)
            self._var_checks[code] = check
            row.addWidget(check)
            row_widget = QWidget()
            row_widget.setLayout(row)
            layout.addWidget(row_widget)

        form = QGridLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(5)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(3, 1)
        self._scheme_name_edit = LineEdit()
        self._scheme_name_edit.setStyleSheet(styles.input_style())
        self._expand_field(self._scheme_name_edit)
        self._scheme_name_edit.setPlaceholderText(tr("set_scheme_name_ph", "输入方案名称"))
        form.addWidget(self._label(tr("scheme_name_label", "方案名称："), word_wrap=False), 0, 0)
        form.addWidget(self._scheme_name_edit, 0, 1, 1, 3)
        self._scheme_combo = ComboBox()
        self._scheme_combo.setStyleSheet(styles.combo_style())
        left_align_combo_text(self._scheme_combo)
        self._expand_field(self._scheme_combo)
        self._scheme_combo.addItems(list(self._schemes.keys()))
        self._scheme_combo.currentTextChanged.connect(self._on_scheme_selected)
        form.addWidget(self._label(tr("current_scheme", "当前方案："), word_wrap=False), 1, 0)
        form.addWidget(self._scheme_combo, 1, 1, 1, 3)
        layout.addLayout(form)

        confirm = PrimaryPushButton(tr("confirm_output_vars", "确认"))
        confirm.setStyleSheet(styles.button_style())
        confirm.clicked.connect(self._scheme_confirm)
        layout.addWidget(confirm)
        delete = PrimaryPushButton(tr("delete_scheme", "删除方案"))
        delete.setStyleSheet(styles.button_style())
        delete.clicked.connect(self._scheme_delete)
        layout.addWidget(delete)

        group.viewLayout.setContentsMargins(11, 10, 11, 12)
        group.viewLayout.addLayout(layout)
        self._vbox.addWidget(group)
        if self._schemes:
            self._on_scheme_selected(self._scheme_combo.currentText())

    def _on_scheme_selected(self, name: str) -> None:
        selected = set(self._schemes.get(name, []))
        for code, check in self._var_checks.items():
            check.setChecked(code in selected)
        if hasattr(self, "_scheme_name_edit"):
            self._scheme_name_edit.setText(name)

    def _checked_vars(self) -> list[str]:
        return [code for code in _OUTPUT_VAR_CODES if self._var_checks[code].isChecked()]

    def _scheme_new(self) -> None:
        dlg = _NamePathDialog(self.window(), name_only=True, title=tr("set_new_scheme","新建方案"))
        if dlg.exec() and dlg.value:
            name = dlg.value["name"]
            self._schemes[name] = self._checked_vars()
            self._vm.save_output_schemes(self._schemes)
            if self._scheme_combo.findText(name) < 0:
                self._scheme_combo.addItem(name)
            self._scheme_combo.setCurrentText(name)
            self._toast(tr("set_scheme_created","已新建方案"))

    def _scheme_save(self) -> None:
        name = self._scheme_combo.currentText().strip()
        if not name:
            return
        self._schemes[name] = self._checked_vars()
        self._vm.save_output_schemes(self._schemes)
        self._toast(tr("set_scheme_saved","已保存方案"))

    def _scheme_confirm(self) -> None:
        name = self._scheme_name_edit.text().strip() or self._scheme_combo.currentText().strip()
        if not name:
            self._toast(tr("set_scheme_name_empty","方案名称不能为空"))
            return
        self._schemes[name] = self._checked_vars()
        self._vm.save_output_schemes(self._schemes)
        if self._scheme_combo.findText(name) < 0:
            self._scheme_combo.addItem(name)
        self._scheme_combo.setCurrentText(name)
        self._toast(tr("set_scheme_saved","已保存方案"))

    def _scheme_delete(self) -> None:
        name = self._scheme_combo.currentText().strip()
        if not name or name not in self._schemes:
            return
        del self._schemes[name]
        self._vm.save_output_schemes(self._schemes)
        idx = self._scheme_combo.currentIndex()
        self._scheme_combo.removeItem(idx)
        self._toast(tr("set_scheme_deleted","已删除方案"))

    # ── 保存（config.json + 网格 JSON）─────────────────────────────────────────

    def _collect_config(self) -> dict:
        updates: dict = {}
        for key, edit in self._fields.items():
            updates[key] = edit.text().strip()
        for key, combo in self._combos.items():
            data = combo.itemData(combo.currentIndex())
            updates[key] = data if data is not None else combo.currentText()
        for key, check in self._checks.items():
            updates[key] = check.isChecked()
        if hasattr(self, "_cpu_group_edit"):
            updates["CPU_GROUP"] = [s.strip() for s in self._cpu_group_edit.text().split(",") if s.strip()]
        return updates

    def _collect_nested(self, fields: dict[str, QWidget]) -> dict:
        out: dict = {}
        for dotted, widget in fields.items():
            if isinstance(widget, ComboBox):
                if dotted == "input.bathymetry_file":
                    value = smc_bathymetry_relpath_for_combo_index(widget.currentIndex())
                else:
                    data = widget.itemData(widget.currentIndex())
                    value = data if data is not None else widget.currentText()
            elif hasattr(widget, "isChecked") and not isinstance(widget, LineEdit):
                value = bool(widget.isChecked())
            else:
                value = _coerce(widget.text().strip())
            _set_dig(out, dotted, value)
        return out

    def _wire_autosave(self) -> None:
        """连接各控件变更信号，改动即时落盘（无需手动保存按钮）。

        在所有卡片构建并填好初值之后调用，避免初始化期间的信号触发写盘。
        ST 版本、谱分区方案、CPU 列表已在各自操作中即时保存。
        """
        for widget in self._fields.values():
            self._connect_autosave(widget, self._save_config_now)
        for widget in self._combos.values():
            self._connect_autosave(widget, self._save_config_now)
        for widget in self._checks.values():
            self._connect_autosave(widget, self._save_config_now)
        for widget in self._unst_fields.values():
            self._connect_autosave(widget, self._save_unst_now)
        for widget in self._smc_fields.values():
            self._connect_autosave(widget, self._save_smc_now)

    def _connect_autosave(self, widget: QWidget, handler: Callable[[], None]) -> None:
        if isinstance(widget, ComboBox):
            widget.currentIndexChanged.connect(lambda *_: handler())
        elif isinstance(widget, LineEdit):
            widget.editingFinished.connect(handler)
        elif isinstance(widget, SwitchButton):
            widget.checkedChanged.connect(lambda *_: handler())
        elif hasattr(widget, "toggled"):
            widget.toggled.connect(lambda *_: handler())

    def _save_config_now(self) -> None:
        self._vm.save(self._collect_config())
        self._config = self._vm.load()

    def _save_unst_now(self) -> None:
        self._vm.save_unst(self._collect_nested(self._unst_fields))

    def _save_smc_now(self) -> None:
        self._vm.save_smc(self._collect_nested(self._smc_fields))

    def _on_theme_changed(self, name: str) -> None:
        self._vm.apply_theme(name)
        self._vm.save({"THEME": name})

    def _on_language_changed(self, code: str) -> None:
        self._vm.save({"LANGUAGE": code})
        self._vm.apply_language(code)
        if callable(self._on_language_changed_callback):
            self._on_language_changed_callback(code)

    def _on_run_mode_changed(self, _index: int = 0) -> None:
        combo = self._combos.get("RUN_MODE")
        if combo is None:
            return
        run_mode = self._run_mode_from_combo(combo)
        if run_mode is None:
            return
        self._vm.save({"RUN_MODE": run_mode})
        self._config = self._vm.load()
        if callable(self._on_run_mode_changed_callback):
            self._on_run_mode_changed_callback(run_mode)

    def _toast(self, message: str) -> None:
        InfoBar.success(title="", content=message, duration=2000, parent=self)


# ── 小对话框：名称(+路径) ─────────────────────────────────────────────────────


class _NamePathDialog(MessageBoxBase):
    """录入名称（可选可执行路径）。"""

    def __init__(self, parent=None, *, initial: dict | None = None, name_only: bool = False, title: str = "") -> None:
        super().__init__(parent)
        self.value: dict | None = None
        initial = initial or {}
        if getattr(self, "yesButton", None):
            self.yesButton.setText(tr("confirm", "确定"))
        if getattr(self, "cancelButton", None):
            self.cancelButton.setText(tr("cancel", "取消"))
        grid = QGridLayout()
        grid.setSpacing(14)
        grid.setColumnStretch(1, 1)
        self._name = LineEdit()
        self._name.setStyleSheet(styles.input_style())
        self._name.setText(str(initial.get("name", "")))
        self._name.setMinimumWidth(280)
        grid.addWidget(QLabel(tr("set_name_label","名称:")), 0, 0)
        grid.addWidget(self._name, 0, 1)
        self._path = None
        if not name_only:
            self._path = LineEdit()
            self._path.setStyleSheet(styles.input_style())
            self._path.setText(str(initial.get("path", "")))
            grid.addWidget(QLabel(tr("set_path_label","路径:")), 1, 0)
            grid.addWidget(self._path, 1, 1)
        self.viewLayout.addLayout(grid)
        self.widget.setMinimumWidth(360)

    def validate(self) -> bool:
        name = self._name.text().strip()
        if not name:
            InfoBar.warning(title="", content=tr("set_name_empty","名称不能为空"), duration=2000, parent=self)
            return False
        self.value = {"name": name, "path": self._path.text().strip() if self._path else ""}
        return True


class _CpuGroupDialog(MessageBoxBase):
    """编辑可选 CPU 分区列表。"""

    def __init__(self, parent=None, cpu_group: list[str] | None = None) -> None:
        super().__init__(parent)
        self.value: list[str] = []
        cpu_group = cpu_group or ["CPU6240R", "CPU6336Y"]
        self.setWindowTitle(tr("cpu_manage", "CPU 管理"))
        if getattr(self, "yesButton", None):
            self.yesButton.setText(tr("confirm", "确定"))
        if getattr(self, "cancelButton", None):
            self.cancelButton.setText(tr("cancel", "取消"))

        layout = QVBoxLayout()
        layout.setSpacing(14)
        layout.addWidget(QLabel(tr("set_cpu_list_label", "CPU 列表（每行一个）：")))

        self._text = TextEdit()
        self._text.setPlaceholderText(tr("set_cpu_list_ph", "输入 CPU 名称，每行一个..."))
        self._text.setPlainText("\n".join(cpu_group))
        self._text.setStyleSheet(styles.input_style())
        self._text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._text.setMinimumHeight(max(150, len(cpu_group) * 25 + 20))
        layout.addWidget(self._text)

        self.viewLayout.addLayout(layout)
        self.widget.setMinimumWidth(360)

    def validate(self) -> bool:
        self.value = [line.strip() for line in self._text.toPlainText().splitlines() if line.strip()]
        if not self.value:
            InfoBar.warning(title="", content=tr("set_cpu_list_empty","CPU 列表不能为空"), duration=2000, parent=self)
            return False
        return True


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_table(headers: list[str], *, first_column_width: int | None = None) -> TableWidget:
    table = TableWidget()
    table.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
    table.setColumnCount(len(headers))
    table.horizontalHeader().setVisible(False)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setBorderVisible(False)
    table.setWordWrap(False)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    header = table.horizontalHeader()
    if first_column_width is not None and len(headers) >= 2:
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(0, first_column_width)
        for col in range(1, len(headers)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
    else:
        for col in range(len(headers)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
    table.insertRow(0)
    for col, title in enumerate(headers):
        item = QTableWidgetItem(title)
        item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        item.setData(Qt.ItemDataRole.UserRole, "header")
        table.setItem(0, col, item)
    return table


def _resize_table(table: TableWidget) -> None:
    table.resizeRowsToContents()
    total = sum(table.rowHeight(r) for r in range(table.rowCount()))
    table.setFixedHeight(total + 2 * table.frameWidth() + 2)


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _as_list(value) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def _coerce(text: str):
    """文本转 int/float（可行时），否则原样字符串。"""
    if text == "":
        return ""
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def _apply_validator(edit: LineEdit, key: str) -> None:
    if key in _INTEGER_CONFIG_KEYS or key in _INTEGER_DOTTED_KEYS:
        edit.setValidator(int_validator(0))
    elif key in _NUMERIC_CONFIG_KEYS or key in _NUMERIC_DOTTED_KEYS:
        edit.setValidator(double_validator())


def _dig(data: dict, dotted: str):
    cur = data
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _set_dig(data: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    cur = data
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def create_settings_interface(view_model: SettingsViewModel | None = None) -> SettingsInterface:
    return SettingsInterface(view_model=view_model)
