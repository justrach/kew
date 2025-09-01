<p align="center">
  <img src="https://github.com/justrach/kew/blob/main/kew_logo.jpg" alt="Kew Logo" width="200"/>
</p>

<h1 align="center">Kew: Modern Async Task Queue</h1>

<p align="center">
  <a href="https://pypi.org/project/kew">
    <img src="https://static.pepy.tech/badge/kew" alt="PyPI Downloads">
  </a>
  <a href="https://github.com/justrach/kew/actions/workflows/python-package.yml">
    <img src="https://github.com/justrach/kew/actions/workflows/python-package.yml/badge.svg" alt="Github Actions">
  </a>
</p>
A Redis-backed task queue built for modern async Python applications. Handles background processing with precise concurrency control, priority queues, and circuit breakers - all running in your existing async process.

## Why Kew?

Building async applications often means dealing with background tasks. Existing solutions like Celery require separate worker processes and complex configuration. Kew takes a different approach:

- **Runs in Your Process**: No separate workers to manage - tasks run in your existing async process
- **True Async**: Native async/await support - no sync/async bridges needed
- **Precise Control**: Semaphore-based concurrency ensures exact worker limits
- **Simple Setup**: Just Redis and a few lines of code to get started

## How It Works

Kew manages task execution using a combination of Redis for persistence and asyncio for processing:
```mermaid
graph LR
    A[Application] -->|Submit Task| B[Task Queue]
    B -->|Semaphore Control| C[Worker Pool]
    C -->|Execute Task| D[Task Processing]
    D -->|Success| E[Complete]
    D -->|Error| F[Circuit Breaker]
    F -->|Reset| B
    style A fill:#f9f,stroke:#333
    style B fill:#bbf,stroke:#333
    style C fill:#bfb,stroke:#333
    style D fill:#fbb,stroke:#333
```
Tasks flow through several states with built-in error handling:
```mermaid
stateDiagram-v2
    [*] --> Submitted: Task Created
    Submitted --> Queued: Priority Assignment
    Queued --> Processing: Worker Available
    Processing --> Completed: Success
    Processing --> Failed: Error
    Failed --> CircuitOpen: Multiple Failures
    CircuitOpen --> Queued: Circuit Reset
    Completed --> [*]
```
## Quick Start

1. Install Kew:
```bash
pip install kew
```

2. Create a simple task processor:
```python
import asyncio
from kew import TaskQueueManager, QueueConfig, QueuePriority

async def process_order(order_id: str):
    # Simulate order processing
    await asyncio.sleep(1)
    return f"Order {order_id} processed"

async def main():
    # Initialize queue manager
    manager = TaskQueueManager(redis_url="redis://localhost:6379")
    await manager.initialize()
    
    # Create processing queue
    await manager.create_queue(QueueConfig(
        name="orders",
        max_workers=4,  # Only 4 concurrent tasks
        max_size=1000
    ))
    
    # Submit some tasks
    tasks = []
    for i in range(10):
        task = await manager.submit_task(
            task_id=f"order-{i}",
            queue_name="orders",
            task_type="process_order",
            task_func=process_order,
            priority=QueuePriority.MEDIUM,
            order_id=str(i)
        )
        tasks.append(task)
    
    # Check results
    # Small delay to allow tasks to complete in this simple example
    await asyncio.sleep(1.2)
    for task in tasks:
        status = await manager.get_task_status(task.task_id)
        print(f"{task.task_id}: {status.result}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Real-World Examples

### Async Web Application
```python
from fastapi import FastAPI
from kew import TaskQueueManager, QueueConfig, QueuePriority

app = FastAPI()
manager = TaskQueueManager()

@app.on_event("startup")
async def startup():
    await manager.initialize()
    await manager.create_queue(QueueConfig(
        name="emails",
        max_workers=2
    ))

@app.post("/signup")
async def signup(email: str):
    # Handle signup immediately
    user = await create_user(email)
    
    # Queue welcome email for background processing
    await manager.submit_task(
        task_id=f"welcome-{user.id}",
        queue_name="emails",
        task_type="send_welcome_email",
        task_func=send_welcome_email,
        priority=QueuePriority.MEDIUM,
        user_id=user.id
    )
    return {"status": "success"}
