"""
theorem_runner.py
Parses a Lean 4 file to extract theorem names and whether they use `sorry`.

Usage:
    python theorem_runner.py path/to/file.lean
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TheoremEntry:
    name: str
    uses_sorry: bool
    line: int


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class TheoremParser:
    """Parse a .lean file and extract theorem declarations."""

    # Matches lines like:
    #   theorem foo ... :=
    #   theorem foo ... := by
    _THEOREM_RE = re.compile(
        r"^(?:theorem|lemma)\s+([A-Za-z_][A-Za-z0-9_']*)", re.MULTILINE
    )

    def parse(self, path: str | Path) -> List[Dict]:
        """
        Parse the given .lean file.

        Returns a list of dicts with keys:
            name       – theorem identifier
            uses_sorry – True if the theorem body contains `sorry`
            line       – 1-based line number of the declaration
        """
        path = Path(path)
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()

        results: List[Dict] = []

        for m in self._THEOREM_RE.finditer(text):
            name = m.group(1)
            # Compute 1-based line number from the character offset
            line_no = text[: m.start()].count("\n") + 1

            # Determine the extent of this theorem's body:
            # collect source from this declaration up to the next top-level
            # declaration or end of file so we can check for sorry.
            body_lines = self._extract_body_lines(lines, line_no - 1)
            body = "\n".join(body_lines)
            uses_sorry = bool(re.search(r"\bsorry\b", body))

            results.append({"name": name, "uses_sorry": uses_sorry, "line": line_no})

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    _TOP_LEVEL_RE = re.compile(
        r"^(?:theorem|lemma|def|noncomputable def|abbrev|instance|structure|"
        r"class|inductive|section|namespace|end|#check|#eval|import)\b"
    )

    def _extract_body_lines(self, lines: List[str], start_idx: int) -> List[str]:
        """
        Return the lines belonging to the theorem starting at `start_idx`.
        We collect lines until we find the next top-level keyword (at column 0)
        that is NOT part of this declaration, or EOF.
        """
        body = [lines[start_idx]]
        for idx in range(start_idx + 1, len(lines)):
            line = lines[idx]
            if line and not line[0].isspace() and self._TOP_LEVEL_RE.match(line):
                break
            body.append(line)
        return body


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

class TheoremReport:
    """Generate a human-readable summary from a list of theorem dicts."""

    def __init__(self, entries: List[Dict]):
        self.entries = entries

    def summary(self) -> str:
        total = len(self.entries)
        proved = sum(1 for e in self.entries if not e["uses_sorry"])
        sorry_count = total - proved

        lines = [
            "=" * 60,
            f"  Theorem Report",
            "=" * 60,
            f"  Total theorems  : {total}",
            f"  Fully proved    : {proved}",
            f"  Uses sorry      : {sorry_count}",
            "-" * 60,
        ]
        for e in self.entries:
            status = "SORRY" if e["uses_sorry"] else "OK   "
            lines.append(f"  [{status}] line {e['line']:>4}  {e['name']}")
        lines.append("=" * 60)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python theorem_runner.py <file.lean>")
        sys.exit(1)
    path = sys.argv[1]
    parser = TheoremParser()
    entries = parser.parse(path)
    report = TheoremReport(entries)
    print(report.summary())


# ---------------------------------------------------------------------------
# Tests (15 test_* functions) — also runnable via pytest
# ---------------------------------------------------------------------------

import tempfile
import os


def _write_temp_lean(content: str) -> str:
    """Write *content* to a temporary .lean file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".lean")
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path


# --- TheoremParser tests ---

def test_parse_empty_file():
    path = _write_temp_lean("")
    entries = TheoremParser().parse(path)
    assert entries == []


def test_parse_single_theorem_no_sorry():
    path = _write_temp_lean("theorem foo : 1 + 1 = 2 := by norm_num\n")
    entries = TheoremParser().parse(path)
    assert len(entries) == 1
    assert entries[0]["name"] == "foo"
    assert entries[0]["uses_sorry"] is False
    assert entries[0]["line"] == 1


