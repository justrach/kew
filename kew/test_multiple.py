# test_multiple.py
import asyncio
from kew import TaskQueueManager, TaskStatus
import random

async def long_task(task_num: int, sleep_time: int) -> dict:
    """Simulate a long-running task"""
    print(f"Starting task {task_num} (will take {sleep_time} seconds)")
    await asyncio.sleep(sleep_time)
    result = sleep_time * 2
    print(f"Task {task_num} completed with result: {result}")
    return {"task_num": task_num, "result": result}

async def main():
    # Initialize manager with 2 workers (so only 2 tasks can run simultaneously)
    manager = TaskQueueManager(max_workers=2)
    
    # Submit 5 tasks with different durations
    tasks = []
    for i in range(5):
        sleep_time = random.randint(3, 7)  # Random duration between 3-7 seconds
        task_info = await manager.submit_task(
            task_id=f"task{i+1}",
            task_type="long_calculation",
            task_func=long_task,
            task_num=i+1,
            sleep_time=sleep_time
        )
        tasks.append(task_info)
        print(f"Submitted task {i+1}")

    # Monitor task progress
    while True:
        all_completed = True
        print("\nCurrent status:")
        for task in tasks:
            status = manager.get_task_status(task.task_id)
            print(f"{task.task_id}: {status.status.value} - Result: {status.result}")
            if status.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                all_completed = False
        
        if all_completed:
            break
            
        await asyncio.sleep(1)  # Wait a second before checking again

    # Final results
    print("\nFinal results:")
    for task in tasks:
        status = manager.get_task_status(task.task_id)
        print(f"{task.task_id}: {status.result}")

    # Properly await shutdown
    await manager.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")