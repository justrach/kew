from typing import Optional, Dict, Any, Callable, List
from datetime import datetime, timedelta
import logging
import asyncio
import json
import redis.asyncio as redis
from .models import TaskStatus, TaskInfo, QueueConfig, QueuePriority
from .exceptions import (
    TaskAlreadyExistsError, 
    TaskNotFoundError, 
    QueueNotFoundError,
    QueueProcessorError
)

logger = logging.getLogger(__name__)

class CircuitBreaker:
    def __init__(self, max_failures: int = 3, reset_timeout: int = 60):
        self.max_failures = max_failures
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure_time = None
        self.is_open = False

    async def record_failure(self):
        self.failures += 1
        self.last_failure_time = datetime.now()
        if self.failures >= self.max_failures:
            self.is_open = True
            logger.error("Circuit breaker opened due to multiple failures")

    async def reset(self):
        self.failures = 0
        self.last_failure_time = None
        self.is_open = False

    async def check_state(self):
        if not self.is_open:
            return True
        
        if self.last_failure_time and \
           (datetime.now() - self.last_failure_time).seconds > self.reset_timeout:
            await self.reset()
            return True
        return False

class QueueWorkerPool:
    def __init__(self, config: QueueConfig):
        self.config = config
        self._shutdown = False
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self.circuit_breaker = CircuitBreaker()
        self.processing_semaphore = asyncio.Semaphore(config.max_workers)
        self.start_processing = asyncio.Event()  # Add this line
