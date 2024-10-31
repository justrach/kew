from datetime import datetime
from enum import Enum
from typing import Optional, TypeVar, Generic

T = TypeVar('T')  # Generic type for task result

class TaskStatus(Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class TaskInfo(Generic[T]):
    def __init__(self, task_id: str, task_type: str):
        self.task_id = task_id
        self.task_type = task_type
        self.status = TaskStatus.QUEUED
        self.queued_time = datetime.now()
        self.started_time: Optional[datetime] = None
        self.completed_time: Optional[datetime] = None
        self.result: Optional[T] = None
        self.error: Optional[str] = None
    
    def to_dict(self):
        """Convert TaskInfo to dictionary representation"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value,
            "queued_time": self.queued_time.isoformat(),
            "started_time": self.started_time.isoformat() if self.started_time else None,
            "completed_time": self.completed_time.isoformat() if self.completed_time else None,
            "result": self.result,
            "error": self.error
        }
