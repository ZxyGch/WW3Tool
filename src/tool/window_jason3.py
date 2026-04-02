"""
Jason-3 download helpers for the plotting page.
"""

import multiprocessing
import os
import re
import json
import tempfile
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from multiprocessing import Process, Queue
from urllib.parse import urljoin

import requests
from PyQt6 import QtCore
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from plot.workers_jason3 import Jason3ServiceMixin
from setting.config import DEFAULT_CONFIG, load_config, ensure_project_data_dir
from setting.language_manager import tr

if hasattr(multiprocessing, "set_start_method"):
    try:
        multiprocessing.set_start_method("spawn", force=True)
    except RuntimeError:
        pass


_JASON3_TIME_PATTERN = re.compile(r"(\d{8}_\d{6})_(\d{8}_\d{6})")
_HTML_HREF_PATTERN = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
_CATALOG_TIMEOUT = (20, 60)
_DOWNLOAD_TIMEOUT = (20, 180)
_CATALOG_CACHE_TTL_SECONDS = 24 * 60 * 60
_CATALOG_SCAN_WORKERS = 4
_HTTP_RETRY_TOTAL = 3
_HTTP_RETRY_BACKOFF_FACTOR = 0.8
_JASON3_SOURCE_SPECS = (
    ("GDR", "gdr/gdr/", ("JA3_GPN_",)),
    ("IGDR", "igdr/igdr/", ("JA3_IPN_",)),
    ("OGDR", "ogdr/ogdr/", ("JA3_OPN_",)),
)


def _queue_log(log_queue, message, update=False):
    try:
        if update:
            log_queue.put(("__UPDATE__", message))
        else:
            log_queue.put(message)
    except Exception:
        pass


def _parse_time_range(time_range):
    start_str, end_str = time_range
    start_dt = datetime.strptime(start_str + "_000000", "%Y%m%d_%H%M%S")
    end_dt = datetime.strptime(end_str + "_235959", "%Y%m%d_%H%M%S")
    return start_dt, end_dt


def _parse_filename_time_range(filename):
    match = _JASON3_TIME_PATTERN.search(filename)
    if not match:
        return None
    return (
        datetime.strptime(match.group(1), "%Y%m%d_%H%M%S"),
        datetime.strptime(match.group(2), "%Y%m%d_%H%M%S"),
    )


def _ranges_overlap(start_a, end_a, start_b, end_b):
    return end_a >= start_b and start_a <= end_b


def _fetch_text(session, url):
    response = session.get(url, timeout=_CATALOG_TIMEOUT)
    response.raise_for_status()
    return response.text


def _build_retry_session():
    session = requests.Session()
    session.headers.update({"User-Agent": "WW3Tool Jason3 Downloader"})

    retry = Retry(
        total=_HTTP_RETRY_TOTAL,
        connect=_HTTP_RETRY_TOTAL,
        read=_HTTP_RETRY_TOTAL,
        status=_HTTP_RETRY_TOTAL,
        backoff_factor=_HTTP_RETRY_BACKOFF_FACTOR,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=_CATALOG_SCAN_WORKERS, pool_maxsize=_CATALOG_SCAN_WORKERS)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _iter_days(start_dt, end_dt):
    current_day = start_dt.date()
    end_day = end_dt.date()
    while current_day <= end_day:
        yield current_day
        current_day += timedelta(days=1)


def _covered_days_for_filename(filename, start_dt, end_dt):
    file_time = _parse_filename_time_range(filename)
    if not file_time:
        return set()
    file_start, file_end = file_time
    if not _ranges_overlap(file_start, file_end, start_dt, end_dt):
        return set()
    covered = set()
    for current_day in _iter_days(max(file_start, start_dt), min(file_end, end_dt)):
        covered.add(current_day)
    return covered


def _extract_links(html_text):
    return _HTML_HREF_PATTERN.findall(html_text)


def _catalog_cache_path(cache_key):
    digest = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()[:16]
    return os.path.join(tempfile.gettempdir(), f"ww3tool_jason3_catalog_cache_{digest}.json")


