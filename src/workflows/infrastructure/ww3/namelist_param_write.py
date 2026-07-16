"""将 ``ww3.namelist`` 物理源项参数写回 ``namelists.nml`` 的共享逻辑。

键名格式为 ``块名%变量名``（如 ``SIN4%BETAMAX``），仅在对应 ``&块名 … /`` 段内替换。

[EN] Shared logic for writing ``ww3.namelist`` physics source-term parameters back
into ``namelists.nml``. Keys use ``block%var`` (e.g. ``SIN4%BETAMAX``); replacements
are scoped to the matching ``&block … /`` section.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Mapping, Optional

from ...support.translations import tr
from ..runtime_config import load_config
from .nml_log_format import Assignment, format_nml_log_message

_PARAM_KEYS = (
    "SIN4%BETAMAX",
    "SIN4%SWELLF",
    "SDS4%SDSC2",
    "SDS4%SDSBR",
    "SBT1%GAMMA",
)


def _parse_param_key(key: str) -> tuple[str, str]:
    block, var = key.split("%", 1)
    return block.strip().upper(), var.strip().upper()


def namelist_parameters_from_config(cfg: Optional[Mapping[str, object]] = None) -> dict[str, str]:
    """从 ``load_config()`` 或合并后的运行时配置读取 ``ww3.namelist`` 参数。

    [EN] Read ``ww3.namelist`` parameters from ``load_config()`` or a merged
    runtime configuration dictionary.
    """
    raw = dict(cfg or load_config())
    ww3 = raw.get("ww3") or {}
    if not isinstance(ww3, Mapping):
        ww3 = {}
    nml = ww3.get("namelist") or {}
    if not isinstance(nml, Mapping):
        nml = {}

    out: dict[str, str] = {}
    for key in _PARAM_KEYS:
        value = nml.get(key)
        if value is not None and str(value).strip():
            out[key] = str(value)
    return out


def _block_var_map(parameters: Mapping[str, str]) -> dict[str, dict[str, str]]:
    grouped: dict[str, dict[str, str]] = {}
    for key, value in parameters.items():
        if key not in _PARAM_KEYS:
            continue
        block, var = _parse_param_key(key)
        grouped.setdefault(block, {})[var] = str(value)
    return grouped


def _namelist_param_log_assignments(parameters: Mapping[str, str]) -> list[Assignment]:
    return [(key.replace("%", "/"), parameters[key]) for key in _PARAM_KEYS if key in parameters]


def write_namelist_parameters_to_nml(
    nml_path: str | Path,
    parameters: Mapping[str, str],
    log: Optional[Callable[[str], None]] = None,
    *,
    level_idx: Optional[int] = None,
) -> bool:
    """写回单个 ``namelists.nml``；``level_idx`` 用于嵌套网格分层日志。

    [EN] Write parameters back to a single ``namelists.nml``; ``level_idx`` is
    used for per-level logging in nested grids.
    """
    path = Path(nml_path)
    block_vars = _block_var_map(parameters)
    if not block_vars:
        return False

    if not path.is_file():
        if log is not None:
            log(
                tr(
                    "namelists_nml_not_found",
                    "⚠️ 未找到 namelists.nml，跳过物理源项参数写入：{path}",
                ).format(path=path)
            )
        return False

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines: list[str] = []
    active_block: Optional[str] = None
    changed = False

    for line in lines:
        stripped = line.lstrip()
        is_comment = stripped.startswith("!")

        if not is_comment:
            block_match = re.match(r"^\s*&([A-Z0-9_]+)\b", line, re.IGNORECASE)
            if block_match:
                active_block = block_match.group(1).upper()

        if active_block and active_block in block_vars and not is_comment:
            updated = line
            for var, new_value in block_vars[active_block].items():
                pattern = rf"^(\s*{re.escape(var)}\s*=\s*)([^,\n]+)(.*)$"
                replaced, count = re.subn(
                    pattern,
                    rf"\g<1>{new_value}\g<3>",
                    updated,
                    count=1,
                    flags=re.IGNORECASE,
                )
                if count:
                    updated = replaced
                    changed = True
            new_lines.append(updated)
            if not is_comment and re.match(r"^\s*/\s*$", line):
                active_block = None
            continue

        new_lines.append(line)
        if active_block and not is_comment and re.match(r"^\s*/\s*$", line):
            active_block = None

    if not changed:
        return False

    path.write_text("".join(new_lines), encoding="utf-8")
    if log is not None:
        assignments = _namelist_param_log_assignments(parameters)
        if level_idx is not None:
            log(
                format_nml_log_message(
                    "namelists_params_applied_level",
                    "✅ 【level{idx}】已将物理源项参数写入 namelists.nml：\n{details}",
                    assignments,
                    idx=level_idx,
                    blank_before_prefixes=("SDS4/", "SBT1/"),
                )
            )
        else:
            log(
                format_nml_log_message(
                    "namelists_params_applied",
                    "✅ 已将物理源项参数写入 namelists.nml：\n{details}",
                    assignments,
                    blank_before_prefixes=("SDS4/", "SBT1/"),
                )
            )
    return True
