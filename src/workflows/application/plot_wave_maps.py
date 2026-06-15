"""WW3 波高填色图与等值线图绘制用例。

从 WW3 输出 NetCDF 生成有效波高（HS）时空分布的填色图或等值线图，
供 CLI ``plot-wave-maps`` / ``plot-contour-maps`` 命令与桌面后处理面板调用。

流水线步骤：后处理（Step 4 结果可视化）— 波高场。

输入/输出
---------
- 输入：``PipelineConfig``（``plot.wave_maps.*`` 与结果目录）
- 输出：``WaveMapsResult``（输出目录、PNG 列表、成功标志与错误信息）
"""

from __future__ import annotations

import os
from ..support.process_worker import run_plot_worker
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..domain.config_models import PipelineConfig, WaveMapsConfig
from ..infrastructure.plot.photo_output import (
    SUBDIR_WAVE_HEIGHT,
    SUBDIR_WAVE_HEIGHT_CONTOUR,
    SUBDIR_WAVE_HEIGHT_VIDEO,
    SUBDIR_WIND_SWELL,
    collect_photo_files,
    photo_subdir,
)
from ..support.logging import CoreLogger, LogCallback
from ..support.translations import tr


@dataclass
class WaveMapsResult:
    """波高图或等值线图绘制操作的返回结果。

    Attributes:
        output_folder: 结果输出根目录（图片位于其下 ``photo/`` 子目录）。
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
    """解析 WW3 结果目录：使用 ``workdir``。"""
    return config.workdir.path


def _collect_images(output_folder: str, pattern: str, subdir: str) -> List[str]:
    """在 ``output_folder/photo/<subdir>/`` 下按 glob 模式收集文件路径。"""
    return collect_photo_files(output_folder, subdir, pattern)


def _resolve_time_step_hours(cfg: WaveMapsConfig, time_step_hours: Optional[float]) -> float:
    """桌面 UI 传入的时间步长优先，否则使用 ``plot.wave_maps.time_step_hours``。"""
    if time_step_hours is not None:
        return float(time_step_hours)
    return float(cfg.time_step_hours)


def _resolve_wave_file(wave_file: Optional[str]) -> Optional[str]:
    if wave_file and os.path.isfile(wave_file):
        return wave_file
    return None


def _resolve_figsize(cfg: WaveMapsConfig) -> tuple:
    """figsize 未配置(None)时回退到 worker 默认 (16, 12)，避免 tuple(None) 崩溃。

    [EN] Fall back to the worker default (16, 12) when figsize is unset (None),
    avoiding a ``tuple(None)`` TypeError.
    """
    return tuple(cfg.figsize) if cfg.figsize else (16, 12)


def _resolve_dpi(cfg: WaveMapsConfig) -> int:
    """dpi 未配置(None)时回退到 worker 默认 300。[EN] Default dpi 300 when unset."""
    return int(cfg.dpi) if cfg.dpi else 300


def run_wave_maps(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    time_step_hours: Optional[float] = None,
    wave_file: Optional[str] = None,
) -> WaveMapsResult:
    """从 WW3 输出 nc 文件生成有效波高填色图序列。

    Args:
        config: 流水线配置（``plot.wave_maps`` 段控制时间步长、DPI 等）。
        log: 可选日志回调。

    Returns:
        ``WaveMapsResult``，图片匹配 ``hs_*.png``；worker 报错时 ``success=False``。
    """
    from ..infrastructure.plot.wave_map_worker import _make_wave_maps_worker

    logger = CoreLogger(callback=log)
    result_folder = _resolve_result_folder(config)
    cfg = config.plot.wave_maps

    output_folder = str(cfg.output_folder) if cfg.output_folder else None
    step_hours = _resolve_time_step_hours(cfg, time_step_hours)

    worker_result = run_plot_worker(
        _make_wave_maps_worker,
        (str(result_folder), step_hours),
        kwargs={
            "FIGSIZE": _resolve_figsize(cfg),
            "DPI": _resolve_dpi(cfg),
            "generate_video": cfg.generate_video,
            "show_land_coastline": cfg.show_land_coastline,
            "output_folder": output_folder,
            "wave_height_file": _resolve_wave_file(wave_file),
        },
        on_log=logger.log,
    )

    out_dir = output_folder or str(result_folder)
    images = _collect_images(out_dir, "hs_*.png", SUBDIR_WAVE_HEIGHT)

    if worker_result and isinstance(worker_result, dict) and worker_result.get("status") == "error":
        return WaveMapsResult(
            output_folder=out_dir,
            image_files=images,
            messages=list(logger.messages),
            success=False,
            error=str(worker_result.get("error", tr("unknown_error", "❌ 未知错误"))),
        )

    logger.log(
        tr("plotting_wave_maps_generated_to", "✅ 波高图已生成至：{path}").format(
            path=photo_subdir(out_dir, SUBDIR_WAVE_HEIGHT)
        )
    )
    return WaveMapsResult(
        output_folder=out_dir,
        image_files=images,
        messages=list(logger.messages),
    )


def run_contour_maps(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    time_step_hours: Optional[float] = None,
    wave_file: Optional[str] = None,
) -> WaveMapsResult:
    """从 WW3 输出 nc 文件生成有效波高等值线图序列。

    Args:
        config: 流水线配置（``plot.wave_maps`` 段控制时间步长、DPI 等）。
        log: 可选日志回调。

    Returns:
        ``WaveMapsResult``，图片匹配 ``contour_hs_*.png``；worker 报错时 ``success=False``。
    """
    from ..infrastructure.plot.wave_map_worker import _make_contour_maps_worker

    logger = CoreLogger(callback=log)
    result_folder = _resolve_result_folder(config)
    cfg = config.plot.wave_maps

    output_folder = str(cfg.output_folder) if cfg.output_folder else None
    step_hours = _resolve_time_step_hours(cfg, time_step_hours)

    worker_result = run_plot_worker(
        _make_contour_maps_worker,
        (str(result_folder), step_hours),
        kwargs={
            "FIGSIZE": _resolve_figsize(cfg),
            "DPI": _resolve_dpi(cfg),
            "show_land_coastline": cfg.show_land_coastline,
            "output_folder": output_folder,
            "wave_height_file": _resolve_wave_file(wave_file),
        },
        on_log=logger.log,
    )

    out_dir = output_folder or str(result_folder)
    images = _collect_images(out_dir, "contour_hs_*.png", SUBDIR_WAVE_HEIGHT_CONTOUR)

    if worker_result and isinstance(worker_result, dict) and worker_result.get("status") == "error":
        return WaveMapsResult(
            output_folder=out_dir,
            image_files=images,
            messages=list(logger.messages),
            success=False,
            error=str(worker_result.get("error", tr("unknown_error", "❌ 未知错误"))),
        )

    logger.log(
        tr("plotting_contour_generated_to", "✅ 等值线图已生成至：{path}").format(
            path=photo_subdir(out_dir, SUBDIR_WAVE_HEIGHT_CONTOUR)
        )
    )
    return WaveMapsResult(
        output_folder=out_dir,
        image_files=images,
        messages=list(logger.messages),
    )


def run_wind_swell_maps(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    time_step_hours: Optional[float] = None,
    wave_file: Optional[str] = None,
) -> WaveMapsResult:
    """从 WW3 输出 nc 文件分别生成风浪（wind-sea）与涌浪（swell）填色图序列。

    内部依次调用 worker 两次：``v=2``（phs0 风浪场）和 ``v=3``（phs1 涌浪场），
    收集 ``phs0_*.png`` 与 ``phs1_*.png`` 图片。

    Args:
        config: 流水线配置（``plot.wave_maps`` 段控制时间步长、DPI 等）。
        log: 可选日志回调。

    Returns:
        ``WaveMapsResult``，图片包含风浪与涌浪两组 PNG；任一 worker 报错时 ``success=False``。
    """
    from ..infrastructure.plot.wave_map_worker import _make_wave_maps_worker

    logger = CoreLogger(callback=log)
    result_folder = _resolve_result_folder(config)
    cfg = config.plot.wave_maps

    output_folder = str(cfg.output_folder) if cfg.output_folder else None
    out_dir = output_folder or str(result_folder)
    step_hours = _resolve_time_step_hours(cfg, time_step_hours)
    resolved_wave_file = _resolve_wave_file(wave_file)

    all_images: List[str] = []
    has_error = False
    error_msg: Optional[str] = None

    for v_val, label in ((2, "wind-sea"), (3, "swell")):
        logger.log(tr("plotting_wind_swell_start", "🔄 开始生成{label}填色图...").format(label=label))

        worker_result = run_plot_worker(
            _make_wave_maps_worker,
            (str(result_folder), step_hours),
            kwargs={
                "FIGSIZE": _resolve_figsize(cfg),
                "DPI": _resolve_dpi(cfg),
                "generate_video": False,
                "show_land_coastline": cfg.show_land_coastline,
                "output_folder": output_folder,
                "v": v_val,
                "wave_height_file": resolved_wave_file,
                "photo_subdir_name": SUBDIR_WIND_SWELL,
                "clear_output": v_val == 2,
            },
            on_log=logger.log,
        )

        if worker_result and isinstance(worker_result, dict) and worker_result.get("status") == "error":
            has_error = True
            error_msg = str(worker_result.get("error", tr("unknown_error", "❌ 未知错误")))
            break

        if v_val == 2:
            images = _collect_images(out_dir, "phs0_*.png", SUBDIR_WIND_SWELL)
        else:
            images = _collect_images(out_dir, "phs1_*.png", SUBDIR_WIND_SWELL)
        all_images.extend(images)

    if has_error:
        return WaveMapsResult(
            output_folder=out_dir,
            image_files=all_images,
            messages=list(logger.messages),
            success=False,
            error=error_msg,
        )

    logger.log(
        tr("plotting_wind_swell_generated_to", "✅ 风浪/涌浪图已生成至：{path}").format(
            path=photo_subdir(out_dir, SUBDIR_WIND_SWELL)
        )
    )
    return WaveMapsResult(
        output_folder=out_dir,
        image_files=all_images,
        messages=list(logger.messages),
    )


def run_wave_video(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    time_step_hours: Optional[float] = None,
    wave_file: Optional[str] = None,
) -> WaveMapsResult:
    """从 WW3 输出 nc 文件生成有效波高填色图序列并合成 MP4 动画视频。

    与 ``run_wave_maps`` 类似，但启用 ``generate_video=True``，worker 将在生成
    各帧图片后合成 ``hs_anim.mp4`` 动画。

    Args:
        config: 流水线配置（``plot.wave_maps`` 段控制时间步长、DPI 等）。
        log: 可选日志回调。

    Returns:
        ``WaveMapsResult``，图片匹配 ``hs_*.png``，``image_files`` 同时包含 ``.mp4`` 视频路径；
        worker 报错时 ``success=False``。
    """
    from ..infrastructure.plot.wave_map_worker import _make_wave_maps_worker

    logger = CoreLogger(callback=log)
    result_folder = _resolve_result_folder(config)
    cfg = config.plot.wave_maps

    output_folder = str(cfg.output_folder) if cfg.output_folder else None
    step_hours = _resolve_time_step_hours(cfg, time_step_hours)

    worker_result = run_plot_worker(
        _make_wave_maps_worker,
        (str(result_folder), step_hours),
        kwargs={
            "FIGSIZE": _resolve_figsize(cfg),
            "DPI": _resolve_dpi(cfg),
            "generate_video": True,
            "show_land_coastline": cfg.show_land_coastline,
            "output_folder": output_folder,
            "wave_height_file": _resolve_wave_file(wave_file),
        },
        on_log=logger.log,
    )

    out_dir = output_folder or str(result_folder)
    images = _collect_images(out_dir, "hs_*.png", SUBDIR_WAVE_HEIGHT_VIDEO)
    videos = _collect_images(out_dir, "*.mp4", SUBDIR_WAVE_HEIGHT_VIDEO)
    all_files = images + videos

    if worker_result and isinstance(worker_result, dict) and worker_result.get("status") == "error":
        return WaveMapsResult(
            output_folder=out_dir,
            image_files=all_files,
            messages=list(logger.messages),
            success=False,
            error=str(worker_result.get("error", tr("unknown_error", "❌ 未知错误"))),
        )

    logger.log(
        tr("plotting_wave_video_generated_to", "✅ 波高视频已生成至：{path}").format(
            path=photo_subdir(out_dir, SUBDIR_WAVE_HEIGHT_VIDEO)
        )
    )
    return WaveMapsResult(
        output_folder=out_dir,
        image_files=all_files,
        messages=list(logger.messages),
    )
