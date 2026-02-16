import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Union

import cloudpickle
import redis.asyncio as redis

from .exceptions import (
    QueueNotFoundError,
    QueueProcessorError,
    TaskAlreadyExistsError,
    TaskNotFoundError,
)
from .models import QueueConfig, QueuePriority, TaskInfo, TaskStatus

logger = logging.getLogger(__name__)

# Lua script for atomic task submission.
# Stores task_info, payload, and queue entry in a single round-trip.
# Returns: 0 = success, -1 = task already exists, -2 = queue full
_SUBMIT_SCRIPT = """
local task_key = KEYS[1]
local payload_key = KEYS[2]
local queue_key = KEYS[3]
local max_size = tonumber(ARGV[1])
local task_json = ARGV[2]
local expiry = tonumber(ARGV[3])
local payload = ARGV[4]
local score = tonumber(ARGV[5])
local task_id = ARGV[6]
if redis.call('EXISTS', task_key) == 1 then
    return -1
end
if redis.call('ZCARD', queue_key) >= max_size then
    return -2
end
redis.call('SET', task_key, task_json, 'EX', expiry)
redis.call('SET', payload_key, payload, 'EX', expiry)
redis.call('ZADD', queue_key, score, task_id)
return 0
"""

# Priority multiplier: 10 trillion ms (~317 years) separation between levels
# Ensures priority ALWAYS dominates over timestamp ordering
_PRIORITY_MULTIPLIER = 10_000_000_000_000


