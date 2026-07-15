"""WW3 Step 2 强迫场文件 I/O 与格式修复服务。

[EN] WW3 Step 2 forcing field file I/O and format fixing service.

用户选定 NetCDF 后，本模块负责将其复制或移动到工作目录，并执行必要的
WW3 兼容性修正，包括：

[EN] After the user selects a NetCDF file, this module is responsible for copying or moving
it to the working directory and performing only the necessary WW3-compatible fixes
on the copy, including:

- 坐标变量名标准化（``lon`` → ``longitude``、``lat`` → ``latitude``、``valid_time`` → ``time`` 等）；
- 将 ``wndewd/wndnwd`` 重命名为 ``u10/v10``（部分再分析产品使用旧名）；
- 一维纬度坐标递减时翻转为递增，避免 ``ww3_prnc`` 在规则经纬网下报错；
- 一维经度坐标递减时明确拒绝，不静默改写经度闭合关系；
- 保留原始时间轴单位与日历属性；
- 扫描工作目录，按文件名规则或变量检测恢复 Step 2 四类场路径。

[EN] - Standardizing coordinate variable names (``lon`` → ``longitude``, ``lat`` → ``latitude``, etc.);
- Renaming ``wndewd/wndnwd`` to ``u10/v10`` (some reanalysis products use legacy names);
- Flipping descending 1-D latitude coordinates to ascending order to avoid
  ``ww3_prnc`` failures on regular lat/lon grids;
- Rejecting descending 1-D longitude coordinates instead of silently rewriting
  longitude closure;
- Preserving original time axis units and calendar attributes;
- Scanning the working directory to recover Step 2 field paths via filename rules or variable detection.
"""
import os
import shutil
import glob
import numpy as np
from datetime import datetime
from netCDF4 import Dataset, num2date
from typing import Optional
from ...domain.forcing_fields import ForcingField, Step2Files
from ...support.translations import tr
from .file_path_manager import FilePathManager
from .forcing_normalize_service import ForcingNormalizeService
from .variable_detector import VariableDetector


