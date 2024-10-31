from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import threading
from typing import Optional, Dict, Any, Callable
from datetime import datetime
import logging
import asyncio
from .models import TaskStatus, TaskInfo
from .exceptions import TaskAlreadyExistsError, TaskNotFoundError

logger = logging.getLogger(__name__)

class TaskQueueManager:
    def __init__(
        self, 
        max_workers: int = 2,
        queue_size: int = 1000,
        task_timeout: int = 3600
    ):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.queue = Queue(maxsize=queue_size)
        self.task_timeout = task_timeout
        self.tasks: Dict[str, TaskInfo] = {}
        self._lock = threading.Lock()
        self._shutdown = False
        self._setup_logging()

    def _setup_logging(self):
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    async def submit_task(
        self,
        task_id: str,
        task_type: str,
        task_func: Callable,
        *args,
        **kwargs
    ) -> TaskInfo:
        with self._lock:
            if task_id in self.tasks:
                raise TaskAlreadyExistsError(
                    f"Task with ID {task_id} already exists"
                )
            
            task_info = TaskInfo(task_id, task_type)
            self.tasks[task_id] = task_info
            logger.info(f"Task {task_id} ({task_type}) submitted")

        # Create task coroutine
        task = asyncio.create_task(self._execute_task(
            task_id,
            task_func,
            *args,
            **kwargs
        ))
        
        # Store the task for later cleanup
        task_info._task = task
        
        return task_info

    async def _execute_task(
        self,
        task_id: str,
        task_func: Callable,
        *args,
        **kwargs
    ):
        try:
            with self._lock:
                task_info = self.tasks[task_id]
                task_info.status = TaskStatus.PROCESSING
                task_info.started_time = datetime.now()
                logger.info(f"Starting execution of task {task_id}")

            # Execute the task function
            result = await task_func(*args, **kwargs)

            with self._lock:
                task_info.result = result
                task_info.status = TaskStatus.COMPLETED
                task_info.completed_time = datetime.now()
                logger.info(f"Task {task_id} completed successfully with result: {result}")

            return result

        except Exception as e:
            logger.error(f"Error executing task {task_id}: {str(e)}")
            with self._lock:
                task_info = self.tasks[task_id]
                task_info.status = TaskStatus.FAILED
                task_info.error = str(e)
                task_info.completed_time = datetime.now()
            raise

    async def wait_for_task(self, task_id: str, timeout: Optional[float] = None) -> TaskInfo:
        """Wait for a specific task to complete"""
        task_info = self.get_task_status(task_id)
        if hasattr(task_info, '_task'):
            try:
                await asyncio.wait_for(task_info._task, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"Task {task_id} timed out after {timeout} seconds")
                raise
        return task_info

    async def wait_for_all_tasks(self, timeout: Optional[float] = None):
        """Wait for all tasks to complete"""
        tasks = [
            task_info._task for task_info in self.tasks.values()
            if hasattr(task_info, '_task') and not task_info._task.done()
        ]
        if tasks:
            await asyncio.wait(tasks, timeout=timeout)

    def get_task_status(self, task_id: str) -> TaskInfo:
        with self._lock:
            task_info = self.tasks.get(task_id)
            if not task_info:
                raise TaskNotFoundError(f"Task {task_id} not found")
            return task_info

    def get_queue_length(self) -> int:
        return self.queue.qsize()

    def cleanup_old_tasks(self, max_age_hours: int = 24):
        current_time = datetime.now()
        cleaned_count = 0
        with self._lock:
            for task_id, task_info in list(self.tasks.items()):
                if task_info.completed_time:
                    age = current_time - task_info.completed_time
                    if age.total_seconds() > max_age_hours * 3600:
                        del self.tasks[task_id]
                        cleaned_count += 1
        
        logger.info(f"Cleaned up {cleaned_count} old tasks")

    async def shutdown(self):
        logger.info("Shutting down TaskQueueManager")
        self._shutdown = True
        # Wait for pending tasks
        await self.wait_for_all_tasks(timeout=5.0)
        self.executor.shutdown(wait=True)