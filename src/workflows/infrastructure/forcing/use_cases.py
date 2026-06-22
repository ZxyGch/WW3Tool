"""WW3 Step 1 强迫场导入用例（基础设施层）。

[EN] WW3 Step 1 forcing field import use cases (infrastructure layer).

本模块封装 Step 1「选择并导入强迫场 NetCDF」的 I/O 编排：变量检测、目标路径
生成、复制/移动、风场归一化及多场合并文件的自动关联。类名保留 ``UseCase`` 后缀
为历史兼容；底部类型别名提供更符合基础设施命名的新名称。

[EN] This module encapsulates the I/O orchestration for Step 1 "select and import forcing
NetCDF": variable detection, target path generation, copy/move, wind normalization, and
auto-association of multi-field merged files. Class names retain the ``UseCase`` suffix for
historical compatibility; type aliases at the bottom provide names more consistent with
infrastructure naming conventions.

与 ``workflows.application.forcing_preparation`` 的关系：应用层负责流程与 UI 状态，
本层只处理文件系统与 NetCDF 格式，不包含 Qt 依赖。

[EN] Relationship with ``workflows.application.forcing_preparation``: the application layer
handles workflow and UI state, while this layer only deals with the file system and NetCDF
formats, without any Qt dependencies.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Callable, Optional

from ...domain.forcing_fields import ForcingField, Step1Files
from ...support.translations import tr

from .file_path_manager import FilePathManager
from .file_service import FileService
from .variable_detector import VariableDetector


def _merge_forcing_files(target: Step1Files, patch: Step1Files) -> None:
    """将 ``patch`` 中非空路径合并进 ``target``。

    [EN] Merge non-empty paths from ``patch`` into ``target``.
    """
    for f in (ForcingField.WIND, ForcingField.CURRENT, ForcingField.LEVEL, ForcingField.ICE):
        path = patch.get(f)
        if path:
            target.set(f, path)


@dataclass
class ForcingImportResult:
    """单次强迫场导入操作的返回结构。

    [EN] Return structure for a single forcing import operation.

    属性:
        success: 是否成功完成导入
        field: 本次导入的场类型（失败时也可能有值）
        invalid_reason: 校验失败原因，如 ``missing_variables``
        error: 用户可读错误信息
        target_filename: 写入工作目录的目标文件名
        actual_file_path: 实际使用的源/目标绝对路径
        display_log_path: 日志中展示给用户的路径
        detected_fields: 文件中检测到的场字典
        files_patch: 需合并进 Step 1 状态的路径补丁

    [EN] Attributes:
        success: Whether the import completed successfully
        field: The field type of this import (may be set even on failure)
        invalid_reason: Validation failure reason, e.g. ``missing_variables``
        error: User-readable error message
        target_filename: Target filename written to the working directory
        actual_file_path: Actual source/target absolute path used
        display_log_path: Path displayed to the user in logs
        detected_fields: Dictionary of fields detected in the file
        files_patch: Path patch to merge into Step 1 state
    """
    success: bool
    field: Optional[ForcingField] = None
    invalid_reason: Optional[str] = None
    error: Optional[str] = None
    target_filename: str = ""
    actual_file_path: Optional[str] = None
    display_log_path: Optional[str] = None
    detected_fields: dict[str, bool] = dataclass_field(default_factory=dict)
    files_patch: Step1Files = dataclass_field(default_factory=Step1Files)


class AutoAssociateUseCase:
    """将多场合并 NetCDF 自动映射到 Step 1 各场选择。

    [EN] Automatically map multi-field merged NetCDF files to Step 1 field selections.

    当用户开启「自动关联」且单个文件同时含 wind/current/level/ice 变量时，
    同一文件路径会写入 ``Step1Files`` 的多个槽位。

    [EN] When the user enables "auto-associate" and a single file contains wind/current/level/ice
    variables simultaneously, the same file path is written to multiple slots in ``Step1Files``.
    """

    def execute(self, detected_fields: dict[str, bool], actual_file_path: str) -> Step1Files:
        """根据检测结果填充 ``Step1Files``。

        [EN] Populate ``Step1Files`` based on detection results.

        参数:
            detected_fields: 各场是否存在的布尔字典
            actual_file_path: 已复制到工作目录的文件路径

        [EN] Parameters:
            detected_fields: Boolean dictionary indicating which fields are present
            actual_file_path: File path already copied to the working directory

        返回:
            仅包含检测为 True 的场及其路径的 ``Step1Files``

        [EN] Returns:
            A ``Step1Files`` containing only detected-True fields and their paths.
        """
        files = Step1Files()
        if not actual_file_path:
            return files
        for field_name, detected in (detected_fields or {}).items():
            if detected and field_name in {"wind", "current", "level", "ice"}:
                files.set(ForcingField(field_name), actual_file_path)
        return files


class ImportForcingFileUseCase:
    """导入强迫场 NetCDF 到工作目录（Step 1 统一入口，支持所有场类型）。

    [EN] Import forcing NetCDF to the working directory (Step 1 unified entry,
    supports all field types: wind, current, level, ice).

    所有场类型统一走 ``FileService.copy_and_fix_forcing_file()``，
    内部通过 ``ForcingNormalizeService`` 单遍完成坐标标准化、时间转换、
    纬度翻转和变量重命名。
    """

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
        """执行单场或多场（自动关联）导入。

        [EN] Execute single-field or multi-field (auto-associated) import.

        参数:
            field: 用户选择的场类型（current/level/ice）
            file_path: 源 NetCDF 绝对路径
            selected_folder: WW3 工作目录
            auto_associate: 是否根据文件内变量自动关联其他场
            process_mode: ``copy`` 或 ``move``

        [EN] Parameters:
            field: User-selected field type (current/level/ice)
            file_path: Source NetCDF absolute path
            selected_folder: WW3 working directory
            auto_associate: Whether to auto-associate other fields based on file variables
            process_mode: ``copy`` or ``move``

        返回:
            ``ForcingImportResult``，失败时 ``success=False`` 并附带原因

        [EN] Returns:
            ``ForcingImportResult``; ``success=False`` with reason on failure.
        """
        inspect_result = self._variable_detector.inspect_forcing_fields(file_path)
        detected_fields = inspect_result.get("detected", {}) or {}
        if not detected_fields.get(field.value, False):
            return ForcingImportResult(
                success=False,
                field=field,
                invalid_reason="missing_variables",
                error=tr(
                    "step1_field_missing_vars",
                    "{field} 文件缺少所需变量，请检查 NetCDF 内容",
                ).format(field=field.value),
            )

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
                    error=tr("log_copy_fix_failed", "❌ 复制或修复文件失败"),
                )

        actual_file_path = target_file if need_process or os.path.exists(target_file) else file_path
        files_patch = Step1Files()
        files_patch.set(field, actual_file_path)
        if auto_associate:
            _merge_forcing_files(files_patch, self._auto_associate_use_case.execute(detected_fields, actual_file_path))

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
        """记录目标文件是否已存在，并返回是否仍需复制/修复。

        [EN] Log whether the target file already exists and return whether copy/fix is still needed.
        """
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


class ScanWorkdirForcingUseCase:
    """从已有工作目录恢复 Step 1 强迫场文件列表。

    [EN] Restore the Step 1 forcing file list from an existing working directory.
    """

    def __init__(self, file_service: FileService) -> None:
        self._file_service = file_service

    def execute(self, selected_folder: Optional[str]) -> Step1Files:
        """扫描目录并返回 ``Step1Files``；目录为空或无效时返回空结构。

        [EN] Scan the directory and return ``Step1Files``; returns empty structure if directory is empty or invalid.
        """
        if not selected_folder:
            return Step1Files()
        return self._file_service.scan_forcing_files(selected_folder)


# 更符合基础设施层命名习惯的类型别名（旧 UseCase 名保留以兼容桌面端）
# [EN] Type aliases with names more consistent with infrastructure layer conventions
# (legacy UseCase names retained for desktop-side compatibility)
ForcingAutoAssociator = AutoAssociateUseCase
ForcingFileImporter = ImportForcingFileUseCase
WorkdirForcingScanner = ScanWorkdirForcingUseCase
