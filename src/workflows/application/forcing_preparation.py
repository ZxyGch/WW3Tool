"""Step 2 强迫场准备用例。

将配置中指定的风、流、水位、海冰 NetCDF 文件导入工作目录，
执行变量检测、路径规范化与（可选）风场归一化，供后续 WW3 预处理使用。

流水线步骤：Step 2（强迫场准备）。

输入/输出
---------
- 输入：``PipelineConfig``（含 ``forcing.*`` 路径与处理模式）
- 输出：``Step2Files``，记录各场类型在工作目录中的实际文件路径

[EN] Step 2 forcing field preparation use case.

Imports wind, current, water level, and ice NetCDF files specified in the configuration
into the workdir, performing variable detection, path normalization, and optional wind
field normalization for subsequent WW3 preprocessing.

Pipeline step: Step 2 (forcing preparation).

Input/Output
------------
- Input: ``PipelineConfig`` (containing ``forcing.*`` paths and processing mode)
- Output: ``Step2Files``, recording actual file paths for each field type in the workdir
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ..domain.forcing_fields import ForcingField, Step2Files
from ..domain.config_models import PipelineConfig
from ..infrastructure.forcing.file_path_manager import FilePathManager
from ..infrastructure.forcing.file_service import FileService
from ..infrastructure.forcing.use_cases import AutoAssociateUseCase, ImportForcingFileUseCase
from ..infrastructure.forcing.variable_detector import VariableDetector
from ..support.translations import tr


def _forcing_import_error_message(result) -> str:
    """将导入失败结果转为用户可读错误信息。

    [EN] Convert an import failure result into a user-readable error message.
    """
    if result.error:
        return str(result.error)
    reason = str(result.invalid_reason or "")
    field = getattr(result.field, "value", None) or ""
    if reason == "missing_variables":
        return tr(
            "step2_field_missing_vars",
            "{field} 文件缺少所需变量，请检查 NetCDF 内容",
        ).format(field=field)
    if reason:
        return reason
    return tr("step2_forcing_import_failed", "❌ 强迫场导入失败").format()


def prepare_forcing(
    config: PipelineConfig,
    logger: CoreLogger,
    *,
    fields: Iterable[ForcingField] | None = None,
) -> Step2Files:
    """按配置导入并准备强迫场文件。

    默认处理全部四类场；传入 ``fields`` 时可仅更新 UI 触发的单个场类型。
    在导入前会检查强迫场范围是否覆盖网格范围（如果网格配置存在）。

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
    Before import, checks if forcing extent covers the grid extent (if grid config exists).

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

    # 检查强迫场范围是否覆盖网格范围（如果网格配置存在）
    _check_and_log_forcing_coverage(config, logger)

    variable_detector = VariableDetector()
    path_manager = FilePathManager()
    file_service = FileService(logger=logger)
    auto = AutoAssociateUseCase()
    importer = ImportForcingFileUseCase(
        variable_detector=variable_detector,
        path_manager=path_manager,
        file_service=file_service,
        auto_associate_use_case=auto,
        log=logger.log,
    )

    files = Step2Files()
    all_fields = [
        (ForcingField.WIND, config.forcing.wind),
        (ForcingField.CURRENT, config.forcing.current),
        (ForcingField.LEVEL, config.forcing.level),
        (ForcingField.ICE, config.forcing.ice),
    ]
    processed_sources: set[str] = set()
    crop_bbox = config.forcing.crop_bbox or None
    for field, path in all_fields:
        if field not in requested_fields or path is None:
            continue
        source_path = str(Path(path).expanduser().resolve())
        if config.forcing.auto_associate and source_path in processed_sources:
            continue
        result = importer.execute(
            field,
            source_path,
            str(workdir),
            config.forcing.auto_associate,
            config.forcing.process_mode,
            crop_time_range=config.forcing.crop_time_range or None,
            crop_bbox=crop_bbox,
        )
        if not result.success:
            raise RuntimeError(_forcing_import_error_message(result))
        if config.forcing.auto_associate:
            processed_sources.add(source_path)
        files = _merge(files, result.files_patch)

    return files


