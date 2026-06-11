"""WW3 Step 1 强迫场 NetCDF 变量检测服务。

WW3 第一步要求识别四类强迫场对应的标准变量名：

- 风场：``u10/v10``，或 ``wndewd/wndnwd``、``uwnd/vwnd``；
- 流场：``uo`` 与 ``vo``；
- 水位：``zos``；
- 海冰：``siconc``。

本模块单次打开文件完成检测，避免重复 I/O，供导入用例与目录扫描复用。
"""
from netCDF4 import Dataset
from typing import Dict, List


class VariableDetector:
    """NetCDF 强迫场变量检测的静态工具类。

    所有检测逻辑基于 ``netCDF4.Dataset`` 变量名匹配，不读取数据数组。
    """

    @staticmethod
    def inspect_forcing_fields(file_path: str) -> Dict[str, object]:
        """
        单次打开文件，汇总风/流/水位/海冰检测结果，避免重复 I/O。

        返回:
            {
                "detected": {"wind": bool, "current": bool, "level": bool, "ice": bool},
                "fields": ["wind", ...]
            }
        """
        detected = {"wind": False, "current": False, "level": False, "ice": False}
        fields = []
        try:
            with Dataset(file_path, "r") as ds:
                has_u10 = "u10" in ds.variables or "U10" in ds.variables
                has_v10 = "v10" in ds.variables or "V10" in ds.variables
                has_wndewd = "wndewd" in ds.variables or "WNDEWD" in ds.variables
                has_wndnwd = "wndnwd" in ds.variables or "WNDNWD" in ds.variables
                has_uwnd = "uwnd" in ds.variables or "UWND" in ds.variables
                has_vwnd = "vwnd" in ds.variables or "VWND" in ds.variables
                detected["wind"] = (has_u10 and has_v10) or (has_wndewd and has_wndnwd) or (has_uwnd and has_vwnd)

                has_uo = "uo" in ds.variables or "UO" in ds.variables
                has_vo = "vo" in ds.variables or "VO" in ds.variables
                detected["current"] = has_uo and has_vo

                detected["level"] = "zos" in ds.variables or "ZOS" in ds.variables
                detected["ice"] = "siconc" in ds.variables or "SICONC" in ds.variables

            fields = [name for name in ("wind", "current", "level", "ice") if detected[name]]
        except Exception:
            pass

        return {"detected": detected, "fields": fields}
    
    @staticmethod
    def check_wind_variables(file_path: str) -> bool:
        """检查文件是否包含风场变量（接受 u10/v10 或 wndewd/wndnwd）"""
        return bool(VariableDetector.inspect_forcing_fields(file_path)["detected"].get("wind"))

    @staticmethod
    def check_current_variables(file_path: str) -> bool:
        """检查文件是否包含流场变量（只接受 uo 和 vo）"""
        try:
            with Dataset(file_path, "r") as ds:
                # 只检查 uo 和 vo
                has_uo = "uo" in ds.variables
                has_vo = "vo" in ds.variables

                return has_uo and has_vo
        except Exception:
            return False

    @staticmethod
    def check_level_variables(file_path: str) -> bool:
        """检查文件是否包含水位场变量（只接受 zos）"""
        try:
            with Dataset(file_path, "r") as ds:
                # 只检查 zos
                return "zos" in ds.variables
        except Exception:
            return False

    @staticmethod
    def check_ice_variables(file_path: str) -> bool:
        """检查文件是否包含海冰场变量（只接受 siconc）"""
        try:
            with Dataset(file_path, "r") as ds:
                # 只检查 siconc
                return "siconc" in ds.variables
        except Exception:
            return False

    @staticmethod
    def detect_forcing_fields(file_path: str) -> List[str]:
        """
        检测文件包含哪些强迫场
        
        返回包含的场名称列表，例如：['wind', 'current', 'level', 'ice']
        """
        return list(VariableDetector.inspect_forcing_fields(file_path)["fields"])

    @staticmethod
    def detect_all_forcing_fields_in_file(file_path: str) -> Dict[str, bool]:
        """
        检测文件包含的所有强迫场变量（不处理文件，只检测）
        
        返回包含的场名称字典，例如：{'wind': True, 'current': True, 'level': True, 'ice': False}
        """
        return dict(VariableDetector.inspect_forcing_fields(file_path)["detected"])
