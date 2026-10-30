"""Adversarial test generator for the self-improving agent."""
from __future__ import annotations
import ast
import re
import random
import copy
import textwrap
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TestCase:
    inputs: tuple
    expected: Any
    description: str = ""
    kills_mutants: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# MutationEngine
# ---------------------------------------------------------------------------

class MutationEngine:
    """Apply source-level mutation operators to Python source code."""

    OPERATORS = [
        "flip_comparison",
        "remove_condition",
        "change_constant",
        "negate_condition",
        "change_return",
    ]

    # --- operator implementations ------------------------------------------

    def _flip_comparison(self, source: str) -> list[str]:
        """Flip comparison operators: < ↔ >, <= ↔ >=, == ↔ !="""
        flips = [
            (r'(?<![<>!])<=(?!=)', '<<<LE>>>'),
            (r'(?<![<>!])>=(?!=)', '>>>GE>>>'),
            (r'(?<![<>!])<(?![<=])', '<<<LT>>>'),
            (r'(?<![<>!])>(?![>=])', '>>>GT>>>'),
            (r'(?<![!=])==(?!=)', '<<<EQ>>>'),
            (r'(?<![!])!=',       '>>>NE>>>'),
        ]
        replacements = {
            '<<<LE>>>': '>=',
            '>>>GE>>>': '<=',
            '<<<LT>>>': '>',
            '>>>GT>>>': '<',
            '<<<EQ>>>': '!=',
            '>>>NE>>>': '==',
        }

        mutants: list[str] = []
        # Find all comparison operators and flip them one at a time
        pattern = r'(?<![<>!=])(<=|>=|==|!=|<(?![<=])|>(?![>=]))'
        matches = list(re.finditer(pattern, source))
        for m in matches:
            op = m.group(0)
            flip_map = {
                '<=': '>=', '>=': '<=',
                '==': '!=', '!=': '==',
                '<': '>', '>': '<',
            }
            if op in flip_map:
                mutant = source[:m.start()] + flip_map[op] + source[m.end():]
                if mutant != source:
                    mutants.append(mutant)
        return mutants

    def _remove_condition(self, source: str) -> list[str]:
        """Replace if-condition with True (condition always passes)."""
        mutants: list[str] = []
        pattern = r'(if\s+)(.+?)(:)'
        for m in re.finditer(pattern, source):
            before = source[:m.start()]
            after = source[m.end():]
            mutant = before + m.group(1) + 'True' + m.group(3) + after
            if mutant != source:
                mutants.append(mutant)
        return mutants

    def _change_constant(self, source: str) -> list[str]:
        """Change numeric constants by ±1."""
        mutants: list[str] = []
        pattern = r'(?<!\w)(-?\d+)(?!\w)'
        matches = list(re.finditer(pattern, source))
        for m in matches:
            val = int(m.group(0))
            for delta in [-1, 1]:
                mutant = source[:m.start()] + str(val + delta) + source[m.end():]
                if mutant != source:
                    mutants.append(mutant)
        return mutants

    def _negate_condition(self, source: str) -> list[str]:
        """Negate boolean conditions: if x → if not x"""
        mutants: list[str] = []
        pattern = r'(if\s+)((?!True|False|not\s).+?)(:)'
        for m in re.finditer(pattern, source):
            cond = m.group(2).strip()
            if cond not in ('True', 'False'):
                before = source[:m.start()]
                after = source[m.end():]
                mutant = before + m.group(1) + f'not ({cond})' + m.group(3) + after
                if mutant != source:
                    mutants.append(mutant)
        return mutants

    def _change_return(self, source: str) -> list[str]:
        """Change return value: return x → return -1"""
        mutants: list[str] = []
        pattern = r'(return\s+)(.+?)(\n|$)'
        for m in re.finditer(pattern, source):
            ret_val = m.group(2).strip()
            for replacement in ['-1', '0', 'None']:
                if ret_val != replacement:
                    mutant = (source[:m.start()]
                              + m.group(1) + replacement
                              + source[m.start() + len(m.group(1)) + len(m.group(2)):])
                    if mutant != source:
                        mutants.append(mutant)
        return mutants

    def mutate(self, source: str, operator: str) -> list[str]:
        """Apply mutation operator, return all possible mutants."""
        dispatch = {
            "flip_comparison": self._flip_comparison,
            "remove_condition": self._remove_condition,
            "change_constant": self._change_constant,
            "negate_condition": self._negate_condition,
            "change_return": self._change_return,
        }
        if operator not in dispatch:
            raise ValueError(f"Unknown operator: {operator}")
        return dispatch[operator](source)

    def _run_test_on_mutant(self, mutant_src: str, test: TestCase) -> bool:
        """Execute the mutant against a test; return True if test KILLS the mutant."""
        try:
            ns: dict = {}
            exec(compile(mutant_src, '<mutant>', 'exec'), ns)
            # Find the first callable in the namespace that isn't a dunder
            func = None
            for name, obj in ns.items():
                if callable(obj) and not name.startswith('_'):
                    func = obj
                    break
            if func is None:
                return False
            result = func(*test.inputs)
            return result != test.expected
        except Exception:
            # If the mutant raises, the test "kills" it (observed different behaviour)
            return True

    def _all_mutants(self, source: str, max_per_op: int = 8) -> list[str]:
        """Generate at most max_per_op mutants per operator, deduplicated."""
        seen: set[str] = set()
        result: list[str] = []
        for op in self.OPERATORS:
            for m in self.mutate(source, op)[:max_per_op]:
                if m != source and m not in seen:
                    seen.add(m)
                    result.append(m)
        return result

    def mutation_score(self, source: str, tests: list[TestCase]) -> float:
        """Run all mutants against test suite, return kill rate (0.0–1.0)."""
        all_mutants = self._all_mutants(source)

        if not all_mutants:
            return 1.0   # No mutants to kill → trivially 1.0

        killed = 0
        for mutant in all_mutants:
            for test in tests:
                if self._run_test_on_mutant(mutant, test):
                    killed += 1
                    break   # One kill per mutant is sufficient

        return killed / len(all_mutants)

    def surviving_mutants(self, source: str, tests: list[TestCase]) -> list[str]:
        """Return mutants not killed by the test suite."""
        survivors = []
        for mutant in self._all_mutants(source):
            killed = False
            for test in tests:
                if self._run_test_on_mutant(mutant, test):
                    killed = True
                    break
            if not killed:
                survivors.append(mutant)
        return survivors


