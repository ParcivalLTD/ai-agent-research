"""10 more synthesized algorithms with correctness proofs and full test suites."""
from __future__ import annotations
from collections import deque, defaultdict
from typing import Optional
import sys


# ===========================================================================
# 1. valid_parentheses
# ===========================================================================

def valid_parentheses(s: str) -> bool:
    """Return True iff every bracket in s is correctly matched and nested.

    Loop invariant: at every character, `stack` contains the sequence of
    open brackets that are awaiting a matching close bracket, in order.
    Proof of correctness:
      - Any open bracket is pushed; its pair must be seen before the scope ends.
      - Any close bracket checks the top: mismatch → False immediately.
      - End of string: stack must be empty (all opens were closed).
    """
    stack: list[str] = []
    match = {')': '(', '}': '{', ']': '['}
    for ch in s:
        if ch in '([{':
            stack.append(ch)
        elif ch in ')]}':
            if not stack or stack[-1] != match[ch]:
                return False
            stack.pop()
    return len(stack) == 0


def _test_valid_parentheses():
    cases = [
        ("", True, "empty"),
        ("()", True, "single pair"),
        ("()[]{}", True, "multiple pairs"),
        ("(]", False, "mismatched"),
        ("([)]", False, "interleaved"),
        ("{[]}", True, "nested"),
        ("(((", False, "unclosed open"),
        (")))", False, "unclosed close"),
        ("((()))", True, "deep nesting"),
        ("{[()]}", True, "mixed nested"),
    ]
    for s, expected, desc in cases:
        result = valid_parentheses(s)
        assert result == expected, f"valid_parentheses({s!r}): expected {expected}, got {result} [{desc}]"
    print(f"  valid_parentheses: {len(cases)}/{ len(cases)} passed")


# ===========================================================================
# 2. two_sum
# ===========================================================================

def two_sum(nums: list[int], target: int) -> list[int]:
    """Return indices [i, j] where nums[i] + nums[j] == target, i < j.

    Hash map invariant: seen[v] = first index where value v was encountered.
    For each position i, complement = target - nums[i].
    If complement already in seen, we have our answer: [seen[complement], i].
    Time: O(n).  Space: O(n).
    """
    seen: dict[int, int] = {}
    for i, num in enumerate(nums):
        complement = target - num
        if complement in seen:
            return [seen[complement], i]
        seen[num] = i
    return []


def _test_two_sum():
    cases = [
        ([2, 7, 11, 15], 9, [0, 1], "basic"),
        ([3, 2, 4], 6, [1, 2], "non-zero start"),
        ([3, 3], 6, [0, 1], "duplicates"),
        ([1, 2, 3, 4], 7, [2, 3], "last two"),
        ([0, 4, 3, 0], 0, [0, 3], "zeros"),
        ([-1, -2, -3, -4, -5], -8, [2, 4], "negatives"),
        ([1, 5, 3, 2], 4, [0, 2], "non-sorted"),
    ]
    for nums, target, expected, desc in cases:
        result = two_sum(nums, target)
        assert result == expected, f"two_sum({nums}, {target}): expected {expected}, got {result} [{desc}]"
    print(f"  two_sum: {len(cases)}/{len(cases)} passed")


# ===========================================================================
# 3. max_subarray  (Kadane's algorithm)
# ===========================================================================

def max_subarray(nums: list[int]) -> int:
    """Return the maximum sum of any contiguous subarray.

    Kadane invariant:
      best_here = maximum subarray sum ending exactly at index i.
      best_so_far = maximum subarray sum seen up to index i.
    Recurrence: best_here = max(nums[i], best_here + nums[i])
    Proof: if best_here < 0 before adding nums[i], starting fresh at nums[i]
    is always at least as good.
    Time: O(n).  Space: O(1).
    """
    if not nums:
        raise ValueError("Input must be non-empty")
    best_here = best_so_far = nums[0]
    for num in nums[1:]:
        best_here = max(num, best_here + num)
        best_so_far = max(best_so_far, best_here)
    return best_so_far


