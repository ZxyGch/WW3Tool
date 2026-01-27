import sys
import os
import json
import time
import numpy as np
import glob
import subprocess
import shutil
import threading
import multiprocessing
import requests
from base64 import b64encode
# 在 Windows 上需要设置启动方法
if hasattr(multiprocessing, 'set_start_method'):
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass  # 如果已经设置过，忽略错误
from multiprocessing import Process, Queue
import socket
import paramiko
import locale
import matplotlib
matplotlib.use('QtAgg')  # 使用 Qt 后端（兼容 PyQt6）
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib import cm
from netCDF4 import Dataset, num2date
import netCDF4 as nc
from datetime import datetime, timedelta
from PIL import Image
import platform
import re
import cv2
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import QEvent, Qt
QSplitter = QtWidgets.QSplitter
from qfluentwidgets import FluentWindow, PrimaryPushButton, LineEdit, TextEdit, InfoBar, setTheme, Theme
from qfluentwidgets import NavigationItemPosition, NavigationWidget, FluentIcon, HeaderCardWidget, ComboBox, TableWidget
from PyQt6.QtGui import QColor, QIcon
from qfluentwidgets import MessageBoxBase
from PyQt6.QtWidgets import QTableWidgetItem, QHeaderView, QScrollArea
from PyQt6.QtGui import QPixmap
QApplication = QtWidgets.QApplication
QWidget = QtWidgets.QWidget
QVBoxLayout = QtWidgets.QVBoxLayout
QHBoxLayout = QtWidgets.QHBoxLayout
QStackedWidget = QtWidgets.QStackedWidget
QFileDialog = QtWidgets.QFileDialog
QDialog = QtWidgets.QDialog
QLabel = QtWidgets.QLabel
QGridLayout = QtWidgets.QGridLayout
QRadioButton = QtWidgets.QRadioButton
QButtonGroup = QtWidgets.QButtonGroup
QSpinBox = QtWidgets.QSpinBox
from setting.config import *
from plot.workers import _match_ww3_jason3_worker, _run_jason3_swh_worker, _make_wave_maps_worker
from setting.language_manager import tr