def _load_catalog_cache(cache_key):
    cache_path = _catalog_cache_path(cache_key)
    if not os.path.exists(cache_path):
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as file_obj:
            cache = json.load(file_obj)
    except Exception:
        return None

    if cache.get("cache_key") != cache_key:
        return None

    updated_at = cache.get("updated_at", 0)
    if not isinstance(updated_at, (int, float)):
        return None

    age_seconds = datetime.now().timestamp() - float(updated_at)
    if age_seconds > _CATALOG_CACHE_TTL_SECONDS:
        return None

    files = cache.get("files")
    if not isinstance(files, dict):
        return None

    return files


def _save_catalog_cache(cache_key, files):
    cache_path = _catalog_cache_path(cache_key)
    payload = {
        "cache_key": cache_key,
        "updated_at": datetime.now().timestamp(),
        "files": files,
    }
    try:
        with open(cache_path, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False)
    except Exception:
        pass


def _build_source_url(base_root_url, relative_path):
    root = base_root_url.rstrip("/") + "/"
    return urljoin(root, relative_path)


def _source_cache_key(source_name, source_url):
    return f"{source_name}:{source_url}"


def _collect_cycle_directories(session, source_url):
    html_text = _fetch_text(session, source_url)
    cycle_urls = []
    for href in _extract_links(html_text):
        if "cycle" not in href.lower():
            continue
        if not href.endswith("/"):
            continue
        cycle_urls.append(urljoin(source_url, href))
    return sorted(set(cycle_urls))


def _scan_cycle_directory(cycle_url, prefixes):
    session = _build_retry_session()
    try:
        html_text = _fetch_text(session, cycle_url)
    finally:
        session.close()

    cycle_candidates = {}
    for href in _extract_links(html_text):
        filename = os.path.basename(href.rstrip("/"))
        if not filename or not filename.endswith(".nc"):
            continue
        if not filename.startswith(prefixes):
            continue
        cycle_candidates[filename] = urljoin(cycle_url, href)

    return cycle_candidates


def _scan_cycle_directory_with_retry(cycle_url, prefixes):
    last_exc = None
    for attempt in range(2):
        try:
            return _scan_cycle_directory(cycle_url, prefixes)
        except Exception as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(0.6)
    raise last_exc


def _filter_remote_candidates(files, start_dt, end_dt):
    matched = []
    for filename, file_url in files.items():
        file_time = _parse_filename_time_range(filename)
        if not file_time:
            continue
        file_start, file_end = file_time
        if _ranges_overlap(file_start, file_end, start_dt, end_dt):
            matched.append((filename, file_url))
    return sorted(matched, key=lambda item: item[0])


def _source_priority(start_dt, end_dt):
    today = datetime.now().date()
    days_from_end = (today - end_dt.date()).days
    if days_from_end <= 2:
        return ("OGDR", "IGDR", "GDR")
    if days_from_end <= 60:
        return ("IGDR", "GDR", "OGDR")
    return ("GDR", "IGDR", "OGDR")