class RedisCircuitBreaker:
    """Circuit breaker backed by Redis for multi-process correctness.

    Uses Redis key expiry for automatic reset: when the 'open' key expires
    after reset_timeout seconds, the circuit automatically closes.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        queue_name: str,
        max_failures: int = 3,
        reset_timeout: int = 60,
    ):
        self._redis = redis_client
        self._prefix = f"kew:circuit:{queue_name}"
        self.max_failures = max_failures
        self.reset_timeout = reset_timeout

    async def record_failure(self):
        pipe = self._redis.pipeline()
        pipe.incr(f"{self._prefix}:failures")
        pipe.expire(f"{self._prefix}:failures", self.reset_timeout * 2)
        results = await pipe.execute()
        failure_count = results[0]
        if failure_count >= self.max_failures:
            await self._redis.set(
                f"{self._prefix}:open", "1", ex=self.reset_timeout
            )
            logger.error(
                f"Circuit breaker opened for queue (failures={failure_count})"
            )

    async def reset(self):
        pipe = self._redis.pipeline()
        pipe.delete(f"{self._prefix}:failures")
        pipe.delete(f"{self._prefix}:open")
        await pipe.execute()

    async def check_state(self) -> bool:
        """Returns True if circuit is closed (healthy), False if open."""
        is_open = await self._redis.get(f"{self._prefix}:open")
        return is_open is None


class QueueWorkerPool:
    def __init__(self, config: QueueConfig):
        self.config = config
        self._shutdown = False
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self.circuit_breaker: Optional[RedisCircuitBreaker] = None
        self.processing_semaphore = asyncio.Semaphore(config.max_workers)
        self._submit_lock = asyncio.Lock()


class TaskQueueManager:
    TASK_EXPIRY_SECONDS = 86400  # 24 hours
    QUEUE_KEY_PREFIX = "queue:"
    TASK_KEY_PREFIX = "task:"
    TASK_PAYLOAD_PREFIX = "task_payload:"
    ACTIVE_TASKS_KEY = "kew:active_tasks"

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        cleanup_on_start: bool = True,
        on_task_start: Optional[Callable] = None,
        on_task_complete: Optional[Callable] = None,
        on_task_fail: Optional[Callable] = None,
    ):
        self.queues: Dict[str, QueueWorkerPool] = {}
        self._lock = asyncio.Lock()  # Only for create_queue
        self._redis: Optional[redis.Redis] = None
        self._redis_binary: Optional[redis.Redis] = None
        self._redis_url = redis_url
        self._shutdown_event = asyncio.Event()
        self._cleanup_on_start = cleanup_on_start
        self._submit_script = None
        # Lifecycle hooks
        self._on_task_start = on_task_start
        self._on_task_complete = on_task_complete
        self._on_task_fail = on_task_fail
        self._setup_logging()

    def _setup_logging(self):
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    async def initialize(self):
        # Text connection for JSON task info
        self._redis = redis.from_url(
            self._redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
        # Binary connection for cloudpickle payloads (no base64 needed)
        self._redis_binary = redis.from_url(
            self._redis_url,
            decode_responses=False,
            max_connections=50,
        )
        # Register the Lua submit script on the binary connection
        # (it handles both text task_info and binary payload in one round-trip)
        self._submit_script = self._redis_binary.register_script(_SUBMIT_SCRIPT)

        logger.info("Connected to Redis")

        if self._cleanup_on_start:
            await self.cleanup()

    async def cleanup(self):
        if not self._redis:
            return

        keys_to_delete = []
        for prefix in [
            self.QUEUE_KEY_PREFIX,
            self.TASK_KEY_PREFIX,
            self.TASK_PAYLOAD_PREFIX,
            "kew:circuit:",
        ]:
            async for key in self._redis.scan_iter(f"{prefix}*"):
                keys_to_delete.append(key)

        # Also clean up the active tasks set
        keys_to_delete.append(self.ACTIVE_TASKS_KEY)

        if keys_to_delete:
            for i in range(0, len(keys_to_delete), 1000):
                chunk = keys_to_delete[i : i + 1000]
                await self._redis.unlink(*chunk)

        logger.info("Cleaned up all existing queues and tasks")

    async def create_queue(self, config: QueueConfig):
        async with self._lock:
            if config.name in self.queues:
                raise ValueError(f"Queue {config.name} already exists")

            worker_pool = QueueWorkerPool(config)
            worker_pool.circuit_breaker = RedisCircuitBreaker(
                redis_client=self._redis,
                queue_name=config.name,
                max_failures=config.max_circuit_breaker_failures,
                reset_timeout=config.circuit_breaker_reset_timeout,
            )
            self.queues[config.name] = worker_pool

            await self._redis.hset(
                f"{self.QUEUE_KEY_PREFIX}{config.name}",
                mapping={
                    "max_workers": config.max_workers,
                    "max_size": config.max_size,
                    "priority": config.priority.value,
                    "max_circuit_breaker_failures": config.max_circuit_breaker_failures,
                    "max_retries": config.max_retries,
                    "retry_delay": config.retry_delay,
                },
            )

            asyncio.create_task(self._process_queue(config.name))
            logger.info(
                f"Created queue {config.name} with {config.max_workers} workers"
            )

    async def submit_task(
        self,
        task_id: str,
        queue_name: str,
        task_type: str,
        task_func: Callable,
        priority: QueuePriority,
        *args,
        _defer_until: Optional[datetime] = None,
        _defer_by: Optional[Union[int, float, timedelta]] = None,
        **kwargs,
    ) -> TaskInfo:
        """Submit a task to a queue.

        Args:
            task_id: Unique identifier for the task
            queue_name: Name of the queue to submit to
            task_type: Type label for the task
            task_func: Async callable to execute
            priority: Task priority (HIGH, MEDIUM, LOW)
            *args: Positional arguments for task_func
            _defer_until: Execute task at this datetime (mutually exclusive with _defer_by)
            _defer_by: Delay execution by this many seconds or timedelta
            **kwargs: Keyword arguments for task_func

        Returns:
            TaskInfo instance for the submitted task
        """
        if queue_name not in self.queues:
            raise QueueNotFoundError(f"Queue {queue_name} not found")

        if _defer_until and _defer_by:
            raise ValueError(
                "Use either '_defer_until' or '_defer_by', not both"
            )

        worker_pool = self.queues[queue_name]

        async with worker_pool._submit_lock:
            queue_key = f"{self.QUEUE_KEY_PREFIX}{queue_name}:tasks"

            task_info = TaskInfo(
                task_id=task_id,
                task_type=task_type,
                queue_name=queue_name,
                priority=priority.value,
            )

            # Serialize function and args with cloudpickle (binary, no base64)
            task_payload = cloudpickle.dumps(
                {"func": task_func, "args": args, "kwargs": kwargs}
            )

            # Score calculation: priority * multiplier + execution_time_ms
            current_time_ms = int(time.time() * 1000)

            if _defer_until is not None:
                exec_time_ms = int(_defer_until.timestamp() * 1000)
            elif _defer_by is not None:
                if isinstance(_defer_by, timedelta):
                    defer_ms = int(_defer_by.total_seconds() * 1000)
                else:
                    defer_ms = int(_defer_by * 1000)
                exec_time_ms = current_time_ms + defer_ms
            else:
                exec_time_ms = current_time_ms

            score = (priority.value * _PRIORITY_MULTIPLIER) + exec_time_ms

            # Single round-trip: Lua script atomically checks existence,
            # checks queue size, stores task_info, stores payload, and
            # adds to queue sorted set.
            payload_key = f"{self.TASK_PAYLOAD_PREFIX}{task_id}"
            result = await self._submit_script(
                keys=[
                    f"{self.TASK_KEY_PREFIX}{task_id}",
                    payload_key,
                    queue_key,
                ],
                args=[
                    worker_pool.config.max_size,
                    task_info.to_json(),
                    self.TASK_EXPIRY_SECONDS,
                    task_payload,
                    score,
                    task_id,
                ],
            )

            if result == -1:
                raise TaskAlreadyExistsError(f"Task {task_id} already exists")
            elif result == -2:
                raise QueueProcessorError(
                    f"Queue {queue_name} is full "
                    f"(max_size={worker_pool.config.max_size})"
                )

            logger.info(f"Task {task_id} submitted to queue {queue_name}")
            return task_info

    async def _process_queue(self, queue_name: str):
        """Process tasks in the queue."""
        worker_pool = self.queues[queue_name]
        queue_key = f"{self.QUEUE_KEY_PREFIX}{queue_name}:tasks"

        while not self._shutdown_event.is_set():
            try:
                # Skip processing if circuit is open
                if not await worker_pool.circuit_breaker.check_state():
                    await asyncio.sleep(0.5)
                    continue


                # Atomically pop the lowest-scored ready task
                popped = await self._redis.zpopmin(queue_key, 1)

                if not popped:
                    await asyncio.sleep(0.02)
                    continue

                task_id = popped[0][0]
                task_score = popped[0][1]

                if isinstance(task_id, bytes):
                    task_id = task_id.decode("utf-8")

                # Check if task is deferred by extracting the time component
                # Score = priority * _PRIORITY_MULTIPLIER + exec_time_ms
                # Extract exec_time_ms by taking score modulo _PRIORITY_MULTIPLIER
                exec_time_ms = task_score % _PRIORITY_MULTIPLIER
                now_ms = int(time.time() * 1000)

                if exec_time_ms > now_ms:
                    # Put it back — not ready yet
                    await self._redis.zadd(queue_key, {task_id: task_score})
                    await asyncio.sleep(0.1)
                    continue

                # We have real work — now acquire a worker slot
                await worker_pool.processing_semaphore.acquire()

                try:
                    # Pipeline: fetch task_info and payload together
                    pipe = self._redis.pipeline()
                    pipe.get(f"{self.TASK_KEY_PREFIX}{task_id}")
                    results = await pipe.execute()

                    task_info_data = results[0]

                    # Fetch binary payload from binary connection
                    payload_data = await self._redis_binary.get(
                        f"{self.TASK_PAYLOAD_PREFIX}{task_id}"
                    )

                    if not task_info_data:
                        worker_pool.processing_semaphore.release()
                        continue

                    task_info = TaskInfo.from_json(task_info_data)

                    if task_info.status not in (TaskStatus.QUEUED, TaskStatus.RETRY):
                        worker_pool.processing_semaphore.release()
                        continue

                    if not payload_data:
                        logger.error(
                            f"Task payload not found for {task_id}, dropping task"
                        )
                        worker_pool.processing_semaphore.release()
                        continue

                    try:
                        payload = cloudpickle.loads(payload_data)
                        func = payload["func"]
                        args = payload.get("args", ())
                        kwargs = payload.get("kwargs", {})
                    except Exception as e:
                        logger.error(
                            f"Failed to deserialize task {task_id}: {e}"
                        )
                        worker_pool.processing_semaphore.release()
                        continue

                    task_info.status = TaskStatus.PROCESSING
                    task_info.started_time = datetime.now()

                    # Track active task and update status in one pipeline
                    pipe = self._redis.pipeline()
                    pipe.set(
                        f"{self.TASK_KEY_PREFIX}{task_id}",
                        task_info.to_json(),
                        ex=self.TASK_EXPIRY_SECONDS,
                    )
                    pipe.sadd(self.ACTIVE_TASKS_KEY, task_id)
                    await pipe.execute()

                    async def _runner(
                        tid: str,
                        f: Callable,
                        a: tuple,
                        kw: dict,
                        qname: str,
                        tinfo: TaskInfo,
                    ):
                        try:
                            await self._execute_task(tinfo, f, a, kw, qname)
                        finally:
                            worker_pool._tasks.pop(tid, None)
                            try:
                                # Remove from active set
                                await self._redis.srem(
                                    self.ACTIVE_TASKS_KEY, tid
                                )
                                # Only delete payload if task is terminal
                                # (keep it for retries)
                                if tinfo.status in (
                                    TaskStatus.COMPLETED,
                                    TaskStatus.FAILED,
                                ):
                                    await self._redis_binary.delete(
                                        f"{self.TASK_PAYLOAD_PREFIX}{tid}"
                                    )
                            except Exception as e:
                                logger.warning(
                                    f"Failed cleanup for {tid}: {e}"
                                )
                            worker_pool.processing_semaphore.release()

                    task = asyncio.create_task(
                        _runner(
                            task_id, func, args, kwargs, queue_name, task_info
                        )
                    )
                    worker_pool._tasks[task_id] = {"task": task}

                except Exception as e:
                    worker_pool.processing_semaphore.release()
                    logger.error(
                        f"Error processing task in queue {queue_name}: {str(e)}"
                    )
                    await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error in queue {queue_name}: {str(e)}")
                await asyncio.sleep(1)

    async def _execute_task(
        self,
        task_info: TaskInfo,
        func: Callable,
        args: tuple,
        kwargs: dict,
        queue_name: str,
    ):
        """Execute a single task and update its status."""
        timeout = None
        if queue_name in self.queues:
            timeout = self.queues[queue_name].config.task_timeout

        # Lifecycle hook: on_task_start
        if self._on_task_start:
            try:
                result = self._on_task_start(task_info)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning(f"on_task_start hook error: {e}")

        try:
            if timeout and timeout > 0:
                result = await asyncio.wait_for(
                    func(*args, **kwargs), timeout=timeout
                )
            else:
                result = await func(*args, **kwargs)

            task_info.status = TaskStatus.COMPLETED
            task_info.result = result
            task_info.completed_time = datetime.now()

            await self._redis.set(
                f"{self.TASK_KEY_PREFIX}{task_info.task_id}",
                task_info.to_json(),
                ex=self.TASK_EXPIRY_SECONDS,
            )
            logger.info(f"Task {task_info.task_id} completed successfully")

            if queue_name in self.queues:
                await self.queues[queue_name].circuit_breaker.reset()

            # Lifecycle hook: on_task_complete
            if self._on_task_complete:
                try:
                    result = self._on_task_complete(task_info)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.warning(f"on_task_complete hook error: {e}")

        except (asyncio.TimeoutError, Exception) as e:
            is_timeout = isinstance(e, asyncio.TimeoutError)
            error_msg = "Task timed out" if is_timeout else str(e)

            if is_timeout:
                logger.error(f"Task {task_info.task_id} timed out")
            else:
                logger.error(f"Task {task_info.task_id} failed: {error_msg}")

            # Check if we should retry
            config = self.queues.get(queue_name)
            if config and task_info.retry_count < config.config.max_retries:
                task_info.retry_count += 1
                task_info.status = TaskStatus.RETRY
                task_info.error = error_msg

                # Calculate retry delay with exponential backoff
                delay = config.config.retry_delay * (2 ** (task_info.retry_count - 1))
                retry_time_ms = int(time.time() * 1000) + int(delay * 1000)
                retry_score = (
                    task_info.priority * _PRIORITY_MULTIPLIER
                ) + retry_time_ms

                # Re-enqueue with delay
                pipe = self._redis.pipeline()
                pipe.set(
                    f"{self.TASK_KEY_PREFIX}{task_info.task_id}",
                    task_info.to_json(),
                    ex=self.TASK_EXPIRY_SECONDS,
                )
                pipe.zadd(
                    f"{self.QUEUE_KEY_PREFIX}{queue_name}:tasks",
                    {task_info.task_id: retry_score},
                )
                await pipe.execute()

                logger.info(
                    f"Task {task_info.task_id} scheduled for retry "
                    f"{task_info.retry_count}/{config.config.max_retries} "
                    f"in {delay:.1f}s"
                )
            else:
                task_info.status = TaskStatus.FAILED
                task_info.error = error_msg
                task_info.completed_time = datetime.now()

                await self._redis.set(
                    f"{self.TASK_KEY_PREFIX}{task_info.task_id}",
                    task_info.to_json(),
                    ex=self.TASK_EXPIRY_SECONDS,
                )

            if queue_name in self.queues:
                await self.queues[queue_name].circuit_breaker.record_failure()

            # Lifecycle hook: on_task_fail
            if self._on_task_fail:
                try:
                    result = self._on_task_fail(task_info, e)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as hook_err:
                    logger.warning(f"on_task_fail hook error: {hook_err}")

    async def get_task_status(self, task_id: str) -> TaskInfo:
        task_data = await self._redis.get(f"{self.TASK_KEY_PREFIX}{task_id}")
        if not task_data:
            raise TaskNotFoundError(f"Task {task_id} not found")
        return TaskInfo.from_json(task_data)

    async def get_queue_status(self, queue_name: str) -> Dict[str, Any]:
        if queue_name not in self.queues:
            raise QueueNotFoundError(f"Queue {queue_name} not found")

        worker_pool = self.queues[queue_name]
        queue_size = await self._redis.zcard(
            f"{self.QUEUE_KEY_PREFIX}{queue_name}:tasks"
        )

        return {
            "name": queue_name,
            "max_workers": worker_pool.config.max_workers,
            "current_workers": worker_pool.config.max_workers
            - worker_pool.processing_semaphore._value,
            "queued_tasks": queue_size,
            "circuit_breaker_status": "open"
            if not await worker_pool.circuit_breaker.check_state()
            else "closed",
        }

    async def shutdown(self, wait: bool = True, timeout: float = 5.0):
        logger.info("Shutting down TaskQueueManager")
        self._shutdown_event.set()

        if wait:
            for queue_name, worker_pool in self.queues.items():
                worker_pool._shutdown = True
                active_tasks = []
                for task_data in worker_pool._tasks.values():
                    if isinstance(task_data, dict) and task_data.get("task"):
                        active_tasks.append(task_data["task"])

                if active_tasks:
                    try:
                        await asyncio.wait(active_tasks, timeout=timeout)
                    except Exception as e:
                        logger.error(
                            f"Error waiting for tasks in queue {queue_name}: {str(e)}"
                        )
            await asyncio.sleep(0.05)

        if self._redis:
            await self._redis.aclose()
        if self._redis_binary:
            await self._redis_binary.aclose()
        logger.info("Closed Redis connections")

    async def get_ongoing_tasks(self) -> List[TaskInfo]:
        """Get all tasks that are currently being processed.
        Uses an active task set instead of SCAN for O(active) instead of O(all_keys).
        """
        task_ids = await self._redis.smembers(self.ACTIVE_TASKS_KEY)

        if not task_ids:
            return []

        # Fetch task info for all active task IDs
        keys = [f"{self.TASK_KEY_PREFIX}{tid}" for tid in task_ids]
        ongoing_tasks = []

        for i in range(0, len(keys), 500):
            chunk = keys[i : i + 500]
            results = await self._redis.mget(*chunk)

            for task_data in results:
                if task_data:
                    task_info = TaskInfo.from_json(task_data)
                    if task_info.status == TaskStatus.PROCESSING:
                        ongoing_tasks.append(task_info)

        return ongoing_tasks