class TaskQueueManager:
    TASK_EXPIRY_SECONDS = 86400  # 24 hours
    QUEUE_KEY_PREFIX = "queue:"
    TASK_KEY_PREFIX = "task:"
    
    def __init__(self, redis_url: str = "redis://localhost:6379", cleanup_on_start: bool = True):
        self.queues: Dict[str, QueueWorkerPool] = {}
        self._lock = asyncio.Lock()
        self._redis: Optional[redis.Redis] = None
        self._redis_url = redis_url
        self._shutdown_event = asyncio.Event()
        self._cleanup_on_start = cleanup_on_start
        self._setup_logging()

    def _setup_logging(self):
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    async def initialize(self):
        self._redis = redis.from_url(
            self._redis_url,
            encoding="utf-8",
            decode_responses=True
        )
        logger.info("Connected to Redis")

        if self._cleanup_on_start:
            await self.cleanup()

    async def cleanup(self):
        if not self._redis:
            return
            
        async for key in self._redis.scan_iter(f"{self.QUEUE_KEY_PREFIX}*"):
            await self._redis.delete(key)
            
        async for key in self._redis.scan_iter(f"{self.TASK_KEY_PREFIX}*"):
            await self._redis.delete(key)
            
        logger.info("Cleaned up all existing queues and tasks")

    async def create_queue(self, config: QueueConfig):
        async with self._lock:
            if config.name in self.queues:
                raise ValueError(f"Queue {config.name} already exists")
            
            worker_pool = QueueWorkerPool(config)
            self.queues[config.name] = worker_pool
            
            await self._redis.hset(
                f"{self.QUEUE_KEY_PREFIX}{config.name}",
                mapping={
                    "max_workers": config.max_workers,
                    "max_size": config.max_size,
                    "priority": config.priority.value
                }
            )
            
            asyncio.create_task(self._process_queue(config.name))
            logger.info(f"Created queue {config.name} with {config.max_workers} workers")

    async def submit_task(
        self,
        task_id: str,
        queue_name: str,
        task_type: str,
        task_func: Callable,
        priority: QueuePriority,
        *args,
        **kwargs
    ) -> TaskInfo:
        """Submit a task to a queue"""
        async with self._lock:
            if queue_name not in self.queues:
                raise QueueNotFoundError(f"Queue {queue_name} not found")
            worker_pool = self.queues[queue_name]
            queue_key = f"{self.QUEUE_KEY_PREFIX}{queue_name}:tasks"

            # Enforce max queue size (backpressure)
            queue_len = await self._redis.zcard(queue_key)
            if queue_len >= worker_pool.config.max_size:
                raise QueueProcessorError(f"Queue {queue_name} is full (max_size={worker_pool.config.max_size})")

            # Duplicate protection by task_id
            existing = await self._redis.get(f"{self.TASK_KEY_PREFIX}{task_id}")
            if existing is not None:
                raise TaskAlreadyExistsError(f"Task {task_id} already exists")

            task_info = TaskInfo(
                task_id=task_id,
                task_type=task_type,
                queue_name=queue_name,
                priority=priority.value
            )
            
            # Store function and args for local execution
            worker_pool._tasks[task_id] = {
                'func': task_func,
                'args': args,
                'kwargs': kwargs,
                'task': None
            }
            
            await self._redis.set(
                f"{self.TASK_KEY_PREFIX}{task_id}",
                task_info.to_json(),
                ex=self.TASK_EXPIRY_SECONDS
            )
            
            # New scoring system:
            # score = priority * 1_000_000 + timestamp
            # This ensures:
            # 1. Priority is the primary factor (lower value = higher priority)
            # 2. Within same priority, earlier tasks come first
            current_time = int(datetime.now().timestamp() * 1000)  # milliseconds
            score = (priority.value * 1_000_000) + current_time
            
            await self._redis.zadd(
                queue_key,
                {task_id: score}
            )
            
            logger.info(f"Task {task_id} submitted to queue {queue_name}")
            return task_info
    
    async def _process_queue(self, queue_name: str):
        """Process tasks in the queue"""
        worker_pool = self.queues[queue_name]
        queue_key = f"{self.QUEUE_KEY_PREFIX}{queue_name}:tasks"
        
        while not self._shutdown_event.is_set():
            try:
                # Skip processing if circuit is open
                if not await worker_pool.circuit_breaker.check_state():
                    await asyncio.sleep(0.5)
                    continue

                # Acquire a worker slot (blocks until available)
                await worker_pool.processing_semaphore.acquire()

                try:
                    # Atomically pop the next task by priority
                    popped = await self._redis.zpopmin(queue_key, 1)

                    if not popped:
                        # Release the semaphore if no task is available
                        worker_pool.processing_semaphore.release()
                        # Lower idle delay to improve responsiveness
                        await asyncio.sleep(0.02)
                        continue

                    task_id = popped[0][0]
                    if isinstance(task_id, bytes):
                        task_id = task_id.decode('utf-8')

                    task_info_data = await self._redis.get(f"{self.TASK_KEY_PREFIX}{task_id}")
                    if not task_info_data:
                        worker_pool.processing_semaphore.release()
                        continue
                        
                    task_info = TaskInfo.from_json(task_info_data)
                    
                    if task_info.status == TaskStatus.QUEUED:
                        task_data = worker_pool._tasks.get(task_id)
                        if not task_data:
                            worker_pool.processing_semaphore.release()
                            continue

                        func = task_data['func']
                        args = task_data.get('args', ())
                        kwargs = task_data.get('kwargs', {})
                        task_info.status = TaskStatus.PROCESSING
                        task_info.started_time = datetime.now()
                        
                        await self._redis.set(
                            f"{self.TASK_KEY_PREFIX}{task_id}",
                            task_info.to_json(),
                            ex=self.TASK_EXPIRY_SECONDS
                        )
                        
                        # Create task and store it
                        task = asyncio.create_task(self._execute_task(task_id, func, args, kwargs))
                        worker_pool._tasks[task_id]['task'] = task
                        
                        # Add callback to release semaphore when task completes
                        def _on_done(_):
                            try:
                                # Cleanup local task store to prevent memory growth
                                worker_pool._tasks.pop(task_id, None)
                            finally:
                                worker_pool.processing_semaphore.release()

                        task.add_done_callback(_on_done)
                    else:
                        worker_pool.processing_semaphore.release()
                
                except Exception as e:
                    worker_pool.processing_semaphore.release()
                    logger.error(f"Error processing task in queue {queue_name}: {str(e)}")
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error in queue {queue_name}: {str(e)}")
                await asyncio.sleep(1)
    async def _execute_task(self, task_id: str, func: Callable, args: tuple, kwargs: dict):
        """Execute a single task and update its status"""
        try:
            # Determine timeout from queue config
            task_info_data_pre = await self._redis.get(f"{self.TASK_KEY_PREFIX}{task_id}")
            queue_name = None
            timeout = None
            if task_info_data_pre:
                ti = TaskInfo.from_json(task_info_data_pre)
                queue_name = ti.queue_name
                if queue_name in self.queues:
                    timeout = self.queues[queue_name].config.task_timeout

            if timeout and timeout > 0:
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
            else:
                result = await func(*args, **kwargs)
            task_info_data = await self._redis.get(f"{self.TASK_KEY_PREFIX}{task_id}")
            if task_info_data:
                task_info = TaskInfo.from_json(task_info_data)
                task_info.status = TaskStatus.COMPLETED
                task_info.result = result
                task_info.completed_time = datetime.now()
                
                await self._redis.set(
                    f"{self.TASK_KEY_PREFIX}{task_id}",
                    task_info.to_json(),
                    ex=self.TASK_EXPIRY_SECONDS
                )
                logger.info(f"Task {task_id} completed successfully")
                # Reset circuit breaker on success
                if queue_name and queue_name in self.queues:
                    await self.queues[queue_name].circuit_breaker.reset()
                
        except asyncio.TimeoutError:
            logger.error(f"Task {task_id} timed out")
            task_info_data = await self._redis.get(f"{self.TASK_KEY_PREFIX}{task_id}")
            if task_info_data:
                task_info = TaskInfo.from_json(task_info_data)
                task_info.status = TaskStatus.FAILED
                task_info.error = "Task timed out"
                task_info.completed_time = datetime.now()
                await self._redis.set(
                    f"{self.TASK_KEY_PREFIX}{task_id}",
                    task_info.to_json(),
                    ex=self.TASK_EXPIRY_SECONDS
                )
            # Record failure in circuit breaker
            task_info_data_pre = await self._redis.get(f"{self.TASK_KEY_PREFIX}{task_id}")
            if task_info_data_pre:
                ti = TaskInfo.from_json(task_info_data_pre)
                if ti.queue_name in self.queues:
                    await self.queues[ti.queue_name].circuit_breaker.record_failure()
        except Exception as e:
            logger.error(f"Task {task_id} failed: {str(e)}")
            task_info_data = await self._redis.get(f"{self.TASK_KEY_PREFIX}{task_id}")
            if task_info_data:
                task_info = TaskInfo.from_json(task_info_data)
                task_info.status = TaskStatus.FAILED
                task_info.error = str(e)
                task_info.completed_time = datetime.now()
                
                await self._redis.set(
                    f"{self.TASK_KEY_PREFIX}{task_id}",
                    task_info.to_json(),
                    ex=self.TASK_EXPIRY_SECONDS
                )
            # Record failure in circuit breaker
            task_info_data_pre = await self._redis.get(f"{self.TASK_KEY_PREFIX}{task_id}")
            if task_info_data_pre:
                ti = TaskInfo.from_json(task_info_data_pre)
                if ti.queue_name in self.queues:
                    await self.queues[ti.queue_name].circuit_breaker.record_failure()
    async def get_task_status(self, task_id: str) -> TaskInfo:
        task_data = await self._redis.get(f"{self.TASK_KEY_PREFIX}{task_id}")
        if not task_data:
            raise TaskNotFoundError(f"Task {task_id} not found")
        return TaskInfo.from_json(task_data)

    async def get_queue_status(self, queue_name: str) -> Dict[str, Any]:
        if queue_name not in self.queues:
            raise QueueNotFoundError(f"Queue {queue_name} not found")
        
        worker_pool = self.queues[queue_name]
        queue_size = await self._redis.zcard(f"{self.QUEUE_KEY_PREFIX}{queue_name}:tasks")
        
        return {
            "name": queue_name,
            "max_workers": worker_pool.config.max_workers,
            # Approximate active workers as max - available semaphore permits
            "current_workers": worker_pool.config.max_workers - worker_pool.processing_semaphore._value,
            "queued_tasks": queue_size,
            "circuit_breaker_status": "open" if worker_pool.circuit_breaker.is_open else "closed"
        }

    async def shutdown(self, wait: bool = True, timeout: float = 5.0):
        logger.info("Shutting down TaskQueueManager")
        self._shutdown_event.set()
        
        if wait:
            for queue_name, worker_pool in self.queues.items():
                worker_pool._shutdown = True
                active_tasks = []
                for task_data in worker_pool._tasks.values():
                    if isinstance(task_data, dict) and task_data.get('task'):
                        active_tasks.append(task_data['task'])
                
                if active_tasks:
                    try:
                        # Give active tasks a chance to complete
                        await asyncio.wait(active_tasks, timeout=timeout)
                    except Exception as e:
                        logger.error(f"Error waiting for tasks in queue {queue_name}: {str(e)}")
            # Allow done callbacks to run and persist final statuses
            await asyncio.sleep(0.05)
        
        if self._redis:
            # Use aclose() to properly close async Redis client
            await self._redis.aclose()
            logger.info("Closed Redis connection")
    async def get_ongoing_tasks(self) -> List[TaskInfo]:
        """Get all tasks that are currently being processed."""
        ongoing_tasks = []
        
        # Scan through all task keys
        async for key in self._redis.scan_iter(f"{self.TASK_KEY_PREFIX}*"):
            task_data = await self._redis.get(key)
            if task_data:
                task_info = TaskInfo.from_json(task_data)
                if task_info.status == TaskStatus.PROCESSING:
                    ongoing_tasks.append(task_info)
        
        return ongoing_tasks