"""Analyze and merge NetCDF forcing files without depending on Qt."""

from __future__ import annotations

import os
import tempfile
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from workflows.infrastructure.forcing.variable_detector import VariableDetector
from workflows.support.translations import tr


_EPOCH_UNITS = "seconds since 1970-01-01 00:00:00"
_EPOCH_CALENDAR = "standard"


@dataclass(frozen=True)
class NetCDFFileInfo:
    """A compact summary used by the desktop merge table."""

    path: str
    filename: str
    lat_range: str
    lon_range: str
    time_range: str
    variables: str
    has_time: bool
    forcing_fields: str = ""
    error: str = ""


@dataclass(frozen=True)
class MergeAnalysis:
    """Result of validating a proposed forcing-file merge."""

    files: tuple[NetCDFFileInfo, ...]
    strategy: str
    errors: tuple[str, ...]
    time_steps: int = 0

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass
class _GroupPlan:
    paths: list[str]
    data_variables: tuple[str, ...]
    times: Any
    time_sources: list[tuple[str, int]]
    time_names: dict[str, str]


@dataclass
class _MergePlan:
    groups: list[_GroupPlan]
    analysis: MergeAnalysis


def _imports():
    try:
        import netCDF4 as nc
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            tr("tools_merge_need_netcdf4", "合并强迫场需要 netCDF4，请安装：pip install netCDF4")
        ) from exc
    return nc, np


def _find_coord(ds, candidates: tuple[str, ...]):
    for name in candidates:
        if name in ds.variables:
            return ds.variables[name]
    return None


def _time_name(ds) -> str | None:
    """Return the CF time coordinate/dimension name, preferring literal ``time``."""

    if "time" in ds.dimensions and "time" in ds.variables:
        return "time"
    for name, var in ds.variables.items():
        if (
            len(var.dimensions) == 1
            and var.dimensions[0] == name
            and name in ds.dimensions
            and (
                str(getattr(var, "standard_name", "")).lower() == "time"
                or str(getattr(var, "axis", "")).upper() == "T"
            )
        ):
            return name
    return None


def _format_range(var, suffix: str = "") -> str:
    _, np = _imports()
    try:
        arr = np.ma.asarray(var[:])
        return f"{float(arr.min()):.2f}{suffix} ~ {float(arr.max()):.2f}{suffix}"
    except Exception:
        return "-"


def _canonical_times(time_var):
    nc, np = _imports()
    units = getattr(time_var, "units", "")
    if not units:
        raise ValueError(tr("tools_merge_time_units_missing", "time 变量缺少 units 属性"))
    calendar = getattr(time_var, "calendar", "standard")
    try:
        dates = nc.num2date(time_var[:], units=units, calendar=calendar)
        values = nc.date2num(dates, units=_EPOCH_UNITS, calendar=_EPOCH_CALENDAR)
    except Exception as exc:
        raise ValueError(
            tr("tools_merge_time_convert_failed", "无法转换时间轴：{error}").format(error=exc)
        ) from exc
    return np.asarray(values, dtype="float64")


def _format_time_range(time_var) -> str:
    nc, _ = _imports()
    try:
        values = nc.num2date(
            time_var[:],
            units=time_var.units,
            calendar=getattr(time_var, "calendar", "standard"),
        )
        if len(values) == 0:
            return "-"
        first, last = str(values[0])[:19], str(values[-1])[:19]
        return first if first == last else f"{first} ~ {last}"
    except Exception:
        return "-"


def _data_variable_names(ds) -> tuple[str, ...]:
    return tuple(sorted(name for name in ds.variables if name not in ds.dimensions))


