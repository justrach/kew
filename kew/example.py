# example.py
import asyncio
from kew import TaskQueueManager

async def example_task(x: int):
    await asyncio.sleep(1)
    return x * 2

async def main():
    # Initialize the task queue manager
    manager = TaskQueueManager(max_workers=2)
    
    # Submit a task
    task_info = await manager.submit_task(
        task_id="task1",
        task_type="multiplication",
        task_func=example_task,
        x=5
    )
    
    # Get task status
    status = manager.get_task_status("task1")
    print(f"Task status: {status.status}")
    
    # Wait a bit to see the result
    await asyncio.sleep(2)
    status = manager.get_task_status("task1")
    print(f"Final status: {status.status}")
    print(f"Result: {status.result}")
    
    # Cleanup and shutdown - now properly awaited
    manager.cleanup_old_tasks()
    await manager.shutdown()

if __name__ == "__main__":
    asyncio.run(main())