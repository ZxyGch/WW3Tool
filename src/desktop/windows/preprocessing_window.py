"""Main desktop shell backed by src workflows instead of legacy src window code."""

from __future__ import annotations

import os
import posixpath
import re
import tempfile
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QTimer, QUrl, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QLabel,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QColor, QDesktopServices, QFont, QFontDatabase, QTextBlockFormat, QTextCursor
from qfluentwidgets import (
    ComboBox,
    FluentIcon,
    FluentWindow,
    InfoBar,
    LineEdit,
    MessageBox,
    NavigationItemPosition,
    PrimaryPushButton,
    Theme,
    setTheme,
    setThemeColor,
)

from workflows.application.configuration import ConfigError, EXAMPLE_YAML
from workflows.domain.config_models import GridRegion, PipelineConfig
from workflows.domain.forcing_fields import ForcingField, Step1Files
from workflows.infrastructure.runtime_config import (
    add_recent_workdir,
    get_forcing_field_default_dir,
    get_project_meshgen_path,
    load_config as _load_runtime_config,
    normalize_run_mode,
    set_active_params_path,
)
from workflows.infrastructure.adapters.grid_generation_adapter import (
    REFERENCE_DATA_REQUIRED_FILES,
)
from workflows.support.translations import tr

from ..background_runner import BackgroundRunner
from ..components.forcing_progress_dialog import ForcingProgressDialog
from ..components.image_gallery_drawer import ImageGalleryHost
from ..components import styles
from ..components.section_title import apply_section_title_style, create_section_title
from .settings_window import SettingsInterface
from .plot_window import PlotInterface
from .tools_window import ToolsInterface, delete_all_under, delete_run_artifacts_under
from ..components.region_map_dialog import RegionMapDialog
from ..qt_callback_dispatcher import QtCallbackDispatcher
from ..steps import CalculationStepPanel, ForcingStepPanel, GridStepPanel, WW3StepPanel
from ..view_models.forcing_step import ForcingStepState, ForcingStepViewModel
from ..view_models.pipeline import PipelineStepState, PipelineViewModel
from ..view_models.plot import PlotViewModel
from ..view_models.remote import RemoteViewModel
from ..view_models.local_run import LocalRunViewModel
from ..steps.local_run_panel import LocalRunPanel
from ..steps.server_connect_panel import ServerConnectPanel
from ..steps.server_ops_panel import ServerOpsPanel

from ..components.scroll_area import NoHScrollArea

# [EN] Unified log area line spacing: extra pixel value for consistent CJK/Latin line height.
# 日志区统一行距：额外像素值，让中英文行高一致。
_LOG_LINE_SPACING_EXTRA_PX = 3
try:
    _LH_LINE_DISTANCE = QTextBlockFormat.LineHeightTypes.LineDistanceHeight.value
except AttributeError:
    _LH_LINE_DISTANCE = 4  # Qt: LineDistanceHeight


