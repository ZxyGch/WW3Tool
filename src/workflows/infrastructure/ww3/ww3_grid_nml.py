"""ww3_grid.nml 修改 Mixin — 结构化 / SMC / 非结构网格 namelist 转换。

负责将 ``grid.meta`` 几何参数同步到 ``ww3_grid.nml``，以及按第二步所选网格类型
在 RECT、UNST（非结构）、SMCG（SMC）三种 namelist 形态间切换对应 namelist 块。
"""
from __future__ import annotations

import glob
import json
import os
import re

import numpy as np
import netCDF4 as nc
from netCDF4 import Dataset

from ...support.translations import tr
from ..runtime_config import PUBLIC_DIR, load_config
from ..grid_visualization.structured_grid_paths import structured_grid_desc_path
from ..grid_visualization.rect_grid_desc_parse import parse_ww3_grid_meta_for_sync
from .nml_primitives import NMLPrimitives


class WW3GridNML(NMLPrimitives):
    """``ww3_grid.nml`` 相关操作的 Mixin 类。

    主要能力
    --------
    - 非结构网格：注释 RECT/DEPTH/MASK/OBST 块，启用 ``&UNST_NML``。
    - SMC 网格：注释 RECT 块，启用 ``&SMC_NML``，写入边界/北极附属面路径。
    - 结构化网格：从 ``grid.meta`` 同步 NX/NY、分辨率、原点及 GRID%CLOS。
    - ``sync_grid_meta_to_grid_nml`` — 公开入口，触发 meta → nml 同步。
    """

    def _is_step2_unstructured_mesh(self):
        """第二步当前是否为「非结构网格」（与 step2 一致）。"""
        if getattr(self, "_raw_mesh_type", None) == "unstructured":
            return True
        ut = tr("step2_mesh_type_unstructured", "非结构网格")
        return getattr(self, "mesh_type_var", "") == ut

    def _is_step2_smc_mesh(self):
        """第二步当前是否为「SMC 网格」（与 step2_mesh_type_smc 一致）。"""
        if getattr(self, "_raw_mesh_type", None) == "smc":
            return True
        st = tr("step2_mesh_type_smc", "SMC 网格")
        return getattr(self, "mesh_type_var", "") == st

    def _transform_ww3_grid_nml_for_unstructured(self, nml_path):
        """RECT/DEPTH/MASK/OBST 块整段注释；启用 &UNST_NML；GRID%TYPE → UNST；UNST%FILENAME → grid.ww3"""
        if not nml_path or not os.path.isfile(nml_path):
            return
        blocks_comment = ("RECT_NML", "DEPTH_NML", "MASK_NML", "OBST_NML")
        try:
            with open(nml_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            out = []
            i = 0
            while i < len(lines):
                line = lines[i]
                line_no_nl = line.rstrip("\n")
                ls = line.lstrip()

                if ls and not ls.startswith("!") and "GRID%TYPE" in line and "=" in line:
                    nl = re.sub(r"(GRID%TYPE\s*=\s*)'RECT'", r"\1'UNST'", line, count=1)
                    nl = re.sub(r'(GRID%TYPE\s*=\s*)"RECT"', r'\1"UNST"', nl, count=1)
                    out.append(nl)
                    i += 1
                    continue

                in_comment_block = None
                for blk in blocks_comment:
                    if re.match(rf"^\s*!?\s*&{re.escape(blk)}\b", line_no_nl):
                        in_comment_block = blk
                        break
                if in_comment_block:
                    while i < len(lines):
                        ln = lines[i]
                        lnn = ln.rstrip("\n")
                        if self._nml_line_is_namelist_close(lnn):
                            out.append(self._ww3_nml_force_comment_line(ln))
                            i += 1
                            break
                        out.append(self._ww3_nml_force_comment_line(ln))
                        i += 1
                    continue

                if re.match(r"^\s*!?\s*&UNST_NML\b", line_no_nl):
                    while i < len(lines):
                        ln = lines[i]
                        lnn = ln.rstrip("\n")
                        if self._nml_line_is_namelist_close(lnn):
                            out.append(self._ww3_nml_force_uncomment_line(ln))
                            i += 1
                            break
                        uln = self._ww3_nml_force_uncomment_line(ln)
                        uls = uln.lstrip()
                        if (
                            not uls.startswith("!")
                            and "UNST%FILENAME" in uln
                            and "=" in uln
                        ):
                            uln = re.sub(
                                r"UNST%FILENAME\s*=\s*'[^']*'",
                                "UNST%FILENAME       = 'grid.ww3'",
                                uln,
                                count=1,
                            )
                        out.append(uln)
                        i += 1
                    continue

                out.append(line)
                i += 1

            with open(nml_path, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(out)
        except Exception as e:
            self.log(
                tr(
                    "step4_unst_ww3_grid_transform_failed",
                    "⚠️ 非结构网格 ww3_grid.nml 调整失败：{err}",
                ).format(err=e)
            )

    def _read_smc_ww3_rect_meta(self, work_dir: str) -> dict | None:
        """smc_generator 写入工作目录 grid.json 的 ww3_rect（与 bathy 上规则网格一致）。"""
        if not work_dir:
            return None
        p = os.path.join(work_dir, "grid.json")
        if not os.path.isfile(p):
            return None
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            return None
        wr = d.get("ww3_rect")
        if not isinstance(wr, dict):
            return None
        try:
            return {
                "nx": int(wr["nx"]),
                "ny": int(wr["ny"]),
                "sx": float(wr["sx"]),
                "sy": float(wr["sy"]),
                "x0": float(wr["x0"]),
                "y0": float(wr["y0"]),
            }
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def _smc_ww3_rect_lonlat_bounds(wr: dict) -> tuple[float, float, float, float]:
        """West/east lon and south/north lat of RECT cell centers (NX×NY span)."""
        lon_w = float(wr["x0"])
        lat_s = float(wr["y0"])
        lon_e = lon_w + (int(wr["nx"]) - 1) * float(wr["sx"])
        lat_n = lat_s + (int(wr["ny"]) - 1) * float(wr["sy"])
        return lon_w, lon_e, lat_s, lat_n

    def _smc_warn_forcing_covers_ww3_rect(self, work_dir: str, *, grid_label: str = "") -> None:
        """SMC: ww3_prnc uses the full RECT; regional wind often only covers regional_bounds."""
        if not self._is_step2_smc_mesh() or not work_dir:
            return
        wr = self._read_smc_ww3_rect_meta(work_dir)
        if not wr:
            return
        lon_w, lon_e, lat_s, lat_n = self._smc_ww3_rect_lonlat_bounds(wr)

        windp = os.path.join(work_dir, "wind.nc")
        if not os.path.isfile(windp):
            alt = glob.glob(os.path.join(work_dir, "*wind*.nc"))
            windp = alt[0] if alt else ""
        if not windp:
            return
        try:
            with nc.Dataset(windp, "r") as ds:
                lon_vn = None
                for nm in ("longitude", "lon", "LONGITUDE", "LON"):
                    if nm in ds.variables and int(ds.variables[nm].ndim) == 1:
                        lon_vn = nm
                        break
                lat_vn = None
                for nm in ("latitude", "lat", "LATITUDE", "LAT"):
                    if nm in ds.variables and int(ds.variables[nm].ndim) == 1:
                        lat_vn = nm
                        break
                if lon_vn is None or lat_vn is None:
                    return
                wlo = float(np.min(ds.variables[lon_vn][:]))
                whi = float(np.max(ds.variables[lon_vn][:]))
                wla = float(np.min(ds.variables[lat_vn][:]))
                wlz = float(np.max(ds.variables[lat_vn][:]))
        except Exception:
            return

        eps = 0.05
        outside = (
            wlo > lon_w + eps
            or whi < lon_e - eps
            or wla > lat_s + eps
            or wlz < lat_n - eps
        )
        if not outside:
            return
        prefix = f"[{grid_label}] " if grid_label else ""
        self.log(
            tr(
                "step4_smc_forcing_narrower_than_rect",
                "{prefix}⚠️ SMC / ww3_prnc：风场范围 lon [{wl:.4f},{wh:.4f}] lat [{wb:.4f},{wn:.4f}] "
                "未完全覆盖 SMC 底网格 RECT 范围 lon [{rlw:.4f},{rle:.4f}] lat [{rls:.4f},{rln:.4f}] "
                "（见 grid.json 的 ww3_rect / ww3_rect_geo；该范围已按实际 MCELS 活动底网格收紧，仍可能因 SMC 对齐略大于 regional_bounds）。"
                " 请在第一步扩大风场或裁切到至少上述 RECT，否则 ww3_prnc 会对大量格点报 NOT COVERED BY INPUT GRID。",
            ).format(
                prefix=prefix,
                wl=wlo,
                wh=whi,
                wb=wla,
                wn=wlz,
                rlw=lon_w,
                rle=lon_e,
                rls=lat_s,
                rln=lat_n,
            )
        )

    def _infer_smc_ww3_rect_from_bathy(self, work_dir: str) -> dict | None:
        """若 grid.json 无 ww3_rect，从 input.bathymetry_file 推断底网格（与 smc_generator 翻转约定一致）。"""
        if not work_dir:
            return None
        p = os.path.join(work_dir, "grid.json")
        if not os.path.isfile(p):
            return None
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            return None
        inp = d.get("input") or {}
        rel = str(inp.get("bathymetry_file") or "").strip()
        if not rel:
            return None
        base = os.path.dirname(os.path.abspath(p))
        bathy = rel if os.path.isabs(rel) else os.path.normpath(os.path.join(base, rel))
        if not os.path.isfile(bathy):
            return None

        lon_cands = ("lon", "longitude", "x", "LON", "XLONG")
        lat_cands = ("lat", "latitude", "y", "LAT", "XLAT")

        def _pick_var(ds, cands: tuple[str, ...], configured: object) -> str | None:
            if isinstance(configured, str) and configured.strip() and configured in ds.variables:
                return configured.strip()
            for name in cands:
                if name in ds.variables:
                    return name
            return None

        try:
            with nc.Dataset(bathy, "r") as ds:
                lon_v = _pick_var(ds, lon_cands, inp.get("lon_var"))
                lat_v = _pick_var(ds, lat_cands, inp.get("lat_var"))
                if not lon_v or not lat_v:
                    return None
                lon = np.asarray(ds.variables[lon_v][:], dtype=float).squeeze()
                lat = np.asarray(ds.variables[lat_v][:], dtype=float).squeeze()
            if lon.ndim != 1 or lat.ndim != 1 or lon.size < 2 or lat.size < 2:
                return None
            if bool(inp.get("auto_flip_lat", True)) and lat[0] > lat[-1]:
                lat = lat[::-1]
            if bool(inp.get("auto_flip_lon", True)) and lon[0] > lon[-1]:
                lon = lon[::-1]
            dlon = float(np.median(np.diff(lon)))
            dlat = float(np.median(np.diff(lat)))
            if dlon <= 0.0 or dlat <= 0.0 or not np.isfinite(dlon) or not np.isfinite(dlat):
                return None
            return {
                "nx": int(lon.size),
                "ny": int(lat.size),
                "sx": dlon,
                "sy": dlat,
                "x0": float(lon[0]),
                "y0": float(lat[0]),
            }
        except Exception:
            return None

    def _resolve_smc_ww3_rect_workdir(self, work_dir: str) -> dict | None:
        """解析 SMC 工作目录下的底网格 RECT 参数（用于 SMCG namelist 写入）。

        优先从 ``grid.json`` 的 ``ww3_rect`` 字段读取；若缺失则尝试从
        ``bathymetry_file`` 推断。均失败时记录警告并返回 ``None``。
        """
        wr = self._read_smc_ww3_rect_meta(work_dir)
        if wr:
            return wr
        wr2 = self._infer_smc_ww3_rect_from_bathy(work_dir)
        if wr2:
            self.log(
                "ℹ️ SMC：grid.json 无 ww3_rect，已从 bathymetry_file 推断 &RECT_NML；"
                "建议重新运行 smc_generator/create_grid.py 以便写入 ww3_rect。"
            )
        else:
            self.log(
                "⚠️ SMC：无法从 grid.json（ww3_rect 或 bathymetry_file）解析底网格，"
                "&RECT_NML 可能仍为模板值（如 NX=301），ww3_grid 会报 SMC longitude 越界。"
            )
        return wr2

    def _smc_patch_rect_content_line(self, line: str, wr: dict) -> str:
        """Replace RECT%NX..Y0 inside an active &RECT_NML block."""
        lns = line.rstrip("\n")
        if "=" not in lns or not lns.strip():
            return line
        u = lns.upper()
        if "XCOORD" in u or "YCOORD" in u:
            return line
        m = re.match(r"^\s*(RECT%[A-Z][A-Z0-9]*)\s*=", lns, re.I)
        if not m:
            return line
        lhs_u = m.group(1).upper()
        key_map = {
            "RECT%NX": str(int(wr["nx"])),
            "RECT%NY": str(int(wr["ny"])),
            "RECT%SX": f"{float(wr['sx']):15.12f}",
            "RECT%SY": f"{float(wr['sy']):15.12f}",
            "RECT%X0": f"{float(wr['x0']):8.4f}",
            "RECT%Y0": f"{float(wr['y0']):8.4f}",
            "RECT%SF": "1.00",
            "RECT%SF0": "1.00",
        }
        val = key_map.get(lhs_u)
        if val is None:
            return line
        return self._ww3_nml_assign_line(lhs_u, val)

    def _transform_ww3_grid_nml_for_smcc(self, nml_path: str) -> None:
        """DEPTH/MASK/OBST 注释；GRID%TYPE → SMCG；启用 &SMC_NML；保留并校正 &RECT_NML。

        SMCG 与 RECT 共用底网格尺度（NOAA WW3 w3gridmd.F90：NML_RECT%NX/NY 等为 0 时
        NX=MAX(3,NX) 会得到 NX=3，胞元 i 指标会报 LONGITUDE RANGE OUTSIDE）。

        WW3 w3gridmd.F90 在读完 MCELS 后会依次无条件 OPEN：ISIDE、JSIDE、SUBTR（见 develop
        model/src/w3gridmd.F90 约 4263–4343 行）。namelist 项若被注释，默认 FILENAME 仍为
        ``unset``，会导致 IOSTAT=2。此处为 ISIDE/JSIDE/SUBTR 写入约定文件名；MCELS、SUBTR
        由 smc_generator 生成，ISIDE/JSIDE 需由 SMCGTools SMCGSideMP 等另行生成。

        ``&RECT_NML`` 从工作目录 ``grid.json`` 的 ``ww3_rect`` 写回（若存在）。"""
        if not nml_path or not os.path.isfile(nml_path):
            return
        work_dir = getattr(self, "selected_folder", None) or os.path.dirname(
            os.path.abspath(nml_path)
        )
        has_bundy = os.path.isfile(os.path.join(work_dir, "grid_boundary.dat"))
        has_mbarc = os.path.isfile(os.path.join(work_dir, "grid_arctic_cells.dat"))
        cell_p = os.path.join(work_dir, "grid_cell.dat")
        if not os.path.isfile(cell_p):
            self.log(
                tr(
                    "step4_smcc_grid_cell_missing",
                    "⚠️ 工作目录中未找到 grid_cell.dat，SMC_NML 仍将指向该文件名（请先完成 SMC 网格生成）",
                )
            )

        blocks_comment = ("DEPTH_NML", "MASK_NML", "OBST_NML")
        wr_rect = self._resolve_smc_ww3_rect_workdir(work_dir)
        # 北极附属面文件：smc_generator 不产出；无 grid_arctic_cells 时保持注释由 WW3 默认处理
        skip_keys = ("AISID", "AJSID")

        def _patch_smcc_smc_line(uln: str) -> str:
            lsu = uln.lstrip()
            if lsu.startswith("!") or "&SMC_NML" in uln or self._nml_line_is_namelist_close(
                uln.rstrip("\n")
            ):
                return uln
            for sk in skip_keys:
                if f"SMC%{sk}%" in uln:
                    return self._ww3_nml_force_comment_line(uln)
            if "SMC%BUNDY%" in uln:
                if not has_bundy:
                    return self._ww3_nml_force_comment_line(uln)
            elif "SMC%MBARC%" in uln:
                if not has_mbarc:
                    return self._ww3_nml_force_comment_line(uln)
            if "SMC%MCELS%FILENAME" in uln and "=" in uln:
                uln = re.sub(
                    r"SMC%MCELS%FILENAME\s*=\s*'[^']*'",
                    "SMC%MCELS%FILENAME       = 'grid_cell.dat'",
                    uln,
                    count=1,
                )
                uln = re.sub(
                    r'SMC%MCELS%FILENAME\s*=\s*"[^"]*"',
                    'SMC%MCELS%FILENAME       = "grid_cell.dat"',
                    uln,
                    count=1,
                )
                return uln
            if "SMC%ISIDE%FILENAME" in uln and "=" in uln:
                uln = re.sub(
                    r"SMC%ISIDE%FILENAME\s*=\s*'[^']*'",
                    "SMC%ISIDE%FILENAME       = 'grid_iside.dat'",
                    uln,
                    count=1,
                )
                uln = re.sub(
                    r'SMC%ISIDE%FILENAME\s*=\s*"[^"]*"',
                    'SMC%ISIDE%FILENAME       = "grid_iside.dat"',
                    uln,
                    count=1,
                )
                return uln
            if "SMC%JSIDE%FILENAME" in uln and "=" in uln:
                uln = re.sub(
                    r"SMC%JSIDE%FILENAME\s*=\s*'[^']*'",
                    "SMC%JSIDE%FILENAME       = 'grid_jside.dat'",
                    uln,
                    count=1,
                )
                uln = re.sub(
                    r'SMC%JSIDE%FILENAME\s*=\s*"[^"]*"',
                    'SMC%JSIDE%FILENAME       = "grid_jside.dat"',
                    uln,
                    count=1,
                )
                return uln
            if "SMC%SUBTR%FILENAME" in uln and "=" in uln:
                uln = re.sub(
                    r"SMC%SUBTR%FILENAME\s*=\s*'[^']*'",
                    "SMC%SUBTR%FILENAME       = 'grid_subtr.dat'",
                    uln,
                    count=1,
                )
                uln = re.sub(
                    r'SMC%SUBTR%FILENAME\s*=\s*"[^"]*"',
                    'SMC%SUBTR%FILENAME       = "grid_subtr.dat"',
                    uln,
                    count=1,
                )
                return uln
            if "SMC%BUNDY%FILENAME" in uln and "=" in uln and has_bundy:
                uln = re.sub(
                    r"SMC%BUNDY%FILENAME\s*=\s*'[^']*'",
                    "SMC%BUNDY%FILENAME       = 'grid_boundary.dat'",
                    uln,
                    count=1,
                )
                uln = re.sub(
                    r'SMC%BUNDY%FILENAME\s*=\s*"[^"]*"',
                    'SMC%BUNDY%FILENAME       = "grid_boundary.dat"',
                    uln,
                    count=1,
                )
                return uln
            if "SMC%MBARC%FILENAME" in uln and "=" in uln and has_mbarc:
                uln = re.sub(
                    r"SMC%MBARC%FILENAME\s*=\s*'[^']*'",
                    "SMC%MBARC%FILENAME       = 'grid_arctic_cells.dat'",
                    uln,
                    count=1,
                )
                uln = re.sub(
                    r'SMC%MBARC%FILENAME\s*=\s*"[^"]*"',
                    'SMC%MBARC%FILENAME       = "grid_arctic_cells.dat"',
                    uln,
                    count=1,
                )
                return uln
            return uln

        try:
            with open(nml_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            out = []
            i = 0
            while i < len(lines):
                line = lines[i]
                line_no_nl = line.rstrip("\n")
                ls = line.lstrip()

                if ls and not ls.startswith("!") and "GRID%TYPE" in line and "=" in line:
                    nl = re.sub(
                        r"GRID%TYPE\s*=\s*'[^']*'",
                        "GRID%TYPE         =  'SMCG'",
                        line,
                        count=1,
                    )
                    nl = re.sub(
                        r'GRID%TYPE\s*=\s*"[^"]*"',
                        'GRID%TYPE         =  "SMCG"',
                        nl,
                        count=1,
                    )
                    out.append(nl)
                    i += 1
                    continue

                if re.match(r"^\s*!?\s*&RECT_NML\b", line_no_nl):
                    while i < len(lines):
                        ln = lines[i]
                        ul = self._ww3_nml_force_uncomment_line(ln)
                        lcc = ul.rstrip("\n")
                        if self._nml_line_is_namelist_close(lcc):
                            out.append(ul)
                            i += 1
                            break
                        if re.match(r"^\s*&RECT_NML\b", lcc, re.I):
                            out.append(ul)
                        elif wr_rect:
                            out.append(self._smc_patch_rect_content_line(ul, wr_rect))
                        else:
                            out.append(ul)
                        i += 1
                    continue

                in_comment_block = None
                for blk in blocks_comment:
                    if re.match(rf"^\s*!?\s*&{re.escape(blk)}\b", line_no_nl):
                        in_comment_block = blk
                        break
                if in_comment_block:
                    while i < len(lines):
                        ln = lines[i]
                        lnn = ln.rstrip("\n")
                        if self._nml_line_is_namelist_close(lnn):
                            out.append(self._ww3_nml_force_comment_line(ln))
                            i += 1
                            break
                        out.append(self._ww3_nml_force_comment_line(ln))
                        i += 1
                    continue

                if re.match(r"^\s*!?\s*&SMC_NML\b", line_no_nl):
                    while i < len(lines):
                        ln = lines[i]
                        lnn = ln.rstrip("\n")
                        if self._nml_line_is_namelist_close(lnn):
                            out.append(self._ww3_nml_force_uncomment_line(ln))
                            i += 1
                            break
                        uln = self._ww3_nml_force_uncomment_line(ln)
                        out.append(_patch_smcc_smc_line(uln))
                        i += 1
                    continue

                out.append(line)
                i += 1

            # SMC 深度取自 grid_cell.dat 第 5 列（正的水深 m）。WW3 海点判据为
            # ZBIN = DEPTH%SF × depth ≤ ZLIM(<0)，故必须 DEPTH%SF=-1 把正深度翻成负（水）；
            # 否则正深度全部 > ZLIM → 全判陆地 → ww3_grid 的 Status map 全 0、波浪全缺测。
            # 上面已把模板里的 DEPTH_NML 文档块注释掉，这里追加一个生效的块强制 SF=-1。
            out.append("\n&DEPTH_NML\n  DEPTH%SF        = -1.0\n/\n")

            with open(nml_path, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(out)
            for aux in ("grid_iside.dat", "grid_jside.dat", "grid_subtr.dat"):
                ap = os.path.join(work_dir, aux)
                if not os.path.isfile(ap):
                    self.log(
                        tr(
                            "step4_smcc_ww3_aux_missing",
                            "⚠️ WW3 SMCG 预处理还需要数据文件 {file}（请放在工作目录；grid_subtr 可由 smc_generator 生成，ISIDE/JSIDE 需 SMCGSideMP 等工具生成）",
                        ).format(file=aux)
                    )
        except Exception as e:
            self.log(
                tr(
                    "step4_smcc_ww3_grid_transform_failed",
                    "⚠️ SMC 网格 ww3_grid.nml 调整失败：{err}",
                ).format(err=e)
            )

    def _set_namelists_misc_flagtr_zero(self, namelists_path):
        """namelists.nml 中 &MISC 的 FLAGTR 改为 0（非结构网格无障碍子网格）。"""
        if not namelists_path or not os.path.isfile(namelists_path):
            return
        try:
            with open(namelists_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            new_lines = []
            for line in lines:
                ls = line.lstrip()
                if ls.startswith("!"):
                    new_lines.append(line)
                    continue
                if "&MISC" in line and "FLAGTR" in line:
                    new_lines.append(
                        re.sub(r"FLAGTR\s*=\s*\d+", "FLAGTR = 0", line, count=1)
                    )
                else:
                    new_lines.append(line)
            with open(namelists_path, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(new_lines)
        except Exception as e:
            self.log(
                tr(
                    "step4_namelists_flagtr_failed",
                    "⚠️ 修改 namelists.nml FLAGTR 失败：{err}",
                ).format(err=e)
            )

    def sync_grid_meta_to_grid_nml(self, target_dir=None):
        """从 grid.meta 提取参数并同步到 ww3_grid.nml（普通网格模式）"""
        if target_dir is None:
            target_dir = self.selected_folder
        if not target_dir or not isinstance(target_dir, str):
            self.log(tr("workdir_not_exists", "❌ 当前工作目录不存在！"))
            return
        self._sync_grid_meta_to_grid_nml_in_dir(target_dir)

    def _apply_cfl_timesteps_to_grid_nml(self, grid_dir):
        """按该网格自身 dx/dy 与（全局）FREQ1 重算 CFL 时间步并写回 ww3_grid.nml。

        嵌套时 coarse/fine 的传播步 DTXY 必须不同（CFL: DTXY ∝ Δx），否则细网格
        会违反 CFL 而数值不稳定。从已写好的 ww3_grid.nml 读 RECT%SX/SY/Y0/NY 与
        SPECTRUM%FREQ1，调用 recommend_timesteps 重算后替换 TIMESTEPS%DT*（只改活动
        行，跳过模板注释里的占位）。
        """
        import os
        import re
        from workflows.domain.timestep_recommendation import recommend_timesteps

        nml = os.path.join(grid_dir, "ww3_grid.nml")
        if not os.path.isfile(nml):
            return
        try:
            with open(nml, encoding="utf-8") as f:
                lines = f.readlines()

            def _val(key, cast=float):
                pat = re.compile(rf"{re.escape(key)}\s*=\s*([0-9.+\-Ee]+)")
                for ln in lines:
                    if ln.lstrip().startswith("!"):
                        continue
                    m = pat.search(ln)
                    if m:
                        return cast(m.group(1))
                return None

            sx = _val("RECT%SX"); sy = _val("RECT%SY")
            y0 = _val("RECT%Y0"); ny = _val("RECT%NY", int)
            freq1 = _val("SPECTRUM%FREQ1")
            if not sx or not sy or not freq1 or y0 is None or not ny:
                return
            lat_center = y0 + (ny - 1) * sy / 2.0
            rec = recommend_timesteps(dx_deg=sx, dy_deg=sy, freq1=freq1, lat_deg=lat_center)
            ts_map = {"TIMESTEPS%DTMAX": rec.dtmax, "TIMESTEPS%DTXY": rec.dtxy,
                      "TIMESTEPS%DTKTH": rec.dtkth, "TIMESTEPS%DTMIN": rec.dtmin}
            out = []
            for ln in lines:
                if not ln.lstrip().startswith("!"):
                    for key, val in ts_map.items():
                        if re.search(rf"{re.escape(key)}\s*=", ln):
                            ln = re.sub(rf"({re.escape(key)}\s*=\s*)[0-9.+\-Ee]+",
                                        rf"\g<1>{val}", ln)
                            break
                out.append(ln)
            with open(nml, "w", encoding="utf-8") as f:
                f.writelines(out)
            prefix = f"[{os.path.basename(grid_dir)}] " if grid_dir else ""
            self.log(prefix + tr(
                "step4_cfl_timesteps_applied",
                "✅ 按 CFL 重算时间步：DTXY={dtxy}, DTMAX={dtmax}, DTKTH={dtkth}").format(
                dtxy=rec.dtxy, dtmax=rec.dtmax, dtkth=rec.dtkth))
        except Exception as e:
            self.log(tr("step4_cfl_timesteps_failed", "⚠️ CFL 时间步重算失败：{error}").format(error=e))

    def _sync_grid_meta_to_grid_nml_in_dir(self, target_dir, grid_label=""):
        """从 grid.meta 仅同步 GRID%TYPE/COORD/CLOS、RECT%*、DEPTH%SF、OBST%SF 到 ww3_grid.nml（与扁平 meta 一致）。"""
        if not target_dir or not isinstance(target_dir, str):
            return

        meta_path = structured_grid_desc_path(target_dir)
        nml_path = os.path.join(target_dir, "ww3_grid.nml")

        if not meta_path:
            self.log(tr("meta_file_not_found", "⚠️ 未找到 grid.meta：{path}，跳过 meta to grid 转换").format(path=target_dir))
            return
        if not os.path.isfile(nml_path):
            self.log(tr("step4_ww3_grid_nml_missing", "⚠️ 未找到 {path}，跳过 meta 同步").format(path=nml_path))
            return

        try:
            sync = parse_ww3_grid_meta_for_sync(meta_path)
            if not sync:
                self.log(
                    tr(
                        "step4_grid_meta_sync_parse_fail",
                        "⚠️ grid.meta 中缺少 RECT 几何行（RECT%NX/NY/SX/SY/X0/Y0），无法同步到 ww3_grid.nml",
                    )
                )
                self.log(tr("file_path", "   文件路径：{path}").format(path=meta_path))
                return

            with open(nml_path, "r", encoding="utf-8") as f:
                nml_lines = f.readlines()

            new_lines = []
            in_grid = in_rect = in_depth = in_obst = False

            for line in nml_lines:
                ls = line.lstrip()
                is_comment = ls.startswith("!")
                u = line.upper()

                if not is_comment and "&GRID_NML" in u:
                    in_grid, in_rect, in_depth, in_obst = True, False, False, False
                    new_lines.append(line)
                    continue
                if not is_comment and "&RECT_NML" in u:
                    in_grid, in_rect, in_depth, in_obst = False, True, False, False
                    new_lines.append(line)
                    continue
                if not is_comment and "&DEPTH_NML" in u:
                    in_grid, in_rect, in_depth, in_obst = False, False, True, False
                    new_lines.append(line)
                    continue
                if not is_comment and "&OBST_NML" in u:
                    in_grid, in_rect, in_depth, in_obst = False, False, False, True
                    new_lines.append(line)
                    continue

                st = line.strip()
                if not is_comment and (st == "/" or st.startswith("/")):
                    in_grid = in_rect = in_depth = in_obst = False
                    new_lines.append(line)
                    continue

                if not is_comment and in_grid and "=" in line:
                    if "GRID%TYPE" in line and "grid_type" in sync:
                        new_lines.append(
                            self._ww3_nml_assign_line("GRID%TYPE", f"'{sync['grid_type']}'")
                        )
                        continue
                    if "GRID%COORD" in line and "grid_coord" in sync:
                        new_lines.append(
                            self._ww3_nml_assign_line("GRID%COORD", f"'{sync['grid_coord']}'")
                        )
                        continue
                    if "GRID%CLOS" in line and "grid_clos" in sync:
                        new_lines.append(
                            self._ww3_nml_assign_line("GRID%CLOS", f"'{sync['grid_clos']}'")
                        )
                        continue

                if not is_comment and in_rect and "=" in line:
                    if "RECT%NX" in line and "XCOORD" not in line.upper():
                        new_lines.append(self._ww3_nml_assign_line("RECT%NX", str(int(sync["nx"]))))
                        continue
                    if "RECT%NY" in line and "YCOORD" not in line.upper():
                        new_lines.append(self._ww3_nml_assign_line("RECT%NY", str(int(sync["ny"]))))
                        continue
                    if "RECT%SX" in line and "XCOORD" not in line.upper():
                        new_lines.append(
                            self._ww3_nml_assign_line("RECT%SX", f"{float(sync['sx']):15.12f}")
                        )
                        continue
                    if "RECT%SY" in line and "YCOORD" not in line.upper():
                        new_lines.append(
                            self._ww3_nml_assign_line("RECT%SY", f"{float(sync['sy']):15.12f}")
                        )
                        continue
                    if "RECT%X0" in line:
                        new_lines.append(
                            self._ww3_nml_assign_line("RECT%X0", f"{float(sync['x0']):8.4f}")
                        )
                        continue
                    if "RECT%Y0" in line:
                        new_lines.append(
                            self._ww3_nml_assign_line("RECT%Y0", f"{float(sync['y0']):8.4f}")
                        )
                        continue

                if not is_comment and in_depth and "DEPTH%SF" in line and "=" in line and "depth_sf" in sync:
                    new_lines.append(
                        self._ww3_nml_assign_line(
                            "DEPTH%SF", f"{float(sync['depth_sf']):.6f}", key_width=16
                        )
                    )
                    continue

                if not is_comment and in_obst and "OBST%SF" in line and "=" in line and "obst_sf" in sync:
                    new_lines.append(
                        self._ww3_nml_assign_line(
                            "OBST%SF", f"{float(sync['obst_sf']):.6f}", key_width=15
                        )
                    )
                    continue

                new_lines.append(line)

            with open(nml_path, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(new_lines)

            prefix = f"{grid_label} " if grid_label else ""
            self.log(f"{prefix}{tr('step4_grid_meta_synced', '✅ 已成功同步 grid.meta 参数到 ww3_grid.nml')}")
        except Exception as e:
            prefix = f"{grid_label} " if grid_label else ""
            self.log(prefix + tr("step4_grid_meta_sync_failed", "⚠️ 同步 grid.meta 到 ww3_grid.nml 失败: {error}").format(error=e))

    def _update_grid_closure_from_meta(self, target_dir, grid_label=""):
        """根据 grid.nml / ww3_grid.nml.* / grid.meta 设置 ww3_grid.nml 中 GRID%CLOS（全球网格用 SMPL）"""
        if not target_dir or not isinstance(target_dir, str):
            return

        meta_path = structured_grid_desc_path(target_dir)
        nml_path = os.path.join(target_dir, "ww3_grid.nml")
        if not meta_path or not os.path.exists(nml_path):
            return

        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta_lines = f.readlines()
        except Exception:
            return

        clos = None
        for line in meta_lines:
            u = line.upper()
            if "GRID%CLOS" in u and "=" in line:
                if "SMPL" in u:
                    clos = "SMPL"
                    break
                if "NONE" in u:
                    clos = "NONE"
                    break
        if clos is None:
            for line in meta_lines:
                u = line.upper()
                if "RECT" in u or "CURV" in u:
                    if "SMPL" in u:
                        clos = "SMPL"
                        break
                    if "NONE" in u:
                        clos = "NONE"
                        break

        if clos is None:
            return

        try:
            with open(nml_path, "r", encoding="utf-8") as f:
                nml_lines = f.readlines()

            new_lines = []
            in_grid_nml = False
            clos_updated = False

            for line in nml_lines:
                if "&GRID_NML" in line.upper():
                    in_grid_nml = True
                    new_lines.append(line)
                    continue

                if in_grid_nml:
                    if "/" in line:
                        if not clos_updated:
                            new_lines.append(f"  GRID%CLOS         =  '{clos}'\n")
                            clos_updated = True
                        in_grid_nml = False
                        new_lines.append(line)
                        continue

                    line_stripped = line.lstrip()
                    is_comment = line_stripped.startswith('!')
                    if not is_comment and "GRID%CLOS" in line and "=" in line:
                        new_lines.append(f"  GRID%CLOS         =  '{clos}'\n")
                        clos_updated = True
                        continue

                new_lines.append(line)

            with open(nml_path, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(new_lines)

            if clos != "NONE":
                prefix = f"[{grid_label}] " if grid_label else ""
                self.log(prefix + tr("step4_grid_clos_updated", "✅ 已更新 ww3_grid.nml 的 GRID%CLOS：{value}").format(value=clos))

        except Exception as e:
            prefix = f"[{grid_label}] " if grid_label else ""
            self.log(prefix + tr("step4_grid_clos_update_failed", "⚠️ 更新 ww3_grid.nml 的 GRID%CLOS 失败: {error}").format(error=e))
