"""ww3_bounc.nml 生成与日志/二进制诊断适配。"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from ...domain.boundary_models import BoundaryMapping, BoundaryTargetPoint
from .errors import BoundaryError
from ...support.translations import tr


def interp_code(method: str) -> int:
    return 2 if str(method).lower() == "linear" else 1


def write_bounc_nml(path: Path, *, spec_list: str, method: str, verbose: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "&BOUND_NML\n"
        "  BOUND%MODE = 'WRITE'\n"
        f"  BOUND%INTERP = {interp_code(method)}\n"
        f"  BOUND%VERBOSE = {int(verbose)}\n"
        f"  BOUND%FILE = '{spec_list}'\n"
        "/\n"
    )
    path.write_text(text, encoding="utf-8")


def write_read_nml(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "&BOUND_NML\n"
        "  BOUND%MODE = 'READ'\n"
        "  BOUND%INTERP = 1\n"
        "  BOUND%VERBOSE = 1\n"
        "/\n",
        encoding="utf-8",
    )


def write_spec_list(path: Path, relpaths: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [item.strip() for item in relpaths if item.strip()]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _try_record(fh, marker_fmt: str, endian: str) -> bytes | None:
    marker = fh.read(struct.calcsize(marker_fmt))
    if len(marker) < struct.calcsize(marker_fmt):
        return None
    (n,) = struct.unpack(endian + marker_fmt, marker)
    payload = fh.read(n)
    tail = fh.read(struct.calcsize(marker_fmt))
    if len(payload) != n or len(tail) < struct.calcsize(marker_fmt):
        raise BoundaryError(
            "BOUNDARY_VERIFY_FAILED",
            tr("boundary_nest_truncated", "nest.ww3 记录被截断"),
            context={"declared": n, "got": len(payload)},
        )
    (n2,) = struct.unpack(endian + marker_fmt, tail)
    if n2 != n:
        raise BoundaryError(
            "BOUNDARY_VERIFY_FAILED",
            tr("boundary_nest_marker_mismatch", "nest.ww3 记录前后长度不一致"),
            context={"begin": n, "end": n2},
        )
    return payload


class NestFileInfo:
    def __init__(self) -> None:
        self.ident = ""
        self.nk = 0
        self.nth = 0
        self.nbi = 0
        self.times: list[str] = []
        self.n_records = 0
        self.n_spec_records = 0
        self.mapping_indices: list[list[int]] = []
        self.mapping_weights: list[list[float]] = []
        self.xb: list[float] = []
        self.yb: list[float] = []
        self.layout = ""
        self.notes: list[str] = []
        self.spec_blobs: list[list[bytes]] = []
        self.spectra: list[list[Any]] = []


def read_nest_file(path: Path) -> NestFileInfo:
    """读取 Fortran 顺序记录的 nest.ww3。无法识别时明确报不支持。"""
    data = Path(path).read_bytes()
    if not data:
        raise BoundaryError("BOUNDARY_VERIFY_FAILED", tr("boundary_nest_empty", "nest.ww3 为空"))
    last_error: Exception | None = None
    parsed: NestFileInfo | None = None
    for endian in ("<", ">"):
        for marker in ("i", "q"):
            try:
                parsed = _parse_nest(data, endian, marker)
                _decode_spec_blobs(parsed, endian)
                return parsed
            except BoundaryError as exc:
                last_error = exc
                if exc.context.get("content"):
                    raise
                continue
            except Exception as exc:
                last_error = exc
                continue
    raise BoundaryError(
        "BOUNDARY_VERIFY_FAILED",
        tr("boundary_nest_layout_unknown", "无法识别 nest.ww3 二进制布局"),
        context={"error": str(last_error) if last_error else ""},
    )


def _parse_nest(data: bytes, endian: str, marker: str) -> NestFileInfo:
    import io

    fh = io.BytesIO(data)
    info = NestFileInfo()
    rec1 = _try_record(fh, marker, endian)
    if rec1 is None:
        raise BoundaryError("BOUNDARY_VERIFY_FAILED", tr("boundary_nest_no_ident", "缺少文件标识记录"))
    ident = rec1[: min(32, len(rec1))].decode("ascii", "replace").strip("\x00 ")
    info.ident = ident
    # ww3_bounc / W3IOBC 把 ID、版本、NK、NTH、XFR、FR1、TH1、NBI 写在同一条记录里
    if ident.startswith("WAVEWATCH III BOUNDARY DATA FILE") and len(rec1) >= 54:
        nk, nth, nbi = _header_dims(rec1, endian)
        info.nk, info.nth, info.nbi = nk, nth, nbi
    else:
        rec2 = _try_record(fh, marker, endian)
        if rec2 is None:
            raise BoundaryError("BOUNDARY_VERIFY_FAILED", tr("boundary_nest_no_dims_record", "缺少谱维度记录"))
        ints = _unpack_ints(rec2, endian)
        if len(ints) < 3:
            raise BoundaryError("BOUNDARY_VERIFY_FAILED", tr("boundary_nest_dims_short", "维度记录过短"), context={"nbytes": len(rec2)})
        info.nk, info.nth, info.nbi = int(ints[0]), int(ints[1]), int(ints[2])
    if info.nk < 1 or info.nth < 1 or info.nbi < 1 or info.nbi > 10**6:
        raise BoundaryError(
            "BOUNDARY_VERIFY_FAILED",
            tr("boundary_nest_bad_dims", "边界点数或谱维数非法"),
            context={"nk": info.nk, "nth": info.nth, "nbi": info.nbi},
        )
    header_left = 12
    spec_sizes = {int(info.nk) * int(info.nth) * 4, int(info.nk) * int(info.nth) * 8}

    def consume_time_group(time_rec: bytes) -> None:
        nsource = _time_nsource(time_rec, endian)
        spec_got = 0
        group: list[bytes] = []
        for _ in range(nsource):
            spec = _try_record(fh, marker, endian)
            if spec is None:
                raise BoundaryError(
                    "BOUNDARY_VERIFY_FAILED",
                    tr("boundary_nest_missing_spectra", "nest.ww3 时刻后缺少谱记录"),
                    context={"time": _fmt_time(time_rec, endian), "required": nsource, "got": spec_got},
                )
            if spec_sizes and len(spec) not in spec_sizes:
                raise BoundaryError(
                    "BOUNDARY_VERIFY_FAILED",
                    tr("boundary_nest_record_length", "nest.ww3 谱记录长度与 NK×NTH 不一致"),
                    context={"nbytes": len(spec), "nk": info.nk, "nth": info.nth},
                )
            spec_got += 1
            group.append(spec)
        info.spec_blobs.append(group)
        info.times.append(_fmt_time(time_rec, endian))
        info.n_records += 1
        info.n_spec_records += spec_got

    while header_left > 0:
        rec = _try_record(fh, marker, endian)
        if rec is None:
            break
        header_left -= 1
        if _looks_like_time(rec, endian):
            consume_time_group(rec)
            break
        _try_parse_interp(rec, info, endian)
        info.layout = f"endian={endian} marker={marker}"
    while True:
        rec = _try_record(fh, marker, endian)
        if rec is None:
            break
        if _looks_like_time(rec, endian):
            consume_time_group(rec)
            continue
        _try_parse_interp(rec, info, endian)
    if info.n_records < 1:
        raise BoundaryError("BOUNDARY_VERIFY_FAILED", tr("boundary_nest_no_times", "nest.ww3 没有时间记录"))
    info.layout = f"endian={endian} marker={marker} ident={ident!r}"
    return info


def _header_dims(payload: bytes, endian: str) -> tuple[int, int, int]:
    """IDSTRBC(32)+VERBPTBC(10) 之后为 NK, NTH, XFR, FR1, TH1, NBI。"""
    base = 42
    nk, nth = struct.unpack(endian + "ii", payload[base : base + 8])
    nbi = struct.unpack(endian + "i", payload[base + 20 : base + 24])[0]
    return int(nk), int(nth), int(nbi)


def _try_parse_interp(rec: bytes, info: NestFileInfo, endian: str) -> None:
    nbi = info.nbi
    if nbi < 1:
        return
    # XB(nbi)+YB(nbi) float32 + IP(nbi,4) int32 + RD(nbi,4) float32
    need = nbi * 4 * (2 + 4 + 4)
    if len(rec) != need:
        return
    off = 0
    n = nbi

    def take_f(count: int) -> list[float]:
        nonlocal off
        out = list(struct.unpack(endian + "f" * count, rec[off : off + 4 * count]))
        off += 4 * count
        return out

    def take_i(count: int) -> list[int]:
        nonlocal off
        out = list(struct.unpack(endian + "i" * count, rec[off : off + 4 * count]))
        off += 4 * count
        return out

    _xy_x = take_f(n)
    _xy_y = take_f(n)
    ip = take_i(4 * n)
    rd = take_f(4 * n)
    if max(abs(v) for v in ip) >= 10**7:
        return
    info.xb = [float(v) for v in _xy_x]
    info.yb = [float(v) for v in _xy_y]
    info.mapping_indices = [[ip[j * n + i] for j in range(4)] for i in range(n)]
    info.mapping_weights = [[rd[j * n + i] for j in range(4)] for i in range(n)]


def _unpack_ints(payload: bytes, endian: str) -> list[int]:
    n = len(payload)
    if n % 8 == 0:
        fmt = endian + "q" * (n // 8)
        values = list(struct.unpack(fmt, payload))
        if all(abs(v) < 10**12 for v in values):
            return [int(v) for v in values]
    if n % 4 == 0:
        fmt = endian + "i" * (n // 4)
        return [int(v) for v in struct.unpack(fmt, payload)]
    return []


def _unpack_floats(payload: bytes, endian: str) -> list[float]:
    n = len(payload)
    if n % 8 == 0:
        return list(struct.unpack(endian + "d" * (n // 8), payload))
    if n % 4 == 0:
        return list(struct.unpack(endian + "f" * (n // 4), payload))
    return []


def _looks_like_time(payload: bytes, endian: str) -> bool:
    ints = _unpack_ints(payload, endian)
    if len(ints) >= 2:
        ymd, hms = ints[0], ints[1]
        if 19000000 < ymd < 21000000 and 0 <= hms <= 235959:
            return True
    return False


def _time_nsource(payload: bytes, endian: str) -> int:
    ints = _unpack_ints(payload, endian)
    if len(ints) >= 3 and ints[2] > 0:
        return int(ints[2])
    raise BoundaryError("BOUNDARY_VERIFY_FAILED", tr("boundary_nest_time_no_count", "时间记录未给出该时刻的源谱条数"))


def _fmt_time(payload: bytes, endian: str) -> str:
    ints = _unpack_ints(payload, endian)
    ymd, hms = ints[0], ints[1]
    return f"{ymd:08d} {hms:06d}"


def compare_mapping_with_nest(
    mappings: list[BoundaryMapping],
    targets: list[BoundaryTargetPoint],
    info: NestFileInfo,
    *,
    method: str,
    source_index: dict[str, int] | None = None,
) -> None:
    if info.nbi != len(targets):
        raise BoundaryError(
            "BOUNDARY_VERIFY_FAILED",
            tr("boundary_nest_nbi_vs_targets", "nest 边界点数 {nbi} 与计划目标点数 {n_targets} 不一致").format(nbi=info.nbi, n_targets=len(targets)),
            context={"nbi": info.nbi, "n_target": len(targets)},
        )
    _compare_nest_geometry_and_sources(
        mappings,
        targets,
        info,
        method=method,
        source_index=source_index,
        check_linear_weights=str(method).lower() == "linear",
    )


def _compare_nest_geometry_and_sources(
    mappings: list[BoundaryMapping],
    targets: list[BoundaryTargetPoint],
    info: NestFileInfo,
    *,
    method: str,
    source_index: dict[str, int] | None,
    check_linear_weights: bool,
) -> None:
    if not info.mapping_indices or not info.xb or not info.yb:
        raise BoundaryError(
            "BOUNDARY_VERIFY_FAILED",
            tr("boundary_nest_no_mapping", "未能从 nest.ww3 提取边界坐标或映射索引"),
            context={"layout": info.layout, "method": method},
        )
    if len(info.mapping_indices) != len(targets) or len(info.xb) != len(targets):
        raise BoundaryError(
            "BOUNDARY_VERIFY_FAILED",
            tr("boundary_nest_mapping_count", "nest 映射条数与目标点数不一致"),
            context={"n_map": len(info.mapping_indices), "n_target": len(targets)},
        )
    if not source_index:
        raise BoundaryError(
            "BOUNDARY_VERIFY_FAILED",
            tr("boundary_verify_needs_index", "验收需要规范化谱在 spec.list 中的 1-based 索引"),
        )
    by_id = {item.target_id: item for item in mappings}

    def nest_row_for(target: BoundaryTargetPoint) -> int:
        best_i = 0
        best_d = abs(float(info.xb[0]) - float(target.lon)) + abs(float(info.yb[0]) - float(target.lat))
        for i, (x, y) in enumerate(zip(info.xb, info.yb)):
            d = abs(float(x) - float(target.lon)) + abs(float(y) - float(target.lat))
            if d < best_d:
                best_i, best_d = i, d
        if best_d > 1e-3:
            raise BoundaryError(
                "BOUNDARY_VERIFY_FAILED",
                tr("boundary_nest_coords_mismatch", "nest 边界点坐标与计划目标不一致"),
                context={"target_id": target.point_id, "delta": best_d, "method": method},
            )
        return best_i

    for target in targets:
        mapped = by_id.get(target.point_id)
        if mapped is None:
            raise BoundaryError("BOUNDARY_VERIFY_FAILED", tr("boundary_preview_missing_target", "缺少目标 {target_id} 的预览映射").format(target_id=target.point_id))
        row = nest_row_for(target)
        nest_ip = [int(v) for v in info.mapping_indices[row][:2]]
        nest_rd = [float(v) for v in (info.mapping_weights[row][:2] if info.mapping_weights else [1.0, 0.0])]
        preview_ip = []
        for source_id in mapped.source_ids[:2]:
            if source_id not in source_index:
                raise BoundaryError(
                    "BOUNDARY_VERIFY_FAILED",
                    tr("boundary_preview_source_not_listed", "预览源 {source_id} 不在 spec.list 中").format(source_id=source_id),
                )
            preview_ip.append(int(source_index[source_id]))
        if not preview_ip:
            raise BoundaryError("BOUNDARY_VERIFY_FAILED", tr("boundary_target_no_source_index", "目标 {target_id} 没有来源索引").format(target_id=target.point_id))
        if not check_linear_weights:
            if int(nest_ip[0]) != int(preview_ip[0]):
                raise BoundaryError(
                    "BOUNDARY_VERIFY_FAILED",
                    tr("boundary_nearest_source_mismatch", "预览主源点与 ww3_bounc 实际映射不一致"),
                    context={"target_id": target.point_id, "preview": preview_ip[0], "nest": nest_ip[0], "method": method},
                )
            continue
        preview_w = list(mapped.weights[:2])
        if len(preview_ip) >= 2 and sorted(nest_ip) != sorted(preview_ip):
            raise BoundaryError(
                "BOUNDARY_VERIFY_FAILED",
                tr("boundary_linear_sources_mismatch", "linear 预览源点与 ww3_bounc 实际映射不一致"),
                context={"target_id": target.point_id, "preview": preview_ip, "nest": nest_ip},
            )
        w_by_ip = {int(preview_ip[j]): float(preview_w[j]) for j in range(len(preview_ip))}
        for ip, rd in zip(nest_ip, nest_rd):
            expected = w_by_ip.get(int(ip))
            if expected is None:
                continue
            if abs(float(rd) - float(expected)) > 0.02:
                raise BoundaryError(
                    "BOUNDARY_VERIFY_FAILED",
                    tr("boundary_linear_weights_mismatch", "linear 预览权重与 ww3_bounc 实际权重不一致"),
                    context={
                        "target_id": target.point_id,
                        "source_index": ip,
                        "preview": expected,
                        "nest": rd,
                    },
                )


def _decode_spec_blobs(info: NestFileInfo, endian: str) -> None:
    import numpy as np

    nk, nth = int(info.nk), int(info.nth)
    nfloat = nk * nth
    decoded: list[list[Any]] = []
    for group in info.spec_blobs:
        row = []
        for blob in group:
            if len(blob) == nfloat * 4:
                arr = np.frombuffer(blob, dtype=endian + "f4")
            elif len(blob) == nfloat * 8:
                arr = np.frombuffer(blob, dtype=endian + "f8")
            else:
                raise BoundaryError(
                    "BOUNDARY_VERIFY_FAILED",
                    tr("boundary_nest_decode_failed", "谱记录无法按 NK×NTH 解码"),
                    context={"nbytes": len(blob), "nk": nk, "nth": nth, "content": True},
                )
            values = np.array(arr, dtype=np.float64, copy=True)
            if not np.isfinite(values).all():
                n_bad = int(np.size(values) - np.isfinite(values).sum())
                raise BoundaryError(
                    "BOUNDARY_VERIFY_FAILED",
                    tr("boundary_nest_nonfinite", "nest.ww3 谱值含非有限值（{n_bad} 个）").format(n_bad=n_bad),
                    context={"n_invalid": n_bad, "content": True},
                )
            row.append(values.reshape(nk, nth))
        decoded.append(row)
    info.spectra = decoded


def sample_compare_nest_spectra(info: NestFileInfo, workdir: Path, plan: Any) -> None:
    """抽样核对不同源文件的 nest 谱与规范化 NetCDF。ww3_bounc 写出时乘 1/(2π)。"""
    import math

    import numpy as np

    from ...support.netcdf_serialization import serialized_dataset

    rels = list(getattr(plan, "normalized_relpaths", None) or [])
    if not info.spectra or not rels:
        raise BoundaryError("BOUNDARY_VERIFY_FAILED", tr("boundary_verify_no_samples", "无法抽样核对谱值：缺少 nest 谱或规范化文件"))
    nsource = len(info.spectra[0])
    if nsource != len(rels):
        raise BoundaryError(
            "BOUNDARY_VERIFY_FAILED",
            tr("boundary_nest_count_vs_speclist", "nest 每个时刻的源谱条数与 spec.list 不一致"),
            context={"n_spec": nsource, "n_files": len(rels)},
        )
    tpiinv = 1.0 / (2.0 * math.pi)
    sample_t = {0, len(info.spectra) - 1}
    sample_s = {0, nsource - 1}
    for it in sorted(sample_t):
        for isrc in sorted(sample_s):
            nest = np.asarray(info.spectra[it][isrc], dtype=np.float64)
            path = Path(workdir) / rels[isrc]
            if not path.is_file():
                raise BoundaryError("BOUNDARY_VERIFY_FAILED", tr("boundary_normalized_missing", "规范化谱不存在：{path}").format(path=path))
            with serialized_dataset(str(path), "r") as ds:
                efth = np.array(ds.variables["efth"][it, 0, :, :], dtype=np.float64)
            expected = efth * tpiinv
            if nest.shape != expected.shape:
                raise BoundaryError(
                    "BOUNDARY_VERIFY_FAILED",
                    tr("boundary_sample_shape_mismatch", "抽样谱形状与规范化文件不一致"),
                    context={"nest": list(nest.shape), "nc": list(expected.shape)},
                )
            if np.allclose(nest, expected, rtol=5e-3, atol=1e-8):
                continue
            raise BoundaryError(
                "BOUNDARY_VERIFY_FAILED",
                tr("boundary_nest_sample_mismatch", "nest 抽样谱值与规范化输入不一致"),
                context={"time_index": it, "source_index": isrc + 1, "nest_max": float(np.max(nest)), "nc_max": float(np.max(expected))},
            )


def memory_estimate_bytes(n_station: int, n_time: int, n_freq: int, n_dir: int) -> int:
    return 3 * 4 * int(n_station) * int(n_time) * int(n_freq) * int(n_dir) + 256 * 2**20
