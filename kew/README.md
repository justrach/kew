# Kew Task Queue Manager

A flexible and robust asynchronous task queue manager for Python applications with support for multiple priority queues.

## Features

- Multiple named queues with independent configurations
- Priority-based task processing
- Asynchronous task execution
- Configurable worker pools per queue
- Task status tracking and monitoring
- Automatic cleanup of completed tasks
- Thread-safe operations
- Comprehensive logging

## Installation

```bash
pip install kew
```

## Quick Start

```python
import asyncio
from kew import TaskQueueManager, QueueConfig, QueuePriority

async def example_task(x: int):
    await asyncio.sleep(1)
    return x * 2

async def main():
    # Initialize the task queue manager
    manager = TaskQueueManager()
    
    # Create queues with different priorities
    manager.create_queue(QueueConfig(
        name="high_priority",
        max_workers=4,
        priority=QueuePriority.HIGH
    ))
    
    manager.create_queue(QueueConfig(
        name="background",
        max_workers=1,
        priority=QueuePriority.LOW
    ))
    
    # Submit tasks to different queues
    critical_task = await manager.submit_task(
        task_id="task1",
        queue_name="high_priority",
        task_type="multiplication",
        task_func=example_task,
        priority=QueuePriority.HIGH,
        x=5
    )
    
    background_task = await manager.submit_task(
        task_id="task2",
        queue_name="background",
        task_type="multiplication",
        task_func=example_task,
        priority=QueuePriority.LOW,
        x=10
    )
    
    # Wait for results
    await asyncio.sleep(2)
    high_status = manager.get_task_status("task1")
    low_status = manager.get_task_status("task2")
    print(f"High Priority Result: {high_status.result}")
    print(f"Background Result: {low_status.result}")
    
    # Cleanup
    await manager.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
```

## Queue Management

### Creating Queues

```python
from kew import QueueConfig, QueuePriority

# Create a high-priority queue with 4 workers
manager.create_queue(QueueConfig(
    name="critical",
    max_workers=4,
    priority=QueuePriority.HIGH,
    max_size=1000,
    task_timeout=3600
))

# Create a background queue with 1 worker
manager.create_queue(QueueConfig(
    name="background",
    max_workers=1,
    priority=QueuePriority.LOW
))
```

### Queue Priorities

- `QueuePriority.HIGH` (1): Critical tasks
- `QueuePriority.MEDIUM` (2): Standard tasks
- `QueuePriority.LOW` (3): Background tasks

### Queue Monitoring

```python
# Get queue status
status = manager.get_queue_status("critical")
print(f"Active Tasks: {status['active_tasks']}")
print(f"Queued Tasks: {status['queued_tasks']}")
print(f"Completed Tasks: {status['completed_tasks']}")
```

### Queue Operations

```python
# Wait for specific queue to complete
await manager.wait_for_queue("critical")

# Clean up old tasks in a queue
manager.cleanup_old_tasks(max_age_hours=24, queue_name="background")
```

## Task Management

### Submitting Tasks

```python
task_info = await manager.submit_task(
    task_id="unique_id",
    queue_name="critical",
    task_type="example",
    task_func=my_async_function,
    priority=QueuePriority.HIGH,
    *args,
    **kwargs
)
```

### Task Status Monitoring

```python
status = manager.get_task_status("unique_id")
print(f"Status: {status.status}")  # TaskStatus.QUEUED, PROCESSING, COMPLETED, FAILED
print(f"Queue: {status.queue_name}")
print(f"Priority: {status.priority}")
print(f"Result: {status.result}")
print(f"Error: {status.error}")
```

### Waiting for Tasks

```python
# Wait for specific task
await manager.wait_for_task("task1", timeout=30)

# Wait for all tasks in a queue
await manager.wait_for_queue("critical", timeout=60)
```

## API Reference

### TaskQueueManager

- `__init__()`
- `create_queue(config: QueueConfig)`
- `async submit_task(task_id, queue_name, task_type, task_func, priority, *args, **kwargs)`
- `get_task_status(task_id)`
- `get_queue_status(queue_name)`
- `async wait_for_task(task_id, timeout=None)`
- `async wait_for_queue(queue_name, timeout=None)`
- `cleanup_old_tasks(max_age_hours=24, queue_name=None)`
- `async shutdown(wait=True)`

### QueueConfig

- `name: str`
- `max_workers: int`
- `priority: QueuePriority = QueuePriority.MEDIUM`
- `max_size: int = 1000`
- `task_timeout: int = 3600`

### TaskStatus

Enum with states:
- `QUEUED`
- `PROCESSING`
- `COMPLETED`
- `FAILED`

### QueuePriority

Enum with levels:
- `HIGH` (1)
- `MEDIUM` (2)
- `LOW` (3)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.