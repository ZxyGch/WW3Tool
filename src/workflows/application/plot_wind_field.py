"""风场填色图绘制用例 — 从风场 NetCDF 生成 10m 风速空间分布图序列。

供 CLI ``plot-wind-field`` 命令与桌面后处理面板调用。

流水线步骤：后处理（Step 4 结果可视化）— 风场。

输入/输出
---------
- 输入：``PipelineConfig``（``plot.wind_field.*`` 与结果目录）及风场 nc 文件路径
- 输出：``WindFieldResult``（输出目录、PNG 列表、成功标志与错误信息）
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..domain.config_models import PipelineConfig
from ..infrastructure.plot.photo_output import SUBDIR_WIND_FIELD, collect_photo_files, photo_subdir
from ..support.logging import CoreLogger, LogCallback
from ..support.process_worker import run_plot_worker
from ..support.translations import tr


# Canonical wind-field flag type codes. These are the only values that
# ``WindFieldConfig.flag_type`` (params.yml) and the worker should see.
# UI labels remain localized via ``tr(...)``.
WIND_FLAG_ARROW = "arrow"
WIND_FLAG_BARB = "barb"
WIND_FLAG_NONE = "none"

_LEGACY_FLAG_ALIASES = {
    "箭头": WIND_FLAG_ARROW,
    "风旗": WIND_FLAG_BARB,
    "无": WIND_FLAG_NONE,
    "arrow": WIND_FLAG_ARROW,
    "barb": WIND_FLAG_BARB,
    "none": WIND_FLAG_NONE,
}


def normalize_wind_flag_type(value: object, *, default: str = WIND_FLAG_ARROW) -> str:
    """Normalize ``flag_type`` to one of ``arrow`` / ``barb`` / ``none``.

    Accepts legacy Chinese labels (``"箭头"`` / ``"风旗"`` / ``"无"``),
    canonical English codes, and ``None``. Unknown values fall back to
    ``default``.
    """
    if value is None:
        return default
    raw = str(value).strip()
    if not raw:
        return default
    return _LEGACY_FLAG_ALIASES.get(raw, default)


@dataclass
class WindFieldResult:
    """风场图绘制操作的返回结果。

    Attributes:
        output_folder: 结果输出根目录（图片位于其下 ``photo/field/`` 子目录）。
        image_files: 生成的 PNG 图片路径列表。
        messages: 执行过程中的日志消息。
        success: 操作是否成功完成。
        error: 失败时的错误描述；成功时为 ``None``。
    """

    output_folder: str
    image_files: List[str] = field(default_factory=list)
    messages: List[str] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None


def _resolve_result_folder(config: PipelineConfig) -> Path:
    """解析结果目录：使用 ``workdir``。"""
    return config.workdir.path


def _collect_wind_images(output_folder: str) -> List[str]:
    """在 ``output_folder/photo/wind_field/`` 下收集 ``wind_*.png`` 文件路径。"""
    return collect_photo_files(output_folder, SUBDIR_WIND_FIELD, "wind_*.png")


def run_wind_field(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    wind_file: str = "",
    time_step_hours: Optional[float] = None,
    flag_type: Optional[str] = None,
    density_step: Optional[int] = None,
) -> WindFieldResult:
    """从风场 NetCDF 文件生成 10m 风速填色图序列。

    Args:
        config: 流水线配置（``plot.wind_field`` 段提供默认值）。
        log: 可选日志回调。
        wind_file: 风场 NetCDF 文件路径；为空时自动在结果目录中查找。
        time_step_hours: 输出时间间隔（小时），覆盖配置中的值。
        flag_type: 叠加标志类型（``"arrow"`` / ``"barb"`` / ``"none"``；
            旧值 ``"箭头"`` / ``"风旗"`` / ``"无"`` 仍被规范化接受）。
        density_step: 箭头/风旗稀疏化步长。

    Returns:
        ``WindFieldResult``；worker 报错时 ``success=False``。
    """
    from ..infrastructure.plot.wind_field_worker import _make_wind_field_worker

    logger = CoreLogger(callback=log)
    result_folder = _resolve_result_folder(config)
    cfg = config.plot.wind_field

    # Resolve each setting: explicit caller value > config > built-in default.
    # None means "caller did not provide it" (the form/UI always passes a value),
    # so an explicit form value is never clobbered by the config.
    # [EN] Resolution order is caller > config > default; None = not provided.
    if time_step_hours is None:
        time_step_hours = cfg.time_step_hours if cfg.time_step_hours is not None else 24.0
    if flag_type is None:
        flag_type = cfg.flag_type
    flag_type = normalize_wind_flag_type(flag_type)
    if density_step is None:
        density_step = cfg.flag_density  # may stay None; worker auto-picks a stride

    # Resolve wind file: fall back to auto-discovery in result folder
    if not wind_file:
        candidates = glob.glob(os.path.join(str(result_folder), "*.nc"))
        if candidates:
            wind_file = candidates[0]
            logger.log(
                tr("wind_auto_found_file", "📂 自动找到风场文件: {file}")
                .format(file=os.path.basename(wind_file))
            )
        else:
            error_msg = tr("wind_file_not_found", "❌ 未找到风场文件，请先选择风场文件或完成转换")
            logger.log(error_msg)
            return WindFieldResult(
                output_folder=str(result_folder),
                messages=list(logger.messages),
                success=False,
                error=error_msg,
            )

    out_dir = str(result_folder)

    worker_result = run_plot_worker(
        _make_wind_field_worker,
        (wind_file, out_dir, time_step_hours, flag_type, density_step),
        on_log=logger.log,
    )

    images = _collect_wind_images(out_dir)

    # Detect worker-level errors: if worker returned empty list but logged
    # error messages, or if result contains an error dict.
    if worker_result and isinstance(worker_result, dict) and worker_result.get("status") == "error":
        return WindFieldResult(
            output_folder=out_dir,
            image_files=images,
            messages=list(logger.messages),
            success=False,
            error=str(
                worker_result.get("error", tr("unknown_error", "❌ 未知错误"))
            ),
        )

    if not images and not (worker_result and isinstance(worker_result, list) and len(worker_result) > 0):
        logger.log(
            tr("wind_no_images_generated",
               "⚠️ 未生成风场图，检查数据是否为空")
        )

    logger.log(
        tr("plotting_wind_field_generated_to",
           "✅ 风场图已生成至：{path}")
        .format(path=photo_subdir(out_dir, SUBDIR_WIND_FIELD))
    )
    return WindFieldResult(
        output_folder=out_dir,
        image_files=images if images else (worker_result if isinstance(worker_result, list) else []),
        messages=list(logger.messages),
    )
