"""
Kew v0.2.0 vs arq v0.27.0 — Head-to-head benchmark

Tests:
  1. Enqueue latency (single task submission time)
  2. Enqueue throughput (tasks/sec for bulk submission)
  3. End-to-end throughput (submit → complete for batch of tasks)

Usage: python bench_kew_vs_arq.py
"""
import asyncio
import logging
import statistics
import sys
import time

# Suppress noisy logs during benchmarks
logging.getLogger("kew.manager").setLevel(logging.WARNING)
logging.getLogger("arq").setLevel(logging.WARNING)

# ─── Kew ──────────────────────────────────────────────────────────────────────

async def bench_kew_enqueue_latency(n: int = 500):
    from kew import TaskQueueManager, QueueConfig, QueuePriority

    async def noop(x: int) -> int:
        return x

    mgr = TaskQueueManager(cleanup_on_start=True)
    await mgr.initialize()
    await mgr.create_queue(QueueConfig(name="bench", max_workers=50, max_size=n + 100))

    # Warm up
    for i in range(5):
        await mgr.submit_task(
            task_id=f"warmup-{i}", queue_name="bench",
            task_type="noop", task_func=noop, priority=QueuePriority.MEDIUM, x=i,
        )
    await asyncio.sleep(0.1)
    await mgr.shutdown()

    # Fresh manager for real benchmark
    mgr = TaskQueueManager(cleanup_on_start=True)
    await mgr.initialize()
    await mgr.create_queue(QueueConfig(name="bench", max_workers=50, max_size=n + 100))

    times = []
    for i in range(n):
        t0 = time.perf_counter()
        await mgr.submit_task(
            task_id=f"kew-{i}", queue_name="bench",
            task_type="noop", task_func=noop, priority=QueuePriority.MEDIUM, x=i,
        )
        times.append((time.perf_counter() - t0) * 1000)

    await mgr.shutdown()
    return times


async def bench_kew_throughput(n: int = 500):
    from kew import TaskQueueManager, QueueConfig, QueuePriority

    async def noop(x: int) -> int:
        return x

    mgr = TaskQueueManager(cleanup_on_start=True)
    await mgr.initialize()
    await mgr.create_queue(QueueConfig(name="tp", max_workers=50, max_size=n + 100))

    t0 = time.perf_counter()
    for i in range(n):
        await mgr.submit_task(
            task_id=f"tp-{i}", queue_name="tp",
            task_type="noop", task_func=noop, priority=QueuePriority.MEDIUM, x=i,
        )
    enqueue_time = time.perf_counter() - t0

    await mgr.shutdown()
    return n / enqueue_time, enqueue_time


async def bench_kew_e2e(n: int = 200):
    from kew import TaskQueueManager, QueueConfig, QueuePriority, TaskStatus

    async def fast_task(x: int) -> int:
        return x * 2

    mgr = TaskQueueManager(cleanup_on_start=True)
    await mgr.initialize()
    await mgr.create_queue(QueueConfig(name="e2e", max_workers=50, max_size=n + 100))

    t0 = time.perf_counter()
    task_ids = []
    for i in range(n):
        t = await mgr.submit_task(
            task_id=f"e2e-{i}", queue_name="e2e",
            task_type="fast", task_func=fast_task, priority=QueuePriority.MEDIUM, x=i,
        )
        task_ids.append(t.task_id)

    # Poll until all complete
    for _ in range(300):  # 30s timeout
        done = 0
        for tid in task_ids:
            try:
                s = await mgr.get_task_status(tid)
                if s.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                    done += 1
            except Exception:
                pass
        if done == n:
            break
        await asyncio.sleep(0.1)

    elapsed = time.perf_counter() - t0
    await mgr.shutdown()
    return n / elapsed, elapsed


# ─── arq ──────────────────────────────────────────────────────────────────────

async def bench_arq_enqueue_latency(n: int = 500):
    from arq import create_pool
    from arq.connections import RedisSettings

    pool = await create_pool(RedisSettings())

    # Clean queue
    await pool.delete("arq:queue")

    times = []
    for i in range(n):
        t0 = time.perf_counter()
        await pool.enqueue_job("noop", i, _job_id=f"arq-{i}")
        times.append((time.perf_counter() - t0) * 1000)

    await pool.aclose()
    return times


