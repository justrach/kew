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
A high-performance Redis-backed task queue built for modern async Python applications. Handles background processing with precise concurrency control, priority queues, circuit breakers, retries, and deferred execution - all running in your existing async process.

## Why Kew?

Building async applications often means dealing with background tasks. Existing solutions like Celery require separate worker processes and complex configuration. Kew takes a different approach:

- **Runs in Your Process**: No separate workers to manage - tasks run in your existing async process
- **True Async**: Native async/await support - no sync/async bridges needed
- **Precise Control**: Semaphore-based concurrency ensures exact worker limits
- **Simple Setup**: Just Redis and a few lines of code to get started
- **Fast**: Single-roundtrip atomic task submission via Lua scripts

## How It Works

Kew manages task execution using a combination of Redis for persistence and asyncio for processing:
```mermaid
graph LR
    A[Application] -->|Submit Task| B[Task Queue]
    B -->|Semaphore Control| C[Worker Pool]
    C -->|Execute Task| D[Task Processing]
    D -->|Success| E[Complete]
    D -->|Error| F[Circuit Breaker]
    F -->|Retry/Reset| B
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
    Processing --> Retry: Error (retries remaining)
    Retry --> Queued: Backoff Delay
    Processing --> Failed: Error (no retries)
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

### Retry with Exponential Backoff (v0.2.0)
```python
await manager.create_queue(QueueConfig(
    name="flaky_api",
    max_workers=4,
    max_retries=3,          # Retry up to 3 times on failure
    retry_delay=1.0,        # Base delay of 1 second (doubles each retry)
))

# Tasks that fail will be re-queued automatically:
# Attempt 1: immediate
# Attempt 2: +1s delay
# Attempt 3: +2s delay
# Attempt 4: +4s delay (or fail permanently)
```

### Deferred Execution (v0.2.0)
```python
from datetime import datetime, timedelta

# Defer by a duration
await manager.submit_task(
    task_id="send-reminder",
    queue_name="emails",
    task_type="reminder",
    task_func=send_reminder,
    priority=QueuePriority.MEDIUM,
    _defer_by=300.0,  # Execute 5 minutes from now
    user_id="abc123",
)

# Defer until a specific time
await manager.submit_task(
    task_id="morning-report",
    queue_name="reports",
    task_type="report",
    task_func=generate_report,
    priority=QueuePriority.LOW,
    _defer_until=datetime(2025, 1, 15, 9, 0, 0),  # Run at 9 AM
)
```

### Lifecycle Hooks (v0.2.0)
```python
async def on_start(task_info):
    print(f"Task {task_info.task_id} started")

async def on_complete(task_info):
    await metrics.record("task.completed", task_info.task_id)

async def on_fail(task_info, error):
    await alert_channel.send(f"Task {task_info.task_id} failed: {error}")

manager = TaskQueueManager(
    redis_url="redis://localhost:6379",
    on_task_start=on_start,
    on_task_complete=on_complete,
    on_task_fail=on_fail,
)
```

### Circuit Breakers
Redis-backed per-queue circuit breaker tracks consecutive failures and temporarily opens the circuit to protect downstreams. Auto-resets via key expiry.

```python
await manager.create_queue(QueueConfig(
    name="external_api",
    max_workers=4,
    max_circuit_breaker_failures=5,     # Open after 5 consecutive failures
    circuit_breaker_reset_timeout=30,   # Auto-close after 30 seconds
))
```

### Backpressure
```python
from kew.exceptions import QueueProcessorError

await manager.create_queue(QueueConfig(
    name="bounded_queue",
    max_workers=2,
    max_size=100,  # Reject submissions beyond 100 queued tasks
))

try:
    await manager.submit_task(...)
except QueueProcessorError:
    # Queue is full - apply backpressure to caller
    return {"status": "busy", "retry_after": 5}
```

### Batch Submit (v0.2.1)
Submit thousands of tasks in a single Redis round-trip for maximum throughput:
```python
tasks = [
    {
        "task_id": f"order-{i}",
        "task_type": "process",
        "task_func": process_order,
        "priority": QueuePriority.MEDIUM,
        "kwargs": {"order_id": i},
    }
    for i in range(1000)
]

# Single call, batched internally in chunks of 50
results = await manager.submit_tasks("orders", tasks)
# ~33,000 tasks/sec — 12x faster than sequential submit_task()
```

### Task Monitoring
```python
# Check task status
status = await manager.get_task_status("task-123")
print(f"Status: {status.status}")
print(f"Result: {status.result}")
print(f"Error: {status.error}")
print(f"Retries: {status.retry_count}")

# Get all currently running tasks
ongoing = await manager.get_ongoing_tasks()

# Monitor queue health
queue_status = await manager.get_queue_status("api_calls")
print(f"Active Tasks: {queue_status['current_workers']}")
print(f"Circuit Breaker: {queue_status['circuit_breaker_status']}")
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
        max_workers=2,
        max_retries=3,       # Retry failed email sends
        retry_delay=5.0,     # 5s base backoff
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

