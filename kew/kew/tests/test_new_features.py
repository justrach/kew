import asyncio
from datetime import datetime, timedelta

import pytest

from kew import QueueConfig, QueuePriority, TaskQueueManager, TaskStatus
from kew.exceptions import TaskAlreadyExistsError, QueueProcessorError


async def simple_task(value: int) -> int:
    await asyncio.sleep(0.05)
    return value * 2


async def failing_task_with_retries(tracker_key: str):
    """Task that fails N times then succeeds."""
    import redis.asyncio as redis_async
    r = await redis_async.from_url("redis://localhost:6379", decode_responses=True)
    try:
        count = await r.incr(f"attempt:{tracker_key}")
        if count < 3:
            raise ValueError(f"Attempt {count} failed")
        return f"Succeeded on attempt {count}"
    finally:
        await r.aclose()


@pytest.mark.asyncio
async def test_retry_support():
    """Test that failed tasks are retried with exponential backoff."""
    manager = TaskQueueManager(
        redis_url="redis://localhost:6379", cleanup_on_start=True
    )
    await manager.initialize()

    try:
        # Clean up attempt counter
        await manager._redis.delete("attempt:retry_test")

        await manager.create_queue(
            QueueConfig(
                name="retry_queue",
                max_workers=1,
                max_retries=3,
                retry_delay=0.1,  # Short delay for testing
            )
        )

        task_info = await manager.submit_task(
            task_id="retry_test",
            queue_name="retry_queue",
            task_type="test",
            task_func=failing_task_with_retries,
            priority=QueuePriority.MEDIUM,
            tracker_key="retry_test",
        )

        # Wait for retries + completion (3 attempts with exponential backoff)
        # Attempt 1: immediate, fails
        # Attempt 2: +0.1s delay, fails
        # Attempt 3: +0.2s delay, succeeds
        for _ in range(50):
            await asyncio.sleep(0.2)
            status = await manager.get_task_status("retry_test")
            if status.status == TaskStatus.COMPLETED:
                break

        status = await manager.get_task_status("retry_test")
        assert status.status == TaskStatus.COMPLETED, (
            f"Expected COMPLETED, got {status.status}"
        )
        assert status.retry_count == 2  # Failed twice, succeeded on 3rd
        assert "Succeeded on attempt 3" in str(status.result)

    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_deferred_execution():
    """Test that deferred tasks execute after the specified delay."""
    manager = TaskQueueManager(
        redis_url="redis://localhost:6379", cleanup_on_start=True
    )
    await manager.initialize()

    try:
        await manager.create_queue(
            QueueConfig(name="defer_queue", max_workers=2)
        )

        # Submit immediate task
        await manager.submit_task(
            task_id="immediate",
            queue_name="defer_queue",
            task_type="test",
            task_func=simple_task,
            priority=QueuePriority.MEDIUM,
            value=10,
        )

        # Submit deferred task (1 second delay)
        await manager.submit_task(
            task_id="deferred",
            queue_name="defer_queue",
            task_type="test",
            task_func=simple_task,
            priority=QueuePriority.MEDIUM,
            _defer_by=1.0,
            value=20,
        )

        # After 0.3s, immediate should be done, deferred should not
        await asyncio.sleep(0.3)
        immediate_status = await manager.get_task_status("immediate")
        deferred_status = await manager.get_task_status("deferred")

        assert immediate_status.status == TaskStatus.COMPLETED
        assert deferred_status.status == TaskStatus.QUEUED  # Not yet processed

        # After another 1s, deferred should be done
        await asyncio.sleep(1.2)
        deferred_status = await manager.get_task_status("deferred")
        assert deferred_status.status == TaskStatus.COMPLETED
        assert deferred_status.result == 40

    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_defer_until():
    """Test _defer_until parameter."""
    manager = TaskQueueManager(
        redis_url="redis://localhost:6379", cleanup_on_start=True
    )
    await manager.initialize()

    try:
        await manager.create_queue(
            QueueConfig(name="defer_until_queue", max_workers=1)
        )

        # Defer until 1 second from now
        defer_time = datetime.now() + timedelta(seconds=1)
        await manager.submit_task(
            task_id="defer_until_task",
            queue_name="defer_until_queue",
            task_type="test",
            task_func=simple_task,
            priority=QueuePriority.MEDIUM,
            _defer_until=defer_time,
            value=42,
        )

        # Should not be processed yet
        await asyncio.sleep(0.3)
        status = await manager.get_task_status("defer_until_task")
        assert status.status == TaskStatus.QUEUED

        # Should be processed after the defer time
        await asyncio.sleep(1.0)
        status = await manager.get_task_status("defer_until_task")
        assert status.status == TaskStatus.COMPLETED
        assert status.result == 84

    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_lifecycle_hooks():
    """Test on_task_start, on_task_complete, on_task_fail hooks."""
    events = []

    def on_start(task_info):
        events.append(("start", task_info.task_id))

    def on_complete(task_info):
        events.append(("complete", task_info.task_id))

    def on_fail(task_info, error):
        events.append(("fail", task_info.task_id, str(error)))

    manager = TaskQueueManager(
        redis_url="redis://localhost:6379",
        cleanup_on_start=True,
        on_task_start=on_start,
        on_task_complete=on_complete,
        on_task_fail=on_fail,
    )
    await manager.initialize()

    try:
        await manager.create_queue(
            QueueConfig(name="hook_queue", max_workers=1)
        )

        # Successful task
        await manager.submit_task(
            task_id="hook_success",
            queue_name="hook_queue",
            task_type="test",
            task_func=simple_task,
            priority=QueuePriority.MEDIUM,
            value=5,
        )

        await asyncio.sleep(0.3)

        # Failing task
        async def fail_task():
            raise RuntimeError("hook test error")

        await manager.submit_task(
            task_id="hook_fail",
            queue_name="hook_queue",
            task_type="test",
            task_func=fail_task,
            priority=QueuePriority.MEDIUM,
        )

        await asyncio.sleep(0.3)

        # Verify hooks were called
        assert ("start", "hook_success") in events
        assert ("complete", "hook_success") in events
        assert ("start", "hook_fail") in events
        # Check fail hook was called with error
        fail_events = [e for e in events if e[0] == "fail"]
        assert len(fail_events) == 1
        assert fail_events[0][1] == "hook_fail"
        assert "hook test error" in fail_events[0][2]

    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_async_lifecycle_hooks():
    """Test that async lifecycle hooks also work."""
    events = []

    async def on_start(task_info):
        events.append(("start", task_info.task_id))

    async def on_complete(task_info):
        events.append(("complete", task_info.task_id))

    manager = TaskQueueManager(
        redis_url="redis://localhost:6379",
        cleanup_on_start=True,
        on_task_start=on_start,
        on_task_complete=on_complete,
    )
    await manager.initialize()

    try:
        await manager.create_queue(
            QueueConfig(name="async_hook_queue", max_workers=1)
        )

        await manager.submit_task(
            task_id="async_hook_test",
            queue_name="async_hook_queue",
            task_type="test",
            task_func=simple_task,
            priority=QueuePriority.MEDIUM,
            value=1,
        )

        await asyncio.sleep(0.3)

        assert ("start", "async_hook_test") in events
        assert ("complete", "async_hook_test") in events

    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_duplicate_task_id_rejected():
    """Test that submitting a task with an existing ID is rejected atomically."""
    manager = TaskQueueManager(
        redis_url="redis://localhost:6379", cleanup_on_start=True
    )
    await manager.initialize()

    try:
        await manager.create_queue(
            QueueConfig(name="dup_queue", max_workers=1)
        )

        # First submission should succeed
        await manager.submit_task(
            task_id="dup_task",
            queue_name="dup_queue",
            task_type="test",
            task_func=simple_task,
            priority=QueuePriority.MEDIUM,
            value=1,
        )

        # Second submission with same ID should fail
        with pytest.raises(TaskAlreadyExistsError):
            await manager.submit_task(
                task_id="dup_task",
                queue_name="dup_queue",
                task_type="test",
                task_func=simple_task,
                priority=QueuePriority.MEDIUM,
                value=2,
            )

    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_queue_backpressure():
    """Test that queue rejects tasks when full."""
    manager = TaskQueueManager(
        redis_url="redis://localhost:6379", cleanup_on_start=True
    )
    await manager.initialize()

    try:
        await manager.create_queue(
            QueueConfig(name="small_queue", max_workers=1, max_size=2)
        )

        # Submit tasks to fill the queue
        # Use a long-running task so they don't complete immediately
        async def slow_task():
            await asyncio.sleep(10)
            return "done"

        await manager.submit_task(
            task_id="bp_task_1",
            queue_name="small_queue",
            task_type="test",
            task_func=slow_task,
            priority=QueuePriority.MEDIUM,
        )

        await manager.submit_task(
            task_id="bp_task_2",
            queue_name="small_queue",
            task_type="test",
            task_func=slow_task,
            priority=QueuePriority.MEDIUM,
        )

        # Third task should be rejected
        with pytest.raises(QueueProcessorError, match="full"):
            await manager.submit_task(
                task_id="bp_task_3",
                queue_name="small_queue",
                task_type="test",
                task_func=slow_task,
                priority=QueuePriority.MEDIUM,
            )

    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_redis_circuit_breaker():
    """Test that the Redis-backed circuit breaker works."""
    manager = TaskQueueManager(
        redis_url="redis://localhost:6379", cleanup_on_start=True
    )
    await manager.initialize()

    try:
        await manager.create_queue(
            QueueConfig(
                name="cb_queue",
                max_workers=1,
                max_circuit_breaker_failures=2,
                circuit_breaker_reset_timeout=1,
            )
        )

        worker_pool = manager.queues["cb_queue"]
        cb = worker_pool.circuit_breaker

        # Circuit should be closed initially
        assert await cb.check_state() is True

        # Record failures until circuit opens
        await cb.record_failure()
        assert await cb.check_state() is True  # 1 failure, threshold is 2

        await cb.record_failure()
        assert await cb.check_state() is False  # 2 failures, circuit open

        # Wait for auto-reset via key expiry
        await asyncio.sleep(1.5)
        assert await cb.check_state() is True  # Key expired, circuit closed

    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_get_ongoing_tasks():
    """Test get_ongoing_tasks uses active task set."""
    manager = TaskQueueManager(
        redis_url="redis://localhost:6379", cleanup_on_start=True
    )
    await manager.initialize()

    try:
        await manager.create_queue(
            QueueConfig(name="ongoing_queue", max_workers=2)
        )

        async def slow_task():
            await asyncio.sleep(2)
            return "done"

        await manager.submit_task(
            task_id="ongoing_1",
            queue_name="ongoing_queue",
            task_type="test",
            task_func=slow_task,
            priority=QueuePriority.MEDIUM,
        )

        await manager.submit_task(
            task_id="ongoing_2",
            queue_name="ongoing_queue",
            task_type="test",
            task_func=slow_task,
            priority=QueuePriority.MEDIUM,
        )

        # Wait for tasks to start processing
        await asyncio.sleep(0.3)

        ongoing = await manager.get_ongoing_tasks()
        assert len(ongoing) == 2
        task_ids = {t.task_id for t in ongoing}
        assert "ongoing_1" in task_ids
        assert "ongoing_2" in task_ids

    finally:
        await manager.shutdown()