class FileService:
    """强迫场文件的复制、修复与工作目录扫描服务。

    [EN] Service for copying, fixing, and scanning the working directory for forcing files.

    参数:
        logger: 可选日志对象，需实现 ``log`` 方法或 Qt ``log_signal``。

    [EN] Parameters:
        logger: Optional logger object, must implement ``log`` method or Qt ``log_signal``.
    """
    
    def __init__(self, logger=None, normalizer: Optional[ForcingNormalizeService] = None):
        """
        初始化文件服务

        [EN] Initialize the file service.

        参数:
            logger: 日志记录器（需要包含 log 方法）
            normalizer: 强迫场归一化服务（默认自动创建）

        [EN] Parameters:
            logger: Logger (must have a log method)
            normalizer: Forcing normalize service (auto-created if not provided)
        """
        self.logger = logger
        self.path_manager = FilePathManager()
        self._normalizer = normalizer or ForcingNormalizeService()
    
    def log(self, msg: str):
        """记录日志

        [EN] Log a message.
        """
        if self.logger and hasattr(self.logger, 'log_signal'):
            try:
                self.logger.log_signal.emit(msg)
                return
            except Exception:
                pass
        if self.logger and hasattr(self.logger, 'log'):
            self.logger.log(msg)

    def _rewrite_wind_vars_to_u10_v10(self, source_path: str, wndewd_name: str, wndnwd_name: str) -> None:
        """原地重写 NetCDF，将 wndewd/wndnwd 重命名为 u10/v10。

        [EN] Rewrite the NetCDF in place, renaming wndewd/wndnwd to u10/v10.

        netCDF4 不支持删除变量，故通过临时文件完整复制并替换变量名，
        保留全局属性、维度、压缩与 ``_FillValue`` 设置。

        [EN] netCDF4 does not support deleting variables, so this method performs a full copy
        via a temporary file and replaces variable names, preserving global attributes,
        dimensions, compression, and ``_FillValue`` settings.
        """
        temp_file = source_path + ".tmp"
        with Dataset(source_path, "r") as src:
            file_format = getattr(src, "file_format", "NETCDF4")
            with Dataset(temp_file, "w", format=file_format) as dst:
                # 复制全局属性
                # [EN] Copy global attributes
                for attr_name in src.ncattrs():
                    dst.setncattr(attr_name, src.getncattr(attr_name))

                # 复制维度
                # [EN] Copy dimensions
                for dim_name, dim in src.dimensions.items():
                    dst.createDimension(dim_name, len(dim) if not dim.isunlimited() else None)

                # 复制变量（wndewd/wndnwd -> u10/v10）
                # [EN] Copy variables (wndewd/wndnwd -> u10/v10)
                for var_name, var in src.variables.items():
                    if var_name == wndewd_name:
                        new_name = "u10"
                    elif var_name == wndnwd_name:
                        new_name = "v10"
                    else:
                        new_name = var_name

                    # 处理 _FillValue 与过滤器
                    # [EN] Handle _FillValue and filters
                    var_attrs = {k: var.getncattr(k) for k in var.ncattrs()}
                    fill_value = var_attrs.pop("_FillValue", None)
                    var_kwargs = {}
                    if fill_value is not None:
                        var_kwargs["fill_value"] = fill_value
                    try:
                        filters = var.filters()
                        if filters and filters.get("zlib"):
                            var_kwargs["zlib"] = True
                            if filters.get("complevel") is not None:
                                var_kwargs["complevel"] = filters["complevel"]
                            if filters.get("shuffle") is not None:
                                var_kwargs["shuffle"] = filters["shuffle"]
                            if filters.get("fletcher32") is not None:
                                var_kwargs["fletcher32"] = filters["fletcher32"]
                            if filters.get("chunksizes") is not None:
                                var_kwargs["chunksizes"] = filters["chunksizes"]
                            if filters.get("least_significant_digit") is not None:
                                var_kwargs["least_significant_digit"] = filters["least_significant_digit"]
                    except Exception:
                        pass

                    new_var = dst.createVariable(new_name, var.dtype, var.dimensions, **var_kwargs)
                    for attr_name, attr_value in var_attrs.items():
                        new_var.setncattr(attr_name, attr_value)
                    new_var[:] = var[:]

        os.replace(temp_file, source_path)

    _LAT_NAMES = ("latitude", "lat", "Latitude", "y", "Y", "LATITUDE", "LAT")
    _LON_NAMES = ("longitude", "lon", "Longitude", "x", "X", "LONGITUDE", "LON")

    @staticmethod
    def _find_coord_name(var_names, candidates):
        for name in candidates:
            if name in var_names:
                return name
        return None

    @staticmethod
    def _decreasing_1d_coord_dimension(coord_var, coordinate_label):
        """返回递减一维坐标对应的维度名；递增返回 None。

        [EN] Return the dimension name for a decreasing 1-D coordinate; return None if increasing.
        """
        if len(coord_var.dimensions) != 1:
            return None

        values = np.ma.asarray(coord_var[:])
        if np.ma.is_masked(values) and np.any(np.ma.getmaskarray(values)):
            raise ValueError(f"{coordinate_label}坐标变量 {coord_var.name} 包含缺测值")

        values = np.asarray(values)
        if values.ndim != 1 or values.size <= 1:
            return None

        try:
            differences = np.diff(values.astype(np.float64))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{coordinate_label}坐标变量 {coord_var.name} 不是数值坐标") from exc

        if np.all(differences > 0):
            return None
        if np.all(differences < 0):
            return coord_var.dimensions[0]
        raise ValueError(
            f"{coordinate_label}坐标变量 {coord_var.name} 必须严格单调，"
            "不能包含重复值或乱序值"
        )

    @staticmethod
    def _variable_creation_kwargs(var):
        var_attrs = {name: var.getncattr(name) for name in var.ncattrs()}
        fill_value = var_attrs.pop("_FillValue", None)
        kwargs = {}
        if fill_value is not None:
            kwargs["fill_value"] = fill_value

        try:
            filters = var.filters() or {}
            if filters.get("zlib"):
                kwargs["zlib"] = True
                kwargs["complevel"] = filters.get("complevel", 4)
                kwargs["shuffle"] = filters.get("shuffle", True)
            if filters.get("fletcher32"):
                kwargs["fletcher32"] = True
        except Exception:
            pass

        try:
            chunking = var.chunking()
            if isinstance(chunking, (list, tuple)):
                kwargs["chunksizes"] = tuple(chunking)
        except Exception:
            pass

        return var_attrs, kwargs

    def _flip_dimension_in_place(self, target_file: str, dimension_name: str) -> None:
        """原地翻转 NetCDF 中所有包含指定维度的变量。

        [EN] Flip all variables containing the specified dimension in the NetCDF in place.
        """
        temp_file = target_file + ".flip_tmp"
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            with Dataset(target_file, "r") as src:
                file_format = getattr(src, "file_format", "NETCDF4")
                with Dataset(temp_file, "w", format=file_format) as dst:
                    for attr_name in src.ncattrs():
                        dst.setncattr(attr_name, src.getncattr(attr_name))

                    for dim_name, dim in src.dimensions.items():
                        dst.createDimension(dim_name, len(dim) if not dim.isunlimited() else None)

                    for var_name, var in src.variables.items():
                        var_attrs, var_kwargs = self._variable_creation_kwargs(var)
                        new_var = dst.createVariable(var_name, var.dtype, var.dimensions, **var_kwargs)
                        for attr_name, attr_value in var_attrs.items():
                            new_var.setncattr(attr_name, attr_value)

                        data = var[...]
                        if dimension_name in var.dimensions:
                            axis = var.dimensions.index(dimension_name)
                            slices = tuple(
                                slice(None, None, -1) if index == axis else slice(None)
                                for index in range(len(var.dimensions))
                            )
                            data = data[slices]
                        new_var[...] = data

            os.replace(temp_file, target_file)
        except Exception:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise

    # [EN] Coordinate name alias → standard name mappings
    _LON_ALIASES = ("lon", "Longitude", "x", "X", "LONGITUDE", "LON")
    _LAT_ALIASES = ("lat", "Latitude", "y", "Y", "LATITUDE", "LAT")
    _TIME_ALIASES = ("valid_time", "Time", "TIME", "t", "MT", "mt")

    def _standardize_coordinate_names(self, target_file: str) -> None:
        """统一坐标变量名为 longitude / latitude / time。

        [EN] Standardize coordinate variable names to longitude / latitude / time.

        如果所有坐标变量名已是标准名，跳过；否则通过临时文件重写。
        维度和引用该维度的变量同步重命名。

        [EN] If all coordinate names are already standard, skip; otherwise rewrite
        via a temporary file. Dimensions and variables referencing the renamed
        dimension are updated accordingly.
        """
        temp_file = target_file + ".std_coord_tmp"
        try:
            with Dataset(target_file, "r") as src:
                # [EN] Build variable rename map: only rename 1-D coord vars whose dim matches
                rename_map: dict[str, str] = {}
                for alias in self._LON_ALIASES:
                    if alias in src.variables:
                        var = src.variables[alias]
                        if len(var.dimensions) == 1 and var.dimensions[0] == alias:
                            rename_map[alias] = "longitude"
                        break
                for alias in self._LAT_ALIASES:
                    if alias in src.variables:
                        var = src.variables[alias]
                        if len(var.dimensions) == 1 and var.dimensions[0] == alias:
                            rename_map[alias] = "latitude"
                        break
                for alias in self._TIME_ALIASES:
                    if alias in src.variables:
                        var = src.variables[alias]
                        if len(var.dimensions) == 1 and var.dimensions[0] == alias:
                            rename_map[alias] = "time"
                        break

                if not rename_map:
                    return  # [EN] Nothing to rename

                # [EN] Build dimension rename map
                dim_rename_map: dict[str, str] = {}
                for old_name, new_name in rename_map.items():
                    if old_name in src.dimensions:
                        dim_rename_map[old_name] = new_name

                if os.path.exists(temp_file):
                    os.remove(temp_file)
                file_format = getattr(src, "file_format", "NETCDF4")
                with Dataset(temp_file, "w", format=file_format) as dst:
                    for attr_name in src.ncattrs():
                        dst.setncattr(attr_name, src.getncattr(attr_name))

                    for dim_name, dim in src.dimensions.items():
                        new_dim = dim_rename_map.get(dim_name, dim_name)
                        dst.createDimension(new_dim, len(dim) if not dim.isunlimited() else None)

                    for var_name, var in src.variables.items():
                        new_name = rename_map.get(var_name, var_name)
                        new_dims = tuple(dim_rename_map.get(d, d) for d in var.dimensions)
                        var_attrs, var_kwargs = self._variable_creation_kwargs(var)
                        new_var = dst.createVariable(new_name, var.dtype, new_dims, **var_kwargs)
                        for attr_name, attr_value in var_attrs.items():
                            new_var.setncattr(attr_name, attr_value)
                        new_var[:] = var[:]

            os.replace(temp_file, target_file)
            renamed = ", ".join(f"{k}→{v}" for k, v in rename_map.items())
            self.log(tr("log_coord_names_standardized",
                        "✅ 坐标变量已标准化：{renamed}").format(renamed=renamed))
        except Exception:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise

    def _standardize_time_units(self, target_file: str) -> None:
        """统一时间单位为 ``seconds since 1970-01-01``。

        [EN] Standardize time units to ``seconds since 1970-01-01``.

        如果已经是标准单位，跳过；否则原地重写时间变量值。

        [EN] If already in standard units, skip; otherwise rewrite the time variable values in place.
        """
        target_units = "seconds since 1970-01-01"
        temp_file = target_file + ".time_tmp"
        try:
            with Dataset(target_file, "r") as src:
                time_name = None
                for candidate in ("time", "MT"):
                    if candidate in src.variables:
                        time_name = candidate
                        break
                if time_name is None:
                    return

                time_var = src.variables[time_name]
                if len(time_var.dimensions) != 1:
                    return

                original_units = getattr(time_var, "units", None)
                if not original_units:
                    return

                if original_units.strip().lower() == target_units.lower():
                    return  # [EN] Already standard

                original_calendar = getattr(time_var, "calendar", "gregorian")
                time_values = np.asarray(time_var[:])

                try:
                    time_datetimes = num2date(time_values, original_units, calendar=original_calendar)
                    if hasattr(time_datetimes, "compressed"):
                        time_datetimes = time_datetimes.compressed()
                    epoch = datetime(1970, 1, 1)
                    time_seconds = [(dt - epoch).total_seconds() for dt in time_datetimes]
                except Exception as exc:
                    self.log(tr("log_time_units_convert_failed",
                                "⚠️ 时间单位转换失败，使用原始值: {error}").format(error=exc))
                    return

                if os.path.exists(temp_file):
                    os.remove(temp_file)
                file_format = getattr(src, "file_format", "NETCDF4")
                with Dataset(temp_file, "w", format=file_format) as dst:
                    for attr_name in src.ncattrs():
                        dst.setncattr(attr_name, src.getncattr(attr_name))

                    for dim_name, dim in src.dimensions.items():
                        dst.createDimension(dim_name, len(dim) if not dim.isunlimited() else None)

                    for var_name, var in src.variables.items():
                        var_attrs, var_kwargs = self._variable_creation_kwargs(var)
                        new_var = dst.createVariable(var_name, var.dtype, var.dimensions, **var_kwargs)
                        for attr_name, attr_value in var_attrs.items():
                            new_var.setncattr(attr_name, attr_value)

                        if var_name == time_name:
                            new_var[:] = time_seconds
                            new_var.units = target_units
                        else:
                            new_var[:] = var[:]

            os.replace(temp_file, target_file)
            self.log(tr("log_time_units_converted",
                        "🔄 时间单位已从 '{old}' 转换为 '{new}'").format(
                old=original_units, new=target_units))
        except Exception:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise

    def copy_and_fix_forcing_file(self, source_file: str, target_file: str, process_mode: str = "copy") -> Optional[str]:
        """
        复制或移动强迫场文件到工作目录，并通过 ForcingNormalizeService 单遍标准化。

        [EN] Copy or move a forcing file to the working directory, then normalize
        in a single pass via ForcingNormalizeService.

        参数:
            source_file: 源文件路径
            target_file: 目标文件路径
            process_mode: 处理方式，"copy" 或 "move"

        [EN] Parameters:
            source_file: Source file path
            target_file: Target file path
            process_mode: Processing mode, "copy" or "move"

        返回:
            目标文件路径，如果失败返回 None

        [EN] Returns:
            Target file path, or None if failed.
        """
        try:
            # 如果目标文件已存在且与源文件相同，直接归一化
            # [EN] If target already exists and is the same as source, normalize directly
            try:
                if os.path.samefile(source_file, target_file):
                    ok = self._normalizer.normalize(source_file, target_file, log=self.log)
                    return target_file if ok else None
            except OSError:
                pass

            # 1. 复制或移动文件
            # [EN] 1. Copy or move the file
            target_dir = os.path.dirname(target_file)
            if target_dir:
                os.makedirs(target_dir, exist_ok=True)

            if process_mode == "move":
                shutil.move(source_file, target_file)
            else:
                shutil.copy2(source_file, target_file)

            # 2. 单遍归一化（坐标标准化 + 时间转换 + 纬度翻转 + 变量重命名）
            # [EN] 2. Single-pass normalization (coord standardization + time conversion
            #        + lat flip + variable renaming)
            ok = self._normalizer.normalize(target_file, target_file, log=self.log)
            if not ok:
                return None

            return target_file

        except Exception as e:
            self.log(f"{tr('log_copy_fix_failed', '❌ 复制或修复文件失败')}: {e}")
            return None

    def crop_and_fix_forcing_file(
        self,
        source_file: str,
        target_file: str,
        *,
        time_range: list[str] | tuple[str, str] | None = None,
        bbox: list[float] | tuple[float, float, float, float] | None = None,
        remove_source: bool = False,
    ) -> Optional[str]:
        """裁剪强迫场到工作目录，并执行 WW3 格式标准化。

        [EN] Crop a forcing NetCDF into the workdir and then normalize it for WW3.
        """
        processing_target = target_file
        replace_target = False
        try:
            from .merge_service import merge_forcing_netcdf

            target_dir = os.path.dirname(target_file)
            if target_dir:
                os.makedirs(target_dir, exist_ok=True)
            try:
                replace_target = os.path.samefile(source_file, target_file)
            except OSError:
                replace_target = os.path.realpath(source_file) == os.path.realpath(target_file)
            if replace_target:
                processing_target = target_file + ".crop_tmp.nc"
                if os.path.exists(processing_target):
                    os.remove(processing_target)
            self.log(
                tr("log_crop_forcing_start", "✂️ 正在按范围裁剪强迫场：{src} → {dst}").format(
                    src=os.path.basename(source_file),
                    dst=os.path.basename(target_file),
                )
            )
            merge_forcing_netcdf(
                [source_file],
                processing_target,
                log=self.log,
                time_range=time_range,
                bbox=bbox,
            )
            ok = self._normalizer.normalize(processing_target, processing_target, log=self.log)
            if not ok:
                if replace_target and os.path.exists(processing_target):
                    os.remove(processing_target)
                return None
            if replace_target:
                os.replace(processing_target, target_file)
            if remove_source:
                try:
                    same_file = os.path.samefile(source_file, target_file)
                except OSError:
                    same_file = False
                if not same_file and os.path.exists(source_file):
                    os.remove(source_file)
                    self.log(
                        tr("log_crop_forcing_source_removed", "🧹 剪切模式：已删除原始强迫场文件：{file}").format(
                            file=os.path.basename(source_file)
                        )
                    )
            self.log(
                tr("log_crop_forcing_done", "✅ 强迫场裁剪并标准化完成：{file}").format(
                    file=os.path.basename(target_file)
                )
            )
            return target_file
        except Exception as e:
            if replace_target and os.path.exists(processing_target):
                try:
                    os.remove(processing_target)
                except OSError:
                    pass
            self.log(f"{tr('log_crop_fix_failed', '❌ 裁剪或修复文件失败')}: {e}")
            return None

    def scan_forcing_files(self, selected_folder: str, *, auto_associate: bool = True) -> Step2Files:
        """扫描工作目录，推断 wind/current/level/ice 四类场对应的 NetCDF 路径。

        [EN] Scan the working directory and infer NetCDF paths for wind/current/level/ice fields.

        匹配顺序：单场标准名（``wind.nc`` 等）→（auto_associate 时）组合文件名解析
        → 打开文件做变量检测。不修改 UI，返回 ``Step2Files`` 供 CLI 或 ViewModel 使用。

        [EN] Matching order: single-field standard names (``wind.nc``, etc.) ->
        (when auto_associate) combined filename parsing -> open file and detect variables.
        Does not modify the UI; returns ``Step2Files`` for CLI or ViewModel use.
        """
        files = Step2Files()
        try:
            if not selected_folder or not os.path.isdir(selected_folder):
                return files

            nc_files = glob.glob(os.path.join(selected_folder, "*.nc"))
            field_patterns = {
                ForcingField.WIND: ["wind.nc"],
                ForcingField.CURRENT: ["current.nc"],
                ForcingField.LEVEL: ["level.nc"],
                ForcingField.ICE: ["ice.nc"],
            }
            found_files: dict[ForcingField, str] = {}

            for field, patterns in field_patterns.items():
                for pattern in patterns:
                    file_path = os.path.join(selected_folder, pattern)
                    if os.path.exists(file_path):
                        found_files[field] = file_path
                        break

            for nc_file in nc_files:
                if not auto_associate:
                    continue
                filename = os.path.basename(nc_file)
                fields = self.path_manager.parse_forcing_filename(filename)
                if len(fields) > 1:
                    for field_name in fields:
                        try:
                            field = ForcingField(field_name)
                        except ValueError:
                            continue
                        if field not in found_files:
                            found_files[field] = nc_file
                        elif found_files[field] == os.path.join(selected_folder, f"{field.value}.nc"):
                            pass

            if auto_associate:
                missing_fields = [field for field in field_patterns.keys() if field not in found_files]
                if missing_fields:
                    for nc_file in nc_files:
                        detected = VariableDetector.detect_all_forcing_fields_in_file(nc_file)
                        for field in list(missing_fields):
                            if detected.get(field.value) and field not in found_files:
                                found_files[field] = nc_file
                                missing_fields.remove(field)
                        if not missing_fields:
                            break

            for field, path in found_files.items():
                files.set(field, path)
        except Exception:
            pass
        return files

    def detect_and_fill_forcing_fields(self, instance, selected_folder: str):
        """扫描工作目录并将检测结果同步到桌面端 Step 2 控件。

        [EN] Scan the working directory and sync detection results to the desktop Step 2 controls.

        内部调用 ``scan_forcing_files``，再更新 ``selected_*_file`` 属性及
        风/流/水位/海冰选择按钮的显示文本。

        [EN] Internally calls ``scan_forcing_files``, then updates ``selected_*_file`` attributes
        and the display text of wind/current/level/ice selection buttons.

        参数:
            instance: 主窗口实例（需含按钮与 ``selected_*_file`` 属性）
            selected_folder: 当前 WW3 工作目录

        [EN] Parameters:
            instance: Main window instance (must have buttons and ``selected_*_file`` attributes)
            selected_folder: Current WW3 working directory
        """
        try:
            found_files = self.scan_forcing_files(selected_folder)

            if hasattr(instance, 'selected_origin_file'):
                instance.selected_origin_file = found_files.wind
            if hasattr(instance, 'selected_current_file'):
                instance.selected_current_file = found_files.current
            if hasattr(instance, 'selected_level_file'):
                instance.selected_level_file = found_files.level
            if hasattr(instance, 'selected_ice_file'):
                instance.selected_ice_file = found_files.ice

            def _display_name(path: Optional[str], default_text: str) -> str:
                if not path:
                    return default_text
                file_name = os.path.basename(path)
                return file_name[:27] + "..." if len(file_name) > 30 else file_name

            if hasattr(instance, '_set_wind_file_button_text'):
                instance._set_wind_file_button_text(
                    _display_name(found_files.wind, tr("step1_choose_wind", "选择风场")),
                    filled=bool(found_files.wind),
                )
            elif hasattr(instance, 'btn_choose_wind_file') and hasattr(instance, '_set_home_forcing_button_text'):
                instance._set_home_forcing_button_text(
                    instance.btn_choose_wind_file,
                    _display_name(found_files.wind, tr("step1_choose_wind", "选择风场")),
                    filled=bool(found_files.wind),
                )

            button_map = {
                'current': ('btn_choose_current_file', tr("step1_choose_current", "选择流场"), found_files.current),
                'level': ('btn_choose_level_file', tr("step1_choose_level", "选择水位场"), found_files.level),
                'ice': ('btn_choose_ice_file_home', tr("step1_choose_ice", "选择海冰场"), found_files.ice),
            }
            for _, (button_attr, default_text, path) in button_map.items():
                if hasattr(instance, button_attr) and hasattr(instance, '_set_home_forcing_button_text'):
                    instance._set_home_forcing_button_text(
                        getattr(instance, button_attr),
                        _display_name(path, default_text),
                        filled=bool(path),
                    )

            if hasattr(instance, '_update_forcing_fields_display'):
                instance._update_forcing_fields_display()
        except Exception:
            pass
