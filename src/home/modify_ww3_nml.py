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
from setting.language_manager import tr
from plot.workers import _match_ww3_jason3_worker, _run_jason3_swh_worker, _make_wave_maps_worker

class ModifyWW3NML:
    """WW3 Namelist 修改功能模块 - 负责WW3配置文件的修改和管理"""
    
    def _is_spectral_point_mode(self):
        """检查当前是否为谱空间逐点计算模式"""
        calc_mode = getattr(self, 'calc_mode_var', tr("step3_region_scale", "区域尺度计算"))
        spectral_text = tr("step3_spectral_point", "谱空间逐点计算")
        return calc_mode == spectral_text or calc_mode == "谱空间逐点计算"

    # ==================== 主入口方法 ====================

    def _validate_and_update_forcing_field_paths(self):
        """验证并更新强迫场文件路径，确保文件在新工作目录中"""
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            return
        
        # 检查并更新每个强迫场文件路径
        forcing_fields = {
            'selected_origin_file': ['wind'],
            'selected_current_file': ['current'],
            'selected_level_file': ['level'],
            'selected_ice_file': ['ice']
        }
        
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
                
                # 如果文件路径存在，检查是否在新工作目录中
                if os.path.exists(file_path):
                    abs_file_path = os.path.abspath(file_path)
                    # 使用 commonpath 检查文件是否在新工作目录中
                    try:
                        common_path = os.path.commonpath([abs_file_path, abs_selected_folder])
                        if common_path != abs_selected_folder:
                            # 文件不在新工作目录中，尝试在新工作目录中查找同名文件
                            file_name = os.path.basename(file_path)
                            new_file_path = os.path.join(self.selected_folder, file_name)
                            
                            if os.path.exists(new_file_path):
                                # 新工作目录中有同名文件，更新路径
                                setattr(self, attr_name, new_file_path)
                            else:
                                # 新工作目录中没有同名文件，尝试查找包含关键词的文件
                                found = False
                                import glob
                                for keyword in keywords:
                                    pattern = os.path.join(self.selected_folder, f"*{keyword}*.nc")
                                    matching_files = glob.glob(pattern)
                                    if matching_files:
                                        # 优先选择包含所有关键词的文件（多场并存文件）
                                        best_match = None
                                        for match_file in matching_files:
                                            match_name = os.path.basename(match_file).lower()
                                            # 如果文件名包含所有关键词，优先选择
                                            if all(kw.lower() in match_name for kw in keywords):
                                                best_match = match_file
                                                break
                                        # 如果没有找到包含所有关键词的文件，使用第一个匹配的文件
                                        if not best_match and matching_files:
                                            best_match = matching_files[0]
                                        
                                        if best_match:
                                            setattr(self, attr_name, best_match)
                                            found = True
                                            break
                                
                                if not found:
                                    # 新工作目录中没有找到对应的文件，清除引用并取消复选框
                                    setattr(self, attr_name, None)
                                    checkbox_key = attr_to_checkbox.get(attr_name)
                                    if checkbox_key and hasattr(self, 'forcing_field_checkboxes') and checkbox_key in self.forcing_field_checkboxes:
                                        checkbox = self.forcing_field_checkboxes[checkbox_key]['checkbox']
                                        checkbox.setChecked(False)
                    except ValueError:
                        # 路径不在同一驱动器上（Windows）或无法比较，清除引用
                        setattr(self, attr_name, None)
                        checkbox_key = attr_to_checkbox.get(attr_name)
                        if checkbox_key and hasattr(self, 'forcing_field_checkboxes') and checkbox_key in self.forcing_field_checkboxes:
                            checkbox = self.forcing_field_checkboxes[checkbox_key]['checkbox']
                            checkbox.setChecked(False)
                else:
                    # 文件不存在，尝试在新工作目录中查找
                    file_name = os.path.basename(file_path) if isinstance(file_path, str) else None
                    if file_name:
                        new_file_path = os.path.join(self.selected_folder, file_name)
                        if os.path.exists(new_file_path):
                            setattr(self, attr_name, new_file_path)
                        else:
                            # 尝试查找包含关键词的文件
                            found = False
                            import glob
                            for keyword in keywords:
                                pattern = os.path.join(self.selected_folder, f"*{keyword}*.nc")
                                matching_files = glob.glob(pattern)
                                if matching_files:
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
                                # 新工作目录中没有找到对应的文件，清除引用并取消复选框
                                setattr(self, attr_name, None)
                                checkbox_key = attr_to_checkbox.get(attr_name)
                                if checkbox_key and hasattr(self, 'forcing_field_checkboxes') and checkbox_key in self.forcing_field_checkboxes:
                                    checkbox = self.forcing_field_checkboxes[checkbox_key]['checkbox']
                                    checkbox.setChecked(False)
                    else:
                        # 文件路径无效，清除引用并取消复选框
                        setattr(self, attr_name, None)
                        checkbox_key = attr_to_checkbox.get(attr_name)
                        if checkbox_key and hasattr(self, 'forcing_field_checkboxes') and checkbox_key in self.forcing_field_checkboxes:
                            checkbox = self.forcing_field_checkboxes[checkbox_key]['checkbox']
                            checkbox.setChecked(False)

    def modify_ww3_file(self):
        """应用所有参数（合并第四步和第五步的功能）"""
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return
        
        # 验证并更新强迫场文件路径（确保文件在新工作目录中）
        self._validate_and_update_forcing_field_paths()

        # 检查是否选择了谱分区输出方案（用于后续显示日志）
        has_output_scheme = self._get_output_scheme_var_list() is not None

        # 检查当前计算模式是否为航迹模式
        track_text = tr("step3_track_mode", "航迹模式")
        is_track_mode = False
        
        # 优先检查 calc_mode_combo 的当前选择（这是用户界面上的实际值）
        if hasattr(self, 'calc_mode_combo') and self.calc_mode_combo:
            combo_text = self.calc_mode_combo.currentText()
            if combo_text == track_text or combo_text == "航迹模式":
                is_track_mode = True
        else:
            # 如果没有 calc_mode_combo，检查 calc_mode_var
            calc_mode = getattr(self, 'calc_mode_var', '')
            if calc_mode == track_text or calc_mode == "航迹模式":
                is_track_mode = True

        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        if grid_type == nested_text or grid_type == "嵌套网格":
            # 嵌套网格模式：合并所有操作，外网格和内网格各自在一个分隔线下完成
            self._apply_all_params_nested(has_output_scheme)
        else:
            # 普通网格模式：按原流程处理
            # 先复制文件（这样后续修改才能应用到工作目录的文件）
            self.copy_public_and_meta_to_grid()

            # 在复制文件后，应用谱分区输出方案到工作目录
            applied_scheme = False
            if has_output_scheme:
                applied_scheme = self._apply_output_scheme_to_dir(self.selected_folder)
                if applied_scheme:
                    self.log(tr("output_scheme_applied", "✅ 已修改 ww3_shel，ww3_ounf 的谱分区输出方案"))
            
            # 更新 server.sh 文件
            self.modify_server_sh_file()
            # 检查是否需要修改 namelists.nml 中的 E3D 参数
            self._modify_namelists_e3d_if_needed()
            # 检查是否需要修改 ww3_ounp.nml（谱空间逐点计算模式）
            self._modify_ww3_ounp_if_needed()
            # 再执行第五步的功能：应用 WW3 参数
            self.apply_ww3_params()
            # 修改 ww3_prnc.nml 中的时间范围
            self._modify_ww3_prnc_times()
            # 根据选择的强迫场生成对应的 ww3_prnc_*.nml 文件
            self._generate_forcing_field_prnc_files()
            # 修改 ww3_shel.nml 中的 INPUT%FORCING%* 设置
            self._modify_ww3_shel_forcing_inputs()
        
        # 在复制和应用参数之后，如果是航迹模式，生成 track_i.ww3 并修改 ww3_shel.nml
        # 这样可以确保 DATE%TRACK 不会被 copy_public_files() 覆盖
        if is_track_mode:
            self._generate_track_i_ww3_file()
            self._modify_ww3_shel_date_track()
            self._modify_ww3_trnc_track()


    # ==================== 复制 ww3 文件和应用 grid.meta 参数到 ww3_grid.nml ====================

    def copy_public_and_meta_to_grid(self):

        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))

        # 嵌套网格模式：所有操作在 _apply_all_params_nested 中完成，这里跳过
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        if grid_type == nested_text or grid_type == "嵌套网格":
            return

        # 普通网格模式：复制文件并同步 meta
        self.copy_public_files()
        self._sync_grid_meta_to_grid_nml_in_dir(self.selected_folder)




    def _load_slurm_params_from_server_sh(self):
        """从工作目录中的 server.sh 文件读取 slurm 参数并设置到 UI"""
        if not hasattr(self, 'selected_folder') or not self.selected_folder:
            return
        
        # 防止重复执行：检查是否已经加载过相同的参数
        server_sh_path = os.path.join(self.selected_folder, "server.sh")
        if not os.path.exists(server_sh_path):
            return
        
        # 使用文件修改时间作为标记，避免重复加载
        if not hasattr(self, '_last_server_sh_mtime'):
            self._last_server_sh_mtime = {}
        
        try:
            current_mtime = os.path.getmtime(server_sh_path)
            if server_sh_path in self._last_server_sh_mtime:
                if self._last_server_sh_mtime[server_sh_path] == current_mtime:
                    # 文件未修改，跳过
                    return
            self._last_server_sh_mtime[server_sh_path] = current_mtime
        except:
            pass
        
        try:
            with open(server_sh_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # 解析 slurm 参数
            cpu = None
            num_n = None
            num_N = None
            st_version = None
            
            for line in lines:
                line_stripped = line.strip()
                # 解析 CPU/partition: #SBATCH -p CPU6240R
                if line_stripped.startswith("#SBATCH -p"):
                    parts = line_stripped.split()
                    # parts = ['#SBATCH', '-p', 'CPU6240R']
                    if len(parts) >= 3:
                        cpu = parts[2]
                # 解析总核数: #SBATCH -n 48
                elif line_stripped.startswith("#SBATCH -n"):
                    parts = line_stripped.split()
                    # parts = ['#SBATCH', '-n', '48']
                    if len(parts) >= 3:
                        num_n = parts[2]
                # 解析节点数: #SBATCH -N 1
                elif line_stripped.startswith("#SBATCH -N"):
                    parts = line_stripped.split()
                    # parts = ['#SBATCH', '-N', '1']
                    if len(parts) >= 3:
                        num_N = parts[2]
                # 解析 ST 版本: #wavewatch3--ST6A
                elif line_stripped.startswith("#wavewatch3--"):
                    # 提取 ST 版本名称，例如 "#wavewatch3--ST6A" -> "ST6A"
                    st_version = line_stripped.replace("#wavewatch3--", "").strip()
            
            # 更新 UI 中的 slurm 参数
            updated = False
            if cpu and hasattr(self, 'cpu_combo') and self.cpu_combo:
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
            
            # 更新 ST 版本
            if st_version and hasattr(self, 'st_combo') and self.st_combo:
                # 检查 ST 版本是否在选项列表中
                items = [self.st_combo.itemText(i) for i in range(self.st_combo.count())]
                if st_version in items:
                    self.st_combo.setCurrentText(st_version)
                    self.st_var = st_version
                    updated = True
            
            # 检查是否为嵌套网格模式
            coarse_dir = os.path.join(self.selected_folder, "coarse")
            fine_dir = os.path.join(self.selected_folder, "fine")
            is_nested_grid = (os.path.isdir(coarse_dir) and os.path.isdir(fine_dir))
            
            if is_nested_grid:
                # 嵌套网格模式：分别读取外网格和内网格的精度值
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
                                    start_date = match.group(1)  # 使用外网格的起始日期
                                    coarse_compute_precision = match.group(2)
                                    end_date = match.group(3)  # 使用外网格的结束日期
                                    break
                    except:
                        pass
                
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
                                    # 内网格的日期范围通常与外网格相同，但这里只读取计算精度
                                    fine_compute_precision = match.group(2)
                                    break
                    except:
                        pass
                
                # 更新外网格的输出精度和计算精度
                if coarse_output_precision and hasattr(self, 'output_precision_edit') and self.output_precision_edit:
                    self.output_precision_edit.setText(coarse_output_precision)
                    updated = True
                
                if coarse_compute_precision and hasattr(self, 'shel_step_edit') and self.shel_step_edit:
                    self.shel_step_edit.setText(coarse_compute_precision)
                    updated = True
                
                # 更新内网格的输出精度和计算精度
                if fine_output_precision and hasattr(self, 'inner_output_precision_edit') and self.inner_output_precision_edit:
                    self.inner_output_precision_edit.setText(fine_output_precision)
                    updated = True
                
                if fine_compute_precision and hasattr(self, 'inner_shel_step_edit') and self.inner_shel_step_edit:
                    self.inner_shel_step_edit.setText(fine_compute_precision)
                    updated = True
                
                # 更新起始和结束日期（使用外网格的日期）
                if start_date and hasattr(self, 'shel_start_edit') and self.shel_start_edit:
                    self.shel_start_edit.setText(start_date)
                    updated = True
                
                if end_date and hasattr(self, 'shel_end_edit') and self.shel_end_edit:
                    self.shel_end_edit.setText(end_date)
                    updated = True
            else:
                # 普通网格模式：从工作目录读取
                # 读取 ww3_ounf.nml 获取输出精度
                output_precision = None
                ounf_path = os.path.join(self.selected_folder, "ww3_ounf.nml")
                if os.path.exists(ounf_path):
                    try:
                        with open(ounf_path, "r", encoding="utf-8") as f:
                            ounf_lines = f.readlines()
                        
                        for line in ounf_lines:
                            line_stripped = line.strip()
                            # 跳过注释行
                            if line_stripped.startswith("!") or line_stripped.startswith("#"):
                                continue
                            # 解析 FIELD%TIMESTRIDE = '3600'
                            if "FIELD%TIMESTRIDE" in line and "=" in line:
                                # 使用正则表达式提取引号中的值
                                match = re.search(r"FIELD%TIMESTRIDE\s*=\s*['\"](\d+)['\"]", line, re.IGNORECASE)
                                if match:
                                    output_precision = match.group(1)
                                    break
                    except:
                        pass
                
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
                            # 跳过注释行
                            if line_stripped.startswith("!") or line_stripped.startswith("#"):
                                continue
                            # 解析 DATE%FIELD = '20250103 000000' '1800' '20250105 235959'
                            if "DATE%FIELD" in line and "=" in line:
                                # 匹配格式：DATE%FIELD = '20250103 000000' '1800' '20250105 235959'
                                match = re.search(r"DATE%FIELD\s*=\s*['\"](\d{8})\s+\d{6}['\"]\s+['\"](\d+)['\"]\s+['\"](\d{8})\s+\d{6}['\"]", line, re.IGNORECASE)
                                if match:
                                    start_date = match.group(1)  # '20250103'
                                    compute_precision = match.group(2)  # '1800'
                                    end_date = match.group(3)  # '20250105'
                                    break
                    except:
                        pass
                
                # 更新输出精度
                if output_precision and hasattr(self, 'output_precision_edit') and self.output_precision_edit:
                    self.output_precision_edit.setText(output_precision)
                    updated = True
                
                # 更新计算精度
                if compute_precision and hasattr(self, 'shel_step_edit') and self.shel_step_edit:
                    self.shel_step_edit.setText(compute_precision)
                    updated = True
                
                # 更新起始日期
                if start_date and hasattr(self, 'shel_start_edit') and self.shel_start_edit:
                    self.shel_start_edit.setText(start_date)
                    updated = True
                
                # 更新结束日期
                if end_date and hasattr(self, 'shel_end_edit') and self.shel_end_edit:
                    self.shel_end_edit.setText(end_date)
                    updated = True
            
            if updated:
                st_info = f", {tr('step4_st_version_label', 'ST版本')}={st_version}" if st_version else ""
                ww3_info = ""
                if is_nested_grid:
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
            # 静默失败，不显示错误日志
            pass

    def modify_server_sh_file(self):
        """更新 server.sh 文件的具体实现"""
        start_date = self.shel_start_edit.text().strip()

        if not (start_date.isdigit() and len(start_date) == 8):
            self.log(tr("date_format_error", "❌ 起始日期格式错误，应为 YYYYMMDD。"))
            return

        # casename 只能是 202504 这样的，未知原因
        start_year_month = int(start_date[:6])

        num_n = self.num_n_edit.text().strip()
        num_N = self.num_N_edit.text().strip()
        cpu = self.cpu_var
        
        # 获取 server.sh 路径
        from setting.config import load_config
        current_config = load_config()
        server_script_path = current_config.get("SERVER_SCRIPT_PATH", "").strip()
        
        # 如果为空，使用默认路径 ./public/ww3/server.sh（相对于项目根目录）
        if not server_script_path:
            # __file__ 是 main/home/modify_ww3_nml.py，需要回到项目根目录
            script_dir = os.path.dirname(os.path.abspath(__file__))  # main/home
            main_dir = os.path.dirname(script_dir)  # main
            project_root = os.path.dirname(main_dir)  # 项目根目录
            server_script_path = os.path.normpath(os.path.join(project_root, "public", "ww3", "server.sh"))
        else:
            server_script_path = os.path.normpath(server_script_path)
        
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

            # 获取 ST 版本信息
            if not hasattr(self, 'st_var') or not self.st_var:
                self.log(tr("st_version_not_selected", "❌ 未选择 ST 版本，请在设置页面配置 ST 版本"))
                return
            
            selected_st = self.st_var
            st_versions = current_config.get("ST_VERSIONS", [])
            
            # 查找选中的 ST 版本路径
            st_name = selected_st
            st_path = None
            
            if st_versions and isinstance(st_versions, list):
                for version in st_versions:
                    if isinstance(version, dict) and version.get("name") == selected_st:
                        st_path = version.get("path", "")
                        break
            
            if not st_path:
                self.log(tr("st_version_path_not_found", "❌ 未找到 ST 版本 {version} 的路径配置，请在设置页面配置 ST 版本路径").format(version=selected_st))
                return
            
            # 构建 ST 版本路径行
            st_path_line = f"{st_path}/exe"
            st_comment = f"#wavewatch3--{st_name}\n"
            st_export = f"export PATH={st_path_line}:$PATH\n"

            new_lines = []
            time_found = False
            st_path_inserted = False
            
            i = 0
            while i < len(lines):
                line = lines[i].replace('\r', '')  # 清理 Windows 换行符
                line_stripped = line.strip()
                
                # 修改 SLURM 配置参数
                if line_stripped.startswith("#SBATCH -J"):
                    new_lines.append(f"#SBATCH -J {start_year_month}\n")
                elif line_stripped.startswith("#SBATCH -p"):
                    new_lines.append(f"#SBATCH -p {cpu}\n")
                elif line_stripped.startswith("#SBATCH -n"):
                    new_lines.append(f"#SBATCH -n {num_n}\n")
                elif line_stripped.startswith("#SBATCH -N"):
                    new_lines.append(f"#SBATCH -N {num_N}\n")
                # 检查是否找到 #SBATCH --time
                elif line_stripped.startswith("#SBATCH --time"):
                    time_found = True
                    new_lines.append(line)
                    # 跳过后续的空行和已存在的 ST 版本路径
                    i += 1
                    while i < len(lines):
                        next_line = lines[i].replace('\r', '')
                        next_stripped = next_line.strip()
                        # 跳过空行
                        if next_stripped == "":
                            i += 1
                            continue
                        # 跳过已存在的 ST 版本注释
                        if next_stripped.startswith("#wavewatch3--"):
                            i += 1
                            continue
                        # 跳过已存在的 export PATH（包含 /model/exe 或 /model: 的）
                        if next_stripped.startswith("export PATH=") and ("/model/exe" in next_line or "/model:" in next_line):
                            i += 1
                            continue
                        # 遇到其他内容，停止跳过
                        break
                    # 在 #SBATCH --time 后面添加 ST 版本路径
                    new_lines.append("\n")
                    new_lines.append(st_comment)
                    new_lines.append(st_export)
                    st_path_inserted = True
                    continue
                # 如果已经插入了 ST 版本路径，跳过后续可能存在的旧版本路径
                elif st_path_inserted:
                    # 跳过已存在的 ST 版本注释（如果不在正确位置）
                    if line_stripped.startswith("#wavewatch3--"):
                        i += 1
                        continue
                    # 跳过已存在的 export PATH（包含 /model/exe 或 /model: 的，如果不在正确位置）
                    if line_stripped.startswith("export PATH=") and ("/model/exe" in line or "/model:" in line):
                        i += 1
                        continue
                    new_lines.append(line)
                # 修改 MPI_NPROCS
                elif line_stripped.startswith("MPI_NPROCS="):
                    new_lines.append(f"MPI_NPROCS={num_n}\n")
                # 修改 CASENAME
                elif line_stripped.startswith("CASENAME="):
                    new_lines.append(f"CASENAME={start_year_month}\n")
                else:
                    new_lines.append(line)
                i += 1

            # 写回文件时使用二进制模式，确保使用 \n 而不是 \r\n
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


    # ==================== Meta 到 Grid NML 同步 ====================

    def sync_grid_meta_to_grid_nml(self, target_dir=None):
        """从 grid.meta 提取参数并同步到 ww3_grid.nml（普通网格模式）"""
        if target_dir is None:
            target_dir = self.selected_folder
        if not target_dir or not isinstance(target_dir, str):
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return
        self._sync_grid_meta_to_grid_nml_in_dir(target_dir)


    def _sync_grid_meta_to_grid_nml_in_dir(self, target_dir, grid_label=""):
        """在指定目录中从 grid.meta 提取 3 行 → 替换 ww3_grid.nml 中 &RECT_NML 的参数"""
        if not target_dir or not isinstance(target_dir, str):
            return

        meta_path = os.path.join(target_dir, "grid.meta")
        nml_path = os.path.join(target_dir, "ww3_grid.nml")

        if not os.path.exists(meta_path):
            self.log(tr("meta_file_not_found", "⚠️ 未找到文件：{path}，跳过 meta to grid 转换").format(path=meta_path))
            return


        try:
            # 1. 读取 meta 文件
            with open(meta_path, "r", encoding="utf-8") as f:
                meta_lines = f.readlines()

            # 查找 RECT 块
            # 尝试多种搜索模式，因为 grid.meta 格式可能有变化
            target_index_meta = None
            for i, line in enumerate(meta_lines):
                # 模式1: 包含 'RECT'、'T' 和 'NONE'（原始模式）
                if "'RECT'" in line and "T" in line and "'NONE'" in line:
                    target_index_meta = i
                    break
                # 模式2: 只包含 'RECT'（更宽松的模式）
                elif "'RECT'" in line or '"RECT"' in line or "RECT" in line.upper():
                    # 检查是否是网格类型行（通常在注释后）
                    stripped = line.strip()
                    if stripped.startswith("'") or stripped.startswith('"') or len(stripped.split()) <= 3:
                        target_index_meta = i
                        break

            if target_index_meta is None:
                self.log(tr("rect_block_not_found", "⚠️ grid.meta 中未找到 RECT 块"))
                self.log(tr("file_path", "   文件路径：{path}").format(path=meta_path))
                self.log(tr("file_line_count", "   文件行数：{count}").format(count=len(meta_lines)))
                # 输出前50行用于调试
                if len(meta_lines) > 0:
                    self.log(tr("file_preview_50_lines", "   文件前50行预览："))
                    for i, line in enumerate(meta_lines[:50]):
                        if "'RECT'" in line or '"RECT"' in line or "RECT" in line.upper():
                            self.log(tr("file_line_preview", "   第{line_num}行: {content}").format(line_num=i+1, content=line.strip()))
                return

            if target_index_meta + 3 >= len(meta_lines):
                self.log(tr("rect_block_insufficient", "⚠️ grid.meta 中 RECT 块内容不足（找到 RECT 在第 {line} 行，但文件只有 {total} 行）").format(line=target_index_meta + 1, total=len(meta_lines)))
                return

            # 提取三行参数
            L1 = meta_lines[target_index_meta + 1].split()
            L2 = meta_lines[target_index_meta + 2].split()
            L3 = meta_lines[target_index_meta + 3].split()

            NX, NY = int(L1[0]), int(L1[1])
            SX, SY, SF = float(L2[0]), float(L2[1]), float(L2[2])
            X0, Y0, SF0 = float(L3[0]), float(L3[1]), float(L3[2])

            # 2. 读取并修改 nml 文件
            with open(nml_path, "r", encoding="utf-8") as f:
                nml_lines = f.readlines()

            new_lines = []
            in_rect = False

            for line in nml_lines:
                if "&RECT_NML" in line:
                    in_rect = True
                    new_lines.append(line)
                    continue

                if in_rect:
                    if "/" in line:
                        in_rect = False
                        new_lines.append(line)
                        continue

                    # 替换参数
                    if "RECT%NX" in line:
                        new_lines.append(f"  RECT%NX           =  {NX}\n")
                        continue
                    if "RECT%NY" in line:
                        new_lines.append(f"  RECT%NY           =  {NY}\n")
                        continue
                    if "RECT%SX" in line:
                        new_lines.append(f"  RECT%SX           =  {SX:.6f}\n")
                        continue
                    if "RECT%SY" in line:
                        new_lines.append(f"  RECT%SY           =  {SY:.6f}\n")
                        continue
                    if "RECT%SF" in line:
                        new_lines.append(f"  RECT%SF           =  {SF:.6f}\n")
                        continue
                    if "RECT%X0" in line:
                        new_lines.append(f"  RECT%X0           =  {X0:.6f}\n")
                        continue
                    if "RECT%Y0" in line:
                        new_lines.append(f"  RECT%Y0           =  {Y0:.6f}\n")
                        continue
                    if "RECT%SF0" in line:
                        new_lines.append(f"  RECT%SF0          =  {SF0:.6f}\n")
                        continue

                new_lines.append(line)

            # 3. 写回文件
            with open(nml_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            prefix = f"{grid_label} " if grid_label else ""
            self.log(f"{prefix}{tr('step4_grid_meta_synced', '✅ 已成功同步 grid.meta 参数到 ww3_grid.nml')}")

        except Exception as e:
            self.log(tr("sync_failed", "❌ 同步失败：{error}").format(error=e))


    # ==================== WW3 参数应用 ====================

    def apply_ww3_params(self):
        """应用 WW3 运行参数（第五步的功能）"""
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))

        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        if grid_type == nested_text or grid_type == "嵌套网格":
            self._apply_ww3_params_nested()
        else:
            self._apply_ww3_params_normal()


    def _copy_public_special_files_to_workdir(self):
        """复制公共文件（server.sh 和 ww3_multi.nml）到工作目录"""
        # 获取项目根目录下的 public/ww3 路径
        # BASE_DIR 已经在文件开头通过 from setting.config import * 导入
        src_dir = os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "public", "ww3")
        if not os.path.exists(src_dir):
            self.log(tr("directory_not_found", "⚠️ 未找到目录：{path}").format(path=src_dir))
            return

        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")

        copied_files = []

        try:
            # 复制 server.sh（从配置路径或默认路径）
            from setting.config import load_config
            current_config = load_config()
            server_script_path = current_config.get("SERVER_SCRIPT_PATH", "").strip()
            
            # 如果为空，使用默认路径 ./public/ww3/server.sh（相对于项目根目录）
            if not server_script_path:
                # __file__ 是 main/home/modify_ww3_nml.py，需要回到项目根目录
                script_dir = os.path.dirname(os.path.abspath(__file__))  # main/home
                main_dir = os.path.dirname(script_dir)  # main
                project_root = os.path.dirname(main_dir)  # 项目根目录
                server_script_path = os.path.normpath(os.path.join(project_root, "public", "ww3", "server.sh"))
            else:
                server_script_path = os.path.normpath(server_script_path)
            
            if os.path.isfile(server_script_path):
                dst_path = os.path.join(self.selected_folder, "server.sh")
                shutil.copy2(server_script_path, dst_path)
                copied_files.append("server.sh")
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
                self.log(tr("server_sh_not_found", "⚠️ 未找到 server.sh 文件：{path}").format(path=server_script_path))
            
            # 只有在嵌套网格模式下才复制 ww3_multi.nml
            if is_nested_grid:
                multi_nml_path = os.path.join(src_dir, "ww3_multi.nml")
                if os.path.isfile(multi_nml_path):
                    dst_path = os.path.join(self.selected_folder, "ww3_multi.nml")
                    shutil.copy2(multi_nml_path, dst_path)
                    copied_files.append("ww3_multi.nml")

            if copied_files:
                files_str = ', '.join(copied_files)
                self.log(tr("step4_special_files_copied", "✅ 已复制 {files} 到工作目录：{path}").format(files=files_str, path=self.selected_folder))
        except Exception as e:
            self.log(tr("copy_public_files_error", "❌ 复制公共文件时出错：{error}").format(error=e))

    def _apply_all_params_nested(self, has_output_scheme=False):
        """嵌套网格模式：合并所有操作，外网格和内网格各自在一个分隔线下完成"""
        coarse_dir = os.path.join(self.selected_folder, "coarse")
        fine_dir = os.path.join(self.selected_folder, "fine")

        if not os.path.isdir(coarse_dir) or not os.path.isdir(fine_dir):
            self.log(tr("nested_grid_folders_not_found", "❌ 未找到 coarse 或 fine 文件夹，请先生成嵌套网格"))
            return

        # 处理公共文件（所有操作在一个分隔线下完成）
        self.log("")
        self.log("=" * 70)
        self.log(tr("step4_public_files_start", "🔄 【工作目录】开始处理公共文件..."))
        # 复制公共文件（server.sh 和 ww3_multi.nml）到工作目录
        self._copy_public_special_files_to_workdir()
        # 更新 server.sh 文件
        self.modify_server_sh_file()
        # 修改 ww3_multi.nml
        workdir_multi_nml = os.path.join(self.selected_folder, "ww3_multi.nml")
        if os.path.exists(workdir_multi_nml):
            self._modify_ww3_multi_nml(workdir_multi_nml)
        else:
            self.log(tr("ww3_multi_not_found", "⚠️ 未找到工作目录中的 ww3_multi.nml：{path}，跳过修改").format(path=workdir_multi_nml))

        # 处理外网格（所有操作在一个分隔线下完成）
        self.log("")
        self.log("=" * 70)
        self.log(tr("step4_outer_grid_start", "🔄 【外网格】开始处理外网格..."))
       
        self._copy_public_files_to_dir(coarse_dir, grid_label="")
        # 在复制文件后，应用谱分区输出方案（外/内网格）
        scheme_applied = False
        if has_output_scheme:
            scheme_applied = self._apply_output_scheme_to_dir(coarse_dir) or scheme_applied
        self._sync_grid_meta_to_grid_nml_in_dir(coarse_dir, grid_label="")
        self._apply_ww3_params_to_dir(
            coarse_dir,
            self.shel_step_edit.text().strip(),
            self.output_precision_edit.text().strip(),
            grid_label=""
        )
        self._modify_ww3_prnc_nml_for_nested(coarse_dir, grid_label="")
        # 修改 ww3_prnc.nml 中的时间范围（外网格）
        self._modify_ww3_prnc_times_in_dir(coarse_dir, grid_label="")
        # 为外网格生成其他强迫场的 ww3_prnc_*.nml 文件（从已修改时间的 ww3_prnc.nml 复制并修改）
        self._generate_forcing_field_prnc_files(coarse_dir, use_relative_path=True)
        # 修改外网格 ww3_shel.nml 中的 INPUT%FORCING%* 设置
        self._modify_ww3_shel_forcing_inputs_in_dir(coarse_dir, grid_label="")
        # 谱空间逐点计算相关操作（外网格）
        self._apply_spectral_params_to_dir(coarse_dir, self.shel_start_edit.text().strip(), 
                                          self.shel_end_edit.text().strip(), 
                                          self.shel_step_edit.text().strip(),
                                          self.output_precision_edit.text().strip())

        # 处理内网格（所有操作在一个分隔线下完成）
        self.log("")
        self.log("=" * 70)
        self.log(tr("step4_inner_grid_start", "🔄 【内网格】开始处理内网格..."))
       
        self._copy_public_files_to_dir(fine_dir, grid_label="")
        if has_output_scheme:
            scheme_applied = self._apply_output_scheme_to_dir(fine_dir) or scheme_applied
        if has_output_scheme and scheme_applied:
            self.log(tr("output_scheme_applied", "✅ 已修改 ww3_shel，ww3_ounf 的谱分区输出方案"))
        self._sync_grid_meta_to_grid_nml_in_dir(fine_dir, grid_label="")
        inner_shel_step = self.inner_shel_step_edit.text().strip()
        inner_output_precision = self.inner_output_precision_edit.text().strip()
        self._apply_ww3_params_to_dir(fine_dir, inner_shel_step, inner_output_precision, grid_label="")
        self._modify_ww3_prnc_nml_for_nested(fine_dir, grid_label="")
        # 修改 ww3_prnc.nml 中的时间范围（内网格）
        self._modify_ww3_prnc_times_in_dir(fine_dir, grid_label="")
        # 为内网格生成其他强迫场的 ww3_prnc_*.nml 文件（从已修改时间的 ww3_prnc.nml 复制并修改）
        self._generate_forcing_field_prnc_files(fine_dir, use_relative_path=True)
        # 修改内网格 ww3_shel.nml 中的 INPUT%FORCING%* 设置
        self._modify_ww3_shel_forcing_inputs_in_dir(fine_dir, grid_label="")
        # 谱空间逐点计算相关操作（内网格）
        self._apply_spectral_params_to_dir(fine_dir, self.shel_start_edit.text().strip(), 
                                          self.shel_end_edit.text().strip(), 
                                          inner_shel_step,
                                          inner_output_precision)


    def _apply_ww3_params_nested(self):
        """嵌套网格模式：应用参数到外网格和内网格"""
        coarse_dir = os.path.join(self.selected_folder, "coarse")
        fine_dir = os.path.join(self.selected_folder, "fine")

        if not os.path.isdir(coarse_dir) or not os.path.isdir(fine_dir):
            self.log(tr("nested_grid_folders_not_found", "❌ 未找到 coarse 或 fine 文件夹，请先生成嵌套网格"))
            return

        
        # 应用外网格参数（所有操作在一个分隔线下完成）
        self.log("")
        self.log("=" * 70)
        self.log(tr("outer_grid_params_start", "🔄 【外网格】开始应用外网格参数..."))
        self.log("=" * 70)
        self._apply_ww3_params_to_dir(
            coarse_dir,
            self.shel_step_edit.text().strip(),
            self.output_precision_edit.text().strip(),
            grid_label=""
        )
        self._modify_ww3_prnc_nml_for_nested(coarse_dir, grid_label="")

        # 应用内网格参数（所有操作在一个分隔线下完成）
        self.log("")
        self.log("=" * 70)
        self.log(tr("inner_grid_params_start", "🔄 【内网格】开始应用内网格参数..."))
        self.log("=" * 70)
        inner_shel_step = self.inner_shel_step_edit.text().strip()
        inner_output_precision = self.inner_output_precision_edit.text().strip()
        self._apply_ww3_params_to_dir(fine_dir, inner_shel_step, inner_output_precision, grid_label="")
        self._modify_ww3_prnc_nml_for_nested(fine_dir, grid_label="")

        # 生成脚本文件

        # 修改 ww3_multi.nml
        workdir_multi_nml = os.path.join(self.selected_folder, "ww3_multi.nml")
        if os.path.exists(workdir_multi_nml):
            self._modify_ww3_multi_nml(workdir_multi_nml)
        else:
            self.log(tr("ww3_multi_not_found", "⚠️ 未找到工作目录中的 ww3_multi.nml：{path}，跳过修改").format(path=workdir_multi_nml))


    def _apply_ww3_params_normal(self):
        """普通网格模式：应用参数"""
        # 应用 ww3_ounf.nml
        self.apply_ww3_ounf()
        # 修改 ww3_shel.nml
        self.modify_ww3_shel_times()


    def _apply_ww3_params_to_dir(self, target_dir, compute_precision, output_precision, grid_label=""):
        """在指定目录中应用 WW3 运行参数"""
        self._apply_ww3_ounf_to_dir(target_dir, output_precision, grid_label=grid_label)
        self._modify_ww3_shel_times_to_dir(target_dir, compute_precision, grid_label=grid_label)

    def _get_output_scheme_var_list(self):
        """获取当前选择的谱分区输出方案变量列表字符串"""
        try:
            if not hasattr(self, 'output_scheme_combo') or not self.output_scheme_combo:
                return None
            scheme_name = self.output_scheme_combo.currentText().strip()
            if not scheme_name:
                return None

            from setting.config import load_config
            config = load_config()
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

    def _apply_output_scheme_to_dir(self, target_dir):
        """将谱分区输出方案写入指定目录的 ww3_shel.nml 和 ww3_ounf.nml"""
        if not target_dir or not isinstance(target_dir, str):
            return False

        var_list_str = self._get_output_scheme_var_list()
        if not var_list_str:
            return False

        modified_any = False

        # 更新 ww3_shel.nml 的 TYPE%FIELD%LIST
        ww3_shel_path = os.path.join(target_dir, "ww3_shel.nml")
        if os.path.exists(ww3_shel_path):
            try:
                with open(ww3_shel_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                new_lines = []
                modified = False
                for line in lines:
                    line_stripped = line.lstrip()
                    is_comment = line_stripped.startswith('!')
                    if not is_comment and re.search(r'TYPE%FIELD%LIST', line, re.IGNORECASE) and "=" in line:
                        new_lines.append(f"  TYPE%FIELD%LIST       = '{var_list_str}'\n")
                        modified = True
                    else:
                        new_lines.append(line)
                if modified:
                    with open(ww3_shel_path, "w", encoding="utf-8") as f:
                        f.writelines(new_lines)
                    modified_any = True
            except Exception:
                pass

        # 更新 ww3_ounf.nml 的 FIELD%LIST
        ww3_ounf_path = os.path.join(target_dir, "ww3_ounf.nml")
        if os.path.exists(ww3_ounf_path):
            try:
                with open(ww3_ounf_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                new_lines = []
                modified = False
                for line in lines:
                    line_stripped = line.lstrip()
                    is_comment = line_stripped.startswith('!')
                    if not is_comment and re.search(r'FIELD%LIST', line, re.IGNORECASE) and "=" in line:
                        new_lines.append(f"  FIELD%LIST             =  '{var_list_str}'\n")
                        modified = True
                    else:
                        new_lines.append(line)
                if modified:
                    with open(ww3_ounf_path, "w", encoding="utf-8") as f:
                        f.writelines(new_lines)
                    modified_any = True
            except Exception:
                pass

        return modified_any


    # ==================== NML 文件修改 ====================

    def _apply_ww3_ounf_to_dir(self, target_dir, output_precision, grid_label=""):
        """在指定目录中修改 ww3_ounf.nml"""
        if not target_dir or not isinstance(target_dir, str):
            return

        nml_path = os.path.join(target_dir, "ww3_ounf.nml")
        if not os.path.exists(nml_path):
            self.log(tr("ww3_ounf_not_found", "⚠️ 未找到 ww3_ounf.nml 文件：{path}，跳过").format(path=nml_path))
            return

        start_date = self.shel_start_edit.text().strip()
        stride = output_precision

        if not (start_date.isdigit() and len(start_date) == 8):
            self.log(tr("date_format_error", "❌ 起始日期格式错误，应为 YYYYMMDD。"))
            return
        if not stride.isdigit():
            self.log(tr("timestep_must_be_number", "❌ 时间步长必须为数字（秒）。"))
            return

        # 从配置中读取文件分割设置
        from setting.config import load_config
        config = load_config()
        file_split = config.get("FILE_SPLIT", tr("file_split_year", "年"))
        
        # 文件分割映射：索引 -> 值
        # 0 (无日期), 4(年), 6(月), 8(日), 10(小时)
        file_split_value_map = {
            tr("file_split_hour", "小时"): 10,
            tr("file_split_day", "天"): 8,
            tr("file_split_month", "月"): 6,
            tr("file_split_year", "年"): 4
        }
        # 英文映射
        file_split_value_map_en = {"Hour": 10, "Day": 8, "Month": 6, "Year": 4}
        
        # 获取对应的值
        timesplit_value = file_split_value_map.get(file_split, file_split_value_map_en.get(file_split, 4))  # 默认4(年)

        try:
            with open(nml_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            timesplit_found = False
            for line in lines:
                # 检查是否为注释行（以 ! 开头，去除前导空格后）
                line_stripped = line.lstrip()
                is_comment = line_stripped.startswith('!')
                
                # 只替换非注释行
                if not is_comment:
                    if "FIELD%TIMESTART" in line:
                        new_lines.append(f"  FIELD%TIMESTART        =  '{start_date} 000000'\n")
                        continue
                    if "FIELD%TIMESTRIDE" in line:
                        new_lines.append(f"  FIELD%TIMESTRIDE       =  '{stride}'\n")
                        continue
                    if "FIELD%TIMESPLIT" in line:
                        new_lines.append(f"  FIELD%TIMESPLIT        =  {timesplit_value}\n")
                        timesplit_found = True
                        continue
                new_lines.append(line)
            
            # 如果 FIELD%TIMESPLIT 不存在，需要在 FIELD_NML 块中添加
            if not timesplit_found:
                # 查找 FIELD_NML 块的结束位置（/ 行），在之前插入
                in_field_nml = False
                insert_index = -1
                for i, line in enumerate(new_lines):
                    if "&FIELD_NML" in line.upper():
                        in_field_nml = True
                    if in_field_nml and re.match(r'^\s*/\s*$', line) and not line.strip().startswith("!"):
                        insert_index = i
                        break
                
                if insert_index > 0:
                    # 在 / 之前插入 FIELD%TIMESPLIT
                    new_lines.insert(insert_index, f"  FIELD%TIMESPLIT        =  {timesplit_value}\n")

            with open(nml_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            prefix = f"{grid_label} " if grid_label else ""
            self.log(f"{prefix}{tr('step4_ww3_ounf_updated', '✅ 已更新 ww3_ounf.nml：FIELD%TIMESTART={start}，FIELD%TIMESTRIDE={stride}秒').format(start=start_date, stride=stride)}")

        except Exception as e:
            self.log(tr("ww3_ounf_modify_error", "❌ 修改 ww3_ounf.nml 出错: {error}").format(error=e))


    def _modify_ww3_shel_times_to_dir(self, target_dir, compute_precision, grid_label=""):
        """在指定目录中修改 ww3_shel.nml"""
        if not target_dir or not isinstance(target_dir, str):
            return

        path = os.path.join(target_dir, "ww3_shel.nml")
        if not os.path.exists(path):
            self.log(tr("ww3_shel_not_found", "⚠️ 未找到 ww3_shel.nml：{path}，跳过").format(path=path))
            return

        start_date = self.shel_start_edit.text().strip()
        end_date = self.shel_end_edit.text().strip()
        main_step = compute_precision

        if not (start_date.isdigit() and len(start_date) == 8 and end_date.isdigit() and len(end_date) == 8):
            self.log(tr("date_range_format_error", "❌ 起始/结束日期格式错误，应为 YYYYMMDD。"))
            return

        if not main_step.isdigit():
            self.log(tr("step_must_be_number", "❌ 步长必须为数字（秒）。"))
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            in_domain = False
            in_output = False

            for line in lines:
                # 检查是否为注释行（以 ! 开头，去除前导空格后）
                line_stripped = line.lstrip()
                is_comment = line_stripped.startswith('!')
                
                # DOMAIN_NML
                if "&DOMAIN_NML" in line:
                    in_domain = True
                    new_lines.append(line)
                    continue

                if in_domain:
                    # 只替换非注释行
                    if not is_comment and re.search(r"DOMAIN%START", line):
                        new_lines.append(f"  DOMAIN%START           =  '{start_date} 000000'\n")
                        continue
                    if not is_comment and re.search(r"DOMAIN%STOP", line):
                        new_lines.append(f"  DOMAIN%STOP            =  '{end_date} 235959'\n")
                        continue
                    if "/" in line:
                        in_domain = False
                        new_lines.append(line)
                        continue

                # OUTPUT_NML
                if "&OUTPUT_NML" in line:
                    in_output = True
                    new_lines.append(line)
                    continue

                if in_output:
                    # 只替换非注释行
                    if not is_comment and re.search(r"OUTPUT%FIELD%TIMESTART", line):
                        new_lines.append(f"  OUTPUT%FIELD%TIMESTART =  '{start_date} 000000'\n")
                        continue
                    if not is_comment and re.search(r"OUTPUT%FIELD%TIMESTRIDE", line):
                        new_lines.append(f"  OUTPUT%FIELD%TIMESTRIDE =  '{main_step}'\n")
                        continue
                    if "/" in line:
                        in_output = False
                        new_lines.append(line)
                        continue

                # OUTPUT_DATE_NML
                # 只替换非注释行
                if not is_comment and re.search(r"DATE%FIELD", line) and "=" in line:
                    new_lines.append(f"  DATE%FIELD          = '{start_date} 000000' '{main_step}' '{end_date} 235959'\n")
                    continue

                new_lines.append(line)

            with open(path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            # 检查是否是谱空间逐点计算模式，如果是则合并日志
            is_spectral_point = self._is_spectral_point_mode()
            has_points = False
            if is_spectral_point and hasattr(self, 'spectral_points_table'):
                point_count = self.spectral_points_table.rowCount()
                has_points = point_count > 1  # 有数据点（除了表头）
            
            prefix = f"{grid_label} " if grid_label else ""
            
            if is_spectral_point and has_points:
                # 谱空间逐点计算模式：合并所有修改的日志
                modified_point_file = self._modify_ww3_shel_point_file_in_dir(target_dir, silent=True)
                modified_date_point = self._modify_ww3_shel_date_point_in_dir(target_dir, start_date, end_date, main_step, silent=True)
                
                # 构建合并的日志消息
                parts = []
                parts.append(tr("step4_date_range_compute_step", "起始={start}, 结束={end}, 计算步长={step}s").format(start=start_date, end=end_date, step=main_step))
                if modified_point_file:
                    parts.append(tr("step4_added_type_point_file", "添加 TYPE%POINT%FILE = 'points.list'"))
                if modified_date_point:
                    parts.append(tr("step4_added_date_point_boundary", "添加 DATE%POINT 和 DATE%BOUNDARY"))
                
                log_msg = prefix + tr("step4_ww3_shel_spectral_point_updated", "✅ 已更新 ww3_shel.nml（谱空间逐点计算模式）：{details}").format(details="，".join(parts))
                self.log(log_msg)
            else:
                # 普通模式：只显示时间更新
                self.log(f"{prefix}{tr('step4_ww3_shel_updated', '✅ 已更新 ww3_shel.nml：DOMAIN%START={start}, DOMAIN%STOP={end}, DATE%FIELD%STRIDE={step}s').format(start=start_date, end=end_date, step=main_step)}")

        except Exception as e:
            self.log(tr("ww3_shel_modify_error", "❌ 修改 {file}/ww3_shel.nml 出错：{error}").format(file=os.path.basename(target_dir), error=e))


    def _format_domain_line(self, field_name, value):
        """格式化 DOMAIN%* 行，确保等号对齐在第17列"""
        prefix = "  "
        target_length = 16  # 等号前总长度（等号在17列）
        current_length = len(prefix + field_name)
        spaces_needed = target_length - current_length
        if spaces_needed < 1:
            spaces_needed = 1  # 至少保留一个空格
        return f"{prefix}{field_name}{' ' * spaces_needed}= {value}\n"
    
    def _check_ice_param1_variable(self, file_path):
        """检查海冰场文件是否包含 ICE_PARAM1 变量（冰厚度，通常是 sithick）"""
        try:
            from netCDF4 import Dataset
            with Dataset(file_path, "r") as ds:
                # 检查常见的冰厚度变量名
                ice_thickness_vars = ["sithick", "SITHICK", "ice_thickness", "ICE_THICKNESS", 
                                     "sit", "SIT", "hi", "HI", "hice", "HICE"]
                for var_name in ice_thickness_vars:
                    if var_name in ds.variables:
                        return True
            return False
        except Exception:
            return False

    def _read_type_field_list_from_shel(self, shel_path):
        """从 ww3_shel.nml 读取 TYPE%FIELD%LIST 的值"""
        if not os.path.exists(shel_path):
            return None
        
        try:
            with open(shel_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            for line in lines:
                # 检查是否为注释行
                line_stripped = line.lstrip()
                is_comment = line_stripped.startswith('!')
                
                # 查找 TYPE%FIELD%LIST 行（非注释行，不区分大小写）
                if not is_comment and re.search(r'TYPE%FIELD%LIST', line, re.IGNORECASE) and "=" in line:
                    # 提取引号内的内容
                    match = re.search(r"['\"]([^'\"]+)['\"]", line)
                    if match:
                        return match.group(1)
        except Exception:
            pass
        
        return None

    def _read_grid_nx_ny_from_nml(self, nml_path):
        """从 ww3_grid.nml 文件中读取 RECT%NX 和 RECT%NY 值"""
        if not os.path.exists(nml_path):
            return None, None
        
        try:
            with open(nml_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            nx = None
            ny = None
            in_rect_nml = False
            
            for line in lines:
                # 检查是否进入 RECT_NML 块
                if "&RECT_NML" in line.upper():
                    in_rect_nml = True
                    continue
                
                # 检查是否离开 RECT_NML 块
                if in_rect_nml and "/" in line and not line.strip().startswith("!"):
                    break
                
                # 在 RECT_NML 块中提取 NX 和 NY
                if in_rect_nml:
                    # 检查是否为注释行
                    line_stripped = line.lstrip()
                    if line_stripped.startswith('!'):
                        continue
                    
                    # 提取 RECT%NX
                    nx_match = re.search(r"RECT%NX\s*=\s*(\d+)", line, re.IGNORECASE)
                    if nx_match:
                        nx = int(nx_match.group(1))
                    
                    # 提取 RECT%NY
                    ny_match = re.search(r"RECT%NY\s*=\s*(\d+)", line, re.IGNORECASE)
                    if ny_match:
                        ny = int(ny_match.group(1))
            
            return nx, ny
        except Exception as e:
            self.log(tr("read_nml_error", "⚠️ 读取 {path} 时出错：{error}").format(path=nml_path, error=e))
            return None, None

    def _modify_ww3_multi_nml(self, nml_path):
        """修改 ww3_multi.nml 的起始时间和强迫场配置"""
        if not os.path.exists(nml_path):
            self.log(tr("ww3_multi_not_found_skip", "⚠️ 未找到 ww3_multi.nml：{path}，跳过修改").format(path=nml_path))
            return

        start_date = self.shel_start_edit.text().strip()
        end_date = self.shel_end_edit.text().strip()
        compute_precision = self.shel_step_edit.text().strip()

        if not (start_date.isdigit() and len(start_date) == 8 and end_date.isdigit() and len(end_date) == 8):
            self.log(tr("date_range_format_error", "❌ 起始/结束日期格式错误，应为 YYYYMMDD。"))
            return

        if not compute_precision.isdigit():
            self.log(tr("compute_precision_must_be_number", "❌ 计算精度必须为数字（秒）。"))
            return

        # 检查当前选择的强迫场
        has_wind = hasattr(self, 'selected_origin_file') and self.selected_origin_file and os.path.exists(self.selected_origin_file)
        has_current = hasattr(self, 'selected_current_file') and self.selected_current_file and os.path.exists(self.selected_current_file)
        has_level = hasattr(self, 'selected_level_file') and self.selected_level_file and os.path.exists(self.selected_level_file)
        has_ice = hasattr(self, 'selected_ice_file') and self.selected_ice_file and os.path.exists(self.selected_ice_file)
        
        # 检查海冰场是否包含 ICE_PARAM1 变量
        has_ice_param1 = False
        if has_ice:
            has_ice_param1 = self._check_ice_param1_variable(self.selected_ice_file)
        
        # 读取内外网格的 ww3_grid.nml 以计算进程比例
        coarse_nx, coarse_ny = None, None
        fine_nx, fine_ny = None, None
        coarse_ratio = 0.50  # 默认值
        fine_ratio = 0.50    # 默认值
        
        if hasattr(self, 'selected_folder') and self.selected_folder:
            coarse_grid_nml = os.path.join(self.selected_folder, "coarse", "ww3_grid.nml")
            fine_grid_nml = os.path.join(self.selected_folder, "fine", "ww3_grid.nml")
            
            coarse_nx, coarse_ny = self._read_grid_nx_ny_from_nml(coarse_grid_nml)
            fine_nx, fine_ny = self._read_grid_nx_ny_from_nml(fine_grid_nml)
            
            if coarse_nx is not None and coarse_ny is not None and fine_nx is not None and fine_ny is not None:
                points_coarse = coarse_nx * coarse_ny
                points_fine = fine_nx * fine_ny
                total_points = points_coarse + points_fine
                
                if total_points > 0:
                    # 计算基础比例
                    base_coarse_ratio = points_coarse / total_points
                    
                    # 考虑网格分辨率的影响：更细的网格需要更多计算资源
                    # 使用加权计算，给 coarse 网格更多的权重（因为需要处理边界条件等）
                    # 或者设置一个最小比例保证
                    min_coarse_ratio = 0.35  # 最小比例保证，避免 coarse 分配过少
                    
                    # 如果基础比例太小，使用最小比例
                    # 否则，在基础比例和最小比例之间取较大值，但不超过 0.6
                    if base_coarse_ratio < min_coarse_ratio:
                        coarse_ratio = min_coarse_ratio
                    else:
                        # 给 coarse 一个额外的权重（+5%），但不超过 0.6
                        coarse_ratio = min(base_coarse_ratio + 0.05, 0.60)
                    
                    fine_ratio = 1.0 - coarse_ratio
            #         self.log(tr("grid_points_info", "📊 网格点数：coarse={coarse} ({coarse_nx}x{coarse_ny}), fine={fine} ({fine_nx}x{fine_ny}), 基础比例：coarse={base_ratio:.2f}, 调整后比例：coarse={coarse_ratio:.2f}, fine={fine_ratio:.2f}").format(coarse=points_coarse, coarse_nx=coarse_nx, coarse_ny=coarse_ny, fine=points_fine, fine_nx=fine_nx, fine_ny=fine_ny, base_ratio=base_coarse_ratio, coarse_ratio=coarse_ratio, fine_ratio=fine_ratio))
            #     else:
            #         self.log(tr("grid_points_zero", "⚠️ 总网格点数为0，使用默认比例"))
            # else:
            #     self.log(tr("grid_size_read_failed", "⚠️ 无法读取网格尺寸，使用默认比例"))

        try:
            with open(nml_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            in_domain = False
            in_output = False
            in_output_type = False
            in_input_grid = False
            in_model_grid = False
            model_index = 0  # 跟踪当前处理的 MODEL 索引
            
            # 跟踪修改状态
            modified_alltype_point_file = False
            modified_alldate_point = False
            modified_alltype_field_list = False
            
            # 检查是否为嵌套网格模式
            grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
            nested_text = tr("step2_grid_type_nested", "嵌套网格")
            is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")
            
            # 如果通过 grid_type_var 无法确定，检查文件夹结构
            if not is_nested_grid and hasattr(self, 'selected_folder') and self.selected_folder:
                coarse_dir = os.path.join(self.selected_folder, "coarse")
                fine_dir = os.path.join(self.selected_folder, "fine")
                is_nested_grid = (os.path.isdir(coarse_dir) and os.path.isdir(fine_dir))
            
            # 如果是嵌套网格模式，读取 ww3_shel.nml 中的 TYPE%FIELD%LIST 值
            alltype_field_list_value = None
            if is_nested_grid:
                # 优先从当前工作目录的 ww3_shel.nml 读取
                if hasattr(self, 'selected_folder') and self.selected_folder:
                    shel_path = os.path.join(self.selected_folder, "ww3_shel.nml")
                    alltype_field_list_value = self._read_type_field_list_from_shel(shel_path)
                
                # 如果工作目录中没有，尝试从 public/ww3 读取
                if not alltype_field_list_value:
                    from setting.config import load_config
                    config = load_config()
                    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                    public_ww3_dir = config.get("PUBLIC_WW3_PATH", os.path.join(project_root, "public", "ww3"))
                    shel_path = os.path.join(public_ww3_dir, "ww3_shel.nml")
                    alltype_field_list_value = self._read_type_field_list_from_shel(shel_path)
                
                # 如果还是找不到，使用默认值（谱分区输出常用变量）
                if not alltype_field_list_value:
                    alltype_field_list_value = 'HS LM T02 T0M1 T01 FP DIR SPR DP PHS PTP PLP PDIR PSPR PWS TWS PNR'
            
            # 检查是否为谱空间逐点计算模式
            is_spectral_point = self._is_spectral_point_mode()
            has_spectral_points = False
            if is_spectral_point and hasattr(self, 'spectral_points_table'):
                point_count = self.spectral_points_table.rowCount()
                has_spectral_points = point_count > 1  # 有数据点（跳过表头）

            for line in lines:
                # DOMAIN_NML
                if "&DOMAIN_NML" in line:
                    in_domain = True
                    new_lines.append(line)
                    continue

                if in_domain:
                    if re.search(r"DOMAIN%START", line):
                        new_lines.append(self._format_domain_line("DOMAIN%START", f"'{start_date} 000000'"))
                        continue
                    if re.search(r"DOMAIN%STOP", line):
                        new_lines.append(self._format_domain_line("DOMAIN%STOP", f"'{end_date} 235959'"))
                        continue
                    if "/" in line:
                        in_domain = False
                        new_lines.append(line)
                        continue

                # OUTPUT_TYPE_NML
                if "&OUTPUT_TYPE_NML" in line:
                    in_output_type = True
                    new_lines.append(line)
                    continue

                if in_output_type:
                    # 处理 ALLTYPE%FIELD%LIST（嵌套网格模式下从 ww3_shel.nml 读取值）
                    if re.search(r'ALLTYPE%FIELD%LIST', line, re.IGNORECASE):
                        if is_nested_grid and alltype_field_list_value:
                            # 嵌套网格模式：设置为从 ww3_shel.nml 读取的值
                            new_lines.append(f"  ALLTYPE%FIELD%LIST     = '{alltype_field_list_value}'\n")
                            modified_alltype_field_list = True
                        else:
                            # 普通网格模式：保留原行
                            new_lines.append(line)
                        continue
                    if "/" in line:
                        # 在结束标记之前，如果是谱空间逐点计算模式，添加 ALLTYPE%POINT%FILE
                        if is_spectral_point and has_spectral_points:
                            # 检查是否已有 ALLTYPE%POINT%FILE
                            has_alltype_point_file = False
                            for prev_line in new_lines[-10:]:  # 检查最近10行
                                if re.search(r'ALLTYPE%POINT%FILE', prev_line, re.IGNORECASE):
                                    has_alltype_point_file = True
                                    break
                            
                            if not has_alltype_point_file:
                                new_lines.append(f"  ALLTYPE%POINT%FILE     = './fine/points.list'\n")
                                modified_alltype_point_file = True
                        # 如果是嵌套网格模式且还没有 ALLTYPE%FIELD%LIST，添加它
                        if is_nested_grid and not modified_alltype_field_list and alltype_field_list_value:
                            # 检查是否已有 ALLTYPE%FIELD%LIST
                            has_alltype_field_list = False
                            for prev_line in new_lines[-10:]:  # 检查最近10行
                                if re.search(r'ALLTYPE%FIELD%LIST', prev_line, re.IGNORECASE):
                                    has_alltype_field_list = True
                                    break
                            
                            if not has_alltype_field_list:
                                new_lines.append(f"  ALLTYPE%FIELD%LIST     = '{alltype_field_list_value}'\n")
                                modified_alltype_field_list = True
                        in_output_type = False
                        new_lines.append(line)
                        continue
                    # 跳过现有的 ALLTYPE%POINT%FILE 行（如果存在）
                    if re.search(r'ALLTYPE%POINT%FILE', line, re.IGNORECASE):
                        # 已存在，保留原行
                        new_lines.append(line)
                        continue
                    new_lines.append(line)
                    continue

                # OUTPUT_DATE_NML
                if "&OUTPUT_DATE_NML" in line:
                    in_output = True
                    new_lines.append(line)
                    continue

                if in_output:
                    if re.search(r"ALLDATE%FIELD", line):
                        new_lines.append(f"  ALLDATE%FIELD          = '{start_date} 000000' '{compute_precision}' '{end_date} 235959'\n")
                        continue
                    if re.search(r"ALLDATE%RESTART", line):
                        # 尝试提取原有的步长
                        m = re.search(r"'(\d{8}\s+\d{6})'\s*'(\d+)'\s*'(\d{8}\s+\d{6})'", line)
                        if m:
                            restart_step = m.group(2)
                            new_lines.append(f"  ALLDATE%RESTART        = '{start_date} 000000' '{restart_step}' '{end_date} 235959'\n")
                        else:
                            new_lines.append(f"  ALLDATE%RESTART        = '{start_date} 000000' '86400' '{end_date} 235959'\n")
                        continue
                    if "/" in line:
                        # 在结束标记之前，如果是谱空间逐点计算模式，添加 ALLDATE%POINT
                        if is_spectral_point and has_spectral_points:
                            # 检查是否已有 ALLDATE%POINT
                            has_alldate_point = False
                            for prev_line in new_lines[-10:]:  # 检查最近10行
                                if re.search(r'ALLDATE%POINT', prev_line, re.IGNORECASE):
                                    has_alldate_point = True
                                    break
                            
                            if not has_alldate_point:
                                new_lines.append(f"  ALLDATE%POINT          = '{start_date} 000000' '{compute_precision}' '{end_date} 235959'\n")
                                modified_alldate_point = True
                        in_output = False
                        new_lines.append(line)
                        continue
                    # 跳过现有的 ALLDATE%POINT 行（如果存在）
                    if re.search(r'ALLDATE%POINT', line, re.IGNORECASE):
                        # 已存在，保留原行
                        new_lines.append(line)
                        continue
                    new_lines.append(line)
                    continue

                # INPUT_GRID_NML
                if "&INPUT_GRID_NML" in line:
                    in_input_grid = True
                    new_lines.append(line)
                    continue

                if in_input_grid:
                    # INPUT(1) - 风场
                    if re.search(r"INPUT\(1\)%FORCING%WINDS", line):
                        value = "T" if has_wind else "F"
                        new_lines.append(self._format_input_model_line("INPUT(1)%FORCING%WINDS", value))
                        continue
                    # INPUT(2) - 流场
                    if re.search(r"INPUT\(2\)%FORCING%CURRENTS", line):
                        value = "T" if has_current else "F"
                        new_lines.append(self._format_input_model_line("INPUT(2)%FORCING%CURRENTS", value))
                        continue
                    # INPUT(3) - 水位场
                    if re.search(r"INPUT\(3\)%FORCING%WATER_LEVELS", line):
                        value = "T" if has_level else "F"
                        new_lines.append(self._format_input_model_line("INPUT(3)%FORCING%WATER_LEVELS", value))
                        continue
                    # INPUT(4) - 海冰场
                    if re.search(r"INPUT\(4\)%FORCING%ICE_CONC", line):
                        value = "T" if has_ice else "F"
                        new_lines.append(self._format_input_model_line("INPUT(4)%FORCING%ICE_CONC", value))
                        continue
                    if re.search(r"INPUT\(5\)%FORCING%ICE_PARAM1", line):
                        value = "T" if (has_ice and has_ice_param1) else "F"
                        new_lines.append(self._format_input_model_line("INPUT(5)%FORCING%ICE_PARAM1", value))
                        continue
                    if "/" in line:
                        in_input_grid = False
                        new_lines.append(line)
                        continue

                # MODEL_GRID_NML
                if "&MODEL_GRID_NML" in line:
                    in_model_grid = True
                    new_lines.append(line)
                    continue

                if in_model_grid:
                    # 检测 MODEL(1) 或 MODEL(2)
                    model_match = re.search(r"MODEL\((\d+)\)", line)
                    if model_match:
                        model_index = int(model_match.group(1))
                    
                    # 处理 MODEL(1) 和 MODEL(2) 的强迫场设置
                    if model_index in [1, 2]:
                        # WINDS
                        if re.search(rf"MODEL\({model_index}\)%FORCING%WINDS", line):
                            value = "'native'" if has_wind else "'no'"
                            new_lines.append(self._format_input_model_line(f"MODEL({model_index})%FORCING%WINDS", value))
                            continue
                        # CURRENTS
                        if re.search(rf"MODEL\({model_index}\)%FORCING%CURRENTS", line):
                            value = "'native'" if has_current else "'no'"
                            new_lines.append(self._format_input_model_line(f"MODEL({model_index})%FORCING%CURRENTS", value))
                            continue
                        # WATER_LEVELS
                        if re.search(rf"MODEL\({model_index}\)%FORCING%WATER_LEVELS", line):
                            value = "'native'" if has_level else "'no'"
                            new_lines.append(self._format_input_model_line(f"MODEL({model_index})%FORCING%WATER_LEVELS", value))
                            continue
                        # ICE_CONC
                        if re.search(rf"MODEL\({model_index}\)%FORCING%ICE_CONC", line):
                            value = "'native'" if has_ice else "'no'"
                            new_lines.append(self._format_input_model_line(f"MODEL({model_index})%FORCING%ICE_CONC", value))
                            continue
                        # ICE_PARAM1
                        if re.search(rf"MODEL\({model_index}\)%FORCING%ICE_PARAM1", line):
                            value = "'native'" if (has_ice and has_ice_param1) else "'no'"
                            new_lines.append(self._format_input_model_line(f"MODEL({model_index})%FORCING%ICE_PARAM1", value))
                            continue
                        # RESOURCE - 根据网格点数动态计算
                        if re.search(rf"MODEL\({model_index}\)%RESOURCE", line):
                            if model_index == 1:
                                # MODEL(1)%RESOURCE = 1 1 0.00 {coarse_ratio:.2f} T
                                resource_value = f"1 1 0.00 {coarse_ratio:.2f} F"
                            elif model_index == 2:
                                # MODEL(2)%RESOURCE = 2 1 {coarse_ratio:.2f} 1.00 F
                                resource_value = f"2 1 {coarse_ratio:.2f} 1.00 F"
                            else:
                                resource_value = None
                            
                            if resource_value:
                                new_lines.append(self._format_input_model_line(f"MODEL({model_index})%RESOURCE", resource_value))
                            else:
                                new_lines.append(line)
                            continue
                    
                    if "/" in line:
                        in_model_grid = False
                        model_index = 0
                        new_lines.append(line)
                        continue

                new_lines.append(line)

            with open(nml_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            # 构建日志消息
            log_parts = []
            log_parts.append(tr("step4_date_range_compute_precision", "起始={start}, 结束={end}, 计算精度={precision}s").format(start=start_date, end=end_date, precision=compute_precision))
            
            # 添加强迫场开关信息
            forcing_fields = []
            if has_wind:
                forcing_fields.append(tr("step4_forcing_field_wind", "风场"))
            if has_current:
                forcing_fields.append(tr("step4_forcing_field_current", "流场"))
            if has_level:
                forcing_fields.append(tr("step4_forcing_field_level", "水位场"))
            if has_ice:
                forcing_fields.append(tr("step4_forcing_field_ice", "海冰场"))
            if has_ice_param1:
                forcing_fields.append(tr("step4_forcing_field_ice_param1", "海冰厚度"))
            
            if forcing_fields:
                forcing_str = tr("step4_forcing_fields_enabled", "强迫场={fields}").format(fields="、".join(forcing_fields))
            else:
                forcing_str = tr("step4_forcing_fields_none", "强迫场=无")
            log_parts.append(forcing_str)
            
            # 添加计算资源信息
            resource_str = tr("step4_resource_ratio", "计算资源：coarse={coarse_ratio:.2f}, fine={fine_ratio:.2f}").format(coarse_ratio=coarse_ratio, fine_ratio=fine_ratio)
            log_parts.append(resource_str)
            
            if modified_alltype_point_file:
                log_parts.append(tr("step4_alltype_point_file_value", "ALLTYPE%POINT%FILE = './fine/points.list'"))
            
            if modified_alldate_point:
                log_parts.append(tr("step4_alldate_point_value", "ALLDATE%POINT = '{start} 000000' '{precision}' '{end} 235959'").format(start=start_date, precision=compute_precision, end=end_date))
            
            if modified_alltype_field_list and alltype_field_list_value:
                log_parts.append(tr("step4_alltype_field_list_set", "ALLTYPE%FIELD%LIST = '{value}' (谱分区输出)").format(value=alltype_field_list_value))
            
            log_msg = tr("step4_ww3_multi_updated_details", "✅ 已更新 ww3_multi.nml：{details}").format(details="，".join(log_parts))
            self.log(log_msg)

        except Exception as e:
            self.log(tr("ww3_multi_modify_error", "❌ 修改 ww3_multi.nml 出错：{error}").format(error=e))
            import traceback
            for line in traceback.format_exc().splitlines():
                self.log(line)


    def apply_ww3_ounf(self):
        """修改 ww3_ounf.nml（普通网格模式）"""
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return
        self._apply_ww3_ounf_to_dir(self.selected_folder, self.output_precision_edit.text().strip())


    def modify_ww3_shel_times(self):
        """修改 ww3_shel.nml（普通网格模式）"""
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return
        self._modify_ww3_shel_times_to_dir(self.selected_folder, self.shel_step_edit.text().strip())


    def _format_forcing_field_line(self, field_name, value):
        """格式化 FORCING%FIELD%* 行，确保等号对齐在第32列"""
        # 等号对齐位置（与模板文件一致，等号在第32列）
        # 等号前总长度应该是31（包括字段名和空格）
        prefix = "  FORCING%FIELD%"
        target_length = 31  # 等号前总长度（等号在32列）
        current_length = len(prefix + field_name)
        spaces_needed = target_length - current_length
        if spaces_needed < 1:
            spaces_needed = 1  # 至少保留一个空格
        return f"{prefix}{field_name}{' ' * spaces_needed}= {value}\n"
    
    def _format_input_model_line(self, field_name, value):
        """格式化 INPUT(*) 或 MODEL(*) 行，确保等号对齐在第33列（索引33）"""
        # 根据模板文件，等号对齐在第33列（从1开始计数）
        # 等号前总长度应该是33（等号在索引33，即第34个字符）
        target_length = 33  # 等号前总长度（等号在索引33）
        prefix = "  "
        current_length = len(prefix + field_name)
        spaces_needed = target_length - current_length
        if spaces_needed < 1:
            spaces_needed = 1  # 至少保留一个空格
        return f"{prefix}{field_name}{' ' * spaces_needed}= {value}\n"
    
    def _modify_ww3_prnc_nml_for_nested(self, target_dir, grid_label=""):
        """
        修改嵌套网格模式下 ww3_prnc.nml 中的：
        1. &FORCING_NML 中的设置（风场总是 T，其他场根据选择）
        2. &FILE_NML 中的 FILE%FILENAME 根据强迫场类型设置
        3. &FILE_NML 中的变量名根据强迫场类型设置
        """
        if not target_dir or not isinstance(target_dir, str):
            return

        nml_path = os.path.join(target_dir, "ww3_prnc.nml")
        if not os.path.exists(nml_path):
            self.log(tr("ww3_prnc_not_found_skip", "⚠️ 未找到 ww3_prnc.nml 文件：{path}，跳过修改").format(path=nml_path))
            return

        try:
            import re
            import glob
            from netCDF4 import Dataset
            
            # 读取文件，确定强迫场类型
            with open(nml_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # 确定强迫场类型（WINDS 或 CURRENTS）
            # 首先检查文件中是否已经设置了强迫场类型
            forcing_field_type = None
            in_forcing_nml_check = False
            for line in lines:
                if "&FORCING_NML" in line.upper():
                    in_forcing_nml_check = True
                    continue
                if in_forcing_nml_check and re.match(r'^\s*/\s*$', line) and not line.strip().startswith("!"):
                    in_forcing_nml_check = False
                    break
                if in_forcing_nml_check:
                    # 检查 FORCING%FIELD%WINDS 或 FORCING%FIELD%CURRENTS
                    if re.search(r'FORCING%FIELD%WINDS\s*=\s*T', line, re.IGNORECASE):
                        forcing_field_type = 'WINDS'
                        break
                    elif re.search(r'FORCING%FIELD%CURRENTS\s*=\s*T', line, re.IGNORECASE):
                        forcing_field_type = 'CURRENTS'
                        break
            
            # 如果文件中没有找到明确的设置，检查用户是否选择了流场
            if forcing_field_type is None:
                # 检查用户是否选择了流场
                has_current = False
                if hasattr(self, 'forcing_field_checkboxes'):
                    if 'current' in self.forcing_field_checkboxes:
                        checkbox = self.forcing_field_checkboxes['current']['checkbox']
                        has_current = checkbox.isChecked() if checkbox else False
                
                # 如果用户选择了流场，且存在流场文件，则使用流场配置
                if has_current and hasattr(self, 'selected_current_file') and self.selected_current_file:
                    if os.path.exists(self.selected_current_file):
                        forcing_field_type = 'CURRENTS'
                    else:
                        forcing_field_type = 'WINDS'
                else:
                    forcing_field_type = 'WINDS'
            
            # 根据强迫场类型确定文件名和变量名
            if forcing_field_type == 'CURRENTS':
                # 流场配置
                filename = "../current_level.nc"  # 默认流场文件名
                var_names = ['uo', 'vo']  # 默认流场变量名
                
                # 优先使用用户选择的流场文件
                current_file_path = None
                if hasattr(self, 'selected_current_file') and self.selected_current_file:
                    if os.path.exists(self.selected_current_file):
                        current_file_path = self.selected_current_file
                        filename = f"../{os.path.basename(self.selected_current_file)}"
                
                # 如果没有用户选择的文件，检查选择的流场文件
                if current_file_path is None:
                    current_files = glob.glob(os.path.join(self.selected_folder, "*current*.nc"))
                    if current_files:
                        current_nc_path = os.path.join(self.selected_folder, "current_level.nc")
                        if os.path.exists(current_nc_path):
                            filename = "../current_level.nc"
                            current_file_path = current_nc_path
                        else:
                            filename = f"../{os.path.basename(current_files[0])}"
                            current_file_path = current_files[0]
                
                # 从流场文件读取变量名
                if current_file_path and os.path.exists(current_file_path):
                    try:
                        with Dataset(current_file_path, "r") as ds:
                            # 检查变量名
                            if "uo" in ds.variables and "vo" in ds.variables:
                                var_names = ['uo', 'vo']
                            elif "UO" in ds.variables and "VO" in ds.variables:
                                var_names = ['UO', 'VO']
                            elif "u" in ds.variables and "v" in ds.variables:
                                var_names = ['u', 'v']
                    except Exception:
                        pass
            else:
                # 风场配置（默认）
                filename = "../wind.nc"  # 默认风场文件名
                var_names = ['u10', 'v10']  # 默认风场变量名
                
                # 检查选择的风场文件
                wind_files = glob.glob(os.path.join(self.selected_folder, "*wind*.nc"))
                if wind_files:
                    wind_nc_path = os.path.join(self.selected_folder, "wind.nc")
                    if os.path.exists(wind_nc_path):
                        filename = "../wind.nc"
                    else:
                        filename = f"../{os.path.basename(wind_files[0])}"
                
                # 从风场文件读取变量名
                wind_file_path = os.path.join(self.selected_folder, filename.replace("../", ""))
                if os.path.exists(wind_file_path):
                    try:
                        with Dataset(wind_file_path, "r") as ds:
                            # 检查变量名
                            if "u10" in ds.variables and "v10" in ds.variables:
                                var_names = ['u10', 'v10']
                            elif "wndewd" in ds.variables and "wndnwd" in ds.variables:
                                var_names = ['wndewd', 'wndnwd']
                            elif "uwnd" in ds.variables and "vwnd" in ds.variables:
                                var_names = ['uwnd', 'vwnd']
                    except Exception:
                        pass
            
            # 处理文件内容
            new_lines = []
            in_forcing_nml = False
            in_file_nml = False

            for line in lines:
                # 检查是否进入 FORCING_NML 块
                if "&FORCING_NML" in line.upper():
                    in_forcing_nml = True
                    new_lines.append(line)
                    continue

                # 检查是否离开 FORCING_NML 块
                if in_forcing_nml and re.match(r'^\s*/\s*$', line) and not line.strip().startswith("!"):
                    in_forcing_nml = False
                    new_lines.append(line)
                    continue

                # 在 FORCING_NML 块中处理
                if in_forcing_nml:
                    # 处理 FORCING%FIELD%* 行：保留所有字段，只修改对应的字段为 T，其他的为 F
                    if re.search(r'FORCING%FIELD%', line, re.IGNORECASE):
                        # 提取字段名
                        field_match = re.search(r'FORCING%FIELD%(\w+)', line, re.IGNORECASE)
                        if field_match:
                            found_field_name = field_match.group(1)
                            # 检查是否是当前需要的字段
                            if (forcing_field_type == 'CURRENTS' and found_field_name.upper() == 'CURRENTS') or \
                               (forcing_field_type == 'WINDS' and found_field_name.upper() == 'WINDS'):
                                # 设置为 T
                                new_lines.append(self._format_forcing_field_line(found_field_name, 'T'))
                            else:
                                # 设置为 F
                                new_lines.append(self._format_forcing_field_line(found_field_name, 'F'))
                        else:
                            # 如果无法提取字段名，保留原行
                            new_lines.append(line)
                        continue
                    # 保留 FORCING%TIMESTART 和 FORCING%TIMESTOP
                    elif re.search(r'FORCING%TIMESTART|FORCING%TIMESTOP', line, re.IGNORECASE):
                        new_lines.append(line)
                    # 保留 FORCING%GRID%*（确保 LATLON = T）
                    elif re.search(r'FORCING%GRID%', line, re.IGNORECASE):
                        if 'LATLON' in line.upper():
                            new_lines.append("  FORCING%GRID%LATLON          = T\n")
                        else:
                            new_lines.append(line)
                    else:
                        # 保留其他行（如注释等）
                        new_lines.append(line)
                    continue

                # 检查是否进入 FILE_NML 块
                if "&FILE_NML" in line.upper():
                    in_file_nml = True
                    new_lines.append(line)
                    continue

                # 检查是否离开 FILE_NML 块
                if in_file_nml and re.match(r'^\s*/\s*$', line) and not line.strip().startswith("!"):
                    new_lines.append(line)
                    in_file_nml = False
                    continue

                # 在 FILE_NML 块中处理
                if in_file_nml:
                    # 替换 FILE%VAR(*) 行（只替换，不插入）
                    # 匹配 FILE%VAR(数字) 模式，允许各种空格格式
                    var_match = re.search(r'FILE%VAR\s*\(\s*(\d+)\s*\)', line, re.IGNORECASE)
                    if var_match:
                        var_index = int(var_match.group(1))
                        # 如果索引在范围内，替换为新变量名
                        if 1 <= var_index <= len(var_names):
                            new_lines.append(f"  FILE%VAR({var_index})        = '{var_names[var_index - 1]}'\n")
                        # 如果索引超出范围，跳过（删除多余的变量行）
                        # 无论是否替换，都跳过原行（已替换或删除）
                        continue
                    # 替换 FILE%FILENAME
                    elif "FILE%FILENAME" in line:
                        new_lines.append(f"  FILE%FILENAME      = '{filename}'\n")
                    # 替换 FILE%LONGITUDE
                    elif "FILE%LONGITUDE" in line:
                        new_lines.append(f"  FILE%LONGITUDE     = 'longitude'\n")
                    # 替换 FILE%LATITUDE
                    elif "FILE%LATITUDE" in line:
                        new_lines.append(f"  FILE%LATITUDE      = 'latitude'\n")
                    else:
                        # 保留其他行（如注释等）
                        new_lines.append(line)
                    continue

                # 其他行直接添加
                new_lines.append(line)

            # 写入文件
            with open(nml_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            prefix = f"{grid_label} " if grid_label else ""
            field_name = "CURRENTS" if forcing_field_type == 'CURRENTS' else "WINDS"
            self.log(prefix + tr("step4_ww3_prnc_modified", "✅ 已修改 ww3_prnc.nml：FORCING%FIELD%{field} = T, FILE%FILENAME = '{file}'").format(field=field_name, file=filename))

        except Exception as e:
            self.log(tr("ww3_prnc_modify_error", "❌ 修改 {file}/ww3_prnc.nml 出错：{error}").format(file=os.path.basename(target_dir), error=e))

    def _modify_ww3_prnc_times(self):
        """修改 ww3_prnc.nml 中的 FORCING%TIMESTART 和 FORCING%TIMESTOP"""
        if not self.selected_folder or not isinstance(self.selected_folder, str):
            return
        
        start_date = self.shel_start_edit.text().strip()
        end_date = self.shel_end_edit.text().strip()
        
        # 验证日期格式
        if not (start_date.isdigit() and len(start_date) == 8):
            self.log(tr("start_date_format_error_skip", "⚠️ 起始日期格式错误，跳过修改 ww3_prnc.nml 的时间范围"))
            return
        
        if not (end_date.isdigit() and len(end_date) == 8):
            self.log(tr("end_date_format_error_skip", "⚠️ 结束日期格式错误，跳过修改 ww3_prnc.nml 的时间范围"))
            return
        
        # 转换为 ww3 格式：YYYYMMDD HHMMSS
        start_datetime = f"{start_date} 000000"
        end_datetime = f"{end_date} 235959"  # 停止时间设置为最后日期的 23:59:59
        
        self._modify_ww3_prnc_times_in_dir(self.selected_folder, start_datetime, end_datetime)
    
    def _modify_ww3_prnc_times_in_dir(self, target_dir, start_datetime=None, end_datetime=None, grid_label=""):
        """在指定目录下修改 ww3_prnc.nml 中的 FORCING%TIMESTART 和 FORCING%TIMESTOP"""
        if not target_dir or not isinstance(target_dir, str):
            return
        
        # 如果没有提供时间，从输入框获取
        if start_datetime is None or end_datetime is None:
            start_date = self.shel_start_edit.text().strip()
            end_date = self.shel_end_edit.text().strip()
            
            # 验证日期格式
            if not (start_date.isdigit() and len(start_date) == 8):
                return
            if not (end_date.isdigit() and len(end_date) == 8):
                return
            
            start_datetime = f"{start_date} 000000"
            end_datetime = f"{end_date} 235959"  # 停止时间设置为最后日期的 23:59:59
        
        nml_path = os.path.join(target_dir, "ww3_prnc.nml")
        if not os.path.exists(nml_path):
            return
        
        try:
            with open(nml_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            new_lines = []
            in_forcing_nml = False
            found_timestart = False
            found_timestop = False
            
            for line in lines:
                # 检查是否进入 FORCING_NML 块
                if "&FORCING_NML" in line:
                    in_forcing_nml = True
                    new_lines.append(line)
                # 检查是否离开 FORCING_NML 块
                elif in_forcing_nml and "/" in line and not line.strip().startswith("!"):
                    # 如果没找到，在结束标记前添加
                    if not found_timestart:
                        new_lines.append(f"  FORCING%TIMESTART            = '{start_datetime}'\n")
                    if not found_timestop:
                        new_lines.append(f"  FORCING%TIMESTOP             = '{end_datetime}'\n")
                    new_lines.append(line)
                    in_forcing_nml = False
                # 在 FORCING_NML 块中处理
                elif in_forcing_nml:
                    if "FORCING%TIMESTART" in line:
                        # 直接替换整行，保持原有的缩进和格式
                        # 提取行首的空白字符（缩进）
                        indent_match = re.match(r"^(\s*)", line)
                        indent = indent_match.group(1) if indent_match else "  "
                        # 生成新行，保持原有格式
                        new_line = f"{indent}FORCING%TIMESTART            = '{start_datetime}'\n"
                        new_lines.append(new_line)
                        found_timestart = True
                    elif "FORCING%TIMESTOP" in line:
                        # 直接替换整行，保持原有的缩进和格式
                        indent_match = re.match(r"^(\s*)", line)
                        indent = indent_match.group(1) if indent_match else "  "
                        # 生成新行，保持原有格式
                        new_line = f"{indent}FORCING%TIMESTOP             = '{end_datetime}'\n"
                        new_lines.append(new_line)
                        found_timestop = True
                    else:
                        # 其他行直接添加
                        new_lines.append(line)
                else:
                    # 不在 FORCING_NML 块中的行直接添加
                    new_lines.append(line)
            
            with open(nml_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            
            prefix = f"{grid_label} " if grid_label else ""
            self.log(f"{prefix}{tr('step4_ww3_prnc_times_updated', '✅ 已修改 ww3_prnc.nml：FORCING%TIMESTART = {start}, FORCING%TIMESTOP = {end}').format(start=start_datetime, end=end_datetime)}")
        
        except Exception as e:
            prefix = f"{grid_label} " if grid_label else ""
            self.log(tr("ww3_prnc_times_modify_failed", "{prefix}❌ 修改 ww3_prnc.nml 时间范围失败：{error}").format(prefix=prefix, error=e))

    def _generate_forcing_field_prnc_files(self, target_dir=None, use_relative_path=False):
        """
        根据选择的强迫场生成对应的 ww3_prnc_*.nml 文件
        
        参数:
            target_dir: 目标目录，如果为 None 则使用 self.selected_folder
            use_relative_path: 是否使用相对路径（../filename.nc），用于嵌套网格模式
        """
        if target_dir is None:
            target_dir = self.selected_folder
        
        if not target_dir or not isinstance(target_dir, str):
            return
        
        # 检查复选框状态
        if not hasattr(self, 'forcing_field_checkboxes'):
            return
        
        # 定义强迫场配置
        forcing_field_configs = {
            'current': {
                'field_name': 'CURRENTS',
                'file_attr': 'selected_current_file',
                'var_candidates': [['uo', 'UO'], ['vo', 'VO']],
                'output_filename': 'ww3_prnc_current.nml'
            },
            'level': {
                'field_name': 'WATER_LEVELS',
                'file_attr': 'selected_level_file',
                'var_candidates': [['zos', 'ZOS']],
                'output_filename': 'ww3_prnc_level.nml'
            },
            'ice': {
                'field_name': 'ICE_CONC',
                'file_attr': 'selected_ice_file',
                'var_candidates': [['siconc', 'SICONC']],
                'output_filename': 'ww3_prnc_ice.nml'
            }
        }
        
        # 为每个选中的强迫场生成文件
        for field_key, config in forcing_field_configs.items():
            # 检查复选框是否选中
            if field_key not in self.forcing_field_checkboxes:
                continue
            
            checkbox = self.forcing_field_checkboxes[field_key]['checkbox']
            if not checkbox.isChecked():
                continue
            
            # 检查文件是否真的存在于当前工作目录中
            file_path = None
            if hasattr(self, config['file_attr']):
                file_path = getattr(self, config['file_attr'])
            
            # 验证文件路径：必须存在且在当前工作目录中
            if not file_path or not isinstance(file_path, str):
                # 切换目录后可能遗留勾选，直接静默取消
                checkbox.setChecked(False)
                continue
            if not os.path.exists(file_path):
                grid_label = os.path.basename(target_dir) if target_dir != self.selected_folder else ""
                prefix = f"[{grid_label}] " if grid_label else ""
                self.log(tr("forcing_field_not_found", "{prefix}⚠️ 未找到 {field} 强迫场文件，跳过生成 {file}").format(prefix=prefix, field=field_key, file=config['output_filename']))
                checkbox.setChecked(False)
                continue
            
            # 确保文件在当前工作目录中（或嵌套网格时在父目录中）
            # 使用绝对路径进行比较，更可靠
            abs_file_path = os.path.abspath(file_path)
            abs_target_dir = os.path.abspath(target_dir)
            
            if not use_relative_path:
                # 普通网格模式：文件必须在 target_dir 中
                try:
                    common_path = os.path.commonpath([abs_file_path, abs_target_dir])
                    if common_path != abs_target_dir:
                        grid_label = os.path.basename(target_dir) if target_dir != self.selected_folder else ""
                        prefix = f"[{grid_label}] " if grid_label else ""
                        self.log(tr("forcing_field_not_in_workdir", "{prefix}⚠️ {field} 强迫场文件不在当前工作目录中，跳过生成 {file}").format(prefix=prefix, field=field_key, file=config['output_filename']))
                        checkbox.setChecked(False)
                        continue
                except ValueError:
                    # 路径不在同一驱动器上（Windows）或无法比较
                    grid_label = os.path.basename(target_dir) if target_dir != self.selected_folder else ""
                    prefix = f"[{grid_label}] " if grid_label else ""
                    self.log(tr("forcing_field_not_in_workdir", "{prefix}⚠️ {field} 强迫场文件不在当前工作目录中，跳过生成 {file}").format(prefix=prefix, field=field_key, file=config['output_filename']))
                    checkbox.setChecked(False)
                    continue
            else:
                # 嵌套网格模式：文件应该在父目录（selected_folder）中
                parent_dir = os.path.dirname(target_dir) if target_dir != self.selected_folder else self.selected_folder
                abs_parent_dir = os.path.abspath(parent_dir)
                try:
                    common_path = os.path.commonpath([abs_file_path, abs_parent_dir])
                    if common_path != abs_parent_dir:
                        grid_label = os.path.basename(target_dir) if target_dir != self.selected_folder else ""
                        prefix = f"[{grid_label}] " if grid_label else ""
                        self.log(tr("forcing_field_not_in_parent", "{prefix}⚠️ {field} 强迫场文件不在父目录中，跳过生成 {file}").format(prefix=prefix, field=field_key, file=config['output_filename']))
                        checkbox.setChecked(False)
                        continue
                except ValueError:
                    # 路径不在同一驱动器上（Windows）或无法比较
                    grid_label = os.path.basename(target_dir) if target_dir != self.selected_folder else ""
                    prefix = f"[{grid_label}] " if grid_label else ""
                    self.log(tr("forcing_field_not_in_parent", "{prefix}⚠️ {field} 强迫场文件不在父目录中，跳过生成 {file}").format(prefix=prefix, field=field_key, file=config['output_filename']))
                    checkbox.setChecked(False)
                    continue
            
            # 从目标目录中已修改时间的 ww3_prnc.nml 复制
            source_nml_path = os.path.join(target_dir, "ww3_prnc.nml")
            if not os.path.exists(source_nml_path):
                grid_label = os.path.basename(target_dir) if target_dir != self.selected_folder else ""
                prefix = f"[{grid_label}] " if grid_label else ""
                self.log(tr("ww3_prnc_not_found_skip_generate", "{prefix}⚠️ 未找到 ww3_prnc.nml 文件，跳过生成 {file}").format(prefix=prefix, file=config['output_filename']))
                continue
            
            # 复制文件
            output_path = os.path.join(target_dir, config['output_filename'])
            try:
                import shutil
                import re
                shutil.copy2(source_nml_path, output_path)
                
                # 修改新复制的文件，设置对应的 FORCING%FIELD%* 为 T，其他的为 F
                with open(output_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                # 获取文件路径和变量名（此时 file_path 已经在上面的检查中确认存在）
                var_names = None
                filename = None
                has_sithick = False
                sithick_var = None
                
                # file_path 已经在上面检查过，这里直接使用
                if file_path and os.path.exists(file_path):
                    # 设置文件名
                    if use_relative_path:
                        filename = f"../{os.path.basename(file_path)}"
                    else:
                        filename = os.path.basename(file_path)
                    # 从 NetCDF 文件中读取变量名
                    var_names = self._get_forcing_field_variables(file_path, config['var_candidates'])
                    
                    # 如果是冰场，检查是否包含 sithick 变量
                    if field_key == 'ice':
                        try:
                            from netCDF4 import Dataset
                            with Dataset(file_path, "r") as ds:
                                if 'sithick' in ds.variables:
                                    has_sithick = True
                                    sithick_var = 'sithick'
                                elif 'SITHICK' in ds.variables:
                                    has_sithick = True
                                    sithick_var = 'SITHICK'
                        except Exception:
                            pass
                
                # 如果没有找到变量名，使用默认值（冰场除外）
                if not var_names and field_key != 'ice':
                    var_names = [candidates[0] for candidates in config['var_candidates']]  # 使用第一个候选变量名
                
                # filename 应该已经设置好了，如果还没有（理论上不应该发生），使用默认值
                if not filename:
                    if use_relative_path:
                        if field_key == 'current':
                            filename = "../current_level.nc"
                        elif field_key == 'level':
                            filename = "../level.nc"
                        elif field_key == 'ice':
                            filename = "../ice.nc"
                    else:
                        if field_key == 'current':
                            filename = "current_level.nc"
                        elif field_key == 'level':
                            filename = "level.nc"
                        elif field_key == 'ice':
                            filename = "ice.nc"
                
                def _write_prnc_file(output_filename, field_name, var_names):
                    output_path = os.path.join(target_dir, output_filename)
                    shutil.copy2(source_nml_path, output_path)

                    new_lines = []
                    in_forcing_nml = False
                    in_file_nml = False

                    # 定义所有需要的字段
                    all_fields = ['WINDS', 'CURRENTS', 'WATER_LEVELS', 'ICE_CONC', 'ICE_PARAM1']
                    found_fields = set()
                    found_grid_latlon = False

                    for line in lines:
                        # 检查是否进入 FORCING_NML 块
                        if "&FORCING_NML" in line.upper():
                            in_forcing_nml = True
                            new_lines.append(line)
                            continue

                        # 检查是否离开 FORCING_NML 块
                        if in_forcing_nml and re.match(r'^\s*/\s*$', line) and not line.strip().startswith("!"):
                            # 在块结束前，添加缺失的字段
                            for fld in all_fields:
                                if fld not in found_fields:
                                    if fld == field_name:
                                        new_lines.append(self._format_forcing_field_line(fld, 'T'))
                                    else:
                                        new_lines.append(self._format_forcing_field_line(fld, 'F'))
                            # 确保 GRID%LATLON 存在
                            if not found_grid_latlon:
                                new_lines.append("  FORCING%GRID%LATLON          = T\n")
                            in_forcing_nml = False
                            new_lines.append(line)
                            continue

                        # 在 FORCING_NML 块中处理
                        if in_forcing_nml:
                            # 处理 FORCING%FIELD%* 行
                            if re.search(r'FORCING%FIELD%', line, re.IGNORECASE):
                                # 提取字段名
                                field_match = re.search(r'FORCING%FIELD%(\w+)', line, re.IGNORECASE)
                                if field_match:
                                    found_field_name = field_match.group(1)
                                    found_fields.add(found_field_name)
                                    # 检查是否是当前字段
                                    if found_field_name.upper() == field_name.upper():
                                        # 设置为 T
                                        new_lines.append(self._format_forcing_field_line(field_name, 'T'))
                                    else:
                                        # 设置为 F
                                        new_lines.append(self._format_forcing_field_line(found_field_name, 'F'))
                                continue
                            # 保留 FORCING%TIMESTART 和 FORCING%TIMESTOP
                            elif re.search(r'FORCING%TIMESTART|FORCING%TIMESTOP', line, re.IGNORECASE):
                                new_lines.append(line)
                            # 保留 FORCING%GRID%*（确保 LATLON = T）
                            elif re.search(r'FORCING%GRID%', line, re.IGNORECASE):
                                if 'LATLON' in line.upper():
                                    new_lines.append("  FORCING%GRID%LATLON          = T\n")
                                    found_grid_latlon = True
                                else:
                                    new_lines.append(line)
                            else:
                                # 保留其他行（如注释等）
                                new_lines.append(line)
                            continue

                        # 检查是否进入 FILE_NML 块
                        if "&FILE_NML" in line.upper():
                            in_file_nml = True
                            new_lines.append(line)
                            continue

                        # 检查是否离开 FILE_NML 块
                        if in_file_nml and re.match(r'^\s*/\s*$', line) and not line.strip().startswith("!"):
                            in_file_nml = False
                            new_lines.append(line)
                            continue

                        # 在 FILE_NML 块中处理
                        if in_file_nml:
                            # 替换 FILE%FILENAME
                            if "FILE%FILENAME" in line:
                                new_lines.append(f"  FILE%FILENAME      = '{filename}'\n")
                                continue
                            # 替换 FILE%VAR(*) 行
                            var_match = re.search(r'FILE%VAR\s*\(\s*(\d+)\s*\)', line, re.IGNORECASE)
                            if var_match:
                                var_index = int(var_match.group(1))
                                # 如果索引在范围内，替换为新变量名
                                if 1 <= var_index <= len(var_names):
                                    new_lines.append(f"  FILE%VAR({var_index})        = '{var_names[var_index - 1]}'\n")
                                # 如果索引超出范围，跳过（删除多余的变量行）
                                continue
                            # 保留其他行（FILE%LONGITUDE, FILE%LATITUDE 等）
                            else:
                                new_lines.append(line)
                            continue

                        # 其他行直接添加
                        new_lines.append(line)

                    # 写回文件
                    with open(output_path, "w", encoding="utf-8") as f:
                        f.writelines(new_lines)

                    grid_label = os.path.basename(target_dir) if target_dir != self.selected_folder else ""
                    prefix = f"[{grid_label}] " if grid_label else ""
                    self.log(tr("file_copied_modified", "✅ 已复制并修改 {file}：FORCING%FIELD%{field} = T").format(file=output_filename, field=field_name))

                tasks = []
                if field_key == 'ice':
                    # 只有存在 siconc 才生成冰场 prnc
                    if not var_names:
                        continue
                    tasks.append({
                        "output_filename": "ww3_prnc_ice.nml",
                        "field_name": "ICE_CONC",
                        "var_names": var_names
                    })
                    if has_sithick:
                        tasks.append({
                            "output_filename": "ww3_prnc_ice1.nml",
                            "field_name": "ICE_PARAM1",
                            "var_names": [sithick_var or "sithick"]
                        })
                else:
                    if not var_names:
                        var_names = [candidates[0] for candidates in config['var_candidates']]  # 使用第一个候选变量名
                    tasks.append({
                        "output_filename": config['output_filename'],
                        "field_name": config['field_name'],
                        "var_names": var_names
                    })

                for task in tasks:
                    try:
                        _write_prnc_file(task["output_filename"], task["field_name"], task["var_names"])
                    except Exception as e:
                        grid_label = os.path.basename(target_dir) if target_dir != self.selected_folder else ""
                        prefix = f"[{grid_label}] " if grid_label else ""
                        self.log(tr("file_copy_modify_failed", "❌ 复制并修改 {file} 失败：{error}").format(file=task["output_filename"], error=e))
            except Exception as e:
                grid_label = os.path.basename(target_dir) if target_dir != self.selected_folder else ""
                prefix = f"[{grid_label}] " if grid_label else ""
                self.log(tr("file_copy_modify_failed", "❌ 复制并修改 {file} 失败：{error}").format(file=config['output_filename'], error=e))
    
    def _modify_ww3_shel_forcing_inputs(self, target_dir=None):
        """修改 ww3_shel.nml 中的 INPUT%FORCING%* 设置，根据选择的强迫场设置为 T 或 F"""
        if target_dir is None:
            target_dir = self.selected_folder
        
        if not target_dir or not isinstance(target_dir, str):
            return
        
        # 嵌套网格模式下使用 ww3_multi.nml，普通网格模式下使用 ww3_shel.nml
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        if grid_type == nested_text or grid_type == "嵌套网格":
            ww3_shel_path = os.path.join(target_dir, "ww3_multi.nml")
        else:
            ww3_shel_path = os.path.join(target_dir, "ww3_shel.nml")
        if not os.path.exists(ww3_shel_path):
            file_name = "ww3_multi.nml" if (grid_type == nested_text or grid_type == "嵌套网格") else "ww3_shel.nml"
            self.log(tr("file_not_found_skip_forcing", "⚠️ 未找到 {file}：{path}，跳过修改 INPUT%FORCING%*").format(file=file_name, path=ww3_shel_path))
            return
        
        self._modify_ww3_shel_forcing_inputs_in_dir(target_dir, ww3_shel_path)
    
    def _modify_ww3_shel_forcing_inputs_in_dir(self, target_dir, ww3_shel_path=None, grid_label=""):
        """在指定目录中修改 ww3_shel.nml 中的 INPUT%FORCING%* 设置"""
        if not target_dir or not isinstance(target_dir, str):
            return
        
        if ww3_shel_path is None:
            ww3_shel_path = os.path.join(target_dir, "ww3_shel.nml")
        
        if not os.path.exists(ww3_shel_path):
            return
        
        # 检查复选框状态，确定哪些强迫场被选中
        has_wind = True  # 风场总是启用
        has_current = False
        has_level = False
        has_ice = False
        has_ice_param1 = False
        
        if hasattr(self, 'forcing_field_checkboxes'):
            if 'current' in self.forcing_field_checkboxes:
                checkbox = self.forcing_field_checkboxes['current']['checkbox']
                has_current = checkbox.isChecked() if checkbox else False
            
            if 'level' in self.forcing_field_checkboxes:
                checkbox = self.forcing_field_checkboxes['level']['checkbox']
                has_level = checkbox.isChecked() if checkbox else False
            
            if 'ice' in self.forcing_field_checkboxes:
                checkbox = self.forcing_field_checkboxes['ice']['checkbox']
                has_ice = checkbox.isChecked() if checkbox else False
                
                # 如果冰场被选中，检查是否包含 sithick 变量
                if has_ice and hasattr(self, 'selected_ice_file') and self.selected_ice_file:
                    try:
                        from netCDF4 import Dataset
                        if os.path.exists(self.selected_ice_file):
                            with Dataset(self.selected_ice_file, "r") as ds:
                                has_ice_param1 = 'sithick' in ds.variables or 'SITHICK' in ds.variables
                    except Exception:
                        pass
        
        try:
            import re
            with open(ww3_shel_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            new_lines = []
            in_input_nml = False
            input_nml_modified = False
            
            for line in lines:
                # 检查是否进入 INPUT_NML 块
                if "&INPUT_NML" in line.upper():
                    in_input_nml = True
                    new_lines.append(line)
                # 检查是否离开 INPUT_NML 块
                elif in_input_nml and "/" in line and not line.strip().startswith("!"):
                    # 如果还没有修改过，在结束前添加所有设置
                    if not input_nml_modified:
                        # 添加所有 INPUT%FORCING%* 设置
                        indent = "  "
                        new_lines.append(f"{indent}INPUT%FORCING%WINDS         = '{'T' if has_wind else 'F'}'\n")
                        new_lines.append(f"{indent}INPUT%FORCING%WATER_LEVELS  = '{'T' if has_level else 'F'}'\n")
                        new_lines.append(f"{indent}INPUT%FORCING%CURRENTS      = '{'T' if has_current else 'F'}'\n")
                        new_lines.append(f"{indent}INPUT%FORCING%ICE_CONC      = '{'T' if has_ice else 'F'}'\n")
                        new_lines.append(f"{indent}INPUT%FORCING%ICE_PARAM1    = '{'T' if has_ice_param1 else 'F'}'\n")
                        input_nml_modified = True
                    new_lines.append(line)
                    in_input_nml = False
                # 在 INPUT_NML 块中处理
                elif in_input_nml:
                    # 跳过现有的 INPUT%FORCING%* 行
                    if re.search(r'INPUT%FORCING%', line, re.IGNORECASE):
                        continue
                    else:
                        new_lines.append(line)
                else:
                    # 不在 INPUT_NML 块中的行直接添加
                    new_lines.append(line)
            
            # 如果文件中没有 INPUT_NML 块，在文件末尾添加
            if not in_input_nml and not input_nml_modified:
                new_lines.append("\n&INPUT_NML\n")
                new_lines.append(f"  INPUT%FORCING%WINDS         = '{'T' if has_wind else 'F'}'\n")
                new_lines.append(f"  INPUT%FORCING%WATER_LEVELS  = '{'T' if has_level else 'F'}'\n")
                new_lines.append(f"  INPUT%FORCING%CURRENTS      = '{'T' if has_current else 'F'}'\n")
                new_lines.append(f"  INPUT%FORCING%ICE_CONC      = '{'T' if has_ice else 'F'}'\n")
                new_lines.append(f"  INPUT%FORCING%ICE_PARAM1    = '{'T' if has_ice_param1 else 'F'}'\n")
                new_lines.append("/\n")
            
            # 写入文件
            with open(ww3_shel_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            
            prefix = f"{grid_label} " if grid_label else ""
            file_name = os.path.basename(ww3_shel_path)
            self.log(tr("file_modified_forcing", "{prefix}✅ 已修改 {file}：更新 INPUT%FORCING%* 设置").format(prefix=prefix, file=file_name))
            
        except Exception as e:
            prefix = f"{grid_label} " if grid_label else ""
            file_name = os.path.basename(ww3_shel_path) if ww3_shel_path else "ww3_shel.nml"
            self.log(tr("file_forcing_modify_failed", "{prefix}❌ 修改 {file} 中的 INPUT%FORCING%* 失败：{error}").format(prefix=prefix, file=file_name, error=e))
    
    def _get_forcing_field_variables(self, file_path, var_candidates):
        """
        从 NetCDF 文件中读取变量名
        
        参数:
            file_path: NetCDF 文件路径
            var_candidates: 变量名候选列表，例如 [['uo', 'UO'], ['vo', 'VO']] 或 [['zos', 'ZOS']]
        
        返回:
            变量名列表，例如 ['uo', 'vo'] 或 ['zos']
        """
        try:
            from netCDF4 import Dataset
            with Dataset(file_path, "r") as ds:
                var_names = []
                for candidates in var_candidates:
                    found = False
                    for candidate in candidates:
                        if candidate in ds.variables:
                            var_names.append(candidate)
                            found = True
                            break
                    if not found:
                        return None  # 如果任何一个变量都找不到，返回 None
                return var_names
        except Exception as e:
            return None
    
    def _create_prnc_content(self, template, field_name, filename, var_names, start_datetime, end_datetime, file_path=None):
        """
        根据模板创建新的 prnc 文件内容
        
        参数:
            template: 模板内容
            field_name: 强迫场名称，例如 'CURRENTS', 'WATER_LEVELS', 'ICE_CONC'
            filename: 文件名，例如 'current.nc'
            var_names: 变量名列表，例如 ['uo', 'vo'] 或 ['zos']
            start_datetime: 开始时间，例如 '20250101 000000'
            end_datetime: 结束时间，例如 '20250131 235959'
            file_path: 文件路径（仅用于冰场检查 sithick 变量）
        
        返回:
            新的文件内容
        """
        import re
        from netCDF4 import Dataset
        
        # 检查冰场是否包含 sithick 变量
        has_sithick = False
        if field_name == 'ICE_CONC' and file_path:
            try:
                with Dataset(file_path, "r") as ds:
                    has_sithick = 'sithick' in ds.variables or 'SITHICK' in ds.variables
            except Exception:
                pass
        
        # 确定需要设置为 T 的字段列表
        fields_to_enable = [field_name]
        if field_name == 'ICE_CONC' and has_sithick:
            fields_to_enable.append('ICE_PARAM1')
        
        # 逐行处理，确保替换精确
        lines = template.split('\n')
        new_lines = []
        
        for line in lines:
            # 替换 FORCING%FIELD%* 字段
            if 'FORCING%FIELD%' in line and '=' in line:
                # 检查当前行是哪个字段
                field_match = re.search(r'FORCING%FIELD%(\w+)', line)
                if field_match:
                    current_field = field_match.group(1)
                    # 如果是要启用的字段，设置为 T
                    if current_field in fields_to_enable:
                        line = re.sub(
                            r'(\s+FORCING%FIELD%\w+\s*=\s*)\w+',
                            r'\1T',
                            line
                        )
                    else:
                        # 其他字段设置为 F
                        line = re.sub(
                            r'(\s+FORCING%FIELD%\w+\s*=\s*)\w+',
                            r'\1F',
                            line
                        )
            
            # 替换时间范围
            if 'FORCING%TIMESTART' in line:
                line = re.sub(
                    r"(\s+FORCING%TIMESTART\s*=\s*')\d{8}\s+\d{6}(')",
                    lambda m: f"{m.group(1)}{start_datetime}{m.group(2)}",
                    line
                )
            elif 'FORCING%TIMESTOP' in line:
                line = re.sub(
                    r"(\s+FORCING%TIMESTOP\s*=\s*')\d{8}\s+\d{6}(')",
                    lambda m: f"{m.group(1)}{end_datetime}{m.group(2)}",
                    line
                )
            
            # 替换文件名
            if 'FILE%FILENAME' in line:
                line = re.sub(
                    r"(FILE%FILENAME\s*=\s*')[\w\.]+(')",
                    lambda m: f"{m.group(1)}{filename}{m.group(2)}",
                    line
                )
            
            new_lines.append(line)
        
        # 重新组合文本，用于后续的变量名替换
        template = '\n'.join(new_lines)
        
        # 替换变量名
        # 先删除所有 FILE%VAR(*) 行（包括可能的注释）
        lines = template.split('\n')
        new_lines = []
        in_file_nml = False
        var_inserted = False
        
        for line in lines:
            # 检查是否进入 FILE_NML 块
            if "&FILE_NML" in line:
                in_file_nml = True
                new_lines.append(line)
            # 检查是否离开 FILE_NML 块
            elif in_file_nml and "/" in line and not line.strip().startswith("!"):
                # 如果还没插入变量名，在结束标记前插入
                # if not var_inserted:
                #     for i, var_name in enumerate(var_names, 1):
                #         new_lines.append(f"  FILE%VAR({i})        = '{var_name}'")
                new_lines.append(line)
                in_file_nml = False
                var_inserted = False
            # 在 FILE_NML 块中处理
            elif in_file_nml:
                # 跳过 FILE%VAR(*) 行
                if re.match(r'\s+FILE%VAR\(\d+\)', line):
                    continue
                # 在 FILE%LATITUDE 行后插入变量名
                elif "FILE%LATITUDE" in line:
                    new_lines.append(line)
                    if not var_inserted:
                        for i, var_name in enumerate(var_names, 1):
                            new_lines.append(f"  FILE%VAR({i})        = '{var_name}'")
                        var_inserted = True
                else:
                    new_lines.append(line)
            else:
                # 不在 FILE_NML 块中的行直接添加
                new_lines.append(line)
        
        return '\n'.join(new_lines)


    # ==================== 脚本生成 ====================



    # ==================== ST 版本选择 ====================
    def apply_st_choice(self):
        """应用 ST 版本选择"""
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

            # 默认的 headers 和路径映射
            default_headers = {
                "ST2": "#wavewatch3--ST2",
                "ST4": "#wavewatch3--ST4",
                "ST6": "#wavewatch3--ST6",
                "ST6a": "#wavewatch3--ST6a",
                "ST6b": "#wavewatch3--ST6b",
            }

            default_base_map = {
                "ST2": "/public/home/weiyl001/software/wavewatch3/model",
                "ST4": "/public/home/weiyl001/software2/ww4/model",
                "ST6": "/public/home/weiyl001/software2/ww6/model",
                "ST6a": "/public/home/weiyl001/software2/ww6a/model",
                "ST6b": "/public/home/weiyl001/software2/ww6b/model",
            }

            selected = self.st_var
            st_versions = load_config().get("ST_VERSIONS", [])
            base_dir = None
            headers = default_headers.copy()

            # 从配置文件中读取 ST 版本信息
            if st_versions and isinstance(st_versions, list):
                for version in st_versions:
                    if isinstance(version, dict) and version.get("name") == selected:
                        base_dir = version.get("path", "")
                        if not base_dir:
                            base_dir = default_base_map.get(selected)
                        break

            if base_dir is None:
                base_dir = default_base_map.get(selected)

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

            # 更新可执行文件路径
            if base_dir:
                exe_grid = f"{base_dir}/exe/ww3_grid\n"
                exe_prnc = f"{base_dir}/exe/ww3_prnc\n"
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

    def _modify_namelists_e3d_if_needed(self):
        """如果需要，修改 namelists.nml 中的 E3D 参数（支持嵌套网格模式）"""
        # 检查计算模式是否为"谱空间逐点计算"
        if not self._is_spectral_point_mode():
            return
        
        # 检查点列表是否不为空（跳过表头，所以 rowCount() > 1）
        if not hasattr(self, 'spectral_points_table'):
            return
        
        point_count = self.spectral_points_table.rowCount()
        if point_count <= 1:  # 只有表头，没有数据点
            return
        
        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")
        
        if is_nested_grid:
            # 嵌套网格模式：修改 coarse 和 fine 目录下的文件
            coarse_dir = os.path.join(self.selected_folder, "coarse")
            fine_dir = os.path.join(self.selected_folder, "fine")
            
            if os.path.isdir(coarse_dir):
                self._modify_namelists_e3d_in_dir(coarse_dir)
            if os.path.isdir(fine_dir):
                self._modify_namelists_e3d_in_dir(fine_dir)
        else:
            # 普通网格模式：修改工作目录下的文件
            self._modify_namelists_e3d_in_dir(self.selected_folder)
        
        # 导出点列表到 points.list 文件（普通网格模式）
        if not is_nested_grid:
            self._export_points_to_file()
        
        # 同时修改 ww3_shel.nml，添加 TYPE%POINT%FILE（支持嵌套网格模式）
        # 注意：在普通网格模式下，这些修改的日志会在 _modify_ww3_shel_times_to_dir 中合并输出
        # 在嵌套网格模式下，这些修改的日志会在各自的 _modify_ww3_shel_times_to_dir 中合并输出
        # 所以这里需要根据网格类型决定是否使用 silent 模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")
        
        # 在普通网格模式下，使用 silent=True，因为日志会在后续的 _modify_ww3_shel_times_to_dir 中合并输出
        # 在嵌套网格模式下，这些方法会自己处理日志输出（因为它们不会调用 _modify_ww3_shel_times_to_dir）
        # 但实际上，嵌套网格模式下这些修改是在 _apply_spectral_params_to_dir 中处理的，那里也会调用 _modify_ww3_shel_times_to_dir
        # 所以统一使用 silent=True，让 _modify_ww3_shel_times_to_dir 统一输出合并的日志
        self._modify_ww3_shel_point_file(silent=True)
        
        # 修改 ww3_shel.nml，添加 DATE%POINT 和 DATE%BOUNDARY（支持嵌套网格模式）
        self._modify_ww3_shel_date_point(silent=True)
    
    def _modify_namelists_e3d_in_dir(self, target_dir):
        """在指定目录下修改 namelists.nml 中的 E3D 参数"""
        namelists_path = os.path.join(target_dir, "namelists.nml")
        if not os.path.exists(namelists_path):
            return
        
        try:
            with open(namelists_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            new_lines = []
            modified = False
            for line in lines:
                # 匹配 &OUTS E3D = 0 / 或类似格式
                if re.match(r'^\s*&OUTS\s+E3D\s*=\s*0\s*/', line, re.IGNORECASE):
                    new_lines.append("&OUTS E3D = 1 /\n")
                    modified = True
                else:
                    new_lines.append(line)
            
            if modified:
                with open(namelists_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                self.log(tr("step4_namelists_e3d_updated", "✅ 已修改 namelists.nml：将 E3D 从 0 改为 1（谱空间逐点计算模式）"))
        
        except Exception as e:
            self.log(tr("namelists_modify_error", "❌ 修改 namelists.nml 时出错：{error}").format(error=str(e)))

    def _modify_ww3_shel_point_file(self, silent=False):
        """修改 ww3_shel.nml，在 TYPE%FIELD%LIST 下一行添加 TYPE%POINT%FILE（支持嵌套网格模式）
        
        参数:
            silent: 如果为 True，不输出日志（用于合并日志）
        """
        # 检查计算模式是否为"谱空间逐点计算"
        if not self._is_spectral_point_mode():
            return
        
        # 检查点列表是否不为空（跳过表头，所以 rowCount() > 1）
        if not hasattr(self, 'spectral_points_table'):
            return
        
        point_count = self.spectral_points_table.rowCount()
        if point_count <= 1:  # 只有表头，没有数据点
            return
        
        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")
        
        if is_nested_grid:
            # 嵌套网格模式：修改 coarse 和 fine 目录下的文件
            coarse_dir = os.path.join(self.selected_folder, "coarse")
            fine_dir = os.path.join(self.selected_folder, "fine")
            
            if os.path.isdir(coarse_dir):
                self._modify_ww3_shel_point_file_in_dir(coarse_dir, silent=silent)
            if os.path.isdir(fine_dir):
                self._modify_ww3_shel_point_file_in_dir(fine_dir, silent=silent)
        else:
            # 普通网格模式：修改工作目录下的文件
            self._modify_ww3_shel_point_file_in_dir(self.selected_folder, silent=silent)
    
    def _modify_ww3_shel_point_file_in_dir(self, target_dir, silent=False):
        """在指定目录下修改 ww3_shel.nml，在 TYPE%FIELD%LIST 下一行添加 TYPE%POINT%FILE
        
        参数:
            target_dir: 目标目录
            silent: 如果为 True，不输出日志（用于合并日志）
        
        返回:
            bool: 是否成功修改
        """
        ww3_shel_path = os.path.join(target_dir, "ww3_shel.nml")
        if not os.path.exists(ww3_shel_path):
            return False
        
        try:
            with open(ww3_shel_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            new_lines = []
            modified_point_file = False
            i = 0
            while i < len(lines):
                line = lines[i]
                
                # 检查是否为注释行（以 ! 开头，去除前导空格后）
                line_stripped = line.lstrip()
                is_comment = line_stripped.startswith('!')
                
                # 查找 TYPE%FIELD%LIST 这一行（不区分大小写，允许空格变化）
                # 只处理非注释行
                if not is_comment and re.search(r'TYPE%FIELD%LIST', line, re.IGNORECASE) and "=" in line:
                    # 保留原行，不替换
                    new_lines.append(line)
                    
                    # 检查下一行是否已经有 TYPE%POINT%FILE
                    if i + 1 < len(lines):
                        next_line = lines[i + 1]
                        if re.search(r'TYPE%POINT%FILE', next_line, re.IGNORECASE):
                            # 已经存在，跳过添加，但需要保留原行
                            new_lines.append(next_line)
                            i += 1
                            continue
                    
                    # 在下一行添加 TYPE%POINT%FILE = 'points.list'
                    new_lines.append("  TYPE%POINT%FILE          = 'points.list'\n")
                    modified_point_file = True
                else:
                    new_lines.append(line)
                
                i += 1
            
            if modified_point_file:
                with open(ww3_shel_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                if not silent:
                    log_msg = tr("step4_ww3_shel_type_point_only", "✅ 已修改 ww3_shel.nml：添加 TYPE%POINT%FILE = 'points.list'")
                    self.log(log_msg)
                return True
            return False
        
        except Exception as e:
            if not silent:
                self.log(tr("ww3_shel_modify_error_str", "❌ 修改 ww3_shel.nml 时出错：{error}").format(error=str(e)))
            return False

    def _modify_ww3_shel_date_point(self, silent=False):
        """修改 ww3_shel.nml，在 DATE%FIELD 下一行添加 DATE%POINT 和 DATE%BOUNDARY（支持嵌套网格模式）
        
        参数:
            silent: 如果为 True，不输出日志（用于合并日志）
        """
        # 检查计算模式是否为"谱空间逐点计算"
        if not self._is_spectral_point_mode():
            return
        
        # 检查点列表是否不为空（跳过表头，所以 rowCount() > 1）
        if not hasattr(self, 'spectral_points_table'):
            return
        
        point_count = self.spectral_points_table.rowCount()
        if point_count <= 1:  # 只有表头，没有数据点
            return
        
        # 获取时间范围和计算精度
        start_date = self.shel_start_edit.text().strip()
        end_date = self.shel_end_edit.text().strip()
        compute_precision = self.shel_step_edit.text().strip()
        
        if not (start_date.isdigit() and len(start_date) == 8 and end_date.isdigit() and len(end_date) == 8):
            if not silent:
                self.log(tr("date_format_error_skip_point", "❌ 起始/结束日期格式错误，应为 YYYYMMDD，跳过 DATE%POINT 和 DATE%BOUNDARY 修改"))
            return
        
        if not compute_precision.isdigit():
            if not silent:
                self.log(tr("compute_precision_error_skip_point", "❌ 计算精度必须为数字（秒），跳过 DATE%POINT 和 DATE%BOUNDARY 修改"))
            return
        
        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")
        
        if is_nested_grid:
            # 嵌套网格模式：修改 coarse 和 fine 目录下的文件
            coarse_dir = os.path.join(self.selected_folder, "coarse")
            fine_dir = os.path.join(self.selected_folder, "fine")
            
            if os.path.isdir(coarse_dir):
                self._modify_ww3_shel_date_point_in_dir(coarse_dir, start_date, end_date, compute_precision, silent=silent)
            if os.path.isdir(fine_dir):
                # 对于内网格，使用内网格的计算精度
                inner_shel_step = self.inner_shel_step_edit.text().strip()
                inner_compute_precision = inner_shel_step if inner_shel_step.isdigit() else compute_precision
                self._modify_ww3_shel_date_point_in_dir(fine_dir, start_date, end_date, inner_compute_precision, silent=silent)
        else:
            # 普通网格模式：修改工作目录下的文件
            self._modify_ww3_shel_date_point_in_dir(self.selected_folder, start_date, end_date, compute_precision, silent=silent)
    
    def _modify_ww3_shel_date_point_in_dir(self, target_dir, start_date, end_date, compute_precision, silent=False):
        """在指定目录下修改 ww3_shel.nml，在 DATE%FIELD 下一行添加 DATE%POINT 和 DATE%BOUNDARY
        
        参数:
            target_dir: 目标目录
            start_date: 起始日期
            end_date: 结束日期
            compute_precision: 计算精度
            silent: 如果为 True，不输出日志（用于合并日志）
        
        返回:
            bool: 是否成功修改
        """
        ww3_shel_path = os.path.join(target_dir, "ww3_shel.nml")
        if not os.path.exists(ww3_shel_path):
            return False
        
        try:
            with open(ww3_shel_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            new_lines = []
            modified = False
            i = 0
            while i < len(lines):
                line = lines[i]
                
                # 检查是否为注释行（以 ! 开头，去除前导空格后）
                line_stripped = line.lstrip()
                is_comment = line_stripped.startswith('!')
                
                new_lines.append(line)
                
                # 查找 DATE%FIELD 所在行（不区分大小写）
                # 只处理非注释行
                if not is_comment and re.search(r'DATE%FIELD', line, re.IGNORECASE):
                    # 检查下一行是否已经有 DATE%POINT（也需要检查是否为注释行）
                    if i + 1 < len(lines):
                        next_line = lines[i + 1]
                        next_line_stripped = next_line.lstrip()
                        next_is_comment = next_line_stripped.startswith('!')
                        # 如果下一行是注释行，或者下一行已经有 DATE%POINT（非注释），则跳过
                        if not next_is_comment and re.search(r'DATE%POINT', next_line, re.IGNORECASE):
                            # 已经存在，跳过
                            i += 1
                            continue
                    
                    # 在下一行添加 DATE%POINT 和 DATE%BOUNDARY
                    new_lines.append(f"  DATE%POINT          = '{start_date} 000000' '{compute_precision}' '{end_date} 235959'\n")
                    new_lines.append(f"  DATE%BOUNDARY       = '{start_date} 000000' '86400' '{end_date} 235959'\n")
                    modified = True
                
                i += 1
            
            if modified:
                with open(ww3_shel_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                if not silent:
                    self.log(tr("step4_ww3_shel_date_updated", "✅ 已修改 ww3_shel.nml：添加 DATE%POINT 和 DATE%BOUNDARY（谱空间逐点计算模式）"))
                return True
            return False
        
        except Exception as e:
            if not silent:
                self.log(tr("ww3_shel_modify_error_str", "❌ 修改 ww3_shel.nml 时出错：{error}").format(error=str(e)))
            return False

    def _apply_spectral_params_to_dir(self, target_dir, start_date, end_date, compute_precision, output_precision):
        """在指定目录下应用谱空间逐点计算相关参数"""
        # 检查计算模式是否为"谱空间逐点计算"
        if not self._is_spectral_point_mode():
            return
        
        # 检查点列表是否不为空（跳过表头，所以 rowCount() > 1）
        if not hasattr(self, 'spectral_points_table'):
            return
        
        point_count = self.spectral_points_table.rowCount()
        if point_count <= 1:  # 只有表头，没有数据点
            return
        
        # 读取点列表数据
        points_data = []
        for i in range(1, self.spectral_points_table.rowCount()):
            lon_item = self.spectral_points_table.item(i, 0)
            lat_item = self.spectral_points_table.item(i, 1)
            name_item = self.spectral_points_table.item(i, 2)
            
            if lon_item and lat_item:
                try:
                    lon = float(lon_item.text().strip())
                    lat = float(lat_item.text().strip())
                    name = name_item.text().strip() if name_item else f"Point_{i-1}"
                    points_data.append({
                        'lon': lon,
                        'lat': lat,
                        'name': name
                    })
                except ValueError:
                    continue
        
        if not points_data:
            return
        
        # 修改 namelists.nml
        self._modify_namelists_e3d_in_dir(target_dir)
        
        # 导出 points.list
        self._export_points_to_dir(target_dir, points_data)
        
        # 修改 ww3_shel.nml
        # 在嵌套网格模式下，这些修改会在 _apply_ww3_params_to_dir 之后进行
        # 在普通网格模式下，这些修改会在 _modify_ww3_shel_times_to_dir 之前进行
        # 所以统一使用 silent=True，让 _modify_ww3_shel_times_to_dir 或这里统一输出合并的日志
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")
        
        # 修改 TYPE%POINT%FILE
        modified_point_file = self._modify_ww3_shel_point_file_in_dir(target_dir, silent=True)
        
        # 修改 DATE%POINT 和 DATE%BOUNDARY
        modified_date_point = False
        if start_date and end_date and compute_precision:
            if (start_date.isdigit() and len(start_date) == 8 and 
                end_date.isdigit() and len(end_date) == 8 and 
                compute_precision.isdigit()):
                modified_date_point = self._modify_ww3_shel_date_point_in_dir(target_dir, start_date, end_date, compute_precision, silent=True)
        
        # 在嵌套网格模式下，这里输出合并的日志（因为 _modify_ww3_shel_times_to_dir 已经在之前调用了）
        if is_nested_grid and (modified_point_file or modified_date_point):
            # 获取时间信息用于日志
            start_date_for_log = self.shel_start_edit.text().strip()
            end_date_for_log = self.shel_end_edit.text().strip()
            compute_precision_for_log = compute_precision if compute_precision else self.shel_step_edit.text().strip()
            
            parts = []
            if start_date_for_log and end_date_for_log and compute_precision_for_log:
                parts.append(tr("step4_date_range_compute_step", "起始={start}, 结束={end}, 计算步长={step}s").format(start=start_date_for_log, end=end_date_for_log, step=compute_precision_for_log))
            if modified_point_file:
                parts.append(tr("step4_added_type_point_file", "添加 TYPE%POINT%FILE = 'points.list'"))
            if modified_date_point:
                parts.append(tr("step4_added_date_point_boundary", "添加 DATE%POINT 和 DATE%BOUNDARY"))
            
            if parts:
                log_msg = tr("step4_ww3_shel_spectral_point_updated", "✅ 已更新 ww3_shel.nml（谱空间逐点计算模式）：{details}").format(details="，".join(parts))
                self.log(log_msg)
        
        # 修改 ww3_ounp.nml
        if start_date and output_precision:
            if (start_date.isdigit() and len(start_date) == 8 and 
                output_precision.isdigit()):
                self._modify_ww3_ounp_in_dir(target_dir, start_date, output_precision)

    def _export_points_to_file(self):
        """将当前点列表导出到 points.list 文件（清空原有内容，支持嵌套网格模式）"""
        # 检查计算模式是否为"谱空间逐点计算"
        if not self._is_spectral_point_mode():
            return
        
        # 检查点列表是否不为空（跳过表头，所以 rowCount() > 1）
        if not hasattr(self, 'spectral_points_table'):
            return
        
        point_count = self.spectral_points_table.rowCount()
        if point_count <= 1:  # 只有表头，没有数据点
            return
        
        # 读取表格中的所有点位（跳过表头，从第1行开始）
        points_data = []
        for i in range(1, self.spectral_points_table.rowCount()):
            lon_item = self.spectral_points_table.item(i, 0)
            lat_item = self.spectral_points_table.item(i, 1)
            name_item = self.spectral_points_table.item(i, 2)
            
            if lon_item and lat_item:
                try:
                    lon = float(lon_item.text().strip())
                    lat = float(lat_item.text().strip())
                    name = name_item.text().strip() if name_item else f"Point_{i-1}"
                    points_data.append({
                        'lon': lon,
                        'lat': lat,
                        'name': name
                    })
                except ValueError:
                    continue
        
        if not points_data:
            self.log(tr("no_valid_points_data", "⚠️ 没有有效的点位数据，跳过 points.list 文件生成"))
            return
        
        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")
        
        if is_nested_grid:
            # 嵌套网格模式：在 coarse 和 fine 目录下生成文件
            coarse_dir = os.path.join(self.selected_folder, "coarse")
            fine_dir = os.path.join(self.selected_folder, "fine")
            
            if os.path.isdir(coarse_dir):
                self._export_points_to_dir(coarse_dir, points_data)
            if os.path.isdir(fine_dir):
                self._export_points_to_dir(fine_dir, points_data)
        else:
            # 普通网格模式：在工作目录下生成文件
            self._export_points_to_dir(self.selected_folder, points_data)
    
    def _export_points_to_dir(self, target_dir, points_data):
        """在指定目录下导出点位到 points.list 文件"""
        points_list_path = os.path.join(target_dir, "points.list")
        
        try:
            # 写入文件（清空原有内容）
            with open(points_list_path, "w", encoding="utf-8") as f:
                for point in points_data:
                    # 格式：经度 纬度 '名称'
                    # 注意：WW3 要求经度纬度为整数（.0f 格式）
                    f.write(f"{point['lon']:.0f} {point['lat']:.0f} '{point['name']}'\n")
            
            self.log(tr("step4_points_list_created", "✅ 已创建 points.list 文件，包含 {count} 个点位").format(count=len(points_data)))
        
        except Exception as e:
            self.log(tr("export_points_error", "❌ 导出 points.list 时出错：{error}").format(error=str(e)))

    def _modify_ww3_ounp_if_needed(self):
        """如果需要，修改 ww3_ounp.nml 中的 POINT%TIMESTART 和 POINT%TIMESTRIDE（支持嵌套网格模式）"""
        # 检查计算模式是否为"谱空间逐点计算"
        if not self._is_spectral_point_mode():
            return
        
        # 检查点列表是否不为空（跳过表头，所以 rowCount() > 1）
        if not hasattr(self, 'spectral_points_table'):
            return
        
        point_count = self.spectral_points_table.rowCount()
        if point_count <= 1:  # 只有表头，没有数据点
            return
        
        # 获取起始日期和输出精度
        start_date = self.shel_start_edit.text().strip()
        output_precision = self.output_precision_edit.text().strip()
        
        if not (start_date.isdigit() and len(start_date) == 8):
            self.log(tr("start_date_format_error_skip_ounp", "❌ 起始日期格式错误，应为 YYYYMMDD，跳过 ww3_ounp.nml 修改"))
            return
        
        if not output_precision.isdigit():
            self.log(tr("output_precision_must_be_number", "❌ 输出精度必须为数字（秒），跳过 ww3_ounp.nml 修改"))
            return
        
        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")
        
        if is_nested_grid:
            # 嵌套网格模式：修改 coarse 和 fine 目录下的文件
            coarse_dir = os.path.join(self.selected_folder, "coarse")
            fine_dir = os.path.join(self.selected_folder, "fine")
            
            if os.path.isdir(coarse_dir):
                self._modify_ww3_ounp_in_dir(coarse_dir, start_date, output_precision)
            if os.path.isdir(fine_dir):
                self._modify_ww3_ounp_in_dir(fine_dir, start_date, output_precision)
        else:
            # 普通网格模式：修改工作目录下的文件
            self._modify_ww3_ounp_in_dir(self.selected_folder, start_date, output_precision)
    
    def _modify_ww3_ounp_in_dir(self, target_dir, start_date, output_precision):
        """在指定目录下修改 ww3_ounp.nml 中的 POINT%TIMESTART 和 POINT%TIMESTRIDE"""
        ww3_ounp_path = os.path.join(target_dir, "ww3_ounp.nml")
        if not os.path.exists(ww3_ounp_path):
            return

        # 读取文件分割设置
        from setting.config import load_config
        config = load_config()
        file_split = config.get("FILE_SPLIT", tr("file_split_year", "年"))
        file_split_value_map = {
            tr("file_split_none", "无日期"): 0,
            tr("file_split_year", "年"): 4,
            tr("file_split_month", "月"): 6,
            tr("file_split_day", "天"): 8,
            tr("file_split_hour", "小时"): 10
        }
        file_split_value_map_en = {"None": 0, "Year": 4, "Month": 6, "Day": 8, "Hour": 10}
        if isinstance(file_split, (int, float)):
            timesplit_value = int(file_split)
        else:
            timesplit_value = file_split_value_map.get(
                file_split,
                file_split_value_map_en.get(file_split, 4)
            )
        
        try:
            with open(ww3_ounp_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            new_lines = []
            modified_start = False
            modified_stride = False
            modified_split = False
            modified_spectra_type = False
            in_spectra_nml = False
            for line in lines:
                # 检查是否为注释行（以 ! 开头，去除前导空格后）
                line_stripped = line.lstrip()
                is_comment = line_stripped.startswith('!')
                
                # 只替换非注释行
                if not is_comment:
                    # 处理 SPECTRA_NML 块
                    if "&SPECTRA_NML" in line.upper():
                        in_spectra_nml = True
                        new_lines.append(line)
                        continue
                    if in_spectra_nml:
                        if re.search(r'SPECTRA%TYPE', line, re.IGNORECASE) and "=" in line:
                            new_lines.append("  SPECTRA%TYPE          =  4\n")
                            modified_spectra_type = True
                            continue
                        if re.match(r'^\s*/\s*$', line) and not line.strip().startswith("!"):
                            if not modified_spectra_type:
                                new_lines.append("  SPECTRA%TYPE          =  4\n")
                                modified_spectra_type = True
                            in_spectra_nml = False
                            new_lines.append(line)
                            continue
                    # 修改 POINT%TIMESTART
                    if re.search(r'POINT%TIMESTART', line, re.IGNORECASE):
                        new_lines.append(f"  POINT%TIMESTART        =  '{start_date} 000000'\n")
                        modified_start = True
                        continue
                    # 修改 POINT%TIMESTRIDE
                    if re.search(r'POINT%TIMESTRIDE', line, re.IGNORECASE):
                        new_lines.append(f"  POINT%TIMESTRIDE       =  '{output_precision}'\n")
                        modified_stride = True
                        continue
                    # 修改 POINT%TIMESPLIT
                    if re.search(r'POINT%TIMESPLIT', line, re.IGNORECASE):
                        new_lines.append(f"  POINT%TIMESPLIT        =  {timesplit_value}\n")
                        modified_split = True
                        continue
                new_lines.append(line)

            if not modified_split:
                in_point_nml = False
                insert_index = -1
                for i, line in enumerate(new_lines):
                    if "&POINT_NML" in line.upper():
                        in_point_nml = True
                    if in_point_nml and re.match(r'^\s*/\s*$', line) and not line.strip().startswith("!"):
                        insert_index = i
                        break
                if insert_index > 0:
                    new_lines.insert(insert_index, f"  POINT%TIMESPLIT        =  {timesplit_value}\n")
            
            if modified_start or modified_stride or modified_split or modified_spectra_type:
                with open(ww3_ounp_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                if modified_start and modified_stride:
                    log_msg = tr("step4_ww3_ounp_updated", "✅ 已修改 ww3_ounp.nml：POINT%TIMESTART = '{start}'，POINT%TIMESTRIDE = '{stride}'（谱空间逐点计算模式）").format(
                        start=f"{start_date} 000000", stride=output_precision
                    )
                elif modified_start:
                    log_msg = tr("step4_ww3_ounp_start_only", "✅ 已修改 ww3_ounp.nml：POINT%TIMESTART = '{start}'（谱空间逐点计算模式）").format(
                        start=f"{start_date} 000000"
                    )
                elif modified_stride:
                    log_msg = tr("step4_ww3_ounp_stride_only", "✅ 已修改 ww3_ounp.nml：POINT%TIMESTRIDE = '{stride}'（谱空间逐点计算模式）").format(
                        stride=output_precision
                    )
                else:
                    log_msg = tr("step4_ww3_ounp_timesplit_only", "✅ 已修改 ww3_ounp.nml：POINT%TIMESPLIT = {split}（谱空间逐点计算模式）").format(
                        split=timesplit_value
                    )
                self.log(log_msg)
        
        except Exception as e:
            self.log(tr("ww3_ounp_modify_error", "❌ 修改 ww3_ounp.nml 时出错：{error}").format(error=str(e)))

    def _generate_track_i_ww3_file(self):
        """生成 track_i.ww3 文件（航迹模式）"""
        if not hasattr(self, 'track_points_table'):
            return
        
        if not hasattr(self, 'selected_folder') or not self.selected_folder:
            return
        
        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")
        
        # 确定保存路径（嵌套网格模式保存到 fine 目录，普通网格保存到工作目录）
        if is_nested_grid:
            fine_dir = os.path.join(self.selected_folder, "fine")
            if not os.path.exists(fine_dir):
                os.makedirs(fine_dir, exist_ok=True)
            track_file_path = os.path.join(fine_dir, "track_i.ww3")
        else:
            track_file_path = os.path.join(self.selected_folder, "track_i.ww3")
        
        try:
            # 读取表格数据（跳过表头行，列顺序：0-时间, 1-经度, 2-纬度, 3-名称）
            track_points = []
            for i in range(1, self.track_points_table.rowCount()):
                time_item = self.track_points_table.item(i, 0)
                lon_item = self.track_points_table.item(i, 1)
                lat_item = self.track_points_table.item(i, 2)
                name_item = self.track_points_table.item(i, 3)
                
                if time_item and lon_item and lat_item and name_item:
                    time_str = time_item.text().strip()
                    lon_str = lon_item.text().strip()
                    lat_str = lat_item.text().strip()
                    name = name_item.text().strip()
                    
                    if time_str and lon_str and lat_str and name:
                        try:
                            # 验证经纬度
                            lon = float(lon_str)
                            lat = float(lat_str)
                            
                            # 验证时间格式（应该是 YYYYMMDD HHMMSS）
                            if len(time_str) == 15 and ' ' in time_str:
                                date_part, time_part = time_str.split()
                                if len(date_part) == 8 and len(time_part) == 6:
                                    track_points.append({
                                        'datetime': time_str,
                                        'lon': lon,
                                        'lat': lat,
                                        'name': name
                                    })
                        except (ValueError, AttributeError):
                            continue
            
            if not track_points:
                self.log(tr("no_valid_track_points", "⚠️ 航迹模式表格中没有有效点位，未生成 track_i.ww3 文件"))
                return
            
            # 生成文件内容
            lines = ["WAVEWATCH III TRACK LOCATIONS DATA \n"]
            for point in track_points:
                # 格式：日期时间 经度 纬度 名称
                # 例如：20250103 000000   112.5   12.0    Track1
                line = f"{point['datetime']}   {point['lon']:.1f}   {point['lat']:.1f}    {point['name']}\n"
                lines.append(line)
            
            # 写入文件
            with open(track_file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            self.log(tr("track_file_generated", "✅ 已生成 track_i.ww3 文件").format(path=track_file_path))
        except Exception as e:
            self.log(tr("track_file_generation_failed", "❌ 生成 track_i.ww3 文件失败：{error}").format(error=e))

    def _modify_ww3_shel_date_track(self):
        """修改 ww3_shel.nml，在 &OUTPUT_DATE_NML 下添加 DATE%TRACK（航迹模式）"""
        # 检查航迹点位表格是否存在且不为空
        if not hasattr(self, 'track_points_table'):
            return
        
        point_count = self.track_points_table.rowCount()
        if point_count <= 1:  # 只有表头，没有数据点
            return
        
        # 从表格中获取所有时间，找到最早和最晚的时间
        times = []
        for i in range(1, self.track_points_table.rowCount()):
            time_item = self.track_points_table.item(i, 0)
            if time_item:
                time_str = time_item.text().strip()
                if time_str and len(time_str) == 15 and ' ' in time_str:
                    try:
                        date_part, time_part = time_str.split()
                        if len(date_part) == 8 and len(time_part) == 6:
                            times.append(time_str)
                    except (ValueError, AttributeError):
                        continue
        
        if not times:
            return
        
        # 找到最早和最晚的时间
        # 将时间转换为可比较的格式进行排序
        # 格式：YYYYMMDD HHMMSS，可以直接按字符串排序
        times.sort()
        start_datetime = times[0]  # 格式：YYYYMMDD HHMMSS - 使用最早的时间（第一个点）
        end_datetime = times[-1]   # 格式：YYYYMMDD HHMMSS - 使用最晚的时间（最后一个点）
        
        # 获取计算步长
        compute_precision = self.shel_step_edit.text().strip()
        if not compute_precision.isdigit():
            self.log(tr("compute_precision_error_skip_track", "❌ 计算精度必须为数字（秒），跳过 DATE%TRACK 修改"))
            return
        
        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")
        
        if is_nested_grid:
            # 嵌套网格模式：修改 coarse 和 fine 目录下的文件
            coarse_dir = os.path.join(self.selected_folder, "coarse")
            fine_dir = os.path.join(self.selected_folder, "fine")
            
            if os.path.isdir(coarse_dir):
                self._modify_ww3_shel_date_track_in_dir(coarse_dir, start_datetime, compute_precision, end_datetime)
            if os.path.isdir(fine_dir):
                # 对于内网格，使用内网格的计算精度
                inner_shel_step = self.inner_shel_step_edit.text().strip()
                inner_compute_precision = inner_shel_step if inner_shel_step.isdigit() else compute_precision
                self._modify_ww3_shel_date_track_in_dir(fine_dir, start_datetime, inner_compute_precision, end_datetime)
        else:
            # 普通网格模式：修改工作目录下的文件
            self._modify_ww3_shel_date_track_in_dir(self.selected_folder, start_datetime, compute_precision, end_datetime)
    
    def _modify_ww3_shel_date_track_in_dir(self, target_dir, start_datetime, compute_precision, end_datetime):
        """在指定目录下修改 ww3_shel.nml，在 &OUTPUT_DATE_NML 下添加 DATE%TRACK"""
        ww3_shel_path = os.path.join(target_dir, "ww3_shel.nml")
        if not os.path.exists(ww3_shel_path):
            return
        
        try:
            with open(ww3_shel_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            new_lines = []
            modified = False
            in_output_date_nml = False
            found_output_date_nml = False
            found_date_field = False
            i = 0
            
            while i < len(lines):
                line = lines[i]
                
                # 检查是否为注释行（以 ! 开头，去除前导空格后）
                line_stripped = line.lstrip()
                is_comment = line_stripped.startswith('!')
                
                new_lines.append(line)
                
                # 查找 &OUTPUT_DATE_NML 开始
                if "&OUTPUT_DATE_NML" in line:
                    found_output_date_nml = True
                    in_output_date_nml = True
                    i += 1
                    continue
                
                # 在 &OUTPUT_DATE_NML 块内查找结束标记或 DATE%FIELD
                if in_output_date_nml:
                    # 如果找到 DATE%FIELD 行（非注释），在其后添加 DATE%TRACK
                    if not is_comment and re.search(r'DATE%FIELD', line, re.IGNORECASE):
                        found_date_field = True
                        # 检查下一行是否已经有 DATE%TRACK
                        if i + 1 < len(lines):
                            next_line = lines[i + 1]
                            next_line_stripped = next_line.lstrip()
                            next_is_comment = next_line_stripped.startswith('!')
                            # 如果下一行已经有 DATE%TRACK（非注释），则跳过
                            if not next_is_comment and re.search(r'DATE%TRACK', next_line, re.IGNORECASE):
                                i += 1
                                continue
                        # 在下一行添加 DATE%TRACK
                        track_line = f"  DATE%TRACK          = '{start_datetime}' '{compute_precision}' '{end_datetime}'\n"
                        new_lines.append(track_line)
                        modified = True
                    # 如果遇到结束标记 "/"
                    elif "/" in line and not is_comment:
                        # 如果在 OUTPUT_DATE_NML 块内且还没有添加 DATE%TRACK，则在结束标记之前插入
                        if not modified:
                            # 在结束标记之前插入 DATE%TRACK
                            # 先移除刚添加的结束标记行
                            new_lines.pop()
                            # 添加 DATE%TRACK
                            track_line = f"  DATE%TRACK          = '{start_datetime}' '{compute_precision}' '{end_datetime}'\n"
                            new_lines.append(track_line)
                            # 再添加结束标记
                            new_lines.append(line)
                            modified = True
                        in_output_date_nml = False
                        i += 1
                        continue
                
                i += 1
            
            if modified:
                with open(ww3_shel_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                self.log(tr("step4_ww3_shel_date_track_updated", "✅ 已修改 ww3_shel.nml：添加 DATE%TRACK（航迹模式）"))
            else:
                if not found_output_date_nml:
                    self.log(tr("output_date_nml_not_found", "⚠️ 航迹模式：未找到 &OUTPUT_DATE_NML 块，无法添加 DATE%TRACK"))
                elif not found_date_field:
                    self.log(tr("date_field_not_found", "⚠️ 航迹模式：未找到 DATE%FIELD 行，无法添加 DATE%TRACK"))
        
        except Exception as e:
            self.log(tr("ww3_shel_modify_error_str", "❌ 修改 ww3_shel.nml 时出错：{error}").format(error=str(e)))
            import traceback
            self.log(tr("detailed_error_info", "❌ 详细错误信息：{error}").format(error=traceback.format_exc()))
    
    def _modify_ww3_trnc_track(self):
        """修改 ww3_trnc.nml，设置 TRACK%TIMESTART 和 TRACK%TIMESTRIDE（航迹模式）"""
        # 检查航迹点位表格是否存在且不为空
        if not hasattr(self, 'track_points_table'):
            return
        
        point_count = self.track_points_table.rowCount()
        if point_count <= 1:  # 只有表头，没有数据点
            return
        
        # 从表格中获取所有时间，找到最早的时间
        times = []
        for i in range(1, self.track_points_table.rowCount()):
            time_item = self.track_points_table.item(i, 0)
            if time_item:
                time_str = time_item.text().strip()
                if time_str and len(time_str) == 15 and ' ' in time_str:
                    try:
                        date_part, time_part = time_str.split()
                        if len(date_part) == 8 and len(time_part) == 6:
                            times.append(time_str)
                    except (ValueError, AttributeError):
                        continue
        
        if not times:
            return
        
        # 找到最早的时间
        times.sort()
        start_datetime = times[0]  # 格式：YYYYMMDD HHMMSS
        
        # 获取输出精度
        if not hasattr(self, 'output_precision_edit'):
            return
        
        output_precision = self.output_precision_edit.text().strip()
        if not output_precision.isdigit():
            self.log(tr("output_precision_error_skip_trnc", "❌ 输出精度必须为数字（秒），跳过 ww3_trnc.nml 修改"))
            return
        
        # 检查是否是嵌套网格模式
        grid_type = getattr(self, 'grid_type_var', tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        is_nested_grid = (grid_type == nested_text or grid_type == "嵌套网格")
        
        if is_nested_grid:
            # 嵌套网格模式：修改 fine 目录下的文件
            fine_dir = os.path.join(self.selected_folder, "fine")
            if os.path.isdir(fine_dir):
                self._modify_ww3_trnc_track_in_dir(fine_dir, start_datetime, output_precision)
        else:
            # 普通网格模式：修改工作目录下的文件
            self._modify_ww3_trnc_track_in_dir(self.selected_folder, start_datetime, output_precision)
    
    def _modify_ww3_trnc_track_in_dir(self, target_dir, start_datetime, output_precision):
        """在指定目录下修改 ww3_trnc.nml，设置 TRACK%TIMESTART 和 TRACK%TIMESTRIDE"""
        ww3_trnc_path = os.path.join(target_dir, "ww3_trnc.nml")
        if not os.path.exists(ww3_trnc_path):
            return

        # 读取文件分割设置
        from setting.config import load_config
        config = load_config()
        file_split = config.get("FILE_SPLIT", tr("file_split_year", "年"))
        file_split_value_map = {
            tr("file_split_none", "无日期"): 0,
            tr("file_split_year", "年"): 4,
            tr("file_split_month", "月"): 6,
            tr("file_split_day", "天"): 8,
            tr("file_split_hour", "小时"): 10
        }
        file_split_value_map_en = {"None": 0, "Year": 4, "Month": 6, "Day": 8, "Hour": 10}
        if isinstance(file_split, (int, float)):
            timesplit_value = int(file_split)
        else:
            timesplit_value = file_split_value_map.get(
                file_split,
                file_split_value_map_en.get(file_split, 4)
            )
        
        try:
            with open(ww3_trnc_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            new_lines = []
            modified = False
            in_track_nml = False
            found_track_nml = False
            timestart_modified = False
            timestride_modified = False
            timesplit_modified = False
            i = 0
            
            while i < len(lines):
                line = lines[i]
                
                # 检查是否为注释行（以 ! 开头，去除前导空格后）
                line_stripped = line.lstrip()
                is_comment = line_stripped.startswith('!')
                
                # 查找 &TRACK_NML 开始
                if "&TRACK_NML" in line:
                    found_track_nml = True
                    in_track_nml = True
                    new_lines.append(line)
                    i += 1
                    continue
                
                # 在 &TRACK_NML 块内查找 TRACK%TIMESTART 和 TRACK%TIMESTRIDE
                if in_track_nml:
                    # 如果找到结束标记 /，退出块
                    if "/" in line and not is_comment:
                        # 如果还没有修改过，在结束标记前添加
                        if not timestart_modified or not timestride_modified or not timesplit_modified:
                            if not timestart_modified:
                                new_lines.append(f"  TRACK%TIMESTART        =  '{start_datetime}'\n")
                                timestart_modified = True
                            if not timestride_modified:
                                new_lines.append(f"  TRACK%TIMESTRIDE       =  '{output_precision}'\n")
                                timestride_modified = True
                            if not timesplit_modified:
                                new_lines.append(f"  TRACK%TIMESPLIT        =  {timesplit_value}\n")
                                timesplit_modified = True
                            modified = True
                        new_lines.append(line)
                        in_track_nml = False
                        i += 1
                        continue
                    
                    # 查找并替换 TRACK%TIMESTART
                    if not is_comment and re.search(r'TRACK%TIMESTART', line, re.IGNORECASE):
                        # 替换整行
                        new_lines.append(f"  TRACK%TIMESTART        =  '{start_datetime}'\n")
                        timestart_modified = True
                        modified = True
                        i += 1
                        continue
                    
                    # 查找并替换 TRACK%TIMESTRIDE
                    if not is_comment and re.search(r'TRACK%TIMESTRIDE', line, re.IGNORECASE):
                        # 替换整行
                        new_lines.append(f"  TRACK%TIMESTRIDE       =  '{output_precision}'\n")
                        timestride_modified = True
                        modified = True
                        i += 1
                        continue

                    # 查找并替换 TRACK%TIMESPLIT
                    if not is_comment and re.search(r'TRACK%TIMESPLIT', line, re.IGNORECASE):
                        new_lines.append(f"  TRACK%TIMESPLIT        =  {timesplit_value}\n")
                        timesplit_modified = True
                        modified = True
                        i += 1
                        continue
                    
                    new_lines.append(line)
                else:
                    new_lines.append(line)
                
                i += 1
            
            if modified:
                with open(ww3_trnc_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                self.log(tr("step4_ww3_trnc_track_updated", "✅ 已修改 ww3_trnc.nml：TRACK%TIMESTART = '{start}', TRACK%TIMESTRIDE = '{stride}'").format(start=start_datetime, stride=output_precision))
        
        except Exception as e:
            self.log(tr("ww3_trnc_modify_error", "❌ 修改 ww3_trnc.nml 时出错：{error}").format(error=str(e)))