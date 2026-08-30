#!/usr/bin/env python3
"""WW3Tool 统一入口（实现位于 src/）。

一个入口通吃三种使用方式，并统一负责环境搭建（虚拟环境 / 依赖 / sys.path）：

    python3 run.py                       → 启动 Desktop 图形界面（默认）
    python3 run.py shell [params.yml]    → 启动交互式 REPL（推荐日常操作）
    python3 run.py <子命令> [选项] [工作目录]  → 无界面 CLI（适合脚本与自动化）

不带子命令执行 ``python3 run.py --help`` 时，打印命令参考（与 ``shell`` 内 ``help`` 相同）。

**重要**：仓库根目录 ``params.yml`` 是模板，不允许直接用于运行。
用 ``workdir <路径>`` 从模板创建或加载工作目录（CLI：
``python3 run.py workdir <路径>``）。其余命令可跟可选的 ``[工作目录]``，
省略时使用当前目录。

典型流程：

    workdir → run-workflow → local-run
                              └→ upload → submit → check-status → download-results

配置管理
  workdir <路径>           创建或加载工作目录（shell）；CLI 为独立子命令
  validate [工作目录]      校验 params.yml
  config [工作目录]        显示配置摘要
  print-params [工作目录]  输出 params.yml 内容

预处理（merge-forcing 除外均可跟 [工作目录]）
  prepare-forcing          Step 1：准备强迫场
  merge-forcing <输入.nc> [...] -o <输出.nc> [--time-range ...] [--bbox ...]
                           独立工具：校验并合并强迫场 NetCDF（无需工作目录）
  inspect-forcing <场> <文件.nc> [-w 工作目录]
                           只读：打印强迫场变量自动识别结果/歧义/可用变量
  generate-grid            Step 2：生成计算网格
  prepare-ww3              仅生成 WW3 namelist
  recommend-cfl            按 CFL 推荐时间步长并写回配置
  recommend-grid           推荐网格间距/分辨率并写回配置
  run-workflow             完整预处理：强迫场 → 网格 → WW3 namelist
  local-run                执行 local.sh（本地跑 WW3）

后处理 / 绘图（plot: 段）
  plot-wave-maps [--contour] / plot-spectrum [--mode ...] [--station N]
  plot-jason3 / plot-jason3-swh / download-jason3 / plot-ndbc [--download]

远程运维（server: 段）
  connect-test / ssh / slurm-idle / list-files
  confirm-slurm [workdir]            写 server.sh
  upload --confirm / submit [--script server.sh]
  check-status / queue-status
  download-results [--nested] / download-log
  clear-remote --confirm / cancel-job <job_id>

辅助
  print-example            打印示例 params.yml
  help / exit              仅 shell 模式

----------------------------------------------------------------------
使用方式
----------------------------------------------------------------------

    python3 run.py shell [params.yml]    交互式 REPL（命令不带 ``[工作目录]`` 时沿用已加载目录）
    python3 run.py <子命令> [选项] [工作目录]  无界面 CLI（每条命令单独指定工作目录）

----------------------------------------------------------------------
全局选项
----------------------------------------------------------------------
--lang <语言代码>   切换输出语言（zh_CN / en_US），三种模式均可用。

----------------------------------------------------------------------
退出码
----------------------------------------------------------------------
0  成功
1  运行时异常 / 任务失败 / 依赖初始化失败
2  参数或 YAML 配置错误
3  破坏性远程操作未加 --confirm

[EN] Unified WW3Tool entry point (implementation lives in src/).

One entry point for three usage modes, and the single place responsible for
runtime setup (venv / dependencies / sys.path):

    python3 run.py                       -> Launch the Desktop GUI (default)
    python3 run.py shell [params.yml]    -> Interactive REPL
    python3 run.py <subcommand> [opts] [workdir]  -> Headless CLI

Running ``python3 run.py --help`` without a subcommand prints the command
reference (same as ``help`` inside ``shell``).

**Important**: The repository-root ``params.yml`` is a template and must not be
run directly. Use ``workdir <path>`` to create or load a workdir (CLI:
``python3 run.py workdir <path>``). Other commands accept an optional ``[workdir]``;
the current directory is used when omitted.

Typical flow:

    workdir -> run-workflow -> local-run
                               -> upload -> submit -> check-status -> download-results

Configuration
  workdir <path>           Create/load workdir (shell); standalone CLI subcommand
  validate [workdir]       Validate params.yml
  config [workdir]         Show configuration summary
  print-params [workdir]   Print params.yml

Preprocessing (all except merge-forcing accept optional [workdir])
  prepare-forcing / inspect-forcing / generate-grid / prepare-ww3 / recommend-cfl / recommend-grid
  run-workflow / local-run
  merge-forcing <in.nc> [...] -o <out.nc> [--time-range ...] [--bbox ...]  (standalone)

Post-processing / plotting (plot: section)
  plot-wave-maps [--contour] / plot-spectrum [--mode ...] [--station N]
  plot-jason3 / plot-jason3-swh / download-jason3 / plot-ndbc [--download]

Remote operations (server: section)
  connect-test / ssh / slurm-idle / list-files
  confirm-slurm [workdir]            Write server.sh
  upload --confirm / submit [--script server.sh]
  check-status / queue-status / download-results [--nested] / download-log
  clear-remote --confirm / cancel-job <job_id>

Auxiliary
  print-example
  help / exit              Shell mode only

----------------------------------------------------------------------
Usage modes
----------------------------------------------------------------------

    python3 run.py shell [params.yml]    Interactive REPL (reuses loaded workdir when omitted)
    python3 run.py <subcommand> [opts] [workdir]  Headless CLI (workdir per invocation)

----------------------------------------------------------------------
Global options
----------------------------------------------------------------------
--lang <code>   Switch output language (zh_CN / en_US); available in all modes.

----------------------------------------------------------------------
Exit codes
----------------------------------------------------------------------
0  Success
1  Runtime exception / task failure / dependency initialization failure
2  Parameter or YAML configuration error
3  Destructive remote operation without --confirm
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path


# WW3TOOL_ROOT 环境变量优先：pip/brew 安装形态下指向含 meshgen/public 的仓库；
# 仓库形态（默认）从脚本位置推导，行为与以前完全一致。
# [EN] WW3TOOL_ROOT env wins: in pip/brew installs it points to the repo holding
# meshgen/public; in the repo layout (default) we infer from __file__ as before.
def _resolve_root() -> Path:
    env_root = os.environ.get("WW3TOOL_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    # 仓库形态：从本文件向上找到含 params.yml 与 run.py 的仓库根
    # [EN] Repo layout: walk up to the dir holding both params.yml and run.py.
    _d = Path(__file__).resolve().parent
    while True:
        if (_d / "params.yml").is_file() and (_d / "run.py").is_file():
            return _d
        if _d.parent == _d:
            break
        _d = _d.parent
    # 装包形态：site-packages 里的 ww3tool_resources 自带全部运行资源
    # （params.yml / public / meshgen），此时它就是资源根。
    # [EN] Packaged install: ww3tool_resources ships the runtime resources.
    try:
        import ww3tool_resources

        pkg_root = Path(ww3tool_resources.__file__).resolve().parent
        if (pkg_root / "params.yml").is_file():
            return pkg_root
    except Exception:
        pass
    return Path(__file__).resolve().parent  # 兜底：原仓库推断


ROOT = _resolve_root()
# 装包形态下本文件（run.py）位于 site-packages 根，仓库形态下位于仓库根，
# 两种形态都用 __file__ 定位，避免资源包内不存在的 run.py。
ENTRY_SCRIPT = Path(__file__).resolve()
REQUIREMENTS_FILE = ROOT / "src" / "requirements.txt"
# pip 安装形态：ROOT 是 ww3tool_resources 资源包（含 params.yml 但无 run.py），
# 此时运行环境就是 pip 安装目标，直接使用当前解释器，禁止在 site-packages 内自建 .venv。
_PACKAGED_INSTALL = (ROOT / "run.py").is_file() is False
VENV_DIR = Path(sys.prefix) if _PACKAGED_INSTALL else ROOT / ".venv"

# 无需完整虚拟环境/依赖即可执行的轻量 CLI 子命令。
# [EN] Lightweight CLI subcommands that don't require the full venv/dependencies.
_LIGHT_CLI_COMMANDS = {"--help", "-h", "print-example", "workdir"}

# 核心依赖（CLI / Shell / Desktop 共用）
# [EN] Core dependencies shared by CLI, Shell, and Desktop.
_CORE_REQUIRED_IMPORTS = {
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
    "requests": "requests",
    "PyYAML": "yaml",
    "pyfiglet": "pyfiglet",
}

# 仅 Desktop / 交互式 GUI 需要
# [EN] Required only for Desktop / interactive GUI.
# 启动桌面端的写法。
# [EN] Flags that launch the desktop.
_GUI_FLAGS = frozenset({"--gui", "--desktop", "gui", "desktop"})

_GUI_REQUIRED_IMPORTS = {
    "PyQt6": "PyQt6.QtWidgets",
    "PyQt6-Fluent-Widgets": "qfluentwidgets",
    "PyQt6-WebEngine": "PyQt6.QtWebEngineCore",
}

# 向后兼容：完整依赖表
# [EN] Backward-compatible full dependency map.
_REQUIRED_IMPORTS = {**_CORE_REQUIRED_IMPORTS, **_GUI_REQUIRED_IMPORTS}



def _has_desktop_environment() -> bool:
    """Whether this machine can actually put a window on a screen.

    macOS and Windows always can.  On Linux it takes a display server, and an
    HPC login or compute node has none -- there the Qt wheels usually cannot
    even be built, so insisting on them turns a perfectly good CLI into a hard
    failure.  ``WW3TOOL_FORCE_DESKTOP=1`` overrides this for cases such as X
    forwarding where the variables are set late.

    [EN] True when a GUI can be displayed.
    """
    if os.environ.get("WW3TOOL_FORCE_DESKTOP", "").strip() not in ("", "0"):
        return True
    if sys.platform in ("darwin", "win32"):
        return True
    return bool(
        os.environ.get("DISPLAY", "").strip()
        or os.environ.get("WAYLAND_DISPLAY", "").strip()
    )


def _required_imports(mode: str) -> dict[str, str]:
    """按运行模式返回需检查的依赖。CLI / Shell 不检查 GUI 包。

    [EN] Return the dependency map to check for *mode*. CLI and shell skip GUI packages.
    """
    if mode == "desktop":
        return dict(_REQUIRED_IMPORTS)
    return dict(_CORE_REQUIRED_IMPORTS)

# 用于在子进程中检测缺失依赖的内联脚本。
# [EN] Inline script to detect missing dependencies in a subprocess.
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


def _bootstrap_src_imports() -> None:
    """将 src 加入 sys.path，以便 import workflows、desktop 等模块。

    [EN] Add src to sys.path so workflows and desktop can be imported.
    """
    src_str = str(ROOT / "src")
    if src_str not in sys.path:
        sys.path.insert(0, src_str)


def _tr(key: str, default: str) -> str:
    """Translate bootstrap messages after src has been added to sys.path."""
    try:
        from workflows.support.translations import tr

        return tr(key, default)
    except Exception:
        return default


def _extract_lang(argv: list[str]) -> tuple[str | None, list[str]]:
    """从参数列表中提取 ``--lang <code>``，返回 ``(语言代码, 剩余参数)``。

    支持 ``--lang en_US`` 与 ``--lang=en_US`` 两种写法；未指定则返回 ``(None, argv)``。

    [EN] Extract ``--lang <code>`` from the argument list, returning
    ``(language code, remaining args)``. Supports both ``--lang en_US`` and
    ``--lang=en_US`` forms; returns ``(None, argv)`` if not specified.
    """
    lang: str | None = None
    remaining: list[str] = []
    skip_next = False
    for i, arg in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if arg == "--lang":
            if i + 1 < len(argv):
                lang = argv[i + 1]
                skip_next = True
            continue
        if arg.startswith("--lang="):
            lang = arg.split("=", 1)[1]
            continue
        remaining.append(arg)
    return lang, remaining


def _apply_language(lang: str | None) -> None:
    """若指定了 ``--lang``，则调用 set_language 切换输出语言。

    [EN] If ``--lang`` is specified, call set_language to switch output language.
    """
    if lang is None:
        return
    try:
        from workflows.support.translations import set_language

        set_language(lang)
    except Exception:
        pass


def _requires_full_dependencies(mode: str, rest: list[str]) -> bool:
    """判断当前调用是否需要检查虚拟环境与依赖。

    Desktop 与 shell 始终检查（shell 不含 GUI 包）；纯帮助以及 CLI 下的
    help / print-example / workdir 可跳过。

    [EN] Whether the current invocation needs the venv/dependency check.
    Desktop and shell always check (shell excludes GUI packages); CLI help /
    print-example / workdir can be skipped.
    """
    if mode == "help":
        # 只打印帮助，不该为此去装任何东西。
        return False
    if mode == "desktop":
        return True
    if mode == "shell":
        return True
    if not rest:
        return True
    if rest[0] in _LIGHT_CLI_COMMANDS:
        return False
    if len(rest) >= 2 and rest[1] in {"--help", "-h"}:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    """统一入口：引导 import 路径、按需检查依赖，并按模式分发。

    [EN] Unified entry point: bootstrap import paths, check dependencies as
    needed, and dispatch by mode.
    """
    _bootstrap_src_imports()
    # 保留 --lang 在原始 argv 中，使 ensure_runtime re-exec 后的新进程也能读取语言设置。
    # [EN] Keep --lang in the original argv so it survives ensure_runtime's re-exec.
    original = sys.argv[1:] if argv is None else list(argv)
    lang, rest = _extract_lang(original)
    _apply_language(lang)

    # 不带参数只打印帮助：桌面端要显式 `ww3tool --gui` 才启动。默认启动桌面端
    # 会在无图形环境的机器上强行要求 GUI 依赖，而那正是只需要 CLI 的场景。
    # [EN] No arguments prints the help; the desktop needs an explicit --gui.
    if not rest:
        mode = "help"
    elif rest[0] in _GUI_FLAGS:
        mode = "desktop"
        rest = rest[1:]
    elif rest[0] == "shell":
        mode = "shell"
    else:
        mode = "cli"

    # 显式要 GUI 但没有图形环境：说清楚为什么起不来，而不是让 pip 去编译
    # 一个注定装不上的 PyQt6 再报一堆编译错。
    # [EN] --gui on a machine with no display: say so plainly.
    if mode == "desktop" and not _has_desktop_environment():
        print(
            _tr(
                "cli_gui_needs_display",
                "未检测到图形环境，桌面端无法启动。请在有显示器的机器上运行；"
                "若确认可用（如 X11 转发）请设置 WW3TOOL_FORCE_DESKTOP=1。"
                "命令行功能不受影响，直接运行 ww3tool shell 或 ww3tool --help。",
            ),
            file=sys.stderr,
        )
        return 1

    # --json 时 stdout 上只能有那一个 JSON 对象，启动阶段的提示一律闭嘴。
    # [EN] In --json mode stdout must carry nothing but the JSON object.
    quiet_startup = "--json" in rest

    if _requires_full_dependencies(mode, rest):
        try:
            _ensure_runtime(entry_script=ENTRY_SCRIPT, argv=original, mode=mode,
                            quiet=quiet_startup)
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
            print(
                _tr("cli_dependency_init_failed", "依赖初始化失败：{error}").format(error=exc),
                file=sys.stderr,
            )
            return 1

    if mode == "help":
        from workflows.interfaces.interactive_cli import print_help

        print_help()
        return 0

    if mode == "desktop":
        from desktop.application import main as run_desktop

        return run_desktop([])

    if mode == "shell":
        from workflows.interfaces.interactive_cli import main as run_interactive

        params_path = rest[1] if len(rest) > 1 and rest[1] not in {"--help", "-h"} else None
        return run_interactive(params_path)

    if rest and rest[0] in {"--help", "-h"}:
        from workflows.interfaces.interactive_cli import print_help

        print_help()
        return 0

    from workflows.interfaces.command_line import main as run_commands

    return run_commands(rest)


# ──────────────────────────────────────────────────────────────────────
# 虚拟环境与依赖管理（原 venv_and_deps.py）
# Venv & dependency management (formerly venv_and_deps.py)
# ──────────────────────────────────────────────────────────────────────


def _venv_python_path() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _running_in_project_venv() -> bool:
    try:
        return Path(sys.prefix).resolve() == VENV_DIR.resolve()
    except OSError:
        return False


def _is_externally_managed_environment() -> bool:
    marker = Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED"
    return marker.is_file()


def _missing_requirements(required: dict[str, str] | None = None) -> list[str]:
    req = required if required is not None else _REQUIRED_IMPORTS
    missing: list[str] = []
    for requirement, module_name in req.items():
        try:
            available = importlib.util.find_spec(module_name) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            available = False
        if not available:
            missing.append(requirement)
    return missing


def _missing_requirements_for_python(python: Path, required: dict[str, str]) -> list[str]:
    proc = subprocess.run(
        [str(python), "-c", _CHECK_SCRIPT, json.dumps(required)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"Failed to detect dependencies: {python}")
    return json.loads(proc.stdout.strip() or "[]")


def _ensure_project_venv() -> Path:
    venv_python = _venv_python_path()
    if venv_python.is_file():
        return venv_python
    print(f"Creating project virtual environment: {VENV_DIR}")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    if not venv_python.is_file():
        raise RuntimeError(f"Failed to create virtual environment: {venv_python}")
    return venv_python


def _resolve_install_python() -> Path:
    if _running_in_project_venv():
        return Path(sys.executable)
    if _is_externally_managed_environment():
        return _ensure_project_venv()
    if _venv_python_path().is_file():
        return _venv_python_path()
    return Path(sys.executable)


def _pip_install(python: Path, packages: list[str] | None = None) -> None:
    if packages:
        subprocess.run(
            [str(python), "-m", "pip", "install", *packages],
            check=True,
        )
        return
    if REQUIREMENTS_FILE.is_file():
        subprocess.run(
            [str(python), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)],
            check=True,
        )
        return
    # 打包形态（pip/brew）没有 src/requirements.txt：直接按全量依赖表安装。
    # [EN] Packaged installs have no requirements.txt: install the full dep map.
    subprocess.run(
        [str(python), "-m", "pip", "install", *list(_REQUIRED_IMPORTS)],
        check=True,
    )


def _different_executable_path(left: Path, right: Path) -> bool:
    # Do not resolve symlinks here: venv/bin/python often points to the
    # Homebrew interpreter, but executing through that path still activates
    # the virtual environment via sys.prefix.
    return left.absolute() != right.absolute()


def _reexec(python: Path, entry_script: Path, argv: list[str]) -> None:
    args = [str(python), str(entry_script), *argv]
    os.execv(str(python), args)


def _ensure_dependencies(*, quiet: bool = False, mode: str = "desktop") -> Path | None:
    """Install missing dependencies. Returns venv python when caller must re-exec."""
    required = _required_imports(mode)
    missing = _missing_requirements(required)
    if not missing:
        if not quiet:
            print("Dependency check passed.")
        return None

    print("Missing dependencies, installing automatically: " + ", ".join(missing))
    install_python = _resolve_install_python()
    try:
        # CLI / Shell 只装缺失的核心包，避免在无显示环境拉 PyQt6
        if mode == "desktop":
            _pip_install(install_python)
        else:
            _pip_install(install_python, missing)
    except subprocess.CalledProcessError:
        if _different_executable_path(install_python, Path(sys.executable)):
            raise
        install_python = _ensure_project_venv()
        if mode == "desktop":
            _pip_install(install_python)
        else:
            _pip_install(install_python, missing)

    if _different_executable_path(install_python, Path(sys.executable)):
        return install_python

    remaining = _missing_requirements(required)
    if remaining:
        raise RuntimeError("Still unimportable after installation: " + ", ".join(remaining))
    print("Dependencies installed.")
    return None


def _ensure_runtime(*, entry_script: Path, argv: list[str] | None = None, mode: str = "cli",
                    quiet: bool = False) -> None:
    """Ensure dependencies and re-exec into the project venv when needed."""
    argv = list(argv or [])
    required = _required_imports(mode)
    venv_python = _venv_python_path()

    if venv_python.is_file() and not _running_in_project_venv():
        if not quiet:
            print(f"Using project virtual environment: {VENV_DIR}")
        _reexec(venv_python, entry_script, argv)

    reexec_python = _ensure_dependencies(mode=mode, quiet=quiet)
    if reexec_python is not None:
        if not quiet:
            print(f"Switched to project virtual environment: {VENV_DIR}")
        _reexec(reexec_python, entry_script, argv)

    if _missing_requirements(required):
        raise RuntimeError(
            "Still unimportable after installation: " + ", ".join(_missing_requirements(required))
        )


# ──────────────────────────────────────────────────────────────────────
# 打包构建后端（原 setup.py，已合并进本文件）
#
# pyproject.toml 的 [build-system] 声明 build-backend = "run"，因此 pip /
# `python3 -m build` 构建 wheel/sdist 时会把本模块当作构建后端 import：
# 构建前先暂存运行资源（params.yml / public 子集 / meshgen 瘦身子集 /
# src/requirements.txt）进 src/ww3tool_resources/ 包，再转交 setuptools。
# 本段所有内容仅在“被当作构建后端调用”时执行，普通运行入口不受影响。
#
# [EN] Packaging build backend (formerly setup.py, merged into this file).
# pyproject.toml declares build-backend = "run", so pip / `python3 -m build`
# import this module as the build backend: stage runtime resources
# (params.yml / public subset / meshgen slim subset / src/requirements.txt)
# into src/ww3tool_resources/ before delegating to setuptools. Nothing here
# runs during normal application startup.
# ──────────────────────────────────────────────────────────────────────

_BUILD_STAGE = ROOT / "src" / "ww3tool_resources"
_BUILD_SKIP_DIRS = {"__pycache__", ".venv"}
_BUILD_MESHGEN_SKIP_TOP = {"__pycache__", ".venv", "cache", "reference_data"}
# 任意层级的运行产物目录都不进包：里面是跑过一次留下的文件，
# 常常带着当时的绝对路径。
_BUILD_SKIP_ANY_DIR = {"output", "__pycache__", ".venv"}
_BUILD_MAX_NONPY_BYTES = 1_000_000  # meshgen 中 >1MB 的非 .py 文件视为数据/文档，不进包

# 资源包的 __init__.py 壳（rmtree 重建时写入，保证包可导入）。
# [EN] The __init__.py shell re-created after the stage dir is wiped.
_BUILD_INIT_PY = '''"""WW3Tool runtime resources (pip install layout).

