"""create_obstr 的数值边界：退化单元与 matmul 的虚假浮点标志。"""

import sys
import unittest
import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PYGRIDGEN = REPO_ROOT / "meshgen" / "structured_generator" / "pygridgen"


@unittest.skipUnless(PYGRIDGEN.is_dir(), "meshgen 源码不在此环境中")
class ClampedRatioTest(unittest.TestCase):
    """零宽/零高单元不该产生除零，也不该给出任意的 0/1。"""

    @classmethod
    def setUpClass(cls):
        if str(PYGRIDGEN) not in sys.path:
            sys.path.insert(0, str(PYGRIDGEN))
        try:
            import importlib
            cls.fn = staticmethod(
                importlib.import_module("grid.create_obstr")._clamped_ratio)
        except ImportError as exc:  # pragma: no cover - optional deps
            raise unittest.SkipTest(f"无法导入 create_obstr：{exc}")

    def test_ordinary_ratio(self):
        self.assertAlmostEqual(self.fn(0.5, 2.0), 0.25)

    def test_clamped_to_unit_range(self):
        self.assertEqual(self.fn(5.0, 2.0), 1.0)
        self.assertEqual(self.fn(-5.0, 2.0), 0.0)

    def test_zero_extent_gives_zero_not_infinity(self):
        # 没有延展的单元无法被部分遮挡，0 才是有意义的答案。
        self.assertEqual(self.fn(1.0, 0.0), 0.0)
        self.assertEqual(self.fn(0.0, 0.0), 0.0)

    def test_zero_extent_raises_no_warning(self):
        import numpy as np
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            with np.errstate(all="warn"):
                self.fn(1.0, 0.0)
        self.assertEqual(list(w), [])

    def test_non_finite_inputs_are_absorbed(self):
        import numpy as np
        self.assertEqual(self.fn(1.0, np.nan), 0.0)
        self.assertEqual(self.fn(np.inf, 2.0), 0.0)
        self.assertEqual(self.fn(np.nan, 2.0), 0.0)


@unittest.skipUnless(PYGRIDGEN.is_dir(), "meshgen 源码不在此环境中")
class DegenerateCellDetectionTest(unittest.TestCase):
    """单行 / 单列 / 重复坐标的网格确实会产生零延展单元。"""

    @classmethod
    def setUpClass(cls):
        if str(PYGRIDGEN) not in sys.path:
            sys.path.insert(0, str(PYGRIDGEN))
        try:
            import importlib
            # staticmethod：否则挂到类上会被当成实例方法，多传一个 self。
            cls.grid = staticmethod(importlib.import_module(
                "utils.compute_cellcorner").compute_cellcorner_grid)
        except ImportError as exc:  # pragma: no cover - optional deps
            raise unittest.SkipTest(f"无法导入 compute_cellcorner：{exc}")

    def _degenerate(self, lon1d, lat1d):
        import numpy as np
        lon, lat = np.meshgrid(np.asarray(lon1d, dtype=float),
                               np.asarray(lat1d, dtype=float))
        c = self.grid(lon, lat)
        return int(np.count_nonzero((c['width'] == 0) | (c['height'] == 0)))

    def test_ordinary_grid_has_none(self):
        import numpy as np
        self.assertEqual(self._degenerate(np.linspace(120, 124, 5),
                                          np.linspace(28, 32, 5)), 0)

    def test_single_column_grid_is_degenerate(self):
        import numpy as np
        self.assertGreater(self._degenerate([120.0], np.linspace(28, 32, 9)), 0)

    def test_single_row_grid_is_degenerate(self):
        import numpy as np
        self.assertGreater(self._degenerate(np.linspace(120, 124, 9), [30.0]), 0)

    def test_repeated_coordinate_is_degenerate(self):
        import numpy as np
        self.assertGreater(
            self._degenerate([120.0, 120.0, 121.0, 122.0],
                             np.linspace(28, 31, 4)), 0)

    def test_corners_stay_finite_even_when_degenerate(self):
        import numpy as np
        lon, lat = np.meshgrid(np.array([120.0]), np.linspace(28, 32, 9))
        c = self.grid(lon, lat)
        for key, arr in c.items():
            self.assertTrue(np.isfinite(arr).all(), msg=key)


if __name__ == "__main__":
    unittest.main()
