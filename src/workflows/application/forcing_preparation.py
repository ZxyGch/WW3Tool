"""Step 1 强迫场准备用例。

将配置中指定的风、流、水位、海冰 NetCDF 文件导入工作目录，
执行变量检测、路径规范化与（可选）风场归一化，供后续 WW3 预处理使用。

流水线步骤：Step 1（强迫场准备）。

输入/输出
---------
- 输入：``PipelineConfig``（含 ``forcing.*`` 路径与处理模式）
- 输出：``Step1Files``，记录各场类型在工作目录中的实际文件路径

[EN] Step 1 forcing field preparation use case.

Imports wind, current, water level, and ice NetCDF files specified in the configuration
into the workdir, performing variable detection, path normalization, and optional wind
field normalization for subsequent WW3 preprocessing.

Pipeline step: Step 1 (forcing preparation).

Input/Output
------------
- Input: ``PipelineConfig`` (containing ``forcing.*`` paths and processing mode)
- Output: ``Step1Files``, recording actual file paths for each field type in the workdir
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ..domain.forcing_fields import ForcingField, Step1Files
from ..domain.config_models import PipelineConfig
from ..infrastructure.forcing.file_path_manager import FilePathManager
from ..infrastructure.forcing.file_service import FileService
from ..infrastructure.forcing.use_cases import AutoAssociateUseCase, ImportForcingFileUseCase, ImportWindForcingUseCase
from ..infrastructure.forcing.variable_detector import VariableDetector
from ..infrastructure.forcing.wind_normalize_service import WindNormalizeService
from ..support.logging import CoreLogger
from ..support.translations import tr


def prepare_forcing(
    config: PipelineConfig,
    logger: CoreLogger,
    *,
    fields: Iterable[ForcingField] | None = None,
) -> Step1Files:
    """按配置导入并准备强迫场文件。

    默认处理全部四类场；传入 ``fields`` 时可仅更新 UI 触发的单个场类型。

    Args:
        config: 流水线配置，含强迫场源路径与 ``process_mode`` / ``auto_associate``。
        logger: 日志记录器，导入过程的消息写入其中。
        fields: 可选，限定本次处理的场类型集合；``None`` 表示全部场。

    Returns:
        工作目录中各场类型的最终文件路径映射。

    Raises:
        RuntimeError: 任一场的导入用例返回失败时。

    [EN] Import and prepare forcing field files according to configuration.
    By default processes all four field types; when ``fields`` is provided, only updates
    the single field type triggered by the UI.

    Args:
        config: Pipeline config with forcing source paths and ``process_mode`` / ``auto_associate``.
        logger: Logger; import messages are written here.
        fields: Optional, restricts the field types to process; ``None`` means all fields.

    Returns:
        Final file path mapping for each field type in the workdir.

    Raises:
        RuntimeError: When any field's import use case returns failure.
    """
    workdir = config.workdir.path
    workdir.mkdir(parents=True, exist_ok=True)
    requested_fields = set(fields) if fields is not None else set(ForcingField)

    variable_detector = VariableDetector()
    path_manager = FilePathManager()
    file_service = FileService(logger=logger)
    auto = AutoAssociateUseCase()
    import_regular = ImportForcingFileUseCase(
        variable_detector=variable_detector,
        path_manager=path_manager,
        file_service=file_service,
        auto_associate_use_case=auto,
        log=logger.log,
    )
    import_wind = ImportWindForcingUseCase(
        variable_detector=variable_detector,
        path_manager=path_manager,
        file_service=file_service,
        normalizer=WindNormalizeService(),
        auto_associate_use_case=auto,
        log=logger.log,
    )

    files = Step1Files()
    if ForcingField.WIND in requested_fields and config.forcing.wind:
        result = import_wind.execute(
            str(config.forcing.wind),
            str(workdir),
            config.forcing.auto_associate,
            config.forcing.process_mode,
        )
        if not result.success:
            raise RuntimeError(result.error or result.invalid_reason or tr("step1_wind_import_failed", "风场导入失败"))
        files = _merge(files, result.files_patch)
        logger.log(tr("step1_wind_prepared", "风场已准备：{path}").format(path=result.actual_file_path))

    regular = [
        (ForcingField.CURRENT, config.forcing.current),
        (ForcingField.LEVEL, config.forcing.level),
        (ForcingField.ICE, config.forcing.ice),
    ]
    for field, path in regular:
        if field not in requested_fields or path is None:
            continue
        result = import_regular.execute(
            field,
            str(path),
            str(workdir),
            config.forcing.auto_associate,
            config.forcing.process_mode,
        )
        if not result.success:
            raise RuntimeError(
                result.error
                or result.invalid_reason
                or tr("step1_field_import_failed", "{field} 导入失败").format(field=field.value)
            )
        files = _merge(files, result.files_patch)
        logger.log(tr("step1_field_prepared", "{field} 已准备：{path}").format(field=field.value, path=result.actual_file_path))

    return files


def _merge(target: Step1Files, patch: Step1Files) -> Step1Files:
    """将 patch 中的非空场路径合并到 target 副本中。

    [EN] Merge non-empty field paths from patch into a copy of target.
    """
    out = target.copy()
    for field in (ForcingField.WIND, ForcingField.CURRENT, ForcingField.LEVEL, ForcingField.ICE):
        path = patch.get(field)
        if path:
            out.set(field, path)
    return out
