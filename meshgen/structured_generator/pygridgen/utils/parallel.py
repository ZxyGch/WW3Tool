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
