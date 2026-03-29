"""
第五步：本地运行模块
包含本地运行相关的 UI 和逻辑
"""
import os
import glob
import shutil
import subprocess
import threading
import signal

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QFileDialog
from qfluentwidgets import PrimaryPushButton, LineEdit
from setting.language_manager import tr
from setting.config import WW3BIN_PATH
from .utils import create_header_card


class HomeLocalRun:
    """第五步：本地运行 Mixin"""
    
    def create_step_5_card(self, content_widget, content_layout):
        """创建第五步：本地运行的UI"""
        # 使用通用函数创建卡片（需要保存引用以便控制可见性）
        step5_card, step5_card_layout = create_header_card(
            content_widget,
            tr("step5_local_title", "本地运行")
        )
        self.step5_card = step5_card  # 保存引用以便控制可见性

        # 如果 WW3 bin 路径为空，隐藏本地运行部分
        if not WW3BIN_PATH or not WW3BIN_PATH.strip():
            step5_card.setVisible(False)

        # 输入框样式：使用主题适配的样式
        input_style = self._get_input_style()

        # 按钮样式：使用主题适配的样式
        button_style = self._get_button_style()

        # WW3 bin 路径选择
        bin_row_layout = QHBoxLayout()
        bin_row_layout.addWidget(QLabel(tr("step5_ww3bin_path", "WW3 bin 路径:")))
        self.ww3_bin_edit = LineEdit()
        self.ww3_bin_edit.setText(WW3BIN_PATH)
        self.ww3_bin_edit.setStyleSheet(input_style)
        bin_row_layout.addWidget(self.ww3_bin_edit, 1)  # 占满剩余宽度
        btn_choose_bin = PrimaryPushButton(tr("select", "选择"))
        btn_choose_bin.setStyleSheet(button_style)
        btn_choose_bin.clicked.connect(self.choose_bin_folder)
        bin_row_layout.addWidget(btn_choose_bin)
        step5_card_layout.addLayout(bin_row_layout)

        # 本地运行（grid/prnc/strt/shel）按钮
        btn_local_run = PrimaryPushButton(tr("step5_local_run", "本地运行"))
        btn_local_run.setStyleSheet(button_style)
        btn_local_run.clicked.connect(self.run_local_ww3)
        step5_card_layout.addWidget(btn_local_run)
        self.local_run_button = btn_local_run  # 保存引用以便禁用/启用

        # 停止 ww3_shel 按钮
        btn_stop_shel = PrimaryPushButton(tr("step5_stop_shel", "停止执行"))
        btn_stop_shel.setStyleSheet(button_style)
        btn_stop_shel.clicked.connect(self.stop_local_shel)
        step5_card_layout.addWidget(btn_stop_shel)

        # 设置内容区内边距
        step5_card.viewLayout.setContentsMargins(11, 10, 11, 12)
        step5_card.viewLayout.addLayout(step5_card_layout)
        content_layout.addWidget(step5_card)

    def choose_bin_folder(self):
        """选择 WW3 bin 文件夹"""
        start_path = self.ww3_bin_edit.text().strip() if hasattr(self, 'ww3_bin_edit') and self.ww3_bin_edit else WW3BIN_PATH
        if not start_path or not os.path.exists(start_path):
            start_path = os.path.expanduser("~")

        # 规范化起始路径
        start_path = os.path.normpath(start_path)

        folder = QFileDialog.getExistingDirectory(
            self,
            tr("step5_choose_ww3bin", "选择 WW3 bin 目录"),
            start_path,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
        )

        if folder:
            # 规范化返回的路径
            folder = os.path.normpath(folder)
            if hasattr(self, 'ww3_bin_edit') and self.ww3_bin_edit:
                self.ww3_bin_edit.setText(folder)
            self.log(tr("step5_ww3bin_selected", "✅ 已选择 WW3 bin 目录：{folder}").format(folder=folder))

    def run_local_ww3(self):
        """执行本地 WW3 运行（grid/prnc/strt/shel）"""
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return

        bin_dir = ''
        try:
            bin_dir = self.ww3_bin_edit.text().strip()
        except Exception:
            bin_dir = ''

        # 进入运行状态，禁用按钮
        self._set_local_run_button_running()

        # 在后台线程中执行
        threading.Thread(target=self._run_local_ww3_internal, args=(bin_dir,), daemon=True).start()

    def _run_local_ww3_internal(self, bin_dir):
        """内部执行本地 WW3 运行（在后台线程中调用）"""
        self._local_run_proc = None
        try:
            # 获取本地脚本路径：优先使用当前工作目录的 local.sh
            local_script_path = os.path.normpath(os.path.join(self.selected_folder, "local.sh"))
            if not os.path.exists(local_script_path):
                # __file__ 是 main/home/home_local_run.py，需要回到项目根目录
                script_dir = os.path.dirname(os.path.abspath(__file__))  # main/home
                main_dir = os.path.dirname(script_dir)  # main
                project_root = os.path.dirname(main_dir)  # 项目根目录
                local_script_path = os.path.normpath(os.path.join(project_root, "public", "ww3", "local.sh"))
            
            if not os.path.exists(local_script_path):
                self.log_signal.emit(tr("step5_local_script_not_found", "❌ 找不到本地脚本：{path}").format(path=local_script_path))
                return

            self.log_signal.emit(tr("step5_local_run_start", "▶️ 开始执行本地 WW3 运行..."))
            
            # 设置环境变量
            env = os.environ.copy()
            if bin_dir:
                env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
            
            # 执行脚本（新会话使 bash 为进程组组长，停止时可一次 killpg 结束 mpirun/ww3_* 整树）
            proc = subprocess.Popen(
                ["bash", local_script_path],
                cwd=self.selected_folder,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=0,
                env=env,
                close_fds=True,
                start_new_session=True,
            )
            self._local_run_proc = proc

            # 读取输出
            try:
                for line in iter(proc.stdout.readline, ''):
                    if not line:
                        break
                    line_stripped = line.rstrip()
                    if line_stripped:
                        self.log_signal.emit(line_stripped)
            except Exception as e:
                self.log_signal.emit(tr("step5_output_read_failed", "⚠️ 输出读取失败：{error}").format(error=e))
            
            ret = proc.wait()
            if ret == 0:
                self.log_signal.emit(tr("step5_local_run_completed", "✅ 本地 WW3 运行已完成"))
            else:
                self.log_signal.emit(tr("step5_local_run_failed", "❌ 本地 WW3 运行失败（返回码 {code}）").format(code=ret))
        except FileNotFoundError:
            self.log_signal.emit(tr("step5_bash_not_found", "❌ 找不到 bash 命令，无法执行脚本"))
        except Exception as e:
            self.log_signal.emit(tr("step5_local_run_error", "❌ 本地 WW3 运行出错：{error}").format(error=e))
        finally:
            self._local_run_proc = None
            QtCore.QTimer.singleShot(0, self._restore_local_run_button)

    @QtCore.pyqtSlot()
    def _set_local_run_button_running(self):
        """进入本地运行中状态，禁用按钮并更新文本"""
        try:
            if hasattr(self, "local_run_button") and self.local_run_button:
                self.local_run_button.setEnabled(False)
                self.local_run_button.setText(tr("step5_local_running", "运行中..."))
        except Exception:
            pass

    @QtCore.pyqtSlot()
    def _restore_local_run_button(self):
        """恢复本地运行按钮状态"""
        try:
            if hasattr(self, "local_run_button") and self.local_run_button:
                self.local_run_button.setEnabled(True)
                self.local_run_button.setText(tr("step5_local_run", "本地运行"))
        except Exception:
            pass

    def run_local_ounf(self):
        """执行 ww3_ounf 或 ww3_ounp（根据计算模式）"""
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return

        # 根据计算模式决定执行哪个命令
        calc_mode = getattr(self, 'calc_mode_var', '区域尺度计算')
        if calc_mode == "谱空间逐点计算":
            # 检查输出文件
            outs = glob.glob(os.path.join(self.selected_folder, "out_pnt.ww3"))
            if not outs:
                outs = glob.glob(os.path.join(self.selected_folder, "out_grd.ww3"))
                if not outs:
                    self.log(tr("step5_output_files_missing_point_or_grid", "❌ 当前文件夹未找到输出文件：out_pnt.ww3 或 out_grd.ww3"))
                    return
        else:
            outs = glob.glob(os.path.join(self.selected_folder, "out_grd.ww3"))
            if not outs:
                self.log(tr("step5_output_file_missing_grid", "❌ 当前文件夹未找到输出文件：out_grd.ww3"))
                return

        bin_dir = ''
        try:
            bin_dir = self.ww3_bin_edit.text().strip()
        except Exception:
            bin_dir = ''

        if calc_mode == "谱空间逐点计算":
            threading.Thread(target=self._run_ounp_and_ounf_internal, args=(bin_dir,), daemon=True).start()
        else:
            threading.Thread(target=self._run_ounf_internal, args=(bin_dir,), daemon=True).start()

    def _run_ounf_internal(self, bin_dir):
        """内部执行 ww3_ounf（在后台线程中调用）"""
        try:
            outs = glob.glob(os.path.join(self.selected_folder, "out_grd.ww3"))
            if not outs:
                self.log_signal.emit(tr("step5_skip_ounf_no_out_grd", "❌ 未找到输出文件 out_grd.ww3，跳过 ww3_ounf"))
                return

            ounf_cmd = os.path.join(bin_dir, "ww3_ounf") if bin_dir else "ww3_ounf"
            use_abs = bin_dir and os.path.isfile(ounf_cmd) and os.access(ounf_cmd, os.X_OK)
            self.log_signal.emit(tr("step5_ounf_start", "▶️ 开始执行：ww3_ounf"))

            try:
                env = os.environ.copy()
                if bin_dir:
                    env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
                proc = subprocess.Popen(
                    [ounf_cmd] if use_abs else ["ww3_ounf"],
                    cwd=self.selected_folder,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=0,
                    env=env,
                    close_fds=True,
                    start_new_session=True
                )
            except FileNotFoundError:
                self.log_signal.emit(tr("step5_ounf_command_not_found", "❌ 找不到命令：ww3_ounf，请在上方填写 WW3 bin 路径或设置 PATH"))
                return
            except Exception as e:
                self.log_signal.emit(tr("step5_ounf_start_failed", "❌ 启动 ww3_ounf 失败：{error}").format(error=e))
                return

            # 读取输出
            try:
                for line in iter(proc.stdout.readline, ''):
                    if not line:
                        break
                    line_stripped = line.rstrip()
                    if line_stripped:
                        self.log_signal.emit(line_stripped)
            except Exception as e:
                self.log_signal.emit(tr("step5_output_read_failed", "⚠️ 输出读取失败：{error}").format(error=e))

            ret = proc.wait()
            if ret == 0:
                self.log_signal.emit(tr("step5_ounf_completed", "✅ ww3_ounf 已完成，输出文件已生成"))
            else:
                self.log_signal.emit(tr("step5_ounf_failed", "❌ ww3_ounf 失败（返回码 {code}）").format(code=ret))
        except Exception as e:
            self.log_signal.emit(tr("step5_ounf_error", "❌ ww3_ounf 执行出错：{error}").format(error=e))

    def _run_ounp_internal(self, bin_dir):
        """内部执行 ww3_ounp（在后台线程中调用，用于谱空间逐点计算模式）"""
        try:
            # 检查输出文件（谱空间逐点计算模式可能使用不同的输出文件）
            # 但通常还是需要 out_grd.ww3 或 out_pnt.ww3
            outs = glob.glob(os.path.join(self.selected_folder, "out_pnt.ww3"))
            if not outs:
                # 如果没有 out_pnt.ww3，检查 out_grd.ww3
                outs = glob.glob(os.path.join(self.selected_folder, "out_grd.ww3"))
            if not outs:
                self.log_signal.emit(tr("step5_skip_ounp_no_out", "❌ 未找到输出文件 out_pnt.ww3 或 out_grd.ww3，跳过 ww3_ounp"))
                return

            ounp_cmd = os.path.join(bin_dir, "ww3_ounp") if bin_dir else "ww3_ounp"
            use_abs = bin_dir and os.path.isfile(ounp_cmd) and os.access(ounp_cmd, os.X_OK)
            self.log_signal.emit(tr("step5_ounp_start", "▶️ 开始执行：ww3_ounp"))

            env = os.environ.copy()
            if bin_dir:
                env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
            proc = subprocess.Popen(
                [ounp_cmd] if use_abs else ["ww3_ounp"],
                cwd=self.selected_folder,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=0,
                env=env,
                close_fds=True,
                start_new_session=True
            )

            # 读取输出
            try:
                for line in iter(proc.stdout.readline, ''):
                    if not line:
                        break
                    line_stripped = line.rstrip()
                    if line_stripped:
                        self.log_signal.emit(line_stripped)
            except Exception as e:
                self.log_signal.emit(tr("step5_output_read_failed", "⚠️ 输出读取失败：{error}").format(error=e))

            ret = proc.wait()
            if ret == 0:
                self.log_signal.emit(tr("step5_ounp_completed", "✅ ww3_ounp 已完成，输出文件已生成"))
            else:
                self.log_signal.emit(tr("step5_ounp_failed", "❌ ww3_ounp 失败（返回码 {code}）").format(code=ret))
        except FileNotFoundError:
            self.log_signal.emit(tr("step5_ounp_command_not_found", "❌ 找不到命令：ww3_ounp，请在上方填写 WW3 bin 路径或设置 PATH"))
        except Exception as e:
            self.log_signal.emit(tr("step5_ounp_error", "❌ ww3_ounp 执行出错：{error}").format(error=e))

    def _run_ounp_and_ounf_internal(self, bin_dir):
        """内部执行 ww3_ounp 和 ww3_ounf（在后台线程中调用，用于谱空间逐点计算模式）"""
        # 先执行 ww3_ounp
        self._run_ounp_internal(bin_dir)
        # 然后执行 ww3_ounf
        self.log_signal.emit("")
        self._run_ounf_internal(bin_dir)

    def _run_trnc_internal(self, bin_dir):
        """内部执行 ww3_trnc（在后台线程中调用，用于航迹模式）"""
        try:
            # 检查输出文件（航迹模式使用 out_grd.ww3）
            outs = glob.glob(os.path.join(self.selected_folder, "out_grd.ww3"))
            if not outs:
                self.log_signal.emit(tr("step5_skip_trnc_no_out", "❌ 未找到输出文件 out_grd.ww3，跳过 ww3_trnc"))
                return

            trnc_cmd = os.path.join(bin_dir, "ww3_trnc") if bin_dir else "ww3_trnc"
            use_abs = bin_dir and os.path.isfile(trnc_cmd) and os.access(trnc_cmd, os.X_OK)
            self.log_signal.emit(tr("step5_trnc_start", "▶️ 开始执行：ww3_trnc"))

            try:
                env = os.environ.copy()
                if bin_dir:
                    env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
                proc = subprocess.Popen(
                    [trnc_cmd] if use_abs else ["ww3_trnc"],
                    cwd=self.selected_folder,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=0,
                    env=env,
                    close_fds=True,
                    start_new_session=True
                )
            except FileNotFoundError:
                self.log_signal.emit(tr("step5_trnc_command_not_found", "❌ 找不到命令：ww3_trnc，请在上方填写 WW3 bin 路径或设置 PATH"))
                return
            except Exception as e:
                self.log_signal.emit(tr("step5_trnc_start_failed", "❌ 启动 ww3_trnc 失败：{error}").format(error=e))
                return

            # 读取输出
            try:
                for line in iter(proc.stdout.readline, ''):
                    if not line:
                        break
                    line_stripped = line.rstrip()
                    if line_stripped:
                        self.log_signal.emit(line_stripped)
            except Exception as e:
                self.log_signal.emit(tr("step5_output_read_failed", "⚠️ 输出读取失败：{error}").format(error=e))

            ret = proc.wait()
            if ret == 0:
                self.log_signal.emit(tr("step5_trnc_completed", "✅ ww3_trnc 已完成，输出文件已生成"))
            else:
                self.log_signal.emit(tr("step5_trnc_failed", "❌ ww3_trnc 失败（返回码 {code}）").format(code=ret))
        except Exception as e:
            self.log_signal.emit(tr("step5_trnc_error", "❌ ww3_trnc 执行出错：{error}").format(error=e))

    def stop_local_shel(self):
        """停止本地运行：优先终止 GUI 启动的 bash 进程组（含 mpirun / ww3_*），否则按进程名清理（兼容手工启动）。"""
        proc = getattr(self, "_local_run_proc", None)
        if proc is not None and proc.poll() is None:
            try:
                if hasattr(os, "killpg"):
                    pgrp = os.getpgid(proc.pid)
                    os.killpg(pgrp, signal.SIGTERM)
                    self.log(
                        tr(
                            "step5_terminate_local_group",
                            "🛑 已向本地运行进程组发送终止信号（PGID {pgid}，含 bash / mpirun / ww3 等）",
                        ).format(pgid=pgrp)
                    )
                    return
                proc.terminate()
                self.log(
                    tr(
                        "step5_terminate_local_proc",
                        "🛑 已向本地运行子进程发送终止信号（PID {pid}）",
                    ).format(pid=proc.pid)
                )
                return
            except ProcessLookupError:
                pass
            except Exception as e:
                self.log(
                    tr("step5_terminate_local_group_failed", "⚠️ 终止进程组失败：{error}，将尝试按进程名结束…").format(
                        error=e
                    )
                )

        # 检查是否是嵌套网格模式
        from .utils import HomeState
        is_nested_grid = HomeState.is_nested_grid()
        
        # 根据网格类型确定要停止的进程名
        if is_nested_grid:
            process_name = 'ww3_multi'
        else:
            process_name = 'ww3_shel'
        
        try:
            pk = shutil.which('pkill')
            ka = shutil.which('killall')
            if pk:
                try:
                    subprocess.run(['pkill', '-f', process_name])
                    self.log(tr("step5_terminate_signal", "🛑 已发送终止信号：{cmd}").format(cmd=f"pkill -f {process_name}"))
                    return
                except Exception:
                    pass
            if ka:
                try:
                    subprocess.run(['killall', process_name])
                    self.log(tr("step5_terminate_signal_cmd", "🛑 已尝试：{cmd}").format(cmd=f"killall {process_name}"))
                    return
                except Exception:
                    pass
            try:
                out = subprocess.run(['ps', 'ax'], stdout=subprocess.PIPE, text=True).stdout
                pids = []
                for line in out.splitlines():
                    if process_name in line:
                        pid_str = line.strip().split(None, 1)[0]
                        try:
                            pids.append(int(pid_str))
                        except Exception:
                            pass
                if not pids:
                    self.log(tr("step5_no_running_process", "ℹ️ 未找到正在运行的 {process} 进程").format(process=process_name))
                    return
                for pid in pids:
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except Exception:
                        pass
                self.log(tr("step5_terminate_signal_pids", "🛑 已发送终止信号给进程：{pids}").format(pids=pids))
            except Exception as e:
                self.log(f'⚠️ 停止 {process_name} 失败：{e}')
        except Exception as e:
            self.log(f'❌ 停止 {process_name} 出错：{e}')
