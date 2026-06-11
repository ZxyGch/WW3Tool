"""ww3_ounp.nml 修改 Mixin — 谱空间逐点输出配置。

在「谱空间逐点计算」模式下，根据用户点列表修改 ``ww3_ounp.nml`` 的
``POINT%FILE``、时间范围与输出变量，并联动 ``namelists.nml``、``ww3_shel.nml``
及 ``points.list`` 文件。
"""
from __future__ import annotations

import os
import re

from ...support.translations import tr
from .nml_primitives import NMLPrimitives


class WW3OunpNML(NMLPrimitives):
    """``ww3_ounp.nml`` 谱点输出相关操作的 Mixin 类。

    核心方法 ``_apply_spectral_params_to_dir`` 在指定目录一次性完成点列表导出、
    E3D 标志、``ww3_shel.nml`` 点文件引用及 ``ww3_ounp.nml`` 参数写入。
    """

    def _apply_spectral_params_to_dir(self, target_dir, start_date, end_date, compute_precision, output_precision):
        """在指定目录下应用谱空间逐点计算相关参数"""
        # 检查计算模式是否为"谱空间逐点计算"
        if not self._is_spectral_point_mode():
            return

        # 检查点列表是否不为空（跳过表头，所以 rowCount() > 1）
        if not hasattr(self, 'spectral_points_table'):
            return

        point_count = self.spectral_points_table.rowCount()
        if point_count <= 1:  # 只有表头，没有数据点
            return

        # 读取点列表数据
        points_data = []
        for i in range(1, self.spectral_points_table.rowCount()):
            lon_item = self.spectral_points_table.item(i, 0)
            lat_item = self.spectral_points_table.item(i, 1)
            name_item = self.spectral_points_table.item(i, 2)

            if lon_item and lat_item:
                try:
                    lon = float(lon_item.text().strip())
                    lat = float(lat_item.text().strip())
                    name = name_item.text().strip() if name_item else f"Point_{i-1}"
                    points_data.append({
                        'lon': lon,
                        'lat': lat,
                        'name': name
                    })
                except ValueError:
                    continue

        if not points_data:
            return

        # 修改 namelists.nml
        self._modify_namelists_e3d_in_dir(target_dir)

        # 导出 points.list
        self._export_points_to_dir(target_dir, points_data)

        # 修改 ww3_shel.nml
        # 在嵌套网格模式下，这些修改会在 _apply_ww3_params_to_dir 之后进行
        # 在普通网格模式下，这些修改会在 _modify_ww3_shel_times_to_dir 之前进行
        # 所以统一使用 silent=True，让 _modify_ww3_shel_times_to_dir 或这里统一输出合并的日志
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")

        # 修改 TYPE%POINT%FILE
        modified_point_file = self._modify_ww3_shel_point_file_in_dir(target_dir, silent=True)

        # 修改 DATE%POINT 和 DATE%BOUNDARY
        modified_date_point = False
        if start_date and end_date and compute_precision:
            if (start_date.isdigit() and len(start_date) == 8 and
                end_date.isdigit() and len(end_date) == 8 and
                compute_precision.isdigit()):
                modified_date_point = self._modify_ww3_shel_date_point_in_dir(target_dir, start_date, end_date, compute_precision, silent=True)

        # 在嵌套网格模式下，这里输出合并的日志（因为 _modify_ww3_shel_times_to_dir 已经在之前调用了）
        if is_nested_grid and (modified_point_file or modified_date_point):
            # 获取时间信息用于日志
            start_date_for_log = self.shel_start_edit.text().strip()
            end_date_for_log = self.shel_end_edit.text().strip()
            compute_precision_for_log = compute_precision if compute_precision else self.shel_step_edit.text().strip()

            parts = []
            if start_date_for_log and end_date_for_log and compute_precision_for_log:
                parts.append(tr("step4_date_range_compute_step", "起始={start}, 结束={end}, 计算步长={step}s").format(start=start_date_for_log, end=end_date_for_log, step=compute_precision_for_log))
            if modified_point_file:
                parts.append(tr("step4_added_type_point_file", "添加 TYPE%POINT%FILE = 'points.list'"))
            if modified_date_point:
                parts.append(tr("step4_added_date_point_boundary", "添加 DATE%POINT 和 DATE%BOUNDARY"))

            if parts:
                log_msg = tr("step4_ww3_shel_spectral_point_updated", "✅ 已更新 ww3_shel.nml（谱空间逐点计算模式）：{details}").format(details="，".join(parts))
                self.log(log_msg)

        # 修改 ww3_ounp.nml
        if start_date and output_precision:
            if (start_date.isdigit() and len(start_date) == 8 and
                output_precision.isdigit()):
                self._modify_ww3_ounp_in_dir(target_dir, start_date, output_precision)

    def _export_points_to_file(self):
        """将当前点列表导出到 points.list 文件（清空原有内容，支持嵌套网格模式）"""
        # 检查计算模式是否为"谱空间逐点计算"
        if not self._is_spectral_point_mode():
            return

        # 检查点列表是否不为空（跳过表头，所以 rowCount() > 1）
        if not hasattr(self, 'spectral_points_table'):
            return

        point_count = self.spectral_points_table.rowCount()
        if point_count <= 1:  # 只有表头，没有数据点
            return

        # 读取表格中的所有点位（跳过表头，从第1行开始）
        points_data = []
        for i in range(1, self.spectral_points_table.rowCount()):
            lon_item = self.spectral_points_table.item(i, 0)
            lat_item = self.spectral_points_table.item(i, 1)
            name_item = self.spectral_points_table.item(i, 2)

            if lon_item and lat_item:
                try:
                    lon = float(lon_item.text().strip())
                    lat = float(lat_item.text().strip())
                    name = name_item.text().strip() if name_item else f"Point_{i-1}"
                    points_data.append({
                        'lon': lon,
                        'lat': lat,
                        'name': name
                    })
                except ValueError:
                    continue

        if not points_data:
            self.log(tr("no_valid_points_data", "⚠️ 没有有效的点位数据，跳过 points.list 文件生成"))
            return

        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")

        if is_nested_grid:
            # 嵌套网格模式：在 coarse 和 fine 目录下生成文件
            coarse_dir = os.path.join(self.selected_folder, "coarse")
            fine_dir = os.path.join(self.selected_folder, "fine")

            if os.path.isdir(coarse_dir):
                self._export_points_to_dir(coarse_dir, points_data)
            if os.path.isdir(fine_dir):
                self._export_points_to_dir(fine_dir, points_data)
        else:
            # 普通网格模式：在工作目录下生成文件
            self._export_points_to_dir(self.selected_folder, points_data)

    def _export_points_to_dir(self, target_dir, points_data):
        """在指定目录下导出点位到 points.list 文件"""
        points_list_path = os.path.join(target_dir, "points.list")

        try:
            def _fmt_point_coord(v):
                s = f"{float(v):.8f}".rstrip("0").rstrip(".")
                if "." not in s:
                    s += ".0"
                return s

            # 写入文件（清空原有内容）
            with open(points_list_path, "w", encoding="utf-8") as f:
                for point in points_data:
                    # 格式：经度 纬度 '名称'
                    f.write(
                        f"{_fmt_point_coord(point['lon'])} "
                        f"{_fmt_point_coord(point['lat'])} "
                        f"'{point['name']}'\n"
                    )

            self.log(tr("step4_points_list_created", "✅ 已创建 points.list 文件，包含 {count} 个点位").format(count=len(points_data)))

        except Exception as e:
            self.log(tr("export_points_error", "❌ 导出 points.list 时出错：{error}").format(error=str(e)))

    def _modify_ww3_ounp_if_needed(self):
        """如果需要，修改 ww3_ounp.nml 中的 POINT%TIMESTART 和 POINT%TIMESTRIDE（支持嵌套网格模式）"""
        # 检查计算模式是否为"谱空间逐点计算"
        if not self._is_spectral_point_mode():
            return

        # 检查点列表是否不为空（跳过表头，所以 rowCount() > 1）
        if not hasattr(self, 'spectral_points_table'):
            return

        point_count = self.spectral_points_table.rowCount()
        if point_count <= 1:  # 只有表头，没有数据点
            return

        # 获取起始日期和输出精度
        start_date = self.shel_start_edit.text().strip()
        output_precision = self.output_precision_edit.text().strip()

        if not (start_date.isdigit() and len(start_date) == 8):
            self.log(tr("start_date_format_error_skip_ounp", "❌ 起始日期格式错误，应为 YYYYMMDD，跳过 ww3_ounp.nml 修改"))
            return

        if not output_precision.isdigit():
            self.log(tr("output_precision_must_be_number", "❌ 输出精度必须为数字（秒），跳过 ww3_ounp.nml 修改"))
            return

        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")

        if is_nested_grid:
            # 嵌套网格模式：修改 coarse 和 fine 目录下的文件
            coarse_dir = os.path.join(self.selected_folder, "coarse")
            fine_dir = os.path.join(self.selected_folder, "fine")

            if os.path.isdir(coarse_dir):
                self._modify_ww3_ounp_in_dir(coarse_dir, start_date, output_precision)
            if os.path.isdir(fine_dir):
                self._modify_ww3_ounp_in_dir(fine_dir, start_date, output_precision)
        else:
            # 普通网格模式：修改工作目录下的文件
            self._modify_ww3_ounp_in_dir(self.selected_folder, start_date, output_precision)

    def _modify_ww3_ounp_in_dir(self, target_dir, start_date, output_precision):
        """在指定目录下修改 ww3_ounp.nml 中的 POINT%TIMESTART 和 POINT%TIMESTRIDE"""
        ww3_ounp_path = os.path.join(target_dir, "ww3_ounp.nml")
        if not os.path.exists(ww3_ounp_path):
            return

        # 读取文件分割设置。底层只接受英文枚举：
        # none/hour/day/month/year；界面翻译仅用于显示。
        from ..runtime_config import load_config
        config = load_config()
        file_split = str(config.get("FILE_SPLIT", "year")).strip().lower()
        file_split_value_map = {"none": 0, "year": 4, "month": 6, "day": 8, "hour": 10}
        if file_split not in file_split_value_map:
            raise ValueError("FILE_SPLIT must be one of: none, hour, day, month, year")
        timesplit_value = file_split_value_map[file_split]

        try:
            with open(ww3_ounp_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            modified_start = False
            modified_stride = False
            modified_split = False
            modified_spectra_type = False
            in_spectra_nml = False
            for line in lines:
                # 检查是否为注释行（以 ! 开头，去除前导空格后）
                line_stripped = line.lstrip()
                is_comment = line_stripped.startswith('!')

                # 只替换非注释行
                if not is_comment:
                    # 处理 SPECTRA_NML 块
                    if "&SPECTRA_NML" in line.upper():
                        in_spectra_nml = True
                        new_lines.append(line)
                        continue
                    if in_spectra_nml:
                        if re.search(r'SPECTRA%TYPE', line, re.IGNORECASE) and "=" in line:
                            new_lines.append("  SPECTRA%TYPE          =  4\n")
                            modified_spectra_type = True
                            continue
                        if re.match(r'^\s*/\s*$', line) and not line.strip().startswith("!"):
                            if not modified_spectra_type:
                                new_lines.append("  SPECTRA%TYPE          =  4\n")
                                modified_spectra_type = True
                            in_spectra_nml = False
                            new_lines.append(line)
                            continue
                    # 修改 POINT%TIMESTART
                    if re.search(r'POINT%TIMESTART', line, re.IGNORECASE):
                        new_lines.append(f"  POINT%TIMESTART        =  '{start_date} 000000'\n")
                        modified_start = True
                        continue
                    # 修改 POINT%TIMESTRIDE
                    if re.search(r'POINT%TIMESTRIDE', line, re.IGNORECASE):
                        new_lines.append(f"  POINT%TIMESTRIDE       =  '{output_precision}'\n")
                        modified_stride = True
                        continue
                    # 修改 POINT%TIMESPLIT
                    if re.search(r'POINT%TIMESPLIT', line, re.IGNORECASE):
                        new_lines.append(f"  POINT%TIMESPLIT        =  {timesplit_value}\n")
                        modified_split = True
                        continue
                new_lines.append(line)

            if not modified_split:
                in_point_nml = False
                insert_index = -1
                for i, line in enumerate(new_lines):
                    if "&POINT_NML" in line.upper():
                        in_point_nml = True
                    if in_point_nml and re.match(r'^\s*/\s*$', line) and not line.strip().startswith("!"):
                        insert_index = i
                        break
                if insert_index > 0:
                    new_lines.insert(insert_index, f"  POINT%TIMESPLIT        =  {timesplit_value}\n")

            if modified_start or modified_stride or modified_split or modified_spectra_type:
                with open(ww3_ounp_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                if modified_start and modified_stride:
                    log_msg = tr("step4_ww3_ounp_updated", "✅ 已修改 ww3_ounp.nml：POINT%TIMESTART = '{start}'，POINT%TIMESTRIDE = '{stride}'（谱空间逐点计算模式）").format(
                        start=f"{start_date} 000000", stride=output_precision
                    )
                elif modified_start:
                    log_msg = tr("step4_ww3_ounp_start_only", "✅ 已修改 ww3_ounp.nml：POINT%TIMESTART = '{start}'（谱空间逐点计算模式）").format(
                        start=f"{start_date} 000000"
                    )
                elif modified_stride:
                    log_msg = tr("step4_ww3_ounp_stride_only", "✅ 已修改 ww3_ounp.nml：POINT%TIMESTRIDE = '{stride}'（谱空间逐点计算模式）").format(
                        stride=output_precision
                    )
                else:
                    log_msg = tr("step4_ww3_ounp_timesplit_only", "✅ 已修改 ww3_ounp.nml：POINT%TIMESPLIT = {split}（谱空间逐点计算模式）").format(
                        split=timesplit_value
                    )
                self.log(log_msg)

        except Exception as e:
            self.log(tr("ww3_ounp_modify_error", "❌ 修改 ww3_ounp.nml 时出错：{error}").format(error=str(e)))
