"""让每条 CLI 指令都能给出机器可读的结果。

给 AI 或脚本调用时，散文式输出只能靠关键词匹配来判断成败，很脆弱。这里提供
一层统一通道：``--json`` 打开后，无论哪条子命令，都在 stdout 上得到**一个**
JSON 对象——状态、退出码、产出文件、结构化数据，以及原本给人看的那些行。

各子命令不必逐个改写：默认就能拿到状态与捕获的输出；需要时再通过
``result()`` 往里补结构化字段。

[EN] One machine-readable object per CLI invocation, so an agent does not have
to parse prose to find out what happened.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import time
from typing import Any

__all__ = [
    "JsonResult",
    "result",
    "json_mode",
    "capture",
    "emit",
    "watch_outputs",
    "collect_outputs",
    "open_progress",
    "close_progress",
    "progress",
]

# 当前调用的结果对象；命令代码通过 result() 取用，不必层层传参。
_CURRENT: "JsonResult | None" = None


class JsonResult:
    """一次 CLI 调用的结构化结果。"""

    def __init__(self, command: str) -> None:
        self.command = command
        self.status = "ok"
        self.exit_code = 0
        self.data: dict[str, Any] = {}
        self.outputs: list[str] = []
        self.stages: list[dict[str, Any]] = []
        self.error: dict[str, Any] | None = None
        self.messages: list[str] = []
        self._started = time.time()

    # ── 供各子命令补充信息 ────────────────────────────────────────────
    def set(self, key: str, value: Any) -> None:
        """写入一个结构化字段。"""
        self.data[key] = value

    def update(self, **fields: Any) -> None:
        self.data.update(fields)

    def add_output(self, path: Any) -> None:
        """登记一个产出文件，供调用方直接取用而不必猜路径。"""
        text = str(path)
        if text not in self.outputs:
            self.outputs.append(text)

    def add_stage(self, name: str, seconds: float, **extra: Any) -> None:
        entry = {"name": name, "seconds": round(float(seconds), 3)}
        entry.update(extra)
        self.stages.append(entry)

    def fail(self, exit_code: int, message: str, *, kind: str = "error",
             hints: list[str] | None = None) -> None:
        """记录失败原因。*hints* 是可操作的下一步，不是解释。"""
        self.status = "error"
        self.exit_code = int(exit_code)
        self.error = {"kind": kind, "message": str(message)}
        if hints:
            self.error["hints"] = [str(h) for h in hints]

    # ── 输出 ─────────────────────────────────────────────────────────
    def to_dict(self, captured: str = "") -> dict[str, Any]:
        payload: dict[str, Any] = {
            "command": self.command,
            "status": self.status,
            "exit_code": self.exit_code,
            "seconds": round(time.time() - self._started, 3),
        }
        if self.data:
            payload["data"] = self.data
        if self.outputs:
            payload["outputs"] = self.outputs
        if self.stages:
            payload["stages"] = self.stages
        if self.error:
            payload["error"] = self.error
        lines = [ln for ln in captured.splitlines() if ln.strip()]
        if lines:
            payload["messages"] = lines
        return payload


def result() -> JsonResult | None:
    """当前调用的结果对象；非 --json 模式下为 None。"""
    return _CURRENT


def json_mode() -> bool:
    return _CURRENT is not None


@contextlib.contextmanager
def capture(command: str):
    """在 --json 模式下运行一条命令：拦下人类可读输出，最后统一成 JSON。

    命令内部的 print 不再直接落到 stdout，而是收进 ``messages``，这样
    stdout 上永远只有一个可解析的 JSON 对象。
    """
    global _CURRENT
    previous = _CURRENT
    res = JsonResult(command)
    _CURRENT = res
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            yield res
    finally:
        _CURRENT = previous
        res._captured = buffer.getvalue()  # type: ignore[attr-defined]




# ── 流式进度 ─────────────────────────────────────────────────────────
# 全球网格要跑十几分钟，期间调用方只能干等。stdout 已经被那个最终对象占住
# （必须保持可直接解析），所以进度走另一条通道，逐行 NDJSON——每行一个
# 独立对象，读到一行就能用，不必等整体结束。
_PROGRESS_SINK = None
_PROGRESS_OWNED = False
_PROGRESS_T0 = 0.0


def open_progress(dest: str) -> None:
    """打开进度通道。*dest* 为 ``stderr`` 或一个文件路径。"""
    global _PROGRESS_SINK, _PROGRESS_OWNED, _PROGRESS_T0
    close_progress()
    _PROGRESS_T0 = time.time()
    if not dest:
        return
    if dest == "stderr":
        _PROGRESS_SINK = sys.stderr
        _PROGRESS_OWNED = False
        return
    try:
        _PROGRESS_SINK = open(dest, "w", encoding="utf-8", buffering=1)
        _PROGRESS_OWNED = True
    except OSError:
        # 进度是附加信息，开不出来不该让整条命令失败。
        _PROGRESS_SINK = None
        _PROGRESS_OWNED = False


def close_progress() -> None:
    global _PROGRESS_SINK, _PROGRESS_OWNED
    if _PROGRESS_SINK is not None and _PROGRESS_OWNED:
        try:
            _PROGRESS_SINK.close()
        except OSError:
            pass
    _PROGRESS_SINK = None
    _PROGRESS_OWNED = False


def progress(event: str, **fields: Any) -> None:
    """写一条进度事件；未开启通道时什么也不做。"""
    if _PROGRESS_SINK is None:
        return
    payload = {"event": event, "elapsed": round(time.time() - _PROGRESS_T0, 3)}
    payload.update(fields)
    try:
        _PROGRESS_SINK.write(json.dumps(payload, ensure_ascii=False) + "\n")
        _PROGRESS_SINK.flush()
    except (OSError, ValueError):
        pass


# ── 产出探测 ─────────────────────────────────────────────────────────
# 逐条命令去登记「我生成了哪些文件」既繁琐又容易漏。改为在工作目录上做
# 前后快照：跑完之后新增或修改过的文件就是这次的产出。
_SNAPSHOT: dict[str, float] = {}
_WATCH_ROOT: str | None = None

# 不算作产出的东西：配置本身、日志、缓存、隐藏文件。
_IGNORED_NAMES = {"params.yml", "run.log", ".DS_Store"}
_IGNORED_DIRS = {"__pycache__", ".git", ".cache", "photo"}


def watch_outputs(root) -> None:
    """记下工作目录当前的文件状态，供结束时对比。"""
    global _SNAPSHOT, _WATCH_ROOT
    import os

    _WATCH_ROOT = str(root)
    _SNAPSHOT = {}
    for dirpath, dirnames, filenames in os.walk(_WATCH_ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in _IGNORED_DIRS and not d.startswith(".")]
        for name in filenames:
            if name in _IGNORED_NAMES or name.startswith("."):
                continue
            full = os.path.join(dirpath, name)
            try:
                _SNAPSHOT[full] = os.path.getmtime(full)
            except OSError:
                pass


def collect_outputs(res: "JsonResult") -> None:
    """把新增或改动过的文件登记为本次产出。"""
    global _WATCH_ROOT
    import os

    if _WATCH_ROOT is None:
        return
    root = _WATCH_ROOT
    _WATCH_ROOT = None
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in _IGNORED_DIRS and not d.startswith(".")]
        for name in filenames:
            if name in _IGNORED_NAMES or name.startswith("."):
                continue
            full = os.path.join(dirpath, name)
            try:
                mtime = os.path.getmtime(full)
                size = os.path.getsize(full)
            except OSError:
                continue
            if _SNAPSHOT.get(full) != mtime:
                found.append((full, size))
    for full, size in sorted(found):
        res.add_output(full)
    if found:
        res.set("output_bytes", sum(size for _, size in found))


def emit(res: JsonResult, exit_code: int) -> None:
    """把结果打到真正的 stdout。"""
    if res.status == "ok" and exit_code != 0:
        res.status = "error"
        res.exit_code = exit_code
        if res.error is None:
            res.error = {"kind": "error", "message": f"exit code {exit_code}"}
    elif res.status == "ok":
        res.exit_code = exit_code
    captured = getattr(res, "_captured", "")
    json.dump(res.to_dict(captured), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    sys.stdout.flush()
