import asyncio
from datetime import datetime

import pytest

from kew import QueueConfig, QueuePriority, TaskQueueManager, TaskStatus


async def long_task(task_num: int, sleep_time: float) -> dict:
    """Simulate a long-running task"""
    await asyncio.sleep(sleep_time)
    result = sleep_time * 2
    return {"task_num": task_num, "result": result}


@pytest.fixture
async def manager():
    """Fixture to provide a TaskQueueManager instance"""
    mgr = TaskQueueManager(redis_url="redis://localhost:6379", cleanup_on_start=True)
    await mgr.initialize()
    try:
        yield mgr
    finally:
        await mgr.shutdown()


@pytest.mark.asyncio
async def test_single_queue():
    """Test single queue operation"""
    # Initialize manager
    manager = TaskQueueManager(
        redis_url="redis://localhost:6379", cleanup_on_start=True
    )
    await manager.initialize()

    try:
        # Create queue
        await manager.create_queue(
            QueueConfig(name="test_queue", max_workers=2, priority=QueuePriority.HIGH)
        )

        # Submit task
        task_info = await manager.submit_task(
            task_id="task1",
            queue_name="test_queue",
            task_type="test",
            task_func=long_task,
            priority=QueuePriority.HIGH,
            task_num=1,
            sleep_time=0.1,
        )

        # Check initial status
        status = await manager.get_task_status(task_info.task_id)
        assert status.queue_name == "test_queue"

        # Wait for completion
        await asyncio.sleep(0.2)

        # Check final status
        status = await manager.get_task_status(task_info.task_id)
        assert status.status == TaskStatus.COMPLETED
        assert status.result["task_num"] == 1
        assert status.result["result"] == 0.2

    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_multiple_queues():
    """Test multiple queues with different priorities"""
    # Initialize manager
    manager = TaskQueueManager(
        redis_url="redis://localhost:6379", cleanup_on_start=True
    )
    await manager.initialize()

    try:
        # Create queues
        await manager.create_queue(
            QueueConfig(name="fast_track", max_workers=2, priority=QueuePriority.HIGH)
        )

        await manager.create_queue(
            QueueConfig(name="standard", max_workers=1, priority=QueuePriority.LOW)
        )

        tasks = []

        # Submit high-priority tasks
        for i in range(2):
            sleep_time = 0.1
            task_info = await manager.submit_task(
                task_id=f"high_task_{i+1}",
                queue_name="fast_track",
                task_type="test",
                task_func=long_task,
                priority=QueuePriority.HIGH,
                task_num=i + 1,
                sleep_time=sleep_time,
            )
            tasks.append(task_info)

        # Submit low-priority task
        task_info = await manager.submit_task(
            task_id="low_task_1",
            queue_name="standard",
            task_type="test",
            task_func=long_task,
            priority=QueuePriority.LOW,
            task_num=3,
            sleep_time=0.1,
        )
        tasks.append(task_info)

        # Wait for completion
        await asyncio.sleep(0.3)

        # Check all tasks completed
        for task in tasks:
            status = await manager.get_task_status(task.task_id)
            assert status.status == TaskStatus.COMPLETED
            assert status.result is not None

        # Check queue statuses
        fast_track_status = await manager.get_queue_status("fast_track")
        standard_status = await manager.get_queue_status("standard")

        assert fast_track_status["queued_tasks"] == 0
        assert standard_status["queued_tasks"] == 0

    finally:
        await manager.shutdown()


async def priority_task_func(priority_name: str, redis_url: str):
    """Task function that stores execution order in Redis"""
    import redis.asyncio as redis_async

    r = await redis_async.from_url(redis_url, encoding="utf-8", decode_responses=True)
    try:
        await r.rpush("execution_order", priority_name)
    finally:
        await r.aclose()
    return f"Completed {priority_name}"


