"""server.sh modifier mixin — SLURM job script configuration and ST version selection."""
from __future__ import annotations

import os
import re
import shutil

from ...support.translations import tr
from ..runtime_config import PUBLIC_DIR, get_nml_template_dir, load_full_config
from .nml_log_format import format_nml_log_message
from .nml_primitives import NMLPrimitives


def _st_executable_dir(path: str) -> str:
    """规范化配置中直接指定的 ST 可执行目录，不推断或补充子目录。"""
    return str(path or "").strip().rstrip("/\\")


def _slurm_nodelist_directive(value: str) -> str:
    nodes = [part.strip() for part in re.split(r"[\s,]+", str(value or "").strip()) if part.strip()]
    return ",".join(nodes)


class ServerSh(NMLPrimitives):
    """Mixin: server.sh and SLURM parameter operations."""

    def _server_sh_job_name(self, fallback) -> str:
        """Return a Slurm-safe job name, defaulting to the workdir name."""
        raw = str(getattr(self, "job_name_var", "") or "").strip()
        if not raw:
            raw = os.path.basename(str(getattr(self, "selected_folder", "") or "")) or str(fallback)
        return "_".join(raw.split())

    def modify_server_sh_file(self):
        """更新 server.sh 文件的具体实现

        [EN] Concrete implementation for updating the server.sh file.
        """
        start_date = self.shel_start_edit.text().strip()

        if not (start_date.isdigit() and len(start_date) == 8):
            self.log(tr("date_format_error", "❌ 起始日期格式错误，应为 YYYYMMDD。"))
            return

        # [EN] start YYYYMM, used only as the Slurm job-name fallback when none is set
        # 起始年月 YYYYMM，仅在未设置作业名时作为 Slurm -J 的回退值
        start_year_month = int(start_date[:6])
        job_name = self._server_sh_job_name(start_year_month)

        num_n = self.num_n_edit.text().strip()
        num_N = self.num_N_edit.text().strip()
        partition = self.partition_var
        mem = str(getattr(self, "mem_var", "") or "").strip()
        nodelist = _slurm_nodelist_directive(str(getattr(self, "nodelist_var", "") or ""))
        slurm_time = str(getattr(self, "time_var", "") or "").strip()

        # [EN] Get default template path for server.sh (prefer public/scripts/server.sh)
        # 获取 server.sh 的默认模板路径（优先使用 public/scripts/server.sh）
        server_script_path = os.path.normpath(os.path.join(PUBLIC_DIR, "scripts", "server.sh"))
        if not os.path.exists(server_script_path):
            server_script_path = os.path.normpath(os.path.join(get_nml_template_dir(), "server.sh"))

        # [EN] If server.sh is not in the working directory, copy it there
        # 如果 server.sh 不在工作目录，复制到工作目录
        workdir_server_sh = os.path.join(self.selected_folder, "server.sh")
        if not os.path.exists(workdir_server_sh):
            if os.path.exists(server_script_path):
                shutil.copy2(server_script_path, workdir_server_sh)
                self.log(
                    tr("scripts_copied_to_workdir", "✅ 已复制 {entries} 到当前工作目录").format(
                        entries="server.sh"
                    )
                )
            else:
                self.log(tr("server_sh_not_found", "❌ 未找到 server.sh 文件：{path}").format(path=server_script_path))
                return

        try:
            with open(workdir_server_sh, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # [EN] Get ST version info
            # 获取 ST 版本信息
            if not hasattr(self, 'st_var') or not self.st_var:
                self.log(tr("st_version_not_selected", "❌ 未选择 ST 版本，请在设置页面配置 ST 版本"))
                return

            selected_st = self.st_var

            # [EN] Find selected ST version path (prefer reading from PipelineConfig / params.yml)
            # 查找选中的 ST 版本路径（优先从 PipelineConfig / params.yml 读取）
            st_name = selected_st
            st_path = None

            slurm_cfg = getattr(getattr(self, '_loaded_config', None), 'slurm', None)
            if slurm_cfg and getattr(slurm_cfg, 'server_st_versions', None):
                st_path = slurm_cfg.server_st_versions.get(selected_st)

            if not st_path:
                # [EN] Fallback: read old format from config.json
                # 回退：从 config.json 读取旧格式
                current_config = load_full_config()
                st_versions = current_config.get("ST_VERSIONS", [])
                if st_versions and isinstance(st_versions, list):
                    for version in st_versions:
                        if isinstance(version, dict) and version.get("name") == selected_st:
                            st_path = version.get("path", "")
                            break

            if not st_path:
                self.log(tr("st_version_path_not_found", "❌ 未找到 ST 版本 {version} 的路径配置，请在设置页面配置 ST 版本路径").format(version=selected_st))
                return

            # [EN] Build ST version path line
            # 构建 ST 版本路径行
            st_path_line = _st_executable_dir(st_path)
            st_comment = f"#wavewatch3--{st_name}\n"
            st_export = f"export PATH={st_path_line}:$PATH\n"

            new_lines = []
            time_found = False
            mem_found = False
            nodelist_found = False
            st_path_inserted = False

            i = 0
            while i < len(lines):
                line = lines[i].replace('\r', '')  # [EN] Clean Windows line endings / 清理 Windows 换行符
                line_stripped = line.strip()

                # [EN] Modify SLURM configuration parameters
                # 修改 SLURM 配置参数
                if line_stripped.startswith("#SBATCH -J"):
                    new_lines.append(f"#SBATCH -J {job_name}\n")
                elif line_stripped.startswith("#SBATCH -p"):
                    new_lines.append(f"#SBATCH -p {partition}\n")
                elif line_stripped.startswith("#SBATCH -n"):
                    new_lines.append(f"#SBATCH -n {num_n}\n")
                elif line_stripped.startswith("#SBATCH -N"):
                    new_lines.append(f"#SBATCH -N {num_N}\n")
                elif line_stripped.startswith("#SBATCH -w") or line_stripped.startswith("#SBATCH --nodelist"):
                    nodelist_found = True
                    if nodelist:
                        new_lines.append(f"#SBATCH -w {nodelist}\n")
                    i += 1
                    continue
                elif line_stripped.startswith("#SBATCH --mem"):
                    if mem_found:
                        # 历史重复行：只保留第一处 --mem，其余丢弃
                        i += 1
                        continue
                    mem_found = True
                    if mem:
                        new_lines.append(f"#SBATCH --mem={mem}\n")
                    else:
                        new_lines.append(line)
                # [EN] Check if #SBATCH --time is found
                # 检查是否找到 #SBATCH --time
                elif line_stripped.startswith("#SBATCH --time"):
                    time_found = True
                    new_lines.append(f"#SBATCH --time={slurm_time}\n" if slurm_time else line)
                    # [EN] Skip subsequent blank lines and existing ST version paths
                    # 跳过后续的空行和已存在的 ST 版本路径
                    i += 1
                    while i < len(lines):
                        next_line = lines[i].replace('\r', '')
                        next_stripped = next_line.strip()
                        # [EN] Skip blank lines
                        # 跳过空行
                        if next_stripped == "":
                            i += 1
                            continue
                        # [EN] Skip existing ST version comments
                        # 跳过已存在的 ST 版本注释
                        if next_stripped.startswith("#wavewatch3--"):
                            i += 1
                            continue
                        # [EN] Skip existing export PATH (ST executable dir; confirm-slurm 只改这一行)
                        # 跳过已存在的 export PATH（仅 ST 可执行目录，不碰下方运行时库配置）
                        if next_stripped.startswith("export PATH="):
                            i += 1
                            continue
                        # [EN] Stop skipping on other content (keep WW3 运行时库 block in server.sh)
                        # 遇到其他内容，停止跳过（保留 server.sh 里手改的运行时库段）
                        break
                    # [EN] Add ST version path after #SBATCH --time
                    # 在 #SBATCH --time 后面添加 ST 版本路径
                    new_lines.append("\n")
                    new_lines.append(st_comment)
                    new_lines.append(st_export)
                    st_path_inserted = True
                    continue
                # [EN] If ST version path already inserted, skip subsequent old version paths
                # 如果已经插入了 ST 版本路径，跳过后续可能存在的旧版本路径
                elif st_path_inserted:
                    # [EN] Keep replacing runtime fields after the ST block is inserted.
                    # 保证插入 ST 路径后仍继续替换运行参数。
                    if line_stripped.startswith("MPI_NPROCS="):
                        new_lines.append(f"MPI_NPROCS={num_n}\n")
                        i += 1
                        continue
                    # [EN] Skip existing ST version comments (if not in correct position)
                    # 跳过已存在的 ST 版本注释（如果不在正确位置）
                    if line_stripped.startswith("#wavewatch3--"):
                        i += 1
                        continue
                    # [EN] Skip duplicate export PATH only (not runtime LD_LIBRARY_PATH block)
                    # 仅跳过重复的 ST export PATH，不修改运行时库段
                    if line_stripped.startswith("export PATH="):
                        i += 1
                        continue
                    new_lines.append(line)
                # [EN] Modify MPI_NPROCS
                # 修改 MPI_NPROCS
                elif line_stripped.startswith("MPI_NPROCS="):
                    new_lines.append(f"MPI_NPROCS={num_n}\n")
                else:
                    new_lines.append(line)
                i += 1

            # 模板无 --mem 时，在 -N 后补一行
            # [EN] If the template has no --mem, append one after -N.
            if mem and not mem_found:
                for idx, out_line in enumerate(new_lines):
                    if out_line.strip().startswith("#SBATCH -N"):
                        new_lines.insert(idx + 1, f"#SBATCH --mem={mem}\n")
                        mem_found = True
                        break
            if nodelist and not nodelist_found:
                insert_at = None
                for idx, out_line in enumerate(new_lines):
                    if out_line.strip().startswith("#SBATCH --mem"):
                        insert_at = idx + 1
                    elif insert_at is None and out_line.strip().startswith("#SBATCH -N"):
                        insert_at = idx + 1
                if insert_at is not None:
                    new_lines.insert(insert_at, f"#SBATCH -w {nodelist}\n")
            if slurm_time and not time_found:
                insert_at = None
                for idx, out_line in enumerate(new_lines):
                    stripped = out_line.strip()
                    if stripped.startswith("#SBATCH -w") or stripped.startswith("#SBATCH --mem"):
                        insert_at = idx + 1
                    elif insert_at is None and stripped.startswith("#SBATCH -N"):
                        insert_at = idx + 1
                if insert_at is not None:
                    new_lines.insert(insert_at, f"#SBATCH --time={slurm_time}\n")

            # [EN] Use binary mode when writing back to ensure \\n instead of \\r\\n
            # 写回文件时使用二进制模式，确保使用 \\n 而不是 \\r\\n
            with open(workdir_server_sh, 'wb') as f:
                content = ''.join(new_lines)
                content_bytes = content.encode('utf-8').replace(b'\r\n', b'\n').replace(b'\r', b'\n')
                f.write(content_bytes)

            mem_display = mem or "-"
            log_assignments = [
                ("#SBATCH -J", job_name),
                ("#SBATCH -p", partition),
                ("#SBATCH -n", num_n),
                ("#SBATCH -N", num_N),
                ("#SBATCH --mem", mem_display),
                ("#SBATCH -w", nodelist or "-"),
                ("#SBATCH --time", slurm_time or "-"),
                ("MPI_NPROCS", num_n),
                ("ST", st_name),
                ("export PATH", st_path_line),
            ]
            log_msg = format_nml_log_message(
                "step4_server_sh_updated",
                "✅ 已更新 server.sh：\n{details}",
                log_assignments,
            )

            self.log(log_msg)

        except Exception as e:
            self.log(tr("server_sh_modify_error", "❌ 修改 server.sh 出错: {error}").format(error=e))

    # [EN] ==================== ST version selection ====================
    # ==================== ST 版本选择 ====================
    def apply_st_choice(self):
        """应用 ST 版本选择

        [EN] Apply ST version selection.
        """
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return

        script_path = os.path.join(self.selected_folder, "run.sh")
        if not os.path.exists(script_path):
            self.log(tr("script_not_found", "❌ 未找到脚本：{path}").format(path=script_path))
            return

        def comment_line(s: str) -> str:
            t = s.lstrip()
            if not t.startswith("#"):
                return "#" + s
            return s

        def uncomment_line(s: str) -> str:
            i = 0
            while i < len(s) and s[i].isspace():
                i += 1
            if i < len(s) and s[i] == '#':
                i += 1
                if i < len(s) and s[i] == ' ':
                    i += 1
                return s[:0] + s[i:]
            return s

        try:
            with open(script_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # [EN] Dynamically build headers and path mapping from PipelineConfig / params.yml
            # 从 PipelineConfig / params.yml 动态构建 headers 和路径映射
            default_headers: dict[str, str] = {}
            default_base_map: dict[str, str] = {}

            selected = self.st_var
            base_dir = None
            headers = default_headers.copy()

            # [EN] Prefer reading ST version path from PipelineConfig / params.yml and dynamically build headers
            # 优先从 PipelineConfig / params.yml 读取 ST 版本路径和动态构建 headers
            slurm_cfg = getattr(getattr(self, '_loaded_config', None), 'slurm', None)
            if slurm_cfg and getattr(slurm_cfg, 'server_st_versions', None):
                base_dir = slurm_cfg.server_st_versions.get(selected)
                for st_name in slurm_cfg.server_st_versions:
                    headers[st_name] = f"#wavewatch3--{st_name}"

            if not base_dir:
                # [EN] Fallback: read old format from params.yml
                # 回退：从 params.yml 读取旧格式
                st_versions = load_full_config().get("ST_VERSIONS", [])
                if st_versions and isinstance(st_versions, list):
                    for version in st_versions:
                        if isinstance(version, dict) and version.get("name") == selected:
                            base_dir = version.get("path", "")
                            break

            if base_dir is None:
                base_dir = default_base_map.get(selected)

            # [EN] Handle ST version comment/uncomment
            # 处理 ST 版本的注释/取消注释
            if selected in headers:
                for st, header in headers.items():
                    idxs = [i for i, s in enumerate(lines) if s.strip().startswith(header)]
                    if not idxs:
                        continue
                    start = idxs[0] + 1
                    end = min(len(lines), start + 6)
                    for i in range(start, end):
                        s = lines[i]
                        if s.strip().startswith("#wavewatch3--ST"):
                            break
                        if not s.strip():
                            continue
                        if "export " in s:
                            if st == selected:
                                lines[i] = uncomment_line(s)
                            else:
                                lines[i] = comment_line(s)

            # [EN] Update executable file paths
            # 更新可执行文件路径
            if base_dir:
                executable_dir = _st_executable_dir(base_dir)
                exe_grid = f"{executable_dir}/ww3_grid\n"
                exe_prnc = f"{executable_dir}/ww3_prnc\n"
                for i, s in enumerate(lines):
                    st = s.strip()
                    if not st or st.startswith("#"):
                        continue
                    if "ww3_grid" in st:
                        lines[i] = exe_grid
                    if "ww3_prnc" in st:
                        lines[i] = exe_prnc

            with open(script_path, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(lines)

            self.log(tr("script_applied", "✅ 已应用 {selected} 到脚本：{path}").format(selected=selected, path=script_path))

        except Exception as e:
            self.log(tr("script_modify_failed", "❌ 修改脚本失败：{error}").format(error=e))
