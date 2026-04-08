"""
Step 1 controller.
"""

from __future__ import annotations

import os
from typing import Optional

from setting.language_manager import tr

from .background_runner import BackgroundRunner
from .facade import Step1Facade
from .file_path_manager import FilePathManager
from .file_service import FileService
from .netcdf_info_service import NetCDFInfoService
from .state import FORCING_FIELD_ORDER, ForcingField, Step1Files
from .use_cases import (
    AutoAssociateUseCase,
    ImportForcingFileUseCase,
    ImportWindForcingUseCase,
    ScanWorkdirForcingUseCase,
)
from .variable_detector import VariableDetector
from .view_adapter import Step1ViewAdapter
from .wind_normalize_service import WindNormalizeService


class _WindowSignalLogger:
    """Thread-safe logger adapter backed by MainWindow signals."""

    def __init__(self, window) -> None:
        self.window = window
        self.log_signal = getattr(window, "log_signal", None)

    def log(self, message: str) -> None:
        if self.log_signal is not None:
            self.log_signal.emit(message)
            return
        if hasattr(self.window, "log"):
            self.window.log(message)


class Step1Controller:
    """Coordinates Step 1 view, state, and use cases."""

    def __init__(
        self,
        owner,
        facade: Step1Facade,
        view: Step1ViewAdapter,
        background_runner: Optional[BackgroundRunner] = None,
    ) -> None:
        self.owner = owner
        self.facade = facade
        self.view = view
        self.background_runner = background_runner or BackgroundRunner(owner)

        self._logger = _WindowSignalLogger(owner)
        self.variable_detector = VariableDetector()
        self.file_path_manager = FilePathManager()
        self.file_service = FileService(logger=self._logger)
        self.netcdf_info_service = NetCDFInfoService(logger=self._logger)
        self.wind_normalize_service = WindNormalizeService()

        auto_associate_use_case = AutoAssociateUseCase()
        self.import_file_use_case = ImportForcingFileUseCase(
            variable_detector=self.variable_detector,
            path_manager=self.file_path_manager,
            file_service=self.file_service,
            auto_associate_use_case=auto_associate_use_case,
            log=self._logger.log,
        )
        self.import_wind_use_case = ImportWindForcingUseCase(
            variable_detector=self.variable_detector,
            path_manager=self.file_path_manager,
            file_service=self.file_service,
            normalizer=self.wind_normalize_service,
            auto_associate_use_case=auto_associate_use_case,
            log=self._logger.log,
        )
        self.scan_workdir_use_case = ScanWorkdirForcingUseCase(self.file_service)

    def choose_file(self, field: ForcingField) -> None:
        self._sync_context()
        file_path = self.view.pick_file(field)
        if not file_path:
            return

        if field != ForcingField.WIND:
            self.netcdf_info_service.print_nc_file_info(file_path)

        if not self.facade.state.selected_folder:
            self.view.log(tr("log_please_select_workdir", "❌ 请先选择或创建工作目录！"))
            return

        if field == ForcingField.WIND:
            self._choose_wind(file_path)
        else:
            self._choose_regular_field(field, file_path)

    def refresh_from_workdir(self, selected_folder: Optional[str] = None) -> None:
        self._sync_context(selected_folder)
        files = self.scan_workdir_use_case.execute(self.facade.state.selected_folder)
        self.facade.replace_files(files)
        self.view.render_state(self.facade.snapshot())

    def view_all_info(self) -> None:
        state = self.facade.snapshot()
        field_titles = {
            ForcingField.WIND: tr("step4_forcing_field_wind", "风场"),
            ForcingField.CURRENT: tr("step4_forcing_field_current", "流场"),
            ForcingField.LEVEL: tr("step4_forcing_field_level", "水位场"),
            ForcingField.ICE: tr("step4_forcing_field_ice", "海冰场"),
        }

        field_files: list[tuple[str, str]] = []
        for field in FORCING_FIELD_ORDER:
            path = state.files.get(field)
            if path and os.path.exists(str(path)):
                field_files.append((field_titles[field], path))

        if not field_files:
            self.view.log(tr("view_no_field_files", "❌ 没有已选择的场文件，请先选择场文件"))
            return

        for field_name, file_path in field_files:
            self.netcdf_info_service.print_step1_field_overview(field_name, file_path)
        self.view.log("=" * 70)

    def write_lonlat_from_file(self, file_path: Optional[str]) -> None:
        if not file_path:
            return
        bounds = self.netcdf_info_service.get_lonlat_bounds(file_path)
        if bounds:
            self.view.write_lonlat_to_step2(bounds)

    def normalize_wind_file(self, source_file: Optional[str], output_file: Optional[str]) -> bool:
        self._sync_context()
        source_file = source_file or self.facade.get_file(ForcingField.WIND)
        output_file = output_file or self._default_wind_output()
        return self.wind_normalize_service.normalize(source_file, output_file, log=self._logger.log)

    def set_file_path(self, field: ForcingField, file_path: Optional[str], *, log_message: Optional[str] = None) -> None:
        files_patch = Step1Files()
        files_patch.set(field, file_path)
        self.apply_files_patch(files_patch)
        if log_message:
            self.view.log(log_message)

    def apply_files_patch(self, files_patch: Step1Files) -> None:
        self.facade.update_files(files_patch)
        self.view.render_state(self.facade.snapshot())

    def _choose_regular_field(self, field: ForcingField, file_path: str) -> None:
        state = self._sync_context()
        result = self.import_file_use_case.execute(
            field=field,
            file_path=file_path,
            selected_folder=state.selected_folder or "",
            auto_associate=state.auto_associate,
            process_mode=state.process_mode,
        )
        if not result.success:
            self._handle_regular_failure(field, result.error or result.invalid_reason or "")
            return

        self.apply_files_patch(result.files_patch)
        self.view.log(self._selected_message(field).format(path=result.display_log_path or file_path))

    def _choose_wind(self, file_path: str) -> None:
        state = self._sync_context()
        if state.is_processing:
            return

        loading_message = tr("step1_forcing_convert_loading_message", "请稍候…")
        self.facade.set_processing(True, loading_message)
        self.view.show_loading(loading_message)

        def _task():
            current_state = self.facade.snapshot()
            return self.import_wind_use_case.execute(
                file_path=file_path,
                selected_folder=current_state.selected_folder or "",
                auto_associate=current_state.auto_associate,
                process_mode=current_state.process_mode,
            )

        self.background_runner.run(_task, self._on_wind_import_finished)

    def _on_wind_import_finished(self, result) -> None:
        self.facade.set_processing(False)
        self.view.hide_loading()

        if isinstance(result, dict):
            success = bool(result.get("success"))
            invalid_reason = result.get("invalid_reason")
            error = result.get("error")
            actual_file_path = result.get("actual_file_path")
            files_patch = result.get("files_patch")
        else:
            success = bool(getattr(result, "success", False))
            invalid_reason = getattr(result, "invalid_reason", None)
            error = getattr(result, "error", None)
            actual_file_path = getattr(result, "actual_file_path", None)
            files_patch = getattr(result, "files_patch", None)

        if not success:
            if invalid_reason == "missing_variables":
                self.view.show_notice(
                    "warning",
                    tr("wind_file_missing_vars", "缺少风场变量"),
                    tr("wind_file_missing_vars_msg", "文件不包含风场变量（u10/v10），请选择正确的风场文件"),
                )
            elif error:
                self.view.log(str(error))
            return

        if isinstance(files_patch, Step1Files):
            self.apply_files_patch(files_patch)
        self.write_lonlat_from_file(actual_file_path)
        self.view.show_notice(
            "success",
            tr("step1_forcing_convert_success_title", "处理完成"),
            tr("step1_forcing_convert_success_content", "强迫场文件已处理完成：{filename}").format(
                filename=os.path.basename(actual_file_path or ""),
            ),
        )

    def _handle_regular_failure(self, field: ForcingField, error: str) -> None:
        if error == "missing_variables":
            self.view.show_notice("warning", *self._missing_variable_notice(field))
            return
        if error:
            self.view.log(str(error))

    def _missing_variable_notice(self, field: ForcingField) -> tuple[str, str]:
        notice_map = {
            ForcingField.CURRENT: (
                tr("current_file_missing_vars", "缺少流场变量"),
                tr("current_file_missing_vars_msg", "文件不包含流场变量（uo/vo），请选择正确的流场文件"),
            ),
            ForcingField.LEVEL: (
                tr("level_file_missing_vars", "缺少水位场变量"),
                tr("level_file_missing_vars_msg", "文件不包含水位场变量（zos），请选择正确的水位场文件"),
            ),
            ForcingField.ICE: (
                tr("ice_file_missing_vars", "缺少海冰场变量"),
                tr("ice_file_missing_vars_msg", "文件不包含海冰场变量（siconc），请选择正确的海冰场文件"),
            ),
        }
        return notice_map[field]

    @staticmethod
    def _selected_message(field: ForcingField) -> str:
        message_map = {
            ForcingField.CURRENT: tr("current_file_selected", "📂 已选择流场文件: {path}"),
            ForcingField.LEVEL: tr("level_file_selected", "📂 已选择水位场文件: {path}"),
            ForcingField.ICE: tr("ice_file_selected", "📂 已选择海冰场文件: {path}"),
        }
        return message_map[field]

    def _sync_context(self, selected_folder: Optional[str] = None):
        self.facade.reload_runtime_options()
        folder = selected_folder if selected_folder is not None else getattr(self.owner, "selected_folder", None)
        self.facade.set_selected_folder(folder)
        return self.facade.state

    def _default_wind_output(self) -> Optional[str]:
        selected_folder = self.facade.state.selected_folder or getattr(self.owner, "selected_folder", None)
        if not selected_folder:
            return None
        return os.path.join(selected_folder, "wind.nc")
