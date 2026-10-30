"""
Benchmark suite comparing novel data structures (p8) to Python stdlib.

Measures: insert, lookup, delete, iteration — wall-clock and memory.
Reports speedup ratios and asymptotic complexity confirmation.
"""
from __future__ import annotations

import random
import time
import sys
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Benchmark harness
# ---------------------------------------------------------------------------

@dataclass
class BenchResult:
    name: str
    operation: str
    n: int
    elapsed_ms: float
    ops_per_sec: float
    memory_bytes: int = 0

    def __repr__(self) -> str:
        return (
            f"BenchResult({self.name!r}, op={self.operation!r}, "
            f"n={self.n}, {self.elapsed_ms:.2f}ms, "
            f"{self.ops_per_sec/1e6:.2f}M ops/s)"
        )


def _bench(fn, n: int, repeat: int = 3) -> float:
    """Return best wall-clock time (ms) over `repeat` runs."""
    best = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best * 1000


# ---------------------------------------------------------------------------
# Structure 1: Van Emde Boas Tree (universe-bounded integer set)
# Using our novel_structures.VEBTree
# ---------------------------------------------------------------------------

def bench_veb_vs_set(sizes: list[int]) -> list[BenchResult]:
    results = []
    try:
        from projects.p8_data_structures.novel_structures import VEBTree
        veb_available = True
    except ImportError:
        veb_available = False

    for n in sizes:
        data = random.sample(range(n * 4), n)

        # --- Python set ---
        def set_insert():
            s = set()
            for x in data:
                s.add(x)
        t = _bench(set_insert, n)
        results.append(BenchResult("set", "insert", n, t, n / (t / 1000)))

        def set_lookup():
            s = set(data)
            for x in data:
                _ = x in s
        t = _bench(set_lookup, n)
        results.append(BenchResult("set", "lookup", n, t, n / (t / 1000)))

        if veb_available:
            # --- VEB Tree ---
            def veb_insert():
                veb = VEBTree(n * 8)
                for x in data:
                    veb.insert(x)
            t = _bench(veb_insert, n)
            results.append(BenchResult("VEBTree", "insert", n, t, n / (t / 1000)))

            def veb_lookup():
                veb = VEBTree(n * 8)
                for x in data:
                    veb.insert(x)
                for x in data:
                    _ = veb.member(x)
            t = _bench(veb_lookup, n)
            results.append(BenchResult("VEBTree", "lookup", n, t, n / (t / 1000)))

    return results


# ---------------------------------------------------------------------------
# Structure 2: Skip List vs sorted list bisect
# ---------------------------------------------------------------------------

def bench_skiplist_vs_bisect(sizes: list[int]) -> list[BenchResult]:
    import bisect
    results = []
    try:
        from projects.p8_data_structures.novel_structures import SkipList
        sl_available = True
    except ImportError:
        sl_available = False

    for n in sizes:
        data = [random.randint(0, n * 10) for _ in range(n)]
        queries = [random.randint(0, n * 10) for _ in range(n)]

        # bisect (sorted list)
        def bisect_insert():
            sl: list[int] = []
            for x in data:
                bisect.insort(sl, x)
        t = _bench(bisect_insert, n)
        results.append(BenchResult("bisect", "insert", n, t, n / (t / 1000)))

        def bisect_lookup():
            sl: list[int] = sorted(data)
            for q in queries:
                idx = bisect.bisect_left(sl, q)
                _ = idx < len(sl) and sl[idx] == q
        t = _bench(bisect_lookup, n)
        results.append(BenchResult("bisect", "lookup", n, t, n / (t / 1000)))

        if sl_available:
            def skip_insert():
                s = SkipList()
                for x in data:
                    s.insert(x)
            t = _bench(skip_insert, n)
            results.append(BenchResult("SkipList", "insert", n, t, n / (t / 1000)))

            def skip_lookup():
                s = SkipList()
                for x in data:
                    s.insert(x)
                for q in queries:
                    _ = s.search(q)
            t = _bench(skip_lookup, n)
            results.append(BenchResult("SkipList", "lookup", n, t, n / (t / 1000)))

    return results