def _check_and_log_forcing_coverage(config: PipelineConfig, logger: CoreLogger) -> None:
    """检查强迫场范围是否覆盖网格范围，并记录警告。

    如果网格配置不存在或无效，跳过检查。
    覆盖不足时记录警告但不中断流程（CLI 场景）。

    [EN] Check forcing extent vs grid extent and log warnings.
    Skips if grid config is missing/invalid. Logs warnings but does not block (CLI mode).
    """
    from .forcing_coverage_checker import check_lonlat_coverage

    # 尝试获取网格范围
    grid = config.grid
    if not grid or not grid.outer:
        return  # 无网格配置，跳过检查

    outer = grid.outer
    try:
        g_west = float(outer.lon_west)
        g_east = float(outer.lon_east)
        g_south = float(outer.lat_south)
        g_north = float(outer.lat_north)
    except (AttributeError, TypeError, ValueError):
        return  # 网格范围无效，跳过检查

    # 获取强迫场路径
    forcing_paths = {}
    field_names = {}
    for key, field in [
        ("wind", ForcingField.WIND),
        ("current", ForcingField.CURRENT),
        ("level", ForcingField.LEVEL),
        ("ice", ForcingField.ICE),
    ]:
        path = getattr(config.forcing, key, None)
        if path:
            forcing_paths[key] = str(Path(path).expanduser().resolve())
            field_names[key] = tr(
                f"step2_field_{key}",
                {"wind": "风场", "current": "流场", "level": "水位场", "ice": "海冰场"}[key],
            )

    if not forcing_paths:
        return  # 无强迫场，跳过检查

    issues = check_lonlat_coverage(g_west, g_east, g_south, g_north, forcing_paths, field_names)
    if not issues:
        return

    # 构建警告消息
    messages = []
    for issue in issues:
        if issue.issue_type == "insufficient":
            bounds = issue.bounds
            messages.append(
                tr(
                    "step2_forcing_coverage_warning_detail",
                    "• {name}：经度 [{lon_min:.2f}, {lon_max:.2f}]，纬度 [{lat_min:.2f}, {lat_max:.2f}]\n"
                    "  网格范围：经度 [{grid_lon_west:.2f}, {grid_lon_east:.2f}]，纬度 [{grid_lat_south:.2f}, {grid_lat_north:.2f}]",
                ).format(
                    name=issue.field_name,
                    lon_min=bounds.lon_min,
                    lon_max=bounds.lon_max,
                    lat_min=bounds.lat_min,
                    lat_max=bounds.lat_max,
                    grid_lon_west=issue.grid_lon[0],
                    grid_lon_east=issue.grid_lon[1],
                    grid_lat_south=issue.grid_lat[0],
                    grid_lat_north=issue.grid_lat[1],
                )
            )
        elif issue.issue_type == "read_failed":
            messages.append(
                tr(
                    "step2_forcing_coverage_read_failed_detail",
                    "• {name}：{path}（读取失败：{error}）",
                ).format(
                    name=issue.field_name,
                    path=issue.path,
                    error=issue.error,
                )
            )

    logger.log(
        tr(
            "step2_forcing_coverage_warning_cli",
            "⚠️ 强迫场范围警告：以下文件范围可能不足或读取失败（将继续导入）：\n{details}",
        ).format(details="\n\n".join(messages))
    )


def _merge(target: Step2Files, patch: Step2Files) -> Step2Files:
    """将 patch 中的非空场路径合并到 target 副本中。

    [EN] Merge non-empty field paths from patch into a copy of target.
    """
    out = target.copy()
    for field in (ForcingField.WIND, ForcingField.CURRENT, ForcingField.LEVEL, ForcingField.ICE):
        path = patch.get(field)
        if path:
            out.set(field, path)
    return out
