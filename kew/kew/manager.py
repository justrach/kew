# kew/kew/manager.py
from concurrent.futures import ThreadPoolExecutor
from queue import PriorityQueue, Queue
import threading
from typing import Optional, Dict, Any, Callable, List, Tuple
from datetime import datetime
import logging
import asyncio
from .models import TaskStatus, TaskInfo, QueueConfig, QueuePriority
from .exceptions import TaskAlreadyExistsError, TaskNotFoundError, QueueNotFoundError

logger = logging.getLogger(__name__)

class PrioritizedItem:
    def __init__(self, priority: int, item: Any):
        self.priority = priority
        self.item = item
        self.timestamp = datetime.now()

    def __lt__(self, other):
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.timestamp < other.timestamp

class QueueWorkerPool:
    """Manages workers for a specific queue"""
    def __init__(self, config: QueueConfig):
        self.config = config
        self.executor = ThreadPoolExecutor(max_workers=config.max_workers)
        self.queue: PriorityQueue[PrioritizedItem] = PriorityQueue(maxsize=config.max_size)
        self._shutdown = False
        self._tasks: Dict[str, asyncio.Task] = {}

class TaskQueueManager:
    def __init__(self):
        """Initialize TaskQueueManager with multiple queue support"""
        self.queues: Dict[str, QueueWorkerPool] = {}
        self.tasks: Dict[str, TaskInfo] = {}
        self._lock = threading.Lock()
        self._setup_logging()

    def _setup_logging(self):
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    def create_queue(self, config: QueueConfig):
        """Create a new queue with specified configuration"""
        with self._lock:
            if config.name in self.queues:
                raise ValueError(f"Queue {config.name} already exists")
            worker_pool = QueueWorkerPool(config)
            self.queues[config.name] = worker_pool
            logger.info(f"Created queue {config.name} with {config.max_workers} workers")
            
            # Start queue processor
            asyncio.create_task(self._process_queue(config.name))

    async def _process_queue(self, queue_name: str):
        """Process tasks in the queue"""
        worker_pool = self.queues[queue_name]
        
        while not worker_pool._shutdown:
            try:
                if not worker_pool.queue.empty():
                    prioritized_item = worker_pool.queue.get_nowait()
                    task_id = prioritized_item.item
                    
                    with self._lock:
                        task_info = self.tasks[task_id]
                        if task_info.status == TaskStatus.QUEUED:
                            # Execute task
                            task_info.status = TaskStatus.PROCESSING
                            task_info.started_time = datetime.now()
                            logger.info(f"Processing task {task_id} from queue {queue_name}")
                            
                            # Create task
                            task = asyncio.create_task(task_info._func(*task_info._args, **task_info._kwargs))
                            worker_pool._tasks[task_id] = task
                            
                            # Add completion callback
                            task.add_done_callback(
                                lambda f, tid=task_id: self._handle_task_completion(tid, f)
                            )
                
                await asyncio.sleep(0.1)  # Small delay to prevent busy waiting
                
            except Exception as e:
                logger.error(f"Error processing queue {queue_name}: {str(e)}")
                await asyncio.sleep(1)  # Longer delay on error

    async def submit_task(
        self,
        task_id: str,
        queue_name: str,
        task_type: str,
        task_func: Callable,
        priority: QueuePriority = QueuePriority.MEDIUM,
        *args,
        **kwargs
    ) -> TaskInfo:
        """Submit a task to a specific queue"""
        with self._lock:
            if task_id in self.tasks:
                raise TaskAlreadyExistsError(
                    f"Task with ID {task_id} already exists"
                )
            
            if queue_name not in self.queues:
                raise QueueNotFoundError(
                    f"Queue {queue_name} not found"
                )
            
            worker_pool = self.queues[queue_name]
            task_info = TaskInfo(task_id, task_type, queue_name, priority.value)
            
            # Store function and arguments for later execution
            task_info._func = task_func
            task_info._args = args
            task_info._kwargs = kwargs
            
            self.tasks[task_id] = task_info
            
            # Add to priority queue
            worker_pool.queue.put(PrioritizedItem(
                priority=priority.value,
                item=task_id
            ))
            
            logger.info(f"Task {task_id} submitted to queue {queue_name}")
            
            return task_info

    def _handle_task_completion(self, task_id: str, future: asyncio.Future):
        """Handle task completion and cleanup"""
        try:
            result = future.result()
            with self._lock:
                task_info = self.tasks[task_id]
                task_info.result = result
                task_info.status = TaskStatus.COMPLETED
                task_info.completed_time = datetime.now()
                logger.info(f"Task {task_id} completed successfully with result: {result}")
                
                # Clean up task
                worker_pool = self.queues[task_info.queue_name]
                if task_id in worker_pool._tasks:
                    del worker_pool._tasks[task_id]
                    
        except Exception as e:
            logger.error(f"Task {task_id} failed: {str(e)}")
            with self._lock:
                task_info = self.tasks[task_id]
                task_info.status = TaskStatus.FAILED
                task_info.error = str(e)
                task_info.completed_time = datetime.now()

    def get_task_status(self, task_id: str) -> TaskInfo:
        """Get status of a specific task"""
        with self._lock:
            task_info = self.tasks.get(task_id)
            if not task_info:
                raise TaskNotFoundError(f"Task {task_id} not found")
            return task_info

    def get_queue_status(self, queue_name: str) -> Dict[str, Any]:
        """Get status of a specific queue"""
        with self._lock:
            if queue_name not in self.queues:
                raise QueueNotFoundError(f"Queue {queue_name} not found")
            
            worker_pool = self.queues[queue_name]
            queue_tasks = [
                task for task in self.tasks.values()
                if task.queue_name == queue_name
            ]
            
            return {
                "name": queue_name,
                "max_workers": worker_pool.config.max_workers,
                "priority": worker_pool.config.priority.value,
                "active_tasks": len([t for t in queue_tasks if t.status == TaskStatus.PROCESSING]),
                "queued_tasks": len([t for t in queue_tasks if t.status == TaskStatus.QUEUED]),
                "completed_tasks": len([t for t in queue_tasks if t.status == TaskStatus.COMPLETED]),
                "failed_tasks": len([t for t in queue_tasks if t.status == TaskStatus.FAILED])
            }

    async def wait_for_task(self, task_id: str, timeout: Optional[float] = None) -> TaskInfo:
        """Wait for a specific task to complete"""
        task_info = self.get_task_status(task_id)
        worker_pool = self.queues[task_info.queue_name]
        
        if task_id in worker_pool._tasks:
            try:
                await asyncio.wait_for(worker_pool._tasks[task_id], timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"Task {task_id} timed out after {timeout} seconds")
                raise
        
        return task_info

    async def wait_for_queue(self, queue_name: str, timeout: Optional[float] = None):
        """Wait for all tasks in a specific queue to complete"""
        if queue_name not in self.queues:
            raise QueueNotFoundError(f"Queue {queue_name} not found")
            
        worker_pool = self.queues[queue_name]
        tasks = list(worker_pool._tasks.values())
        
        if tasks:
            await asyncio.wait(tasks, timeout=timeout)

    def cleanup_old_tasks(self, max_age_hours: int = 24, queue_name: Optional[str] = None):
        """Clean up completed tasks, optionally for a specific queue"""
        current_time = datetime.now()
        cleaned_count = 0
        with self._lock:
            for task_id, task_info in list(self.tasks.items()):
                if queue_name and task_info.queue_name != queue_name:
                    continue
                    
                if task_info.completed_time:
                    age = current_time - task_info.completed_time
                    if age.total_seconds() > max_age_hours * 3600:
                        del self.tasks[task_id]
                        cleaned_count += 1
        
        logger.info(f"Cleaned up {cleaned_count} old tasks")

    async def shutdown(self, wait: bool = True):
        """Shutdown all queues"""
        logger.info("Shutting down TaskQueueManager")
        
        # Wait for pending tasks if requested
        if wait:
            for queue_name, worker_pool in self.queues.items():
                tasks = list(worker_pool._tasks.values())
                if tasks:
                    try:
                        await asyncio.wait(tasks, timeout=5.0)
                    except Exception as e:
                        logger.error(f"Error waiting for tasks in queue {queue_name}: {str(e)}")
        
        # Shutdown all worker pools
        for queue_name, worker_pool in self.queues.items():
            worker_pool._shutdown = True
            worker_pool.executor.shutdown(wait=wait)
            logger.info(f"Shut down queue {queue_name}")