# Changelog

All notable changes to this project will be documented in this file.

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
