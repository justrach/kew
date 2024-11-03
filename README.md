# Kew Task Queue Manager

A robust, Redis-backed asynchronous task queue manager for Python applications with support for priority-based queues and circuit breaker patterns.

## Features

- Multiple named queues with independent configurations
- Priority-based task scheduling with millisecond precision
- Redis-backed persistence for reliability
- Configurable worker pools per queue with strict concurrency control
- Built-in circuit breaker for fault tolerance
- Comprehensive task lifecycle management
- Proper semaphore-based worker slot management
- Race condition protection in concurrent processing
- Automatic task expiration (24-hour default)
- Detailed logging and monitoring
- Graceful shutdown handling
- Thread-safe operations

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
    # Initialize the task queue manager with Redis connection
    manager = TaskQueueManager(redis_url="redis://localhost:6379")
    await manager.initialize()
    
    # Create a high-priority queue with concurrent processing limits
    await manager.create_queue(QueueConfig(
        name="high_priority",
        max_workers=4,  # Strictly enforced concurrent task limit
        max_size=1000,
        priority=QueuePriority.HIGH
    ))
    
    # Submit a task
    task_info = await manager.submit_task(
        task_id="task1",
        queue_name="high_priority",
        task_type="multiplication",
        task_func=example_task,
        priority=QueuePriority.HIGH,
        x=5
    )
    
    # Check task status
    await asyncio.sleep(2)
    status = await manager.get_task_status("task1")
    print(f"Task Result: {status.result}")
    
    # Graceful shutdown
    await manager.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
```

## Queue Configuration

### Creating Queues

```python
from kew import QueueConfig, QueuePriority

# Create a high-priority queue with strictly enforced concurrent processing
await manager.create_queue(QueueConfig(
    name="critical",
    max_workers=4,  # Maximum number of concurrent tasks
    max_size=1000,
    priority=QueuePriority.HIGH
))
```

### Worker Pool Management

The queue manager now implements strict concurrency control:
- Uses semaphores to guarantee max_workers limit is respected
- Prevents task starvation through fair scheduling
- Properly releases worker slots after task completion
- Handles error cases with automatic worker slot cleanup
- Protects against race conditions in concurrent processing

### Queue Priority Levels

- `QueuePriority.HIGH` (1)
- `QueuePriority.MEDIUM` (2)
- `QueuePriority.LOW` (3)

Tasks within the same priority level are processed in FIFO order with millisecond precision.

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

### Monitoring Task Status

```python
status = await manager.get_task_status("unique_id")
print(f"Status: {status.status}")  # QUEUED, PROCESSING, COMPLETED, FAILED
print(f"Queue: {status.queue_name}")
print(f"Priority: {status.priority}")
print(f"Result: {status.result}")
print(f"Error: {status.error}")
```

### Queue Status Monitoring

```python
status = await manager.get_queue_status("critical")
print(f"Queue Size: {status['queued_tasks']}")
print(f"Active Workers: {status['current_workers']}")  # Shows current concurrent tasks
print(f"Circuit Breaker: {status['circuit_breaker_status']}")
```

## Advanced Features

### Concurrent Processing

Each queue now implements robust concurrent task processing:
- Strict enforcement of max_workers limit through semaphores
- Fair scheduling of tasks to prevent starvation
- Automatic cleanup of worker slots on task completion
- Protected against race conditions in high-concurrency scenarios
- Error handling with proper resource cleanup

### Circuit Breaker

Each queue has a built-in circuit breaker that helps prevent cascade failures:
- Opens after 3 consecutive failures (configurable)
- Auto-resets after 60 seconds (configurable)
- Provides circuit state monitoring
- Integrates with concurrent processing controls

### Task Expiration

Tasks automatically expire after 24 hours (configurable) to prevent resource leaks.

### Redis Configuration

```python
manager = TaskQueueManager(
    redis_url="redis://username:password@hostname:6379/0",
    cleanup_on_start=True  # Optional: cleans up existing tasks on startup
)
```

## Error Handling

The system handles various error scenarios:

- `TaskAlreadyExistsError`: Raised when submitting a task with a duplicate ID
- `TaskNotFoundError`: Raised when querying a non-existent task
- `QueueNotFoundError`: Raised when accessing an undefined queue
- `QueueProcessorError`: Raised for queue processing failures

## API Reference

### TaskQueueManager

Core Methods:
- `async initialize()`
- `async create_queue(config: QueueConfig)`
- `async submit_task(task_id, queue_name, task_type, task_func, priority, *args, **kwargs)`
- `async get_task_status(task_id)`
- `async get_queue_status(queue_name)`
- `async shutdown(wait=True, timeout=5.0)`

### QueueConfig

Configuration Parameters:
- `name: str`
- `max_workers: int` - Strictly enforced concurrent task limit
- `max_size: int`
- `priority: QueuePriority`

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.