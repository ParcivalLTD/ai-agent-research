"""
Novel data structures for specific workload traces — P8.

Three structures, each designed for a workload standard hash maps / B-trees fail at:
1. ZipfianAdaptiveDict  — 85% lookups, Zipfian(α=1.2) keys, 10M unique keys
2. AppendRangeTree      — 70% appends, 20% range queries by time window
3. CompactAdjacencyGraph — 40% edge insert, 30% neighbor query, 10% path existence
"""
from __future__ import annotations
import array
from collections import defaultdict, OrderedDict
from dataclasses import dataclass, field
from typing import Any, Iterator
import bisect


# ---------------------------------------------------------------------------
# 1. ZipfianAdaptiveDict
# ---------------------------------------------------------------------------

class ZipfianAdaptiveDict:
    """
    Two-tier dictionary optimised for Zipfian access patterns.

    Hot tier : list of [key, value, frequency] — at most K entries.
               Scanned linearly; sits entirely in cache for small K.
    Cold tier: plain dict for all other entries.

    Invariant: every hot key has frequency >= every cold key's frequency.
    """

    HOT_CAPACITY: int = 64
    PROMOTE_THRESHOLD: int = 2   # cold frequency must exceed this to trigger promotion

    def __init__(self, hot_capacity: int = 64, promote_threshold: int = 2) -> None:
        self.K = hot_capacity
        self.threshold = promote_threshold
        # Each entry: [key, value, frequency]
        self._hot: list[list] = []
        self._cold: dict[Any, list] = {}          # key → [value, frequency]

    # ------------------------------------------------------------------ public API

    def get(self, key: Any) -> Any | None:
        """O(K) hot scan then O(1) cold lookup."""
        for entry in self._hot:
            if entry[0] == key:
                entry[2] += 1
                return entry[1]
        if key in self._cold:
            self._cold[key][1] += 1
            freq = self._cold[key][1]
            if freq > self.threshold:
                self.promote(key)
            return self._cold[key][1] and self._cold.get(key, [None])[0]
        return None

    def _cold_get_value(self, key: Any) -> Any | None:
        """Return value from cold tier without side-effects (internal helper)."""
        entry = self._cold.get(key)
        return entry[0] if entry else None

    def get(self, key: Any) -> Any | None:  # noqa: F811  (redefine intentionally)
        """O(K) hot scan then O(1) cold lookup."""
        for entry in self._hot:
            if entry[0] == key:
                entry[2] += 1
                return entry[1]
        if key in self._cold:
            cold_entry = self._cold[key]
            cold_entry[1] += 1
            if cold_entry[1] > self.threshold:
                self.promote(key)
                # After promotion the entry is in hot; return from there
                for entry in self._hot:
                    if entry[0] == key:
                        return entry[1]
            return cold_entry[0]
        return None

    def set(self, key: Any, value: Any) -> None:
        """Insert or update; promotes cold entry if frequency > threshold."""
        # Check hot first
        for entry in self._hot:
            if entry[0] == key:
                entry[1] = value
                return
        # Check cold
        if key in self._cold:
            self._cold[key][0] = value
            if self._cold[key][1] > self.threshold:
                self.promote(key)
            return
        # New key — start in cold with frequency 0
        self._cold[key] = [value, 0]

    def promote(self, key: Any) -> None:
        """Move key from cold to hot, demoting the lowest-frequency hot entry if full."""
        if key not in self._cold:
            return
        value, freq = self._cold.pop(key)
        if len(self._hot) < self.K:
            self._hot.append([key, value, freq])
        else:
            # Find lowest-frequency hot entry
            min_idx = min(range(len(self._hot)), key=lambda i: self._hot[i][2])
            demoted = self._hot[min_idx]
            # Only promote if incoming freq is higher than the min hot freq
            if freq >= demoted[2]:
                self._cold[demoted[0]] = [demoted[1], demoted[2]]
                self._hot[min_idx] = [key, value, freq]
            else:
                # Put it back in cold — it doesn't deserve hot
                self._cold[key] = [value, freq]

    def range_scan(self, min_freq: int) -> list[tuple[Any, Any]]:
        """Return all (key, value) pairs from hot tier with frequency >= min_freq."""
        return [(e[0], e[1]) for e in self._hot if e[2] >= min_freq]

    def __contains__(self, key: Any) -> bool:
        for entry in self._hot:
            if entry[0] == key:
                return True
        return key in self._cold

    def hot_keys(self) -> list[Any]:
        return [e[0] for e in self._hot]

    def cold_size(self) -> int:
        return len(self._cold)

    def hot_size(self) -> int:
        return len(self._hot)

    def _check_invariant(self) -> bool:
        """Verify hot/cold frequency invariant (for testing)."""
        if not self._hot:
            return True
        min_hot_freq = min(e[2] for e in self._hot)
        for cold_entry in self._cold.values():
            if cold_entry[1] > min_hot_freq:
                return False
        return True


