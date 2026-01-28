# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [0.1.8] - 2026-01-29

### Added
- Redis pipelining and batching for significantly improved performance
  - Pipeline validation checks (queue size + duplicate) in single round-trip
  - Pipeline writes (payload, task info, queue entry) atomically
  - Batch deletes using `UNLINK` for non-blocking bulk cleanup
  - MGET batching for `get_ongoing_tasks()` in chunks of 500
- Connection pool configuration (`max_connections=50`)
- Benchmark suite in `benchmarks/redis_benchmark.py`

### Performance
- `submit_task`: 0.95ms → 0.28ms (**3.4x faster**)
- `cleanup` (500 keys): 890ms → 555ms (**1.6x faster**)
- `get_ongoing_tasks` (200 tasks): 288ms → 187ms (**1.5x faster**)
- Overall throughput: 855 → 1550 tasks/sec (**1.8x faster**)

### Changed
- `_execute_task` now receives `queue_name` parameter to avoid redundant Redis GETs
- Optimized `_process_queue` to fetch task_info and payload in single pipeline

## [0.1.7] - 2026-01-25

### Added
- Multi-process worker support with Redis-based task storage ([@Ahmad-cercli](https://github.com/Ahmad-cercli))
  - Store task payloads (func/args/kwargs) in Redis using cloudpickle
  - Enable distributed workers across multiple processes/machines
  - Add `max_circuit_breaker_failures` configuration option
  - Implement automatic payload cleanup after task completion

### Dependencies
- Added `cloudpickle>=1.1.1` for robust function serialization

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning when applicable.

## [0.1.5] - 2025-08-16

### Fixed
- Task processing reliability: reduced worker loop idle delay from 100ms to 20ms to improve responsiveness and reduce tasks lingering in PROCESSING.
- Graceful shutdown: await active tasks, allow done-callbacks to persist final statuses, and close Redis with `aclose()` to avoid deprecation warnings and dropped updates.
- Example: updated to correct async API usage (await initialize, create_queue; submit_task includes `task_type` and `priority`).

### Changed
- Restored coverage fail-under gate to 80% (current total ~87%).
- CI uses Redis 7 service; pip cache; simplified install via `pip install -e ".[test]"`.
- Added `py.typed` marker for typed package distribution.

### Tests
- All tests pass locally (7/7) with Redis 7.

### Notes
- Requires Redis 7 locally and in CI.

## [0.1.4] - 2024 

### Known Issues
- Longer idle delay could cause tasks to remain in PROCESSING briefly and increase flakiness in timing-sensitive tests.
- Shutdown used deprecated `close()` path for Redis, leading to warnings and occasional lost final status updates.
- README/example snippets did not consistently reflect the async API (`task_type`, `priority`).

### Features (unchanged)
- Async task queues with per-queue concurrency control.
- Priority-based scheduling using Redis sorted sets.
- Per-queue circuit breaker (defaults: 3 failures, 60s reset).

[0.1.5]: https://github.com/justrach/kew/compare/v0.1.4...v0.1.5