def _collect_source_files(session, base_root_url, source_name, relative_path, prefixes, log_queue):
    source_url = _build_source_url(base_root_url, relative_path)
    cache_key = _source_cache_key(source_name, source_url)
    cached_files = _load_catalog_cache(cache_key)
    if cached_files:
        _queue_log(
            log_queue,
            tr(
                "plotting_jason_catalog_cache_hit",
                "⚡ 使用本地远程索引缓存，跳过远程全量扫描。",
            ) + f" [{source_name}]",
        )
        return cached_files

    _queue_log(
        log_queue,
        tr("plotting_jason_fetch_catalog", "🔄 正在查询 NCEI Jason-3 目录...") + f" [{source_name}]",
    )

    cycle_urls = _collect_cycle_directories(session, source_url)
    _queue_log(
        log_queue,
        tr(
            "plotting_jason_cycle_catalogs_found",
            "📚 远程目录中找到 {count} 个 cycle catalog",
        ).format(count=len(cycle_urls)) + f" [{source_name}]",
    )

    _queue_log(
        log_queue,
        tr(
            "plotting_jason_parallel_scan_start",
            "🚀 正在并发构建远程文件索引...",
        ) + f" [{source_name}]",
    )

    all_files = {}
    completed = 0
    with ThreadPoolExecutor(max_workers=_CATALOG_SCAN_WORKERS) as executor:
        future_map = {
            executor.submit(_scan_cycle_directory_with_retry, cycle_url, prefixes): cycle_url
            for cycle_url in cycle_urls
        }
        total = len(future_map)

        for future in as_completed(future_map):
            completed += 1
            cycle_url = future_map[future]
            if completed == 1 or completed % 25 == 0 or completed == total:
                _queue_log(
                    log_queue,
                    tr(
                        "plotting_jason_cycle_scan_progress",
                        "🔍 正在扫描远程目录 {current}/{total}",
                    ).format(current=completed, total=total) + f" [{source_name}]",
                    update=True,
                )

            try:
                all_files.update(future.result())
            except Exception as exc:
                _queue_log(
                    log_queue,
                    tr(
                        "plotting_jason_catalog_fetch_failed",
                        "⚠️ 读取远程目录失败：{url} -> {error}",
                    ).format(url=cycle_url, error=exc),
                )

    _save_catalog_cache(cache_key, all_files)
    _queue_log(
        log_queue,
        tr(
            "plotting_jason_catalog_cache_saved",
            "💾 已缓存远程文件索引，后续下载会更快。",
        ) + f" [{source_name}]",
    )
    return all_files


def _collect_remote_candidates(session, base_root_url, start_dt, end_dt, log_queue):
    source_map = {name: (relative_path, prefixes) for name, relative_path, prefixes in _JASON3_SOURCE_SPECS}
    requested_days = set(_iter_days(start_dt, end_dt))
    covered_days = set()
    merged_candidates = {}

    for source_name in _source_priority(start_dt, end_dt):
        relative_path, prefixes = source_map[source_name]
        files = _collect_source_files(
            session, base_root_url, source_name, relative_path, prefixes, log_queue
        )
        source_matches = _filter_remote_candidates(files, start_dt, end_dt)

        for filename, file_url in source_matches:
            merged_candidates.setdefault(filename, file_url)
            covered_days.update(_covered_days_for_filename(filename, start_dt, end_dt))

        _queue_log(
            log_queue,
            tr(
                "plotting_jason_remote_candidates_found",
                "✅ 找到 {count} 个符合时间范围的远程文件",
            ).format(count=len(source_matches)) + f" [{source_name}]",
        )

        missing_days = sorted(requested_days - covered_days)
        if not missing_days:
            _queue_log(
                log_queue,
                tr(
                    "plotting_jason_source_coverage_complete",
                    "✅ 当前产品层级已覆盖所需日期，无需继续回退。",
                ),
            )
            break

        if source_name != _source_priority(start_dt, end_dt)[-1]:
            missing_text = ", ".join(day.strftime("%Y%m%d") for day in missing_days[:6])
            if len(missing_days) > 6:
                missing_text += ", ..."
            _queue_log(
                log_queue,
                tr(
                    "plotting_jason_source_missing_days",
                    "⚠️ 当前产品层级仍缺少 {count} 天，继续尝试下一档：{days}",
                ).format(count=len(missing_days), days=missing_text),
            )

    matched = sorted(merged_candidates.items(), key=lambda item: item[0])
    _queue_log(
        log_queue,
        tr(
            "plotting_jason_remote_candidates_found",
            "✅ 找到 {count} 个符合时间范围的远程文件",
        ).format(count=len(matched)),
    )
    return matched