def read_netcdf_info(path: str) -> NetCDFFileInfo:
    """Read a compact summary without loading data variables."""

    nc, _ = _imports()
    filename = os.path.basename(path)
    try:
        with nc.Dataset(path, "r") as ds:
            time_name = _time_name(ds)
            time_var = ds.variables.get(time_name) if time_name else None
            fields = VariableDetector.detect_forcing_fields(path)
            return NetCDFFileInfo(
                path=os.path.abspath(path),
                filename=filename,
                lat_range=_format_range(_find_coord(ds, ("latitude", "lat", "y")), "°")
                if _find_coord(ds, ("latitude", "lat", "y")) is not None else "-",
                lon_range=_format_range(_find_coord(ds, ("longitude", "lon", "x")), "°")
                if _find_coord(ds, ("longitude", "lon", "x")) is not None else "-",
                time_range=_format_time_range(time_var) if time_var is not None else "-",
                variables=", ".join(_data_variable_names(ds)) or "-",
                has_time=time_var is not None,
                forcing_fields=", ".join(fields) or "-",
            )
    except Exception as exc:
        return NetCDFFileInfo(
            path=os.path.abspath(path),
            filename=filename,
            lat_range="-",
            lon_range="-",
            time_range="-",
            variables="-",
            has_time=False,
            forcing_fields="-",
            error=str(exc),
        )


def _arrays_equal(left, right) -> bool:
    _, np = _imports()
    try:
        return bool(np.ma.allequal(np.ma.asarray(left), np.ma.asarray(right)))
    except Exception:
        return False


def _normalized_dimensions(var, time_name: str) -> tuple[str, ...]:
    return tuple("time" if name == time_name else name for name in var.dimensions)


def _variable_definition(var, time_name: str) -> tuple:
    attrs = {
        name: var.getncattr(name)
        for name in var.ncattrs()
        if name != "_FillValue"
    }
    return str(var.dtype), _normalized_dimensions(var, time_name), attrs


def _validate_group(paths: list[str], data_variables: tuple[str, ...]) -> _GroupPlan:
    nc, np = _imports()
    datasets = [nc.Dataset(path, "r") for path in paths]
    try:
        first = datasets[0]
        first_time_name = _time_name(first)
        if first_time_name is None:
            raise ValueError(
                tr("tools_merge_no_time_dim", "文件缺少 time 维度：{path}").format(
                    path=os.path.basename(paths[0])
                )
            )
        time_names: dict[str, str] = {}
        for ds, path in zip(datasets, paths):
            time_name = _time_name(ds)
            if time_name is None:
                raise ValueError(
                    tr("tools_merge_no_time_dim", "文件缺少 time 维度：{path}").format(
                        path=os.path.basename(path)
                    )
                )
            time_names[path] = time_name
            if _data_variable_names(ds) != data_variables:
                raise ValueError(tr("tools_merge_variable_mismatch", "待拼接文件的数据变量不一致"))

            for dim_name, dim in first.dimensions.items():
                if dim_name == first_time_name:
                    continue
                if dim_name not in ds.dimensions or len(ds.dimensions[dim_name]) != len(dim):
                    raise ValueError(
                        tr("tools_merge_dimension_mismatch", "维度不一致：{dimension}").format(
                            dimension=dim_name
                        )
                    )
                if dim_name in first.variables:
                    if dim_name not in ds.variables or not _arrays_equal(
                        first.variables[dim_name][:], ds.variables[dim_name][:]
                    ):
                        raise ValueError(
                            tr("tools_merge_coordinate_mismatch", "坐标不一致：{coordinate}").format(
                                coordinate=dim_name
                            )
                        )

            for var_name in data_variables:
                if _variable_definition(first.variables[var_name], first_time_name) != _variable_definition(
                    ds.variables[var_name], time_name
                ):
                    raise ValueError(
                        tr("tools_merge_definition_mismatch", "变量定义不一致：{variable}").format(
                            variable=var_name
                        )
                    )
                if first_time_name not in first.variables[var_name].dimensions and not _arrays_equal(
                    first.variables[var_name][:], ds.variables[var_name][:]
                ):
                    raise ValueError(
                        tr("tools_merge_static_mismatch", "静态变量内容不一致：{variable}").format(
                            variable=var_name
                        )
                    )

        entries: list[tuple[float, str, int]] = []
        for ds, path in zip(datasets, paths):
            entries.extend(
                (float(value), path, index)
                for index, value in enumerate(_canonical_times(ds.variables[time_names[path]]))
            )
        entries.sort(key=lambda item: item[0])

        unique_times: list[float] = []
        sources: list[tuple[str, int]] = []
        opened = {path: ds for path, ds in zip(paths, datasets)}
        for value, path, index in entries:
            if unique_times and np.isclose(value, unique_times[-1], rtol=0, atol=1e-6):
                previous_path, previous_index = sources[-1]
                for var_name in data_variables:
                    var = opened[path].variables[var_name]
                    time_name = time_names[path]
                    previous_time_name = time_names[previous_path]
                    if time_name not in var.dimensions:
                        continue
                    axis = var.dimensions.index(time_name)
                    previous_axis = opened[previous_path].variables[var_name].dimensions.index(previous_time_name)
                    if not _arrays_equal(
                        np.take(
                            opened[previous_path].variables[var_name][:],
                            previous_index,
                            axis=previous_axis,
                        ),
                        np.take(var[:], index, axis=axis),
                    ):
                        raise ValueError(
                            tr(
                                "tools_merge_duplicate_conflict",
                                "重复时间的数据不一致：{time}（{first} / {second}）",
                            ).format(
                                time=value,
                                first=os.path.basename(previous_path),
                                second=os.path.basename(path),
                            )
                        )
                continue
            unique_times.append(value)
            sources.append((path, index))
        return _GroupPlan(paths, data_variables, np.asarray(unique_times), sources, time_names)
    finally:
        for ds in datasets:
            ds.close()


