"""SMC 网格 namelist 与 ``ww3.version``（6.07 / 7.14）的字段对应。

6.07 SMC 使用 ``GRID%TYPE='RECT'`` + ``&SMC_NML``，``&PSMC`` 字段为
``CFLTM`` / ``DTIME`` / ``LATMIN``（实数纬度）。

7.14+ 使用 ``GRID%TYPE='SMCG'``，``&PSMC`` 字段为 ``CFLSM`` / ``DTIMS`` / ``Arctic``（逻辑）。

[EN] Mapping between SMC grid namelist fields and ``ww3.version`` (6.07 / 7.14).

WW3 6.07 SMC uses ``GRID%TYPE='RECT'`` + ``&SMC_NML``; ``&PSMC`` fields are
``CFLTM`` / ``DTIME`` / ``LATMIN`` (real latitude).

WW3 7.14+ uses ``GRID%TYPE='SMCG'``; ``&PSMC`` fields are ``CFLSM`` / ``DTIMS`` / ``Arctic`` (logical).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from ..runtime_config import get_ww3_version, read_ww3_version

DEFAULT_WW3_VERSION = "6.07"


def normalize_ww3_version(version: str | None) -> str:
    """规范为 ``6.07`` 或 ``7.14``。

    [EN] Normalize the version string to ``6.07`` or ``7.14``.
    """
    v = (version or DEFAULT_WW3_VERSION).strip()
    if v.startswith("6"):
        return "6.07"
    if v.startswith("7"):
        return "7.14"
    return v


def is_ww3_version_6(version: str | None) -> bool:
    return normalize_ww3_version(version).startswith("6")


def smc_grid_type_for_version(version: str | None) -> str:
    """6.07 → ``RECT``；7.14 → ``SMCG``。

    [EN] Map WW3 version to SMC grid type: 6.07 → ``RECT``; 7.14 → ``SMCG``.
    """
    return "RECT" if is_ww3_version_6(version) else "SMCG"


def resolve_ww3_version(
    *,
    work_dir: str | Path | None = None,
    config: dict | None = None,
) -> str:
    """从运行时 config、工作目录 ``params.yml`` 或仓库默认读取版本。

    [EN] Resolve the WW3 version from runtime config, ``params.yml`` in the working directory,
    or the repository default.
    """
    if config and config.get("WW3_VERSION"):
        return normalize_ww3_version(str(config["WW3_VERSION"]))
    if work_dir:
        params = Path(work_dir).expanduser() / "params.yml"
        if params.is_file():
            return normalize_ww3_version(read_ww3_version(params_path=params))
    return normalize_ww3_version(get_ww3_version())


def _arctic_to_latmin(value: str) -> str:
    v = value.strip().rstrip(",").upper()
    if v in (".TRUE.", "T", "TRUE"):
        return "85.0"
    return "86.0"


def _latmin_to_arctic(value: str) -> str:
    try:
        lat = float(value.strip().rstrip(","))
    except ValueError:
        return ".FALSE."
    return ".TRUE." if lat < 86.0 else ".FALSE."


def _psmc_key_for_version(key: str, value: str, *, ww3_version: str) -> tuple[str, str]:
    """将单行 PSMC 键名/值映射到目标 WW3 版本。

    [EN] Map a single PSMC key/value pair to the target WW3 version.
    """
    key_u = key.upper()
    if is_ww3_version_6(ww3_version):
        if key_u == "CFLSM":
            return "CFLTM", value
        if key_u == "DTIMS":
            return "DTIME", value
        if key_u == "ARCTIC":
            return "LATMIN", _arctic_to_latmin(value)
        return key, value

    if key_u == "CFLTM":
        return "CFLSM", value
    if key_u == "DTIME":
        return "DTIMS", value
    if key_u == "LATMIN":
        return "Arctic", _latmin_to_arctic(value)
    return key, value


def normalize_psmc_assignment_line(line: str, *, ww3_version: str) -> str:
    """按目标版本改写 ``&PSMC`` 块内单行赋值。

    [EN] Rewrite a single assignment line inside ``&PSMC`` for the target WW3 version.
    """
    body = line.rstrip("\n")
    nl = "\n" if line.endswith("\n") else ""
    m = re.match(r"^(\s*)([A-Za-z][A-Za-z0-9]*)\s*=\s*(.+)$", body)
    if not m:
        return line
    indent, key, rest = m.groups()
    new_key, new_rest = _psmc_key_for_version(key, rest, ww3_version=ww3_version)
    if new_key == key and new_rest == rest:
        return line
    return f"{indent}{new_key} = {new_rest}{nl}"


def normalize_psmc_namelist_lines(
    lines: Iterable[str],
    *,
    ww3_version: str,
) -> tuple[list[str], bool]:
    """规范化 ``namelists.nml`` 中 ``&PSMC`` 块的字段名（6.07 ↔ 7.14）。

    [EN] Normalize ``&PSMC`` block field names in ``namelists.nml`` between WW3 6.07 and 7.14.
    """
    out: list[str] = []
    modified = False
    in_psmc = False
    for line in lines:
        stripped = line.lstrip()
        is_comment = stripped.startswith("!")

        if not is_comment and re.match(r"^\s*&PSMC\b", line, re.IGNORECASE):
            in_psmc = True
            out.append(line)
            continue

        if in_psmc and not is_comment:
            if re.match(r"^\s*/\s*$", line):
                in_psmc = False
                out.append(line)
                continue
            updated = normalize_psmc_assignment_line(line, ww3_version=ww3_version)
            modified = modified or (updated != line)
            out.append(updated)
            continue

        out.append(line)
    return out, modified