class PreprocessingWindow(FluentWindow, ImageGalleryHost):
    """Workflow-backed preprocessing UI with CLI/GUI separation."""

    def __init__(self) -> None:
        setTheme(Theme.AUTO)
        setThemeColor(QColor(0, 120, 212))
        super().__init__()
        self._base_title = tr("app_title", "海浪模式 WAVEWATCH III 可视化运行软件")
        self.setWindowTitle(self._base_title)
        _lang = _load_runtime_config().get("LANGUAGE", "zh_CN")
        _width = 1300 if str(_lang).startswith("en") else 1200
        self.resize(_width, 760)
        self._match_legacy_titlebar_buttons()
        self._params_path: Path | None = None
        self._loaded_config: PipelineConfig | None = None
        self._busy = False
        self._forcing_progress: ForcingProgressDialog | None = None
        self._map_preview_path: Path | None = None
        self._runner = BackgroundRunner(self)
        self._forcing_updates = QtCallbackDispatcher(
            on_log=self._append_log,
            on_state_change=self._render_forcing_state,
            parent=self,
        )
        self._pipeline_updates = QtCallbackDispatcher(
            on_log=self._append_log,
            on_state_change=self._render_pipeline_state,
            parent=self,
        )
        self._forcing_vm = ForcingStepViewModel(
            on_log=self._forcing_updates.post_log,
            on_state_change=self._forcing_updates.post_state,
        )
        self._pipeline_vm = PipelineViewModel(
            on_log=self._pipeline_updates.post_log,
            on_state_change=self._pipeline_updates.post_state,
        )
        self._plot_vm = PlotViewModel(on_log=self._pipeline_updates.post_log)
        self._remote_vm = RemoteViewModel(on_log=self._pipeline_updates.post_log)
        self._local_vm = LocalRunViewModel(on_log=self._pipeline_updates.post_log)
        self._paths: dict[str, LineEdit] = {}
        self._paths["workdir"] = LineEdit(self)
        self._paths["workdir"].hide()
        self._path_buttons: dict[str, PrimaryPushButton] = {}
        self._display_fields: dict[str, LineEdit] = {}
        self._params_label = LineEdit(self)
        self._params_label.hide()
        self._build_surface()
        self._last_dark_theme = self._is_dark_theme()
        self._setup_theme_monitor()
        if str(_load_runtime_config().get("LANGUAGE", "zh_CN")).startswith("en"):
            self._append_log("Developed by Gong Chuheng, Shanghai Ocean University, Sep 2025. Assisted by Han Ziqi, supervised by Prof. Wei Yongliang")
        else:
            self._append_log("本软件由上海海洋大学宫楚恒于 2025 年 9 月开发，师兄韩梓琪帮助，导师魏永亮")

    def _match_legacy_titlebar_buttons(self) -> None:
        if hasattr(self, "setSystemTitleBarButtonVisible"):
            self.setSystemTitleBarButtonVisible(False)
        for button_name in ("minBtn", "maxBtn", "closeBtn"):
            button = getattr(getattr(self, "titleBar", None), button_name, None)
            if button is not None:
                button.show()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self.titleBar.raise_()
        self.sync_image_gallery_geometry()

    def _is_dark_theme(self) -> bool:
        color = self.palette().color(self.palette().ColorRole.Window)
        return color.lightness() < 128

    def _setup_theme_monitor(self) -> None:
        app = QApplication.instance()
        if app is not None and hasattr(app, "paletteChanged"):
            app.paletteChanged.connect(self._on_palette_changed)

    def _on_palette_changed(self, _palette) -> None:
        dark = self._is_dark_theme()
        if dark == self._last_dark_theme:
            return
        self._last_dark_theme = dark
        setTheme(Theme.DARK if dark else Theme.LIGHT)
        self._refresh_manual_styles()

    def _refresh_manual_styles(self) -> None:
        for button in self.findChildren(PrimaryPushButton):
            button.setStyleSheet(self._button_style())
        if hasattr(self, "_forcing_panel"):
            self._forcing_panel.apply_clear_button_style(self._button_style())
        for field in self.findChildren(LineEdit):
            field.setStyleSheet(self._input_style())
        for combo in self.findChildren(ComboBox):
            combo.setStyleSheet(self._combo_style())
        for label in self.findChildren(QLabel):
            if label.objectName() == "headerLabel":
                continue
            if label.property("sectionTitle"):
                apply_section_title_style(label)
            elif label.styleSheet().strip() and "font-size" not in label.styleSheet():
                label.setStyleSheet(styles.label_style())
        if hasattr(self, "_log"):
            self._log.setStyleSheet(self._log_style())

    def _button_style(self) -> str:
        if self._is_dark_theme():
            return """
                PrimaryPushButton {
                    background-color: #2D2D2D; border: 1px solid #404040;
                    border-radius: 4px; min-height: 20px; padding: 8px 16px; color: #FFFFFF;
                }
                PrimaryPushButton:hover { background-color: #3D3D3D; }
                PrimaryPushButton:pressed { background-color: #353535; }
                PrimaryPushButton:disabled { background-color: #1D1D1D; color: #666666; }
                PrimaryPushButton[filled="true"] { color: #2E6BD9; }
            """
        return """
            PrimaryPushButton {
                background-color: #F5F5F5; border: 1px solid #E0E0E0;
                border-radius: 4px; min-height: 20px; padding: 8px 16px;
            }
            PrimaryPushButton:hover { background-color: #EEEEEE; }
            PrimaryPushButton:pressed { background-color: #E8E8E8; }
            PrimaryPushButton:disabled { background-color: #E0E0E0; color: #999999; }
            PrimaryPushButton[filled="true"] { color: #2E6BD9; }
        """

    def _input_style(self) -> str:
        if self._is_dark_theme():
            return """
                LineEdit {
                    background-color: #2D2D2D; border: 1px solid #404040;
                    border-radius: 4px; padding: 4px 8px; color: #FFFFFF;
                }
                LineEdit:focus { border: 1px solid #404040; }
            """
        return """
            LineEdit {
                background-color: #FFFFFF; border: 1px solid #D0D0D0;
                border-radius: 4px; padding: 4px 8px; color: #000000;
            }
            LineEdit:focus { border: 1px solid #D0D0D0; }
        """

    def _combo_style(self) -> str:
        if self._is_dark_theme():
            return """
                ComboBox {
                    background-color: #2D2D2D; border: 1px solid #404040;
                    border-radius: 4px; padding: 4px 8px; color: #FFFFFF;
                    text-align: left;
                }
                ComboBox:disabled { color: #FFFFFF; }
            """
        return """
            ComboBox {
                background-color: #FFFFFF; border: 1px solid #D0D0D0;
                border-radius: 4px; padding: 4px 8px; color: #000000;
                text-align: left;
            }
            ComboBox:disabled { color: #000000; }
        """

    def _log_style(self) -> str:
        if self._is_dark_theme():
            return (
                "QTextEdit { background-color: #2d2d2d; border: 0.5px solid #404040;"
                " border-radius: 4px; padding-left: 2px; }"
                " QTextEdit:focus { border: 0.5px solid #404040; padding-left: 2px; }"
                " QTextEdit:hover { border: 0.5px solid #404040; padding-left: 2px; }"
            )
        return (
            "QTextEdit { background-color: transparent; border: 0.5px solid #D0D0D0;"
            " border-radius: 4px; padding-left: 2px; }"
            " QTextEdit:focus { border: 0.5px solid #D0D0D0; padding-left: 2px; }"
            " QTextEdit:hover { border: 0.5px solid #D0D0D0; padding-left: 2px; }"
        )

    def _primary_button(self, text: str, handler) -> PrimaryPushButton:
        button = PrimaryPushButton(text)
        button.setStyleSheet(self._button_style())
        button.clicked.connect(handler)
        return button

    # Keep the presentation helpers named like the original desktop surface.
    def _get_button_style(self) -> str:
        return self._button_style()

    def _get_input_style(self) -> str:
        return self._input_style()

    def _section_title(self, text: str) -> QWidget:
        return create_section_title(text)

    def _build_surface(self) -> None:
        if hasattr(self, "navigationInterface"):
            self.navigationInterface.setReturnButtonVisible(False)

        main_interface = QWidget()
        main_interface.setObjectName("main_interface")
        main_interface.setStyleSheet("QWidget#main_interface { background: transparent; border: none; }")
        main_layout = QVBoxLayout(main_interface)
        main_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(
            """
            QSplitter::handle:horizontal {
                background-color: #64AADE;
                border-width: 2px;
                border-radius: 0.8px;
                margin: 330px 2px;
            }
            QSplitter::handle:horizontal:hover {
                background-color: #909090;
            }
            """
        )
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_log_panel())
        splitter.setStretchFactor(0, 33)
        splitter.setStretchFactor(1, 67)
        main_layout.addWidget(splitter)
        self.main_splitter = splitter
        self._main_interface = main_interface
        self.bind_image_gallery(main_interface)

        home_item = self.addSubInterface(
            main_interface,
            FluentIcon.HOME,
            tr("home", "主页"),
            NavigationItemPosition.TOP,
            isTransparent=True,
        )
        # [EN] "Settings" is a page in the left stacked widget (right-side log is shared), navigation only switches stacked pages.
        # 「设置」是左侧堆叠里的一页（右侧日志栏常驻共享），导航仅切换堆叠页。
        home_item.clicked.connect(lambda *_: self._show_home())
        self.navigationInterface.addItem(
            routeKey="plot",
            icon=self._navigation_icon("PALETTE", "PHOTO", "PIE_SINGLE"),
            text=tr("plot", "绘图"),
            onClick=self._show_plot_page,
            selectable=True,
            position=NavigationItemPosition.TOP,
        )
        self.navigationInterface.addItem(
            routeKey="tools",
            icon=self._navigation_icon("DEVELOPER_TOOLS", "BROOM", "COMMAND_PROMPT", "APPLICATION"),
            text=tr("tools", "工具"),
            onClick=lambda: self.left_stacked.setCurrentIndex(3),
            selectable=True,
            position=NavigationItemPosition.TOP,
        )
        self.navigationInterface.addItem(
            routeKey="settings",
            icon=self._navigation_icon("SETTING", "SETTING_FILLED"),
            text=tr("settings", "设置"),
            onClick=lambda: self.left_stacked.setCurrentIndex(1),
            selectable=True,
            position=NavigationItemPosition.BOTTOM,
        )
        self._add_navigation_commands()
        QTimer.singleShot(0, lambda: splitter.setSizes([400, 800, 0]))

    def _navigation_icon(self, *names: str):
        for name in names:
            icon = getattr(FluentIcon, name, None)
            if icon is not None:
                return icon
        return FluentIcon.DOCUMENT

    def _add_navigation_commands(self) -> None:
        self.navigationInterface.addItem(
            routeKey="open-workdir",
            icon=self._navigation_icon("LINK", "FOLDER_OPEN", "FOLDER"),
            text=tr("open_workdir", "打开工作目录"),
            onClick=self._open_work_directory,
            selectable=False,
            position=NavigationItemPosition.TOP,
        )
        self.navigationInterface.addItem(
            routeKey="choose-workdir",
            icon=self._navigation_icon("FOLDER_ADD", "FOLDER"),
            text=tr("choose_workdir", "选择工作目录"),
            onClick=self._choose_work_directory,
            selectable=False,
            position=NavigationItemPosition.TOP,
        )
        self.navigationInterface.addItem(
            routeKey="clear-log",
            icon=self._navigation_icon("DELETE", "REMOVE"),
            text=tr("clear_log", "清空日志"),
            onClick=self._log.clear,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )

    def _build_left_panel(self) -> QWidget:
        left_content = QWidget()
        left_content.setStyleSheet("QWidget { background-color: transparent; }")
        left_layout = QVBoxLayout(left_content)
        left_layout.setContentsMargins(0, 0, 5, 10)
        left_layout.setSpacing(0)

        self.left_stacked = QStackedWidget()
        self.left_stacked.setStyleSheet("QStackedWidget { background-color: transparent; }")

        scroll = NoHScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            """
            QScrollArea {
                background-color: transparent;
                border: none;
                margin: 0px;
                padding: 0px;
            }
            QScrollArea > QWidget > QWidget {
                margin: 0px;
                padding: 0px;
            }
            """
        )

        content_widget = QWidget()
        content_widget.setStyleSheet("QWidget { background-color: transparent; margin: 0px; padding: 0px; }")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._build_step_panels(content_widget, content_layout)

        scroll.setWidget(content_widget)
        self._steps_scroll = scroll
        self.left_stacked.addWidget(scroll)  # [EN] index 0: preprocessing steps
        # index 0：预处理步骤
        self._settings_interface = SettingsInterface(
            on_language_changed=self._restart_for_language_change,
            on_run_mode_changed=self._on_run_mode_changed_from_settings,
            on_config_changed=self._on_settings_config_changed,
        )
        self.left_stacked.addWidget(self._settings_interface)  # [EN] index 1: settings page (shares right-side log)
        # index 1：设置页（共享右侧日志）
        self._plot_interface = PlotInterface(
            run_jason3=self._plot_jason3,
            run_download_jason3=self._plot_download_jason3,
            run_jason3_swh=self._plot_jason3_swh,
            run_download_ndbc=self._plot_download_ndbc,
            run_match_ndbc=self._plot_match_ndbc,
            run_ndbc_station_map=self._plot_ndbc_station_map,
            run_spectrum_all=self._plot_spectrum_all,
            run_spectrum_selected=self._plot_spectrum_selected,
            run_spectrum_map=self._plot_spectrum_map,
            run_wave_maps=self._plot_wave_maps,
            run_wind_swell=self._plot_wind_swell,
            run_contour=self._plot_contour,
            run_wave_video=self._plot_wave_video,
            run_wind_field=self._plot_wind_field,
            view_photo_subdir=self._plot_view_photo_subdir,
            open_photo_folder=self._plot_open_photo_folder,
            log=self._append_log,
        )
        self.left_stacked.addWidget(self._plot_interface)  # [EN] index 2: plot page (shares right-side log)
        # index 2：绘图页（共享右侧日志）
        self._tools_interface = ToolsInterface(
            clean_all=self._tools_clean_all,
            clean_run=self._tools_clean_run,
            log=self._append_log,
            get_forcing_dir=lambda: str(get_forcing_field_default_dir() or ""),
        )
        self.left_stacked.addWidget(self._tools_interface)  # [EN] index 3: tools page (shares right-side log)
        # index 3：工具页（共享右侧日志）
        self.left_stacked.setCurrentIndex(0)
        left_layout.addWidget(self.left_stacked)
        QTimer.singleShot(200, self._update_run_mode_visibility)
        return left_content

    def _preserve_steps_scroll(self, fn) -> None:
        scroll = getattr(self, "_steps_scroll", None)
        if scroll is None:
            fn()
            return
        scroll.preserve_vertical_scroll(fn)

    def _scroll_steps_to_top(self) -> None:
        scroll = getattr(self, "_steps_scroll", None)
        if scroll is not None:
            scroll.scroll_to_top()

    def _on_run_mode_changed_from_settings(self, run_mode: str) -> None:
        self._update_run_mode_visibility(run_mode)
        mode_names = {
            "local": tr("run_mode_local", "本地运行"),
            "server": tr("run_mode_server", "服务器运行"),
            "both": tr("run_mode_both", "本地+服务器运行"),
        }
        self._append_log(
            tr("run_mode_switched", "✅ 已切换运行方式为: {mode}").format(
                mode=mode_names.get(run_mode, tr("unknown", "未知"))
            )
        )

    def _on_settings_config_changed(self, section: str) -> None:
        try:
            from workflows.infrastructure import runtime_config

            config = runtime_config.load_full_config()
        except Exception:
            return

        if section in {"st_versions", "output_schemes"}:
            self._refresh_home_st_and_output_options(config)
        if section in {"st_versions", "local_st_versions"} and hasattr(self, "_local_run_panel"):
            self._local_run_panel.refresh_st_versions()

    def _refresh_home_st_and_output_options(self, config: dict) -> None:
        st_names = self._server_st_names(config)
        default_st = str(config.get("DEFAULT_ST", "") or "")
        if hasattr(self, "_ww3_panel"):
            current = self._ww3_panel.st_combo.currentText().strip()
            selected = current if current in st_names else (default_st if default_st in st_names else (st_names[0] if st_names else ""))
            self._ww3_panel._replace_combo_items(self._ww3_panel.st_combo, st_names, selected)

            schemes = config.get("OUTPUT_VARS_SCHEMES", {})
            scheme_names = sorted(str(name) for name in schemes) if isinstance(schemes, dict) else []
            current_scheme = self._ww3_panel.output_scheme_combo.currentText().strip()
            selected_scheme = current_scheme if current_scheme in scheme_names else (scheme_names[0] if scheme_names else "")
            self._ww3_panel._replace_combo_items(self._ww3_panel.output_scheme_combo, scheme_names, selected_scheme)

        if hasattr(self, "_server_connect_panel"):
            current = self._server_connect_panel.st_combo.currentText().strip()
            selected = current if current in st_names else (default_st if default_st in st_names else (st_names[0] if st_names else ""))
            self._server_connect_panel._replace_combo_items(self._server_connect_panel.st_combo, st_names, selected)

    @staticmethod
    def _server_st_names(config: dict) -> list[str]:
        versions = config.get("ST_VERSIONS")
        if isinstance(versions, list):
            names = [
                str(item.get("name", "")).strip()
                for item in versions
                if isinstance(item, dict) and str(item.get("name", "")).strip()
            ]
            if names:
                return names
        options = config.get("ST_OPTIONS")
        if isinstance(options, list):
            return [str(item).strip() for item in options if str(item).strip()]
        return []

    def _update_run_mode_visibility(self, run_mode: str | None = None) -> None:
        # [EN] Show/hide local run / server steps and Step 4 Slurm config based on RUN_MODE (aligned with src).
        """根据 RUN_MODE 显隐本地运行 / 服务器步骤与 Step 4 Slurm 配置（对齐 src）。"""
        if run_mode is None:
            run_mode = normalize_run_mode(_load_runtime_config().get("RUN_MODE", "both"))

        show_local = run_mode in {"local", "both"}
        show_server = run_mode in {"server", "both"}

        if hasattr(self, "_local_run_panel"):
            self._local_run_panel.widget.setVisible(show_local)
        if hasattr(self, "_server_connect_panel"):
            self._server_connect_panel.widget.setVisible(show_server)
        if hasattr(self, "_server_ops_panel"):
            self._server_ops_panel.widget.setVisible(show_server)
        if hasattr(self, "_ww3_panel"):
            self._ww3_panel.set_slurm_visible(False)

    def _build_step_panels(self, parent: QWidget, layout: QVBoxLayout) -> None:
        self._forcing_panel = ForcingStepPanel(
            parent,
            create_button=self._primary_button,
            input_style=self._input_style,
            combo_style=self._combo_style,
            browse_path=self._browse_path,
            clear_path=self._clear_forcing_path,
            show_file_info=self._show_forcing_files_info,
            crop_import=self._crop_forcing_import,
            direct_import=self._direct_forcing_import,
            load_intersection=self._load_forcing_intersection,
            view_map=self._view_forcing_region_map,
            mode_changed=self._on_forcing_mode_changed,
        )
        self._paths.update(self._forcing_panel.paths)
        self._path_buttons.update(self._forcing_panel.path_buttons)
        self._mode = self._forcing_panel.mode
        self._auto_associate = self._forcing_panel.auto_associate
        self._forcing_status = self._forcing_panel.status
        layout.addWidget(self._forcing_panel.widget)

        self._grid_panel = GridStepPanel(
            parent,
            create_button=self._primary_button,
            input_style=self._input_style,
            combo_style=self._combo_style,
            section_title=self._section_title,
            nested_factor=self._nested_factor,
            load_bounds=self._load_wind_bounds,
            view_map=self._view_region_map,
            generate_grid=self._generate_grid,
            visualize_grid=self._visualize_grid,
            recommend_params=self._recommend_grid_params,
        )
        self._display_fields.update(self._grid_panel.fields)
        self._outer_grid_title = self._grid_panel.outer_grid_title
        self._grid_type_combo = self._grid_panel.grid_type_combo
        self._mesh_type_combo = self._grid_panel.mesh_type_combo
        self._grid_type_label = self._grid_panel.grid_type_label
        self._skip_grid = self._grid_panel.skip_grid
        self._load_bounds_button = self._grid_panel.load_bounds_button
        self._map_button = self._grid_panel.map_button
        self._grid_button = self._grid_panel.grid_button
        self._visualize_button = self._grid_panel.visualize_button
        self._step2_action_buttons = self._grid_panel.action_buttons
        layout.addWidget(self._grid_panel.widget)

        self._calculation_panel = CalculationStepPanel(
            parent,
            create_button=self._primary_button,
            combo_style=self._combo_style,
            input_style=self._input_style,
            button_style=self._button_style,
            bounds_provider=self._calc_grid_bounds,
            notify=self._append_log,
        )
        self._calc_mode_combo = self._calculation_panel.mode_combo
        layout.addWidget(self._calculation_panel.widget)

        self._ww3_panel = WW3StepPanel(
            parent,
            create_button=self._primary_button,
            input_style=self._input_style,
            combo_style=self._combo_style,
            section_title=self._section_title,
            load_time_range=self._load_wind_time_range,
            auto_configure_timesteps=self._auto_configure_timesteps,
            run_pipeline=self._apply_ww3_params_only,
        )
        self._display_fields.update(self._ww3_panel.fields)
        self._st_combo = self._ww3_panel.st_combo
        self._cpu_combo = self._ww3_panel.cpu_combo
        self._output_scheme_combo = self._ww3_panel.output_scheme_combo
        self._pipeline_status = self._ww3_panel.status
        self._ww3_panel.set_slurm_visible(False)
        self._action_buttons = [
            *self._step2_action_buttons,
            self._ww3_panel.load_time_button,
            self._ww3_panel.run_button,
        ]
        layout.addWidget(self._ww3_panel.widget)

        self._local_run_panel = LocalRunPanel(
            parent,
            create_button=self._primary_button,
            input_style=self._input_style,
            local_run=self._local_run,
            stop=self._local_stop,
        )
        layout.addWidget(self._local_run_panel.widget)

        self._server_connect_panel = ServerConnectPanel(
            parent,
            create_button=self._primary_button,
            input_style=self._input_style,
            combo_style=self._combo_style,
            connect=self._server_connect,
            confirm_slurm=self._server_confirm_slurm,
            inject_ntfy=self._server_inject_ntfy,
            watch_job_ntfy=self._server_watch_ntfy_job,
            node_status=self._server_node_status,
            cancel=self._server_cancel,
        )
        self._st_combo = self._server_connect_panel.st_combo
        self._cpu_combo = self._server_connect_panel.cpu_combo
        layout.addWidget(self._server_connect_panel.widget)

        self._server_ops_panel = ServerOpsPanel(
            parent,
            create_button=self._primary_button,
            input_style=self._input_style,
            list_files=self._server_list_files,
            queue=self._server_queue,
            upload=self._server_upload,
            upload_without_forcing=self._server_upload_without_forcing,
            submit=self._server_submit,
            check=self._server_check,
            clear=self._server_clear,
            download_results=self._server_download_results,
            download_log=self._server_download_log,
            exec_command=self._server_exec_command,
        )
        layout.addWidget(self._server_ops_panel.widget)

    def _build_log_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 1, 10, 11)
        self._log = QTextEdit()
        mono_font = QFont(self.font())
        fallback_monos = [
            "Menlo",
            "Monaco",
            "Consolas",
            "SF Mono",
            "Courier New",
            "Liberation Mono",
            "DejaVu Sans Mono",
            "Noto Sans Mono",
        ]
        available = set(QFontDatabase.families())
        chosen = next((family for family in fallback_monos if family in available), None)
        if not chosen:
            chosen = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()
        mono_font.setFamily(chosen)
        self._log.setFont(mono_font)
        self._log.setReadOnly(True)
        self._log.setAcceptRichText(False)
        self._log.setUndoRedoEnabled(False)
        try:
            self._log.document().setMaximumBlockCount(5000)
        except Exception:
            pass
        self._log.setStyleSheet(self._log_style())
        self._log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._log, 1)
        return panel

    def _set_path_value(self, key: str, value: str, empty_text: str | None = None) -> None:
        self._paths[key].setText(value)
        button = self._path_buttons.get(key)
        if button is None:
            return
        if value:
            path = Path(value)
            button.setText(path.name or str(path))
            button.setToolTip(str(path))
            button.setProperty("filled", True)
        elif empty_text:
            button.setText(empty_text)
            button.setToolTip("")
            button.setProperty("filled", False)
        button.setStyleSheet(self._button_style())
        button.style().unpolish(button)
        button.style().polish(button)

    def _forcing_field_button_labels(self) -> dict[str, str]:
        return {
            "wind": tr("step1_choose_wind", "选择风场"),
            "current": tr("step1_choose_current", "选择流场"),
            "level": tr("step1_choose_level", "选择水位场"),
            "ice": tr("step1_choose_ice", "选择海冰场"),
        }

    def _forcing_field_names(self) -> dict[str, str]:
        return {
            "wind": tr("step1_field_wind", "风场"),
            "current": tr("step1_field_current", "流场"),
            "level": tr("step1_field_level", "水位场"),
            "ice": tr("step1_field_ice", "海冰场"),
        }

    def _resolve_auto_associate_from_config(self, config: PipelineConfig, defaults: dict) -> bool:
        aa = config.forcing.auto_associate
        if aa is None:
            aa = defaults.get("forcing", {}).get("auto_associate")
        return bool(aa) if aa is not None else True

    def _sync_forcing_options_from_config(self, config: PipelineConfig, defaults: dict) -> None:
        pm = config.forcing.process_mode or defaults.get("forcing", {}).get("process_mode") or "copy"
        self._forcing_panel.set_process_mode(pm if pm in {"copy", "move"} else "copy")
        self._auto_associate.setChecked(self._resolve_auto_associate_from_config(config, defaults))
        default_forcing = defaults.get("forcing", {}) if isinstance(defaults.get("forcing"), dict) else {}
        crop_time = config.forcing.crop_time_range or default_forcing.get("crop_time_range") or None
        crop_bbox = config.forcing.crop_bbox or default_forcing.get("crop_bbox") or None
        self._forcing_panel.set_range_values(time_range=crop_time, bbox=crop_bbox, overwrite_editable=True)
        self._on_forcing_mode_changed()

    def _scan_and_fill_forcing_buttons(self, workdir: str, *, auto_associate: bool | None = None) -> None:
        if not workdir or not os.path.isdir(workdir):
            return
        if auto_associate is None:
            auto_associate = self._auto_associate.isChecked()
        from workflows.infrastructure.forcing.file_service import FileService

        scanned = FileService().scan_forcing_files(workdir, auto_associate=auto_associate)
        labels = self._forcing_field_button_labels()
        for key in ("wind", "current", "level", "ice"):
            value = getattr(scanned, key, None)
            self._set_path_value(key, str(value) if value else "", labels[key])

    def _apply_workdir_ui(self, folder: str) -> None:
        # [EN] Only update workdir-related UI (fields/recent list/title), without triggering params adoption.
        """仅更新工作目录相关 UI（字段/最近列表/标题），不触发 params 采纳。"""
        folder = os.path.abspath(os.path.normpath(folder))
        self._set_path_value("workdir", folder, tr("choose_workdir", "选择工作目录"))
        self.selected_folder = folder
        add_recent_workdir(folder)
        self._append_log(tr("workdir_current", "📂 工作目录：{folder}").format(folder=folder))
        self.setWindowTitle(f"{self._base_title}  |  {tr('workdir_path', '工作目录:')} {folder}")
        # [EN] Refresh step 6 server path (append workdir name)
        # 刷新第六步服务器路径（追加工作目录名）
        self._refresh_server_path()
        if hasattr(self, "_plot_interface"):
            self._plot_interface.auto_detect_from_workdir(folder)
        self._scan_and_fill_forcing_buttons(folder)
        self._refresh_forcing_common_ranges(clear_if_empty=True)

    def _show_plot_page(self) -> None:
        # [EN] Switch to plot page and auto-detect wind.nc / ww3*.nc in workdir (aligned with src).
        """切换到绘图页，并自动检测工作目录中的 wind.nc / ww3*.nc（对齐 src）。"""
        if hasattr(self, "left_stacked") and self.left_stacked.count() >= 3:
            self.left_stacked.setCurrentIndex(2)
        workdir = getattr(self, "selected_folder", None)
        if not workdir and "workdir" in self._paths:
            workdir = self._paths["workdir"].text().strip() or None
        if hasattr(self, "_plot_interface"):
            self._plot_interface.auto_detect_from_workdir(workdir)

    def _restart_for_language_change(self, _code: str) -> None:
        """Rebuild the already-created widgets so translated text becomes visible."""
        params_path = self._params_path
        workdir = self._paths.get("workdir").text().strip() if "workdir" in self._paths else ""
        geometry = self.saveGeometry()
        new_window = PreprocessingWindow()
        new_window.restoreGeometry(geometry)
        if params_path and params_path.is_file():
            new_window.load_params_file(params_path)
        elif workdir:
            new_window.set_work_directory(workdir)
        new_window.show()
        app = QApplication.instance()
        if app is not None:
            setattr(app, "_ww3tool_window", new_window)
        self.close()

    def set_work_directory(self, folder: str | None) -> None:
        # [EN] Workdir entry: ensure params.yml exists in directory (generate from template + config.json if missing), and adopt as current.
        # [EN] All subsequent load/save operations target ``<workdir>/params.yml``.
        """工作目录入口：确保目录内有 params.yml（缺失则按模板+config.json 生成），并切为当前。

        之后所有载入/保存都针对 ``<workdir>/params.yml``。
        """
        if not folder:
            return
        folder = os.path.abspath(os.path.normpath(folder))
        target = Path(folder) / "params.yml"
        if not target.is_file():
            try:
                self._pipeline_vm.init_workdir_params(target, folder)
                self._append_log(tr("params_created_in_workdir", "已在工作目录创建 params.yml：{path}").format(path=target))
            except Exception as exc:
                self._show_error(tr("params_init_workdir_failed", "初始化工作目录 params.yml 失败：{error}").format(error=exc))
                self._apply_workdir_ui(folder)
                return
        self._load_params(target, update_workdir_ui=False)
        self._apply_workdir_ui(folder)

    def _open_work_directory(self) -> None:
        folder = self._paths["workdir"].text().strip()
        if folder and Path(folder).is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
            return
        self._show_error(tr("tools_clean_no_workdir", "请先选择工作目录"))

    def _choose_work_directory(self) -> None:
        from .work_folder_dialog import WorkFolderDialog

        current = getattr(self, "selected_folder", None)
        if not current and "workdir" in self._paths:
            current = self._paths["workdir"].text().strip() or None
        dialog = WorkFolderDialog(parent=self, current_folder=current)
        if dialog.exec() == dialog.DialogCode.Accepted and dialog.selected_folder:
            self.set_work_directory(dialog.selected_folder)
        self.titleBar.raise_()

    def _browse_params(self) -> None:
        start = str(self._params_path or Path.cwd())
        selected, _ = QFileDialog.getOpenFileName(
            self,
            tr("load_params_file", "载入参数文件"),
            start,
            tr("file_filter_yaml_all", "YAML 参数文件 (*.yml *.yaml);;所有文件 (*)"),
        )
        if selected:
            self._params_label.setText(selected)
            self._load_params(Path(selected))

    def _load_params_from_field(self) -> None:
        text = self._params_label.text().strip()
        if not text:
            self._show_error(tr("select_params_first", "请先选择 params.yml"))
            return
        self._load_params(Path(text))

    def _load_params(self, path: Path, *, update_workdir_ui: bool = True) -> None:
        try:
            config = self._pipeline_vm.load_config(path, validation_stage="plot")
        except Exception as exc:
            self._show_error(str(exc))
            return
        self._params_path = path.resolve()
        self._loaded_config = config
        self._params_label.setText(str(self._params_path))
        set_active_params_path(self._params_path)

        # [EN] Load defaults from root params.yml for fallback when workdir fields are empty
        # 从根 params.yml 加载默认值，供工作目录字段为空时回退使用
        defaults = self._load_root_defaults()
        self._sync_forcing_options_from_config(config, defaults)

        if update_workdir_ui:
            self._apply_workdir_ui(str(config.workdir.path))
        else:
            # set_work_directory：先同步 auto_associate，再按工作目录扫描强迫场
            self._scan_and_fill_forcing_buttons(str(config.workdir.path))
        self._render_summary(config)
        self._refresh_forcing_common_ranges(clear_if_empty=True)
        self._append_log(tr("params_loaded", "已载入参数文件：{path}").format(path=self._params_path))

    def _load_root_defaults(self) -> dict:
        # [EN] Load root params.yml raw dict, used as default fallback for new workdir creation.
        """加载根目录 params.yml 原始字典，用作新建工作目录的默认值回退。"""
        try:
            from workflows.infrastructure.runtime_config import _read_root_params
            return _read_root_params()
        except Exception:
            return {}

    def load_params_file(self, path: str | Path) -> None:
        """Public entry for startup or external callers."""
        self._load_params(Path(path))

    def _create_example_params(self) -> None:
        target, _ = QFileDialog.getSaveFileName(
            self,
            tr("save_example_params", "保存示例 params.yml"),
            str(Path.cwd() / "params.yml"),
            tr("file_filter_yaml", "YAML 参数文件 (*.yml *.yaml)"),
        )
        if not target:
            return
        path = Path(target)
        path.write_text(EXAMPLE_YAML, encoding="utf-8")
        self._params_label.setText(str(path))
        self._load_params(path)

    def _server_path_with_workdir(self, base_path: str) -> str:
        # [EN] Append current workdir name to server base path (do not append again if last segment matches).
        # [EN] Use posixpath since server paths are always Unix-style, even on Windows.
        """在服务器基础路径后追加当前工作目录名（末段相同时不重复追加）。"""
        if not base_path:
            return base_path
        workdir = getattr(self, "selected_folder", None)
        if not workdir and "workdir" in self._paths:
            workdir = self._paths["workdir"].text().strip()
        if workdir:
            name = os.path.basename(os.path.normpath(workdir))
            if name:
                base_name = posixpath.basename(base_path.rstrip("/"))
                if base_name == name:
                    return base_path.rstrip("/")
                return posixpath.join(base_path.rstrip("/"), name)
        return base_path

    def _refresh_server_path(self) -> None:
        # [EN] Refresh step 6 server path input field.
        # [EN] Always ensure workdir name is appended to the resolved base path.
        """刷新第六步服务器路径输入框。

        无论 remote_dir 是否为空，都通过 _server_path_with_workdir 确保末段包含工作目录名。
        """
        if not hasattr(self, "_server_ops_panel"):
            return
        cfg = self._loaded_config
        if cfg and cfg.server.remote_dir:
            self._server_ops_panel.set_server_path(self._server_path_with_workdir(cfg.server.remote_dir))
        else:
            base = cfg.server.default_remote_dir if cfg else ""
            self._server_ops_panel.set_server_path(self._server_path_with_workdir(base))

    def _effective_server_path(self, config: PipelineConfig) -> str:
        # [EN] Always ensure workdir name is appended to the resolved base path.
        """显示用服务器路径：始终确保末段包含工作目录名。"""
        if config.server.remote_dir:
            return self._server_path_with_workdir(config.server.remote_dir)
        return self._server_path_with_workdir(config.server.default_remote_dir)

    def _show_home(self) -> None:
        # [EN] Switch back to home step page and refresh step 6 server path.
        """切回主页步骤页，并刷新第六步服务器路径。"""
        self.left_stacked.setCurrentIndex(0)
        self._refresh_server_path()
        self._scroll_steps_to_top()

    def _render_summary(self, config: PipelineConfig) -> None:
        # [EN] Override config with current UI form forcing paths (ensure Step 4 shows latest selection)
        # 用当前 UI 表单中的强迫场路径覆盖 config（确保 Step 4 显示最新选择）
        for key in ("wind", "current", "level", "ice"):
            text = self._paths[key].text().strip()
            setattr(config.forcing, key, Path(text) if text else None)
        self._grid_panel.render(config.grid)
        self._calculation_panel.render(config.calc)
        self._ww3_panel.render(config)
        if hasattr(self, "_server_connect_panel"):
            self._server_connect_panel.render_slurm(config)
        if hasattr(self, "_server_ops_panel"):
            self._server_ops_panel.set_server_path(self._effective_server_path(config))
        self._scroll_steps_to_top()

    def _browse_path(self, key: str, directory: bool) -> None:
        current = self._paths[key].text().strip()
        if current:
            start = current
        elif key in {"wind", "current", "level", "ice"}:
            start = get_forcing_field_default_dir()
        else:
            start = str(Path.home())
        if directory:
            selected = QFileDialog.getExistingDirectory(self, tr("select_path", "选择路径"), start)
        else:
            selected, _ = QFileDialog.getOpenFileName(
                self,
                tr("choose_forcing_file", "选择强迫场文件"),
                start,
                tr("file_filter_netcdf_all", "NetCDF 文件 (*.nc *.nc4 *.cdf);;所有文件 (*)"),
            )
        if selected:
            self._set_path_value(key, selected)
            if key in {"wind", "current", "level", "ice"}:
                if not self._paths["workdir"].text().strip():
                    self._show_error(tr("tools_clean_no_workdir", "请先选择工作目录"))
                    return
                self._refresh_forcing_common_ranges(clear_if_empty=False)
                self._append_log(
                    tr(
                        "step1_wait_confirm_import",
                        "已选择强迫场文件。请确认导入方式后点击导入按钮。",
                    )
                )

    def _show_forcing_files_info(self) -> None:
        if self._busy:
            return
        files = Step1Files(
            wind=self._paths["wind"].text().strip() or None,
            current=self._paths["current"].text().strip() or None,
            level=self._paths["level"].text().strip() or None,
            ice=self._paths["ice"].text().strip() or None,
        )
        self._set_busy(True)

        def task():
            return self._forcing_vm.report_file_overviews(files)

        self._runner.run(task, self._on_forcing_info_done)

    def _on_forcing_info_done(self, result: object) -> None:
        self._set_busy(False)
        if isinstance(result, dict) and result.get("error"):
            self._show_error(str(result["error"]))

    def _require_params_path(self) -> Path | None:
        if self._params_path is not None:
            return self._params_path
        text = self._params_label.text().strip()
        if text:
            return Path(text)
        self._show_error(tr("load_params_first", "请先载入 params.yml"))
        return None

    def _current_workdir_params_path(self, *, create: bool = False) -> Path | None:
        workdir = self._paths["workdir"].text().strip()
        if not workdir:
            self._show_error(tr("tools_clean_no_workdir", "请先选择工作目录"))
            return None
        target = Path(workdir).expanduser().resolve() / "params.yml"
        if target.is_file():
            return target
        if not create:
            self._show_error(tr("params_missing_in_current_workdir", "当前工作目录缺少 params.yml：{path}").format(path=target))
            return None
        try:
            self._pipeline_vm.init_workdir_params(
                target, str(Path(workdir).expanduser().resolve())
            )
        except Exception as exc:
            self._show_error(tr("params_init_current_workdir_failed", "初始化当前工作目录 params.yml 失败：{error}").format(error=exc))
            return None
        self._append_log(tr("params_created_in_current_workdir", "已在当前工作目录创建 params.yml：{path}").format(path=target))
        return target

    def _build_forcing_config(self):
        process_mode = self._forcing_process_mode()
        apply_crop = bool(getattr(self, "_forcing_apply_crop", False))
        crop_time_range = self._forcing_crop_time_range() if apply_crop else []
        crop_bbox = self._forcing_crop_bbox() if apply_crop else []
        if apply_crop and (crop_time_range is None or crop_bbox is None):
            return None
        try:
            return self._forcing_vm.config_from_selection(
                workdir=self._paths["workdir"].text().strip(),
                wind=self._paths["wind"].text().strip(),
                current=self._paths["current"].text().strip(),
                level=self._paths["level"].text().strip(),
                ice=self._paths["ice"].text().strip(),
                process_mode=process_mode,
                auto_associate=self._auto_associate.isChecked(),
                crop_time_range=crop_time_range,
                crop_bbox=crop_bbox,
            )
        except ConfigError as exc:
            self._show_error(str(exc))
            return None

    def _form_overrides(self) -> dict:
        # [EN] Collect current form values from all panels (shared by run config building and params.yml writeback).
        """收集各面板当前表单值（供构建运行配置与写回 params.yml 共用）。"""
        return dict(
            workdir=self._paths["workdir"].text().strip(),
            wind=self._paths["wind"].text().strip(),
            current=self._paths["current"].text().strip(),
            level=self._paths["level"].text().strip(),
            ice=self._paths["ice"].text().strip(),
            process_mode=self._forcing_process_mode(),
            auto_associate=self._auto_associate.isChecked(),
            crop_time_range=[],
            crop_bbox=[],
            grid_overrides=self._grid_panel.overrides(),
            calc_mode=self._calculation_panel.mode,
            calc_points=self._calculation_panel.points(),
            calc_track_points=self._calculation_panel.track_points(),
            ww3_overrides={
                **self._ww3_panel.ww3_overrides(),
                **(
                    self._server_connect_panel.ww3_overrides()
                    if hasattr(self, "_server_connect_panel")
                    else {}
                ),
            },
            ww3_grid_overrides=self._ww3_panel.ww3_grid_overrides(),
            slurm_overrides=(
                self._server_connect_panel.slurm_overrides()
                if hasattr(self, "_server_connect_panel")
                else self._ww3_panel.slurm_overrides()
            ),
            server_overrides=self._server_overrides(),
        )

    def _server_overrides(self) -> dict:
        if hasattr(self, "_server_ops_panel"):
            remote_dir = self._server_ops_panel.remote_dir()
            if remote_dir:
                return {"remote_dir": remote_dir}
        return {}

    def _persist_server_remote_dir(self) -> bool:
        params_path = self._current_workdir_params_path(create=True)
        if params_path is None:
            return False
        remote_dir = self._server_ops_panel.remote_dir() if hasattr(self, "_server_ops_panel") else ""
        if not remote_dir:
            self._show_error(tr("server_path_required", "请先填写服务器路径"))
            return False
        try:
            destination = self._pipeline_vm.save_server_remote_dir(params_path, remote_dir)
        except Exception as exc:
            self._show_error(tr("server_path_save_failed", "保存服务器路径失败：{error}").format(error=exc))
            return False
        if getattr(self, "_server_polling_active", False):
            self._server_poll_config = self._build_poll_config()
        return True

    def _build_pipeline_config(self, *, validation_stage: str = "full", params_path: Path | None = None):
        params_path = params_path or self._require_params_path()
        if params_path is None:
            return None
        try:
            return self._pipeline_vm.config_from_form(
                params_path, validation_stage=validation_stage, **self._form_overrides()
            )
        except ConfigError as exc:
            self._show_error(str(exc))
            return None

    def _persist_current_form_to_workdir_params(
        self,
        *,
        validation_stage: str = "grid",
        log: bool = False,
    ) -> Path | None:
        # [EN] Unified entry for home page flow: first sync defaults from root params.yml, then write current form to workdir params.yml.
        """主页流程统一入口：先从根 params.yml 同步默认值，再把当前表单写入工作目录 params.yml。"""
        params_path = self._current_workdir_params_path(create=True)
        if params_path is None:
            return None
        try:
            self._pipeline_vm.sync_from_root(params_path)
            destination = self._pipeline_vm.save_form_to_params(
                params_path,
                validation_stage=validation_stage,
                **self._form_overrides(),
            )
        except ConfigError as exc:
            self._show_error(str(exc))
            return None
        except Exception as exc:
            self._show_error(tr("params_save_failed", "保存 params.yml 失败：{error}").format(error=exc))
            return None
        self._params_path = destination
        self._params_label.setText(str(destination))
        set_active_params_path(destination)
        if log:
            self._append_log(tr("params_saved", "已保存参数文件：{path}").format(path=destination))
        return destination

    def _config_from_current_workdir_params(
        self,
        *,
        validation_stage: str = "full",
        log: bool = True,
    ):
        params_path = self._persist_current_form_to_workdir_params(
            validation_stage="grid",
            log=log,
        )
        if params_path is None:
            return None
        try:
            return self._pipeline_vm.load_config(params_path, validation_stage=validation_stage)
        except ConfigError as exc:
            self._show_error(str(exc))
            return None
        except Exception as exc:
            self._show_error(tr("params_or_execution_error", "参数或执行错误") + f"：{exc}")
            return None

    def _calc_grid_bounds(self) -> dict | None:
        # [EN] Read grid lon/lat bounding box from params.yml (config.grid) for step 3 point validation.
        # [EN] Nested grids include every level rectangle for map display (union for click validation).
        """从 params.yml 的 config.grid 读取经纬度包围盒，供第三步点位校验。

        嵌套网格返回各层矩形列表（``levels``）及并集范围；选点须在并集内。
        """
        from ..steps.point_io import bounds_from_level_regions

        config = self._config_from_current_workdir_params(validation_stage="grid", log=False)
        if config is None:
            return None
        levels = config.grid.nested_levels or ([config.grid.outer] if config.grid.outer else [])
        n = len(levels)
        labels = []
        for i in range(n):
            if n == 1:
                labels.append(tr("step3_map_grid_range", "网格范围"))
            elif i == n - 1:
                labels.append(tr("step2_level_finest", "level{i}（最细）").format(i=i))
            else:
                labels.append(tr("step2_level_n", "level{i}").format(i=i))
        return bounds_from_level_regions(levels, level_labels=labels)

    def _persist_params(self) -> bool:
        # [EN] Write current form (including step 3 points) back to params.yml; report error and return False if points are incomplete.
        # [EN] Called alongside step 4 "Confirm Parameters" to persist form edits to disk.
        """将当前表单（含第三步点位）写回 params.yml；点位不全则报错并返回 False。

        在第四步「确认参数」时顺带调用，使表单编辑落盘。
        """
        mode = self._calculation_panel.mode
        if mode == "spectral_point" and not self._calculation_panel.points():
            self._show_error(tr("step3_spectral_points_required", "谱空间逐点计算需至少一个谱点"))
            return False
        if mode == "track" and not self._calculation_panel.track_points():
            self._show_error(tr("step3_track_points_required", "航迹模式需至少一个航迹点"))
            return False
        return self._persist_current_form_to_workdir_params() is not None

    def _prepare_forcing(self, *, fields: tuple[ForcingField, ...] | None = None) -> None:
        config = self._build_forcing_config()
        if config is None or self._busy:
            return
        self._set_busy(True)
        self._show_forcing_progress()

        def task():
            return self._forcing_vm.prepare(config, fields=fields)

        self._runner.run(task, self._on_forcing_done)

    def _forcing_process_mode(self) -> str:
        return self._forcing_panel.process_mode_value() if hasattr(self, "_forcing_panel") else "copy"

    def _selected_forcing_paths(self) -> list[str]:
        paths = []
        for key in ("wind", "current", "level", "ice"):
            value = self._paths[key].text().strip()
            if value:
                paths.append(value)
        return paths

    def _selected_forcing_fields(self) -> tuple[ForcingField, ...]:
        return tuple(
            ForcingField(key)
            for key in ("wind", "current", "level", "ice")
            if self._paths[key].text().strip()
        )

    def _is_workdir_converted_forcing_file(self, path: Path) -> bool:
        workdir_text = self._paths["workdir"].text().strip()
        if not workdir_text:
            return False
        try:
            workdir = Path(workdir_text).expanduser().resolve()
            candidate = path.expanduser().resolve()
        except OSError:
            return False
        if not candidate.is_file():
            return False
        try:
            relative = candidate.relative_to(workdir)
        except ValueError:
            return False
        if relative.parent != Path("."):
            return False
        if candidate.suffix.lower() != ".nc":
            return False
        from workflows.infrastructure.forcing.file_path_manager import FilePathManager

        return bool(FilePathManager.parse_forcing_filename(candidate.name))

    def _same_path_text(self, left: str, right: str) -> bool:
        try:
            return Path(left).expanduser().resolve() == Path(right).expanduser().resolve()
        except OSError:
            return os.path.abspath(os.path.normpath(left)) == os.path.abspath(os.path.normpath(right))

    def _clear_forcing_path(self, key: str) -> None:
        if key not in {"wind", "current", "level", "ice"} or self._busy:
            return
        value = self._paths[key].text().strip()
        if not value:
            return
        labels = self._forcing_field_button_labels()
        field_names = self._forcing_field_names()
        path = Path(value)
        delete_file = self._is_workdir_converted_forcing_file(path)
        if delete_file:
            box = MessageBox(
                tr("step1_delete_forcing_title", "删除已转换强迫场文件"),
                tr(
                    "step1_delete_forcing_content",
                    "将删除当前工作目录中的已转换强迫场文件，并清除引用它的选择。此操作不可恢复。\n\n{path}",
                ).format(path=str(path)),
                self,
            )
            if not box.exec():
                self.titleBar.raise_()
                return
            self.titleBar.raise_()
            try:
                path.expanduser().resolve().unlink()
                self._append_log(tr("step1_forcing_file_deleted", "🗑️ 已删除工作目录强迫场文件：{path}").format(path=value))
            except OSError as exc:
                self._show_error(tr("step1_forcing_file_delete_failed", "删除强迫场文件失败：{error}").format(error=exc))
                return
            cleared_keys = [
                field_key
                for field_key in ("wind", "current", "level", "ice")
                if self._paths[field_key].text().strip()
                and self._same_path_text(self._paths[field_key].text().strip(), value)
            ]
        else:
            cleared_keys = [key]

        for field_key in cleared_keys:
            self._set_path_value(field_key, "", labels[field_key])
        if not delete_file:
            self._append_log(
                tr("step1_forcing_selection_cleared", "已清除{field}选择").format(
                    field=field_names.get(key, key)
                )
            )
        self._refresh_forcing_common_ranges(clear_if_empty=True)

    def _forcing_crop_time_range(self, *, silent: bool = False) -> list[str] | None:
        values = self._forcing_panel.crop_time_range()
        if len(values) == 2 and all(values) and all(re.fullmatch(r"\d{8}", value) for value in values):
            return values
        if not silent:
            self._show_error(tr("step1_crop_time_required", "范围裁剪需要填写 YYYYMMDD 格式的开始日期和结束日期"))
        return None

    def _forcing_crop_bbox(self, *, silent: bool = False) -> list[float] | None:
        try:
            return self._forcing_panel.crop_bbox()
        except ValueError:
            if not silent:
                self._show_error(tr("step1_crop_bbox_required", "范围裁剪需要填写有效的西/东/南/北边界"))
            return None

    def _on_forcing_mode_changed(self) -> None:
        self._forcing_panel.set_range_editable(True)

    def _prepare_selected_forcing(self, *, apply_crop: bool) -> None:
        if self._busy:
            return
        if not self._paths["workdir"].text().strip():
            self._show_error(tr("tools_clean_no_workdir", "请先选择工作目录"))
            return
        fields = self._selected_forcing_fields()
        if not fields:
            self._show_error(tr("step1_select_forcing_first", "请先选择至少一个强迫场文件"))
            return
        if apply_crop and (self._forcing_crop_time_range() is None or self._forcing_crop_bbox() is None):
            return
        self._forcing_apply_crop = apply_crop
        self._prepare_forcing(fields=fields)

    def _crop_forcing_import(self) -> None:
        self._prepare_selected_forcing(apply_crop=True)

    def _direct_forcing_import(self) -> None:
        self._prepare_selected_forcing(apply_crop=False)

    def _forcing_map_regions(self) -> tuple[list[GridRegion], list[str]] | None:
        from workflows.application.grid_tools import read_wind_bounds

        labels = self._forcing_field_names()
        regions: list[GridRegion] = []
        region_labels: list[str] = []
        for key in ("wind", "current", "level", "ice"):
            path = self._paths[key].text().strip()
            if not path:
                continue
            bounds = read_wind_bounds(path)
            regions.append(
                GridRegion(
                    lon=[bounds.lon_min, bounds.lon_max],
                    lat=[bounds.lat_min, bounds.lat_max],
                )
            )
            region_labels.append(labels[key])
        return (regions, region_labels) if regions else None

    def _forcing_map_aspect(self, regions: list[GridRegion]) -> float:
        import numpy as np

        all_lon = [value for region in regions for value in (region.lon or [])]
        all_lat = [value for region in regions for value in (region.lat or [])]
        if not all_lon or not all_lat:
            return 4.0 / 3.0
        lat_center = (min(all_lat) + max(all_lat)) / 2.0
        lon_span = max(max(all_lon) - min(all_lon), 1e-6)
        lat_span = max(max(all_lat) - min(all_lat), 1e-6)
        cos_ref = max(abs(np.cos(np.radians(lat_center))), 0.08)
        return float(np.clip((lon_span * cos_ref) / lat_span, 0.2, 14.0))

    def _view_forcing_region_map(self) -> None:
        if self._busy:
            return
        try:
            regions_and_labels = self._forcing_map_regions()
        except Exception as exc:
            self._show_error(tr("step1_forcing_range_read_failed", "⚠️ 读取强迫场公共范围失败：{error}").format(error=exc))
            return
        if regions_and_labels is None:
            self._show_error(tr("step1_select_forcing_first", "请先选择至少一个强迫场文件"))
            return
        regions, labels = regions_and_labels
        handle, output = tempfile.mkstemp(suffix="_forcing_map.png", prefix="ww3tool_")
        os.close(handle)
        self._map_preview_path = Path(output)
        self._map_dialog = RegionMapDialog(self, map_aspect_wh=self._forcing_map_aspect(regions))
        self._forcing_panel.map_button.setText(tr("status_reading", "读取中..."))
        self._set_busy(True)

        def task():
            return self._pipeline_vm.render_forcing_region_map(regions, labels, output)

        def on_done(result: object) -> None:
            self._forcing_panel.map_button.setText(tr("step2_view_map", "查看地图"))
            self._set_busy(False)
            dlg = getattr(self, "_map_dialog", None)
            if dlg is None:
                return
            if isinstance(result, PipelineStepState) and result.error:
                dlg.show_error(result.error)
            elif isinstance(result, PipelineStepState) and result.result is not None and result.result.images:
                dlg.show_image(result.result.images[0])
            else:
                dlg.show_error(tr("step2_map_image_not_generated", "未生成地图图片"))

        def on_cancel() -> None:
            self._map_dialog = None

        self._map_dialog.set_cancel_callback(on_cancel)
        self._runner.run(task, on_done)
        try:
            self._map_dialog.exec()
        finally:
            self._map_dialog = None

    def _load_forcing_intersection(self) -> None:
        if not self._selected_forcing_paths():
            self._show_error(tr("step1_select_forcing_first", "请先选择至少一个强迫场文件"))
            return
        self._refresh_forcing_common_ranges(clear_if_empty=False)

    def _clear_forcing_common_ranges(self) -> None:
        self._forcing_panel.clear_range_values()

    def _refresh_forcing_common_ranges(self, *, clear_if_empty: bool = False) -> None:
        if not self._selected_forcing_paths():
            if clear_if_empty:
                self._clear_forcing_common_ranges()
            return
        self._update_forcing_intersection_ranges(overwrite=True, update_ww3_time=True)

    def _update_forcing_intersection_ranges(
        self,
        *,
        overwrite: bool = False,
        update_ww3_time: bool = False,
    ) -> None:
        paths = self._selected_forcing_paths()
        if not paths:
            return
        try:
            from workflows.infrastructure.forcing.merge_service import common_lonlat_box, common_time_range

            time_range = common_time_range(paths)
            bbox = common_lonlat_box(paths)
        except Exception as exc:
            self._append_log(
                tr("step1_forcing_range_read_failed", "⚠️ 读取强迫场公共范围失败：{error}").format(error=exc)
            )
            return
        self._forcing_panel.set_range_values(
            time_range=time_range,
            bbox=bbox,
            overwrite_editable=overwrite,
        )
        if update_ww3_time:
            start_field = self._ww3_panel.fields["ww3_start"].text().strip()
            end_field = self._ww3_panel.fields["ww3_end"].text().strip()
            if not start_field and not end_field:
                self._ww3_panel.set_value("ww3_start", _date_yyyymmdd(time_range[0]))
                self._ww3_panel.set_value("ww3_end", _date_yyyymmdd(time_range[1]))

    def _validate_params(self) -> None:
        params_path = self._persist_current_form_to_workdir_params(validation_stage="grid")
        if params_path is None or self._busy:
            return
        self._log.clear()
        self._set_busy(True)

        def task():
            return self._pipeline_vm.validate_file(params_path)

        self._runner.run(task, self._on_pipeline_done)

    def _load_wind_bounds(self) -> None:
        if self._busy:
            return
        wind_path = self._resolve_wind_nc()
        if wind_path is None or not wind_path.is_file():
            self._show_error(tr("wind_nc_not_found_select_first", "未找到 wind.nc，请先选择并处理风场文件"))
            return
        self._load_bounds_button.setEnabled(False)
        self._load_bounds_button.setText(tr("status_reading", "读取中..."))

        def task():
            return self._pipeline_vm.load_wind_bounds(wind_path)

        self._runner.run(task, self._on_bounds_done)

    def _resolve_wind_nc(self) -> Path | None:
        workdir_text = self._paths["workdir"].text().strip()
        if workdir_text:
            workdir = Path(workdir_text).expanduser().resolve()
            wind_nc = workdir / "wind.nc"
            if wind_nc.is_file():
                return wind_nc
            matches = sorted(workdir.glob("*wind*.nc"))
            if matches:
                return matches[0]
        selected = self._paths["wind"].text().strip()
        return Path(selected).expanduser().resolve() if selected else None

    def _on_bounds_done(self, result: object) -> None:
        self._load_bounds_button.setText(tr("step2_load_from_nc", "从 wind.nc 读取范围"))
        self._load_bounds_button.setEnabled(True)
        if not isinstance(result, PipelineStepState):
            return
        if result.error:
            self._show_error(result.error)
            return
        bounds = result.result
        if bounds is None:
            return
        # wind.nc 的范围即整个计算域 = level0（最外层）；内层由用户在层卡中自定义
        self._grid_panel.set_bounds(
            "grid",
            (bounds.lon_min, bounds.lon_max),
            (bounds.lat_min, bounds.lat_max),
        )
        self._prompt_global_grid_alignment()

    def _load_wind_time_range(self) -> None:
        if self._busy:
            return
        wind_path = self._resolve_wind_nc()
        if wind_path is None or not wind_path.is_file():
            self._show_error(tr("wind_nc_not_found_select_first", "未找到 wind.nc，请先选择并处理风场文件"))
            return
        self._ww3_panel.load_time_button.setEnabled(False)
        self._ww3_panel.load_time_button.setText(tr("status_reading", "读取中..."))

        def task():
            return self._pipeline_vm.load_wind_time_range(wind_path)

        self._runner.run(task, self._on_time_range_done)

    def _on_time_range_done(self, result: object) -> None:
        self._ww3_panel.load_time_button.setText(tr("step4_load_time_from_wind_nc", "从 wind.nc 读取时间范围"))
        self._ww3_panel.load_time_button.setEnabled(True)
        if not isinstance(result, PipelineStepState):
            return
        if result.error:
            self._show_error(result.error)
            return
        time_range = result.result
        if time_range is None:
            return
        self._ww3_panel.set_value("ww3_start", time_range.start_date)
        self._ww3_panel.set_value("ww3_end", time_range.end_date)

    def _auto_configure_timesteps(self) -> None:
        from workflows.domain.timestep_recommendation import (
            as_ww3_grid_parameters,
            recommend_timesteps_from_spacing,
        )

        # 按网格类型取最小尺度：非结构化用 hmin，结构化/SMC 用 DX/DY+纬度
        # [EN] Min spacing by mesh type: unstructured→hmin, structured/SMC→DX/DY+lat
        dxy_m, reason = self._grid_panel.cfl_spacing_m()
        if dxy_m is None:
            if reason == "need_hmin":
                self._show_error(
                    tr("step4_auto_timesteps_need_hmin", "请先在第二步填写有效的非结构网格最小尺度 hmin（km）")
                )
            else:
                self._show_error(
                    tr("step4_auto_timesteps_need_grid", "请先在第二步填写有效的 DX、DY 与纬度范围")
                )
            return

        freq1_text = self._ww3_panel.spectrum_freq1_text()
        if not freq1_text and self._loaded_config is not None:
            freq1_text = self._loaded_config.ww3_grid.parameters.get("SPECTRUM%FREQ1", "")
        try:
            freq1 = float(freq1_text)
        except ValueError:
            self._show_error(
                tr(
                    "step4_auto_timesteps_need_freq1",
                    "请填写有效的起始频率 FREQ1（Hz）",
                )
            )
            return

        try:
            rec = recommend_timesteps_from_spacing(dxy_m=dxy_m, freq1=freq1)
        except ValueError as exc:
            self._show_error(str(exc))
            return

        self._ww3_panel.set_timestep_values(as_ww3_grid_parameters(rec))
        summary = tr(
            "step4_auto_timesteps_done",
            "已按 CFL 推荐时间步长：DXY≈{dxy:.0f} m，Tcfl≈{tcfl:.0f} s → DTXY={dtxy}，DTMAX={dtmax}，DTKTH={dtkth}，DTMIN={dtmin}",
        ).format(
            dxy=rec.dxy_m,
            tcfl=rec.tcfl,
            dtxy=rec.dtxy,
            dtmax=rec.dtmax,
            dtkth=rec.dtkth,
            dtmin=rec.dtmin,
        )
        self._append_log(summary)

    def _nested_factor(self) -> float:
        nested = self._loaded_config.grid.structured.nested if self._loaded_config else None
        factor = nested.nested_contraction_coefficient if nested else 1.3
        if factor <= 0:
            raise ValueError(tr("nested_factor_must_positive", "❌ 嵌套收缩系数必须大于 0"))
        return factor

    def _recommend_grid_params(self) -> None:
        ok, summary = self._grid_panel.apply_recommendations()
        if not ok:
            InfoBar.warning(
                title=tr("step2_recommend_params", "推荐参数"),
                content=tr("step2_recommend_need_bounds", "请先设置有效的经纬度范围"),
                duration=3000,
                parent=self,
            )
            self.titleBar.raise_()
            return
        InfoBar.success(
            title=tr("step2_recommend_done", "已根据范围推荐参数"),
            content=summary,
            duration=4000,
            parent=self,
        )
        self.titleBar.raise_()

    def _view_region_map(self) -> None:
        config = self._config_from_current_workdir_params(validation_stage="grid", log=False)
        if config is None or self._busy:
            return

        # Calculate map aspect ratio from grid extent so the dialog sizes correctly
        import numpy as np
        # 取所有嵌套层的并集（level0 最外即已覆盖全部，但稳妥起见汇总各层）
        levels = config.grid.nested_levels or [config.grid.outer]
        all_lon = [v for lv in levels for v in lv.lon]
        all_lat = [v for lv in levels for v in lv.lat]
        lat_center = (min(all_lat) + max(all_lat)) / 2.0
        lon_span = max(max(all_lon) - min(all_lon), 1e-6)
        lat_span = max(max(all_lat) - min(all_lat), 1e-6)
        cos_ref = max(abs(np.cos(np.radians(lat_center))), 0.08)
        map_aspect_wh = float(np.clip((lon_span * cos_ref) / lat_span, 0.2, 14.0))

        handle, output = tempfile.mkstemp(suffix="_region_map.png", prefix="ww3tool_")
        os.close(handle)
        self._map_preview_path = Path(output)

        # Show the dialog immediately (with loading state), then render in background
        self._map_dialog = RegionMapDialog(self, map_aspect_wh=map_aspect_wh)
        self._set_busy(True)

        def task():
            return self._pipeline_vm.render_region_map(config, output)

        def on_done(result: object) -> None:
            self._map_button.setText(tr("step2_view_map", "查看地图"))
            self._set_busy(False)
            dlg = getattr(self, "_map_dialog", None)
            if dlg is None:
                return
            if isinstance(result, PipelineStepState) and result.error:
                dlg.show_error(result.error)
            elif isinstance(result, PipelineStepState) and result.result is not None and result.result.images:
                dlg.show_image(result.result.images[0])
            else:
                dlg.show_error(tr("step2_map_image_not_generated", "未生成地图图片"))

        def on_cancel() -> None:
            # BackgroundRunner doesn't support cancellation, but we mark the dialog gone
            self._map_dialog = None

        self._map_dialog.set_cancel_callback(on_cancel)
        self._runner.run(task, on_done)
        try:
            self._map_dialog.exec()
        finally:
            self._map_dialog = None
            self.titleBar.raise_()
            if self._map_preview_path is not None:
                try:
                    self._map_preview_path.unlink(missing_ok=True)
                except OSError:
                    pass
                self._map_preview_path = None

    def _prompt_global_grid_alignment(self) -> None:
        """Ask whether to snap near-global level0 bounds to the canonical global domain."""
        if not self._grid_panel.needs_global_alignment_prompt():
            return
        box = MessageBox(
            tr("step2_global_grid_title", "确认全球范围网格"),
            tr(
                "step2_global_grid_prompt",
                "检测到网格范围非常接近全球范围。\n是否按全球范围生成（经度 -180~180，纬度 -90~90）？",
            ),
            self,
        )
        if getattr(box, "yesButton", None):
            box.yesButton.setText(tr("step2_global_grid_confirm_button", "按全球生成"))
        if getattr(box, "cancelButton", None):
            box.cancelButton.setText(tr("step2_global_grid_cancel_button", "保持当前范围"))
        if not box.exec():
            self.titleBar.raise_()
            return
        self.titleBar.raise_()
        outer_only = self._grid_panel.is_nested and bool(self._grid_panel.level_cards)
        self._grid_panel.apply_global_bounds(outer_only=outer_only)
        self._persist_current_form_to_workdir_params(validation_stage="grid", log=False)
        self._append_log(
            tr("step2_global_grid_outer_only", "✅ 已将外网格范围调整为全球范围")
            if outer_only
            else tr("step2_global_grid_applied", "✅ 已将网格范围调整为全球范围")
        )

    def _generate_grid(self) -> None:
        if self._busy:
            return
        # [EN] Check reference_data availability before starting generation
        # 在开始生成前检查 reference_data 是否就绪
        if not self._reference_data_available():
            return
        self._prompt_global_grid_alignment()
        config = self._config_from_current_workdir_params(
            validation_stage="grid",
            log=False,
        )
        if config is None:
            return
        # Only disable the grid button — other buttons remain usable
        self._grid_button.setEnabled(False)
        self._grid_button.setText(tr("step2_create_grid_ing", "生成网格中..."))

        def task():
            return self._pipeline_vm.generate_grid(config)

        self._runner.run(task, self._on_grid_done)

    def _reference_data_available(self) -> bool:
        """Check if reference_data files are present. Prompt to download if missing."""
        ref_dir = Path(get_project_meshgen_path()) / "reference_data"
        missing = [name for name in REFERENCE_DATA_REQUIRED_FILES if not (ref_dir / name).exists()]
        if not missing:
            return True
        # [EN] Show dialog offering to download
        # 弹出对话框提示用户下载
        box = MessageBox(
            tr("ref_data_missing_title", "缺少 reference_data"),
            tr(
                "ref_data_missing_prompt",
                "reference_data 目录中缺少必要的数据文件（海岸线、地形等），无法生成网格。\n\n路径：{path}\n\n是否从 GitHub 下载？（约 6.5 GB）",
            ).format(path=ref_dir),
            self,
        )
        if not box.exec():
            self.titleBar.raise_()
            return False
        self.titleBar.raise_()
        self._download_reference_data_bg(ref_dir)
        return False

    def _download_reference_data_bg(self, ref_dir: Path) -> None:
        """Run reference_data download in background thread with progress logging."""
        import importlib.util as _ilu

        # [EN] meshgen/ is at project root, which may not be on sys.path
        # meshgen/ 位于项目根目录，可能不在 sys.path 中
        _meshgen_mod = _ilu.spec_from_file_location(
            "get_reference_data",
            str(Path(get_project_meshgen_path()).parent / "meshgen" / "get_reference_data.py"),
        )
        _grd = _ilu.module_from_spec(_meshgen_mod)
        _meshgen_mod.loader.exec_module(_grd)
        _download_fn = _grd.download_reference_data_github

        self._grid_button.setEnabled(False)
        self._grid_button.setText(tr("ref_data_downloading", "📥 正在下载 reference_data..."))
        self._append_log(tr("ref_data_downloading", "📥 正在下载 reference_data（约 6.5 GB），请耐心等待..."))

        def task():
            work_dir = ref_dir.parent
            _download_fn(
                work_dir, ref_dir, log=lambda msg, **_kw: self._pipeline_updates.post_log(str(msg))
            )
            return True

        self._runner.run(task, self._on_ref_data_download_done)

    def _on_ref_data_download_done(self, result: object) -> None:
        self._grid_button.setText(tr("step2_create_grid", "生成网格"))
        self._grid_button.setEnabled(True)
        if result is True:
            self._append_log(tr("ref_data_download_complete", "✅ reference_data 下载完成！现在可以点击「生成网格」继续。"))
        elif isinstance(result, Exception):
            self._show_error(
                tr("ref_data_download_failed", "❌ reference_data 下载失败：{error}").format(error=result)
            )
        elif isinstance(result, dict) and result.get("error"):
            self._show_error(
                tr("ref_data_download_failed", "❌ reference_data 下载失败：{error}").format(error=result["error"])
            )

    def _visualize_grid(self) -> None:
        config = self._config_from_current_workdir_params(validation_stage="grid")
        if config is None or self._busy:
            return
        self._visualize_button.setEnabled(False)
        self._visualize_button.setText(tr("status_generating", "生成中..."))

        def task():
            return self._pipeline_vm.visualize_grid(config)

        self._runner.run(task, self._on_visualize_done)

    def _on_visualize_done(self, result: object) -> None:
        self._visualize_button.setText(tr("step2_visualize_grid", "网格可视化"))
        self._visualize_button.setEnabled(True)
        if not isinstance(result, PipelineStepState):
            return
        if result.error:
            self._show_error(result.error)
        elif result.result is not None:
            self._show_grid_images(result.result.title, result.result.images)

    _VIDEO_SUFFIXES = frozenset({".mp4", ".avi", ".mov", ".mkv", ".webm"})

    @classmethod
    def _split_image_and_video_paths(cls, files: list[str]) -> tuple[list[str], list[str]]:
        images: list[str] = []
        videos: list[str] = []
        for path in files:
            if Path(path).suffix.lower() in cls._VIDEO_SUFFIXES:
                videos.append(path)
            else:
                images.append(path)
        return images, videos

    def _open_video_file(self, videos: list[str]) -> None:
        # [EN] Open the most recent video file with the system default application.
        """用系统默认程序打开最新的视频文件。"""
        existing = [path for path in videos if os.path.isfile(path)]
        if not existing:
            self._append_log(tr("plotting_no_video_found", "未找到视频文件"))
            return
        target = max(existing, key=os.path.getmtime)
        QDesktopServices.openUrl(QUrl.fromLocalFile(target))

    def _present_plot_media(self, title: str, files: list[str]) -> None:
        # [EN] Images go to sidebar; videos are opened directly with system player (not in sidebar).
        """图片进侧边栏；视频用系统播放器直接打开（不进侧边栏）。"""
        images, videos = self._split_image_and_video_paths(files)
        if videos:
            self._open_video_file(videos)
            return
        if images:
            self._show_grid_images(title, images)
        else:
            self._append_log(tr("plotting_done_no_images", "绘图完成，但未找到图片。"))

    def _show_grid_images(self, title: str, images: list[str]) -> None:
        # [EN] Display results in window's right-side image drawer, without changing main splitter width.
        """在窗口右侧图片抽屉展示结果，不改变主 splitter 宽度。"""
        self.show_image_gallery(title, images)

    def _hide_grid_images(self) -> None:
        self.hide_image_gallery()

    # [EN] ── Plotting (scientific post-processing)─────────────────────────────────────────────────────
    # ── 绘图（科研后处理）─────────────────────────────────────────────────────

    def _run_plot(self, runner_fn) -> None:
        # [EN] Build plot stage config and execute a plotting use case in the background.
        """构建 plot 阶段配置并在后台执行一个绘图用例。"""
        params_path = self._persist_current_form_to_workdir_params(validation_stage="grid")
        if params_path is None:
            return
        try:
            config = self._pipeline_vm.load_config(params_path, validation_stage="plot")
        except Exception as exc:
            self._show_error(str(exc))
            return
        if self._busy:
            return
        self._set_busy(True)
        self._runner.run(lambda: runner_fn(config), self._on_plot_done)

    def _on_plot_done(self, result: object) -> None:
        self._set_busy(False)
        if result is None:
            return
        images = list(getattr(result, "image_files", []) or [])
        if not getattr(result, "success", True):
            messages = getattr(result, "messages", []) or []
            self._show_error(messages[-1] if messages else tr("plotting_failed", "绘图失败"))
            return
        if images:
            first = str(images[0]).replace("\\", "/")
            if "/photo/jason3_satellite/" in first:
                title = tr("plotting_jason3_swh_results", "Jason-3 卫星观测图")
            else:
                title = tr("plotting_results", "绘图结果")
            self._present_plot_media(title, images)
        else:
            self._append_log(tr("plotting_done_no_images", "绘图完成，但未找到图片。"))

    def _plot_wave_maps(self) -> None:
        params = self._plot_interface.wave_maps_params()
        self._run_plot(
            lambda c: self._plot_vm.wave_maps(
                c,
                time_step_hours=params["time_step_hours"],
                wave_file=params["wave_file"],
            )
        )

    def _plot_contour(self) -> None:
        params = self._plot_interface.wave_maps_params()
        self._run_plot(
            lambda c: self._plot_vm.contour_maps(
                c,
                time_step_hours=params["time_step_hours"],
                wave_file=params["wave_file"],
            )
        )

    def _plot_spectrum_all(self) -> None:
        self._run_plot(lambda c: self._plot_vm.spectrum(c, mode="all"))

    def _plot_spectrum_selected(self) -> None:
        station = self._plot_interface.spectrum_station()
        self._run_plot(lambda c: self._plot_vm.spectrum(c, mode="selected", station_index=station))

    def _plot_jason3(self) -> None:
        jason_folder = self._plot_interface.jason3_folder() or None
        self._run_plot(lambda c: self._plot_vm.match_jason3(c, data_folder=jason_folder or ""))

    def _plot_download_ndbc(self) -> None:
        lon_lat = self._plot_interface.ndbc_lon_lat()
        time_range = self._plot_interface.ndbc_time_range()
        self._run_plot(lambda c: self._plot_vm.download_ndbc(c, lon_lat=lon_lat, time_range=time_range))

    def _plot_match_ndbc(self) -> None:
        lon_lat = self._plot_interface.ndbc_lon_lat()
        time_range = self._plot_interface.ndbc_time_range()
        self._run_plot(lambda c: self._plot_vm.match_ndbc(c, lon_lat=lon_lat, time_range=time_range))

    def _plot_view_photo_subdir(self, subdir: str) -> None:
        # [EN] View results under workdir ``photo/<subdir>`` (videos opened with system player).
        """查看工作目录 ``photo/<subdir>`` 下的结果（视频用系统播放器打开）。"""
        from workflows.infrastructure.plot.photo_output import (
            SUBDIR_WAVE_HEIGHT_VIDEO,
            collect_photo_files,
            photo_subdir,
        )

        workdir = self._paths["workdir"].text().strip()
        if not workdir:
            self._show_error(tr("tools_clean_no_workdir", "请先选择工作目录"))
            return
        folder = photo_subdir(workdir, subdir)
        if not os.path.isdir(folder):
            self._append_log(
                tr("plotting_photo_subdir_not_found", "未找到图片目录，请先生成：{path}").format(path=folder)
            )
            return

        videos = collect_photo_files(workdir, subdir, "*.mp4")
        if subdir == SUBDIR_WAVE_HEIGHT_VIDEO:
            if not videos:
                self._append_log(
                    tr("plotting_photo_video_subdir_empty", "目录中没有视频，请先生成：{path}").format(
                        path=folder
                    )
                )
                return
            self._open_video_file(videos)
            return

        images = collect_photo_files(workdir, subdir, "*.png")
        if not images:
            self._append_log(
                tr("plotting_photo_subdir_empty", "目录中没有图片，请先生成：{path}").format(path=folder)
            )
            return
        self._show_grid_images(tr("plotting_results", "绘图结果"), images)

    def _plot_open_photo_folder(self) -> None:
        from workflows.infrastructure.plot.photo_output import photo_subdir

        workdir = self._paths["workdir"].text().strip()
        if not workdir:
            self._show_error(tr("tools_clean_no_workdir", "请先选择工作目录"))
            return
        photo_root = os.path.join(workdir, "photo")
        if os.path.isdir(photo_root):
            QDesktopServices.openUrl(QUrl.fromLocalFile(photo_root))
            return
        self._show_error(tr("plotting_photo_root_not_found", "未找到 photo 文件夹，请先生成图片"))

    def _plot_download_jason3(self) -> None:
        time_range = self._plot_interface.jason3_time_range()
        local_folder = self._plot_interface.jason3_folder() or None
        self._run_plot(lambda c: self._plot_vm.download_jason3(c, time_range=time_range, local_folder=local_folder))

    def _plot_jason3_swh(self) -> None:
        lon_lat = self._plot_interface.jason3_lon_lat()
        time_range = self._plot_interface.jason3_time_range()
        if not lon_lat:
            self._show_error(tr("plotting_fill_lonlat_range", "❌ 请正确填写经纬度范围"))
            return
        if not time_range:
            self._show_error(tr("plotting_fill_time_range", "❌ 请填写开始和结束时间（格式：YYYYMMDD）"))
            return
        jason_folder = self._plot_interface.jason3_folder() or None
        self._run_plot(
            lambda c: self._plot_vm.jason3_swh(
                c,
                lon_lat=lon_lat,
                time_range=time_range,
                data_folder=jason_folder or "",
            )
        )

    def _plot_ndbc_station_map(self) -> None:
        # [EN] Show NDBC buoy station map in dialog (aligned with src run_ndbc_observation).
        """在对话框中展示 NDBC 浮标站点地图（对齐 src run_ndbc_observation）。"""
        lon_lat = self._plot_interface.ndbc_lon_lat()
        if not lon_lat:
            self._show_error(tr("plotting_fill_lonlat_range", "❌ 请正确填写经纬度范围"))
            return

        time_range = self._plot_interface.ndbc_time_range()
        if not time_range:
            self._show_error(tr("plotting_fill_time_range", "❌ 请填写开始和结束时间（格式：YYYYMMDD）"))
            return

        start_str, end_str = time_range
        if not re.fullmatch(r"\d{8}", start_str) or not re.fullmatch(r"\d{8}", end_str):
            self._show_error(tr("plotting_ndbc_invalid_time_format", "❌ 时间格式错误，请使用 YYYYMMDD。"))
            return
        try:
            datetime.strptime(start_str, "%Y%m%d")
            datetime.strptime(end_str, "%Y%m%d")
        except ValueError:
            self._show_error(tr("plotting_ndbc_invalid_time_format", "❌ 时间格式错误，请使用 YYYYMMDD。"))
            return

        from workflows.application.match_ndbc import load_ndbc_station_points

        ndbc_folder = self._plot_interface.ndbc_folder().strip()
        if not ndbc_folder or not os.path.isdir(ndbc_folder):
            # [EN] Fall back to PipelineConfig paths.ndbc_path
            # 回退到 PipelineConfig 的 paths.ndbc_path
            if self._loaded_config and self._loaded_config.paths.ndbc_path and os.path.isdir(self._loaded_config.paths.ndbc_path):
                ndbc_folder = self._loaded_config.paths.ndbc_path
            else:
                ndbc_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "ndbc")
                os.makedirs(ndbc_folder, exist_ok=True)

        self._append_log(tr("plotting_ndbc_fetch_stations", "🔄 正在获取 NDBC 站点列表..."))

        def task() -> dict:
            stations = load_ndbc_station_points(lon_lat, time_range, ndbc_folder)
            return {"stations": stations, "lon_lat": lon_lat}

        self._runner.run(task, self._on_ndbc_station_map_ready)

    def _on_ndbc_station_map_ready(self, result: object) -> None:
        if isinstance(result, dict) and result.get("success") is False:
            self._append_log(
                tr("plotting_ndbc_download_process_failed", "❌ NDBC 下载失败：{error}").format(
                    error=result.get("error", tr("unknown_error", "❌ 未知错误"))
                )
            )
            return
        if not isinstance(result, dict):
            return

        stations = result.get("stations") or []
        lon_lat = result.get("lon_lat") or []
        if not stations:
            InfoBar.warning(
                title=tr("plotting_display_failed", "显示失败"),
                content=tr("plotting_no_station_data", "没有可显示的站点数据"),
                duration=3000,
                parent=self,
            )
            self.titleBar.raise_()
            self._append_log(
                tr("plotting_ndbc_no_station_in_range", "⚠️ 当前经纬度范围内没有找到 NDBC 活跃站点。")
            )
            return

        try:
            from ..components.ndbc_station_map_dialog import NDBCStationMapDialog

            dialog = NDBCStationMapDialog(parent=self, stations=stations, lon_lat=lon_lat)
            dialog.exec()
        except ImportError as exc:
            self._append_log(
                tr("plotting_cartopy_not_available", "缺少 cartopy 库，无法显示站点地图：{error}").format(
                    error=exc
                )
            )
            return
        self.titleBar.raise_()

        self._append_log(
            tr("plotting_ndbc_station_selected", "✅ 范围内找到 {count} 个 NDBC 站点").format(count=len(stations))
        )

    def _plot_spectrum_map(self) -> None:
        # [EN] Show spectrum station map in dialog.
        """在对话框中展示谱站点地图。"""
        spec_file = self._plot_interface.spectrum_file_path()
        if not spec_file or not os.path.exists(spec_file):
            self._show_error(tr("plotting_spectrum_file_not_selected", "请先选择二维谱文件"))
            return
        try:
            from ..components.spectrum_station_map_dialog import SpectrumStationMapDialog
            dialog = SpectrumStationMapDialog(parent=self, spec_file=spec_file)
            dialog.exec()
        except ImportError as exc:
            self._append_log(
                tr("plotting_cartopy_not_available", "缺少 cartopy 库，无法显示站点地图：{error}").format(
                    error=exc
                )
            )
            return
        except Exception as exc:
            self._append_log(
                tr("plotting_display_failed_with_error", "显示失败：{error}").format(error=exc)
            )
            return
        self.titleBar.raise_()

    def _plot_wind_swell(self) -> None:
        params = self._plot_interface.wave_maps_params()
        self._run_plot(
            lambda c: self._plot_vm.wind_swell_maps(
                c,
                time_step_hours=params["time_step_hours"],
                wave_file=params["wave_file"],
            )
        )

    def _plot_wave_video(self) -> None:
        params = self._plot_interface.wave_maps_params()
        self._run_plot(
            lambda c: self._plot_vm.wave_video(
                c,
                time_step_hours=params["time_step_hours"],
                wave_file=params["wave_file"],
            )
        )

    def _plot_wind_field(self) -> None:
        params = self._plot_interface.wind_field_params()
        self._run_plot(
            lambda c: self._plot_vm.wind_field(
                c,
                wind_file=params["wind_file"],
                time_step_hours=params["time_step_hours"],
                flag_type=params["flag_type"],
                density_step=params["density_step"],
            )
        )

    # [EN] ── Local run ──────────────────────────────────────────────────────────────
    # ── 本地运行 ──────────────────────────────────────────────────────────────

    def _run_job(self, runner_fn, on_done=None) -> bool:
        # [EN] Build plot stage config and execute a local/remote operation in the background.
        """构建 plot 阶段配置并在后台执行一个本地/远程操作。"""
        params_path = self._persist_current_form_to_workdir_params(validation_stage="grid")
        if params_path is None:
            return False
        try:
            config = self._pipeline_vm.load_config(params_path, validation_stage="plot")
        except Exception as exc:
            self._show_error(str(exc))
            return False
        if self._busy:
            return False
        self._set_busy(True)
        self._runner.run(lambda: runner_fn(config), on_done or self._on_job_done)
        return True

    def _on_job_done(self, result: object) -> None:
        self._set_busy(False)
        self._sync_step5_if_needed()
        if result is None:
            return
        if not getattr(result, "success", True):
            error = getattr(result, "error", None)
            if not error:
                messages = getattr(result, "messages", []) or []
                error = messages[-1] if messages else tr("operation_failed", "操作失败")
            self._show_error(str(error))

    def _sync_step5_if_needed(self) -> None:
        # [EN] Sync state if remote VM has auto-connected but step 5 UI has not been updated.
        """若远程 VM 已自动连接但第五步 UI 未更新，同步状态。"""
        if not self._remote_vm.is_connected:
            return
        if getattr(self, "_step5_ui_synced", False):
            return
        self._step5_ui_synced = True

        def sync_ui() -> None:
            self._server_connect_panel.set_connected(True)
            self._server_poll_config = self._build_poll_config()
            self._start_server_polling()

        self._preserve_steps_scroll(sync_ui)
        # [EN] Update ntfy button text after a short delay (non-blocking).
        # 短暂延迟后更新 ntfy 按钮文本（不阻塞 UI）
        QTimer.singleShot(2000, self._update_ntfy_button_text)

    def _local_run(self) -> None:
        bin_dir = self._local_run_panel.bin_dir() or None
        self._local_run_panel.local_run_button.setEnabled(False)
        self._local_run_panel.local_run_button.setText(tr("status_running", "运行中..."))
        started = self._run_job(
            lambda c: self._local_vm.local_run(c, bin_dir=bin_dir),
            on_done=self._on_local_run_done,
        )
        if not started:
            self._local_run_panel.local_run_button.setText(tr("step5_local_run", "本地运行"))
            self._local_run_panel.local_run_button.setEnabled(True)

    def _on_local_run_done(self, result: object) -> None:
        self._local_run_panel.local_run_button.setText(tr("step5_local_run", "本地运行"))
        self._local_run_panel.local_run_button.setEnabled(True)
        # [EN] No InfoBar for local runs — all output is already in the log.
        self._set_busy(False)
        self._sync_step5_if_needed()

    def _local_stop(self) -> None:
        if self._local_vm.stop():
            self._append_log(tr("step5_stop_signal_sent", "⏹️ 已发送停止信号"))
        else:
            self._append_log(tr("step5_no_running_local_task", "当前没有正在运行的本地任务"))

    # [EN] ── Server: connect/queue/cancel ────────────────────────────────────────────────
    # ── 服务器：连接/队列/取消 ────────────────────────────────────────────────

    def _server_connect(self) -> None:
        self._server_connect_panel.connect_button.setEnabled(False)
        if not self._run_job(self._remote_vm.connect_test, on_done=self._on_connect_done):
            self._server_connect_panel.connect_button.setEnabled(True)

    def _on_connect_done(self, result: object) -> None:
        self._set_busy(False)
        self._server_connect_panel.connect_button.setEnabled(True)
        connected = bool(getattr(result, "success", False))
        self._server_connect_panel.set_connected(connected)
        if not connected:
            self._step5_ui_synced = False
            error = getattr(result, "error", None)
            if not error:
                messages = getattr(result, "messages", []) or []
                error = messages[-1] if messages else tr("connect_failed", "连接失败")
            self._show_error(str(error))
            self._stop_server_polling()
        else:
            self._step5_ui_synced = True
            # [EN] Cache current config for polling, avoid rebuilding each time
            # 缓存当前配置用于轮询，避免每次重新构建
            self._server_poll_config = self._build_poll_config()
            self._start_server_polling()

    def _server_queue(self) -> None:
        self._run_job(self._remote_vm.queue_status)

    def _server_cancel(self) -> None:
        job_id = self._server_connect_panel.job_id()
        if not job_id:
            self._show_error(tr("step5_cancel_empty_jobid", "请填写要取消的任务 ID"))
            return
        # [EN] Lightweight: run scancel in background without blocking UI.
        # 轻量操作：后台执行 scancel，不阻塞 UI。
        params_path = self._persist_current_form_to_workdir_params(validation_stage="grid")
        if params_path is None:
            return
        try:
            config = self._pipeline_vm.load_config(params_path, validation_stage="plot")
        except Exception as exc:
            self._show_error(str(exc))
            return
        self._runner.run(
            lambda: self._remote_vm.cancel_job(config, job_id),
            self._on_job_done,
        )

    # [EN] ── Server status auto-polling (cluster jobs + idle resources + task queue) ──
    # ── 服务器状态自动轮询（集群作业 + 空闲资源 + 任务队列）────────────────────────────

    def _build_poll_config(self):
        # [EN] Try to build PipelineConfig for polling; returns None on failure.
        """尝试构建轮询用的 PipelineConfig，失败时返回 None。"""
        try:
            params_path = self._persist_current_form_to_workdir_params(validation_stage="grid")
            if params_path is None:
                return None
            return self._pipeline_vm.load_config(params_path, validation_stage="plot")
        except Exception:
            return None

    def _start_server_polling(self) -> None:
        # [EN] Start timer after successful connection, polling all three server lists every second.
        """连接成功后启动定时器，每 1 秒拉取集群作业、空闲资源和任务队列。"""
        self._stop_server_polling()
        self._server_polling_active = True
        self._server_poll_in_flight = False
        # [EN] Pull once immediately
        # 立即拉取一次
        self._poll_server_status()
        self._server_poll_timer = QTimer(self)
        self._server_poll_timer.timeout.connect(self._poll_server_status)
        self._server_poll_timer.start(1_000)

    def _stop_server_polling(self) -> None:
        self._server_polling_active = False
        self._server_poll_in_flight = False
        timer = getattr(self, "_server_poll_timer", None)
        if timer is not None:
            timer.stop()
            self._server_poll_timer = None

    def _poll_server_status(self) -> None:
        # [EN] Lightweight pull: reuse persistent SSH connection, do not set busy flag, no log output.
        """轻量级拉取：复用持久化 SSH 连接，不设置 busy 标志，不输出日志。"""
        cfg = getattr(self, "_server_poll_config", None)
        if cfg is None or not getattr(self, "_server_polling_active", False):
            return
        if getattr(self, "_server_poll_in_flight", False):
            return
        self._server_poll_in_flight = True
        # [EN] Reuse ViewModel's persistent client, skip log callback
        # 复用 ViewModel 的持久化 client，跳过 log 回调
        from workflows.application.remote_ops import run_server_status
        persistent = self._remote_vm._client
        self._runner.run(
            lambda: run_server_status(cfg, client=persistent),
            self._on_server_status_done,
        )

    def _on_server_status_done(self, result: object) -> None:
        self._server_poll_in_flight = False
        if result is None:
            return
        data = getattr(result, "data", None)
        if isinstance(data, dict):
            cpu_data = data.get("cpu", []) or []
            idle_data = data.get("idle", []) or []
            partition_data = data.get("partitions", []) or []
            queue_lines = data.get("queue", []) or []

            def apply_status() -> None:
                self._server_connect_panel.update_cpu_table(cpu_data)
                self._server_connect_panel.update_idle_resources(idle_data)
                self._server_connect_panel.replace_cpu_options_if_changed(partition_data)
                self._server_connect_panel.update_queue_table(queue_lines)
                self._server_connect_panel.apply_suggested_slurm_mem()

            self._preserve_steps_scroll(apply_status)
        # [EN] Stop polling when connection fails
        # 连接失败时停止轮询
        if not getattr(result, "success", True):
            self._step5_ui_synced = False
            self._stop_server_polling()
            self._server_connect_panel.set_connected(False)

    # [EN] ── Server: operations ──────────────────────────────────────────────────────────
    # ── 服务器：操作 ──────────────────────────────────────────────────────────

    def _server_list_files(self) -> None:
        if not self._persist_server_remote_dir():
            return
        self._run_job(self._remote_vm.list_files)

    def _server_upload(self) -> None:
        if not self._persist_server_remote_dir():
            return
        self._run_job(lambda c: self._remote_vm.upload(c, confirmed=True))

    def _server_confirm_slurm(self) -> None:
        params_path = self._persist_current_form_to_workdir_params(validation_stage="grid")
        if params_path is None:
            return
        try:
            config = self._pipeline_vm.load_config(params_path, validation_stage="plot")
        except Exception as exc:
            self._show_error(str(exc))
            return
        if self._busy:
            return
        self._set_busy(True)

        def task():
            return self._pipeline_vm.apply_server_script(config)

        self._runner.run(task, self._on_pipeline_done)

    def _server_upload_without_forcing(self) -> None:
        if not self._persist_server_remote_dir():
            return
        self._run_job(lambda c: self._remote_vm.upload_without_forcing(c, confirmed=True))

    def _server_submit(self) -> None:
        if not self._persist_server_remote_dir():
            return
        self._run_job(self._remote_vm.submit)

    def _server_check(self) -> None:
        if not self._persist_server_remote_dir():
            return
        self._run_job(self._remote_vm.check_status)

    def _server_inject_ntfy(self) -> None:
        if not self._persist_server_remote_dir():
            return
        self._run_job(self._remote_vm.ntfy_smart_action, on_done=self._on_ntfy_smart_done)

    def _on_ntfy_smart_done(self, result: object) -> None:
        self._on_job_done(result)
        if not getattr(result, "success", False):
            self._update_ntfy_button_text()
            return
        self._server_connect_panel.inject_ntfy_button.setText(
            tr("step6_ntfy_send_test", "发送测试通知")
        )
        data = getattr(result, "data", None) or {}
        topic = data.get("topic", "")
        action = data.get("action", "")
        if not topic:
            return
        url = f"https://ntfy.sh/{topic}"
        if action == "inject":
            title = tr("ntfy_info_title_injected", "📡 ntfy 监听已启动")
            content = (
                tr("ntfy_info_topic", "Topic: {topic}").format(topic=topic)
                + "\n"
                + tr("ntfy_info_subscribe", "订阅链接: {url}").format(url=url)
                + "\n"
                + tr("ntfy_info_action_injected", "已注入 watcher 并发送启动通知")
            )
        else:
            title = tr("ntfy_info_title_test", "📡 ntfy 测试通知已发送")
            content = (
                tr("ntfy_info_topic", "Topic: {topic}").format(topic=topic)
                + "\n"
                + tr("ntfy_info_subscribe", "订阅链接: {url}").format(url=url)
                + "\n"
                + tr("ntfy_info_action_test", "已从服务器发送一条测试通知，请检查订阅端")
            )
        InfoBar.success(
            title=title,
            content=content,
            duration=8000,
            parent=self,
        )
        self.titleBar.raise_()

    def _on_ntfy_job_done(self, result: object) -> None:
        self._on_job_done(result)
        if not getattr(result, "success", False):
            return
        # [EN] Show per-job topic info (different from the global listener topic).
        # 显示单任务 topic 信息（与全局监听使用不同频道）。
        data = getattr(result, "data", None) or {}
        topic = data.get("topic", "")
        if not topic:
            return
        url = f"https://ntfy.sh/{topic}"
        title = tr("ntfy_info_title_job", "📡 单任务 ntfy 监听已启动")
        content = (
            tr("ntfy_info_topic", "Topic: {topic}").format(topic=topic)
            + "\n"
            + tr("ntfy_info_subscribe", "订阅链接: {url}").format(url=url)
            + "\n"
            + tr("ntfy_info_action_job", "已启动单任务监听，任务完成后将自动通知")
        )
        InfoBar.success(
            title=title,
            content=content,
            duration=8000,
            parent=self,
        )
        self.titleBar.raise_()

    def _update_ntfy_button_text(self) -> None:
        # [EN] Check ntfy watcher status and update button text accordingly.
        """检查 ntfy watcher 状态并更新按钮文本。"""
        if not self._remote_vm.is_connected:
            return
        config = self._build_poll_config()
        if config is None:
            return
        try:
            from workflows.application.remote_ops import run_check_ntfy_status

            status_result = run_check_ntfy_status(
                config,
                log=None,
                client=self._remote_vm._client,
            )
            data = getattr(status_result, "data", {}) or {}
            if data.get("running"):
                self._server_connect_panel.inject_ntfy_button.setText(
                    tr("step6_ntfy_send_test", "发送测试通知")
                )
            else:
                self._server_connect_panel.inject_ntfy_button.setText(
                    tr("step6_inject_ntfy", "常驻 ntfy 监听")
                )
        except Exception:
            pass

    def _server_watch_ntfy_job(self) -> None:
        job_id = self._server_connect_panel.job_id()
        if not job_id:
            self._show_error(tr("step6_watch_job_empty", "请填写要监听的任务 ID"))
            return
        if not self._persist_server_remote_dir():
            return
        self._run_job(
            lambda c: self._remote_vm.inject_ntfy_job_listener(c, job_id),
            on_done=self._on_ntfy_job_done,
        )

    def _server_node_status(self) -> None:
        self._run_job(self._remote_vm.node_status)

    def _server_clear(self) -> None:
        remote_dir = self._server_ops_panel.remote_dir() if hasattr(self, "_server_ops_panel") else ""
        if not remote_dir:
            self._show_error(tr("server_path_required", "请先填写服务器路径"))
            return
        box = MessageBox(
            tr("confirm_clear_remote_folder", "确认清空远程文件夹"),
            tr(
                "confirm_clear_remote_folder_content",
                "将删除远程目录内的所有文件与子文件夹（目录本身保留）。此操作不可恢复。\n\n{path}",
            ).format(path=remote_dir),
            self,
        )
        if not box.exec():
            self.titleBar.raise_()
            return
        self.titleBar.raise_()
        if not self._persist_server_remote_dir():
            return
        self._run_job(lambda c: self._remote_vm.clear_remote(c, confirmed=True))

    def _server_download_results(self) -> None:
        if not self._persist_server_remote_dir():
            return
        self._run_job(lambda c: self._remote_vm.download_results(c, nested=c.grid.grid_type == "nested"))

    def _server_download_log(self) -> None:
        if not self._persist_server_remote_dir():
            return
        self._run_job(self._remote_vm.download_log)

    def _server_exec_command(self) -> None:
        # [EN] Execute arbitrary command on remote server.
        """在远程服务器执行任意命令。"""
        cmd = self._server_ops_panel.cmd_edit.text().strip()
        if not cmd:
            return
        if not self._persist_server_remote_dir():
            return
        self._run_job(lambda config: self._remote_vm.exec_command(config, cmd))

    # [EN] ── Tools: clean workdir ────────────────────────────────────────────────────
    # ── 工具：清理工作目录 ────────────────────────────────────────────────────

    def _tools_workdir(self) -> str | None:
        workdir = self._paths["workdir"].text().strip()
        if not workdir:
            self._show_error(tr("tools_clean_no_workdir", "请先选择工作目录"))
            return None
        if not Path(workdir).is_dir():
            self._show_error(tr("tools_clean_not_exists", "工作目录不存在：{path}").format(path=workdir))
            return None
        return os.path.abspath(os.path.normpath(workdir))

    def _tools_clean(self, *, title: str, content: str, deleter, kind: str) -> None:
        workdir = self._tools_workdir()
        if workdir is None:
            return
        box = MessageBox(title, content.format(path=workdir), self)
        if not box.exec():
            self.titleBar.raise_()
            return
        self.titleBar.raise_()
        try:
            removed, errors = deleter(workdir)
        except Exception as exc:
            self._show_error(tr("tools_clean_failed", "清理失败：{error}").format(error=exc))
            return
        for line in errors[:20]:
            self._append_log(f"   {line}")
        if len(errors) > 20:
            self._append_log("   …")
        self._append_log(tr("tools_clean_done_kind", "🗑️ 已清理{kind}（删除 {n} 个文件）：{path}").format(kind=kind, n=removed, path=workdir))
        InfoBar.success(
            title=tr("tools_clean_workdir_card_title", "清理工作目录"),
            content=tr("tools_clean_done_all_short", "已删除 {n} 个文件").format(n=removed),
            duration=2500,
            parent=self,
        )
        self.titleBar.raise_()

    def _tools_clean_all(self) -> None:
        self._tools_clean(
            title=tr("tools_clean_confirm_all_title", "确认清空工作目录"),
            content=tr("tools_clean_confirm_all_content", "将删除该目录下的所有文件与子文件夹（目录本身保留）。此操作不可恢复。\n\n{path}"),
            deleter=delete_all_under,
            kind=tr("tools_clean_kind_all", "工作目录内文件"),
        )

    def _tools_clean_run(self) -> None:
        self._tools_clean(
            title=tr("tools_clean_confirm_run_title", "确认清空运行文件"),
            content=tr("tools_clean_confirm_run_content", "将删除该目录下的运行产物（.ww3 除 grid.ww3、.log、.bin）。此操作不可恢复。\n\n{path}"),
            deleter=delete_run_artifacts_under,
            kind=tr("tools_clean_kind_run", "运行文件"),
        )

    def _apply_ww3_params_only(self) -> None:
        """Apply WW3 namelist parameters without re-running forcing or grid generation."""
        # Use "plot" stage to skip forcing-path existence checks — files are
        # already in the workdir from a previous run; we only need WW3 params.
        params_path = self._persist_current_form_to_workdir_params(validation_stage="grid")
        if params_path is None:
            return
        try:
            config = self._pipeline_vm.load_config(params_path, validation_stage="plot")
        except Exception as exc:
            self._show_error(str(exc))
            return
        if self._busy:
            return
        self._set_busy(True)

        def task():
            return self._pipeline_vm.apply_ww3_params(config)

        self._runner.run(task, self._on_pipeline_done)

    def _run_pipeline(self) -> None:
        params_path = self._persist_current_form_to_workdir_params(validation_stage="grid")
        if params_path is None:
            return
        try:
            config = self._pipeline_vm.load_config(params_path, validation_stage="full")
        except Exception as exc:
            self._show_error(str(exc))
            return
        if self._busy:
            return
        skip_grid = self._skip_grid.isChecked()
        self._log.clear()
        self._set_busy(True)

        def task():
            return self._pipeline_vm.run(config, skip_grid=skip_grid)

        self._runner.run(task, self._on_pipeline_done)

    def _on_forcing_done(self, result: object) -> None:
        self._hide_forcing_progress()
        self._set_busy(False)
        if isinstance(result, ForcingStepState) and result.error:
            self._show_error(result.error)
        elif isinstance(result, dict) and result.get("error"):
            self._show_error(str(result["error"]))
        # [EN] Refresh Step 4 panel forcing enabled state after forcing processing completes
        # 强迫场处理完毕后刷新 Step 4 面板的启用状态显示
        if self._loaded_config is not None:
            self._render_summary(self._loaded_config)

    def _on_pipeline_done(self, result: object) -> None:
        self._set_busy(False)
        if isinstance(result, dict) and result.get("error"):
            self._show_error(str(result["error"]))

    def _on_grid_done(self, result: object) -> None:
        self._grid_button.setText(tr("step2_create_grid", "生成网格"))
        self._grid_button.setEnabled(True)
        if isinstance(result, PipelineStepState) and result.error:
            self._show_error(result.error)
        elif isinstance(result, dict) and result.get("error"):
            self._show_error(str(result["error"]))

    def _set_busy(self, busy: bool) -> None:
        # Match legacy src behavior: background tasks do not globally disable
        # homepage buttons. Operations that must prevent duplicate clicks manage
        # their own button state locally.
        self._busy = False
        if busy:
            self._forcing_status.setText(tr("status_processing", "正在处理"))
            self._pipeline_status.setText(tr("status_processing", "正在处理"))
        else:
            self._render_forcing_state(self._forcing_vm.state)
            self._render_pipeline_state(self._pipeline_vm.state)

    def _show_forcing_progress(self) -> None:
        if self._forcing_progress is None:
            self._forcing_progress = ForcingProgressDialog(self, tr("please_wait", "请稍候..."))
        self._forcing_progress.show()
        self._forcing_progress.raise_()
        self._forcing_progress.activateWindow()

    def _hide_forcing_progress(self) -> None:
        if self._forcing_progress is not None:
            self._forcing_progress.close()
            self._forcing_progress.deleteLater()
            self._forcing_progress = None
        self.titleBar.raise_()

    def _create_log_block_format(self) -> QTextBlockFormat:
        """返回统一的日志段落格式，让中英文行距一致。"""
        extra = float(_LOG_LINE_SPACING_EXTRA_PX)
        bottom_margin = min(4.0, extra * 0.35 + 0.75)
        fmt = QTextBlockFormat()
        if extra > 0:
            fmt.setLineHeight(extra, _LH_LINE_DISTANCE)
        fmt.setBottomMargin(bottom_margin)
        return fmt

    def _append_log(self, message: str) -> None:
        """以段落方式追加纯文本，确保每行应用统一行距。"""
        text = str(message)
        had_log_focus = self._log.hasFocus()
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = self._create_log_block_format()

        doc = self._log.document()
        is_empty = doc.blockCount() == 1 and doc.firstBlock().text() == ""
        parts = text.split("\n") if text else [""]

        for idx, part in enumerate(parts):
            if is_empty and idx == 0:
                cursor.setBlockFormat(fmt)
            else:
                cursor.insertBlock(fmt)
            if part:
                cursor.insertText(part)

        self._log.setTextCursor(cursor)
        if not had_log_focus:
            self._log.clearFocus()

    def _render_forcing_state(self, state: ForcingStepState) -> None:
        if self._busy and state.is_running:
            self._forcing_status.setText(tr("status_processing", "正在处理"))
        elif state.error:
            self._forcing_status.setText(tr("status_failed", "处理失败"))
        elif any(getattr(state.files, key, None) for key in ("wind", "current", "level", "ice")):
            self._forcing_status.setText(tr("forcing_prepared", "强迫场已准备"))
            labels = self._forcing_field_button_labels()
            for key, empty_text in labels.items():
                value = getattr(state.files, key, None)
                if value:
                    self._set_path_value(key, str(value), empty_text)
            self._refresh_forcing_common_ranges(clear_if_empty=False)
        else:
            self._forcing_status.setText(tr("status_waiting", "等待执行"))

    def _render_pipeline_state(self, state: PipelineStepState) -> None:
        if self._busy and state.is_running:
            self._pipeline_status.setText(tr("status_processing", "正在处理"))
        elif state.error:
            self._pipeline_status.setText(tr("status_failed", "处理失败"))
        elif state.action == "validate" and not state.error:
            self._pipeline_status.setText(tr("status_params_valid", "参数有效"))
        elif state.action == "run" and not state.error:
            self._pipeline_status.setText(tr("status_preprocess_done", "✅ 预处理流程完成"))
        elif state.action == "grid" and not state.error:
            self._pipeline_status.setText(tr("status_grid_done", "✅ 网格生成完成"))
        elif state.action == "bounds" and not state.error:
            self._pipeline_status.setText(tr("status_bounds_loaded", "范围已读取"))
        elif state.action == "map" and not state.error:
            self._pipeline_status.setText(tr("status_map_done", "地图已生成"))
        elif state.action == "visualize" and not state.error:
            self._pipeline_status.setText(tr("status_visualize_done", "网格可视化完成"))
        else:
            self._pipeline_status.setText(tr("status_waiting", "等待执行"))

    def _show_error(self, message: str) -> None:
        InfoBar.error(
            title=tr("params_or_execution_error", "参数或执行错误"),
            content=message,
            duration=5000,
            parent=self,
        )
        self.titleBar.raise_()


def create_preprocessing_window() -> PreprocessingWindow:
    return PreprocessingWindow()


def _date_yyyymmdd(value: object) -> str:
    text = str(value or "").strip()
    digits = "".join(ch for ch in text[:10] if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else text
