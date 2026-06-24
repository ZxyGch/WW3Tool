"""WW3 namelist 修改调度层。

``ModifyWW3NML`` 通过 Mixin 继承聚合各 namelist 修改职责，每个目标文件的修改
逻辑独立封装在同目录的 ``ww3_*_nml.py`` 或 ``server_sh.py`` 中。
本文件只保留顶层调度方法（``modify_ww3_file``、``apply_ww3_params`` 等）。

Mixin 文件与对应目标：

==============================  ===========================
``nml_primitives.py``           NML 行级文本操作辅助函数
``ww3_grid_nml.py``             ``ww3_grid.nml``
``ww3_shel_nml.py``             ``ww3_shel.nml``
``ww3_ounf_nml.py``             ``ww3_ounf.nml``
``ww3_prnc_nml.py``             ``ww3_prnc*.nml``
``ww3_ounp_nml.py``             ``ww3_ounp.nml``（谱点输出）
``ww3_trnc_nml.py``             ``ww3_trnc.nml``（航迹模式）
``namelists_nml.py``            ``namelists.nml``
``server_sh.py``                ``server.sh``
``ww3_multi_nml.py``            ``ww3_multi.nml``（嵌套网格）
==============================  ===========================

[EN] WW3 namelist modification dispatch layer.

``ModifyWW3NML`` aggregates namelist modification responsibilities via Mixin
inheritance; each target file's modification logic is independently encapsulated
in ``ww3_*_nml.py`` or ``server_sh.py`` in the same directory.
This file only retains top-level dispatch methods (``modify_ww3_file``,
``apply_ww3_params``, etc.).

Mixin files and their targets:

==============================  ===========================
``nml_primitives.py``           NML line-level text operation helpers
``ww3_grid_nml.py``             ``ww3_grid.nml``
``ww3_shel_nml.py``             ``ww3_shel.nml``
``ww3_ounf_nml.py``             ``ww3_ounf.nml``
``ww3_prnc_nml.py``             ``ww3_prnc*.nml``
``ww3_ounp_nml.py``             ``ww3_ounp.nml`` (spectral point output)
``ww3_trnc_nml.py``             ``ww3_trnc.nml`` (track mode)
``namelists_nml.py``            ``namelists.nml``
``server_sh.py``                ``server.sh``
``ww3_multi_nml.py``            ``ww3_multi.nml`` (nested grid)
==============================  ===========================
"""
from __future__ import annotations

import os
import shutil

from ..runtime_config import PUBLIC_DIR, get_nml_template_dir
from ...support.translations import tr
from .nml_primitives import NMLPrimitives
from .ww3_grid_nml import WW3GridNML
from .ww3_shel_nml import WW3ShelNML
from .ww3_ounf_nml import WW3OunfNML
from .ww3_prnc_nml import WW3PrncNML
from .ww3_ounp_nml import WW3OunpNML
from .ww3_trnc_nml import WW3TrncNML
from .namelists_nml import NamelistsNML
from .server_sh import ServerSh
from .ww3_multi_nml import WW3MultiNML


