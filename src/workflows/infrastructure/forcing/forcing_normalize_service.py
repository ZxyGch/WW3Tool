"""WW3 Step 2 强迫场 NetCDF 归一化服务。

[EN] WW3 Step 2 forcing field NetCDF normalization service.

将各类再分析/预报强迫场统一转换为 WW3 ``ww3_prnc`` 可读格式，主要处理：

[EN] Converts various reanalysis/forecast forcing fields into a unified
WW3 ``ww3_prnc``-readable format. Main processing includes:

- 经纬度变量名标准化，必要时翻转纬度递增方向；经度递减统一拒绝；
- 强迫场变量统一命名为标准名（u10/v10、uo/vo、zos、siconc）；
- 保留原始时间轴单位与日历属性（WW3 ww3_prnc 按 CF 约定自行解析）；
- 保留源文件中所有变量，仅重命名坐标和强迫场变量；
- 大文件分块或并行变换以控制内存占用。

[EN] - Standardizing lat/lon variable names, flipping latitude when necessary;
      descending longitude is always rejected;
- Renaming forcing variables to standard names (u10/v10, uo/vo, zos, siconc);
- Preserving original time axis units and calendar attributes (WW3 ww3_prnc parses them via CF conventions);
- Preserving all source variables, only renaming coordinates and forcing variables;
- Chunking or parallel transformation for large files to control memory usage.
"""

from __future__ import annotations

import multiprocessing
import os
import traceback
from concurrent.futures import ProcessPoolExecutor
from typing import Callable, List, Optional

import numpy as np
from netCDF4 import Dataset

from ...support.translations import tr
from .forcing_time_metadata import (
    audit_time_metadata_for_ww3,
    format_time_metadata_issue_logs,
    normalize_calendar_for_ww3,
    normalize_time_units_for_ww3,
)
from .forcing_variable_resolver import (
    ForcingVariableError,
    resolve_all_fields,
    resolve_forcing_variables,
)
from ...domain.config_models import ForcingVariableOverride, ResolvedForcingVariables

# WW3 ww3_prnc 硬编码的坐标变量名：坐标数组（ALO/ALA）读取不读 namelist，
# 只从 longitude/lon/Longitude/x/X 与 latitude/lat/Latitude/y/Y 候选名中查找。
# 因此归一化输出必须使用 longitude/latitude。
# [EN] Coordinate variable names hard-coded in ww3_prnc: the coordinate arrays
# (ALO/ALA) are NOT looked up via namelist — only the candidate names
# longitude/lon/Longitude/x/X and latitude/lat/Latitude/y/Y are tried, so the
# normalized output must use longitude/latitude.
_WW3_LON_NAME = "longitude"
_WW3_LAT_NAME = "latitude"


def _transpose_to_output(chunk, transpose_axes):
    """把源数组转置到 WW3 布局 (time, lat, lon)；无法完全对应时不转置。

    [EN] Transpose a source array to the WW3 layout (time, lat, lon);
    fall back to no-op when the axes do not fully correspond.
    """
    chunk = np.asarray(chunk)
    axes = tuple(a for a in transpose_axes if a is not None and a < chunk.ndim)
    if len(axes) == chunk.ndim and axes != tuple(range(chunk.ndim)):
        chunk = np.transpose(chunk, axes)
    return chunk


def _transform_chunks_for_pool(chunks, lat_needs_flip, lat_axis, lon_needs_flip, lon_axis, transpose_axes):
    """多进程池用通用数组变换：纬度/经度翻转 + 转置到 WW3 布局并确保 C 连续。

    [EN] Generic array transform for multiprocessing pool: lat/lon flip,
    transpose to the WW3 layout, and ensure C-contiguity.
    """
    results = []
    for chunk in chunks:
        chunk = np.asarray(chunk)
        if lat_needs_flip and lat_axis is not None and lat_axis < chunk.ndim:
            chunk = np.flip(chunk, axis=lat_axis)
        if lon_needs_flip and lon_axis is not None and lon_axis < chunk.ndim:
            chunk = np.flip(chunk, axis=lon_axis)
        results.append(np.ascontiguousarray(_transpose_to_output(chunk, transpose_axes)))
    return tuple(results)


