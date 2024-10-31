# Kew Task Queue Manager

A flexible and robust asynchronous task queue manager for Python applications.

## Features

- Asynchronous task execution
- Configurable worker pool
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
from kew import TaskQueueManager

async def example_task(x: int):
    await asyncio.sleep(1)
    return x * 2

async def main():
    # Initialize the task queue manager
    manager = TaskQueueManager(max_workers=2)
    
    # Submit a task
    task_info = await manager.submit_task(
        task_id="task1",
        task_type="multiplication",
        task_func=example_task,
        x=5
    )
    
    # Wait for result
    await asyncio.sleep(2)
    status = manager.get_task_status("task1")
    print(f"Result: {status.result}")
    
    # Cleanup
    await manager.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
```

## Advanced Usage

### Concurrent Task Execution

```python
async def main():
    manager = TaskQueueManager(max_workers=2)
    
    # Submit multiple tasks
    tasks = []
    for i in range(5):
        task_info = await manager.submit_task(
            task_id=f"task{i}",
            task_type="example",
            task_func=example_task,
            x=i
        )
        tasks.append(task_info)
    
    # Wait for all tasks to complete
    await manager.wait_for_all_tasks()
```

### Task Status Monitoring

```python
status = manager.get_task_status("task1")
print(f"Status: {status.status}")
print(f"Result: {status.result}")
print(f"Error: {status.error}")
```

## API Reference

### TaskQueueManager

- `__init__(max_workers=2, queue_size=1000, task_timeout=3600)`
- `async submit_task(task_id, task_type, task_func, *args, **kwargs)`
- `get_task_status(task_id)`
- `async wait_for_task(task_id, timeout=None)`
- `async wait_for_all_tasks(timeout=None)`
- `cleanup_old_tasks(max_age_hours=24)`
- `async shutdown()`

### TaskStatus

Enum with states:
- `QUEUED`
- `PROCESSING`
- `COMPLETED`
- `FAILED`

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.