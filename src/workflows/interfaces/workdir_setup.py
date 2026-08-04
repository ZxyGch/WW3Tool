"""Shared workdir creation and validation for shell and headless CLI."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from ..support.translations import tr


class WorkdirError(Exception):
    """Raised when a workdir path cannot be created or loaded."""


def repo_root_path() -> Path:
    """Return the WW3Tool repository root directory.

    ``WW3TOOL_ROOT`` env wins (packaged installs); otherwise inferred from
    the repository layout.
    """
    env_root = os.environ.get("WW3TOOL_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def ensure_workdir(path: str) -> tuple[Path, bool]:
    """Create *path* from the root template, or verify an existing workdir.

    When *path* is a bare directory name (no path separators), it is resolved
    relative to the default workspace parent (``workSpace/``) rather than the
    current working directory, keeping behaviour consistent with the Desktop GUI.

    Returns:
        ``(workdir, created)`` where *created* is ``True`` when a new directory
        was created and ``params.yml`` was copied from the template.
    """
    expanded = Path(path).expanduser()

    # Bare name (no separators) → place under default workspace parent
    if expanded.name == path.strip() and "/" not in path and "\\" not in path:
        try:
            from ..infrastructure.runtime_config import get_default_workdir
            default_base = get_default_workdir(create_if_not_exists=True)
            if default_base:
                workdir = (Path(default_base) / path.strip()).resolve()
            else:
                workdir = expanded.resolve()
        except Exception:
            workdir = expanded.resolve()
    else:
        workdir = expanded.resolve()
    params_yml = workdir / "params.yml"

    if workdir.exists():
        if not params_yml.is_file():
            raise WorkdirError(
                tr("icli_workdir_no_params", "❌ 目录已存在但缺少 params.yml：{}").format(workdir)
            )
        return workdir, False

    root_params = repo_root_path() / "params.yml"
    if not root_params.is_file():
        raise WorkdirError(tr("icli_no_template", "❌ 仓库根目录没有 params.yml 模板文件"))

    try:
        workdir.mkdir(parents=True)
    except OSError as exc:
        raise WorkdirError(
            tr("icli_workdir_mkdir_failed", "❌ 无法创建工作目录：{path}（{error}）").format(
                path=workdir, error=exc
            )
        )
    # [EN] Use copyfile instead of copy2 to avoid [Errno 22] on external disks
    # (exFAT/NTFS/FAT32 may not support metadata/extended-attribute copying).
    shutil.copyfile(str(root_params), str(params_yml))
    content = params_yml.read_text(encoding="utf-8")
    content = re.sub(
        r"(^workdir:\s*\n  path:\s*).*",
        r"\g<1>" + str(workdir).replace("\\", "\\\\"),
        content,
        count=1,
        flags=re.MULTILINE,
    )
    params_yml.write_text(content, encoding="utf-8")
    return workdir, True
