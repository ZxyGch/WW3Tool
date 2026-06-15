"""server.sh modifier mixin — SLURM job script configuration and ST version selection."""
from __future__ import annotations

import os
import re
import shutil

from ...support.translations import tr
from ..runtime_config import PUBLIC_DIR, load_full_config
from .nml_primitives import NMLPrimitives


def _st_executable_dir(path: str) -> str:
    """规范化配置中直接指定的 ST 可执行目录，不推断或补充子目录。"""
    return str(path or "").strip().rstrip("/\\")


class ServerSh(NMLPrimitives):
    """Mixin: server.sh and SLURM parameter operations."""

    def _load_slurm_params_from_server_sh(self):
        """从工作目录中的 server.sh 文件读取 slurm 参数并设置到 UI

        [EN] Read SLURM parameters from the server.sh file in the working directory
        and set them in the UI.
        """
        if not hasattr(self, 'selected_folder') or not self.selected_folder:
            return

        # [EN] Prevent duplicate execution: check if the same parameters have already been loaded
        # 防止重复执行：检查是否已经加载过相同的参数
        server_sh_path = os.path.join(self.selected_folder, "server.sh")
        if not os.path.exists(server_sh_path):
            return

        # [EN] Use file modification time as marker to avoid duplicate loading
        # 使用文件修改时间作为标记，避免重复加载
        if not hasattr(self, '_last_server_sh_mtime'):
            self._last_server_sh_mtime = {}

        try:
            current_mtime = os.path.getmtime(server_sh_path)
            if server_sh_path in self._last_server_sh_mtime:
                if self._last_server_sh_mtime[server_sh_path] == current_mtime:
                    # [EN] File not modified, skip
                    # 文件未修改，跳过
                    return
            self._last_server_sh_mtime[server_sh_path] = current_mtime
        except:
            pass

        try:
            with open(server_sh_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # [EN] Parse SLURM parameters
            # 解析 slurm 参数
            cpu = None
            num_n = None
            num_N = None
            st_version = None

            for line in lines:
                line_stripped = line.strip()
                # [EN] Parse CPU/partition: #SBATCH -p CPU6240R
                # 解析 CPU/partition: #SBATCH -p CPU6240R
                if line_stripped.startswith("#SBATCH -p"):
                    parts = line_stripped.split()
                    # parts = ['#SBATCH', '-p', 'CPU6240R']
                    if len(parts) >= 3:
                        cpu = parts[2]
                # [EN] Parse total core count: #SBATCH -n 48
                # 解析总核数: #SBATCH -n 48
                elif line_stripped.startswith("#SBATCH -n"):
                    parts = line_stripped.split()
                    # parts = ['#SBATCH', '-n', '48']
                    if len(parts) >= 3:
                        num_n = parts[2]
                # [EN] Parse node count: #SBATCH -N 1
                # 解析节点数: #SBATCH -N 1
                elif line_stripped.startswith("#SBATCH -N"):
                    parts = line_stripped.split()
                    # parts = ['#SBATCH', '-N', '1']
                    if len(parts) >= 3:
                        num_N = parts[2]
                # [EN] Parse ST version: #wavewatch3--ST6A
                # 解析 ST 版本: #wavewatch3--ST6A
                elif line_stripped.startswith("#wavewatch3--"):
                    # [EN] Extract ST version name, e.g. "#wavewatch3--ST6A" -> "ST6A"
                    # 提取 ST 版本名称，例如 "#wavewatch3--ST6A" -> "ST6A"
                    st_version = line_stripped.replace("#wavewatch3--", "").strip()

            # [EN] Update SLURM parameters in the UI
            # 更新 UI 中的 slurm 参数
            updated = False
            if cpu and hasattr(self, 'cpu_combo') and self.cpu_combo:
                # [EN] Check if CPU is in the option list
                # 检查 CPU 是否在选项列表中
                items = [self.cpu_combo.itemText(i) for i in range(self.cpu_combo.count())]
                if cpu in items:
                    self.cpu_combo.setCurrentText(cpu)
                    self.cpu_var = cpu
                    updated = True

            if num_n and hasattr(self, 'num_n_edit') and self.num_n_edit:
                self.num_n_edit.setText(num_n)
                updated = True

            if num_N and hasattr(self, 'num_N_edit') and self.num_N_edit:
                self.num_N_edit.setText(num_N)
                updated = True

            # [EN] Update ST version
            # 更新 ST 版本
            if st_version and hasattr(self, 'st_combo') and self.st_combo:
                # [EN] Check if ST version is in the option list
                # 检查 ST 版本是否在选项列表中
                items = [self.st_combo.itemText(i) for i in range(self.st_combo.count())]
                if st_version in items:
                    self.st_combo.setCurrentText(st_version)
                    self.st_var = st_version
                    updated = True

            # [EN] Check if nested grid mode
            # 检查是否为嵌套网格模式
            coarse_dir = os.path.join(self.selected_folder, "coarse")
            fine_dir = os.path.join(self.selected_folder, "fine")
            is_nested_grid = (os.path.isdir(coarse_dir) and os.path.isdir(fine_dir))

            if is_nested_grid:
                # [EN] Nested grid mode: read precision values for outer and inner grids separately
                # 嵌套网格模式：分别读取外网格和内网格的精度值
                # [EN] Read output precision and compute precision for outer grid (coarse)
                # 读取外网格（coarse）的输出精度和计算精度
                coarse_output_precision = None
                coarse_compute_precision = None
                coarse_ounf_path = os.path.join(coarse_dir, "ww3_ounf.nml")
                coarse_shel_path = os.path.join(coarse_dir, "ww3_shel.nml")

                if os.path.exists(coarse_ounf_path):
                    try:
                        with open(coarse_ounf_path, "r", encoding="utf-8") as f:
                            ounf_lines = f.readlines()
                        for line in ounf_lines:
                            line_stripped = line.strip()
                            if line_stripped.startswith("!") or line_stripped.startswith("#"):
                                continue
                            if "FIELD%TIMESTRIDE" in line and "=" in line:
                                match = re.search(r"FIELD%TIMESTRIDE\s*=\s*['\"](\d+)['\"]", line, re.IGNORECASE)
                                if match:
                                    coarse_output_precision = match.group(1)
                                    break
                    except:
                        pass

                if os.path.exists(coarse_shel_path):
                    try:
                        with open(coarse_shel_path, "r", encoding="utf-8") as f:
                            shel_lines = f.readlines()
                        for line in shel_lines:
                            line_stripped = line.strip()
                            if line_stripped.startswith("!") or line_stripped.startswith("#"):
                                continue
                            if "DATE%FIELD" in line and "=" in line:
                                match = re.search(r"DATE%FIELD\s*=\s*['\"](\d{8})\s+\d{6}['\"]\s+['\"](\d+)['\"]\s+['\"](\d{8})\s+\d{6}['\"]", line, re.IGNORECASE)
                                if match:
                                    # [EN] Use outer grid start date
                                    start_date = match.group(1)  # 使用外网格的起始日期
                                    coarse_compute_precision = match.group(2)
                                    # [EN] Use outer grid end date
                                    end_date = match.group(3)  # 使用外网格的结束日期
                                    break
                    except:
                        pass

                # [EN] Read output precision and compute precision for inner grid (fine)
                # 读取内网格（fine）的输出精度和计算精度
                fine_output_precision = None
                fine_compute_precision = None
                fine_ounf_path = os.path.join(fine_dir, "ww3_ounf.nml")
                fine_shel_path = os.path.join(fine_dir, "ww3_shel.nml")

                if os.path.exists(fine_ounf_path):
                    try:
                        with open(fine_ounf_path, "r", encoding="utf-8") as f:
                            ounf_lines = f.readlines()
                        for line in ounf_lines:
                            line_stripped = line.strip()
                            if line_stripped.startswith("!") or line_stripped.startswith("#"):
                                continue
                            if "FIELD%TIMESTRIDE" in line and "=" in line:
                                match = re.search(r"FIELD%TIMESTRIDE\s*=\s*['\"](\d+)['\"]", line, re.IGNORECASE)
                                if match:
                                    fine_output_precision = match.group(1)
                                    break
                    except:
                        pass

                if os.path.exists(fine_shel_path):
                    try:
                        with open(fine_shel_path, "r", encoding="utf-8") as f:
                            shel_lines = f.readlines()
                        for line in shel_lines:
                            line_stripped = line.strip()
                            if line_stripped.startswith("!") or line_stripped.startswith("#"):
                                continue
                            if "DATE%FIELD" in line and "=" in line:
                                match = re.search(r"DATE%FIELD\s*=\s*['\"](\d{8})\s+\d{6}['\"]\s+['\"](\d+)['\"]\s+['\"](\d{8})\s+\d{6}['\"]", line, re.IGNORECASE)
                                if match:
                                    # [EN] Inner grid date range is usually same as outer grid, but here only read compute precision
                                    # 内网格的日期范围通常与外网格相同，但这里只读取计算精度
                                    fine_compute_precision = match.group(2)
                                    break
                    except:
                        pass

                # [EN] Update outer grid output precision and compute precision
                # 更新外网格的输出精度和计算精度
                if coarse_output_precision and hasattr(self, 'output_precision_edit') and self.output_precision_edit:
                    self.output_precision_edit.setText(coarse_output_precision)
                    updated = True

                if coarse_compute_precision and hasattr(self, 'shel_step_edit') and self.shel_step_edit:
                    self.shel_step_edit.setText(coarse_compute_precision)
                    updated = True

                # [EN] Update inner grid output precision and compute precision
                # 更新内网格的输出精度和计算精度
                if fine_output_precision and hasattr(self, 'inner_output_precision_edit') and self.inner_output_precision_edit:
                    self.inner_output_precision_edit.setText(fine_output_precision)
                    updated = True

                if fine_compute_precision and hasattr(self, 'inner_shel_step_edit') and self.inner_shel_step_edit:
                    self.inner_shel_step_edit.setText(fine_compute_precision)
                    updated = True

                # [EN] Update start and end dates (using outer grid dates)
                # 更新起始和结束日期（使用外网格的日期）
                if start_date and hasattr(self, 'shel_start_edit') and self.shel_start_edit:
                    self.shel_start_edit.setText(start_date)
                    updated = True

                if end_date and hasattr(self, 'shel_end_edit') and self.shel_end_edit:
                    self.shel_end_edit.setText(end_date)
                    updated = True
            else:
                # [EN] Normal grid mode: read from working directory
                # 普通网格模式：从工作目录读取
                # [EN] Read ww3_ounf.nml to get output precision
                # 读取 ww3_ounf.nml 获取输出精度
                output_precision = None
                ounf_path = os.path.join(self.selected_folder, "ww3_ounf.nml")
                if os.path.exists(ounf_path):
                    try:
                        with open(ounf_path, "r", encoding="utf-8") as f:
                            ounf_lines = f.readlines()

                        for line in ounf_lines:
                            line_stripped = line.strip()
                            # [EN] Skip comment lines
                            # 跳过注释行
                            if line_stripped.startswith("!") or line_stripped.startswith("#"):
                                continue
                            # [EN] Parse FIELD%TIMESTRIDE = '3600'
                            # 解析 FIELD%TIMESTRIDE = '3600'
                            if "FIELD%TIMESTRIDE" in line and "=" in line:
                                # [EN] Use regex to extract value in quotes
                                # 使用正则表达式提取引号中的值
                                match = re.search(r"FIELD%TIMESTRIDE\s*=\s*['\"](\d+)['\"]", line, re.IGNORECASE)
                                if match:
                                    output_precision = match.group(1)
                                    break
                    except:
                        pass

                # [EN] Read ww3_shel.nml to get compute precision and time range
                # 读取 ww3_shel.nml 获取计算精度和时间范围
                compute_precision = None
                start_date = None
                end_date = None
                shel_path = os.path.join(self.selected_folder, "ww3_shel.nml")
                if os.path.exists(shel_path):
                    try:
                        with open(shel_path, "r", encoding="utf-8") as f:
                            shel_lines = f.readlines()

                        for line in shel_lines:
                            line_stripped = line.strip()
                            # [EN] Skip comment lines
                            # 跳过注释行
                            if line_stripped.startswith("!") or line_stripped.startswith("#"):
                                continue
                            # [EN] Parse DATE%FIELD = '20250103 000000' '1800' '20250105 235959'
                            # 解析 DATE%FIELD = '20250103 000000' '1800' '20250105 235959'
                            if "DATE%FIELD" in line and "=" in line:
                                # [EN] Match format: DATE%FIELD = '20250103 000000' '1800' '20250105 235959'
                                # 匹配格式：DATE%FIELD = '20250103 000000' '1800' '20250105 235959'
                                match = re.search(r"DATE%FIELD\s*=\s*['\"](\d{8})\s+\d{6}['\"]\s+['\"](\d+)['\"]\s+['\"](\d{8})\s+\d{6}['\"]", line, re.IGNORECASE)
                                if match:
                                    start_date = match.group(1)  # '20250103'
                                    compute_precision = match.group(2)  # '1800'
                                    end_date = match.group(3)  # '20250105'
                                    break
                    except:
                        pass

                # [EN] Update output precision
                # 更新输出精度
                if output_precision and hasattr(self, 'output_precision_edit') and self.output_precision_edit:
                    self.output_precision_edit.setText(output_precision)
                    updated = True

                # [EN] Update compute precision
                # 更新计算精度
                if compute_precision and hasattr(self, 'shel_step_edit') and self.shel_step_edit:
                    self.shel_step_edit.setText(compute_precision)
                    updated = True

                # [EN] Update start date
                # 更新起始日期
                if start_date and hasattr(self, 'shel_start_edit') and self.shel_start_edit:
                    self.shel_start_edit.setText(start_date)
                    updated = True

                # [EN] Update end date
                # 更新结束日期
                if end_date and hasattr(self, 'shel_end_edit') and self.shel_end_edit:
                    self.shel_end_edit.setText(end_date)
                    updated = True

            if updated:
                st_info = f", {tr('step4_st_version_label', 'ST版本')}={st_version}" if st_version else ""
                ww3_info = ""
                if is_nested_grid:
                    # [EN] Nested grid mode: display inner/outer grid precision info
                    # 嵌套网格模式：显示内外网格的精度信息
                    ww3_parts = []
                    if coarse_output_precision:
                        ww3_parts.append(tr("step4_outer_output_precision_value", "外网格输出精度={precision}s").format(precision=coarse_output_precision))
                    if coarse_compute_precision:
                        ww3_parts.append(tr("step4_outer_compute_precision_value", "外网格计算精度={precision}s").format(precision=coarse_compute_precision))
                    if fine_output_precision:
                        ww3_parts.append(tr("step4_inner_output_precision_value", "内网格输出精度={precision}s").format(precision=fine_output_precision))
                    if fine_compute_precision:
                        ww3_parts.append(tr("step4_inner_compute_precision_value", "内网格计算精度={precision}s").format(precision=fine_compute_precision))
                    if start_date:
                        ww3_parts.append(tr("step4_start_date_value", "起始日期={date}").format(date=start_date))
                    if end_date:
                        ww3_parts.append(tr("step4_end_date_value", "结束日期={date}").format(date=end_date))
                    if ww3_parts:
                        ww3_info = f", {', '.join(ww3_parts)}"
                else:
                    # [EN] Normal grid mode: display normal precision info
                    # 普通网格模式：显示普通精度信息
                    if output_precision or compute_precision or start_date or end_date:
                        ww3_parts = []
                        if output_precision:
                            ww3_parts.append(tr("step4_output_precision_value", "输出精度={precision}s").format(precision=output_precision))
                        if compute_precision:
                            ww3_parts.append(tr("step4_compute_precision_value", "计算精度={precision}s").format(precision=compute_precision))
                        if start_date:
                            ww3_parts.append(tr("step4_start_date_value", "起始日期={date}").format(date=start_date))
                        if end_date:
                            ww3_parts.append(tr("step4_end_date_value", "结束日期={date}").format(date=end_date))
                        if ww3_parts:
                            ww3_info = f", {', '.join(ww3_parts)}"

                # self.log(tr("slurm_params_loaded_from_server_sh", "✅ 已从 server.sh 读取 slurm 参数：CPU={cpu}, 核数={cores}, 节点数={nodes}{st_info}{ww3_info}").format(
                #     cpu=cpu if cpu else tr("not_set", "未设置"),
                #     cores=num_n if num_n else tr("not_set", "未设置"),
                #     nodes=num_N if num_N else tr("not_set", "未设置"),
                #     st_info=st_info,
                #     ww3_info=ww3_info
                # ))

        except Exception as e:
            # [EN] Silent failure, do not display error log
            # 静默失败，不显示错误日志
            pass

    def modify_server_sh_file(self):
        """更新 server.sh 文件的具体实现

        [EN] Concrete implementation for updating the server.sh file.
        """
        start_date = self.shel_start_edit.text().strip()

        if not (start_date.isdigit() and len(start_date) == 8):
            self.log(tr("date_format_error", "❌ 起始日期格式错误，应为 YYYYMMDD。"))
            return

        # [EN] casename can only be like 202504, unknown reason
        # casename 只能是 202504 这样的，未知原因
        start_year_month = int(start_date[:6])

        num_n = self.num_n_edit.text().strip()
        num_N = self.num_N_edit.text().strip()
        cpu = self.cpu_var

        # [EN] Get default template path for server.sh (public/ww3/server.sh)
        # 获取 server.sh 的默认模板路径（public/ww3/server.sh）
        server_script_path = os.path.normpath(os.path.join(PUBLIC_DIR, "ww3", "server.sh"))

        # [EN] If server.sh is not in the working directory, copy it there
        # 如果 server.sh 不在工作目录，复制到工作目录
        workdir_server_sh = os.path.join(self.selected_folder, "server.sh")
        if not os.path.exists(workdir_server_sh):
            if os.path.exists(server_script_path):
                shutil.copy2(server_script_path, workdir_server_sh)
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

            presets_st = getattr(getattr(self, '_loaded_config', None), 'presets', None)
            if presets_st and hasattr(presets_st, 'st'):
                st_path = presets_st.st.get(selected_st)

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
            st_path_inserted = False

            i = 0
            while i < len(lines):
                line = lines[i].replace('\r', '')  # [EN] Clean Windows line endings / 清理 Windows 换行符
                line_stripped = line.strip()

                # [EN] Modify SLURM configuration parameters
                # 修改 SLURM 配置参数
                if line_stripped.startswith("#SBATCH -J"):
                    new_lines.append(f"#SBATCH -J {start_year_month}\n")
                elif line_stripped.startswith("#SBATCH -p"):
                    new_lines.append(f"#SBATCH -p {cpu}\n")
                elif line_stripped.startswith("#SBATCH -n"):
                    new_lines.append(f"#SBATCH -n {num_n}\n")
                elif line_stripped.startswith("#SBATCH -N"):
                    new_lines.append(f"#SBATCH -N {num_N}\n")
                # [EN] Check if #SBATCH --time is found
                # 检查是否找到 #SBATCH --time
                elif line_stripped.startswith("#SBATCH --time"):
                    time_found = True
                    new_lines.append(line)
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
                        # [EN] Skip existing export PATH (containing /model/exe or /model:)
                        # 跳过已存在的 export PATH（包含 /model/exe 或 /model: 的）
                        if next_stripped.startswith("export PATH=") and ("/model/exe" in next_line or "/model:" in next_line):
                            i += 1
                            continue
                        # [EN] Stop skipping on other content
                        # 遇到其他内容，停止跳过
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
                    # [EN] Skip existing ST version comments (if not in correct position)
                    # 跳过已存在的 ST 版本注释（如果不在正确位置）
                    if line_stripped.startswith("#wavewatch3--"):
                        i += 1
                        continue
                    # [EN] Skip existing export PATH (containing /model/exe or /model:, if not in correct position)
                    # 跳过已存在的 export PATH（包含 /model/exe 或 /model: 的，如果不在正确位置）
                    if line_stripped.startswith("export PATH=") and ("/model/exe" in line or "/model:" in line):
                        i += 1
                        continue
                    new_lines.append(line)
                # [EN] Modify MPI_NPROCS
                # 修改 MPI_NPROCS
                elif line_stripped.startswith("MPI_NPROCS="):
                    new_lines.append(f"MPI_NPROCS={num_n}\n")
                # [EN] Modify CASENAME
                # 修改 CASENAME
                elif line_stripped.startswith("CASENAME="):
                    new_lines.append(f"CASENAME={start_year_month}\n")
                else:
                    new_lines.append(line)
                i += 1

            # [EN] Use binary mode when writing back to ensure \\n instead of \\r\\n
            # 写回文件时使用二进制模式，确保使用 \\n 而不是 \\r\\n
            with open(workdir_server_sh, 'wb') as f:
                content = ''.join(new_lines)
                content_bytes = content.encode('utf-8').replace(b'\r\n', b'\n').replace(b'\r', b'\n')
                f.write(content_bytes)

            log_msg = tr("step4_server_sh_updated", "✅ 已更新 server.sh：-J={job}, -p={cpu}, -n={cores}, -N={nodes}, MPI_NPROCS={mpi_cores}, CASENAME={name}, ST={st}").format(
                job=start_year_month, cpu=cpu, cores=num_n, nodes=num_N, mpi_cores=num_n, name=start_year_month, st=st_name
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
            presets_st = getattr(getattr(self, '_loaded_config', None), 'presets', None)
            if presets_st and hasattr(presets_st, 'st'):
                base_dir = presets_st.st.get(selected)
                # [EN] Dynamically generate comment headers from configured ST versions
                # 从配置的 ST 版本动态生成 comment headers
                for st_name in presets_st.st:
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

            with open(script_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            self.log(tr("script_applied", "✅ 已应用 {selected} 到脚本：{path}").format(selected=selected, path=script_path))

        except Exception as e:
            self.log(tr("script_modify_failed", "❌ 修改脚本失败：{error}").format(error=e))
