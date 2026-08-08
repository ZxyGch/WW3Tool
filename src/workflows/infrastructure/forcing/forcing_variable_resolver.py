"""强迫场变量统一解析服务。

[EN] Unified forcing-field variable resolution service.

本模块是强迫场变量识别/校验的**唯一入口**：自动识别常见变量名、应用用户
自定义映射（``forcing.custom``）、检测歧义并执行结构校验，最终产出
``ResolvedForcingVariables`` 供导入归一化、裁剪合并与 NML 生成共用。

[EN] This module is the single entry point for forcing-field variable
identification/validation: auto-detects common variable names, applies user
custom overrides (``forcing.custom``), flags ambiguity, and validates structure,
producing ``ResolvedForcingVariables`` shared by import normalization, crop/merge,
and NML generation.

解析顺序（方案 §4）：
1. 读取 NetCDF 全部变量名、维度、``standard_name``、``long_name``、``units``；
2. 用户已填写的项做精确、区分大小写的存在性校验；
3. 空项先按常见名称自动识别；
4. 名称无法判断时使用 CF 属性（standard_name / units / axis）识别；
5. 仍存在多个候选时标记为歧义，禁止擅自选择；
6. 通过 ``ForcingVariableError`` 返回缺失角色、候选变量与原因。

[EN] Resolution order (spec §4):
1. Read all NetCDF variable names, dimensions, ``standard_name``, ``long_name``, ``units``;
2. Validate user-filled items exactly (case-sensitive);
3. Auto-detect empty items by common names first;
4. Fall back to CF attributes (standard_name / units / axis);
5. Multiple candidates still remaining = ambiguous, never pick arbitrarily;
6. Raise ``ForcingVariableError`` with missing roles, candidates, and reason.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field as dataclass_field
from typing import Dict, List, Optional, Tuple

import numpy as np
from netCDF4 import Dataset

from ...domain.config_models import ForcingVariableOverride, ResolvedForcingVariables
from ...support.translations import tr


# ── 固定场关系（方案 §2，不进 YAML）──────────────────────────────────
# [EN] Fixed field-component relations (spec §2, not in YAML)

FIELD_COMPONENTS: Dict[str, Tuple[str, ...]] = {
    "wind": ("u", "v"),
    "current": ("u", "v"),
    "level": ("value",),
    "ice": ("concentration",),
}

WW3_FIELDS: Dict[str, str] = {
    "wind": "WINDS",
    "current": "CURRENTS",
    "level": "WATER_LEVELS",
    "ice": "ICE_CONC",
}

# 每个场可用的角色顺序（经度/纬度/时间 + 分量 + 可选厚度）
# [EN] Role order per field (lon/lat/time + components + optional thickness)
_FIELD_ROLES: Dict[str, Tuple[str, ...]] = {
    "wind": ("longitude", "latitude", "time", "u", "v"),
    "current": ("longitude", "latitude", "time", "u", "v"),
    "level": ("longitude", "latitude", "time", "value"),
    "ice": ("longitude", "latitude", "time", "concentration", "thickness"),
}


# ── 常见名称候选表（方案 §4 自动识别覆盖范围）────────────────────────
# [EN] Common-name candidate tables (spec §4 auto-detection coverage)

_LON_NAME_CANDIDATES = ("longitude", "lon", "x", "Longitude", "LONGITUDE", "LON", "X")
_LAT_NAME_CANDIDATES = ("latitude", "lat", "y", "Latitude", "LATITUDE", "LAT", "Y")
_TIME_NAME_CANDIDATES = ("time", "valid_time", "MT", "t", "Time", "TIME", "mt", "T")

_ROLE_NAME_CANDIDATES: Dict[str, Tuple[str, ...]] = {
    "wind_u": (
        "u10", "U10", "wndewd", "WNDEWD", "eastward_wind",
        "u", "uwnd", "UWND", "uwnd10m", "UWND10M", "uas",
    ),
    "wind_v": (
        "v10", "V10", "wndnwd", "WNDNWD", "northward_wind",
        "v", "vwnd", "VWND", "vwnd10m", "VWND10M", "vas",
    ),
    "current_u": ("uo", "UO"),
    "current_v": ("vo", "VO"),
    "level": ("zos", "ZOS"),
    "ice": ("siconc", "SICONC"),
    "thickness": ("sithick", "SITHICK"),
}

# CF standard_name 匹配表（角色 → 可接受的 standard_name 集合）
# [EN] CF standard_name matching table (role → acceptable standard_name set)
_ROLE_STANDARD_NAMES: Dict[str, Tuple[str, ...]] = {
    "longitude": ("longitude",),
    "latitude": ("latitude",),
    "wind_u": ("eastward_wind", "wind_speed"),
    "wind_v": ("northward_wind",),
    "current_u": ("eastward_sea_water_velocity", "sea_water_x_velocity"),
    "current_v": ("northward_sea_water_velocity", "sea_water_y_velocity"),
    "level": ("sea_surface_height", "sea_surface_height_above_geoid", "water_surface_height"),
    "ice": ("sea_ice_area_fraction",),
    "thickness": ("sea_ice_thickness",),
}

# CF units 匹配表（角色 → 可接受的 units 片段，小写匹配）
# [EN] CF units matching table (role → acceptable unit fragments, lowercase)
_ROLE_UNITS: Dict[str, Tuple[str, ...]] = {
    "longitude": ("degrees_east", "degree_east"),
    "latitude": ("degrees_north", "degree_north"),
    "time": ("since",),
    "wind_u": ("m s-1", "m/s", "m s**-1", "meter second-1", "meters per second"),
    "wind_v": ("m s-1", "m/s", "m s**-1", "meter second-1", "meters per second"),
    "current_u": ("m s-1", "m/s", "m s**-1", "meter second-1", "meters per second"),
    "current_v": ("m s-1", "m/s", "m s**-1", "meter second-1", "meters per second"),
    "level": ("m", "meter", "meters"),
    "ice": ("1", "%", "percent"),
    "thickness": ("m", "meter", "meters"),
}


@dataclass
class VariableInfo:
    """NetCDF 中单个变量的元信息（供 GUI 下拉与 CLI 展示）。

    [EN] Metadata of a single NetCDF variable (for GUI dropdowns and CLI output).
    """

    name: str
    dimensions: Tuple[str, ...]
    shape: Tuple[int, ...]
    standard_name: Optional[str] = None
    long_name: Optional[str] = None
    units: Optional[str] = None
    axis: Optional[str] = None

    def summary(self) -> str:
        """单行摘要，如 ``u10 (time, latitude, longitude) [m s-1]``。

        [EN] One-line summary, e.g. ``u10 (time, latitude, longitude) [m s-1]``.
        """
        dims = ", ".join(self.dimensions) if self.dimensions else "scalar"
        unit = f" [{self.units}]" if self.units else ""
        return f"{self.name} ({dims}){unit}"


class ForcingVariableError(Exception):
    """变量解析失败：携带缺失角色、候选变量与原因。

    [EN] Variable resolution failure: carries missing roles, candidate variables, and reason.
    """

    def __init__(
        self,
        message: str,
        *,
        field: str,
        role: str,
        candidates: Optional[List[VariableInfo]] = None,
    ) -> None:
        super().__init__(message)
        self.field = field
        self.role = role
        self.candidates = candidates or []


def _snapshot_variables(ds: Dataset) -> Dict[str, VariableInfo]:
    """快照文件内全部变量元信息。

    [EN] Snapshot metadata of all variables in the file.
    """
    out: Dict[str, VariableInfo] = {}
    for name, var in ds.variables.items():
        out[name] = VariableInfo(
            name=name,
            dimensions=tuple(var.dimensions),
            shape=tuple(var.shape),
            standard_name=getattr(var, "standard_name", None),
            long_name=getattr(var, "long_name", None),
            units=getattr(var, "units", None),
            axis=getattr(var, "axis", None),
        )
    return out


def inspect_variables(file_path: str) -> Dict[str, VariableInfo]:
    """打开文件并返回全部变量元信息（只读，不读数据数组）。

    [EN] Open the file and return metadata for all variables (read-only; no data reads).
    """
    with Dataset(file_path, "r") as ds:
        return _snapshot_variables(ds)


def _role_key(field: str, role: str) -> str:
    """把角色映射为候选表键；坐标角色原样返回。

    [EN] Map a role to a candidate-table key; coordinate roles pass through.
    """
    if role == "u":
        return "wind_u" if field == "wind" else "current_u"
    if role == "v":
        return "wind_v" if field == "wind" else "current_v"
    if field == "level" and role == "value":
        return "level"
    if field == "ice" and role == "concentration":
        return "ice"
    return role  # longitude / latitude / time / value→level / concentration→ice / thickness


def _match_by_name(variables: Dict[str, VariableInfo], role: str) -> List[str]:
    """按常见名称候选匹配变量（精确匹配，收集全部命中）。

    [EN] Match variables by common-name candidates (exact; collect all hits).
    """
    if role == "longitude":
        candidates = _LON_NAME_CANDIDATES
    elif role == "latitude":
        candidates = _LAT_NAME_CANDIDATES
    elif role == "time":
        candidates = _TIME_NAME_CANDIDATES
    else:
        candidates = _ROLE_NAME_CANDIDATES.get(role, ())
    return [name for name in candidates if name in variables]


def _match_by_cf(variables: Dict[str, VariableInfo], role: str) -> List[str]:
    """按 CF 属性（standard_name / units / axis）匹配变量。

    standard_name 命中优先；无 standard_name 命中时才按 units 兜底，
    避免同单位变量（如 U/V 都是 m/s）互相干扰。

    [EN] Match variables by CF attributes (standard_name / units / axis).
    standard_name hits win; units only as fallback so same-unit variables
    (e.g. U and V both m/s) do not interfere.
    """
    std_names = _ROLE_STANDARD_NAMES.get(role)
    units_frags = _ROLE_UNITS.get(role, ())
    std_hits: List[str] = []
    unit_hits: List[str] = []
    for name, info in variables.items():
        if role == "time" and str(info.axis or "").upper() == "T":
            std_hits.append(name)
            continue
        if std_names and info.standard_name and str(info.standard_name).lower() in std_names:
            std_hits.append(name)
            continue
        if units_frags and info.units:
            unit_lower = str(info.units).lower()
            if any(frag in unit_lower for frag in units_frags):
                unit_hits.append(name)
    if std_hits:
        return std_hits
    return unit_hits


def _unique_match(variables: Dict[str, VariableInfo], role: str, *, user_value: Optional[str]) -> Tuple[Optional[str], List[VariableInfo]]:
    """解析单个角色：用户值 > 名称匹配 > CF 匹配；多个候选即歧义。

    [EN] Resolve one role: user value > name match > CF match; multiple candidates = ambiguous.

    返回 ``(选中变量名或 None, 候选变量列表)``。

    [EN] Returns ``(selected name or None, candidate variable list)``.
    """
    if user_value:
        if user_value not in variables:
            raise ForcingVariableError(
                tr(
                    "forcing_custom_var_not_found",
                    "自定义变量 {var} 在文件中不存在（角色：{role}）",
                ).format(var=user_value, role=role),
                field="", role=role,
            )
        return user_value, [variables[user_value]]

    name_hits = _match_by_name(variables, role)
    if len(name_hits) == 1:
        return name_hits[0], [variables[name_hits[0]]]
    if len(name_hits) > 1:
        return None, [variables[n] for n in name_hits]

    cf_hits = _match_by_cf(variables, role)
    if len(cf_hits) == 1:
        return cf_hits[0], [variables[cf_hits[0]]]
    if len(cf_hits) > 1:
        return None, [variables[n] for n in cf_hits]

    return None, []


def _validate_resolution(
    field: str,
    resolved: Dict[str, str],
    variables: Dict[str, VariableInfo],
    components: List[str],
) -> None:
    """结构校验（方案 §5）：分量、维度一致性、坐标约束。

    [EN] Structural validation (spec §5): components, dimension consistency, coordinate constraints.
    """
    lon_name = resolved["longitude"]
    lat_name = resolved["latitude"]
    time_name = resolved["time"]

    lon_info = variables[lon_name]
    lat_info = variables[lat_name]
    time_info = variables[time_name]

    # 坐标维度名 = 各坐标变量自身的一维维度名（维度名可与变量名不同，
    # 例如坐标变量 valid_time 的维度名是 time）
    # [EN] Coordinate dimension name = the 1-D dimension of each coordinate
    # variable (dimension name may differ from variable name, e.g. variable
    # valid_time on dimension time)
    lon_dim = lon_info.dimensions[0] if lon_info.dimensions else None
    lat_dim = lat_info.dimensions[0] if lat_info.dimensions else None
    time_dim = time_info.dimensions[0] if time_info.dimensions else None

    # 经纬度必须是一维（单调性由归一化阶段检查：经度递减拒绝、纬度递减翻转）
    # [EN] lon/lat must be 1-D (monotonicity is checked at normalization:
    # descending longitude rejected, descending latitude flipped)
    if len(lon_info.dimensions) != 1:
        raise ForcingVariableError(
            tr("forcing_lon_not_1d", "经度变量 {name} 必须是一维（实际维度：{dims}）").format(
                name=lon_name, dims=", ".join(lon_info.dimensions) or "标量"
            ),
            field=field, role="longitude",
        )
    if len(lat_info.dimensions) != 1:
        raise ForcingVariableError(
            tr("forcing_lat_not_1d", "纬度变量 {name} 必须是一维（实际维度：{dims}）").format(
                name=lat_name, dims=", ".join(lat_info.dimensions) or "标量"
            ),
            field=field, role="latitude",
        )
    if len(time_info.dimensions) != 1:
        raise ForcingVariableError(
            tr("forcing_time_not_1d", "时间变量 {name} 必须是一维（实际维度：{dims}）").format(
                name=time_name, dims=", ".join(time_info.dimensions) or "标量"
            ),
            field=field, role="time",
        )

    # 时间必须带 WW3 可识别的单位（units 含 "since" 或为 CF 时间单位）
    # [EN] Time must carry WW3-recognizable units (units containing "since" or CF time units)
    units = (time_info.units or "").strip().lower()
    if not units or not (
        "since" in units
        or units.startswith("seconds")
        or units.startswith("minutes")
        or units.startswith("hours")
        or units.startswith("days")
    ):
        raise ForcingVariableError(
            tr(
                "forcing_time_units_unknown",
                "时间变量 {name} 缺少 WW3 可识别的 units 属性（当前：{units}）",
            ).format(name=time_name, units=time_info.units or "无"),
            field=field, role="time",
        )

    # 分量：数量校验 + 维度一致性 + 无未处理非单例额外维度 + U/V 不同变量
    # [EN] Components: count, dimension consistency, no unhandled non-singleton extra dims, U != V
    comp_vars = [variables[c] for c in components]
    coord_dims = {lon_dim, lat_dim, time_dim}
    for info in comp_vars:
        extra_dims = [d for d in info.dimensions if d not in coord_dims]
        for extra in extra_dims:
            idx = list(info.dimensions).index(extra)
            if info.shape[idx] != 1:
                raise ForcingVariableError(
                    tr(
                        "forcing_extra_dim",
                        "数据变量 {var} 存在未处理的非单例额外维度 {dim}（形状 {shape}）",
                    ).format(var=info.name, dim=extra, shape=info.shape),
                    field=field, role="data",
                )
        for coord in (lon_dim, lat_dim, time_dim):
            if coord not in info.dimensions:
                raise ForcingVariableError(
                    tr(
                        "forcing_component_missing_dim",
                        "数据变量 {var} 缺少坐标维度 {coord}（实际维度：{dims}）",
                    ).format(var=info.name, coord=coord, dims=", ".join(info.dimensions) or "标量"),
                    field=field, role="data",
                )

    if field in ("wind", "current") and len(set(components)) < len(components):
        raise ForcingVariableError(
            tr("forcing_u_v_same", "U 分量与 V 分量不能是同一个变量"),
            field=field, role="data",
        )


def resolve_forcing_variables(
    file_path: str,
    field: str,
    custom: Optional[ForcingVariableOverride] = None,
) -> ResolvedForcingVariables:
    """解析单个强迫场的变量映射（方案 §4 的唯一入口）。

    [EN] Resolve the variable mapping for one forcing field (spec §4 single entry point).

    参数:
        file_path: 源 NetCDF 路径
        field: 场类型（wind/current/level/ice）
        custom: 用户自定义映射；``None`` 或全空时全部自动识别

    返回:
        ``ResolvedForcingVariables``

    异常:
        ``ForcingVariableError``：缺失角色/歧义/结构非法，携带候选变量供展示
    """
    if field not in _FIELD_ROLES:
        raise ValueError(f"未知强迫场类型: {field}")
    if not file_path or not os.path.isfile(file_path):
        raise ForcingVariableError(
            tr("forcing_file_missing", "文件不存在：{path}").format(path=file_path),
            field=field, role="file",
        )

    variables = inspect_variables(file_path)
    roles = _FIELD_ROLES[field]
    override = custom or ForcingVariableOverride()

    resolved: Dict[str, str] = {}
    for role in roles:
        user_value = getattr(override, role, None)
        if role == "thickness" and not user_value:
            # 厚度是可选项：未填写时尝试自动识别，识别不到不报错
            # [EN] Thickness is optional: try auto-detect; not found is fine
            name_hits = _match_by_name(variables, "thickness") or _match_by_cf(variables, "thickness")
            if len(name_hits) == 1:
                resolved[role] = name_hits[0]
            continue
        key = _role_key(field, role)
        name, candidates = _unique_match(variables, key, user_value=user_value)
        if name is None:
            detail = (
                tr("forcing_role_ambiguous", "存在多个候选变量，无法自动确定：{cands}")
                if candidates
                else tr(
                    "forcing_role_not_found",
                    "无法自动识别该角色；可用变量：{avail}",
                ).format(avail=", ".join(sorted(variables)) or "（无）")
            )
            raise ForcingVariableError(
                tr(
                    "forcing_role_unresolved",
                    "无法确定 {field} 场的 {role} 角色。{detail}",
                ).format(field=field, role=role, detail=detail),
                field=field, role=role,
                candidates=[c for c in candidates] or list(variables.values()),
            )
        resolved[role] = name

    components = [resolved[r] for r in FIELD_COMPONENTS[field]]
    _validate_resolution(field, resolved, variables, components)

    return ResolvedForcingVariables(
        field=field,
        longitude=resolved["longitude"],
        latitude=resolved["latitude"],
        source_time=resolved["time"],
        output_time="time",
        components=components,
        thickness=resolved.get("thickness"),
    )


def _has_any_role_candidate(variables: Dict[str, VariableInfo], role: str) -> bool:
    """场是否存在某角色的候选（名字候选或 CF standard_name 候选）。

    [EN] Whether a role has any candidate in the file (name candidates or CF standard_name).
    """
    if any(n in variables for n in _ROLE_NAME_CANDIDATES.get(role, ())):
        return True
    std_names = _ROLE_STANDARD_NAMES.get(role, ())
    return any(
        info.standard_name and str(info.standard_name).lower() in std_names
        for info in variables.values()
    )


def resolve_all_fields(
    file_path: str,
    custom: Optional[Dict[str, ForcingVariableOverride]] = None,
) -> Dict[str, ResolvedForcingVariables]:
    """解析文件中全部可识别的场（供自动关联/多场合并文件使用）。

    [EN] Resolve all recognizable fields in a file (for auto-association /
    multi-field merged files).

    只返回完整解析成功的场；任一角色失败即跳过该场。

    [EN] Only fully resolved fields are returned; a field is skipped when any
    role fails.
    """
    custom = custom or {}
    results: Dict[str, ResolvedForcingVariables] = {}
    variables = inspect_variables(file_path)
    # 预检：文件是否至少包含每个场的一个分量候选（快速跳过不相关文件）。
    # 用户自定义了变量名时跳过预检（自定义名可能是任意不规则名），直接尝试解析。
    # [EN] Precheck whether the file contains at least one component candidate
    # per field (fast skip). When the user provided custom names, skip the
    # precheck (custom names may be arbitrary) and try resolving directly.
    for field in _FIELD_ROLES:
        field_custom = custom.get(field)
        has_custom_names = bool(
            field_custom is not None
            and any(v for v in vars(field_custom).values() if v)
        )
        if not has_custom_names:
            if field in ("wind", "current"):
                u_role = "wind_u" if field == "wind" else "current_u"
                v_role = "wind_v" if field == "wind" else "current_v"
                has = _has_any_role_candidate(variables, u_role) and _has_any_role_candidate(variables, v_role)
            else:
                has = _has_any_role_candidate(variables, field)
            if not has:
                continue
        try:
            results[field] = resolve_forcing_variables(file_path, field, custom.get(field))
        except ForcingVariableError:
            continue
    return results