def _validate_cross_groups(groups: list[_GroupPlan]) -> None:
    nc, _ = _imports()
    if len(groups) < 2:
        return
    reference = groups[0]
    reference_time_name = reference.time_names[reference.paths[0]]
    with nc.Dataset(reference.paths[0], "r") as first:
        reference_dims = {
            name: len(dim)
            for name, dim in first.dimensions.items()
            if name != reference_time_name
        }
        reference_coords = {
            name: first.variables[name][:]
            for name in reference_dims
            if name in first.variables
        }
    for group in groups[1:]:
        if not _arrays_equal(reference.times, group.times):
            raise ValueError(tr("tools_merge_cross_time_mismatch", "不同强迫场的时间轴不一致"))
        with nc.Dataset(group.paths[0], "r") as ds:
            group_time_name = group.time_names[group.paths[0]]
            dimensions = {
                name: len(dim)
                for name, dim in ds.dimensions.items()
                if name != group_time_name
            }
            shared = set(reference_dims) & set(dimensions)
            for name in shared:
                if reference_dims[name] != dimensions[name]:
                    raise ValueError(
                        tr("tools_merge_dimension_mismatch", "维度不一致：{dimension}").format(dimension=name)
                    )
                if name in reference_coords and (
                    name not in ds.variables or not _arrays_equal(reference_coords[name], ds.variables[name][:])
                ):
                    raise ValueError(
                        tr("tools_merge_coordinate_mismatch", "坐标不一致：{coordinate}").format(coordinate=name)
                    )
            with nc.Dataset(reference.paths[0], "r") as reference_ds:
                for name in set(reference.data_variables) & set(group.data_variables):
                    if _variable_definition(
                        reference_ds.variables[name], reference.time_names[reference.paths[0]]
                    ) != _variable_definition(ds.variables[name], group.time_names[group.paths[0]]):
                        raise ValueError(
                            tr("tools_merge_definition_mismatch", "变量定义不一致：{variable}").format(
                                variable=name
                            )
                        )
                    if not _arrays_equal(reference_ds.variables[name][:], ds.variables[name][:]):
                        raise ValueError(
                            tr("tools_merge_shared_variable_mismatch", "共享变量内容不一致：{variable}").format(
                                variable=name
                            )
                        )


def _build_plan(input_paths: Sequence[str]) -> _MergePlan:
    normalized = list(dict.fromkeys(os.path.abspath(path) for path in input_paths))
    infos = tuple(read_netcdf_info(path) for path in normalized)
    errors = [f"{info.filename}: {info.error}" for info in infos if info.error]
    if len(normalized) < 2:
        errors.append(tr("tools_merge_need_multiple", "至少需要选择 2 个文件"))
    if errors:
        return _MergePlan([], MergeAnalysis(infos, "", tuple(errors)))

    grouped: dict[tuple[str, ...], list[str]] = defaultdict(list)
    nc, _ = _imports()
    try:
        for path in normalized:
            with nc.Dataset(path, "r") as ds:
                grouped[_data_variable_names(ds)].append(path)
        groups = [_validate_group(paths, variables) for variables, paths in grouped.items()]
        _validate_cross_groups(groups)
    except Exception as exc:
        return _MergePlan([], MergeAnalysis(infos, "", (str(exc),)))

    has_time_concat = any(len(group.paths) > 1 for group in groups)
    has_field_merge = len(groups) > 1
    strategy = (
        tr("tools_merge_strategy_both", "先按时间拼接，再合并不同强迫场")
        if has_time_concat and has_field_merge
        else tr("tools_merge_strategy_time", "按时间拼接")
        if has_time_concat
        else tr("tools_merge_strategy_fields", "合并不同强迫场")
    )
    return _MergePlan(
        groups,
        MergeAnalysis(infos, strategy, (), len(groups[0].times) if groups else 0),
    )


