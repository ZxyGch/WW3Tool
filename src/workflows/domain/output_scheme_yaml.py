"""ww3.output_scheme YAML 块解析与写回。

推荐写法：方案名 → 空格分隔字段::

    output_scheme:
      use: with_spectrum          # 多方案时指定当前启用项
      standard: HS DIR FP T02 WND PHS PTP PDIR PWS PNR TWS
      with_spectrum: HS DIR FP T02 WND PHS PTP PDIR PWS PNR TWS EF

仅一个方案时可省略 ``use``::

    output_scheme:
      with_spectrum: HS DIR FP T02 WND PHS PTP PDIR PWS PNR TWS EF

旧格式（兼容）::

    output_scheme:
      name: with_spectrum
      fields: HS DIR FP T02 WND PHS PTP PDIR PWS PNR TWS EF
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from .parameter_catalog import OUTPUT_FIELD_OPTIONS

OUTPUT_SCHEME_META_KEYS = frozenset({"use", "active"})
SYNTHETIC_OUTPUT_SCHEME_KEYS = frozenset({"__params__"})


def visible_output_scheme_names(schemes: Mapping[str, object]) -> list[str]:
    """返回应展示给用户的方案名（排除 __params__ 等内部键）。"""
    return sorted(
        str(name)
        for name in schemes
        if str(name) not in SYNTHETIC_OUTPUT_SCHEME_KEYS and not str(name).startswith("__")
    )


def visible_output_schemes(schemes: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    """返回应展示/编辑的方案映射（排除内部合成键）。"""
    return {
        str(name): list(fields)
        for name, fields in schemes.items()
        if str(name) not in SYNTHETIC_OUTPUT_SCHEME_KEYS and not str(name).startswith("__")
    }


def _normalize_field_codes(raw_fields: Iterable[str], path: str) -> list[str]:
    fields: list[str] = []
    for field in raw_fields:
        code = str(field).strip().upper()
        if not code:
            continue
        if code not in OUTPUT_FIELD_OPTIONS:
            raise ValueError(f"{path} 包含未知输出字段：{field}")
        if code not in fields:
            fields.append(code)
    if not fields:
        raise ValueError(f"{path} 必须是非空字段数组或空格分隔字符串")
    return fields


def parse_output_fields_value(value: Any, path: str) -> list[str]:
    """解析字段列表（字符串或数组）。"""
    if isinstance(value, str):
        raw_fields = value.replace(",", " ").split()
    elif isinstance(value, list):
        raw_fields = value
    else:
        raise ValueError(f"{path} 必须是非空字段数组或空格分隔字符串")
    return _normalize_field_codes(raw_fields, path)


def is_legacy_output_scheme_dict(value: Mapping[str, Any]) -> bool:
    return "fields" in value


def parse_ww3_output_scheme(
    value: Any,
    *,
    path: str = "ww3.output_scheme",
) -> tuple[str, list[str], dict[str, list[str]]]:
    """解析 ``ww3.output_scheme``，返回 (当前方案名, 当前字段, yaml 内定义的全部方案)。"""
    if value is None:
        raise ValueError(f"{path} 不能为空")

    yaml_schemes: dict[str, list[str]] = {}

    if isinstance(value, str):
        raise ValueError(
            f"{path} 请使用映射格式，例如：with_spectrum: HS DIR FP T02 WND PHS PTP PDIR PWS PNR TWS EF"
        )

    if not isinstance(value, dict):
        raise ValueError(f"{path} 必须是方案映射对象或旧版 name/fields 对象")

    if is_legacy_output_scheme_dict(value):
        active = str(value.get("name") or "").strip()
        fields = parse_output_fields_value(value.get("fields"), f"{path}.fields")
        if not active:
            raise ValueError(f"{path}.name 不能为空")
        yaml_schemes[active] = fields
        return active, fields, yaml_schemes

    active: str | None = None
    for key, raw in value.items():
        scheme_name = str(key).strip()
        if not scheme_name:
            raise ValueError(f"{path} 的方案名不能为空")
        if scheme_name in OUTPUT_SCHEME_META_KEYS:
            active = str(raw).strip()
            continue
        yaml_schemes[scheme_name] = parse_output_fields_value(
            raw,
            f"{path}.{scheme_name}",
        )

    if not yaml_schemes:
        raise ValueError(f"{path} 至少应定义一个方案（方案名: 空格分隔字段）")

    if not active:
        if len(yaml_schemes) == 1:
            active = next(iter(yaml_schemes))
        else:
            raise ValueError(f"{path} 定义了多个方案时需指定 use: <方案名>")

    if active not in yaml_schemes:
        raise ValueError(f"{path}.use 未知方案名：{active}；须在 output_scheme 中定义")

    return active, yaml_schemes[active], yaml_schemes


def serialize_ww3_output_scheme(
    active: str,
    schemes: Mapping[str, Sequence[str]],
) -> dict[str, str]:
    """将方案映射写回 YAML 友好格式（use + 方案名: 字段字符串）。"""
    active_name = str(active).strip()
    body: dict[str, str] = {}
    for name, fields in schemes.items():
        key = str(name).strip()
        if not key or key.startswith("__") or key in OUTPUT_SCHEME_META_KEYS:
            continue
        body[key] = " ".join(str(f).strip().upper() for f in fields if str(f).strip())
    if not body:
        raise ValueError("output_scheme 无有效方案可写回")
    if active_name not in body:
        body[active_name] = " ".join(str(f) for f in schemes.get(active_name, []))
    if len(body) > 1:
        return {"use": active_name, **body}
    return body
