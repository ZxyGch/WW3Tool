"""流水线 YAML 参数加载、解析、默认值合并与分阶段校验。

本模块是 WW3Tool 配置系统的应用层入口：将 ``params.yml``（或内存中的
dict）转换为强类型的 ``PipelineConfig``，并在各流水线阶段执行相应校验。

流水线步骤：全局配置 — 所有步骤的前置依赖。

主要公开 API
------------
- ``load_pipeline_config``：从 YAML 文件路径加载并校验
- ``parse_pipeline_config``：从已解析的 dict 构建 ``PipelineConfig``
- ``validate_pipeline_config``：按阶段（forcing / grid / full / plot）校验
- ``ConfigError``：参数非法时抛出的异常类型
- ``EXAMPLE_YAML``：完整参数模板字符串，供 ``--print-example`` 等使用

输入/输出
---------
- 输入：YAML 文件路径或 ``dict``，以及 ``base_dir`` 用于相对路径解析
- 输出：校验通过的 ``PipelineConfig`` 实例

[EN] Pipeline YAML parameter loading, parsing, default merging, and staged validation.

This module is the application-layer entry point of the WW3Tool configuration system:
it converts ``params.yml`` (or an in-memory dict) into a strongly-typed ``PipelineConfig``
and performs corresponding validation at each pipeline stage.

Pipeline step: Global configuration -- prerequisite for all steps.

Main public API
---------------
- ``load_pipeline_config``: Load and validate from a YAML file path
- ``parse_pipeline_config``: Build ``PipelineConfig`` from a parsed dict
- ``validate_pipeline_config``: Validate by stage (forcing / grid / full / plot)
- ``ConfigError``: Exception type raised when parameters are invalid
- ``EXAMPLE_YAML``: Complete parameter template string for ``--print-example`` etc.

Input/Output
------------
- Input: YAML file path or ``dict``, plus ``base_dir`` for relative path resolution
- Output: Validated ``PipelineConfig`` instance
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ..support.translations import tr
from ..domain.config_models import (
    CalcConfig,
    ForcingConfig,
    GridConfig,
    GridRegion,
    Jason3Config,
    NDBCConfig,
    ParameterPresets,
    PathsConfig,
    PipelineConfig,
    PlotConfig,
    PointConfig,
    SMCGridSettings,
    ServerConfig,
    SlurmConfig,
    SpectrumConfig,
    StructuredGridSettings,
    TrackPointConfig,
    UnstructuredGridSettings,
    WW3Config,
    WW3GridSettings,
    WaveMapsConfig,
    WindFieldConfig,
    WorkdirConfig,
)
from ..domain.parameter_catalog import (
    COASTLINE_PRECISION_OPTIONS,
    DEFAULT_OUTPUT_SCHEME_PRESETS,
    DEFAULT_ST_PRESETS,
    FILE_SPLIT_OPTIONS,
    OUTPUT_FIELD_OPTIONS,
    SMC_BATHYMETRY_OPTIONS,
    STRUCTURED_BATHYMETRY_OPTIONS,
)


class ConfigError(ValueError):
    """YAML 参数文件格式或内容不合法时抛出的异常。

    继承自 ``ValueError``，消息为中文描述，指明具体字段与约束违反原因。

    [EN] Exception raised when the YAML parameter file has invalid format or content.
    Inherits from ``ValueError``; messages describe the specific field and constraint violation.
    """


def _import_yaml():
    try:
        import yaml
    except ImportError as exc:
        raise ConfigError(
            "YAML 参数文件需要 PyYAML，请先安装依赖：python -m pip install -r src/requirements.txt"
        ) from exc
    return yaml


def _deep_merge_defaults(defaults: dict, overrides: dict) -> dict:
    """深度合并：以 defaults 为底，overrides 中非 None 的值覆盖对应位置。

    - overrides 中值为 ``None`` → 保留 defaults 的值
    - overrides 中值为 dict → 递归合并
    - overrides 中值为其它非 None → 直接覆盖
    - defaults 中没有的键 → 保留 overrides 的值

    [EN] Deep merge: use defaults as the base; non-None values in overrides replace corresponding positions.
    - overrides value is ``None`` -> keep defaults value
    - overrides value is dict -> recursive merge
    - overrides value is other non-None -> direct replacement
    - Key not in defaults -> keep overrides value
    """
    if not isinstance(defaults, dict) or not isinstance(overrides, dict):
        return overrides if overrides is not None else defaults
    merged = dict(defaults)
    for key, value in overrides.items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_defaults(merged[key], value)
        else:
            merged[key] = value
    return merged


def _as_dict(value: Any, name: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{name} 必须是对象")
    return value


def _resolve_path(value: Any, base_dir: Path, *, required: bool = False) -> Optional[Path]:
    if value is None or str(value).strip() == "":
        if required:
            raise ConfigError("路径不能为空")
        return None
    raw = os.path.expandvars(os.path.expanduser(str(value).strip()))
    path = Path(raw)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _float_pair(value: Any, name: str) -> List[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ConfigError(f"{name} 必须是长度为 2 的数组")
    try:
        return [float(value[0]), float(value[1])]
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} 必须包含数字") from exc


def _float_value(value: Any, name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} 必须是数字") from exc


def _int_value(value: Any, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} 必须是整数") from exc


def _numeric_text(value: Any, name: str, *, integer: bool = False, positive: bool = False) -> str:
    text = str(value).strip()
    try:
        number = int(text) if integer else float(text)
    except (TypeError, ValueError) as exc:
        kind = "整数" if integer else "数字"
        raise ConfigError(f"{name} 必须是{kind}") from exc
    if positive and number <= 0:
        raise ConfigError(f"{name} 必须大于 0")
    return text


def _bool_value(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    raise ConfigError(f"{name} 必须是 true 或 false")


def _process_mode(value: Any) -> str:
    if value is None:
        raise ConfigError("forcing.process_mode 不能为空")
    raw = str(value).strip().lower()
    if raw == "copy":
        return "copy"
    if raw == "move":
        return "move"
    raise ConfigError("forcing.process_mode 必须是 copy 或 move")


def _file_split(value: Any) -> str:
    if value is None:
        raise ConfigError("ww3.file_split 不能为空")
    raw = str(value).strip().lower()
    if raw not in FILE_SPLIT_OPTIONS:
        raise ConfigError(f"ww3.file_split 必须是 {'、'.join(FILE_SPLIT_OPTIONS)}")
    return raw


def _output_fields(value: Any, name: str) -> List[str]:
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{name} 必须是非空字段数组")
    fields: List[str] = []
    for field in value:
        code = str(field).strip().upper()
        if code not in OUTPUT_FIELD_OPTIONS:
            raise ConfigError(f"{name} 包含未知输出字段：{field}")
        if code not in fields:
            fields.append(code)
    return fields


def _selected_output_scheme(value: Any, presets: ParameterPresets) -> str:
    if value is None:
        raise ConfigError("ww3.output_scheme 不能为空")
    name = str(value).strip()
    if not name:
        raise ConfigError("ww3.output_scheme 不能为空")
    if name not in presets.output_scheme:
        raise ConfigError(
            "ww3.output_scheme 必须使用 presets.output_scheme 中定义的名称："
            + "、".join(presets.output_scheme)
        )
    return name


def _st(value: Any) -> Optional[str]:
    """解析 ST 版本名，允许 None（已迁移至 slurm.server_st，保留向后兼容）。"""
    if value is None:
        return None
    st = str(value).strip()
    return st if st else None


def _server_st_presets(value: Any) -> Dict[str, str]:
    if value is None:
        return dict(DEFAULT_ST_PRESETS)
    raw = _as_dict(value, "presets.server_st")
    result: Dict[str, str] = {}
    for name, path in raw.items():
        st_name = str(name).strip()
        executable_dir = str(path).strip()
        if not st_name or not executable_dir:
            raise ConfigError("presets.server_st 的名称和路径均不能为空")
        result[st_name] = executable_dir.rstrip("/")
    return result


def _preset_values(
    value: Any,
    name: str,
    defaults: Iterable[str],
    supported: Iterable[str],
    *,
    upper: bool = False,
    lower: bool = False,
) -> List[str]:
    if value is None:
        return list(defaults)
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{name} 必须是非空数组")
    supported_values = set(supported)
    result: List[str] = []
    for item in value:
        normalized = str(item).strip()
        if upper:
            normalized = normalized.upper()
        if lower:
            normalized = normalized.lower()
        if normalized not in supported_values:
            raise ConfigError(f"{name} 包含不支持的选项：{item}")
        if normalized not in result:
            result.append(normalized)
    return result


def _parameter_presets(value: Any) -> ParameterPresets:
    raw = _as_dict(value, "presets")
    output_scheme_raw = _as_dict(raw.get("output_scheme"), "presets.output_scheme")
    if output_scheme_raw:
        output_schemes = {}
        for name, fields in output_scheme_raw.items():
            preset_name = str(name).strip()
            if not preset_name:
                raise ConfigError("presets.output_scheme 的预设名称不能为空")
            output_schemes[preset_name] = _output_fields(
                fields,
                f"presets.output_scheme.{preset_name}",
            )
    else:
        output_schemes = {
            name: list(fields) for name, fields in DEFAULT_OUTPUT_SCHEME_PRESETS.items()
        }
    return ParameterPresets(
        output_scheme=output_schemes,
        server_st=_server_st_presets(raw.get("server_st")),
        structured_bathymetry=_preset_values(
            raw.get("structured_bathymetry"),
            "presets.structured_bathymetry",
            STRUCTURED_BATHYMETRY_OPTIONS,
            STRUCTURED_BATHYMETRY_OPTIONS,
            upper=True,
        ),
        smc_bathymetry=_preset_values(
            raw.get("smc_bathymetry"),
            "presets.smc_bathymetry",
            SMC_BATHYMETRY_OPTIONS,
            SMC_BATHYMETRY_OPTIONS,
            upper=True,
        ),
        coastline_precision=_preset_values(
            raw.get("coastline_precision"),
            "presets.coastline_precision",
            COASTLINE_PRECISION_OPTIONS,
            COASTLINE_PRECISION_OPTIONS,
            lower=True,
        ),
        file_split=_preset_values(
            raw.get("file_split"),
            "presets.file_split",
            FILE_SPLIT_OPTIONS,
            FILE_SPLIT_OPTIONS,
            lower=True,
        ),
    )


def _region(data: Dict[str, Any], name: str) -> GridRegion:
    dx = data.get("dx")
    dy = data.get("dy")
    if dx is None or dy is None:
        raise ConfigError(f"{name}.dx / {name}.dy 不能为空")
    try:
        dx_f = float(dx)
        dy_f = float(dy)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name}.dx / {name}.dy 必须是数字") from exc
    if dx_f <= 0 or dy_f <= 0:
        raise ConfigError(f"{name}.dx / {name}.dy 必须大于 0")
    lon = _float_pair(data.get("lon"), f"{name}.lon")
    lat = _float_pair(data.get("lat"), f"{name}.lat")
    if lon[0] == lon[1] or lat[0] == lat[1]:
        raise ConfigError(f"{name}.lon / {name}.lat 范围不能为 0")
    return GridRegion(dx=dx_f, dy=dy_f, lon=lon, lat=lat)


def _contract_region(region: GridRegion, factor: float) -> Dict[str, Any]:
    def _contract(bounds: List[float]) -> List[float]:
        center = (bounds[0] + bounds[1]) / 2
        half_extent = abs(bounds[1] - bounds[0]) / (2 * factor)
        return [center - half_extent, center + half_extent]

    return {
        "dx": region.dx,
        "dy": region.dy,
        "lon": _contract(region.lon),
        "lat": _contract(region.lat),
    }


def _points(raw: Any) -> List[PointConfig]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConfigError("calc.points 必须是数组")
    out: List[PointConfig] = []
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ConfigError(f"calc.points[{i}] 必须是对象")
        try:
            out.append(
                PointConfig(
                    lon=float(item["lon"]),
                    lat=float(item["lat"]),
                    name=str(item.get("name") or f"Point_{i}"),
                )
            )
        except KeyError as exc:
            raise ConfigError(f"calc.points[{i}] 缺少 lon/lat") from exc
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"calc.points[{i}] lon/lat 必须是数字") from exc
    return out


def _track_points(raw: Any) -> List[TrackPointConfig]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConfigError("calc.track_points 必须是数组")
    out: List[TrackPointConfig] = []
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ConfigError(f"calc.track_points[{i}] 必须是对象")
        dt = str(item.get("datetime") or "").strip()
        if len(dt) != 15 or " " not in dt:
            raise ConfigError(f"calc.track_points[{i}].datetime 必须形如 YYYYMMDD HHMMSS")
        try:
            out.append(
                TrackPointConfig(
                    datetime=dt,
                    lon=float(item["lon"]),
                    lat=float(item["lat"]),
                    name=str(item.get("name") or f"Track_{i}"),
                )
            )
        except KeyError as exc:
            raise ConfigError(f"calc.track_points[{i}] 缺少 lon/lat") from exc
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"calc.track_points[{i}] lon/lat 必须是数字") from exc
    return out


def _plot_config(raw: Any, base_dir: Path) -> PlotConfig:
    r = _as_dict(raw, "plot")

    wm_raw = _as_dict(r.get("wave_maps"), "plot.wave_maps")
    figsize_raw = wm_raw.get("figsize")
    if figsize_raw is not None:
        if not isinstance(figsize_raw, (list, tuple)) or len(figsize_raw) != 2:
            raise ConfigError("plot.wave_maps.figsize 必须是长度为 2 的数组")
        figsize = [float(figsize_raw[0]), float(figsize_raw[1])]
    else:
        figsize = None
    wave_maps = WaveMapsConfig(
        time_step_hours=_float_value(wm_raw["time_step_hours"], "plot.wave_maps.time_step_hours") if wm_raw.get("time_step_hours") is not None else None,
        figsize=figsize,
        dpi=_int_value(wm_raw["dpi"], "plot.wave_maps.dpi") if wm_raw.get("dpi") is not None else None,
        generate_video=_bool_value(wm_raw.get("generate_video", False), "plot.wave_maps.generate_video"),
        show_land_coastline=_bool_value(wm_raw.get("show_land_coastline", True), "plot.wave_maps.show_land_coastline"),
        output_folder=_resolve_path(wm_raw.get("output_folder"), base_dir),
    )

    sp_raw = _as_dict(r.get("spectrum"), "plot.spectrum")
    spectrum = SpectrumConfig(
        time_step_hours=_float_value(sp_raw["time_step_hours"], "plot.spectrum.time_step_hours") if sp_raw.get("time_step_hours") is not None else None,
        energy_threshold=_float_value(sp_raw["energy_threshold"], "plot.spectrum.energy_threshold") if sp_raw.get("energy_threshold") is not None else None,
        plot_mode=str(sp_raw["plot_mode"]) if sp_raw.get("plot_mode") is not None else None,
    )

    j3_raw = _as_dict(r.get("jason3"), "plot.jason3")
    j3_lon_lat = j3_raw.get("lon_lat", [])
    if j3_lon_lat and not isinstance(j3_lon_lat, (list, tuple)):
        raise ConfigError("plot.jason3.lon_lat 必须是 [西经, 东经, 南纬, 北纬] 数组")
    j3_time_range = j3_raw.get("time_range", [])
    if j3_time_range and not isinstance(j3_time_range, (list, tuple)):
        raise ConfigError("plot.jason3.time_range 必须是 [起始日期, 结束日期] 数组")
    jason3 = Jason3Config(
        data_folder=_resolve_path(j3_raw.get("data_folder"), base_dir),
        lon_lat=[float(v) for v in j3_lon_lat] if j3_lon_lat else [],
        time_range=[str(t) for t in j3_time_range] if j3_time_range else [],
        max_dist_deg=_float_value(j3_raw["max_dist_deg"], "plot.jason3.max_dist_deg") if j3_raw.get("max_dist_deg") is not None else None,
        time_window_hours=_float_value(j3_raw["time_window_hours"], "plot.jason3.time_window_hours") if j3_raw.get("time_window_hours") is not None else None,
    )

    ndbc_raw = _as_dict(r.get("ndbc"), "plot.ndbc")
    ndbc_tr = ndbc_raw.get("time_range", [])
    if not isinstance(ndbc_tr, (list, tuple)):
        raise ConfigError("plot.ndbc.time_range 必须是 [起始日期, 结束日期] 数组")
    ndbc = NDBCConfig(
        data_folder=_resolve_path(ndbc_raw.get("data_folder"), base_dir),
        download=_bool_value(ndbc_raw.get("download", False), "plot.ndbc.download"),
        time_range=[str(t) for t in ndbc_tr],
    )

    wind_field_raw = _as_dict(r.get("wind_field"), "plot.wind_field")
    wind_field = WindFieldConfig(
        time_step_hours=_float_value(wind_field_raw["time_step_hours"], "plot.wind_field.time_step_hours") if wind_field_raw.get("time_step_hours") is not None else None,
        flag_type=str(wind_field_raw["flag_type"]) if wind_field_raw.get("flag_type") is not None else None,
        flag_density=_int_value(wind_field_raw["flag_density"], "plot.wind_field.flag_density") if wind_field_raw.get("flag_density") is not None else None,
    )

    return PlotConfig(
        wave_maps=wave_maps,
        spectrum=spectrum,
        jason3=jason3,
        ndbc=ndbc,
        wind_field=wind_field,
    )


def _server_config(raw: Any, base_dir: Path) -> ServerConfig:
    r = _as_dict(raw, "server")
    port_raw = r.get("port")
    if port_raw is not None:
        try:
            port = int(port_raw)
        except (TypeError, ValueError) as exc:
            raise ConfigError("server.port 必须是整数") from exc
    else:
        port = None
    return ServerConfig(
        host=str(r.get("host") or "").strip(),
        port=port,
        user=str(r.get("user") or "").strip(),
        password=str(r.get("password") or ""),
        key_file=_resolve_path(r.get("key_file"), base_dir),
        ssh_config_host=str(r.get("ssh_config_host") or "").strip(),
        default_remote_dir=str(r.get("default_remote_dir") or "").strip(),
        remote_dir=str(r.get("remote_dir") or "").strip(),
    )


def _validate_existing_paths(paths: Iterable[Optional[Path]], labels: Iterable[str]) -> None:
    for path, label in zip(paths, labels):
        if path is not None and not path.exists():
            raise ConfigError(tr("cfg_path_not_exists", "{label} 不存在：{path}").format(label=label, path=path))


def _validate_wind_path(wind: Optional[Path]) -> None:
    """校验风场源文件路径：必填且指向存在的文件。"""
    if wind is None:
        raise ConfigError(tr("cfg_wind_path_required", "风场文件路径不能为空"))
    if not wind.is_file():
        raise ConfigError(tr("cfg_wind_path_not_exists", "❌ 风场文件不存在：{path}").format(path=wind))


def load_pipeline_config(
    path: str | os.PathLike[str],
    *,
    validation_stage: str = "full",
) -> PipelineConfig:
    """从 YAML 文件路径加载流水线配置并完成校验。

    若工作目录 params.yml 无法解析（YAML 语法错误或结构异常），整体回退到根 params.yml。

    Args:
        path: ``params.yml`` 或同类参数文件的路径。
        validation_stage: 校验严格程度 — ``"forcing"``、``"grid"``、
            ``"full"`` 或 ``"plot"``；默认 ``"full"`` 校验完整预处理所需项。

    Returns:
        解析并校验通过的 ``PipelineConfig``。

    Raises:
        ConfigError: 文件不存在、YAML 格式错误或校验未通过时。

    [EN] Load pipeline configuration from a YAML file path and complete validation.
    If the workdir params.yml cannot be parsed (YAML syntax error or structural anomaly),
    the entire config falls back to the root params.yml.

    Args:
        path: Path to ``params.yml`` or similar parameter file.
        validation_stage: Validation strictness -- ``"forcing"``, ``"grid"``,
            ``"full"`` or ``"plot"``; default ``"full"`` validates all items needed for full preprocessing.

    Returns:
        Parsed and validated ``PipelineConfig``.

    Raises:
        ConfigError: When the file does not exist, YAML format is invalid, or validation fails.
    """
    source_path = Path(path).expanduser().resolve()
    if not source_path.is_file():
        raise ConfigError(f"参数文件不存在：{source_path}")
    yaml = _import_yaml()

    raw: dict = {}
    try:
        with source_path.open("r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        if isinstance(loaded, dict):
            raw = loaded
    except Exception:
        pass

    return parse_pipeline_config(
        raw,
        base_dir=source_path.parent,
        source_path=source_path,
        validation_stage=validation_stage,
    )


def _paths_config(raw: Any, base_dir: Path) -> PathsConfig:
    """解析 paths: 段。

    [EN] Parse the paths: section.
    """
    r = _as_dict(raw, "paths")
    return PathsConfig(
        matlab_path=str(r.get("matlab_path") or ""),
        ww3bin_path=str(r.get("ww3bin_path") or ""),
        jason_path=str(r.get("jason_path") or ""),
        ndbc_path=str(r.get("ndbc_path") or ""),
        jason3_download_url=str(r.get("jason3_download_url") or ""),
    )


def parse_pipeline_config(
    raw: Dict[str, Any],
    *,
    base_dir: Path,
    source_path: Optional[Path] = None,
    validation_stage: str = "full",
) -> PipelineConfig:
    """将原始 YAML dict 解析为 ``PipelineConfig`` 并合并运行时默认值。

    相对路径均相对于 ``base_dir`` 解析；嵌套字段会映射到
    ``domain.config_models`` 中的 dataclass 结构。

    Args:
        raw: YAML ``safe_load`` 得到的顶层 dict。
        base_dir: 相对路径解析基准目录（通常为 YAML 文件所在目录）。
        source_path: 可选，记录配置来源文件路径。
        validation_stage: 传给 ``validate_pipeline_config`` 的校验阶段。

    Returns:
        完整的 ``PipelineConfig`` 实例。

    Raises:
        ConfigError: 字段类型、枚举值或路径约束不满足时。

    [EN] Parse a raw YAML dict into ``PipelineConfig`` and merge runtime defaults.
    Relative paths are resolved relative to ``base_dir``; nested fields map to
    dataclass structures in ``domain.config_models``.

    Args:
        raw: Top-level dict from YAML ``safe_load``.
        base_dir: Base directory for relative path resolution (usually the YAML file's directory).
        source_path: Optional, records the configuration source file path.
        validation_stage: Validation stage passed to ``validate_pipeline_config``.

    Returns:
        Complete ``PipelineConfig`` instance.

    Raises:
        ConfigError: When field types, enum values, or path constraints are not satisfied.
    """
    # [EN] 1) Fill empty values in workdir with root params.yml defaults
    # 1) 用根 params.yml 默认值填充工作目录中的空值
    from ..infrastructure.runtime_config import PARAMS_FILE
    if os.path.isfile(PARAMS_FILE):
        yaml = _import_yaml()
        with open(PARAMS_FILE, "r", encoding="utf-8") as f:
            root_data = yaml.safe_load(f) or {}
        raw = _deep_merge_defaults(root_data, raw)

    presets = _parameter_presets(raw.get("presets"))
    workdir_raw = _as_dict(raw.get("workdir"), "workdir")
    workdir_path = _resolve_path(
        workdir_raw.get("path"),
        base_dir,
        required=True,
    )
    assert workdir_path is not None

    forcing_raw = _as_dict(raw.get("forcing"), "forcing")
    forcing = ForcingConfig(
        wind=_resolve_path(forcing_raw.get("wind"), base_dir),
        current=_resolve_path(forcing_raw.get("current"), base_dir),
        level=_resolve_path(forcing_raw.get("level"), base_dir),
        ice=_resolve_path(forcing_raw.get("ice"), base_dir),
        process_mode=_process_mode(forcing_raw.get("process_mode")),
        auto_associate=_bool_value(forcing_raw.get("auto_associate"), "forcing.auto_associate"),
    )

    grid_raw = _as_dict(raw.get("grid"), "grid")
    grid_type = str(grid_raw.get("grid_type") or "").strip().lower()
    mesh_type = str(grid_raw.get("mesh_type") or "").strip().lower()
    if not mesh_type:
        raise ConfigError("grid.mesh_type 不能为空")
    if mesh_type not in {"structured", "smc", "unstructured"}:
        raise ConfigError("grid.mesh_type 必须是 structured、smc 或 unstructured")
    if not grid_type:
        raise ConfigError("grid.grid_type 不能为空")
    if grid_type not in {"normal", "nested"}:
        raise ConfigError("grid.grid_type 必须是 normal 或 nested")
    if mesh_type != "structured" and grid_type == "nested":
        raise ConfigError("第一版仅 structured 支持 nested 网格")
    nested_contraction = _float_value(
        grid_raw.get("nested_contraction_coefficient"),
        "grid.nested_contraction_coefficient",
    )
    if nested_contraction <= 0:
        raise ConfigError("grid.nested_contraction_coefficient 必须大于 0")
    outer_region = _region(_as_dict(grid_raw.get("outer"), "grid.outer"), "grid.outer")
    inner_region = None
    if grid_type == "nested":
        inner_data = _as_dict(grid_raw.get("inner"), "grid.inner")
        if not inner_data:
            inner_data = _contract_region(outer_region, nested_contraction)
        inner_region = _region(inner_data, "grid.inner")
    structured_raw = _as_dict(grid_raw.get("structured"), "grid.structured")
    legacy_options = _as_dict(grid_raw.get("options"), "grid.options")
    structured = StructuredGridSettings(
        bathymetry=str(structured_raw.get("bathymetry") or "").upper(),
        coastline_precision=str(structured_raw.get("coastline_precision") or "").lower(),
        min_dist=_float_value(structured_raw.get("min_dist"), "grid.structured.min_dist"),
        cut_off=_float_value(structured_raw.get("cut_off"), "grid.structured.cut_off"),
        lim_bathy=_float_value(structured_raw.get("lim_bathy"), "grid.structured.lim_bathy"),
        lim_val=_float_value(structured_raw.get("lim_val"), "grid.structured.lim_val"),
        split_lim=_float_value(structured_raw.get("split_lim"), "grid.structured.split_lim"),
        lake_tol=_float_value(structured_raw.get("lake_tol"), "grid.structured.lake_tol"),
    )
    if structured.bathymetry not in presets.structured_bathymetry:
        raise ConfigError(
            "grid.structured.bathymetry 必须使用 presets.structured_bathymetry 中的选项："
            + "、".join(presets.structured_bathymetry)
        )
    if structured.coastline_precision not in presets.coastline_precision:
        raise ConfigError(
            "grid.structured.coastline_precision 必须使用 presets.coastline_precision 中的选项："
            + "、".join(presets.coastline_precision)
        )

    smc_raw = _as_dict(grid_raw.get("smc"), "grid.smc")
    smc = SMCGridSettings(
        bathymetry=str(smc_raw.get("bathymetry") or "").upper(),
        bathy_convention=str(smc_raw.get("bathy_convention") or "").lower(),
        n_levels=_int_value(smc_raw.get("n_levels"), "grid.smc.n_levels"),
        wlevel=_float_value(smc_raw.get("wlevel"), "grid.smc.wlevel"),
        depmin=_float_value(smc_raw.get("depmin"), "grid.smc.depmin"),
        dshalw=_float_value(smc_raw.get("dshalw"), "grid.smc.dshalw"),
        generate_boundary_cells=_bool_value(
            smc_raw.get("generate_boundary_cells"),
            "grid.smc.generate_boundary_cells",
        ),
        msea=_int_value(smc_raw.get("msea"), "grid.smc.msea"),
        options=_as_dict(smc_raw.get("options"), "grid.smc.options"),
    )
    if smc.bathymetry not in presets.smc_bathymetry:
        raise ConfigError(
            "grid.smc.bathymetry 必须使用 presets.smc_bathymetry 中的选项："
            + "、".join(presets.smc_bathymetry)
        )
    if smc.bathy_convention not in {"elevation", "depth"}:
        raise ConfigError("grid.smc.bathy_convention 必须是 elevation 或 depth")
    if smc.n_levels < 1:
        raise ConfigError("grid.smc.n_levels 必须大于 0")

    unstructured_raw = _as_dict(grid_raw.get("unstructured"), "grid.unstructured")
    unstructured = UnstructuredGridSettings(
        hmax=_float_value(unstructured_raw.get("hmax"), "grid.unstructured.hmax"),
        hmin=_float_value(unstructured_raw.get("hmin"), "grid.unstructured.hmin"),
        hshr=_float_value(unstructured_raw.get("hshr"), "grid.unstructured.hshr"),
        nwav=_int_value(unstructured_raw.get("nwav"), "grid.unstructured.nwav"),
        dhdx=_float_value(unstructured_raw.get("dhdx"), "grid.unstructured.dhdx"),
        deep_ocean_threshold_m=_float_value(
            unstructured_raw.get("deep_ocean_threshold_m"),
            "grid.unstructured.deep_ocean_threshold_m",
        ),
        margin_deg=_float_value(unstructured_raw.get("margin_deg"), "grid.unstructured.margin_deg"),
        edge_segments=_int_value(
            unstructured_raw.get("edge_segments"),
            "grid.unstructured.edge_segments",
        ),
        options=_as_dict(unstructured_raw.get("options"), "grid.unstructured.options"),
    )
    if unstructured.hmax <= 0 or unstructured.hshr <= 0:
        raise ConfigError("grid.unstructured.hmax / hshr 必须大于 0")
    if unstructured.nwav < 1 or unstructured.edge_segments < 1:
        raise ConfigError("grid.unstructured.nwav / edge_segments 必须大于 0")

    grid = GridConfig(
        mesh_type=mesh_type,
        grid_type=grid_type,
        outer=outer_region,
        inner=inner_region,
        gridgen_version=str(grid_raw.get("gridgen_version") or ""),
        reference_data_path=_resolve_path(grid_raw.get("reference_data_path"), base_dir),
        nested_contraction_coefficient=nested_contraction,
        structured=structured,
        smc=smc,
        unstructured=unstructured,
        options=legacy_options,
    )
    calc_raw = _as_dict(raw.get("calc"), "calc")
    calc_mode = str(calc_raw.get("mode") or "").strip().lower()
    if not calc_mode:
        raise ConfigError("calc.mode 不能为空")
    if calc_mode not in {"region", "spectral_point", "track"}:
        raise ConfigError("calc.mode 必须是 region、spectral_point 或 track")
    calc = CalcConfig(
        mode=calc_mode,
        points=_points(calc_raw.get("points")),
        track_points=_track_points(calc_raw.get("track_points")),
    )

    ww3_raw = _as_dict(raw.get("ww3"), "ww3")
    ww3 = WW3Config(
        start_date=str(ww3_raw.get("start_date") or "").strip(),
        end_date=str(ww3_raw.get("end_date") or "").strip(),
        compute_precision=str(ww3_raw.get("compute_precision") or ""),
        output_precision=str(ww3_raw.get("output_precision") or ""),
        inner_compute_precision=(
            str(ww3_raw["inner_compute_precision"]) if "inner_compute_precision" in ww3_raw else None
        ),
        inner_output_precision=(
            str(ww3_raw["inner_output_precision"]) if "inner_output_precision" in ww3_raw else None
        ),
        file_split=_file_split(ww3_raw.get("file_split")),
        output_scheme=_selected_output_scheme(ww3_raw.get("output_scheme"), presets),
        st=_st(ww3_raw.get("st")),
    )
    if ww3.file_split not in presets.file_split:
        raise ConfigError(
            "ww3.file_split 必须使用 presets.file_split 中的选项："
            + "、".join(presets.file_split)
        )

    ww3_grid_raw = _as_dict(raw.get("ww3_grid"), "ww3_grid")
    ww3_grid = WW3GridSettings(
        parameters={
            "SPECTRUM%XFR": _numeric_text(
                ww3_grid_raw.get("SPECTRUM%XFR"),
                "ww3_grid.SPECTRUM%XFR",
                positive=True,
            ),
            "SPECTRUM%FREQ1": _numeric_text(
                ww3_grid_raw.get("SPECTRUM%FREQ1"),
                "ww3_grid.SPECTRUM%FREQ1",
                positive=True,
            ),
            "SPECTRUM%NK": _numeric_text(
                ww3_grid_raw.get("SPECTRUM%NK"),
                "ww3_grid.SPECTRUM%NK",
                integer=True,
                positive=True,
            ),
            "SPECTRUM%NTH": _numeric_text(
                ww3_grid_raw.get("SPECTRUM%NTH"),
                "ww3_grid.SPECTRUM%NTH",
                integer=True,
                positive=True,
            ),
            "TIMESTEPS%DTMAX": _numeric_text(
                ww3_grid_raw.get("TIMESTEPS%DTMAX"),
                "ww3_grid.TIMESTEPS%DTMAX",
                positive=True,
            ),
            "TIMESTEPS%DTXY": _numeric_text(
                ww3_grid_raw.get("TIMESTEPS%DTXY"),
                "ww3_grid.TIMESTEPS%DTXY",
                positive=True,
            ),
            "TIMESTEPS%DTKTH": _numeric_text(
                ww3_grid_raw.get("TIMESTEPS%DTKTH"),
                "ww3_grid.TIMESTEPS%DTKTH",
                positive=True,
            ),
            "TIMESTEPS%DTMIN": _numeric_text(
                ww3_grid_raw.get("TIMESTEPS%DTMIN"),
                "ww3_grid.TIMESTEPS%DTMIN",
                positive=True,
            ),
        }
    )

    slurm_raw = _as_dict(raw.get("slurm"), "slurm")
    # [EN] server_st: prefer slurm.server_st, fall back to ww3.st for backward compat.
    # 优先读 slurm.server_st，向后兼容 ww3.st
    _slurm_server_st = str(slurm_raw.get("server_st") or "").strip() or None
    if _slurm_server_st is None and ww3.st:
        _slurm_server_st = ww3.st
    if not _slurm_server_st:
        raise ConfigError(
            tr("cfg_server_st_required", "slurm.server_st（或 ww3.st）不能为空，请在 params.yml 中配置 ST 版本")
        )
    slurm = SlurmConfig(
        job_name=str(slurm_raw.get("job_name") or "").strip() or workdir_path.name,
        cpu=str(slurm_raw.get("cpu") or ""),
        cpu_group=list(slurm_raw.get("cpu_group") or []),
        nodes=str(slurm_raw.get("nodes") or ""),
        cores=str(slurm_raw.get("cores") or ""),
        server_st=_slurm_server_st,
    )
    if presets.server_st and slurm.server_st not in presets.server_st:
        raise ConfigError(
            "slurm.server_st 必须使用 presets.server_st 中定义的名称：" + "、".join(presets.server_st)
        )

    plot = _plot_config(raw.get("plot"), base_dir)
    server = _server_config(raw.get("server"), base_dir)
    paths = _paths_config(raw.get("paths"), base_dir)

    cfg = PipelineConfig(
        source_path=source_path,
        base_dir=base_dir,
        workdir=WorkdirConfig(path=workdir_path),
        presets=presets,
        forcing=forcing,
        grid=grid,
        calc=calc,
        ww3=ww3,
        ww3_grid=ww3_grid,
        slurm=slurm,
        plot=plot,
        server=server,
        paths=paths,
    )
    validate_pipeline_config(cfg, stage=validation_stage)
    return cfg


def validate_pipeline_config(config: PipelineConfig, *, stage: str = "full") -> None:
    """按流水线阶段校验已构建的 ``PipelineConfig``。

    各阶段校验范围：
    - ``"plot"``：跳过硬校验（后处理命令自行检查必要字段）
    - ``"grid"``：仅校验网格后端兼容性
    - ``"forcing"``：校验强迫场源文件存在且 wind 必填
    - ``"full"``：在上述基础上校验 WW3 日期、SLURM 脚本、计算模式等

    Args:
        config: 待校验的配置对象。
        stage: 校验阶段名称。

    Raises:
        ConfigError: 任一约束不满足时；``stage`` 非法时同样抛出。

    [EN] Validate a constructed ``PipelineConfig`` by pipeline stage.
    Validation scope per stage:
    - ``"plot"``: Skip hard validation (post-processing commands check required fields themselves)
    - ``"grid"``: Only validate grid backend compatibility
    - ``"forcing"``: Validate forcing source files exist and wind is required
    - ``"full"``: Additionally validate WW3 dates, SLURM scripts, computation mode, etc.

    Args:
        config: Configuration object to validate.
        stage: Validation stage name.

    Raises:
        ConfigError: When any constraint is not met; also raised when ``stage`` is invalid.
    """
    if stage not in {"forcing", "grid", "full", "plot"}:
        raise ConfigError(tr("cfg_invalid_stage", "validation_stage 必须是 forcing、grid、full 或 plot"))
    if stage == "plot":
        return
    if stage == "grid":
        if config.grid.mesh_type == "structured" and config.grid.gridgen_version.lower() != "python":
            raise ConfigError(tr("cfg_structured_python_only", "当前无界面流程的 structured 网格仅支持 grid.gridgen_version=Python"))
        return
    _validate_wind_path(config.forcing.wind)
    _validate_existing_paths(
        [config.forcing.current, config.forcing.level, config.forcing.ice],
        ["forcing.current", "forcing.level", "forcing.ice"],
    )
    if stage == "forcing":
        return
    if config.grid.mesh_type == "structured" and config.grid.gridgen_version.lower() != "python":
        raise ConfigError(tr("cfg_structured_python_only", "当前无界面流程的 structured 网格仅支持 grid.gridgen_version=Python"))
    for label, date in (("ww3.start_date", config.ww3.start_date), ("ww3.end_date", config.ww3.end_date)):
        if not (date.isdigit() and len(date) == 8):
            raise ConfigError(tr("cfg_date_format", "{label} 必须是 YYYYMMDD").format(label=label))
    for label, value in (
        ("ww3.compute_precision", config.ww3.compute_precision),
        ("ww3.output_precision", config.ww3.output_precision),
    ):
        if not str(value).isdigit():
            raise ConfigError(tr("cfg_must_be_seconds", "{label} 必须是秒数").format(label=label))
    if config.grid.grid_type == "nested":
        if config.grid.inner is None:
            raise ConfigError(tr("cfg_nested_inner_required", "nested 网格需要 grid.inner"))
        if config.ww3.inner_compute_precision is not None and not config.ww3.inner_compute_precision.isdigit():
            raise ConfigError(tr("cfg_must_be_seconds", "{label} 必须是秒数").format(label="ww3.inner_compute_precision"))
        if config.ww3.inner_output_precision is not None and not config.ww3.inner_output_precision.isdigit():
            raise ConfigError(tr("cfg_must_be_seconds", "{label} 必须是秒数").format(label="ww3.inner_output_precision"))
    if config.calc.mode == "spectral_point" and not config.calc.points:
        raise ConfigError(tr("cfg_spectral_points_required", "calc.mode=spectral_point 时必须提供 calc.points"))
    if config.calc.mode == "track" and not config.calc.track_points:
        raise ConfigError(tr("cfg_track_points_required", "calc.mode=track 时必须提供 calc.track_points"))


# [EN] Complete params.yml example template: for CLI ``--print-example`` and documentation reference.
# [EN] Covers presets, workdir, forcing, grid, calc, ww3, slurm, plot, server sections.
# 完整 params.yml 示例模板：供 CLI ``--print-example`` 与文档引用。
# 涵盖 presets、workdir、forcing、grid、calc、ww3、slurm、plot、server 各段。
EXAMPLE_YAML = """# Headless preprocessing example
presets:
  # [EN] Define output field schemes here; ww3.output_scheme selects one name only
  # 在这里完整定义输出字段方案，ww3.output_scheme 只选择一个名称
  output_scheme:
    standard: [HS, DIR, FP, T02, WND, PHS, PTP, PDIR, PWS, PNR, TWS]
    with_spectrum: [HS, DIR, FP, T02, WND, PHS, PTP, PDIR, PWS, PNR, TWS, EF]
    all_fields: [DPT, CUR, WND, AST, WLV, ICE, IBG, D50, IC1, IC5,
      HS, LM, T02, T0M1, T01, FP, DIR, SPR, DP, HIG,
      EF, TH1M, STH1M, TH2M, STH2M, WN,
      PHS, PTP, PLP, PDIR, PSPR, PWS, PDP, PQP, PPE, PGW, PSW, PTM10, PT01, PT02, PEP, TWS, PNR,
      UST, CHA, CGE, FAW, TAW, TWA, WCC, WCF, WCH, WCM, FWS,
      SXY, TWO, BHD, FOC, TUS, USS, P2S, USF, P2L, TWI, FIC, USP, TOC,
      ABR, UBR, BED, FBB, TBB, MSS, MSC, MSD, MCD, QP, QKK, SKW, EMB,
      DTD, FC, CFX, CFD, CFK]
  # [EN] ST values are executable directories on the server; directory names are unrestricted
  # [EN] Configure according to your actual server environment, example:
  # ST 值是服务器上的可执行文件所在目录，目录名不限；ww3.st 从这些名称中选择一个
  # 请根据实际服务器环境自行配置，示例：
  #   ST4: /path/to/your/ww3/model/exe
  server_st: {}
  structured_bathymetry: [GEBCO, ETOP1, ETOP2]
  smc_bathymetry: [ETOPO1, ETOPO2, GEBCO]
  coastline_precision: [full, high, inter, low, coarse]
  file_split: [none, hour, day, month, year]

workdir:
  path: ./workdir/example

forcing:
  wind: ./data/wind.nc
  current:
  level:
  ice:
  process_mode: copy
  auto_associate: true

grid:
  mesh_type: structured
  grid_type: normal
  gridgen_version: Python
  reference_data_path:
  nested_contraction_coefficient: 1.3
  outer:
    dx: 0.05
    dy: 0.05
    lon: [110, 130]
    lat: [10, 30]
  # [EN] When grid_type is nested, inner can be filled; omitted auto-generates from outer using nested_contraction_coefficient
  # grid_type 为 nested 时，可填写 inner；省略时依据 nested_contraction_coefficient 从 outer 自动生成
  # inner:
  #   dx: 0.05
  #   dy: 0.05
  #   lon: [112, 128]
  #   lat: [12, 28]
  structured:
    bathymetry: GEBCO             # GEBCO | ETOP1 | ETOP2
    coastline_precision: full     # full | high | inter | low | coarse
    min_dist: 20
    cut_off: 0
    lim_bathy: 0.4
    lim_val: 0.5
    split_lim: 0
    lake_tol: 50
  smc:
    bathymetry: ETOPO2            # ETOPO1 | ETOPO2 | GEBCO
    bathy_convention: elevation
    n_levels: 2
    wlevel: 0
    depmin: 0
    dshalw: -150
    generate_boundary_cells: true
    msea: 1
    options:
      input:
        auto_flip_lat: true
        auto_flip_lon: true
        coord_spacing_rtol: 0.001
        coord_spacing_atol: 1.0e-8
        nan_fill_value: 1000.0
      grid:
        name: grid
        global: false
        arctic: false
        glb_arc_lat: 84.4
        origin: {lon0: 0.0, lat0: -90.0}
      output:
        file_prefix: ""
  unstructured:
    hmax: 100
    hshr: 20
    nwav: 400
    dhdx: 0.05
    deep_ocean_threshold_m: 4000
    margin_deg: 1
    edge_segments: 64
    options:
      spacing:
        hmin: 20
      data:
        mask_file: ""
      command_line_args:
        black_sea: 3
      regional:
        stereo_lon: 120.0
        stereo_lat: 20.0

calc:
  mode: region
  points: []
  track_points: []
  # [EN] Example for mode: spectral_point: points: [{lon: 120.0, lat: 20.0, name: P1}]
  # [EN] Example for mode: track: track_points: [{datetime: "20250101 000000", lon: 120.0, lat: 20.0, name: T1}]
  # mode: spectral_point 时示例：points: [{lon: 120.0, lat: 20.0, name: P1}]
  # mode: track 时示例：track_points: [{datetime: "20250101 000000", lon: 120.0, lat: 20.0, name: T1}]

ww3:
  start_date: "20250101"
  end_date: "20250103"
  compute_precision: "1800"
  output_precision: "3600"
  # [EN] Nested grids can specify precision for inner grid separately; omitted inherits from outer grid
  # nested 网格可为内网格单独指定精度；省略则沿用外网格
  # inner_compute_precision: "900"
  # inner_output_precision: "1800"
  file_split: year
  output_scheme: standard          # [EN] Select one scheme defined in presets.output_scheme
                                   # 选择 presets.output_scheme 中定义的一个方案

# [EN] The following values will be written into the generated ww3_grid.nml
# 下列值会写入生成的 ww3_grid.nml
ww3_grid:
  SPECTRUM%XFR: "1.1"            # [EN] Frequency increment
                                 # 频率增量
  SPECTRUM%FREQ1: "0.04118"      # [EN] Starting frequency Hz
                                 # 起始频率 Hz
  SPECTRUM%NK: "32"              # [EN] Number of frequencies
                                 # 频率数量
  SPECTRUM%NTH: "24"             # [EN] Number of directions
                                 # 方向数量
  TIMESTEPS%DTMAX: "900"
  TIMESTEPS%DTXY: "320"
  TIMESTEPS%DTKTH: "300"
  TIMESTEPS%DTMIN: "15"

slurm:
  job_name: null                 # [EN] Slurm job name (#SBATCH -J); null uses workdir name
                                  # Slurm 作业名（#SBATCH -J）；null 使用工作目录名
  cpu: CPU6240R
  cpu_group:                # [EN] Available CPU partition list (for UI dropdown)
                            # 可用 CPU 分区列表（供 UI 下拉选择）
  - CPU6240R
  - CPU6336Y
  nodes: "1"
  cores: "48"
  server_st: ST2                  # [EN] Select one path name from presets.server_st
                                  # 选择 presets.server_st 中的一个路径名称

# [EN] Post-processing plot configuration (used by CLI commands plot-wave-maps / plot-spectrum / plot-jason3 / plot-ndbc)
# 后处理绘图配置（CLI 命令 plot-wave-maps / plot-spectrum / plot-jason3 / plot-ndbc 使用）
plot:
  wave_maps:
    enabled: true
    time_step_hours: 1
    figsize: [16, 12]
    dpi: 300
    generate_video: false
    show_land_coastline: true
    output_folder:          # [EN] When omitted, outputs under workdir/photo
                            # 省略时在 workdir/photo 下输出
  spectrum:
    enabled: false
    time_step_hours: 24
    energy_threshold: 0.01
    plot_mode: "normalized"          # normalized | actual
  jason3:
    enabled: false
    data_folder:            # [EN] Directory containing Jason-3 .nc files (when omitted, uses paths.jason_path or project jason3/)
                            # Jason-3 .nc 文件所在目录（省略时使用 paths.jason_path 或项目 jason3/）
    lon_lat: []             # [EN] [west_lon, east_lon, south_lat, north_lat]; omitted tries grid.outer
                            # [西经, 东经, 南纬, 北纬]；省略时尝试 grid.outer
    time_range: []          # [EN] [start_date, end_date] YYYYMMDD; omitted tries ww3.start_date/end_date
                            # [起始日期, 结束日期] YYYYMMDD；省略时尝试 ww3.start_date/end_date
    max_dist_deg: 0.125
    time_window_hours: 0.5
  ndbc:
    enabled: false
    data_folder:            # [EN] NDBC local data directory (used when download: false)
                            # NDBC 本地数据目录（download: false 时使用）
    download: false
    time_range: []          # [EN] Used when downloading, e.g. ["20250101", "20250103"]
                            # 下载时使用，如 ["20250101", "20250103"]

# [EN] Server connection configuration (used by CLI commands upload / submit / download-results / check-status etc.)
# [EN] Upload and clearing remote directories are destructive operations; must explicitly pass --confirm
# 服务器连接配置（CLI 命令 upload / submit / download-results / check-status 等使用）
# 上传和清空远程目录是破坏性操作，必须显式传 --confirm 才能执行
server:
  host: ""                  # [EN] Server address
                            # 服务器地址
  port: 22
  user: ""                  # [EN] Username
                            # 用户名
  password: ""              # [EN] Password (consider using key_file instead)
                            # 密码（建议改用 key_file）
  key_file:                 # [EN] SSH private key file path (takes priority over password)
                            # SSH 私钥文件路径（优先于 password）
  ssh_config_host:          # [EN] Host alias in ~/.ssh/config (resolved at connect time)
                            # ~/.ssh/config 中的 Host 别名（连接时解析）
  default_remote_dir: ""    # [EN] Default remote base directory, e.g. /home/username/ww3_run (set in settings page)
                            # 默认远程基础目录，如 /home/username/ww3_run（设置页写入）
  remote_dir: ""            # [EN] Actual remote workdir (set in step 6 input; when empty, uses default_remote_dir + workdir name)
                            # 实际远程工作目录（第六步输入框写入，为空时使用 default_remote_dir + 工作目录名）

# [EN] External tool and data directory paths (migrated from config.json, managed per workspace)
# 外部工具与数据目录路径（从 config.json 迁移，按工作区管理）
paths:
  matlab_path: /Applications/MATLAB_R2024a.app/bin/matlab
  ww3bin_path: /Users/zxy/ocean/WW3/build/ST2/bin
  jason_path: /Users/zxy/ocean/Paper/WW3Tool/jason3
  ndbc_path: /Users/zxy/ocean/Paper/WW3Tool/ndbc
  jason3_download_url: https://www.ncei.noaa.gov/data/oceans/jason3/
"""
