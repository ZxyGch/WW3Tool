"""namelists.nml 修改 Mixin — E3D 谱分区标志与谱点模式联动。

当用户启用谱空间逐点计算或输出方案包含 EF 变量时，将 ``&OUTS`` 块中的 ``E3D``
设为 1，并联动修改 ``ww3_shel.nml`` 中的 ``TYPE%POINT%FILE``、``DATE%POINT`` 等项。
支持普通网格与嵌套网格（coarse/fine 子目录）两种布局。

[EN] namelists.nml modification Mixin — E3D spectral partition flag and spectral
point mode linkage.

When the user enables spectral point-by-point computation or the output scheme
contains EF variables, ``E3D`` in the ``&OUTS`` block is set to 1, and related
items in ``ww3_shel.nml`` such as ``TYPE%POINT%FILE``, ``DATE%POINT`` etc. are
updated accordingly. Supports both normal grid and nested grid (coarse/fine
subdirectory) layouts.
"""
from __future__ import annotations

import os
import re

from ...support.translations import tr
from .nml_primitives import NMLPrimitives


class NamelistsNML(NMLPrimitives):
    """``namelists.nml`` 相关操作的 Mixin 类。

    主要方法
    --------
    - ``_modify_namelists_e3d_if_needed`` — 根据计算模式与输出方案决定是否启用 E3D。
    - ``_modify_namelists_e3d_in_dir`` — 在指定目录将 ``&OUTS`` 块内 ``E3D`` 设为 1。

    [EN] Mixin class for ``namelists.nml`` related operations.

    Main methods
    ------------
    - ``_modify_namelists_e3d_if_needed`` — Decide whether to enable E3D based on
      computation mode and output scheme.
    - ``_modify_namelists_e3d_in_dir`` — Set ``E3D`` to 1 within the ``&OUTS`` block
      in the specified directory.
    """

    def _modify_namelists_e3d_if_needed(self):
        """如果需要，修改 namelists.nml 中的 E3D 参数（支持嵌套网格模式）

        [EN] If needed, modify the E3D parameter in namelists.nml
        (supports nested grid mode).
        """
        spectral_point_mode = self._is_spectral_point_mode()
        has_spectral_points = (
            spectral_point_mode
            and hasattr(self, 'spectral_points_table')
            and self.spectral_points_table.rowCount() > 1
        )
        output_scheme_has_ef = self._output_scheme_contains_var("EF")

        if not has_spectral_points and not output_scheme_has_ef:
            return

        # [EN] Check if nested grid mode
        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")

        if is_nested_grid:
            # [EN] Nested grid mode: modify files in coarse and fine directories
            # 嵌套网格模式：修改 coarse 和 fine 目录下的文件
            coarse_dir = os.path.join(self.selected_folder, "coarse")
            fine_dir = os.path.join(self.selected_folder, "fine")

            if os.path.isdir(coarse_dir):
                self._modify_namelists_e3d_in_dir(coarse_dir)
            if os.path.isdir(fine_dir):
                self._modify_namelists_e3d_in_dir(fine_dir)
        else:
            # [EN] Normal grid mode: modify files in the working directory
            # 普通网格模式：修改工作目录下的文件
            self._modify_namelists_e3d_in_dir(self.selected_folder)

        if not has_spectral_points:
            return

        # [EN] Export point list to points.list file (normal grid mode)
        # 导出点列表到 points.list 文件（普通网格模式）
        if not is_nested_grid:
            self._export_points_to_file()

        # [EN] Also modify ww3_shel.nml, adding TYPE%POINT%FILE (supports nested grid mode)
        # Note: In normal grid mode, logs for these modifications are merged in _modify_ww3_shel_times_to_dir
        # In nested grid mode, logs for these modifications are merged in their respective _modify_ww3_shel_times_to_dir
        # So we need to decide whether to use silent mode based on grid type
        # 同时修改 ww3_shel.nml，添加 TYPE%POINT%FILE（支持嵌套网格模式）
        # 注意：在普通网格模式下，这些修改的日志会在 _modify_ww3_shel_times_to_dir 中合并输出
        # 在嵌套网格模式下，这些修改的日志会在各自的 _modify_ww3_shel_times_to_dir 中合并输出
        # 所以这里需要根据网格类型决定是否使用 silent 模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")

        # [EN] In normal grid mode, use silent=True because logs will be merged in _modify_ww3_shel_times_to_dir
        # In nested grid mode, these methods handle their own logs (they don't call _modify_ww3_shel_times_to_dir)
        # But actually, in nested grid mode these modifications are handled in _apply_spectral_params_to_dir,
        # which also calls _modify_ww3_shel_times_to_dir
        # So uniformly use silent=True, letting _modify_ww3_shel_times_to_dir output merged logs
        # 在普通网格模式下，使用 silent=True，因为日志会在后续的 _modify_ww3_shel_times_to_dir 中合并输出
        # 在嵌套网格模式下，这些方法会自己处理日志输出（因为它们不会调用 _modify_ww3_shel_times_to_dir）
        # 但实际上，嵌套网格模式下这些修改是在 _apply_spectral_params_to_dir 中处理的，那里也会调用 _modify_ww3_shel_times_to_dir
        # 所以统一使用 silent=True，让 _modify_ww3_shel_times_to_dir 统一输出合并的日志
        self._modify_ww3_shel_point_file(silent=True)

        # [EN] Modify ww3_shel.nml, adding DATE%POINT and DATE%BOUNDARY (supports nested grid mode)
        # 修改 ww3_shel.nml，添加 DATE%POINT 和 DATE%BOUNDARY（支持嵌套网格模式）
        self._modify_ww3_shel_date_point(silent=True)

    def _modify_namelists_e3d_in_dir(self, target_dir):
        """在指定目录下修改 namelists.nml 中的 E3D 参数

        [EN] Modify the E3D parameter in namelists.nml under the specified directory.
        """
        namelists_path = os.path.join(target_dir, "namelists.nml")
        if not os.path.exists(namelists_path):
            return False

        try:
            with open(namelists_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            modified = False
            in_outs_block = False
            for line in lines:
                stripped = line.lstrip()
                is_comment = stripped.startswith('!')

                if not is_comment and re.match(r'^\s*&OUTS\b', line, re.IGNORECASE):
                    in_outs_block = True
                    new_lines.append(line)
                    continue

                if in_outs_block and not is_comment:
                    updated_line, replace_count = re.subn(
                        r'^(\s*E3D\s*=\s*)\d+(\s*,.*)?$',
                        r'\g<1>1\2',
                        line,
                        count=1,
                        flags=re.IGNORECASE,
                    )
                    if replace_count > 0:
                        new_lines.append(updated_line)
                        modified = (updated_line != line) or modified
                        continue

                    if re.match(r'^\s*/\s*$', line):
                        in_outs_block = False

                new_lines.append(line)

            if modified:
                with open(namelists_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                self.log(tr("step4_namelists_e3d_updated", "✅ 已修改 namelists.nml：将 &OUTS 中的 E3D 设为 1"))
                return True
            return False

        except Exception as e:
            self.log(tr("namelists_modify_error", "❌ 修改 namelists.nml 时出错：{error}").format(error=str(e)))
            return False