def analyze_merge_inputs(input_paths: Sequence[str]) -> MergeAnalysis:
    """Analyze inputs and return the selected automatic strategy and validation errors."""

    return _build_plan(input_paths).analysis


def _variable_kwargs(var) -> dict[str, Any]:
    attrs = {name: var.getncattr(name) for name in var.ncattrs()}
    kwargs: dict[str, Any] = {}
    if "_FillValue" in attrs:
        kwargs["fill_value"] = attrs["_FillValue"]
    try:
        filters = var.filters() or {}
        for key in ("zlib", "complevel", "shuffle", "fletcher32"):
            if filters.get(key) is not None:
                kwargs[key] = filters[key]
        chunks = var.chunking()
        if isinstance(chunks, list):
            kwargs["chunksizes"] = tuple(chunks)
    except Exception:
        pass
    return kwargs


def _copy_attrs(source, target, *, skip: set[str] | None = None) -> None:
    skipped = skip or set()
    for name in source.ncattrs():
        if name not in skipped:
            target.setncattr(name, source.getncattr(name))


def _create_variable(out, name: str, source_var, *, time_name: str):
    kwargs = _variable_kwargs(source_var)
    dimensions = _normalized_dimensions(source_var, time_name)
    if time_name in source_var.dimensions and "chunksizes" in kwargs:
        axis = source_var.dimensions.index(time_name)
        chunks = list(kwargs["chunksizes"])
        chunks[axis] = min(chunks[axis], max(1, len(out.dimensions["time"])))
        kwargs["chunksizes"] = tuple(chunks)
    try:
        var = out.createVariable(name, source_var.dtype, dimensions, **kwargs)
    except Exception:
        var = out.createVariable(
            name,
            source_var.dtype,
            dimensions,
            fill_value=kwargs.get("fill_value"),
        )
    _copy_attrs(source_var, var, skip={"_FillValue", "units", "calendar"} if name == "time" else {"_FillValue"})
    return var


