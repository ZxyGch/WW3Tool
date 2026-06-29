"""ww3_multi.nml modifier mixin — nested grid multi-domain configuration."""
from __future__ import annotations

import os
import re
import traceback

from ...support.translations import tr
from ..runtime_config import DEFAULT_OUTPUT_VARS_SCHEME_VARS
from .nml_log_format import Assignment, format_nml_log_message
from .nml_primitives import NMLPrimitives


class WW3MultiNML(NMLPrimitives):
    """Mixin: ww3_multi.nml operations for nested grid mode."""

    def _resolve_output_field_list_for_multi(self) -> str:
        """从 params/GUI 当前谱分区方案解析变量列表（写入 ww3_multi.nml）。"""
        var_list = self._get_output_scheme_var_list()
        if var_list:
            return var_list
        return " ".join(DEFAULT_OUTPUT_VARS_SCHEME_VARS)

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
            modified_flghg1 = False
            modified_flghg2 = False

            # 检查是否为嵌套网格模式
            grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
            nested_text = tr("step2_grid_type_nested", "嵌套网格")
            is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")

            # 如果通过 grid_type_var 无法确定，检查 level* 目录结构
            if not is_nested_grid and hasattr(self, 'selected_folder') and self.selected_folder:
                is_nested_grid = bool(level_resources)

            alltype_field_list_value = None
            if is_nested_grid:
                alltype_field_list_value = self._resolve_output_field_list_for_multi()

            # 检查是否为二维谱点计算模式
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
                    # 双向嵌套（ww3_multi）：粗网格在细网格重叠区掩码计算与输出
                    if re.search(r"DOMAIN%FLGHG1", line):
                        new_lines.append(self._format_domain_line("DOMAIN%FLGHG1", "T"))
                        modified_flghg1 = True
                        continue
                    if re.search(r"DOMAIN%FLGHG2", line):
                        new_lines.append(self._format_domain_line("DOMAIN%FLGHG2", "T"))
                        modified_flghg2 = True
                        continue
                    if "/" in line:
                        if not modified_flghg1:
                            new_lines.append(self._format_domain_line("DOMAIN%FLGHG1", "T"))
                        if not modified_flghg2:
                            new_lines.append(self._format_domain_line("DOMAIN%FLGHG2", "T"))
                        in_domain = False
                        new_lines.append(line)
                        continue

                # OUTPUT_TYPE_NML
                if "&OUTPUT_TYPE_NML" in line:
                    in_output_type = True
                    new_lines.append(line)
                    continue

                if in_output_type:
                    # 处理 ALLTYPE%FIELD%LIST（嵌套网格：与 params 谱分区方案一致）
                    if re.search(r'ALLTYPE%FIELD%LIST', line, re.IGNORECASE):
                        if is_nested_grid and alltype_field_list_value:
                            # 嵌套网格：谱分区方案直接写入 ww3_multi，各层不用 ww3_shel.nml
                            new_lines.append(f"  ALLTYPE%FIELD%LIST     = '{alltype_field_list_value}'\n")
                            modified_alltype_field_list = True
                        else:
                            # 普通网格模式：保留原行
                            new_lines.append(line)
                        continue
                    if "/" in line:
                        # 在结束标记之前，如果是二维谱点计算模式，添加 ALLTYPE%POINT%FILE
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
                    # ALLDATE%FIELD：统一写入 output_step（输出步长）
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

                    # ALLDATE%POINT：谱点模式下同样使用 output_step
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

            # 构建日志：列出实际写入的 nml 字段
            field_triple = (
                f"'{start_date} 000000' '{output_stride}' '{end_date} 235959'"
            )
            multi_assignments: list[Assignment] = []
            if level_resources:
                multi_assignments.append(("DOMAIN%NRGRD", str(len(level_resources))))
            multi_assignments.extend(
                [
                    ("DOMAIN%START", f"'{start_date} 000000'"),
                    ("DOMAIN%STOP", f"'{end_date} 235959'"),
                    ("DOMAIN%FLGHG1", "T"),
                    ("DOMAIN%FLGHG2", "T"),
                    ("ALLDATE%FIELD", field_triple),
                    ("ALLDATE%RESTART%START", f"'{start_date} 000000'"),
                    ("ALLDATE%RESTART%STOP", f"'{end_date} 235959'"),
                ]
            )
            multi_assignments.extend(
                [
                    ("INPUT(1)%FORCING%WINDS", "T" if has_wind else "F"),
                    ("INPUT(2)%FORCING%CURRENTS", "T" if has_current else "F"),
                    ("INPUT(3)%FORCING%WATER_LEVELS", "T" if has_level else "F"),
                    ("INPUT(4)%FORCING%ICE_CONC", "T" if has_ice else "F"),
                    (
                        "INPUT(5)%FORCING%ICE_PARAM1",
                        "T" if (has_ice and has_ice_param1) else "F",
                    ),
                ]
            )
            if level_resources:
                forcing_native = [
                    ("WINDS", "'native'" if has_wind else "'no'"),
                    ("CURRENTS", "'native'" if has_current else "'no'"),
                    ("WATER_LEVELS", "'native'" if has_level else "'no'"),
                    ("ICE_CONC", "'native'" if has_ice else "'no'"),
                    (
                        "ICE_PARAM1",
                        "'native'" if (has_ice and has_ice_param1) else "'no'",
                    ),
                ]
                for name, rank, lo, hi in level_resources:
                    multi_assignments.append((f"MODEL({rank})%NAME", f"'{name}'"))
                    for fkey, fval in forcing_native:
                        multi_assignments.append((f"MODEL({rank})%FORCING%{fkey}", fval))
                    multi_assignments.append(
                        (f"MODEL({rank})%RESOURCE", f"{rank} 1 {lo:.2f} {hi:.2f} F")
                    )
            if modified_alltype_point_file:
                multi_assignments.extend(
                    [
                        ("ALLTYPE%POINT%FILE", "'points.list'"),
                        ("ALLTYPE%POINT%NAME", f"'{finest_name}'"),
                    ]
                )
            if modified_alldate_point:
                multi_assignments.append(("ALLDATE%POINT", field_triple))
            if modified_alltype_field_list and alltype_field_list_value:
                multi_assignments.append(
                    ("ALLTYPE%FIELD%LIST", f"'{alltype_field_list_value}'")
                )

            self.log(
                format_nml_log_message(
                    "step4_ww3_multi_updated_details",
                    "✅ 已更新 ww3_multi.nml：\n{details}",
                    multi_assignments,
                    blank_before_prefixes=(
                        "ALLTYPE%",
                        "ALLDATE%POINT",
                        "INPUT(",
                        "MODEL(",
                    ),
                )
            )

        except Exception as e:
            self.log(tr("ww3_multi_modify_error", "❌ 修改 ww3_multi.nml 出错：{error}").format(error=e))
            for line in traceback.format_exc().splitlines():
                self.log(line)

    def _modify_ww3_multi_alldate_track(self, nml_path: str) -> None:
        """嵌套 + 航迹：在 ww3_multi.nml 写入 ALLDATE%TRACK（积分阶段启用航迹输出）。

        普通网格走 ww3_shel 的 DATE%TRACK；嵌套由 ww3_multi 驱动，须配置 ALLDATE%TRACK。
        """
        if not nml_path or not os.path.exists(nml_path):
            return
        if not self._is_track_mode():
            return
        datetimes = self._track_datetimes_from_table()
        if not datetimes:
            return
        start_datetime, end_datetime = datetimes
        output_stride = self.output_precision_edit.text().strip()
        if not output_stride.isdigit():
            self.log(tr("output_precision_error_skip_track", "❌ 输出精度必须为数字（秒），跳过 ALLDATE%TRACK 修改"))
            return

        try:
            with open(nml_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines: list[str] = []
            in_output = False
            modified = False
            track_triple = (
                f"  ALLDATE%TRACK          = '{start_datetime}' '{output_stride}' '{end_datetime}'\n"
            )

            for line in lines:
                if "&OUTPUT_DATE_NML" in line:
                    in_output = True
                    new_lines.append(line)
                    continue

                if in_output:
                    if re.search(r"ALLDATE%TRACK%START", line, re.IGNORECASE):
                        new_lines.append(f"  ALLDATE%TRACK%START         = '{start_datetime}'\n")
                        modified = True
                        continue
                    if re.search(r"ALLDATE%TRACK%STRIDE", line, re.IGNORECASE):
                        new_lines.append(f"  ALLDATE%TRACK%STRIDE        = '{output_stride}'\n")
                        modified = True
                        continue
                    if re.search(r"ALLDATE%TRACK%STOP", line, re.IGNORECASE):
                        new_lines.append(f"  ALLDATE%TRACK%STOP          = '{end_datetime}'\n")
                        modified = True
                        continue
                    if re.search(r"ALLDATE%TRACK", line) and not re.search(
                        r"ALLDATE%TRACK%", line, re.IGNORECASE
                    ):
                        new_lines.append(track_triple)
                        modified = True
                        continue
                    if "/" in line:
                        if not modified:
                            new_lines.append(track_triple)
                            modified = True
                        in_output = False
                        new_lines.append(line)
                        continue

                new_lines.append(line)

            if modified:
                with open(nml_path, "w", encoding="utf-8", newline="\n") as f:
                    f.writelines(new_lines)
                self.log(
                    format_nml_log_message(
                        "step4_ww3_multi_alldate_track_updated",
                        "✅ 已修改 ww3_multi.nml：\n{details}",
                        [
                            (
                                "ALLDATE%TRACK",
                                f"'{start_datetime}' '{output_stride}' '{end_datetime}'",
                            )
                        ],
                    )
                )
        except Exception as e:
            self.log(tr("ww3_multi_modify_error", "❌ 修改 ww3_multi.nml 出错：{error}").format(error=e))
