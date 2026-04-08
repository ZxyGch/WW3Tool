"""
NetCDF 信息处理服务模块
负责读取和显示 NetCDF 文件信息
"""
import os
import numpy as np
from netCDF4 import Dataset, num2date
from setting.language_manager import tr


class NetCDFInfoService:
    """NetCDF 信息处理服务类"""
    
    def __init__(self, logger=None):
        """
        初始化 NetCDF 信息服务
        
        参数:
            logger: 日志记录器（需要包含 log 方法）
        """
        self.logger = logger
    
    def log(self, msg: str):
        """记录日志"""
        if self.logger and hasattr(self.logger, 'log_signal'):
            try:
                self.logger.log_signal.emit(msg)
                return
            except Exception:
                pass
        if self.logger and hasattr(self.logger, 'log'):
            self.logger.log(msg)
    
    def print_nc_file_info(self, file_path: str):
        """读取并输出 NetCDF 文件的基本信息"""
        try:
            self.log(tr("file_info_separator", "=" * 60))
            self.log(tr("file_info_title", "📄 文件信息：{filename}").format(filename=os.path.basename(file_path)))
            self.log(tr("file_info_separator", "=" * 60))

            # 文件大小
            file_size = os.path.getsize(file_path)
            if file_size < 1024:
                size_str = f"{file_size} B"
            elif file_size < 1024 * 1024:
                size_str = f"{file_size / 1024:.2f} KB"
            elif file_size < 1024 * 1024 * 1024:
                size_str = f"{file_size / (1024 * 1024):.2f} MB"
            else:
                size_str = f"{file_size / (1024 * 1024 * 1024):.2f} GB"
            self.log(tr("file_size", "📦 文件大小：{size}").format(size=size_str))

            with Dataset(file_path, "r") as ds:
                # 文件格式
                self.log(tr("file_format", "📋 文件格式：{format}").format(format=ds.file_format))

                # 经纬度范围
                lon_min = lon_max = lat_min = lat_max = None
                if "longitude" in ds.variables:
                    lon = ds.variables["longitude"][:]
                    lon_min = float(np.min(lon))
                    lon_max = float(np.max(lon))
                    self.log(tr("longitude_range", "🌍 经度范围：{min}° ~ {max}°").format(min=f"{lon_min:.6f}",
                                                                                        max=f"{lon_max:.6f}"))
                elif "lon" in ds.variables:
                    lon = ds.variables["lon"][:]
                    lon_min = float(np.min(lon))
                    lon_max = float(np.max(lon))
                    self.log(tr("longitude_range", "🌍 经度范围：{min}° ~ {max}°").format(min=f"{lon_min:.6f}",
                                                                                        max=f"{lon_max:.6f}"))

                if "latitude" in ds.variables:
                    lat = ds.variables["latitude"][:]
                    lat_min = float(np.min(lat))
                    lat_max = float(np.max(lat))
                    self.log(tr("latitude_range", "🌍 纬度范围：{min}° ~ {max}°").format(min=f"{lat_min:.6f}",
                                                                                       max=f"{lat_max:.6f}"))
                elif "lat" in ds.variables:
                    lat = ds.variables["lat"][:]
                    lat_min = float(np.min(lat))
                    lat_max = float(np.max(lat))
                    self.log(tr("latitude_range", "🌍 纬度范围：{min}° ~ {max}°").format(min=f"{lat_min:.6f}",
                                                                                       max=f"{lat_max:.6f}"))

                # 时间范围（支持多种时间变量名，包括 CFSR 的 MT）
                time_start = time_end = None
                time_var = None
                time_var_name = None

                # 按优先级查找时间变量
                for time_name_candidate in ["time", "Time", "TIME", "valid_time", "MT", "mt", "t"]:
                    if time_name_candidate in ds.variables:
                        time_var = ds.variables[time_name_candidate]
                        time_var_name = time_name_candidate
                        break

                if time_var is not None:
                    try:
                        # 尝试使用 netCDF4 的 num2date 转换
                        time_units = getattr(time_var, 'units', None)
                        time_calendar = getattr(time_var, 'calendar', 'gregorian')

                        if time_units:
                            times = num2date(time_var[:], time_units, calendar=time_calendar)
                            if hasattr(times, "compressed"):
                                times = times.compressed()
                            if isinstance(times, np.ndarray):
                                times = times.ravel().tolist()
                            elif not isinstance(times, (list, tuple)):
                                times = [times]
                            times = [t for t in times if hasattr(t, "strftime")]
                            if len(times) > 0:
                                time_start = times[0]
                                time_end = times[-1]
                                self.log(tr("time_range", "⏰ 时间范围：{start} ~ {end}").format(
                                    start=time_start.strftime('%Y-%m-%d %H:%M:%S'),
                                    end=time_end.strftime('%Y-%m-%d %H:%M:%S')))
                                self.log(tr("time_steps", "⏰ 时间步数：{count}").format(count=len(times)))
                                if time_var_name != "time":
                                    self.log(tr("time_var_used", "ℹ️ 使用时间变量：{name}").format(name=time_var_name))
                        else:
                            # 如果没有时间单位，显示原始数值
                            time_data = time_var[:]
                            if len(time_data) > 0:
                                time_start_val = float(np.min(time_data))
                                time_end_val = float(np.max(time_data))
                                self.log(
                                    tr("time_range", "⏰ 时间范围：{start} ~ {end}").format(start=f"{time_start_val:.2f}",
                                                                                          end=f"{time_end_val:.2f} {tr('no_unit', '(无单位)')}"))
                                self.log(tr("time_steps", "⏰ 时间步数：{count}").format(count=len(time_data)))
                                if time_var_name != "time":
                                    self.log(tr("time_var_used", "ℹ️ 使用时间变量：{name}").format(name=time_var_name))
                    except Exception as e:
                        # 如果无法解析时间单位，显示原始数值
                        time_data = time_var[:]
                        if len(time_data) > 0:
                            time_start_val = float(np.min(time_data))
                            time_end_val = float(np.max(time_data))
                            units = getattr(time_var, 'units', 'unknown')
                            self.log(
                                tr("time_range", "⏰ 时间范围：{start} ~ {end}").format(start=f"{time_start_val:.2f}",
                                                                                      end=f"{time_end_val:.2f} ({units})"))
                            self.log(tr("time_steps", "⏰ 时间步数：{count}").format(count=len(time_data)))
                            if time_var_name != "time":
                                self.log(tr("time_var_used", "ℹ️ 使用时间变量：{name}").format(name=time_var_name))
                            self.log(tr("time_parse_failed", "⚠️ 时间解析失败：{error}").format(error=e))

                # 维度信息
                self.log(tr("dimensions_info", "\n📏 维度信息（共 {count} 个）：").format(count=len(ds.dimensions)))
                for dim_name, dim in ds.dimensions.items():
                    size = len(dim) if not dim.isunlimited() else tr("dim_unlimited", "unlimited")
                    self.log(f"  - {dim_name}: {size}")

                # 变量信息
                self.log(tr("variables_info", "\n📊 变量信息（共 {count} 个）：").format(count=len(ds.variables)))
                for var_name, var in ds.variables.items():
                    dims = ", ".join(var.dimensions) if var.dimensions else tr("var_scalar", "(scalar)")
                    dtype = var.dtype
                    shape = var.shape
                    self.log(f"  - {var_name}:")
                    self.log(tr("var_dimension", "     维度: {dims}").format(dims=dims))
                    self.log(tr("var_type", "     类型: {dtype}").format(dtype=dtype))
                    self.log(tr("var_shape", "     形状: {shape}").format(shape=shape))

                    # 输出数据范围（如果是数值型）
                    if var.size > 0 and np.issubdtype(var.dtype, np.number):
                        try:
                            data = var[:]
                            if data.size > 0:
                                valid_data = data[~np.isnan(data)] if np.issubdtype(data.dtype, np.floating) else data
                                if valid_data.size > 0:
                                    self.log(tr("var_data_range", "     数据范围: [{min}, {max}]").format(
                                        min=f"{np.min(valid_data):.6f}", max=f"{np.max(valid_data):.6f}"))
                        except Exception:
                            pass

                # 全局属性
                if ds.ncattrs():
                    self.log(tr("global_attrs_info", "\n🌐 全局属性（共 {count} 个）：").format(count=len(ds.ncattrs())))
                    for attr_name in ds.ncattrs():
                        attr_value = getattr(ds, attr_name)
                        # 如果属性值太长，截断显示
                        attr_str = str(attr_value)
                        if len(attr_str) > 100:
                            attr_str = attr_str[:100] + "..."
                        self.log(f"  - {attr_name}: {attr_str}")

            self.log(tr("file_info_separator", "=" * 60))

        except Exception as e:
            self.log(tr("read_file_info_failed", "❌ 读取文件信息失败：{error}").format(error=e))
            import traceback
            traceback.print_exc()

    def get_lonlat_bounds(self, file_path: str) -> dict[str, float]:
        """读取文件的经纬度范围。"""
        try:
            with Dataset(file_path, "r") as ds:
                lon_var = None
                lat_var = None
                for lon_name in ["longitude", "lon", "Longitude", "LON"]:
                    if lon_name in ds.variables:
                        lon_var = ds.variables[lon_name]
                        break
                for lat_name in ["latitude", "lat", "Latitude", "LAT"]:
                    if lat_name in ds.variables:
                        lat_var = ds.variables[lat_name]
                        break
                if lon_var is None or lat_var is None:
                    return {}
                lon = lon_var[:]
                lat = lat_var[:]
                return {
                    "lon_min": float(np.min(lon)),
                    "lon_max": float(np.max(lon)),
                    "lat_min": float(np.min(lat)),
                    "lat_max": float(np.max(lat)),
                }
        except Exception:
            return {}

    def print_step1_field_overview(self, field_name: str, file_path: str):
        """输出 Step 1 的场文件总览信息。"""
        self.log("")
        self.log(f"{'=' * 70}")
        self.log(tr("view_field_banner", "【{name}】").format(name=field_name))
        self.log(tr("view_filename", "文件名：{name}").format(name=os.path.basename(file_path)))
        try:
            file_size = os.path.getsize(file_path)
            if file_size < 1024:
                size_str = f"{file_size} B"
            elif file_size < 1024 * 1024:
                size_str = f"{file_size / 1024:.2f} KB"
            elif file_size < 1024 * 1024 * 1024:
                size_str = f"{file_size / (1024 * 1024):.2f} MB"
            else:
                size_str = f"{file_size / (1024 * 1024 * 1024):.2f} GB"
            self.log(tr("view_filesize", "文件大小：{size}").format(size=size_str))
        except Exception as exc:
            self.log(tr("view_filesize_error", "文件大小：无法读取 ({error})").format(error=exc))

        try:
            with Dataset(file_path, "r") as ds:
                lon_var = lat_var = None
                lon = lat = None

                for lon_name in ["longitude", "lon", "Longitude", "LON"]:
                    if lon_name in ds.variables:
                        lon_var = ds.variables[lon_name]
                        lon = lon_var[:]
                        self.log(
                            tr("longitude_range", "🌍 经度范围：{min}° ~ {max}°").format(
                                min=f"{float(np.min(lon)):.6f}",
                                max=f"{float(np.max(lon)):.6f}",
                            )
                        )
                        break

                for lat_name in ["latitude", "lat", "Latitude", "LAT"]:
                    if lat_name in ds.variables:
                        lat_var = ds.variables[lat_name]
                        lat = lat_var[:]
                        self.log(
                            tr("latitude_range", "🌍 纬度范围：{min}° ~ {max}°").format(
                                min=f"{float(np.min(lat)):.6f}",
                                max=f"{float(np.max(lat)):.6f}",
                            )
                        )
                        break

                if lon_var is not None and lon is not None and len(lon_var) > 1:
                    lon_diff = np.diff(lon)
                    if len(lon_diff) > 0:
                        self.log(
                            tr("view_lon_resolution", "经度精度：{val}°").format(
                                val=f"{float(np.mean(np.abs(lon_diff))):.6f}"
                            )
                        )
                if lat_var is not None and lat is not None and len(lat_var) > 1:
                    lat_diff = np.diff(lat)
                    if len(lat_diff) > 0:
                        self.log(
                            tr("view_lat_resolution", "纬度精度：{val}°").format(
                                val=f"{float(np.mean(np.abs(lat_diff))):.6f}"
                            )
                        )

                time_var = None
                time_var_name = None
                for time_name in ["time", "Time", "TIME", "valid_time", "MT", "mt", "t"]:
                    if time_name in ds.variables:
                        time_var = ds.variables[time_name]
                        time_var_name = time_name
                        break

                if time_var is not None:
                    try:
                        time_units = getattr(time_var, "units", None)
                        time_calendar = getattr(time_var, "calendar", "gregorian")
                        if time_units:
                            times = num2date(time_var[:], time_units, calendar=time_calendar)
                            if hasattr(times, "compressed"):
                                times = times.compressed()
                            if isinstance(times, np.ndarray):
                                times = times.ravel().tolist()
                            elif not isinstance(times, (list, tuple)):
                                times = [times]
                            times = [item for item in times if hasattr(item, "strftime")]
                            if len(times) > 0:
                                time_start, time_end = times[0], times[-1]
                                self.log(
                                    tr("time_range", "⏰ 时间范围：{start} ~ {end}").format(
                                        start=time_start.strftime("%Y-%m-%d %H:%M:%S"),
                                        end=time_end.strftime("%Y-%m-%d %H:%M:%S"),
                                    )
                                )
                                self.log(tr("time_steps", "⏰ 时间步数：{count}").format(count=len(times)))
                                if len(times) > 1:
                                    time_diffs = [
                                        (times[index + 1] - times[index]).total_seconds()
                                        for index in range(len(times) - 1)
                                    ]
                                    if time_diffs:
                                        avg_time_diff = np.mean(time_diffs)
                                        if avg_time_diff < 60:
                                            time_res_str = f"{avg_time_diff:.0f} " + tr("view_unit_seconds", "秒")
                                        elif avg_time_diff < 3600:
                                            time_res_str = (
                                                f"{avg_time_diff / 60:.1f} " + tr("view_unit_minutes", "分钟")
                                            )
                                        elif avg_time_diff < 86400:
                                            time_res_str = (
                                                f"{avg_time_diff / 3600:.2f} " + tr("view_unit_hours", "小时")
                                            )
                                        else:
                                            time_res_str = (
                                                f"{avg_time_diff / 86400:.2f} " + tr("view_unit_days", "天")
                                            )
                                        self.log(
                                            tr("view_time_resolution", "时间精度：{resolution}").format(
                                                resolution=time_res_str
                                            )
                                        )
                                if time_var_name != "time":
                                    self.log(
                                        tr("time_var_used", "ℹ️ 使用时间变量：{name}").format(name=time_var_name)
                                    )
                        else:
                            time_data = time_var[:]
                            if len(time_data) > 0:
                                self.log(
                                    tr("view_time_range_no_unit", "时间范围：{min} ~ {max} (无单位)").format(
                                        min=f"{float(np.min(time_data)):.2f}",
                                        max=f"{float(np.max(time_data)):.2f}",
                                    )
                                )
                                self.log(tr("time_steps", "⏰ 时间步数：{count}").format(count=len(time_data)))
                    except Exception as exc:
                        self.log(tr("view_time_parse_error", "时间范围：无法解析 ({error})").format(error=exc))
                else:
                    self.log(tr("view_time_var_missing", "时间范围：未找到时间变量"))
        except Exception as exc:
            self.log(tr("read_file_info_failed", "❌ 读取文件信息失败：{error}").format(error=exc))
