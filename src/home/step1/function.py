"""
第一步：选择强迫场文件模块 - 函数逻辑部分
包含所有业务逻辑函数（从 ui.py 拆分出来）

已拆分为多个服务模块：
- variable_detector.py: 变量检测服务
- file_path_manager.py: 文件路径管理
- file_service.py: 文件操作服务
- netcdf_info_service.py: NetCDF 信息处理服务
"""
import os
import glob
import shutil
import threading
import numpy as np
from netCDF4 import Dataset, num2date

from PyQt6.QtWidgets import QFileDialog
from qfluentwidgets import InfoBar
from setting.language_manager import tr
from setting.config import get_forcing_field_default_dir

# 导入服务模块
from .variable_detector import VariableDetector
from .file_path_manager import FilePathManager
from .file_service import FileService
from .netcdf_info_service import NetCDFInfoService


class StepOneFunctionsMixin:
    """第一步相关的函数逻辑 Mixin"""

    def _set_home_forcing_button_text(self, button, text: str, filled: bool = False):
        """设置主页强迫场按钮文本并根据状态着色"""
        if not button:
            return
        button.setText(text)
        try:
            button.setProperty("filled", filled)
        except Exception:
            pass
        if hasattr(self, '_get_button_style'):
            base_style = self._get_button_style()
            button.setStyleSheet(base_style)
            try:
                button.style().unpolish(button)
                button.style().polish(button)
            except Exception:
                pass
    
    @property
    def variable_detector(self):
        """获取变量检测服务实例（延迟初始化）"""
        if not hasattr(self, '_variable_detector') or self._variable_detector is None:
            self._variable_detector = VariableDetector()
        return self._variable_detector
    
    @property
    def file_path_manager(self):
        """获取文件路径管理服务实例（延迟初始化）"""
        if not hasattr(self, '_file_path_manager') or self._file_path_manager is None:
            self._file_path_manager = FilePathManager()
        return self._file_path_manager
    
    @property
    def file_service(self):
        """获取文件操作服务实例（延迟初始化）"""
        if not hasattr(self, '_file_service') or self._file_service is None:
            self._file_service = FileService(logger=self)
        return self._file_service
    
    @property
    def netcdf_info_service(self):
        """获取 NetCDF 信息服务实例（延迟初始化）"""
        if not hasattr(self, '_netcdf_info_service') or self._netcdf_info_service is None:
            self._netcdf_info_service = NetCDFInfoService(logger=self)
        return self._netcdf_info_service

    def choose_wind_field_file(self):
        """选择风场文件并自动转换（保留转换纬度的逻辑）"""
        default_dir = get_forcing_field_default_dir()

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("wind_file_dialog_title", "选择风场文件"),
            default_dir,
            tr("wind_file_filter", "NetCDF 文件 (*.nc);;所有文件 (*.*)")
        )

        if not file_path:
            return

        self.netcdf_info_service.print_nc_file_info(file_path)

        if not self.variable_detector.check_wind_variables(file_path):
            InfoBar.warning(
                title=tr("wind_file_missing_vars", "缺少风场变量"),
                content=tr("wind_file_missing_vars_msg", "文件不包含风场变量（u10/v10），请选择正确的风场文件"),
                duration=3000,
                parent=self
            )
            return

        if not getattr(self, 'selected_folder', None):
            self.log(tr("log_please_select_workdir", "❌ 请先选择或创建工作目录！"))
            return

        from setting.config import load_config
        config = load_config()
        auto_associate = config.get("FORCING_FIELD_AUTO_ASSOCIATE", True)
        process_mode = config.get("FORCING_FIELD_FILE_PROCESS_MODE", "copy")
        fields = self.variable_detector.detect_forcing_fields(file_path)


        if not fields:
            fields = ["wind"]
        
        if auto_associate:
            target_filename = self.file_path_manager.generate_forcing_filename(fields, auto_associate=True)
        else:
            target_filename = self.file_path_manager.generate_forcing_filename(["wind"], auto_associate=False)
        
        target_file = os.path.join(self.selected_folder, target_filename)
        
        if auto_associate and len(fields) > 1:
            self.log(tr("log_detected_multi_forcing", "ℹ️ 检测到文件包含多个强迫场: {fields}").format(
                fields=', '.join(fields)))
            self.log(tr("log_file_will_save_as", "📁 文件将保存为: {filename}").format(filename=target_filename))
       
        need_process = True
        
        if os.path.exists(target_file):
            try:
                if os.path.samefile(file_path, target_file):
                    self.log(tr("log_file_exists_same", "ℹ️ 文件已存在于工作目录且与源文件相同: {filename}").format(
                        filename=target_filename))
                    need_process = False
                else:
                    self.log(tr("log_target_exists_overwrite", "ℹ️ 目标文件已存在，将覆盖: {filename}").format(
                        filename=target_filename))
            except OSError:
                self.log(tr("log_target_exists_overwrite", "ℹ️ 目标文件已存在，将覆盖: {filename}").format(
                    filename=target_filename))
        detected_fields = {}
        
        if auto_associate:
            detected_fields = self.variable_detector.detect_all_forcing_fields_in_file(file_path)
        
        if need_process:
            copied_file = self.file_service.copy_and_fix_forcing_file(file_path, target_file, process_mode)
            if not copied_file:
                self.log(tr("log_copy_fix_failed", "❌ 复制或修复文件失败！"))
                return
        
        actual_file_path = target_file if need_process or os.path.exists(target_file) else file_path
        
        if process_mode == "move" and need_process:
            actual_file_path = target_file
            normalized_file_path = os.path.normpath(target_file)
        else:
            normalized_file_path = os.path.normpath(file_path)
        
        self.selected_origin_file = actual_file_path
        
        if auto_associate and detected_fields:
            if detected_fields.get("current", False):
                self.file_path_manager.set_file_path(self, "current", actual_file_path, target_filename)
            if detected_fields.get("level", False):
                self.file_path_manager.set_file_path(self, "level", actual_file_path, target_filename)
            if detected_fields.get("ice", False):
                self.file_path_manager.set_file_path(self, "ice", actual_file_path, target_filename)
        
        # 精简日志：不输出自动转换过程中的提示
        
        # 使用目标文件名更新按钮（actual_file_path 是目标文件路径）
        file_name = os.path.basename(actual_file_path)
        
        if len(file_name) > 30:
            file_name = file_name[:27] + "..."
        
        # 更新所有相关的按钮（step1 + plot）
        if hasattr(self, '_set_wind_file_button_text'):
            self._set_wind_file_button_text(file_name, filled=True)
        elif hasattr(self, 'btn_choose_wind_file'):
            self._set_home_forcing_button_text(self.btn_choose_wind_file, file_name, filled=True)
        
        self._update_forcing_fields_display()
        
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(500, lambda: self._load_latlon_from_source_file(file_path))
        threading.Thread(target=self._convert_file_thread, daemon=True).start()



    def choose_current_field_file(self):
        """选择流场文件"""
        default_dir = get_forcing_field_default_dir()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("current_file_dialog_title", "选择流场文件"),
            default_dir,
            tr("wind_file_filter", "NetCDF 文件 (*.nc);;所有文件 (*.*)")
        )

        if not file_path:
            return

        self.netcdf_info_service.print_nc_file_info(file_path)

        if not self.variable_detector.check_current_variables(file_path):
            InfoBar.warning(
                title=tr("current_file_missing_vars", "缺少流场变量"),
                content=tr("current_file_missing_vars_msg", "文件不包含流场变量（uo/vo），请选择正确的流场文件"),
                duration=3000,
                parent=self
            )
            return

        if not getattr(self, 'selected_folder', None):
            self.log(tr("log_please_select_workdir", "❌ 请先选择或创建工作目录！"))
            return

        from setting.config import load_config
        config = load_config()

        auto_associate = config.get("FORCING_FIELD_AUTO_ASSOCIATE", True)
        process_mode = config.get("FORCING_FIELD_FILE_PROCESS_MODE", "copy")
        fields = self.variable_detector.detect_forcing_fields(file_path)

        if not fields:
            fields = ["current"]
        if auto_associate:
            target_filename = self.file_path_manager.generate_forcing_filename(fields, auto_associate=True)
        else:
            target_filename = self.file_path_manager.generate_forcing_filename(["current"], auto_associate=False)

        target_file = os.path.join(self.selected_folder, target_filename)

        if auto_associate and len(fields) > 1:
            self.log(tr("log_detected_multi_forcing", "ℹ️ 检测到文件包含多个强迫场: {fields}").format(
                fields=', '.join(fields)))
            self.log(tr("log_file_will_save_as", "📁 文件将保存为: {filename}").format(filename=target_filename))
        detected_fields = {}

        if auto_associate:
            detected_fields = self.variable_detector.detect_all_forcing_fields_in_file(file_path)

        need_process = True

        if os.path.exists(target_file):
            try:
                if os.path.samefile(file_path, target_file):
                    self.log(tr("log_file_exists_same", "ℹ️ 文件已存在于工作目录且与源文件相同: {filename}").format(
                        filename=target_filename))
                    need_process = False
                else:
                    self.log(tr("log_target_exists_overwrite", "ℹ️ 目标文件已存在，将覆盖: {filename}").format(
                        filename=target_filename))
            except OSError:
                self.log(tr("log_target_exists_overwrite", "ℹ️ 目标文件已存在，将覆盖: {filename}").format(
                    filename=target_filename))

        if need_process:
            copied_file = self.file_service.copy_and_fix_forcing_file(file_path, target_file, process_mode)
            if not copied_file:
                self.log(tr("log_copy_fix_failed", "❌ 复制或修复文件失败！"))
                return

        actual_file_path = target_file if need_process or os.path.exists(target_file) else file_path

        if process_mode == "move" and need_process:
            normalized_file_path = os.path.normpath(target_file)
        else:
            normalized_file_path = os.path.normpath(file_path)

        self.selected_current_file = actual_file_path

        if auto_associate and detected_fields:
            if detected_fields.get("level", False):
                self.file_path_manager.set_file_path(self, "level", actual_file_path, target_filename)
            if detected_fields.get("wind", False):
                self.file_path_manager.set_file_path(self, "wind", actual_file_path, target_filename)
            if detected_fields.get("ice", False):
                self.file_path_manager.set_file_path(self, "ice", actual_file_path, target_filename)
        
        self.log(tr("current_file_selected", "📂 已选择流场文件: {path}").format(path=normalized_file_path))
        
        file_name = target_filename

        if len(file_name) > 30:
            file_name = file_name[:27] + "..."

        self._set_home_forcing_button_text(self.btn_choose_current_file, file_name, filled=True)

        self._update_forcing_fields_display()



    def choose_level_field_file(self):
        """选择水位场文件"""
        default_dir = get_forcing_field_default_dir()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("level_file_dialog_title", "选择水位场文件"),
            default_dir,
            tr("wind_file_filter", "NetCDF 文件 (*.nc);;所有文件 (*.*)")
        )
        if not file_path:
            return
        self.netcdf_info_service.print_nc_file_info(file_path)
        if not self.variable_detector.check_level_variables(file_path):
            InfoBar.warning(
                title=tr("level_file_missing_vars", "缺少水位场变量"),
                content=tr("level_file_missing_vars_msg", "文件不包含水位场变量（zos），请选择正确的水位场文件"),
                duration=3000,
                parent=self
            )
            return
        if not getattr(self, 'selected_folder', None):
            self.log(tr("log_please_select_workdir", "❌ 请先选择或创建工作目录！"))
            return
        from setting.config import load_config
        config = load_config()
        auto_associate = config.get("FORCING_FIELD_AUTO_ASSOCIATE", True)
        process_mode = config.get("FORCING_FIELD_FILE_PROCESS_MODE", "copy")
        fields = self.variable_detector.detect_forcing_fields(file_path)
        if not fields:
            fields = ["level"]
        if auto_associate:
            target_filename = self.file_path_manager.generate_forcing_filename(fields, auto_associate=True)
        else:
            target_filename = self.file_path_manager.generate_forcing_filename(["level"], auto_associate=False)
        target_file = os.path.join(self.selected_folder, target_filename)
        if auto_associate and len(fields) > 1:
            self.log(tr("log_detected_multi_forcing", "ℹ️ 检测到文件包含多个强迫场: {fields}").format(
                fields=', '.join(fields)))
            self.log(tr("log_file_will_save_as", "📁 文件将保存为: {filename}").format(filename=target_filename))
        need_process = True
        if os.path.exists(target_file):
            try:
                if os.path.samefile(file_path, target_file):
                    self.log(tr("log_file_exists_same", "ℹ️ 文件已存在于工作目录且与源文件相同: {filename}").format(
                        filename=target_filename))
                    need_process = False
                else:
                    self.log(tr("log_target_exists_overwrite", "ℹ️ 目标文件已存在，将覆盖: {filename}").format(
                        filename=target_filename))
            except OSError:
                self.log(tr("log_target_exists_overwrite", "ℹ️ 目标文件已存在，将覆盖: {filename}").format(
                    filename=target_filename))
        if need_process:
            copied_file = self.file_service.copy_and_fix_forcing_file(file_path, target_file, process_mode)
            if not copied_file:
                self.log(tr("log_copy_fix_failed", "❌ 复制或修复文件失败！"))
                return
        normalized_file_path = os.path.normpath(file_path)
        self.selected_level_file = target_file if need_process or os.path.exists(target_file) else normalized_file_path
        self.log(tr("level_file_selected", "📂 已选择水位场文件: {path}").format(path=normalized_file_path))
        file_name = target_filename
        if len(file_name) > 30:
            file_name = file_name[:27] + "..."
        self._set_home_forcing_button_text(self.btn_choose_level_file, file_name, filled=True)
        detected_fields = {}
        if auto_associate:
            detected_fields = self.variable_detector.detect_all_forcing_fields_in_file(file_path)
        if auto_associate and detected_fields:
            actual_file_path = target_file if need_process or os.path.exists(target_file) else file_path
            if detected_fields.get("current", False):
                self.file_path_manager.set_file_path(self, "current", actual_file_path, target_filename)
            if detected_fields.get("wind", False):
                self.file_path_manager.set_file_path(self, "wind", actual_file_path, target_filename)
            if detected_fields.get("ice", False):
                self.file_path_manager.set_file_path(self, "ice", actual_file_path, target_filename)
        self._update_forcing_fields_display()

    def choose_ice_field_file(self):
        """选择海冰场文件"""
        default_dir = get_forcing_field_default_dir()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("ice_file_dialog_title", "选择海冰场文件"),
            default_dir,
            tr("wind_file_filter", "NetCDF 文件 (*.nc);;所有文件 (*.*)")
        )
        if not file_path:
            return
        self.netcdf_info_service.print_nc_file_info(file_path)
        if not self.variable_detector.check_ice_variables(file_path):
            InfoBar.warning(
                title=tr("ice_file_missing_vars", "缺少海冰场变量"),
                content=tr("ice_file_missing_vars_msg", "文件不包含海冰场变量（siconc），请选择正确的海冰场文件"),
                duration=3000,
                parent=self
            )
            return
        if not getattr(self, 'selected_folder', None):
            self.log(tr("log_please_select_workdir", "❌ 请先选择或创建工作目录！"))
            return
        from setting.config import load_config
        config = load_config()
        auto_associate = config.get("FORCING_FIELD_AUTO_ASSOCIATE", True)
        process_mode = config.get("FORCING_FIELD_FILE_PROCESS_MODE", "copy")
        fields = self.variable_detector.detect_forcing_fields(file_path)
        if not fields:
            fields = ["ice"]
        if auto_associate:
            target_filename = self.file_path_manager.generate_forcing_filename(fields, auto_associate=True)
        else:
            target_filename = self.file_path_manager.generate_forcing_filename(["ice"], auto_associate=False)
        target_file = os.path.join(self.selected_folder, target_filename)
        if auto_associate and len(fields) > 1:
            self.log(tr("log_detected_multi_forcing", "ℹ️ 检测到文件包含多个强迫场: {fields}").format(
                fields=', '.join(fields)))
            self.log(tr("log_file_will_save_as", "📁 文件将保存为: {filename}").format(filename=target_filename))
        need_process = True
        if os.path.exists(target_file):
            try:
                if os.path.samefile(file_path, target_file):
                    self.log(tr("log_file_exists_same", "ℹ️ 文件已存在于工作目录且与源文件相同: {filename}").format(
                        filename=target_filename))
                    need_process = False
                else:
                    self.log(tr("log_target_exists_overwrite", "ℹ️ 目标文件已存在，将覆盖: {filename}").format(
                        filename=target_filename))
            except OSError:
                self.log(tr("log_target_exists_overwrite", "ℹ️ 目标文件已存在，将覆盖: {filename}").format(
                    filename=target_filename))
        if need_process:
            copied_file = self.file_service.copy_and_fix_forcing_file(file_path, target_file, process_mode)
            if not copied_file:
                self.log(tr("log_copy_fix_failed", "❌ 复制或修复文件失败！"))
                return
        if process_mode == "move" and need_process:
            self.selected_ice_file = target_file
            normalized_file_path = os.path.normpath(target_file)
        else:
            self.selected_ice_file = target_file if need_process or os.path.exists(target_file) else file_path
            normalized_file_path = os.path.normpath(file_path)
        self.log(tr("ice_file_selected", "📂 已选择海冰场文件: {path}").format(path=normalized_file_path))
        file_name = target_filename
        if len(file_name) > 30:
            file_name = file_name[:27] + "..."
        self._set_home_forcing_button_text(self.btn_choose_ice_file_home, file_name, filled=True)
        detected_fields = {}
        if auto_associate:
            detected_fields = self.variable_detector.detect_all_forcing_fields_in_file(file_path)
        if auto_associate and detected_fields:
            actual_file_path = target_file if need_process or os.path.exists(target_file) else file_path
            if detected_fields.get("current", False):
                self.file_path_manager.set_file_path(self, "current", actual_file_path, target_filename)
            if detected_fields.get("wind", False):
                self.file_path_manager.set_file_path(self, "wind", actual_file_path, target_filename)
            if detected_fields.get("level", False):
                self.file_path_manager.set_file_path(self, "level", actual_file_path, target_filename)
        self._update_forcing_fields_display()

    def _detect_and_fill_forcing_fields(self):
        """检测工作目录中符合规范的强迫场文件，并自动填充相应的按钮"""
        if hasattr(self, 'selected_folder') and self.selected_folder:
            self.file_service.detect_and_fill_forcing_fields(self, self.selected_folder)

    def view_all_field_files_info(self):
        """查看所有场文件的信息，输出到log"""
        field_files = []
        if getattr(self, 'selected_origin_file', None) and os.path.exists(str(self.selected_origin_file)):
            field_files.append((tr("step4_forcing_field_wind", "风场"), self.selected_origin_file))
        if getattr(self, 'selected_current_file', None) and os.path.exists(str(self.selected_current_file)):
            field_files.append((tr("step4_forcing_field_current", "流场"), self.selected_current_file))
        if getattr(self, 'selected_level_file', None) and os.path.exists(str(self.selected_level_file)):
            field_files.append((tr("step4_forcing_field_level", "水位场"), self.selected_level_file))
        if getattr(self, 'selected_ice_file', None) and os.path.exists(str(self.selected_ice_file)):
            field_files.append((tr("step4_forcing_field_ice", "海冰场"), self.selected_ice_file))
        if not field_files:
            self.log(tr("view_no_field_files", "❌ 没有已选择的场文件，请先选择场文件"))
            return
        for field_name, file_path in field_files:
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
            except Exception as e:
                self.log(tr("view_filesize_error", "文件大小：无法读取 ({error})").format(error=e))
            try:
                with Dataset(file_path, "r") as ds:
                    lon_min = lon_max = lat_min = lat_max = None
                    lon_var = lat_var = None
                    for lon_name in ["longitude", "lon", "Longitude", "LON"]:
                        if lon_name in ds.variables:
                            lon_var = ds.variables[lon_name]
                            lon = lon_var[:]
                            lon_min = float(np.min(lon))
                            lon_max = float(np.max(lon))
                            break
                    for lat_name in ["latitude", "lat", "Latitude", "LAT"]:
                        if lat_name in ds.variables:
                            lat_var = ds.variables[lat_name]
                            lat = lat_var[:]
                            lat_min = float(np.min(lat))
                            lat_max = float(np.max(lat))
                            break
                    if lon_min is not None and lon_max is not None:
                        self.log(tr("longitude_range", "🌍 经度范围：{min}° ~ {max}°").format(min=f"{lon_min:.6f}",
                                                                                            max=f"{lon_max:.6f}"))
                    if lat_min is not None and lat_max is not None:
                        self.log(tr("latitude_range", "🌍 纬度范围：{min}° ~ {max}°").format(min=f"{lat_min:.6f}",
                                                                                           max=f"{lat_max:.6f}"))
                    if lon_var is not None and len(lon_var) > 1:
                        lon_diff = np.diff(lon)
                        if len(lon_diff) > 0:
                            self.log(tr("view_lon_resolution", "经度精度：{val}°").format(
                                val=f"{float(np.mean(np.abs(lon_diff))):.6f}"))
                    if lat_var is not None and len(lat_var) > 1:
                        lat_diff = np.diff(lat)
                        if len(lat_diff) > 0:
                            self.log(tr("view_lat_resolution", "纬度精度：{val}°").format(
                                val=f"{float(np.mean(np.abs(lat_diff))):.6f}"))
                    time_var = None
                    time_var_name = None
                    for time_name in ["time", "Time", "TIME", "valid_time", "MT", "mt", "t"]:
                        if time_name in ds.variables:
                            time_var = ds.variables[time_name]
                            time_var_name = time_name
                            break
                    if time_var is not None:
                        try:
                            time_units = getattr(time_var, 'units', None)
                            time_calendar = getattr(time_var, 'calendar', 'gregorian')
                            if time_units:
                                times = num2date(time_var[:], time_units, calendar=time_calendar)
                                if len(times) > 0:
                                    time_start, time_end = times[0], times[-1]
                                    self.log(tr("time_range", "⏰ 时间范围：{start} ~ {end}").format(
                                        start=time_start.strftime('%Y-%m-%d %H:%M:%S'),
                                        end=time_end.strftime('%Y-%m-%d %H:%M:%S')))
                                    self.log(tr("time_steps", "⏰ 时间步数：{count}").format(count=len(times)))
                                    if len(times) > 1:
                                        time_diffs = [(times[i + 1] - times[i]).total_seconds() for i in
                                                      range(len(times) - 1)]
                                        if time_diffs:
                                            avg_time_diff = np.mean(time_diffs)
                                            if avg_time_diff < 60:
                                                time_res_str = f"{avg_time_diff:.0f} " + tr("view_unit_seconds", "秒")
                                            elif avg_time_diff < 3600:
                                                time_res_str = f"{avg_time_diff / 60:.1f} " + tr("view_unit_minutes",
                                                                                                 "分钟")
                                            elif avg_time_diff < 86400:
                                                time_res_str = f"{avg_time_diff / 3600:.2f} " + tr("view_unit_hours",
                                                                                                   "小时")
                                            else:
                                                time_res_str = f"{avg_time_diff / 86400:.2f} " + tr("view_unit_days",
                                                                                                    "天")
                                            self.log(tr("view_time_resolution", "时间精度：{resolution}").format(
                                                resolution=time_res_str))
                            else:
                                time_data = time_var[:]
                                if len(time_data) > 0:
                                    t_min, t_max = float(np.min(time_data)), float(np.max(time_data))
                                    self.log(tr("view_time_range_no_unit", "时间范围：{min} ~ {max} (无单位)").format(
                                        min=f"{t_min:.2f}", max=f"{t_max:.2f}"))
                                    self.log(tr("time_steps", "⏰ 时间步数：{count}").format(count=len(time_data)))
                        except Exception as e:
                            self.log(tr("view_time_parse_error", "时间范围：无法解析 ({error})").format(error=e))
                    else:
                        self.log(tr("view_time_var_missing", "时间范围：未找到时间变量"))
            except Exception as e:
                self.log(tr("read_file_info_failed", "❌ 读取文件信息失败：{error}").format(error=e))
        self.log("=" * 70)

    def _print_nc_file_info(self, file_path):
        """读取并输出 NetCDF 文件的基本信息"""
        self.netcdf_info_service.print_nc_file_info(file_path)

    # ========== 第一步相关的辅助函数（已迁移到服务模块，保留向后兼容）==========
    def _check_wind_variables(self, file_path):
        """检查文件是否包含风场变量（接受 u10/v10 或 wndewd/wndnwd）"""
        return self.variable_detector.check_wind_variables(file_path)

    def _check_current_variables(self, file_path):
        """检查文件是否包含流场变量（只接受 uo 和 vo）"""
        return self.variable_detector.check_current_variables(file_path)

    def _check_level_variables(self, file_path):
        """检查文件是否包含水位场变量（只接受 zos）"""
        return self.variable_detector.check_level_variables(file_path)

    def _check_ice_variables(self, file_path):
        """检查文件是否包含海冰场变量（只接受 siconc）"""
        return self.variable_detector.check_ice_variables(file_path)

    def _detect_all_forcing_fields_in_file(self, file_path):
        """检测文件包含的所有强迫场变量（不处理文件，只检测）"""
        return self.variable_detector.detect_all_forcing_fields_in_file(file_path)

    def _set_level_file_from_path(self, file_path, filename):
        """设置水位场文件路径（不复制/移动，只设置）"""
        self.file_path_manager.set_file_path(self, "level", file_path, filename)

    def _set_wind_file_from_path(self, file_path, filename):
        """设置风场文件路径（不复制/移动，只设置）"""
        self.file_path_manager.set_file_path(self, "wind", file_path, filename)

    def _set_ice_file_from_path(self, file_path, filename):
        """设置海冰场文件路径（不复制/移动，只设置）"""
        self.file_path_manager.set_file_path(self, "ice", file_path, filename)

    def _set_current_file_from_path(self, file_path, filename):
        """设置流场文件路径（不复制/移动，只设置）"""
        self.file_path_manager.set_file_path(self, "current", file_path, filename)

    def _detect_forcing_fields(self, file_path):
        """检测文件包含哪些强迫场"""
        return self.variable_detector.detect_forcing_fields(file_path)

    def _generate_forcing_filename(self, fields, auto_associate=True):
        """根据包含的强迫场生成文件名"""
        return self.file_path_manager.generate_forcing_filename(fields, auto_associate)

    def _parse_forcing_filename(self, filename):
        """解析强迫场文件名，提取包含的场"""
        return self.file_path_manager.parse_forcing_filename(filename)

    def _copy_and_fix_forcing_file(self, source_file, target_file, process_mode="copy"):
        """复制或移动强迫场文件到工作目录，并修复时间变量格式问题（如果存在）"""
        return self.file_service.copy_and_fix_forcing_file(source_file, target_file, process_mode)

    def _auto_detect_and_fill_level_if_present(self, file_path, target_file=None, process_mode="copy", work_dir=None):
        """检测文件是否包含水位场变量（zos），如果包含则自动填充水位场按钮"""
        try:
            # 检查自动关联是否开启
            from setting.config import load_config
            config = load_config()
            auto_associate = config.get("FORCING_FIELD_AUTO_ASSOCIATE", True)

            if not auto_associate:
                return

            # 检查源文件是否存在（如果已移动，源文件不存在）
            source_file_exists = os.path.exists(file_path)
            if not source_file_exists:
                # 如果源文件不存在，说明文件已经被移动了，使用 target_file
                if target_file and os.path.exists(target_file):
                    file_to_check = target_file
                else:
                    return
            else:
                file_to_check = file_path

            with Dataset(file_to_check, "r") as ds:
                # 只检查 zos
                if "zos" in ds.variables:
                    # 找到水位场变量，需要复制或移动到工作目录
                    if work_dir:
                        # 生成目标文件名
                        target_filename = self.file_path_manager.generate_forcing_filename(["level"], auto_associate=False)
                        target_file_path = os.path.join(work_dir, target_filename)

                        # 检查目标文件是否已存在且与源文件相同
                        need_process = True
                        if os.path.exists(target_file_path):
                            try:
                                if os.path.samefile(file_to_check, target_file_path):
                                    need_process = False
                            except OSError:
                                pass

                        # 根据设置复制或移动文件
                        if need_process:
                            if process_mode == "move" and source_file_exists:
                                # 移动文件
                                if not os.path.exists(os.path.dirname(target_file_path)):
                                    os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
                                shutil.move(file_path, target_file_path)
                                self.log(tr("log_detect_level_moved",
                                            "✂️ 检测到水位场变量 'zos'，已移动文件到工作目录: {filename}").format(
                                    filename=target_filename))
                                normalized_path = os.path.normpath(target_file_path)
                            else:
                                # 复制文件（如果源文件不存在，说明已经移动过了，使用 target_file）
                                if source_file_exists:
                                    copied_file = self.file_service.copy_and_fix_forcing_file(file_path, target_file_path, "copy")
                                else:
                                    # 源文件已移动，从 target_file 复制
                                    copied_file = self.file_service.copy_and_fix_forcing_file(file_to_check, target_file_path,
                                                                                  "copy")
                                if copied_file:
                                    self.log(tr("log_detect_level_copied",
                                                "📋 检测到水位场变量 'zos'，已复制文件到工作目录: {filename}").format(
                                        filename=target_filename))
                                    normalized_path = os.path.normpath(target_file_path)
                                else:
                                    normalized_path = os.path.normpath(file_to_check)
                        else:
                            normalized_path = os.path.normpath(target_file_path)
                    else:
                        # 如果没有提供工作目录，使用源文件路径或目标文件路径
                        if target_file:
                            normalized_path = os.path.normpath(target_file)
                        else:
                            normalized_path = os.path.normpath(file_to_check)

                    if not hasattr(self, 'selected_level_file'):
                        self.selected_level_file = None
                    self.selected_level_file = normalized_path

                    # 更新按钮文本
                    if hasattr(self, 'btn_choose_level_file'):
                        file_name = os.path.basename(normalized_path)
                        if len(file_name) > 30:
                            file_name = file_name[:27] + "..."
                        self._set_home_forcing_button_text(self.btn_choose_level_file, file_name, filled=True)

                    if not work_dir or not need_process:
                        self.log(tr("log_auto_fill_level", "✅ 检测到水位场变量 'zos'，已自动填充水位场"))
        except Exception as e:
            # 检测失败不影响主流程
            pass

    def _auto_detect_and_fill_current_if_present(self, file_path, target_file=None, process_mode="copy", work_dir=None):
        """检测文件是否包含流场变量（uo/vo），如果包含则自动填充流场按钮"""
        try:
            # 检查自动关联是否开启
            from setting.config import load_config
            config = load_config()
            auto_associate = config.get("FORCING_FIELD_AUTO_ASSOCIATE", True)

            if not auto_associate:
                return

            # 检查源文件是否存在（如果已移动，源文件不存在）
            source_file_exists = os.path.exists(file_path)
            if not source_file_exists:
                # 如果源文件不存在，说明文件已经被移动了，使用 target_file
                if target_file and os.path.exists(target_file):
                    file_to_check = target_file
                else:
                    return
            else:
                file_to_check = file_path

            with Dataset(file_to_check, "r") as ds:
                # 只检查 uo 和 vo
                has_uo = "uo" in ds.variables
                has_vo = "vo" in ds.variables

                if has_uo and has_vo:
                    # 找到流场变量，需要复制或移动到工作目录
                    if work_dir:
                        # 生成目标文件名
                        target_filename = self.file_path_manager.generate_forcing_filename(["current"], auto_associate=False)
                        target_file_path = os.path.join(work_dir, target_filename)

                        # 检查目标文件是否已存在且与源文件相同
                        need_process = True
                        if os.path.exists(target_file_path):
                            try:
                                if os.path.samefile(file_to_check, target_file_path):
                                    need_process = False
                            except OSError:
                                pass

                        # 根据设置复制或移动文件
                        if need_process:
                            if process_mode == "move" and source_file_exists:
                                # 移动文件
                                if not os.path.exists(os.path.dirname(target_file_path)):
                                    os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
                                shutil.move(file_path, target_file_path)
                                self.log(tr("log_detect_current_moved",
                                            "✂️ 检测到流场变量（uo/vo），已移动文件到工作目录: {filename}").format(
                                    filename=target_filename))
                                normalized_path = os.path.normpath(target_file_path)
                            else:
                                # 复制文件（如果源文件不存在，说明已经移动过了，使用 target_file）
                                if source_file_exists:
                                    copied_file = self.file_service.copy_and_fix_forcing_file(file_path, target_file_path, "copy")
                                else:
                                    # 源文件已移动，从 target_file 复制
                                    copied_file = self.file_service.copy_and_fix_forcing_file(file_to_check, target_file_path,
                                                                                  "copy")
                                if copied_file:
                                    self.log(tr("log_detect_current_copied",
                                                "📋 检测到流场变量（uo/vo），已复制文件到工作目录: {filename}").format(
                                        filename=target_filename))
                                    normalized_path = os.path.normpath(target_file_path)
                                else:
                                    normalized_path = os.path.normpath(file_to_check)
                        else:
                            normalized_path = os.path.normpath(target_file_path)
                    else:
                        # 如果没有提供工作目录，使用源文件路径或目标文件路径
                        if target_file:
                            normalized_path = os.path.normpath(target_file)
                        else:
                            normalized_path = os.path.normpath(file_to_check)

                    if not hasattr(self, 'selected_current_file'):
                        self.selected_current_file = None
                    self.selected_current_file = normalized_path

                    # 更新按钮文本
                    if hasattr(self, 'btn_choose_current_file'):
                        file_name = os.path.basename(normalized_path)
                        if len(file_name) > 30:
                            file_name = file_name[:27] + "..."
                        self._set_home_forcing_button_text(self.btn_choose_current_file, file_name, filled=True)

                    if not work_dir or not need_process:
                        self.log(tr("log_auto_fill_current", "✅ 检测到流场变量（uo/vo），已自动填充流场"))
        except Exception as e:
            # 检测失败不影响主流程
            pass

    def _auto_detect_and_fill_wind_if_present(self, file_path, target_file=None, process_mode="copy", work_dir=None):
        """检测文件是否包含风场变量（u10/v10），如果包含则自动填充风场按钮"""
        try:
            # 检查自动关联是否开启
            from setting.config import load_config
            config = load_config()
            auto_associate = config.get("FORCING_FIELD_AUTO_ASSOCIATE", True)

            if not auto_associate:
                return

            # 检查源文件是否存在（如果已移动，源文件不存在）
            source_file_exists = os.path.exists(file_path)
            if not source_file_exists:
                # 如果源文件不存在，说明文件已经被移动了，使用 target_file
                if target_file and os.path.exists(target_file):
                    file_to_check = target_file
                else:
                    return
            else:
                file_to_check = file_path

            with Dataset(file_to_check, "r") as ds:
                # 只检查 u10 和 v10
                has_u10 = "u10" in ds.variables
                has_v10 = "v10" in ds.variables

                if has_u10 and has_v10:
                    # 找到风场变量，需要复制或移动到工作目录
                    if work_dir:
                        # 生成目标文件名
                        target_filename = self.file_path_manager.generate_forcing_filename(["wind"], auto_associate=False)
                        target_file_path = os.path.join(work_dir, target_filename)

                        # 检查目标文件是否已存在且与源文件相同
                        need_process = True
                        if os.path.exists(target_file_path):
                            try:
                                if os.path.samefile(file_to_check, target_file_path):
                                    need_process = False
                            except OSError:
                                pass

                        # 根据设置复制或移动文件
                        if need_process:
                            if process_mode == "move" and source_file_exists:
                                # 移动文件
                                if not os.path.exists(os.path.dirname(target_file_path)):
                                    os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
                                shutil.move(file_path, target_file_path)
                                self.log(tr("log_detect_wind_moved",
                                            "✂️ 检测到风场变量（u10/v10），已移动文件到工作目录: {filename}").format(
                                    filename=target_filename))
                                normalized_path = os.path.normpath(target_file_path)
                            else:
                                # 复制文件（如果源文件不存在，说明已经移动过了，使用 target_file）
                                if source_file_exists:
                                    copied_file = self.file_service.copy_and_fix_forcing_file(file_path, target_file_path, "copy")
                                else:
                                    # 源文件已移动，从 target_file 复制
                                    copied_file = self.file_service.copy_and_fix_forcing_file(file_to_check, target_file_path,
                                                                                  "copy")
                                if copied_file:
                                    self.log(tr("log_detect_wind_copied",
                                                "📋 检测到风场变量（u10/v10），已复制文件到工作目录: {filename}").format(
                                        filename=target_filename))
                                    normalized_path = os.path.normpath(target_file_path)
                                else:
                                    normalized_path = os.path.normpath(file_to_check)
                        else:
                            normalized_path = os.path.normpath(target_file_path)
                    else:
                        # 如果没有提供工作目录，使用源文件路径或目标文件路径
                        if target_file:
                            normalized_path = os.path.normpath(target_file)
                        else:
                            normalized_path = os.path.normpath(file_to_check)

                    if not hasattr(self, 'selected_origin_file'):
                        self.selected_origin_file = None
                    self.selected_origin_file = normalized_path

                    # 更新按钮文本
                    if hasattr(self, 'btn_choose_wind_file'):
                        file_name = os.path.basename(normalized_path)
                        if len(file_name) > 30:
                            file_name = file_name[:27] + "..."
                        self._set_home_forcing_button_text(self.btn_choose_wind_file, file_name, filled=True)

                    if not work_dir or not need_process:
                        self.log(tr("log_auto_fill_wind", "✅ 检测到风场变量（u10/v10），已自动填充风场"))
        except Exception as e:
            # 检测失败不影响主流程
            pass

    def _auto_detect_and_fill_ice_if_present(self, file_path, target_file=None, process_mode="copy", work_dir=None):
        """检测文件是否包含海冰场变量（siconc），如果包含则自动填充海冰场按钮"""
        try:
            # 检查自动关联是否开启
            from setting.config import load_config
            config = load_config()
            auto_associate = config.get("FORCING_FIELD_AUTO_ASSOCIATE", True)

            if not auto_associate:
                return

            # 检查源文件是否存在（如果已移动，源文件不存在）
            source_file_exists = os.path.exists(file_path)
            if not source_file_exists:
                # 如果源文件不存在，说明文件已经被移动了，使用 target_file
                if target_file and os.path.exists(target_file):
                    file_to_check = target_file
                else:
                    return
            else:
                file_to_check = file_path

            with Dataset(file_to_check, "r") as ds:
                # 只检查 siconc
                if "siconc" in ds.variables:
                    # 找到海冰场变量，需要复制或移动到工作目录
                    if work_dir:
                        # 生成目标文件名
                        target_filename = self.file_path_manager.generate_forcing_filename(["ice"], auto_associate=False)
                        target_file_path = os.path.join(work_dir, target_filename)

                        # 检查目标文件是否已存在且与源文件相同
                        need_process = True
                        if os.path.exists(target_file_path):
                            try:
                                if os.path.samefile(file_to_check, target_file_path):
                                    need_process = False
                            except OSError:
                                pass

                        # 根据设置复制或移动文件
                        if need_process:
                            if process_mode == "move" and source_file_exists:
                                # 移动文件
                                if not os.path.exists(os.path.dirname(target_file_path)):
                                    os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
                                shutil.move(file_path, target_file_path)
                                self.log(tr("log_detect_ice_moved",
                                            "✂️ 检测到海冰场变量 'siconc'，已移动文件到工作目录: {filename}").format(
                                    filename=target_filename))
                                normalized_path = os.path.normpath(target_file_path)
                            else:
                                # 复制文件（如果源文件不存在，说明已经移动过了，使用 target_file）
                                if source_file_exists:
                                    copied_file = self.file_service.copy_and_fix_forcing_file(file_path, target_file_path, "copy")
                                else:
                                    # 源文件已移动，从 target_file 复制
                                    copied_file = self.file_service.copy_and_fix_forcing_file(file_to_check, target_file_path,
                                                                                  "copy")
                                if copied_file:
                                    self.log(tr("log_detect_ice_copied",
                                                "📋 检测到海冰场变量 'siconc'，已复制文件到工作目录: {filename}").format(
                                        filename=target_filename))
                                    normalized_path = os.path.normpath(target_file_path)
                                else:
                                    normalized_path = os.path.normpath(file_to_check)
                        else:
                            normalized_path = os.path.normpath(target_file_path)
                    else:
                        # 如果没有提供工作目录，使用源文件路径或目标文件路径
                        if target_file:
                            normalized_path = os.path.normpath(target_file)
                        else:
                            normalized_path = os.path.normpath(file_to_check)

                    if not hasattr(self, 'selected_ice_file'):
                        self.selected_ice_file = None
                    self.selected_ice_file = normalized_path

                    # 更新按钮文本
                    if hasattr(self, 'btn_choose_ice_file_home'):
                        file_name = os.path.basename(normalized_path)
                        if len(file_name) > 30:
                            file_name = file_name[:27] + "..."
                        self._set_home_forcing_button_text(self.btn_choose_ice_file_home, file_name, filled=True)

                    if not work_dir or not need_process:
                        self.log(tr("log_auto_fill_ice", "✅ 检测到海冰场变量 'siconc'，已自动填充海冰场"))
        except Exception as e:
            # 检测失败不影响主流程
            pass

    def _convert_file_thread(self):
        """在后台线程中执行文件转换"""
        try:
            self.reorder_nc()
        except Exception as e:
            self.log_signal.emit(tr("log_convert_error", "❌ 转换过程出错: {error}").format(error=e))

    def _load_latlon_from_source_file(self, file_path):
        """从原始文件读取经纬度范围并填充到输入框"""
        try:
            with Dataset(file_path, "r") as ds:
                # 查找经纬度变量（支持多种变量名变体）
                lon_var = None
                lat_var = None

                # 查找经度变量
                for lon_name in ["longitude", "lon", "Longitude", "LON"]:
                    if lon_name in ds.variables:
                        lon_var = ds.variables[lon_name]
                        break

                # 查找纬度变量
                for lat_name in ["latitude", "lat", "Latitude", "LAT"]:
                    if lat_name in ds.variables:
                        lat_var = ds.variables[lat_name]
                        break

                if lon_var is None or lat_var is None:
                    return  # 如果找不到变量，静默失败

                lon = lon_var[:]
                lat = lat_var[:]

                # 计算经纬度范围
                lon_min = float(np.min(lon))
                lon_max = float(np.max(lon))
                lat_min = float(np.min(lat))
                lat_max = float(np.max(lat))

                # 更新外网格输入框
                if hasattr(self, 'lon_west_edit') and self.lon_west_edit:
                    self.lon_west_edit.setText(f"{lon_min:.2f}")
                if hasattr(self, 'lon_east_edit') and self.lon_east_edit:
                    self.lon_east_edit.setText(f"{lon_max:.2f}")
                if hasattr(self, 'lat_south_edit') and self.lat_south_edit:
                    self.lat_south_edit.setText(f"{lat_min:.2f}")
                if hasattr(self, 'lat_north_edit') and self.lat_north_edit:
                    self.lat_north_edit.setText(f"{lat_max:.2f}")

                # 如果是嵌套网格模式，同时填充内网格参数
                if hasattr(self, 'grid_type_var'):
                    grid_type = self.grid_type_var
                    if grid_type == tr("step2_grid_type_nested", "嵌套网格"):
                        if hasattr(self, 'inner_lon_west_edit') and self.inner_lon_west_edit:
                            self.inner_lon_west_edit.setText(f"{lon_min:.2f}")
                        if hasattr(self, 'inner_lon_east_edit') and self.inner_lon_east_edit:
                            self.inner_lon_east_edit.setText(f"{lon_max:.2f}")
                        if hasattr(self, 'inner_lat_south_edit') and self.inner_lat_south_edit:
                            self.inner_lat_south_edit.setText(f"{lat_min:.2f}")
                        if hasattr(self, 'inner_lat_north_edit') and self.inner_lat_north_edit:
                            self.inner_lat_north_edit.setText(f"{lat_max:.2f}")
                    else:
                        pass
                else:
                    pass
        except Exception as e:
            # 静默失败，不输出错误信息（因为这是自动操作）
            pass

    def reorder_nc(self):
        """
        将数据按照纬度从小到大排列 (WW3 要求)
        从 main_tk.py 迁移过来的转换函数
        """
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            # 检查是否在后台线程中（通过检查是否有 log_signal）
            if hasattr(self, 'log_signal'):
                self.log_signal.emit(tr("log_select_folder_first", "❌ 请先选择或创建文件夹！"))
            else:
                self.log(tr("log_select_folder_first", "❌ 请先选择或创建文件夹！"))
            return
        if not self.selected_origin_file:
            if hasattr(self, 'log_signal'):
                self.log_signal.emit(tr("log_select_origin_file_first", "❌ 请先选择原始数据文件！"))
            else:
                self.log(tr("log_select_origin_file_first", "❌ 请先选择原始数据文件！"))
            return

        # 如果工作目录已经有包含 wind 的文件（已复制并修复），使用它；否则使用原始文件
        # 查找工作目录中包含 wind 的文件（可能是 wind.nc 或 wind_current_level_ice.nc 等）
        wind_files = glob.glob(os.path.join(self.selected_folder, "*wind*.nc"))
        if wind_files:
            # 如果有多个，优先选择 wind.nc，否则选择第一个
            wind_nc_path = os.path.join(self.selected_folder, "wind.nc")
            if wind_nc_path in wind_files:
                origin_data_path = wind_nc_path
            else:
                origin_data_path = wind_files[0]
        else:
            origin_data_path = self.selected_origin_file

        new_data_file_path = os.path.join(self.selected_folder, "wind.nc")

        try:
            with Dataset(origin_data_path, "r") as src:
                # 兼容不同命名的经纬度/时间变量
                def _pick_var_name(candidates):
                    for name in candidates:
                        if name in src.variables:
                            return name
                    return None

                # 支持更多变量名变体，包括 CFSR 和 CCMP 格式
                lon_name = _pick_var_name(["longitude", "lon", "LONGITUDE", "LON", "Longitude", "longitude"])
                lat_name = _pick_var_name(["latitude", "lat", "LATITUDE", "LAT", "Latitude", "latitude"])
                time_name = _pick_var_name(["valid_time", "time", "Time", "TIME", "t", "MT", "mt", "time"])

                if not lon_name:
                    raise KeyError(tr("log_lon_var_not_found", "未找到经度变量（longitude/lon/Longitude）"))
                if not lat_name:
                    raise KeyError(tr("log_lat_var_not_found", "未找到纬度变量（latitude/lat/Latitude）"))
                if not time_name:
                    raise KeyError(tr("log_time_var_not_found", "未找到时间变量（valid_time/time/MT）"))

                longitude = src.variables[lon_name][:]
                latitude = src.variables[lat_name][:]
                time_var_obj = src.variables[time_name]
                time = time_var_obj[:]

                # 获取原始时间单位，用于后续转换
                original_time_units = getattr(time_var_obj, 'units', None)
                original_time_calendar = getattr(time_var_obj, 'calendar', 'gregorian')

                # 支持多种格式的风场变量名：
                # - 标准格式：u10/v10
                # - CFSR 格式：wndewd/wndnwd
                # - CCMP 格式：uwnd/vwnd, uwnd10m/vwnd10m
                u10_name = _pick_var_name(
                    ["u10", "U10", "wndewd", "WNDEWD", "eastward_wind", "u", "uwnd", "UWND", "uwnd10m", "UWND10M"])
                v10_name = _pick_var_name(
                    ["v10", "V10", "wndnwd", "WNDNWD", "northward_wind", "v", "vwnd", "VWND", "vwnd10m", "VWND10M"])

                if not u10_name:
                    raise KeyError(tr("log_u10_var_not_found", "未找到东向风变量（u10/wndewd/uwnd）"))
                if not v10_name:
                    raise KeyError(tr("log_v10_var_not_found", "未找到北向风变量（v10/wndnwd/vwnd）"))

                u10 = src.variables[u10_name][:]
                v10 = src.variables[v10_name][:]

                # 检测并调整维度顺序，确保为 (time, lat, lon)
                u10_shape = u10.shape
                v10_shape = v10.shape

                # 获取维度名称（如果存在）
                u10_dims = src.variables[u10_name].dimensions if hasattr(src.variables[u10_name],
                                                                         'dimensions') else None

                # 如果维度顺序不是 (time, lat, lon)，需要转置
                transpose_order = None
                if len(u10_shape) == 3:
                    # 检查维度顺序
                    # 标准顺序应该是 (time, lat, lon)
                    # 但 CFSR 可能是 (time, lon, lat) 或其他顺序

                    # 通过维度名称判断
                    if u10_dims:
                        time_dim_idx = None
                        lat_dim_idx = None
                        lon_dim_idx = None

                        for i, dim_name in enumerate(u10_dims):
                            if dim_name == time_name or time_name in dim_name or dim_name in time_name:
                                time_dim_idx = i
                            elif dim_name == lat_name or lat_name in dim_name or dim_name in lat_name:
                                lat_dim_idx = i
                            elif dim_name == lon_name or lon_name in dim_name or dim_name in lon_name:
                                lon_dim_idx = i

                        # 如果找到了所有维度，且顺序不是 (time, lat, lon)，则转置
                        if time_dim_idx is not None and lat_dim_idx is not None and lon_dim_idx is not None:
                            if not (time_dim_idx == 0 and lat_dim_idx == 1 and lon_dim_idx == 2):
                                # 需要转置到 (time, lat, lon)
                                transpose_order = [time_dim_idx, lat_dim_idx, lon_dim_idx]
                                u10 = np.transpose(u10, transpose_order)
                                v10 = np.transpose(v10, transpose_order)
                                if hasattr(self, 'log_signal'):
                                    self.log_signal.emit(tr("log_dim_order_transposed",
                                                            "🔄 检测到维度顺序为 {dims}，已转置为 (time, lat, lon)").format(
                                        dims=u10_dims))
                                else:
                                    self.log(tr("log_dim_order_transposed",
                                                "🔄 检测到维度顺序为 {dims}，已转置为 (time, lat, lon)").format(
                                        dims=u10_dims))
                    else:
                        # 如果没有维度名称，通过形状推断
                        # 假设第一个维度是时间，后两个是空间维度
                        # 如果 lat 的长度匹配第二个维度，lon 的长度匹配第三个维度，则顺序正确
                        # 否则需要转置
                        if u10_shape[1] == len(latitude) and u10_shape[2] == len(longitude):
                            # 顺序正确 (time, lat, lon)
                            pass
                        elif u10_shape[1] == len(longitude) and u10_shape[2] == len(latitude):
                            # 顺序是 (time, lon, lat)，需要转置为 (time, lat, lon)
                            transpose_order = (0, 2, 1)
                            u10 = np.transpose(u10, transpose_order)
                            v10 = np.transpose(v10, transpose_order)
                            if hasattr(self, 'log_signal'):
                                self.log_signal.emit(tr("log_dim_order_tlonlat",
                                                        "🔄 检测到维度顺序为 (time, lon, lat)，已转置为 (time, lat, lon)"))
                            else:
                                self.log(tr("log_dim_order_tlonlat",
                                            "🔄 检测到维度顺序为 (time, lon, lat)，已转置为 (time, lat, lon)"))
                        else:
                            # 无法匹配，发出警告
                            warning_msg = tr("log_dim_order_uncertain",
                                             "⚠️ 警告：无法确定维度顺序！数据形状={shape}, 纬度长度={lat_len}, 经度长度={lon_len}").format(
                                shape=u10_shape, lat_len=len(latitude), lon_len=len(longitude))
                            if hasattr(self, 'log_signal'):
                                self.log_signal.emit(warning_msg)
                            else:
                                self.log(warning_msg)

                # 确保是 numpy 数组
                if not isinstance(u10, np.ndarray):
                    u10 = np.array(u10)
                if not isinstance(v10, np.ndarray):
                    v10 = np.array(v10)

                # 验证数据形状是否与经纬度长度匹配
                if len(u10.shape) == 3:
                    expected_lat_len = u10.shape[1]  # 第二个维度应该是纬度
                    expected_lon_len = u10.shape[2]  # 第三个维度应该是经度
                    if expected_lat_len != len(latitude):
                        error_msg = tr("log_lat_dim_mismatch",
                                       "⚠️ 警告：数据纬度维度 ({expected}) 与纬度变量长度 ({actual}) 不匹配！").format(
                            expected=expected_lat_len, actual=len(latitude))
                        if hasattr(self, 'log_signal'):
                            self.log_signal.emit(error_msg)
                        else:
                            self.log(error_msg)
                    if expected_lon_len != len(longitude):
                        error_msg = tr("log_lon_dim_mismatch",
                                       "⚠️ 警告：数据经度维度 ({expected}) 与经度变量长度 ({actual}) 不匹配！").format(
                            expected=expected_lon_len, actual=len(longitude))
                        if hasattr(self, 'log_signal'):
                            self.log_signal.emit(error_msg)
                        else:
                            self.log(error_msg)

        except Exception as e:
            if hasattr(self, 'log_signal'):
                self.log_signal.emit(tr("log_read_origin_failed", "❌ 读取原始文件失败: {error}").format(error=e))
            else:
                self.log(tr("log_read_origin_failed", "❌ 读取原始文件失败: {error}").format(error=e))
            return

        # 检查经纬度是否从大到小，如果是则转换为从小到大
        # 检查经度方向
        lon_needs_flip = len(longitude) > 1 and longitude[0] > longitude[-1]
        # 检查纬度方向
        lat_needs_flip = len(latitude) > 1 and latitude[0] > latitude[-1]

        # 根据检查结果决定是否翻转
        if lon_needs_flip:
            longitude = longitude[::-1]
            u10 = u10[:, :, ::-1]
            v10 = v10[:, :, ::-1]
            pass

        if lat_needs_flip:
            latitude = latitude[::-1]
            u10 = u10[:, ::-1, :]
            v10 = v10[:, ::-1, :]
            pass

        if not lon_needs_flip and not lat_needs_flip:
            pass

        # 如果源文件就是目标 wind.nc，直接原地写回，保持原始压缩与大小
        try:
            same_file = os.path.samefile(origin_data_path, new_data_file_path)
        except OSError:
            same_file = False

        # 若变量名/维度名不是标准格式，强制重写为标准格式
        try:
            needs_standardize = (
                lon_name.lower() != "longitude"
                or lat_name.lower() != "latitude"
                or time_name.lower() not in ("time", "valid_time")
                or u10_name.lower() != "u10"
                or v10_name.lower() != "v10"
            )
        except Exception:
            needs_standardize = True

        if needs_standardize:
            same_file = False

        if same_file:
            try:
                with Dataset(new_data_file_path, "r+") as dst:
                    if lon_name in dst.variables:
                        dst.variables[lon_name][:] = longitude
                    if lat_name in dst.variables:
                        dst.variables[lat_name][:] = latitude
                    if time_name in dst.variables:
                        dst.variables[time_name][:] = time

                    u10_out = u10
                    v10_out = v10
                    if transpose_order is not None:
                        inverse_order = np.argsort(transpose_order)
                        u10_out = np.transpose(u10, inverse_order)
                        v10_out = np.transpose(v10, inverse_order)

                    if u10_name in dst.variables:
                        dst.variables[u10_name][:] = u10_out
                    if v10_name in dst.variables:
                        dst.variables[v10_name][:] = v10_out

                if hasattr(self, 'log_signal'):
                    self.log_signal.emit(tr("lat_flip_complete", "✅ 已完成纬度重排并保存至: {path}").format(path=new_data_file_path))
                else:
                    self.log(tr("lat_flip_complete", "✅ 已完成纬度重排并保存至: {path}").format(path=new_data_file_path))
                return
            except Exception as e:
                if hasattr(self, 'log_signal'):
                    self.log_signal.emit(tr("log_write_file_failed", "❌ 写入新文件失败: {error}").format(error=e))
                else:
                    self.log(tr("log_write_file_failed", "❌ 写入新文件失败: {error}").format(error=e))
                return

        try:
            with Dataset(new_data_file_path, "w", format="NETCDF4") as dst:
                # 定义维度
                dst.createDimension("longitude", len(longitude))
                dst.createDimension("latitude", len(latitude))
                dst.createDimension("time", len(time))

                # 定义变量（注意 fill_value 要在这里指定）
                # 仅做纬度重排，不做压缩；尽量保持原始数据类型
                lon_dtype = src.variables[lon_name].dtype
                lat_dtype = src.variables[lat_name].dtype
                time_dtype = src.variables[time_name].dtype
                u10_dtype = src.variables[u10_name].dtype
                v10_dtype = src.variables[v10_name].dtype
                lon_var = dst.createVariable("longitude", lon_dtype, ("longitude",))
                lat_var = dst.createVariable("latitude", lat_dtype, ("latitude",))
                time_var = dst.createVariable("time", time_dtype, ("time",))
                def _build_var_kwargs(var_obj):
                    kwargs = {"fill_value": -32767.0}
                    try:
                        if hasattr(var_obj, "filters"):
                            filters = var_obj.filters()
                            if filters and filters.get("zlib"):
                                kwargs["zlib"] = True
                                if "complevel" in filters and filters["complevel"] is not None:
                                    kwargs["complevel"] = filters["complevel"]
                                if "shuffle" in filters and filters["shuffle"] is not None:
                                    kwargs["shuffle"] = filters["shuffle"]
                                if "fletcher32" in filters and filters["fletcher32"] is not None:
                                    kwargs["fletcher32"] = filters["fletcher32"]
                                if "chunksizes" in filters and filters["chunksizes"] is not None:
                                    kwargs["chunksizes"] = filters["chunksizes"]
                                if "least_significant_digit" in filters and filters["least_significant_digit"] is not None:
                                    kwargs["least_significant_digit"] = filters["least_significant_digit"]
                    except Exception:
                        # 如果读取过滤器失败，保持无压缩写入
                        pass
                    return kwargs

                def _create_data_var(name, dtype, src_var):
                    try:
                        return dst.createVariable(
                            name,
                            dtype,
                            ("time", "latitude", "longitude"),
                            **_build_var_kwargs(src_var),
                        )
                    except Exception:
                        # 回退：不使用过滤器参数
                        return dst.createVariable(
                            name,
                            dtype,
                            ("time", "latitude", "longitude"),
                            fill_value=-32767.0,
                        )

                u10_var = _create_data_var("u10", u10_dtype, src.variables[u10_name])
                v10_var = _create_data_var("v10", v10_dtype, src.variables[v10_name])

                # 写入数据
                lon_var[:] = longitude
                lat_var[:] = latitude

                # 转换时间单位到标准格式（seconds since 1970-01-01）
                if original_time_units:
                    # 检查是否已经是标准格式
                    target_units = "seconds since 1970-01-01"
                    if original_time_units.strip().lower() == target_units.lower():
                        # 已经是标准格式，直接使用原始时间值
                        time_var[:] = time
                    else:
                        # 需要转换
                        try:
                            # 使用 num2date 将原始时间转换为 datetime 对象
                            time_datetimes = num2date(time, original_time_units, calendar=original_time_calendar)
                            # 转换为 seconds since 1970-01-01
                            from datetime import datetime
                            epoch = datetime(1970, 1, 1)
                            time_seconds = [(dt - epoch).total_seconds() for dt in time_datetimes]
                            time_var[:] = time_seconds
                            if hasattr(self, 'log_signal'):
                                self.log_signal.emit(tr("log_time_units_convert",
                                                        "🔄 时间单位已从 '{old}' 转换为 'seconds since 1970-01-01'").format(
                                    old=original_time_units))
                            else:
                                self.log(tr("log_time_units_convert",
                                            "🔄 时间单位已从 '{old}' 转换为 'seconds since 1970-01-01'").format(
                                    old=original_time_units))
                        except Exception as e:
                            # 如果转换失败，直接使用原始时间值
                            time_var[:] = time
                            if hasattr(self, 'log_signal'):
                                self.log_signal.emit(
                                    tr("log_time_units_convert_failed", "⚠️ 时间单位转换失败，使用原始值: {error}").format(
                                        error=e))
                            else:
                                self.log(
                                    tr("log_time_units_convert_failed", "⚠️ 时间单位转换失败，使用原始值: {error}").format(
                                        error=e))
                else:
                    # 如果没有时间单位信息，直接使用原始值
                    time_var[:] = time

                u10_var[:] = u10
                v10_var[:] = v10

                # 添加属性
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
                time_var.calendar = "standard"  # WAVEWATCH III 要求使用 'standard' calendar

                u10_var.description = "10 meters wind speed u"
                u10_var.units = "m/s"
                u10_var.level = "10m"

                v10_var.description = "10 meters wind speed v"
                v10_var.units = "m/s"
                v10_var.level = "10m"

            if hasattr(self, 'log_signal'):
                self.log_signal.emit(
                    tr("lat_flip_complete", "✅ 已完成纬度重排并保存至: {path}").format(path=new_data_file_path))
            else:
                self.log(tr("lat_flip_complete", "✅ 已完成纬度重排并保存至: {path}").format(path=new_data_file_path))

        except Exception as e:
            if hasattr(self, 'log_signal'):
                self.log_signal.emit(tr("log_write_file_failed", "❌ 写入新文件失败: {error}").format(error=e))
            else:
                self.log(tr("log_write_file_failed", "❌ 写入新文件失败: {error}").format(error=e))
