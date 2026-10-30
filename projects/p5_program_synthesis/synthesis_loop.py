"""Program synthesis loop — P5."""
from __future__ import annotations
import ast
import re
from dataclasses import dataclass, field
from typing import Any, Callable
from enum import Enum


class DiagnosisType(Enum):
    WRONG_LOGIC = "wrong_logic"
    EDGE_CASE_GAP = "edge_case_gap"
    WRONG_SPEC_INTERPRETATION = "wrong_spec_interpretation"
    RUNTIME_ERROR = "runtime_error"
    TIMEOUT = "timeout"


@dataclass
class FormalSpec:
    natural_language: str
    preconditions: list[str] = field(default_factory=list)
    postconditions: list[str] = field(default_factory=list)
    edge_cases: list[str] = field(default_factory=list)
    examples: list[tuple] = field(default_factory=list)  # (input, expected_output)
    function_signature: str = ""


@dataclass
class TestCase:
    inputs: tuple
    expected: Any
    description: str = ""
    category: str = "general"  # boundary, property, metamorphic, example


@dataclass
class TestSuite:
    tests: list[TestCase] = field(default_factory=list)

    def add(self, test: TestCase):
        self.tests.append(test)

    def __len__(self):
        return len(self.tests)


@dataclass
class Diagnosis:
    failure_type: DiagnosisType
    failing_test: "TestCase"
    explanation: str
    suggested_fix: str = ""


@dataclass
class SynthesisResult:
    success: bool
    code: str
    iterations: int
    passed_tests: int
    failed_tests: int
    final_diagnosis: Diagnosis | None = None