# ---------------------------------------------------------------------------
# 2. AppendRangeTree
# ---------------------------------------------------------------------------

class AppendRangeTree:
    """
    Epoch-based structure optimised for heavy-append, medium-range-query workloads.

    Appends are O(1) amortised (buffered in `active`).
    Range queries are O(log E + R) via bisect over epoch start timestamps.
    """

    EPOCH_SIZE: int = 100

    def __init__(self, epoch_size: int = 100) -> None:
        self.EPOCH_SIZE = epoch_size
        # Each epoch: sorted list of (timestamp, value)
        self.epochs: list[list[tuple[float, Any]]] = []
        # epoch_starts[i] = minimum timestamp in epochs[i]
        self._epoch_starts: list[float] = []
        self._epoch_ends: list[float] = []
        # Unsorted write buffer
        self.active: list[tuple[float, Any]] = []

    # ------------------------------------------------------------------ public API

    def append(self, timestamp: float, value: Any) -> None:
        """O(1) amortised append."""
        self.active.append((timestamp, value))
        if len(self.active) >= self.EPOCH_SIZE:
            self._flush()

    def range_query(self, t_start: float, t_end: float) -> list[Any]:
        """
        O(log E + R) range query across all sealed epochs + active buffer.
        Returns values with t_start <= timestamp <= t_end.
        """
        results: list[Any] = []

        # Binary search for first epoch whose END is >= t_start
        lo = bisect.bisect_left(self._epoch_ends, t_start)
        for i in range(lo, len(self.epochs)):
            epoch = self.epochs[i]
            if self._epoch_starts[i] > t_end:
                break
            # Within this epoch, binary search for the window
            left = bisect.bisect_left(epoch, (t_start,))
            right = bisect.bisect_right(epoch, (t_end, float('inf')))
            for ts, val in epoch[left:right]:
                if t_start <= ts <= t_end:
                    results.append(val)

        # Scan active buffer (unsorted, small)
        for ts, val in self.active:
            if t_start <= ts <= t_end:
                results.append(val)

        return results

    def evict_old(self, cutoff_timestamp: float) -> int:
        """Remove sealed epochs whose latest timestamp < cutoff. Returns #evicted."""
        evicted = 0
        while self._epoch_ends and self._epoch_ends[0] < cutoff_timestamp:
            self.epochs.pop(0)
            self._epoch_starts.pop(0)
            self._epoch_ends.pop(0)
            evicted += 1
        return evicted

    def _flush(self) -> None:
        """Sort active buffer and seal it as a new epoch."""
        if not self.active:
            return
        sorted_epoch = sorted(self.active)
        self.epochs.append(sorted_epoch)
        self._epoch_starts.append(sorted_epoch[0][0])
        self._epoch_ends.append(sorted_epoch[-1][0])
        self.active = []

    def total_entries(self) -> int:
        return sum(len(e) for e in self.epochs) + len(self.active)

    def flush(self) -> None:
        """Public flush — force active buffer into epochs."""
        self._flush()


# ---------------------------------------------------------------------------
# 3. CompactAdjacencyGraph
# ---------------------------------------------------------------------------

BLOCK_CAPACITY = 7   # edges per block (fits in one cache line with pointer overhead)


