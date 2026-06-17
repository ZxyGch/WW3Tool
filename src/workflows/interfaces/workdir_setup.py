"""Shared workdir creation and validation for shell and headless CLI."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from ..support.translations import tr


class WorkdirError(Exception):
    """Raised when a workdir path cannot be created or loaded."""


def repo_root_path() -> Path:
    """Return the WW3Tool repository root directory."""
    return Path(__file__).resolve().parents[3]


def ensure_workdir(path: str) -> tuple[Path, bool]:
    """Create *path* from the root template, or verify an existing workdir.

    Returns:
        ``(workdir, created)`` where *created* is ``True`` when a new directory
        was created and ``params.yml`` was copied from the template.
    """
    workdir = Path(path).expanduser().resolve()
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

    workdir.mkdir(parents=True)
    shutil.copy2(str(root_params), str(params_yml))
    content = params_yml.read_text(encoding="utf-8")
    content = re.sub(
        r"(^workdir:\s*\n  path:\s*).*",
        rf"\g<1>{workdir}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    params_yml.write_text(content, encoding="utf-8")
    return workdir, True