Build-time staged resources (params.yml / public / meshgen / requirements).
"""

from pathlib import Path

__all__ = ["resource_root", "is_packaged_root"]


def resource_root() -> Path:
    """Return this resource package's root directory."""
    return Path(__file__).resolve().parent


def is_packaged_root() -> bool:
    """True when this package carries the staged resources."""
    return (Path(__file__).resolve().parent / "params.yml").is_file()
'''



# ── 打包前清除模板中的个人信息 ─────────────────────────────────────────
# 仓库根的 params.yml 同时是「开发者日常使用的配置」和「随包分发的模板」。
# 直接打包会把开发机路径、集群家目录、SSH 别名一起发出去（实测 37 处）。
# 处理时逐行改写而不是 YAML 往返：模板里大段说明注释是它的主要价值，
# safe_load/safe_dump 会把它们全部丢掉。
# [EN] Strip developer-specific values from the packaged params.yml template.

import re as _re

# 值以这些前缀开头就是某个人的家目录，不该随包发布。
_PERSONAL_PATH = _re.compile(
    r"^(/Users/|/home/|/root/|/public/home/|[A-Za-z]:[\\/](Users|home)[\\/])"
)

# 这些键无论取值如何都要清空：它们标识的是某台机器或某个账号。
_PERSONAL_KEYS = frozenset({
    "ssh_config_host", "default_remote_dir", "host", "user",
    "password", "key_file", "passphrase",
})

# 历史记录类的列表整段清空。
_HISTORY_KEYS = frozenset({"recent_workdirs"})

# 开发机上的个人偏好，发行版里改回中性默认值，否则打包那一刻的开发者
# 设置会变成所有用户的默认值（语言就这么长期默认成了中文）。
_NEUTRAL_DEFAULTS = {"language": "auto"}

_KV = _re.compile(r"^(?P<indent>\s*)(?P<key>[^#:][^:]*):(?P<gap>\s*)(?P<value>.*?)(?P<eol>\s*)$")

# Fortran namelist：KEY = '值'
_NML_KV = _re.compile(r"^(?P<head>\s*[A-Za-z_][A-Za-z0-9_]*\s*=\s*)(?P<q>['\"])(?P<value>.*?)(?P=q)(?P<tail>.*)$")

# 随包分发的文本模板，暂存时一并清洗。
_BUILD_SANITIZE_SUFFIXES = frozenset({".nml", ".json", ".yaml", ".yml", ".flag"})


def _sanitize_config_text(text: str) -> str:
    """Blank developer-specific values in a staged config template.

    Handles the two shapes that ship with the package: YAML ``key: value``
    and Fortran namelist ``KEY = 'value'``.
    """
    out = []
    for line in text.splitlines(keepends=True):
        m = _NML_KV.match(line.rstrip("\n"))
        if m and _PERSONAL_PATH.match(m.group("value").strip()):
            q = m.group("q")
            out.append(f"{m.group('head')}{q}{q}{m.group('tail')}\n")
            continue
        out.append(line)
    return _sanitize_params_template("".join(out))


def _sanitize_params_template(text: str) -> str:
    """Blank developer-specific values in the params.yml template.

    Keys and comments are kept as they are -- the point is to ship a template
    that documents every setting while pointing at nobody's machine.
    """
    out = []
    drop_list_under = None
    for line in text.splitlines(keepends=True):
        stripped = line.strip()

        # 正在丢弃某个历史列表的条目
        if drop_list_under is not None:
            if stripped.startswith("- "):
                continue
            drop_list_under = None

        m = _KV.match(line.rstrip("\n"))
        if m and not stripped.startswith("#"):
            key = m.group("key").strip().strip("'\"")
            value = m.group("value").strip()
            bare = key.split(".")[-1]
            if bare in _HISTORY_KEYS:
                out.append(f"{m.group('indent')}{m.group('key')}: []\n")
                drop_list_under = key
                continue
            if bare in _NEUTRAL_DEFAULTS:
                out.append(f"{m.group('indent')}{m.group('key')}: {_NEUTRAL_DEFAULTS[bare]}\n")
                continue
            if value and (bare in _PERSONAL_KEYS or _PERSONAL_PATH.match(value.strip("'\""))):
                out.append(f"{m.group('indent')}{m.group('key')}:\n")
                continue
        out.append(line)
    return "".join(out)


def _build_walk_copy(src_root: Path, rel_dir: str, skip_top: set[str] | None = None) -> None:
    src = src_root / rel_dir
    if not src.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames
                       if d not in _BUILD_SKIP_DIRS and d not in _BUILD_SKIP_ANY_DIR]
        if skip_top and dirpath == str(src):
            dirnames[:] = [d for d in dirnames if d not in skip_top]
        for fn in filenames:
            if fn == ".DS_Store":
                continue
            p = Path(dirpath) / fn
            try:
                if p.stat().st_size > _BUILD_MAX_NONPY_BYTES and p.suffix != ".py":
                    continue
            except OSError:
                continue
            tgt = _BUILD_STAGE / rel_dir / p.relative_to(src)
            tgt.parent.mkdir(parents=True, exist_ok=True)
            if p.suffix in _BUILD_SANITIZE_SUFFIXES:
                try:
                    tgt.write_text(
                        _sanitize_config_text(p.read_text(encoding="utf-8")),
                        encoding="utf-8",
                    )
                    continue
                except (OSError, UnicodeDecodeError):
                    pass
            shutil.copy2(p, tgt)


def _stage_packaging_resources() -> None:
    """将运行资源暂存进 src/ww3tool_resources/（构建 wheel/sdist 前调用）。

    [EN] Stage runtime resources into src/ww3tool_resources/ (called before
    building the wheel/sdist).
    """
    # 非仓库根（例如从 sdist 解压后资源已在包内）时直接跳过，保持幂等。
    if not ROOT.joinpath("params.yml").is_file():
        return
    if _BUILD_STAGE.is_dir():
        shutil.rmtree(_BUILD_STAGE)
    _BUILD_STAGE.mkdir(parents=True, exist_ok=True)
    (_BUILD_STAGE / "__init__.py").write_text(_BUILD_INIT_PY, encoding="utf-8")

    # 模板随包分发，先去掉开发者自己的路径/主机/账号再落盘。
    (_BUILD_STAGE / "params.yml").write_text(
        _sanitize_params_template((ROOT / "params.yml").read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    req_src = ROOT / "src" / "requirements.txt"
    if req_src.is_file():
        tgt = _BUILD_STAGE / "src" / "requirements.txt"
        tgt.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(req_src, tgt)

    for rel in (
        "public/languages",
        "public/7.14_nml",
        "public/6.07_nml",
        "public/globe_picker",
        "public/scripts",
    ):
        _build_walk_copy(ROOT, rel)

    # public/resource 只取 logo.png（README 媒体图等不进包）
    logo = ROOT / "public" / "resource" / "logo.png"
    if logo.is_file():
        tgt = _BUILD_STAGE / "public" / "resource" / "logo.png"
        tgt.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(logo, tgt)

    _build_walk_copy(ROOT, "meshgen", skip_top=_BUILD_MESHGEN_SKIP_TOP)


def _build_meta():
    """Lazily import setuptools.build_meta (only available in build envs)."""
    from setuptools import build_meta

    return build_meta


def build_wheel(
    wheel_directory: str,
    config_settings: dict | None = None,
    metadata_directory: str | None = None,
) -> str:
    _stage_packaging_resources()
    return _build_meta().build_wheel(wheel_directory, config_settings, metadata_directory)


def prepare_metadata_for_build_wheel(
    metadata_directory: str, config_settings: dict | None = None
) -> str:
    _stage_packaging_resources()
    return _build_meta().prepare_metadata_for_build_wheel(metadata_directory, config_settings)


def build_sdist(sdist_directory: str, config_settings: dict | None = None) -> str:
    _stage_packaging_resources()
    return _build_meta().build_sdist(sdist_directory, config_settings)


def build_editable(
    wheel_directory: str,
    config_settings: dict | None = None,
    metadata_directory: str | None = None,
) -> str:
    _stage_packaging_resources()
    return _build_meta().build_editable(wheel_directory, config_settings, metadata_directory)


def prepare_metadata_for_build_editable(
    metadata_directory: str, config_settings: dict | None = None
) -> str:
    _stage_packaging_resources()
    return _build_meta().prepare_metadata_for_build_editable(metadata_directory, config_settings)


def get_requires_for_build_wheel(config_settings: dict | None = None) -> list[str]:
    return _build_meta().get_requires_for_build_wheel(config_settings)


def get_requires_for_build_sdist(config_settings: dict | None = None) -> list[str]:
    return _build_meta().get_requires_for_build_sdist(config_settings)


def get_requires_for_build_editable(config_settings: dict | None = None) -> list[str]:
    return _build_meta().get_requires_for_build_editable(config_settings)


if __name__ == "__main__":
    raise SystemExit(main())
