
# Kew Performance Benchmark Results

## System Performance

The following benchmarks were run with:
- 100 total tasks
- 10 concurrent workers
- Multiple computational workloads

### Overall Performance
- Total Duration: 22.04 seconds
- Overall Throughput: 4.54 tasks/second

### Task-Specific Performance

### Large Matrix Multiplication (1000x1000)
| Metric | Value |
|--------|-------|
| Average Latency | 17.815s |
| Median Latency | 17.849s |
| 95th Percentile | 18.208s |
| 99th Percentile | 18.209s |
| Throughput | 1.13 tasks/second |

### Heavy Prime Calculation (up to 10M)
| Metric | Value |
|--------|-------|
| Average Latency | 18.581s |
| Median Latency | 18.555s |
| 95th Percentile | 18.863s |
| 99th Percentile | 18.863s |
| Throughput | 1.13 tasks/second |

### Complex FFT (10M points)
| Metric | Value |
|--------|-------|
| Average Latency | 16.033s |
| Median Latency | 15.951s |
| 95th Percentile | 18.436s |
| 99th Percentile | 18.979s |
| Throughput | 1.13 tasks/second |

### Distributed Data Processing
| Metric | Value |
|--------|-------|
| Average Latency | 8.800s |
| Median Latency | 8.981s |
| 95th Percentile | 11.974s |
| 99th Percentile | 12.649s |
| Throughput | 1.13 tasks/second |


## Load Distribution

Testing load distribution across multiple queues with:
- 3 queues
- 5 workers per queue
- 100 total tasks

### Queue Performance

#### Queue: load_test_queue_0
- Tasks processed: 78
- Average execution time: 0.384s

#### Queue: load_test_queue_1
- Tasks processed: 74
- Average execution time: 0.388s

#### Queue: load_test_queue_2
- Tasks processed: 74
- Average execution time: 0.388s


### Load Balance Score: 0.004s
(Lower score indicates better load distribution)

---
*Benchmark run on 2025-01-10 17:16:56*

## Extended Performance Comparison

### 1. Heavy Workload Performance

| Queue System | Total Duration (s) | Throughput (tasks/s) | Recovery from Failures | Data Persistence |
|--------------|-------------------|---------------------|---------------------|------------------|
| Kew | 22.04 | 4.54 | Yes | Yes |
| asyncio.Queue | 42.74 | 4.68 | No | No |
| multiprocessing.Queue | ERROR | ERROR | Limited | No |

### Error Notes
- multiprocessing.Queue benchmark failed with: `None`
- This error occurs because multiprocessing cannot pickle async functions across process boundaries
- This limitation demonstrates why distributed task queues like Kew are necessary for complex distributed workloads
