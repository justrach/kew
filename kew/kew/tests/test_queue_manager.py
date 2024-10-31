import pytest
import asyncio
import random
from kew import TaskQueueManager, QueueConfig, QueuePriority, TaskStatus

async def long_task(task_num: int, sleep_time: float) -> dict:
    """Simulate a long-running task"""
    await asyncio.sleep(sleep_time)
    result = sleep_time * 2
    return {"task_num": task_num, "result": result}

@pytest.mark.asyncio
async def test_single_queue():
    """Test single queue operation"""
    manager = TaskQueueManager()
    
    # Create queue
    manager.create_queue(QueueConfig(
        name="test_queue",
        max_workers=2,
        priority=QueuePriority.HIGH
    ))
    
    # Submit task
    task_info = await manager.submit_task(
        task_id="task1",
        queue_name="test_queue",
        task_type="test",
        task_func=long_task,
        priority=QueuePriority.HIGH,
        task_num=1,
        sleep_time=0.1
    )
    
    # Check initial status
    status = manager.get_task_status(task_info.task_id)
    assert status.queue_name == "test_queue"
    
    # Wait for completion
    await asyncio.sleep(0.2)
    
    # Check final status
    status = manager.get_task_status(task_info.task_id)
    assert status.status == TaskStatus.COMPLETED
    assert status.result["task_num"] == 1
    assert status.result["result"] == 0.2
    
    await manager.shutdown()

@pytest.mark.asyncio
async def test_multiple_queues():
    """Test multiple queues with different priorities"""
    manager = TaskQueueManager()
    
    # Create queues
    manager.create_queue(QueueConfig(
        name="fast_track",
        max_workers=2,
        priority=QueuePriority.HIGH
    ))
    
    manager.create_queue(QueueConfig(
        name="standard",
        max_workers=1,
        priority=QueuePriority.LOW
    ))
    
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
            task_num=i+1,
            sleep_time=sleep_time
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
        sleep_time=0.1
    )
    tasks.append(task_info)
    
    # Wait for completion
    await asyncio.sleep(0.3)
    
    # Check all tasks completed
    for task in tasks:
        status = manager.get_task_status(task.task_id)
        assert status.status == TaskStatus.COMPLETED
        assert status.result is not None
    
    # Check queue statuses
    fast_track_status = manager.get_queue_status("fast_track")
    standard_status = manager.get_queue_status("standard")
    
    assert fast_track_status["completed_tasks"] == 2
    assert standard_status["completed_tasks"] == 1
    
    await manager.shutdown()

@pytest.mark.asyncio
async def test_queue_priorities():
    """Test that high priority tasks complete before low priority ones"""
    manager = TaskQueueManager()
    
    manager.create_queue(QueueConfig(
        name="mixed_queue",
        max_workers=1,  # Single worker to ensure sequential execution
        priority=QueuePriority.MEDIUM
    ))
    
    completion_order = []
    
    async def tracking_task(priority_level: str):
        await asyncio.sleep(0.1)
        completion_order.append(priority_level)
        return priority_level
    
    # Submit low priority task first
    await manager.submit_task(
        task_id="low_priority",
        queue_name="mixed_queue",
        task_type="test",
        task_func=tracking_task,
        priority=QueuePriority.LOW,
        priority_level="low"
    )
    
    # Submit high priority task second
    await manager.submit_task(
        task_id="high_priority",
        queue_name="mixed_queue",
        task_type="test",
        task_func=tracking_task,
        priority=QueuePriority.HIGH,
        priority_level="high"
    )
    
    # Wait for completion
    await asyncio.sleep(0.3)
    
    # High priority task should complete first
    assert completion_order[0] == "high"
    assert completion_order[1] == "low"
    
    await manager.shutdown()

@pytest.mark.asyncio
async def test_error_handling():
    """Test error handling in tasks"""
    manager = TaskQueueManager()
    
    manager.create_queue(QueueConfig(
        name="test_queue",
        max_workers=1
    ))
    
    async def failing_task():
        await asyncio.sleep(0.1)
        raise ValueError("Test error")
    
    task_info = await manager.submit_task(
        task_id="failing_task",
        queue_name="test_queue",
        task_type="test",
        task_func=failing_task,
        priority=QueuePriority.MEDIUM
    )
    
    # Wait for task to fail
    await asyncio.sleep(0.2)
    
    status = manager.get_task_status("failing_task")
    assert status.status == TaskStatus.FAILED
    assert "Test error" in status.error
    
    await manager.shutdown()

@pytest.mark.asyncio
async def test_queue_cleanup():
    """Test queue cleanup functionality"""
    manager = TaskQueueManager()
    
    manager.create_queue(QueueConfig(
        name="test_queue",
        max_workers=1
    ))
    
    task_info = await manager.submit_task(
        task_id="task1",
        queue_name="test_queue",
        task_type="test",
        task_func=long_task,
        priority=QueuePriority.MEDIUM,
        task_num=1,
        sleep_time=0.1
    )
    
    # Wait for completion
    await asyncio.sleep(0.2)
    
    # Clean up old tasks
    manager.cleanup_old_tasks(max_age_hours=0)
    
    # Check task was cleaned up
    with pytest.raises(Exception):
        manager.get_task_status("task1")
    
    await manager.shutdown()