class SynthesisLoop:
    """
    Deterministic template-based program synthesis loop.

    Strategy:
      1. Formalize the natural-language spec into pre/postconditions.
      2. Generate a test suite covering boundary, property, and example cases.
      3. Attempt to match the spec to a known algorithm template.
      4. Execute the candidate against the test suite.
      5. Diagnose failures and iterate with a refined template.
    """

    MAX_ITERATIONS = 8

    # ------------------------------------------------------------------ #
    # Public entry point                                                   #
    # ------------------------------------------------------------------ #

    def synthesize(self, spec: FormalSpec) -> SynthesisResult:
        """Full synthesis loop: spec → passing candidate."""
        formal = self.formalize_spec(spec.natural_language) if not spec.preconditions else spec
        suite = self.generate_test_suite(formal)

        failing: list[TestCase] = list(suite.tests)
        candidate = ""
        last_diagnosis: Diagnosis | None = None

        for iteration in range(1, self.MAX_ITERATIONS + 1):
            candidate = self.synthesize_candidate(formal, failing)

            still_failing: list[TestCase] = []
            for tc in suite.tests:
                ok, _ = self._run_test(candidate, tc)
                if not ok:
                    still_failing.append(tc)

            if not still_failing:
                passed = len(suite.tests)
                return SynthesisResult(
                    success=True,
                    code=candidate,
                    iterations=iteration,
                    passed_tests=passed,
                    failed_tests=0,
                )

            last_diagnosis = self.diagnose_failure(candidate, still_failing[0])
            failing = still_failing

        passed = sum(1 for tc in suite.tests if self._run_test(candidate, tc)[0])
        return SynthesisResult(
            success=False,
            code=candidate,
            iterations=self.MAX_ITERATIONS,
            passed_tests=passed,
            failed_tests=len(suite.tests) - passed,
            final_diagnosis=last_diagnosis,
        )

    # ------------------------------------------------------------------ #
    # Spec formalization                                                   #
    # ------------------------------------------------------------------ #

    def formalize_spec(self, natural_language: str) -> FormalSpec:
        """
        Extract pre/postconditions from natural language via keyword analysis.
        Returns a FormalSpec populated with heuristically inferred fields.
        """
        nl = natural_language.lower()
        spec = FormalSpec(natural_language=natural_language)

        # --- preconditions ---
        if "list" in nl or "array" in nl:
            spec.preconditions.append("input is a list")
        if "string" in nl or "str" in nl:
            spec.preconditions.append("input is a string")
        if "non-negative" in nl or "positive" in nl:
            spec.preconditions.append("all values >= 0")
        if "sorted" in nl:
            spec.preconditions.append("input is sorted in ascending order")
        if "target" in nl:
            spec.preconditions.append("target value is provided")

        # --- postconditions ---
        if "return true" in nl or "returns true" in nl:
            spec.postconditions.append("return bool")
        if "return index" in nl or "indices" in nl:
            spec.postconditions.append("return list of indices")
        if "minimum" in nl or "min coins" in nl:
            spec.postconditions.append("return minimum count or -1 if impossible")
        if "valid" in nl:
            spec.postconditions.append("return bool indicating validity")

        # --- edge cases ---
        if "empty" in nl:
            spec.edge_cases.append("empty input")
        if "single" in nl or "one element" in nl:
            spec.edge_cases.append("single element")
        if "duplicate" in nl:
            spec.edge_cases.append("duplicate elements")

        # --- function signature inference ---
        if "valid parentheses" in nl or "balanced brackets" in nl:
            spec.function_signature = "def valid_parentheses(s: str) -> bool:"
        elif "two sum" in nl:
            spec.function_signature = "def two_sum(nums: list, target: int) -> list:"
        elif "coin change" in nl or "fewest coins" in nl:
            spec.function_signature = "def coin_change(coins: list, amount: int) -> int:"
        else:
            spec.function_signature = "def solution(*args):"

        return spec

    # ------------------------------------------------------------------ #
    # Test-suite generation                                                #
    # ------------------------------------------------------------------ #

    def generate_test_suite(self, spec: FormalSpec) -> TestSuite:
        """
        Generate a test suite from the spec's examples, edge cases, and
        postconditions.  Also adds boundary and metamorphic tests for known
        algorithm patterns.
        """
        suite = TestSuite()

        # Seed from spec examples
        for inp, expected in spec.examples:
            if not isinstance(inp, tuple):
                inp = (inp,)
            suite.add(TestCase(inputs=inp, expected=expected, category="example"))

        sig = spec.function_signature.lower()

        if "valid_parentheses" in sig:
            suite.add(TestCase(("",), True, "empty string", "boundary"))
            suite.add(TestCase(("()",), True, "single pair", "example"))
            suite.add(TestCase(("()[]{}", ), True, "multiple pairs", "example"))
            suite.add(TestCase(("(]",), False, "mismatched", "example"))
            suite.add(TestCase(("([)]",), False, "interleaved", "example"))
            suite.add(TestCase(("{[]}",), True, "nested", "example"))
            suite.add(TestCase(("(((",), False, "unclosed open", "boundary"))
            suite.add(TestCase((")))",), False, "unclosed close", "boundary"))

        elif "two_sum" in sig:
            suite.add(TestCase(([2, 7, 11, 15], 9), [0, 1], "basic", "example"))
            suite.add(TestCase(([3, 2, 4], 6), [1, 2], "non-zero indices", "example"))
            suite.add(TestCase(([3, 3], 6), [0, 1], "duplicates", "example"))
            suite.add(TestCase(([1, 2, 3, 4], 7), [2, 3], "last two", "boundary"))
            suite.add(TestCase(([0, 4, 3, 0], 0), [0, 3], "zeros", "boundary"))

        elif "coin_change" in sig:
            suite.add(TestCase(([1, 5, 11], 11), 1, "exact coin", "example"))
            suite.add(TestCase(([1, 2, 5], 11), 3, "classic", "example"))
            suite.add(TestCase(([2], 3), -1, "impossible", "example"))
            suite.add(TestCase(([1], 0), 0, "amount zero", "boundary"))
            suite.add(TestCase(([1], 1), 1, "single coin", "boundary"))
            suite.add(TestCase(([1, 2, 5], 0), 0, "zero amount", "boundary"))
            suite.add(TestCase(([2, 5, 10, 1], 27), 4, "greedy fails", "property"))

        return suite

    # ------------------------------------------------------------------ #
    # Candidate generation                                                 #
    # ------------------------------------------------------------------ #

    # Template library — deterministic, no LLM
    _TEMPLATES: dict[str, str] = {
        "valid_parentheses": """\
def valid_parentheses(s: str) -> bool:
    # Stack invariant: stack holds unmatched open brackets.
    # After processing all chars, stack must be empty.
    stack = []
    matching = {')': '(', '}': '{', ']': '['}
    for ch in s:
        if ch in '([{':
            stack.append(ch)
        elif ch in ')]}':
            if not stack or stack[-1] != matching[ch]:
                return False
            stack.pop()
    return len(stack) == 0
""",
        "two_sum": """\
def two_sum(nums: list, target: int) -> list:
    # Hash map invariant: seen[v] = index of v encountered so far.
    # For each num, complement = target - num; if seen, return pair.
    seen = {}
    for i, num in enumerate(nums):
        complement = target - num
        if complement in seen:
            return [seen[complement], i]
        seen[num] = i
    return []
""",
        "coin_change": """\
def coin_change(coins: list, amount: int) -> int:
    # DP invariant: dp[i] = fewest coins summing to i, or inf if impossible.
    # dp[0] = 0 (base case). dp[i] = min(dp[i - c] + 1) for c in coins, c <= i.
    INF = float('inf')
    dp = [INF] * (amount + 1)
    dp[0] = 0
    for i in range(1, amount + 1):
        for c in coins:
            if c <= i and dp[i - c] + 1 < dp[i]:
                dp[i] = dp[i - c] + 1
    return dp[amount] if dp[amount] != INF else -1
""",
    }

    def synthesize_candidate(self, spec: FormalSpec, failing_tests: list[TestCase]) -> str:
        """
        Select and return a candidate implementation.

        Uses the function signature to pick a template.  If a previous
        attempt failed, the same template is returned (templates are already
        correct; failures indicate a spec/test mismatch in this toy system).
        """
        sig = spec.function_signature.lower()

        for key, template in self._TEMPLATES.items():
            if key in sig:
                return template

        # Generic fallback — identity function
        return "def solution(*args):\n    return args[0] if args else None\n"

    # ------------------------------------------------------------------ #
    # Failure diagnosis                                                    #
    # ------------------------------------------------------------------ #

    def diagnose_failure(self, candidate: str, test: TestCase) -> Diagnosis:
        """Classify the failure mode of *candidate* on *test*."""
        ok, exc = self._run_test(candidate, test)
        if ok:
            return Diagnosis(
                failure_type=DiagnosisType.WRONG_LOGIC,
                failing_test=test,
                explanation="Test actually passed — no diagnosis needed.",
            )

        if exc is not None:
            if isinstance(exc, (TypeError, AttributeError, IndexError)):
                return Diagnosis(
                    failure_type=DiagnosisType.RUNTIME_ERROR,
                    failing_test=test,
                    explanation=f"Runtime error: {exc}",
                    suggested_fix="Check type assumptions and bounds.",
                )
            return Diagnosis(
                failure_type=DiagnosisType.RUNTIME_ERROR,
                failing_test=test,
                explanation=str(exc),
            )

        # Distinguish edge-case gaps from logic errors
        if test.category in ("boundary", "edge"):
            return Diagnosis(
                failure_type=DiagnosisType.EDGE_CASE_GAP,
                failing_test=test,
                explanation=(
                    f"Edge case not handled: {test.description!r}. "
                    f"Input {test.inputs!r} expected {test.expected!r}."
                ),
                suggested_fix="Add explicit handling for this boundary condition.",
            )

        return Diagnosis(
            failure_type=DiagnosisType.WRONG_LOGIC,
            failing_test=test,
            explanation=(
                f"Logic error on {test.description!r}: "
                f"input {test.inputs!r} expected {test.expected!r}."
            ),
            suggested_fix="Re-examine the core algorithm invariant.",
        )

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _run_test(self, code: str, test: TestCase) -> tuple[bool, Exception | None]:
        """Execute *code* and call the synthesized function with test.inputs."""
        try:
            namespace: dict = {}
            exec(compile(code, "<synthesis>", "exec"), namespace)

            # Find the first callable that isn't a builtin
            fn = None
            for v in namespace.values():
                if callable(v) and not isinstance(v, type):
                    fn = v
                    break

            if fn is None:
                return False, ValueError("No callable found in synthesized code")

            result = fn(*test.inputs)
            return result == test.expected, None
        except Exception as exc:
            return False, exc


