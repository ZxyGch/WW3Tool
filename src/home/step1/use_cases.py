"""
Step 1 use cases.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field as dataclass_field
from typing import Callable, Optional

from setting.language_manager import tr

from .file_path_manager import FilePathManager
from .file_service import FileService
from .state import ForcingField, Step1Files
from .variable_detector import VariableDetector
from .wind_normalize_service import WindNormalizeService


@dataclass
class ForcingImportResult:
    success: bool
    field: Optional[ForcingField] = None
    invalid_reason: Optional[str] = None
    error: Optional[str] = None
    target_filename: str = ""
    actual_file_path: Optional[str] = None
    normalized_wind_path: Optional[str] = None
    display_log_path: Optional[str] = None
    detected_fields: dict[str, bool] = dataclass_field(default_factory=dict)
    files_patch: Step1Files = dataclass_field(default_factory=Step1Files)


class AutoAssociateUseCase:
    """Maps detected combined forcing files into Step 1 selections."""

    def execute(self, detected_fields: dict[str, bool], actual_file_path: str) -> Step1Files:
        files = Step1Files()
        if not actual_file_path:
            return files
        for field_name, detected in (detected_fields or {}).items():
            if detected and field_name in {"wind", "current", "level", "ice"}:
                files.set(ForcingField(field_name), actual_file_path)
        return files


class ImportForcingFileUseCase:
    """Imports current/level/ice forcing files into the work directory."""

    def __init__(
        self,
        variable_detector: VariableDetector,
        path_manager: FilePathManager,
        file_service: FileService,
        auto_associate_use_case: AutoAssociateUseCase,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._variable_detector = variable_detector
        self._path_manager = path_manager
        self._file_service = file_service
        self._auto_associate_use_case = auto_associate_use_case
        self._log = log

    def execute(
        self,
        field: ForcingField,
        file_path: str,
        selected_folder: str,
        auto_associate: bool,
        process_mode: str,
    ) -> ForcingImportResult:
        inspect_result = self._variable_detector.inspect_forcing_fields(file_path)
        detected_fields = inspect_result.get("detected", {}) or {}
        if not detected_fields.get(field.value, False):
            return ForcingImportResult(success=False, field=field, invalid_reason="missing_variables")

        fields = inspect_result.get("fields", []) or [field.value]
        if auto_associate:
            target_filename = self._path_manager.generate_forcing_filename(fields, auto_associate=True)
        else:
            target_filename = self._path_manager.generate_forcing_filename([field.value], auto_associate=False)
        target_file = os.path.join(selected_folder, target_filename)

        if auto_associate and len(fields) > 1:
            self._emit(
                tr("log_detected_multi_forcing", "ℹ️ 检测到文件包含多个强迫场: {fields}").format(
                    fields=", ".join(fields)
                )
            )
            self._emit(
                tr("log_file_will_save_as", "📁 文件将保存为: {filename}").format(filename=target_filename)
            )

        need_process = self._log_existing_target(file_path, target_file, target_filename)
        if need_process:
            copied_file = self._file_service.copy_and_fix_forcing_file(file_path, target_file, process_mode)
            if not copied_file:
                return ForcingImportResult(
                    success=False,
                    field=field,
                    error=tr("log_copy_fix_failed", "❌ 复制或修复文件失败！"),
                )

        actual_file_path = target_file if need_process or os.path.exists(target_file) else file_path
        files_patch = Step1Files()
        files_patch.set(field, actual_file_path)
        if auto_associate:
            self._merge_files(files_patch, self._auto_associate_use_case.execute(detected_fields, actual_file_path))

        display_log_path = os.path.normpath(file_path)
        if field in {ForcingField.CURRENT, ForcingField.ICE} and process_mode == "move" and need_process:
            display_log_path = os.path.normpath(target_file)

        return ForcingImportResult(
            success=True,
            field=field,
            target_filename=target_filename,
            actual_file_path=actual_file_path,
            display_log_path=display_log_path,
            detected_fields=detected_fields,
            files_patch=files_patch,
        )

    def _log_existing_target(self, file_path: str, target_file: str, target_filename: str) -> bool:
        need_process = True
        if os.path.exists(target_file):
            try:
                if os.path.samefile(file_path, target_file):
                    self._emit(
                        tr(
                            "log_file_exists_same",
                            "ℹ️ 文件已存在于工作目录且与源文件相同: {filename}",
                        ).format(filename=target_filename)
                    )
                    need_process = False
                else:
                    self._emit(
                        tr("log_target_exists_overwrite", "ℹ️ 目标文件已存在，将覆盖: {filename}").format(
                            filename=target_filename
                        )
                    )
            except OSError:
                self._emit(
                    tr("log_target_exists_overwrite", "ℹ️ 目标文件已存在，将覆盖: {filename}").format(
                        filename=target_filename
                    )
                )
        return need_process

    def _emit(self, message: str) -> None:
        if self._log is not None:
            self._log(message)

    @staticmethod
    def _merge_files(target: Step1Files, patch: Step1Files) -> None:
        for field in (ForcingField.WIND, ForcingField.CURRENT, ForcingField.LEVEL, ForcingField.ICE):
            path = patch.get(field)
            if path:
                target.set(field, path)


class ImportWindForcingUseCase:
    """Imports and normalizes wind forcing files."""

    def __init__(
        self,
        variable_detector: VariableDetector,
        path_manager: FilePathManager,
        file_service: FileService,
        normalizer: WindNormalizeService,
        auto_associate_use_case: AutoAssociateUseCase,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._variable_detector = variable_detector
        self._path_manager = path_manager
        self._file_service = file_service
        self._normalizer = normalizer
        self._auto_associate_use_case = auto_associate_use_case
        self._log = log

    def execute(
        self,
        file_path: str,
        selected_folder: str,
        auto_associate: bool,
        process_mode: str,
    ) -> ForcingImportResult:
        inspect_result = self._variable_detector.inspect_forcing_fields(file_path)
        detected_fields = inspect_result.get("detected", {}) or {}
        fields = inspect_result.get("fields", []) or []
        if not detected_fields.get("wind", False):
            return ForcingImportResult(
                success=False,
                field=ForcingField.WIND,
                invalid_reason="missing_variables",
            )

        if not fields:
            fields = ["wind"]

        if auto_associate:
            target_filename = self._path_manager.generate_forcing_filename(fields, auto_associate=True)
        else:
            target_filename = self._path_manager.generate_forcing_filename(["wind"], auto_associate=False)
        target_file = os.path.join(selected_folder, target_filename)

        if auto_associate and len(fields) > 1:
            self._emit(
                tr("log_detected_multi_forcing", "ℹ️ 检测到文件包含多个强迫场: {fields}").format(
                    fields=", ".join(fields)
                )
            )
            self._emit(
                tr("log_file_will_save_as", "📁 文件将保存为: {filename}").format(filename=target_filename)
            )

        need_process = True
        if os.path.exists(target_file):
            try:
                if os.path.samefile(file_path, target_file):
                    self._emit(
                        tr(
                            "log_file_exists_same",
                            "ℹ️ 文件已存在于工作目录且与源文件相同: {filename}",
                        ).format(filename=target_filename)
                    )
                    need_process = False
                else:
                    self._emit(
                        tr("log_target_exists_overwrite", "ℹ️ 目标文件已存在，将覆盖: {filename}").format(
                            filename=target_filename
                        )
                    )
            except OSError:
                self._emit(
                    tr("log_target_exists_overwrite", "ℹ️ 目标文件已存在，将覆盖: {filename}").format(
                        filename=target_filename
                    )
                )

        wind_only_direct = detected_fields.get("wind", False) and not any(
            detected_fields.get(name, False) for name in ("current", "level", "ice")
        )

        if wind_only_direct:
            normalize_ok = self._normalizer.normalize(file_path, target_file, log=self._log)
            if not normalize_ok:
                return ForcingImportResult(
                    success=False,
                    field=ForcingField.WIND,
                    error=tr("log_write_file_failed", "❌ 写入新文件失败"),
                )
            actual_file_path = target_file
            normalized_wind_path = target_file
            same_source_target = False
            try:
                if os.path.exists(target_file):
                    same_source_target = os.path.samefile(file_path, target_file)
            except OSError:
                same_source_target = False
            if process_mode == "move" and not same_source_target and os.path.exists(file_path):
                os.remove(file_path)
        else:
            if need_process:
                copied_file = self._file_service.copy_and_fix_forcing_file(file_path, target_file, process_mode)
                if not copied_file:
                    return ForcingImportResult(
                        success=False,
                        field=ForcingField.WIND,
                        error=tr("log_copy_fix_failed", "❌ 复制或修复文件失败！"),
                    )

            actual_file_path = target_file if need_process or os.path.exists(target_file) else file_path
            normalized_wind_path = os.path.join(selected_folder, "wind.nc")
            normalize_ok = self._normalizer.normalize(actual_file_path, normalized_wind_path, log=self._log)
            if not normalize_ok:
                return ForcingImportResult(
                    success=False,
                    field=ForcingField.WIND,
                    error=tr("log_write_file_failed", "❌ 写入新文件失败"),
                )

        files_patch = Step1Files()
        files_patch.set(ForcingField.WIND, actual_file_path)
        if auto_associate:
            self._merge_files(files_patch, self._auto_associate_use_case.execute(detected_fields, actual_file_path))

        return ForcingImportResult(
            success=True,
            field=ForcingField.WIND,
            target_filename=target_filename,
            actual_file_path=actual_file_path,
            normalized_wind_path=normalized_wind_path,
            display_log_path=os.path.normpath(actual_file_path),
            detected_fields=detected_fields,
            files_patch=files_patch,
        )

    def _emit(self, message: str) -> None:
        if self._log is not None:
            self._log(message)

    @staticmethod
    def _merge_files(target: Step1Files, patch: Step1Files) -> None:
        for field in (ForcingField.WIND, ForcingField.CURRENT, ForcingField.LEVEL, ForcingField.ICE):
            path = patch.get(field)
            if path:
                target.set(field, path)


class ScanWorkdirForcingUseCase:
    """Restores Step 1 files from a work directory."""

    def __init__(self, file_service: FileService) -> None:
        self._file_service = file_service

    def execute(self, selected_folder: Optional[str]) -> Step1Files:
        if not selected_folder:
            return Step1Files()
        return self._file_service.scan_forcing_files(selected_folder)
