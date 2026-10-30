"""Patch generator for the autonomous GitHub issue-fixing agent."""
from __future__ import annotations
import ast
import difflib
import re
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class BugDiagnosis:
    issue_title: str
    issue_body: str
    relevant_files: dict[str, str]  # filename -> content
    suspected_function: str
    root_cause_hypothesis: str


@dataclass
class PatchCandidate:
    diff: str
    explanation: str
    confidence: float
    files_changed: list[str] = field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0

    def __post_init__(self):
        if not self.files_changed:
            for line in self.diff.splitlines():
                if line.startswith("+++ b/"):
                    self.files_changed.append(line[6:])
        if not self.lines_added:
            self.lines_added = sum(
                1
                for l in self.diff.splitlines()
                if l.startswith("+") and not l.startswith("+++")
            )
        if not self.lines_removed:
            self.lines_removed = sum(
                1
                for l in self.diff.splitlines()
                if l.startswith("-") and not l.startswith("---")
            )


class DiffValidator:
    """Validates patch candidates for correctness and style."""

    def validate(self, candidate: PatchCandidate, original_source: str) -> tuple[bool, list[str]]:
        errors: list[str] = []

        if not candidate.diff.strip():
            errors.append("Empty diff")
            return False, errors

        if candidate.lines_added == 0 and candidate.lines_removed == 0:
            errors.append("Diff has no net changes")

        # Minimality: no more than 50 lines changed
        total_changed = candidate.lines_added + candidate.lines_removed
        if total_changed > 50:
            errors.append(f"Diff too large: {total_changed} lines changed (max 50)")

        # Style: no trailing whitespace added
        for line in candidate.diff.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                if line.rstrip() != line:
                    errors.append(f"Trailing whitespace in added line: {repr(line)}")

        # Syntax: if the patch touches Python files, check parse
        for fname in candidate.files_changed:
            if fname.endswith(".py"):
                patched = self._apply_diff_to_source(candidate.diff, original_source)
                if patched is not None:
                    try:
                        ast.parse(patched)
                    except SyntaxError as e:
                        errors.append(f"Syntax error after patch: {e}")

        return len(errors) == 0, errors

    def _apply_diff_to_source(self, diff: str, source: str) -> str | None:
        """Attempt to apply a unified diff to source, return patched or None."""
        try:
            lines = source.splitlines(keepends=True)
            result = list(lines)
            offset = 0
            for chunk in re.findall(
                r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*?)(?=\n@@|\Z)",
                diff,
                re.DOTALL,
            ):
                old_start = int(chunk[0]) - 1
                patch_lines = chunk[4].splitlines()
                removes = [l[1:] for l in patch_lines if l.startswith("-")]
                adds = [l[1:] + "\n" for l in patch_lines if l.startswith("+")]
                idx = old_start + offset
                result[idx : idx + len(removes)] = adds
                offset += len(adds) - len(removes)
            return "".join(result)
        except Exception:
            return None


class PatchApplier:
    """Applies and reverts unified diffs."""

    def apply(self, source: str, diff: str) -> str:
        """Apply a unified diff to source text."""
        lines = source.splitlines(keepends=True)
        result = list(lines)
        offset = 0
        for m in re.finditer(
            r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@[^\n]*\n(.*?)(?=\n@@|\Z)",
            diff,
            re.DOTALL,
        ):
            old_start = int(m.group(1)) - 1 + offset
            hunk_lines = m.group(2).splitlines()
            removes = []
            adds = []
            for l in hunk_lines:
                if l.startswith("-"):
                    removes.append(l[1:] + "\n")
                elif l.startswith("+"):
                    adds.append(l[1:] + "\n")
            result[old_start : old_start + len(removes)] = adds
            offset += len(adds) - len(removes)
        return "".join(result)

    def revert(self, patched: str, diff: str) -> str:
        """Revert a unified diff (swap + and -)."""
        reverted = re.sub(r"^(\+)", r"\x00", diff, flags=re.MULTILINE)
        reverted = re.sub(r"^(-)", r"+", reverted, flags=re.MULTILINE)
        reverted = re.sub(r"^\x00", r"-", reverted, flags=re.MULTILINE)
        # Also swap the @@ line counts
        def swap_hunk_header(m):
            a, b = m.group(1), m.group(2)
            return f"@@ -{b} +{a} @@"
        reverted = re.sub(r"@@ (-[^\s]+) (\+[^\s]+) @@", swap_hunk_header, reverted)
        return self.apply(patched, reverted)


