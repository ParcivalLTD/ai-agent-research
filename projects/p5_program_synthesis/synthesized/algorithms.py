"""
Synthesized programs from P5 — Program Synthesis from Natural Language.

All three programs are synthesized from English specifications,
with formal correctness arguments and adversarially-derived test suites.
"""

import bisect
from collections import OrderedDict
from functools import lru_cache


# =============================================================================
# SPEC 1: Longest Strictly Increasing Subsequence
# =============================================================================
# Spec: "Given a list of integers, return the length of the longest
# strictly increasing subsequence. The subsequence does not need to be
# contiguous."
#
# Preconditions:  nums is a list of integers
# Postconditions: result == len of longest strictly increasing subsequence
#                 0 <= result <= len(nums)
#                 result == 0 iff nums is empty
#
# Correctness: Patience sorting invariant.
# Invariant: tails[i] is the minimum possible tail value of any strictly
# increasing subsequence of length i+1 seen so far. tails is always sorted.
# =============================================================================

def lis_length(nums: list[int]) -> int:
    """O(n log n) via patience sorting."""
    tails = []
    for num in nums:
        pos = bisect.bisect_left(tails, num)  # leftmost position >= num
        if pos == len(tails):
            tails.append(num)   # extend: new longest length
        else:
            tails[pos] = num    # replace: better tail for length pos+1
    return len(tails)


def lis_length_dp(nums: list[int]) -> int:
    """O(n^2) DP — alternative, useful when actual subsequence is needed."""
    if not nums:
        return 0
    dp = [1] * len(nums)
    for i in range(1, len(nums)):
        for j in range(i):
            if nums[j] < nums[i]:
                dp[i] = max(dp[i], dp[j] + 1)
    return max(dp)


# Test suite (12 cases, derived from spec before implementation)
_LIS_TESTS = [
    ([], 0),
    ([7], 1),
    ([5, 5, 5, 5], 1),          # all same — strict inequality
    ([1, 2, 3, 4, 5], 5),       # sorted ascending
    ([5, 4, 3, 2, 1], 1),       # sorted descending
    ([10, 9, 2, 5, 3, 7, 101, 18], 4),  # canonical mixed
    ([0, 1, 0, 3, 2, 3], 4),
    ([2, 2, 2, 1], 1),
    ([-3, -2, -1, 0], 4),       # negative integers
    ([3, 1, 4, 1, 5, 9, 2, 6], 4),
    ([1, 3, 6, 7, 9, 4, 10, 5, 6], 6),
    ([2, 15, 3, 7, 8, 6, 18], 5),
]


# =============================================================================
# SPEC 2: Minimum Deletions to Make a Palindrome
# =============================================================================
# Spec: "Given a string, return the minimum number of characters that need
# to be deleted to make the string a palindrome."
#
# Key reduction: min_deletions = len(s) - LPS(s)
#                LPS(s) = LCS(s, reverse(s))
#
# Correctness: A subsequence P of s is a palindrome iff P is a common
# subsequence of s and s_reversed.
# =============================================================================

