import asyncio
import random
from kew import TaskQueueManager, QueueConfig, QueuePriority, TaskStatus

async def long_task(task_num: int, sleep_time: int) -> dict:
    """Simulate a long-running task"""
    print(f"Starting task {task_num} (will take {sleep_time} seconds)")
    await asyncio.sleep(sleep_time)
    result = sleep_time * 2
    print(f"Task {task_num} completed with result: {result}")
    return {"task_num": task_num, "result": result}

async def run_tasks():
    # Initialize manager with Redis connection and cleanup
    manager = TaskQueueManager(
        redis_url="redis://localhost:6379",
        cleanup_on_start=True  # This will clean up existing queues on start
    )
    await manager.initialize()
    
    try:
        # Create queues
        await manager.create_queue(QueueConfig(
            name="fast_track",
            max_workers=2,
            priority=QueuePriority.HIGH
        ))
        
        await manager.create_queue(QueueConfig(
            name="standard",
            max_workers=1,
            priority=QueuePriority.LOW
        ))
        
        tasks = []
        
        # Submit 3 high-priority tasks
        for i in range(3):
            sleep_time = random.randint(2, 4)
            task_info = await manager.submit_task(
                task_id=f"high_task_{i+1}",
                queue_name="fast_track",
                task_type="long_calculation",
                task_func=long_task,
                priority=QueuePriority.HIGH,
                task_num=i+1,
                sleep_time=sleep_time
            )
            tasks.append(task_info)
        
        # Submit 2 low-priority tasks
        for i in range(2):
            sleep_time = random.randint(1, 3)
            task_info = await manager.submit_task(
                task_id=f"low_task_{i+1}",
                queue_name="standard",
                task_type="long_calculation",
                task_func=long_task,
                priority=QueuePriority.LOW,
                task_num=i+1,
                sleep_time=sleep_time
            )
            tasks.append(task_info)

        # Monitor progress
        while True:
            all_completed = True
            print("\nCurrent status:")
            for task in tasks:
                status = await manager.get_task_status(task.task_id)
                print(f"{task.task_id} ({task.queue_name}): {status.status.value} - Result: {status.result}")
                if status.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                    all_completed = False
            
            if all_completed:
                break
                
            await asyncio.sleep(1)

        # Final queue statuses
        print("\nFinal Queue Statuses:")
        print("Fast Track Queue:", await manager.get_queue_status("fast_track"))
        print("Standard Queue:", await manager.get_queue_status("standard"))

    finally:
        # Ensure manager is properly shut down
        await manager.shutdown()

async def main():
    try:
        await run_tasks()
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
    except Exception as e:
        print(f"Error occurred: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())