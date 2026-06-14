"""无 GUI 环境下准备 WW3 namelist 与运行脚本。

架构说明 — 对象适配器模式
--------------------------
``ModifyWW3NML`` 与 ``StepFourServiceMixin`` 原为 Qt Mixin：方法通过
``self.some_widget.text()`` / ``.currentText()`` 读取界面参数。

``_WW3Adapter`` 是无头 *对象适配器*：继承上述 Mixin，但用 ``widget_stubs.py``
中的轻量桩对象替代真实 Qt 控件，从 ``PipelineConfig`` 注入纯 Python 值，
无需导入 Qt。

    桌面端：真实 Qt 控件 → Mixin 调用 ``self.widget.text()``
    CLI 端：``_TextValue(字符串)`` → Mixin 调用相同 API

[EN] Prepare WW3 namelist and run scripts in a headless (no-GUI) environment.

Architecture note — Object Adapter pattern
-------------------------------------------
``ModifyWW3NML`` and ``StepFourServiceMixin`` were originally Qt Mixins: methods
read UI parameters via ``self.some_widget.text()`` / ``.currentText()``.

``_WW3Adapter`` is a headless *object adapter*: it inherits from those Mixins but
replaces real Qt widgets with lightweight stub objects from ``widget_stubs.py``,
injecting pure Python values from ``PipelineConfig`` without importing Qt.

    Desktop: real Qt widgets -> Mixin calls ``self.widget.text()``
    CLI:     ``_TextValue(string)`` -> Mixin calls the same API
"""

from __future__ import annotations

import copy
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ...domain.config_models import PipelineConfig, PointConfig, TrackPointConfig
from ...domain.forcing_fields import ForcingField, Step1Files
from ...support.logging import CoreLogger
from ...support.translations import tr
from .. import runtime_config
from ..ww3 import modify_ww3_nml as modify_ww3_nml_module
from ..ww3 import step4_service as step4_service_module
from ..ww3.modify_ww3_nml import ModifyWW3NML
from ..ww3.step4_service import StepFourServiceMixin
from ..ww3.widget_stubs import _Checkbox, _ComboValue, _Table, _TextValue


class _WW3Adapter(ModifyWW3NML, StepFourServiceMixin):
    """将 ``PipelineConfig`` 与 Step 1 强迫场路径映射为 Mixin 所需的桩控件属性。

    [EN] Map ``PipelineConfig`` and Step 1 forcing field paths to stub widget properties expected by the Mixin.
    """

    def __init__(self, config: PipelineConfig, files: Step1Files, logger: CoreLogger, app_config: Dict[str, Any]) -> None:
        self._logger = logger
        self._app_config = app_config
        self._loaded_config = config
        self.selected_folder = str(config.workdir.path)

        self.grid_type_var = "嵌套网格" if config.grid.grid_type == "nested" else "普通网格"
        # 存储原始 mesh_type 供检测方法使用（避免翻译后文本不匹配）
        # [EN] Store the raw mesh_type for detection methods (to avoid mismatches with translated text)
        self._raw_mesh_type = config.grid.mesh_type
        if config.grid.mesh_type == "unstructured":
            self.mesh_type_var = "非结构网格"
        elif config.grid.mesh_type == "smc":
            self.mesh_type_var = "SMC 网格"
        else:
            self.mesh_type_var = "结构网格"

        if config.calc.mode == "spectral_point":
            self.calc_mode_var = "谱空间逐点计算"
        elif config.calc.mode == "track":
            self.calc_mode_var = "航迹模式"
        else:
            self.calc_mode_var = "区域尺度计算"
        self.calc_mode_combo = _ComboValue(self.calc_mode_var)

        inner_compute = config.ww3.inner_compute_precision or config.ww3.compute_precision
        inner_output = config.ww3.inner_output_precision or config.ww3.output_precision
        self.shel_start_edit = _TextValue(config.ww3.start_date)
        self.shel_end_edit = _TextValue(config.ww3.end_date)
        self.shel_step_edit = _TextValue(config.ww3.compute_precision)
        self.output_precision_edit = _TextValue(config.ww3.output_precision)
        self.inner_shel_step_edit = _TextValue(inner_compute)
        self.inner_output_precision_edit = _TextValue(inner_output)

        self.num_n_edit = _TextValue(config.slurm.cores)
        self.num_N_edit = _TextValue(config.slurm.nodes)
        self.cpu_var = config.slurm.cpu
        self.st_var = _resolve_st_name(config, app_config)

        self.output_scheme_combo = _ComboValue(_resolve_output_scheme_name(config, app_config))

        self.selected_origin_file = files.get(ForcingField.WIND)
        self.selected_current_file = files.get(ForcingField.CURRENT)
        self.selected_level_file = files.get(ForcingField.LEVEL)
        self.selected_ice_file = files.get(ForcingField.ICE)
        self.forcing_field_checkboxes = {
            "wind": {"checkbox": _Checkbox(bool(self.selected_origin_file))},
            "current": {"checkbox": _Checkbox(bool(self.selected_current_file))},
            "level": {"checkbox": _Checkbox(bool(self.selected_level_file))},
            "ice": {"checkbox": _Checkbox(bool(self.selected_ice_file))},
        }

        self.spectral_points_table = _Table(_spectral_rows(config.calc.points))
        self.track_points_table = _Table(_track_rows(config.calc.track_points))

    def log(self, message: str) -> None:
        """将 Mixin 内部日志转发至 ``CoreLogger``。

        [EN] Forward Mixin internal logs to ``CoreLogger``.
        """
        self._logger.log(message)

    def _show_info_bar(self, *_args, **_kwargs) -> None:
        """CLI 模式下忽略桌面信息条。

        [EN] Ignore desktop info bar messages in CLI mode.
        """
        return None