def min_deletions_palindrome(s: str) -> int:
    """O(n^2) via LCS(s, reverse(s)). Iterative DP, O(n^2) space."""
    n = len(s)
    if n == 0:
        return 0
    t = s[::-1]
    dp = [[0] * (n + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, n + 1):
            if s[i - 1] == t[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return n - dp[n][n]


def min_deletions_palindrome_v2(s: str) -> int:
    """Alternative: direct LPS via memoized recursion. Clearer semantics."""
    @lru_cache(maxsize=None)
    def lps(i: int, j: int) -> int:
        if i > j:   return 0
        if i == j:  return 1
        if s[i] == s[j]:  return 2 + lps(i + 1, j - 1)
        return max(lps(i + 1, j), lps(i, j - 1))
    return len(s) - lps(0, len(s) - 1)


# Test suite (14 cases)
_PALINDROME_TESTS = [
    ("", 0),
    ("a", 0),
    ("aa", 0),
    ("ab", 1),
    ("racecar", 0),
    ("abcba", 0),
    ("abcd", 3),
    ("aab", 1),
    ("abcbad", 1),
    ("abcdef", 5),
    ("aaaa", 0),
    ("abca", 1),
    ("abcda", 2),
    ("geeksforgeeks", 8),
]


# =============================================================================
# SPEC 3: Largest Rectangle in Histogram
# =============================================================================
# Spec: "Given a list of non-negative integers representing the heights of
# bars in a histogram, return the area of the largest rectangle that can
# be formed within the histogram."
#
# Correctness argument (monotonic stack):
# For bar at index p popped by index i:
#   - Right boundary: i is the first index with height < heights[p]
#   - Left boundary: stack[-1] is the nearest index with height < heights[p]
#   - Width = i - left - 1 is the widest span where heights[p] is minimum
# Every bar is pushed/popped exactly once → O(n)
# =============================================================================

def largest_rectangle_histogram(heights: list[int]) -> int:
    """O(n) monotonic stack solution."""
    stack = []
    max_area = 0
    extended = heights + [0]   # sentinel forces full stack flush

    for i, h in enumerate(extended):
        while stack and extended[stack[-1]] > h:
            height = extended[stack.pop()]
            left   = stack[-1] if stack else -1
            width  = i - left - 1
            max_area = max(max_area, height * width)
        stack.append(i)

    return max_area


def largest_rectangle_histogram_dc(heights: list[int]) -> int:
    """Alternative: O(n log n) average divide and conquer.
    Correctness: every max rectangle has some min bar m; it spans across m
    (handled by full case), lies left of m, or right of m. Exhaustive. """
    def solve(lo: int, hi: int) -> int:
        if lo > hi:  return 0
        min_idx = min(range(lo, hi + 1), key=lambda k: heights[k])
        full  = heights[min_idx] * (hi - lo + 1)
        left  = solve(lo, min_idx - 1)
        right = solve(min_idx + 1, hi)
        return max(full, left, right)
    return solve(0, len(heights) - 1) if heights else 0


# Test suite (14 cases)
_HISTOGRAM_TESTS = [
    ([], 0),
    ([0], 0),
    ([5], 5),
    ([2, 1, 2], 3),
    ([2, 1, 5, 6, 2, 3], 10),
    ([1, 1, 1, 1], 4),
    ([4, 4, 4, 4], 16),
    ([1, 2, 3, 4, 5], 9),
    ([5, 4, 3, 2, 1], 9),
    ([6, 2, 5, 4, 5, 1, 6], 12),
    ([0, 0, 0], 0),
    ([3, 6, 5, 7, 4, 8, 1, 0], 20),
    ([2, 2], 4),
    ([1, 2, 3, 4, 5, 3, 3], 15),
]


# =============================================================================
# Test runner
# =============================================================================

def run_all_tests() -> None:
    passed = 0
    failed = 0

    for nums, expected in _LIS_TESTS:
        result = lis_length(nums)
        assert result == expected, f"LIS({nums}): got {result}, expected {expected}"
        assert lis_length_dp(nums) == expected, f"LIS_DP({nums}) mismatch"
        passed += 2

    for s, expected in _PALINDROME_TESTS:
        result = min_deletions_palindrome(s)
        assert result == expected, f"PALINDROME({s!r}): got {result}, expected {expected}"
        assert min_deletions_palindrome_v2(s) == expected, f"PALINDROME_V2({s!r}) mismatch"
        passed += 2

    for heights, expected in _HISTOGRAM_TESTS:
        result = largest_rectangle_histogram(heights)
        assert result == expected, f"HISTOGRAM({heights}): got {result}, expected {expected}"
        assert largest_rectangle_histogram_dc(heights) == expected, f"HISTOGRAM_DC({heights}) mismatch"
        passed += 2

    print(f"All {passed} tests passed.")


if __name__ == "__main__":
    run_all_tests()
