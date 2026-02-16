import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Generic, Optional, TypeVar, Union

T = TypeVar("T")


class TaskStatus(Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"


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
    max_circuit_breaker_failures: int = 3
    circuit_breaker_reset_timeout: int = 60
    max_retries: int = 0
    retry_delay: float = 1.0


class TaskInfo(Generic[T]):
    def __init__(
        self,
        task_id: str,
        task_type: str,
        queue_name: str,
        priority: int,
        status: TaskStatus = TaskStatus.QUEUED,
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
        self.retry_count: int = 0
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
            "started_time": (
                self.started_time.isoformat() if self.started_time else None
            ),
            "completed_time": (
                self.completed_time.isoformat() if self.completed_time else None
            ),
            "result": self.result,
            "error": self.error,
            "retry_count": self.retry_count,
        }

    def to_json(self) -> str:
        """Convert task info to JSON string"""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> "TaskInfo":
        """Create TaskInfo instance from JSON string"""
        data = json.loads(json_str)
        task = cls(
            task_id=data["task_id"],
            task_type=data["task_type"],
            queue_name=data["queue_name"],
            priority=data["priority"],
            status=TaskStatus(data["status"]),
        )
        task.queued_time = datetime.fromisoformat(data["queued_time"])
        task.started_time = (
            datetime.fromisoformat(data["started_time"])
            if data["started_time"]
            else None
        )
        task.completed_time = (
            datetime.fromisoformat(data["completed_time"])
            if data["completed_time"]
            else None
        )
        task.result = data["result"]
        task.error = data["error"]
        task.retry_count = data.get("retry_count", 0)
        return task