def _download_jason3_worker(time_range, local_folder, base_catalog_url, log_queue, result_queue):
    try:
        from setting.language_manager import load_language

        current_config = load_config()
        load_language(current_config.get("LANGUAGE", "zh_CN"))

        start_dt, end_dt = _parse_time_range(time_range)

        session = _build_retry_session()

        remote_candidates = _collect_remote_candidates(
            session, base_catalog_url, start_dt, end_dt, log_queue
        )
        if not remote_candidates:
            _queue_log(
                log_queue,
                tr(
                    "plotting_jason_download_no_remote_files",
                    "⚠️ 远程目录中没有符合时间范围的 Jason-3 文件。",
                ),
            )
            result_queue.put(
                {"ok": False, "downloaded": 0, "skipped": 0, "failed": 0, "total": 0}
            )
            log_queue.put("__DONE__")
            return

        local_existing = set(os.listdir(local_folder))
        to_download = []
        skipped = 0
        for filename, file_url in remote_candidates:
            if filename in local_existing:
                skipped += 1
                continue
            to_download.append((filename, file_url))

        if skipped:
            _queue_log(
                log_queue,
                tr(
                    "plotting_jason_skip_existing_files",
                    "ℹ️ 跳过 {count} 个本地已存在的文件",
                ).format(count=skipped),
            )

        if not to_download:
            _queue_log(
                log_queue,
                tr(
                    "plotting_jason_download_already_complete",
                    "✅ 当前时间范围所需文件已在本地，无需下载。",
                ),
            )
            result_queue.put(
                {
                    "ok": True,
                    "downloaded": 0,
                    "skipped": skipped,
                    "failed": 0,
                    "total": len(remote_candidates),
                }
            )
            log_queue.put("__DONE__")
            return

        downloaded = 0
        failed = 0

        for filename, file_url in to_download:
            local_path = os.path.join(local_folder, filename)
            temp_path = local_path + ".part"
            _queue_log(
                log_queue,
                tr(
                    "plotting_jason_start_file_download",
                    "⬇️ 开始下载 {file}",
                ).format(file=filename),
            )

            try:
                with session.get(file_url, stream=True, timeout=_DOWNLOAD_TIMEOUT) as response:
                    response.raise_for_status()
                    total_size = int(response.headers.get("Content-Length", "0") or "0")
                    transferred = 0
                    last_percent = -1

                    with open(temp_path, "wb") as file_obj:
                        for chunk in response.iter_content(chunk_size=1024 * 256):
                            if not chunk:
                                continue
                            file_obj.write(chunk)
                            transferred += len(chunk)

                            if total_size > 0:
                                percent = int(transferred / total_size * 100)
                                if percent > last_percent:
                                    last_percent = percent
                                    _queue_log(
                                        log_queue,
                                        tr(
                                            "plotting_jason_download_progress",
                                            "下载 Jason-3 {file} ... {percent}%",
                                        ).format(file=filename, percent=percent),
                                        update=True,
                                    )

                os.replace(temp_path, local_path)
                downloaded += 1
                _queue_log(
                    log_queue,
                    tr(
                        "plotting_jason_file_download_complete",
                        "✅ 下载完成 {file}",
                    ).format(file=filename),
                    update=True,
                )
            except Exception as exc:
                failed += 1
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except OSError:
                    pass
                _queue_log(
                    log_queue,
                    tr(
                        "plotting_jason_download_failed_file",
                        "❌ 下载 Jason-3 文件失败：{file} -> {error}",
                    ).format(file=filename, error=exc),
                )

        _queue_log(
            log_queue,
            tr(
                "plotting_jason_download_summary",
                "📦 下载完成：共 {total} 个候选文件，新增 {downloaded} 个，跳过 {skipped} 个，失败 {failed} 个。",
            ).format(
                total=len(remote_candidates),
                downloaded=downloaded,
                skipped=skipped,
                failed=failed,
            ),
        )
        result_queue.put(
            {
                "ok": failed == 0,
                "downloaded": downloaded,
                "skipped": skipped,
                "failed": failed,
                "total": len(remote_candidates),
            }
        )
    except Exception as exc:
        _queue_log(
            log_queue,
            tr(
                "plotting_jason_download_process_failed",
                "❌ JASON3 下载失败：{error}",
            ).format(error=exc),
        )
        result_queue.put({"ok": False, "downloaded": 0, "skipped": 0, "failed": 1, "total": 0})
    finally:
        try:
            session.close()
        except Exception:
            pass
        try:
            log_queue.put("__DONE__")
        except Exception:
            pass


