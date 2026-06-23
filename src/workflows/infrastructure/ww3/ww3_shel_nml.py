"""ww3_shel.nml 修改 Mixin — 时间设置、强迫输入、输出方案与点/航迹日期。

负责写入 WW3 主程序 namelist 中的模拟起止时间、计算步长、强迫场 INPUT 开关、
谱分区输出变量列表（``TYPE%FIELD%LIST``），以及谱点/航迹模式的 DATE 与 POINT 配置。
"""
from __future__ import annotations

import os
import re
import glob
import shutil

from ...support.translations import tr
from ..runtime_config import get_nml_template_dir
from .nml_primitives import NMLPrimitives


class WW3ShelNML(NMLPrimitives):
    """``ww3_shel.nml`` 相关操作的 Mixin 类。

    公开入口 ``modify_ww3_shel_times`` 将 GUI 时间参数写入工作目录；
    ``_apply_output_scheme_to_dir`` 同步谱分区变量至 shel 与 ounf namelist。
    """

    def _ensure_ww3_shel_nml(self, target_dir: str) -> str | None:
        """确保目录中存在 ww3_shel.nml（缺失则从 NML 模板复制）。"""
        if not target_dir or not isinstance(target_dir, str):
            return None
        shel_path = os.path.join(target_dir, "ww3_shel.nml")
        if os.path.isfile(shel_path):
            return shel_path
        template = os.path.join(get_nml_template_dir(), "ww3_shel.nml")
        if not os.path.isfile(template):
            return None
        try:
            shutil.copy2(template, shel_path)
            return shel_path
        except OSError:
            return None

    def _write_type_field_list_to_shel(self, target_dir: str, var_list_str: str) -> bool:
        """将谱分区变量列表写入指定目录 ww3_shel.nml 的 TYPE%FIELD%LIST。"""
        if not var_list_str or not target_dir or not isinstance(target_dir, str):
            return False
        shel_path = self._ensure_ww3_shel_nml(target_dir)
        if not shel_path:
            return False
        try:
            with open(shel_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            new_lines = []
            modified = False
            for line in lines:
                line_stripped = line.lstrip()
                is_comment = line_stripped.startswith("!")
                if not is_comment and re.search(r"TYPE%FIELD%LIST", line, re.IGNORECASE) and "=" in line:
                    new_lines.append(f"  TYPE%FIELD%LIST       = '{var_list_str}'\n")
                    modified = True
                else:
                    new_lines.append(line)
            if not modified:
                return False
            with open(shel_path, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(new_lines)
            return True
        except OSError:
            return False

    def _apply_output_scheme_to_dir(self, target_dir):
        """将谱分区输出方案写入指定目录的 ww3_shel.nml 和 ww3_ounf.nml"""
        if not target_dir or not isinstance(target_dir, str):
            return False

        var_list_str = self._get_output_scheme_var_list()
        if not var_list_str:
            return False

        modified_any = self._write_type_field_list_to_shel(target_dir, var_list_str)

        # 更新 ww3_ounf.nml 的 FIELD%LIST
        ww3_ounf_path = os.path.join(target_dir, "ww3_ounf.nml")
        if os.path.exists(ww3_ounf_path):
            try:
                with open(ww3_ounf_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                new_lines = []
                modified = False
                for line in lines:
                    line_stripped = line.lstrip()
                    is_comment = line_stripped.startswith('!')
                    if not is_comment and re.search(r'FIELD%LIST', line, re.IGNORECASE) and "=" in line:
                        new_lines.append(f"  FIELD%LIST             =  '{var_list_str}'\n")
                        modified = True
                    else:
                        new_lines.append(line)
                if modified:
                    with open(ww3_ounf_path, "w", encoding="utf-8", newline="\n") as f:
                        f.writelines(new_lines)
                    modified_any = True
            except Exception:
                pass

        if modified_any and self._output_scheme_contains_var("EF"):
            self._modify_namelists_e3d_in_dir(target_dir)

        return modified_any


    def _modify_ww3_shel_times_to_dir(self, target_dir, output_stride, grid_label=""):
        """在指定目录中修改 ww3_shel.nml"""
        if not target_dir or not isinstance(target_dir, str):
            return

        path = os.path.join(target_dir, "ww3_shel.nml")
        if not os.path.exists(path):
            self.log(tr("ww3_shel_not_found", "⚠️ 未找到 ww3_shel.nml：{path}，跳过").format(path=path))
            return

        start_date = self.shel_start_edit.text().strip()
        end_date = self.shel_end_edit.text().strip()
        main_step = output_stride

        if not (start_date.isdigit() and len(start_date) == 8 and end_date.isdigit() and len(end_date) == 8):
            self.log(tr("date_range_format_error", "❌ 起始/结束日期格式错误，应为 YYYYMMDD。"))
            return

        if not main_step.isdigit():
            self.log(tr("step_must_be_number", "❌ 步长必须为数字（秒）。"))
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            in_domain = False
            in_output = False

            for line in lines:
                # 检查是否为注释行（以 ! 开头，去除前导空格后）
                line_stripped = line.lstrip()
                is_comment = line_stripped.startswith('!')

                # DOMAIN_NML
                if "&DOMAIN_NML" in line:
                    in_domain = True
                    new_lines.append(line)
                    continue

                if in_domain:
                    # 只替换非注释行
                    if not is_comment and re.search(r"DOMAIN%START", line):
                        new_lines.append(f"  DOMAIN%START           =  '{start_date} 000000'\n")
                        continue
                    if not is_comment and re.search(r"DOMAIN%STOP", line):
                        new_lines.append(f"  DOMAIN%STOP            =  '{end_date} 235959'\n")
                        continue
                    if "/" in line:
                        in_domain = False
                        new_lines.append(line)
                        continue

                # OUTPUT_NML
                if "&OUTPUT_NML" in line:
                    in_output = True
                    new_lines.append(line)
                    continue

                if in_output:
                    # 只替换非注释行
                    if not is_comment and re.search(r"OUTPUT%FIELD%TIMESTART", line):
                        new_lines.append(f"  OUTPUT%FIELD%TIMESTART =  '{start_date} 000000'\n")
                        continue
                    if not is_comment and re.search(r"OUTPUT%FIELD%TIMESTRIDE", line):
                        new_lines.append(f"  OUTPUT%FIELD%TIMESTRIDE =  '{main_step}'\n")
                        continue
                    if "/" in line:
                        in_output = False
                        new_lines.append(line)
                        continue

                # OUTPUT_DATE_NML
                # 只替换非注释行
                # 模板中 DATE%FIELD%START/STRIDE/STOP 是三行，只替换 START 为合并格式，跳过 STRIDE 和 STOP
                if not is_comment and re.search(r"DATE%FIELD", line) and "=" in line:
                    if re.search(r"DATE%FIELD%START", line, re.IGNORECASE):
                        # 将 DATE%FIELD%START 替换为合并的 DATE%FIELD
                        new_lines.append(f"  DATE%FIELD          = '{start_date} 000000' '{main_step}' '{end_date} 235959'\n")
                        continue
                    elif re.search(r"DATE%FIELD%(STRIDE|STOP)", line, re.IGNORECASE):
                        # 跳过 STRIDE 和 STOP（已合并到上面一行）
                        continue
                    else:
                        # 已经是合并格式的 DATE%FIELD，直接替换
                        new_lines.append(f"  DATE%FIELD          = '{start_date} 000000' '{main_step}' '{end_date} 235959'\n")
                        continue

                # DATE%RESTART%START/STRIDE/STOP：更新为正确的模拟日期（保留 restart 输出配置）
                if not is_comment and re.search(r"DATE%RESTART%START", line, re.IGNORECASE) and "=" in line:
                    new_lines.append(f"  DATE%RESTART%START       = '{start_date} 000000'\n")
                    continue
                if not is_comment and re.search(r"DATE%RESTART%STOP", line, re.IGNORECASE) and "=" in line:
                    new_lines.append(f"  DATE%RESTART%STOP        = '{end_date} 235959'\n")
                    continue

                # DATE%POINT%START/STRIDE/STOP：跳过（删除），后续由 _modify_ww3_shel_date_point_in_dir 添加正确的 DATE%POINT
                if not is_comment and re.search(r"DATE%POINT%(START|STRIDE|STOP)", line, re.IGNORECASE) and "=" in line:
                    continue

                new_lines.append(line)

            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(new_lines)

            # 检查是否是谱空间逐点计算模式，如果是则合并日志
            is_spectral_point = self._is_spectral_point_mode()
            has_points = False
            if is_spectral_point and hasattr(self, 'spectral_points_table'):
                point_count = self.spectral_points_table.rowCount()
                has_points = point_count > 1  # 有数据点（除了表头）

            prefix = f"{grid_label} " if grid_label else ""

            if is_spectral_point and has_points:
                # 谱空间逐点计算模式：合并所有修改的日志
                modified_point_file = self._modify_ww3_shel_point_file_in_dir(target_dir, silent=True)
                modified_date_point = self._modify_ww3_shel_date_point_in_dir(target_dir, start_date, end_date, main_step, silent=True)

                # 构建合并的日志消息
                parts = []
                parts.append(tr("step4_date_range_output_step", "起始={start}, 结束={end}, 输出步长={step}s").format(start=start_date, end=end_date, step=main_step))
                if modified_point_file:
                    parts.append(tr("step4_added_type_point_file", "添加 TYPE%POINT%FILE = 'points.list'"))
                if modified_date_point:
                    parts.append(tr("step4_added_date_point_boundary", "添加 DATE%POINT 和 DATE%BOUNDARY"))

                log_msg = prefix + tr("step4_ww3_shel_spectral_point_updated", "✅ 已更新 ww3_shel.nml（谱空间逐点计算模式）：{details}").format(details="，".join(parts))
                self.log(log_msg)
            else:
                # 普通模式：只显示时间更新
                self.log(f"{prefix}{tr('step4_ww3_shel_updated', '✅ 已更新 ww3_shel.nml：DOMAIN%START={start}, DOMAIN%STOP={end}, DATE%FIELD%STRIDE={step}s').format(start=start_date, end=end_date, step=main_step)}")

        except Exception as e:
            self.log(tr("ww3_shel_modify_error", "❌ 修改 {file}/ww3_shel.nml 出错：{error}").format(file=os.path.basename(target_dir), error=e))


    def _format_domain_line(self, field_name, value):
        """格式化 DOMAIN%* 行，确保等号对齐在第17列"""
        prefix = "  "
        target_length = 16  # 等号前总长度（等号在17列）
        current_length = len(prefix + field_name)
        spaces_needed = target_length - current_length
        if spaces_needed < 1:
            spaces_needed = 1  # 至少保留一个空格
        return f"{prefix}{field_name}{' ' * spaces_needed}= {value}\n"

    def modify_ww3_shel_times(self):
        """修改 ww3_shel.nml（普通网格模式）"""
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return
        self._modify_ww3_shel_times_to_dir(self.selected_folder, self.output_precision_edit.text().strip())

    def _modify_ww3_shel_forcing_inputs(self, target_dir=None):
        """修改 ww3_shel.nml 中的 INPUT%FORCING%* 设置，根据选择的强迫场设置为 T 或 F"""
        if target_dir is None:
            target_dir = self.selected_folder

        if not target_dir or not isinstance(target_dir, str):
            return

        # 嵌套网格模式下使用 ww3_multi.nml，普通网格模式下使用 ww3_shel.nml
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        if grid_type == nested_text or grid_type == "嵌套网格":
            ww3_shel_path = os.path.join(target_dir, "ww3_multi.nml")
        else:
            ww3_shel_path = os.path.join(target_dir, "ww3_shel.nml")
        if not os.path.exists(ww3_shel_path):
            file_name = "ww3_multi.nml" if (grid_type == nested_text or grid_type == "嵌套网格") else "ww3_shel.nml"
            self.log(tr("file_not_found_skip_forcing", "⚠️ 未找到 {file}：{path}，跳过修改 INPUT%FORCING%*").format(file=file_name, path=ww3_shel_path))
            return

        self._modify_ww3_shel_forcing_inputs_in_dir(target_dir, ww3_shel_path)

    def _modify_ww3_shel_forcing_inputs_in_dir(self, target_dir, ww3_shel_path=None, grid_label=""):
        """在指定目录中修改 ww3_shel.nml 中的 INPUT%FORCING%* 设置"""
        if not target_dir or not isinstance(target_dir, str):
            return

        if ww3_shel_path is None:
            ww3_shel_path = os.path.join(target_dir, "ww3_shel.nml")

        if not os.path.exists(ww3_shel_path):
            return

        # 检查复选框状态，确定哪些强迫场被选中
        has_wind = True  # 风场总是启用
        has_current = False
        has_level = False
        has_ice = False
        has_ice_param1 = False

        if hasattr(self, 'forcing_field_checkboxes'):
            if 'current' in self.forcing_field_checkboxes:
                checkbox = self.forcing_field_checkboxes['current']['checkbox']
                has_current = checkbox.isChecked() if checkbox else False

            if 'level' in self.forcing_field_checkboxes:
                checkbox = self.forcing_field_checkboxes['level']['checkbox']
                has_level = checkbox.isChecked() if checkbox else False

            if 'ice' in self.forcing_field_checkboxes:
                checkbox = self.forcing_field_checkboxes['ice']['checkbox']
                has_ice = checkbox.isChecked() if checkbox else False

                # 如果冰场被选中，检查是否包含 sithick 变量
                if has_ice and hasattr(self, 'selected_ice_file') and self.selected_ice_file:
                    try:
                        from netCDF4 import Dataset
                        if os.path.exists(self.selected_ice_file):
                            with Dataset(self.selected_ice_file, "r") as ds:
                                has_ice_param1 = 'sithick' in ds.variables or 'SITHICK' in ds.variables
                    except Exception:
                        pass

        try:
            import re
            with open(ww3_shel_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            in_input_nml = False
            input_nml_modified = False

            for line in lines:
                # 检查是否进入 INPUT_NML 块
                if "&INPUT_NML" in line.upper():
                    in_input_nml = True
                    new_lines.append(line)
                # 检查是否离开 INPUT_NML 块
                elif in_input_nml and "/" in line and not line.strip().startswith("!"):
                    # 如果还没有修改过，在结束前添加所有设置
                    if not input_nml_modified:
                        # 添加所有 INPUT%FORCING%* 设置
                        indent = "  "
                        new_lines.append(f"{indent}INPUT%FORCING%WINDS         = '{'T' if has_wind else 'F'}'\n")
                        new_lines.append(f"{indent}INPUT%FORCING%WATER_LEVELS  = '{'T' if has_level else 'F'}'\n")
                        new_lines.append(f"{indent}INPUT%FORCING%CURRENTS      = '{'T' if has_current else 'F'}'\n")
                        new_lines.append(f"{indent}INPUT%FORCING%ICE_CONC      = '{'T' if has_ice else 'F'}'\n")
                        new_lines.append(f"{indent}INPUT%FORCING%ICE_PARAM1    = '{'T' if has_ice_param1 else 'F'}'\n")
                        input_nml_modified = True
                    new_lines.append(line)
                    in_input_nml = False
                # 在 INPUT_NML 块中处理
                elif in_input_nml:
                    # 跳过现有的 INPUT%FORCING%* 行
                    if re.search(r'INPUT%FORCING%', line, re.IGNORECASE):
                        continue
                    else:
                        new_lines.append(line)
                else:
                    # 不在 INPUT_NML 块中的行直接添加
                    new_lines.append(line)

            # 如果文件中没有 INPUT_NML 块，在文件末尾添加
            if not in_input_nml and not input_nml_modified:
                new_lines.append("\n&INPUT_NML\n")
                new_lines.append(f"  INPUT%FORCING%WINDS         = '{'T' if has_wind else 'F'}'\n")
                new_lines.append(f"  INPUT%FORCING%WATER_LEVELS  = '{'T' if has_level else 'F'}'\n")
                new_lines.append(f"  INPUT%FORCING%CURRENTS      = '{'T' if has_current else 'F'}'\n")
                new_lines.append(f"  INPUT%FORCING%ICE_CONC      = '{'T' if has_ice else 'F'}'\n")
                new_lines.append(f"  INPUT%FORCING%ICE_PARAM1    = '{'T' if has_ice_param1 else 'F'}'\n")
                new_lines.append("/\n")

            # 写入文件
            with open(ww3_shel_path, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(new_lines)

            prefix = f"{grid_label} " if grid_label else ""
            file_name = os.path.basename(ww3_shel_path)
            self.log(tr("file_modified_forcing", "{prefix}✅ 已修改 {file}：更新 INPUT%FORCING%* 设置").format(prefix=prefix, file=file_name))

        except Exception as e:
            prefix = f"{grid_label} " if grid_label else ""
            file_name = os.path.basename(ww3_shel_path) if ww3_shel_path else "ww3_shel.nml"
            self.log(tr("file_forcing_modify_failed", "{prefix}❌ 修改 {file} 中的 INPUT%FORCING%* 失败：{error}").format(prefix=prefix, file=file_name, error=e))

    def _modify_ww3_shel_point_file(self, silent=False):
        """修改 ww3_shel.nml，在 TYPE%FIELD%LIST 下一行添加 TYPE%POINT%FILE（支持嵌套网格模式）

        参数:
            silent: 如果为 True，不输出日志（用于合并日志）
        """
        # 检查计算模式是否为"谱空间逐点计算"
        if not self._is_spectral_point_mode():
            return

        # 检查点列表是否不为空（跳过表头，所以 rowCount() > 1）
        if not hasattr(self, 'spectral_points_table'):
            return

        point_count = self.spectral_points_table.rowCount()
        if point_count <= 1:  # 只有表头，没有数据点
            return

        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")

        if is_nested_grid:
            from .nested_level_dirs import list_nested_level_paths

            for level_dir in list_nested_level_paths(self.selected_folder):
                self._modify_ww3_shel_point_file_in_dir(str(level_dir), silent=silent)
        else:
            # 普通网格模式：修改工作目录下的文件
            self._modify_ww3_shel_point_file_in_dir(self.selected_folder, silent=silent)

    def _modify_ww3_shel_point_file_in_dir(self, target_dir, silent=False):
        """在指定目录下修改 ww3_shel.nml，在 TYPE%FIELD%LIST 下一行添加 TYPE%POINT%FILE

        参数:
            target_dir: 目标目录
            silent: 如果为 True，不输出日志（用于合并日志）

        返回:
            bool: 是否成功修改
        """
        ww3_shel_path = os.path.join(target_dir, "ww3_shel.nml")
        if not os.path.exists(ww3_shel_path):
            return False

        try:
            with open(ww3_shel_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            modified_point_file = False
            i = 0
            while i < len(lines):
                line = lines[i]

                # 检查是否为注释行（以 ! 开头，去除前导空格后）
                line_stripped = line.lstrip()
                is_comment = line_stripped.startswith('!')

                # 查找 TYPE%FIELD%LIST 这一行（不区分大小写，允许空格变化）
                # 只处理非注释行
                if not is_comment and re.search(r'TYPE%FIELD%LIST', line, re.IGNORECASE) and "=" in line:
                    # 保留原行，不替换
                    new_lines.append(line)

                    # 检查下一行是否已经有 TYPE%POINT%FILE
                    if i + 1 < len(lines):
                        next_line = lines[i + 1]
                        if re.search(r'TYPE%POINT%FILE', next_line, re.IGNORECASE):
                            # 已经存在，跳过添加，但需要保留原行
                            new_lines.append(next_line)
                            i += 1
                            continue

                    # 在下一行添加 TYPE%POINT%FILE = 'points.list'
                    new_lines.append("  TYPE%POINT%FILE          = 'points.list'\n")
                    modified_point_file = True
                else:
                    new_lines.append(line)

                i += 1

            if modified_point_file:
                with open(ww3_shel_path, "w", encoding="utf-8", newline="\n") as f:
                    f.writelines(new_lines)
                if not silent:
                    log_msg = tr("step4_ww3_shel_type_point_only", "✅ 已修改 ww3_shel.nml：添加 TYPE%POINT%FILE = 'points.list'")
                    self.log(log_msg)
                return True
            return False

        except Exception as e:
            if not silent:
                self.log(tr("ww3_shel_modify_error_str", "❌ 修改 ww3_shel.nml 时出错：{error}").format(error=str(e)))
            return False

    def _modify_ww3_shel_date_point(self, silent=False):
        """修改 ww3_shel.nml，在 DATE%FIELD 下一行添加 DATE%POINT 和 DATE%BOUNDARY（支持嵌套网格模式）

        参数:
            silent: 如果为 True，不输出日志（用于合并日志）
        """
        # 检查计算模式是否为"谱空间逐点计算"
        if not self._is_spectral_point_mode():
            return

        # 检查点列表是否不为空（跳过表头，所以 rowCount() > 1）
        if not hasattr(self, 'spectral_points_table'):
            return

        point_count = self.spectral_points_table.rowCount()
        if point_count <= 1:  # 只有表头，没有数据点
            return

        # 获取时间范围和计算精度
        start_date = self.shel_start_edit.text().strip()
        end_date = self.shel_end_edit.text().strip()
        output_stride = self.output_precision_edit.text().strip()

        if not (start_date.isdigit() and len(start_date) == 8 and end_date.isdigit() and len(end_date) == 8):
            if not silent:
                self.log(tr("date_format_error_skip_point", "❌ 起始/结束日期格式错误，应为 YYYYMMDD，跳过 DATE%POINT 和 DATE%BOUNDARY 修改"))
            return

        if not output_stride.isdigit():
            if not silent:
                self.log(tr("output_precision_error_skip_point", "❌ 输出精度必须为数字（秒），跳过 DATE%POINT 和 DATE%BOUNDARY 修改"))
            return

        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")

        if is_nested_grid:
            from .nested_level_dirs import list_nested_level_paths

            for level_dir in list_nested_level_paths(self.selected_folder):
                self._modify_ww3_shel_date_point_in_dir(
                    str(level_dir), start_date, end_date, output_stride, silent=silent
                )
        else:
            # 普通网格模式：修改工作目录下的文件
            self._modify_ww3_shel_date_point_in_dir(self.selected_folder, start_date, end_date, output_stride, silent=silent)

    def _modify_ww3_shel_date_point_in_dir(self, target_dir, start_date, end_date, output_stride, silent=False):
        """在指定目录下修改 ww3_shel.nml，在 DATE%FIELD 下一行添加 DATE%POINT 和 DATE%BOUNDARY

        参数:
            target_dir: 目标目录
            start_date: 起始日期
            end_date: 结束日期
            output_stride: 输出步长（秒）
            silent: 如果为 True，不输出日志（用于合并日志）

        返回:
            bool: 是否成功修改
        """
        ww3_shel_path = os.path.join(target_dir, "ww3_shel.nml")
        if not os.path.exists(ww3_shel_path):
            return False

        try:
            with open(ww3_shel_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            modified = False
            i = 0
            date_point_added = False  # 只在第一个 DATE%FIELD 后添加一次
            while i < len(lines):
                line = lines[i]

                # 检查是否为注释行（以 ! 开头，去除前导空格后）
                line_stripped = line.lstrip()
                is_comment = line_stripped.startswith('!')

                # 跳过（删除）模板中已有的 DATE%POINT%START/STRIDE/STOP
                # 这些是模板默认值，会与我们添加的 DATE%POINT 冲突（Fortran namelist 最后值生效）
                # 注意：不删除 DATE%RESTART%START/STRIDE/STOP，那些是 restart 输出配置，需要保留
                if not is_comment and re.search(r'DATE%POINT%(START|STRIDE|STOP)', line, re.IGNORECASE):
                    i += 1
                    continue

                new_lines.append(line)

                # 查找 DATE%FIELD 所在行（不区分大小写）
                # 只处理非注释行，且只在第一次出现时添加 DATE%POINT
                if not date_point_added and not is_comment and re.search(r'DATE%FIELD', line, re.IGNORECASE):
                    # 检查下一行是否已经有 DATE%POINT（也需要检查是否为注释行）
                    if i + 1 < len(lines):
                        next_line = lines[i + 1]
                        next_line_stripped = next_line.lstrip()
                        next_is_comment = next_line_stripped.startswith('!')
                        # 如果下一行是注释行，或者下一行已经有 DATE%POINT（非注释），则跳过
                        if not next_is_comment and re.search(r'DATE%POINT', next_line, re.IGNORECASE):
                            # 已经存在，标记已添加，继续处理
                            date_point_added = True
                            i += 1
                            continue

                    # 在下一行添加 DATE%POINT 和 DATE%BOUNDARY
                    new_lines.append(f"  DATE%POINT          = '{start_date} 000000' '{output_stride}' '{end_date} 235959'\n")
                    new_lines.append(f"  DATE%BOUNDARY       = '{start_date} 000000' '86400' '{end_date} 235959'\n")
                    modified = True
                    date_point_added = True

                i += 1

            if modified:
                with open(ww3_shel_path, "w", encoding="utf-8", newline="\n") as f:
                    f.writelines(new_lines)
                if not silent:
                    self.log(tr("step4_ww3_shel_date_updated", "✅ 已修改 ww3_shel.nml：添加 DATE%POINT 和 DATE%BOUNDARY（谱空间逐点计算模式）"))
                return True
            return False

        except Exception as e:
            if not silent:
                self.log(tr("ww3_shel_modify_error_str", "❌ 修改 ww3_shel.nml 时出错：{error}").format(error=str(e)))
            return False

    def _modify_ww3_shel_date_track(self):
        """修改 ww3_shel.nml，在 &OUTPUT_DATE_NML 下添加 DATE%TRACK（航迹模式）"""
        # 检查航迹点位表格是否存在且不为空
        if not hasattr(self, 'track_points_table'):
            return

        point_count = self.track_points_table.rowCount()
        if point_count <= 1:  # 只有表头，没有数据点
            return

        # 从表格中获取所有时间，找到最早和最晚的时间
        times = []
        for i in range(1, self.track_points_table.rowCount()):
            time_item = self.track_points_table.item(i, 0)
            if time_item:
                time_str = time_item.text().strip()
                if time_str and len(time_str) == 15 and ' ' in time_str:
                    try:
                        date_part, time_part = time_str.split()
                        if len(date_part) == 8 and len(time_part) == 6:
                            times.append(time_str)
                    except (ValueError, AttributeError):
                        continue

        if not times:
            return

        # 找到最早和最晚的时间
        # 将时间转换为可比较的格式进行排序
        # 格式：YYYYMMDD HHMMSS，可以直接按字符串排序
        times.sort()
        start_datetime = times[0]  # 格式：YYYYMMDD HHMMSS - 使用最早的时间（第一个点）
        end_datetime = times[-1]   # 格式：YYYYMMDD HHMMSS - 使用最晚的时间（最后一个点）

        # 获取输出步长
        output_stride = self.output_precision_edit.text().strip()
        if not output_stride.isdigit():
            self.log(tr("output_precision_error_skip_track", "❌ 输出精度必须为数字（秒），跳过 DATE%TRACK 修改"))
            return

        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")

        if is_nested_grid:
            from .nested_level_dirs import list_nested_level_paths

            for level_dir in list_nested_level_paths(self.selected_folder):
                self._modify_ww3_shel_date_track_in_dir(
                    str(level_dir), start_datetime, output_stride, end_datetime
                )
        else:
            # 普通网格模式：修改工作目录下的文件
            self._modify_ww3_shel_date_track_in_dir(self.selected_folder, start_datetime, output_stride, end_datetime)

    def _modify_ww3_shel_date_track_in_dir(self, target_dir, start_datetime, output_stride, end_datetime):
        """在指定目录下修改 ww3_shel.nml，在 &OUTPUT_DATE_NML 下添加 DATE%TRACK"""
        ww3_shel_path = os.path.join(target_dir, "ww3_shel.nml")
        if not os.path.exists(ww3_shel_path):
            return

        try:
            with open(ww3_shel_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            modified = False
            in_output_date_nml = False
            found_output_date_nml = False
            found_date_field = False
            i = 0

            while i < len(lines):
                line = lines[i]

                # 检查是否为注释行（以 ! 开头，去除前导空格后）
                line_stripped = line.lstrip()
                is_comment = line_stripped.startswith('!')

                new_lines.append(line)

                # 查找 &OUTPUT_DATE_NML 开始
                if "&OUTPUT_DATE_NML" in line:
                    found_output_date_nml = True
                    in_output_date_nml = True
                    i += 1
                    continue

                # 在 &OUTPUT_DATE_NML 块内查找结束标记或 DATE%FIELD
                if in_output_date_nml:
                    # 如果找到 DATE%FIELD 行（非注释），在其后添加 DATE%TRACK
                    if not is_comment and re.search(r'DATE%FIELD', line, re.IGNORECASE):
                        found_date_field = True
                        # 检查下一行是否已经有 DATE%TRACK
                        if i + 1 < len(lines):
                            next_line = lines[i + 1]
                            next_line_stripped = next_line.lstrip()
                            next_is_comment = next_line_stripped.startswith('!')
                            # 如果下一行已经有 DATE%TRACK（非注释），则跳过
                            if not next_is_comment and re.search(r'DATE%TRACK', next_line, re.IGNORECASE):
                                i += 1
                                continue
                        # 在下一行添加 DATE%TRACK
                        track_line = f"  DATE%TRACK          = '{start_datetime}' '{output_stride}' '{end_datetime}'\n"
                        new_lines.append(track_line)
                        modified = True
                    # 如果遇到结束标记 "/"
                    elif "/" in line and not is_comment:
                        # 如果在 OUTPUT_DATE_NML 块内且还没有添加 DATE%TRACK，则在结束标记之前插入
                        if not modified:
                            # 在结束标记之前插入 DATE%TRACK
                            # 先移除刚添加的结束标记行
                            new_lines.pop()
                            # 添加 DATE%TRACK
                            track_line = f"  DATE%TRACK          = '{start_datetime}' '{output_stride}' '{end_datetime}'\n"
                            new_lines.append(track_line)
                            # 再添加结束标记
                            new_lines.append(line)
                            modified = True
                        in_output_date_nml = False
                        i += 1
                        continue

                i += 1

            if modified:
                with open(ww3_shel_path, "w", encoding="utf-8", newline="\n") as f:
                    f.writelines(new_lines)
                self.log(tr("step4_ww3_shel_date_track_updated", "✅ 已修改 ww3_shel.nml：添加 DATE%TRACK（航迹模式）"))
            else:
                if not found_output_date_nml:
                    self.log(tr("output_date_nml_not_found", "⚠️ 航迹模式：未找到 &OUTPUT_DATE_NML 块，无法添加 DATE%TRACK"))
                elif not found_date_field:
                    self.log(tr("date_field_not_found", "⚠️ 航迹模式：未找到 DATE%FIELD 行，无法添加 DATE%TRACK"))

        except Exception as e:
            self.log(tr("ww3_shel_modify_error_str", "❌ 修改 ww3_shel.nml 时出错：{error}").format(error=str(e)))
            import traceback
            self.log(tr("detailed_error_info", "❌ 详细错误信息：{error}").format(error=traceback.format_exc()))
