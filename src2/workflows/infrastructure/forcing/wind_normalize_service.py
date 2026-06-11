"""WW3 Step 1 风场 NetCDF 归一化服务。

从桌面端 Step 1 逻辑抽取，将各类再分析/预报风场统一转换为 WW3 ``ww3_prnc``
可读格式，主要处理：

- 维度顺序统一为 ``(time, latitude, longitude)``；
- 经纬度变量名标准化，必要时翻转 lat/lon 递增方向；
- 东/北风分量统一命名为 ``u10/v10``；
- 时间轴转为 ``seconds since 1970-01-01``；
- 大文件分块或并行变换以控制内存占用。
"""

from __future__ import annotations

import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from typing import Callable, Optional

import numpy as np
from netCDF4 import Dataset, num2date

from ...support.translations import tr


def _transform_wind_chunks_for_pool(
    u10_chunk,
    v10_chunk,
    transpose_order,
    lat_needs_flip,
    lon_needs_flip,
):
    """多进程池用的纯数组变换：转置、纬向/经向翻转并保证 C 连续。"""

    def _transform(chunk):
        chunk = np.asarray(chunk)
        changed = False
        if transpose_order is not None:
            chunk = np.transpose(chunk, transpose_order)
            changed = True
        if lat_needs_flip:
            chunk = chunk[:, ::-1, :]
            changed = True
        if lon_needs_flip:
            chunk = chunk[:, :, ::-1]
            changed = True
        return np.ascontiguousarray(chunk) if changed else chunk

    return _transform(u10_chunk), _transform(v10_chunk)


def _get_available_memory_bytes() -> int:
    """尽力检测当前可用物理内存（字节），用于分块大小决策。"""
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
            match = re.match(r"^([^:]+):\s+([0-9]+)\.$", line.strip())
            if match:
                pages[match.group(1)] = int(match.group(2))

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


