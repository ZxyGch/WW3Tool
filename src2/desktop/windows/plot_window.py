"""绘图子界面：JASON 3 拟合 / NDBC 拟合 / 风场绘图 / 海浪二维方向谱绘图 / 波高图绘制。

卡片标题、控件、标签与按钮文案、排列顺序对齐 src 绘图页（``src/plot/*._create_*_ui``）。
作为 FluentWindow 左侧堆叠的一页，右侧共享日志常驻，结果图复用窗口右侧图片面板。
有 src2 后端的按钮交由窗口回调执行；文件/文件夹选择在本类内处理；暂无后端的按钮提示。
"""

from __future__ import annotations

import glob
import os
from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import ComboBox, LineEdit, PrimaryPushButton, TableWidget

from ..components.combo_box import left_align_combo_text
from ..components.header_card import create_header_card
from ..components import styles
from ..components.styles import is_dark
from ..components.validators import double_validator
from workflows.infrastructure.plot.photo_output import (
    SUBDIR_DIRECTIONAL_SPECTRUM,
    SUBDIR_JASON3_FIT,
    SUBDIR_JASON3_SATELLITE,
    SUBDIR_NDBC_FIT,
    SUBDIR_WAVE_HEIGHT,
    SUBDIR_WAVE_HEIGHT_CONTOUR,
    SUBDIR_WAVE_HEIGHT_VIDEO,
    SUBDIR_WIND_FIELD,
    SUBDIR_WIND_SWELL,
)
from workflows.support.translations import tr


class _NoHScrollArea(QScrollArea):
    """QScrollArea that completely disables horizontal scrolling."""

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: N802
        super().scrollContentsBy(0, dy)

    def horizontalScrollBar(self):
        bar = super().horizontalScrollBar()
        bar.setRange(0, 0)
        return bar


