"""第四步：WW3 运行参数配置 — 业务逻辑 Mixin。

从原 ``ui.py`` 拆分而来，负责输出变量方案管理、从 NetCDF 读取模拟时间范围、
将 ``public/ww3`` 模板文件复制到工作目录，以及嵌套网格 UI 状态联动等第四步
面板功能。与 ``ModifyWW3NML`` 组合后构成完整的 WW3 配置流程。
"""
import os
import json
import re
import glob
import shutil
import numpy as np
from netCDF4 import Dataset, num2date
from ...support.translations import tr
from ..runtime_config import (
    CONFIG_FILE,
    PUBLIC_DIR,
    load_config,
    ST_OPTIONS,
    CPU_GROUP,
    DEFAULT_CPU,
    KERNEL_NUM,
    NODE_NUM,
    DEFAULT_CONFIG,
    DEFAULT_OUTPUT_VARS_SCHEME_NAME,
    DEFAULT_OUTPUT_VARS_SCHEME_VARS,
)


class StepFourServiceMixin:
    """第四步 WW3 运行参数相关的业务逻辑 Mixin。

    主要公开方法
    ------------
    - ``load_time_from_nc`` — 从风场 NetCDF 读取时间范围并写入 GUI 起止日期。
    - ``copy_public_files`` — 将 ``public/ww3`` 模板复制到当前工作目录。
    - ``_load_output_schemes_to_combo`` / ``_on_output_scheme_changed`` — 管理谱分区输出方案。
    """

    def _load_output_schemes_to_combo(self, preserve_selection=None):
        """加载输出变量方案列表到下拉框
        
        Args:
            preserve_selection: 如果提供，刷新后保持选择该方案；否则默认选择"默认方案"
        """
        if not hasattr(self, 'output_scheme_combo'):
            return
        
        # 保存当前选择（如果未指定要保留的选择）
        if preserve_selection is None:
            preserve_selection = self.output_scheme_combo.currentText()
        
        # 从配置文件加载方案
        config = load_config()
        schemes = config.get("OUTPUT_VARS_SCHEMES", {})
        
        # 默认方案的变量列表
        default_scheme_name = DEFAULT_OUTPUT_VARS_SCHEME_NAME
        
        # 如果没有方案或默认方案不存在，创建默认方案
        if not schemes or default_scheme_name not in schemes:
            default_scheme_vars = list(DEFAULT_OUTPUT_VARS_SCHEME_VARS)
            schemes[default_scheme_name] = default_scheme_vars
            config["OUTPUT_VARS_SCHEMES"] = schemes
            
            # 保存配置
            try:
                with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=4)
            except Exception as e:
                if hasattr(self, 'log'):
                    self.log(tr("step4_default_scheme_save_failed", "⚠️ 保存默认方案失败：{error}").format(error=e))
        
        # 清空下拉框并添加方案名称
        # 临时断开信号连接，避免在刷新时触发更新配置
        self.output_scheme_combo.blockSignals(True)
        self.output_scheme_combo.clear()
        scheme_names = list(schemes.keys())
        if scheme_names:
            self.output_scheme_combo.addItems(scheme_names)
            # 如果指定了要保留的选择且该方案存在，则选择它；否则默认选择"默认方案"
            if preserve_selection and preserve_selection in scheme_names:
                # 确保选择正确的方案
                index = scheme_names.index(preserve_selection)
                self.output_scheme_combo.setCurrentIndex(index)
                # 验证选择是否正确
                if self.output_scheme_combo.currentText() != preserve_selection:
                    self.output_scheme_combo.setCurrentText(preserve_selection)
            elif default_scheme_name in scheme_names:
                self.output_scheme_combo.setCurrentText(default_scheme_name)
            else:
                self.output_scheme_combo.setCurrentIndex(0)
        # 恢复信号连接
        self.output_scheme_combo.blockSignals(False)

        # 刷新完成后再同步一次（确保列表已就绪）
        self._load_output_scheme_from_ww3_shel()

    def _load_output_scheme_from_ww3_shel(self):
        """从当前工作目录的 ww3_shel.nml 读取 TYPE%FIELD%LIST 并设置方案"""
        if not hasattr(self, 'selected_folder') or not self.selected_folder:
            return
        if not hasattr(self, 'output_scheme_combo'):
            return

        # 查找 ww3_shel.nml（优先工作目录，其次 coarse/fine）
        candidates = [
            os.path.join(self.selected_folder, "ww3_shel.nml"),
            os.path.join(self.selected_folder, "coarse", "ww3_shel.nml"),
            os.path.join(self.selected_folder, "fine", "ww3_shel.nml"),
        ]
        shel_path = next((p for p in candidates if os.path.exists(p)), None)
        if not shel_path:
            return

        try:
            with open(shel_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            in_output_type = False
            type_field_list = None
            for line in lines:
                line_stripped = line.strip()
                if line_stripped.startswith("!"):
                    continue
                if "&OUTPUT_TYPE_NML" in line_stripped:
                    in_output_type = True
                    continue
                if in_output_type and line_stripped.startswith("/"):
                    break
                if in_output_type and "TYPE%FIELD%LIST" in line_stripped and "=" in line_stripped:
                    match = re.search(r"TYPE%FIELD%LIST\s*=\s*['\"]([^'\"]+)['\"]", line, re.IGNORECASE)
                    if match:
                        type_field_list = match.group(1)
                        break

            if not type_field_list:
                return

            # 归一化为大写列表
            target_vars = [v.strip().upper() for v in type_field_list.split() if v.strip()]
            if not target_vars:
                return

            config = load_config()
            schemes = config.get("OUTPUT_VARS_SCHEMES", {})
            matched_scheme = None
            for scheme_name, vars_list in schemes.items():
                if not vars_list:
                    continue
                scheme_vars = [str(v).strip().upper() for v in vars_list if str(v).strip()]
                if sorted(scheme_vars) == sorted(target_vars):
                    matched_scheme = scheme_name
                    break
            
            if matched_scheme:
                self.output_scheme_combo.blockSignals(True)
                self.output_scheme_combo.setCurrentText(matched_scheme)
                self.output_scheme_combo.blockSignals(False)
        except Exception:
            # 静默失败，避免打扰用户
            pass
    
    def _on_output_scheme_changed(self, scheme_name):
        """当选择输出变量方案时，更新配置文件"""
        import re
        
        if not scheme_name:
            return
        
        # 从配置文件加载方案
        config = load_config()
        schemes = config.get("OUTPUT_VARS_SCHEMES", {})
        
        if scheme_name not in schemes:
            if hasattr(self, 'log'):
                self.log(tr("no_scheme_selected", "❌ 请先选择一个方案"))
            return
        
        # 获取选中方案的变量列表
        selected_vars = schemes[scheme_name]
        if not selected_vars:
            if hasattr(self, 'log'):
                self.log(tr("output_vars_empty", "❌ 请至少选择一个输出变量"))
            return
        
        # 生成变量列表字符串
        var_list_str = ' '.join(selected_vars)
        
        # 获取 public/ww3 目录路径（在项目根目录下）
        # __file__ is main/home/step4/step4_service.py; public is under project root
        public_ww3_dir = config.get("PUBLIC_WW3_PATH", os.path.join(PUBLIC_DIR, "ww3"))
        
        ww3_shel_path = os.path.join(public_ww3_dir, "ww3_shel.nml")
        ww3_ounf_path = os.path.join(public_ww3_dir, "ww3_ounf.nml")
        
        success_count = 0
        error_messages = []
        
        # 更新 ww3_shel.nml
        if not os.path.exists(ww3_shel_path):
            error_messages.append(tr("step4_file_not_found", "文件不存在: {path}").format(path=ww3_shel_path))
        else:
            try:
                with open(ww3_shel_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                new_lines = []
                modified = False
                
                for line in lines:
                    # 检查是否为注释行
                    line_stripped = line.lstrip()
                    is_comment = line_stripped.startswith('!')
                    
                    # 查找并替换 TYPE%FIELD%LIST 行（非注释行）
                    if not is_comment and re.search(r'TYPE%FIELD%LIST', line, re.IGNORECASE) and "=" in line:
                        # 替换为新的变量列表
                        new_lines.append(f"  TYPE%FIELD%LIST       = '{var_list_str}'\n")
                        modified = True
                    else:
                        new_lines.append(line)
                
                if modified:
                    with open(ww3_shel_path, "w", encoding="utf-8") as f:
                        f.writelines(new_lines)
                    success_count += 1
                else:
                    error_messages.append(tr("step4_ww3_shel_type_field_list_missing", "ww3_shel.nml 中未找到 TYPE%FIELD%LIST 配置行"))
            except Exception as e:
                error_messages.append(tr("step4_ww3_shel_update_failed", "更新 ww3_shel.nml 失败：{error}").format(error=str(e)))
        
        # 更新 ww3_ounf.nml
        if not os.path.exists(ww3_ounf_path):
            error_messages.append(tr("step4_file_not_found", "文件不存在: {path}").format(path=ww3_ounf_path))
        else:
            try:
                with open(ww3_ounf_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                new_lines = []
                modified = False
                
                for line in lines:
                    # 检查是否为注释行
                    line_stripped = line.lstrip()
                    is_comment = line_stripped.startswith('!')
                    
                    # 查找并替换 FIELD%LIST 行（非注释行）
                    if not is_comment and re.search(r'FIELD%LIST', line, re.IGNORECASE) and "=" in line:
                        # 替换为新的变量列表
                        new_lines.append(f"  FIELD%LIST             =  '{var_list_str}'\n")
                        modified = True
                    else:
                        new_lines.append(line)
                
                if modified:
                    with open(ww3_ounf_path, "w", encoding="utf-8") as f:
                        f.writelines(new_lines)
                    success_count += 1
                else:
                    error_messages.append(tr("step4_ww3_ounf_field_list_missing", "ww3_ounf.nml 中未找到 FIELD%LIST 配置行"))
            except Exception as e:
                error_messages.append(tr("step4_ww3_ounf_update_failed", "更新 ww3_ounf.nml 失败：{error}").format(error=str(e)))
        
        # 不在这里显示日志，只在确认参数时显示
        # 如果更新失败，记录错误但不显示日志
        if success_count == 0 and error_messages:
            # 静默记录错误，不显示给用户
            pass
    
    def _update_wavewatch_title(self):
        """更新 WAVEWATCH 配置标签文本和嵌套网格相关的 UI（根据网格类型）"""
        is_nested = getattr(self, "grid_type_var", "") == tr("step2_grid_type_nested", "嵌套网格")

        if hasattr(self, 'wavewatch_title') and self.wavewatch_title:
            if is_nested:
                # 嵌套网格时，显示"外网格参数"
                self.wavewatch_title.setText(tr("step4_outer_params", "外网格参数"))
            else:
                # 普通网格时，显示"WAVEWATCH 配置"
                self.wavewatch_title.setText(tr("step4_wavewatch_config", "WAVEWATCH 配置"))

        # 更新嵌套网格相关的 UI 可见性
        if hasattr(self, 'outer_precision_title_container'):
            # 外网格参数标题：嵌套网格时显示，普通网格时隐藏
            self.outer_precision_title_container.setVisible(is_nested)

        if hasattr(self, 'inner_precision_widget'):
            # 内网格精度参数：嵌套网格时显示，普通网格时隐藏
            self.inner_precision_widget.setVisible(is_nested)

    def load_time_from_nc(self, file_name="wind.nc"):
        """从风场文件中读取时间范围并更新 GUI 起止日期"""
        # 严格的类型和值检查
        if not hasattr(self, 'selected_folder'):
            self.log(tr("step4_selected_folder_missing", "❌ selected_folder 属性不存在！"))
            return

        if self.selected_folder is None:
            self.log(tr("step4_workdir_missing", "❌ 当前工作目录不存在！"))
            return

        if not isinstance(self.selected_folder, str):
            self.log(tr("step4_selected_folder_type_error", "❌ selected_folder 类型错误: {type}, 值: {value}").format(type=type(self.selected_folder), value=repr(self.selected_folder)))
            self.log(tr("step4_workdir_missing", "❌ 当前工作目录不存在！"))
            return

        if not self.selected_folder.strip():
            self.log(tr("step4_workdir_path_empty", "❌ 工作目录路径为空！"))
            return

        # 查找工作目录中包含 wind 的文件（可能是 wind.nc 或 wind_current_ssh_ice.nc 等）
        wind_files = glob.glob(os.path.join(self.selected_folder, "*wind*.nc"))
        
        if not wind_files:
            # 如果找不到包含 wind 的文件，尝试使用 wind.nc
            data_nc_path = os.path.join(self.selected_folder, "wind.nc")
            if not os.path.exists(data_nc_path):
                self.log(tr("step4_wind_nc_not_found", "❌ 未找到风场文件（工作目录中不存在包含 'wind' 的 .nc 文件）"))
                return
        else:
            # 如果有多个，优先选择 wind.nc，否则选择第一个
            wind_nc_path = os.path.join(self.selected_folder, "wind.nc")
            if wind_nc_path in wind_files:
                data_nc_path = wind_nc_path
            else:
                data_nc_path = wind_files[0]
        
        file_name = os.path.basename(data_nc_path)

        try:
            ds = Dataset(data_nc_path)
            
            # 查找时间变量（与 view_all_field_files_info 保持一致的顺序）
            time_var = None
            time_var_name = None
            for time_name in ["time", "Time", "TIME", "valid_time", "MT", "mt", "t"]:
                if time_name in ds.variables:
                    time_var = ds.variables[time_name]
                    time_var_name = time_name
                    break
            
            if time_var is None:
                self.log(tr("step4_time_var_not_found", "❌ {file} 中未找到时间变量（尝试了: time, Time, TIME, valid_time, MT, mt, t）。").format(file=file_name))
                ds.close()
                return

            # 获取时间范围（完全按照 view_all_field_files_info 的逻辑）
            try:
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
                        # 格式化为 YYYYMMDD
                        start_str = time_start.strftime("%Y%m%d")
                        end_str = time_end.strftime("%Y%m%d")
                    else:
                        self.log(tr("step4_time_var_empty", "❌ {file} 中的时间变量为空。").format(file=file_name))
                        ds.close()
                        return
                else:
                    # 如果没有单位，无法转换
                    self.log(tr("step4_time_units_missing", "⚠️ {file} 中的时间变量没有 units 属性，无法转换时间。").format(file=file_name))
                    ds.close()
                    return
            except Exception as e:
                self.log(tr("step4_time_read_failed", "❌ 读取 {file} 时间失败：{error}").format(file=file_name, error=e))
                ds.close()
                return

            ds.close()

            self.shel_start_edit.setText(start_str)
            self.shel_end_edit.setText(end_str)

            self.log(tr("step4_time_range_loaded", "✅ 已从 {file} 读取时间范围：{start} → {end}").format(file=file_name, start=start_str, end=end_str))

        except Exception as e:
            self.log(tr("step4_time_read_failed", "❌ 读取 {file} 时间失败：{error}").format(file=file_name, error=e))

    def copy_public_files(self):
        """将 public/ww3 下的文件复制到工作文件夹"""
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            self.log(tr("step4_workdir_missing", "❌ 当前工作目录不存在！"))
            return
        self._copy_public_files_to_dir(self.selected_folder)

    def _copy_public_files_to_dir(self, target_dir, grid_label=""):
        """将 public/ww3 下的文件复制到指定目录"""
        if not target_dir or not isinstance(target_dir, str):
            return

        # 获取项目根目录下的 public/ww3 路径
        src_dir = os.path.normpath(os.path.join(PUBLIC_DIR, "ww3"))
        
        if not os.path.exists(src_dir):
            self.log(tr("step4_dir_not_found", "⚠️ 未找到目录：{path}").format(path=src_dir))
            return

        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        # 使用翻译函数检查是否为嵌套网格（支持中英文）
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")

        # 检查计算模式
        calc_mode = getattr(self, 'calc_mode_var', '')
        # 优先检查 calc_mode_combo 的当前选择（这是用户界面上的实际值）
        if hasattr(self, 'calc_mode_combo') and self.calc_mode_combo:
            combo_text = self.calc_mode_combo.currentText()
            if combo_text:
                calc_mode = combo_text
        
        spectral_text = tr("step3_spectral_point", "谱空间逐点计算")
        track_text = tr("step3_track_mode", "航迹模式")
        is_spectral_mode = (calc_mode == spectral_text or calc_mode == "谱空间逐点计算")
        is_track_mode = (calc_mode == track_text or calc_mode == "航迹模式")

        # 如果是嵌套网格模式，server.sh 和 ww3_multi.nml 应该复制到工作目录而不是子文件夹
        workdir_for_special = self.selected_folder if is_nested_grid and hasattr(self, 'selected_folder') else target_dir
        # 需要复制到工作目录的文件列表（嵌套网格模式下）
        special_files = ["server.sh", "ww3_multi.nml"]

        # 根据模式决定需要跳过的文件
        skip_files = []
        # 如果不是嵌套网格模式，跳过 ww3_multi.nml
        if not is_nested_grid:
            skip_files.append("ww3_multi.nml")
        # 如果不是航迹模式，跳过 ww3_trnc.nml
        if not is_track_mode:
            skip_files.append("ww3_trnc.nml")
        # 如果不是谱空间逐点计算模式，跳过 ww3_ounp.nml
        if not is_spectral_mode:
            skip_files.append("ww3_ounp.nml")
        # 嵌套网格模式下，local.sh 仅保留在工作目录，不复制到 coarse/fine
        if is_nested_grid:
            skip_files.append("local.sh")

        try:
            # 遍历 public 目录下的文件并复制
            copied = 0
            for item in os.listdir(src_dir):
                src_path = os.path.join(src_dir, item)

                # 如果是嵌套网格模式且文件是特殊文件（ww3.slurm 或 ww3_multi.nml），跳过（已在公共文件处理中复制）
                if is_nested_grid and item in special_files:
                    continue  # 跳过特殊文件，它们已在 _copy_public_special_files_to_workdir 中处理
                
                # 根据模式跳过不需要的文件
                if item in skip_files:
                    continue
                
                # 确保是文件而不是目录
                if not os.path.isfile(src_path):
                    continue
                
                dst_path = os.path.join(target_dir, item)
                shutil.copy2(src_path, dst_path)
                copied += 1
                

            if copied > 0:
                prefix = f"{grid_label} " if grid_label else ""
                # 嵌套网格模式下，特殊文件已在公共文件处理中复制，这里只显示其他文件
                self.log(f"{prefix}{tr('step4_files_copied', '✅ 已复制 {count} 个 public/ww3 文件到当前工作目录').format(count=copied)}")
            else:
                self.log(tr("step4_no_files_to_copy", "⚠️ {path} 中没有可复制的文件。").format(path=src_dir))

        except Exception as e:
            self.log(tr("step4_copy_files_failed", "❌ 复制文件时出错：{error}").format(error=e))
