"""
Redis Performance Benchmarks for Kew

Run before optimizations to establish baseline, then after to measure improvement.
Usage: cd kew && python -m benchmarks.redis_benchmark
"""
import asyncio
import sys
import time
import statistics

sys.path.insert(0, ".")
from kew import TaskQueueManager, QueueConfig, QueuePriority


async def dummy_task(x: int) -> int:
    return x * 2


class BenchmarkSuite:
    def __init__(self, iterations: int = 100):
        self.iterations = iterations
        self.results = {}

    async def setup(self):
        self.manager = TaskQueueManager(cleanup_on_start=True)
        await self.manager.initialize()
        await self.manager.create_queue(
            QueueConfig(name="bench", max_workers=10, max_size=10000)
        )

    async def teardown(self):
        await self.manager.shutdown()

    async def bench_submit_task(self) -> dict:
        """Benchmark: submit_task latency (tests pipelining optimization)"""
        times = []
        for i in range(self.iterations):
            start = time.perf_counter()
            await self.manager.submit_task(
                task_id=f"bench-submit-{i}",
                queue_name="bench",
                task_type="dummy",
                task_func=dummy_task,
                priority=QueuePriority.MEDIUM,
                x=i,
            )
            times.append((time.perf_counter() - start) * 1000)  # ms

        return {
            "operation": "submit_task",
            "iterations": self.iterations,
            "mean_ms": statistics.mean(times),
            "median_ms": statistics.median(times),
            "p95_ms": sorted(times)[int(self.iterations * 0.95)],
            "total_ms": sum(times),
        }

    async def bench_cleanup(self) -> dict:
        """Benchmark: cleanup with many keys (tests batch delete optimization)"""
        # Create 500 tasks first
        for i in range(500):
            await self.manager._redis.set(f"task:cleanup-bench-{i}", f"data-{i}")
            await self.manager._redis.set(
                f"task_payload:cleanup-bench-{i}", f"payload-{i}"
            )

        start = time.perf_counter()
        await self.manager.cleanup()
        elapsed = (time.perf_counter() - start) * 1000

        return {
            "operation": "cleanup_500_keys",
            "total_ms": elapsed,
        }

    async def bench_get_ongoing_tasks(self) -> dict:
        """Benchmark: get_ongoing_tasks with many tasks (tests MGET optimization)"""
        from kew.models import TaskInfo, TaskStatus

        # Create 200 task entries using proper TaskInfo serialization
        for i in range(200):
            task = TaskInfo(
                task_id=f"ongoing-{i}",
                task_type="test",
                queue_name="bench",
                priority=2,
                status=TaskStatus.PROCESSING,
            )
            await self.manager._redis.set(f"task:ongoing-{i}", task.to_json())

        times = []
        for _ in range(10):
            start = time.perf_counter()
            await self.manager.get_ongoing_tasks()
            times.append((time.perf_counter() - start) * 1000)

        # Cleanup
        for i in range(200):
            await self.manager._redis.delete(f"task:ongoing-{i}")

        return {
            "operation": "get_ongoing_tasks_200",
            "iterations": 10,
            "mean_ms": statistics.mean(times),
            "median_ms": statistics.median(times),
        }

    async def bench_task_throughput(self) -> dict:
        """Benchmark: end-to-end task throughput"""
        # Create a fresh manager for this test to avoid interference
        throughput_manager = TaskQueueManager(cleanup_on_start=True)
        await throughput_manager.initialize()
        await throughput_manager.create_queue(
            QueueConfig(name="throughput", max_workers=20, max_size=10000)
        )

        start = time.perf_counter()
        tasks = []
        for i in range(100):
            t = await throughput_manager.submit_task(
                task_id=f"throughput-{i}",
                queue_name="throughput",
                task_type="dummy",
                task_func=dummy_task,
                priority=QueuePriority.MEDIUM,
                x=i,
            )
            tasks.append(t)

        # Wait for all to complete with timeout
        max_wait = 30  # seconds
        wait_start = time.perf_counter()
        while time.perf_counter() - wait_start < max_wait:
            completed = 0
            for t in tasks:
                try:
                    status = await throughput_manager.get_task_status(t.task_id)
                    if status.status.value in ("completed", "failed"):
                        completed += 1
                except Exception:
                    pass
            if completed == len(tasks):
                break
            await asyncio.sleep(0.01)

        elapsed = time.perf_counter() - start
        await throughput_manager.shutdown()

        return {
            "operation": "throughput_100_tasks",
            "total_seconds": elapsed,
            "tasks_per_second": 100 / elapsed,
        }

    async def run_all(self):
        await self.setup()
        print("=" * 60)
        print("KEW REDIS PERFORMANCE BENCHMARKS")
        print("=" * 60)

        benchmarks = [
            self.bench_submit_task,
            self.bench_cleanup,
            self.bench_get_ongoing_tasks,
            self.bench_task_throughput,
        ]

        for bench in benchmarks:
            try:
                result = await bench()
                self.results[result["operation"]] = result
                print(f"\n{result['operation']}:")
                for k, v in result.items():
                    if k != "operation":
                        if isinstance(v, float):
                            print(f"  {k}: {v:.3f}")
                        else:
                            print(f"  {k}: {v}")
            except Exception as e:
                print(f"\n{bench.__name__}: FAILED - {e}")
                import traceback

                traceback.print_exc()

        await self.teardown()
        return self.results


async def main():
    suite = BenchmarkSuite(iterations=100)
    await suite.run_all()


if __name__ == "__main__":
    asyncio.run(main())
