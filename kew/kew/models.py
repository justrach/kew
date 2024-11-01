from datetime import datetime
from enum import Enum
from typing import Optional, TypeVar, Generic, Dict, Any
from dataclasses import dataclass
import json
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
T = TypeVar('T')  # Generic type for task result

@dataclass
class QueueConfig:
    """Configuration for a single queue"""
    name: str
    max_workers: int
    priority: QueuePriority = QueuePriority.MEDIUM
    max_size: int = 1000
    task_timeout: int = 3600

class TaskInfo(Generic[T]):
    def __init__(
        self,
        task_id: str,
        task_type: str,
        queue_name: str,
        priority: int,
        status: TaskStatus = TaskStatus.QUEUED  # Made optional with default
    ):
        self.task_id = task_id
        self.task_type = task_type
        self.queue_name = queue_name
        self.priority = priority
        self.status = status
        self.queued_time = datetime.now()
        self.started_time: Optional[datetime] = None
        self.completed_time: Optional[datetime] = None
        self.result: Optional[T] = None
        self.error: Optional[str] = None
        # Store function and arguments for execution
        self._func = None
        self._args = ()
        self._kwargs = {}
    
    def to_dict(self) -> Dict[str, Any]:
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

    def to_json(self) -> str:
        """Convert task info to JSON string"""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> 'TaskInfo':
        """Create TaskInfo instance from JSON string"""
        data = json.loads(json_str)
        task = cls(
            task_id=data["task_id"],
            task_type=data["task_type"],
            queue_name=data["queue_name"],
            priority=data["priority"],
            status=TaskStatus(data["status"])
        )
        task.queued_time = datetime.fromisoformat(data["queued_time"])
        task.started_time = datetime.fromisoformat(data["started_time"]) if data["started_time"] else None
        task.completed_time = datetime.fromisoformat(data["completed_time"]) if data["completed_time"] else None
        task.result = data["result"]
        task.error = data["error"]
        return task