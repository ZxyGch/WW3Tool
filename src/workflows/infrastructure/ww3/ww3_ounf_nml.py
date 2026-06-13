"""ww3_ounf.nml 修改 Mixin — 场输出时间步长与变量列表配置。

写入 ``FIELD%TIMESTART``、``FIELD%TIMESTRIDE``、``FIELD%TIMESPLIT`` 及
``FIELD%LIST``，使 WW3 场输出 NetCDF 的起止时间、输出间隔与文件分割策略
与用户界面设置一致。

[EN] ww3_ounf.nml modification Mixin — field output timestep and variable list
configuration.

Writes ``FIELD%TIMESTART``, ``FIELD%TIMESTRIDE``, ``FIELD%TIMESPLIT``, and
``FIELD%LIST`` so that the WW3 field output NetCDF start/end times, output
interval, and file splitting strategy are consistent with UI settings.
"""
from __future__ import annotations

import os
import re

from ...support.translations import tr
from ..runtime_config import load_full_config
from .nml_primitives import NMLPrimitives


class WW3OunfNML(NMLPrimitives):
    """``ww3_ounf.nml`` 相关操作的 Mixin 类。

    公开入口 ``apply_ww3_ounf`` 将 GUI 中的起始日期、输出精度及文件分割选项
    写入工作目录下的 ``ww3_ounf.nml``。

    [EN] Mixin class for ``ww3_ounf.nml`` related operations.

    Public entry ``apply_ww3_ounf`` writes the start date, output precision, and
    file splitting options from the GUI into ``ww3_ounf.nml`` in the working directory.
    """

    def _apply_ww3_ounf_to_dir(self, target_dir, output_precision, grid_label=""):
        """在指定目录中修改 ww3_ounf.nml

        [EN] Modify ww3_ounf.nml in the specified directory.
        """
        if not target_dir or not isinstance(target_dir, str):
            return

        nml_path = os.path.join(target_dir, "ww3_ounf.nml")
        if not os.path.exists(nml_path):
            self.log(tr("ww3_ounf_not_found", "⚠️ 未找到 ww3_ounf.nml 文件：{path}，跳过").format(path=nml_path))
            return

        start_date = self.shel_start_edit.text().strip()
        stride = output_precision

        if not (start_date.isdigit() and len(start_date) == 8):
            self.log(tr("date_format_error", "❌ 起始日期格式错误，应为 YYYYMMDD。"))
            return
        if not stride.isdigit():
            self.log(tr("timestep_must_be_number", "❌ 时间步长必须为数字（秒）。"))
            return

        # [EN] Read file split setting from configuration. The underlying layer only accepts
        # English enumerations: none/hour/day/month/year; UI translations are for display only.
        # 从配置中读取文件分割设置。底层只接受英文枚举：
        # none/hour/day/month/year；界面翻译仅用于显示。
        config = load_full_config()
        file_split = str(config.get("FILE_SPLIT", "year")).strip().lower()
        file_split_value_map = {"none": 0, "year": 4, "month": 6, "day": 8, "hour": 10}
        if file_split not in file_split_value_map:
            raise ValueError("FILE_SPLIT must be one of: none, hour, day, month, year")
        timesplit_value = file_split_value_map[file_split]

        try:
            with open(nml_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            timesplit_found = False
            for line in lines:
                # [EN] Check if comment line (starts with !, after stripping leading whitespace)
                # 检查是否为注释行（以 ! 开头，去除前导空格后）
                line_stripped = line.lstrip()
                is_comment = line_stripped.startswith('!')

                # [EN] Only replace non-comment lines
                # 只替换非注释行
                if not is_comment:
                    if "FIELD%TIMESTART" in line:
                        new_lines.append(f"  FIELD%TIMESTART        =  '{start_date} 000000'\n")
                        continue
                    if "FIELD%TIMESTRIDE" in line:
                        new_lines.append(f"  FIELD%TIMESTRIDE       =  '{stride}'\n")
                        continue
                    if "FIELD%TIMESPLIT" in line:
                        new_lines.append(f"  FIELD%TIMESPLIT        =  {timesplit_value}\n")
                        timesplit_found = True
                        continue
                new_lines.append(line)

            # [EN] If FIELD%TIMESPLIT does not exist, add it in the FIELD_NML block
            # 如果 FIELD%TIMESPLIT 不存在，要在 FIELD_NML 块中添加
            if not timesplit_found:
                # [EN] Find the end of the FIELD_NML block (/ line) and insert before it
                # 查找 FIELD_NML 块的结束位置（/ 行），在之前插入
                in_field_nml = False
                insert_index = -1
                for i, line in enumerate(new_lines):
                    if "&FIELD_NML" in line.upper():
                        in_field_nml = True
                    if in_field_nml and re.match(r'^\s*/\s*$', line) and not line.strip().startswith("!"):
                        insert_index = i
                        break

                if insert_index > 0:
                    # [EN] Insert FIELD%TIMESPLIT before /
                    # 在 / 之前插入 FIELD%TIMESPLIT
                    new_lines.insert(insert_index, f"  FIELD%TIMESPLIT        =  {timesplit_value}\n")

            with open(nml_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            prefix = f"{grid_label} " if grid_label else ""
            self.log(f"{prefix}{tr('step4_ww3_ounf_updated', '✅ 已更新 ww3_ounf.nml：FIELD%TIMESTART={start}，FIELD%TIMESTRIDE={stride}秒').format(start=start_date, stride=stride)}")

        except Exception as e:
            self.log(tr("ww3_ounf_modify_error", "❌ 修改 ww3_ounf.nml 出错: {error}").format(error=e))

    def apply_ww3_ounf(self):
        """修改 ww3_ounf.nml（普通网格模式）

        [EN] Modify ww3_ounf.nml (normal grid mode).
        """
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return
        self._apply_ww3_ounf_to_dir(self.selected_folder, self.output_precision_edit.text().strip())
