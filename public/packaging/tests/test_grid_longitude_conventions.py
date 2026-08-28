"""经度写法（-180~180 / 0~360 / 跨日界线）在网格判定与岸线对齐上的一致性。

[EN] A domain written 0~360, or normalised past 180 by the desktop
(170~-170 becomes 170~190), must be treated as the same domain as its
-180~180 spelling.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = str(REPO_ROOT / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from workflows.domain.grid_bounds import (  # noqa: E402
    is_global_bounds,
    is_near_global_bounds,
    point_in_lon_lat_bounds,
    regional_map_extent,
)

GLOBAL_LAT_BOX = (-90.0, 90.0)


class GlobalBoundsTest(unittest.TestCase):
    def test_both_conventions_count_as_global(self):
        for lon in ((-180.0, 180.0), (0.0, 360.0), (20.0, 380.0)):
            self.assertTrue(is_global_bounds(lon, GLOBAL_LAT_BOX), msg=str(lon))

    def test_exactly_global_does_not_ask_to_snap(self):
        # 这是用户报的问题：-90~90 / 0~360 本来就是全球，不该再弹确认框。
        for lon in ((-180.0, 180.0), (0.0, 360.0)):
            self.assertFalse(is_near_global_bounds(lon, GLOBAL_LAT_BOX), msg=str(lon))

    def test_almost_global_still_asks(self):
        self.assertTrue(is_near_global_bounds((0.0, 355.0), GLOBAL_LAT_BOX))
        self.assertTrue(is_near_global_bounds((-180.0, 179.995), (-90.0, 89.9973)))

    def test_regional_is_neither(self):
        self.assertFalse(is_global_bounds((100.0, 140.0), (10.0, 40.0)))
        self.assertFalse(is_near_global_bounds((100.0, 140.0), (10.0, 40.0)))

    def test_partial_latitude_is_not_global(self):
        self.assertFalse(is_global_bounds((0.0, 360.0), (-60.0, 60.0)))


class PointInBoundsTest(unittest.TestCase):
    def test_global_0_360_accepts_every_longitude(self):
        # Normalising first would collapse 0~360 to 0~0 and reject everything.
        for lon in (-150.0, 0.0, 150.0, 359.0):
            self.assertTrue(
                point_in_lon_lat_bounds(lon, 20.0, lon_min=0.0, lon_max=360.0,
                                        lat_min=-90.0, lat_max=90.0),
                msg=str(lon))

    def test_box_past_180_accepts_both_spellings_of_a_point(self):
        for lon in (210.0, -150.0):
            self.assertTrue(
                point_in_lon_lat_bounds(lon, 50.0, lon_min=190.0, lon_max=230.0,
                                        lat_min=40.0, lat_max=60.0),
                msg=str(lon))

    def test_point_outside_is_still_rejected(self):
        self.assertFalse(
            point_in_lon_lat_bounds(100.0, 50.0, lon_min=190.0, lon_max=230.0,
                                    lat_min=40.0, lat_max=60.0))
        self.assertFalse(
            point_in_lon_lat_bounds(210.0, 10.0, lon_min=190.0, lon_max=230.0,
                                    lat_min=40.0, lat_max=60.0))


class MapExtentTest(unittest.TestCase):
    def test_box_past_180_gives_an_increasing_extent(self):
        extent = regional_map_extent((190.0, 230.0), (40.0, 60.0))["extent"]
        self.assertLess(extent[0], extent[1])
        self.assertGreaterEqual(extent[0], -180.0)
        self.assertLessEqual(extent[1], 180.0)

    def test_global_0_360_gives_the_global_extent(self):
        extent = regional_map_extent((0.0, 360.0), GLOBAL_LAT_BOX)["extent"]
        self.assertEqual(extent, [-180.0, 180.0, -90.0, 90.0])


PYGRIDGEN = REPO_ROOT / "meshgen" / "structured_generator" / "pygridgen"


@unittest.skipUnless(PYGRIDGEN.is_dir(), "meshgen 源码不在此环境中")
class BoundaryAlignmentTest(unittest.TestCase):
    """岸线多边形要落到目标网格所在的经度分支上。"""

    @classmethod
    def setUpClass(cls):
        if str(PYGRIDGEN) not in sys.path:
            sys.path.insert(0, str(PYGRIDGEN))
        try:
            import create_grid
        except ImportError as exc:  # pragma: no cover - optional deps
            raise unittest.SkipTest(f"无法导入 create_grid：{exc}")
        # staticmethod：否则挂到类上会被当成实例方法，多传一个 self。
        cls.align = staticmethod(create_grid._align_boundaries_to_grid)

    @staticmethod
    def _poly(west, east):
        import numpy as np

        return {"x": np.array([west, east, east, west], dtype=float),
                "y": np.array([0.0, 0.0, 1.0, 1.0]),
                "west": float(west), "east": float(east),
                "south": 0.0, "north": 1.0, "n": 4, "level": 1}

    def test_minus180_grid_keeps_the_originals_untouched(self):
        polys = [self._poly(-170.0, -160.0), self._poly(10.0, 20.0)]
        aligned = self.align(polys, -180.0, 180.0)
        self.assertEqual(len(aligned), 2)
        for original, kept in zip(polys, aligned):
            self.assertIs(original, kept)

    def test_0_360_grid_shifts_western_polygons(self):
        aligned = self.align([self._poly(-170.0, -160.0)], 0.0, 360.0)
        self.assertEqual(len(aligned), 1)
        self.assertAlmostEqual(aligned[0]["west"], 190.0)
        self.assertAlmostEqual(aligned[0]["east"], 200.0)
        self.assertAlmostEqual(float(aligned[0]["x"].min()), 190.0)

    def test_polygon_on_the_seam_is_kept_from_both_sides(self):
        # A polygon straddling 0 shows up at both ends of a 0~360 grid.
        aligned = self.align([self._poly(-1.0, 1.0)], 0.0, 360.0)
        self.assertEqual(len(aligned), 2)
        self.assertEqual(sorted(round(p["west"]) for p in aligned), [-1, 359])

    def test_polygon_outside_the_grid_is_dropped(self):
        self.assertEqual(self.align([self._poly(-170.0, -160.0)], 100.0, 140.0), [])

    def test_grid_past_180_recovers_polygons(self):
        # 150~210 grids used to see no coastline at all beyond 180.
        aligned = self.align([self._poly(-156.0, -155.0)], 149.75, 210.25)
        self.assertEqual(len(aligned), 1)
        self.assertAlmostEqual(aligned[0]["west"], 204.0)


if __name__ == "__main__":
    unittest.main()