def _test_max_subarray():
    cases = [
        ([-2, 1, -3, 4, -1, 2, 1, -5, 4], 6, "classic"),
        ([1], 1, "single positive"),
        ([-1], -1, "single negative"),
        ([1, 2, 3, 4], 10, "all positive"),
        ([-1, -2, -3], -1, "all negative"),
        ([0, 0, 0], 0, "all zeros"),
        ([5, -3, 5], 7, "two peaks"),
        ([-2, -3, 4, -1, -2, 1, 5, -3], 7, "mixed"),
    ]
    for nums, expected, desc in cases:
        result = max_subarray(nums)
        assert result == expected, f"max_subarray({nums}): expected {expected}, got {result} [{desc}]"
    print(f"  max_subarray: {len(cases)}/{len(cases)} passed")


# ===========================================================================
# 4. num_islands  (BFS connected-components)
# ===========================================================================

def num_islands(grid: list[list[str]]) -> int:
    """Return the number of islands (connected '1' cells) in grid.

    BFS invariant: once a cell is enqueued it is marked '0' (visited).
    Every BFS expansion visits all cells reachable from the starting '1'.
    We increment the island counter once per BFS start.
    Time: O(R*C).  Space: O(min(R,C)) for the queue.
    """
    if not grid or not grid[0]:
        return 0
    rows, cols = len(grid), len(grid[0])
    count = 0

    def bfs(r: int, c: int) -> None:
        q: deque = deque([(r, c)])
        grid[r][c] = '0'
        while q:
            row, col = q.popleft()
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = row + dr, col + dc
                if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == '1':
                    grid[nr][nc] = '0'
                    q.append((nr, nc))

    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == '1':
                count += 1
                bfs(r, c)
    return count


def _test_num_islands():
    import copy
    cases = [
        (
            [
                ["1", "1", "1", "1", "0"],
                ["1", "1", "0", "1", "0"],
                ["1", "1", "0", "0", "0"],
                ["0", "0", "0", "0", "0"],
            ],
            1, "one large island"
        ),
        (
            [
                ["1", "1", "0", "0", "0"],
                ["1", "1", "0", "0", "0"],
                ["0", "0", "1", "0", "0"],
                ["0", "0", "0", "1", "1"],
            ],
            3, "three islands"
        ),
        ([["0", "0", "0"], ["0", "0", "0"]], 0, "all water"),
        ([["1"]], 1, "single land cell"),
        ([["0"]], 0, "single water cell"),
        (
            [["1", "0", "1"], ["0", "1", "0"], ["1", "0", "1"]],
            5, "diagonal — each separate"
        ),
    ]
    for grid, expected, desc in cases:
        result = num_islands(copy.deepcopy(grid))
        assert result == expected, f"num_islands: expected {expected}, got {result} [{desc}]"
    print(f"  num_islands: {len(cases)}/{len(cases)} passed")


# ===========================================================================
# 5. coin_change  (DP)
# ===========================================================================

def coin_change(coins: list[int], amount: int) -> int:
    """Return fewest coins summing to amount, or -1 if impossible.

    DP invariant: dp[i] = minimum number of coins needed to make amount i.
    dp[0] = 0 (base case — zero coins for zero amount).
    dp[i] = min(dp[i - c] + 1) for all c in coins where c <= i.
    If dp[amount] is still ∞, no combination exists → return -1.
    Time: O(amount * |coins|).  Space: O(amount).
    """
    INF = float('inf')
    dp = [INF] * (amount + 1)
    dp[0] = 0
    for i in range(1, amount + 1):
        for c in coins:
            if c <= i and dp[i - c] + 1 < dp[i]:
                dp[i] = dp[i - c] + 1
    return int(dp[amount]) if dp[amount] != INF else -1


