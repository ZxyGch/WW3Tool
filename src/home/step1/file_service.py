"""
文件操作服务模块
负责文件的复制、移动、修复等操作
"""
import os
import shutil
import glob
from netCDF4 import Dataset
from typing import Optional
from setting.language_manager import tr
from .file_path_manager import FilePathManager


class FileService:
    """文件操作服务类"""
    
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
        if self.logger and hasattr(self.logger, 'log'):
            self.logger.log(msg)

    def _rewrite_wind_vars_to_u10_v10(self, source_path: str, wndewd_name: str, wndnwd_name: str) -> None:
        """重写文件，将 wndewd/wndnwd 变量重命名为 u10/v10，并保持变量属性/压缩设置"""
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

    def detect_and_fill_forcing_fields(self, instance, selected_folder: str):
        """
        检测工作目录中符合规范的强迫场文件，并自动填充相应的按钮
        
        参数:
            instance: 主窗口实例（需要包含按钮和文件路径属性）
            selected_folder: 工作目录路径
        """
        try:
            # 重置按钮文本
            if hasattr(instance, 'btn_choose_wind_file'):
                default_text = tr("step1_choose_wind", "选择风场")
                if hasattr(instance, '_set_home_forcing_button_text'):
                    instance._set_home_forcing_button_text(instance.btn_choose_wind_file, default_text, filled=False)
                else:
                    instance.btn_choose_wind_file.setText(default_text)
            if hasattr(instance, 'selected_origin_file'):
                instance.selected_origin_file = None

            if hasattr(instance, 'btn_choose_current_file'):
                default_text = tr("step1_choose_current", "选择流场")
                if hasattr(instance, '_set_home_forcing_button_text'):
                    instance._set_home_forcing_button_text(instance.btn_choose_current_file, default_text, filled=False)
                else:
                    instance.btn_choose_current_file.setText(default_text)
            if hasattr(instance, 'selected_current_file'):
                instance.selected_current_file = None

            if hasattr(instance, 'btn_choose_level_file'):
                default_text = tr("step1_choose_level", "选择水位场")
                if hasattr(instance, '_set_home_forcing_button_text'):
                    instance._set_home_forcing_button_text(instance.btn_choose_level_file, default_text, filled=False)
                else:
                    instance.btn_choose_level_file.setText(default_text)
            if hasattr(instance, 'selected_level_file'):
                instance.selected_level_file = None

            if hasattr(instance, 'btn_choose_ice_file_home'):
                default_text = tr("step1_choose_ice", "选择海冰场")
                if hasattr(instance, '_set_home_forcing_button_text'):
                    instance._set_home_forcing_button_text(instance.btn_choose_ice_file_home, default_text, filled=False)
                else:
                    instance.btn_choose_ice_file_home.setText(default_text)
            if hasattr(instance, 'selected_ice_file'):
                instance.selected_ice_file = None

            # 查找文件
            nc_files = glob.glob(os.path.join(selected_folder, "*.nc"))
            field_patterns = {
                'wind': ['wind.nc'],
                'current': ['current.nc'],
                'level': ['level.nc'],
                'ice': ['ice.nc']
            }
            found_files = {}
            
            # 先查找单场文件
            for field_name, patterns in field_patterns.items():
                for pattern in patterns:
                    file_path = os.path.join(selected_folder, pattern)
                    if os.path.exists(file_path):
                        found_files[field_name] = file_path
                        break
            
            # 再查找多场文件
            for nc_file in nc_files:
                filename = os.path.basename(nc_file)
                fields = self.path_manager.parse_forcing_filename(filename)
                if len(fields) > 1:
                    for field in fields:
                        if field not in found_files:
                            found_files[field] = nc_file
                        elif found_files[field] == os.path.join(selected_folder, f"{field}.nc"):
                            pass  # 单场文件优先
            
            # 更新UI和状态
            for field_name, file_path in found_files.items():
                file_name = os.path.basename(file_path)
                display_name = file_name[:27] + "..." if len(file_name) > 30 else file_name
                
                if field_name == 'wind':
                    if hasattr(instance, '_set_wind_file_button_text'):
                        instance._set_wind_file_button_text(display_name, filled=True)
                    elif hasattr(instance, 'btn_choose_wind_file'):
                        if hasattr(instance, '_set_home_forcing_button_text'):
                            instance._set_home_forcing_button_text(instance.btn_choose_wind_file, display_name, filled=True)
                        else:
                            instance.btn_choose_wind_file.setText(display_name)
                    if not getattr(instance, 'selected_origin_file', None):
                        instance.selected_origin_file = file_path
                elif field_name == 'current':
                    if hasattr(instance, 'selected_current_file'):
                        instance.selected_current_file = file_path
                    if hasattr(instance, 'btn_choose_current_file'):
                        if hasattr(instance, '_set_home_forcing_button_text'):
                            instance._set_home_forcing_button_text(instance.btn_choose_current_file, display_name, filled=True)
                        else:
                            instance.btn_choose_current_file.setText(display_name)
                elif field_name == 'level':
                    if hasattr(instance, 'selected_level_file'):
                        instance.selected_level_file = file_path
                    if hasattr(instance, 'btn_choose_level_file'):
                        if hasattr(instance, '_set_home_forcing_button_text'):
                            instance._set_home_forcing_button_text(instance.btn_choose_level_file, display_name, filled=True)
                        else:
                            instance.btn_choose_level_file.setText(display_name)
                elif field_name == 'ice':
                    if hasattr(instance, 'selected_ice_file'):
                        instance.selected_ice_file = file_path
                    if hasattr(instance, 'btn_choose_ice_file_home'):
                        if hasattr(instance, '_set_home_forcing_button_text'):
                            instance._set_home_forcing_button_text(instance.btn_choose_ice_file_home, display_name, filled=True)
                        else:
                            instance.btn_choose_ice_file_home.setText(display_name)
            
            # 更新显示
            if hasattr(instance, '_update_forcing_fields_display'):
                instance._update_forcing_fields_display()
        except Exception:
            pass