def test_parse_single_theorem_with_sorry():
    path = _write_temp_lean("theorem bar : True := by\n  sorry\n")
    entries = TheoremParser().parse(path)
    assert len(entries) == 1
    assert entries[0]["name"] == "bar"
    assert entries[0]["uses_sorry"] is True


def test_parse_multiple_theorems():
    lean = (
        "theorem t1 : True := trivial\n"
        "theorem t2 : False := by sorry\n"
        "theorem t3 : 1 = 1 := rfl\n"
    )
    path = _write_temp_lean(lean)
    entries = TheoremParser().parse(path)
    assert len(entries) == 3


def test_parse_lemma_keyword():
    path = _write_temp_lean("lemma my_lemma : True := trivial\n")
    entries = TheoremParser().parse(path)
    assert len(entries) == 1
    assert entries[0]["name"] == "my_lemma"


def test_parse_sorry_inline():
    path = _write_temp_lean("theorem inline_sorry : 1 = 2 := sorry\n")
    entries = TheoremParser().parse(path)
    assert entries[0]["uses_sorry"] is True


def test_parse_correct_line_numbers():
    lean = "\n\ntheorem late_start : True := trivial\n"
    path = _write_temp_lean(lean)
    entries = TheoremParser().parse(path)
    assert entries[0]["line"] == 3


def test_parse_theorem_with_apostrophe_in_name():
    path = _write_temp_lean("theorem foo' : True := trivial\n")
    entries = TheoremParser().parse(path)
    assert entries[0]["name"] == "foo'"


def test_parse_returns_list_of_dicts():
    path = _write_temp_lean("theorem abc : True := trivial\n")
    entries = TheoremParser().parse(path)
    assert isinstance(entries, list)
    assert isinstance(entries[0], dict)
    assert set(entries[0].keys()) == {"name", "uses_sorry", "line"}


def test_parse_no_sorry_word_in_name():
    # "sorry" appearing in a comment before the theorem must not trigger
    path = _write_temp_lean(
        "-- sorry this is a comment\n"
        "theorem good : True := trivial\n"
    )
    entries = TheoremParser().parse(path)
    # The comment is in the header, not the body of 'good'; body has no sorry.
    assert entries[0]["uses_sorry"] is False


# --- TheoremReport tests ---

def test_report_summary_no_theorems():
    report = TheoremReport([])
    s = report.summary()
    assert "Total theorems  : 0" in s


def test_report_summary_counts():
    entries = [
        {"name": "t1", "uses_sorry": False, "line": 1},
        {"name": "t2", "uses_sorry": True,  "line": 5},
        {"name": "t3", "uses_sorry": False, "line": 9},
    ]
    report = TheoremReport(entries)
    s = report.summary()
    assert "Total theorems  : 3" in s
    assert "Fully proved    : 2" in s
    assert "Uses sorry      : 1" in s


def test_report_summary_is_string():
    report = TheoremReport([])
    assert isinstance(report.summary(), str)


def test_report_summary_contains_theorem_name():
    entries = [{"name": "famous_theorem", "uses_sorry": False, "line": 42}]
    report = TheoremReport(entries)
    assert "famous_theorem" in report.summary()


def test_report_sorry_label_in_output():
    entries = [{"name": "incomplete", "uses_sorry": True, "line": 7}]
    report = TheoremReport(entries)
    assert "SORRY" in report.summary()


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys as _sys
    if len(_sys.argv) >= 2 and not _sys.argv[1].startswith("test"):
        main()
    else:
        # Run all test functions when invoked without a lean file
        import traceback
        tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
        passed = failed = 0
        for t in tests:
            try:
                t()
                print(f"  PASS  {t.__name__}")
                passed += 1
            except Exception as exc:
                print(f"  FAIL  {t.__name__}: {exc}")
                traceback.print_exc()
                failed += 1
        print(f"\n{passed} passed, {failed} failed out of {passed+failed} tests.")
        if failed:
            _sys.exit(1)