class WindNormalizeService:
    """将风场 NetCDF 归一化为 WW3 标准布局的服务类。"""

    def normalize(
        self,
        source_file: str,
        output_file: str,
        log: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """读取源文件并写出归一化后的风场 NetCDF。

        参数:
            source_file: 原始 NetCDF 路径
            output_file: 目标路径（通常为工作目录下的 ``wind.nc``）
            log: 可选进度/诊断日志回调

        返回:
            成功写入为 ``True``，读取或写入失败为 ``False``
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

        try:
            with Dataset(source_file, "r") as src:
                src.set_auto_mask(False)

                def _pick_var_name(candidates):
                    for name in candidates:
                        if name in src.variables:
                            return name
                    return None

                lon_name = _pick_var_name(["longitude", "lon", "LONGITUDE", "LON", "Longitude"])
                lat_name = _pick_var_name(["latitude", "lat", "LATITUDE", "LAT", "Latitude"])
                time_name = _pick_var_name(["valid_time", "time", "Time", "TIME", "t", "MT", "mt"])

                if not lon_name:
                    raise KeyError(tr("log_lon_var_not_found", "未找到经度变量（longitude/lon/Longitude）"))
                if not lat_name:
                    raise KeyError(tr("log_lat_var_not_found", "未找到纬度变量（latitude/lat/Latitude）"))
                if not time_name:
                    raise KeyError(tr("log_time_var_not_found", "未找到时间变量（valid_time/time/MT）"))

                longitude = np.asarray(src.variables[lon_name][:])
                latitude = np.asarray(src.variables[lat_name][:])
                time_var_obj = src.variables[time_name]
                time = np.asarray(time_var_obj[:])

                original_time_units = getattr(time_var_obj, "units", None)
                original_time_calendar = getattr(time_var_obj, "calendar", "gregorian")

                u10_name = _pick_var_name(
                    [
                        "u10",
                        "U10",
                        "wndewd",
                        "WNDEWD",
                        "eastward_wind",
                        "u",
                        "uwnd",
                        "UWND",
                        "uwnd10m",
                        "UWND10M",
                    ]
                )
                v10_name = _pick_var_name(
                    [
                        "v10",
                        "V10",
                        "wndnwd",
                        "WNDNWD",
                        "northward_wind",
                        "v",
                        "vwnd",
                        "VWND",
                        "vwnd10m",
                        "VWND10M",
                    ]
                )

                if not u10_name:
                    raise KeyError(tr("log_u10_var_not_found", "未找到东向风变量（u10/wndewd/uwnd）"))
                if not v10_name:
                    raise KeyError(tr("log_v10_var_not_found", "未找到北向风变量（v10/wndnwd/vwnd）"))

                src_u10_var = src.variables[u10_name]
                src_v10_var = src.variables[v10_name]
                u10_shape = src_u10_var.shape
                u10_dims = src_u10_var.dimensions if hasattr(src_u10_var, "dimensions") else None

                transpose_order = None
                time_dim_idx = 0
                lat_dim_idx = 1
                lon_dim_idx = 2

                if len(u10_shape) != 3:
                    raise ValueError(
                        tr("log_data_dim_unsupported", "风场数据维度不受支持：{shape}").format(shape=u10_shape)
                    )

                if u10_dims:
                    time_dim_idx = None
                    lat_dim_idx = None
                    lon_dim_idx = None

                    for index, dim_name in enumerate(u10_dims):
                        if dim_name == time_name or time_name in dim_name or dim_name in time_name:
                            time_dim_idx = index
                        elif dim_name == lat_name or lat_name in dim_name or dim_name in lat_name:
                            lat_dim_idx = index
                        elif dim_name == lon_name or lon_name in dim_name or dim_name in lon_name:
                            lon_dim_idx = index

                    if time_dim_idx is not None and lat_dim_idx is not None and lon_dim_idx is not None:
                        if not (time_dim_idx == 0 and lat_dim_idx == 1 and lon_dim_idx == 2):
                            transpose_order = [time_dim_idx, lat_dim_idx, lon_dim_idx]
                            self._emit(
                                log,
                                tr(
                                    "log_dim_order_transposed",
                                    "🔄 检测到维度顺序为 {dims}，已转置为 (time, lat, lon)",
                                ).format(dims=u10_dims),
                            )
                else:
                    if u10_shape[1] == len(latitude) and u10_shape[2] == len(longitude):
                        time_dim_idx, lat_dim_idx, lon_dim_idx = 0, 1, 2
                    elif u10_shape[1] == len(longitude) and u10_shape[2] == len(latitude):
                        time_dim_idx, lat_dim_idx, lon_dim_idx = 0, 2, 1
                        transpose_order = (0, 2, 1)
                        self._emit(
                            log,
                            tr(
                                "log_dim_order_tlonlat",
                                "🔄 检测到维度顺序为 (time, lon, lat)，已转置为 (time, lat, lon)",
                            ),
                        )
                    else:
                        raise ValueError(
                            tr(
                                "log_dim_order_uncertain",
                                "⚠️ 警告：无法确定维度顺序！数据形状={shape}, 纬度长度={lat_len}, 经度长度={lon_len}",
                            ).format(shape=u10_shape, lat_len=len(latitude), lon_len=len(longitude))
                        )

                expected_lat_len = u10_shape[lat_dim_idx] if lat_dim_idx is not None else None
                expected_lon_len = u10_shape[lon_dim_idx] if lon_dim_idx is not None else None
                if expected_lat_len is not None and expected_lat_len != len(latitude):
                    self._emit(
                        log,
                        tr(
                            "log_lat_dim_mismatch",
                            "⚠️ 警告：数据纬度维度 ({expected}) 与纬度变量长度 ({actual}) 不匹配！",
                        ).format(expected=expected_lat_len, actual=len(latitude)),
                    )
                if expected_lon_len is not None and expected_lon_len != len(longitude):
                    self._emit(
                        log,
                        tr(
                            "log_lon_dim_mismatch",
                            "⚠️ 警告：数据经度维度 ({expected}) 与经度变量长度 ({actual}) 不匹配！",
                        ).format(expected=expected_lon_len, actual=len(longitude)),
                    )

                lon_dtype = src.variables[lon_name].dtype
                lat_dtype = src.variables[lat_name].dtype
                time_dtype = time_var_obj.dtype
                u10_dtype = src_u10_var.dtype
                v10_dtype = src_v10_var.dtype

                def _snapshot_filters(var_obj):
                    try:
                        if hasattr(var_obj, "filters"):
                            return var_obj.filters()
                    except Exception:
                        pass
                    return None

                u10_filters = _snapshot_filters(src_u10_var)
                v10_filters = _snapshot_filters(src_v10_var)

                if time_dim_idx is None or lat_dim_idx is None or lon_dim_idx is None:
                    raise ValueError(
                        tr(
                            "log_dim_order_uncertain",
                            "⚠️ 警告：无法确定维度顺序！数据形状={shape}, 纬度长度={lat_len}, 经度长度={lon_len}",
                        ).format(shape=u10_shape, lat_len=len(latitude), lon_len=len(longitude))
                    )

        except Exception as exc:
            self._emit(log, tr("log_read_origin_failed", "❌ 读取原始文件失败: {error}").format(error=exc))
            return False

        lon_needs_flip = len(longitude) > 1 and longitude[0] > longitude[-1]
        lat_needs_flip = len(latitude) > 1 and latitude[0] > latitude[-1]

        if lon_needs_flip:
            longitude = longitude[::-1]
        if lat_needs_flip:
            latitude = latitude[::-1]

        needs_standardize = (
            lon_name.lower() != "longitude"
            or lat_name.lower() != "latitude"
            or time_name.lower() != "time"
            or u10_name.lower() != "u10"
            or v10_name.lower() != "v10"
        )
        time_units_standard = bool(original_time_units) and (
            original_time_units.strip().lower() == "seconds since 1970-01-01"
        )

        try:
            same_target_file = os.path.samefile(source_file, output_file)
        except OSError:
            same_target_file = False

        if (
            same_target_file
            and not lon_needs_flip
            and not lat_needs_flip
            and transpose_order is None
            and not needs_standardize
            and time_units_standard
        ):
            self._emit(log, tr("lat_flip_complete", "✅ 已完成纬度重排并保存至: {path}").format(path=output_file))
            return True

        def _transform_chunk_local(chunk):
            chunk = np.asarray(chunk)
            changed = False
            if transpose_order is not None:
                chunk = np.transpose(chunk, transpose_order)
                changed = True
            if lat_needs_flip:
                chunk = chunk[:, ::-1, :]
                changed = True
            if lon_needs_flip:
                chunk = chunk[:, :, ::-1]
                changed = True
            return np.ascontiguousarray(chunk) if changed else chunk

        points_per_step = max(1, len(latitude) * len(longitude))
        bytes_per_value = max(np.dtype(u10_dtype).itemsize, np.dtype(v10_dtype).itemsize)
        bytes_per_step_pair = points_per_step * bytes_per_value * 2
        estimated_total_bytes = len(time) * points_per_step * bytes_per_value * 2
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

        chunk_time = max(1, min(len(time), target_chunk_bytes // max(1, bytes_per_step_pair)))
        chunk_time = min(chunk_time, 256)
        max_workers = min(2, max(1, (os.cpu_count() or 1) - 1))
        try:
            file_size_bytes = os.path.getsize(source_file)
        except OSError:
            file_size_bytes = 0

        use_full_load_transform = estimated_total_bytes <= full_load_threshold_bytes
        use_parallel_transform = (
            not use_full_load_transform
            and len(time) >= 96
            and len(time) > chunk_time
            and max(1, (len(time) + chunk_time - 1) // chunk_time) >= 8
            and max_workers > 1
            and file_size_bytes >= 2 * 1024 * 1024 * 1024
            and points_per_step <= 300000
        )
        transform_order = tuple(transpose_order) if transpose_order is not None else None
        total_chunks = max(1, (len(time) + chunk_time - 1) // chunk_time)
        progress_log_interval = 1 if total_chunks <= 12 else max(1, total_chunks // 8)

        def _build_time_major_chunksizes(dtype):
            plane_bytes = max(1, len(latitude) * len(longitude) * np.dtype(dtype).itemsize)
            target_storage_chunk_bytes = 16 * 1024 * 1024
            time_chunk = max(1, min(len(time), target_storage_chunk_bytes // plane_bytes))
            time_chunk = min(time_chunk, 16)
            return (time_chunk, len(latitude), len(longitude))

        output_u10_chunksizes = _build_time_major_chunksizes(u10_dtype)
        output_v10_chunksizes = _build_time_major_chunksizes(v10_dtype)

        try:
            temp_output_path = output_file + ".reorder_tmp"
            if os.path.exists(temp_output_path):
                os.remove(temp_output_path)

            with Dataset(source_file, "r") as src, Dataset(temp_output_path, "w", format="NETCDF4") as dst:
                src.set_auto_mask(False)
                try:
                    dst.set_fill_off()
                except Exception:
                    pass

                src_u10_var = src.variables[u10_name]
                src_v10_var = src.variables[v10_name]
                dst.createDimension("longitude", len(longitude))
                dst.createDimension("latitude", len(latitude))
                dst.createDimension("time", len(time))

                lon_var = dst.createVariable("longitude", lon_dtype, ("longitude",))
                lat_var = dst.createVariable("latitude", lat_dtype, ("latitude",))
                time_var = dst.createVariable("time", time_dtype, ("time",))

                def _build_var_kwargs_from_filters(filters, output_chunksizes):
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
                            if output_chunksizes is not None:
                                kwargs["chunksizes"] = output_chunksizes
                            if filters.get("least_significant_digit") is not None:
                                kwargs["least_significant_digit"] = filters["least_significant_digit"]
                    except Exception:
                        pass
                    return kwargs

                def _create_data_var(name, dtype, cached_filters, output_chunksizes):
                    try:
                        return dst.createVariable(
                            name,
                            dtype,
                            ("time", "latitude", "longitude"),
                            **_build_var_kwargs_from_filters(cached_filters, output_chunksizes),
                        )
                    except Exception:
                        return dst.createVariable(
                            name,
                            dtype,
                            ("time", "latitude", "longitude"),
                            fill_value=-32767.0,
                        )

                u10_var = _create_data_var("u10", u10_dtype, u10_filters, output_u10_chunksizes)
                v10_var = _create_data_var("v10", v10_dtype, v10_filters, output_v10_chunksizes)

                lon_var[:] = longitude
                lat_var[:] = latitude

                if original_time_units:
                    target_units = "seconds since 1970-01-01"
                    if original_time_units.strip().lower() == target_units.lower():
                        time_var[:] = time
                    else:
                        try:
                            time_datetimes = num2date(time, original_time_units, calendar=original_time_calendar)
                            if hasattr(time_datetimes, "compressed"):
                                time_datetimes = time_datetimes.compressed()
                            epoch = datetime(1970, 1, 1)
                            time_seconds = [(dt - epoch).total_seconds() for dt in time_datetimes]
                            time_var[:] = time_seconds
                            self._emit(
                                log,
                                tr(
                                    "log_time_units_convert",
                                    "🔄 时间单位已从 '{old}' 转换为 'seconds since 1970-01-01'",
                                ).format(old=original_time_units),
                            )
                        except Exception as exc:
                            time_var[:] = time
                            self._emit(
                                log,
                                tr(
                                    "log_time_units_convert_failed",
                                    "⚠️ 时间单位转换失败，使用原始值: {error}",
                                ).format(error=exc),
                            )
                else:
                    time_var[:] = time

                if use_full_load_transform:
                    u10_var[:] = _transform_chunk_local(src_u10_var[:])
                    v10_var[:] = _transform_chunk_local(src_v10_var[:])
                elif use_parallel_transform:
                    self._emit(
                        log,
                        tr("log_parallel_chunk_transform", "🔄 已启用并行分块处理（{workers} 个进程）").format(
                            workers=max_workers
                        ),
                    )
                    ctx = multiprocessing.get_context("spawn")
                    with ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx) as executor:
                        pending = None
                        for start in range(0, len(time), chunk_time):
                            end = min(start + chunk_time, len(time))
                            chunk_index = start // chunk_time + 1
                            if (
                                chunk_index == 1
                                or chunk_index == total_chunks
                                or chunk_index % progress_log_interval == 0
                            ):
                                self._emit(
                                    log,
                                    tr(
                                        "step1_debug_chunk_progress",
                                        "🔍 [调试] 正在处理分块 {current}/{total}（time: {start}~{end}）",
                                    ).format(
                                        current=chunk_index,
                                        total=total_chunks,
                                        start=start,
                                        end=end - 1,
                                    ),
                                )

                            read_slices = [slice(None)] * len(u10_shape)
                            read_slices[time_dim_idx] = slice(start, end)
                            u10_chunk = np.asarray(src_u10_var[tuple(read_slices)])
                            v10_chunk = np.asarray(src_v10_var[tuple(read_slices)])
                            future = executor.submit(
                                _transform_wind_chunks_for_pool,
                                u10_chunk,
                                v10_chunk,
                                transform_order,
                                lat_needs_flip,
                                lon_needs_flip,
                            )
                            if pending is not None:
                                prev_start, prev_end, prev_future = pending
                                prev_u10, prev_v10 = prev_future.result()
                                u10_var[prev_start:prev_end, :, :] = prev_u10
                                v10_var[prev_start:prev_end, :, :] = prev_v10
                            pending = (start, end, future)

                        if pending is not None:
                            prev_start, prev_end, prev_future = pending
                            prev_u10, prev_v10 = prev_future.result()
                            u10_var[prev_start:prev_end, :, :] = prev_u10
                            v10_var[prev_start:prev_end, :, :] = prev_v10
                else:
                    for start in range(0, len(time), chunk_time):
                        end = min(start + chunk_time, len(time))
                        chunk_index = start // chunk_time + 1
                        if (
                            chunk_index == 1
                            or chunk_index == total_chunks
                            or chunk_index % progress_log_interval == 0
                        ):
                            self._emit(
                                log,
                                tr(
                                    "step1_debug_chunk_progress",
                                    "🔍 [调试] 正在处理分块 {current}/{total}（time: {start}~{end}）",
                                ).format(
                                    current=chunk_index,
                                    total=total_chunks,
                                    start=start,
                                    end=end - 1,
                                ),
                            )
                        read_slices = [slice(None)] * len(u10_shape)
                        read_slices[time_dim_idx] = slice(start, end)
                        u10_var[start:end, :, :] = _transform_chunk_local(src_u10_var[tuple(read_slices)])
                        v10_var[start:end, :, :] = _transform_chunk_local(src_v10_var[tuple(read_slices)])

                lon_var.description = "LONGITUDE, WEST IS NEGATIVE"
                lon_var.units = "degree_east"

                lat_var.description = "LATITUDE, SOUTH IS NEGATIVE"
                lat_var.units = "degree_north"

                time_var.standard_name = "time"
                time_var.long_name = "time"
                time_var.units = "seconds since 1970-01-01"
                time_var.reference_time = 1647349200
                time_var.reference_time_type = 1
                time_var.reference_date = "2022.03.15 21:00:00 UTC"
                time_var.time_step_setting = "auto"
                time_var.time_step = 0
                time_var.calendar = "standard"

                u10_var.description = "10 meters wind speed u"
                u10_var.units = "m/s"
                u10_var.level = "10m"

                v10_var.description = "10 meters wind speed v"
                v10_var.units = "m/s"
                v10_var.level = "10m"

            os.replace(temp_output_path, output_file)
            self._emit(log, tr("lat_flip_complete", "✅ 已完成纬度重排并保存至: {path}").format(path=output_file))
            return True

        except Exception as exc:
            try:
                if "temp_output_path" in locals() and os.path.exists(temp_output_path):
                    os.remove(temp_output_path)
            except Exception:
                pass
            self._emit(log, tr("log_write_file_failed", "❌ 写入新文件失败: {error}").format(error=exc))
            return False

    @staticmethod
    def _emit(log: Optional[Callable[[str], None]], message: str) -> None:
        """若提供 log 回调则输出一条消息。"""
        if log is not None:
            log(message)
