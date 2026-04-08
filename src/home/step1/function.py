"""
Step 1 thin adapter layer.

The heavy Step 1 logic now lives in:
- state.py / facade.py: centralized state
- controller.py: orchestration
- use_cases.py: import flows
- wind_normalize_service.py: wind normalization
- file_service.py / netcdf_info_service.py / variable_detector.py: infrastructure
"""

from __future__ import annotations

import os

from .background_runner import BackgroundRunner
from .controller import Step1Controller
from .facade import Step1Facade
from .state import ForcingField
from .view_adapter import Step1ViewAdapter
from setting.language_manager import tr


class StepOneFunctionsMixin:
    """Thin compatibility mixin for Step 1."""

    def _set_home_forcing_button_text(self, button, text: str, filled: bool = False):
        """设置主页强迫场按钮文本并根据状态着色"""
        if not button:
            return
        button.setText(text)
        try:
            button.setProperty("filled", filled)
        except Exception:
            pass
        if hasattr(self, "_get_button_style"):
            base_style = self._get_button_style()
            button.setStyleSheet(base_style)
            try:
                button.style().unpolish(button)
                button.style().polish(button)
            except Exception:
                pass

    @property
    def step1_facade(self) -> Step1Facade:
        return self._ensure_step1_runtime().facade

    @property
    def step1_controller(self) -> Step1Controller:
        return self._ensure_step1_runtime()

    @property
    def variable_detector(self):
        return self.step1_controller.variable_detector

    @property
    def file_path_manager(self):
        return self.step1_controller.file_path_manager

    @property
    def file_service(self):
        return self.step1_controller.file_service

    @property
    def netcdf_info_service(self):
        return self.step1_controller.netcdf_info_service

    @property
    def selected_origin_file(self):
        return self.step1_facade.get_file(ForcingField.WIND)

    @selected_origin_file.setter
    def selected_origin_file(self, value):
        self.step1_facade.set_file(ForcingField.WIND, value)

    @property
    def selected_current_file(self):
        return self.step1_facade.get_file(ForcingField.CURRENT)

    @selected_current_file.setter
    def selected_current_file(self, value):
        self.step1_facade.set_file(ForcingField.CURRENT, value)

    @property
    def selected_level_file(self):
        return self.step1_facade.get_file(ForcingField.LEVEL)

    @selected_level_file.setter
    def selected_level_file(self, value):
        self.step1_facade.set_file(ForcingField.LEVEL, value)

    @property
    def selected_ice_file(self):
        return self.step1_facade.get_file(ForcingField.ICE)

    @selected_ice_file.setter
    def selected_ice_file(self, value):
        self.step1_facade.set_file(ForcingField.ICE, value)

    def choose_wind_field_file(self):
        self.step1_controller.choose_file(ForcingField.WIND)

    def choose_current_field_file(self):
        self.step1_controller.choose_file(ForcingField.CURRENT)

    def choose_level_field_file(self):
        self.step1_controller.choose_file(ForcingField.LEVEL)

    def choose_ice_field_file(self):
        self.step1_controller.choose_file(ForcingField.ICE)

    def _detect_and_fill_forcing_fields(self):
        self.step1_controller.refresh_from_workdir(getattr(self, "selected_folder", None))

    def view_all_field_files_info(self):
        self.step1_controller.view_all_info()

    def _print_nc_file_info(self, file_path):
        self.netcdf_info_service.print_nc_file_info(file_path)

    def _check_wind_variables(self, file_path):
        return self.variable_detector.check_wind_variables(file_path)

    def _check_current_variables(self, file_path):
        return self.variable_detector.check_current_variables(file_path)

    def _check_level_variables(self, file_path):
        return self.variable_detector.check_level_variables(file_path)

    def _check_ice_variables(self, file_path):
        return self.variable_detector.check_ice_variables(file_path)

    def _detect_all_forcing_fields_in_file(self, file_path):
        return self.variable_detector.detect_all_forcing_fields_in_file(file_path)

    def _detect_forcing_fields(self, file_path):
        return self.variable_detector.detect_forcing_fields(file_path)

    def _generate_forcing_filename(self, fields, auto_associate=True):
        return self.file_path_manager.generate_forcing_filename(fields, auto_associate)

    def _parse_forcing_filename(self, filename):
        return self.file_path_manager.parse_forcing_filename(filename)

    def _copy_and_fix_forcing_file(self, source_file, target_file, process_mode="copy"):
        return self.file_service.copy_and_fix_forcing_file(source_file, target_file, process_mode)

    def _set_level_file_from_path(self, file_path, filename):
        self._set_file_from_path(ForcingField.LEVEL, file_path, filename)

    def _set_wind_file_from_path(self, file_path, filename):
        self._set_file_from_path(ForcingField.WIND, file_path, filename)

    def _set_ice_file_from_path(self, file_path, filename):
        self._set_file_from_path(ForcingField.ICE, file_path, filename)

    def _set_current_file_from_path(self, file_path, filename):
        self._set_file_from_path(ForcingField.CURRENT, file_path, filename)

    def _load_latlon_from_source_file(self, file_path):
        self.step1_controller.write_lonlat_from_file(file_path)

    def reorder_nc(self, origin_file_path=None, output_file_path=None):
        source_file = origin_file_path or self.selected_origin_file
        output_file = output_file_path
        if output_file is None and getattr(self, "selected_folder", None):
            output_file = os.path.join(self.selected_folder, "wind.nc")
        return self.step1_controller.normalize_wind_file(source_file, output_file)

    def _ensure_step1_runtime(self) -> Step1Controller:
        controller = getattr(self, "_step1_controller_instance", None)
        if controller is not None:
            return controller

        facade = getattr(self, "_step1_facade_instance", None)
        if facade is None:
            facade = Step1Facade()
            self._step1_facade_instance = facade

        view = getattr(self, "_step1_view_instance", None)
        if view is None:
            view = Step1ViewAdapter(self)
            self._step1_view_instance = view

        runner = getattr(self, "_step1_background_runner", None)
        if runner is None:
            runner = BackgroundRunner(self)
            self._step1_background_runner = runner

        controller = Step1Controller(
            owner=self,
            facade=facade,
            view=view,
            background_runner=runner,
        )
        self._step1_controller_instance = controller
        if getattr(self, "selected_folder", None):
            facade.set_selected_folder(self.selected_folder)
        return controller

    def _set_file_from_path(self, field: ForcingField, file_path, filename):
        del filename
        message_map = {
            ForcingField.WIND: tr("log_auto_fill_wind", "✅ 检测到风场变量（u10/v10），已自动填充风场"),
            ForcingField.CURRENT: tr("log_auto_fill_current", "✅ 检测到流场变量（uo/vo），已自动填充流场"),
            ForcingField.LEVEL: tr("log_auto_fill_level", "✅ 检测到水位场变量 'zos'，已自动填充水位场"),
            ForcingField.ICE: tr("log_auto_fill_ice", "✅ 检测到海冰场变量 'siconc'，已自动填充海冰场"),
        }
        self.step1_controller.set_file_path(field, file_path, log_message=message_map[field])
