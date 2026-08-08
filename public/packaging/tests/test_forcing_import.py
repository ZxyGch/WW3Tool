"""强迫场自定义变量映射（方案 §12）测试。

[EN] Forcing custom variable mapping tests (spec §12).

覆盖：标准变量自动识别、部分/完全自定义、错误场景、坐标与时间变量名
不规则、裁剪/纬度翻转后变量名保持不变、manifest 持久化与恢复、NML 生成。
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import netCDF4
from netCDF4 import Dataset

from workflows.domain.config_models import ForcingVariableOverride
from workflows.infrastructure.forcing.forcing_normalize_service import ForcingNormalizeService
from workflows.infrastructure.forcing.forcing_manifest import load_manifest, save_manifest_entry
from workflows.infrastructure.forcing.forcing_variable_resolver import (
    ForcingVariableError,
    resolve_all_fields,
    resolve_forcing_variables,
)


def _make_wind_file(path, *, irregular=False, with_cf=False, descending_lat=False):
    """构造风场 NetCDF；``irregular`` 使用不规则变量名。

    [EN] Build a wind NetCDF; ``irregular`` uses non-standard variable names.
    """
    with Dataset(path, "w") as ds:
        ds.createDimension("XLONG", 4)
        ds.createDimension("XLAT", 3)
        ds.createDimension("time", 2)
        lon = ds.createVariable("XLONG", "f4", ("XLONG",))
        lat = ds.createVariable("XLAT", "f4", ("XLAT",))
        t = ds.createVariable("valid_time", "f8", ("time",))
        t.units = "hours since 2020-01-01 00:00:00"
        u = ds.createVariable("UGRD_10m", "f4", ("time", "XLAT", "XLONG"))
        v = ds.createVariable("VGRD_10m", "f4", ("time", "XLAT", "XLONG"))
        if with_cf or irregular:
            if with_cf:
                lon.standard_name = "longitude"
                lat.standard_name = "latitude"
                t.axis = "T"
                u.standard_name = "eastward_wind"
                v.standard_name = "northward_wind"
                u.units = "m s-1"
                v.units = "m s-1"
            lon.units = "degrees_east"
            lat.units = "degrees_north"
        lon[:] = [100, 102, 104, 106]
        lat[:] = [24, 22, 20] if descending_lat else [20, 22, 24]
        t[:] = [0, 6]
        u[:] = 1.0
        v[:] = 2.0


class ForcingResolverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_standard_names_auto_detected(self):
        path = os.path.join(self.tmp, "wind.nc")
        with Dataset(path, "w") as ds:
            ds.createDimension("longitude", 4)
            ds.createDimension("latitude", 3)
            ds.createDimension("time", 2)
            t = ds.createVariable("time", "f8", ("time",))
            t.units = "hours since 2020-01-01"
            ds.createVariable("longitude", "f4", ("longitude",))
            ds.createVariable("latitude", "f4", ("latitude",))
            ds.createVariable("u10", "f4", ("time", "latitude", "longitude"))
            ds.createVariable("v10", "f4", ("time", "latitude", "longitude"))
        r = resolve_forcing_variables(path, "wind")
        self.assertEqual(r.components, ["u10", "v10"])
        self.assertEqual((r.longitude, r.latitude), ("longitude", "latitude"))

    def test_irregular_names_with_cf_auto_detected(self):
        path = os.path.join(self.tmp, "wind_custom.nc")
        _make_wind_file(path, with_cf=True)
        r = resolve_forcing_variables(path, "wind")
        self.assertEqual(r.components, ["UGRD_10m", "VGRD_10m"])
        self.assertEqual((r.longitude, r.latitude, r.source_time), ("XLONG", "XLAT", "valid_time"))

    def test_irregular_names_without_cf_require_manual(self):
        path = os.path.join(self.tmp, "wind_noattr.nc")
        _make_wind_file(path, irregular=True)
        with self.assertRaises(ForcingVariableError):
            resolve_forcing_variables(path, "wind")
        r = resolve_forcing_variables(
            path,
            "wind",
            ForcingVariableOverride(
                longitude="XLONG",
                latitude="XLAT",
                time="valid_time",
                u="UGRD_10m",
                v="VGRD_10m",
            ),
        )
        self.assertEqual(r.components, ["UGRD_10m", "VGRD_10m"])

    def test_partial_custom_partial_auto(self):
        path = os.path.join(self.tmp, "wind_custom.nc")
        _make_wind_file(path, with_cf=True)
        r = resolve_forcing_variables(path, "wind", ForcingVariableOverride(u="UGRD_10m"))
        self.assertEqual(r.components, ["UGRD_10m", "VGRD_10m"])

    def test_custom_variable_not_exists(self):
        path = os.path.join(self.tmp, "wind_custom.nc")
        _make_wind_file(path, with_cf=True)
        with self.assertRaises(ForcingVariableError):
            resolve_forcing_variables(path, "wind", ForcingVariableOverride(v="NOPE"))

    def test_u_v_same_variable_rejected(self):
        path = os.path.join(self.tmp, "wind_custom.nc")
        _make_wind_file(path, with_cf=True)
        with self.assertRaises(ForcingVariableError):
            resolve_forcing_variables(
                path, "wind", ForcingVariableOverride(u="UGRD_10m", v="UGRD_10m")
            )

    def test_multi_field_file_resolves_both(self):
        path = os.path.join(self.tmp, "merged.nc")
        with Dataset(path, "w") as ds:
            ds.createDimension("longitude", 4)
            ds.createDimension("latitude", 3)
            ds.createDimension("time", 2)
            ds.createVariable("longitude", "f4", ("longitude",))
            ds.createVariable("latitude", "f4", ("latitude",))
            t = ds.createVariable("time", "f8", ("time",))
            t.units = "hours since 2020-01-01"
            ds.createVariable("u10", "f4", ("time", "latitude", "longitude"))
            ds.createVariable("v10", "f4", ("time", "latitude", "longitude"))
            zos = ds.createVariable("zos", "f4", ("time", "latitude", "longitude"))
            zos.standard_name = "sea_surface_height"
        allf = resolve_all_fields(path)
        self.assertIn("wind", allf)
        self.assertIn("level", allf)
        self.assertEqual(allf["level"].components, ["zos"])


class ForcingNormalizeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_normalize_preserves_names_and_standardizes_time(self):
        src = os.path.join(self.tmp, "wind_custom.nc")
        _make_wind_file(src, with_cf=True)
        r = resolve_forcing_variables(src, "wind")
        out = os.path.join(self.tmp, "wind_out.nc")
        ok = ForcingNormalizeService().normalize(src, out, variables=r)
        self.assertTrue(ok)
        with Dataset(out, "r") as ds:
            names = set(ds.variables.keys())
            self.assertIn("UGRD_10m", names)  # 不再重命名为 u10
            self.assertIn("VGRD_10m", names)
            self.assertIn("XLONG", names)  # 经纬度保留原名
            self.assertIn("XLAT", names)
            self.assertIn("time", names)
            self.assertNotIn("valid_time", names)  # 时间统一为 time
            self.assertNotIn("u10", names)

    def test_normalize_flips_descending_latitude_keeps_names(self):
        src = os.path.join(self.tmp, "wind_desc.nc")
        _make_wind_file(src, with_cf=True, descending_lat=True)
        r = resolve_forcing_variables(src, "wind")
        out = os.path.join(self.tmp, "wind_out.nc")
        ok = ForcingNormalizeService().normalize(src, out, variables=r)
        self.assertTrue(ok)
        with Dataset(out, "r") as ds:
            self.assertIn("UGRD_10m", ds.variables)
            self.assertIn("XLAT", ds.variables)
            lat = ds.variables["XLAT"][:]
            self.assertLess(lat[0], lat[-1])  # 翻转后递增


class ForcingManifestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_manifest_roundtrip(self):
        from workflows.domain.config_models import ResolvedForcingVariables

        rv = ResolvedForcingVariables(
            field="wind",
            longitude="XLONG",
            latitude="XLAT",
            source_time="valid_time",
            output_time="time",
            components=["UGRD_10m", "VGRD_10m"],
        )
        self.assertTrue(save_manifest_entry(self.tmp, "wind", rv, "wind.nc"))
        data = load_manifest(self.tmp)
        self.assertEqual(data["wind"]["file"], "wind.nc")
        self.assertEqual(data["wind"]["longitude"], "XLONG")
        self.assertEqual(data["wind"]["variables"], ["UGRD_10m", "VGRD_10m"])
        # 覆盖更新
        self.assertTrue(save_manifest_entry(self.tmp, "ice", rv, "ice.nc"))
        data = load_manifest(self.tmp)
        self.assertIn("ice", data)
        self.assertIn("wind", data)


class ForcingConfigTest(unittest.TestCase):
    def test_legacy_yaml_without_custom_parses(self):
        from workflows.application.configuration import _parse_forcing_custom

        self.assertEqual(_parse_forcing_custom(None), {})
        self.assertEqual(_parse_forcing_custom(""), {})

    def test_custom_parses_and_validates(self):
        from workflows.application.configuration import _parse_forcing_custom

        custom = _parse_forcing_custom(
            {"wind": {"u": "UGRD_10m", "longitude": None}, "ice": {"thickness": "sithick"}}
        )
        self.assertEqual(custom["wind"].u, "UGRD_10m")
        self.assertIsNone(custom["wind"].longitude)
        self.assertEqual(custom["ice"].thickness, "sithick")
        with self.assertRaises(Exception):
            _parse_forcing_custom({"wind": {"bad_key": "x"}})


class ForcingRemotePathTest(unittest.TestCase):
    """服务器路径场（本机不处理）测试。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _write_params(self, workdir, **forcing_extra):
        params = os.path.join(self.tmp, "params.yml")
        lines = [f"workdir:\n  path: {workdir}\n", "forcing:\n  wind: null\n  process_mode: copy\n  auto_associate: false\n"]
        for key, value in forcing_extra.items():
            if "\n" in str(value):
                lines.append(str(value))
                if not str(value).endswith("\n"):
                    lines.append("\n")
            else:
                lines.append(f"  {key}: {value}\n")
        with open(params, "w") as f:
            f.writelines(lines)
        return params

    def test_remote_paths_parsed(self):
        from workflows.application.configuration import _parse_forcing_remote_paths

        out = _parse_forcing_remote_paths({"wind": "/data/wind.nc", "current": None, "ice": ""})
        self.assertEqual(out, {"wind": "/data/wind.nc"})
        self.assertEqual(_parse_forcing_remote_paths(None), {})

    def test_remote_field_skips_local_import(self):
        from workflows.application.configuration import load_pipeline_config
        from workflows.application.preprocessing_workflow import run_prepare_forcing
        from workflows.domain.forcing_fields import ForcingField
        from workflows.infrastructure.forcing.forcing_manifest import load_manifest

        workdir = os.path.join(self.tmp, "workdir")
        params = self._write_params(
            workdir,
            custom=(
                "  custom:\n"
                "    wind:\n"
                "      longitude: XLONG\n"
                "      latitude: XLAT\n"
                "      time: valid_time\n"
                "      u: UGRD_10m\n"
                "      v: VGRD_10m\n"
            ),
            remote_paths=(
                "  remote_paths:\n"
                "    wind: /data/cluster/wind_global.nc\n"
            ),
        )
        cfg = load_pipeline_config(params)
        self.assertEqual(cfg.forcing.remote_paths["wind"], "/data/cluster/wind_global.nc")
        result = run_prepare_forcing(cfg, None, fields=[ForcingField.WIND])
        self.assertEqual(result.forcing_files.wind, "/data/cluster/wind_global.nc")
        # 本机不应生成任何强迫场数据文件（仅 manifest 记录）
        # [EN] No forcing data files are produced locally (manifest only)
        self.assertEqual([f for f in os.listdir(workdir) if f.endswith(".nc")], [])
        mani = load_manifest(workdir)
        self.assertEqual(mani["wind"]["file"], "wind_global.nc")
        self.assertEqual(mani["wind"]["variables"], ["UGRD_10m", "VGRD_10m"])

    def test_remote_field_without_vars_warns_no_manifest(self):
        from workflows.application.configuration import load_pipeline_config
        from workflows.application.preprocessing_workflow import run_prepare_forcing
        from workflows.domain.forcing_fields import ForcingField
        from workflows.infrastructure.forcing.forcing_manifest import load_manifest

        workdir = os.path.join(self.tmp, "workdir")
        params = self._write_params(
            workdir,
            remote_paths="  remote_paths:\n    wind: /data/cluster/wind.nc\n",
        )
        cfg = load_pipeline_config(params)
        result = run_prepare_forcing(cfg, None, fields=[ForcingField.WIND])
        self.assertEqual(result.forcing_files.wind, "/data/cluster/wind.nc")
        # 变量未填写 → manifest 不生成，NML 阶段会提示
        self.assertEqual(load_manifest(workdir), {})

    def test_scan_workdir_recovers_remote_field_from_manifest(self):
        """「仅应用 WW3 参数」路径：scan_forcing_files 从 manifest 恢复远程场。"""
        from workflows.domain.forcing_fields import ForcingField, Step2Files
        from workflows.infrastructure.forcing.file_service import FileService
        from workflows.infrastructure.forcing.forcing_manifest import save_remote_manifest_entry
        from workflows.domain.config_models import ForcingVariableOverride

        workdir = os.path.join(self.tmp, "workdir")
        os.makedirs(workdir)
        save_remote_manifest_entry(
            workdir,
            "wind",
            "/data/cluster/wind_global.nc",
            ForcingVariableOverride(u="UGRD_10m", v="VGRD_10m"),
        )
        files = FileService().scan_forcing_files(workdir, auto_associate=True)
        self.assertIsNotNone(files.wind)
        # 本地无文件，但路径被记录（NML 阶段走远程分支）
        self.assertFalse(os.path.exists(files.wind))
        self.assertEqual(os.path.basename(files.wind), "wind_global.nc")


if __name__ == "__main__":
    unittest.main()
