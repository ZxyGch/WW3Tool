"""WW3 Step 1 强迫场 NetCDF 归一化服务。

[EN] WW3 Step 1 forcing field NetCDF normalization service.

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
from concurrent.futures import ProcessPoolExecutor
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from netCDF4 import Dataset

from ...support.translations import tr


# ── 强迫场变量名候选列表 → 标准名映射 ──────────────────────────────
# [EN] Forcing variable name candidates → standard name mapping

_WIND_U_CANDIDATES = [
    "u10", "U10", "wndewd", "WNDEWD", "eastward_wind",
    "u", "uwnd", "UWND", "uwnd10m", "UWND10M",
]
_WIND_V_CANDIDATES = [
    "v10", "V10", "wndnwd", "WNDNWD", "northward_wind",
    "v", "vwnd", "VWND", "vwnd10m", "VWND10M",
]
_CURRENT_U_CANDIDATES = ["uo", "UO"]
_CURRENT_V_CANDIDATES = ["vo", "VO"]
_LEVEL_CANDIDATES = ["zos", "ZOS"]
_ICE_CANDIDATES = ["siconc", "SICONC"]

_LON_CANDIDATES = ["longitude", "lon", "LONGITUDE", "LON", "Longitude"]
_LAT_CANDIDATES = ["latitude", "lat", "LATITUDE", "LAT", "Latitude"]
_TIME_CANDIDATES = ["valid_time", "time", "Time", "TIME", "t", "MT", "mt"]


def _transform_chunks_for_pool(chunks, lat_needs_flip, lat_axis, lon_needs_flip, lon_axis):
    """多进程池用通用数组变换：纬度/经度翻转并确保 C 连续。

    [EN] Generic array transform for multiprocessing pool: lat/lon flip
    and ensure C-contiguous.
    """
    results = []
    for chunk in chunks:
        chunk = np.asarray(chunk)
        changed = False
        if lat_needs_flip and lat_axis is not None:
            chunk = np.flip(chunk, axis=lat_axis)
            changed = True
        if lon_needs_flip and lon_axis is not None:
            chunk = np.flip(chunk, axis=lon_axis)
            changed = True
        results.append(np.ascontiguousarray(chunk) if changed else chunk)
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


def _pick_var_name(src_variables, candidates):
    """从 NetCDF 变量字典中按候选列表顺序匹配第一个存在的变量名。"""
    for name in candidates:
        if name in src_variables:
            return name
    return None


def _detect_forcing_var_map(src_variables) -> Dict[str, Tuple[str, str]]:
    """检测源文件中的强迫场变量，返回 ``{标准名: (源变量名, 场类型)}`` 映射。

    [EN] Detect forcing variables in source, returning
    ``{standard_name: (source_name, field_type)}`` mapping.
    """
    var_map: Dict[str, Tuple[str, str]] = {}

    u_name = _pick_var_name(src_variables, _WIND_U_CANDIDATES)
    v_name = _pick_var_name(src_variables, _WIND_V_CANDIDATES)
    if u_name and v_name:
        var_map["u10"] = (u_name, "wind")
        var_map["v10"] = (v_name, "wind")

    cu = _pick_var_name(src_variables, _CURRENT_U_CANDIDATES)
    cv = _pick_var_name(src_variables, _CURRENT_V_CANDIDATES)
    if cu and cv:
        var_map["uo"] = (cu, "current")
        var_map["vo"] = (cv, "current")

    zos_name = _pick_var_name(src_variables, _LEVEL_CANDIDATES)
    if zos_name:
        var_map["zos"] = (zos_name, "level")

    ice_name = _pick_var_name(src_variables, _ICE_CANDIDATES)
    if ice_name:
        var_map["siconc"] = (ice_name, "ice")

    return var_map


class ForcingNormalizeService:
    """将强迫场 NetCDF 归一化为 WW3 标准布局的服务类。

    [EN] Service class for normalizing forcing field NetCDF into the WW3 standard layout.
    """

    def normalize(
        self,
        source_file: str,
        output_file: str,
        log: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """读取源文件并写出归一化后的强迫场 NetCDF。

        [EN] Read the source file and write the normalized forcing NetCDF.

        参数:
            source_file: 原始 NetCDF 路径
            output_file: 目标路径
            log: 可选进度/诊断日志回调

        返回:
            成功写入为 ``True``，失败为 ``False``
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
        try:
            with Dataset(source_file, "r") as src:
                src.set_auto_mask(False)

                lon_name = _pick_var_name(src.variables, _LON_CANDIDATES)
                lat_name = _pick_var_name(src.variables, _LAT_CANDIDATES)
                time_name = _pick_var_name(src.variables, _TIME_CANDIDATES)

                if not lon_name:
                    raise KeyError(tr("log_lon_var_not_found", "❌ 未找到经度变量（longitude/lon/Longitude）"))
                if not lat_name:
                    raise KeyError(tr("log_lat_var_not_found", "❌ 未找到纬度变量（latitude/lat/Latitude）"))
                if not time_name:
                    raise KeyError(tr("log_time_var_not_found", "❌ 未找到时间变量（valid_time/time/MT）"))

                longitude = np.asarray(src.variables[lon_name][:])
                latitude = np.asarray(src.variables[lat_name][:])
                time_var_obj = src.variables[time_name]
                time_data = np.asarray(time_var_obj[:])

                original_time_units = getattr(time_var_obj, "units", None)
                original_time_calendar = getattr(time_var_obj, "calendar", "gregorian")

                # 检测强迫场变量
                forcing_var_map = _detect_forcing_var_map(src.variables)
                if not forcing_var_map:
                    raise KeyError(
                        tr(
                            "forcing_vars_not_found",
                            "❌ 未检测到强迫场变量（u10/v10, uo/vo, zos, siconc）",
                        )
                    )

                # 收集所有数据变量的信息
                data_var_infos = []
                for std_name, (src_name, field_type) in forcing_var_map.items():
                    src_var = src.variables[src_name]
                    shape = src_var.shape
                    dims = list(src_var.dimensions) if hasattr(src_var, "dimensions") else None
                    dtype = src_var.dtype

                    def _snapshot_filters(var_obj):
                        try:
                            if hasattr(var_obj, "filters"):
                                return var_obj.filters()
                        except Exception:
                            pass
                        return None

                    data_var_infos.append({
                        "std_name": std_name,
                        "src_name": src_name,
                        "field_type": field_type,
                        "shape": shape,
                        "dims": dims,
                        "dtype": dtype,
                        "filters": _snapshot_filters(src_var),
                    })

                # 以第一个数据变量为基准确定维度顺序
                primary = data_var_infos[0]
                primary_shape = primary["shape"]
                primary_dims = primary["dims"]

                if len(primary_shape) < 2:
                    raise ValueError(
                        tr("log_data_dim_unsupported", "❌ 数据维度不受支持：{shape}").format(shape=primary_shape)
                    )

                # 推断 time/lat/lon 在数据数组中的维度索引
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

                # 输出维度顺序
                _std_names_map = {time_dim_idx: "time", lat_dim_idx: "latitude", lon_dim_idx: "longitude"}
                output_dim_order = [_std_names_map[i] for i in sorted(_std_names_map.keys())]

                lon_dtype = src.variables[lon_name].dtype
                lat_dtype = src.variables[lat_name].dtype
                time_dtype = time_var_obj.dtype

                # 记录所有源变量名（用于后续全量复制）
                all_src_var_names = list(src.variables.keys())

        except Exception as exc:
            self._emit(log, tr("log_read_origin_failed", "❌ 读取原始文件失败: {error}").format(error=exc))
            return False

        # ── 经度递减检查：统一拒绝 ────────────────────────────────────
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
        lat_needs_flip = len(latitude) > 1 and latitude[0] > latitude[-1]
        if lat_needs_flip:
            latitude = latitude[::-1]

        # ── 短路判断 ────────────────────────────────────────────────────
        needs_rename = (
            lon_name.lower() != "longitude"
            or lat_name.lower() != "latitude"
            or time_name.lower() != "time"
            or any(std != info["src_name"] for std, info in forcing_var_map.items())
        )

        try:
            same_target_file = os.path.samefile(source_file, output_file)
        except OSError:
            same_target_file = False

        if (
            same_target_file
            and not lat_needs_flip
            and not needs_rename
        ):
            self._emit(log, tr("forcing_already_normalized", "✅ 文件已是标准格式: {path}").format(path=output_file))
            return True

        # ── 分块策略 ────────────────────────────────────────────────────
        n_time = len(time_data)
        n_lat = len(latitude)
        n_lon = len(longitude)
        points_per_step = max(1, n_lat * n_lon)

        # 估算总数据量（所有数据变量）
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
        )
        total_chunks = max(1, (n_time + chunk_time - 1) // chunk_time)
        progress_log_interval = 1 if total_chunks <= 12 else max(1, total_chunks // 8)

        def _build_chunksizes(dtype):
            plane_bytes = max(1, n_lat * n_lon * np.dtype(dtype).itemsize)
            target_storage = 16 * 1024 * 1024
            tc = max(1, min(n_time, target_storage // plane_bytes))
            tc = min(tc, 16)
            size_map = {"time": tc, "latitude": n_lat, "longitude": n_lon}
            return tuple(size_map[d] for d in output_dim_order)

        def _transform_chunk(chunk, ndim):
            """本地翻转：对 time-lat-lon 3D 数据翻转 lat/lon 轴。"""
            chunk = np.asarray(chunk)
            changed = False
            if lat_needs_flip and ndim >= 2:
                # lat 轴在 3D 中通常是 -2
                lat_ax = ndim - 2 if ndim >= 2 else None
                if lat_ax is not None:
                    chunk = np.flip(chunk, axis=lat_ax)
                    changed = True
            return np.ascontiguousarray(chunk) if changed else chunk

        # ── Phase 2: 写出标准化文件 ─────────────────────────────────────
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
                for attr_name in src.ncattrs():
                    try:
                        dst.setncattr(attr_name, src.getncattr(attr_name))
                    except Exception:
                        pass

                # 创建标准化维度
                dst.createDimension("longitude", n_lon)
                dst.createDimension("latitude", n_lat)
                dst.createDimension("time", n_time)
                # 复制源文件中其他维度（如 depth 等）
                for dim_name, dim_obj in src.dimensions.items():
                    std_dim = {"longitude": "longitude", "latitude": "latitude", "time": "time"}.get(
                        lon_name if dim_name == lon_name else (
                            lat_name if dim_name == lat_name else (
                                time_name if dim_name == time_name else dim_name
                            )
                        ),
                        dim_name,
                    )
                    if std_dim in ("longitude", "latitude", "time"):
                        continue
                    if std_dim not in dst.dimensions:
                        dst.createDimension(std_dim, len(dim_obj) if not dim_obj.isunlimited() else None)

                # 创建坐标变量
                lon_var = dst.createVariable("longitude", lon_dtype, ("longitude",))
                lat_var = dst.createVariable("latitude", lat_dtype, ("latitude",))
                time_var = dst.createVariable("time", time_dtype, ("time",))

                # 创建数据变量
                def _build_var_kwargs(filters, chunksizes):
                    kwargs = {"fill_value": -32767.0}
                    try:
                        if filters and filters.get("zlib"):
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
                    dst_data_vars[info["std_name"]] = _create_data_var(
                        info["std_name"], info["dtype"], info["filters"], cs
                    )

                # 写入坐标
                lon_var[:] = longitude
                lat_var[:] = latitude

                # 时间：保留原始值与单位（WW3 ww3_prnc 按 CF 约定自行解析）
                # [EN] Time: preserve original values and units (WW3 ww3_prnc parses via CF conventions)
                time_var[:] = time_data

                # ── 写入数据变量 ────────────────────────────────────────
                # 对每个数据变量构建读取切片
                def _make_read_slices(src_var_shape, start, end):
                    slices = [slice(None)] * len(src_var_shape)
                    # 找到时间维度索引（在该变量的维度中）
                    if len(src_var_shape) >= 3:
                        slices[time_dim_idx] = slice(start, end)
                    return tuple(slices)

                if use_full_load:
                    for info in data_var_infos:
                        src_var = src.variables[info["src_name"]]
                        data = np.asarray(src_var[:])
                        dst_data_vars[info["std_name"]][:] = _transform_chunk(data, len(info["shape"]))

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
                            chunks = []
                            for info in data_var_infos:
                                src_var = src.variables[info["src_name"]]
                                slices = _make_read_slices(info["shape"], start, end)
                                chunks.append(np.asarray(src_var[slices]))

                            # 计算该变量数组中 lat/lon 的轴位置
                            ndim = len(data_var_infos[0]["shape"])
                            lat_ax = lat_dim_idx if lat_dim_idx is not None else (ndim - 2 if ndim >= 2 else None)
                            lon_ax = lon_dim_idx if lon_dim_idx is not None else (ndim - 1 if ndim >= 1 else None)

                            future = executor.submit(
                                _transform_chunks_for_pool,
                                chunks, lat_needs_flip, lat_ax, False, lon_ax,  # lon_needs_flip=False (已拒绝)
                            )
                            if pending is not None:
                                prev_start, prev_end, prev_future = pending
                                prev_results = prev_future.result()
                                for i, info in enumerate(data_var_infos):
                                    dst_data_vars[info["std_name"]][prev_start:prev_end, :, :] = prev_results[i]
                            pending = (start, end, future)

                        if pending is not None:
                            prev_start, prev_end, prev_future = pending
                            prev_results = prev_future.result()
                            for i, info in enumerate(data_var_infos):
                                dst_data_vars[info["std_name"]][prev_start:prev_end, :, :] = prev_results[i]
                else:
                    # 顺序分块
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
                            dst_data_vars[info["std_name"]][start:end, :, :] = _transform_chunk(
                                chunk_data, len(info["shape"])
                            )

                # ── 复制非坐标非强迫场的变量（如 depth、crs 等）──────────
                coord_names = {lon_name, lat_name, time_name}
                forcing_src_names = {info["src_name"] for info in data_var_infos}
                skip_names = coord_names | forcing_src_names

                for var_name in all_src_var_names:
                    if var_name in skip_names:
                        continue
                    src_var = src.variables[var_name]
                    try:
                        # 映射维度名
                        mapped_dims = []
                        for d in src_var.dimensions:
                            if d == lon_name:
                                mapped_dims.append("longitude")
                            elif d == lat_name:
                                mapped_dims.append("latitude")
                            elif d == time_name:
                                mapped_dims.append("time")
                            else:
                                mapped_dims.append(d)
                        mapped_dims = tuple(mapped_dims)

                        dst_var = dst.createVariable(var_name, src_var.dtype, mapped_dims)
                        # 复制属性
                        for attr in src_var.ncattrs():
                            try:
                                dst_var.setncattr(attr, src_var.getncattr(attr))
                            except Exception:
                                pass
                        # 复制数据
                        try:
                            dst_var[:] = src_var[:]
                        except Exception:
                            pass
                    except Exception:
                        pass

                # ── 设置标准属性 ────────────────────────────────────────
                lon_var.description = "LONGITUDE, WEST IS NEGATIVE"
                lon_var.units = "degree_east"

                lat_var.description = "LATITUDE, SOUTH IS NEGATIVE"
                lat_var.units = "degree_north"

                time_var.standard_name = "time"
                time_var.long_name = "time"
                if original_time_units:
                    time_var.units = original_time_units
                if original_time_calendar:
                    time_var.calendar = original_time_calendar

                # 设置强迫场变量属性
                _VAR_ATTRS = {
                    "u10": {"description": "10 meters wind speed u", "units": "m/s", "level": "10m"},
                    "v10": {"description": "10 meters wind speed v", "units": "m/s", "level": "10m"},
                    "uo": {"description": "sea water x velocity", "units": "m/s"},
                    "vo": {"description": "sea water y velocity", "units": "m/s"},
                    "zos": {"description": "sea surface height above geoid", "units": "m"},
                    "siconc": {"description": "sea ice concentration", "units": "1"},
                }
                for std_name, dst_var in dst_data_vars.items():
                    attrs = _VAR_ATTRS.get(std_name, {})
                    for k, v in attrs.items():
                        try:
                            setattr(dst_var, k, v)
                        except Exception:
                            pass

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
            self._emit(log, tr("log_write_file_failed", "❌ 写入新文件失败") + f": {exc}")
            return False

    @staticmethod
    def _emit(log: Optional[Callable[[str], None]], message: str) -> None:
        """若提供 log 回调则输出一条消息。"""
        if log is not None:
            log(message)


# ── 向后兼容 ──────────────────────────────────────────────────────
WindNormalizeService = ForcingNormalizeService
