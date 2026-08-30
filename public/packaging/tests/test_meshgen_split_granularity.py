"""split_boundary 的并行粒度：按子块而不是按多边形。

岸线数据极度不均衡——18.8 万个多边形里只有 165 个需要拆分，而单个最大的
就占 72.9% 的工作量。按多边形发任务时，无论多少 worker，加速比都被那一个
多边形卡在 1.4x 左右。
"""

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PYGRIDGEN = REPO_ROOT / "meshgen" / "structured_generator" / "pygridgen"


@unittest.skipUnless(PYGRIDGEN.is_dir(), "meshgen 源码不在此环境中")
class TileGranularityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if str(PYGRIDGEN) not in sys.path:
            sys.path.insert(0, str(PYGRIDGEN))
        try:
            import importlib
            cls.sb = importlib.import_module("grid.split_boundary")
        except ImportError as exc:  # pragma: no cover - optional deps
            raise unittest.SkipTest(f"无法导入 split_boundary：{exc}")

    @staticmethod
    def _poly(west, east, south, north, n=40):
        import numpy as np
        t = np.linspace(0, 2 * np.pi, n)
        cx, cy = (west + east) / 2, (south + north) / 2
        rx, ry = (east - west) / 2, (north - south) / 2
        x = cx + rx * np.cos(t)
        y = cy + ry * np.sin(t)
        return {"x": x, "y": y, "n": n, "west": float(west), "east": float(east),
                "south": float(south), "north": float(north),
                "width": float(east - west), "height": float(north - south),
                "level": 1}

    # ── 子块划分 ────────────────────────────────────────────
    def test_tiles_cover_the_polygon_in_lx_ly_order(self):
        poly = self._poly(-4.2, 3.7, -1.5, 2.9)
        boxes = self.sb._tile_boxes(poly, 2)
        xs = self.sb._tile_axis(poly["west"], poly["east"], 2)
        ys = self.sb._tile_axis(poly["south"], poly["north"], 2)
        self.assertEqual(len(boxes), (len(xs) - 1) * (len(ys) - 1))
        # 顺序必须是先 lx 后 ly，与原串行实现一致
        expect = [[ys[ly], xs[lx], ys[ly + 1], xs[lx + 1]]
                  for lx in range(len(xs) - 1) for ly in range(len(ys) - 1)]
        self.assertEqual(boxes, expect)

    def test_tile_axis_spans_the_whole_extent(self):
        axis = self.sb._tile_axis(-23.4, -18.1, 2)
        import math
        self.assertLessEqual(axis[0], math.floor(-23.4))
        self.assertGreaterEqual(axis[-1], math.ceil(-18.1))
        self.assertEqual(axis, sorted(set(axis)))

    def test_a_big_polygon_yields_many_tiles(self):
        # 这是重点：单个大多边形必须能拆成很多份，否则并行度上不去。
        poly = self._poly(-180.0, 180.0, -80.0, 80.0)
        self.assertGreater(len(self.sb._tile_boxes(poly, 5)), 100)

    # ── 输出顺序与内容 ──────────────────────────────────────
    def test_small_polygons_pass_through_untouched(self):
        small = [self._poly(0.1, 0.4, 0.1, 0.4), self._poly(5.1, 5.4, 5.1, 5.4)]
        with redirect_stdout(io.StringIO()):
            out = self.sb.split_boundary(small, 5, 20)
        self.assertEqual(len(out), 2)
        for original, kept in zip(small, out):
            self.assertIs(original, kept)

    def test_order_follows_the_input_polygons(self):
        polys = [self._poly(0.1, 0.4, 0.1, 0.4),        # 不拆
                 self._poly(-3.0, 3.0, -3.0, 3.0),       # 拆
                 self._poly(9.1, 9.4, 9.1, 9.4)]         # 不拆
        with redirect_stdout(io.StringIO()):
            out = self.sb.split_boundary(polys, 2, 20)
        self.assertIs(out[0], polys[0])
        self.assertIs(out[-1], polys[-1])
        self.assertGreater(len(out), 3)

    def test_nothing_to_split_returns_the_input(self):
        polys = [self._poly(0.1, 0.4, 0.1, 0.4)]
        with redirect_stdout(io.StringIO()):
            out = self.sb.split_boundary(polys, 100, 20)
        self.assertEqual(out, polys)

    def test_empty_input(self):
        self.assertEqual(self.sb.split_boundary([], 5, 20), [])


if __name__ == "__main__":
    unittest.main()