@pytest.mark.asyncio
async def test_queue_priorities():
    """Test that high priority tasks are processed before lower priority
    ones when available"""
    redis_url = "redis://localhost:6379"
    manager = TaskQueueManager(redis_url=redis_url, cleanup_on_start=True)
    await manager.initialize()

    try:
        # Clean up execution_order from previous runs
        await manager._redis.delete("execution_order")

        await manager.create_queue(
            QueueConfig(
                name="priority_queue", max_workers=1, priority=QueuePriority.MEDIUM
            )
        )

        # Submit low priority task first - it should start processing
        low_task = await manager.submit_task(
            task_id="low_priority",
            queue_name="priority_queue",
            task_type="test",
            task_func=priority_task_func,
            priority=QueuePriority.LOW,
            priority_name="low",
            redis_url=redis_url,
        )

        # Give it a moment to start processing
        await asyncio.sleep(0.1)

        # Submit high and medium priority tasks
        high_task = await manager.submit_task(
            task_id="high_priority",
            queue_name="priority_queue",
            task_type="test",
            task_func=priority_task_func,
            priority=QueuePriority.HIGH,
            priority_name="high",
            redis_url=redis_url,
        )

        medium_task = await manager.submit_task(
            task_id="medium_priority",
            queue_name="priority_queue",
            task_type="test",
            task_func=priority_task_func,
            priority=QueuePriority.MEDIUM,
            priority_name="medium",
            redis_url=redis_url,
        )

        # Wait for all tasks to complete
        tasks = [low_task, medium_task, high_task]
        for _ in range(30):  # 3 second timeout
            all_completed = True
            for task in tasks:
                status = await manager.get_task_status(task.task_id)
                if status.status != TaskStatus.COMPLETED:
                    all_completed = False
                    break
            if all_completed:
                break
            await asyncio.sleep(0.1)

        # Get execution order from Redis
        execution_order = await manager._redis.lrange("execution_order", 0, -1)
        execution_order = [
            item.decode("utf-8") if isinstance(item, bytes) else item
            for item in execution_order
        ]

        # Verify that high priority tasks are processed before lower priority ones
        # when they're available at the same time
        assert (
            len(execution_order) == 3
        ), f"Expected 3 tasks, got {len(execution_order)}"
        high_index = execution_order.index("high")
        medium_index = execution_order.index("medium")
        assert (
            high_index < medium_index
        ), "High priority should be processed before medium"

    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_error_handling():
    """Test error handling in tasks"""
    manager = TaskQueueManager(
        redis_url="redis://localhost:6379", cleanup_on_start=True
    )
    await manager.initialize()

    try:
        await manager.create_queue(QueueConfig(name="test_queue", max_workers=1))

        async def failing_task():
            await asyncio.sleep(0.1)
            raise ValueError("Test error")

        # Submit failing task
        await manager.submit_task(
            task_id="failing_task",
            queue_name="test_queue",
            task_type="test",
            task_func=failing_task,
            priority=QueuePriority.MEDIUM,
        )

        # Wait for task to fail
        # Increased wait time and added polling
        max_attempts = 10
        for _ in range(max_attempts):
            await asyncio.sleep(0.1)
            status = await manager.get_task_status("failing_task")
            if status.status == TaskStatus.FAILED:
                break

        assert (
            status.status == TaskStatus.FAILED
        ), f"Expected FAILED status, got {status.status}"
        assert (
            "Test error" in status.error
        ), f"Expected 'Test error' in error message, got {status.error}"

    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_queue_cleanup():
    """Test queue cleanup functionality"""
    # Initialize manager
    manager = TaskQueueManager(
        redis_url="redis://localhost:6379", cleanup_on_start=True
    )
    await manager.initialize()

    try:
        await manager.create_queue(QueueConfig(name="test_queue", max_workers=1))

        await manager.submit_task(
            task_id="task1",
            queue_name="test_queue",
            task_type="test",
            task_func=long_task,
            priority=QueuePriority.MEDIUM,
            task_num=1,
            sleep_time=0.1,
        )

        # Wait for completion
        await asyncio.sleep(0.2)

        # Clean up Redis
        await manager.cleanup()

        # Check task was cleaned up
        with pytest.raises(Exception):
            await manager.get_task_status("task1")

    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_task_timing():
    """Test that task timing information is recorded correctly"""
    manager = TaskQueueManager(
        redis_url="redis://localhost:6379", cleanup_on_start=True
    )
    await manager.initialize()

    try:
        await manager.create_queue(QueueConfig(name="timing_queue", max_workers=1))

        # Submit task with known sleep time
        sleep_duration = 0.2
        task_info = await manager.submit_task(
            task_id="timing_task",
            queue_name="timing_queue",
            task_type="test",
            task_func=long_task,
            priority=QueuePriority.MEDIUM,
            task_num=1,
            sleep_time=sleep_duration,
        )

        # Get initial timestamp
        initial_status = await manager.get_task_status(task_info.task_id)
        queued_time = initial_status.queued_time

        # Wait for completion
        await asyncio.sleep(sleep_duration + 0.1)  # Add small buffer

        # Get final status
        final_status = await manager.get_task_status(task_info.task_id)

        # Verify timestamps exist and are in correct order
        assert final_status.started_time is not None, "Start time should be set"
        assert final_status.completed_time is not None, "Completed time should be set"
        assert (
            queued_time < final_status.started_time < final_status.completed_time
        ), "Timestamps should be in order: queued < started < completed"

        # Verify processing duration is approximately correct
        processing_duration = (
            final_status.completed_time - final_status.started_time
        ).total_seconds()
        assert (
            sleep_duration - 0.1 <= processing_duration <= sleep_duration + 0.1
        ), (f"Processing duration ({processing_duration}) should be close to "
            f"sleep duration ({sleep_duration})")

    finally:
        await manager.shutdown()