class PlotInterface(QWidget):
    """科研绘图页（样式对齐 src）。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        run_jason3: Callable[[], None],
        run_download_jason3: Callable[[], None],
        run_jason3_swh: Callable[[], None],
        run_download_ndbc: Callable[[], None],
        run_match_ndbc: Callable[[], None],
        run_ndbc_station_map: Callable[[], None],
        run_spectrum_all: Callable[[], None],
        run_spectrum_selected: Callable[[], None],
        run_spectrum_map: Callable[[], None],
        run_wave_maps: Callable[[], None],
        run_wind_swell: Callable[[], None],
        run_contour: Callable[[], None],
        run_wave_video: Callable[[], None],
        run_wind_field: Callable[[], None],
        view_photo_subdir: Callable[[str], None],
        open_photo_folder: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self.setObjectName("plot_interface")
        self._view_photo_subdir = view_photo_subdir

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = _NoHScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        content = QWidget()
        content.setStyleSheet("QWidget { background: transparent; }")
        self._content = content
        self._vbox = QVBoxLayout(content)
        self._vbox.setContentsMargins(0, 0, 0, 10)
        self._vbox.setSpacing(14)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        self._jason3_fields = self._build_match_card(
            tr("plotting_jason3_fit", "JASON 3 拟合"),
            choose_label=tr("plotting_jason3_choose", "JASON 3 选择"),
            download_label=tr("plotting_download_jason3", "下载 JASON 3 数据"),
            generate_obs_label=tr("plotting_generate_jason3_swh", "生成卫星观测图"),
            generate_fit_label=tr("plotting_generate_jason3_fit", "生成拟合图"),
            on_download=run_download_jason3,
            on_generate_obs=run_jason3_swh,
            on_generate_fit=run_jason3,
            view_obs_subdir=SUBDIR_JASON3_SATELLITE,
            view_fit_subdir=SUBDIR_JASON3_FIT,
        )
        self._ndbc_fields = self._build_match_card(
            tr("plotting_ndbc_fit", "NDBC 拟合"),
            choose_label=tr("plotting_ndbc_choose", "NDBC 选择"),
            download_label=tr("plotting_download_ndbc", "下载 NDBC 数据"),
            view_obs_label=tr("plotting_view_ndbc_stations", "查看浮标站点图"),
            generate_fit_label=tr("plotting_generate_ndbc_fit", "生成 NDBC 拟合图"),
            on_download=run_download_ndbc,
            on_view_obs=run_ndbc_station_map,
            on_generate_fit=run_match_ndbc,
            view_fit_subdir=SUBDIR_NDBC_FIT,
            ndbc_mode=True,
        )
        self._build_wind_field_card(run_wind_field, SUBDIR_WIND_FIELD)
        self._build_spectrum_card(run_spectrum_all, run_spectrum_selected, run_spectrum_map)
        self._build_wave_card(run_wave_maps, run_wind_swell, run_contour, run_wave_video, open_photo_folder)
        self._vbox.addStretch(1)

    # ── 通用件 ────────────────────────────────────────────────────────────────

    def _card(self, title: str) -> QVBoxLayout:
        group, layout = create_header_card(self._content, title)
        layout.setSpacing(10)
        group.viewLayout.setContentsMargins(11, 10, 11, 12)
        group.viewLayout.addLayout(layout)
        self._vbox.addWidget(group)
        return layout

    def _button(self, text: str, handler: Callable[[], None]) -> PrimaryPushButton:
        button = PrimaryPushButton(text)
        button.setStyleSheet(styles.button_style())
        button.clicked.connect(handler)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return button

    def _gen_view_row(
        self,
        generate_label: str,
        generate_cb: Callable[[], None],
        view_subdir: str,
    ) -> QHBoxLayout:
        """生成 / 查看按钮行，宽度比例 3:1。"""
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self._button(generate_label, generate_cb), 3)
        row.addWidget(
            self._button(tr("plotting_view_short", "查看"), lambda: self._view_photo_subdir(view_subdir)),
            1,
        )
        return row

    def _add_gen_view_row(
        self,
        layout: QVBoxLayout,
        generate_label: str,
        generate_cb: Callable[[], None],
        view_subdir: str,
    ) -> None:
        layout.addLayout(self._gen_view_row(generate_label, generate_cb, view_subdir))

    def _add_gen_view_pair(
        self,
        layout: QVBoxLayout,
        row_a: tuple[str, Callable[[], None], str],
        row_b: tuple[str, Callable[[], None], str],
    ) -> None:
        """两行生成/查看按钮共用列宽，保证「查看」列垂直对齐。"""
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        for row_idx, (label, generate_cb, view_subdir) in enumerate((row_a, row_b)):
            grid.addWidget(self._button(label, generate_cb), row_idx, 0)
            grid.addWidget(
                self._button(
                    tr("plotting_view_short", "查看"),
                    lambda subdir=view_subdir: self._view_photo_subdir(subdir),
                ),
                row_idx,
                1,
            )
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

    def _set_button_file_chosen(self, button: PrimaryPushButton, filepath: str) -> None:
        """将按钮文字改为文件名，并在原有样式基础上将文字颜色设为蓝色。"""
        filename = os.path.basename(filepath)
        if len(filename) > 28:
            filename = filename[:25] + "..."
        button.setText(filename)
        # 在原有 button_style 基础上追加蓝色文字，不替换整个样式表
        base = styles.button_style()
        if is_dark():
            color_rule = "PrimaryPushButton { color: #5CB3FF; }"
        else:
            color_rule = "PrimaryPushButton { color: #1E90FF; }"
        button.setStyleSheet(base + "\n" + color_rule)

    def _reset_file_button(self, button: PrimaryPushButton, default_text: str) -> None:
        """将文件选择按钮恢复为默认文案与样式。"""
        button.setText(default_text)
        button.setStyleSheet(styles.button_style())

    @staticmethod
    def _resolve_wind_nc_path(workdir: str) -> str | None:
        """在工作目录中查找 wind.nc，否则回退到 wind_*.nc。"""
        wind_nc = os.path.join(workdir, "wind.nc")
        if os.path.isfile(wind_nc):
            return wind_nc
        wind_files = sorted(glob.glob(os.path.join(workdir, "wind_*.nc")))
        return wind_files[0] if wind_files else None

    @staticmethod
    def _resolve_wave_nc_path(workdir: str) -> str | None:
        """在工作目录中查找 ww3*.nc（排除谱文件）。"""
        wave_files = sorted(glob.glob(os.path.join(workdir, "ww3*.nc")))
        wave_files = [f for f in wave_files if "spec" not in os.path.basename(f).lower()]
        return wave_files[0] if wave_files else None

    @staticmethod
    def _resolve_spectrum_nc_path(workdir: str) -> str | None:
        """在工作目录中查找 ww3*spec*nc 二维谱文件。"""
        spec_files = glob.glob(os.path.join(workdir, "ww3*spec*nc"))
        return spec_files[0] if spec_files else None

    def _resolve_detected_path(self, fields: dict[str, LineEdit], file_key: str, workdir: str, detector) -> str | None:
        """优先保留用户已选且仍存在的文件，否则从工作目录自动检测。"""
        edit = fields.get(file_key)
        current = edit.text().strip() if edit is not None else ""
        if current and os.path.isfile(current):
            return current
        return detector(workdir)

    def _apply_detected_file(
        self,
        fields: dict[str, LineEdit],
        file_key: str,
        btn_key: str,
        path: str | None,
        default_text: str,
    ) -> None:
        edit = fields.get(file_key)
        btn = fields.get(btn_key)
        if edit is None or btn is None:
            return
        if path:
            edit.setText(path)
            self._set_button_file_chosen(btn, path)
        else:
            edit.clear()
            self._reset_file_button(btn, default_text)

    def auto_detect_from_workdir(self, workdir: str | None) -> None:
        """静默检测工作目录中的 wind.nc / ww3*.nc 并填充绘图页按钮（对齐 src show_plot_page）。"""
        try:
            if not workdir or not os.path.isdir(workdir):
                return
            workdir = os.path.abspath(workdir)

            from workflows.infrastructure.runtime_config import ensure_project_data_dir

            if not self._jason3_fields["folder"].text().strip():
                self._jason3_fields["folder"].setText(ensure_project_data_dir("JASON_PATH", "jason3"))
            if not self._ndbc_fields["folder"].text().strip():
                self._ndbc_fields["folder"].setText(ensure_project_data_dir("NDBC_PATH", "ndbc"))

            jason3_wind_path = self._resolve_detected_path(
                self._jason3_fields, "wind_file", workdir, self._resolve_wind_nc_path
            )
            jason3_wave_path = self._resolve_detected_path(
                self._jason3_fields, "wave_file", workdir, self._resolve_wave_nc_path
            )
            ndbc_wind_path = self._resolve_detected_path(
                self._ndbc_fields, "wind_file", workdir, self._resolve_wind_nc_path
            )
            ndbc_wave_path = self._resolve_detected_path(
                self._ndbc_fields, "wave_file", workdir, self._resolve_wave_nc_path
            )
            wind_field_path = (
                self._wind_file_edit.text().strip()
                if self._wind_file_edit.text().strip() and os.path.isfile(self._wind_file_edit.text().strip())
                else self._resolve_wind_nc_path(workdir)
            )
            wave_card_path = (
                self._wave_file.text().strip()
                if self._wave_file.text().strip() and os.path.isfile(self._wave_file.text().strip())
                else self._resolve_wave_nc_path(workdir)
            )
            spec_path = self._resolve_spectrum_nc_path(workdir)

            wind_default = tr("step1_choose_wind", "选择风场文件")
            wave_default = tr("plotting_choose_wave_height", "选择波高文件")
            wave_card_default = tr("plotting_choose_wave_file", "选择波高文件")
            spec_default = tr("plotting_choose_spectrum_file", "选择二维谱文件")

            self._apply_detected_file(self._jason3_fields, "wind_file", "wind_file_btn", jason3_wind_path, wind_default)
            self._apply_detected_file(self._jason3_fields, "wave_file", "wave_file_btn", jason3_wave_path, wave_default)
            self._apply_detected_file(self._ndbc_fields, "wind_file", "wind_file_btn", ndbc_wind_path, wind_default)
            self._apply_detected_file(self._ndbc_fields, "wave_file", "wave_file_btn", ndbc_wave_path, wave_default)

            if wind_field_path:
                self._wind_file_edit.setText(wind_field_path)
                self._set_button_file_chosen(self._wind_file_btn, wind_field_path)
            else:
                self._wind_file_edit.clear()
                self._reset_file_button(self._wind_file_btn, wind_default)

            if wave_card_path:
                self._wave_file.setText(wave_card_path)
                self._set_button_file_chosen(self._wave_file_btn, wave_card_path)
            else:
                self._wave_file.clear()
                self._reset_file_button(self._wave_file_btn, wave_card_default)

            if spec_path:
                self._spectrum_file.setText(spec_path)
                self._set_button_file_chosen(self._spectrum_file_btn, spec_path)
                self._load_spectrum_stations(spec_path)
            else:
                self._spectrum_file.clear()
                self._reset_file_button(self._spectrum_file_btn, spec_default)
                self._spectrum_table.setRowCount(0)
                self._spectrum_table.setVisible(False)
        except Exception:
            pass

    def _line(self, value: str = "", *, placeholder: str = "") -> LineEdit:
        edit = LineEdit()
        edit.setStyleSheet(styles.input_style())
        edit.setText(value)
        if placeholder:
            edit.setPlaceholderText(placeholder)
        edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return edit

    def _todo(self, name: str) -> None:
        pass

    def _pick_file(self, edit: LineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("select_file", "选择文件"),
            edit.text().strip() or "",
            tr("file_filter_netcdf_all_short", "NetCDF (*.nc);;所有文件 (*)"),
        )
        if path:
            edit.setText(path)

    def _pick_folder(self, edit: LineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, tr("select_folder", "选择文件夹"), edit.text().strip() or "")
        if path:
            edit.setText(path)

    # ── 从 NC 读取范围 ────────────────────────────────────────────────────────

    def _load_range_from_nc(self, fields: dict[str, LineEdit], file_pattern: str) -> None:
        """从 NetCDF 文件中读取经纬度和时间范围并填入对应输入框。

        优先使用用户手动选择的文件（wind_file / wave_file 字段），
        如果没有选择则回退到工作目录中按 file_pattern 搜索。

        Args:
            fields: 卡片内的输入框字典。
            file_pattern: 文件匹配模式，如 ``"wind.nc"`` 或 ``"ww3.*.nc"``。
        """
        nc_path: str | None = None

        # 1) 优先使用用户手动选择的文件
        is_ww3_pattern = "ww3" in file_pattern.lower() or "*" in file_pattern
        file_key = "wave_file" if is_ww3_pattern else "wind_file"
        selected = fields.get(file_key, LineEdit()).text().strip()
        if selected and os.path.isfile(selected):
            nc_path = selected
        else:
            # 2) 回退：在工作目录中按 pattern 搜索
            folder_edit = fields.get("folder")
            work_dir = folder_edit.text().strip() if folder_edit else ""
            if not work_dir:
                for p in (fields.get("wind_file", LineEdit()).text().strip(),
                          fields.get("wave_file", LineEdit()).text().strip()):
                    if p and os.path.isfile(p):
                        work_dir = os.path.dirname(p)
                        break
            if work_dir and os.path.isdir(work_dir):
                candidates = glob.glob(os.path.join(work_dir, file_pattern))
                if candidates:
                    nc_path = candidates[0]

        if not nc_path:
            return

        self._read_and_fill_range(fields, nc_path)

    def _pick_file_and_fill_range(self, fields: dict[str, LineEdit], file_key: str) -> None:
        """选择文件后，更新路径显示并自动读取经纬度/时间范围。"""
        edit = fields.get(file_key)
        if edit is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("select_file", "选择文件"),
            edit.text().strip() or "",
            tr("file_filter_netcdf_all_short", "NetCDF (*.nc);;所有文件 (*)"),
        )
        if not path:
            return
        edit.setText(path)
        # 更新按钮文字为文件名，并改为蓝色
        btn = fields.get(f"{file_key}_btn")
        if btn is not None:
            self._set_button_file_chosen(btn, path)
        # 自动读取范围并填充经纬度/时间
        self._read_and_fill_range(fields, path)

    def _read_and_fill_range(self, fields: dict[str, LineEdit], nc_path: str) -> None:
        """从指定 NC 文件读取经纬度和时间范围，填充到 fields。"""
        try:
            from netCDF4 import Dataset, num2date

            ds = Dataset(nc_path, "r")
            try:
                lon = ds.variables["longitude"][:]
                lat = ds.variables["latitude"][:]
            except KeyError:
                return

            # 处理 masked array
            if hasattr(lon, "data"):
                import numpy as np
                lon = np.array(lon.data)
                lat = np.array(lat.data)

            fields["lon_west"].setText(f"{float(lon.min()):.2f}")
            fields["lon_east"].setText(f"{float(lon.max()):.2f}")
            fields["lat_south"].setText(f"{float(lat.min()):.2f}")
            fields["lat_north"].setText(f"{float(lat.max()):.2f}")

            # 尝试读取时间范围
            try:
                if "time" in ds.variables:
                    time_var = ds.variables["time"]
                    times = num2date(time_var[:], time_var.units)
                    start_time = times[0]
                    end_time = times[-1]
                    if hasattr(start_time, "strftime"):
                        fields["start"].setText(start_time.strftime("%Y%m%d"))
                        fields["end"].setText(end_time.strftime("%Y%m%d"))
            except Exception:
                pass  # 时间读取失败不影响经纬度

            ds.close()
        except ImportError:
            pass
        except Exception:
            pass

    # ── Jason-3 / NDBC 共用卡片 ───────────────────────────────────────────────

    def _build_match_card(
        self,
        title: str,
        *,
        choose_label: str,
        download_label: str,
        view_obs_label: str = "",
        generate_obs_label: str = "",
        generate_fit_label: str,
        on_download: Callable[[], None],
        on_view_obs: Callable[[], None] | None = None,
        on_generate_obs: Callable[[], None] | None = None,
        on_generate_fit: Callable[[], None],
        view_obs_subdir: str = "",
        view_fit_subdir: str,
        ndbc_mode: bool = False,
    ) -> dict[str, LineEdit]:
        layout = self._card(title)
        fields: dict[str, LineEdit] = {}

        # 1) 经纬度 + 时间网格（与 src 一致：放在最前）
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(5)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        for key, default, tkey, r, c in (
            ("lon_west", "西经:", "step2_lon_west", 0, 0),
            ("lon_east", "东经:", "step2_lon_east", 0, 2),
            ("lat_south", "南纬:", "step2_lat_south", 1, 0),
            ("lat_north", "北纬:", "step2_lat_north", 1, 2),
            ("start", "开始:", "plotting_start", 2, 0),
            ("end", "结束:", "plotting_end", 2, 2),
        ):
            fields[key] = self._line(placeholder="YYYYMMDD" if key in ("start", "end") else "")
            grid.addWidget(QLabel(tr(tkey, default)), r, c)
            grid.addWidget(fields[key], r, c + 1)
        layout.addLayout(grid)

        # 2) 数据文件夹（输入框 + 选择按钮，无标签，与 src 一致）
        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        fields["folder"] = self._line()
        folder_row.addWidget(fields["folder"], 1)
        choose = self._button(choose_label, lambda: self._pick_folder(fields["folder"]))
        folder_row.addWidget(choose)
        layout.addLayout(folder_row)

        # 3) [选择风场文件 | 从 wind.nc 读取范围]
        fields["wind_file"] = self._line()
        wind_btn = self._button(tr("step1_choose_wind", "选择风场文件"), lambda: self._pick_file_and_fill_range(fields, "wind_file"))
        fields["wind_file_btn"] = wind_btn
        wind_row = QHBoxLayout()
        wind_row.setSpacing(10)
        wind_row.addWidget(wind_btn, 1)
        wind_row.addWidget(self._button(tr("step2_load_from_nc", "从 wind.nc 读取范围"), lambda: self._load_range_from_nc(fields, "wind.nc")), 1)
        layout.addLayout(wind_row)

        # 4) [选择波高文件 | 从模拟结果读取范围]
        fields["wave_file"] = self._line()
        wave_btn = self._button(tr("plotting_choose_wave_height", "选择波高文件"), lambda: self._pick_file_and_fill_range(fields, "wave_file"))
        fields["wave_file_btn"] = wave_btn
        wave_row = QHBoxLayout()
        wave_row.setSpacing(10)
        wave_row.addWidget(wave_btn, 1)
        wave_row.addWidget(self._button(tr("step2_load_from_ww3", "从模拟结果读取范围"), lambda: self._load_range_from_nc(fields, "ww3.*.nc")), 1)
        layout.addLayout(wave_row)

        # 5) 下载 / 生成+查看
        layout.addWidget(self._button(download_label, on_download))
        if ndbc_mode:
            layout.addWidget(self._button(view_obs_label, on_view_obs))
            self._add_gen_view_row(layout, generate_fit_label, on_generate_fit, view_fit_subdir)
        else:
            self._add_gen_view_row(layout, generate_obs_label, on_generate_obs, view_obs_subdir)
            self._add_gen_view_row(layout, generate_fit_label, on_generate_fit, view_fit_subdir)
        return fields

    # ── 风场绘图 ────────────────────────────────────────────────────────────────

    def _build_wind_field_card(self, run_wind_field: Callable, view_subdir: str) -> None:
        layout = self._card(tr("plotting_wind_field", "风场绘图"))

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(5)

        # 时间步长
        self._wind_timestep = self._line("24", placeholder=tr("plotting_default_24_hours", "默认 24 小时"))
        self._wind_timestep.setValidator(double_validator(0.0, 1.0e12))
        grid.addWidget(QLabel(tr("plotting_wind_timestep", "时间步长 (小时):")), 0, 0)
        grid.addWidget(self._wind_timestep, 0, 1)

        # 风向标志类型
        self._wind_flag_combo = ComboBox()
        self._wind_flag_combo.addItems([
            tr("plotting_wind_flag_arrow", "箭头"),
            tr("plotting_wind_flag_flag", "风旗"),
            tr("plotting_wind_flag_none", "无"),
        ])
        self._wind_flag_combo.setCurrentText(tr("plotting_wind_flag_arrow", "箭头"))
        self._wind_flag_combo.setStyleSheet(styles.combo_style())
        left_align_combo_text(self._wind_flag_combo)
        self._wind_flag_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        grid.addWidget(QLabel(tr("plotting_wind_flag", "风向标志:")), 1, 0)
        grid.addWidget(self._wind_flag_combo, 1, 1)

        # 标志密度
        self._wind_density = self._line("10", placeholder=tr("plotting_wind_flag_density_placeholder", "自动"))
        grid.addWidget(QLabel(tr("plotting_wind_flag_density", "标志密度 (步长):")), 2, 0)
        grid.addWidget(self._wind_density, 2, 1)

        layout.addLayout(grid)

        # 选择风场文件
        self._wind_file_edit = self._line()
        self._wind_file_btn = self._button(tr("step1_choose_wind", "选择风场文件"), self._pick_wind_field_file)
        layout.addWidget(self._wind_file_btn)

        self._add_gen_view_row(
            layout,
            tr("plotting_generate_wind", "生成风场图"),
            run_wind_field,
            view_subdir,
        )

    def _pick_wind_field_file(self) -> None:
        """选择风场文件后更新按钮文字为文件名并改为蓝色。"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("select_file", "选择文件"),
            self._wind_file_edit.text().strip() or "",
            tr("file_filter_netcdf_all_short", "NetCDF (*.nc);;所有文件 (*)"),
        )
        if not path:
            return
        self._wind_file_edit.setText(path)
        self._set_button_file_chosen(self._wind_file_btn, path)

    # ── 二维谱 ────────────────────────────────────────────────────────────────

    def _build_spectrum_card(self, run_spectrum_all, run_spectrum_selected, run_spectrum_map) -> None:
        layout = self._card(tr("plotting_spectrum_card_title", "海浪二维方向谱绘图"))

        self._spectrum_table = TableWidget()
        self._spectrum_table.setColumnCount(3)
        self._spectrum_table.setHorizontalHeaderLabels(
            [tr("plotting_station", "站点"), tr("step3_longitude", "经度"), tr("step3_latitude", "纬度")]
        )
        self._spectrum_table.verticalHeader().setVisible(False)
        self._spectrum_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._spectrum_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for col in range(3):
            self._spectrum_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        self._spectrum_table.setMinimumHeight(120)
        self._spectrum_table.setVisible(False)  # 选择谱文件后才显示（与 src 一致）
        layout.addWidget(self._spectrum_table)

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(5)
        self._energy_edit = self._line("0.01", placeholder=tr("plotting_energy_threshold_example", "例如 0.01"))
        self._energy_edit.setValidator(double_validator(0.0, 1.0e12))
        grid.addWidget(QLabel(tr("plotting_energy_threshold", "最低能量密度：")), 0, 0)
        grid.addWidget(self._energy_edit, 0, 1)
        self._spectrum_timestep = self._line("24", placeholder=tr("plotting_default_24_hours", "默认 24 小时"))
        self._spectrum_timestep.setValidator(double_validator(0.0, 1.0e12))
        grid.addWidget(QLabel(tr("plotting_timestep_hours_label", "时间步长 (小时):")), 1, 0)
        grid.addWidget(self._spectrum_timestep, 1, 1)
        self._spectrum_mode = ComboBox()
        self._spectrum_mode.addItems([tr("plotting_mode_normalized", "最大值归一化"), tr("plotting_mode_actual", "实际值")])
        self._spectrum_mode.setCurrentText(tr("plotting_mode_actual", "实际值"))
        self._spectrum_mode.setStyleSheet(styles.combo_style())
        left_align_combo_text(self._spectrum_mode)
        self._spectrum_mode.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        grid.addWidget(QLabel(tr("plotting_plot_mode", "绘制方式:")), 2, 0)
        grid.addWidget(self._spectrum_mode, 2, 1)
        layout.addLayout(grid)

        self._spectrum_file = self._line()
        self._spectrum_file_btn = self._button(tr("plotting_choose_spectrum_file", "选择二维谱文件"), self._on_spectrum_file_picked)
        layout.addWidget(self._spectrum_file_btn)
        layout.addWidget(self._button(tr("plotting_show_on_map", "显示在地图上"), run_spectrum_map))
        self._add_gen_view_pair(
            layout,
            (
                tr("plotting_generate_all_spectrum", "生成所有二维谱图"),
                run_spectrum_all,
                SUBDIR_DIRECTIONAL_SPECTRUM,
            ),
            (
                tr("plotting_generate_selected_spectrum", "生成选中站点的二维谱图"),
                run_spectrum_selected,
                SUBDIR_DIRECTIONAL_SPECTRUM,
            ),
        )

    def _on_spectrum_file_picked(self) -> None:
        """选择二维谱文件并自动加载站点信息到表格。"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("plotting_choose_spectrum_file", "选择二维谱文件"),
            self._spectrum_file.text().strip() or "",
            tr("file_filter_netcdf_all_short", "NetCDF (*.nc);;所有文件 (*)"),
        )
        if not path:
            return
        self._spectrum_file.setText(path)
        self._set_button_file_chosen(self._spectrum_file_btn, path)
        self._load_spectrum_stations(path)

    def _load_spectrum_stations(self, spec_file_path: str) -> None:
        """从二维谱文件读取站点信息填入表格。"""
        if not spec_file_path or not os.path.exists(spec_file_path):
            return
        try:
            import numpy as np
            from netCDF4 import Dataset

            with Dataset(spec_file_path, "r") as ds:
                if "longitude" not in ds.variables or "latitude" not in ds.variables:
                    return

                lon_var = ds.variables["longitude"]
                lat_var = ds.variables["latitude"]
                name_var = ds.variables.get("station_name")

                if "station" in ds.dimensions:
                    n_stations = len(ds.dimensions["station"])
                else:
                    n_stations = len(lon_var) if hasattr(lon_var, "__len__") else 1

                lon = np.array(lon_var[:]).flatten()
                lat = np.array(lat_var[:]).flatten()

                station_names = []
                if name_var is not None:
                    try:
                        raw_names = np.array(name_var[:])
                        for row in raw_names[:n_stations]:
                            name = b"".join(row.tolist()).decode("utf-8", "ignore").strip()
                            station_names.append(name.replace("\x00", "").strip())
                    except Exception:
                        station_names = []

                self._spectrum_table.setRowCount(0)
                for i in range(min(n_stations, len(lon), len(lat))):
                    row = self._spectrum_table.rowCount()
                    self._spectrum_table.insertRow(row)
                    from PyQt6.QtWidgets import QTableWidgetItem
                    self._spectrum_table.setItem(row, 0, QTableWidgetItem(f"{float(lon[i]):.6f}"))
                    self._spectrum_table.setItem(row, 1, QTableWidgetItem(f"{float(lat[i]):.6f}"))
                    sname = station_names[i] if i < len(station_names) else str(i)
                    self._spectrum_table.setItem(row, 2, QTableWidgetItem(sname))

                self._spectrum_table.setVisible(True)
        except Exception:
            pass

    # ── 波高图 ────────────────────────────────────────────────────────────────

    def _build_wave_card(self, run_wave_maps, run_wind_swell, run_contour, run_wave_video, open_photo_folder) -> None:
        layout = self._card(tr("plotting_wave_card_title", "波高图绘制"))
        ts_row = QHBoxLayout()
        ts_row.setSpacing(5)
        ts_row.addWidget(QLabel(tr("plotting_timestep_label", "时间步长：")))
        self._wave_timestep = self._line("6")
        self._wave_timestep.setValidator(double_validator(0.0, 1.0e12))
        ts_row.addWidget(self._wave_timestep, 1)
        ts_row.addWidget(QLabel(tr("hours", "小时")))
        layout.addLayout(ts_row)

        self._wave_file = self._line()
        self._wave_file_btn = self._button(tr("plotting_choose_wave_file", "选择波高文件"), self._pick_wave_file)
        layout.addWidget(self._wave_file_btn)
        self._add_gen_view_row(
            layout, tr("plotting_generate_wave_maps", "生成波高图"), run_wave_maps, SUBDIR_WAVE_HEIGHT
        )
        self._add_gen_view_row(
            layout, tr("plotting_generate_wind_swell", "生成风涌浪图"), run_wind_swell, SUBDIR_WIND_SWELL
        )
        self._add_gen_view_row(
            layout, tr("plotting_generate_contour", "生成等高线图"), run_contour, SUBDIR_WAVE_HEIGHT_CONTOUR
        )
        self._add_gen_view_row(
            layout, tr("plotting_generate_wave_video", "生成波高视频"), run_wave_video, SUBDIR_WAVE_HEIGHT_VIDEO
        )
        layout.addWidget(self._button(tr("plotting_open_photo_folder", "打开图片文件夹"), open_photo_folder))

    def _pick_wave_file(self) -> None:
        """选择波高文件后更新按钮文字为文件名并改为蓝色。"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("select_file", "选择文件"),
            self._wave_file.text().strip() or "",
            tr("file_filter_netcdf_all_short", "NetCDF (*.nc);;所有文件 (*)"),
        )
        if not path:
            return
        self._wave_file.setText(path)
        self._set_button_file_chosen(self._wave_file_btn, path)

    # ── 取值 ──────────────────────────────────────────────────────────────────

    def spectrum_station(self) -> int:
        row = self._spectrum_table.currentRow()
        return row if row >= 0 else 0

    def jason3_lon_lat(self) -> list[float] | None:
        return self._collect_lon_lat(self._jason3_fields)

    def jason3_time_range(self) -> list[str] | None:
        return self._collect_time_range(self._jason3_fields)

    def jason3_folder(self) -> str:
        return self._jason3_fields["folder"].text().strip()

    def ndbc_lon_lat(self) -> list[float] | None:
        return self._collect_lon_lat(self._ndbc_fields)

    def ndbc_time_range(self) -> list[str] | None:
        return self._collect_time_range(self._ndbc_fields)

    def ndbc_folder(self) -> str:
        return self._ndbc_fields["folder"].text().strip()

    def wave_maps_params(self) -> dict:
        """返回波高绘图参数（时间步长、波高文件）。"""
        try:
            time_step = float(self._wave_timestep.text().strip() or "6")
        except ValueError:
            time_step = 6.0
        if time_step <= 0:
            time_step = 6.0
        return {
            "time_step_hours": time_step,
            "wave_file": self._wave_file.text().strip(),
        }

    def wind_field_params(self) -> dict:
        """返回风场绘图参数。"""
        try:
            time_step = float(self._wind_timestep.text().strip() or "24")
        except ValueError:
            time_step = 24.0
        flag_type = self._wind_flag_combo.currentText()
        try:
            density = max(1, int(float(self._wind_density.text().strip() or "10")))
        except ValueError:
            density = 10
        wind_file = self._wind_file_edit.text().strip()
        return {
            "time_step_hours": time_step,
            "flag_type": flag_type,
            "density_step": density,
            "wind_file": wind_file,
        }

    def spectrum_file_path(self) -> str:
        return self._spectrum_file.text().strip()

    @staticmethod
    def _collect_lon_lat(fields: dict[str, LineEdit]) -> list[float] | None:
        texts = [
            fields["lon_west"].text().strip(),
            fields["lon_east"].text().strip(),
            fields["lat_south"].text().strip(),
            fields["lat_north"].text().strip(),
        ]
        if not all(texts):
            return None
        try:
            return [float(t) for t in texts]
        except ValueError:
            return None

    @staticmethod
    def _collect_time_range(fields: dict[str, LineEdit]) -> list[str] | None:
        start = fields["start"].text().strip()
        end = fields["end"].text().strip()
        return [start, end] if start and end else None