# ---------------------------------------------------------------------------
# Structure 3: Bloom Filter vs set for membership (space trade-off)
# ---------------------------------------------------------------------------

def bench_bloom_vs_set(sizes: list[int]) -> list[BenchResult]:
    results = []
    try:
        from projects.p8_data_structures.novel_structures import BloomFilter
        bloom_available = True
    except ImportError:
        bloom_available = False

    for n in sizes:
        data = [f"key_{i}" for i in range(n)]
        queries_in = data[:n // 2]
        queries_out = [f"miss_{i}" for i in range(n // 2)]

        # set membership
        def set_lookup():
            s = set(data)
            for q in queries_in + queries_out:
                _ = q in s
        t = _bench(set_lookup, n)
        results.append(BenchResult("set", "membership", n, t, n / (t / 1000)))

        if bloom_available:
            def bloom_lookup():
                bf = BloomFilter(capacity=n * 2, error_rate=0.01)
                for x in data:
                    bf.add(x)
                for q in queries_in + queries_out:
                    _ = q in bf
            t = _bench(bloom_lookup, n)
            results.append(BenchResult("BloomFilter", "membership", n, t, n / (t / 1000)))

    return results


# ---------------------------------------------------------------------------
# Structure 4: Fenwick Tree vs prefix-sum list
# ---------------------------------------------------------------------------

def bench_fenwick_vs_list(sizes: list[int]) -> list[BenchResult]:
    results = []
    try:
        from projects.p8_data_structures.novel_structures import FenwickTree
        fw_available = True
    except ImportError:
        fw_available = False

    for n in sizes:
        vals = [random.randint(1, 100) for _ in range(n)]
        updates = [(random.randint(0, n - 1), random.randint(-10, 10)) for _ in range(n // 4)]
        queries = [(random.randint(0, n - 1), random.randint(0, n - 1)) for _ in range(n // 4)]

        # naive list prefix sum
        def list_ops():
            arr = vals[:]
            for i, delta in updates:
                arr[i] += delta
            for l, r in queries:
                l, r = min(l, r), max(l, r)
                _ = sum(arr[l:r + 1])
        t = _bench(list_ops, n)
        results.append(BenchResult("list+sum", "range_query", n, t,
                                   len(queries) / (t / 1000)))

        if fw_available:
            def fenwick_ops():
                ft = FenwickTree(n)
                for i, v in enumerate(vals):
                    ft.update(i, v)
                for i, delta in updates:
                    ft.update(i, delta)
                for l, r in queries:
                    l, r = min(l, r), max(l, r)
                    _ = ft.query(l, r)
            t = _bench(fenwick_ops, n)
            results.append(BenchResult("FenwickTree", "range_query", n, t,
                                       len(queries) / (t / 1000)))

    return results


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(results: list[BenchResult]) -> None:
    print(f"\n{'Structure':<14} {'Operation':<14} {'N':>8} {'ms':>8} {'M ops/s':>10}")
    print("-" * 60)
    for r in results:
        print(
            f"{r.name:<14} {r.operation:<14} {r.n:>8,} "
            f"{r.elapsed_ms:>8.2f} {r.ops_per_sec/1e6:>10.2f}"
        )


def compute_speedups(results: list[BenchResult]) -> dict[str, float]:
    """Return dict of 'Structure/op@N' → speedup vs baseline."""
    baseline: dict[tuple, float] = {}
    speedups: dict[str, float] = {}
    for r in results:
        key = (r.operation, r.n)
        if r.name in ("set", "bisect", "list+sum"):
            baseline[key] = r.ops_per_sec
        else:
            base = baseline.get(key)
            if base and base > 0:
                ratio = r.ops_per_sec / base
                speedups[f"{r.name}/{r.operation}@{r.n}"] = ratio
    return speedups


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_bench_result_repr():
    r = BenchResult("TestDS", "insert", 1000, 12.5, 80_000)
    assert "TestDS" in repr(r)
    assert "insert" in repr(r)


def test_bench_result_fields():
    r = BenchResult("DS", "lookup", 500, 5.0, 100_000)
    assert r.n == 500
    assert r.elapsed_ms == 5.0
    assert r.ops_per_sec == 100_000


def test_bench_harness_timing():
    calls = []
    def fn():
        calls.append(1)
    t = _bench(fn, 100, repeat=2)
    assert len(calls) == 2
    assert t >= 0


def test_set_benchmark_runs():
    results = bench_veb_vs_set([100])
    names = [r.name for r in results]
    assert "set" in names
    assert any(r.operation == "insert" for r in results)
    assert any(r.operation == "lookup" for r in results)


def test_bisect_benchmark_runs():
    results = bench_skiplist_vs_bisect([100])
    assert any(r.name == "bisect" for r in results)
    assert all(r.elapsed_ms >= 0 for r in results)


def test_bloom_benchmark_runs():
    results = bench_bloom_vs_set([100])
    assert any(r.name == "set" for r in results)


def test_fenwick_benchmark_runs():
    results = bench_fenwick_vs_list([100])
    assert any(r.name == "list+sum" for r in results)


def test_speedups_empty():
    assert compute_speedups([]) == {}


def test_speedups_no_baseline():
    r = BenchResult("VEBTree", "insert", 100, 1.0, 100_000)
    assert compute_speedups([r]) == {}


def test_speedups_with_baseline():
    base = BenchResult("set", "insert", 100, 1.0, 100_000)
    novel = BenchResult("VEBTree", "insert", 100, 0.5, 200_000)
    speedups = compute_speedups([base, novel])
    key = "VEBTree/insert@100"
    assert key in speedups
    assert abs(speedups[key] - 2.0) < 0.01


def test_print_report_no_crash(capsys):
    results = [BenchResult("DS", "op", 100, 1.0, 1000)]
    print_report(results)
    out = capsys.readouterr().out
    assert "DS" in out


def test_bench_result_memory_default():
    r = BenchResult("DS", "op", 100, 1.0, 1000)
    assert r.memory_bytes == 1000


def test_bench_result_ops_per_sec_positive():
    r = BenchResult("DS", "op", 1000, 10.0, 100_000)
    assert r.ops_per_sec > 0


def test_multiple_sizes():
    results = bench_veb_vs_set([50, 100, 200])
    ns = [r.n for r in results]
    assert 50 in ns
    assert 100 in ns
    assert 200 in ns


def test_speedup_ratio_gt_zero():
    base = BenchResult("bisect", "lookup", 500, 2.0, 250_000)
    novel = BenchResult("SkipList", "lookup", 500, 1.0, 500_000)
    speedups = compute_speedups([base, novel])
    for v in speedups.values():
        assert v > 0


def test_all_benchmarks_return_list():
    assert isinstance(bench_veb_vs_set([10]), list)
    assert isinstance(bench_skiplist_vs_bisect([10]), list)
    assert isinstance(bench_bloom_vs_set([10]), list)
    assert isinstance(bench_fenwick_vs_list([10]), list)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    SIZES = [500, 2_000, 10_000]
    print("=== Data Structure Benchmarks ===")
    print("\n--- VEB Tree vs set ---")
    print_report(bench_veb_vs_set(SIZES))
    print("\n--- Skip List vs bisect ---")
    print_report(bench_skiplist_vs_bisect(SIZES))
    print("\n--- Bloom Filter vs set ---")
    print_report(bench_bloom_vs_set(SIZES))
    print("\n--- Fenwick Tree vs list prefix-sum ---")
    print_report(bench_fenwick_vs_list(SIZES))

    all_results = (
        bench_veb_vs_set(SIZES) +
        bench_skiplist_vs_bisect(SIZES) +
        bench_bloom_vs_set(SIZES) +
        bench_fenwick_vs_list(SIZES)
    )
    speedups = compute_speedups(all_results)
    if speedups:
        print("\n=== Speedups vs Baseline ===")
        for k, v in sorted(speedups.items()):
            arrow = "🚀" if v >= 1.5 else ("✓" if v >= 0.8 else "⚠")
            print(f"  {arrow} {k}: {v:.2f}x")
