class TaskQueueError(Exception):
    """Base exception for task queue errors"""
    pass

class TaskAlreadyExistsError(TaskQueueError):
    """Raised when attempting to add a task with an ID that already exists"""
    pass

class TaskNotFoundError(TaskQueueError):
    """Raised when attempting to access a non-existent task"""
    pass

class QueueNotFoundError(TaskQueueError):
    """Raised when attempting to access a non-existent queue"""
    pass

class QueueProcessorError(TaskQueueError):
    """Raised when the queue processor encounters an error"""
    pass