"""Desktop adapter for validate / run pipeline workflow entrypoints."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any, Callable, List, Optional

from workflows.application.configuration import (
    ConfigError,
    load_pipeline_config,
    parse_pipeline_config,
    validate_pipeline_config,
)
from workflows.domain.config_models import GridRegion, PipelineConfig
from workflows.domain.forcing_fields import Step1Files
from workflows.support.translations import tr


LogCallback = Callable[[str], None]
StateCallback = Callable[["PipelineStepState"], None]


@dataclass
class PipelineStepState:
    is_running: bool = False
    action: str = ""
    workdir: str = ""
    messages: List[str] = field(default_factory=list)
    error: Optional[str] = None
    result: Any = None


class PipelineViewModel:
    """Bridge from desktop actions to the same workflows used by runCLI.py."""

    def __init__(
        self,
        *,
        on_log: Optional[LogCallback] = None,
        on_state_change: Optional[StateCallback] = None,
    ) -> None:
        self._on_log = on_log
        self._on_state_change = on_state_change
        self.state = PipelineStepState()

    def load_config(self, params_path: str | Path, *, validation_stage: str = "full") -> PipelineConfig:
        return load_pipeline_config(params_path, validation_stage=validation_stage)

    def validate(self, config: PipelineConfig, *, stage: str = "full") -> None:
        validate_pipeline_config(config, stage=stage)

    def validate_file(self, params_path: str | Path, *, stage: str = "full") -> PipelineStepState:
        self._set_state(PipelineStepState(is_running=True, action="validate"))
        try:
            config = self.load_config(params_path, validation_stage=stage)
            self.validate(config, stage=stage)
            self._handle_log(tr("params_validation_ok", "参数校验通过：{path}").format(path=params_path))
            self._set_state(
                PipelineStepState(
                    is_running=False,
                    action="validate",
                    workdir=str(config.workdir.path),
                    messages=list(self.state.messages),
                )
            )
        except ConfigError as exc:
            self._fail("validate", str(exc))
        except Exception as exc:
            self._fail("validate", str(exc))
        return self.state

    def run(self, config: PipelineConfig, *, skip_grid: bool = False) -> PipelineStepState:
        self._set_state(
            PipelineStepState(
                is_running=True,
                action="run",
                workdir=str(config.workdir.path),
                messages=list(self.state.messages),
            )
        )
        try:
            from workflows.application.preprocessing_workflow import run_pipeline

            result = run_pipeline(config, log=self._handle_log, skip_grid=skip_grid)
            self._handle_log(tr("status_preprocess_done", "预处理流程完成"))
            self._set_state(
                PipelineStepState(
                    is_running=False,
                    action="run",
                    workdir=result.workdir,
                    messages=list(self.state.messages),
                    result=result,
                )
            )
        except Exception as exc:
            self._fail("run", str(exc))
        return self.state

    def apply_ww3_params(self, config: PipelineConfig) -> PipelineStepState:
        """Write WW3 namelists from config — does NOT re-run forcing or grid generation."""
        self._set_state(
            PipelineStepState(
                is_running=True,
                action="ww3",
                workdir=str(config.workdir.path),
                messages=list(self.state.messages),
            )
        )
        try:
            from workflows.infrastructure.forcing.use_cases import ScanWorkdirForcingUseCase
            from workflows.infrastructure.forcing.file_service import FileService
            from workflows.infrastructure.adapters.ww3_namelist_adapter import prepare_ww3_files
            from workflows.support.logging import CoreLogger

            logger = CoreLogger(callback=self._handle_log)
            file_service = FileService(logger=logger)
            files = ScanWorkdirForcingUseCase(file_service).execute(str(config.workdir.path))
            prepare_ww3_files(config, files, logger)
            self._handle_log(tr("ww3_params_applied", "✅ WW3 参数已应用"))
            self._set_state(
                PipelineStepState(
                    is_running=False,
                    action="ww3",
                    workdir=str(config.workdir.path),
                    messages=list(self.state.messages),
                )
            )
        except Exception as exc:
            self._fail("ww3", str(exc))
        return self.state

    def generate_grid(self, config: PipelineConfig) -> PipelineStepState:
        self._set_state(
            PipelineStepState(
                is_running=True,
                action="grid",
                workdir=str(config.workdir.path),
                messages=list(self.state.messages),
            )
        )
        try:
            from workflows.application.grid_preparation import run_generate_grid

            result = run_generate_grid(config, log=self._handle_log)
            self._set_state(
                PipelineStepState(
                    is_running=False,
                    action="grid",
                    workdir=result.workdir,
                    messages=list(self.state.messages),
                    result=result,
                )
            )
        except Exception as exc:
            self._fail("grid", str(exc))
        return self.state

    def load_wind_bounds(self, wind_path: str | Path) -> PipelineStepState:
        self._set_state(PipelineStepState(is_running=True, action="bounds"))
        try:
            from workflows.application.grid_tools import read_wind_bounds

            result = read_wind_bounds(wind_path, log=self._handle_log)
            self._set_state(
                PipelineStepState(
                    is_running=False,
                    action="bounds",
                    messages=list(self.state.messages),
                    result=result,
                )
            )
        except Exception as exc:
            self._fail("bounds", str(exc))
        return self.state

    def load_wind_time_range(self, wind_path: str | Path) -> PipelineStepState:
        self._set_state(PipelineStepState(is_running=True, action="time_range"))
        try:
            from workflows.application.grid_tools import read_wind_time_range

            result = read_wind_time_range(wind_path, log=self._handle_log)
            self._set_state(
                PipelineStepState(
                    is_running=False,
                    action="time_range",
                    messages=list(self.state.messages),
                    result=result,
                )
            )
        except Exception as exc:
            self._fail("time_range", str(exc))
        return self.state

    def render_region_map(self, config: PipelineConfig, output_path: str | Path) -> PipelineStepState:
        self._set_state(PipelineStepState(is_running=True, action="map", workdir=str(config.workdir.path)))
        try:
            from workflows.application.grid_tools import render_region_map

            result = render_region_map(config, output_path, log=self._handle_log)
            self._set_state(
                PipelineStepState(
                    is_running=False,
                    action="map",
                    workdir=result.images[0],
                    messages=list(self.state.messages),
                    result=result,
                )
            )
        except Exception as exc:
            self._fail("map", str(exc))
        return self.state

    def visualize_grid(self, config: PipelineConfig) -> PipelineStepState:
        self._set_state(PipelineStepState(is_running=True, action="visualize", workdir=str(config.workdir.path)))
        try:
            from workflows.application.grid_tools import visualize_grid

            result = visualize_grid(config, log=self._handle_log)
            self._set_state(
                PipelineStepState(
                    is_running=False,
                    action="visualize",
                    workdir=str(config.workdir.path),
                    messages=list(self.state.messages),
                    result=result,
                )
            )
        except Exception as exc:
            self._fail("visualize", str(exc))
        return self.state

    @staticmethod
    def scaled_nested_region(region: GridRegion, factor: float, *, expand: bool) -> GridRegion:
        from workflows.application.grid_tools import scale_nested_region

        return scale_nested_region(region, factor, expand=expand)

    def config_from_form(
        self,
        params_path: str | Path,
        *,
        workdir: str | Path,
        wind: str | Path,
        current: str | Path | None = None,
        level: str | Path | None = None,
        ice: str | Path | None = None,
        process_mode: str = "copy",
        auto_associate: bool = True,
        grid_overrides: dict | None = None,
        calc_mode: str | None = None,
        calc_points: list[dict] | None = None,
        calc_track_points: list[dict] | None = None,
        ww3_overrides: dict | None = None,
        ww3_grid_overrides: dict | None = None,
        slurm_overrides: dict | None = None,
        server_overrides: dict | None = None,
        validation_stage: str = "full",
    ) -> PipelineConfig:
        source_path = Path(params_path).expanduser().resolve()
        raw = self._form_raw(
            source_path,
            workdir=workdir,
            wind=wind,
            current=current,
            level=level,
            ice=ice,
            process_mode=process_mode,
            auto_associate=auto_associate,
            grid_overrides=grid_overrides,
            calc_mode=calc_mode,
            calc_points=calc_points,
            calc_track_points=calc_track_points,
            ww3_overrides=ww3_overrides,
            ww3_grid_overrides=ww3_grid_overrides,
            slurm_overrides=slurm_overrides,
            server_overrides=server_overrides,
        )
        return parse_pipeline_config(
            raw,
            base_dir=source_path.parent,
            source_path=source_path,
            validation_stage=validation_stage,
        )

    def save_form_to_params(
        self,
        params_path: str | Path,
        *,
        target_path: str | Path | None = None,
        grid_generated: bool | None = None,
        validation_stage: str = "grid",
        **overrides,
    ) -> Path:
        """将表单覆盖项合并进 params.yml 并写回磁盘，返回写入路径。

        覆盖项与 :meth:`config_from_form` 同名（workdir/wind/.../calc_points 等）；
        写回前先解析校验一遍，避免落盘非法配置。
        """
        source_path = Path(params_path).expanduser().resolve()
        raw = self._form_raw(source_path, **overrides)
        if grid_generated is not None:
            grid_raw = {**_as_dict(raw.get("grid"))}
            grid_raw["generated"] = bool(grid_generated)
            raw["grid"] = grid_raw
        parse_pipeline_config(
            raw, base_dir=source_path.parent, source_path=source_path, validation_stage=validation_stage
        )
        _normalize_params_scalar_types(raw)
        _strip_unstructured_dem_file(raw)
        destination = Path(target_path).expanduser().resolve() if target_path else source_path
        from workflows.application.configuration import _import_yaml

        yaml = _import_yaml()
        with destination.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(raw, handle, allow_unicode=True, sort_keys=False, default_flow_style=False)
        return destination

    def save_server_remote_dir(
        self,
        params_path: str | Path,
        remote_dir: str,
        *,
        target_path: str | Path | None = None,
    ) -> Path:
        """只更新 params.yml 的 ``server.remote_dir``，用于第六步路径输入框。"""
        source_path = Path(params_path).expanduser().resolve()
        raw = _load_raw_yaml(source_path)
        server = {**_as_dict(raw.get("server")), "remote_dir": str(remote_dir).strip()}
        raw["server"] = server
        parse_pipeline_config(
            raw, base_dir=source_path.parent, source_path=source_path, validation_stage="plot"
        )
        _normalize_params_scalar_types(raw)
        _strip_unstructured_dem_file(raw)
        destination = Path(target_path).expanduser().resolve() if target_path else source_path
        from workflows.application.configuration import _import_yaml

        yaml = _import_yaml()
        with destination.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(raw, handle, allow_unicode=True, sort_keys=False, default_flow_style=False)
        return destination

    def save_prepared_forcing_to_params(
        self,
        params_path: str | Path,
        files: Step1Files,
        *,
        target_path: str | Path | None = None,
    ) -> Path:
        """将 Step 1 转换后的强迫场路径写回 params.yml，并标记已转换完成。"""
        source_path = Path(params_path).expanduser().resolve()
        raw = _load_raw_yaml(source_path)
        forcing = {**_as_dict(raw.get("forcing"))}
        for field in ("wind", "current", "level", "ice"):
            path = getattr(files, field, None)
            if path:
                forcing[field] = str(path)
        forcing["converted"] = True
        raw["forcing"] = forcing
        parse_pipeline_config(
            raw, base_dir=source_path.parent, source_path=source_path, validation_stage="plot"
        )
        _normalize_params_scalar_types(raw)
        _strip_unstructured_dem_file(raw)
        destination = Path(target_path).expanduser().resolve() if target_path else source_path
        from workflows.application.configuration import _import_yaml

        yaml = _import_yaml()
        with destination.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(raw, handle, allow_unicode=True, sort_keys=False, default_flow_style=False)
        return destination

    def save_grid_generated_to_params(
        self,
        params_path: str | Path,
        generated: bool = True,
        *,
        target_path: str | Path | None = None,
    ) -> Path:
        """只更新 params.yml 的 ``grid.generated`` 状态。"""
        source_path = Path(params_path).expanduser().resolve()
        raw = _load_raw_yaml(source_path)
        grid = {**_as_dict(raw.get("grid"))}
        grid["generated"] = bool(generated)
        raw["grid"] = grid
        parse_pipeline_config(
            raw, base_dir=source_path.parent, source_path=source_path, validation_stage="grid"
        )
        _normalize_params_scalar_types(raw)
        _strip_unstructured_dem_file(raw)
        destination = Path(target_path).expanduser().resolve() if target_path else source_path
        from workflows.application.configuration import _import_yaml

        yaml = _import_yaml()
        with destination.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(raw, handle, allow_unicode=True, sort_keys=False, default_flow_style=False)
        return destination

    def _form_raw(
        self,
        source_path: Path,
        *,
        workdir: str | Path,
        wind: str | Path,
        current: str | Path | None = None,
        level: str | Path | None = None,
        ice: str | Path | None = None,
        process_mode: str = "copy",
        auto_associate: bool = True,
        grid_overrides: dict | None = None,
        calc_mode: str | None = None,
        calc_points: list[dict] | None = None,
        calc_track_points: list[dict] | None = None,
        ww3_overrides: dict | None = None,
        ww3_grid_overrides: dict | None = None,
        slurm_overrides: dict | None = None,
        server_overrides: dict | None = None,
    ) -> dict:
        """载入原始 yaml，先叠加 config.json 覆盖，再叠加表单覆盖，返回合并后的 raw。

        优先级：表单 > config.json > params.yml（表单覆盖在 config.json 之后套用）。
        """
        raw = _load_raw_yaml(source_path)
        _apply_config_overrides(raw)
        raw["workdir"] = {"path": str(workdir)}
        raw["forcing"] = {
            **(_as_dict(raw.get("forcing"))),
            "wind": str(wind),
            "current": str(current) if current else None,
            "level": str(level) if level else None,
            "ice": str(ice) if ice else None,
            "process_mode": process_mode,
            "auto_associate": auto_associate,
            "converted": bool(_as_dict(raw.get("forcing")).get("converted", False)),
        }
        if grid_overrides:
            grid_raw = {**_as_dict(raw.get("grid"))}
            for key, value in grid_overrides.items():
                if key in {"outer", "inner"} and isinstance(value, dict):
                    grid_raw[key] = {**_as_dict(grid_raw.get(key)), **value}
                elif key == "inner" and value is None:
                    grid_raw.pop("inner", None)
                else:
                    grid_raw[key] = value
            grid_raw["generated"] = bool(_as_dict(raw.get("grid")).get("generated", False))
            raw["grid"] = grid_raw
        if calc_mode or calc_points is not None or calc_track_points is not None:
            calc_raw = {**_as_dict(raw.get("calc"))}
            if calc_mode:
                calc_raw["mode"] = calc_mode
            if calc_points is not None:
                calc_raw["points"] = calc_points
            if calc_track_points is not None:
                calc_raw["track_points"] = calc_track_points
            raw["calc"] = calc_raw
        if ww3_overrides:
            raw["ww3"] = {**_as_dict(raw.get("ww3")), **ww3_overrides}
        if ww3_grid_overrides:
            # 第四步可见的频谱/时间步分组覆盖 ww3_grid（在 config.json 覆盖之后 → 表单优先）。
            raw["ww3_grid"] = {**_as_dict(raw.get("ww3_grid")), **ww3_grid_overrides}
        if slurm_overrides:
            raw["slurm"] = {**_as_dict(raw.get("slurm")), **slurm_overrides}
        if server_overrides:
            raw["server"] = {**_as_dict(raw.get("server")), **server_overrides}
        return raw

    def init_workdir_params(self, source: Path | None, target: Path, workdir: str) -> Path:
        """为新工作目录生成 params.yml：复制模板 + config.json 覆盖 + 写入 workdir.path。

        ``source`` 为模板（通常是当前 params.yml）；缺失或不可读时回退到仓库根 ``params.yml``，
        再缺失则用内置 ``EXAMPLE_YAML``。返回写入路径 ``target``。
        """
        from workflows.application.configuration import EXAMPLE_YAML, _import_yaml

        yaml = _import_yaml()
        raw: dict = {}
        candidates = [source, _repo_params_path()]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                try:
                    raw = _load_raw_yaml(Path(candidate))
                    break
                except Exception:
                    raw = {}
        if not raw:
            raw = yaml.safe_load(EXAMPLE_YAML) or {}
        _apply_config_overrides(raw)
        raw["workdir"] = {"path": str(workdir)}
        # 新工作目录：强迫场文件路径清空，待用户重新选择。
        forcing = dict(raw.get("forcing") or {})
        for field in ("wind", "current", "level", "ice"):
            forcing[field] = None
        forcing["converted"] = False
        raw["forcing"] = forcing
        grid = dict(raw.get("grid") or {})
        grid["generated"] = False
        raw["grid"] = grid
        _normalize_params_scalar_types(raw)
        _strip_unstructured_dem_file(raw)
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(raw, handle, allow_unicode=True, sort_keys=False, default_flow_style=False)
        return target

    def _fail(self, action: str, message: str) -> None:
        self._handle_log(message)
        self._set_state(
            PipelineStepState(
                is_running=False,
                action=action,
                workdir=self.state.workdir,
                messages=list(self.state.messages),
                error=message,
            )
        )

    def _handle_log(self, message: str) -> None:
        text = str(message)
        self.state.messages.append(text)
        if self._on_log is not None:
            self._on_log(text)

    def _set_state(self, state: PipelineStepState) -> None:
        self.state = state
        if self._on_state_change is not None:
            self._on_state_change(state)


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


_INT_PARAM_PATHS = {
    "grid.smc.n_levels",
    "grid.smc.msea",
    "grid.unstructured.nwav",
    "grid.unstructured.edge_segments",
    "ww3.compute_precision",
    "ww3.output_precision",
    "ww3.inner_compute_precision",
    "ww3.inner_output_precision",
    "ww3_grid.SPECTRUM%NK",
    "ww3_grid.SPECTRUM%NTH",
    "ww3_grid.TIMESTEPS%DTMAX",
    "ww3_grid.TIMESTEPS%DTXY",
    "ww3_grid.TIMESTEPS%DTKTH",
    "ww3_grid.TIMESTEPS%DTMIN",
    "slurm.nodes",
    "slurm.cores",
    "server.port",
    "plot.wave_maps.dpi",
}

_NUMERIC_PARAM_PATHS = {
    "grid.nested_contraction_coefficient",
    "grid.structured.min_dist",
    "grid.structured.cut_off",
    "grid.structured.lim_bathy",
    "grid.structured.lim_val",
    "grid.structured.split_lim",
    "grid.structured.lake_tol",
    "grid.smc.wlevel",
    "grid.smc.depmin",
    "grid.smc.dshalw",
    "grid.unstructured.hmax",
    "grid.unstructured.hshr",
    "grid.unstructured.dhdx",
    "grid.unstructured.deep_ocean_threshold_m",
    "grid.unstructured.margin_deg",
    "ww3_grid.SPECTRUM%XFR",
    "ww3_grid.SPECTRUM%FREQ1",
    "ww3_grid.GRID%ZLIM",
    "ww3_grid.GRID%DMIN",
    "plot.wave_maps.time_step_hours",
    "plot.spectrum.time_step_hours",
    "plot.spectrum.energy_threshold",
    "plot.jason3.max_dist_deg",
    "plot.jason3.time_window_hours",
}

_REGION_KEYS = ("outer", "inner")


def _normalize_params_scalar_types(raw: dict) -> None:
    for key in _REGION_KEYS:
        _coerce_region(_as_dict(_as_dict(raw.get("grid")).get(key)))
    for path in _INT_PARAM_PATHS:
        _coerce_dotted(raw, path, integer=True)
    for path in _NUMERIC_PARAM_PATHS:
        _coerce_dotted(raw, path)
    _coerce_nested_numeric(_as_dict(_as_dict(_as_dict(raw.get("grid")).get("smc")).get("options")))
    _coerce_nested_numeric(_as_dict(_as_dict(_as_dict(raw.get("grid")).get("unstructured")).get("options")))
    _coerce_points(_as_dict(raw.get("calc")).get("points"))
    _coerce_points(_as_dict(raw.get("calc")).get("track_points"))
    wave_maps = _as_dict(_as_dict(raw.get("plot")).get("wave_maps"))
    figsize = wave_maps.get("figsize")
    if isinstance(figsize, list):
        wave_maps["figsize"] = [_coerce_number(item) for item in figsize]


def _coerce_region(region: dict) -> None:
    if not region:
        return
    for key in ("dx", "dy"):
        if key in region:
            region[key] = _coerce_number(region[key])
    for key in ("lon", "lat"):
        value = region.get(key)
        if isinstance(value, list):
            region[key] = [_coerce_number(item) for item in value]


def _coerce_dotted(raw: dict, dotted: str, *, integer: bool = False) -> None:
    cur = raw
    parts = dotted.split(".")
    for part in parts[:-1]:
        cur = cur.get(part) if isinstance(cur, dict) else None
        if not isinstance(cur, dict):
            return
    key = parts[-1]
    if key in cur and cur[key] is not None:
        cur[key] = _coerce_int(cur[key]) if integer else _coerce_number(cur[key])


def _coerce_nested_numeric(value: object) -> object:
    if isinstance(value, dict):
        for key, item in list(value.items()):
            value[key] = _coerce_nested_numeric(item)
        return value
    if isinstance(value, list):
        return [_coerce_nested_numeric(item) for item in value]
    return _coerce_number(value)


def _coerce_points(points: object) -> None:
    if not isinstance(points, list):
        return
    for point in points:
        if not isinstance(point, dict):
            continue
        for key in ("lon", "lat"):
            if key in point:
                point[key] = _coerce_number(point[key])


def _coerce_int(value: object) -> object:
    if isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"[+-]?\d+", text):
            return int(text)
        if re.fullmatch(r"[+-]?\d+\.0+", text):
            return int(float(text))
    return value


def _coerce_number(value: object) -> object:
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return value
    if not isinstance(value, str):
        return value
    text = value.strip()
    if re.fullmatch(r"[+-]?\d+", text):
        return int(text)
    if re.fullmatch(r"[+-]?(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?", text) or re.fullmatch(
        r"[+-]?\d+[eE][+-]?\d+",
        text,
    ):
        return float(text)
    return value


def _strip_unstructured_dem_file(raw: dict) -> None:
    """Keep DEM selection in gridgen defaults instead of exposing it in params.yml."""
    grid = _as_dict(raw.get("grid"))
    unstructured = _as_dict(grid.get("unstructured"))
    options = _as_dict(unstructured.get("options"))
    data = _as_dict(options.get("data"))
    data.pop("dem_file", None)
    if not data and "data" in options:
        options.pop("data", None)


# config.json（设置页）键 -> params.yml 嵌套路径（点号分隔）。仅在 config.json 值非空时套用。
# 不含经纬度边界等 per-run 项（由 params.yml/表单负责）。
_CONFIG_TO_PARAMS = {
    "DX": "grid.outer.dx",
    "DY": "grid.outer.dy",
    "GRIDGEN_VERSION": "grid.gridgen_version",
    "REFERENCE_DATA_PATH": "grid.reference_data_path",
    "NESTED_CONTRACTION_COEFFICIENT": "grid.nested_contraction_coefficient",
    "BATHYMETRY": "grid.structured.bathymetry",
    "COASTLINE_PRECISION": "grid.structured.coastline_precision",
    "MIN_DIST": "grid.structured.min_dist",
    "CUT_OFF": "grid.structured.cut_off",
    "LIM_BATHY": "grid.structured.lim_bathy",
    "LIM_VAL": "grid.structured.lim_val",
    "SPLIT_LIM": "grid.structured.split_lim",
    "LAKE_TOL": "grid.structured.lake_tol",
    "COMPUTE_PRECISION": "ww3.compute_precision",
    "OUTPUT_PRECISION": "ww3.output_precision",
    "FILE_SPLIT": "ww3.file_split",
    "FREQ_INC": "ww3_grid.SPECTRUM%XFR",
    "FREQ_START": "ww3_grid.SPECTRUM%FREQ1",
    "FREQ_NUM": "ww3_grid.SPECTRUM%NK",
    "DIR_NUM": "ww3_grid.SPECTRUM%NTH",
    "DTMAX": "ww3_grid.TIMESTEPS%DTMAX",
    "DTXY": "ww3_grid.TIMESTEPS%DTXY",
    "DTKTH": "ww3_grid.TIMESTEPS%DTKTH",
    "DTMIN": "ww3_grid.TIMESTEPS%DTMIN",
    "GRID_ZLIM": "ww3_grid.GRID%ZLIM",
    "GRID_DMIN": "ww3_grid.GRID%DMIN",
    "KERNEL_NUM": "slurm.cores",
    "NODE_NUM": "slurm.nodes",
    "DEFAULT_CPU": "slurm.cpu",
    "SERVER_HOST": "server.host",
    "SERVER_PORT": "server.port",
    "SERVER_USER": "server.user",
    "SERVER_PASSWORD": "server.password",
    "SERVER_PATH": "server.remote_dir",
}


def _apply_config_overrides(raw: dict) -> None:
    """用 config.json（设置页）的非空值覆盖 raw 中相同参数（就地修改）。

    优先级中位于 params.yml 之上、表单之下：本函数在表单覆盖之前调用。
    """
    from workflows.infrastructure import runtime_config

    try:
        app = runtime_config.load_config()
    except Exception:
        return
    for cfg_key, dotted in _CONFIG_TO_PARAMS.items():
        value = app.get(cfg_key)
        if value is None or str(value) == "":
            continue
        parts = dotted.split(".")
        cur = raw
        for part in parts[:-1]:
            nxt = cur.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[part] = nxt
            cur = nxt
        cur[parts[-1]] = value


def _repo_params_path() -> Path:
    """仓库根 params.yml 路径（作为新工作目录 params 的回退模板）。"""
    return Path(__file__).resolve().parents[3] / "params.yml"


def _load_raw_yaml(path: Path) -> dict:
    from workflows.application.configuration import _import_yaml

    yaml = _import_yaml()
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ConfigError("参数文件顶层必须是对象")
    return raw