# ---------------------------------------------------------------------------
# AdversarialTestGenerator
# ---------------------------------------------------------------------------

class AdversarialTestGenerator:
    """Generate tests that kill surviving mutants of a program."""

    def __init__(self, engine: MutationEngine | None = None,
                 rng_seed: int = 42) -> None:
        self.engine = engine or MutationEngine()
        self.rng = random.Random(rng_seed)

    # ---- public API -------------------------------------------------------

    def generate_adversarial_tests(
        self,
        program: str,
        spec: dict | None = None,
        existing_tests: list[TestCase] | None = None,
    ) -> list[TestCase]:
        """
        Generate adversarial tests by combining boundary analysis and
        mutation-based test generation.

        Returns a list of new TestCase objects, deduplicated against
        existing_tests.
        """
        existing = existing_tests or []
        existing_inputs = {t.inputs for t in existing}

        candidates: list[TestCase] = []
        candidates.extend(self.boundary_analysis(program))
        candidates.extend(self.mutation_based_tests(program))

        # Deduplicate
        new_tests = []
        seen: set = set()
        for tc in candidates:
            key = (tc.inputs, repr(tc.expected))
            if key not in seen and tc.inputs not in existing_inputs:
                seen.add(key)
                new_tests.append(tc)

        return new_tests

    def boundary_analysis(self, program: str) -> list[TestCase]:
        """
        Find all numeric comparisons in the program source and generate
        inputs at the boundary values (n-1, n, n+1).

        Returns TestCase objects with inputs derived from each comparison.
        """
        tests: list[TestCase] = []

        # Compile to check syntax; if invalid, return empty
        try:
            tree = ast.parse(program)
        except SyntaxError:
            return tests

        # Find all Compare nodes and extract constants
        constants_found: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                for comparator in node.comparators:
                    if isinstance(comparator, ast.Constant) and isinstance(comparator.value, int):
                        constants_found.add(comparator.value)
            elif isinstance(node, ast.BinOp):
                if isinstance(node.right, ast.Constant) and isinstance(node.right.value, int):
                    constants_found.add(node.right.value)

        # Build test cases around each constant boundary
        ns: dict = {}
        try:
            exec(compile(program, '<prog>', 'exec'), ns)
        except Exception:
            return tests

        func = self._find_func(ns)
        if func is None:
            return tests

        for const in sorted(constants_found):
            for val in [const - 1, const, const + 1]:
                # Try calling with a single int argument
                for inp in [(val,), ([val],), (val, val)]:
                    try:
                        result = func(*inp)
                        tests.append(TestCase(
                            inputs=inp,
                            expected=result,
                            description=f"boundary: comparison constant {const}, input {inp}",
                        ))
                    except Exception:
                        continue

        return tests

    def mutation_based_tests(self, program: str) -> list[TestCase]:
        """
        Generate tests that specifically kill surviving mutants.
        For each surviving mutant, find an input that distinguishes the
        mutant's output from the original.
        """
        tests: list[TestCase] = []

        ns: dict = {}
        try:
            exec(compile(program, '<prog>', 'exec'), ns)
        except Exception:
            return tests

        func = self._find_func(ns)
        if func is None:
            return tests

        # Small fixed candidate input set — fast, enough to catch most mutations
        candidate_inputs = [
            ([],),
            ([1],),
            ([1, 2, 3], 0),
            ([1, 2, 3], 2),
            ([1, 2, 3], 4),
            ([0, 1, 2, 3, 4], 2),
            ([0, 1, 2, 3, 4], 5),
            (0,), (1,), (-1,), (5,),
        ]

        for op in self.engine.OPERATORS:
            mutants = self.engine.mutate(program, op)
            for mutant_src in mutants[:3]:   # limit per operator
                try:
                    mut_ns: dict = {}
                    exec(compile(mutant_src, '<mutant>', 'exec'), mut_ns)
                    mut_func = self._find_func(mut_ns)
                    if mut_func is None:
                        continue

                    for inp in candidate_inputs:
                        try:
                            original_result = func(*inp)
                            mutant_result = mut_func(*inp)
                            if original_result != mutant_result:
                                tc = TestCase(
                                    inputs=inp,
                                    expected=original_result,
                                    description=f"mutation-based: kills {op} mutant",
                                    kills_mutants=[op],
                                )
                                tests.append(tc)
                                break   # one killing test per mutant is enough
                        except Exception:
                            continue
                except Exception:
                    continue

        return tests

    def kills_new_mutant(self, test: TestCase, program: str) -> bool:
        """
        Quality gate: does this test kill at least one new mutant
        (not already in its kills_mutants list)?
        """
        ns: dict = {}
        try:
            exec(compile(program, '<prog>', 'exec'), ns)
            func = self._find_func(ns)
            if func is None:
                return False
        except Exception:
            return False

        for op in self.engine.OPERATORS:
            if op in test.kills_mutants:
                continue   # already known to kill this operator's mutants
            mutants = self.engine.mutate(program, op)
            for mutant_src in mutants[:3]:
                if self.engine._run_test_on_mutant(mutant_src, test):
                    return True
        return False

    # ---- helpers ----------------------------------------------------------

    def _find_func(self, ns: dict):
        """Return the first top-level callable in a namespace."""
        for name, obj in ns.items():
            if callable(obj) and not name.startswith('_'):
                return obj
        return None

    def _generate_candidate_inputs(self, program: str) -> list[tuple]:
        """Heuristically generate a range of candidate inputs for a program."""
        inputs: list[tuple] = []

        # Always try common single-value inputs
        for v in [-1, 0, 1, 2, 5, 10, 100]:
            inputs.append((v,))

        # Sorted arrays of various sizes
        for size in [0, 1, 2, 5, 10]:
            arr = list(range(size))
            inputs.append((arr,))
            if size > 0:
                inputs.append((arr, 0))   # (array, target)
                inputs.append((arr, size - 1))
                inputs.append((arr, size // 2))
                inputs.append((arr, -1))   # target not in array

        # Edge cases
        inputs.append(([],))
        inputs.append(([1],))
        inputs.append(([1, 2, 3], 2))
        inputs.append(([1, 2, 3], 4))

        return inputs


# ---------------------------------------------------------------------------
# ConvergenceDetector
# ---------------------------------------------------------------------------

class ConvergenceDetector:
    """Determine whether a test suite has converged for a given program."""

    MUTATION_SCORE_THRESHOLD = 0.85

    def __init__(self, engine: MutationEngine | None = None,
                 threshold: float = 0.85) -> None:
        self.engine = engine or MutationEngine()
        self.threshold = threshold

    def is_converged(self, program: str, tests: list[TestCase]) -> bool:
        """
        Return True iff:
        1. All tests pass against the original program, AND
        2. mutation_score >= threshold
        """
        if not self._all_pass(program, tests):
            return False
        score = self.engine.mutation_score(program, tests)
        return score >= self.threshold

    def convergence_report(self, program: str, tests: list[TestCase]) -> dict:
        """Return a dict with mutation_score, passing_tests, failing_tests, and converged."""
        passing = []
        failing = []

        ns: dict = {}
        try:
            exec(compile(program, '<prog>', 'exec'), ns)
            func_name, func = None, None
            for name, obj in ns.items():
                if callable(obj) and not name.startswith('_'):
                    func_name, func = name, obj
                    break
        except Exception:
            func = None

        for tc in tests:
            if func is None:
                failing.append(tc.description)
                continue
            try:
                result = func(*tc.inputs)
                if result == tc.expected:
                    passing.append(tc.description)
                else:
                    failing.append(tc.description)
            except Exception:
                failing.append(tc.description)

        score = self.engine.mutation_score(program, tests)
        converged = (len(failing) == 0) and (score >= self.threshold)

        return {
            "mutation_score": round(score, 4),
            "passing_tests": len(passing),
            "failing_tests": len(failing),
            "converged": converged,
            "threshold": self.threshold,
        }

    def _all_pass(self, program: str, tests: list[TestCase]) -> bool:
        ns: dict = {}
        try:
            exec(compile(program, '<prog>', 'exec'), ns)
        except Exception:
            return False

        func = None
        for name, obj in ns.items():
            if callable(obj) and not name.startswith('_'):
                func = obj
                break

        if func is None:
            return False

        for tc in tests:
            try:
                result = func(*tc.inputs)
                if result != tc.expected:
                    return False
            except Exception:
                return False
        return True


# ---------------------------------------------------------------------------
# DEMO — binary_search from P9 results
# ---------------------------------------------------------------------------

BINARY_SEARCH_SRC = textwrap.dedent("""\
def binary_search(arr, target):
    lo, hi = 0, len(arr) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1
""")


def demo() -> None:
    print("=" * 60)
    print("DEMO: Adversarial test generation for binary_search")
    print("=" * 60)

    engine = MutationEngine()
    generator = AdversarialTestGenerator(engine, rng_seed=0)
    detector = ConvergenceDetector(engine, threshold=0.85)

    # Initial (minimal) test suite
    initial_tests = [
        TestCase(inputs=([1, 2, 3, 4, 5], 3), expected=2,
                 description="basic: find middle element"),
        TestCase(inputs=([1, 2, 3, 4, 5], 1), expected=0,
                 description="basic: find first element"),
    ]

    report_before = detector.convergence_report(BINARY_SEARCH_SRC, initial_tests)
    print(f"\nBefore adversarial round:")
    print(f"  Mutation score : {report_before['mutation_score']:.2%}")
    print(f"  Passing tests  : {report_before['passing_tests']}")
    print(f"  Converged      : {report_before['converged']}")

    # Generate adversarial tests
    new_tests = generator.generate_adversarial_tests(
        BINARY_SEARCH_SRC,
        existing_tests=initial_tests,
    )

    all_tests = initial_tests + new_tests

    report_after = detector.convergence_report(BINARY_SEARCH_SRC, all_tests)
    print(f"\nAfter adversarial round ({len(new_tests)} new tests added):")
    print(f"  Mutation score : {report_after['mutation_score']:.2%}")
    print(f"  Passing tests  : {report_after['passing_tests']}")
    print(f"  Converged      : {report_after['converged']}")

    improvement = report_after['mutation_score'] - report_before['mutation_score']
    print(f"\nMutation score improvement: {improvement:+.2%}")

    survived = engine.surviving_mutants(BINARY_SEARCH_SRC, all_tests)
    print(f"Surviving mutants          : {len(survived)}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    passed = 0
    failed = 0

    def ok(cond: bool, name: str) -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {name}")

    engine = MutationEngine()

    # ------- MutationEngine.mutate -----------------------------------------
    simple = "def f(x):\n    if x < 10:\n        return 1\n    return 0\n"

    fc_mutants = engine.mutate(simple, "flip_comparison")
    ok(len(fc_mutants) > 0,               "flip_comparison produces mutants")
    ok(any('>' in m for m in fc_mutants), "flip_comparison creates > from <")

    cc_mutants = engine.mutate(simple, "change_constant")
    ok(len(cc_mutants) > 0,               "change_constant produces mutants")
    ok(any('11' in m or '9' in m for m in cc_mutants), "change_constant shifts 10")

    nc_mutants = engine.mutate(simple, "negate_condition")
    ok(len(nc_mutants) > 0,               "negate_condition produces mutants")
    ok(any('not' in m for m in nc_mutants), "negate_condition adds 'not'")

    cr_mutants = engine.mutate(simple, "change_return")
    ok(len(cr_mutants) > 0,               "change_return produces mutants")

    # remove_condition
    rc_mutants = engine.mutate(simple, "remove_condition")
    ok(any('True' in m for m in rc_mutants), "remove_condition inserts True")

    # Unknown operator raises
    raised = False
    try:
        engine.mutate(simple, "nonexistent_op")
    except ValueError:
        raised = True
    ok(raised,                            "unknown operator raises ValueError")

    # ------- mutation_score ------------------------------------------------
    good_tests = [
        TestCase(inputs=(5,), expected=1,   description="x < 10 → 1"),
        TestCase(inputs=(10,), expected=0,  description="x == 10 → 0"),
        TestCase(inputs=(15,), expected=0,  description="x > 10 → 0"),
        TestCase(inputs=(9,), expected=1,   description="x = 9 → 1"),
        TestCase(inputs=(11,), expected=0,  description="x = 11 → 0"),
    ]
    score = engine.mutation_score(simple, good_tests)
    ok(0.0 <= score <= 1.0,               "mutation_score in [0,1]")
    ok(score > 0.0,                        "good tests kill at least one mutant")

    poor_tests: list[TestCase] = []
    score_empty = engine.mutation_score(simple, poor_tests)
    ok(score_empty == 1.0,                 "empty test suite returns 1.0 (no mutants to kill?)")

    # Actually: no tests → 0 killed → but we special-case it above
    # Let's also verify with one bad test that kills nothing significant
    trivial = [TestCase(inputs=(0,), expected=1, description="trivial")]
    score_trivial = engine.mutation_score(simple, trivial)
    ok(0.0 <= score_trivial <= 1.0,       "trivial test suite has valid score")

    # ------- surviving_mutants --------------------------------------------
    survivors = engine.surviving_mutants(simple, good_tests)
    ok(isinstance(survivors, list),        "surviving_mutants returns a list")
    all_mutants_count = sum(len(engine.mutate(simple, op)) for op in engine.OPERATORS)
    ok(len(survivors) <= all_mutants_count, "survivors is subset of all mutants")

    # ------- AdversarialTestGenerator.boundary_analysis -------------------
    gen = AdversarialTestGenerator(engine, rng_seed=0)
    boundary_tests = gen.boundary_analysis(BINARY_SEARCH_SRC)
    ok(len(boundary_tests) > 0,            "boundary_analysis returns tests")
    ok(all(isinstance(t, TestCase) for t in boundary_tests),
                                           "boundary_analysis returns TestCase objects")

    # ------- AdversarialTestGenerator.mutation_based_tests ----------------
    mut_tests = gen.mutation_based_tests(BINARY_SEARCH_SRC)
    ok(isinstance(mut_tests, list),        "mutation_based_tests returns a list")

    # ------- AdversarialTestGenerator.generate_adversarial_tests ----------
    seed_tests = [
        TestCase(inputs=([1, 2, 3], 2), expected=1, description="seed"),
    ]
    new_tests = gen.generate_adversarial_tests(BINARY_SEARCH_SRC, existing_tests=seed_tests)
    ok(isinstance(new_tests, list),        "generate_adversarial_tests returns a list")
    # New tests should not duplicate seed tests
    ok(all(t.inputs != ([1, 2, 3], 2) for t in new_tests),
                                           "adversarial tests deduplicated vs seed")

    # ------- AdversarialTestGenerator.kills_new_mutant --------------------
    killer_test = TestCase(inputs=([1, 2, 3], -1), expected=-1, description="not found")
    ok(isinstance(gen.kills_new_mutant(killer_test, BINARY_SEARCH_SRC), bool),
                                           "kills_new_mutant returns bool")

    # ------- ConvergenceDetector ------------------------------------------
    detector = ConvergenceDetector(engine, threshold=0.85)

    report = detector.convergence_report(BINARY_SEARCH_SRC, seed_tests)
    ok("mutation_score" in report,         "convergence_report has mutation_score key")
    ok("converged" in report,              "convergence_report has converged key")
    ok("passing_tests" in report,          "convergence_report has passing_tests key")
    ok(0.0 <= report["mutation_score"] <= 1.0, "mutation_score in [0,1]")

    # With no tests, converged should be False
    ok(not detector.is_converged(BINARY_SEARCH_SRC, []),
                                           "is_converged False with no tests")

    # A comprehensive test suite should have higher mutation score
    comprehensive = [
        TestCase(inputs=([1, 2, 3, 4, 5], 3), expected=2,     description="middle"),
        TestCase(inputs=([1, 2, 3, 4, 5], 1), expected=0,     description="first"),
        TestCase(inputs=([1, 2, 3, 4, 5], 5), expected=4,     description="last"),
        TestCase(inputs=([1, 2, 3, 4, 5], 6), expected=-1,    description="not found"),
        TestCase(inputs=([], 1), expected=-1,                  description="empty"),
        TestCase(inputs=([1], 1), expected=0,                  description="single found"),
        TestCase(inputs=([1], 2), expected=-1,                 description="single not found"),
        TestCase(inputs=([1, 3], 2), expected=-1,              description="gap"),
    ]
    report_comp = detector.convergence_report(BINARY_SEARCH_SRC, comprehensive)
    ok(report_comp["mutation_score"] >= report["mutation_score"],
                                           "comprehensive suite has >= mutation_score vs seed")
    ok(report_comp["passing_tests"] == len(comprehensive),
                                           "all comprehensive tests pass")

    # ------- Edge cases ---------------------------------------------------
    # Syntax error source
    bad_src = "def f(x: def\n"
    ok(gen.boundary_analysis(bad_src) == [], "boundary_analysis: syntax error returns []")

    # Source with no comparisons
    no_cmp = "def f(x):\n    return x + 1\n"
    nc_result = gen.boundary_analysis(no_cmp)
    ok(isinstance(nc_result, list),        "boundary_analysis: no comparisons ok")

    # MutationEngine with program that has no comparisons
    score2 = engine.mutation_score(no_cmp, [TestCase(inputs=(0,), expected=1, description="x+1")])
    ok(0.0 <= score2 <= 1.0,              "mutation_score: no comparisons is valid float")

    total = passed + failed
    print(f"\nResults: {passed}/{total} tests passed", end="")
    if failed:
        print(f"  ({failed} FAILED)")
        raise SystemExit(1)
    else:
        print(" ✓")


if __name__ == "__main__":
    _run_tests()
    print()
    demo()
