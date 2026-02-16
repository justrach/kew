#!/usr/bin/env python3
"""Update README.md performance section from benchmark JSON.

Usage:
    python scripts/update_readme_benchmarks.py benchmark_results.json README.md
"""
import json
import re
import sys
from pathlib import Path


def fmt_throughput(n: float) -> str:
    return f"~{n:,.0f}/sec"


def fmt_ms(n: float) -> str:
    return f"{n:.2f}ms"


def generate_performance_section(data: dict) -> str:
    r = data["results"]
    kew_v = data["kew_version"]
    arq_v = data["arq_version"]
    ts = data["timestamp"][:10]  # date only

    lat = r["enqueue_latency"]
    seq = r["sequential_throughput"]
    conc = r["concurrent_throughput"]
    batch = r["batch_throughput"]
    e2e = r["e2e_throughput"]

    baseline = 850  # v0.1.4 historical
    seq_ratio = seq["kew"]["tasks_per_sec"] / baseline
    conc_ratio = conc["kew"]["tasks_per_sec"] / baseline
    batch_ratio = batch["kew"]["tasks_per_sec"] / baseline

    return f"""## Performance

### v{kew_v} vs arq (head-to-head benchmark)

Single-process enqueue throughput on Redis 7, measured in CI:

| Metric | kew v{kew_v} | arq v{arq_v} | Winner |
|--------|-----------|-----------|--------|
| Mean enqueue latency | {fmt_ms(lat['kew']['mean_ms'])} | {fmt_ms(lat['arq']['mean_ms'])} | **{lat['winner']}** |
| Sequential throughput | {fmt_throughput(seq['kew']['tasks_per_sec'])} | {fmt_throughput(seq['arq']['tasks_per_sec'])} | **{seq['winner']}** |
| Concurrent (gather) | {fmt_throughput(conc['kew']['tasks_per_sec'])} | N/A | **kew** |
| Batch (`submit_tasks()`) | **{fmt_throughput(batch['kew']['tasks_per_sec'])}** | N/A | **kew {batch['speedup_vs_arq_sequential']:.0f}x** |
| End-to-end throughput | {fmt_throughput(e2e['kew']['tasks_per_sec'])} | N/A* | **kew** |

\\*arq requires separate worker processes; kew runs tasks in-process.

> Numbers from [GitHub Actions](https://github.com/justrach/kew/actions/workflows/benchmark.yml) on `ubuntu-latest` ({ts}).

### Version progression

| Version | Throughput | vs v0.1.4 |
|---------|-----------|-----------|
| v0.1.4 | ~850/sec | 1x |
| v0.1.8 | ~1,550/sec | 1.8x |
| v0.2.0 | ~2,990/sec | 3.5x |
| v{kew_v} (sequential) | {fmt_throughput(seq['kew']['tasks_per_sec'])} | {seq_ratio:.1f}x |
| v{kew_v} (concurrent) | {fmt_throughput(conc['kew']['tasks_per_sec'])} | {conc_ratio:.1f}x |
| **v{kew_v} (batch)** | **{fmt_throughput(batch['kew']['tasks_per_sec'])}** | **{batch_ratio:.1f}x** |

### Key optimizations
- **v0.2.1**: Lock-free submit (Lua atomicity), batch Lua script for N tasks in 1 RTT
- **v0.2.0**: Atomic Lua script, binary Redis, per-queue locks, semaphore reorder, active task SET
- **v0.1.8**: Redis pipelining & batching

"""


def update_readme(readme_path: str, json_path: str) -> bool:
    """Patch the README. Returns True if content changed."""
    readme = Path(readme_path)
    content = readme.read_text()

    with open(json_path) as f:
        data = json.load(f)

    new_section = generate_performance_section(data)

    # Try marker-based replacement first
    pattern = r"(<!-- BENCHMARK_START -->\n).*?(<!-- BENCHMARK_END -->)"
    replacement = r"\1" + new_section.replace("\\", "\\\\") + r"\2"
    new_content, count = re.subn(pattern, replacement, content, flags=re.DOTALL)

    if count == 0:
        # Fallback: find by headings and add markers
        pattern2 = r"## Performance\n.*?(?=## Version History)"
        match = re.search(pattern2, content, flags=re.DOTALL)
        if not match:
            print("ERROR: Could not find performance section in README", file=sys.stderr)
            return False
        replacement2 = "<!-- BENCHMARK_START -->\n" + new_section + "<!-- BENCHMARK_END -->\n"
        new_content = content[:match.start()] + replacement2 + content[match.start() + len(match.group()):]

    if new_content == content:
        print("README is already up to date.")
        return False

    readme.write_text(new_content)
    print(f"README updated with benchmark data from {data['timestamp'][:10]}")
    return True


if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else "benchmark_results.json"
    readme_path = sys.argv[2] if len(sys.argv) > 2 else "README.md"
    changed = update_readme(readme_path, json_path)
    sys.exit(0 if not changed else 0)
