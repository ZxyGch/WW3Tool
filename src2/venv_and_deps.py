"""runCLI / runDesktop 共用：创建项目虚拟环境并安装 Python 依赖。"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import sysconfig
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_FILE = ROOT / "src2" / "requirements.txt"
VENV_DIR = ROOT / ".venv"

_CHECK_SCRIPT = """\
import importlib.util
import json
import sys

missing = []
for name, module in json.loads(sys.argv[1]).items():
    try:
        ok = importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        ok = False
    if not ok:
        missing.append(name)
print(json.dumps(missing))
"""


def venv_python_path() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def running_in_project_venv() -> bool:
    try:
        return Path(sys.prefix).resolve() == VENV_DIR.resolve()
    except OSError:
        return False


def is_externally_managed_environment() -> bool:
    marker = Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED"
    return marker.is_file()


def missing_requirements() -> list[str]:
    return _missing_requirements_for_modules(REQUIRED_IMPORTS)


def missing_requirements_for_python(python: Path) -> list[str]:
    proc = subprocess.run(
        [str(python), "-c", _CHECK_SCRIPT, json.dumps(REQUIRED_IMPORTS)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"无法检测依赖：{python}")
    return json.loads(proc.stdout.strip() or "[]")


def ensure_project_venv() -> Path:
    venv_python = venv_python_path()
    if venv_python.is_file():
        return venv_python
    print(f"正在创建项目虚拟环境：{VENV_DIR}")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    if not venv_python.is_file():
        raise RuntimeError(f"虚拟环境创建失败：{venv_python}")
    return venv_python


def _resolve_install_python() -> Path:
    if running_in_project_venv():
        return Path(sys.executable)
    if is_externally_managed_environment():
        return ensure_project_venv()
    if venv_python_path().is_file():
        return venv_python_path()
    return Path(sys.executable)


def _pip_install(python: Path) -> None:
    subprocess.run(
        [str(python), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)],
        check=True,
    )


def ensure_dependencies(*, quiet: bool = False) -> Path | None:
    """Install missing dependencies. Returns venv python when caller must re-exec."""
    missing = missing_requirements()
    if not missing:
        if not quiet:
            print("依赖检查通过。")
        return None

    if not REQUIREMENTS_FILE.is_file():
        raise RuntimeError(f"依赖文件不存在：{REQUIREMENTS_FILE}")

    print("缺少依赖，正在自动安装：" + ", ".join(missing))
    install_python = _resolve_install_python()
    try:
        _pip_install(install_python)
    except subprocess.CalledProcessError:
        if _different_executable_path(install_python, Path(sys.executable)):
            raise
        install_python = ensure_project_venv()
        _pip_install(install_python)

    if _different_executable_path(install_python, Path(sys.executable)):
        return install_python

    remaining = missing_requirements()
    if remaining:
        raise RuntimeError("依赖安装完成后仍无法导入：" + ", ".join(remaining))
    print("依赖安装完成。")
    return None


def ensure_runtime(*, entry_script: Path, argv: list[str] | None = None) -> None:
    """Ensure dependencies and re-exec into the project venv when needed."""
    argv = list(argv or [])
    venv_python = venv_python_path()

    if venv_python.is_file() and not running_in_project_venv():
        print(f"使用项目虚拟环境：{VENV_DIR}")
        _reexec(venv_python, entry_script, argv)

    reexec_python = ensure_dependencies()
    if reexec_python is not None:
        print(f"已切换到项目虚拟环境：{VENV_DIR}")
        _reexec(reexec_python, entry_script, argv)

    if missing_requirements():
        raise RuntimeError("依赖安装完成后仍无法导入：" + ", ".join(missing_requirements()))


REQUIRED_IMPORTS = {
    "numpy": "numpy",
    "netCDF4": "netCDF4",
    "pandas": "pandas",
    "matplotlib": "matplotlib",
    "cartopy": "cartopy",
    "Pillow": "PIL",
    "scipy": "scipy",
    "scikit-image": "skimage",
    "opencv-python": "cv2",
    "paramiko": "paramiko",
    "PyQt6": "PyQt6.QtWidgets",
    "PyQt6-Fluent-Widgets": "qfluentwidgets",
    "requests": "requests",
    "PyYAML": "yaml",
}


def _missing_requirements_for_modules(required: dict[str, str]) -> list[str]:
    missing: list[str] = []
    for requirement, module_name in required.items():
        try:
            available = importlib.util.find_spec(module_name) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            available = False
        if not available:
            missing.append(requirement)
    return missing


def _different_executable_path(left: Path, right: Path) -> bool:
    # Do not resolve symlinks here: venv/bin/python often points to the
    # Homebrew interpreter, but executing through that path still activates
    # the virtual environment via sys.prefix.
    return left.absolute() != right.absolute()


def _reexec(python: Path, entry_script: Path, argv: list[str]) -> None:
    args = [str(python), str(entry_script), *argv]
    os.execv(str(python), args)
