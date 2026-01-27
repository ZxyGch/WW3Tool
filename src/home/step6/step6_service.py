"""
第六步：服务器操作模块 - 函数逻辑部分
包含所有业务逻辑函数（从 ui.py 拆分出来）
"""
import os
import threading
import paramiko
from PyQt6 import QtCore, QtWidgets
from qfluentwidgets import InfoBar, MessageBox
from setting.language_manager import tr
from setting.config import load_config


class StepSixFunctionsMixin:
    """第六步相关的函数逻辑 Mixin"""

    def _is_ssh_alive(self, ssh):
        """检查 SSH 连接是否存活"""
        try:
            if ssh is None:
                return False
            transport = ssh.get_transport()
            if transport is None:
                return False
            return transport.is_active()
        except Exception:
            return False

    def execute_remote_script(self, mode: str = "submit"):
        """复用全局 SSH 连接执行远程脚本（server.sh 或 export.sh）"""
        if self.ssh is None or not self._is_ssh_alive(self.ssh):
            self.log("⚠️ SSH 连接不存在或已断开，正在尝试重新连接...")
            try:
                if not self._last_conn_args:
                    self.log("❌ 无法重新连接：缺少连接信息")
                    return
                host, port, user, pwd = self._last_conn_args
                self.ssh = paramiko.SSHClient()
                self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                self.ssh.connect(
                    hostname=host,
                    port=port,
                    username=user,
                    password=pwd,
                    look_for_keys=False,
                    allow_agent=False,
                    timeout=15,
                    banner_timeout=200
                )
                self.log(f"✅ 已重新连接服务器 {host}:{port}")
            except Exception as e:
                self.log(f"❌ 无法重新连接服务器: {e}")
                return

        # 解析远程目录
        if not self._last_conn_args:
            self.log("❌ 执行失败：未检测到上次连接信息，请重新连接服务器。")
            return

        host, port, user, pwd = self._last_conn_args
        remote_dir = self.ssh_dest_edit.text().strip() if hasattr(self, 'ssh_dest_edit') else ''
        if not remote_dir:
            local_folder = self.selected_folder or os.getcwd()
            remote_dir = f"/home/{user}/{os.path.basename(local_folder)}"

        # 根据 mode 确定要执行的脚本文件
        if mode == "submit":
            script_file = "server.sh"
            cmd = f"cd '{remote_dir}' && chmod +x {script_file} || true; cd '{remote_dir}' && bash {script_file}"
        elif mode == "export_script":
            script_file = "export.sh"
            cmd = f"cd '{remote_dir}' && chmod +x {script_file} || true; cd '{remote_dir}' && bash {script_file}"
        else:
            # run.sh 不再需要执行，只支持 server.sh 和 export.sh
            self.log(f"❌ 不支持的模式：{mode}，请使用 'submit' 或 'export_script'")
            return

        # 异步执行
        def _run():
            try:
                self.log_signal.emit(f"开始远程执行：{cmd}")
                stdin, stdout, stderr = self.ssh.exec_command(cmd, get_pty=True)

                # 实时输出标准输出
                for line in iter(stdout.readline, ''):
                    if not line:
                        break
                    self.log_signal.emit(line.rstrip())

                # 捕获错误输出
                err = stderr.read().decode('utf-8', errors='ignore')
                if err.strip():
                    for l in err.splitlines():
                        self.log_signal.emit(l)

                # 等待结束状态
                exit_status = stdout.channel.recv_exit_status()
                if exit_status == 0:
                    self.log_signal.emit(tr("remote_script_completed", "✅ 远程脚本执行完成"))
                else:
                    self.log_signal.emit(tr("remote_script_exit_code", "❌ 远程脚本执行返回码: {code}").format(code=exit_status))

            except Exception as e:
                self.log_signal.emit(tr("remote_execution_failed", "❌ 执行失败：{error}").format(error=e))

        # 不再禁用按钮，允许用户随时提交任务
        threading.Thread(target=_run, daemon=True).start()

    def show_remote_file_list(self):
        """列出 ssh_dest_edit 指定路径下的文件"""
        if not self.ssh:
            self.log("⚠️ 当前未连接服务器。")
            return

        remote_dir = self.ssh_dest_edit.text().strip()
        if not remote_dir:
            self.log("⚠️ 服务器路径为空。")
            return

        def _worker():
            try:
                stdin, stdout, stderr = self.ssh.exec_command(f"ls -lh {remote_dir}", timeout=10)
                files = stdout.read().decode("utf-8", errors="ignore").strip()
                err = stderr.read().decode("utf-8", errors="ignore").strip()

                if err:
                    self.log_signal.emit(tr("directory_read_error", "❌ 目录读取错误：{error}").format(error=err))
                elif not files:
                    self.log_signal.emit(tr("server_directory_empty", "📂 目录为空：{path}").format(path=remote_dir))
                else:
                    self.log_signal.emit(f"{tr('file_list_header', '📁 {path} 下的文件列表：').format(path=remote_dir)}\n{files}\n==============================================")
            except Exception as e:
                self.log_signal.emit(tr("list_files_failed", "❌ 无法列出文件：{error}").format(error=str(e)))

        threading.Thread(target=_worker, daemon=True).start()

    def clear_remote_folder(self):
        """清空远程服务器文件夹"""
        if not self.ssh:
            self.log(tr("clear_folder_not_connected", "⚠️ 当前未连接服务器。"))
            return

        remote_dir = self.ssh_dest_edit.text().strip()
        if not remote_dir:
            self.log(tr("clear_folder_path_empty", "⚠️ 服务器路径为空。"))
            return

        # 显示确认对话框
        msg_box = MessageBox(
            tr("clear_folder_confirm_title", "确认清空文件夹"),
            tr("clear_folder_confirm_content", "确定要清空远程文件夹：\n{path}\n\n此操作不可恢复！").format(path=remote_dir),
            self
        )
        
        # 设置对话框宽度（参考 WorkFolderDialog 的实现方式，通过内容区域控制宽度）
        # 设置最小宽度，让对话框有足够的空间显示内容
        msg_box.setMinimumWidth(750)
        
        # 设置确认按钮为红色高亮
        # 使用 QTimer 延迟设置，确保 MessageBox 已经完全初始化
        def set_confirm_button_red():
            try:
                # 尝试多种方式查找确认按钮
                confirm_button = None
                
                # 方法1：尝试 yesButton 属性
                if hasattr(msg_box, 'yesButton'):
                    confirm_button = msg_box.yesButton
                
                # 方法2：通过查找子控件
                if not confirm_button:
                    buttons = msg_box.findChildren(QtWidgets.QPushButton)
                    if buttons:
                        # MessageBox 通常第一个按钮是确认按钮（Yes/OK）
                        # 查找文本包含"确定"、"OK"、"Yes"或"Confirm"的按钮
                        confirm_text = tr("confirm", "确定")
                        for btn in buttons:
                            btn_text = btn.text()
                            if confirm_text in btn_text or "OK" in btn_text or "Yes" in btn_text or "Confirm" in btn_text:
                                confirm_button = btn
                                break
                        # 如果没找到，使用第一个按钮
                        if not confirm_button and buttons:
                            confirm_button = buttons[0]
                
                # 设置红色样式
                if confirm_button:
                    confirm_button.setStyleSheet("""
                        QPushButton {
                            background-color: #d32f2f;
                            color: white;
                            border: none;
                            border-radius: 4px;
                            padding: 8px 16px;
                            font-weight: bold;
                        }
                        QPushButton:hover {
                            background-color: #b71c1c;
                        }
                        QPushButton:pressed {
                            background-color: #8b0000;
                        }
                    """)
            except Exception as e:
                # 静默失败，不影响对话框显示
                pass
        
        # 延迟执行，确保 MessageBox 已完全渲染
        QtCore.QTimer.singleShot(50, set_confirm_button_red)
        
        if not msg_box.exec():
            return

        def _worker():
            try:
                # 检查连接
                if self.ssh is None or not self._is_ssh_alive(self.ssh):
                    self.log_signal.emit(tr("clear_folder_ssh_reconnecting", "⚠️ SSH 连接不存在或已断开，正在尝试重新连接..."))
                    try:
                        if not self._last_conn_args:
                            self.log_signal.emit(tr("clear_folder_reconnect_failed", "❌ 无法重新连接：缺少连接信息"))
                            return
                        host, port, user, pwd = self._last_conn_args
                        self.ssh = paramiko.SSHClient()
                        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                        self.ssh.connect(
                            hostname=host,
                            port=port,
                            username=user,
                            password=pwd,
                            look_for_keys=False,
                            allow_agent=False,
                            timeout=15,
                            banner_timeout=200
                        )
                        self.log_signal.emit(tr("reconnect_success", "已重新连接服务器 {host}:{port}").format(host=host, port=port))
                    except Exception as e:
                        self.log_signal.emit(tr("reconnect_failed", "无法重新连接服务器: {error}").format(error=str(e)))
                        return

                # 执行清空文件夹命令
                # 使用 rm -rf * 删除所有文件和文件夹，但保留目录本身
                # 注意：使用 sh -c 来确保通配符正确展开
                cmd = f"cd '{remote_dir}' && sh -c 'rm -rf * .[!.]*' 2>&1 || true"
                self.log_signal.emit(tr("clear_folder_start", "🔄 开始清空远程文件夹：{path}").format(path=remote_dir))
                
                stdin, stdout, stderr = self.ssh.exec_command(cmd, get_pty=True, timeout=30)
                
                # 读取输出
                stdout_text = stdout.read().decode("utf-8", errors="ignore").strip()
                stderr_text = stderr.read().decode("utf-8", errors="ignore").strip()
                
                # 等待命令完成
                exit_status = stdout.channel.recv_exit_status()
                
                if exit_status == 0 or "No such file" not in stderr_text:
                    self.log_signal.emit(tr("clear_folder_success", "✅ 已清空远程文件夹：{path}").format(path=remote_dir))
                    if stdout_text:
                        self.log_signal.emit(tr("clear_folder_output", "输出：{output}").format(output=stdout_text))
                else:
                    self.log_signal.emit(tr("clear_folder_warning", "⚠️ 清空文件夹时出现警告：{warning}").format(warning=stderr_text))
                    if stdout_text:
                        self.log_signal.emit(tr("clear_folder_output", "输出：{output}").format(output=stdout_text))
                        
            except Exception as e:
                self.log_signal.emit(tr("clear_folder_failed", "❌ 清空远程文件夹失败：{error}").format(error=str(e)))
                import traceback
                for line in traceback.format_exc().splitlines():
                    self.log_signal.emit(line)

        threading.Thread(target=_worker, daemon=True).start()

    def view_task_queue(self):
        """查看服务器任务队列（执行 squeue -l）"""
        if not self.ssh:
            self.log("⚠️ 当前未连接服务器。")
            return

        def _worker():
            try:
                stdin, stdout, stderr = self.ssh.exec_command("squeue -l", get_pty=True, timeout=10)
                queue_output = stdout.read().decode("utf-8", errors="ignore").strip()
                err = stderr.read().decode("utf-8", errors="ignore").strip()

                if err:
                    self.log_signal.emit(tr("queue_query_error", "❌ 任务队列查询错误：{error}").format(error=err))
                elif not queue_output:
                    self.log_signal.emit(tr("queue_empty", "📋 任务队列为空（当前没有运行中的任务）"))
                else:
                    self.log_signal.emit(f"{tr('queue_header', '📋 任务队列（squeue -l）：')}\n{queue_output}\n==============================================")
            except Exception as e:
                self.log_signal.emit(tr("queue_query_failed", "❌ 无法查询任务队列：{error}").format(error=str(e)))

        threading.Thread(target=_worker, daemon=True).start()

    def check_remote_completion(self):
        """检查服务器目录是否存在 success.log 或 fail.log 来判断计算状态"""
        if not self.ssh:
            InfoBar.warning(
                title="检查失败",
                content="当前未连接服务器，无法检查结果状态",
                duration=3000,
                parent=self
            )
            return

        remote_dir = self.ssh_dest_edit.text().strip()
        if not remote_dir:
            InfoBar.warning(
                title="检查失败",
                content="未指定远程目录",
                duration=3000,
                parent=self
            )
            return

        def _worker():
            try:
                sftp = self.ssh.open_sftp()
                try:
                    files = sftp.listdir(remote_dir)
                except IOError as e:
                    sftp.close()
                    self.show_info_bar_signal.emit("error", "检查失败", f"无法访问远程目录：{remote_dir}")
                    return

                # 检查服务器目录中的文件
                has_success = "success.log" in files
                has_fail = "fail.log" in files

                sftp.close()

                # 在主线程中显示消息
                if has_success:
                    self.show_info_bar_signal.emit("success", tr("computation_success", "计算成功"), tr("computation_success_detected", "检测到 success.log，计算已完成"))
                elif has_fail:
                    self.show_info_bar_signal.emit("error", tr("computation_failed", "计算失败"), tr("computation_failed_detected", "检测到 fail.log，计算失败"))
                else:
                    self.show_info_bar_signal.emit("warning", tr("computation_incomplete", "计算未完成"), tr("computation_incomplete_detected", "未检测到 success.log 或 fail.log，计算仍在进行中"))

            except Exception as e:
                self.show_info_bar_signal.emit("error", "检查失败", f"检查远程结果失败：{e}")

        threading.Thread(target=_worker, daemon=True).start()


    def download_remote_nc(self):
        """从远程目录下载以 ww3 开头、.nc 结尾的文件到本地选中目录，显示每1%下载进度"""
        if not self.selected_folder:
            self.log("❌ 本地未选择有效的目标文件夹。")
            return

        os.makedirs(self.selected_folder, exist_ok=True)

        if not self.ssh:
            self.log("❌ 请先连接服务器。")
            return

        remote_dir = self.ssh_dest_edit.text().strip()
        if not remote_dir:
            self.log("❌ 请填写服务器路径")
            return

        def _run():
            try:
                sftp = self.ssh.open_sftp()

                # 检查是否是嵌套模式
                grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
                nested_text = tr("step2_grid_type_nested", "嵌套网格")
                is_nested = (grid_type == nested_text or grid_type == "嵌套网格")

                # 根据模式确定要搜索的目录
                if is_nested:
                    # 嵌套模式：从 fine 目录下载
                    search_dir = os.path.join(remote_dir, "fine").replace("\\", "/")
                    try:
                        files = sftp.listdir(search_dir)
                    except (IOError, OSError) as e:
                        self.log_signal.emit(f"❌ 无法列出远程目录: {search_dir} -> {e}")
                        sftp.close()
                        return
                else:
                    # 普通模式：从主目录下载
                    search_dir = remote_dir
                    try:
                        files = sftp.listdir(search_dir)
                    except IOError as e:
                        self.log_signal.emit(f"❌ 无法列出远程目录: {search_dir} -> {e}")
                        sftp.close()
                        return

                # 分别匹配普通结果文件和 spec 文件
                # 普通结果文件：ww3*.nc 但不包含 spec
                matched_result = [f for f in files if f.startswith("ww3") and f.endswith(".nc") and "spec" not in f.lower()]
                # spec 文件：ww3*spec*nc
                matched_spec = [f for f in files if f.startswith("ww3") and "spec" in f.lower() and f.endswith(".nc")]
                
                # 合并文件列表：先下载普通结果文件，再下载 spec 文件
                matched = matched_result + matched_spec
                
                if not matched:
                    self.log_signal.emit("⚠️ 远程目录未找到匹配的 ww3*.nc 文件。")
                    sftp.close()
                    return

                # 根据模式确定本地保存目录
                if is_nested:
                    # 嵌套模式：下载到 fine 目录
                    local_download_dir = os.path.join(self.selected_folder, "fine")
                    os.makedirs(local_download_dir, exist_ok=True)
                else:
                    # 普通模式：下载到主工作目录
                    local_download_dir = self.selected_folder

                # 串行下载所有文件（先普通结果文件，再 spec 文件）
                for name in matched:
                    rpath = f"{search_dir.rstrip('/')}/{name}"
                    lpath = os.path.join(local_download_dir, name)
                    try:
                        filesize = sftp.stat(rpath).st_size
                        last_percent = [0]  # 使用列表可在回调中修改
                        is_first_progress = [True]  # 标记是否是第一次进度更新

                        def progress(transferred, total=filesize):
                            percent = int(transferred / total * 100)
                            if percent > last_percent[0]:
                                last_percent[0] = percent
                                # 第一次进度更新时，先添加一行
                                if is_first_progress[0]:
                                    is_first_progress[0] = False
                                    self.log_signal.emit(f"开始下载 {name} ({filesize/1024:.1f} KB)")
                                # 后续更新使用更新最后一行
                                self.log_update_last_line_signal.emit(f"下载 {name} ... {percent}%")

                        self.log_signal.emit(f"开始下载 {name} ({filesize/1024:.1f} KB)")
                        sftp.get(rpath, lpath, callback=progress)
                        # 下载完成后，更新最后一行显示完成信息
                        self.log_update_last_line_signal.emit(f"✅ 下载完成 {name}")
                        # 然后添加新行，确保后续日志在新行显示
                        self.log_signal.emit("")

                    except Exception as e:
                        self.log_signal.emit(f"❌ 下载 {name} 失败: {e}")

                sftp.close()

            except Exception as e:
                self.log_signal.emit(f"❌ 下载失败：{e}")

        threading.Thread(target=_run, daemon=True).start()

    def download_remote_log(self):
        """从远程目录下载 success.log 或 fail.log 文件到本地选中目录"""
        if not self.selected_folder:
            self.log("❌ 本地未选择有效的目标文件夹。")
            return

        os.makedirs(self.selected_folder, exist_ok=True)

        if not self.ssh:
            self.log("❌ 请先连接服务器。")
            return

        remote_dir = self.ssh_dest_edit.text().strip()
        if not remote_dir:
            self.log("❌ 请填写服务器路径")
            return

        def _run():
            try:
                sftp = self.ssh.open_sftp()

                # 检查 success.log 和 fail.log 是否存在
                success_log_path = f"{remote_dir.rstrip('/')}/success.log"
                fail_log_path = f"{remote_dir.rstrip('/')}/fail.log"
                
                log_files_to_download = []
                
                # 检查 success.log
                try:
                    sftp.stat(success_log_path)
                    log_files_to_download.append(("success.log", success_log_path))
                except (IOError, OSError):
                    pass
                
                # 检查 fail.log
                try:
                    sftp.stat(fail_log_path)
                    log_files_to_download.append(("fail.log", fail_log_path))
                except (IOError, OSError):
                    pass
                
                if not log_files_to_download:
                    self.log_signal.emit("⚠️ 远程目录未找到 success.log 或 fail.log 文件。")
                    sftp.close()
                    return
                
                # 下载找到的 log 文件
                for log_name, remote_path in log_files_to_download:
                    local_path = os.path.join(self.selected_folder, log_name)
                    try:
                        filesize = sftp.stat(remote_path).st_size
                        self.log_signal.emit(f"开始下载 {log_name} ({filesize/1024:.1f} KB)")
                        sftp.get(remote_path, local_path)
                        self.log_signal.emit(f"✅ 下载完成 {log_name}")
                    except Exception as e:
                        self.log_signal.emit(f"❌ 下载 {log_name} 失败: {e}")

                sftp.close()

            except Exception as e:
                self.log_signal.emit(f"❌ 下载 log 文件失败：{e}")

        threading.Thread(target=_run, daemon=True).start()

    def upload_folder(self):
        """上传整个文件夹到远程服务器"""
        if not self.selected_folder or not os.path.exists(self.selected_folder):
            self.log(tr("upload_local_folder_invalid", "❌ 未选择有效的本地文件夹！"))
            return

        remote_folder = self.ssh_dest_edit.text().strip() if hasattr(self, 'ssh_dest_edit') else None
        if not remote_folder:
            remote_folder = None

        def _worker():
            nonlocal remote_folder  # 声明使用外部作用域的变量
            # 检查连接
            if self.ssh is None or not self._is_ssh_alive(self.ssh):
                self.log_signal.emit(tr("ssh_reconnect_start", "⚠️ SSH 连接不存在或已断开，正在尝试重新连接..."))
                try:
                    if not self._last_conn_args:
                        self.log_signal.emit(tr("reconnect_missing_info", "❌ 无法重新连接：缺少连接信息"))
                        return
                    host, port, user, pwd = self._last_conn_args
                    self.ssh = paramiko.SSHClient()
                    self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    self.ssh.connect(
                        hostname=host,
                        port=port,
                        username=user,
                        password=pwd,
                        look_for_keys=False,
                        allow_agent=False,
                        timeout=15,
                        banner_timeout=200
                    )
                    self.log_signal.emit(tr("reconnect_success", "✅ 已重新连接服务器 {host}:{port}").format(host=host, port=port))
                except Exception as e:
                    self.log_signal.emit(tr("reconnect_failed", "❌ 无法重新连接服务器: {error}").format(error=e))
                    return

            # 确保 SFTP 可用
            try:
                sftp = self.ssh.open_sftp()
            except Exception as e:
                self.log_signal.emit(tr("sftp_open_failed_retry", "⚠️ 打开 SFTP 通道失败: {error}，尝试重新建立 SSH...").format(error=e))
                try:
                    if not self._last_conn_args:
                        self.log_signal.emit(tr("reconnect_missing_info", "❌ 无法重新连接：缺少连接信息"))
                        return
                    host, port, user, pwd = self._last_conn_args
                    if self.ssh:
                        try:
                            self.ssh.close()
                        except:
                            pass
                    self.ssh = paramiko.SSHClient()
                    self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    self.ssh.connect(hostname=host, port=port, username=user, password=pwd,
                                   look_for_keys=False, allow_agent=False, timeout=15, banner_timeout=200)
                    sftp = self.ssh.open_sftp()
                except Exception as e2:
                    self.log_signal.emit(tr("sftp_open_failed", "❌ SFTP 通道建立失败: {error}").format(error=e2))
                    return

            # 处理远程路径
            if not self._last_conn_args:
                self.log_signal.emit(tr("connection_info_missing", "❌ 无法获取连接信息"))
                sftp.close()
                return
            host, port, username, _ = self._last_conn_args
            if not remote_folder:
                remote_folder = f"/home/{username}/{os.path.basename(self.selected_folder)}"
            else:
                if remote_folder.startswith("~"):
                    remote_folder = remote_folder.replace("~", f"/home/{username}", 1)

           
            self.log_signal.emit(tr("upload_folder_start", "📤 开始上传文件夹到 {path} ...").format(path=remote_folder))

            # 确保远程目录存在
            def ensure_remote_dir(sftp_client, remote_dir):
                parts = remote_dir.strip('/').split('/')
                cur = ''
                for p in parts:
                    cur += '/' + p
                    try:
                        sftp_client.stat(cur)
                    except IOError:
                        try:
                            sftp_client.mkdir(cur)
                        except IOError as me:
                            raise PermissionError(f"创建远程目录失败: {cur} -> {me}")

            try:
                ensure_remote_dir(sftp, remote_folder)
                sftp.chdir(remote_folder)
            except Exception as e:
               
                self.log_signal.emit(tr("cannot_enter_remote_dir", "⚠️ 无法进入远程目录 {path}: {error}").format(path=remote_folder, error=str(e)))
                sftp.close()
                return

            # 上传整个文件夹
            try:
                for root_dir, dirs, files in os.walk(self.selected_folder):
                    rel_path = os.path.relpath(root_dir, self.selected_folder)
                    remote_path = os.path.join(remote_folder, rel_path).replace("\\", "/")
                    try:
                        ensure_remote_dir(sftp, remote_path)
                    except Exception as e:
                       
                        self.log_signal.emit(tr("cannot_create_remote_dir", "⚠️ 无法创建远程目录 {path}: {error}").format(path=remote_path, error=str(e)))
                        continue

                    for file in files:
                        local_file = os.path.join(root_dir, file)
                        remote_file = os.path.join(remote_path, file).replace("\\", "/")
                       
                        try:
                            # 检查是否是 server.sh 或 ww3.slurm，如果是则移除 \r
                            if file in ("server.sh", "ww3.slurm"):
                                # 读取文件内容
                                with open(local_file, 'rb') as f:
                                    content = f.read()
                                # 检查是否包含 \r
                                if b'\r' in content:
                                    # 移除所有 \r
                                    content = content.replace(b'\r', b'')
                                    # 创建临时文件
                                    import tempfile
                                    with tempfile.NamedTemporaryFile(mode='wb', delete=False) as tmp_file:
                                        tmp_file.write(content)
                                        tmp_path = tmp_file.name
                                    try:
                                        # 上传清理后的文件
                                        sftp.put(tmp_path, remote_file)
                                    finally:
                                        # 删除临时文件
                                        try:
                                            os.unlink(tmp_path)
                                        except:
                                            pass
                                else:
                                    # 没有 \r，直接上传
                                    sftp.put(local_file, remote_file)
                            else:
                                # 其他文件直接上传
                                sftp.put(local_file, remote_file)
                            # 上传成功后显示日志
                            self.log_signal.emit(tr("upload_file_success", "上传 {file} 文件成功").format(file=file))
                        except (IOError, paramiko.ssh_exception.SSHException, EOFError, OSError) as e:
                           
                            self.log_signal.emit(tr("cannot_upload_file", "⚠️ 无法上传 {file}: {error}").format(file=file, error=str(e)))
                            # 检查连接是否断开
                            if isinstance(e, (paramiko.ssh_exception.SSHException, EOFError)):
                                self.log_signal.emit(tr("upload_connection_lost_interrupted", "⚠️ 服务器连接已断开，上传中断"))
                                try:
                                    sftp.close()
                                except:
                                    pass
                                # 关闭SSH连接
                                if hasattr(self, 'ssh') and self.ssh:
                                    try:
                                        self.ssh.close()
                                    except:
                                        pass
                                    self.ssh = None
                                # 更新连接状态
                               
                                self.status_signal.emit(tr("not_connected_disconnected", "未连接(连接断开)"))
                                return
                            continue

                sftp.close()
               
                self.log_signal.emit(tr("upload_folder_complete", "✅ 文件夹上传完成: {path}").format(path=remote_folder))
            except (paramiko.ssh_exception.SSHException, EOFError, OSError) as e:
               
                self.log_signal.emit(tr("upload_connection_lost", "❌ 上传过程中连接断开: {error}").format(error=str(e)))
                try:
                    sftp.close()
                except:
                    pass
                # 关闭SSH连接
                if hasattr(self, 'ssh') and self.ssh:
                    try:
                        self.ssh.close()
                    except:
                        pass
                    self.ssh = None
                # 更新连接状态
               
                self.status_signal.emit(tr("not_connected_disconnected", "未连接(连接断开)"))
            except Exception as e:
                self.log_signal.emit(tr("upload_error", "❌ 上传过程中出错: {error}").format(error=e))
                try:
                    sftp.close()
                except:
                    pass

        threading.Thread(target=_worker, daemon=True).start()
