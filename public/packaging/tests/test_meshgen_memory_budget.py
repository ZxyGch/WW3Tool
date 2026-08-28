"""网格生成的内存预算：worker 数要服从内存，而不是服从核数。

[EN] The mesh generator sizes its worker pool from the memory budget, so a
many-core node cannot turn "more cores" into "out of memory".
"""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
PYGRIDGEN = REPO_ROOT / "meshgen" / "structured_generator" / "pygridgen"


@unittest.skipUnless(PYGRIDGEN.is_dir(), "meshgen 源码不在此环境中")
class MemoryBudgetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if str(PYGRIDGEN) not in sys.path:
            sys.path.insert(0, str(PYGRIDGEN))
        try:
            from utils import parallel
        except ImportError as exc:  # pragma: no cover - optional deps
            raise unittest.SkipTest(f"无法导入 utils.parallel：{exc}")
        cls.parallel = parallel

    # ── 预算来源 ────────────────────────────────────────────────
    def test_env_override_wins(self):
        with mock.patch.dict(os.environ, {"WW3TOOL_MESHGEN_MEM_MB": "2048"}):
            self.assertEqual(self.parallel.available_memory_bytes(), 2048 * (1 << 20))

    def test_slurm_mem_per_node_is_read(self):
        env = {"SLURM_MEM_PER_NODE": "4096"}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("WW3TOOL_MESHGEN_MEM_MB", None)
            with mock.patch.object(self.parallel, "_cgroup_memory_limit", return_value=None):
                self.assertEqual(self.parallel.available_memory_bytes(), 4096 * (1 << 20))

    def test_cgroup_limit_wins_over_slurm(self):
        # cgroup 是真正触发 OOM killer 的那个数，必须优先。
        env = {"SLURM_MEM_PER_NODE": "100000"}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("WW3TOOL_MESHGEN_MEM_MB", None)
            with mock.patch.object(self.parallel, "_cgroup_memory_limit",
                                   return_value=1 << 30):
                self.assertEqual(self.parallel.available_memory_bytes(), 1 << 30)

    def test_unlimited_cgroup_sentinels_are_ignored(self):
        for raw in ("max", "-1", str(1 << 63)):
            with mock.patch("builtins.open", mock.mock_open(read_data=raw)):
                self.assertIsNone(self.parallel._read_int_file("/fake"))

    # ── worker 限流 ─────────────────────────────────────────────
    def test_pool_is_narrowed_to_fit(self):
        with mock.patch.object(self.parallel, "available_memory_bytes",
                               return_value=4 << 30):
            # 预算 4 GiB，一半给池子 = 2 GiB；每 worker 512 MiB → 4 个。
            self.assertEqual(
                self.parallel.cap_workers_for_memory(16, 512 << 20), 4)

    def test_pool_is_left_alone_when_it_fits(self):
        with mock.patch.object(self.parallel, "available_memory_bytes",
                               return_value=64 << 30):
            self.assertEqual(self.parallel.cap_workers_for_memory(8, 256 << 20), 8)

    def test_never_drops_below_one_worker(self):
        with mock.patch.object(self.parallel, "available_memory_bytes",
                               return_value=1 << 20):
            self.assertEqual(self.parallel.cap_workers_for_memory(8, 8 << 30), 1)

    def test_unknown_budget_does_not_narrow(self):
        with mock.patch.object(self.parallel, "available_memory_bytes",
                               return_value=None):
            self.assertEqual(self.parallel.cap_workers_for_memory(8, 8 << 30), 8)

    # ── 开跑前的可行性判断 ──────────────────────────────────────
    def test_oversized_grid_is_refused_with_advice(self):
        with mock.patch.object(self.parallel, "available_memory_bytes",
                               return_value=2 << 30):
            fits, msg = self.parallel.check_memory_plan(
                40_000_000, base_bytes=1 << 30, n_workers=8,
                per_worker_bytes=64 << 20)
        self.assertFalse(fits)
        self.assertIn("--mem", msg)
        self.assertIn("BOUNDARY", msg)

    def test_reasonable_grid_is_allowed(self):
        with mock.patch.object(self.parallel, "available_memory_bytes",
                               return_value=64 << 30):
            fits, _ = self.parallel.check_memory_plan(
                2_560_000, base_bytes=1 << 30, n_workers=8,
                per_worker_bytes=64 << 20)
        self.assertTrue(fits)

    def test_unknown_budget_allows_the_run(self):
        # 预算读不到时宁可放行，也不要因为一个猜测挡住正常作业。
        with mock.patch.object(self.parallel, "available_memory_bytes",
                               return_value=None):
            fits, msg = self.parallel.check_memory_plan(40_000_000)
        self.assertTrue(fits)
        self.assertIn("unknown", msg)

    def test_estimate_grows_with_cells_and_workers(self):
        base = dict(base_bytes=1 << 30, per_worker_bytes=64 << 20)
        small = self.parallel.estimate_peak_bytes(1_000_000, n_workers=1, **base)
        big = self.parallel.estimate_peak_bytes(10_000_000, n_workers=1, **base)
        wide = self.parallel.estimate_peak_bytes(1_000_000, n_workers=8, **base)
        self.assertGreater(big, small)
        self.assertGreater(wide, small)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(PYGRIDGEN.is_dir(), "meshgen 源码不在此环境中")
class SummedAreaCeilingTest(unittest.TestCase):
    """积分图必须先按形状判负担得起，再分配——否则检查形同虚设。"""

    @classmethod
    def setUpClass(cls):
        if str(PYGRIDGEN) not in sys.path:
            sys.path.insert(0, str(PYGRIDGEN))
        try:
            import importlib
            cls.gg = importlib.import_module("grid.generate_grid")
        except ImportError as exc:  # pragma: no cover - optional deps
            raise unittest.SkipTest(f"无法导入 grid.generate_grid：{exc}")

    def setUp(self):
        os.environ.pop("WW3TOOL_SAT_MAX_MB", None)

    def test_global_gebco_shape_is_refused(self):
        # 43200x86400 的积分图要上百 GiB，必须拒绝。
        self.assertFalse(self.gg._sat_is_affordable((43200, 86400)))

    def test_global_etopo1_shape_is_refused(self):
        # 实测这个形状的表要 ~6.8 GiB，换来 1.8 倍提速——不划算。
        self.assertFalse(self.gg._sat_is_affordable((9602, 21602)))

    def test_small_window_is_allowed(self):
        self.assertTrue(self.gg._sat_is_affordable((2000, 3000)))

    def test_absolute_ceiling_holds_even_on_a_huge_budget(self):
        with mock.patch("utils.parallel.available_memory_bytes",
                        return_value=1024 * (1 << 30)):
            self.assertFalse(self.gg._sat_is_affordable((9602, 21602)))

    def test_degenerate_shapes_are_refused(self):
        for shape in ((0, 10), (10, 0), (10,), (1, 2, 3)):
            self.assertFalse(self.gg._sat_is_affordable(shape))

    def test_env_override_is_honoured(self):
        os.environ["WW3TOOL_SAT_MAX_MB"] = "0"
        try:
            self.assertFalse(self.gg._sat_is_affordable((100, 100)))
        finally:
            os.environ.pop("WW3TOOL_SAT_MAX_MB", None)
