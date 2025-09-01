import asyncio
from kew import TaskQueueManager, QueueConfig, QueuePriority

async def example_task(x: int):
    await asyncio.sleep(1)
    return x * 2

async def main():
    # Create manager
    manager = TaskQueueManager()
    await manager.initialize()
    
    # Create queues
    await manager.create_queue(QueueConfig(
        name="critical",
        max_workers=4,
        priority=QueuePriority.HIGH
    ))
    
    await manager.create_queue(QueueConfig(
        name="background",
        max_workers=1,
        priority=QueuePriority.LOW
    ))
    
    # Submit tasks to different queues
    task1 = await manager.submit_task(
        task_id="task1",
        queue_name="critical",
        task_type="multiplication",
        task_func=example_task,
        priority=QueuePriority.HIGH,
        x=5
    )
    
    task2 = await manager.submit_task(
        task_id="task2",
        queue_name="background",
        task_type="multiplication",
        task_func=example_task,
        priority=QueuePriority.LOW,
        x=10
    )
    
    # Get initial queue statuses
    print("\nInitial Queue Statuses:")
    print("Critical Queue:", await manager.get_queue_status("critical"))
    print("Background Queue:", await manager.get_queue_status("background"))
    
    # Wait for tasks to complete
    await asyncio.sleep(2)
    
    # Get final queue statuses
    print("\nFinal Queue Statuses:")
    print("Critical Queue:", await manager.get_queue_status("critical"))
    print("Background Queue:", await manager.get_queue_status("background"))
    
    # Get task results
    task1_status = await manager.get_task_status("task1")
    task2_status = await manager.get_task_status("task2")
    
    print("\nTask Results:")
    print(f"Task 1 (Critical): {task1_status.result}")
    print(f"Task 2 (Background): {task2_status.result}")
    
    # Shutdown
    await manager.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
