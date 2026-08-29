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
            status, msg = self.parallel.check_memory_plan(
                40_000_000, base_bytes=1 << 30, n_workers=8,
                per_worker_bytes=64 << 20)
        self.assertEqual(status, "over")
        self.assertIn("--mem", msg)
        self.assertIn("BOUNDARY", msg)

    def test_comfortable_grid_is_plain_ok(self):
        with mock.patch.object(self.parallel, "available_memory_bytes",
                               return_value=64 << 30):
            status, _ = self.parallel.check_memory_plan(
                2_560_000, base_bytes=1 << 30, n_workers=8,
                per_worker_bytes=64 << 20)
        self.assertEqual(status, "ok")

    def test_tight_grid_warns_but_is_allowed(self):
        # 关键的中间档：能起跑，但要明确告诉用户余量不足、估算不准。
        need = self.parallel.estimate_peak_bytes(
            2_560_000, base_bytes=1 << 30, n_workers=8,
            per_worker_bytes=64 << 20)
        budget = int(need / 0.75)          # 占 75%，在 60% 与拒绝线之间
        with mock.patch.object(self.parallel, "available_memory_bytes",
                               return_value=budget):
            status, msg = self.parallel.check_memory_plan(
                2_560_000, base_bytes=1 << 30, n_workers=8,
                per_worker_bytes=64 << 20)
        self.assertEqual(status, "tight")
        self.assertIn("% of the budget", msg)
        self.assertIn("--mem", msg)

    def test_unknown_budget_allows_the_run_but_says_so(self):
        # 预算读不到时宁可放行，也不要因为一个猜测挡住正常作业；但要讲明白。
        with mock.patch.object(self.parallel, "available_memory_bytes",
                               return_value=None):
            status, msg = self.parallel.check_memory_plan(40_000_000)
        self.assertEqual(status, "unknown")
        self.assertIn("could not be determined", msg)

    def test_tier_boundaries_are_ordered(self):
        # ok < tight < over，随预算收紧单调变化。
        args = dict(base_bytes=1 << 30, n_workers=4, per_worker_bytes=32 << 20)
        need = self.parallel.estimate_peak_bytes(1_000_000, **args)
        seen = []
        for share in (0.3, 0.75, 1.2):     # 占预算 30% / 75% / 120%
            with mock.patch.object(self.parallel, "available_memory_bytes",
                                   return_value=int(need / share)):
                seen.append(self.parallel.check_memory_plan(1_000_000, **args)[0])
        self.assertEqual(seen, ["ok", "tight", "over"])

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


