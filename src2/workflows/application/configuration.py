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
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ..infrastructure.runtime_config import DEFAULT_CONFIG, load_config

from ..domain.config_models import (
    CalcConfig,
    ForcingConfig,
    GridConfig,
    GridRegion,
    Jason3Config,
    NDBCConfig,
    ParameterPresets,
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
    """


def _import_yaml():
    try:
        import yaml
    except ImportError as exc:
        raise ConfigError(
            "YAML 参数文件需要 PyYAML，请先安装依赖：python -m pip install -r src2/requirements.txt"
        ) from exc
    return yaml


def _merged_app_config() -> Dict[str, Any]:
    data = copy.deepcopy(DEFAULT_CONFIG)
    try:
        user = load_config()
        if isinstance(user, dict):
            data.update(user)
    except Exception:
        pass
    return data


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
    raw = str(value if value is not None else "copy").strip()
    aliases = {
        "copy": "copy",
        "复制": "copy",
        "move": "move",
        "移动": "move",
        "剪切": "move",
    }
    mode = aliases.get(raw.lower(), aliases.get(raw))
    if mode is None:
        raise ConfigError("forcing.process_mode 必须是 copy 或 move")
    return mode


def _file_split(value: Any) -> str:
    raw = str(value if value is not None else "year").strip()
    normalized = raw.lower()
    if normalized not in FILE_SPLIT_OPTIONS:
        raise ConfigError(f"ww3.file_split 必须是 {'、'.join(FILE_SPLIT_OPTIONS)}")
    return normalized


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
    name = str(value if value is not None else "standard").strip()
    if not name:
        raise ConfigError("ww3.output_scheme 不能为空")
    if name not in presets.output_scheme:
        raise ConfigError(
            "ww3.output_scheme 必须使用 presets.output_scheme 中定义的名称："
            + "、".join(presets.output_scheme)
        )
    return name


def _st(value: Any) -> str:
    st = str(value if value is not None else "ST2").strip()
    if not st:
        raise ConfigError("ww3.st 不能为空")
    return st


def _st_presets(value: Any) -> Dict[str, str]:
    if value is None:
        return dict(DEFAULT_ST_PRESETS)
    raw = _as_dict(value, "presets.st")
    if not raw:
        raise ConfigError("presets.st 必须至少提供一个 ST 名称和可执行目录路径")
    result: Dict[str, str] = {}
    for name, path in raw.items():
        st_name = str(name).strip()
        executable_dir = str(path).strip()
        if not st_name or not executable_dir:
            raise ConfigError("presets.st 的名称和路径均不能为空")
        if Path(executable_dir.rstrip("/")).name.lower() != "exe":
            raise ConfigError(f"presets.st.{st_name} 必须填写以 /exe 结尾的可执行目录路径")
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
        st=_st_presets(raw.get("st")),
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


def _region(data: Dict[str, Any], defaults: Dict[str, Any], name: str) -> GridRegion:
    dx = data.get("dx", defaults.get("dx", 0.05))
    dy = data.get("dy", defaults.get("dy", 0.05))
    try:
        dx_f = float(dx)
        dy_f = float(dy)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name}.dx / {name}.dy 必须是数字") from exc
    if dx_f <= 0 or dy_f <= 0:
        raise ConfigError(f"{name}.dx / {name}.dy 必须大于 0")
    lon = _float_pair(data.get("lon", defaults.get("lon", [110.0, 130.0])), f"{name}.lon")
    lat = _float_pair(data.get("lat", defaults.get("lat", [10.0, 30.0])), f"{name}.lat")
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
    result_folder = _resolve_path(r.get("result_folder"), base_dir)

    wm_raw = _as_dict(r.get("wave_maps"), "plot.wave_maps")
    figsize_raw = wm_raw.get("figsize", [16.0, 12.0])
    if not isinstance(figsize_raw, (list, tuple)) or len(figsize_raw) != 2:
        raise ConfigError("plot.wave_maps.figsize 必须是长度为 2 的数组")
    wave_maps = WaveMapsConfig(
        enabled=_bool_value(wm_raw.get("enabled", True), "plot.wave_maps.enabled"),
        time_step_hours=_float_value(wm_raw.get("time_step_hours", 1.0), "plot.wave_maps.time_step_hours"),
        figsize=[float(figsize_raw[0]), float(figsize_raw[1])],
        dpi=_int_value(wm_raw.get("dpi", 300), "plot.wave_maps.dpi"),
        generate_video=_bool_value(wm_raw.get("generate_video", False), "plot.wave_maps.generate_video"),
        show_land_coastline=_bool_value(wm_raw.get("show_land_coastline", True), "plot.wave_maps.show_land_coastline"),
        output_folder=_resolve_path(wm_raw.get("output_folder"), base_dir),
    )

    sp_raw = _as_dict(r.get("spectrum"), "plot.spectrum")
    spectrum = SpectrumConfig(
        enabled=_bool_value(sp_raw.get("enabled", False), "plot.spectrum.enabled"),
        time_step_hours=_float_value(sp_raw.get("time_step_hours", 24.0), "plot.spectrum.time_step_hours"),
        energy_threshold=_float_value(sp_raw.get("energy_threshold", 0.01), "plot.spectrum.energy_threshold"),
        plot_mode=str(sp_raw.get("plot_mode", "最大值归一化")),
    )

    j3_raw = _as_dict(r.get("jason3"), "plot.jason3")
    j3_lon_lat = j3_raw.get("lon_lat", [])
    if j3_lon_lat and not isinstance(j3_lon_lat, (list, tuple)):
        raise ConfigError("plot.jason3.lon_lat 必须是 [西经, 东经, 南纬, 北纬] 数组")
    j3_time_range = j3_raw.get("time_range", [])
    if j3_time_range and not isinstance(j3_time_range, (list, tuple)):
        raise ConfigError("plot.jason3.time_range 必须是 [起始日期, 结束日期] 数组")
    jason3 = Jason3Config(
        enabled=_bool_value(j3_raw.get("enabled", False), "plot.jason3.enabled"),
        data_folder=_resolve_path(j3_raw.get("data_folder"), base_dir),
        lon_lat=[float(v) for v in j3_lon_lat] if j3_lon_lat else [],
        time_range=[str(t) for t in j3_time_range] if j3_time_range else [],
        max_dist_deg=_float_value(j3_raw.get("max_dist_deg", 0.125), "plot.jason3.max_dist_deg"),
        time_window_hours=_float_value(j3_raw.get("time_window_hours", 0.5), "plot.jason3.time_window_hours"),
    )

    ndbc_raw = _as_dict(r.get("ndbc"), "plot.ndbc")
    ndbc_tr = ndbc_raw.get("time_range", [])
    if not isinstance(ndbc_tr, (list, tuple)):
        raise ConfigError("plot.ndbc.time_range 必须是 [起始日期, 结束日期] 数组")
    ndbc = NDBCConfig(
        enabled=_bool_value(ndbc_raw.get("enabled", False), "plot.ndbc.enabled"),
        data_folder=_resolve_path(ndbc_raw.get("data_folder"), base_dir),
        download=_bool_value(ndbc_raw.get("download", False), "plot.ndbc.download"),
        time_range=[str(t) for t in ndbc_tr],
    )

    return PlotConfig(
        result_folder=result_folder,
        wave_maps=wave_maps,
        spectrum=spectrum,
        jason3=jason3,
        ndbc=ndbc,
    )


def _server_config(raw: Any, base_dir: Path) -> ServerConfig:
    r = _as_dict(raw, "server")
    port_raw = r.get("port", 22)
    try:
        port = int(port_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError("server.port 必须是整数") from exc
    return ServerConfig(
        host=str(r.get("host") or "").strip(),
        port=port,
        user=str(r.get("user") or "").strip(),
        password=str(r.get("password") or ""),
        key_file=_resolve_path(r.get("key_file"), base_dir),
        remote_dir=str(r.get("remote_dir") or "").strip(),
    )


def _validate_existing_paths(paths: Iterable[Optional[Path]], labels: Iterable[str]) -> None:
    for path, label in zip(paths, labels):
        if path is not None and not path.exists():
            raise ConfigError(f"{label} 不存在：{path}")


def load_pipeline_config(
    path: str | os.PathLike[str],
    *,
    validation_stage: str = "full",
) -> PipelineConfig:
    """从 YAML 文件路径加载流水线配置并完成校验。

    Args:
        path: ``params.yml`` 或同类参数文件的路径。
        validation_stage: 校验严格程度 — ``"forcing"``、``"grid"``、
            ``"full"`` 或 ``"plot"``；默认 ``"full"`` 校验完整预处理所需项。

    Returns:
        解析并校验通过的 ``PipelineConfig``。

    Raises:
        ConfigError: 文件不存在、YAML 格式错误或校验未通过时。
    """
    source_path = Path(path).expanduser().resolve()
    if not source_path.is_file():
        raise ConfigError(f"参数文件不存在：{source_path}")
    yaml = _import_yaml()
    with source_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ConfigError("参数文件顶层必须是对象")
    return parse_pipeline_config(
        raw,
        base_dir=source_path.parent,
        source_path=source_path,
        validation_stage=validation_stage,
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
    """
    app = _merged_app_config()
    presets = _parameter_presets(raw.get("presets"))
    workdir_raw = _as_dict(raw.get("workdir"), "workdir")
    workdir_path = _resolve_path(
        workdir_raw.get("path") or app.get("DEFAULT_WORKDIR"),
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
        process_mode=_process_mode(forcing_raw.get("process_mode", app.get("FORCING_FIELD_FILE_PROCESS_MODE", "copy"))),
        auto_associate=bool(forcing_raw.get("auto_associate", app.get("FORCING_FIELD_AUTO_ASSOCIATE", True))),
        converted=_bool_value(forcing_raw.get("converted", False), "forcing.converted"),
    )

    grid_raw = _as_dict(raw.get("grid"), "grid")
    outer_defaults = {
        "dx": app.get("DX", 0.05),
        "dy": app.get("DY", 0.05),
        "lon": [app.get("LONGITUDE_WEST") or 110.0, app.get("LONGITUDE_EAST") or 130.0],
        "lat": [app.get("LATITUDE_SORTH") or 10.0, app.get("LATITUDE_NORTH") or 30.0],
    }
    inner_defaults = {
        "dx": app.get("NESTED_OUTER_DX", outer_defaults["dx"]),
        "dy": app.get("NESTED_OUTER_DY", outer_defaults["dy"]),
        "lon": outer_defaults["lon"],
        "lat": outer_defaults["lat"],
    }
    grid_type = str(grid_raw.get("grid_type", "normal")).strip().lower()
    mesh_type = str(grid_raw.get("mesh_type", "structured")).strip().lower()
    if mesh_type not in {"structured", "smc", "unstructured"}:
        raise ConfigError("grid.mesh_type 必须是 structured、smc 或 unstructured")
    if grid_type not in {"normal", "nested"}:
        raise ConfigError("grid.grid_type 必须是 normal 或 nested")
    if mesh_type != "structured" and grid_type == "nested":
        raise ConfigError("第一版仅 structured 支持 nested 网格")
    nested_contraction = _float_value(
        grid_raw.get(
            "nested_contraction_coefficient",
            app.get("NESTED_CONTRACTION_COEFFICIENT", 1.3),
        ),
        "grid.nested_contraction_coefficient",
    )
    if nested_contraction <= 0:
        raise ConfigError("grid.nested_contraction_coefficient 必须大于 0")
    outer_region = _region(_as_dict(grid_raw.get("outer"), "grid.outer"), outer_defaults, "grid.outer")
    inner_region = None
    if grid_type == "nested":
        if grid_raw.get("inner") is None:
            inner_defaults = _contract_region(outer_region, nested_contraction)
        inner_region = _region(_as_dict(grid_raw.get("inner"), "grid.inner"), inner_defaults, "grid.inner")
    structured_raw = _as_dict(grid_raw.get("structured"), "grid.structured")
    legacy_options = _as_dict(grid_raw.get("options"), "grid.options")
    structured = StructuredGridSettings(
        bathymetry=str(
            structured_raw.get("bathymetry", grid_raw.get("bathymetry", app.get("BATHYMETRY", "GEBCO")))
        ).upper(),
        coastline_precision=str(
            structured_raw.get(
                "coastline_precision",
                grid_raw.get("coastline_precision", app.get("COASTLINE_PRECISION", "full")),
            )
        ).lower(),
        min_dist=_float_value(
            structured_raw.get("min_dist", legacy_options.get("MIN_DIST", app.get("MIN_DIST", 20))),
            "grid.structured.min_dist",
        ),
        cut_off=_float_value(
            structured_raw.get("cut_off", legacy_options.get("CUT_OFF", app.get("CUT_OFF", 0))),
            "grid.structured.cut_off",
        ),
        lim_bathy=_float_value(
            structured_raw.get("lim_bathy", legacy_options.get("LIM_BATHY", app.get("LIM_BATHY", 0.4))),
            "grid.structured.lim_bathy",
        ),
        lim_val=_float_value(
            structured_raw.get("lim_val", legacy_options.get("LIM_VAL", app.get("LIM_VAL", 0.5))),
            "grid.structured.lim_val",
        ),
        split_lim=_float_value(
            structured_raw.get("split_lim", legacy_options.get("SPLIT_LIM", app.get("SPLIT_LIM", 0))),
            "grid.structured.split_lim",
        ),
        lake_tol=_float_value(
            structured_raw.get("lake_tol", legacy_options.get("LAKE_TOL", app.get("LAKE_TOL", 50))),
            "grid.structured.lake_tol",
        ),
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
        bathymetry=str(smc_raw.get("bathymetry", "ETOPO2")).upper(),
        bathy_convention=str(smc_raw.get("bathy_convention", "elevation")).lower(),
        n_levels=_int_value(smc_raw.get("n_levels", 2), "grid.smc.n_levels"),
        wlevel=_float_value(smc_raw.get("wlevel", 0.0), "grid.smc.wlevel"),
        depmin=_float_value(smc_raw.get("depmin", 0.0), "grid.smc.depmin"),
        dshalw=_float_value(smc_raw.get("dshalw", -150.0), "grid.smc.dshalw"),
        generate_boundary_cells=_bool_value(
            smc_raw.get("generate_boundary_cells", True),
            "grid.smc.generate_boundary_cells",
        ),
        msea=_int_value(smc_raw.get("msea", 1), "grid.smc.msea"),
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
        hmax=_float_value(unstructured_raw.get("hmax", 100.0), "grid.unstructured.hmax"),
        hshr=_float_value(unstructured_raw.get("hshr", 20.0), "grid.unstructured.hshr"),
        nwav=_int_value(unstructured_raw.get("nwav", 400), "grid.unstructured.nwav"),
        dhdx=_float_value(unstructured_raw.get("dhdx", 0.05), "grid.unstructured.dhdx"),
        deep_ocean_threshold_m=_float_value(
            unstructured_raw.get("deep_ocean_threshold_m", 4000.0),
            "grid.unstructured.deep_ocean_threshold_m",
        ),
        margin_deg=_float_value(unstructured_raw.get("margin_deg", 1.0), "grid.unstructured.margin_deg"),
        edge_segments=_int_value(
            unstructured_raw.get("edge_segments", 64),
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
        generated=_bool_value(grid_raw.get("generated", False), "grid.generated"),
        outer=outer_region,
        inner=inner_region,
        gridgen_version=str(grid_raw.get("gridgen_version", app.get("GRIDGEN_VERSION", "Python"))),
        reference_data_path=_resolve_path(grid_raw.get("reference_data_path") or app.get("REFERENCE_DATA_PATH"), base_dir),
        nested_contraction_coefficient=nested_contraction,
        structured=structured,
        smc=smc,
        unstructured=unstructured,
        options=legacy_options,
    )
    calc_raw = _as_dict(raw.get("calc"), "calc")
    calc_mode = str(calc_raw.get("mode", "region")).strip().lower()
    if calc_mode not in {"region", "spectral_point", "track"}:
        raise ConfigError("calc.mode 必须是 region、spectral_point 或 track")
    calc = CalcConfig(
        mode=calc_mode,
        points=_points(calc_raw.get("points")),
        track_points=_track_points(calc_raw.get("track_points")),
    )

    ww3_raw = _as_dict(raw.get("ww3"), "ww3")
    ww3 = WW3Config(
        start_date=str(ww3_raw.get("start_date", "")).strip(),
        end_date=str(ww3_raw.get("end_date", "")).strip(),
        compute_precision=str(ww3_raw.get("compute_precision", app.get("COMPUTE_PRECISION", "1800"))),
        output_precision=str(ww3_raw.get("output_precision", app.get("OUTPUT_PRECISION", "3600"))),
        inner_compute_precision=(
            str(ww3_raw["inner_compute_precision"]) if "inner_compute_precision" in ww3_raw else None
        ),
        inner_output_precision=(
            str(ww3_raw["inner_output_precision"]) if "inner_output_precision" in ww3_raw else None
        ),
        file_split=_file_split(ww3_raw.get("file_split", app.get("FILE_SPLIT", "year"))),
        output_scheme=_selected_output_scheme(ww3_raw.get("output_scheme"), presets),
        st=_st(ww3_raw.get("st", "ST2")),
    )
    if ww3.file_split not in presets.file_split:
        raise ConfigError(
            "ww3.file_split 必须使用 presets.file_split 中的选项："
            + "、".join(presets.file_split)
        )
    if ww3.st not in presets.st:
        raise ConfigError("ww3.st 必须使用 presets.st 中定义的名称：" + "、".join(presets.st))

    ww3_grid_raw = _as_dict(raw.get("ww3_grid"), "ww3_grid")
    ww3_grid = WW3GridSettings(
        parameters={
            "SPECTRUM%XFR": _numeric_text(
                ww3_grid_raw.get("SPECTRUM%XFR", app.get("FREQ_INC", "1.1")),
                "ww3_grid.SPECTRUM%XFR",
                positive=True,
            ),
            "SPECTRUM%FREQ1": _numeric_text(
                ww3_grid_raw.get("SPECTRUM%FREQ1", app.get("FREQ_START", "0.04118")),
                "ww3_grid.SPECTRUM%FREQ1",
                positive=True,
            ),
            "SPECTRUM%NK": _numeric_text(
                ww3_grid_raw.get("SPECTRUM%NK", app.get("FREQ_NUM", "32")),
                "ww3_grid.SPECTRUM%NK",
                integer=True,
                positive=True,
            ),
            "SPECTRUM%NTH": _numeric_text(
                ww3_grid_raw.get("SPECTRUM%NTH", app.get("DIR_NUM", "24")),
                "ww3_grid.SPECTRUM%NTH",
                integer=True,
                positive=True,
            ),
            "TIMESTEPS%DTMAX": _numeric_text(
                ww3_grid_raw.get("TIMESTEPS%DTMAX", app.get("DTMAX", "900")),
                "ww3_grid.TIMESTEPS%DTMAX",
                positive=True,
            ),
            "TIMESTEPS%DTXY": _numeric_text(
                ww3_grid_raw.get("TIMESTEPS%DTXY", app.get("DTXY", "320")),
                "ww3_grid.TIMESTEPS%DTXY",
                positive=True,
            ),
            "TIMESTEPS%DTKTH": _numeric_text(
                ww3_grid_raw.get("TIMESTEPS%DTKTH", app.get("DTKTH", "300")),
                "ww3_grid.TIMESTEPS%DTKTH",
                positive=True,
            ),
            "TIMESTEPS%DTMIN": _numeric_text(
                ww3_grid_raw.get("TIMESTEPS%DTMIN", app.get("DTMIN", "15")),
                "ww3_grid.TIMESTEPS%DTMIN",
                positive=True,
            ),
            "GRID%ZLIM": _numeric_text(
                ww3_grid_raw.get("GRID%ZLIM", app.get("GRID_ZLIM", "-0.1")),
                "ww3_grid.GRID%ZLIM",
            ),
            "GRID%DMIN": _numeric_text(
                ww3_grid_raw.get("GRID%DMIN", app.get("GRID_DMIN", "2.5")),
                "ww3_grid.GRID%DMIN",
                positive=True,
            ),
        }
    )

    slurm_raw = _as_dict(raw.get("slurm"), "slurm")
    slurm = SlurmConfig(
        cpu=str(slurm_raw.get("cpu", app.get("DEFAULT_CPU", "CPU6240R"))),
        nodes=str(slurm_raw.get("nodes", app.get("NODE_NUM", "1"))),
        cores=str(slurm_raw.get("cores", app.get("KERNEL_NUM", "48"))),
        server_script_path=_resolve_path(slurm_raw.get("server_script_path"), base_dir),
    )

    plot = _plot_config(raw.get("plot"), base_dir)
    server = _server_config(raw.get("server"), base_dir)

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
    """
    if stage not in {"forcing", "grid", "full", "plot"}:
        raise ConfigError("validation_stage 必须是 forcing、grid、full 或 plot")
    if stage == "plot":
        return
    if stage == "grid":
        if config.grid.mesh_type == "structured" and config.grid.gridgen_version.lower() != "python":
            raise ConfigError("当前无界面流程的 structured 网格仅支持 grid.gridgen_version=Python")
        return
    _validate_existing_paths(
        [config.forcing.wind, config.forcing.current, config.forcing.level, config.forcing.ice],
        ["forcing.wind", "forcing.current", "forcing.level", "forcing.ice"],
    )
    if config.forcing.wind is None:
        raise ConfigError("第一版流水线要求提供 forcing.wind")
    if stage == "forcing":
        return
    if config.grid.mesh_type == "structured" and config.grid.gridgen_version.lower() != "python":
        raise ConfigError("当前无界面流程的 structured 网格仅支持 grid.gridgen_version=Python")
    _validate_existing_paths([config.slurm.server_script_path], ["slurm.server_script_path"])
    for label, date in (("ww3.start_date", config.ww3.start_date), ("ww3.end_date", config.ww3.end_date)):
        if not (date.isdigit() and len(date) == 8):
            raise ConfigError(f"{label} 必须是 YYYYMMDD")
    for label, value in (
        ("ww3.compute_precision", config.ww3.compute_precision),
        ("ww3.output_precision", config.ww3.output_precision),
    ):
        if not str(value).isdigit():
            raise ConfigError(f"{label} 必须是秒数")
    if config.grid.grid_type == "nested":
        if config.grid.inner is None:
            raise ConfigError("nested 网格需要 grid.inner")
        if config.ww3.inner_compute_precision is not None and not config.ww3.inner_compute_precision.isdigit():
            raise ConfigError("ww3.inner_compute_precision 必须是秒数")
        if config.ww3.inner_output_precision is not None and not config.ww3.inner_output_precision.isdigit():
            raise ConfigError("ww3.inner_output_precision 必须是秒数")
    if config.calc.mode == "spectral_point" and not config.calc.points:
        raise ConfigError("calc.mode=spectral_point 时必须提供 calc.points")
    if config.calc.mode == "track" and not config.calc.track_points:
        raise ConfigError("calc.mode=track 时必须提供 calc.track_points")


# 完整 params.yml 示例模板：供 CLI ``--print-example`` 与文档引用。
# 涵盖 presets、workdir、forcing、grid、calc、ww3、slurm、plot、server 各段。
EXAMPLE_YAML = """# Headless preprocessing example
presets:
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
  # ST 值是服务器上的可执行文件目录；ww3.st 从这些名称中选择一个
  st:
    ST2: /public/home//software/wavewatch3/model/exe
    ST4: /public/home//software2/ww4/model/exe
    ST6: /public/home//software2/ww6/model/exe
    ST6A: /public/home//software2/ww6a/model/exe
    ST6B: /public/home//software2/ww6b/model/exe
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
  converted: false

grid:
  mesh_type: structured
  grid_type: normal
  generated: false
  gridgen_version: Python
  reference_data_path:
  nested_contraction_coefficient: 1.3
  outer:
    dx: 0.05
    dy: 0.05
    lon: [110, 130]
    lat: [10, 30]
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
  # mode: spectral_point 时示例：points: [{lon: 120.0, lat: 20.0, name: P1}]
  # mode: track 时示例：track_points: [{datetime: "20250101 000000", lon: 120.0, lat: 20.0, name: T1}]

ww3:
  start_date: "20250101"
  end_date: "20250103"
  compute_precision: "1800"
  output_precision: "3600"
  # nested 网格可为内网格单独指定精度；省略则沿用外网格
  # inner_compute_precision: "900"
  # inner_output_precision: "1800"
  file_split: year
  output_scheme: standard          # 选择 presets.output_scheme 中定义的一个方案
  st: ST2                        # 选择 presets.st 中的一个路径名称

# 下列值会写入生成的 ww3_grid.nml
ww3_grid:
  SPECTRUM%XFR: "1.1"            # 频率增量
  SPECTRUM%FREQ1: "0.04118"      # 起始频率 Hz
  SPECTRUM%NK: "32"              # 频率数量
  SPECTRUM%NTH: "24"             # 方向数量
  TIMESTEPS%DTMAX: "900"
  TIMESTEPS%DTXY: "320"
  TIMESTEPS%DTKTH: "300"
  TIMESTEPS%DTMIN: "15"
  GRID%ZLIM: "-0.1"              # 海岸线限制深度 m
  GRID%DMIN: "2.5"               # 绝对最小水深 m

slurm:
  cpu: CPU6240R
  nodes: "1"
  cores: "48"
  # 可指定本地 server.sh 模板；省略时使用 public/ww3/server.sh
  server_script_path:

# 后处理绘图配置（CLI 命令 plot / plot-wave-maps / plot-spectrum / match-jason3 / match-ndbc 使用）
plot:
  # WW3 输出结果所在文件夹；省略时使用 workdir
  result_folder:
  wave_maps:
    enabled: true
    time_step_hours: 1
    figsize: [16, 12]
    dpi: 300
    generate_video: false
    show_land_coastline: true
    output_folder:          # 省略时在 result_folder/photo 下输出
  spectrum:
    enabled: false
    time_step_hours: 24
    energy_threshold: 0.01
    plot_mode: "最大值归一化"    # 最大值归一化 | 绝对值
  jason3:
    enabled: false
    data_folder:            # Jason-3 .nc 文件所在目录（省略时使用 config.json 的 JASON_PATH 或项目 jason3/）
    lon_lat: []             # [西经, 东经, 南纬, 北纬]；省略时尝试 grid.outer
    time_range: []          # [起始日期, 结束日期] YYYYMMDD；省略时尝试 ww3.start_date/end_date
    max_dist_deg: 0.125
    time_window_hours: 0.5
  ndbc:
    enabled: false
    data_folder:            # NDBC 本地数据目录（download: false 时使用）
    download: false
    time_range: []          # 下载时使用，如 ["20250101", "20250103"]

# 服务器连接配置（CLI 命令 upload / submit / download-results / check-status 等使用）
# 上传和清空远程目录是破坏性操作，必须显式传 --confirm 才能执行
server:
  host: ""                  # 服务器地址
  port: 22
  user: ""                  # 用户名
  password: ""              # 密码（建议改用 key_file）
  key_file:                 # SSH 私钥文件路径（优先于 password）
  remote_dir: ""            # 远程工作目录，如 /home/username/ww3_run
"""
