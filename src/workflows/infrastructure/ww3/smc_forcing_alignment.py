"""SMC 网格生成后，自动将强迫场裁剪范围扩大到 ``ww3_rect_geo``。"""
from __future__ import annotations

import os
from pathlib import Path

from ...domain.forcing_fields import ForcingField
from ...domain.config_models import PipelineConfig
from ...support.logging import CoreLogger
from ...support.translations import tr
from ..forcing.file_service import FileService
from ..forcing.file_path_manager import FilePathManager
from ..forcing.use_cases import ImportForcingFileUseCase
from ..forcing.variable_detector import VariableDetector
from ..forcing.use_cases import AutoAssociateUseCase
from .smc_forcing_bbox import (
    FORCING_IMPORT_META_NAME,
    forcing_covers_rect,
    forcing_nc_lonlat_bounds,
    load_forcing_import_meta,
    read_ww3_rect_geo,
    recommended_forcing_bbox,
)

_FIELD_META_KEYS = {
    ForcingField.WIND: "wind",
    ForcingField.CURRENT: "current",
    ForcingField.LEVEL: "level",
    ForcingField.ICE: "ice",
}


def ensure_smc_forcing_covers_ww3_rect(
    config: PipelineConfig,
    logger: CoreLogger,
    *,
    grid_label: str = "",
) -> bool:
    """若风场未覆盖 SMC RECT，则按 ``grid.json`` 推荐范围从 Step 1 源文件重新裁剪。

    Returns:
        True 若已覆盖或已成功扩大裁剪；False 若缺少 rect/meta 或无法自动处理。
    """
    work_dir = config.workdir.path
    rect_geo = read_ww3_rect_geo(work_dir)
    if not rect_geo:
        return False

    wind_path = work_dir / "wind.nc"
    if not wind_path.is_file():
        return False

    wind_bounds = forcing_nc_lonlat_bounds(wind_path)
    if wind_bounds is None:
        return False
    if forcing_covers_rect(wind_bounds, rect_geo):
        return True

    need_bbox = recommended_forcing_bbox(rect_geo)
    prefix = f"[{grid_label}] " if grid_label else ""
    wlo, whi, wla, wlz = wind_bounds
    logger.log(
        tr(
            "step4_smc_forcing_narrower_than_rect",
            "{prefix}⚠️ SMC / ww3_prnc：风场范围 lon [{wl:.4f},{wh:.4f}] lat [{wb:.4f},{wn:.4f}] "
            "未完全覆盖 SMC 底网格 RECT 范围 lon [{rlw:.4f},{rle:.4f}] lat [{rls:.4f},{rln:.4f}] "
            "（见 grid.json 的 ww3_rect / ww3_rect_geo；该范围已按实际 MCELS 活动底网格收紧，仍可能因 SMC 对齐略大于 regional_bounds）。"
            " 请在第一步扩大风场或裁切到至少上述 RECT，否则 ww3_prnc 会对大量格点报 NOT COVERED BY INPUT GRID。",
        ).format(
            prefix=prefix,
            wl=wlo,
            wh=whi,
            wb=wla,
            wn=wlz,
            rlw=rect_geo["lon_west"],
            rle=rect_geo["lon_east"],
            rls=rect_geo["lat_south"],
            rln=rect_geo["lat_north"],
        )
    )
    logger.log(
        tr(
            "step4_smc_recommended_forcing_bbox",
            "{prefix}ℹ️ 推荐强迫场裁剪范围（已按 0.25° 外扩对齐）：west={w:.4f}, east={e:.4f}, south={s:.4f}, north={n:.4f}",
        ).format(
            prefix=prefix,
            w=need_bbox[0],
            e=need_bbox[1],
            s=need_bbox[2],
            n=need_bbox[3],
        )
    )

    meta = load_forcing_import_meta(work_dir)
    if not meta:
        logger.log(
            tr(
                "step4_smc_forcing_auto_expand_need_meta",
                "{prefix}⚠️ 无法自动扩大强迫场：缺少 {meta}（请用「范围裁剪」重新执行 Step 1，或手动按推荐范围裁剪）",
            ).format(prefix=prefix, meta=FORCING_IMPORT_META_NAME)
        )
        return False

    time_range = config.forcing.crop_time_range or None
    file_service = FileService(logger=logger)
    path_manager = FilePathManager()
    importer = ImportForcingFileUseCase(
        variable_detector=VariableDetector(),
        path_manager=path_manager,
        file_service=file_service,
        auto_associate_use_case=AutoAssociateUseCase(),
        log=logger.log,
    )

    expanded_any = False
    processed_sources: set[str] = set()
    for field, cfg_path in (
        (ForcingField.WIND, config.forcing.wind),
        (ForcingField.CURRENT, config.forcing.current),
        (ForcingField.LEVEL, config.forcing.level),
        (ForcingField.ICE, config.forcing.ice),
    ):
        if cfg_path is None:
            continue
        key = _FIELD_META_KEYS[field]
        entry = meta.get(key)
        if not isinstance(entry, dict):
            continue
        source = str(entry.get("source") or "").strip()
        if not source or not os.path.isfile(source):
            continue
        if source in processed_sources and config.forcing.auto_associate:
            continue
        crop_time = entry.get("crop_time_range") or time_range
        result = importer.execute(
            field,
            source,
            str(work_dir),
            config.forcing.auto_associate,
            "copy",
            crop_time_range=crop_time or None,
            crop_bbox=need_bbox,
        )
        if result.success:
            expanded_any = True
            if config.forcing.auto_associate:
                processed_sources.add(source)
        else:
            logger.log(
                tr(
                    "step4_smc_forcing_auto_expand_failed",
                    "{prefix}⚠️ 自动扩大 {field} 强迫场失败",
                ).format(prefix=prefix, field=field.value)
            )

    if expanded_any:
        wind_bounds2 = forcing_nc_lonlat_bounds(wind_path)
        if wind_bounds2 and forcing_covers_rect(wind_bounds2, rect_geo):
            logger.log(
                tr(
                    "step4_smc_forcing_auto_expand_ok",
                    "{prefix}✅ 已按 ww3_rect_geo 自动重新裁剪强迫场",
                ).format(prefix=prefix)
            )
            return True
        logger.log(
            tr(
                "step4_smc_forcing_auto_expand_partial",
                "{prefix}⚠️ 已重新裁剪强迫场，但范围仍可能不足；请检查源文件是否覆盖推荐范围",
            ).format(prefix=prefix)
        )
    return expanded_any