```

### Data Processing Script
```python
async def process_batch(items: list):
    manager = TaskQueueManager()
    await manager.initialize()
    
    # Create high and low priority queues
    await manager.create_queue(QueueConfig(
        name="critical",
        max_workers=4,
        priority=QueuePriority.HIGH
    ))
    
    await manager.create_queue(QueueConfig(
        name="batch",
        max_workers=2,
        priority=QueuePriority.LOW
    ))
    
    # Process priority items first
    for item in filter(is_priority, items):
        await manager.submit_task(
            task_id=f"item-{item.id}",
            queue_name="critical",
            task_type="process_item",
            task_func=process_item,
            priority=QueuePriority.HIGH,
            item=item
        )
    
    # Queue remaining items
    for item in filter(lambda x: not is_priority(x), items):
        await manager.submit_task(
            task_id=f"item-{item.id}",
            queue_name="batch",
            task_type="process_item",
            task_func=process_item,
            priority=QueuePriority.LOW,
            item=item
        )
```

## Key Features

### Concurrency Control
```python
# Strictly enforce 4 concurrent tasks max
await manager.create_queue(QueueConfig(
    name="api_calls",
    max_workers=4  # Guaranteed not to exceed
))
```

### Priority Queues
```python
# High priority queue for urgent tasks
await manager.create_queue(QueueConfig(
    name="urgent",
    priority=QueuePriority.HIGH
))

# Lower priority for batch processing
await manager.create_queue(QueueConfig(
    name="batch",
    priority=QueuePriority.LOW
))
```

### Circuit Breakers
Built-in per-queue circuit breaker tracks consecutive failures and temporarily opens the circuit to protect downstreams.

- Defaults: `max_failures=3`, `reset_timeout=60s`
- Note: Currently not configurable via `QueueConfig`.

### Task Monitoring
```python
# Check task status
status = await manager.get_task_status("task-123")
print(f"Status: {status.status}")
print(f"Result: {status.result}")
print(f"Error: {status.error}")

# Monitor queue health
queue_status = await manager.get_queue_status("api_calls")
print(f"Active Tasks: {queue_status['current_workers']}")
print(f"Circuit Breaker: {queue_status['circuit_breaker_status']}")
```

## Performance & Reliability (v0.1.5)

- Reduced worker-loop idle delay (from 100ms to 20ms) for faster task pickup and lower test flakiness.
- Graceful shutdown: awaits active tasks, flushes callbacks, and uses Redis `aclose()` to avoid deprecation warnings and lost updates.
- Requires Redis 7 locally and in CI.

## Version Differences

See the full changelog in [CHANGELOG.md](CHANGELOG.md).

- 0.1.5 (current)
  - Faster task pickup (idle delay 100ms → 20ms)
  - More reliable shutdown (await tasks, flush callbacks, Redis `aclose()`)
  - Tests: 7/7 passing; coverage gate restored to 80% (total ~87%)
  - Docs: examples aligned with async API (`task_type`, `priority`)
  - CI: Redis 7 service; pip cache; simplified install
- 0.1.4
  - Stable async queues, priorities, and concurrency control
  - Circuit breaker defaults (3 failures, 60s reset)
  - Known issues: longer idle delay could leave tasks in PROCESSING briefly; Redis `close()` deprecation warnings

## Roadmap

- Make circuit breaker settings configurable per queue (max failures, reset timeout)
- Configurable task expiry and queue polling intervals (idle delay)
- Retry and backoff policies with dead-letter queue
- Pause/resume controls and basic admin/health endpoints
- Metrics and observability (Prometheus/OpenTelemetry), richer `get_queue_status()`
- Distributed workers with coordination (locks) for multi-process scaling
- Rate limiting per queue and burst control
- CLI tooling for inspection and maintenance

## Configuration

### Redis Settings
```python
manager = TaskQueueManager(
    redis_url="redis://username:password@hostname:6379/0",
    cleanup_on_start=True  # Optional: clean stale tasks
)
```

### Task Expiration
Tasks expire after 24 hours by default. This value is currently not configurable.

## Error Handling

Kew provides comprehensive error handling:

- `TaskAlreadyExistsError`: Task ID already in use
- `TaskNotFoundError`: Task doesn't exist
- `QueueNotFoundError`: Queue not configured
- `QueueProcessorError`: Task processing failed

```python
try:
    await manager.submit_task(...)
except TaskAlreadyExistsError:
    # Handle duplicate task
except QueueProcessorError as e:
    # Handle processing error
    print(f"Task failed: {e}")
```

## Contributing

We welcome contributions! Please check our [Contributing Guide](CONTRIBUTING.md) for details.

## License

MIT License - see the [LICENSE](LICENSE) file for details.