@unittest.skipUnless(PYGRIDGEN.is_dir(), "meshgen 源码不在此环境中")
class CgroupResolutionTest(unittest.TestCase):
    """Slurm 节点通常没有命名空间，必须沿自己的 cgroup 路径找限额。"""

    @classmethod
    def setUpClass(cls):
        if str(PYGRIDGEN) not in sys.path:
            sys.path.insert(0, str(PYGRIDGEN))
        try:
            from utils import parallel
        except ImportError as exc:  # pragma: no cover - optional deps
            raise unittest.SkipTest(f"无法导入 utils.parallel：{exc}")
        cls.parallel = parallel

    @staticmethod
    def _make_tree(root, spec):
        """spec: {相对路径: (limit, usage)}；limit 为 None 表示写 'max'。"""
        import pathlib
        for rel, (limit, usage) in spec.items():
            d = pathlib.Path(root) / rel.strip("/")
            d.mkdir(parents=True, exist_ok=True)
            (d / "memory.max").write_text("max" if limit is None else str(limit))
            (d / "memory.current").write_text(str(usage))

    def test_job_limit_is_found_below_an_unlimited_root(self):
        import tempfile
        job = "/system.slice/slurmstepd.scope/job_1234/step_0"
        with tempfile.TemporaryDirectory() as root:
            self._make_tree(root, {
                "/": (None, 0),                      # 根：无限制
                "/system.slice": (None, 0),
                "/system.slice/slurmstepd.scope": (None, 0),
                "/system.slice/slurmstepd.scope/job_1234": (8 << 30, 1 << 30),
                job: (None, 0),
            })
            got = self.parallel._cgroup_limit_along(root, job,
                                                    "memory.max", "memory.current")
        self.assertEqual(got, (8 << 30) - (1 << 30))

    def test_tightest_ancestor_wins(self):
        import tempfile
        job = "/a/b/c"
        with tempfile.TemporaryDirectory() as root:
            self._make_tree(root, {
                "/": (None, 0),
                "/a": (16 << 30, 0),
                "/a/b": (4 << 30, 0),      # 最紧的一层
                "/a/b/c": (32 << 30, 0),
            })
            got = self.parallel._cgroup_limit_along(root, job,
                                                    "memory.max", "memory.current")
        self.assertEqual(got, 4 << 30)

    def test_unlimited_everywhere_gives_none(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            self._make_tree(root, {"/": (None, 0), "/a": (None, 0)})
            self.assertIsNone(
                self.parallel._cgroup_limit_along(root, "/a",
                                                  "memory.max", "memory.current"))

    def test_missing_path_gives_none(self):
        self.assertIsNone(
            self.parallel._cgroup_limit_along("/nonexistent", "/a/b",
                                              "memory.max", "memory.current"))
        self.assertIsNone(
            self.parallel._cgroup_limit_along("/tmp", None,
                                              "memory.max", "memory.current"))

    def test_proc_cgroup_v2_line_is_parsed(self):
        data = "0::/system.slice/slurmstepd.scope/job_99/step_0\n"
        with mock.patch("builtins.open", mock.mock_open(read_data=data)):
            v2, v1 = self.parallel._own_cgroup_paths()
        self.assertEqual(v2, "/system.slice/slurmstepd.scope/job_99/step_0")

    def test_proc_cgroup_v1_memory_line_is_parsed(self):
        data = ("11:cpuset:/slurm/uid_1000/job_99\n"
                "6:memory:/slurm/uid_1000/job_99/step_0\n"
                "3:cpu,cpuacct:/slurm/uid_1000/job_99\n")
        with mock.patch("builtins.open", mock.mock_open(read_data=data)):
            v2, v1 = self.parallel._own_cgroup_paths()
        self.assertIsNone(v2)
        self.assertEqual(v1, "/slurm/uid_1000/job_99/step_0")

    def test_unreadable_proc_cgroup_is_tolerated(self):
        with mock.patch("builtins.open", side_effect=OSError):
            self.assertEqual(self.parallel._own_cgroup_paths(), (None, None))


@unittest.skipUnless(PYGRIDGEN.is_dir(), "meshgen 源码不在此环境中")
class MemoryWatchdogTest(unittest.TestCase):
    """看门狗看的是运行时的真实占用，不依赖任何估算模型。"""

    @classmethod
    def setUpClass(cls):
        if str(PYGRIDGEN) not in sys.path:
            sys.path.insert(0, str(PYGRIDGEN))
        try:
            from utils import parallel
        except ImportError as exc:  # pragma: no cover - optional deps
            raise unittest.SkipTest(f"无法导入 utils.parallel：{exc}")
        cls.parallel = parallel

    def test_no_limit_gives_a_noop(self):
        with mock.patch.object(self.parallel, "_cgroup_current_and_max",
                               return_value=(None, None)), \
             mock.patch.object(self.parallel, "available_memory_bytes",
                               return_value=None):
            stop = self.parallel.start_memory_watchdog()
        self.assertTrue(callable(stop))
        stop()

    def test_cgroup_reading_is_preferred_over_the_budget(self):
        # cgroup 覆盖 worker 进程，是 Slurm 上 OOM killer 真正看的数。
        with mock.patch.object(self.parallel, "_cgroup_current_and_max",
                               return_value=(1 << 30, 8 << 30)) as cg, \
             mock.patch.object(self.parallel, "available_memory_bytes") as budget:
            stop = self.parallel.start_memory_watchdog(interval=60)
            stop()
        self.assertTrue(cg.called)
        budget.assert_not_called()

    def test_trip_fraction_is_clamped_to_a_sane_range(self):
        for raw, lo, hi in (("0.01", 0.5, 0.5), ("5", 0.99, 0.99), ("junk", 0.9, 0.9)):
            with mock.patch.dict(os.environ,
                                 {"WW3TOOL_MESHGEN_MEM_ABORT_FRACTION": raw}), \
                 mock.patch.object(self.parallel, "_cgroup_current_and_max",
                                   return_value=(None, None)), \
                 mock.patch.object(self.parallel, "available_memory_bytes",
                                   return_value=1 << 30):
                stop = self.parallel.start_memory_watchdog(interval=60)
                stop()
        # 只要不抛异常即可：范围钳制在内部完成。

    def test_tree_rss_is_at_least_own_rss(self):
        own = self.parallel._self_rss_bytes()
        if own is None:
            self.skipTest("平台不支持 getrusage")
        self.assertGreaterEqual(self.parallel._tree_rss_bytes(), own)


@unittest.skipUnless(PYGRIDGEN.is_dir(), "meshgen 源码不在此环境中")
class PointlessMaskingTest(unittest.TestCase):
    """声明了 fill/valid 的变量保持默认；没声明的不该白白多占一字节/点。"""

    @classmethod
    def setUpClass(cls):
        if str(PYGRIDGEN) not in sys.path:
            sys.path.insert(0, str(PYGRIDGEN))
        try:
            import importlib
            cls.gg = importlib.import_module("grid.generate_grid")
        except ImportError as exc:  # pragma: no cover - optional deps
            raise unittest.SkipTest(f"无法导入 grid.generate_grid：{exc}")

    class _Var:
        def __init__(self, attrs):
            self._attrs = list(attrs)
            self.masked = True

        def ncattrs(self):
            return self._attrs

        def set_auto_mask(self, flag):
            self.masked = flag

    def test_variable_without_fill_is_read_unmasked(self):
        # GEBCO 就是这种：没有 _FillValue，掩码全 False，纯浪费。
        var = self._Var(["units", "long_name", "standard_name"])
        self.assertTrue(self.gg._disable_pointless_masking(var))
        self.assertFalse(var.masked)

    def test_declared_fill_value_keeps_masking(self):
        for attr in ("_FillValue", "missing_value", "valid_min",
                     "valid_max", "valid_range"):
            var = self._Var(["units", attr])
            self.assertFalse(self.gg._disable_pointless_masking(var), msg=attr)
            self.assertTrue(var.masked, msg=attr)

    def test_object_without_ncattrs_is_left_alone(self):
        self.assertFalse(self.gg._disable_pointless_masking(object()))