class CompactAdjacencyGraph:
    """
    Adjacency representation using fixed-size edge blocks (7 edges each).
    Union-find for O(α(n)) path existence queries.
    """

    def __init__(self) -> None:
        # blocks[i] = list of up to BLOCK_CAPACITY destination node ids
        self.blocks: list[list[int]] = []
        # node → list of block indices belonging to that node
        self.node_to_block: dict[int, list[int]] = {}
        # Union-find
        self.parent: dict[int, int] = {}
        self.rank: dict[int, int] = {}

    # ------------------------------------------------------------------ public API

    def add_edge(self, u: int, v: int) -> None:
        """Add directed edge u→v. O(1) expected."""
        self._ensure_node(u)
        self._ensure_node(v)

        block_list = self.node_to_block[u]
        if block_list:
            last_block = self.blocks[block_list[-1]]
            if len(last_block) < BLOCK_CAPACITY:
                last_block.append(v)
                self._union(u, v)
                return
        # Need a new block
        new_block_idx = len(self.blocks)
        self.blocks.append([v])
        block_list.append(new_block_idx)
        self._union(u, v)

    def neighbors(self, node: int) -> list[int]:
        """Return all neighbors of node. O(deg/7) cache lines."""
        if node not in self.node_to_block:
            return []
        result: list[int] = []
        for blk_idx in self.node_to_block[node]:
            result.extend(self.blocks[blk_idx])
        return result

    def path_exists(self, u: int, v: int) -> bool:
        """O(α(n)) via union-find."""
        if u not in self.parent or v not in self.parent:
            return False
        return self._find(u) == self._find(v)

    def remove_edge(self, u: int, v: int) -> None:
        """Swap-with-tail in block containing v; remove block if empty."""
        if u not in self.node_to_block:
            return
        for blk_list_idx, blk_idx in enumerate(self.node_to_block[u]):
            block = self.blocks[blk_idx]
            for edge_idx, dest in enumerate(block):
                if dest == v:
                    # Swap with tail
                    block[edge_idx] = block[-1]
                    block.pop()
                    if not block:
                        # Remove empty block
                        self.blocks[blk_idx] = []   # mark as empty (don't renumber)
                        self.node_to_block[u].pop(blk_list_idx)
                    return

    def node_count(self) -> int:
        return len(self.parent)

    def edge_count(self) -> int:
        return sum(len(b) for b in self.blocks)

    # ------------------------------------------------------------------ union-find internals

    def _ensure_node(self, x: int) -> None:
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0
            self.node_to_block[x] = []

    def _find(self, x: int) -> int:
        """Path-compressed find."""
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        # Path compression
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def _union(self, x: int, y: int) -> None:
        """Union by rank."""
        rx, ry = self._find(x), self._find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1


# ===========================================================================
# TESTS
# ===========================================================================

