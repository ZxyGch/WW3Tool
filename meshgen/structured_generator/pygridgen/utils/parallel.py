"""
Parallel Processing Utilities

Worker-count resolution and a small process-pool helper shared by the gridgen
stages.  The point of the module is that the number of workers must reflect
what the *scheduler* gave us, not what the machine happens to have: on a Slurm
node ``os.cpu_count()`` reports every core of the box while the job may only
own a handful of them, and oversubscribing a cpuset is markedly slower than
running serially.
"""

import os
import sys

_ENV_OVERRIDE = "WW3TOOL_MESHGEN_WORKERS"

# Thread knobs of the numeric libraries.  Workers are processes, so each one
# spinning up its own BLAS/OpenMP thread pool would multiply the core count.
_THREAD_ENV = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


def _int_env(name):
    """Read a positive integer from the environment, or None."""
    raw = os.environ.get(name)
    if not raw:
        return None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def available_cpus():
    """Number of CPUs this process may actually run on.

    Honours, in order: the ``WW3TOOL_MESHGEN_WORKERS`` override, Slurm's
    per-task allocation, the scheduler affinity mask (which is what cgroup /
    cpuset confinement shows up as), and finally the machine core count.
    """
    for name in (_ENV_OVERRIDE, "SLURM_CPUS_PER_TASK", "SLURM_CPUS_ON_NODE"):
        value = _int_env(name)
        if value is not None:
            return value

    if hasattr(os, "sched_getaffinity"):
        try:
            return max(1, len(os.sched_getaffinity(0)))
        except OSError:
            pass

    return max(1, os.cpu_count() or 1)


def startup_penalty():
    """How expensive a worker process is to start, relative to ``fork``.

    ``fork`` shares the parent image and costs almost nothing; ``spawn`` (macOS
    and Windows) re-imports numpy, scipy and matplotlib in every worker, which
    is seconds; ``forkserver`` sits in between.  Stages use this to decide how much work must be on the table
    before a pool is worth it.
    """
    import multiprocessing as mp

    try:
        method = mp.get_start_method(allow_none=False)
    except (ValueError, RuntimeError):
        return 8
    return {"fork": 1, "forkserver": 4}.get(method, 8)