def _get_available_memory_bytes() -> int:
    """尽力检测当前可用物理内存（字节），用于分块大小决策。

    [EN] Best-effort detection of currently available physical memory (bytes),
    used for chunk size decisions.
    """
    try:
        import psutil
        return int(psutil.virtual_memory().available)
    except Exception:
        pass
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        avail_pages = os.sysconf("SC_AVPHYS_PAGES")
        available = int(page_size * avail_pages)
        if available > 0:
            return available
    except Exception:
        pass
    try:
        import re
        import subprocess
        output = subprocess.check_output(["vm_stat"], text=True, stderr=subprocess.DEVNULL)
        page_size = 4096
        match = re.search(r"page size of (\d+) bytes", output)
        if match:
            page_size = int(match.group(1))
        pages = {}
        for line in output.splitlines():
            m = re.match(r"^([^:]+):\s+([0-9]+)\.$", line.strip())
            if m:
                pages[m.group(1)] = int(m.group(2))
        available_pages = (
            pages.get("Pages free", 0)
            + pages.get("Pages inactive", 0)
            + pages.get("Pages speculative", 0)
        )
        available = int(available_pages * page_size)
        if available > 0:
            return available
    except Exception:
        pass
    return 0


class ForcingNormalizeService:
    """将强迫场 NetCDF 归一化为 WW3 标准布局的服务类。

    [EN] Service class for normalizing forcing field NetCDF into the WW3 standard layout.

    自变量映射功能起，不再重命名强迫场/经纬度变量（方案 §6）：数据变量与
    经纬度变量保留源名；仅时间变量统一为 ``time``（WW3 无 ``FILE%TIME``）。
    变量识别统一由 ``forcing_variable_resolver`` 完成。

    [EN] Since variable mapping support, forcing/coordinate variables are no
    longer renamed (spec §6): data and lon/lat variables keep their source
    names; only the time variable is standardized to ``time`` (WW3 has no
    ``FILE%TIME``). Identification is delegated to ``forcing_variable_resolver``.
    """

    def normalize(
        self,
        source_file: str,
        output_file: str,
        log: Optional[Callable[[str], None]] = None,
        variables: Optional[object] = None,
    ) -> bool:
        """读取源文件并写出归一化后的强迫场 NetCDF。

        [EN] Read the source file and write the normalized forcing NetCDF.

        参数:
            source_file: 原始 NetCDF 路径
            output_file: 目标路径
            log: 可选进度/诊断日志回调
            variables: 解析结果（单个或列表，对应一个或多个强迫场）；
                为 ``None`` 时调用统一解析服务自动识别全部场

        [EN] Parameters:
            source_file: Source NetCDF path
            output_file: Target path
            log: Optional progress/diagnostic log callback
            variables: Resolved variables (single or list, for one or more
                forcing fields); when ``None``, all fields are auto-resolved.

        返回:
            成功写入为 ``True``，失败为 ``False``

        [EN] Returns:
            ``True`` on success, ``False`` on failure.
        """
        if not source_file:
            self._emit(log, tr("log_select_origin_file_first", "❌ 请先选择原始数据文件！"))
            return False
        if not output_file:
            self._emit(log, tr("log_write_file_failed", "❌ 写入新文件失败"))
            return False

        output_dir = os.path.dirname(output_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # ── Phase 1: 读取元数据 ─────────────────────────────────────────
        # [EN] Phase 1: read metadata
        try:
            with Dataset(source_file, "r") as src:
                src.set_auto_mask(False)

                resolved_list = self._collect_resolved_variables(source_file, variables)
                if not resolved_list:
                    raise KeyError(
                        tr(
                            "forcing_vars_not_found",
                            "❌ 未检测到可识别的强迫场变量，请在变量映射中手动指定",
                        )
                    )

                lon_name = resolved_list[0].longitude
                lat_name = resolved_list[0].latitude
                time_name = resolved_list[0].source_time
                output_time = resolved_list[0].output_time or "time"
                for _rv in resolved_list:
                    if (
                        _rv.longitude != lon_name
                        or _rv.latitude != lat_name
                        or _rv.source_time != time_name
                    ):
                        raise ValueError(
                            tr(
                                "forcing_multi_field_coord_mismatch",
                                "❌ 同一文件的多个强迫场必须使用相同的经纬度/时间变量",
                            )
                        )

                if lon_name not in src.variables:
                    raise KeyError(tr("log_lon_var_not_found", "❌ 未找到经度变量：{name}").format(name=lon_name))
                if lat_name not in src.variables:
                    raise KeyError(tr("log_lat_var_not_found", "❌ 未找到纬度变量：{name}").format(name=lat_name))
                if time_name not in src.variables:
                    raise KeyError(tr("log_time_var_not_found", "❌ 未找到时间变量：{name}").format(name=time_name))

                longitude = np.asarray(src.variables[lon_name][:])
                latitude = np.asarray(src.variables[lat_name][:])
                time_var_obj = src.variables[time_name]
                time_data = np.asarray(time_var_obj[:])

                original_time_units = getattr(time_var_obj, "units", None)
                original_time_calendar = getattr(time_var_obj, "calendar", "gregorian")

                # 收集所有数据变量（分量 + 可选冰厚）的信息，保留源变量名
                # [EN] Collect metadata for all data variables (components + optional ice thickness), keeping source names
                data_var_infos = []
                for _rv in resolved_list:
                    for _comp in list(_rv.components) + ([_rv.thickness] if _rv.thickness else []):
                        src_var = src.variables[_comp]
                        shape = src_var.shape
                        dims = list(src_var.dimensions) if hasattr(src_var, "dimensions") else None
                        dtype = src_var.dtype

                        def _snapshot_filters(var_obj):
                            try:
                                if hasattr(var_obj, "filters"):
                                    result = var_obj.filters()
                                    if isinstance(result, dict):
                                        return result
                                # [EN] Some netCDF4 versions may return non-dict; convert if possible
                                    if isinstance(result, (list, tuple)):
                                        return dict(result)
                            except Exception:
                                pass
                            return {}

                        data_var_infos.append({
                            "src_name": _comp,
                            "field": _rv.field,
                            "shape": shape,
                            "dims": dims,
                            "dtype": dtype,
                            "filters": _snapshot_filters(src_var),
                        })

                # 以第一个数据变量为基准确定维度顺序
                # [EN] Determine dimension order based on the first data variable
                primary = data_var_infos[0]
                primary_shape = primary["shape"]
                primary_dims = primary["dims"]

                if len(primary_shape) < 2:
                    raise ValueError(
                        tr("log_data_dim_unsupported", "❌ 数据维度不受支持：{shape}").format(shape=primary_shape)
                    )

                # 推断 time/lat/lon 在数据数组中的维度索引
                # [EN] Infer the dimension indices of time/lat/lon in the data array
                time_dim_idx = None
                lat_dim_idx = None
                lon_dim_idx = None

                if primary_dims:
                    for index, dim_name in enumerate(primary_dims):
                        if dim_name == time_name or time_name in dim_name or dim_name in time_name:
                            time_dim_idx = index
                        elif dim_name == lat_name or lat_name in dim_name or dim_name in lat_name:
                            lat_dim_idx = index
                        elif dim_name == lon_name or lon_name in dim_name or dim_name in lon_name:
                            lon_dim_idx = index

                if time_dim_idx is None or lat_dim_idx is None or lon_dim_idx is None:
                    # 按形状推断
                    # [EN] Infer by shape
                    if len(primary_shape) >= 3:
                        if primary_shape[-2] == len(latitude) and primary_shape[-1] == len(longitude):
                            time_dim_idx, lat_dim_idx, lon_dim_idx = len(primary_shape) - 3, len(primary_shape) - 2, len(primary_shape) - 1
                        elif primary_shape[-1] == len(latitude) and primary_shape[-2] == len(longitude):
                            time_dim_idx, lat_dim_idx, lon_dim_idx = len(primary_shape) - 3, len(primary_shape) - 1, len(primary_shape) - 2
                    if time_dim_idx is None or lat_dim_idx is None or lon_dim_idx is None:
                        raise ValueError(
                            tr(
                                "log_dim_order_uncertain",
                                "⚠️ 无法确定维度顺序！数据形状={shape}, 纬度长度={lat_len}, 经度长度={lon_len}",
                            ).format(shape=primary_shape, lat_len=len(latitude), lon_len=len(longitude))
                        )

                # 输出维度顺序固定 (time, latitude, longitude)：
                # WW3 7.14 ww3_prnc.F90 读取数据用 NF90_GET_VAR(...,
                # start=(/1,1,ITIME/), count=(/MXM,MYM,1/))；Fortran 接口的
                # 维度序与 CDL 声明相反，故文件必须声明 time 在前、lat 次之、
                # lon 最后。time 放在末维会触发
                # "NetCDF: Start+count exceeds dimension bound"（退出码 59）。
                # [EN] Output dims fixed to (time, latitude, longitude): WW3 7.14
                # ww3_prnc.F90 reads fields via NF90_GET_VAR(...,
                # start=(/1,1,ITIME/), count=(/MXM,MYM,1/)); the Fortran
                # interface's dimension order is reversed w.r.t. the CDL
                # declaration, so the file must declare time first, lat second,
                # lon last. A time-last layout triggers
                # "NetCDF: Start+count exceeds dimension bound" (exit 59).
                output_dim_order = (output_time, _WW3_LAT_NAME, _WW3_LON_NAME)
                # 源轴 → 输出轴顺序 (time, lat, lon)，用于数据转置
                # [EN] Source axes ordered as (time, lat, lon), used to transpose data
                _src_axes = (time_dim_idx, lat_dim_idx, lon_dim_idx)

                lon_dtype = src.variables[lon_name].dtype
                lat_dtype = src.variables[lat_name].dtype
                time_dtype = time_var_obj.dtype

                # 记录所有源变量名（用于后续全量复制）
                # [EN] Record all source variable names (for subsequent full copy)
                all_src_var_names = list(src.variables.keys())

        except Exception as exc:
            self._emit(log, tr("log_read_origin_failed", "❌ 读取原始文件失败: {error}").format(error=exc))
            return False

        # ── 经度递减检查：统一拒绝 ────────────────────────────────────
        # [EN] Longitude descending check: always reject
        if len(longitude) > 1 and longitude[0] > longitude[-1]:
            self._emit(
                log,
                tr(
                    "forcing_lon_descending_rejected",
                    "❌ 经度坐标递减（{first} → {last}），拒绝导入。经度闭合和范围关系不能安全猜测。",
                ).format(first=float(longitude[0]), last=float(longitude[-1])),
            )
            return False

        # ── 纬度递减：翻转 ──────────────────────────────────────────────
        # [EN] Latitude descending: flip
        lat_needs_flip = len(latitude) > 1 and latitude[0] > latitude[-1]
        if lat_needs_flip:
            latitude = latitude[::-1]

        # ── 短路判断 ────────────────────────────────────────────────────
        # [EN] Short-circuit check: only time standardization and lat flip
        # require a rewrite (data/lon/lat variable names are preserved now)
        needs_rename = time_name.lower() != "time" or lat_needs_flip

        time_metadata_issues = audit_time_metadata_for_ww3(source_file, time_name=time_name)
        needs_time_metadata_fix = bool(time_metadata_issues)

        try:
            same_target_file = os.path.samefile(source_file, output_file)
        except OSError:
            same_target_file = False

        if needs_time_metadata_fix:
            format_time_metadata_issue_logs(time_metadata_issues, log=log)
            self._emit(
                log,
                tr(
                    "forcing_time_metadata_rewrite",
                    "🔄 将重写时间元数据为 WW3 可读的 char 属性（units + calendar）",
                ),
            )

        if (
            same_target_file
            and not lat_needs_flip
            and not needs_rename
            and not needs_time_metadata_fix
        ):
            self._emit(log, tr("forcing_already_normalized", "✅ 文件已是标准格式: {path}").format(path=output_file))
            return True

        # ── 分块策略 ────────────────────────────────────────────────────
        # [EN] Chunking strategy
        n_time = len(time_data)
        n_lat = len(latitude)
        n_lon = len(longitude)
        points_per_step = max(1, n_lat * n_lon)

        # 估算总数据量（所有数据变量）
        # [EN] Estimate total data volume (all data variables)
        total_bytes_per_step = sum(
            points_per_step * max(1, np.dtype(info["dtype"]).itemsize) for info in data_var_infos
        )
        estimated_total_bytes = n_time * total_bytes_per_step

        available_memory_bytes = _get_available_memory_bytes()
        if available_memory_bytes > 0:
            full_load_threshold_bytes = min(
                3 * 1024 * 1024 * 1024,
                max(768 * 1024 * 1024, available_memory_bytes // 4),
            )
            target_chunk_bytes = min(
                2 * 1024 * 1024 * 1024,
                max(768 * 1024 * 1024, available_memory_bytes // 5),
            )
        else:
            full_load_threshold_bytes = 512 * 1024 * 1024
            target_chunk_bytes = 1536 * 1024 * 1024

        chunk_time = max(1, min(n_time, target_chunk_bytes // max(1, total_bytes_per_step)))
        chunk_time = min(chunk_time, 256)
        max_workers = min(2, max(1, (os.cpu_count() or 1) - 1))

        try:
            file_size_bytes = os.path.getsize(source_file)
        except OSError:
            file_size_bytes = 0

        use_full_load = estimated_total_bytes <= full_load_threshold_bytes
        n_data_vars = len(data_var_infos)
        use_parallel = (
            not use_full_load
            and n_time >= 96
            and n_time > chunk_time
            and max(1, (n_time + chunk_time - 1) // chunk_time) >= 8
            and max_workers > 1
            and file_size_bytes >= 2 * 1024 * 1024 * 1024
            and points_per_step <= 300000
            and n_data_vars <= 4  # 并行仅适用于少量数据变量
            # [EN] Parallel processing is only suitable for a small number of data variables
        )
        total_chunks = max(1, (n_time + chunk_time - 1) // chunk_time)
        progress_log_interval = 1 if total_chunks <= 12 else max(1, total_chunks // 8)

        def _build_chunksizes(dtype):
            plane_bytes = max(1, n_lat * n_lon * np.dtype(dtype).itemsize)
            target_storage = 16 * 1024 * 1024
            tc = max(1, min(n_time, target_storage // plane_bytes))
            tc = min(tc, 16)
            size_map = {output_time: tc, _WW3_LAT_NAME: n_lat, _WW3_LON_NAME: n_lon}
            return tuple(size_map[d] for d in output_dim_order)

        def _transform_chunk(chunk, ndim):
            """本地变换：翻转 lat 轴并把数据转置到 (time, lat, lon)。

            [EN] Local transform: flip the lat axis and transpose the data
            to (time, lat, lon).
            """
            chunk = np.asarray(chunk)
            if lat_needs_flip and lat_dim_idx is not None and lat_dim_idx < ndim:
                chunk = np.flip(chunk, axis=lat_dim_idx)
            return np.ascontiguousarray(_transpose_to_output(chunk, _src_axes))

        # ── Phase 2: 写出标准化文件 ─────────────────────────────────────
        # [EN] Phase 2: write normalized file
        try:
            temp_output_path = output_file + ".normalize_tmp"
            if os.path.exists(temp_output_path):
                os.remove(temp_output_path)

            with Dataset(source_file, "r") as src, Dataset(temp_output_path, "w", format="NETCDF4") as dst:
                src.set_auto_mask(False)
                try:
                    dst.set_fill_off()
                except Exception:
                    pass

                # 复制全局属性
                # [EN] Copy global attributes
                for attr_name in src.ncattrs():
                    try:
                        dst.setncattr(attr_name, src.getncattr(attr_name))
                    except Exception:
                        pass

                # 创建输出维度：坐标统一为 longitude/latitude（WW3 硬编码候选名），
                # 时间统一为 time
                # [EN] Create output dimensions: coordinates unified to
                # longitude/latitude (hard-coded candidate names in ww3_prnc),
                # time standardized to ``time``
                dst.createDimension(_WW3_LON_NAME, n_lon)
                dst.createDimension(_WW3_LAT_NAME, n_lat)
                dst.createDimension(output_time, n_time)
                # 复制源文件中其他维度（如 depth 等）
                # [EN] Copy other dimensions from source (e.g., depth)
                for dim_name, dim_obj in src.dimensions.items():
                    if dim_name in (lon_name, lat_name, time_name, output_time, _WW3_LON_NAME, _WW3_LAT_NAME):
                        continue
                    if dim_name not in dst.dimensions:
                        dst.createDimension(dim_name, len(dim_obj) if not dim_obj.isunlimited() else None)

                # 创建坐标变量（统一为 longitude/latitude；时间统一为 time）
                # [EN] Create coordinate variables (unified to longitude/latitude;
                # time standardized)
                lon_var = dst.createVariable(_WW3_LON_NAME, lon_dtype, (_WW3_LON_NAME,))
                lat_var = dst.createVariable(_WW3_LAT_NAME, lat_dtype, (_WW3_LAT_NAME,))
                time_var = dst.createVariable(output_time, time_dtype, (output_time,))

                # 创建数据变量
                # [EN] Create data variables
                def _build_var_kwargs(filters, chunksizes):
                    kwargs = {"fill_value": -32767.0}
                    if not isinstance(filters, dict):
                        return kwargs
                    try:
                        if filters.get("zlib"):
                            kwargs["zlib"] = True
                            if filters.get("complevel") is not None:
                                kwargs["complevel"] = filters["complevel"]
                            if filters.get("shuffle") is not None:
                                kwargs["shuffle"] = filters["shuffle"]
                            if filters.get("fletcher32") is not None:
                                kwargs["fletcher32"] = filters["fletcher32"]
                            if chunksizes is not None:
                                kwargs["chunksizes"] = chunksizes
                            if filters.get("least_significant_digit") is not None:
                                kwargs["least_significant_digit"] = filters["least_significant_digit"]
                    except Exception:
                        pass
                    return kwargs

                def _create_data_var(std_name, dtype, filters, chunksizes):
                    dims = tuple(output_dim_order)
                    try:
                        return dst.createVariable(std_name, dtype, dims, **_build_var_kwargs(filters, chunksizes))
                    except Exception:
                        return dst.createVariable(std_name, dtype, dims, fill_value=-32767.0)

                dst_data_vars = {}
                for info in data_var_infos:
                    cs = _build_chunksizes(info["dtype"])
                    dst_data_vars[info["src_name"]] = _create_data_var(
                        info["src_name"], info["dtype"], info["filters"], cs
                    )
                    # 保留源变量全部属性（方案 §6：不重命名、保留属性）
                    # [EN] Preserve all source variable attributes (spec §6)
                    src_var_obj = src.variables[info["src_name"]]
                    for attr_name in src_var_obj.ncattrs():
                        try:
                            dst_data_vars[info["src_name"]].setncattr(
                                attr_name, src_var_obj.getncattr(attr_name)
                            )
                        except Exception:
                            pass

                # 写入坐标
                # [EN] Write coordinates
                lon_var[:] = longitude
                lat_var[:] = latitude

                # 时间：保留原始值与单位（WW3 ww3_prnc 按 CF 约定自行解析）
                # [EN] Time: preserve original values and units (WW3 ww3_prnc parses via CF conventions)
                time_var[:] = time_data

                # ── 写入数据变量 ────────────────────────────────────────
                # [EN] Write data variables
                # 对每个数据变量构建读取切片
                # [EN] Build read slices for each data variable
                def _make_read_slices(src_var_shape, start, end):
                    slices = [slice(None)] * len(src_var_shape)
                    # 找到时间维度索引（在该变量的维度中）
                    # [EN] Find the time dimension index (in this variable's dimensions)
                    if len(src_var_shape) >= 3:
                        slices[time_dim_idx] = slice(start, end)
                    return tuple(slices)

                if use_full_load:
                    for info in data_var_infos:
                        src_var = src.variables[info["src_name"]]
                        data = np.asarray(src_var[:])
                        dst_data_vars[info["src_name"]][:] = _transform_chunk(data, len(info["shape"]))

                elif use_parallel:
                    self._emit(
                        log,
                        tr("log_parallel_chunk_transform", "🔄 已启用并行分块处理（{workers} 个进程）").format(
                            workers=max_workers
                        ),
                    )
                    ctx = multiprocessing.get_context("spawn")
                    with ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx) as executor:
                        pending = None
                        for start in range(0, n_time, chunk_time):
                            end = min(start + chunk_time, n_time)
                            chunk_index = start // chunk_time + 1
                            if chunk_index == 1 or chunk_index == total_chunks or chunk_index % progress_log_interval == 0:
                                self._emit(
                                    log,
                                    tr("step1_debug_chunk_progress", "🔍 [调试] 正在处理分块 {current}/{total}（time: {start}~{end}）").format(
                                        current=chunk_index, total=total_chunks, start=start, end=end - 1,
                                    ),
                                )
                            # 读取所有数据变量的当前块
                            # [EN] Read the current chunk for all data variables
                            chunks = []
                            for info in data_var_infos:
                                src_var = src.variables[info["src_name"]]
                                slices = _make_read_slices(info["shape"], start, end)
                                chunks.append(np.asarray(src_var[slices]))

                            # 计算该变量数组中 lat/lon 的轴位置
                            # [EN] Compute the lat/lon axis positions in the variable array
                            ndim = len(data_var_infos[0]["shape"])
                            lat_ax = lat_dim_idx if lat_dim_idx is not None else (ndim - 2 if ndim >= 2 else None)
                            lon_ax = lon_dim_idx if lon_dim_idx is not None else (ndim - 1 if ndim >= 1 else None)

                            future = executor.submit(
                                _transform_chunks_for_pool,
                                # lon_needs_flip=False (已拒绝)
                                # [EN] lon_needs_flip=False (descending longitude already rejected)
                                chunks, lat_needs_flip, lat_ax, False, lon_ax, _src_axes,
                            )
                            if pending is not None:
                                prev_start, prev_end, prev_future = pending
                                prev_results = prev_future.result()
                                for i, info in enumerate(data_var_infos):
                                    dst_data_vars[info["src_name"]][prev_start:prev_end, :, :] = prev_results[i]
                            pending = (start, end, future)

                        if pending is not None:
                            prev_start, prev_end, prev_future = pending
                            prev_results = prev_future.result()
                            for i, info in enumerate(data_var_infos):
                                dst_data_vars[info["src_name"]][prev_start:prev_end, :, :] = prev_results[i]
                else:
                    # 顺序分块
                    # [EN] Sequential chunking
                    for start in range(0, n_time, chunk_time):
                        end = min(start + chunk_time, n_time)
                        chunk_index = start // chunk_time + 1
                        if chunk_index == 1 or chunk_index == total_chunks or chunk_index % progress_log_interval == 0:
                            self._emit(
                                log,
                                tr("step1_debug_chunk_progress", "🔍 [调试] 正在处理分块 {current}/{total}（time: {start}~{end}）").format(
                                    current=chunk_index, total=total_chunks, start=start, end=end - 1,
                                ),
                            )
                        for info in data_var_infos:
                            src_var = src.variables[info["src_name"]]
                            slices = _make_read_slices(info["shape"], start, end)
                            chunk_data = np.asarray(src_var[slices])
                            dst_data_vars[info["src_name"]][start:end, :, :] = _transform_chunk(
                                chunk_data, len(info["shape"])
                            )

                # ── 复制非坐标非强迫场的变量（如 depth、crs 等）──────────
                # [EN] Copy non-coordinate, non-forcing variables (e.g., depth, crs)
                coord_names = {lon_name, lat_name, time_name}
                forcing_src_names = {info["src_name"] for info in data_var_infos}
                skip_names = coord_names | forcing_src_names

                for var_name in all_src_var_names:
                    if var_name in skip_names:
                        continue
                    src_var = src.variables[var_name]
                    try:
                        # 映射维度名（坐标维度映射到输出名；其余保持）
                        # [EN] Map dimension names (coordinates → output names; others kept)
                        mapped_dims = []
                        for d in src_var.dimensions:
                            if d == lon_name:
                                mapped_dims.append(_WW3_LON_NAME)
                            elif d == lat_name:
                                mapped_dims.append(_WW3_LAT_NAME)
                            elif d == time_name:
                                mapped_dims.append(output_time)
                            else:
                                mapped_dims.append(d)
                        mapped_dims = tuple(mapped_dims)

                        dst_var = dst.createVariable(var_name, src_var.dtype, mapped_dims)
                        # 复制属性
                        # [EN] Copy attributes
                        for attr in src_var.ncattrs():
                            try:
                                dst_var.setncattr(attr, src_var.getncattr(attr))
                            except Exception:
                                pass
                        # 复制数据
                        # [EN] Copy data
                        try:
                            dst_var[:] = src_var[:]
                        except Exception:
                            pass
                    except Exception:
                        pass

                # ── 设置坐标与时间标准属性 ──────────────────────────────
                # [EN] Set standard attributes for coordinates and time
                lon_var.description = "LONGITUDE, WEST IS NEGATIVE"
                lon_var.units = "degree_east"

                lat_var.description = "LATITUDE, SOUTH IS NEGATIVE"
                lat_var.units = "degree_north"

                time_var.standard_name = "time"
                time_var.long_name = "time"
                ww3_units = normalize_time_units_for_ww3(str(original_time_units or ""))
                if not ww3_units:
                    raise ValueError(
                        tr("forcing_time_issue_missing_units", "⚠️ time 变量缺少 units 属性")
                    )
                time_var.units = ww3_units
                ww3_calendar = normalize_calendar_for_ww3(original_time_calendar)
                if not ww3_calendar:
                    raise ValueError(
                        tr(
                            "forcing_time_issue_unsupported_calendar",
                            "⚠️ 不支持的日历类型：{calendar}（WW3 仅支持 standard/gregorian/360_day；noleap 等无法在不转换时间数值的前提下安全导入）",
                        ).format(calendar=original_time_calendar)
                    )
                time_var.calendar = ww3_calendar

            os.replace(temp_output_path, output_file)
            self._emit(
                log,
                tr("forcing_normalize_complete", "✅ 强迫场标准化完成并保存至: {path}").format(path=output_file),
            )
            return True

        except Exception as exc:
            try:
                if "temp_output_path" in locals() and os.path.exists(temp_output_path):
                    os.remove(temp_output_path)
            except Exception:
                pass
            self._emit(log, tr("log_write_file_failed", "❌ 写入新文件失败") + f": {exc}\n{traceback.format_exc()}")
            return False

    @staticmethod
    def _collect_resolved_variables(
        source_file: str,
        variables: Optional[object],
    ) -> List[ResolvedForcingVariables]:
        """把传入的解析结果规范化为列表；为 ``None`` 时自动解析全部场。

        [EN] Normalize passed-in resolution results to a list; when ``None``,
        auto-resolve all fields.
        """
        if variables is None:
            resolved_map = resolve_all_fields(source_file)
            return list(resolved_map.values())
        if isinstance(variables, ResolvedForcingVariables):
            return [variables]
        return [v for v in variables if isinstance(v, ResolvedForcingVariables)]

    @staticmethod
    def _emit(log: Optional[Callable[[str], None]], message: str) -> None:
        """若提供 log 回调则输出一条消息。

        [EN] Emit a message if a log callback is provided.
        """
        if log is not None:
            log(message)


# ── 向后兼容 ──────────────────────────────────────────────────────
# [EN] Backward compatibility
WindNormalizeService = ForcingNormalizeService