def _write_plan(
    plan: _MergePlan,
    output_path: str,
    *,
    progress: Callable[[int, str], None] | None = None,
) -> None:
    nc, _ = _imports()
    last_progress = -1

    def _progress(value: int, message: str) -> None:
        nonlocal last_progress
        if progress and value > last_progress:
            last_progress = value
            progress(value, message)

    data_work = 0
    for group in plan.groups:
        with nc.Dataset(group.paths[0], "r") as ds:
            time_name = group.time_names[group.paths[0]]
            for name in group.data_variables:
                data_work += len(group.time_sources) if time_name in ds.variables[name].dimensions else 1
    completed_work = 0

    def _advance(message: str) -> None:
        nonlocal completed_work
        completed_work += 1
        value = 15 + round(80 * completed_work / max(1, data_work))
        _progress(min(value, 95), message)

    _progress(10, tr("tools_merge_progress_create", "正在创建输出文件"))
    first_group = plan.groups[0]
    with nc.Dataset(first_group.paths[0], "r") as first, nc.Dataset(output_path, "w", format="NETCDF4") as out:
        _copy_attrs(first, out)
        first_time_name = first_group.time_names[first_group.paths[0]]
        dimension_sizes: dict[str, int | None] = {
            "time": None if first.dimensions[first_time_name].isunlimited() else len(first_group.times)
        }
        for group in plan.groups:
            with nc.Dataset(group.paths[0], "r") as ds:
                time_name = group.time_names[group.paths[0]]
                for name, dim in ds.dimensions.items():
                    if name == time_name:
                        continue
                    size = None if dim.isunlimited() else len(dim)
                    if name in dimension_sizes and dimension_sizes[name] != size:
                        raise ValueError(
                            tr("tools_merge_dimension_mismatch", "维度不一致：{dimension}").format(dimension=name)
                        )
                    dimension_sizes[name] = size
        for name, size in dimension_sizes.items():
            out.createDimension(name, size)

        time_source = first.variables[first_time_name]
        time_out = out.createVariable("time", "f8", ("time",))
        _copy_attrs(time_source, time_out, skip={"_FillValue", "units", "calendar"})
        time_out.units = _EPOCH_UNITS
        time_out.calendar = _EPOCH_CALENDAR
        time_out[:] = first_group.times

        created: set[str] = {"time"}
        for group in plan.groups:
            with nc.Dataset(group.paths[0], "r") as ds:
                time_name = group.time_names[group.paths[0]]
                for name, source_var in ds.variables.items():
                    if name == time_name or name in created or name in group.data_variables:
                        continue
                    target = _create_variable(out, name, source_var, time_name=time_name)
                    target[:] = source_var[:]
                    created.add(name)

            opened = {path: nc.Dataset(path, "r") for path in group.paths}
            try:
                for name in group.data_variables:
                    if name in created:
                        continue
                    source_var = opened[group.paths[0]].variables[name]
                    first_source_time_name = group.time_names[group.paths[0]]
                    target = _create_variable(out, name, source_var, time_name=first_source_time_name)
                    if first_source_time_name not in source_var.dimensions:
                        target[:] = source_var[:]
                        created.add(name)
                        _advance(
                            tr("tools_merge_progress_variable", "正在写入变量：{variable}").format(variable=name)
                        )
                        continue
                    for target_index, (path, source_index) in enumerate(group.time_sources):
                        source_time_name = group.time_names[path]
                        source = opened[path].variables[name]
                        source_axis = source.dimensions.index(source_time_name)
                        target_axis = target.dimensions.index("time")
                        source_indexer = [slice(None)] * source.ndim
                        source_indexer[source_axis] = source_index
                        indexer = [slice(None)] * target.ndim
                        indexer[target_axis] = target_index
                        target[tuple(indexer)] = source[tuple(source_indexer)]
                        _advance(
                            tr(
                                "tools_merge_progress_variable_step",
                                "正在写入 {variable}：{current}/{total}",
                            ).format(
                                variable=name,
                                current=target_index + 1,
                                total=len(group.time_sources),
                            )
                        )
                    created.add(name)
            finally:
                for ds in opened.values():
                    ds.close()
    _progress(98, tr("tools_merge_progress_finalize", "正在完成输出文件"))


def merge_forcing_netcdf(
    input_paths: Sequence[str],
    output_path: str,
    *,
    log: Callable[[str], None] | None = None,
    progress: Callable[[int, str], None] | None = None,
) -> str:
    """Validate and merge forcing files, atomically replacing the output on success."""

    normalized_output = os.path.abspath(output_path)
    normalized_inputs = {os.path.abspath(path) for path in input_paths}
    if normalized_output in normalized_inputs:
        raise ValueError(tr("tools_merge_output_is_input", "输出路径不能与输入文件相同"))

    if progress:
        progress(0, tr("tools_merge_progress_validate", "正在校验输入文件"))
    plan = _build_plan(input_paths)
    if not plan.analysis.valid:
        raise ValueError("\n".join(plan.analysis.errors))
    if log:
        log(
            tr("tools_merge_plan", "合并方式：{strategy}，共 {steps} 个时间步").format(
                strategy=plan.analysis.strategy,
                steps=plan.analysis.time_steps,
            )
        )

    output = Path(normalized_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    os.close(fd)
    try:
        _write_plan(plan, temp_path, progress=progress)
        os.replace(temp_path, output)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise
    if progress:
        progress(100, tr("tools_merge_progress_complete", "合并完成"))
    if log:
        log(
            tr("tools_merge_done", "✅ 合并完成：{n_files} 个文件 → {out}（{n_time} 个时间步）").format(
                n_files=len(input_paths),
                out=output.name,
                n_time=plan.analysis.time_steps,
            )
        )
    return str(output)
