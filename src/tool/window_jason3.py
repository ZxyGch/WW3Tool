"""
Jason3 功能模块
包含 JASON-3 数据下载逻辑，数据读取与匹配逻辑在 plot.workers_jason3.Jason3ServiceMixin
"""
import os
import re
import glob
import threading
import multiprocessing
import requests
if hasattr(multiprocessing, 'set_start_method'):
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass
from multiprocessing import Process, Queue
import numpy as np
from datetime import datetime, timedelta
from PyQt6 import QtCore
from setting.config import *
from setting.language_manager import tr
from plot.workers_jason3 import Jason3ServiceMixin


class Jason3Mixin(Jason3ServiceMixin):
    """Jason3功能模块（下载逻辑）"""

    def _run_download_jason3_process(self, time_range, local_folder, download_url=None, callback=None):
        """在子进程中执行 Jason-3 数据下载操作（使用 multiprocessing 避免阻塞 UI）"""
        # 自动下载逻辑已移除
        return
        # 创建队列用于子进程和主进程之间的通信
        log_queue = Queue()
        result_queue = Queue()

        # 如果没有提供下载 URL，从配置中读取
        if download_url is None:
            from setting.config import load_config
            current_config = load_config()
            download_url = current_config.get("JASON3_DOWNLOAD_URL", "").strip()
            if not download_url:
                # 使用默认值
                download_url = "ftp-oceans.ncei.noaa.gov/nodc/data/jason3-igdr/igdr/igdr/"

        # 启动子进程
        process = Process(
            target=_download_jason3_worker,
            args=(time_range, local_folder, log_queue, result_queue, download_url)
        )
        process.start()

        # 在主线程中监听日志队列并更新UI
        def _poll_logs():
            try:
                # 非阻塞检查队列
                done = False
                while True:
                    try:
                        msg = log_queue.get_nowait()
                        if msg == "__DONE__":
                            done = True
                            break
                        # 检查是否是更新消息（用于进度更新）
                        if isinstance(msg, tuple) and len(msg) == 2 and msg[0] == "__UPDATE__":
                            self.log_update_last_line_signal.emit(msg[1])
                        else:
                            self.log_signal.emit(msg)
                    except:
                        break

                # 检查进程是否完成
                if not done and process.is_alive():
                    # 继续轮询
                    QtCore.QTimer.singleShot(100, _poll_logs)  # 每100ms检查一次
                else:
                    # 进程完成，获取最后的结果
                    if not done:
                        # 如果还没收到完成信号，再尝试获取一次
                        try:
                            while True:
                                try:
                                    msg = log_queue.get_nowait()
                                    if msg == "__DONE__":
                                        done = True
                                        break
                                    if isinstance(msg, tuple) and len(msg) == 2 and msg[0] == "__UPDATE__":
                                        self.log_update_last_line_signal.emit(msg[1])
                                    else:
                                        self.log_signal.emit(msg)
                                except:
                                    break
                        except:
                            pass

                    # 获取结果
                    try:
                        result = result_queue.get_nowait()
                        if not result:
                            self.log_signal.emit("⚠️ 下载失败或未找到符合时间范围的文件")
                    except:
                        pass

                    # 等待进程结束
                    process.join(timeout=1)
                    if process.is_alive():
                        process.terminate()
                        process.join()
                    
                    # 如果提供了回调函数，在下载完成后调用
                    if callback:
                        try:
                            callback()
                        except Exception as e:
                            self.log_signal.emit(f"⚠️ 执行下载完成回调时出错：{e}")

            except Exception as e:
                self.log_signal.emit(f"❌ 轮询下载进度时出错：{e}")

        # 开始轮询
        _poll_logs()

    def _download_jason3_for_range(self, time_range, local_folder, lon_lat=None):
        """
        如果本地指定时间范围内没有 Jason-3 文件，则尝试从 NOAA FTP 服务器下载到 local_folder。
        在子进程中执行下载，并显示进度。
        返回 True 表示下载后本地已有对应时间范围文件，False 表示仍然没有。
        """
        # 自动下载逻辑已移除
        return False
        start_str, end_str = time_range
        # 文件名格式：JA3_GPN_2PfP078_254_20180331_193738_20180331_203351.nc
        time_pattern = r"(\d{8}_\d{6})_(\d{8}_\d{6})"
        start_dt = datetime.strptime(start_str + "_000000", "%Y%m%d_%H%M%S")
        end_dt = datetime.strptime(end_str + "_235959", "%Y%m%d_%H%M%S")

        if not os.path.isdir(local_folder):
            os.makedirs(local_folder, exist_ok=True)

        def _has_local_files():
            """检查是否有文件在时间范围内（不检查是否所有天数都被覆盖）"""
            nc_files = [f for f in os.listdir(local_folder) if f.startswith("JA3_GPN_") and f.endswith(".nc")]
            for f in nc_files:
                m = re.search(time_pattern, f)
                if not m:
                    continue
                t1 = datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
                t2 = datetime.strptime(m.group(2), "%Y%m%d_%H%M%S")
                if t2 >= start_dt and t1 <= end_dt:
                    return True
            return False

        # 检查是否有缺失的天数
        def _check_missing_days():
            """检查目标时间范围内哪些天数没有被覆盖"""
            # 检查本地已下载的文件（包括GDR和IGDR）
            if not os.path.isdir(local_folder):
                # 如果文件夹不存在，返回所有天数
                return [start_dt.date() + timedelta(days=i) for i in range((end_dt.date() - start_dt.date()).days + 1)]
            
            local_nc_files = [f for f in os.listdir(local_folder) if (f.startswith("JA3_GPN_") or f.startswith("JA3_IPN_")) and f.endswith(".nc")]
            local_file_ranges = []
            
            for filename in local_nc_files:
                # 匹配GDR和IGDR格式（两者格式相同）
                m = re.search(time_pattern, filename)
                if m:
                    try:
                        file_start = datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
                        file_end = datetime.strptime(m.group(2), "%Y%m%d_%H%M%S")
                        # 检查是否在目标时间范围内（有重叠即可）
                        if file_end >= start_dt and file_start <= end_dt:
                            local_file_ranges.append((file_start, file_end))
                    except ValueError:
                        continue
            
            missing_days = []
            current_date = start_dt.date()
            end_date = end_dt.date()
            
            while current_date <= end_date:
                # 检查这一天是否有数据文件覆盖
                # 使用更宽松的条件：只要文件的时间范围与这一天有重叠，就认为覆盖了
                day_start = datetime.combine(current_date, datetime.min.time())
                day_end = datetime.combine(current_date, datetime.max.time())
                
                has_data = False
                for file_start, file_end in local_file_ranges:
                    # 检查文件时间范围是否与这一天有重叠
                    if file_end >= day_start and file_start <= day_end:
                        has_data = True
                        break
                
                if not has_data:
                    missing_days.append(current_date)
                
                current_date += timedelta(days=1)
            
            return missing_days

        # 检查是否有缺失的天数
        missing_days = _check_missing_days()
        
        # 如果所有天数都有数据，直接返回
        if not missing_days:
            return True
        
        # 有缺失天数，需要下载
        if missing_days:
            self.log_signal.emit(f"⚠️ 发现 {len(missing_days)} 个缺失的天数：{', '.join([d.strftime('%Y%m%d') for d in missing_days])}")
            
            # 检查是否开启了自动下载
            from setting.config import load_config
            current_config = load_config()
            auto_download = current_config.get("JASON3_AUTO_DOWNLOAD_MISSING", True)
            if isinstance(auto_download, str):
                auto_download = auto_download.lower() in ('true', '1', 'yes')
            
            if not auto_download:
                self.log_signal.emit("⚠️ 自动下载功能已关闭，请手动下载缺失的数据或开启自动下载功能")
                return False
            
            download_url = current_config.get("JASON3_DOWNLOAD_URL", "").strip()
            if not download_url:
                self.log_signal.emit("⚠️ 未配置 JASON3 下载链接，无法自动下载")
                return False
            
            self.log_signal.emit(f"🔄 开始下载缺失日期的数据（使用下载链接：{download_url}）...")
        else:
            # 没有缺失天数，直接返回
            return True
        
        # 使用同步方式等待下载完成
        from PyQt6.QtCore import QEventLoop, QTimer
        download_complete = [False]
        download_result = [False]
        
        # 先创建 loop，以便在回调中使用
        loop = QEventLoop()
        
        def _on_download_complete():
            """下载完成后的回调"""
            # 等待更长时间，确保所有文件已完全写入磁盘
            import time
            self.log_signal.emit("🔄 等待文件写入完成...")
            time.sleep(3)  # 等待3秒确保文件完全写入
            
            # 再次检查缺失天数
            remaining_missing = _check_missing_days()
            if not remaining_missing:
                download_result[0] = True
                self.log_signal.emit("✅ 所有缺失天数的数据已下载完成")
            else:
                download_result[0] = False
                # 列出本地文件以便调试
                if os.path.isdir(local_folder):
                    local_files = [f for f in os.listdir(local_folder) if (f.startswith("JA3_GPN_") or f.startswith("JA3_IPN_")) and f.endswith(".nc")]
                    self.log_signal.emit(f"⚠️ 仍有 {len(remaining_missing)} 个缺失天数：{', '.join([d.strftime('%Y%m%d') for d in remaining_missing])}")
                    if local_files:
                        self.log_signal.emit(f"   本地文件数量：{len(local_files)}")
                        # 显示最近下载的文件（最多5个）
                        recent_files = sorted(local_files, reverse=True)[:5]
                        for f in recent_files:
                            self.log_signal.emit(f"   - {f}")
            download_complete[0] = True
            if loop.isRunning():
                loop.quit()
        
        # 在子进程中执行下载（包括补充下载缺失天数）
        # download_url 已经在上面从配置中读取了
        self._run_download_jason3_process(time_range, local_folder, download_url=download_url, callback=_on_download_complete)
        timeout_timer = QTimer()
        timeout_timer.setSingleShot(True)
        
        def _on_timeout():
            if not download_complete[0]:
                self.log_signal.emit("⚠️ 下载等待超时（120秒）")
            loop.quit()
        
        timeout_timer.timeout.connect(_on_timeout)
        timeout_timer.start(120000)  # 120秒超时
        
        # 定期检查下载是否完成
        check_timer = QTimer()
        
        def _check_complete():
            if download_complete[0]:
                loop.quit()
        
        check_timer.timeout.connect(_check_complete)
        check_timer.start(500)  # 每500ms检查一次
        
        # 启动事件循环等待
        loop.exec()
        
        # 停止定时器
        timeout_timer.stop()
        check_timer.stop()
        
        if download_complete[0]:
            # 如果下载成功，再等待一小段时间确保文件完全写入
            if download_result[0]:
                import time
                time.sleep(2)  # 等待2秒确保文件完全写入
            return download_result[0]
        else:
            # 超时，但下载可能仍在进行中
            self.log_signal.emit("⚠️ 下载超时，但下载仍在后台进行中...")
            # 等待下载进程真正完成
            self.log_signal.emit("🔄 等待下载进程完成...")
            # 再次检查缺失天数，并等待一段时间
            import time
            time.sleep(5)  # 等待5秒让下载继续
            remaining_missing = _check_missing_days()
            if not remaining_missing:
                return True
            else:
                # 仍有缺失，返回False，不继续绘图（等待下载完成）
                return False

        # 如果仍然没有，尝试从服务器下载（如已配置）
        if self.ssh and JASON_REMOTE_PATH:
            remote_dir = JASON_REMOTE_PATH
            self.log_signal.emit(f"🔄 本地未找到指定时间范围的 Jason-3 文件，尝试从服务器下载：{remote_dir}")

            try:
                sftp = self.ssh.open_sftp()
            except Exception as e:
                self.log_signal.emit(f"❌ 无法打开服务器 SFTP 连接，下载 Jason-3 数据失败：{e}")
                sftp = None

            if sftp is not None:
                try:
                    try:
                        files = sftp.listdir(remote_dir)
                    except IOError as e:
                        self.log_signal.emit(f"❌ 无法列出远程 Jason-3 目录: {remote_dir} -> {e}")
                        sftp.close()
                        sftp = None
                    if sftp is not None:
                        matched = []
                        for name in files:
                            if not (name.startswith("JA3_GPN_") and name.endswith(".nc")):
                                continue
                            m = re.search(time_pattern, name)
                            if not m:
                                continue
                            t1 = datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
                            t2 = datetime.strptime(m.group(2), "%Y%m%d_%H%M%S")
                            if t2 >= start_dt and t1 <= end_dt:
                                matched.append(name)

                        if not matched:
                            self.log_signal.emit("⚠️ 服务器上未找到符合时间范围的 Jason-3 文件。")
                        else:
                            os.makedirs(local_folder, exist_ok=True)

                            for name in matched:
                                remote_path = f"{remote_dir.rstrip('/')}/{name}"
                                local_path = os.path.join(local_folder, name)
                                try:
                                    filesize = sftp.stat(remote_path).st_size
                                    last_percent = [0]

                                    def progress(transferred, total=filesize):
                                        if total <= 0:
                                            return
                                        percent = int(transferred / total * 100)
                                        if percent > last_percent[0]:
                                            last_percent[0] = percent
                                            self.log_update_last_line_signal.emit(f"下载 Jason-3 {name} ... {percent}%")

                                    self.log_signal.emit(f"开始下载 Jason-3 {name} ({filesize/1024:.1f} KB)")
                                    sftp.get(remote_path, local_path, callback=progress)
                                    self.log_update_last_line_signal.emit(f"✅ 下载完成 Jason-3 {name}")
                                    self.log_signal.emit("")
                                except Exception as e:
                                    self.log_signal.emit(f"❌ 下载 Jason-3 {name} 失败: {e}")

                        sftp.close()
                except Exception as e:
                    try:
                        sftp.close()
                    except Exception:
                        pass
                    self.log_signal.emit(f"❌ 下载 Jason-3 数据时发生错误：{e}")

        # 所有下载完成后再次检查本地是否已有文件
        if _has_local_files():
            self.log_signal.emit("✅ 已获取指定时间范围的 Jason-3 数据。")
            return True

        self.log_signal.emit("⚠️ 下载完成后仍未找到符合时间范围的 Jason-3 文件。")
        return False