<!-- BENCHMARK_START -->
## Performance

### v0.2.1 vs arq (head-to-head benchmark)

Single-process enqueue throughput on Redis 7, measured in CI:

| Metric | kew v0.2.1 | arq v0.27.0 | Winner |
|--------|-----------|-----------|--------|
| Mean enqueue latency | 0.67ms | 0.62ms | **arq** |
| Sequential throughput | ~1,525/sec | ~1,585/sec | **arq** |
| Concurrent (gather) | ~3,148/sec | N/A | **kew** |
| Batch (`submit_tasks()`) | **~16,202/sec** | N/A | **kew 10x** |
| End-to-end throughput | ~351/sec | N/A* | **kew** |

\*arq requires separate worker processes; kew runs tasks in-process.

> Numbers from [GitHub Actions](https://github.com/justrach/kew/actions/workflows/benchmark.yml) on `ubuntu-latest` (2026-02-16).

### Version progression

| Version | Throughput | vs v0.1.4 |
|---------|-----------|-----------|
| v0.1.4 | ~850/sec | 1x |
| v0.1.8 | ~1,550/sec | 1.8x |
| v0.2.0 | ~2,990/sec | 3.5x |
| v0.2.1 (sequential) | ~1,525/sec | 1.8x |
| v0.2.1 (concurrent) | ~3,148/sec | 3.7x |
| **v0.2.1 (batch)** | **~16,202/sec** | **19.1x** |

### Key optimizations
- **v0.2.1**: Lock-free submit (Lua atomicity), batch Lua script for N tasks in 1 RTT
- **v0.2.0**: Atomic Lua script, binary Redis, per-queue locks, semaphore reorder, active task SET
- **v0.1.8**: Redis pipelining & batching

<!-- BENCHMARK_END -->
## Version History

See the full changelog in [CHANGELOG.md](CHANGELOG.md).

| Version | Highlights |
|---------|-----------|
| 0.2.1 (current) | Batch submit API (12x arq), lock-free submit, concurrent-safe |
| 0.2.0 | Atomic Lua submit, retries, deferred execution, lifecycle hooks, Redis circuit breaker |
| 0.1.8 | Redis pipelining & batching, 3.4x faster task submission |
| 0.1.7 | Multi-process worker support, Redis task storage ([@Ahmad-cercli](https://github.com/Ahmad-cercli)) |
| 0.1.5 | Faster task pickup, reliable shutdown, Redis 7 support |
| 0.1.4 | Stable async queues, priorities, circuit breakers |

## Roadmap

### Completed
- [x] Batch submit API for high-throughput ingestion (v0.2.1)
- [x] Lock-free atomic submit via Lua scripts (v0.2.1)
- [x] Retry with configurable exponential backoff (v0.2.0)
- [x] Deferred/scheduled task execution (v0.2.0)
- [x] Lifecycle hooks: on_task_start, on_task_complete, on_task_fail (v0.2.0)
- [x] Redis-backed circuit breaker with TTL auto-reset (v0.2.0)
- [x] Binary Redis connection for zero-overhead payloads (v0.2.0)
- [x] Active task set for O(1) ongoing task queries (v0.2.0)
- [x] Redis pipelining & batching (v0.1.8)
- [x] Distributed workers with coordination (v0.1.7 - [@Ahmad-cercli](https://github.com/Ahmad-cercli))

### Planned
- [ ] Dead-letter queue for permanently failed tasks
- [ ] Pause/resume controls and basic admin/health endpoints
- [ ] Metrics and observability (Prometheus/OpenTelemetry)
- [ ] Rate limiting per queue and burst control
- [ ] CLI tooling for inspection and maintenance
- [ ] Web dashboard for task monitoring

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

- `TaskAlreadyExistsError`: Task ID already in use (atomic duplicate detection)
- `TaskNotFoundError`: Task doesn't exist
- `QueueNotFoundError`: Queue not configured
- `QueueProcessorError`: Task processing failed or queue is full

```python
try:
    await manager.submit_task(...)
except TaskAlreadyExistsError:
    # Handle duplicate task
except QueueProcessorError as e:
    # Handle processing error or queue full
    print(f"Task failed: {e}")
```

## Contributing

We welcome contributions! Please check our [Contributing Guide](CONTRIBUTING.md) for details.

## Contributors

Thanks to these wonderful people for their contributions:

| Contributor | Contribution |
|-------------|--------------|
| [@justrach](https://github.com/justrach) | Creator & Maintainer |
| [@Ahmad-cercli](https://github.com/Ahmad-cercli) | Multi-process worker support with Redis task storage ([PR #5](https://github.com/justrach/kew/pull/5)) |

Want to see your name here? Check out the [Contributing Guide](CONTRIBUTING.md)!

## License

MIT License - see the [LICENSE](LICENSE) file for details.
