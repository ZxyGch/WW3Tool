"""全球网格的两个几何前提：不重复经线，且「宽」不等于「绕接缝」。"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PYGRIDGEN = REPO_ROOT / "meshgen" / "structured_generator" / "pygridgen"


@unittest.skipUnless(PYGRIDGEN.is_dir(), "meshgen 源码不在此环境中")
class WideDomainIsNotWrappedTest(unittest.TestCase):
    """compute_boundary 曾把「跨度 > 180°」当成「绕接缝」。

    全球域跨满一圈却仍是一个普通矩形；当成绕接缝会让整块位于域内的多边形
    也走裁剪路径，而那条路径只保留真正穿越边界的多边形——结果全球网格几乎
    没有岸线（10830 个多边形只留下 30 段）。
    """

    @classmethod
    def setUpClass(cls):
        if str(PYGRIDGEN) not in sys.path:
            sys.path.insert(0, str(PYGRIDGEN))
        try:
            import importlib
            cls.cb = staticmethod(
                importlib.import_module("grid.compute_boundary").compute_boundary)
        except ImportError as exc:  # pragma: no cover - optional deps
            raise unittest.SkipTest(f"无法导入 compute_boundary：{exc}")

    @staticmethod
    def _square(west, east, south, north):
        import numpy as np
        return {
            "x": np.array([west, east, east, west, west], dtype=float),
            "y": np.array([south, south, north, north, south], dtype=float),
            "n": 5, "west": float(west), "east": float(east),
            "south": float(south), "north": float(north), "level": 1,
        }

    def test_polygon_inside_a_global_domain_is_kept(self):
        # 全球域：lat -91..91, lon -181..180
        poly = self._square(-23.0, -22.0, 33.0, 34.0)
        _b, n = self.cb([-91.0, -181.0, 91.0, 180.0], [poly], 20, 1, quiet=True)
        self.assertEqual(n, 1, "整块位于全球域内的多边形必须被保留")

    def test_polygon_inside_a_0_360_global_domain_is_kept(self):
        poly = self._square(337.0, 338.0, 33.0, 34.0)
        _b, n = self.cb([-91.0, -1.0, 91.0, 360.0], [poly], 20, 1, quiet=True)
        self.assertEqual(n, 1)

    def test_polygon_outside_is_still_rejected(self):
        poly = self._square(-23.0, -22.0, 33.0, 34.0)
        _b, n = self.cb([-91.0, 100.0, 91.0, 140.0], [poly], 20, 1, quiet=True)
        self.assertEqual(n, 0)

    def test_a_polygon_spanning_the_whole_turn_is_not_clipped(self):
        # 南极洲那种跨满整圈的多边形：域覆盖全球时不该被域边界切开，
        # 切开后沿边界闭合会凭空造出一条岸线。
        poly = self._square(-180.0, 180.0, -78.0, -62.0)
        for lo, hi in ((-181.0, 180.0), (-1.0, 360.0)):
            _b, n = self.cb([-91.0, lo, 91.0, hi], [poly], 20, 1, quiet=True)
            self.assertEqual(n, 1, msg=f"域 [{lo}, {hi}] 不该切开整圈多边形")

    def test_latitude_still_excludes_on_a_global_domain(self):
        # 经度全覆盖不代表纬度也全覆盖。
        poly = self._square(-23.0, -22.0, 80.0, 85.0)
        _b, n = self.cb([-60.0, -181.0, 60.0, 180.0], [poly], 20, 1, quiet=True)
        self.assertEqual(n, 0)

    def test_regional_domain_behaviour_is_unchanged(self):
        poly = self._square(120.5, 121.5, 29.0, 30.0)
        _b, n = self.cb([28.0, 120.0, 32.0, 124.0], [poly], 20, 1, quiet=True)
        self.assertEqual(n, 1)


@unittest.skipUnless(PYGRIDGEN.is_dir(), "meshgen 源码不在此环境中")
class GlobalMeridianNotRepeatedTest(unittest.TestCase):
    """周期网格里 0° 与 360° 是同一条经线，不能各占一列。

    WW3 对 GRID%CLOS='SMPL' 会强制 SX = 360/NX（w3gridmd.F90:3773），
    所以多出来的那一列会把整条经度轴压缩，最东端偏差达一整个格子。
    """

    def test_source_drops_the_repeat(self):
        src = (PYGRIDGEN / "create_grid.py").read_text(encoding="utf-8")
        self.assertIn("dropped the repeated meridian", src)

    def test_spacing_is_consistent_after_dropping(self):
        # NX = 360/dx 时，WW3 强制的 SX 恰好等于请求的 dx。
        for dx in (0.5, 0.25, 1.0, 0.1):
            nx_wrong = int(round(360.0 / dx)) + 1     # 含重复经线
            nx_right = int(round(360.0 / dx))
            self.assertNotAlmostEqual(360.0 / nx_wrong, dx, places=6)
            self.assertAlmostEqual(360.0 / nx_right, dx, places=12)

    def test_the_displacement_reaches_a_whole_cell(self):
        # 0.5 度全球网格用 721 列时，最东端偏差正好一个格子。
        dx, nx = 0.5, 721
        sx_ww3 = 360.0 / nx
        err = (nx - 1) * dx - (nx - 1) * sx_ww3
        self.assertAlmostEqual(err / dx, 1.0, places=2)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(PYGRIDGEN.is_dir(), "meshgen 源码不在此环境中")
class PeriodicNeighbourTest(unittest.TestCase):
    """全球网格在经度上是周期的，首尾两列互为邻居。"""

    @classmethod
    def setUpClass(cls):
        if str(PYGRIDGEN) not in sys.path:
            sys.path.insert(0, str(PYGRIDGEN))
        try:
            import importlib
            cls.nb = staticmethod(
                importlib.import_module("grid.create_obstr")._x_neighbour)
        except ImportError as exc:  # pragma: no cover - optional deps
            raise unittest.SkipTest(f"无法导入 create_obstr：{exc}")

    def test_interior_is_unaffected_by_wrapping(self):
        for wrap in (False, True):
            self.assertEqual(self.nb(5, 1, 10, wrap), 6)
            self.assertEqual(self.nb(5, -1, 10, wrap), 4)

    def test_non_periodic_grid_has_no_neighbour_past_the_edge(self):
        self.assertIsNone(self.nb(9, 1, 10, False))
        self.assertIsNone(self.nb(0, -1, 10, False))

    def test_periodic_grid_wraps_at_both_ends(self):
        self.assertEqual(self.nb(9, 1, 10, True), 0)
        self.assertEqual(self.nb(0, -1, 10, True), 9)

    def test_multi_step_offsets_wrap(self):
        self.assertEqual(self.nb(8, 3, 10, True), 1)
        self.assertEqual(self.nb(1, -3, 10, True), 8)

    def test_a_cell_is_never_its_own_neighbour(self):
        # 绕一整圈会回到自己，那不是邻居。
        self.assertIsNone(self.nb(3, 10, 10, True))
        self.assertIsNone(self.nb(0, 1, 1, True))

    def test_single_column_grid_has_no_neighbour(self):
        self.assertIsNone(self.nb(0, 1, 1, False))
