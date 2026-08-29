"""split_boundary 逐子块调用 compute_boundary 时不应刷屏。

[EN] split_boundary calls compute_boundary once per one-degree sub-tile of
every large polygon.  Left chatty, that is thousands of lines per run, each
claiming that "clipping may take minutes" for a tile that takes milliseconds.
"""

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PYGRIDGEN = REPO_ROOT / "meshgen" / "structured_generator" / "pygridgen"


@unittest.skipUnless(PYGRIDGEN.is_dir(), "meshgen 源码不在此环境中")
class ComputeBoundaryQuietTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if str(PYGRIDGEN) not in sys.path:
            sys.path.insert(0, str(PYGRIDGEN))
        try:
            import importlib
            # staticmethod：否则挂到类上会被当成实例方法，多传一个 self。
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

    def _run(self, **kw):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.cb([0.0, 0.0, 2.0, 2.0], [self._square(0.5, 1.5, 0.5, 1.5)],
                    20, 1, **kw)
        return buf.getvalue()

    def test_default_reports_progress(self):
        self.assertIn("compute_boundary:", self._run())

    def test_quiet_prints_nothing(self):
        self.assertEqual(self._run(quiet=True).strip(), "")

    def test_quiet_does_not_change_the_result(self):
        poly = [self._square(0.5, 1.5, 0.5, 1.5)]
        coord = [0.0, 0.0, 2.0, 2.0]
        with redirect_stdout(io.StringIO()):
            loud, n_loud = self.cb(coord, poly, 20, 1)
            quiet, n_quiet = self.cb(coord, poly, 20, 1, quiet=True)
        self.assertEqual(n_loud, n_quiet)
        self.assertEqual(len(loud), len(quiet))

    def test_split_boundary_calls_it_quietly(self):
        src = (PYGRIDGEN / "grid" / "split_boundary.py").read_text(encoding="utf-8")
        self.assertIn("quiet=True", src)


if __name__ == "__main__":
    unittest.main()
