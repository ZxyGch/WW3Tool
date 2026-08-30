"""长任务的流式进度。

全球网格要跑十几分钟，调用方此前只能干等到结束。stdout 已经被最终那个 JSON
对象占住（必须保持可直接解析），所以进度另走一条逐行 NDJSON 的通道——读到
一行就能用，不必等整体完成。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src"
RUN_PY = REPO_ROOT / "run.py"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from workflows.interfaces import json_output as jo  # noqa: E402


class ProgressSinkTest(unittest.TestCase):
    def tearDown(self):
        jo.close_progress()

    def test_events_are_one_json_object_per_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.ndjson"
            jo.open_progress(str(path))
            jo.progress("start", command="x")
            jo.progress("stage", stage="Step 1", index=1)
            jo.close_progress()
            lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        for line in lines:
            json.loads(line)          # 每行独立可解析

    def test_every_event_carries_elapsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.ndjson"
            jo.open_progress(str(path))
            jo.progress("start")
            jo.close_progress()
            event = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        self.assertIn("elapsed", event)

    def test_writing_without_a_sink_is_a_no_op(self):
        jo.close_progress()
        jo.progress("stage", stage="Step 1")     # 不应抛异常

    def test_unwritable_destination_is_tolerated(self):
        # 进度是附加信息，开不出来不该让整条命令失败。
        jo.open_progress("/nonexistent/dir/p.ndjson")
        jo.progress("start")
        jo.close_progress()

    def test_empty_destination_disables_it(self):
        jo.open_progress("")
        jo.progress("start")
        jo.close_progress()


@unittest.skipUnless(RUN_PY.is_file(), "需要仓库形态")
class ProgressChannelSeparationTest(unittest.TestCase):
    """进度和最终结果必须分居两条流，否则 stdout 就没法直接解析了。"""

    def _run(self, *argv):
        return subprocess.run([sys.executable, str(RUN_PY), *argv],
                              capture_output=True, text=True, cwd=str(REPO_ROOT))

    def test_stdout_stays_parseable_with_progress_on_stderr(self):
        out = self._run("--json", "--progress", "stderr", "schema")
        payload = json.loads(out.stdout)      # 不该被进度污染
        self.assertEqual(payload["status"], "ok")

    def test_progress_events_land_on_stderr(self):
        out = self._run("--json", "--progress", "stderr", "schema")
        events = [json.loads(l) for l in out.stderr.splitlines()
                  if l.startswith("{")]
        kinds = {e["event"] for e in events}
        self.assertIn("start", kinds)
        self.assertIn("done", kinds)

    def test_done_event_reports_the_outcome(self):
        out = self._run("--json", "--progress", "stderr", "schema")
        done = [json.loads(l) for l in out.stderr.splitlines()
                if l.startswith("{") and '"done"' in l][0]
        self.assertEqual(done["status"], "ok")
        self.assertEqual(done["exit_code"], 0)

    def test_progress_works_without_json_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.ndjson"
            out = self._run("--progress", str(path), "print-example")
            self.assertTrue(path.is_file())
            self.assertTrue(path.read_text(encoding="utf-8").strip())
        # 人类可读输出不受影响
        self.assertIn("workdir", out.stdout)

    def test_no_progress_flag_means_no_events(self):
        out = self._run("--json", "schema")
        self.assertNotIn('"event"', out.stderr)


class StageLineParsingTest(unittest.TestCase):
    """阶段行只在生成器的日志里出现，抽取要在一处完成。"""

    def setUp(self):
        from workflows.interfaces.command_line import _STAGE_LINE
        self.pat = _STAGE_LINE

    def test_matches_a_generator_stage_line(self):
        m = self.pat.match("Step 6: Splitting large boundary polygons...")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "Step 6")
        self.assertEqual(m.group(2), "6")
        self.assertEqual(m.group(3).strip(), "Splitting large boundary polygons")

    def test_matches_full_width_colon(self):
        self.assertIsNotNone(self.pat.match("Step 3：生成地形"))

    def test_ignores_ordinary_log_lines(self):
        for line in ("  Done.", "Completed 50 per cent", "Total time: 12s"):
            self.assertIsNone(self.pat.match(line), line)


if __name__ == "__main__":
    unittest.main()
