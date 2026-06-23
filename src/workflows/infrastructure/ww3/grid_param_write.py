"""将 ``ww3_grid`` 配置参数写回 ``ww3_grid.nml`` 的共享逻辑。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping, Optional

from ...support.translations import tr
from ..runtime_config import load_config

_PARAM_KEYS = (
    "SPECTRUM%XFR",
    "SPECTRUM%FREQ1",
    "SPECTRUM%NK",
    "SPECTRUM%NTH",
    "TIMESTEPS%DTMAX",
    "TIMESTEPS%DTXY",
    "TIMESTEPS%DTKTH",
    "TIMESTEPS%DTMIN",
)

_FLAT_KEY_FALLBACK = {
    "SPECTRUM%XFR": "FREQ_INC",
    "SPECTRUM%FREQ1": "FREQ_START",
    "SPECTRUM%NK": "FREQ_NUM",
    "SPECTRUM%NTH": "DIR_NUM",
    "TIMESTEPS%DTMAX": "DTMAX",
    "TIMESTEPS%DTXY": "DTXY",
    "TIMESTEPS%DTKTH": "DTKTH",
    "TIMESTEPS%DTMIN": "DTMIN",
}


def parameters_from_config(cfg: Optional[Mapping[str, object]] = None) -> dict[str, str]:
    """从 ``load_config()`` 或合并后的运行时配置字典提取 ww3_grid 参数。"""
    raw = dict(cfg or load_config())
    wg = raw.get("ww3_grid") or {}
    if not isinstance(wg, Mapping):
        wg = {}

    out: dict[str, str] = {}
    for key in _PARAM_KEYS:
        value = wg.get(key)
        if value is None:
            flat = _FLAT_KEY_FALLBACK.get(key)
            if flat:
                value = raw.get(flat)
        if value is not None:
            out[key] = str(value)
    return out


def _param_value_lines(parameters: Mapping[str, str]) -> dict[str, dict[str, str]]:
    return {
        "SPECTRUM_NML": {
            "SPECTRUM%XFR": f"  SPECTRUM%XFR       =  {parameters['SPECTRUM%XFR']}\n",
            "SPECTRUM%FREQ1": f"  SPECTRUM%FREQ1     =  {parameters['SPECTRUM%FREQ1']}\n",
            "SPECTRUM%NK": f"  SPECTRUM%NK        =  {parameters['SPECTRUM%NK']}\n",
            "SPECTRUM%NTH": f"  SPECTRUM%NTH       =  {parameters['SPECTRUM%NTH']}\n",
        },
        "TIMESTEPS_NML": {
            "TIMESTEPS%DTMAX": f"  TIMESTEPS%DTMAX        =  {parameters['TIMESTEPS%DTMAX']}\n",
            "TIMESTEPS%DTXY": f"  TIMESTEPS%DTXY         =  {parameters['TIMESTEPS%DTXY']}\n",
            "TIMESTEPS%DTKTH": f"  TIMESTEPS%DTKTH        =  {parameters['TIMESTEPS%DTKTH']}\n",
            "TIMESTEPS%DTMIN": f"  TIMESTEPS%DTMIN        =  {parameters['TIMESTEPS%DTMIN']}\n",
        },
    }


def write_ww3_grid_parameters_to_nml(
    nml_path: str | Path,
    parameters: Mapping[str, str],
    log: Optional[Callable[[str], None]] = None,
    *,
    level_idx: Optional[int] = None,
) -> bool:
    """写回单个 ``ww3_grid.nml``；``level_idx`` 用于嵌套网格分层日志。"""
    path = Path(nml_path)
    if not path.is_file():
        if log is not None:
            log(
                tr(
                    "ww3_grid_nml_not_found",
                    "⚠️ 未找到 ww3_grid.nml，跳过频谱与时间步长参数写入：{path}",
                ).format(path=path)
            )
        return False

    values = _param_value_lines(parameters)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines: list[str] = []
    active_section: Optional[str] = None
    changed = False
    for line in lines:
        stripped = line.lstrip()
        upper = stripped.upper()
        for section in values:
            if upper.startswith(f"&{section}"):
                active_section = section
                break
        if active_section and not stripped.startswith("!"):
            replacement = next(
                (replacement for key, replacement in values[active_section].items() if key in upper),
                None,
            )
            if replacement is not None:
                new_lines.append(replacement)
                changed = True
                continue
        new_lines.append(line)
        if active_section and stripped.startswith("/"):
            active_section = None

    if not changed:
        return False

    path.write_text("".join(new_lines), encoding="utf-8")
    if log is not None:
        if level_idx is not None:
            log(
                tr(
                    "ww3_grid_params_applied_level",
                    "✅ 【level{idx}】已将频谱参数与时间步长写入 ww3_grid.nml",
                ).format(idx=level_idx)
            )
        else:
            log(tr("ww3_grid_params_applied", "✅ 已将频谱参数与时间步长写入 ww3_grid.nml"))
    return True