def resolve_workers(n_items=None, min_chunk=1, requested=None):
    """Pick a worker count for a job of *n_items* units of work.

    Never returns more workers than there is work to hand out, so small grids
    fall back to a single process instead of paying pool start-up for nothing.
    ``min_chunk`` is the work per worker that makes a pool worthwhile under
    ``fork``; it is scaled up where starting a worker costs more.
    """
    workers = requested if requested and requested > 0 else available_cpus()
    workers = max(1, int(workers))
    if requested and requested > 0:
        return workers
    if n_items is not None:
        chunk = max(1, int(min_chunk) * startup_penalty())
        workers = max(1, min(workers, int(n_items) // chunk))
    return workers


def limit_worker_threads():
    """Pin the numeric libraries to one thread. Call from a pool initializer."""
    for name in _THREAD_ENV:
        os.environ[name] = "1"


def describe_cpu_budget():
    """One-line summary of where the worker count came from (for the log)."""
    source = "os.cpu_count()"
    for name in (_ENV_OVERRIDE, "SLURM_CPUS_PER_TASK", "SLURM_CPUS_ON_NODE"):
        if _int_env(name) is not None:
            source = name
            break
    else:
        if hasattr(os, "sched_getaffinity"):
            source = "sched_getaffinity"
    return f"{available_cpus()} CPUs (from {source})"




def _self_rss_bytes():
    """This process's resident size, without depending on psutil."""
    try:
        import resource
    except ImportError:
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if not peak:
        return None
    # ru_maxrss is bytes on macOS/BSD and kilobytes on Linux.
    return peak if sys.platform == "darwin" else peak * 1024


# Captured while only the interpreter and the numeric libraries are loaded, so
# it is a fair estimate of what a *spawned* worker needs before it touches any
# of our data.  Under fork a worker shares those pages instead, and this term
# does not apply.
_IMPORT_BASELINE_RSS = _self_rss_bytes() or 0


def worker_baseline_bytes():
    """Memory a fresh worker costs before it is sent anything.

    On spawn platforms (macOS, Windows) that is a whole new interpreter with
    numpy, scipy and matplotlib re-imported -- in practice the largest
    per-worker term by far.  Under fork the pages are shared copy-on-write.
    """
    import multiprocessing as mp

    try:
        method = mp.get_start_method(allow_none=False)
    except (ValueError, RuntimeError):
        method = "spawn"
    if method == "fork":
        return 0
    return _IMPORT_BASELINE_RSS


_MEM_ENV_OVERRIDE = "WW3TOOL_MESHGEN_MEM_MB"

# Of whatever memory we believe we may use, this much is handed to the worker
# pool.  The rest covers the parent's own arrays, the interpreter, and the
# fact that every estimate here is a lower bound on real RSS.
_POOL_MEMORY_SHARE = 0.5


def _read_int_file(path):
    """First integer in *path*, or None. cgroup limits read as 'max' when off."""
    try:
        with open(path, "r") as handle:
            raw = handle.read().strip().split()[0]
    except (OSError, IndexError):
        return None
    if raw in ("max", "-1"):
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    # cgroup v1 writes a sentinel near 2**63 to mean "no limit".
    return value if 0 < value < (1 << 62) else None


def _cgroup_memory_limit():
    """Memory this container/cgroup may use, minus what it already holds.

    Slurm confines a job with cgroups, so this is the number that decides
    whether the job gets OOM-killed -- not the size of the node.
    """
    for limit_path, usage_path in (
        ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current"),
        ("/sys/fs/cgroup/memory/memory.limit_in_bytes",
         "/sys/fs/cgroup/memory/memory.usage_in_bytes"),
    ):
        limit = _read_int_file(limit_path)
        if limit is None:
            continue
        used = _read_int_file(usage_path) or 0
        return max(0, limit - used)
    return None


def _slurm_memory_limit():
    """Bytes Slurm allocated to this task, from the usual MB-valued knobs."""
    per_node = _int_env("SLURM_MEM_PER_NODE")
    if per_node is not None:
        return per_node * (1 << 20)
    per_cpu = _int_env("SLURM_MEM_PER_CPU")
    if per_cpu is not None:
        return per_cpu * available_cpus() * (1 << 20)
    return None


def _sysconf(name):
    """``os.sysconf`` that returns None instead of raising on absent keys."""
    try:
        value = os.sysconf(name)
    except (ValueError, OSError, AttributeError):
        return None
    return value if value and value > 0 else None


def _macos_available_memory():
    """Free + reclaimable memory on macOS, which has no SC_AVPHYS_PAGES."""
    if sys.platform != "darwin":
        return None
    import subprocess

    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True,
                             timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    page = _sysconf("SC_PAGE_SIZE") or 4096
    pages = 0
    for line in out.splitlines():
        for label in ("Pages free:", "Pages inactive:", "Pages speculative:"):
            if line.startswith(label):
                try:
                    pages += int(line.split(":")[1].strip().rstrip("."))
                except (IndexError, ValueError):
                    pass
    return pages * page if pages else None


def _system_available_memory():
    """Free physical memory, by whatever route the platform offers.

    Falls back to total physical memory: worse than a real "available"
    reading, but still far better than assuming the pool can be as wide as
    the core count.
    """
    try:
        with open("/proc/meminfo", "r") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except (OSError, IndexError, ValueError):
        pass

    page = _sysconf("SC_PAGE_SIZE")
    avail = _sysconf("SC_AVPHYS_PAGES")
    if page and avail:
        return page * avail

    mac = _macos_available_memory()
    if mac:
        return mac

    total = _sysconf("SC_PHYS_PAGES")
    if page and total:
        return page * total
    return None


def available_memory_bytes():
    """Memory this process may reasonably use, or None if it cannot be told.

    Order matters: an explicit override wins, then the cgroup limit that
    actually triggers the OOM killer under Slurm, then Slurm's own accounting,
    and only then the free memory of the machine.
    """
    override = _int_env(_MEM_ENV_OVERRIDE)
    if override is not None:
        return override * (1 << 20)

    limits = [value for value in (_cgroup_memory_limit(), _slurm_memory_limit())
              if value is not None]
    if limits:
        return min(limits)
    return _system_available_memory()


def describe_memory_budget():
    """One-line summary of the memory budget (for the log)."""
    total = available_memory_bytes()
    if total is None:
        return "memory budget unknown"
    source = "system"
    if _int_env(_MEM_ENV_OVERRIDE) is not None:
        source = _MEM_ENV_OVERRIDE
    elif _cgroup_memory_limit() is not None:
        source = "cgroup"
    elif _slurm_memory_limit() is not None:
        source = "Slurm"
    return f"{total / (1 << 30):.1f} GiB usable (from {source})"


def cap_workers_for_memory(n_workers, per_worker_bytes, label=""):
    """Reduce *n_workers* so the pool fits the memory budget.

    Every worker holds its own copy of what it is sent, so a wide pool is a
    way to run out of memory on a machine that had plenty for one process.
    Returns at least 1: with no budget left the caller still has to do the
    work, just serially.
    """
    n_workers = max(1, int(n_workers))
    if n_workers == 1 or not per_worker_bytes or per_worker_bytes <= 0:
        return n_workers

    budget = available_memory_bytes()
    if budget is None:
        return n_workers

    affordable = int((budget * _POOL_MEMORY_SHARE) // per_worker_bytes)
    if affordable >= n_workers:
        return n_workers

    capped = max(1, affordable)
    where = f" for {label}" if label else ""
    print(
        f'  Memory budget{where}: {describe_memory_budget()}, '
        f'~{per_worker_bytes / (1 << 20):.0f} MiB per worker '
        f'-> using {capped} of {n_workers} workers.',
        flush=True,
    )
    return capped



# Grid-proportional cost of a run, measured over 0.16M / 0.64M / 2.56M cell
# grids: the arrays the parent keeps (bathymetry, mask, obstructions, cell
# geometry) plus the base bathymetry window.  Deliberately on the high side --
# the point is to catch "this will never fit", not to predict to the megabyte.
_BYTES_PER_CELL_ESTIMATE = 320

# Estimates run about 10-15% under measured RSS, and running out of memory is
# far more expensive than declining to start, so require some slack.
_MEMORY_SAFETY_MARGIN = 1.25


def estimate_peak_bytes(cells, base_bytes=None, n_workers=1, per_worker_bytes=0):
    """Rough peak RSS of a grid run, in bytes.

    *base_bytes* is what the process already holds (the coastline database
    dominates it, and it does not depend on the grid); pass the current RSS
    once the coastline is loaded and the estimate is grounded in fact rather
    than in a guess about file formats.
    """
    if base_bytes is None:
        base_bytes = _self_rss_bytes() or 0
    return (int(base_bytes)
            + int(cells) * _BYTES_PER_CELL_ESTIMATE
            + max(0, int(n_workers) - 1) * int(per_worker_bytes))


def check_memory_plan(cells, base_bytes=None, n_workers=1, per_worker_bytes=0):
    """Report whether a run of this size is expected to fit.

    Returns ``(fits, message)``.  ``fits`` is True when there is no reason to
    think it will not -- including when the budget cannot be determined, since
    refusing to run on an unknown budget would be worse than trying.
    """
    need = estimate_peak_bytes(cells, base_bytes, n_workers, per_worker_bytes)
    budget = available_memory_bytes()
    gib = float(1 << 30)
    if budget is None:
        return True, (f"Estimated peak memory ~{need / gib:.1f} GiB "
                      f"({cells / 1e6:.2f}M cells); memory budget unknown.")

    summary = (f"Estimated peak memory ~{need / gib:.1f} GiB "
               f"({cells / 1e6:.2f}M cells, {n_workers} worker(s)); "
               f"{describe_memory_budget()}.")
    if need * _MEMORY_SAFETY_MARGIN <= budget:
        return True, summary
    return False, (
        summary + "\n"
        "  This grid is not expected to fit.  Options, cheapest first:\n"
        "    - give the job more memory (Slurm: --mem);\n"
        "    - for a global or very wide domain, use a coarser bathymetry\n"
        "      (REF_GRID='etopo2' or 'etopo1' instead of 'gebco'): the base\n"
        "      slice is read whole, and 15-arcsecond GEBCO is ~11 GiB global;\n"
        "    - use a coarser coastline (BOUNDARY='inter' or 'low' instead of\n"
        "      'full'), which is most of the fixed cost;\n"
        "    - enlarge DX/DY, or split the domain and generate it in pieces.\n"
        "  Set WW3TOOL_MESHGEN_MEM_MB to override the budget if this estimate\n"
        "  is wrong for your machine."
    )


def chunk_ranges(n_items, n_chunks):
    """Split ``range(n_items)`` into at most *n_chunks* contiguous (start, stop)."""
    n_items = int(n_items)
    n_chunks = max(1, min(int(n_chunks), n_items)) if n_items > 0 else 1
    if n_items <= 0:
        return []
    size, extra = divmod(n_items, n_chunks)
    ranges = []
    start = 0
    for i in range(n_chunks):
        stop = start + size + (1 if i < extra else 0)
        if stop > start:
            ranges.append((start, stop))
        start = stop
    return ranges


def run_parallel(func, tasks, workers, initializer=None, initargs=(), ordered=True):
    """Map *func* over *tasks* in a process pool, falling back to a plain loop.

    Returns results in submission order when ``ordered``.  Any failure to
    start or drive the pool degrades to serial execution rather than aborting
    the grid run — the stages using this are all correctness-critical.
    """
    tasks = list(tasks)
    if not tasks:
        return []

    workers = max(1, min(int(workers), len(tasks)))
    if workers == 1:
        if initializer is not None:
            initializer(*initargs)
        return [func(t) for t in tasks]

    from concurrent.futures import ProcessPoolExecutor

    executor = None
    try:
        executor = ProcessPoolExecutor(
            max_workers=workers, initializer=initializer, initargs=initargs
        )
        chunksize = max(1, len(tasks) // (workers * 4))
        results = list(executor.map(func, tasks, chunksize=chunksize))
    except Exception as exc:  # pool unusable (no fork, restricted env, OOM, ...)
        print(f'  Warning: parallel execution unavailable ({exc}); running serially.',
              flush=True)
        if initializer is not None:
            initializer(*initargs)
        results = [func(t) for t in tasks]
    finally:
        if executor is not None:
            executor.shutdown(wait=True)
    return results
