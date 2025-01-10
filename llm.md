
# **Kew: A Lightweight Python Task Queue Manager**

Kew is a **Redis-backed asynchronous task queue** built for simplicity, efficiency, and scalability. With support for features like **priority-based scheduling**, **circuit breaker patterns**, and **customizable worker pools**, it’s designed to address the gaps in task management for Python developers.

---

## **Features**

- **Priority-Based Queues**  
  Tasks can be scheduled with `HIGH`, `MEDIUM`, or `LOW` priorities, ensuring critical tasks are executed first.

- **Circuit Breaker**  
  Built-in fault tolerance to prevent cascading failures during execution.

- **Configurable Worker Pools**  
  Set the number of workers per queue to optimize resource usage for different workloads.

- **Redis-Backed Persistence**  
  Reliable storage for tasks and queues with easy integration into distributed systems.

---

## **Installation**

Install Kew using pip:

\`\`\`bash
pip install kew
\`\`\`

---

## **Setup**

### **Initialization**
Connect Kew to your Redis instance and clean up old tasks on startup:

\`\`\`python
from kew import TaskQueueManager

task_manager = TaskQueueManager(redis_url="redis://localhost:6379")

async def initialize():
    await task_manager.initialize()
    print("Task Manager Initialized")
\`\`\`

### **Create Queues**
Define queues with configurable settings:

\`\`\`python
from kew import QueueConfig, QueuePriority

await task_manager.create_queue(
    QueueConfig(
        name="document_processing",
        max_workers=3,
        max_size=100,
        priority=QueuePriority.HIGH
    )
)
\`\`\`

---

## **Submit Tasks**

Submit tasks to the queues:

\`\`\`python
async def process_document(document_id: str):
    # Simulate document processing
    print(f"Processing document {document_id}")
    await asyncio.sleep(5)
    return {"status": "success"}

await task_manager.submit_task(
    task_id="doc123",
    queue_name="document_processing",
    task_type="process",
    task_func=process_document,
    priority=QueuePriority.HIGH,
    document_id="doc123"
)
\`\`\`

---

## **Monitor and Manage**

### **Get Queue Status**
Retrieve the current status of a queue:

\`\`\`python
status = await task_manager.get_queue_status("document_processing")
print(f"Queue Status: {status}")
\`\`\`

### **Check Task Status**
Monitor the progress of tasks:

\`\`\`python
from kew import TaskStatus

task_info = await task_manager.get_task_status("doc123")
if task_info.status == TaskStatus.COMPLETED:
    print("Task completed successfully!")
\`\`\`

---

## **Production Use Case**

Below is a real-world example where Kew is used in a FastAPI application to process documents asynchronously.

### **Queue Initialization in FastAPI**
\`\`\`python
from kew import QueueConfig, QueuePriority

app = FastAPI()

@app.on_event("startup")
async def startup():
    await task_manager.initialize()

    await task_manager.create_queue(
        QueueConfig(
            name="document_processing",
            max_workers=3,
            max_size=100,
            priority=QueuePriority.HIGH
        )
    )
    print("Queues initialized")
\`\`\`

### **Submit Document Processing Tasks**
\`\`\`python
@app.post("/process-document/")
async def process_document(document_id: str):
    async def process():
        print(f"Processing document {document_id}")
        await asyncio.sleep(5)  # Simulate processing
        return {"status": "processed"}
    
    await task_manager.submit_task(
        task_id=f"process_{document_id}",
        queue_name="document_processing",
        task_type="process",
        task_func=process,
        priority=QueuePriority.HIGH
    )
    return {"message": "Task submitted"}
\`\`\`

### **Monitor Queue and Tasks**
\`\`\`python
@app.get("/queue-status/")
async def queue_status():
    return await task_manager.get_queue_status("document_processing")

@app.get("/task-status/{task_id}")
async def task_status(task_id: str):
    try:
        return await task_manager.get_task_status(task_id)
    except TaskNotFoundError:
        return {"status": "Task not found"}
\`\`\`

---

## **Advanced Features**

### Circuit Breaker for Fault Tolerance
Kew prevents continuous task failures by implementing a circuit breaker pattern. After repeated failures, the circuit breaker stops task execution for a specified timeout.

---

## **Why Use Kew?**

- **Lightweight**: Minimal setup and dependency requirements.
- **Flexible**: Ideal for both small-scale projects and enterprise systems.
- **Robust**: Built-in features like circuit breakers and Redis-backed persistence.
- **Developer-Friendly**: Designed to reduce boilerplate code and complexity.

---

## **Conclusion**

Kew is a simple yet powerful task management library tailored for Python developers. Whether you’re handling document processing, API integrations, or complex workflows, Kew provides the tools you need to streamline task execution.

Get started today by [installing Kew](https://pypi.org/project/kew/) and joining the community of developers building better systems with less effort!
