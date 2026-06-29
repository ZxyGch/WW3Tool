"""第四步：WW3 运行参数配置 — 业务逻辑 Mixin。

负责将 NML 模板文件复制到工作目录等第四步面板相关逻辑。
与 ``ModifyWW3NML`` 组合后构成完整的 WW3 配置流程。
"""
import os
import shutil

from ...support.translations import tr
from ..runtime_config import PUBLIC_DIR, get_nml_template_dir


class StepFourServiceMixin:
    """第四步 WW3 运行参数相关的业务逻辑 Mixin。

    主要公开方法
    ------------
    - ``copy_public_files`` — 将 NML 模板复制到当前工作目录。
  """

    def copy_public_files(self):
        """将 NML 模板目录下的文件复制到工作文件夹"""
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            self.log(tr("step4_workdir_missing", "❌ 当前工作目录不存在！"))
            return
        self._copy_public_files_to_dir(self.selected_folder)

    def _copy_public_files_to_dir(self, target_dir, grid_label=""):
        """将 NML 模板目录下的文件复制到指定目录"""
        if not target_dir or not isinstance(target_dir, str):
            return

        # 获取项目根目录下的 NML 模板路径
        src_dir = os.path.normpath(get_nml_template_dir())
        scripts_dir = os.path.normpath(os.path.join(PUBLIC_DIR, "scripts"))

        if not os.path.exists(src_dir):
            self.log(tr("step4_dir_not_found", "⚠️ 未找到目录：{path}").format(path=src_dir))
            return

        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        # 使用翻译函数检查是否为嵌套网格（支持中英文）
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")

        # 检查计算模式
        calc_mode = getattr(self, 'calc_mode_var', '')
        # 优先检查 calc_mode_combo 的当前选择（这是用户界面上的实际值）
        if hasattr(self, 'calc_mode_combo') and self.calc_mode_combo:
            combo_text = self.calc_mode_combo.currentText()
            if combo_text:
                calc_mode = combo_text

        spectral_text = tr("step3_spectral_point", "二维谱点计算")
        track_text = tr("step3_track_mode", "轨迹计算")
        is_spectral_mode = calc_mode in (spectral_text, "二维谱点计算", "谱空间逐点计算")
        is_track_mode = calc_mode in (track_text, "轨迹计算", "航迹模式")

        # 嵌套网格模式下需复制到工作目录（而非各 level 子目录）的特殊文件
        special_files = ["server.sh", "ww3_multi.nml"]

        # 根据模式决定需要跳过的文件
        skip_files = []
        # 如果不是嵌套网格模式，跳过 ww3_multi.nml
        if not is_nested_grid:
            skip_files.append("ww3_multi.nml")
        # 如果不是轨迹计算，跳过 ww3_trnc.nml
        if not is_track_mode:
            skip_files.append("ww3_trnc.nml")
        # 如果不是二维谱点计算模式，跳过 ww3_ounp.nml
        if not is_spectral_mode:
            skip_files.append("ww3_ounp.nml")
        # 嵌套网格：local.sh / ww3_shel.nml 仅用于普通单网格，不复制到各 level* 子目录
        if is_nested_grid:
            skip_files.append("local.sh")
            skip_files.append("ww3_shel.nml")

        try:
            # 遍历 public 目录下的文件并复制
            copied = 0
            for item in os.listdir(src_dir):
                src_path = os.path.join(src_dir, item)

                # 如果是嵌套网格模式且文件是特殊文件（ww3.slurm 或 ww3_multi.nml），跳过（已在公共文件处理中复制）
                if is_nested_grid and item in special_files:
                    continue  # 跳过特殊文件，它们已在 _copy_public_special_files_to_workdir 中处理

                # 根据模式跳过不需要的文件
                if item in skip_files:
                    continue

                # 确保是文件而不是目录
                if not os.path.isfile(src_path):
                    continue

                dst_path = os.path.join(target_dir, item)
                shutil.copy2(src_path, dst_path)
                copied += 1
            # 脚本(server.sh/local.sh)只在普通网格模式下随 NML 复制到工作目录；
            # 嵌套模式下脚本已由 _copy_public_special_files_to_workdir 统一复制一次，
            # 这里不再逐层重复拷贝、也不重复打日志。
            if not is_nested_grid:
                if os.path.isdir(scripts_dir):
                    script_copy_entries = []
                    for item in os.listdir(scripts_dir):
                        src_path = os.path.join(scripts_dir, item)
                        if not os.path.isfile(src_path):
                            continue
                        dst_path = os.path.join(target_dir, item)
                        shutil.copy2(src_path, dst_path)
                        if item in {"server.sh", "local.sh"}:
                            script_copy_entries.append(item)
                        if item.endswith(".sh"):
                            try:
                                os.chmod(dst_path, os.stat(dst_path).st_mode | 0o755)
                            except OSError:
                                pass
                    if script_copy_entries:
                        self.log(
                            tr("scripts_copied_to_workdir", "✅ 已复制 {entries} 到当前工作目录").format(
                                entries=", ".join(script_copy_entries)
                            )
                        )
                else:
                    self.log(tr("step4_dir_not_found", "⚠️ 未找到目录：{path}").format(path=scripts_dir))

            if copied > 0:
                prefix = ""
                # 嵌套网格模式下，特殊文件已在公共文件处理中复制，这里只显示其他文件
                self.log(f"{prefix}{tr('step4_files_copied', '✅ 已复制 {count} 个 NML 模板文件到当前工作目录').format(count=copied)}")
            else:
                self.log(tr("step4_no_files_to_copy", "⚠️ {path} 中没有可复制的文件。").format(path=src_dir))

        except Exception as e:
            self.log(tr("step4_copy_files_failed", "❌ 复制文件时出错：{error}").format(error=e))