def _test_coin_change():
    cases = [
        ([1, 5, 11], 11, 1, "exact single coin"),
        ([1, 2, 5], 11, 3, "classic"),
        ([2], 3, -1, "impossible"),
        ([1], 0, 0, "amount zero"),
        ([1], 1, 1, "single coin"),
        ([1, 2, 5], 0, 0, "zero amount any coins"),
        ([2, 5, 10, 1], 27, 4, "greedy fails — need DP"),
        ([186, 419, 83, 408], 6249, 20, "large sparse coins"),
    ]
    for coins, amount, expected, desc in cases:
        result = coin_change(coins, amount)
        assert result == expected, f"coin_change({coins}, {amount}): expected {expected}, got {result} [{desc}]"
    print(f"  coin_change: {len(cases)}/{len(cases)} passed")


# ===========================================================================
# 6. word_break  (DP)
# ===========================================================================

def word_break(s: str, word_dict: list[str]) -> bool:
    """Return True iff s can be segmented into words from word_dict.

    DP invariant: dp[i] = True iff s[:i] can be segmented using word_dict.
    dp[0] = True (empty prefix).
    dp[i] = True if ∃ j < i such that dp[j] and s[j:i] in word_set.
    Time: O(n^2 * max_word_len).  Space: O(n).
    """
    word_set = set(word_dict)
    n = len(s)
    dp = [False] * (n + 1)
    dp[0] = True
    for i in range(1, n + 1):
        for j in range(i):
            if dp[j] and s[j:i] in word_set:
                dp[i] = True
                break
    return dp[n]


def _test_word_break():
    cases = [
        ("leetcode", ["leet", "code"], True, "classic"),
        ("applepenapple", ["apple", "pen"], True, "reuse allowed"),
        ("catsandog", ["cats", "dog", "sand", "and", "cat"], False, "impossible"),
        ("", ["a", "b"], True, "empty string"),
        ("a", ["a"], True, "single char match"),
        ("ab", ["a", "b"], True, "two single chars"),
        ("goalspecific", ["goal", "spec", "ific"], True, "three parts"),
        ("aaaaaaa", ["aaaa", "aaa"], True, "overlapping lengths"),
    ]
    for s, wd, expected, desc in cases:
        result = word_break(s, wd)
        assert result == expected, f"word_break({s!r}, {wd}): expected {expected}, got {result} [{desc}]"
    print(f"  word_break: {len(cases)}/{len(cases)} passed")


# ===========================================================================
# 7. merge_intervals
# ===========================================================================