class Jason3Mixin:
    """Jason3功能模块"""

    def haversine_distance(self, lat1, lon1, lat2, lon2):
            """计算两点间的距离（度）"""
            lat1_rad = np.radians(lat1)
            lon1_rad = np.radians(lon1)
            lat2_rad = np.radians(lat2)
            lon2_rad = np.radians(lon2)

            dlat = lat2_rad - lat1_rad
            dlon = lon2_rad - lon1_rad

            a = np.sin(dlat / 2) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2) ** 2
            c = 2 * np.arcsin(np.sqrt(a))

            R = 6371.0
            distance_km = R * c
            distance_deg = distance_km / 111.0

            return distance_deg


    def _empty_jason3_result(self):
        """返回空的 Jason-3 结果"""
        return {
            'ja_time': np.array([]),
            'longitude': np.array([]),
            'latitude': np.array([]),
            'wind': np.array([]),
            'swh': np.array([])
        }


    def read_jason3_chen(self, lon_lat, timeinput, jasonpath, verbose=False):
        """读取 Jason-3 数据（Chen 方法）"""
        from pathlib import Path

        # 只在 verbose=True 时输出详细日志，减少日志更新频率
        if verbose:
            self.log_signal.emit('======== Processing Jason_3 ================================')
            self.log_signal.emit(f'The path of Jason_3 is "{jasonpath}"')

        jasonpath = Path(jasonpath)
        timeinput = np.array(timeinput)
        if timeinput.ndim == 2:
            start_dt = datetime(*timeinput[0, :6].astype(int))
            end_dt = datetime(*timeinput[1, :6].astype(int))
        else:
            start_dt = datetime(int(timeinput[0]), int(timeinput[1]), int(timeinput[2]), 0, 0, 0)
            end_dt = start_dt + timedelta(days=1)

        if not jasonpath.exists():
            if verbose:
                self.log_signal.emit(f"WARNING: Path does not exist: {jasonpath}")
            return self._empty_jason3_result()

        ncfiles = []

        if timeinput.ndim == 1:
            year = f"{int(timeinput[0]):04d}"
            month = f"{int(timeinput[1]):02d}"
            day = f"{int(timeinput[2]):02d}"
            # 支持 JA3_GPN_ 和 JA3_IPN_ 两种格式
            pattern_gpn = f"JA3_GPN_*{year}{month}{day}_*.nc"
            pattern_ipn = f"JA3_IPN_*{year}{month}{day}_*.nc"
            ncfiles = list(jasonpath.glob(pattern_gpn)) + list(jasonpath.glob(pattern_ipn))
        else:
            # 支持 JA3_GPN_ 和 JA3_IPN_ 两种格式
            all_files = list(jasonpath.glob('JA3_GPN_*.nc')) + list(jasonpath.glob('JA3_IPN_*.nc'))
            pattern = re.compile(r'(\d{8}_\d{6})_(\d{8}_\d{6})')

            start_dt = datetime(*timeinput[0, :6].astype(int))
            end_dt = datetime(*timeinput[1, :6].astype(int))

            for filepath in all_files:
                fname = filepath.name
                match = pattern.search(fname)
                if not match:
                    continue

                file_start = datetime.strptime(match.group(1), '%Y%m%d_%H%M%S')
                file_end = datetime.strptime(match.group(2), '%Y%m%d_%H%M%S')

                if file_end >= start_dt and file_start <= end_dt:
                    ncfiles.append(filepath)

        if not ncfiles:
            return self._empty_jason3_result()

        ncfiles = list(set(ncfiles))
        ncfiles.sort()

        longitude_list = []
        latitude_list = []
        wind_list = []
        swh_list = []
        time_list = []

        for filepath in ncfiles:
            try:
                with Dataset(filepath, 'r') as nc:
                    data_group = nc.groups['data_01']

                    latitude_tmp = data_group.variables['latitude'][:].astype(float)
                    longitude_tmp = data_group.variables['longitude'][:].astype(float)
                    time_tmp = data_group.variables['time'][:].astype(float)
                    wind_tmp = data_group.variables['wind_speed_alt_mle3'][:].astype(float)

                    ku_group = data_group.groups['ku']
                    swh_tmp = ku_group.variables['swh_ocean'][:].astype(float)

                    longitude_tmp = ((longitude_tmp + 180.0) % 360.0) - 180.0

                    idx_spatial = ((longitude_tmp >= lon_lat[0]) & (longitude_tmp <= lon_lat[1]) &
                                   (latitude_tmp >= lon_lat[2]) & (latitude_tmp <= lon_lat[3]))

                    if np.sum(idx_spatial) == 0:
                        continue

                    latitude_tmp = latitude_tmp[idx_spatial]
                    longitude_tmp = longitude_tmp[idx_spatial]
                    wind_tmp = wind_tmp[idx_spatial]
                    swh_tmp = swh_tmp[idx_spatial]
                    time_tmp = time_tmp[idx_spatial]

                    time_tmp = time_tmp / (24 * 60 * 60)
                    ref_date = datetime(2000, 1, 1)
                    start_days = (start_dt - ref_date).total_seconds() / (24 * 60 * 60)
                    end_days = (end_dt - ref_date).total_seconds() / (24 * 60 * 60)
                    idx_time = (time_tmp >= start_days) & (time_tmp <= end_days)
                    if np.sum(idx_time) == 0:
                        continue
                    latitude_tmp = latitude_tmp[idx_time]
                    longitude_tmp = longitude_tmp[idx_time]
                    wind_tmp = wind_tmp[idx_time]
                    swh_tmp = swh_tmp[idx_time]
                    time_tmp = time_tmp[idx_time]

                    invalid_values = [0, 32767, 9999, 65535]

                    valid_idx = (~np.isnan(swh_tmp) &
                                 ~np.isnan(wind_tmp) &
                                 ~np.isin(swh_tmp, invalid_values) &
                                 ~np.isin(wind_tmp, invalid_values))

                    if np.sum(valid_idx) == 0:
                        continue

                    latitude_tmp = latitude_tmp[valid_idx]
                    longitude_tmp = longitude_tmp[valid_idx]
                    wind_tmp = wind_tmp[valid_idx]
                    swh_tmp = swh_tmp[valid_idx]
                    time_tmp = time_tmp[valid_idx]

                    if len(latitude_tmp) > 0:
                        latitude_list.append(latitude_tmp)
                        longitude_list.append(longitude_tmp)
                        wind_list.append(wind_tmp)
                        swh_list.append(swh_tmp)
                        time_list.append(time_tmp)

            except Exception as e:
                # 只在 verbose 模式下输出错误，减少日志更新
                if verbose:
                    self.log_signal.emit(f'Error reading {filepath}: {str(e)}')
                continue

        if not latitude_list:
            return self._empty_jason3_result()

        latitude = np.concatenate(latitude_list)
        longitude = np.concatenate(longitude_list)
        wind = np.concatenate(wind_list)
        swh = np.concatenate(swh_list)
        time_days = np.concatenate(time_list)

        reference_date = datetime(2000, 1, 1)
        ja_time = np.zeros((len(time_days), 6))

        for i, days in enumerate(time_days):
            dt = reference_date + timedelta(days=float(days))
            ja_time[i] = [dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second]

        jason = {
            'ja_time': ja_time,
            'longitude': longitude,
            'latitude': latitude,
            'wind': wind,
            'swh': swh
        }

        # 只在 verbose 模式下输出成功信息，减少日志更新
        if verbose:
            self.log_signal.emit(f'Success: Total {len(latitude)} points loaded')
            self.log_signal.emit('============================================================')

        return jason

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


    def match_ww3_jason3(self, ww3_file, jason3_path, out_folder, max_dist_deg=0.125, time_window_hours=0.5):
        """匹配 WW3 和 Jason-3 数据"""
        self.log_signal.emit('Reading WW3 data...')
        with Dataset(ww3_file, 'r') as nc:
            ww3_lon = nc.variables['longitude'][:].astype(float)
            ww3_lat = nc.variables['latitude'][:].astype(float)
            ww3_swh = nc.variables['hs'][:].astype(float)
            time_ww3 = nc.variables['time'][:].astype(float)

        ww3_lon = ((ww3_lon + 180.0) % 360.0) - 180.0
        ww3_swh[(ww3_swh < 0) | (ww3_swh > 50)] = np.nan

        self.log_signal.emit(f"WW3 lon range: [{ww3_lon.min():.2f}, {ww3_lon.max():.2f}]")
        self.log_signal.emit(f"WW3 lat range: [{ww3_lat.min():.2f}, {ww3_lat.max():.2f}]")
        self.log_signal.emit(f"WW3 time steps: {len(time_ww3)}")

        nx = len(ww3_lon)
        ny = len(ww3_lat)
        lon_grid, lat_grid = np.meshgrid(ww3_lon, ww3_lat, indexing='xy')
        lon1 = lon_grid.ravel()
        lat1 = lat_grid.ravel()

        reference_date = datetime(1990, 1, 1, 0, 0, 0)
        timesec = [reference_date + timedelta(days=float(t)) for t in time_ww3]
        T = np.array([dt.strftime('%Y%m%d%H%M%S') for dt in timesec])
        self.log_signal.emit(f"WW3 time range: {timesec[0]} to {timesec[-1]}")

        lon_lat = [ww3_lon.min(), ww3_lon.max(), ww3_lat.min(), ww3_lat.max()]
        self.log_signal.emit(f"Matching region: lon[{lon_lat[0]}, {lon_lat[1]}], lat[{lon_lat[2]}, {lon_lat[3]}]")

        swh_jason3 = []
        swh_ww3 = []

        self.log_signal.emit(f"🔄 处理 {len(T)} 个时间步，这可能需要一些时间...")
        total_matched = 0
        # 使用 log_update_last_line 来更新进度，避免频繁追加新行
        # 根据时间步数量动态调整更新频率：时间步越多，更新越不频繁
        update_interval = max(1, len(T) // 50)  # 最多更新50次
        if update_interval < 10:
            update_interval = 10  # 至少每10个时间步更新一次
        elif update_interval > 50:
            update_interval = 50  # 最多每50个时间步更新一次

        for i in range(len(T)):
            # 动态调整更新频率，减少日志更新
            if (i + 1) % update_interval == 0 or i == 0:
                progress_pct = int((i + 1) / len(T) * 100)
                # 使用更新最后一行而不是追加新行，减少UI操作
                self.log_update_last_line_signal.emit(f"📊 进度: {i + 1}/{len(T)} ({progress_pct}%) - 已匹配 {total_matched} 个点")

            ww3_swh1 = ww3_swh[i, :, :].ravel()
            year = int(T[i][0:4])
            month = int(T[i][4:6])
            day = int(T[i][6:8])
            hour = int(T[i][8:10])

            window = time_window_hours
            timeinput = np.zeros((2, 6))
            start_dt = datetime(year, month, day, hour, 0, 0) - timedelta(hours=window)
            end_dt = datetime(year, month, day, hour, 0, 0) + timedelta(hours=window)
            timeinput[0, :] = [start_dt.year, start_dt.month, start_dt.day, start_dt.hour, start_dt.minute,
                               start_dt.second]
            timeinput[1, :] = [end_dt.year, end_dt.month, end_dt.day, end_dt.hour, end_dt.minute, end_dt.second]

            # 在循环中调用时，不输出详细日志（verbose=False），减少日志更新
            jason3 = self.read_jason3_chen(lon_lat, timeinput, jason3_path, verbose=False)
            j3_lat = jason3['latitude']
            j3_lon = jason3['longitude']
            j3_swh = jason3['swh']

            if len(j3_lat) == 0:
                continue

            # 优化：只处理有效的WW3数据点，跳过NaN值
            valid_mask = ~np.isnan(ww3_swh1)
            valid_indices = np.where(valid_mask)[0]

            if len(valid_indices) == 0:
                continue

            # 批量计算所有有效点到所有Jason-3点的距离
            for j in valid_indices:
                distances = self.haversine_distance(lat1[j], lon1[j], j3_lat, j3_lon)
                min_dist = np.min(distances)
                if min_dist < max_dist_deg:
                    index = np.argmin(distances)
                    swh_jason3.append(j3_swh[index])
                    swh_ww3.append(ww3_swh1[j])
                    total_matched += 1

        swh_jason3 = np.array(swh_jason3)
        swh_ww3 = np.array(swh_ww3)

        self.log_signal.emit('============================================================')
        self.log_signal.emit('Matching completed!')
        self.log_signal.emit(f'Total matched points: {len(swh_jason3)}')

        os.makedirs(out_folder, exist_ok=True)

        if len(swh_jason3) > 0:
            x = swh_jason3
            y = swh_ww3
            diff = np.abs(y - x)
            valid = (~np.isnan(x)) & (~np.isnan(y))
            xv = x[valid]
            yv = y[valid]
            dv = diff[valid]
            cutoff = 30
            idx = dv <= cutoff
            xf = xv[idx]
            yf = yv[idx]
            if len(xf) == 0 or len(yf) == 0:
                xf = xv
                yf = yv

            bias = float(np.nanmean(yf - xf)) if len(yf) > 0 else np.nan
            rmse = float(np.sqrt(np.nanmean((yf - xf) ** 2))) if len(yf) > 0 else np.nan
            corr = float(np.corrcoef(xf, yf)[0, 1]) if (
                        len(xf) > 1 and np.nanstd(xf) > 0 and np.nanstd(yf) > 0) else np.nan

            np.savez(os.path.join(out_folder, 'matching_results.npz'), swh_jason3=swh_jason3, swh_ww3=swh_ww3)
            self.log_signal.emit(f"Results saved to {os.path.join(out_folder, 'matching_results.npz')}")

            try:
                # 切换到 Agg 后端
                original_backend = matplotlib.get_backend()
                matplotlib.use("Agg")

                max_val = float(np.nanmax(np.concatenate([xf, yf]))) if len(xf) > 0 else 10.0
                upper = max(1.0, max_val * 1.02)
                fig = plt.figure(figsize=(8, 8), dpi=300)
                plt.scatter(xf, yf, s=8, c='royalblue', alpha=0.6)
                plt.xlabel('Jason-3 (m)')
                plt.ylabel('WW3 (m)')
                plt.title('Linear fit of simulation and observation')
                plt.xlim([0, upper])
                plt.ylim([0, upper])
                plt.plot([0, upper], [0, upper], 'k--', linewidth=1.5)
                r_text = f"R = {corr:.3f}" if np.isfinite(corr) else "R = N/A"
                txt = f"{r_text}\nBias = {bias:.3f}\nRMSE = {rmse:.3f}"
                plt.text(0.05 * upper, 0.95 * upper, txt, va='top')
                plt.grid(False)
                plt.tight_layout()

                # 保存到 photo 文件夹
                photo_folder = os.path.join(out_folder, 'photo')
                os.makedirs(photo_folder, exist_ok=True)
                out_png = os.path.join(photo_folder, 'ww3_jason3_comparison.png')
                plt.savefig(out_png, dpi=300, bbox_inches='tight')
                plt.close(fig)

                # 恢复后端
                matplotlib.use(original_backend)
            except ImportError:
                self.log_signal.emit('Matplotlib not available, skipping plots')
            return {'bias': bias, 'rmse': rmse, 'corr': corr, 'count': len(swh_jason3)}
        else:
            self.log_signal.emit('No matching points found. Please check:')
            self.log_signal.emit('  1. Jason-3 data temporal coverage')
            self.log_signal.emit('  2. Jason-3 data spatial coverage in the region')
            self.log_signal.emit('  3. Time window settings')
            return {'bias': None, 'rmse': None, 'corr': None, 'count': 0}




