#!/usr/bin/env python3
"""Launch the desktop application implemented in src."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ENTRY_SCRIPT = Path(__file__).resolve()


def _bootstrap_src_imports() -> None:
    root = ENTRY_SCRIPT.parent
    for path in (root / "src",):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


def main(argv: list[str] | None = None) -> int:
    _bootstrap_src_imports()
    from venv_and_deps import ensure_runtime

    arguments = sys.argv[1:] if argv is None else argv
    try:
        ensure_runtime(entry_script=ENTRY_SCRIPT, argv=arguments)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"依赖初始化失败：{exc}", file=sys.stderr)
        return 1

    from desktop.application import main as run_desktop

    return run_desktop(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