class ModifyWW3NML(
    WW3GridNML,
    WW3ShelNML,
    WW3OunfNML,
    WW3PrncNML,
    WW3OunpNML,
    WW3TrncNML,
    NamelistsNML,
    ServerSh,
    WW3MultiNML,
):
    """WW3 namelist 修改核心类（调度层）。

    各 Mixin 基类按职责提供具体实现；本类仅负责调度入口
    ``modify_ww3_file`` 以及共用的输出方案辅助函数。

    [EN] WW3 namelist modification core class (dispatch layer).

    Each Mixin base class provides specific implementations by responsibility;
    this class only manages the dispatch entry point ``modify_ww3_file`` and
    shared output scheme helper functions.
    """

    def _is_spectral_point_mode(self):
        """检查当前是否为谱空间逐点计算模式

        [EN] Check whether the current mode is spectral point-by-point computation.
        """
        calc_mode = getattr(self, 'calc_mode_var', tr("step3_region_scale", "区域尺度计算"))
        spectral_text = tr("step3_spectral_point", "谱空间逐点计算")
        return calc_mode == spectral_text or calc_mode == "谱空间逐点计算"

    def _validate_and_update_forcing_field_paths(self):
        """验证并更新强迫场文件路径，确保文件在新工作目录中

        [EN] Validate and update forcing field file paths, ensuring files exist
        in the new working directory.
        """
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            return
        
        # [EN] Check and update each forcing field file path
        # 检查并更新每个强迫场文件路径
        forcing_fields = {
            'selected_origin_file': ['wind'],
            'selected_current_file': ['current'],
            'selected_level_file': ['level'],
            'selected_ice_file': ['ice']
        }
        
        # [EN] Map attribute names to checkbox key names
        # 映射属性名到复选框键名
        attr_to_checkbox = {
            'selected_origin_file': 'wind',
            'selected_current_file': 'current',
            'selected_level_file': 'level',
            'selected_ice_file': 'ice'
        }
        
        abs_selected_folder = os.path.abspath(self.selected_folder)
        
        for attr_name, keywords in forcing_fields.items():
            if hasattr(self, attr_name) and getattr(self, attr_name):
                file_path = getattr(self, attr_name)
                
                # [EN] If file path exists, check if it is in the new working directory
                # 如果文件路径存在，检查是否在新工作目录中
                if os.path.exists(file_path):
                    abs_file_path = os.path.abspath(file_path)
                    # [EN] Use commonpath to check if file is in the new working directory
                    # 使用 commonpath 检查文件是否在新工作目录中
                    try:
                        common_path = os.path.commonpath([abs_file_path, abs_selected_folder])
                        if common_path != abs_selected_folder:
                            # [EN] File not in new working directory, try to find a file with the same name
                            # 文件不在新工作目录中，尝试在新工作目录中查找同名文件
                            file_name = os.path.basename(file_path)
                            new_file_path = os.path.join(self.selected_folder, file_name)
                            
                            if os.path.exists(new_file_path):
                                # [EN] Same-name file exists in new working directory, update path
                                # 新工作目录中有同名文件，更新路径
                                setattr(self, attr_name, new_file_path)
                            else:
                                # [EN] No same-name file, try to find files containing keywords
                                # 新工作目录中没有同名文件，尝试查找包含关键词的文件
                                found = False
                                import glob
                                for keyword in keywords:
                                    pattern = os.path.join(self.selected_folder, f"*{keyword}*.nc")
                                    matching_files = glob.glob(pattern)
                                    if matching_files:
                                        # [EN] Prefer files containing all keywords (multi-field coexisting files)
                                        # 优先选择包含所有关键词的文件（多场并存文件）
                                        best_match = None
                                        for match_file in matching_files:
                                            match_name = os.path.basename(match_file).lower()
                                            # [EN] If filename contains all keywords, prefer it
                                            # 如果文件名包含所有关键词，优先选择
                                            if all(kw.lower() in match_name for kw in keywords):
                                                best_match = match_file
                                                break
                                        # [EN] If no file with all keywords found, use the first match
                                        # 如果没有找到包含所有关键词的文件，使用第一个匹配的文件
                                        if not best_match and matching_files:
                                            best_match = matching_files[0]
                                        
                                        if best_match:
                                            setattr(self, attr_name, best_match)
                                            found = True
                                            break
                                
                                if not found:
                                    # [EN] No matching file found in new working directory, clear reference and uncheck checkbox
                                    # 新工作目录中没有找到对应的文件，清除引用并取消复选框
                                    setattr(self, attr_name, None)
                                    checkbox_key = attr_to_checkbox.get(attr_name)
                                    if checkbox_key and hasattr(self, 'forcing_field_checkboxes') and checkbox_key in self.forcing_field_checkboxes:
                                        checkbox = self.forcing_field_checkboxes[checkbox_key]['checkbox']
                                        checkbox.setChecked(False)
                    except ValueError:
                        # [EN] Paths not on same drive (Windows) or incomparable, clear reference
                        # 路径不在同一驱动器上（Windows）或无法比较，清除引用
                        setattr(self, attr_name, None)
                        checkbox_key = attr_to_checkbox.get(attr_name)
                        if checkbox_key and hasattr(self, 'forcing_field_checkboxes') and checkbox_key in self.forcing_field_checkboxes:
                            checkbox = self.forcing_field_checkboxes[checkbox_key]['checkbox']
                            checkbox.setChecked(False)
                else:
                    # [EN] File does not exist, try to find in new working directory
                    # 文件不存在，尝试在新工作目录中查找
                    file_name = os.path.basename(file_path) if isinstance(file_path, str) else None
                    if file_name:
                        new_file_path = os.path.join(self.selected_folder, file_name)
                        if os.path.exists(new_file_path):
                            setattr(self, attr_name, new_file_path)
                        else:
                            # [EN] Try to find files containing keywords
                            # 尝试查找包含关键词的文件
                            found = False
                            import glob
                            for keyword in keywords:
                                pattern = os.path.join(self.selected_folder, f"*{keyword}*.nc")
                                matching_files = glob.glob(pattern)
                                if matching_files:
                                    # [EN] Prefer files containing all keywords (multi-field coexisting files)
                                    # 优先选择包含所有关键词的文件（多场并存文件）
                                    best_match = None
                                    for match_file in matching_files:
                                        match_name = os.path.basename(match_file).lower()
                                        if all(kw.lower() in match_name for kw in keywords):
                                            best_match = match_file
                                            break
                                    if not best_match and matching_files:
                                        best_match = matching_files[0]
                                    
                                    if best_match:
                                        setattr(self, attr_name, best_match)
                                        found = True
                                        break
                            
                            if not found:
                                # [EN] No matching file found in new working directory, clear reference and uncheck checkbox
                                # 新工作目录中没有找到对应的文件，清除引用并取消复选框
                                setattr(self, attr_name, None)
                                checkbox_key = attr_to_checkbox.get(attr_name)
                                if checkbox_key and hasattr(self, 'forcing_field_checkboxes') and checkbox_key in self.forcing_field_checkboxes:
                                    checkbox = self.forcing_field_checkboxes[checkbox_key]['checkbox']
                                    checkbox.setChecked(False)
                    else:
                        # [EN] File path invalid, clear reference and uncheck checkbox
                        # 文件路径无效，清除引用并取消复选框
                        setattr(self, attr_name, None)
                        checkbox_key = attr_to_checkbox.get(attr_name)
                        if checkbox_key and hasattr(self, 'forcing_field_checkboxes') and checkbox_key in self.forcing_field_checkboxes:
                            checkbox = self.forcing_field_checkboxes[checkbox_key]['checkbox']
                            checkbox.setChecked(False)

    def modify_ww3_file(self):
        """应用所有参数（合并第四步和第五步的功能）

        [EN] Apply all parameters (merging Step 4 and Step 5 functionality).
        """
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return
        
        # [EN] Validate and update forcing field file paths (ensure files are in the new working directory)
        # 验证并更新强迫场文件路径（确保文件在新工作目录中）
        self._validate_and_update_forcing_field_paths()

        # [EN] Check if a spectral partition output scheme is selected (for subsequent log display)
        # 检查是否选择了谱分区输出方案（用于后续显示日志）
        has_output_scheme = self._get_output_scheme_var_list() is not None

        # [EN] Check if current computation mode is track mode
        # 检查当前计算模式是否为航迹模式
        is_track_mode = self._is_track_mode()

        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        if grid_type == nested_text or grid_type == "嵌套网格":
            # [EN] Nested grid mode: merge all operations, outer and inner grids each completed under one separator line
            # 嵌套网格模式：合并所有操作，外网格和内网格各自在一个分隔线下完成
            self._apply_all_params_nested(has_output_scheme)
        else:
            # [EN] Normal grid mode: process according to original workflow
            # 普通网格模式：按原流程处理
            # [EN] Copy files first (so subsequent modifications apply to working directory files)
            # 先复制文件（这样后续修改才能应用到工作目录的文件）
            self.copy_public_and_meta_to_grid()

            # [EN] After copying files, apply spectral partition output scheme to working directory
            # 在复制文件后，应用谱分区输出方案到工作目录
            applied_scheme = False
            if has_output_scheme:
                applied_scheme = self._apply_output_scheme_to_dir(self.selected_folder)
                if applied_scheme:
                    self.log(tr("output_scheme_applied", "✅ 已修改 ww3_shel，ww3_ounf 的谱分区输出方案"))
            
            # [EN] Update server.sh file
            # 更新 server.sh 文件
            self.modify_server_sh_file()
            # [EN] Check if namelists.nml E3D parameter needs modification
            # 检查是否需要修改 namelists.nml 中的 E3D 参数
            self._modify_namelists_e3d_if_needed()
            # [EN] Check if ww3_ounp.nml needs modification (spectral point-by-point computation mode)
            # 检查是否需要修改 ww3_ounp.nml（谱空间逐点计算模式）
            self._modify_ww3_ounp_if_needed()
            # [EN] Execute Step 5 functionality: apply WW3 parameters
            # 再执行第五步的功能：应用 WW3 参数
            self.apply_ww3_params()
            # [EN] Modify time range in ww3_prnc.nml
            # 修改 ww3_prnc.nml 中的时间范围
            self._modify_ww3_prnc_times()
            # [EN] Generate corresponding ww3_prnc_*.nml files based on selected forcing fields
            # 根据选择的强迫场生成对应的 ww3_prnc_*.nml 文件
            self._generate_forcing_field_prnc_files()
            # [EN] Modify INPUT%FORCING%* settings in ww3_shel.nml
            # 修改 ww3_shel.nml 中的 INPUT%FORCING%* 设置
            self._modify_ww3_shel_forcing_inputs()
        
        # [EN] After copying and applying parameters, if in track mode, generate track_i.ww3
        # 在复制和应用参数之后，如果是航迹模式，生成 track_i.ww3 并写航迹 namelist
        if is_track_mode:
            self._generate_track_i_ww3_file()
            nested_text = tr("step2_grid_type_nested", "嵌套网格")
            is_nested = grid_type in (nested_text, "嵌套网格")
            if is_nested:
                workdir_multi = os.path.join(self.selected_folder, "ww3_multi.nml")
                self._modify_ww3_multi_alldate_track(workdir_multi)
            else:
                self._modify_ww3_shel_date_track()
            self._modify_ww3_trnc_track()

    def copy_public_and_meta_to_grid(self):
        """复制 NML 模板并按网格类型初始化 ww3_grid.nml（普通网格专用入口）。

        嵌套网格时由 ``_apply_all_params_nested`` 接管，此处直接返回。
        普通网格流程：复制 public 文件 → 按非结构 / SMC / RECT 分支改写 ww3_grid.nml
        并同步 grid.meta 或设置 namelists.nml 标志位。

        [EN] Copy NML templates and initialize ww3_grid.nml by grid type
        (entry point for normal grids only).

        For nested grids, ``_apply_all_params_nested`` takes over; this method returns directly.
        Normal grid workflow: copy public files -> rewrite ww3_grid.nml by unstructured / SMC / RECT
        branch and sync grid.meta or set namelists.nml flags.
        """
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))

        # [EN] Nested grid mode: all operations done in _apply_all_params_nested, skip here
        # 嵌套网格模式：所有操作在 _apply_all_params_nested 中完成，这里跳过
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        if grid_type == nested_text or grid_type == "嵌套网格":
            return

        # [EN] Normal grid mode: copy files and sync meta (rewrite ww3_grid.nml / namelists.nml for unstructured grids)
        # 普通网格模式：复制文件并同步 meta（非结构网格则改写 ww3_grid.nml / namelists.nml）
        self.copy_public_files()
        if self._is_step2_unstructured_mesh():
            wgp = os.path.join(self.selected_folder, "ww3_grid.nml")
            self._transform_ww3_grid_nml_for_unstructured(wgp)
            nlp = os.path.join(self.selected_folder, "namelists.nml")
            self._set_namelists_misc_flagtr_zero(nlp)
            self.log(
                tr(
                    "step4_unst_nml_applied",
                    "✅ 非结构网格：已将 ww3_grid.nml 设为 UNST（RECT/DEPTH/MASK/OBST 已注释，UNST_NML 启用），namelists.nml 中 FLAGTR=0",
                )
            )
        elif self._is_step2_smc_mesh():
            wgp = os.path.join(self.selected_folder, "ww3_grid.nml")
            self._transform_ww3_grid_nml_for_smcc(wgp)
            self.log(
                tr(
                    "step4_smcc_nml_applied",
                    "✅ SMC 网格：已将 ww3_grid.nml 设为 SMCG（RECT/DEPTH/MASK/OBST 已注释，SMC_NML 启用；grid_cell / grid_subtr 由 smc_generator，ISIDE/JSIDE 见 README；边界/北极文件存在时写入 BUNDY/MBARC）",
                )
            )
            self._smc_warn_forcing_covers_ww3_rect(self.selected_folder, grid_label="")
        else:
            self._sync_grid_meta_to_grid_nml_in_dir(self.selected_folder)
            self._update_grid_closure_from_meta(self.selected_folder)

    def apply_ww3_params(self):
        """应用 WW3 运行参数（第五步的功能）

        [EN] Apply WW3 runtime parameters (Step 5 functionality).
        """
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))

        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        if grid_type == nested_text or grid_type == "嵌套网格":
            self._apply_ww3_params_nested()
        else:
            self._apply_ww3_params_normal()

    def _copy_public_special_files_to_workdir(self):
        """复制公共文件（server.sh、ww3_multi.nml、local.sh）到工作目录

        [EN] Copy public files (server.sh, ww3_multi.nml, local.sh) to working directory.
        """
        # [EN] Get the NML template directory
        # 获取 NML 模板目录路径
        src_dir = get_nml_template_dir()
        scripts_dir = os.path.join(PUBLIC_DIR, "scripts")
        if not os.path.exists(src_dir):
            self.log(tr("directory_not_found", "⚠️ 未找到目录：{path}").format(path=src_dir))
            return

        # [EN] Check if nested grid mode
        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")

        copied_files = []
        script_copy_entries = []

        try:
            # [EN] Copy server.sh (prefer public/scripts/server.sh)
            # 复制 server.sh（优先使用 public/scripts/server.sh）
            server_script_path = os.path.normpath(os.path.join(scripts_dir, "server.sh"))
            if not os.path.isfile(server_script_path):
                server_script_path = os.path.normpath(os.path.join(src_dir, "server.sh"))

            if os.path.isfile(server_script_path):
                dst_path = os.path.join(self.selected_folder, "server.sh")
                shutil.copy2(server_script_path, dst_path)
                script_copy_entries.append("server.sh")
                copied_files.append("server.sh")
                # [EN] Clean up \\r
                # 清理 \r
                try:
                    with open(dst_path, 'rb') as f:
                        content = f.read()
                    if b'\r' in content:
                        content = content.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
                        with open(dst_path, 'wb') as f:
                            f.write(content)
                except Exception as e:
                    self.log(tr("server_sh_cleanup_error", "⚠️ 清理 server.sh 的 \\r 时出错：{error}").format(error=e))
            else:
                self.log(tr("server_sh_not_found", "❌ 未找到 server.sh 文件：{path}").format(path=server_script_path))
            
            # [EN] Only copy ww3_multi.nml / local.sh in nested grid mode
            # 只有在嵌套网格模式下才复制 ww3_multi.nml / local.sh
            if is_nested_grid:
                multi_nml_path = os.path.join(src_dir, "ww3_multi.nml")
                if os.path.isfile(multi_nml_path):
                    dst_path = os.path.join(self.selected_folder, "ww3_multi.nml")
                    shutil.copy2(multi_nml_path, dst_path)
                    copied_files.append("ww3_multi.nml")

                local_sh_path = os.path.join(scripts_dir, "local.sh")
                if not os.path.isfile(local_sh_path):
                    local_sh_path = os.path.join(src_dir, "local.sh")
                if os.path.isfile(local_sh_path):
                    dst_path = os.path.join(self.selected_folder, "local.sh")
                    shutil.copy2(local_sh_path, dst_path)
                    script_copy_entries.append("local.sh")
                    copied_files.append("local.sh")

            if script_copy_entries:
                self.log(
                    tr("scripts_copied_to_workdir", "✅ 已复制 {entries} 到当前工作目录").format(
                        entries=", ".join(script_copy_entries)
                    )
                )
            if copied_files:
                files_str = ', '.join(copied_files)
                self.log(tr("step4_special_files_copied", "✅ 已复制 {files} 到当前工作目录").format(files=files_str))
        except Exception as e:
            self.log(tr("copy_public_files_error", "❌ 复制公共文件时出错：{error}").format(error=e))

    def _nested_level_dirs(self):
        """返回嵌套各层目录 [(dir_path, idx), ...]，按 level 序号排序。"""
        from .nested_level_dirs import list_nested_level_entries

        return [(str(path), idx) for path, idx in list_nested_level_entries(self.selected_folder)]

    def _output_stride(self):
        """全局输出步长（秒），统一用于 ww3_shel / ww3_ounp / ww3_ounf。"""
        return self.output_precision_edit.text().strip()

    def _apply_all_params_nested(self, has_output_scheme=False):
        """嵌套网格模式：对 level0…levelN 逐层完成全部操作（每层在一条分隔线下）。

        各层输出步统一使用全局 ww3.output_step；CFL 传播步按各层 dx 自动重算。

        [EN] Nested grid mode: process level0..levelN, each under one separator line.
        """
        level_dirs = self._nested_level_dirs()
        if not level_dirs:
            self.log(tr("nested_grid_folders_not_found",
                        "❌ 未找到 level* 网格目录，请先生成嵌套网格"))
            return
        output_stride = self._output_stride()

        # 公共文件（server.sh + ww3_multi.nml）
        self.log("")
        self.log("=" * 70)
        self.log(tr("step4_public_files_start", "🔄 【工作目录】开始处理公共文件..."))
        self._copy_public_special_files_to_workdir()
        self.modify_server_sh_file()
        workdir_multi_nml = os.path.join(self.selected_folder, "ww3_multi.nml")
        if os.path.exists(workdir_multi_nml):
            self._modify_ww3_multi_nml(workdir_multi_nml)
        else:
            self.log(tr("ww3_multi_not_found", "⚠️ 未找到工作目录中的 ww3_multi.nml：{path}，跳过修改").format(path=workdir_multi_nml))

        self._export_points_to_file()

        scheme_applied = False
        for dir_path, idx in level_dirs:
            self.log("")
            self.log("=" * 70)
            self.log(tr("step4_level_grid_start", "🔄 【level{idx}】开始处理网格...").format(idx=idx))

            self._copy_public_files_to_dir(dir_path, grid_label="")
            if has_output_scheme:
                scheme_applied = self._apply_output_scheme_to_dir(dir_path) or scheme_applied
            self._sync_grid_meta_to_grid_nml_in_dir(dir_path, grid_label="")
            self._update_grid_closure_from_meta(dir_path, grid_label="")
            self._apply_ww3_params_to_dir(dir_path, output_stride, grid_label="")
            self._modify_ww3_prnc_nml_for_nested(dir_path, grid_label="")
            self._modify_ww3_prnc_times_in_dir(dir_path, grid_label="")
            self._generate_forcing_field_prnc_files(dir_path, use_relative_path=True)
            self._modify_ww3_shel_forcing_inputs_in_dir(dir_path, grid_label="")
            self._apply_spectral_params_to_dir(dir_path, self.shel_start_edit.text().strip(),
                                              self.shel_end_edit.text().strip(), output_stride)
            self._apply_config_parameters_to_grid_nml_in_dir(dir_path, level_idx=idx)
            # 按各层自身 dx 与全局 FREQ1 重算 CFL 时间步（细网格 DTXY 更小）
            self._apply_cfl_timesteps_to_grid_nml(dir_path)

        if has_output_scheme and scheme_applied:
            self.log(tr("output_scheme_applied", "✅ 已修改 ww3_shel，ww3_ounf 的谱分区输出方案"))
        if self._is_step2_smc_mesh():
            self._smc_warn_forcing_covers_ww3_rect(self.selected_folder, grid_label="nested")

    def _apply_ww3_params_nested(self):
        """嵌套网格模式：对 level0…levelN 逐层应用 WW3 运行参数。

        [EN] Nested grid mode: apply parameters to level0..levelN.
        """
        level_dirs = self._nested_level_dirs()
        if not level_dirs:
            self.log(tr("nested_grid_folders_not_found",
                        "❌ 未找到 level* 网格目录，请先生成嵌套网格"))
            return
        output_stride = self._output_stride()
        for dir_path, idx in level_dirs:
            self.log("")
            self.log("=" * 70)
            self.log(tr("level_grid_params_start", "🔄 【level{idx}】开始应用网格参数...").format(idx=idx))
            self.log("=" * 70)
            self._apply_ww3_params_to_dir(dir_path, output_stride, grid_label="")
            self._modify_ww3_prnc_nml_for_nested(dir_path, grid_label="")

        # 修改 ww3_multi.nml
        workdir_multi_nml = os.path.join(self.selected_folder, "ww3_multi.nml")
        if os.path.exists(workdir_multi_nml):
            self._modify_ww3_multi_nml(workdir_multi_nml)
            if self._is_track_mode():
                self._modify_ww3_multi_alldate_track(workdir_multi_nml)
        else:
            self.log(tr("ww3_multi_not_found", "⚠️ 未找到工作目录中的 ww3_multi.nml：{path}，跳过修改").format(path=workdir_multi_nml))

    def _apply_ww3_params_normal(self):
        """普通网格模式：应用参数

        [EN] Normal grid mode: apply parameters.
        """
        # [EN] Apply ww3_ounf.nml
        # 应用 ww3_ounf.nml
        self.apply_ww3_ounf()
        # [EN] Modify ww3_shel.nml
        # 修改 ww3_shel.nml
        self.modify_ww3_shel_times()

    def _apply_ww3_params_to_dir(self, target_dir, output_precision, grid_label=""):
        """在指定目录中应用 WW3 运行参数

        [EN] Apply WW3 runtime parameters in the specified directory.
        """
        self._apply_ww3_ounf_to_dir(target_dir, output_precision, grid_label=grid_label)
        self._modify_ww3_shel_times_to_dir(target_dir, output_precision, grid_label=grid_label)

    def _get_output_scheme_var_list(self):
        """获取当前选择的谱分区输出方案变量列表字符串

        [EN] Get the variable list string of the currently selected spectral
        partition output scheme.
        """
        try:
            if not hasattr(self, 'output_scheme_combo') or not self.output_scheme_combo:
                return None
            scheme_name = self.output_scheme_combo.currentText().strip()
            if not scheme_name:
                return None

            # [EN] Prefer reading from PipelineConfig
            # 优先从 PipelineConfig 读取
            loaded_cfg = getattr(self, '_loaded_config', None)
            if loaded_cfg is not None and hasattr(loaded_cfg, 'presets'):
                schemes = dict(loaded_cfg.presets.output_scheme)
                # __params__ 是合成键，实际对应 ww3.output_scheme 指定的预设
                # [EN] __params__ is a synthetic key; resolve to the actual preset name
                if scheme_name == "__params__" and loaded_cfg.ww3.output_scheme in schemes:
                    scheme_name = loaded_cfg.ww3.output_scheme
            else:
                from ..runtime_config import load_full_config
                config = load_full_config()
                schemes = config.get("OUTPUT_VARS_SCHEMES", {})
            vars_list = schemes.get(scheme_name)
            if not vars_list:
                return None

            selected_vars = [str(v).strip() for v in vars_list if str(v).strip()]
            if not selected_vars:
                return None

            return ' '.join(selected_vars)
        except Exception:
            return None

    def _output_scheme_contains_var(self, target_var):
        """检查当前谱分区输出方案是否包含指定变量

        [EN] Check whether the current spectral partition output scheme contains
        the specified variable.
        """
        if not target_var:
            return False

        var_list_str = self._get_output_scheme_var_list()
        if not var_list_str:
            return False

        target = str(target_var).strip().upper()
        if not target:
            return False

        selected_vars = [item.strip().upper() for item in var_list_str.split() if item.strip()]
        return target in selected_vars