async def tracked_task_func(task_num: int, sleep_time: float, redis_url: str):
    """Task function that tracks execution timing in Redis"""
    from datetime import datetime

    import redis.asyncio as redis_async

    r = await redis_async.from_url(redis_url, encoding="utf-8", decode_responses=True)
    try:
        start_timestamp = datetime.now().timestamp()
        await r.hset(f"execution_time:{task_num}", "start", start_timestamp)
        await r.hset(f"execution_time:{task_num}", "sleep_time", sleep_time)

        await asyncio.sleep(sleep_time)

        end_timestamp = datetime.now().timestamp()
        await r.hset(f"execution_time:{task_num}", "end", end_timestamp)
    finally:
        await r.aclose()
    return f"Task {task_num} completed"


@pytest.mark.asyncio
async def test_concurrent_processing():
    """Test that tasks can be processed concurrently up to max_workers"""
    redis_url = "redis://localhost:6379"
    manager = TaskQueueManager(redis_url=redis_url, cleanup_on_start=True)
    await manager.initialize()

    try:
        # Clean up execution_time keys from previous runs
        for i in range(4):
            await manager._redis.delete(f"execution_time:{i}")

        # Create queue with 3 workers
        await manager.create_queue(
            QueueConfig(
                name="concurrent_queue", max_workers=3, priority=QueuePriority.MEDIUM
            )
        )

        start_time = datetime.now()

        # Submit 4 tasks, each taking 0.5 seconds
        tasks = []
        for i in range(4):
            task_info = await manager.submit_task(
                task_id=f"concurrent_task_{i}",
                queue_name="concurrent_queue",
                task_type="test",
                task_func=tracked_task_func,
                priority=QueuePriority.MEDIUM,
                task_num=i,
                sleep_time=0.5,
                redis_url=redis_url,
            )
            tasks.append(task_info)

        # Wait for all tasks to complete
        await asyncio.sleep(
            1.2
        )  # Should be enough time for all tasks with concurrent processing

        # Verify all tasks completed
        for task in tasks:
            status = await manager.get_task_status(task.task_id)
            assert status.status == TaskStatus.COMPLETED

        # Retrieve execution times from Redis
        start_times = []
        for i in range(4):
            start_timestamp = await manager._redis.hget(f"execution_time:{i}", "start")
            if start_timestamp:
                start_timestamp = float(start_timestamp)
                start_times.append(datetime.fromtimestamp(start_timestamp))

        # Verify we got all execution times
        assert (
            len(start_times) == 4
        ), f"Expected 4 execution times, got {len(start_times)}"

        # Verify concurrent execution
        # First 3 tasks should start at almost the same time
        # Fourth task should start after one of the first 3 finishes
        start_times.sort()

        # First 3 tasks should start within 0.1s of each other
        assert (
            start_times[2] - start_times[0]
        ).total_seconds() < 0.1, "First 3 tasks should start almost simultaneously"

        # Fourth task should start after about 0.5s (when first task finishes)
        assert (
            0.4 < (start_times[3] - start_times[0]).total_seconds() < 0.6
        ), "Fourth task should start after one of the first tasks completes"

        # Total execution time should be about 1 second (two batches of 0.5s)
        total_time = (datetime.now() - start_time).total_seconds()
        assert (
            0.9 < total_time < 1.3
        ), f"Expected total execution time around 1 second, got {total_time}"

    finally:
        await manager.shutdown()