async def bench_arq_throughput(n: int = 500):
    from arq import create_pool
    from arq.connections import RedisSettings

    pool = await create_pool(RedisSettings())
    await pool.delete("arq:queue")

    t0 = time.perf_counter()
    for i in range(n):
        await pool.enqueue_job("noop", i, _job_id=f"arq-tp-{i}")
    enqueue_time = time.perf_counter() - t0

    await pool.aclose()
    return n / enqueue_time, enqueue_time


async def bench_arq_e2e(n: int = 200):
    """arq e2e requires a separate worker process, so we measure enqueue-only
    for fair comparison. arq's worker model makes true e2e benchmarking
    from a single script impractical without subprocess coordination."""
    from arq import create_pool
    from arq.connections import RedisSettings

    pool = await create_pool(RedisSettings())
    await pool.delete("arq:queue")

    t0 = time.perf_counter()
    for i in range(n):
        await pool.enqueue_job("fast_task", i, _job_id=f"arq-e2e-{i}")
    elapsed = time.perf_counter() - t0

    await pool.aclose()
    return n / elapsed, elapsed


# ─── Runner ───────────────────────────────────────────────────────────────────

def fmt_ms(times):
    return (
        f"mean={statistics.mean(times):.3f}ms  "
        f"median={statistics.median(times):.3f}ms  "
        f"p95={sorted(times)[int(len(times) * 0.95)]:.3f}ms  "
        f"p99={sorted(times)[int(len(times) * 0.99)]:.3f}ms"
    )


async def main():
    N_LATENCY = 500
    N_THROUGHPUT = 1000
    N_E2E = 200

    print("=" * 70)
    print("  KEW v0.2.0 vs arq v0.27.0 — HEAD-TO-HEAD BENCHMARK")
    print("=" * 70)
    print(f"  Enqueue latency:    {N_LATENCY} tasks")
    print(f"  Enqueue throughput: {N_THROUGHPUT} tasks")
    print(f"  End-to-end:         {N_E2E} tasks")
    print("=" * 70)

    # ── 1. Enqueue latency ──
    print("\n[1] ENQUEUE LATENCY (single task submission time)")
    print("-" * 50)

    kew_times = await bench_kew_enqueue_latency(N_LATENCY)
    print(f"  kew:  {fmt_ms(kew_times)}")

    arq_times = await bench_arq_enqueue_latency(N_LATENCY)
    print(f"  arq:  {fmt_ms(arq_times)}")

    speedup = statistics.mean(arq_times) / statistics.mean(kew_times)
    winner = "kew" if speedup > 1 else "arq"
    print(f"  → {winner} is {max(speedup, 1/speedup):.1f}x faster")

    # ── 2. Enqueue throughput ──
    print(f"\n[2] ENQUEUE THROUGHPUT ({N_THROUGHPUT} tasks, sequential)")
    print("-" * 50)

    kew_tps, kew_time = await bench_kew_throughput(N_THROUGHPUT)
    print(f"  kew:  {kew_tps:,.0f} tasks/sec  ({kew_time:.3f}s)")

    arq_tps, arq_time = await bench_arq_throughput(N_THROUGHPUT)
    print(f"  arq:  {arq_tps:,.0f} tasks/sec  ({arq_time:.3f}s)")

    speedup = kew_tps / arq_tps
    winner = "kew" if speedup > 1 else "arq"
    print(f"  → {winner} is {max(speedup, 1/speedup):.1f}x faster")

    # ── 3. End-to-end ──
    print(f"\n[3] END-TO-END (submit → complete, {N_E2E} tasks)")
    print("-" * 50)

    kew_e2e_tps, kew_e2e_time = await bench_kew_e2e(N_E2E)
    print(f"  kew:  {kew_e2e_tps:,.0f} tasks/sec  ({kew_e2e_time:.3f}s)")

    arq_e2e_tps, arq_e2e_time = await bench_arq_e2e(N_E2E)
    print(f"  arq:  {arq_e2e_tps:,.0f} tasks/sec  ({arq_e2e_time:.3f}s enqueue-only*)")
    print(f"  * arq requires a separate worker process for execution;")
    print(f"    this measures enqueue time only for arq vs full e2e for kew")

    print("\n" + "=" * 70)
    print("  DONE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