class Jason3Mixin(Jason3ServiceMixin):
    """Jason-3 download features for the UI."""

    def download_jason3_range(self):
        """Download Jason-3 files for the requested date range."""
        start_str = self.shel_start_step9_edit.text().strip() if hasattr(self, "shel_start_step9_edit") else ""
        end_str = self.shel_end_step9_edit.text().strip() if hasattr(self, "shel_end_step9_edit") else ""
        if not start_str or not end_str:
            self.log_signal.emit(tr("plotting_fill_time_range", "❌ 请填写开始和结束时间（格式：YYYYMMDD）"))
            return

        if not re.fullmatch(r"\d{8}", start_str) or not re.fullmatch(r"\d{8}", end_str):
            self.log_signal.emit(
                tr(
                    "plotting_jason_invalid_time_format",
                    "❌ 时间格式错误，请使用 YYYYMMDD。",
                )
            )
            return

        try:
            start_dt = datetime.strptime(start_str, "%Y%m%d")
            end_dt = datetime.strptime(end_str, "%Y%m%d")
        except ValueError:
            self.log_signal.emit(
                tr(
                    "plotting_jason_invalid_time_format",
                    "❌ 时间格式错误，请使用 YYYYMMDD。",
                )
            )
            return

        if start_dt > end_dt:
            self.log_signal.emit(
                tr(
                    "plotting_jason_start_after_end",
                    "❌ 开始时间不能晚于结束时间。",
                )
            )
            return

        local_folder = self.jason_folder_edit.text().strip() if hasattr(self, "jason_folder_edit") else ""
        if not local_folder or not os.path.isdir(local_folder):
            local_folder = ensure_project_data_dir("JASON_PATH", "jason3")
            if hasattr(self, "jason_folder_edit") and self.jason_folder_edit:
                self.jason_folder_edit.setText(local_folder)

        self.btn_download_jason3.setEnabled(False)
        self.btn_download_jason3.setText(tr("plotting_jason_downloading", "下载中..."))
        self._run_download_jason3_process([start_str, end_str], local_folder)

    def _run_download_jason3_process(self, time_range, local_folder):
        """Run Jason-3 download in a background process."""
        current_config = load_config()
        base_catalog_url = current_config.get(
            "JASON3_DOWNLOAD_BASE_URL",
            DEFAULT_CONFIG.get("JASON3_DOWNLOAD_BASE_URL", ""),
        ).strip() or DEFAULT_CONFIG["JASON3_DOWNLOAD_BASE_URL"]

        log_queue = Queue()
        result_queue = Queue()
        process = Process(
            target=_download_jason3_worker,
            args=(time_range, local_folder, base_catalog_url, log_queue, result_queue),
        )
        process.start()

        def _poll_logs():
            try:
                done = False
                while True:
                    try:
                        message = log_queue.get_nowait()
                        if message == "__DONE__":
                            done = True
                            break
                        if (
                            isinstance(message, tuple)
                            and len(message) == 2
                            and message[0] == "__UPDATE__"
                        ):
                            self.log_update_last_line_signal.emit(message[1])
                        else:
                            self.log_signal.emit(message)
                    except Exception:
                        break

                if not done and process.is_alive():
                    QtCore.QTimer.singleShot(100, _poll_logs)
                    return

                if process.is_alive():
                    process.join(timeout=1)
                if process.is_alive():
                    process.terminate()
                    process.join()

                try:
                    result = result_queue.get_nowait()
                    if result.get("failed", 0) > 0:
                        self.log_signal.emit(
                            tr(
                                "plotting_jason_download_partial_failed",
                                "⚠️ 部分文件下载失败，请查看上方日志。",
                            )
                        )
                except Exception:
                    pass

            except Exception as exc:
                self.log_signal.emit(
                    tr(
                        "plotting_jason_download_process_failed",
                        "❌ JASON3 下载失败：{error}",
                    ).format(error=exc)
                )
            finally:
                self._restore_download_jason3_button()

        _poll_logs()

    def _restore_download_jason3_button(self):
        if hasattr(self, "btn_download_jason3"):
            self.btn_download_jason3.setEnabled(True)
            self.btn_download_jason3.setText(
                tr("plotting_download_jason3", "下载 JASON 3 数据")
            )
