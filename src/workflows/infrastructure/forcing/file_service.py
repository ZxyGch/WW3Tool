"""WW3 Step 1 强迫场文件 I/O 与格式修复服务。

[EN] WW3 Step 1 forcing field file I/O and format fixing service.

用户选定 NetCDF 后，本模块负责将其复制或移动到工作目录，并只执行必要的
WW3 兼容性修正，包括：

[EN] After the user selects a NetCDF file, this module is responsible for copying or moving
it to the working directory and performing only the necessary WW3-compatible fixes
on the copy, including:

- 将 ``wndewd/wndnwd`` 重命名为 ``u10/v10``（部分再分析产品使用旧名）；
- 一维纬度坐标递减时翻转为递增，避免 ``ww3_prnc`` 在规则经纬网下报错；
- 一维经度坐标递减时明确拒绝，不静默改写经度闭合关系；
- 扫描工作目录，按文件名规则或变量检测恢复 Step 1 四类场路径。

[EN] - Renaming ``wndewd/wndnwd`` to ``u10/v10`` (some reanalysis products use legacy names);
- Flipping descending 1-D latitude coordinates to ascending order to avoid
  ``ww3_prnc`` failures on regular lat/lon grids;
- Rejecting descending 1-D longitude coordinates instead of silently rewriting
  longitude closure;
- Scanning the working directory to recover Step 1 field paths via filename rules or variable detection.
"""
import os
import shutil
import glob
import numpy as np
from netCDF4 import Dataset
from typing import Optional
from ...domain.forcing_fields import ForcingField, Step1Files
from ...support.translations import tr
from .file_path_manager import FilePathManager
from .variable_detector import VariableDetector


