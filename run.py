#!/usr/bin/env python3
import os
import runpy
import subprocess
import sys


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def _in_venv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def _ensure_linux_venv(root: str) -> None:
    """Create/enter venv on Linux, then install requirements once."""
    if not _is_linux() or _in_venv():
        return

    venv_dir = os.path.join(root, "venv")
    venv_python = os.path.join(venv_dir, "bin", "python")
    if not os.path.isfile(venv_python):
        subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)

    # Re-exec inside venv to emulate "source venv/bin/activate"
    env = os.environ.copy()
    env["WW3TOOL_IN_VENV"] = "1"
    os.execvpe(venv_python, [venv_python, __file__], env)


def _install_requirements_if_needed(root: str) -> None:
    req_file = os.path.join(root, "src", "requirements.txt")
    if not os.path.isfile(req_file):
        return
    marker = os.path.join(root, ".venv_ready")
    if os.path.isfile(marker) and os.path.getmtime(marker) >= os.path.getmtime(req_file):
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_file], check=True)
    with open(marker, "w", encoding="utf-8") as f:
        f.write("ok\n")


def _repo_root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def main() -> None:
    root = _repo_root()
    _ensure_linux_venv(root)
    _install_requirements_if_needed(root)
    src_dir = os.path.join(root, "src")
    main_py = os.path.join(src_dir, "main.py")
    if not os.path.isfile(main_py):
        raise SystemExit(f"main.py not found: {main_py}")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    os.chdir(src_dir)
    runpy.run_path(main_py, run_name="__main__")


if __name__ == "__main__":
    main()
