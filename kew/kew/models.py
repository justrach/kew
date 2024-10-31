from datetime import datetime
from enum import Enum
from typing import Optional, TypeVar, Generic
from dataclasses import dataclass

T = TypeVar('T')  # Generic type for task result

class TaskStatus(Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class QueuePriority(Enum):
    HIGH = 1
    MEDIUM = 2
    LOW = 3

@dataclass
class QueueConfig:
    """Configuration for a single queue"""
    name: str
    max_workers: int
    priority: QueuePriority = QueuePriority.MEDIUM
    max_size: int = 1000
    task_timeout: int = 3600

class TaskInfo(Generic[T]):
    def __init__(self, task_id: str, task_type: str, queue_name: str, priority: int):
        self.task_id = task_id
        self.task_type = task_type
        self.queue_name = queue_name
        self.priority = priority
        self.status = TaskStatus.QUEUED
        self.queued_time = datetime.now()
        self.started_time: Optional[datetime] = None
        self.completed_time: Optional[datetime] = None
        self.result: Optional[T] = None
        self.error: Optional[str] = None
    
    def to_dict(self):
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "queue_name": self.queue_name,
            "priority": self.priority,
            "status": self.status.value,
            "queued_time": self.queued_time.isoformat(),
            "started_time": self.started_time.isoformat() if self.started_time else None,
            "completed_time": self.completed_time.isoformat() if self.completed_time else None,
            "result": self.result,
            "error": self.error
        }
