# Kew Agent Log — 16 August 2025

Version: 0.1.5

## Summary of changes (increment 1)

- Packaging/config
  - Bumped version to 0.1.5 in `kew/kew/pyproject.toml`.
  - Pruned unused deps: removed `aioredis`, `asyncio`, `pydantic`, `typing-extensions` from `[project.dependencies]`.
  - Fixed test discovery to `testpaths = ["kew/tests"]`.
- Public API/version
  - Updated `kew/kew/kew/__init__.py` to `__version__ = "0.1.5"`.
  - Exported `QueueProcessorError` in `__all__`.
- Core runtime improvements (`kew/kew/kew/manager.py`)
  - Atomic queue pop with `ZPOPMIN` to avoid duplicate pulls across workers.
  - Enforced `QueueConfig.max_size` in `submit_task()` (backpressure).
  - Added duplicate task protection; raises `TaskAlreadyExistsError` if `task_id` exists.
  - Enforced per-queue `task_timeout` via `asyncio.wait_for()`.
  - Circuit breaker: records failures on exceptions/timeouts; resets on success; respected during processing.
  - Prevented memory growth by cleaning up `worker_pool._tasks` on completion.
  - More accurate `current_workers` using semaphore permits.
  - Prevented duplicate log handlers when multiple managers are created.
- CI updates (`.github/workflows/python-package.yml`)
  - Pinned Redis service to v7.
  - Simplified deps install to `pip install -e ".[test]"` with pip cache.

## Summary of changes (increment 2)

- Reliability fixes (`kew/kew/kew/manager.py`)
  - Reduced idle wait in `_process_queue()` when no task is popped from 100ms to 20ms for faster pickup and completion.
  - Improved `shutdown()` to await active tasks, add a brief 50ms delay to let done-callbacks persist statuses, and use `await redis.aclose()` to close the async client correctly.
- Coverage gate
  - Restored `coverage` `fail_under = 80` in `kew/pyproject.toml`.
- Results
  - All tests pass locally (7/7) against Redis 7. Total coverage ~87%.

## Rationale
- Reliability: Atomic pop + duplicate protection reduce double-processing under concurrency.
- Backpressure: `max_size` enforcement prevents unbounded growth.
- Correctness: Timeouts, circuit breaker integration, and accurate metrics.
- Tooling: Consistent versioning; lean dependencies; stable CI runtime.

## Verification plan
- Unit/integration tests: run `pytest` from `kew/` with Redis 7 running on `localhost:6379`.
- Manual smoke test: run `kew/kew/example.py` after fixing to proper async usage (next increment).
- Benchmarks: run `python kew_benchmark_report.py` to collect throughput/latency.

## Next increments (planned)
1) Documentation & examples
   - Align root `README.md` examples with current async API.
   - Move/repair `kew/kew/example.py` into `examples/` and make it runnable end-to-end.
2) CI quality gates
   - Add `ruff` and `mypy` steps to CI using config in `pyproject.toml`.
   - Add `py.typed` marker for typed package distribution.
3) Benchmarks & comparison graph
   - Extend `kew_benchmark_report.py` to compare Kew 0.1.4 vs 0.1.5 throughput/latency.
   - Produce a graph (PNG/SVG) and embed in `BENCHMARK.md`.
   - If needed, install `kew==0.1.4` in a throwaway venv to benchmark prior version.
4) Optional runtime enhancements
   - Add pause/resume admin controls.
   - Add simple retry policy with backoff.

## Notes
- Local testing requires Redis running: `redis-server` (v7). Configure via `REDIS_URL` if non-default.
- For multi-process safety, current design is optimized for single-process per queue; distributed locks are a future enhancement.
