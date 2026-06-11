"""ww3_trnc.nml 修改 Mixin — 航迹模式配置与 track_i.ww3 生成。

在「航迹模式」下，根据用户航迹点表格生成 ``track_i.ww3`` 输入文件，并修改
``ww3_shel.nml`` 的 ``DATE%TRACK`` 与 ``ww3_trnc.nml`` 的航迹输出参数。
"""
from __future__ import annotations

import os
import re

from ...support.translations import tr
from .nml_primitives import NMLPrimitives


class WW3TrncNML(NMLPrimitives):
    """航迹模式相关操作的 Mixin 类。

    核心方法 ``_generate_track_i_ww3_file`` 从 GUI 表格导出航迹点；
    ``_modify_ww3_trnc_track`` 写入 trnc namelist 航迹输出配置。
    """

    def _generate_track_i_ww3_file(self):
        """生成 track_i.ww3 文件（航迹模式）"""
        if not hasattr(self, 'track_points_table'):
            return

        if not hasattr(self, 'selected_folder') or not self.selected_folder:
            return

        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")

        # 确定保存路径（嵌套网格模式保存到 fine 目录，普通网格保存到工作目录）
        if is_nested_grid:
            fine_dir = os.path.join(self.selected_folder, "fine")
            if not os.path.exists(fine_dir):
                os.makedirs(fine_dir, exist_ok=True)
            track_file_path = os.path.join(fine_dir, "track_i.ww3")
        else:
            track_file_path = os.path.join(self.selected_folder, "track_i.ww3")

        try:
            def _fmt_track_coord(v):
                s = f"{float(v):.8f}".rstrip("0").rstrip(".")
                if "." not in s:
                    s += ".0"
                return s

            # 读取表格数据（跳过表头行，列顺序：0-时间, 1-经度, 2-纬度, 3-名称）
            track_points = []
            for i in range(1, self.track_points_table.rowCount()):
                time_item = self.track_points_table.item(i, 0)
                lon_item = self.track_points_table.item(i, 1)
                lat_item = self.track_points_table.item(i, 2)
                name_item = self.track_points_table.item(i, 3)

                if time_item and lon_item and lat_item and name_item:
                    time_str = time_item.text().strip()
                    lon_str = lon_item.text().strip()
                    lat_str = lat_item.text().strip()
                    name = name_item.text().strip()

                    if time_str and lon_str and lat_str and name:
                        try:
                            # 验证经纬度
                            lon = float(lon_str)
                            lat = float(lat_str)

                            # 验证时间格式（应该是 YYYYMMDD HHMMSS）
                            if len(time_str) == 15 and ' ' in time_str:
                                date_part, time_part = time_str.split()
                                if len(date_part) == 8 and len(time_part) == 6:
                                    track_points.append({
                                        'datetime': time_str,
                                        'lon': lon,
                                        'lat': lat,
                                        'name': name
                                    })
                        except (ValueError, AttributeError):
                            continue

            if not track_points:
                self.log(tr("no_valid_track_points", "⚠️ 航迹模式表格中没有有效点位，未生成 track_i.ww3 文件"))
                return

            # 生成文件内容
            lines = ["WAVEWATCH III TRACK LOCATIONS DATA \n"]
            for point in track_points:
                # 格式：日期时间 经度 纬度 名称
                # 例如：20250103 000000   112.5   12.0    Track1
                line = (
                    f"{point['datetime']}   "
                    f"{_fmt_track_coord(point['lon'])}   "
                    f"{_fmt_track_coord(point['lat'])}    "
                    f"{point['name']}\n"
                )
                lines.append(line)

            # 写入文件
            with open(track_file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)

            self.log(tr("track_file_generated", "✅ 已生成 track_i.ww3 文件").format(path=track_file_path))
        except Exception as e:
            self.log(tr("track_file_generation_failed", "❌ 生成 track_i.ww3 文件失败：{error}").format(error=e))

    def _modify_ww3_trnc_track(self):
        """修改 ww3_trnc.nml，设置 TRACK%TIMESTART 和 TRACK%TIMESTRIDE（航迹模式）"""
        # 检查航迹点位表格是否存在且不为空
        if not hasattr(self, 'track_points_table'):
            return

        point_count = self.track_points_table.rowCount()
        if point_count <= 1:  # 只有表头，没有数据点
            return

        # 从表格中获取所有时间，找到最早的时间
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

        # 找到最早的时间
        times.sort()
        start_datetime = times[0]  # 格式：YYYYMMDD HHMMSS

        # 获取输出精度
        if not hasattr(self, 'output_precision_edit'):
            return

        output_precision = self.output_precision_edit.text().strip()
        if not output_precision.isdigit():
            self.log(tr("output_precision_error_skip_trnc", "❌ 输出精度必须为数字（秒），跳过 ww3_trnc.nml 修改"))
            return

        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")

        if is_nested_grid:
            # 嵌套网格模式：修改 fine 目录下的文件
            fine_dir = os.path.join(self.selected_folder, "fine")
            if os.path.isdir(fine_dir):
                self._modify_ww3_trnc_track_in_dir(fine_dir, start_datetime, output_precision)
        else:
            # 普通网格模式：修改工作目录下的文件
            self._modify_ww3_trnc_track_in_dir(self.selected_folder, start_datetime, output_precision)

    def _modify_ww3_trnc_track_in_dir(self, target_dir, start_datetime, output_precision):
        """在指定目录下修改 ww3_trnc.nml，设置 TRACK%TIMESTART 和 TRACK%TIMESTRIDE"""
        ww3_trnc_path = os.path.join(target_dir, "ww3_trnc.nml")
        if not os.path.exists(ww3_trnc_path):
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
            with open(ww3_trnc_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            modified = False
            in_track_nml = False
            found_track_nml = False
            timestart_modified = False
            timestride_modified = False
            timesplit_modified = False
            i = 0

            while i < len(lines):
                line = lines[i]

                # 检查是否为注释行（以 ! 开头，去除前导空格后）
                line_stripped = line.lstrip()
                is_comment = line_stripped.startswith('!')

                # 查找 &TRACK_NML 开始
                if "&TRACK_NML" in line:
                    found_track_nml = True
                    in_track_nml = True
                    new_lines.append(line)
                    i += 1
                    continue

                # 在 &TRACK_NML 块内查找 TRACK%TIMESTART 和 TRACK%TIMESTRIDE
                if in_track_nml:
                    # 如果找到结束标记 /，退出块
                    if "/" in line and not is_comment:
                        # 如果还没有修改过，在结束标记前添加
                        if not timestart_modified or not timestride_modified or not timesplit_modified:
                            if not timestart_modified:
                                new_lines.append(f"  TRACK%TIMESTART        =  '{start_datetime}'\n")
                                timestart_modified = True
                            if not timestride_modified:
                                new_lines.append(f"  TRACK%TIMESTRIDE       =  '{output_precision}'\n")
                                timestride_modified = True
                            if not timesplit_modified:
                                new_lines.append(f"  TRACK%TIMESPLIT        =  {timesplit_value}\n")
                                timesplit_modified = True
                            modified = True
                        new_lines.append(line)
                        in_track_nml = False
                        i += 1
                        continue

                    # 查找并替换 TRACK%TIMESTART
                    if not is_comment and re.search(r'TRACK%TIMESTART', line, re.IGNORECASE):
                        # 替换整行
                        new_lines.append(f"  TRACK%TIMESTART        =  '{start_datetime}'\n")
                        timestart_modified = True
                        modified = True
                        i += 1
                        continue

                    # 查找并替换 TRACK%TIMESTRIDE
                    if not is_comment and re.search(r'TRACK%TIMESTRIDE', line, re.IGNORECASE):
                        # 替换整行
                        new_lines.append(f"  TRACK%TIMESTRIDE       =  '{output_precision}'\n")
                        timestride_modified = True
                        modified = True
                        i += 1
                        continue

                    # 查找并替换 TRACK%TIMESPLIT
                    if not is_comment and re.search(r'TRACK%TIMESPLIT', line, re.IGNORECASE):
                        new_lines.append(f"  TRACK%TIMESPLIT        =  {timesplit_value}\n")
                        timesplit_modified = True
                        modified = True
                        i += 1
                        continue

                    new_lines.append(line)
                else:
                    new_lines.append(line)

                i += 1

            if modified:
                with open(ww3_trnc_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                self.log(tr("step4_ww3_trnc_track_updated", "✅ 已修改 ww3_trnc.nml：TRACK%TIMESTART = '{start}', TRACK%TIMESTRIDE = '{stride}'").format(start=start_datetime, stride=output_precision))

        except Exception as e:
            self.log(tr("ww3_trnc_modify_error", "❌ 修改 ww3_trnc.nml 时出错：{error}").format(error=str(e)))
