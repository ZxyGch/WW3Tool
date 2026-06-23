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

    def _read_grid_dtxy_from_nml(self, nml_path):
        """从 ww3_grid.nml 读取 TIMESTEPS%DTXY（CFL 传播时间步，秒）。"""
        if not os.path.exists(nml_path):
            return None
        try:
            with open(nml_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.lstrip().startswith("!"):
                        continue
                    m = re.search(r"TIMESTEPS%DTXY\s*=\s*([0-9]*\.?[0-9]+)", line, re.IGNORECASE)
                    if m:
                        return float(m.group(1))
        except Exception:
            return None
        return None

    def _compute_level_resources(self):
        """列出工作目录里的 level0..N 各层，按计算量(点数/DTXY)分配 COMM_FRAC。

        返回 ``[(name, rank, frac_lo, frac_hi), ...]``：name 为目录名 ``levelI``，
        rank 从 1 起（level0=rank 1，越细 rank 越大），frac 为累积进程区间。
        细网格 DTXY 更小、步数更多、每点更贵，故按 点数/DTXY 加权。
        """
        from .nested_level_dirs import list_nested_level_entries

        folder = getattr(self, "selected_folder", None)
        entries = list_nested_level_entries(folder) if folder else []
        if not entries:
            return []
        costs = []
        for path, _idx in entries:
            nml = os.path.join(str(path), "ww3_grid.nml")
            nx, ny = self._read_grid_nx_ny_from_nml(nml)
            dtxy = self._read_grid_dtxy_from_nml(nml) or 1.0
            costs.append(((nx or 1) * (ny or 1)) / dtxy)
        total = sum(costs) or 1.0
        out, acc, n = [], 0.0, len(entries)
        for i, (path, _idx) in enumerate(entries):
            lo = acc
            acc += costs[i] / total
            hi = 1.0 if i == n - 1 else acc
            out.append((path.name, i + 1, round(lo, 4), round(hi, 4)))
        return out

    def _modify_ww3_multi_nml(self, nml_path):
        """修改 ww3_multi.nml 的起始时间和强迫场配置"""
        if not os.path.exists(nml_path):
            self.log(tr("ww3_multi_not_found_skip", "⚠️ 未找到 ww3_multi.nml：{path}，跳过修改").format(path=nml_path))
            return

        start_date = self.shel_start_edit.text().strip()
        end_date = self.shel_end_edit.text().strip()
        output_stride = self.output_precision_edit.text().strip()

        if not (start_date.isdigit() and len(start_date) == 8 and end_date.isdigit() and len(end_date) == 8):
            self.log(tr("date_range_format_error", "❌ 起始/结束日期格式错误，应为 YYYYMMDD。"))
            return

        if not output_stride.isdigit():
            self.log(tr("output_precision_must_be_number", "❌ 输出精度必须为数字（秒）。"))
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

        # 计算各嵌套层(level0..N)的进程分配 COMM_FRAC，按计算量 点数/DTXY 加权
        level_resources = self._compute_level_resources()
        # 最细层目录名（谱点输出 out_pnt 命名用最细层）
        from .nested_level_dirs import finest_nested_level_name

        finest_name = (
            level_resources[-1][0]
            if level_resources
            else finest_nested_level_name(getattr(self, "selected_folder", "") or "")
        )

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
            modified_alldate_field = False
            modified_alltype_field_list = False

            # 检查是否为嵌套网格模式
            grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
            nested_text = tr("step2_grid_type_nested", "嵌套网格")
            is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")

            # 如果通过 grid_type_var 无法确定，检查 level* 目录结构
            if not is_nested_grid and hasattr(self, 'selected_folder') and self.selected_folder:
                is_nested_grid = bool(level_resources)

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
                    if re.search(r"DOMAIN%NRGRD", line) and level_resources:
                        new_lines.append(self._format_domain_line("DOMAIN%NRGRD", str(len(level_resources))))
                        continue
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
                                new_lines.append("  ALLTYPE%POINT%FILE     = 'points.list'\n")
                                # 统一点输出命名为最细层 → out_pnt.<finest>，与运行脚本一致
                                new_lines.append(f"  ALLTYPE%POINT%NAME     = '{finest_name}'\n")
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
                    # ALLDATE%FIELD：统一写入 output_precision（输出步长）
                    if re.search(r"ALLDATE%FIELD%START", line, re.IGNORECASE):
                        new_lines.append(f"  ALLDATE%FIELD          = '{start_date} 000000' '{output_stride}' '{end_date} 235959'\n")
                        modified_alldate_field = True
                        continue
                    if re.search(r"ALLDATE%FIELD%(STRIDE|STOP)", line, re.IGNORECASE):
                        continue
                    if re.search(r"ALLDATE%FIELD", line) and not re.search(r"ALLDATE%FIELD%", line, re.IGNORECASE):
                        new_lines.append(f"  ALLDATE%FIELD          = '{start_date} 000000' '{output_stride}' '{end_date} 235959'\n")
                        modified_alldate_field = True
                        continue

                    # ALLDATE%POINT：谱点模式下同样使用 output_precision
                    if re.search(r"ALLDATE%POINT%START", line, re.IGNORECASE):
                        if is_spectral_point and has_spectral_points:
                            new_lines.append(f"  ALLDATE%POINT          = '{start_date} 000000' '{output_stride}' '{end_date} 235959'\n")
                            modified_alldate_point = True
                        continue
                    if re.search(r"ALLDATE%POINT%(STRIDE|STOP)", line, re.IGNORECASE):
                        continue
                    if re.search(r"ALLDATE%POINT", line) and not re.search(r"ALLDATE%POINT%", line, re.IGNORECASE):
                        if is_spectral_point and has_spectral_points:
                            new_lines.append(f"  ALLDATE%POINT          = '{start_date} 000000' '{output_stride}' '{end_date} 235959'\n")
                            modified_alldate_point = True
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

                    if "/" in line:
                        if not modified_alldate_field:
                            new_lines.append(f"  ALLDATE%FIELD          = '{start_date} 000000' '{output_stride}' '{end_date} 235959'\n")
                            modified_alldate_field = True
                        # 谱点模式：若模板无 POINT 行，在结束前补写
                        if is_spectral_point and has_spectral_points and not modified_alldate_point:
                            new_lines.append(f"  ALLDATE%POINT          = '{start_date} 000000' '{output_stride}' '{end_date} 235959'\n")
                            modified_alldate_point = True
                        in_output = False
                        new_lines.append(line)
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

                # MODEL_GRID_NML — 按 level_resources 重新生成 N 个 MODEL 块
                if "&MODEL_GRID_NML" in line:
                    in_model_grid = True
                    new_lines.append(line)
                    if level_resources:
                        forcing = [
                            ("WINDS", "'native'" if has_wind else "'no'"),
                            ("CURRENTS", "'native'" if has_current else "'no'"),
                            ("WATER_LEVELS", "'native'" if has_level else "'no'"),
                            ("ICE_CONC", "'native'" if has_ice else "'no'"),
                            ("ICE_PARAM1", "'native'" if (has_ice and has_ice_param1) else "'no'"),
                        ]
                        for name, rank, lo, hi in level_resources:
                            new_lines.append("\n")
                            new_lines.append(self._format_input_model_line(f"MODEL({rank})%NAME", f"'{name}'"))
                            for fkey, fval in forcing:
                                new_lines.append(self._format_input_model_line(f"MODEL({rank})%FORCING%{fkey}", fval))
                            new_lines.append(self._format_input_model_line(
                                f"MODEL({rank})%RESOURCE", f"{rank} 1 {lo:.2f} {hi:.2f} F"))
                    continue

                if in_model_grid:
                    # 已重新生成；跳过模板原有 MODEL 行，仅在结束标记 / 处收尾
                    if line.strip() == "/":
                        in_model_grid = False
                        new_lines.append(line)
                        continue
                    if not level_resources:
                        new_lines.append(line)  # 没读到层信息时保留模板原样
                    continue

                new_lines.append(line)

            with open(nml_path, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(new_lines)

            # 构建日志消息
            log_parts = []
            log_parts.append(tr("step4_date_range_output_step", "起始={start}, 结束={end}, 输出步长={step}s").format(start=start_date, end=end_date, step=output_stride))

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

            # 添加计算资源信息（各层进程占比）
            if level_resources:
                ratios = ", ".join(f"{name}={hi - lo:.2f}" for name, _rank, lo, hi in level_resources)
                resource_str = tr("step4_resource_ratio", "计算资源：{ratios}").format(ratios=ratios)
                log_parts.append(resource_str)

            if modified_alltype_point_file:
                log_parts.append(tr("step4_alltype_point_file_value", "ALLTYPE%POINT%FILE = '{path}'").format(path="points.list"))

            if modified_alldate_point:
                log_parts.append(tr("step4_alldate_point_value", "ALLDATE%POINT = '{start} 000000' '{precision}' '{end} 235959'").format(start=start_date, precision=output_stride, end=end_date))

            if modified_alltype_field_list and alltype_field_list_value:
                log_parts.append(tr("step4_alltype_field_list_set", "ALLTYPE%FIELD%LIST = '{value}' (谱分区输出)").format(value=alltype_field_list_value))

            log_msg = tr("step4_ww3_multi_updated_details", "✅ 已更新 ww3_multi.nml：{details}").format(details="，".join(log_parts))
            self.log(log_msg)

        except Exception as e:
            self.log(tr("ww3_multi_modify_error", "❌ 修改 ww3_multi.nml 出错：{error}").format(error=e))
            for line in traceback.format_exc().splitlines():
                self.log(line)