def _spectral_rows(points: Iterable[PointConfig]) -> List[List[Any]]:
    """将谱点配置转为 Mixin 表格行（含表头）。

    [EN] Convert spectral point configurations to Mixin table rows (including header).
    """
    rows: List[List[Any]] = [["lon", "lat", "name"]]
    for i, point in enumerate(points, 1):
        rows.append([point.lon, point.lat, point.name or f"Point_{i}"])
    return rows


def _track_rows(points: Iterable[TrackPointConfig]) -> List[List[Any]]:
    """将航迹点配置转为 Mixin 表格行（含表头）。

    [EN] Convert track point configurations to Mixin table rows (including header).
    """
    rows: List[List[Any]] = [["datetime", "lon", "lat", "name"]]
    for i, point in enumerate(points, 1):
        rows.append([point.datetime, point.lon, point.lat, point.name or f"Track_{i}"])
    return rows


def _resolve_st_name(config: PipelineConfig, app_config: Dict[str, Any]) -> str:
    """解析源项（ST）方案名称，优先使用流水线配置。

    [EN] Resolve the source term (ST) scheme name, preferring the pipeline configuration.
    """
    if config.ww3.st:
        return str(config.ww3.st)
    versions = app_config.get("ST_VERSIONS") or []
    if versions and isinstance(versions, list) and isinstance(versions[0], dict):
        return str(versions[0].get("name") or "")
    opts = app_config.get("ST_OPTIONS") or []
    if opts:
        return str(opts[0])
    return ""


def _resolve_output_scheme_name(config: PipelineConfig, app_config: Dict[str, Any]) -> str:
    """输出变量方案在运行时配置中的键名（``__params__`` 表示来自 params.yml）。

    [EN] Key name of the output variable scheme in the runtime config (``__params__`` indicates it comes from params.yml).
    """
    return "__params__"


def _merged_runtime_config(config: PipelineConfig) -> Dict[str, Any]:
    """构建供 WW3 namelist 生成使用的运行时配置字典。

    路径全部来自 ``PipelineConfig.paths``（params.yml），项目参数来自其他段。

    [EN] Build the runtime configuration dictionary used for WW3 namelist generation.

    All paths come from ``PipelineConfig.paths`` (params.yml); project parameters come from other sections.
    """
    merged: Dict[str, Any] = {}

    # 路径参数全部来自 params.yml 的 paths: 段
    # [EN] Path parameters all come from the paths: section of params.yml
    paths = config.paths
    merged["MATLAB_PATH"] = paths.matlab_path
    merged["GRIDGEN_VERSION"] = config.grid.gridgen_version
    merged["REFERENCE_DATA_PATH"] = str(config.grid.reference_data_path or "")
    merged["WW3BIN_PATH"] = paths.ww3bin_path

    # 项目参数来自 PipelineConfig 各段
    # [EN] Project parameters come from various sections of PipelineConfig
    merged["FILE_SPLIT"] = config.ww3.file_split
    merged["DEFAULT_CPU"] = config.slurm.cpu
    merged["NODE_NUM"] = config.slurm.nodes
    merged["KERNEL_NUM"] = config.slurm.cores

    parameters = config.ww3_grid.parameters
    merged.update(
        {
            "FREQ_INC": parameters["SPECTRUM%XFR"],
            "FREQ_START": parameters["SPECTRUM%FREQ1"],
            "FREQ_NUM": parameters["SPECTRUM%NK"],
            "DIR_NUM": parameters["SPECTRUM%NTH"],
            "DTMAX": parameters["TIMESTEPS%DTMAX"],
            "DTXY": parameters["TIMESTEPS%DTXY"],
            "DTKTH": parameters["TIMESTEPS%DTKTH"],
            "DTMIN": parameters["TIMESTEPS%DTMIN"],
        }
    )
    merged["ST_OPTIONS"] = list(config.presets.st)
    merged["ST_VERSIONS"] = [
        {
            "name": name,
            "path": str(Path(executable_dir).parent),
        }
        for name, executable_dir in config.presets.st.items()
    ]

    # 谱分区输出方案：全部来自 PipelineConfig.presets.output_scheme (params.yml)
    # [EN] Spectral partition output scheme: all from PipelineConfig.presets.output_scheme (params.yml)
    schemes = copy.deepcopy(config.presets.output_scheme)
    # 追加当前项目方案作为 __params__，供下游 namelist 模板使用
    # [EN] Append the current project scheme as __params__ for use by downstream namelist templates
    if config.ww3.output_scheme in config.presets.output_scheme:
        schemes["__params__"] = list(config.presets.output_scheme[config.ww3.output_scheme])
    merged["OUTPUT_VARS_SCHEMES"] = schemes
    return merged