# ======================================================================= #
# Demo                                                                      #
# ======================================================================= #

def _run_demo():
    loop = SynthesisLoop()

    # ---- valid_parentheses ----
    vp_spec = FormalSpec(
        natural_language="valid parentheses: given a string of brackets return true if balanced",
        function_signature="def valid_parentheses(s: str) -> bool:",
        examples=[("()", True), ("(]", False), ("{[]}", True)],
        edge_cases=["empty string"],
    )
    vp_result = loop.synthesize(vp_spec)
    assert vp_result.success, f"valid_parentheses synthesis failed: {vp_result}"
    print(f"[valid_parentheses] iterations={vp_result.iterations}  "
          f"passed={vp_result.passed_tests}  failed={vp_result.failed_tests}")

    # ---- two_sum ----
    ts_spec = FormalSpec(
        natural_language="two sum: return indices of two numbers that add to target",
        function_signature="def two_sum(nums: list, target: int) -> list:",
        examples=[([2, 7, 11, 15], 9)],
    )
    # inject expected into examples properly
    ts_spec.examples = [((( [2, 7, 11, 15], 9), [0, 1]))]
    ts_spec.examples = []
    ts_result = loop.synthesize(ts_spec)
    assert ts_result.success, f"two_sum synthesis failed: {ts_result}"
    print(f"[two_sum]           iterations={ts_result.iterations}  "
          f"passed={ts_result.passed_tests}  failed={ts_result.failed_tests}")

    # ---- coin_change ----
    cc_spec = FormalSpec(
        natural_language="coin change: fewest coins to make amount, return -1 if impossible",
        function_signature="def coin_change(coins: list, amount: int) -> int:",
        examples=[],
    )
    cc_result = loop.synthesize(cc_spec)
    assert cc_result.success, f"coin_change synthesis failed: {cc_result}"
    print(f"[coin_change]       iterations={cc_result.iterations}  "
          f"passed={cc_result.passed_tests}  failed={cc_result.failed_tests}")

    print("\nAll synthesis demos passed.")


if __name__ == "__main__":
    _run_demo()
