"""ww3_prnc*.nml 修改 Mixin — 强迫场预处理 namelist 生成与改写。

根据用户选择的强迫场类型（风、流、水位、海冰等），生成或修改 ``ww3_prnc.nml``
及 ``ww3_prnc_wind.nc``、``ww3_prnc_cur.nc`` 等专用 namelist，写入时间范围、
变量名映射与 ``FORCING%FIELD%*`` 开关。
"""
from __future__ import annotations

import glob
import os
import re
import shutil

import numpy as np
import netCDF4 as nc
from netCDF4 import Dataset

from ..runtime_config import PUBLIC_DIR, load_config
from ...support.translations import tr
from .nml_log_format import Assignment, format_nml_log_message
from .nml_primitives import NMLPrimitives


class WW3PrncNML(NMLPrimitives):
    """``ww3_prnc*.nml`` 强迫场预处理相关操作的 Mixin 类。

    涵盖嵌套网格 prnc 修改、多强迫场 namelist 批量生成、时间范围同步及
    NetCDF 变量名自动检测（如海冰 ``sithick`` / ``ICE_PARAM1``）。
    """

    def _check_ice_param1_variable(self, file_path):
        """检查海冰场文件是否包含 ICE_PARAM1 变量（冰厚度，通常是 sithick）"""
        try:
            from netCDF4 import Dataset
            with Dataset(file_path, "r") as ds:
                # 检查常见的冰厚度变量名
                ice_thickness_vars = ["sithick", "SITHICK", "ice_thickness", "ICE_THICKNESS",
                                     "sit", "SIT", "hi", "HI", "hice", "HICE"]
                for var_name in ice_thickness_vars:
                    if var_name in ds.variables:
                        return True
            return False
        except Exception:
            return False

    def _format_forcing_field_line(self, field_name, value):
        """格式化 FORCING%FIELD%* 行，确保等号对齐在第32列"""
        # 等号对齐位置（与模板文件一致，等号在第32列）
        # 等号前总长度应该是31（包括字段名和空格）
        prefix = "  FORCING%FIELD%"
        target_length = 31  # 等号前总长度（等号在32列）
        current_length = len(prefix + field_name)
        spaces_needed = target_length - current_length
        if spaces_needed < 1:
            spaces_needed = 1  # 至少保留一个空格
        return f"{prefix}{field_name}{' ' * spaces_needed}= {value}\n"

    def _format_input_model_line(self, field_name, value):
        """格式化 INPUT(*) 或 MODEL(*) 行，确保等号对齐在第33列（索引33）"""
        # 根据模板文件，等号对齐在第33列（从1开始计数）
        # 等号前总长度应该是33（等号在索引33，即第34个字符）
        target_length = 33  # 等号前总长度（等号在索引33）
        prefix = "  "
        current_length = len(prefix + field_name)
        spaces_needed = target_length - current_length
        if spaces_needed < 1:
            spaces_needed = 1  # 至少保留一个空格
        return f"{prefix}{field_name}{' ' * spaces_needed}= {value}\n"

    def _modify_ww3_prnc_nml_for_nested(self, target_dir, grid_label=""):
        """
        修改嵌套网格模式下 ww3_prnc.nml 中的：
        1. &FORCING_NML 中的设置（风场总是 T，其他场根据选择）
        2. &FILE_NML 中的 FILE%FILENAME 根据强迫场类型设置
        3. &FILE_NML 中的变量名根据强迫场类型设置
        """
        if not target_dir or not isinstance(target_dir, str):
            return

        nml_path = os.path.join(target_dir, "ww3_prnc.nml")
        if not os.path.exists(nml_path):
            self.log(tr("ww3_prnc_not_found_skip", "⚠️ 未找到 ww3_prnc.nml 文件：{path}，跳过修改").format(path=nml_path))
            return

        try:
            import re
            import glob
            from netCDF4 import Dataset

            # 读取文件，确定强迫场类型
            with open(nml_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # 确定强迫场类型（WINDS 或 CURRENTS）
            # 首先检查文件中是否已经设置了强迫场类型
            forcing_field_type = None
            in_forcing_nml_check = False
            for line in lines:
                if "&FORCING_NML" in line.upper():
                    in_forcing_nml_check = True
                    continue
                if in_forcing_nml_check and re.match(r'^\s*/\s*$', line) and not line.strip().startswith("!"):
                    in_forcing_nml_check = False
                    break
                if in_forcing_nml_check:
                    # 检查 FORCING%FIELD%WINDS 或 FORCING%FIELD%CURRENTS
                    if re.search(r'FORCING%FIELD%WINDS\s*=\s*T', line, re.IGNORECASE):
                        forcing_field_type = 'WINDS'
                        break
                    elif re.search(r'FORCING%FIELD%CURRENTS\s*=\s*T', line, re.IGNORECASE):
                        forcing_field_type = 'CURRENTS'
                        break

            # 如果文件中没有找到明确的设置，检查用户是否选择了流场
            if forcing_field_type is None:
                # 检查用户是否选择了流场
                has_current = False
                if hasattr(self, 'forcing_field_checkboxes'):
                    if 'current' in self.forcing_field_checkboxes:
                        checkbox = self.forcing_field_checkboxes['current']['checkbox']
                        has_current = checkbox.isChecked() if checkbox else False

                # 如果用户选择了流场，且存在流场文件，则使用流场配置
                if has_current and hasattr(self, 'selected_current_file') and self.selected_current_file:
                    if os.path.exists(self.selected_current_file):
                        forcing_field_type = 'CURRENTS'
                    else:
                        forcing_field_type = 'WINDS'
                else:
                    forcing_field_type = 'WINDS'

            # 根据强迫场类型确定文件名和变量名（统一解析服务，方案 §8）
            # [EN] Determine filename and variable names per field type
            # (unified resolver, spec §8)
            lon_name = 'longitude'
            lat_name = 'latitude'
            if forcing_field_type == 'CURRENTS':
                # 流场配置
                filename = "../current_level.nc"  # 默认流场文件名
                var_names = ['uo', 'vo']  # 默认流场变量名

                # 优先使用用户选择的流场文件
                current_file_path = None
                if hasattr(self, 'selected_current_file') and self.selected_current_file:
                    if os.path.exists(self.selected_current_file):
                        current_file_path = self.selected_current_file
                        filename = f"../{os.path.basename(self.selected_current_file)}"

                # 如果没有用户选择的文件，检查选择的流场文件
                if current_file_path is None:
                    current_files = glob.glob(os.path.join(self.selected_folder, "*current*.nc"))
                    if current_files:
                        current_nc_path = os.path.join(self.selected_folder, "current_level.nc")
                        if os.path.exists(current_nc_path):
                            filename = "../current_level.nc"
                            current_file_path = current_nc_path
                        else:
                            filename = f"../{os.path.basename(current_files[0])}"
                            current_file_path = current_files[0]

                # 从流场文件读取变量映射
                if current_file_path and os.path.exists(current_file_path):
                    resolved = self._load_field_resolution(self.selected_folder, 'current', current_file_path)
                    if resolved is not None:
                        var_names = list(resolved.components)
                        lon_name = resolved.longitude or lon_name
                        lat_name = resolved.latitude or lat_name
            else:
                # 风场配置（默认）
                filename = "../wind.nc"  # 默认风场文件名
                var_names = ['u10', 'v10']  # 默认风场变量名

                # 检查选择的风场文件
                wind_files = glob.glob(os.path.join(self.selected_folder, "*wind*.nc"))
                wind_file_path = None
                if wind_files:
                    wind_nc_path = os.path.join(self.selected_folder, "wind.nc")
                    if os.path.exists(wind_nc_path):
                        filename = "../wind.nc"
                        wind_file_path = wind_nc_path
                    else:
                        filename = f"../{os.path.basename(wind_files[0])}"
                        wind_file_path = wind_files[0]

                # 从风场文件读取变量映射
                if wind_file_path and os.path.exists(wind_file_path):
                    resolved = self._load_field_resolution(self.selected_folder, 'wind', wind_file_path)
                    if resolved is not None:
                        var_names = list(resolved.components)
                        lon_name = resolved.longitude or lon_name
                        lat_name = resolved.latitude or lat_name

            # 处理文件内容
            new_lines = []
            in_forcing_nml = False
            in_file_nml = False

            for line in lines:
                # 检查是否进入 FORCING_NML 块
                if "&FORCING_NML" in line.upper():
                    in_forcing_nml = True
                    new_lines.append(line)
                    continue

                # 检查是否离开 FORCING_NML 块
                if in_forcing_nml and re.match(r'^\s*/\s*$', line) and not line.strip().startswith("!"):
                    in_forcing_nml = False
                    new_lines.append(line)
                    continue

                # 在 FORCING_NML 块中处理
                if in_forcing_nml:
                    # 处理 FORCING%FIELD%* 行：保留所有字段，只修改对应的字段为 T，其他的为 F
                    if re.search(r'FORCING%FIELD%', line, re.IGNORECASE):
                        # 提取字段名
                        field_match = re.search(r'FORCING%FIELD%(\w+)', line, re.IGNORECASE)
                        if field_match:
                            found_field_name = field_match.group(1)
                            # 检查是否是当前需要的字段
                            if (forcing_field_type == 'CURRENTS' and found_field_name.upper() == 'CURRENTS') or \
                               (forcing_field_type == 'WINDS' and found_field_name.upper() == 'WINDS'):
                                # 设置为 T
                                new_lines.append(self._format_forcing_field_line(found_field_name, 'T'))
                            else:
                                # 设置为 F
                                new_lines.append(self._format_forcing_field_line(found_field_name, 'F'))
                        else:
                            # 如果无法提取字段名，保留原行
                            new_lines.append(line)
                        continue
                    # 保留 FORCING%TIMESTART 和 FORCING%TIMESTOP
                    elif re.search(r'FORCING%TIMESTART|FORCING%TIMESTOP', line, re.IGNORECASE):
                        new_lines.append(line)
                    # 保留 FORCING%GRID%*（确保 LATLON = T）
                    elif re.search(r'FORCING%GRID%', line, re.IGNORECASE):
                        if 'LATLON' in line.upper():
                            new_lines.append("  FORCING%GRID%LATLON          = T\n")
                        else:
                            new_lines.append(line)
                    else:
                        # 保留其他行（如注释等）
                        new_lines.append(line)
                    continue

                # 检查是否进入 FILE_NML 块
                if "&FILE_NML" in line.upper():
                    in_file_nml = True
                    new_lines.append(line)
                    continue

                # 检查是否离开 FILE_NML 块
                if in_file_nml and re.match(r'^\s*/\s*$', line) and not line.strip().startswith("!"):
                    new_lines.append(line)
                    in_file_nml = False
                    continue

                # 在 FILE_NML 块中处理
                if in_file_nml:
                    # 替换 FILE%VAR(*) 行（只替换，不插入）
                    # 匹配 FILE%VAR(数字) 模式，允许各种空格格式
                    var_match = re.search(r'FILE%VAR\s*\(\s*(\d+)\s*\)', line, re.IGNORECASE)
                    if var_match:
                        var_index = int(var_match.group(1))
                        # 如果索引在范围内，替换为新变量名
                        if 1 <= var_index <= len(var_names):
                            new_lines.append(f"  FILE%VAR({var_index})        = '{var_names[var_index - 1]}'\n")
                        # 如果索引超出范围，跳过（删除多余的变量行）
                        # 无论是否替换，都跳过原行（已替换或删除）
                        continue
                    # 替换 FILE%FILENAME
                    elif "FILE%FILENAME" in line:
                        new_lines.append(f"  FILE%FILENAME      = '{filename}'\n")
                    # 替换 FILE%LONGITUDE（用解析结果中的经度变量名）
                    elif "FILE%LONGITUDE" in line:
                        new_lines.append(f"  FILE%LONGITUDE     = '{lon_name}'\n")
                    # 替换 FILE%LATITUDE
                    elif "FILE%LATITUDE" in line:
                        new_lines.append(f"  FILE%LATITUDE      = '{lat_name}'\n")
                    else:
                        # 保留其他行（如注释等）
                        new_lines.append(line)
                    continue

                # 其他行直接添加
                new_lines.append(line)

            # 写入文件
            with open(nml_path, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(new_lines)

            prefix = ""
            field_name = "CURRENTS" if forcing_field_type == 'CURRENTS' else "WINDS"
            prnc_assignments: list[Assignment] = [
                (f"FORCING%FIELD%{field_name}", "T"),
                ("FILE%FILENAME", f"'{filename}'"),
            ]
            for index, var_name in enumerate(var_names, start=1):
                prnc_assignments.append((f"FILE%VAR({index})", f"'{var_name}'"))
            self.log(
                prefix
                + format_nml_log_message(
                    "step4_ww3_prnc_modified",
                    "✅ 已修改 ww3_prnc.nml：\n{details}",
                    prnc_assignments,
                )
            )

        except Exception as e:
            self.log(tr("ww3_prnc_modify_error", "❌ 修改 {file}/ww3_prnc.nml 出错：{error}").format(file=os.path.basename(target_dir), error=e))

    def _modify_ww3_prnc_times(self):
        """修改 ww3_prnc.nml 中的 FORCING%TIMESTART 和 FORCING%TIMESTOP"""
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            return

        start_date = self.shel_start_edit.text().strip()
        end_date = self.shel_end_edit.text().strip()

        # 验证日期格式
        if not (start_date.isdigit() and len(start_date) == 8):
            self.log(tr("start_date_format_error_skip", "⚠️ 起始日期格式错误，跳过修改 ww3_prnc.nml 的时间范围"))
            return

        if not (end_date.isdigit() and len(end_date) == 8):
            self.log(tr("end_date_format_error_skip", "⚠️ 结束日期格式错误，跳过修改 ww3_prnc.nml 的时间范围"))
            return

        # 转换为 ww3 格式：YYYYMMDD HHMMSS
        start_datetime = f"{start_date} 000000"
        end_datetime = f"{end_date} 235959"  # 停止时间设置为最后日期的 23:59:59

        self._modify_ww3_prnc_times_in_dir(self.selected_folder, start_datetime, end_datetime)

    def _modify_ww3_prnc_times_in_dir(self, target_dir, start_datetime=None, end_datetime=None, grid_label=""):
        """在指定目录下修改 ww3_prnc.nml 中的 FORCING%TIMESTART 和 FORCING%TIMESTOP"""
        if not target_dir or not isinstance(target_dir, str):
            return

        # 如果没有提供时间，从输入框获取
        if start_datetime is None or end_datetime is None:
            start_date = self.shel_start_edit.text().strip()
            end_date = self.shel_end_edit.text().strip()

            # 验证日期格式
            if not (start_date.isdigit() and len(start_date) == 8):
                return
            if not (end_date.isdigit() and len(end_date) == 8):
                return

            start_datetime = f"{start_date} 000000"
            end_datetime = f"{end_date} 235959"  # 停止时间设置为最后日期的 23:59:59

        nml_path = os.path.join(target_dir, "ww3_prnc.nml")
        if not os.path.exists(nml_path):
            return

        try:
            with open(nml_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            in_forcing_nml = False
            found_timestart = False
            found_timestop = False

            for line in lines:
                # 检查是否进入 FORCING_NML 块
                if "&FORCING_NML" in line:
                    in_forcing_nml = True
                    new_lines.append(line)
                # 检查是否离开 FORCING_NML 块
                elif in_forcing_nml and "/" in line and not line.strip().startswith("!"):
                    # 如果没找到，在结束标记前添加
                    if not found_timestart:
                        new_lines.append(f"  FORCING%TIMESTART            = '{start_datetime}'\n")
                    if not found_timestop:
                        new_lines.append(f"  FORCING%TIMESTOP             = '{end_datetime}'\n")
                    new_lines.append(line)
                    in_forcing_nml = False
                # 在 FORCING_NML 块中处理
                elif in_forcing_nml:
                    if "FORCING%TIMESTART" in line:
                        # 直接替换整行，保持原有的缩进和格式
                        # 提取行首的空白字符（缩进）
                        indent_match = re.match(r"^(\s*)", line)
                        indent = indent_match.group(1) if indent_match else "  "
                        # 生成新行，保持原有格式
                        new_line = f"{indent}FORCING%TIMESTART            = '{start_datetime}'\n"
                        new_lines.append(new_line)
                        found_timestart = True
                    elif "FORCING%TIMESTOP" in line:
                        # 直接替换整行，保持原有的缩进和格式
                        indent_match = re.match(r"^(\s*)", line)
                        indent = indent_match.group(1) if indent_match else "  "
                        # 生成新行，保持原有格式
                        new_line = f"{indent}FORCING%TIMESTOP             = '{end_datetime}'\n"
                        new_lines.append(new_line)
                        found_timestop = True
                    else:
                        # 其他行直接添加
                        new_lines.append(line)
                else:
                    # 不在 FORCING_NML 块中的行直接添加
                    new_lines.append(line)

            with open(nml_path, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(new_lines)

            prefix = ""
            self.log(
                prefix
                + format_nml_log_message(
                    "step4_ww3_prnc_times_updated",
                    "✅ 已修改 ww3_prnc.nml：\n{details}",
                    [
                        ("FORCING%TIMESTART", f"'{start_datetime}'"),
                        ("FORCING%TIMESTOP", f"'{end_datetime}'"),
                    ],
                )
            )

        except Exception as e:
            prefix = ""
            self.log(tr("ww3_prnc_times_modify_failed", "{prefix}❌ 修改 ww3_prnc.nml 时间范围失败：{error}").format(prefix=prefix, error=e))

    def _generate_forcing_field_prnc_files(self, target_dir=None, use_relative_path=False):
        """
        根据选择的强迫场生成对应的 ww3_prnc_*.nml 文件

        参数:
            target_dir: 目标目录，如果为 None 则使用 self.selected_folder
            use_relative_path: 是否使用相对路径（../filename.nc），用于嵌套网格模式
        """
        if target_dir is None:
            target_dir = self.selected_folder

        if not target_dir or not isinstance(target_dir, str):
            return

        # 检查复选框状态
        if not hasattr(self, 'forcing_field_checkboxes'):
            return

        # 定义强迫场配置（变量名不再内置候选表，统一来自 manifest/解析服务）
        # [EN] Forcing field configs (variable names now come from the
        # manifest / resolver service instead of a built-in candidate table)
        forcing_field_configs = {
            'current': {
                'field_name': 'CURRENTS',
                'file_attr': 'selected_current_file',
                'output_filename': 'ww3_prnc_current.nml'
            },
            'level': {
                'field_name': 'WATER_LEVELS',
                'file_attr': 'selected_level_file',
                'output_filename': 'ww3_prnc_level.nml'
            },
            'ice': {
                'field_name': 'ICE_CONC',
                'file_attr': 'selected_ice_file',
                'output_filename': 'ww3_prnc_ice.nml'
            }
        }

        prefix = ""

        # 为每个选中的强迫场生成文件
        for field_key, config in forcing_field_configs.items():
            # 检查复选框是否选中
            if field_key not in self.forcing_field_checkboxes:
                continue

            checkbox = self.forcing_field_checkboxes[field_key]['checkbox']
            if not checkbox.isChecked():
                continue

            # 检查文件是否真的存在于当前工作目录中
            file_path = None
            if hasattr(self, config['file_attr']):
                file_path = getattr(self, config['file_attr'])

            # 验证文件路径：必须存在且在当前工作目录中
            if not file_path or not isinstance(file_path, str):
                # 切换目录后可能遗留勾选，直接静默取消
                checkbox.setChecked(False)
                continue
            if not os.path.exists(file_path):
                self.log(tr("forcing_field_not_found", "{prefix}⚠️ 未找到 {field} 强迫场文件，跳过生成 {file}").format(prefix=prefix, field=field_key, file=config['output_filename']))
                checkbox.setChecked(False)
                continue

            # 确保文件在当前工作目录中（或嵌套网格时在父目录中）
            # 使用绝对路径进行比较，更可靠
            abs_file_path = os.path.abspath(file_path)
            abs_target_dir = os.path.abspath(target_dir)

            if not use_relative_path:
                # 普通网格模式：文件必须在 target_dir 中
                try:
                    common_path = os.path.commonpath([abs_file_path, abs_target_dir])
                    if common_path != abs_target_dir:
                        self.log(tr("forcing_field_not_in_workdir", "{prefix}⚠️ {field} 强迫场文件不在当前工作目录中，跳过生成 {file}").format(prefix=prefix, field=field_key, file=config['output_filename']))
                        checkbox.setChecked(False)
                        continue
                except ValueError:
                    # 路径不在同一驱动器上（Windows）或无法比较
                    self.log(tr("forcing_field_not_in_workdir", "{prefix}⚠️ {field} 强迫场文件不在当前工作目录中，跳过生成 {file}").format(prefix=prefix, field=field_key, file=config['output_filename']))
                    checkbox.setChecked(False)
                    continue
            else:
                # 嵌套网格模式：文件应该在父目录（selected_folder）中
                parent_dir = os.path.dirname(target_dir) if target_dir != self.selected_folder else self.selected_folder
                abs_parent_dir = os.path.abspath(parent_dir)
                try:
                    common_path = os.path.commonpath([abs_file_path, abs_parent_dir])
                    if common_path != abs_parent_dir:
                        self.log(tr("forcing_field_not_in_parent", "{prefix}⚠️ {field} 强迫场文件不在父目录中，跳过生成 {file}").format(prefix=prefix, field=field_key, file=config['output_filename']))
                        checkbox.setChecked(False)
                        continue
                except ValueError:
                    # 路径不在同一驱动器上（Windows）或无法比较
                    self.log(tr("forcing_field_not_in_parent", "{prefix}⚠️ {field} 强迫场文件不在父目录中，跳过生成 {file}").format(prefix=prefix, field=field_key, file=config['output_filename']))
                    checkbox.setChecked(False)
                    continue

            # 从目标目录中已修改时间的 ww3_prnc.nml 复制
            source_nml_path = os.path.join(target_dir, "ww3_prnc.nml")
            if not os.path.exists(source_nml_path):
                self.log(tr("ww3_prnc_not_found_skip_generate", "{prefix}⚠️ 未找到 ww3_prnc.nml 文件，跳过生成 {file}").format(prefix=prefix, file=config['output_filename']))
                continue

            # 复制文件
            output_path = os.path.join(target_dir, config['output_filename'])
            try:
                import shutil
                import re
                shutil.copy2(source_nml_path, output_path)

                # 修改新复制的文件，设置对应的 FORCING%FIELD%* 为 T，其他的为 F
                with open(output_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                # 获取文件路径和变量名（此时 file_path 已经在上面的检查中确认存在）
                var_names = None
                filename = None
                has_sithick = False
                sithick_var = None

                # file_path 已经在上面检查过，这里直接使用
                # 变量映射来自工作目录 manifest；缺失时用统一解析服务重新解析
                # [EN] Variable mapping comes from the workdir manifest; the
                # unified resolver is used as fallback when the manifest is missing
                resolved = None
                lon_name = None
                lat_name = None
                has_sithick = False
                sithick_var = None
                if file_path and os.path.exists(file_path):
                    # 设置文件名
                    if use_relative_path:
                        filename = f"../{os.path.basename(file_path)}"
                    else:
                        filename = os.path.basename(file_path)
                    resolved = self._load_field_resolution(target_dir, field_key, file_path)
                    if resolved is not None:
                        var_names = list(resolved.components)
                        lon_name = resolved.longitude or None
                        lat_name = resolved.latitude or None
                        if resolved.thickness:
                            has_sithick = True
                            sithick_var = resolved.thickness
                    else:
                        var_names = None

                # 找不到解析结果：不生成 NML（校验失败不能继续生成，方案 §5）
                # [EN] No resolution: do not generate NML (validation failure must
                # stop generation, spec §5)
                if not var_names:
                    if field_key != 'ice':
                        self.log(
                            tr(
                                "forcing_field_unresolved",
                                "{prefix}⚠️ 无法确定 {field} 强迫场的变量映射（请在变量映射中手动指定），跳过生成 {file}",
                            ).format(prefix=prefix, field=field_key, file=config['output_filename'])
                        )
                        checkbox.setChecked(False)
                        continue

                # filename 应该已经设置好了，如果还没有（理论上不应该发生），使用默认值
                if not filename:
                    if use_relative_path:
                        if field_key == 'current':
                            filename = "../current_level.nc"
                        elif field_key == 'level':
                            filename = "../level.nc"
                        elif field_key == 'ice':
                            filename = "../ice.nc"
                    else:
                        if field_key == 'current':
                            filename = "current_level.nc"
                        elif field_key == 'level':
                            filename = "level.nc"
                        elif field_key == 'ice':
                            filename = "ice.nc"

                def _write_prnc_file(output_filename, field_name, var_names, lon_name=None, lat_name=None):
                    output_path = os.path.join(target_dir, output_filename)
                    shutil.copy2(source_nml_path, output_path)

                    new_lines = []
                    in_forcing_nml = False
                    in_file_nml = False

                    # 定义所有需要的字段
                    all_fields = ['WINDS', 'CURRENTS', 'WATER_LEVELS', 'ICE_CONC', 'ICE_PARAM1']
                    found_fields = set()
                    found_grid_latlon = False

                    for line in lines:
                        # 检查是否进入 FORCING_NML 块
                        if "&FORCING_NML" in line.upper():
                            in_forcing_nml = True
                            new_lines.append(line)
                            continue

                        # 检查是否离开 FORCING_NML 块
                        if in_forcing_nml and re.match(r'^\s*/\s*$', line) and not line.strip().startswith("!"):
                            # 在块结束前，添加缺失的字段
                            for fld in all_fields:
                                if fld not in found_fields:
                                    if fld == field_name:
                                        new_lines.append(self._format_forcing_field_line(fld, 'T'))
                                    else:
                                        new_lines.append(self._format_forcing_field_line(fld, 'F'))
                            # 确保 GRID%LATLON 存在
                            if not found_grid_latlon:
                                new_lines.append("  FORCING%GRID%LATLON          = T\n")
                            in_forcing_nml = False
                            new_lines.append(line)
                            continue

                        # 在 FORCING_NML 块中处理
                        if in_forcing_nml:
                            # 处理 FORCING%FIELD%* 行
                            if re.search(r'FORCING%FIELD%', line, re.IGNORECASE):
                                # 提取字段名
                                field_match = re.search(r'FORCING%FIELD%(\w+)', line, re.IGNORECASE)
                                if field_match:
                                    found_field_name = field_match.group(1)
                                    found_fields.add(found_field_name)
                                    # 检查是否是当前字段
                                    if found_field_name.upper() == field_name.upper():
                                        # 设置为 T
                                        new_lines.append(self._format_forcing_field_line(field_name, 'T'))
                                    else:
                                        # 设置为 F
                                        new_lines.append(self._format_forcing_field_line(found_field_name, 'F'))
                                continue
                            # 保留 FORCING%TIMESTART 和 FORCING%TIMESTOP
                            elif re.search(r'FORCING%TIMESTART|FORCING%TIMESTOP', line, re.IGNORECASE):
                                new_lines.append(line)
                            # 保留 FORCING%GRID%*（确保 LATLON = T）
                            elif re.search(r'FORCING%GRID%', line, re.IGNORECASE):
                                if 'LATLON' in line.upper():
                                    new_lines.append("  FORCING%GRID%LATLON          = T\n")
                                    found_grid_latlon = True
                                else:
                                    new_lines.append(line)
                            else:
                                # 保留其他行（如注释等）
                                new_lines.append(line)
                            continue

                        # 检查是否进入 FILE_NML 块
                        if "&FILE_NML" in line.upper():
                            in_file_nml = True
                            new_lines.append(line)
                            continue

                        # 检查是否离开 FILE_NML 块
                        if in_file_nml and re.match(r'^\s*/\s*$', line) and not line.strip().startswith("!"):
                            in_file_nml = False
                            new_lines.append(line)
                            continue

                        # 在 FILE_NML 块中处理
                        if in_file_nml:
                            # 替换 FILE%FILENAME
                            if "FILE%FILENAME" in line:
                                new_lines.append(f"  FILE%FILENAME      = '{filename}'\n")
                                continue
                            # 替换 FILE%VAR(*) 行
                            var_match = re.search(r'FILE%VAR\s*\(\s*(\d+)\s*\)', line, re.IGNORECASE)
                            if var_match:
                                var_index = int(var_match.group(1))
                                # 如果索引在范围内，替换为新变量名
                                if 1 <= var_index <= len(var_names):
                                    new_lines.append(f"  FILE%VAR({var_index})        = '{var_names[var_index - 1]}'\n")
                                # 如果索引超出范围，跳过（删除多余的变量行）
                                continue
                            # 替换 FILE%LONGITUDE / FILE%LATITUDE（方案 §8：来自解析结果）
                            elif "FILE%LONGITUDE" in line and lon_name:
                                new_lines.append(f"  FILE%LONGITUDE     = '{lon_name}'\n")
                                continue
                            elif "FILE%LATITUDE" in line and lat_name:
                                new_lines.append(f"  FILE%LATITUDE      = '{lat_name}'\n")
                                continue
                            # 保留其他行（注释等）
                            else:
                                new_lines.append(line)
                            continue

                        # 其他行直接添加
                        new_lines.append(line)

                    # 写回文件
                    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
                        f.writelines(new_lines)

                    copied_assignments: list[Assignment] = [
                        (f"FORCING%FIELD%{field_name}", "T"),
                        ("FILE%FILENAME", f"'{filename}'"),
                    ]
                    for index, var_name in enumerate(var_names, start=1):
                        copied_assignments.append((f"FILE%VAR({index})", f"'{var_name}'"))
                    self.log(
                        format_nml_log_message(
                            "file_copied_modified",
                            "✅ 已复制并修改 {file}：\n{details}",
                            copied_assignments,
                            file=output_filename,
                        )
                    )

                tasks = []
                if field_key == 'ice':
                    # 只有存在 siconc 才生成冰场 prnc
                    if not var_names:
                        continue
                    tasks.append({
                        "output_filename": "ww3_prnc_ice.nml",
                        "field_name": "ICE_CONC",
                        "var_names": var_names
                    })
                    if has_sithick:
                        tasks.append({
                            "output_filename": "ww3_prnc_ice1.nml",
                            "field_name": "ICE_PARAM1",
                            "var_names": [sithick_var or "sithick"]
                        })
                else:
                    tasks.append({
                        "output_filename": config['output_filename'],
                        "field_name": config['field_name'],
                        "var_names": var_names
                    })

                for task in tasks:
                    try:
                        _write_prnc_file(task["output_filename"], task["field_name"], task["var_names"], lon_name=lon_name, lat_name=lat_name)
                    except Exception as e:
                        self.log(tr("file_copy_modify_failed", "❌ 复制并修改 {file} 失败：{error}").format(file=task["output_filename"], error=e))
            except Exception as e:
                self.log(tr("file_copy_modify_failed", "❌ 复制并修改 {file} 失败：{error}").format(file=config['output_filename'], error=e))

    def _load_field_resolution(self, workdir, field_key, file_path):
        """获取单个强迫场的变量解析结果（方案 §7/§8）。

        优先读取工作目录 ``forcing_manifest.json``；清单缺失或场不存在时
        用统一解析服务重新解析（兼容旧工作目录）。

        [EN] Get one field's variable resolution (spec §7/§8). The workdir
        ``forcing_manifest.json`` is preferred; when missing, the unified
        resolver re-parses the file (backwards compatible with old workdirs).

        返回:
            ``ResolvedForcingVariables`` 或 ``None``

        [EN] Returns:
            ``ResolvedForcingVariables`` or ``None``.
        """
        try:
            from ...domain.config_models import ResolvedForcingVariables
            from ...infrastructure.forcing.forcing_manifest import load_manifest

            data = load_manifest(workdir)
            entry = data.get(field_key) if isinstance(data, dict) else None
            if entry and entry.get("variables"):
                return ResolvedForcingVariables(
                    field=field_key,
                    longitude=entry.get("longitude") or "longitude",
                    latitude=entry.get("latitude") or "latitude",
                    source_time="",
                    output_time=entry.get("time") or "time",
                    components=list(entry.get("variables", [])),
                    thickness=entry.get("thickness"),
                )
        except Exception:
            pass
        try:
            from ...infrastructure.forcing.forcing_variable_resolver import (
                ForcingVariableError,
                resolve_forcing_variables,
            )

            custom = None
            try:
                params_path = os.path.join(workdir, "params.yml")
                if os.path.isfile(params_path):
                    from ...application.configuration import load_pipeline_config

                    cfg = load_pipeline_config(params_path)
                    custom = cfg.forcing.custom.get(field_key)
            except Exception:
                pass
            return resolve_forcing_variables(file_path, field_key, custom)
        except ForcingVariableError:
            return None
        except Exception:
            return None

    def _get_forcing_field_variables(self, file_path, var_candidates):
        """
        从 NetCDF 文件中读取变量名

        参数:
            file_path: NetCDF 文件路径
            var_candidates: 变量名候选列表，例如 [['uo', 'UO'], ['vo', 'VO']] 或 [['zos', 'ZOS']]

        返回:
            变量名列表，例如 ['uo', 'vo'] 或 ['zos']
        """
        try:
            from netCDF4 import Dataset
            with Dataset(file_path, "r") as ds:
                var_names = []
                for candidates in var_candidates:
                    found = False
                    for candidate in candidates:
                        if candidate in ds.variables:
                            var_names.append(candidate)
                            found = True
                            break
                    if not found:
                        return None  # 如果任何一个变量都找不到，返回 None
                return var_names
        except Exception as e:
            return None

    def _create_prnc_content(self, template, field_name, filename, var_names, start_datetime, end_datetime, file_path=None):
        """
        根据模板创建新的 prnc 文件内容

        参数:
            template: 模板内容
            field_name: 强迫场名称，例如 'CURRENTS', 'WATER_LEVELS', 'ICE_CONC'
            filename: 文件名，例如 'current.nc'
            var_names: 变量名列表，例如 ['uo', 'vo'] 或 ['zos']
            start_datetime: 开始时间，例如 '20250101 000000'
            end_datetime: 结束时间，例如 '20250131 235959'
            file_path: 文件路径（仅用于冰场检查 sithick 变量）

        返回:
            新的文件内容
        """
        import re
        from netCDF4 import Dataset

        # 检查冰场是否包含 sithick 变量
        has_sithick = False
        if field_name == 'ICE_CONC' and file_path:
            try:
                with Dataset(file_path, "r") as ds:
                    has_sithick = 'sithick' in ds.variables or 'SITHICK' in ds.variables
            except Exception:
                pass

        # 确定需要设置为 T 的字段列表
        fields_to_enable = [field_name]
        if field_name == 'ICE_CONC' and has_sithick:
            fields_to_enable.append('ICE_PARAM1')

        # 逐行处理，确保替换精确
        lines = template.split('\n')
        new_lines = []

        for line in lines:
            # 替换 FORCING%FIELD%* 字段
            if 'FORCING%FIELD%' in line and '=' in line:
                # 检查当前行是哪个字段
                field_match = re.search(r'FORCING%FIELD%(\w+)', line)
                if field_match:
                    current_field = field_match.group(1)
                    # 如果是要启用的字段，设置为 T
                    if current_field in fields_to_enable:
                        line = re.sub(
                            r'(\s+FORCING%FIELD%\w+\s*=\s*)\w+',
                            r'\1T',
                            line
                        )
                    else:
                        # 其他字段设置为 F
                        line = re.sub(
                            r'(\s+FORCING%FIELD%\w+\s*=\s*)\w+',
                            r'\1F',
                            line
                        )

            # 替换时间范围
            if 'FORCING%TIMESTART' in line:
                line = re.sub(
                    r"(\s+FORCING%TIMESTART\s*=\s*')\d{8}\s+\d{6}(')",
                    lambda m: f"{m.group(1)}{start_datetime}{m.group(2)}",
                    line
                )
            elif 'FORCING%TIMESTOP' in line:
                line = re.sub(
                    r"(\s+FORCING%TIMESTOP\s*=\s*')\d{8}\s+\d{6}(')",
                    lambda m: f"{m.group(1)}{end_datetime}{m.group(2)}",
                    line
                )

            # 替换文件名
            if 'FILE%FILENAME' in line:
                line = re.sub(
                    r"(FILE%FILENAME\s*=\s*')[\w\.]+(')",
                    lambda m: f"{m.group(1)}{filename}{m.group(2)}",
                    line
                )

            new_lines.append(line)

        # 重新组合文本，用于后续的变量名替换
        template = '\n'.join(new_lines)

        # 替换变量名
        # 先删除所有 FILE%VAR(*) 行（包括可能的注释）
        lines = template.split('\n')
        new_lines = []
        in_file_nml = False
        var_inserted = False

        for line in lines:
            # 检查是否进入 FILE_NML 块
            if "&FILE_NML" in line:
                in_file_nml = True
                new_lines.append(line)
            # 检查是否离开 FILE_NML 块
            elif in_file_nml and "/" in line and not line.strip().startswith("!"):
                # 如果还没插入变量名，在结束标记前插入
                # if not var_inserted:
                #     for i, var_name in enumerate(var_names, 1):
                #         new_lines.append(f"  FILE%VAR({i})        = '{var_name}'")
                new_lines.append(line)
                in_file_nml = False
                var_inserted = False
            # 在 FILE_NML 块中处理
            elif in_file_nml:
                # 跳过 FILE%VAR(*) 行
                if re.match(r'\s+FILE%VAR\(\d+\)', line):
                    continue
                # 在 FILE%LATITUDE 行后插入变量名
                elif "FILE%LATITUDE" in line:
                    new_lines.append(line)
                    if not var_inserted:
                        for i, var_name in enumerate(var_names, 1):
                            new_lines.append(f"  FILE%VAR({i})        = '{var_name}'")
                        var_inserted = True
                else:
                    new_lines.append(line)
            else:
                # 不在 FILE_NML 块中的行直接添加
                new_lines.append(line)

        return '\n'.join(new_lines)
