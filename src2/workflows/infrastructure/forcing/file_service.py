"""WW3 Step 1 强迫场文件 I/O 与格式修复服务。

用户选定 NetCDF 后，本模块负责将其复制或移动到工作目录，并在副本上执行
WW3 兼容性格式修正，包括：

- 时间变量 ``calendar`` 设为 ``standard``，``units`` 去掉多余时分秒；
- 将 ``wndewd/wndnwd`` 重命名为 ``u10/v10``（部分再分析产品使用旧名）；
- 扫描工作目录，按文件名规则或变量检测恢复 Step 1 四类场路径。
"""
import os
import shutil
import glob
from netCDF4 import Dataset
from typing import Optional
from ...domain.forcing_fields import ForcingField, Step1Files
from ...support.translations import tr
from .file_path_manager import FilePathManager
from .variable_detector import VariableDetector


class FileService:
    """强迫场文件的复制、修复与工作目录扫描服务。

    参数:
        logger: 可选日志对象，需实现 ``log`` 方法或 Qt ``log_signal``。
    """
    
    def __init__(self, logger=None):
        """
        初始化文件服务
        
        参数:
            logger: 日志记录器（需要包含 log 方法）
        """
        self.logger = logger
        self.path_manager = FilePathManager()
    
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

    def _rewrite_wind_vars_to_u10_v10(self, source_path: str, wndewd_name: str, wndnwd_name: str) -> None:
        """原地重写 NetCDF，将 wndewd/wndnwd 重命名为 u10/v10。

        netCDF4 不支持删除变量，故通过临时文件完整复制并替换变量名，
        保留全局属性、维度、压缩与 ``_FillValue`` 设置。
        """
        temp_file = source_path + ".tmp"
        with Dataset(source_path, "r") as src:
            file_format = getattr(src, "file_format", "NETCDF4")
            with Dataset(temp_file, "w", format=file_format) as dst:
                # 复制全局属性
                for attr_name in src.ncattrs():
                    dst.setncattr(attr_name, src.getncattr(attr_name))

                # 复制维度
                for dim_name, dim in src.dimensions.items():
                    dst.createDimension(dim_name, len(dim) if not dim.isunlimited() else None)

                # 复制变量（wndewd/wndnwd -> u10/v10）
                for var_name, var in src.variables.items():
                    if var_name == wndewd_name:
                        new_name = "u10"
                    elif var_name == wndnwd_name:
                        new_name = "v10"
                    else:
                        new_name = var_name

                    # 处理 _FillValue 与过滤器
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
    
    def copy_and_fix_forcing_file(self, source_file: str, target_file: str, process_mode: str = "copy") -> Optional[str]:
        """
        复制或移动强迫场文件到工作目录，并修复时间变量格式问题和风场变量名（如果存在）
        
        参数:
            source_file: 源文件路径
            target_file: 目标文件路径
            process_mode: 处理方式，"copy" 或 "move"
        
        返回:
            目标文件路径，如果失败返回 None
        """
        try:
            # 如果目标文件已存在且与源文件相同，不需要再次处理
            if os.path.exists(target_file):
                try:
                    if os.path.samefile(source_file, target_file):
                        return target_file
                except OSError:
                    # 如果无法比较（例如跨文件系统），继续处理
                    pass

            # 1. 复制或移动文件到工作目录
            if not os.path.exists(os.path.dirname(target_file)):
                os.makedirs(os.path.dirname(target_file), exist_ok=True)

            if process_mode == "move":
                shutil.move(source_file, target_file)
            else:
                shutil.copy2(source_file, target_file)

            # 2. 检查是否存在格式问题
            needs_fix_calendar = False
            needs_fix_units = False
            needs_fix_wind_vars = False
            time_var_name = None
            old_units = None
            new_units = None
            has_wndewd = False
            has_wndnwd = False

            with Dataset(target_file, "r") as f:
                # 查找时间变量
                for var_name in ["valid_time", "time", "Time", "TIME", "t", "MT", "mt"]:
                    if var_name in f.variables:
                        time_var_name = var_name
                        break

                # 检查是否需要修复风场变量名（wndewd/wndnwd -> u10/v10）
                if "wndewd" in f.variables or "WNDEWD" in f.variables:
                    has_wndewd = True
                if "wndnwd" in f.variables or "WNDNWD" in f.variables:
                    has_wndnwd = True
                
                # 如果存在 wndewd/wndnwd 且不存在 u10/v10，需要修复
                if has_wndewd and has_wndnwd:
                    if "u10" not in f.variables and "v10" not in f.variables:
                        needs_fix_wind_vars = True

                if time_var_name:
                    time_var = f.variables[time_var_name]

                    # 检查 Calendar 属性是否需要修复
                    current_calendar = getattr(time_var, 'calendar', None)
                    if current_calendar != 'standard':
                        needs_fix_calendar = True

                    # 检查时间单位格式是否需要修复
                    if hasattr(time_var, 'units') and time_var.units:
                        old_units = time_var.units
                        parts = old_units.split()
                        # 检查是否包含时间部分（第四部分包含 ":"，如 "00:00:00"）
                        if len(parts) >= 4 and ':' in parts[3]:
                            # 包含时间部分，只保留前三个部分（单位、since、日期）
                            new_units = ' '.join(parts[:3])
                            if new_units != old_units:
                                needs_fix_units = True
                        # 检查日期部分是否包含时间（如 "2025-01-01T00:00:00"）
                        elif len(parts) >= 3 and 'T' in parts[2]:
                            # 日期部分包含时间，移除 T 之后的内容
                            date_part = parts[2].split('T')[0]
                            new_units = f"{parts[0]} {parts[1]} {date_part}"
                            if new_units != old_units:
                                needs_fix_units = True

            # 3. 如果需要修复风场变量名，需要重新创建文件（因为 netCDF4 不支持删除变量）
            # 先处理风场变量修复，因为这会创建新文件，然后再处理时间变量修复
            if needs_fix_wind_vars:
                try:
                    with Dataset(target_file, "r") as src:
                        # 确定变量名（处理大小写）
                        wndewd_name = "wndewd" if "wndewd" in src.variables else "WNDEWD"
                        wndnwd_name = "wndnwd" if "wndnwd" in src.variables else "WNDNWD"
                    self._rewrite_wind_vars_to_u10_v10(target_file, wndewd_name, wndnwd_name)
                    self.log(tr("log_wind_vars_fixed", "✅ 已修复风场变量名：wndewd/wndnwd -> u10/v10"))
                except Exception as e:
                    # 记录详细错误信息
                    self.log(tr("log_wind_vars_fix_failed", "⚠️ 修复风场变量名失败: {error}").format(error=str(e)))
                    # 不抛出异常，继续处理，让调用者决定如何处理

            # 4. 如果存在时间变量格式问题，在工作目录的副本上进行修复
            # 注意：不使用 renameVariable/renameDimension 重命名 valid_time -> time，
            # 因为 netCDF4 在变量名与维度名相同时 rename 会导致数据损坏（全部变成 fill value）。
            # 变量名标准化由 reorder_nc 的 non-same-file 路径自动完成。
            if needs_fix_calendar or needs_fix_units:
                with Dataset(target_file, "r+") as f:
                    if time_var_name:
                        time_var = f.variables[time_var_name]

                        # 修复 Calendar 属性
                        if needs_fix_calendar:
                            time_var.calendar = 'standard'

                        # 修复时间单位格式
                        if needs_fix_units:
                            time_var.units = new_units

                        f.sync()

            return target_file

        except Exception as e:
            # 修复失败时记录但不中断流程
            self.log(tr("log_copy_fix_failed", "⚠️ 复制或修复文件时出错: {error}").format(error=e))
            return None

    def scan_forcing_files(self, selected_folder: str) -> Step1Files:
        """扫描工作目录，推断 wind/current/level/ice 四类场对应的 NetCDF 路径。

        匹配顺序：单场标准名（``wind.nc`` 等）→ 组合文件名解析 → 打开文件做变量检测。
        不修改 UI，返回 ``Step1Files`` 供 CLI 或 ViewModel 使用。
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

        内部调用 ``scan_forcing_files``，再更新 ``selected_*_file`` 属性及
        风/流/水位/海冰选择按钮的显示文本。

        参数:
            instance: 主窗口实例（需含按钮与 ``selected_*_file`` 属性）
            selected_folder: 当前 WW3 工作目录
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
