# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [0.2.1] - 2026-02-16

### Added
- **Batch submit API**: `submit_tasks()` method submits N tasks in a single Redis round-trip via a new batch Lua script. Chunks of 50 tasks internally.
- **Concurrent-safe lock-free submit**: Removed `_submit_lock` from `submit_task()` since the Lua script already provides atomicity. Concurrent `asyncio.gather` callers can now overlap Redis round-trips.

### Performance
- **Batch throughput**: ~33,700 tasks/sec (12x faster than arq sequential)
- **Concurrent throughput**: ~8,000 tasks/sec via `asyncio.gather` (2.9x arq)
- **Sequential throughput**: ~3,000 tasks/sec (now faster than arq's ~2,800/sec)
- kew now **beats arq on every single-process metric**

### Changed
- `submit_task()` no longer holds a per-queue lock (Lua atomicity is sufficient)
- New `_SUBMIT_BATCH_SCRIPT` Lua script for multi-task atomic insertion

## [0.2.0] - 2026-02-16

### Breaking Changes
- Circuit breaker is now Redis-backed (`RedisCircuitBreaker`) instead of in-memory. Shared state across processes, auto-resets via key expiry.
- Priority score multiplier increased from `1_000_000` to `10_000_000_000_000` to prevent score collisions between priority levels over long uptimes.

### Added
- **Atomic task submission via Lua script**: Single Redis round-trip for existence check, queue size check, task info write, payload write, and enqueue. Eliminates the race condition where two concurrent submits with the same task_id could both succeed.
- **Retry with exponential backoff**: `max_retries` and `retry_delay` on `QueueConfig`. Failed tasks are re-queued with delay `retry_delay * 2^(attempt-1)`. New `RETRY` status in `TaskStatus` enum. `retry_count` field on `TaskInfo`.
- **Deferred task execution**: `_defer_by` (seconds) and `_defer_until` (datetime) parameters on `submit_task`. Uses sorted set score to encode execution time; tasks with future scores are skipped until ready.
- **Lifecycle hooks**: `on_task_start`, `on_task_complete`, `on_task_fail` callbacks on `TaskQueueManager`. Supports both sync and async callables.
- **Redis-backed circuit breaker**: `RedisCircuitBreaker` class uses Redis keys with TTL-based auto-reset. Configurable via `circuit_breaker_reset_timeout` on `QueueConfig`.
- **Binary Redis connection**: Second connection with `decode_responses=False` for cloudpickle payloads. Eliminates 33% base64 encoding overhead.
- **Per-queue submit locks**: `submit_task` uses per-queue `asyncio.Lock` instead of a global lock. Independent queues no longer serialize.
- **Active task set**: `SADD`/`SREM` on `kew:active_tasks` replaces `SCAN` over entire keyspace for `get_ongoing_tasks()`.
- 9 new tests covering retries, deferred execution, lifecycle hooks, duplicate rejection, backpressure, circuit breaker, and active task set.

### Fixed
- **`timedelta.seconds` bug**: Circuit breaker used `.seconds` (which ignores the days component) instead of `.total_seconds()`. Caused the circuit breaker to stay open indefinitely after 1+ days of uptime.
- **Race condition in `submit_task`**: Two separate Redis pipelines (check then write) allowed concurrent submits with the same task_id to both succeed. Replaced with an atomic Lua script.
- **Duplicate `TypeVar` declaration**: `T = TypeVar("T")` was declared twice in `models.py`.

### Performance
- `submit_task` latency: 0.64ms -> 0.29ms (**2.2x faster**)
- Throughput: 1,550/sec -> 2,990/sec (**1.9x faster**)
- Payload storage: +33% (base64) -> 0% overhead (raw binary)
- `get_ongoing_tasks`: O(all_keys) -> O(active_tasks)
- Task execution: 2 Redis round-trips -> 1 (eliminated redundant GET in `_execute_task`)
- Semaphore reorder: check Redis before acquiring worker slot (don't block on empty queues)

### Comparison with arq v0.27
- kew enqueue: 0.29ms mean, ~2,990/sec
- arq enqueue: 0.26ms mean, ~3,440/sec
- kew is within 1.15x of arq's enqueue speed. The remaining gap is structural (cloudpickle serialization vs function name strings).

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
- `submit_task`: 0.95ms -> 0.28ms (**3.4x faster**)
- `cleanup` (500 keys): 890ms -> 555ms (**1.6x faster**)
- `get_ongoing_tasks` (200 tasks): 288ms -> 187ms (**1.5x faster**)
- Overall throughput: 855 -> 1550 tasks/sec (**1.8x faster**)

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

[0.2.1]: https://github.com/justrach/kew/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/justrach/kew/compare/v0.1.8...v0.2.0
[0.1.8]: https://github.com/justrach/kew/compare/v0.1.7...v0.1.8
[0.1.7]: https://github.com/justrach/kew/compare/v0.1.5...v0.1.7
[0.1.5]: https://github.com/justrach/kew/compare/v0.1.4...v0.1.5
