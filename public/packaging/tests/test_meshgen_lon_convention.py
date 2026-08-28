"""底图经度约定对齐测试（GEBCO 用 -180~180，ETOPO1 用 0~360）。

[EN] Longitude-convention matching between the target grid and the base
bathymetry.  Pure array logic, so no reference data is needed.
"""

import sys
import unittest
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
PYGRIDGEN = REPO_ROOT / "meshgen" / "structured_generator" / "pygridgen"
if str(PYGRIDGEN) not in sys.path:
    sys.path.insert(0, str(PYGRIDGEN))

from grid.generate_grid import _match_lon_convention  # noqa: E402

GEBCO = (-179.99791666666667, 179.99791666666667)
ETOPO1 = (0.0, 360.0)
ETOPO2 = (-180.0, 180.0)


def _row(lon0, lon1, step=0.25):
    n = int(round((lon1 - lon0) / step)) + 1
    return np.linspace(lon0, lon1, n).reshape(1, n)


class MatchLonConventionTest(unittest.TestCase):
    def test_no_base_span_leaves_grid_alone(self):
        x = _row(-10.0, 36.0)
        out, changed = _match_lon_convention(x, None)
        self.assertFalse(changed)
        self.assertIs(out, x)

    def test_negative_target_moves_onto_a_0_360_base(self):
        # This is the combination that used to raise
        # "Longitudes (-10.0,36.0) beyond range (0.0,360.0)".
        out, changed = _match_lon_convention(_row(-10.0, 36.0), ETOPO1)
        self.assertTrue(changed)
        self.assertGreaterEqual(out.min(), 0.0)
        self.assertLessEqual(out.max(), 360.0)
        self.assertIn(350.0, out)

    def test_target_past_360_wraps_onto_a_0_360_base(self):
        out, changed = _match_lon_convention(_row(350.0, 370.0), ETOPO1)
        self.assertTrue(changed)
        self.assertGreaterEqual(out.min(), 0.0)
        self.assertLessEqual(out.max(), 360.0)

    def test_in_range_target_is_untouched_on_a_0_360_base(self):
        x = _row(105.0, 140.0)
        out, changed = _match_lon_convention(x, ETOPO1)
        self.assertFalse(changed)
        self.assertIs(out, x)

    def test_dateline_target_folds_onto_a_180_base(self):
        out, changed = _match_lon_convention(_row(150.0, 210.0), GEBCO)
        self.assertTrue(changed)
        self.assertGreaterEqual(out.min(), -180.0)
        self.assertLessEqual(out.max(), 180.0)

    def test_exactly_180_keeps_its_sign(self):
        # The cut is the convention boundary, not the data extent: GEBCO's
        # last cell centre is 179.9979, but a target cell on 180.0 must stay
        # positive or the seam column shifts to the other end of the file.
        for span in (GEBCO, ETOPO2):
            out, _ = _match_lon_convention(_row(150.0, 210.0), span)
            self.assertIn(180.0, out, msg=f"base span {span}")
            self.assertNotIn(-180.0, out, msg=f"base span {span}")

    def test_target_below_minus_180_wraps_onto_a_180_base(self):
        out, changed = _match_lon_convention(_row(-190.0, -170.0), ETOPO2)
        self.assertTrue(changed)
        self.assertGreaterEqual(out.min(), -180.0)
        self.assertLessEqual(out.max(), 180.0)

    def test_in_range_target_is_untouched_on_a_180_base(self):
        x = _row(100.0, 140.0)
        out, changed = _match_lon_convention(x, ETOPO2)
        self.assertFalse(changed)
        self.assertIs(out, x)


if __name__ == "__main__":
    unittest.main()