def _ww3_grid_paths(config: PipelineConfig) -> List[Path]:
    """返回需写入谱/时间步参数的 ``ww3_grid.nml`` 路径列表。

    [EN] Return the list of ``ww3_grid.nml`` paths that need spectral/timestep parameters written into them.
    """
    if config.grid.grid_type == "nested":
        return [config.workdir.path / "coarse" / "ww3_grid.nml", config.workdir.path / "fine" / "ww3_grid.nml"]
    return [config.workdir.path / "ww3_grid.nml"]


def _apply_ww3_grid_settings(config: PipelineConfig, logger: CoreLogger) -> None:
    """将 ``ww3_grid.parameters`` 中的数值写回已有 ``ww3_grid.nml`` 对应 namelist 段。

    [EN] Write numeric values from ``ww3_grid.parameters`` back into the corresponding namelist sections of existing ``ww3_grid.nml`` files.
    """
    parameters = config.ww3_grid.parameters
    values = {
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
    for path in _ww3_grid_paths(config):
        if not path.is_file():
            logger.log(tr("ww3_grid_nml_not_found", "未找到 ww3_grid.nml，跳过频谱与时间步长参数写入"))
            continue
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        new_lines: List[str] = []
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
        if changed:
            path.write_text("".join(new_lines), encoding="utf-8")
            logger.log(tr("ww3_grid_params_applied", "✅ 已将频谱参数与时间步长写入 ww3_grid.nml"))


@contextmanager
def _patched_load_config(config: Dict[str, Any]):
    """临时将各 WW3 模块的 ``load_config`` 指向合并后的内存配置。

    [EN] Temporarily redirect ``load_config`` in each WW3 module to the merged in-memory configuration.
    """
    originals = {
        "runtime": runtime_config.load_config,
        "modify": getattr(modify_ww3_nml_module, "load_config", None),
        "step4": getattr(step4_service_module, "load_config", None),
    }

    def _load_config():
        return copy.deepcopy(config)

    runtime_config.load_config = _load_config
    modify_ww3_nml_module.load_config = _load_config
    step4_service_module.load_config = _load_config
    try:
        yield
    finally:
        runtime_config.load_config = originals["runtime"]
        if originals["modify"] is not None:
            modify_ww3_nml_module.load_config = originals["modify"]
        if originals["step4"] is not None:
            step4_service_module.load_config = originals["step4"]


def prepare_ww3_files(config: PipelineConfig, files: Step1Files, logger: CoreLogger) -> None:
    """根据流水线配置与 Step 1 强迫场路径生成 WW3 namelist 与辅助脚本。

    参数:
        config: 完整流水线配置（网格、计算模式、SLURM、WW3 时间范围等）
        files: Step 1 已选 wind/current/level/ice 文件路径
        logger: 进度与诊断日志

    流程:
        1. 构建 ``_WW3Adapter`` 并 patch ``load_config``；
        2. 调用 ``modify_ww3_file()`` 写出 namelist；
        3. 将 ``ww3_grid.parameters`` 数值写回 ``ww3_grid.nml``。

    [EN] Generate WW3 namelist and auxiliary scripts based on the pipeline configuration and Step 1 forcing field paths.

    Args:
        config: Complete pipeline configuration (grid, computation mode, SLURM, WW3 time range, etc.)
        files: Step 1 selected wind/current/level/ice file paths
        logger: Progress and diagnostic logging

    Workflow:
        1. Build ``_WW3Adapter`` and patch ``load_config``;
        2. Call ``modify_ww3_file()`` to write out the namelist;
        3. Write ``ww3_grid.parameters`` values back into ``ww3_grid.nml``.
    """
    app_config = _merged_runtime_config(config)
    adapter = _WW3Adapter(config, files, logger, app_config)
    with _patched_load_config(app_config):
        adapter.modify_ww3_file()
    _apply_ww3_grid_settings(config, logger)