class FileService:
    """强迫场文件的复制、修复与工作目录扫描服务。

    [EN] Service for copying, fixing, and scanning the working directory for forcing files.

    参数:
        logger: 可选日志对象，需实现 ``log`` 方法或 Qt ``log_signal``。

    [EN] Parameters:
        logger: Optional logger object, must implement ``log`` method or Qt ``log_signal``.
    """
    
    def __init__(self, logger=None):
        """
        初始化文件服务

        [EN] Initialize the file service.
        
        参数:
            logger: 日志记录器（需要包含 log 方法）

        [EN] Parameters:
            logger: Logger (must have a log method)
        """
        self.logger = logger
        self.path_manager = FilePathManager()
    
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
        """返回递减一维坐标对应的维度名；递增返回 None。"""
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
        """原地翻转 NetCDF 中所有包含指定维度的变量。"""
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

    def copy_and_fix_forcing_file(self, source_file: str, target_file: str, process_mode: str = "copy") -> Optional[str]:
        """
        复制或移动强迫场文件到工作目录，并执行必要兼容性修复。

        [EN] Copy or move a forcing file to the working directory, and apply necessary
        compatibility fixes.
        
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
            # 如果目标文件已存在且与源文件相同，不需要再次处理
            # [EN] If the target file already exists and is the same as the source, skip processing
            if os.path.exists(target_file):
                try:
                    if os.path.samefile(source_file, target_file):
                        return target_file
                except OSError:
                    # 如果无法比较（例如跨文件系统），继续处理
                    # [EN] If comparison fails (e.g. cross-filesystem), continue processing
                    pass

            # 1. 复制或移动文件到工作目录
            # [EN] 1. Copy or move the file to the working directory
            if not os.path.exists(os.path.dirname(target_file)):
                os.makedirs(os.path.dirname(target_file), exist_ok=True)

            if process_mode == "move":
                shutil.move(source_file, target_file)
            else:
                shutil.copy2(source_file, target_file)

            # 2. 检查必要兼容性。WW3 源码按维度名读取，不需要重排维度或改写 time
            # units/calendar；规则经纬网下纬度递减会被 ww3_prnc 硬拒绝。
            # [EN] 2. Check necessary compatibility. WW3 reads dimensions by name, so
            # this generic path does not reorder dimensions or rewrite time
            # units/calendar; descending latitude is rejected by ww3_prnc for regular
            # lat/lon grids.
            needs_fix_wind_vars = False
            has_wndewd = False
            has_wndnwd = False
            lat_flip_dimension = None

            with Dataset(target_file, "r") as f:
                # 检查是否需要修复风场变量名（wndewd/wndnwd -> u10/v10）
                # [EN] Check if wind variable names need fixing (wndewd/wndnwd -> u10/v10)
                if "wndewd" in f.variables or "WNDEWD" in f.variables:
                    has_wndewd = True
                if "wndnwd" in f.variables or "WNDNWD" in f.variables:
                    has_wndnwd = True
                
                # 如果存在 wndewd/wndnwd 且不存在 u10/v10，需要修复
                # [EN] If wndewd/wndnwd exist and u10/v10 do not, fixing is needed
                if has_wndewd and has_wndnwd:
                    if "u10" not in f.variables and "v10" not in f.variables:
                        needs_fix_wind_vars = True

                lat_name = self._find_coord_name(f.variables.keys(), self._LAT_NAMES)
                lon_name = self._find_coord_name(f.variables.keys(), self._LON_NAMES)
                if lat_name:
                    lat_flip_dimension = self._decreasing_1d_coord_dimension(
                        f.variables[lat_name], "纬度"
                    )
                if lon_name:
                    lon_flip_dimension = self._decreasing_1d_coord_dimension(
                        f.variables[lon_name], "经度"
                    )
                    if lon_flip_dimension:
                        raise ValueError(
                            tr(
                                "log_lon_descending_not_supported",
                                "经度坐标为递减顺序，WW3 插值假设经度递增；请先将经度调整为递增后再导入",
                            )
                        )

            # 3. 如果需要修复风场变量名，需要重新创建文件（因为 netCDF4 不支持删除变量）
            # [EN] 3. If wind variable names need fixing, recreate the file (netCDF4 does not support deleting variables)
            if needs_fix_wind_vars:
                try:
                    with Dataset(target_file, "r") as src:
                        # 确定变量名（处理大小写）
                        # [EN] Determine variable names (handle case)
                        wndewd_name = "wndewd" if "wndewd" in src.variables else "WNDEWD"
                        wndnwd_name = "wndnwd" if "wndnwd" in src.variables else "WNDNWD"
                    self._rewrite_wind_vars_to_u10_v10(target_file, wndewd_name, wndnwd_name)
                    self.log(tr("log_wind_vars_fixed", "✅ 已修复风场变量名：wndewd/wndnwd -> u10/v10"))
                except Exception as e:
                    # 记录详细错误信息
                    # [EN] Log detailed error message
                    self.log(tr("log_wind_vars_fix_failed", "⚠️ 修复风场变量名失败: {error}").format(error=str(e)))
                    # 不抛出异常，继续处理，让调用者决定如何处理
                    # [EN] Do not raise; continue processing and let the caller decide how to handle

            if lat_flip_dimension:
                self._flip_dimension_in_place(target_file, lat_flip_dimension)
                self.log(tr("log_lat_flipped", "✅ 已翻转纬度坐标方向（递减→递增）"))

            return target_file

        except Exception as e:
            # 修复失败时记录但不中断流程
            # [EN] Log but do not interrupt the workflow if fixing fails
            self.log(f"{tr('log_copy_fix_failed', '❌ 复制或修复文件失败')}: {e}")
            return None

    def scan_forcing_files(self, selected_folder: str) -> Step1Files:
        """扫描工作目录，推断 wind/current/level/ice 四类场对应的 NetCDF 路径。

        [EN] Scan the working directory and infer NetCDF paths for wind/current/level/ice fields.

        匹配顺序：单场标准名（``wind.nc`` 等）→ 组合文件名解析 → 打开文件做变量检测。
        不修改 UI，返回 ``Step1Files`` 供 CLI 或 ViewModel 使用。

        [EN] Matching order: single-field standard names (``wind.nc``, etc.) -> combined filename parsing
        -> open file and detect variables. Does not modify the UI; returns ``Step1Files``
        for CLI or ViewModel use.
        """
        files = Step1Files()
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
        """扫描工作目录并将检测结果同步到桌面端 Step 1 控件。

        [EN] Scan the working directory and sync detection results to the desktop Step 1 controls.

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