def merge_intervals(intervals: list[list[int]]) -> list[list[int]]:
    """Merge all overlapping intervals and return the sorted non-overlapping result.

    Invariant: after sorting by start, result is accumulated left to right.
    For each interval [s, e]: if it overlaps the last result interval
    (last_end >= s), merge by extending last_end = max(last_end, e).
    Otherwise, append as a new non-overlapping interval.
    Time: O(n log n).  Space: O(n).
    """
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda x: x[0])
    merged = [intervals[0][:]]
    for s, e in intervals[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return merged


def _test_merge_intervals():
    cases = [
        ([[1, 3], [2, 6], [8, 10], [15, 18]], [[1, 6], [8, 10], [15, 18]], "classic"),
        ([[1, 4], [4, 5]], [[1, 5]], "touching"),
        ([[1, 4], [2, 3]], [[1, 4]], "contained"),
        ([], [], "empty"),
        ([[1, 2]], [[1, 2]], "single"),
        ([[1, 3], [4, 6]], [[1, 3], [4, 6]], "no overlap"),
        ([[1, 10], [2, 3], [4, 5]], [[1, 10]], "fully contained multiple"),
        ([[3, 5], [1, 4]], [[1, 5]], "unsorted input"),
    ]
    for intervals, expected, desc in cases:
        result = merge_intervals([iv[:] for iv in intervals])
        assert result == expected, f"merge_intervals({intervals}): expected {expected}, got {result} [{desc}]"
    print(f"  merge_intervals: {len(cases)}/{len(cases)} passed")


# ===========================================================================
# 8. find_anagrams  (sliding window)
# ===========================================================================

def find_anagrams(s: str, p: str) -> list[int]:
    """Return start indices of all anagrams of p in s.

    Sliding window invariant: maintain frequency diffs between the current
    window of length |p| and p.  'diff_count' tracks how many character
    positions currently differ.  When diff_count == 0, window is an anagram.
    Time: O(|s|).  Space: O(1) — alphabet size is constant.
    """
    if len(p) > len(s):
        return []
    from collections import Counter
    p_count = Counter(p)
    window = Counter(s[:len(p)])
    result: list[int] = []

    def _matches(a: Counter, b: Counter) -> bool:
        return a == b

    if _matches(window, p_count):
        result.append(0)

    for i in range(len(p), len(s)):
        # Add right character
        window[s[i]] += 1
        # Remove left character
        left = s[i - len(p)]
        window[left] -= 1
        if window[left] == 0:
            del window[left]
        if window == p_count:
            result.append(i - len(p) + 1)

    return result


def _test_find_anagrams():
    cases = [
        ("cbaebabacd", "abc", [0, 6], "classic"),
        ("abab", "ab", [0, 1, 2], "overlapping"),
        ("aa", "bb", [], "no match"),
        ("baa", "aa", [1], "end of string"),
        ("a", "a", [0], "single char match"),
        ("a", "b", [], "single char no match"),
        ("abcabc", "abc", [0, 1, 2, 3], "many matches"),
        ("aaaaaaaaaa", "aaaa", [0, 1, 2, 3, 4, 5, 6], "all same char"),
    ]
    for s, p, expected, desc in cases:
        result = find_anagrams(s, p)
        assert result == expected, f"find_anagrams({s!r}, {p!r}): expected {expected}, got {result} [{desc}]"
    print(f"  find_anagrams: {len(cases)}/{len(cases)} passed")


# ===========================================================================
# 9. can_finish  (Kahn's BFS topological sort)
# ===========================================================================

def can_finish(num_courses: int, prerequisites: list[list[int]]) -> bool:
    """Return True iff all courses can be finished (no cycle in prereq graph).

    Kahn's invariant: at each step, nodes with in-degree 0 have no remaining
    prerequisites and can be "taken".  If we process all n nodes, there is no
    cycle.  If we stop with nodes remaining, a cycle exists.
    Time: O(V + E).  Space: O(V + E).
    """
    in_degree = [0] * num_courses
    adj: list[list[int]] = [[] for _ in range(num_courses)]
    for course, prereq in prerequisites:
        adj[prereq].append(course)
        in_degree[course] += 1

    q: deque = deque(c for c in range(num_courses) if in_degree[c] == 0)
    processed = 0
    while q:
        node = q.popleft()
        processed += 1
        for neighbour in adj[node]:
            in_degree[neighbour] -= 1
            if in_degree[neighbour] == 0:
                q.append(neighbour)
    return processed == num_courses


def _test_can_finish():
    cases = [
        (2, [[1, 0]], True, "linear chain"),
        (2, [[1, 0], [0, 1]], False, "direct cycle"),
        (3, [[1, 0], [2, 1]], True, "chain of 3"),
        (3, [[0, 1], [1, 2], [2, 0]], False, "triangle cycle"),
        (1, [], True, "single course no prereqs"),
        (4, [[1, 0], [2, 0], [3, 1], [3, 2]], True, "diamond — no cycle"),
        (5, [[1, 4], [2, 4], [3, 1], [3, 2]], True, "multi-source"),
        (3, [[1, 0], [2, 1], [0, 2]], False, "cycle length 3"),
    ]
    for nc, prereqs, expected, desc in cases:
        result = can_finish(nc, prereqs)
        assert result == expected, f"can_finish({nc}, {prereqs}): expected {expected}, got {result} [{desc}]"
    print(f"  can_finish: {len(cases)}/{len(cases)} passed")


# ===========================================================================
# 10. serialize_tree / deserialize_tree  (BFS with None markers)
# ===========================================================================

class TreeNode:
    def __init__(self, val: int = 0, left: Optional['TreeNode'] = None,
                 right: Optional['TreeNode'] = None):
        self.val = val
        self.left = left
        self.right = right

    def __eq__(self, other: object) -> bool:
        if other is None:
            return False
        if not isinstance(other, TreeNode):
            return NotImplemented
        return (self.val == other.val and
                self.left == other.left and
                self.right == other.right)

    def __repr__(self) -> str:
        return f"TreeNode({self.val}, {self.left!r}, {self.right!r})"


def serialize(root: Optional[TreeNode]) -> str:
    """BFS serialization.

    Invariant: the queue always contains nodes in BFS order.
    None children are emitted as 'null' to preserve structure.
    Unique encoding: every tree maps to exactly one string, and
    no two distinct trees map to the same string (injectivity).
    """
    if root is None:
        return "[]"
    result: list[str] = []
    q: deque = deque([root])
    while q:
        node = q.popleft()
        if node is None:
            result.append("null")
        else:
            result.append(str(node.val))
            q.append(node.left)
            q.append(node.right)
    # Strip trailing nulls
    while result and result[-1] == "null":
        result.pop()
    return "[" + ",".join(result) + "]"


def deserialize(data: str) -> Optional[TreeNode]:
    """BFS deserialization — inverse of serialize.

    Invariant: parent_queue holds nodes whose children have not yet been
    assigned.  We consume values from the token list two at a time per parent.
    """
    data = data.strip()
    if data in ("[]", ""):
        return None
    tokens = data[1:-1].split(",")
    if not tokens or tokens[0] == "null":
        return None
    root = TreeNode(int(tokens[0]))
    q: deque = deque([root])
    i = 1
    while q and i < len(tokens):
        node = q.popleft()
        if i < len(tokens) and tokens[i] != "null":
            node.left = TreeNode(int(tokens[i]))
            q.append(node.left)
        i += 1
        if i < len(tokens) and tokens[i] != "null":
            node.right = TreeNode(int(tokens[i]))
            q.append(node.right)
        i += 1
    return root


def _make_tree(*vals: Optional[int]) -> Optional[TreeNode]:
    """Build a BFS-level tree from a flat list (None = missing node)."""
    if not vals or vals[0] is None:
        return None
    root = TreeNode(vals[0])
    q: deque = deque([root])
    i = 1
    while q and i < len(vals):
        node = q.popleft()
        if i < len(vals) and vals[i] is not None:
            node.left = TreeNode(vals[i])  # type: ignore[arg-type]
            q.append(node.left)
        i += 1
        if i < len(vals) and vals[i] is not None:
            node.right = TreeNode(vals[i])  # type: ignore[arg-type]
            q.append(node.right)
        i += 1
    return root


def _test_serialize_tree():
    cases = [
        (None, "round-trip None"),
        (_make_tree(1), "single node"),
        (_make_tree(1, 2, 3), "full 3-node"),
        (_make_tree(1, 2, 3, 4, 5), "5 nodes"),
        (_make_tree(1, None, 2, None, 3), "right-skewed"),
        (_make_tree(1, 2, None, 3), "left-skewed with gap"),
    ]
    for tree, desc in cases:
        encoded = serialize(tree)
        decoded = deserialize(encoded)
        # Re-encode for comparison (avoids reference equality)
        re_encoded = serialize(decoded)
        assert encoded == re_encoded, (
            f"serialize/deserialize round-trip failed [{desc}]: "
            f"original={encoded!r}, re-encoded={re_encoded!r}"
        )
    print(f"  serialize/deserialize: {len(cases)}/{len(cases)} passed")


# ===========================================================================
# Runner
# ===========================================================================

def main():
    print("Running all algorithm tests...\n")
    _test_valid_parentheses()
    _test_two_sum()
    _test_max_subarray()
    _test_num_islands()
    _test_coin_change()
    _test_word_break()
    _test_merge_intervals()
    _test_find_anagrams()
    _test_can_finish()
    _test_serialize_tree()

    total_tests = (10 + 7 + 8 + 6 + 8 + 8 + 8 + 8 + 8 + 6)
    print(f"\nAll {total_tests} tests passed across 10 algorithms.")


if __name__ == "__main__":
    main()
