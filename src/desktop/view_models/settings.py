"""设置页视图模型：封装根目录 ``params.yml`` 与网格 JSON 的读写。

不直接依赖 Qt（``apply_theme`` 内部按需导入 qfluentwidgets）。所有持久化转调
:mod:`workflows.infrastructure.runtime_config` 既有函数。

[EN] Settings page view model: encapsulates reading/writing of root ``params.yml`` and grid JSON.

Does not directly depend on Qt (``apply_theme`` imports qfluentwidgets on demand). All persistence
delegates to existing functions in :mod:`workflows.infrastructure.runtime_config`.
"""

from __future__ import annotations

from typing import Any

from workflows.domain.output_scheme_yaml import visible_output_schemes
from workflows.infrastructure import runtime_config


class SettingsViewModel:
    # [EN] Desktop global config load/save adapter (reads/writes root params.yml).
    """桌面全局配置的加载/保存适配（读写根目录 params.yml）。"""

    # [EN] ── params.yml (desktop section + pipeline parameters) ──────────────────────────────────────
    # ── params.yml（desktop 段 + 管线参数） ──────────────────────────────────────

    def load(self) -> dict[str, Any]:
        # [EN] Return a flat dict merging desktop section + pipeline parameters.
        """返回 desktop 段 + 管线参数合并后的扁平字典。"""
        return runtime_config.load_full_config()

    def save(self, updates: dict[str, Any]) -> bool:
        # [EN] Merge ``updates`` into existing config and write back to params.yml.
        """将 ``updates`` 合并进现有配置并写回 params.yml。"""
        config = runtime_config.load_full_config()
        config.update(updates)
        return runtime_config.save_full_config(config)

    # [EN] ── Output variables (spectral partition) scheme ────────────────────────────────────────────────
    # ── 输出变量（谱分区）方案 ────────────────────────────────────────────────

    def output_schemes(self) -> dict[str, list[str]]:
        config = runtime_config.load_full_config()
        schemes = config.get("OUTPUT_VARS_SCHEMES")
        return visible_output_schemes(schemes) if isinstance(schemes, dict) else {}

    def save_output_schemes(self, schemes: dict[str, list[str]]) -> bool:
        return self.save({"OUTPUT_VARS_SCHEMES": schemes})

    # [EN] ── ST versions ───────────────────────────────────────────────────────────────
    # ── ST 版本 ───────────────────────────────────────────────────────────────

    def st_versions(self) -> list[dict[str, str]]:
        config = runtime_config.load_full_config()
        versions = config.get("ST_VERSIONS")
        out: list[dict[str, str]] = []
        if isinstance(versions, list):
            for item in versions:
                if isinstance(item, dict) and item.get("name"):
                    out.append({"name": str(item["name"]), "path": str(item.get("path", ""))})
        return out

    def default_st(self) -> str:
        return str(runtime_config.load_full_config().get("DEFAULT_ST", "") or "")

    def save_st_versions(self, versions: list[dict[str, str]], default_name: str) -> bool:
        names = [v["name"] for v in versions]
        return self.save(
            {
                "ST_VERSIONS": versions,
                "ST_OPTIONS": names,
                "DEFAULT_ST": default_name if default_name in names else (names[0] if names else ""),
            }
        )

    # [EN] ── Local ST versions ─────────────────────────────────────────────────────────
    # ── 本地 ST 版本 ─────────────────────────────────────────────────────────

    def local_st_versions(self) -> list[dict[str, str]]:
        config = runtime_config.load_full_config()
        versions = config.get("LOCAL_ST_VERSIONS")
        out: list[dict[str, str]] = []
        if isinstance(versions, list):
            for item in versions:
                if isinstance(item, dict) and item.get("name"):
                    out.append({"name": str(item["name"]), "path": str(item.get("path", ""))})
        return out

    def default_local_st(self) -> str:
        return str(runtime_config.load_full_config().get("DEFAULT_LOCAL_ST", "") or "")

    def save_local_st_versions(self, versions: list[dict[str, str]], default_name: str) -> bool:
        names = [v["name"] for v in versions]
        return self.save(
            {
                "LOCAL_ST_VERSIONS": versions,
                "LOCAL_ST_OPTIONS": names,
                "DEFAULT_LOCAL_ST": default_name if default_name in names else (names[0] if names else ""),
            }
        )

    # [EN] ── Unstructured / SMC grid JSON ────────────────────────────────────────────────
    # ── 非结构 / SMC 网格 JSON ────────────────────────────────────────────────

    def load_unst(self) -> dict[str, Any]:
        return runtime_config.load_unst_msh_gen_config()

    def save_unst(self, updates: dict[str, Any]) -> None:
        runtime_config.save_unst_msh_gen_config(updates)

    def load_smc(self) -> dict[str, Any]:
        return runtime_config.load_smc_grid_json_for_settings()

    def save_smc(self, updates: dict[str, Any]) -> None:
        runtime_config.save_smc_grid_json_updates(updates)

    # [EN] ── Immediate apply: theme / language ─────────────────────────────────────────────────
    # ── 即时应用：主题 / 语言 ─────────────────────────────────────────────────

    def apply_theme(self, name: str) -> None:
        # [EN] Switch qfluentwidgets theme by ``AUTO``/``LIGHT``/``DARK`` (best-effort).
        """按 ``AUTO``/``LIGHT``/``DARK`` 切换 qfluentwidgets 主题（best-effort）。"""
        try:
            from qfluentwidgets import Theme, setTheme

            mapping = {"AUTO": Theme.AUTO, "LIGHT": Theme.LIGHT, "DARK": Theme.DARK}
            setTheme(mapping.get(str(name).upper(), Theme.AUTO))
        except Exception:
            pass

    def apply_language(self, code: str) -> None:
        # [EN] Switch src translation cache; window layer is responsible for rebuilding the UI.
        """切换 src 翻译缓存；窗口层负责重建界面。"""
        try:
            from workflows.support.translations import set_language

            set_language(str(code or "zh_CN"))
        except Exception:
            pass
