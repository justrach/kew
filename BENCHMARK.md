
# Kew Performance Benchmark Results


## System Information

| Component | Details |
|-----------|---------|
| Operating System | Darwin Darwin Kernel Version 24.1.0: Thu Nov 14 18:15:21 PST 2024; root:xnu-11215.41.3~13/RELEASE_ARM64_T6041 |
| Python Version | 3.12.5 |
| Processor | arm |
| CPU Cores | 14 |
| CPU Frequency | 4.00MHz |
| Total Memory | 48.0GB |
| Available Memory | 16.0GB |


## System Performance

The following benchmarks were run with:
- 100 total tasks
- 10 concurrent workers
- Multiple computational workloads

### Overall Performance
- Total Duration: 22.30 seconds
- Overall Throughput: 4.48 tasks/second

### Task-Specific Performance

### Large Matrix Multiplication (1000x1000)
| Metric | Value |
|--------|-------|
| Average Latency | 17.681s |
| Median Latency | 17.696s |
| 95th Percentile | 18.040s |
| 99th Percentile | 18.049s |
| Throughput | 1.12 tasks/second |

### Heavy Prime Calculation (up to 10M)
| Metric | Value |
|--------|-------|
| Average Latency | 18.409s |
| Median Latency | 18.390s |
| 95th Percentile | 18.734s |
| 99th Percentile | 18.743s |
| Throughput | 1.12 tasks/second |

### Complex FFT (10M points)
| Metric | Value |
|--------|-------|
| Average Latency | 16.209s |
| Median Latency | 15.958s |
| 95th Percentile | 18.852s |
| 99th Percentile | 18.861s |
| Throughput | 1.12 tasks/second |

### Distributed Data Processing
| Metric | Value |
|--------|-------|
| Average Latency | 9.173s |
| Median Latency | 9.349s |
| 95th Percentile | 12.984s |
| 99th Percentile | 12.985s |
| Throughput | 1.12 tasks/second |


## Load Distribution

Testing load distribution across multiple queues with:
- 3 queues
- 5 workers per queue
- 100 total tasks

### Queue Performance

#### Queue: load_test_queue_0
- Tasks processed: 73
- Average execution time: 0.378s

#### Queue: load_test_queue_1
- Tasks processed: 69
- Average execution time: 0.382s

#### Queue: load_test_queue_2
- Tasks processed: 66
- Average execution time: 0.389s


### Load Balance Score: 0.011s
(Lower score indicates better load distribution)

---
*Benchmark run on 2025-01-10 17:19:50*

## Extended Performance Comparison

### 1. Heavy Workload Performance

| Queue System | Total Duration (s) | Throughput (tasks/s) | Recovery from Failures | Data Persistence |
|--------------|-------------------|---------------------|---------------------|------------------|
| Kew | 22.30 | 4.48 | Yes | Yes |
| asyncio.Queue | 43.71 | 4.58 | No | No |
| multiprocessing.Queue | ERROR | ERROR | Limited | No |

### Error Notes
- multiprocessing.Queue benchmark failed with: `None`
- This error occurs because multiprocessing cannot pickle async functions across process boundaries
- This limitation demonstrates why distributed task queues like Kew are necessary for complex distributed workloads
