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

from grid.generate_grid import (  # noqa: E402
    _lon_axis_periodicity,
    _match_lon_convention,
    _wrap_into_axis,
)

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


class LonAxisPeriodicityTest(unittest.TestCase):
    """接缝识别：全球轴分像元中心式和节点式两种。"""

    def test_pixel_centred_global_axis(self):
        # GEBCO: one cell of gap across the seam, no repeated meridian.
        lon = np.linspace(GEBCO[0], GEBCO[1], 86400)
        periodic, duplicate = _lon_axis_periodicity(lon, 359.99583333333334 / 86399)
        self.assertTrue(periodic)
        self.assertFalse(duplicate)

    def test_node_registered_global_axes(self):
        # ETOPO1 / ETOPO2: the meridian appears at both ends.
        for lon, dx in ((np.linspace(0.0, 360.0, 21601), 360.0 / 21600),
                        (np.linspace(-180.0, 180.0, 10801), 360.0 / 10800)):
            periodic, duplicate = _lon_axis_periodicity(lon, dx)
            self.assertTrue(periodic)
            self.assertTrue(duplicate)

    def test_regional_axis_is_not_periodic(self):
        lon = np.linspace(118.0, 126.0, 481)
        periodic, duplicate = _lon_axis_periodicity(lon, 360.0 / 21600)
        self.assertFalse(periodic)
        self.assertFalse(duplicate)

    def test_too_short_axis_is_not_periodic(self):
        self.assertEqual(_lon_axis_periodicity(np.array([0.0, 1.0]), 0.5), (False, False))
        self.assertEqual(_lon_axis_periodicity(np.linspace(0, 360, 5), 0.0), (False, False))


class WrapIntoAxisTest(unittest.TestCase):
    """越过接缝的格子框整圈折回，框内的值一位不动。"""

    def setUp(self):
        self.lon = np.linspace(GEBCO[0], GEBCO[1], 8641)

    def test_values_inside_are_bit_identical(self):
        v = np.array([-179.0, -0.5, 0.0, 120.25, 179.9])
        np.testing.assert_array_equal(_wrap_into_axis(v, self.lon), v)

    def test_value_past_the_east_end_folds_west(self):
        out = _wrap_into_axis(np.array([180.125]), self.lon)
        self.assertAlmostEqual(float(out[0]), -179.875)

    def test_value_before_the_west_end_folds_east(self):
        out = _wrap_into_axis(np.array([-180.125]), self.lon)
        self.assertAlmostEqual(float(out[0]), 179.875)

    def test_straddling_box_inverts_start_and_end(self):
        # A cell centred on the seam: after folding, the box start sorts
        # above its end, which is how the readers recognise a wrap.
        lo = _wrap_into_axis(np.array([179.875]), self.lon)[0]
        hi = _wrap_into_axis(np.array([180.125]), self.lon)[0]
        self.assertGreater(lo, hi)


if __name__ == "__main__":
    unittest.main()
