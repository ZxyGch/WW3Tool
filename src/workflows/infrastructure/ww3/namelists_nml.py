"""namelists.nml 修改 Mixin — E3D 谱分区标志与谱点模式联动。

当用户启用二维谱点计算或输出方案包含 EF 变量时，将 ``&OUTS`` 块中的 ``E3D``
设为 1，并联动修改 ``ww3_shel.nml`` 中的 ``TYPE%POINT%FILE``、``DATE%POINT`` 等项。
支持普通网格与嵌套网格（level0…levelN 子目录）两种布局。

[EN] namelists.nml modification Mixin — E3D spectral partition flag and spectral
point mode linkage.

When the user enables spectral point-by-point computation or the output scheme
contains EF variables, ``E3D`` in the ``&OUTS`` block is set to 1, and related
items in ``ww3_shel.nml`` such as ``TYPE%POINT%FILE``, ``DATE%POINT`` etc. are
updated accordingly. Supports both normal grid and nested grid (level0…levelN
subdirectory) layouts.
"""
from __future__ import annotations

import os
import re

from ...support.translations import tr
from .nml_log_format import Assignment, format_nml_log_message
from .nml_primitives import NMLPrimitives
from .smc_open_boundary import BUNDY_FILENAME, count_smc_bundy_points, read_smc_n_levels
from .smc_ww3_version import normalize_psmc_namelist_lines, resolve_ww3_version


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
        grid_type = getattr(self, 'grid_type_var', tr("step1_grid_type_normal", "普通网格"))
        nested_text = tr("step1_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")

        if is_nested_grid:
            from .nested_level_dirs import list_nested_level_paths

            for level_dir in list_nested_level_paths(self.selected_folder):
                self._modify_namelists_e3d_in_dir(str(level_dir))
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

        if not is_nested_grid:
            self._modify_ww3_shel_point_file(silent=True)
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
                with open(namelists_path, "w", encoding="utf-8", newline="\n") as f:
                    f.writelines(new_lines)
                self.log(
                    format_nml_log_message(
                        "step4_namelists_e3d_updated",
                        "✅ 已修改 namelists.nml：\n{details}",
                        [("E3D", "1")],
                    )
                )
                return True
            return False

        except Exception as e:
            self.log(tr("namelists_modify_error", "❌ 修改 namelists.nml 时出错：{error}").format(error=str(e)))
            return False

    def _normalize_smc_psmc_namelist_in_dir(self, target_dir: str) -> bool:
        """按 ``ww3.version`` 将 ``&PSMC`` 字段名对齐到 6.07 或 7.14 约定。

        [EN] Align ``&PSMC`` field names to the 6.07 or 7.14 convention
        according to ``ww3.version``.
        """
        namelists_path = os.path.join(target_dir, "namelists.nml")
        if not os.path.isfile(namelists_path):
            return False

        ww3_version = resolve_ww3_version(work_dir=target_dir)
        try:
            with open(namelists_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            new_lines, modified = normalize_psmc_namelist_lines(
                lines, ww3_version=ww3_version
            )
            if not modified:
                return False
            with open(namelists_path, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(new_lines)
            self.log(
                tr(
                    "step4_namelists_smc_psmc_normalized",
                    "✅ 已按 WW3 {ver} 规范化 namelists.nml &PSMC 字段名",
                ).format(ver=ww3_version)
            )
            return True
        except Exception as e:
            self.log(
                tr(
                    "step4_namelists_smc_psmc_normalize_failed",
                    "⚠️ 规范化 namelists.nml &PSMC 失败：{err}",
                ).format(err=e)
            )
            return False

    def _sync_smc_psmc_namelist_if_needed(self) -> None:
        """Regional SMC runs: sync ``&PSMC`` ``NBISMC`` / ``LvSMC`` from grid outputs."""
        if not getattr(self, "_is_step1_smc_mesh", lambda: False)():
            return
        self._normalize_smc_psmc_namelist_in_dir(self.selected_folder)
        self._sync_smc_psmc_namelist_in_dir(self.selected_folder)

    def _sync_smc_psmc_namelist_in_dir(self, target_dir: str) -> bool:
        """Set ``&PSMC`` ``NBISMC`` and ``LvSMC`` in ``namelists.nml`` for SMC open boundaries."""
        namelists_path = os.path.join(target_dir, "namelists.nml")
        if not os.path.isfile(namelists_path):
            return False

        nbismc = count_smc_bundy_points(target_dir)
        n_levels = read_smc_n_levels(target_dir)
        if n_levels is None:
            return False

        try:
            with open(namelists_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines: list[str] = []
            modified = False
            in_psmc = False
            for line in lines:
                stripped = line.lstrip()
                is_comment = stripped.startswith("!")

                if not is_comment and re.match(r"^\s*&PSMC\b", line, re.IGNORECASE):
                    in_psmc = True
                    new_lines.append(line)
                    continue

                if in_psmc and not is_comment:
                    updated = line
                    if re.search(r"^\s*NBISMC\s*=", line, re.IGNORECASE):
                        updated, n = re.subn(
                            r"^(\s*NBISMC\s*=\s*)\d+",
                            rf"\g<1>{nbismc}",
                            line,
                            count=1,
                            flags=re.IGNORECASE,
                        )
                        modified = modified or n > 0
                    if n_levels is not None and re.search(r"^\s*LvSMC\s*=", line, re.IGNORECASE):
                        updated, n = re.subn(
                            r"^(\s*LvSMC\s*=\s*)\d+",
                            rf"\g<1>{int(n_levels)}",
                            updated,
                            count=1,
                            flags=re.IGNORECASE,
                        )
                        modified = modified or n > 0
                    new_lines.append(updated)
                    if re.match(r"^\s*/\s*$", line):
                        in_psmc = False
                    continue

                new_lines.append(line)

            if not modified:
                return False

            with open(namelists_path, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(new_lines)

            psmc_assignments: list[Assignment] = [
                (
                    "NBISMC",
                    f"{nbismc} ({BUNDY_FILENAME})" if nbismc > 0 else str(nbismc),
                ),
                ("LvSMC", str(int(n_levels))),
            ]
            self.log(
                format_nml_log_message(
                    "step4_namelists_smc_psmc_updated",
                    "✅ 已修改 namelists.nml：\n{details}",
                    psmc_assignments,
                )
            )
            return True
        except Exception as e:
            self.log(
                tr(
                    "step4_namelists_smc_psmc_failed",
                    "⚠️ 修改 namelists.nml &PSMC 失败：{err}",
                ).format(err=e)
            )
            return False
