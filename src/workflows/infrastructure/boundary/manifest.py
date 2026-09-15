"""指纹、原子写入、文件归属与执行锁。"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

from ...domain.boundary_models import BOUNDARY_SCHEMA_VERSION, utc_now_iso
from .errors import BoundaryError
from ...support.translations import tr

LOCK_NAME = ".boundary.lock"
MANAGED_KIND_NEST = "nest.ww3"


def sha256_file(path: Path, *, max_bytes: int | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        remaining = max_bytes
        while True:
            chunk = handle.read(1024 * 1024 if remaining is None else min(1024 * 1024, remaining))
            if not chunk:
                break
            digest.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
                if remaining <= 0:
                    break
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def atomic_replace(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(src, dest)


def fingerprint_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256_text(encoded)


class WorkdirLock:
    """跨节点算例锁：O_EXCL 锁文件 + 作业 UUID，禁止用裸 PID 当身份。

    同一作业的后续阶段必须传入相同 ``owner`` token。未指定时每个实例独立 UUID，不得重入。
    ``owner_pid`` 只写入诊断字段，不参与互斥与释放。
    """

    def __init__(self, workdir: Path, *, owner: str | None = None, owner_pid: int | None = None) -> None:
        self.path = Path(workdir) / "boundary" / LOCK_NAME
        token = str(owner).strip() if owner is not None else ""
        self.owner = token or uuid.uuid4().hex
        self._pid_hint = int(owner_pid) if owner_pid is not None else os.getpid()
        self._depth = 0
        self._keep_file = False

    def _read_payload(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        except Exception:
            return {}
        return raw if isinstance(raw, dict) else {}

    def _read_owner(self) -> str | None:
        owner = self._read_payload().get("owner")
        return str(owner) if owner else None

    def acquire(self) -> None:
        if self._depth > 0:
            self._depth += 1
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "owner": self.owner,
            "pid": self._pid_hint,
            "hostname": socket.gethostname(),
            "time": utc_now_iso(),
        }
        encoded = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            if self._read_owner() == self.owner:
                self._depth = 1
                self._keep_file = False
                return
            raise BoundaryError(
                "BOUNDARY_WORKDIR_BUSY",
                tr("boundary_workdir_busy", "同一算例已在准备或运行边界"),
                context={"lock": str(self.path), "stale": self._stale_info()},
                hints=[tr("boundary_hint_workdir_busy", "等待任务结束，或确认作业已退出后删除 boundary/.boundary.lock")],
            )
        try:
            os.write(fd, encoded)
            os.fsync(fd)
        finally:
            os.close(fd)
        self._depth = 1
        self._keep_file = False

    def _stale_info(self) -> dict[str, Any]:
        raw = self._read_payload()
        raw["lock_exists"] = self.path.is_file()
        return raw

    def release(self) -> None:
        if self._depth > 1:
            self._depth -= 1
            return
        keep = self._keep_file
        self._keep_file = False
        self._depth = 0
        if keep:
            return
        self._unlink_if_owner()

    def drop_local(self) -> None:
        """结束本进程持有计数，但保留锁文件给同一 owner 的后续阶段。"""
        if self._depth > 1:
            self._depth -= 1
            return
        self._depth = 0
        self._keep_file = False

    def _unlink_if_owner(self) -> None:
        if self._read_owner() != self.owner:
            return
        try:
            self.path.unlink()
        except OSError:
            pass

    def __enter__(self) -> "WorkdirLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


def load_manifest(workdir: Path) -> dict[str, Any]:
    path = Path(workdir) / "boundary" / "manifest.json"
    if not path.is_file():
        return {"schema_version": BOUNDARY_SCHEMA_VERSION, "files": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"schema_version": BOUNDARY_SCHEMA_VERSION, "files": []}


def save_manifest(workdir: Path, manifest: dict[str, Any]) -> None:
    manifest["schema_version"] = BOUNDARY_SCHEMA_VERSION
    atomic_write_json(Path(workdir) / "boundary" / "manifest.json", manifest)


def record_managed_file(
    manifest: dict[str, Any],
    *,
    relpath: str,
    kind: str,
    sha256: str,
    run_id: str,
) -> None:
    files = [item for item in manifest.get("files") or [] if item.get("relpath") != relpath]
    files.append(
        {
            "relpath": relpath,
            "kind": kind,
            "sha256": sha256,
            "run_id": run_id,
            "recorded_at": utc_now_iso(),
        }
    )
    manifest["files"] = files


def managed_entry(manifest: dict[str, Any], relpath: str) -> dict[str, Any] | None:
    for item in manifest.get("files") or []:
        if item.get("relpath") == relpath:
            return item
    return None


def inspect_unmanaged_nest(workdir: Path) -> None:
    """mode=none 也必须检查根目录 nest.ww3。"""
    nest = Path(workdir) / "nest.ww3"
    if not nest.is_file():
        return
    manifest = load_manifest(workdir)
    entry = managed_entry(manifest, "nest.ww3")
    digest = sha256_file(nest)
    if entry and entry.get("sha256") == digest:
        return
    raise BoundaryError(
        "BOUNDARY_UNMANAGED_FILE",
        tr("boundary_unmanaged_nest", "工作目录存在无归属或校验不符的 nest.ww3，积分前必须由用户检查"),
        context={"path": str(nest), "recorded": entry},
        hints=[tr("boundary_hint_unmanaged_nest", "移走或确认该文件后重试；工具不会覆盖未知 nest.ww3")],
    )


def archive_managed_nest(workdir: Path) -> str | None:
    nest = Path(workdir) / "nest.ww3"
    if not nest.is_file():
        return None
    manifest = load_manifest(workdir)
    entry = managed_entry(manifest, "nest.ww3")
    digest = sha256_file(nest)
    if not entry or entry.get("sha256") != digest:
        inspect_unmanaged_nest(workdir)
        return None
    archive = Path(workdir) / "boundary" / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    dest = archive / f"nest.{entry.get('run_id', 'unknown')}.{int(time.time())}.ww3"
    shutil.move(str(nest), str(dest))
    files = [item for item in manifest.get("files") or [] if item.get("relpath") != "nest.ww3"]
    manifest["files"] = files
    save_manifest(workdir, manifest)
    return str(dest)


def file_digest_record(path: Path) -> dict[str, Any]:
    st = path.stat()
    return {
        "path": str(path),
        "size": int(st.st_size),
        "mtime_ns": int(st.st_mtime_ns),
        "sha256": sha256_file(path),
    }