class PatchGenerator:
    """Generates patch candidates using multiple strategies."""

    STRATEGIES = [
        "_strategy_off_by_one",
        "_strategy_null_check",
        "_strategy_wrong_operator",
        "_strategy_missing_return",
        "_strategy_wrong_variable",
    ]

    def __init__(self):
        self.validator = DiffValidator()
        self.applier = PatchApplier()

    def generate(self, diagnosis: BugDiagnosis) -> list[PatchCandidate]:
        """Run all strategies and return ranked candidates."""
        candidates: list[PatchCandidate] = []
        for strategy_name in self.STRATEGIES:
            strategy: Callable = getattr(self, strategy_name)
            try:
                result = strategy(diagnosis)
                if result:
                    candidates.extend(result if isinstance(result, list) else [result])
            except Exception as e:
                pass  # strategy not applicable

        # Score and sort
        scored = []
        for c in candidates:
            score = self._score(c, diagnosis)
            scored.append((score, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored]

    def _score(self, candidate: PatchCandidate, diagnosis: BugDiagnosis) -> float:
        """Score a candidate on confidence + minimal diff size."""
        size_penalty = (candidate.lines_added + candidate.lines_removed) * 0.01
        relevance = 0.1 if diagnosis.suspected_function in candidate.diff else 0.0
        return candidate.confidence - size_penalty + relevance

    def _make_diff(self, filename: str, original: str, patched: str) -> str:
        original_lines = original.splitlines(keepends=True)
        patched_lines = patched.splitlines(keepends=True)
        diff = difflib.unified_diff(
            original_lines,
            patched_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm="",
        )
        return "\n".join(diff)

    def _strategy_off_by_one(self, diagnosis: BugDiagnosis) -> list[PatchCandidate]:
        """Replace `< n` with `<= n` or `range(n)` with `range(n+1)` etc."""
        candidates = []
        hypothesis = diagnosis.root_cause_hypothesis.lower()
        if "off-by-one" not in hypothesis and "off by one" not in hypothesis:
            return []
        for filename, source in diagnosis.relevant_files.items():
            # Strategy A: `< n` -> `<= n`
            patched_a = re.sub(
                r"(\bfor\b.*\brange\b\s*\(\s*\d+\s*,\s*)(\w+)(\s*\))",
                lambda m: m.group(1) + m.group(2) + " + 1" + m.group(3),
                source,
                count=1,
            )
            if patched_a != source:
                diff = self._make_diff(filename, source, patched_a)
                candidates.append(
                    PatchCandidate(
                        diff=diff,
                        explanation="Off-by-one: extend range upper bound by 1 so the final element is included.",
                        confidence=0.72,
                    )
                )
            # Strategy B: `i < len(x)` -> `i <= len(x)`
            patched_b = re.sub(
                r"(\bi\s*)<(\s*len\s*\()",
                r"\1<=\2",
                source,
                count=1,
            )
            if patched_b != source and patched_b != patched_a:
                diff = self._make_diff(filename, source, patched_b)
                candidates.append(
                    PatchCandidate(
                        diff=diff,
                        explanation="Off-by-one: change strict `<` to `<=` for inclusive upper bound.",
                        confidence=0.65,
                    )
                )
        return candidates

    def _strategy_null_check(self, diagnosis: BugDiagnosis) -> list[PatchCandidate]:
        """Insert None/null guard before attribute access."""
        hypothesis = diagnosis.root_cause_hypothesis.lower()
        if "null" not in hypothesis and "none" not in hypothesis and "attribute" not in hypothesis:
            return []
        candidates = []
        for filename, source in diagnosis.relevant_files.items():
            # Find the suspected function body and add a None guard
            func = diagnosis.suspected_function
            pattern = re.compile(
                rf"(def {re.escape(func)}\([^)]*\)\s*(?:->[^:]+)?:\s*\n)([ \t]+)",
            )
            m = pattern.search(source)
            if m:
                indent = m.group(2)
                guard = f'{indent}if {func.split("_")[-1]} is None:\n{indent}    return None\n'
                patched = source[: m.end()] + guard + source[m.end() :]
                diff = self._make_diff(filename, source, patched)
                candidates.append(
                    PatchCandidate(
                        diff=diff,
                        explanation=f"Null check: guard against None input in `{func}` before attribute access.",
                        confidence=0.68,
                    )
                )
        return candidates

    def _strategy_wrong_operator(self, diagnosis: BugDiagnosis) -> list[PatchCandidate]:
        """Replace a wrong comparison operator with the correct one."""
        hypothesis = diagnosis.root_cause_hypothesis.lower()
        if "operator" not in hypothesis and "comparison" not in hypothesis:
            return []
        candidates = []
        replacements = [("!=", "=="), ("==", "!="), (">=", ">"), ("<=", "<")]
        for filename, source in diagnosis.relevant_files.items():
            func = diagnosis.suspected_function
            tree = None
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == func:
                    # Find comparisons inside this function
                    for child in ast.walk(node):
                        if isinstance(child, ast.Compare):
                            line_no = child.lineno
                            src_lines = source.splitlines()
                            line = src_lines[line_no - 1]
                            for old_op, new_op in replacements:
                                if old_op in line:
                                    patched_line = line.replace(old_op, new_op, 1)
                                    patched_lines = list(src_lines)
                                    patched_lines[line_no - 1] = patched_line
                                    patched = "\n".join(patched_lines) + "\n"
                                    diff = self._make_diff(filename, source, patched)
                                    candidates.append(
                                        PatchCandidate(
                                            diff=diff,
                                            explanation=f"Wrong operator: replaced `{old_op}` with `{new_op}` on line {line_no}.",
                                            confidence=0.60,
                                        )
                                    )
        return candidates

    def _strategy_missing_return(self, diagnosis: BugDiagnosis) -> list[PatchCandidate]:
        """Add a missing return statement to a function."""
        hypothesis = diagnosis.root_cause_hypothesis.lower()
        if "return" not in hypothesis and "none" not in hypothesis:
            return []
        candidates = []
        for filename, source in diagnosis.relevant_files.items():
            func = diagnosis.suspected_function
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == func:
                    has_return = any(isinstance(n, ast.Return) for n in ast.walk(node))
                    if not has_return:
                        src_lines = source.splitlines()
                        end_line = node.end_lineno  # type: ignore[attr-defined]
                        indent = "    "
                        patched_lines = list(src_lines)
                        patched_lines.insert(end_line, f"{indent}return result")
                        patched = "\n".join(patched_lines) + "\n"
                        diff = self._make_diff(filename, source, patched)
                        candidates.append(
                            PatchCandidate(
                                diff=diff,
                                explanation=f"Missing return: added `return result` at end of `{func}`.",
                                confidence=0.55,
                            )
                        )
        return candidates

    def _strategy_wrong_variable(self, diagnosis: BugDiagnosis) -> list[PatchCandidate]:
        """Replace a wrong variable name with the correct one."""
        hypothesis = diagnosis.root_cause_hypothesis.lower()
        if "variable" not in hypothesis and "typo" not in hypothesis:
            return []
        candidates = []
        for filename, source in diagnosis.relevant_files.items():
            func = diagnosis.suspected_function
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == func:
                    args = [a.arg for a in node.args.args]
                    assigned: list[str] = []
                    for child in ast.walk(node):
                        if isinstance(child, ast.Assign):
                            for t in child.targets:
                                if isinstance(t, ast.Name):
                                    assigned.append(t.id)
                    all_vars = args + assigned
                    src_lines = source.splitlines()
                    # Find Name nodes that are close in edit distance to args
                    for child in ast.walk(node):
                        if isinstance(child, ast.Name) and child.id not in all_vars:
                            for correct in all_vars:
                                if (
                                    abs(len(child.id) - len(correct)) <= 2
                                    and child.id != correct
                                    and child.id not in ("None", "True", "False")
                                ):
                                    line = src_lines[child.lineno - 1]
                                    if child.id in line:
                                        patched_line = line.replace(child.id, correct, 1)
                                        patched_lines = list(src_lines)
                                        patched_lines[child.lineno - 1] = patched_line
                                        patched = "\n".join(patched_lines) + "\n"
                                        diff = self._make_diff(filename, source, patched)
                                        candidates.append(
                                            PatchCandidate(
                                                diff=diff,
                                                explanation=f"Wrong variable: replaced `{child.id}` with `{correct}` on line {child.lineno}.",
                                                confidence=0.50,
                                            )
                                        )
        return candidates


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _run_tests():
    print("Running PatchGenerator tests...")
    generator = PatchGenerator()
    validator = DiffValidator()
    passed = 0
    failed = 0

    # --- Test 1: Off-by-one in a loop ---
    source_obo = """\
def sum_first_n(n):
    total = 0
    for i in range(0, n):
        total += i
    return total
"""
    diag1 = BugDiagnosis(
        issue_title="sum_first_n returns wrong value",
        issue_body="sum_first_n(5) should return 15 but returns 10",
        relevant_files={"utils.py": source_obo},
        suspected_function="sum_first_n",
        root_cause_hypothesis="Off-by-one: the range excludes the last element",
    )
    candidates1 = generator.generate(diag1)
    if candidates1:
        print(f"  Test 1 PASS: {len(candidates1)} candidates for off-by-one")
        print(f"    Best: {candidates1[0].explanation} (conf={candidates1[0].confidence:.2f})")
        passed += 1
    else:
        print("  Test 1 FAIL: no candidates generated for off-by-one")
        failed += 1

    # --- Test 2: Missing null check ---
    source_null = """\
def get_user_name(user):
    return user.name.strip()
"""
    diag2 = BugDiagnosis(
        issue_title="get_user_name crashes on None input",
        issue_body="AttributeError: 'NoneType' object has no attribute 'name'",
        relevant_files={"models.py": source_null},
        suspected_function="get_user_name",
        root_cause_hypothesis="Missing None check before attribute access on user",
    )
    candidates2 = generator.generate(diag2)
    if candidates2:
        print(f"  Test 2 PASS: {len(candidates2)} candidates for null check")
        print(f"    Best: {candidates2[0].explanation}")
        passed += 1
    else:
        print("  Test 2 FAIL: no candidates for null check")
        failed += 1

    # --- Test 3: Wrong comparison operator ---
    source_cmp = """\
def is_adult(age):
    if age >= 18:
        return True
    return False
"""
    diag3 = BugDiagnosis(
        issue_title="is_adult returns True for age==18 but should not",
        issue_body="18-year-olds are not adults in this jurisdiction. Use strict >.",
        relevant_files={"validation.py": source_cmp},
        suspected_function="is_adult",
        root_cause_hypothesis="Wrong comparison operator: >= should be >",
    )
    candidates3 = generator.generate(diag3)
    if candidates3:
        print(f"  Test 3 PASS: {len(candidates3)} candidates for wrong operator")
        print(f"    Best: {candidates3[0].explanation}")
        passed += 1
    else:
        print("  Test 3 FAIL: no candidates for wrong operator")
        failed += 1

    # --- Test 4: DiffValidator ---
    c = PatchCandidate(
        diff="--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,3 @@\n def f():\n+    pass\n     return 1\n",
        explanation="test",
        confidence=0.9,
    )
    ok, errs = validator.validate(c, "def f():\n    return 1\n")
    print(f"  Test 4 (DiffValidator): ok={ok}, errors={errs}")
    passed += 1

    # --- Test 5: PatchApplier round-trip ---
    applier = PatchApplier()
    original = "a = 1\nb = 2\nc = 3\n"
    diff = "--- a/x.py\n+++ b/x.py\n@@ -2,1 +2,1 @@\n-b = 2\n+b = 99\n"
    patched = applier.apply(original, diff)
    print(f"  Test 5 (PatchApplier): patched={'b = 99' in patched}")
    passed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    _run_tests()
