"""外部边界谱单向嵌套的纯数据对象。

本模块属于 ``domain/`` 层，禁止依赖 Qt。配置项在 ``config_models.BoundaryConfig``；
本文件存放检查结果、点位、映射、计划与运行结果。

[EN] Pure data objects for one-way external spectral nesting. Configuration lives
in ``config_models.BoundaryConfig``; this module holds inspection, mapping, and
plan/result records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


BOUNDARY_SCHEMA_VERSION = 1
SELECTION_ALGO_VERSION = "inset1-v1"
MAPPING_ALGO_VERSION = "haversine-nn-ww3-bounc-linear-v2"
NORMALIZE_ALGO_VERSION = "ww3-netcdf-strict-v1"

FREQ_RTOL = 1e-6
FREQ_ATOL_HZ = 1e-10
ANGLE_TOL_DEG = 1e-4
NEG_SPECTRA_CLIP_TOL = 1e-12

BOUNDARY_STATES = (
    "disabled",
    "needs_input",
    "needs_inspection",
    "metadata_checked",
    "deferred_remote",
    "prepared",
    "stale",
    "failed",
)

RUNTIME_STAGES = (
    "inspect",
    "normalize",
    "grid",
    "build_boundary",
    "verify_boundary",
    "forcing",
    "initialize",
    "integrate",
    "postprocess",
    "done",
)

SUPPORTED_SIDES = ("west", "east", "south", "north")


@dataclass
class BoundaryIssue:
    """单条检查问题。"""

    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    hints: list[str] = field(default_factory=list)


@dataclass
class BoundaryStation:
    """源站点身份与位置。"""

    source_id: str
    name: str
    lon: float
    lat: float
    file_paths: list[str] = field(default_factory=list)


@dataclass
class SpectralDiscrete:
    """频率与方向离散。"""

    frequencies_hz: list[float]
    directions_deg: list[float]
    thoff: float = 0.0
    units: str = ""
    direction_convention: str = "to_direction"


@dataclass
class BoundaryInspection:
    """源文件、站点、时间、谱坐标、单位、检查阶段与问题列表。"""

    state: str = "needs_inspection"
    validation_depth: str = "metadata"
    source_location: str = "local"
    files: list[str] = field(default_factory=list)
    stations: list[BoundaryStation] = field(default_factory=list)
    time_start: Optional[str] = None
    time_end: Optional[str] = None
    n_times: int = 0
    spectral: Optional[SpectralDiscrete] = None
    pending_checks: list[str] = field(default_factory=list)
    issues: list[BoundaryIssue] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not any(item.code.startswith("BOUNDARY_") and item.code != "BOUNDARY_STALE" for item in self.issues)


@dataclass
class BoundaryTargetPoint:
    """活动边界目标点。"""

    point_id: str
    i: int
    j: int
    lon: float
    lat: float
    sides: list[str] = field(default_factory=list)


@dataclass
class BoundaryMapping:
    """目标点到源站点的映射。"""

    target_id: str
    source_ids: list[str]
    distances_km: list[float]
    weights: list[float]
    method: str
    covered: bool
    degenerate: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class BoundaryPlan:
    """执行计划。"""

    schema_version: int = BOUNDARY_SCHEMA_VERSION
    state: str = "needs_input"
    execution_inputs_mode: str = "normalized_bundle"
    effective_start: str = ""
    effective_end: str = ""
    interpolation: str = "nearest"
    max_distance_km: Optional[float] = None
    max_time_gap_seconds: Optional[int] = None
    grid_fingerprint: str = ""
    spectral_fingerprint: str = ""
    source_fingerprint: str = ""
    files: list[str] = field(default_factory=list)
    normalized_relpaths: list[str] = field(default_factory=list)
    normalized_digests: dict[str, str] = field(default_factory=dict)
    target_count: int = 0
    mapped_count: int = 0
    memory_estimate_bytes: int = 0
    normalized_size_bytes: int = 0
    executable_dir: str = ""
    ww3_bounc: str = ""
    ww3_grid: str = ""
    pending_checks: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "state": self.state,
            "execution_inputs": {"mode": self.execution_inputs_mode},
            "effective_start": self.effective_start,
            "effective_end": self.effective_end,
            "interpolation": self.interpolation,
            "max_distance_km": self.max_distance_km,
            "max_time_gap_seconds": self.max_time_gap_seconds,
            "grid_fingerprint": self.grid_fingerprint,
            "spectral_fingerprint": self.spectral_fingerprint,
            "source_fingerprint": self.source_fingerprint,
            "files": list(self.files),
            "normalized_relpaths": list(self.normalized_relpaths),
            "normalized_digests": dict(self.normalized_digests),
            "target_count": self.target_count,
            "mapped_count": self.mapped_count,
            "memory_estimate_bytes": self.memory_estimate_bytes,
            "normalized_size_bytes": self.normalized_size_bytes,
            "executable_dir": self.executable_dir,
            "ww3_bounc": self.ww3_bounc,
            "ww3_grid": self.ww3_grid,
            "pending_checks": list(self.pending_checks),
            "artifacts": dict(self.artifacts),
            "notes": list(self.notes),
            "selection_algo_version": SELECTION_ALGO_VERSION,
            "mapping_algo_version": MAPPING_ALGO_VERSION,
            "normalize_algo_version": NORMALIZE_ALGO_VERSION,
            "freq_rtol": FREQ_RTOL,
            "freq_atol_hz": FREQ_ATOL_HZ,
            "angle_tol_deg": ANGLE_TOL_DEG,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BoundaryPlan":
        exec_inputs = data.get("execution_inputs") or {}
        return cls(
            schema_version=int(data.get("schema_version") or BOUNDARY_SCHEMA_VERSION),
            state=str(data.get("state") or "needs_input"),
            execution_inputs_mode=str(exec_inputs.get("mode") or data.get("execution_inputs_mode") or "normalized_bundle"),
            effective_start=str(data.get("effective_start") or ""),
            effective_end=str(data.get("effective_end") or ""),
            interpolation=str(data.get("interpolation") or "nearest"),
            max_distance_km=(
                float(data["max_distance_km"]) if data.get("max_distance_km") is not None else None
            ),
            max_time_gap_seconds=(
                int(data["max_time_gap_seconds"]) if data.get("max_time_gap_seconds") is not None else None
            ),
            grid_fingerprint=str(data.get("grid_fingerprint") or ""),
            spectral_fingerprint=str(data.get("spectral_fingerprint") or ""),
            source_fingerprint=str(data.get("source_fingerprint") or ""),
            files=list(data.get("files") or []),
            normalized_relpaths=list(data.get("normalized_relpaths") or []),
            normalized_digests=dict(data.get("normalized_digests") or {}),
            target_count=int(data.get("target_count") or 0),
            mapped_count=int(data.get("mapped_count") or 0),
            memory_estimate_bytes=int(data.get("memory_estimate_bytes") or 0),
            normalized_size_bytes=int(data.get("normalized_size_bytes") or 0),
            executable_dir=str(data.get("executable_dir") or ""),
            ww3_bounc=str(data.get("ww3_bounc") or ""),
            ww3_grid=str(data.get("ww3_grid") or ""),
            pending_checks=list(data.get("pending_checks") or []),
            artifacts=dict(data.get("artifacts") or {}),
            notes=list(data.get("notes") or []),
        )


@dataclass
class BoundaryResult:
    """准备或运行阶段结果。"""

    stage: str
    state: str
    ok: bool
    outputs: dict[str, str] = field(default_factory=dict)
    diagnostics: dict[str, str] = field(default_factory=dict)
    errors: list[BoundaryIssue] = field(default_factory=list)
    pending_checks: list[str] = field(default_factory=list)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    exit_code: Optional[int] = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def point_id(i: int, j: int) -> str:
    """稳定点 ID：一基索引编码，不随列表顺序变化。"""
    return f"i{int(i):04d}j{int(j):04d}"
