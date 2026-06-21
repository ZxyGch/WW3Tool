"""ww3_multi.nml modifier mixin — nested grid multi-domain configuration."""
from __future__ import annotations

import os
import re
import traceback

from ...support.translations import tr
from ..runtime_config import load_config, PUBLIC_DIR, get_nml_template_dir
from .nml_primitives import NMLPrimitives


class WW3MultiNML(NMLPrimitives):
    """Mixin: ww3_multi.nml operations for nested grid mode."""

    def _read_type_field_list_from_shel(self, shel_path):
        """从 ww3_shel.nml 读取 TYPE%FIELD%LIST 的值"""
        if not os.path.exists(shel_path):
            return None

        try:
            with open(shel_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            for line in lines:
                # 检查是否为注释行
                line_stripped = line.lstrip()
                is_comment = line_stripped.startswith('!')

                # 查找 TYPE%FIELD%LIST 行（非注释行，不区分大小写）
                if not is_comment and re.search(r'TYPE%FIELD%LIST', line, re.IGNORECASE) and "=" in line:
                    # 提取引号内的内容
                    match = re.search(r"['\"]([^'\"]+)['\"]", line)
                    if match:
                        return match.group(1)
        except Exception:
            pass

        return None

    def _read_grid_nx_ny_from_nml(self, nml_path):
        """从 ww3_grid.nml 文件中读取 RECT%NX 和 RECT%NY 值"""
        if not os.path.exists(nml_path):
            return None, None

        try:
            with open(nml_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            nx = None
            ny = None
            in_rect_nml = False

            for line in lines:
                # 检查是否进入 RECT_NML 块
                if "&RECT_NML" in line.upper():
                    in_rect_nml = True
                    continue

                # 检查是否离开 RECT_NML 块
                if in_rect_nml and "/" in line and not line.strip().startswith("!"):
                    break

                # 在 RECT_NML 块中提取 NX 和 NY
                if in_rect_nml:
                    # 检查是否为注释行
                    line_stripped = line.lstrip()
                    if line_stripped.startswith('!'):
                        continue

                    # 提取 RECT%NX
                    nx_match = re.search(r"RECT%NX\s*=\s*(\d+)", line, re.IGNORECASE)
                    if nx_match:
                        nx = int(nx_match.group(1))

                    # 提取 RECT%NY
                    ny_match = re.search(r"RECT%NY\s*=\s*(\d+)", line, re.IGNORECASE)
                    if ny_match:
                        ny = int(ny_match.group(1))

            return nx, ny
        except Exception as e:
            self.log(tr("read_nml_error", "⚠️ 读取 {path} 时出错：{error}").format(path=nml_path, error=e))
            return None, None

    def _modify_ww3_multi_nml(self, nml_path):
        """修改 ww3_multi.nml 的起始时间和强迫场配置"""
        if not os.path.exists(nml_path):
            self.log(tr("ww3_multi_not_found_skip", "⚠️ 未找到 ww3_multi.nml：{path}，跳过修改").format(path=nml_path))
            return

        start_date = self.shel_start_edit.text().strip()
        end_date = self.shel_end_edit.text().strip()
        compute_precision = self.shel_step_edit.text().strip()

        if not (start_date.isdigit() and len(start_date) == 8 and end_date.isdigit() and len(end_date) == 8):
            self.log(tr("date_range_format_error", "❌ 起始/结束日期格式错误，应为 YYYYMMDD。"))
            return

        if not compute_precision.isdigit():
            self.log(tr("compute_precision_must_be_number", "❌ 计算精度必须为数字（秒）。"))
            return

        # 检查当前选择的强迫场
        has_wind = hasattr(self, 'selected_origin_file') and self.selected_origin_file and os.path.exists(self.selected_origin_file)
        has_current = hasattr(self, 'selected_current_file') and self.selected_current_file and os.path.exists(self.selected_current_file)
        has_level = hasattr(self, 'selected_level_file') and self.selected_level_file and os.path.exists(self.selected_level_file)
        has_ice = hasattr(self, 'selected_ice_file') and self.selected_ice_file and os.path.exists(self.selected_ice_file)

        # 检查海冰场是否包含 ICE_PARAM1 变量
        has_ice_param1 = False
        if has_ice:
            has_ice_param1 = self._check_ice_param1_variable(self.selected_ice_file)

        # 读取内外网格的 ww3_grid.nml 以计算进程比例
        coarse_nx, coarse_ny = None, None
        fine_nx, fine_ny = None, None
        coarse_ratio = 0.50  # 默认值
        fine_ratio = 0.50    # 默认值

        if hasattr(self, 'selected_folder') and self.selected_folder:
            coarse_grid_nml = os.path.join(self.selected_folder, "coarse", "ww3_grid.nml")
            fine_grid_nml = os.path.join(self.selected_folder, "fine", "ww3_grid.nml")

            coarse_nx, coarse_ny = self._read_grid_nx_ny_from_nml(coarse_grid_nml)
            fine_nx, fine_ny = self._read_grid_nx_ny_from_nml(fine_grid_nml)

            if coarse_nx is not None and coarse_ny is not None and fine_nx is not None and fine_ny is not None:
                points_coarse = coarse_nx * coarse_ny
                points_fine = fine_nx * fine_ny
                total_points = points_coarse + points_fine

                if total_points > 0:
                    # 计算基础比例
                    base_coarse_ratio = points_coarse / total_points

                    # 考虑网格分辨率的影响：更细的网格需要更多计算资源
                    # 使用加权计算，给 coarse 网格更多的权重（因为需要处理边界条件等）
                    # 或者设置一个最小比例保证
                    min_coarse_ratio = 0.35  # 最小比例保证，避免 coarse 分配过少

                    # 如果基础比例太小，使用最小比例
                    # 否则，在基础比例和最小比例之间取较大值，但不超过 0.6
                    if base_coarse_ratio < min_coarse_ratio:
                        coarse_ratio = min_coarse_ratio
                    else:
                        # 给 coarse 一个额外的权重（+5%），但不超过 0.6
                        coarse_ratio = min(base_coarse_ratio + 0.05, 0.60)

                    fine_ratio = 1.0 - coarse_ratio
            #         self.log(tr("grid_points_info", "📊 网格点数：coarse={coarse} ({coarse_nx}x{coarse_ny}), fine={fine} ({fine_nx}x{fine_ny}), 基础比例：coarse={base_ratio:.2f}, 调整后比例：coarse={coarse_ratio:.2f}, fine={fine_ratio:.2f}").format(coarse=points_coarse, coarse_nx=coarse_nx, coarse_ny=coarse_ny, fine=points_fine, fine_nx=fine_nx, fine_ny=fine_ny, base_ratio=base_coarse_ratio, coarse_ratio=coarse_ratio, fine_ratio=fine_ratio))
            #     else:
            #         self.log(tr("grid_points_zero", "⚠️ 总网格点数为0，使用默认比例"))
            # else:
            #     self.log(tr("grid_size_read_failed", "⚠️ 无法读取网格尺寸，使用默认比例"))

        try:
            with open(nml_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            in_domain = False
            in_output = False
            in_output_type = False
            in_input_grid = False
            in_model_grid = False
            model_index = 0  # 跟踪当前处理的 MODEL 索引

            # 跟踪修改状态
            modified_alltype_point_file = False
            modified_alldate_point = False
            modified_alltype_field_list = False

            # 检查是否为嵌套网格模式
            grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
            nested_text = tr("step2_grid_type_nested", "嵌套网格")
            is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")

            # 如果通过 grid_type_var 无法确定，检查文件夹结构
            if not is_nested_grid and hasattr(self, 'selected_folder') and self.selected_folder:
                coarse_dir = os.path.join(self.selected_folder, "coarse")
                fine_dir = os.path.join(self.selected_folder, "fine")
                is_nested_grid = (os.path.isdir(coarse_dir) and os.path.isdir(fine_dir))

            # 如果是嵌套网格模式，读取 ww3_shel.nml 中的 TYPE%FIELD%LIST 值
            alltype_field_list_value = None
            if is_nested_grid:
                # 优先从当前工作目录的 ww3_shel.nml 读取
                if hasattr(self, 'selected_folder') and self.selected_folder:
                    shel_path = os.path.join(self.selected_folder, "ww3_shel.nml")
                    alltype_field_list_value = self._read_type_field_list_from_shel(shel_path)

                # 如果工作目录中没有，尝试从 NML 模板目录读取
                if not alltype_field_list_value:
                    config = load_config()
                    nml_template_dir = get_nml_template_dir()
                    shel_path = os.path.join(nml_template_dir, "ww3_shel.nml")
                    alltype_field_list_value = self._read_type_field_list_from_shel(shel_path)

                # 如果还是找不到，使用默认值（谱分区输出常用变量）
                if not alltype_field_list_value:
                    alltype_field_list_value = 'HS LM T02 T0M1 T01 FP DIR SPR DP PHS PTP PLP PDIR PSPR PWS TWS PNR'

            # 检查是否为谱空间逐点计算模式
            is_spectral_point = self._is_spectral_point_mode()
            has_spectral_points = False
            if is_spectral_point and hasattr(self, 'spectral_points_table'):
                point_count = self.spectral_points_table.rowCount()
                has_spectral_points = point_count > 1  # 有数据点（跳过表头）

            for line in lines:
                # DOMAIN_NML
                if "&DOMAIN_NML" in line:
                    in_domain = True
                    new_lines.append(line)
                    continue

                if in_domain:
                    if re.search(r"DOMAIN%START", line):
                        new_lines.append(self._format_domain_line("DOMAIN%START", f"'{start_date} 000000'"))
                        continue
                    if re.search(r"DOMAIN%STOP", line):
                        new_lines.append(self._format_domain_line("DOMAIN%STOP", f"'{end_date} 235959'"))
                        continue
                    if "/" in line:
                        in_domain = False
                        new_lines.append(line)
                        continue

                # OUTPUT_TYPE_NML
                if "&OUTPUT_TYPE_NML" in line:
                    in_output_type = True
                    new_lines.append(line)
                    continue

                if in_output_type:
                    # 处理 ALLTYPE%FIELD%LIST（嵌套网格模式下从 ww3_shel.nml 读取值）
                    if re.search(r'ALLTYPE%FIELD%LIST', line, re.IGNORECASE):
                        if is_nested_grid and alltype_field_list_value:
                            # 嵌套网格模式：设置为从 ww3_shel.nml 读取的值
                            new_lines.append(f"  ALLTYPE%FIELD%LIST     = '{alltype_field_list_value}'\n")
                            modified_alltype_field_list = True
                        else:
                            # 普通网格模式：保留原行
                            new_lines.append(line)
                        continue
                    if "/" in line:
                        # 在结束标记之前，如果是谱空间逐点计算模式，添加 ALLTYPE%POINT%FILE
                        if is_spectral_point and has_spectral_points:
                            # 检查是否已有 ALLTYPE%POINT%FILE
                            has_alltype_point_file = False
                            for prev_line in new_lines[-10:]:  # 检查最近10行
                                if re.search(r'ALLTYPE%POINT%FILE', prev_line, re.IGNORECASE):
                                    has_alltype_point_file = True
                                    break

                            if not has_alltype_point_file:
                                new_lines.append(f"  ALLTYPE%POINT%FILE     = './fine/points.list'\n")
                                modified_alltype_point_file = True
                        # 如果是嵌套网格模式且还没有 ALLTYPE%FIELD%LIST，添加它
                        if is_nested_grid and not modified_alltype_field_list and alltype_field_list_value:
                            # 检查是否已有 ALLTYPE%FIELD%LIST
                            has_alltype_field_list = False
                            for prev_line in new_lines[-10:]:  # 检查最近10行
                                if re.search(r'ALLTYPE%FIELD%LIST', prev_line, re.IGNORECASE):
                                    has_alltype_field_list = True
                                    break

                            if not has_alltype_field_list:
                                new_lines.append(f"  ALLTYPE%FIELD%LIST     = '{alltype_field_list_value}'\n")
                                modified_alltype_field_list = True
                        in_output_type = False
                        new_lines.append(line)
                        continue
                    # 跳过现有的 ALLTYPE%POINT%FILE 行（如果存在）
                    if re.search(r'ALLTYPE%POINT%FILE', line, re.IGNORECASE):
                        # 已存在，保留原行
                        new_lines.append(line)
                        continue
                    new_lines.append(line)
                    continue

                # OUTPUT_DATE_NML
                if "&OUTPUT_DATE_NML" in line:
                    in_output = True
                    new_lines.append(line)
                    continue

                if in_output:
                    # ALLDATE%FIELD%START/STRIDE/STOP: 只替换 START 为合并格式，跳过 STRIDE 和 STOP
                    if re.search(r"ALLDATE%FIELD%START", line, re.IGNORECASE):
                        new_lines.append(f"  ALLDATE%FIELD          = '{start_date} 000000' '{compute_precision}' '{end_date} 235959'\n")
                        continue
                    if re.search(r"ALLDATE%FIELD%(STRIDE|STOP)", line, re.IGNORECASE):
                        continue  # 跳过（已合并到 ALLDATE%FIELD）
                    if re.search(r"ALLDATE%FIELD", line) and not re.search(r"ALLDATE%FIELD%", line, re.IGNORECASE):
                        # 已经是合并格式，直接替换
                        new_lines.append(f"  ALLDATE%FIELD          = '{start_date} 000000' '{compute_precision}' '{end_date} 235959'\n")
                        continue

                    # ALLDATE%RESTART%START/STOP: 更新为正确日期，保留 STRIDE
                    if re.search(r"ALLDATE%RESTART%START", line, re.IGNORECASE):
                        # 提取原有步长（从 START 行或回退查找 STRIDE 行）
                        new_lines.append(f"  ALLDATE%RESTART%START       = '{start_date} 000000'\n")
                        continue
                    if re.search(r"ALLDATE%RESTART%STRIDE", line, re.IGNORECASE):
                        # 保留原有 STRIDE 值
                        m = re.search(r"'(\d+)'", line)
                        restart_step_val = m.group(1) if m else '86400'
                        new_lines.append(f"  ALLDATE%RESTART%STRIDE      = '{restart_step_val}'\n")
                        continue
                    if re.search(r"ALLDATE%RESTART%STOP", line, re.IGNORECASE):
                        new_lines.append(f"  ALLDATE%RESTART%STOP        = '{end_date} 235959'\n")
                        continue
                    if re.search(r"ALLDATE%RESTART", line) and not re.search(r"ALLDATE%RESTART%", line, re.IGNORECASE):
                        # 已经是合并格式
                        m = re.search(r"'(\d{8}\s+\d{6})'\s*'(\d+)'\s*'(\d{8}\s+\d{6})'", line)
                        restart_step_val = m.group(2) if m else '86400'
                        new_lines.append(f"  ALLDATE%RESTART        = '{start_date} 000000' '{restart_step_val}' '{end_date} 235959'\n")
                        continue

                    # ALLDATE%POINT%START/STRIDE/STOP: 删除（模板默认 2025 年日期会覆盖正确值）
                    if re.search(r"ALLDATE%POINT%(START|STRIDE|STOP)", line, re.IGNORECASE):
                        continue

                    if "/" in line:
                        # 在结束标记之前，如果是谱空间逐点计算模式，添加 ALLDATE%POINT
                        if is_spectral_point and has_spectral_points:
                            # 检查是否已有合并格式的 ALLDATE%POINT
                            has_alldate_point = False
                            for prev_line in new_lines[-10:]:
                                if re.search(r'ALLDATE%POINT\s*=', prev_line, re.IGNORECASE) and not re.search(r'ALLDATE%POINT%', prev_line, re.IGNORECASE):
                                    has_alldate_point = True
                                    break

                            if not has_alldate_point:
                                new_lines.append(f"  ALLDATE%POINT          = '{start_date} 000000' '{compute_precision}' '{end_date} 235959'\n")
                                modified_alldate_point = True
                        in_output = False
                        new_lines.append(line)
                        continue
                    # 跳过已有的合并格式 ALLDATE%POINT 行（后续在 / 处重新添加）
                    if re.search(r'ALLDATE%POINT', line, re.IGNORECASE) and not re.search(r'ALLDATE%POINT%', line, re.IGNORECASE):
                        continue
                    new_lines.append(line)
                    continue

                # INPUT_GRID_NML
                if "&INPUT_GRID_NML" in line:
                    in_input_grid = True
                    new_lines.append(line)
                    continue

                if in_input_grid:
                    # INPUT(1) - 风场
                    if re.search(r"INPUT\(1\)%FORCING%WINDS", line):
                        value = "T" if has_wind else "F"
                        new_lines.append(self._format_input_model_line("INPUT(1)%FORCING%WINDS", value))
                        continue
                    # INPUT(2) - 流场
                    if re.search(r"INPUT\(2\)%FORCING%CURRENTS", line):
                        value = "T" if has_current else "F"
                        new_lines.append(self._format_input_model_line("INPUT(2)%FORCING%CURRENTS", value))
                        continue
                    # INPUT(3) - 水位场
                    if re.search(r"INPUT\(3\)%FORCING%WATER_LEVELS", line):
                        value = "T" if has_level else "F"
                        new_lines.append(self._format_input_model_line("INPUT(3)%FORCING%WATER_LEVELS", value))
                        continue
                    # INPUT(4) - 海冰场
                    if re.search(r"INPUT\(4\)%FORCING%ICE_CONC", line):
                        value = "T" if has_ice else "F"
                        new_lines.append(self._format_input_model_line("INPUT(4)%FORCING%ICE_CONC", value))
                        continue
                    if re.search(r"INPUT\(5\)%FORCING%ICE_PARAM1", line):
                        value = "T" if (has_ice and has_ice_param1) else "F"
                        new_lines.append(self._format_input_model_line("INPUT(5)%FORCING%ICE_PARAM1", value))
                        continue
                    if "/" in line:
                        in_input_grid = False
                        new_lines.append(line)
                        continue

                # MODEL_GRID_NML
                if "&MODEL_GRID_NML" in line:
                    in_model_grid = True
                    new_lines.append(line)
                    continue

                if in_model_grid:
                    # 检测 MODEL(1) 或 MODEL(2)
                    model_match = re.search(r"MODEL\((\d+)\)", line)
                    if model_match:
                        model_index = int(model_match.group(1))

                    # 处理 MODEL(1) 和 MODEL(2) 的强迫场设置
                    if model_index in [1, 2]:
                        # WINDS
                        if re.search(rf"MODEL\({model_index}\)%FORCING%WINDS", line):
                            value = "'native'" if has_wind else "'no'"
                            new_lines.append(self._format_input_model_line(f"MODEL({model_index})%FORCING%WINDS", value))
                            continue
                        # CURRENTS
                        if re.search(rf"MODEL\({model_index}\)%FORCING%CURRENTS", line):
                            value = "'native'" if has_current else "'no'"
                            new_lines.append(self._format_input_model_line(f"MODEL({model_index})%FORCING%CURRENTS", value))
                            continue
                        # WATER_LEVELS
                        if re.search(rf"MODEL\({model_index}\)%FORCING%WATER_LEVELS", line):
                            value = "'native'" if has_level else "'no'"
                            new_lines.append(self._format_input_model_line(f"MODEL({model_index})%FORCING%WATER_LEVELS", value))
                            continue
                        # ICE_CONC
                        if re.search(rf"MODEL\({model_index}\)%FORCING%ICE_CONC", line):
                            value = "'native'" if has_ice else "'no'"
                            new_lines.append(self._format_input_model_line(f"MODEL({model_index})%FORCING%ICE_CONC", value))
                            continue
                        # ICE_PARAM1
                        if re.search(rf"MODEL\({model_index}\)%FORCING%ICE_PARAM1", line):
                            value = "'native'" if (has_ice and has_ice_param1) else "'no'"
                            new_lines.append(self._format_input_model_line(f"MODEL({model_index})%FORCING%ICE_PARAM1", value))
                            continue
                        # RESOURCE - 根据网格点数动态计算
                        if re.search(rf"MODEL\({model_index}\)%RESOURCE", line):
                            if model_index == 1:
                                # MODEL(1)%RESOURCE = 1 1 0.00 {coarse_ratio:.2f} T
                                resource_value = f"1 1 0.00 {coarse_ratio:.2f} F"
                            elif model_index == 2:
                                # MODEL(2)%RESOURCE = 2 1 {coarse_ratio:.2f} 1.00 F
                                resource_value = f"2 1 {coarse_ratio:.2f} 1.00 F"
                            else:
                                resource_value = None

                            if resource_value:
                                new_lines.append(self._format_input_model_line(f"MODEL({model_index})%RESOURCE", resource_value))
                            else:
                                new_lines.append(line)
                            continue

                    if "/" in line:
                        in_model_grid = False
                        model_index = 0
                        new_lines.append(line)
                        continue

                new_lines.append(line)

            with open(nml_path, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(new_lines)

            # 构建日志消息
            log_parts = []
            log_parts.append(tr("step4_date_range_compute_precision", "起始={start}, 结束={end}, 计算精度={precision}s").format(start=start_date, end=end_date, precision=compute_precision))

            # 添加强迫场开关信息
            forcing_fields = []
            if has_wind:
                forcing_fields.append(tr("step4_forcing_field_wind", "风场"))
            if has_current:
                forcing_fields.append(tr("step4_forcing_field_current", "流场"))
            if has_level:
                forcing_fields.append(tr("step4_forcing_field_level", "水位场"))
            if has_ice:
                forcing_fields.append(tr("step4_forcing_field_ice", "海冰场"))
            if has_ice_param1:
                forcing_fields.append(tr("step4_forcing_field_ice_param1", "海冰厚度"))

            if forcing_fields:
                forcing_str = tr("step4_forcing_fields_enabled", "强迫场={fields}").format(fields="、".join(forcing_fields))
            else:
                forcing_str = tr("step4_forcing_fields_none", "强迫场=无")
            log_parts.append(forcing_str)

            # 添加计算资源信息
            resource_str = tr("step4_resource_ratio", "计算资源：coarse={coarse_ratio:.2f}, fine={fine_ratio:.2f}").format(coarse_ratio=coarse_ratio, fine_ratio=fine_ratio)
            log_parts.append(resource_str)

            if modified_alltype_point_file:
                log_parts.append(tr("step4_alltype_point_file_value", "ALLTYPE%POINT%FILE = './fine/points.list'"))

            if modified_alldate_point:
                log_parts.append(tr("step4_alldate_point_value", "ALLDATE%POINT = '{start} 000000' '{precision}' '{end} 235959'").format(start=start_date, precision=compute_precision, end=end_date))

            if modified_alltype_field_list and alltype_field_list_value:
                log_parts.append(tr("step4_alltype_field_list_set", "ALLTYPE%FIELD%LIST = '{value}' (谱分区输出)").format(value=alltype_field_list_value))

            log_msg = tr("step4_ww3_multi_updated_details", "✅ 已更新 ww3_multi.nml：{details}").format(details="，".join(log_parts))
            self.log(log_msg)

        except Exception as e:
            self.log(tr("ww3_multi_modify_error", "❌ 修改 ww3_multi.nml 出错：{error}").format(error=e))
            for line in traceback.format_exc().splitlines():
                self.log(line)
