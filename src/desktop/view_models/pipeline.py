"""Desktop adapter for validate / run pipeline workflow entrypoints."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import posixpath
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
from workflows.infrastructure.runtime_config import _dump_yaml_with_comments
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
    """Bridge from desktop actions to the same workflows used by run.py."""

    def __init__(
        self,
        *,
        on_log: Optional[LogCallback] = None,
        on_state_change: Optional[StateCallback] = None,
    ) -> None:
        self._on_log = on_log
        self._on_state_change = on_state_change
        self.state = PipelineStepState()
        self._run_log_path: Optional[Path] = None

    def load_config(self, params_path: str | Path, *, validation_stage: str = "full") -> PipelineConfig:
        # [EN] Load workdir params.yml; empty values auto-fall-back to root params.yml defaults.
        # [EN] If workdir params.yml cannot be parsed, fail fast instead of falling back.
        """加载工作目录 params.yml，空值自动回退到根 params.yml 默认值。

        若工作目录 params.yml 无法解析（YAML 语法错误或结构异常），立即报错。
        """
        from workflows.application.configuration import _import_yaml, parse_pipeline_config

        path = Path(params_path).expanduser().resolve()
        yaml = _import_yaml()

        try:
            with path.open("r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
        except Exception as exc:
            raise ConfigError(
                tr("params_parse_failed", "参数文件无法读取或解析：{path}（{error}）").format(
                    path=path,
                    error=exc,
                )
            ) from exc
        if not isinstance(loaded, dict):
            raise ConfigError(tr("params_top_level_invalid", "参数文件顶层必须是对象：{path}").format(path=path))
        workdir_raw: dict = loaded

        # [EN] Fill empty values in workdir with root params.yml defaults
        # 用根 params.yml 默认值填充工作目录中的空值
        root_path = _repo_params_path()
        if root_path.is_file():
            with root_path.open("r", encoding="utf-8") as f:
                root_raw = yaml.safe_load(f) or {}
            workdir_raw = _deep_merge_defaults(root_raw, workdir_raw)

        return parse_pipeline_config(
            workdir_raw, base_dir=path.parent, source_path=path, validation_stage=validation_stage
        )

    def validate(self, config: PipelineConfig, *, stage: str = "full") -> None:
        validate_pipeline_config(config, stage=stage)

    def validate_file(self, params_path: str | Path, *, stage: str = "full") -> PipelineStepState:
        self._set_state(PipelineStepState(is_running=True, action="validate"))
        try:
            config = self.load_config(params_path, validation_stage=stage)
            self.validate(config, stage=stage)
            self._handle_log(tr("params_validation_ok", "✅ 参数校验通过：{path}").format(path=params_path))
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
            self._handle_log(tr("status_preprocess_done", "✅ 预处理流程完成"))
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
            files = ScanWorkdirForcingUseCase(file_service).execute(
                str(config.workdir.path),
                auto_associate=bool(config.forcing.auto_associate),
            )
            prepare_ww3_files(config, files, logger, update_server_script=False)
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

    def apply_server_script(self, config: PipelineConfig) -> PipelineStepState:
        """Update only the workdir ``server.sh`` from Slurm/ST settings."""
        self._set_state(
            PipelineStepState(
                is_running=True,
                action="server_sh",
                workdir=str(config.workdir.path),
                messages=list(self.state.messages),
            )
        )
        try:
            from workflows.infrastructure.adapters.ww3_namelist_adapter import update_server_script
            from workflows.support.logging import CoreLogger

            logger = CoreLogger(callback=self._handle_log)
            update_server_script(config, logger)
            self._set_state(
                PipelineStepState(
                    is_running=False,
                    action="server_sh",
                    workdir=str(config.workdir.path),
                    messages=list(self.state.messages),
                )
            )
        except Exception as exc:
            self._fail("server_sh", str(exc))
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

    def render_forcing_region_map(self, regions: list, labels: list[str], output_path: str | Path) -> PipelineStepState:
        self._set_state(PipelineStepState(is_running=True, action="map"))
        try:
            from workflows.application.grid_tools import render_forcing_region_map

            result = render_forcing_region_map(regions, labels, output_path, log=self._handle_log)
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
        crop_time_range: list[str] | None = None,
        crop_bbox: list[float] | None = None,
        grid_overrides: dict | None = None,
        calc_mode: str | None = None,
        calc_points: list[dict] | None = None,
        calc_track_points: list[dict] | None = None,
        ww3_overrides: dict | None = None,
        restart_overrides: dict | None = None,
        ww3_grid_overrides: dict | None = None,
        plot_overrides: dict | None = None,
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
            crop_time_range=crop_time_range,
            crop_bbox=crop_bbox,
            grid_overrides=grid_overrides,
            calc_mode=calc_mode,
            calc_points=calc_points,
            calc_track_points=calc_track_points,
            ww3_overrides=ww3_overrides,
            ww3_grid_overrides=ww3_grid_overrides,
            plot_overrides=plot_overrides,
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
        validation_stage: str = "grid",
        **overrides,
    ) -> Path:
        # [EN] Merge form overrides into params.yml and write back to disk, returning the written path.
        # [EN] Override names match :meth:`config_from_form` (workdir/wind/.../calc_points etc.);
        # [EN] parsing and validation are done before writing to avoid persisting invalid configs.
        """将表单覆盖项合并进 params.yml 并写回磁盘，返回写入路径。

        覆盖项与 :meth:`config_from_form` 同名（workdir/wind/.../calc_points 等）；
        写回前先解析校验一遍，避免落盘非法配置。
        """
        source_path = Path(params_path).expanduser().resolve()
        raw = self._form_raw(source_path, **overrides)
        # [EN] Auto-fill server.remote_dir when empty:
        # default_remote_dir + workdir name, persisted so downstream
        # reads see the resolved value instead of relying on runtime fallback.
        server = raw.get("server") or {}
        if not (server.get("remote_dir") or "").strip():
            base = (server.get("default_remote_dir") or "").strip()
            workdir_path = (raw.get("workdir") or {}).get("path") or ""
            workdir_name = Path(workdir_path).name if workdir_path else ""
            if base and workdir_name:
                tail = posixpath.basename(base.rstrip("/"))
                server["remote_dir"] = base.rstrip("/") if tail == workdir_name else posixpath.join(base.rstrip("/"), workdir_name)
                raw["server"] = server
        parse_pipeline_config(
            raw, base_dir=source_path.parent, source_path=source_path, validation_stage=validation_stage
        )
        _normalize_params_scalar_types(raw)
        _strip_unstructured_dem_file(raw)
        destination = Path(target_path).expanduser().resolve() if target_path else source_path
        from workflows.application.configuration import _import_yaml

        yaml = _import_yaml()
        with destination.open("w", encoding="utf-8") as handle:
            handle.write(_dump_yaml_with_comments(raw, yaml))
        return destination

    def save_server_remote_dir(
        self,
        params_path: str | Path,
        remote_dir: str,
        *,
        target_path: str | Path | None = None,
    ) -> Path:
        # [EN] Only update ``server.remote_dir`` in params.yml, used by step 6 path input.
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
            handle.write(_dump_yaml_with_comments(raw, yaml))
        return destination

    def sync_from_root(self, workdir_params_path: str | Path) -> Path:
        # [EN] Sync root params.yml template to workdir (overwrite), preserving case-specific fields.
        # [EN] Preserved fields: ``workdir.path``, ``forcing`` file paths (wind/current/level/ice).
        # [EN] All other parameters are overwritten from root params.yml to ensure latest defaults take effect.
        """将根 params.yml 模板同步到工作目录（覆盖），保留 case 专属字段。

        保留的字段：``workdir.path``、``forcing`` 的文件路径（wind/current/level/ice）。
        其余参数全部从根 params.yml 覆盖，确保设置页最新默认值生效。
        """
        from workflows.application.configuration import _import_yaml

        dest = Path(workdir_params_path).expanduser().resolve()
        root_path = _repo_params_path()

        yaml = _import_yaml()
        # [EN] 1) Read current workdir, preserve case-specific fields
        # 1) 读当前工作目录，保存 case 专属字段
        case_fields: dict = {}
        if dest.is_file():
            try:
                old = _load_raw_yaml(dest)
                case_fields["workdir"] = old.get("workdir", {})
                case_fields["forcing"] = {
                    k: old.get("forcing", {}).get(k)
                    for k in (
                        "wind",
                        "current",
                        "level",
                        "ice",
                        "process_mode",
                        "auto_associate",
                        "crop_time_range",
                        "crop_bbox",
                    )
                }
                # [EN] Preserve ww3 dates and calc points (case-specific values set by user in form)
                # 保留 ww3 日期和 calc 点位（用户在表单中设置的 case 专属值）
                case_fields["ww3_dates"] = {
                    k: old.get("ww3", {}).get(k)
                    for k in ("start_date", "end_date")
                    if old.get("ww3", {}).get(k)
                }
                old_ww3_version = (old.get("ww3") or {}).get("version")
                if old_ww3_version:
                    case_fields["ww3_version"] = old_ww3_version
                case_fields["calc"] = old.get("calc", {})
                # [EN] Preserve per-case server.remote_dir (custom value written by step 6 input)
                # 保留 per-case 的 server.remote_dir（第六步输入框写入的自定义值）
                old_server = old.get("server", {}) or {}
                if old_server.get("remote_dir"):
                    case_fields["server_remote_dir"] = old_server["remote_dir"]
            except Exception:
                pass

        # [EN] 2) Read root params.yml
        # 2) 读根 params.yml
        raw = _load_raw_yaml(root_path) if root_path.is_file() else {}

        # [EN] 3) Restore case-specific fields
        # 3) 恢复 case 专属字段
        if "workdir" in case_fields:
            raw["workdir"] = case_fields["workdir"]
        if "forcing" in case_fields:
            forcing = dict(raw.get("forcing") or {})
            forcing.update(case_fields["forcing"])
            raw["forcing"] = forcing
        if case_fields.get("ww3_dates"):
            ww3 = dict(raw.get("ww3") or {})
            ww3.update(case_fields["ww3_dates"])
            raw["ww3"] = ww3
        if case_fields.get("ww3_version"):
            ww3 = dict(raw.get("ww3") or {})
            ww3["version"] = case_fields["ww3_version"]
            raw["ww3"] = ww3
        if "calc" in case_fields:
            raw["calc"] = case_fields["calc"]
        if "server_remote_dir" in case_fields:
            server = dict(raw.get("server") or {})
            server["remote_dir"] = case_fields["server_remote_dir"]
            raw["server"] = server

        _normalize_params_scalar_types(raw)
        _strip_unstructured_dem_file(raw)
        with dest.open("w", encoding="utf-8") as handle:
            handle.write(_dump_yaml_with_comments(raw))
        return dest

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
        crop_time_range: list[str] | None = None,
        crop_bbox: list[float] | None = None,
        grid_overrides: dict | None = None,
        calc_mode: str | None = None,
        calc_points: list[dict] | None = None,
        calc_track_points: list[dict] | None = None,
        ww3_overrides: dict | None = None,
        ww3_grid_overrides: dict | None = None,
        plot_overrides: dict | None = None,
        slurm_overrides: dict | None = None,
        server_overrides: dict | None = None,
    ) -> dict:
        # [EN] Load raw yaml, overlay form overrides, return merged raw.
        # [EN] Priority: form > params.yml.
        """载入原始 yaml，叠加表单覆盖，返回合并后的 raw。

        优先级：表单 > params.yml。
        """
        raw = _load_raw_yaml(source_path)
        raw["workdir"] = {"path": str(workdir)}
        raw["forcing"] = {
            **(_as_dict(raw.get("forcing"))),
            "wind": str(wind),
            "current": str(current) if current else None,
            "level": str(level) if level else None,
            "ice": str(ice) if ice else None,
            "process_mode": process_mode,
            "auto_associate": auto_associate,
            "crop_time_range": crop_time_range or [],
            "crop_bbox": crop_bbox or [],
        }
        if grid_overrides:
            grid_raw = {**_as_dict(raw.get("grid"))}
            structured_raw = {**_as_dict(grid_raw.get("structured"))}
            nested_raw = {**_as_dict(structured_raw.get("nested"))}
            # GUI 直接回传 levels 列表（level0…levelN，粗 → 细）
            levels = None
            for key, value in grid_overrides.items():
                if key == "levels" and isinstance(value, list):
                    levels = [_as_dict(lv) for lv in value]
                elif key in {"unstructured", "smc"} and isinstance(value, dict):
                    grid_raw[key] = {**_as_dict(grid_raw.get(key)), **value}
                else:
                    grid_raw[key] = value
            if levels:
                nested_raw["levels"] = levels
                nested_raw.pop("outer", None)  # 清掉旧键，避免与 levels 并存
                nested_raw.pop("inner", None)
                # level0 边界同步为主域 grid.lon / grid.lat
                if levels[0].get("lon") is not None:
                    grid_raw["lon"] = levels[0]["lon"]
                if levels[0].get("lat") is not None:
                    grid_raw["lat"] = levels[0]["lat"]
            structured_raw["nested"] = nested_raw
            grid_raw["structured"] = structured_raw
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
        if restart_overrides:
            raw["restart"] = {**_as_dict(raw.get("restart")), **restart_overrides}
        if ww3_grid_overrides:
            # [EN] Step 4 visible spectrum/timestep groups override ww3_grid (after config.json overrides -> form takes priority).
            # 第四步可见的频谱/时间步分组覆盖 ww3_grid（在 config.json 覆盖之后 → 表单优先）。
            raw["ww3_grid"] = {**_as_dict(raw.get("ww3_grid")), **ww3_grid_overrides}
        if plot_overrides:
            plot_raw = {**_as_dict(raw.get("plot"))}
            for section, values in plot_overrides.items():
                if isinstance(values, dict):
                    plot_raw[section] = {**_as_dict(plot_raw.get(section)), **values}
                else:
                    plot_raw[section] = values
            raw["plot"] = plot_raw
        if slurm_overrides:
            from workflows.application.configuration import normalize_slurm_section

            raw["slurm"] = normalize_slurm_section(
                {**_as_dict(raw.get("slurm")), **slurm_overrides}
            )
        if server_overrides:
            raw["server"] = {**_as_dict(raw.get("server")), **server_overrides}
        return raw

    def init_workdir_params(self, target: Path, workdir: str) -> Path:
        # [EN] Generate params.yml for a new workdir: always copy repository root
        # ``params.yml`` (never the previously loaded workdir file), then clear
        # case-specific paths via regex substitution.
        """为新工作目录生成 params.yml：始终从仓库根 params.yml 复制模板，再清空案例专属字段。"""
        import re
        import shutil

        template = _repo_params_path()
        if not Path(template).is_file():
            from workflows.application.configuration import EXAMPLE_YAML
            target = Path(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(EXAMPLE_YAML, encoding="utf-8")
            return target

        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        # [EN] Use copyfile instead of copy2 to avoid [Errno 22] on external disks
        # (exFAT/NTFS/FAT32 may not support metadata/extended-attribute copying).
        shutil.copyfile(str(template), str(target))

        content = target.read_text(encoding="utf-8")

        # [EN] Only modify specific fields via regex; preserve everything else as-is.
        # 仅通过正则修改特定字段，其余内容（包括 desktop 段、注释、顺序）保持不变。
        content = re.sub(
            r"(^workdir:\s*\n  path:\s*).*",
            r"\g<1>" + str(workdir).replace("\\", "\\\\"),
            content, count=1, flags=re.MULTILINE,
        )
        for field in ("wind", "current", "level", "ice"):
            content = re.sub(
                rf"(^  {field}:\s*).*",
                rf"\g<1>",
                content, count=1, flags=re.MULTILINE,
            )
        for field in ("start_date", "end_date"):
            content = re.sub(
                rf"(^  {field}:\s*).*",
                rf"\g<1>",
                content, count=1, flags=re.MULTILINE,
            )
        content = re.sub(
            r"(^  remote_dir:\s*).*",
            r"\g<1>",
            content, count=1, flags=re.MULTILINE,
        )

        target.write_text(content, encoding="utf-8")
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
        if self._run_log_path is not None:
            try:
                with self._run_log_path.open("a", encoding="utf-8") as fh:
                    fh.write(text + "\n")
            except Exception:
                pass
        if self._on_log is not None:
            self._on_log(text)

    def _set_state(self, state: PipelineStepState) -> None:
        self.state = state
        # 应用操作日志追加到工作目录的 run.log；成败标记 success / fail（空文件）
        # 只由 local.sh / server.sh 创建，应用层不碰。
        if state.is_running and state.workdir:
            self._begin_run_log(state.workdir)
        if self._on_state_change is not None:
            self._on_state_change(state)

    def _begin_run_log(self, workdir: str) -> None:
        """应用操作日志追加到工作目录的 run.log（不存在则创建，不截断）。
        成败标记文件 success / fail 只由 local.sh / server.sh 创建，应用层不碰。"""
        self._run_log_path = None
        try:
            d = Path(workdir)
            if not d.is_dir():
                return
            run_log = d / "run.log"
            if not run_log.exists():
                run_log.touch()
            self._run_log_path = run_log
        except Exception:
            self._run_log_path = None


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


_INT_PARAM_PATHS = {
    "grid.smc.n_levels",
    "grid.smc.msea",
    "grid.unstructured.nwav",
    "grid.unstructured.edge_segments",
    "ww3.output_step",
    "ww3_grid.SPECTRUM%NK",
    "ww3_grid.SPECTRUM%NTH",
    "ww3_grid.TIMESTEPS%DTMAX",
    "ww3_grid.TIMESTEPS%DTXY",
    "ww3_grid.TIMESTEPS%DTKTH",
    "ww3_grid.TIMESTEPS%DTMIN",
    "slurm.nodes",
    "slurm.cores",
    "slurm.partition",
    "server.port",
    "plot.wave_maps.dpi",
}

_NUMERIC_PARAM_PATHS = {
    "grid.structured.nested.nested_contraction_coefficient",
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
    "plot.wave_maps.time_step_hours",
    "plot.spectrum.time_step_hours",
    "plot.spectrum.energy_threshold",
    "plot.jason3.max_dist_deg",
    "plot.jason3.time_window_hours",
}

def _normalize_params_scalar_types(raw: dict) -> None:
    grid = _as_dict(raw.get("grid"))
    nested = _as_dict(_as_dict(grid.get("structured")).get("nested"))
    for region in (nested.get("levels") or []):  # 嵌套各层
        _coerce_region(_as_dict(region))
    for key in ("lon", "lat"):  # 主域 grid.lon / grid.lat
        seq = grid.get(key)
        if isinstance(seq, list):
            grid[key] = [_coerce_number(item) for item in seq]
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



def _repo_params_path() -> Path:
    # [EN] Repository root params.yml path (used as fallback template for new workdir params).
    """仓库根 params.yml 路径（作为新工作目录 params 的回退模板）。"""
    return Path(__file__).resolve().parents[3] / "params.yml"


def _deep_merge_defaults(defaults: dict, overrides: dict) -> dict:
    # [EN] Deep merge: defaults as base, non-None values in overrides replace corresponding positions.
    #
    # [EN] - overrides value is ``None`` -> keep defaults value
    # [EN] - overrides value is dict -> recursive merge
    # [EN] - overrides value is other non-None -> direct override
    # [EN] - keys not in defaults -> keep overrides value
    """深度合并：以 defaults 为底，overrides 中非 None 的值覆盖对应位置。

    - overrides 中值为 ``None`` → 保留 defaults 的值
    - overrides 中值为 dict → 递归合并
    - overrides 中值为其它非 None → 直接覆盖
    - defaults 中没有的键 → 保留 overrides 的值
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


def _load_raw_yaml(path: Path) -> dict:
    from workflows.application.configuration import _import_yaml

    yaml = _import_yaml()
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ConfigError("参数文件顶层必须是对象")
    return raw


# ── YAML comment injection is now in runtime_config ─────────────────────────
# _YAML_COMMENTS and _dump_yaml_with_comments moved to
# workflows.infrastructure.runtime_config to be shared by all YAML writers.