def _run_tests() -> None:
    passed = 0
    failed = 0

    def ok(condition: bool, name: str) -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {name}")

    # -------------------------------------------------------------------
    print("=== ZipfianAdaptiveDict ===")
    d = ZipfianAdaptiveDict(hot_capacity=4, promote_threshold=1)

    # Basic set/get
    d.set("a", 1)
    d.set("b", 2)
    ok(d.get("a") == 1,          "get cold key a")
    ok(d.get("b") == 2,          "get cold key b")
    ok(d.get("z") is None,       "get missing key returns None")

    # After enough gets, key should promote
    d.get("a")   # freq becomes 2 > threshold=1 → promotes
    ok("a" in d.hot_keys(),      "a promoted to hot after threshold exceeded")

    # Update existing hot key
    d.set("a", 99)
    ok(d.get("a") == 99,         "update hot key value")

    # Update existing cold key
    d.set("b", 42)
    ok(d.get("b") == 42,         "update cold key value")

    # range_scan
    d2 = ZipfianAdaptiveDict(hot_capacity=4, promote_threshold=0)
    d2.set("x", 10); d2.promote("x")
    d2.set("y", 20); d2.promote("y")
    d2.set("z", 30); d2.promote("z")
    # Bump freq of x and y manually
    d2.get("x"); d2.get("x"); d2.get("y")
    results = d2.range_scan(0)
    ok(len(results) >= 2,        "range_scan(0) returns entries")
    hot_keys = [r[0] for r in results]
    ok("x" in hot_keys or "y" in hot_keys, "range_scan contains x or y")

    # range_scan with high min_freq
    high_results = d2.range_scan(100)
    ok(len(high_results) == 0,   "range_scan with very high freq returns empty")

    # Demote on promote when hot is full
    d3 = ZipfianAdaptiveDict(hot_capacity=2, promote_threshold=0)
    d3.set("p", 1); d3.promote("p")
    d3.set("q", 2); d3.promote("q")
    ok(d3.hot_size() == 2,       "hot tier at capacity")
    d3.set("r", 3); d3.promote("r")  # Should demote lowest-freq
    ok(d3.hot_size() <= 2,       "hot tier stays within capacity after promotion")

    # Invariant check
    d4 = ZipfianAdaptiveDict(hot_capacity=8, promote_threshold=1)
    for i in range(20):
        d4.set(f"key{i}", i)
    for i in range(0, 10, 2):
        d4.get(f"key{i}"); d4.get(f"key{i}")
    ok(d4._check_invariant(),    "hot/cold frequency invariant holds")

    # Contains operator
    d5 = ZipfianAdaptiveDict()
    d5.set("hello", "world")
    ok("hello" in d5,            "__contains__ finds cold key")
    ok("missing" not in d5,      "__contains__ returns False for missing")

    # Cold size
    d6 = ZipfianAdaptiveDict(hot_capacity=2)
    d6.set("a", 1); d6.set("b", 2); d6.set("c", 3)
    ok(d6.cold_size() == 3,      "all keys start cold")

    # Promote from empty cold — should be no-op
    d7 = ZipfianAdaptiveDict()
    d7.promote("nonexistent")    # must not raise
    ok(True,                     "promote nonexistent key is safe")

    # Large-scale Zipfian simulation
    import random
    random.seed(42)
    d8 = ZipfianAdaptiveDict(hot_capacity=16, promote_threshold=3)
    for i in range(200):
        d8.set(i, i * 2)
    # Heavy access on keys 0-9 (simulate Zipfian hot keys)
    for _ in range(50):
        for k in range(10):
            d8.get(k)
    ok(d8.hot_size() > 0,        "Zipfian simulation: some keys promoted")
    ok(d8._check_invariant(),    "Zipfian simulation: invariant holds")

    # -------------------------------------------------------------------
    print("=== AppendRangeTree ===")
    t = AppendRangeTree(epoch_size=5)

    # Basic append and range query (within active buffer)
    t.append(1.0, "a")
    t.append(2.0, "b")
    t.append(3.0, "c")
    results = t.range_query(1.0, 3.0)
    ok(set(results) == {"a", "b", "c"}, "range_query within active buffer")

    # Partial range
    results2 = t.range_query(1.5, 2.5)
    ok("b" in results2,               "partial range hits correct value")
    ok("a" not in results2,           "partial range excludes out-of-range")

    # Flush trigger
    for i in range(5):   # total 8 appends → flushes once at 5
        t.append(float(10 + i), f"ep{i}")
    ok(len(t.epochs) >= 1,            "flush triggered after EPOCH_SIZE appends")

    # Range query spanning epoch boundary
    t2 = AppendRangeTree(epoch_size=3)
    for ts in [1.0, 2.0, 3.0]:
        t2.append(ts, ts)   # flush at 3
    t2.append(4.0, 4.0)
    t2.append(5.0, 5.0)
    results3 = t2.range_query(2.5, 4.5)
    ok(3.0 in results3,               "range spans epoch boundary - epoch val")
    ok(4.0 in results3,               "range spans epoch boundary - active val")
    ok(2.0 not in results3,           "range boundary excludes val 2.0")

    # Total entries
    t3 = AppendRangeTree(epoch_size=10)
    for i in range(25):
        t3.append(float(i), i)
    ok(t3.total_entries() == 25,      "total_entries counts all 25")

    # evict_old
    t4 = AppendRangeTree(epoch_size=3)
    for ts in [1.0, 2.0, 3.0]:
        t4.append(ts, ts)   # sealed epoch
    for ts in [10.0, 11.0, 12.0]:
        t4.append(ts, ts)   # second sealed epoch
    evicted = t4.evict_old(9.0)
    ok(evicted == 1,                  "evict_old removes 1 epoch before cutoff")
    ok(t4.range_query(1.0, 3.0) == [], "evicted epoch no longer in results")
    ok(10.0 in t4.range_query(9.5, 12.5), "later epoch still present after eviction")

    # Empty range query
    t5 = AppendRangeTree()
    ok(t5.range_query(0.0, 100.0) == [], "empty tree range_query returns []")

    # Exact boundary timestamps (inclusive)
    t6 = AppendRangeTree(epoch_size=10)
    t6.append(5.0, "exact")
    ok("exact" in t6.range_query(5.0, 5.0), "exact boundary timestamp included")

    # Out-of-range query
    t7 = AppendRangeTree(epoch_size=10)
    t7.append(50.0, "far")
    ok(t7.range_query(0.0, 10.0) == [],  "out-of-range query returns []")

    # Manual flush
    t8 = AppendRangeTree(epoch_size=100)
    t8.append(1.0, "x")
    t8.flush()
    ok(len(t8.epochs) == 1,           "manual flush creates epoch")
    ok(len(t8.active) == 0,           "manual flush clears active buffer")

    # Out-of-order appends
    t9 = AppendRangeTree(epoch_size=5)
    for ts in [5.0, 3.0, 1.0, 4.0, 2.0]:
        t9.append(ts, ts)   # triggers flush
    results9 = t9.range_query(2.0, 4.0)
    ok(set(results9) == {2.0, 3.0, 4.0}, "out-of-order appends sorted in epoch")

    # -------------------------------------------------------------------
    print("=== CompactAdjacencyGraph ===")
    g = CompactAdjacencyGraph()

    # Add edges
    g.add_edge(0, 1)
    g.add_edge(0, 2)
    g.add_edge(0, 3)
    ok(set(g.neighbors(0)) == {1, 2, 3}, "neighbors after 3 edges")

    # Path existence via union-find
    ok(g.path_exists(0, 1),      "path_exists: connected nodes")
    ok(g.path_exists(0, 2),      "path_exists: connected via union")
    ok(not g.path_exists(0, 99), "path_exists: disconnected returns False")

    # Fill a block and overflow to second block
    g2 = CompactAdjacencyGraph()
    for dest in range(8):   # 7 in first block, 1 in second
        g2.add_edge(0, dest)
    ok(len(g2.node_to_block[0]) == 2, "overflow creates second block")
    ok(set(g2.neighbors(0)) == set(range(8)), "all 8 neighbors present")

    # remove_edge — normal case
    g3 = CompactAdjacencyGraph()
    g3.add_edge(0, 1)
    g3.add_edge(0, 2)
    g3.add_edge(0, 3)
    g3.remove_edge(0, 2)
    ok(2 not in g3.neighbors(0), "remove_edge removes correct edge")
    ok(1 in g3.neighbors(0),     "remove_edge leaves other edges intact")

    # remove_edge — last edge in block (block becomes empty)
    g4 = CompactAdjacencyGraph()
    g4.add_edge(0, 42)
    g4.remove_edge(0, 42)
    ok(g4.neighbors(0) == [],    "remove last edge: empty neighbor list")
    ok(len(g4.node_to_block[0]) == 0, "remove last edge: block list empty")

    # remove nonexistent edge — must not raise
    g5 = CompactAdjacencyGraph()
    g5.add_edge(1, 2)
    g5.remove_edge(1, 99)        # silent no-op
    ok(g5.neighbors(1) == [2],   "remove nonexistent edge: no side-effect")

    # path_exists on empty graph
    g6 = CompactAdjacencyGraph()
    ok(not g6.path_exists(0, 1), "path_exists on empty graph returns False")

    # Isolated nodes after add_edge
    g7 = CompactAdjacencyGraph()
    g7.add_edge(10, 20)
    g7.add_edge(30, 40)
    ok(not g7.path_exists(10, 30), "disconnected components: path_exists False")
    ok(g7.path_exists(10, 20),     "same component: path_exists True")

    # node_count and edge_count
    g8 = CompactAdjacencyGraph()
    g8.add_edge(0, 1)
    g8.add_edge(1, 2)
    ok(g8.node_count() == 3,     "node_count after 3 unique nodes")
    ok(g8.edge_count() == 2,     "edge_count after 2 edges")

    # Path compression correctness (long chain)
    g9 = CompactAdjacencyGraph()
    for i in range(20):
        g9.add_edge(i, i + 1)
    ok(g9.path_exists(0, 20),    "long chain: path_exists True for 0→20")
    ok(not g9.path_exists(0, 99), "long chain: path_exists False for 0→99")

    # Large graph stress test
    g10 = CompactAdjacencyGraph()
    for i in range(100):
        g10.add_edge(i, i + 1)
        g10.add_edge(i, i + 2)
    ok(g10.node_count() > 100,   "stress: 100+ nodes")
    ok(g10.path_exists(0, 50),   "stress: long path via union-find")

    # -------------------------------------------------------------------
    total = passed + failed
    print(f"\nResults: {passed}/{total} tests passed", end="")
    if failed:
        print(f"  ({failed} FAILED)")
        raise SystemExit(1)
    else:
        print(" ✓")


if __name__ == "__main__":
    _run_tests()
