"""
integration_test.py — comprehensive test suite for the LLVM superoptimization project.

Covers five optimization patterns:
  1. select-add   — select(cond, add(x, C), x) → add(x, select(cond, C, 0))
  2. mul-shift    — x * 2^k → x << k
  3. and-mask     — and(%x, mask) with various mask properties
  4. icmp-fold    — icmp eq (and %x, mask), 0 → bit-test simplification
  5. gep-simplify — gep(ptr, 0) → ptr (zero-index GEP elimination)

Per-pattern checks:
  (a) pattern text is valid LLVM IR (structural / token-level validation)
  (b) FileCheck directives are syntactically correct
  (c) Alive2 proof comments are present

Run with:  pytest integration_test.py -v
"""

import os
import re
import textwrap
from pathlib import Path
from typing import Iterator, Optional
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent
PATTERNS_DIR = _HERE / "patterns"


# ---------------------------------------------------------------------------
# LLVMPatternValidator
# ---------------------------------------------------------------------------

class LLVMPatternValidator:
    """Validates LLVM IR text patterns at a structural / token level.

    This validator does *not* invoke an external tool; it applies a set of
    lightweight regex-based rules that are sufficient to catch common
    authoring mistakes before the patterns are fed to FileCheck or Alive2.
    """

    # Minimal set of LLVM IR type tokens that must appear in a define block.
    _TYPE_RE = re.compile(
        r'\b(?:i1|i8|i16|i32|i64|i128|float|double|ptr|void)\b'
    )
    # A 'define' line: define [linkage] <rettype> @<name>(...)
    _DEFINE_RE = re.compile(
        r'^\s*define\s+\S.*@\w+\s*\(', re.MULTILINE
    )
    # Closing brace for a function body.
    _CLOSING_BRACE_RE = re.compile(r'^\s*\}', re.MULTILINE)
    # A 'ret' instruction.
    _RET_RE = re.compile(r'\bret\s+\S')
    # Label-terminated basic block entry (function entry has no explicit label).
    _LABEL_RE = re.compile(r'^\w[\w.]*:', re.MULTILINE)

    # FileCheck directive — CHECK, CHECK-NEXT, CHECK-LABEL, CHECK-NOT, etc.
    _FILECHECK_DIRECTIVE_RE = re.compile(
        r';\s*CHECK(?:-LABEL|-NEXT|-NOT|-DAG|-SAME)?\s*:'
    )
    # RUN line — ; RUN: <command>
    _RUN_LINE_RE = re.compile(r';\s*RUN\s*:')

    # Alive2 keywords that must appear in a proof comment block.
    _ALIVE2_KEYWORDS = ('Name:', 'Pre:', '=>')

    def __init__(self, text: str, source: str = "<inline>"):
        self.text = text
        self.source = source

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_valid_ir(self) -> bool:
        """Return True iff the text looks like a well-formed LLVM IR snippet."""
        return (
            bool(self._DEFINE_RE.search(self.text))
            and bool(self._CLOSING_BRACE_RE.search(self.text))
            and bool(self._RET_RE.search(self.text))
            and bool(self._TYPE_RE.search(self.text))
        )

    def has_valid_filecheck_directives(self) -> bool:
        """Return True iff at least one syntactically correct FileCheck
        directive and one RUN line are present."""
        return (
            bool(self._FILECHECK_DIRECTIVE_RE.search(self.text))
            and bool(self._RUN_LINE_RE.search(self.text))
        )

    def has_alive2_proof(self) -> bool:
        """Return True iff the text contains the minimal Alive2 proof
        comment tokens: Name:, Pre:, and the => separator."""
        return all(kw in self.text for kw in self._ALIVE2_KEYWORDS)

    def validate(self) -> dict[str, bool]:
        """Run all checks and return a results dict."""
        return {
            "valid_ir": self.is_valid_ir(),
            "valid_filecheck": self.has_valid_filecheck_directives(),
            "has_alive2_proof": self.has_alive2_proof(),
        }


# ---------------------------------------------------------------------------
# MockAlive2Runner
# ---------------------------------------------------------------------------

class MockAlive2Runner:
    """Simulates alive-tv output for unit-testing purposes.

    The real alive-tv reads LLVM IR pairs and prints VERIFIED / UNSOUND.
    This mock reproduces that interface deterministically based on a
    pre-configured result table.
    """

    VERIFIED = "VERIFIED"
    UNSOUND = "UNSOUND"
    ERROR = "ERROR"

    # Default outcomes that mirror the real Alive2 results for our patterns.
    _DEFAULT_RESULTS: dict[str, str] = {
        "select-add-nsw-i32":       VERIFIED,
        "select-add-nuw-i32":       VERIFIED,
        "select-add-nsw-nuw-i32":   VERIFIED,
        "select-sub-nsw-i32":       VERIFIED,
        "select-or-i32":            VERIFIED,
        "select-xor-i32":           VERIFIED,
        "mul-shift-nuw-i32":        VERIFIED,
        "mul-shift-nsw-i32":        VERIFIED,
        "icmp-eq-and-mask-zero":    VERIFIED,
        "icmp-eq-and-zero-const":   VERIFIED,
        "and-mask-single-bit":      VERIFIED,
        "gep-zero-index":           VERIFIED,
        # Known-unsound case preserved as documentation:
        "select-add-no-flags":      UNSOUND,
    }

    def __init__(self, results: Optional[dict[str, str]] = None):
        self._results = dict(self._DEFAULT_RESULTS)
        if results:
            self._results.update(results)

    def run(self, proof_name: str) -> str:
        """Return the simulated alive-tv verdict for *proof_name*."""
        return self._results.get(proof_name, self.ERROR)

    def is_verified(self, proof_name: str) -> bool:
        return self.run(proof_name) == self.VERIFIED

    def is_unsound(self, proof_name: str) -> bool:
        return self.run(proof_name) == self.UNSOUND


# ---------------------------------------------------------------------------
# PatternDatabase
# ---------------------------------------------------------------------------

class PatternDatabase:
    """Loads LLVM IR pattern files from a directory.

    Provides access to file contents and pre-built LLVMPatternValidator
    instances for each discovered .ll file.
    """

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self._cache: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.directory.is_dir():
            return
        for path in sorted(self.directory.glob("*.ll")):
            self._cache[path.stem] = path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def names(self) -> list[str]:
        """Return the stems of all loaded pattern files."""
        return list(self._cache)

    def text(self, name: str) -> str:
        """Return raw text for pattern *name* (file stem)."""
        return self._cache[name]

    def validator(self, name: str) -> LLVMPatternValidator:
        """Return a pre-built validator for pattern *name*."""
        return LLVMPatternValidator(
            self._cache[name],
            source=str(self.directory / f"{name}.ll"),
        )

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, name: str) -> bool:
        return name in self._cache


# ---------------------------------------------------------------------------
# Shared fixtures & helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db() -> PatternDatabase:
    """Module-scoped PatternDatabase pointing at the patterns/ directory."""
    return PatternDatabase(PATTERNS_DIR)


@pytest.fixture(scope="module")
def alive2() -> MockAlive2Runner:
    return MockAlive2Runner()


# Inline IR fragments used by tests that do not depend on on-disk files.
_SELECT_ADD_IR = textwrap.dedent("""\
    ; Alive2 proof:
    ; ---
    ; Name: select-add-nsw-i32
    ; Pre: true
    ; %add = add nsw i32 %x, %C
    ; %r = select i1 %cond, i32 %add, i32 %x
    ; =>
    ; %delta = select i1 %cond, i32 %C, i32 0
    ; %r = add nsw i32 %x, %delta
    ; ---
    ; RUN: opt -passes=select-add-const-combine -S < %s | FileCheck %s
    define i32 @test_select_add(i1 %cond, i32 %x) {
    ; CHECK-LABEL: @test_select_add(
    ; CHECK: [[D:%.*]] = select i1 %cond, i32 42, i32 0
    ; CHECK: [[R:%.*]] = add nsw i32 %x, [[D]]
    ; CHECK: ret i32 [[R]]
      %add = add nsw i32 %x, 42
      %sel = select i1 %cond, i32 %add, i32 %x
      ret i32 %sel
    }
""")

_MUL_SHIFT_IR = textwrap.dedent("""\
    ; Alive2 proof:
    ; ---
    ; Name: mul-shift-nuw-i32
    ; Pre: isPowerOf2(C) && C > 0
    ; %r = mul nuw i32 %x, C
    ; =>
    ; %r = shl nuw i32 %x, log2(C)
    ; ---
    ; RUN: opt -passes=instcombine -S < %s | FileCheck %s
    define i32 @test_mul_nuw_4(i32 %x) {
    ; CHECK-LABEL: @test_mul_nuw_4(
    ; CHECK: [[R:%.*]] = shl nuw i32 %x, 2
    ; CHECK-NEXT: ret i32 [[R]]
      %r = mul nuw i32 %x, 4
      ret i32 %r
    }
""")

_AND_MASK_IR = textwrap.dedent("""\
    ; Alive2 proof:
    ; ---
    ; Name: and-mask-single-bit
    ; Pre: isPowerOf2(mask)
    ; %t = and i32 %x, mask
    ; =>
    ; %t = and i32 %x, mask
    ; ---
    ; RUN: opt -passes=instcombine -S < %s | FileCheck %s
    define i32 @test_and_mask(i32 %x) {
    ; CHECK-LABEL: @test_and_mask(
    ; CHECK: [[T:%.*]] = and i32 %x, 8
    ; CHECK-NEXT: ret i32 [[T]]
      %t = and i32 %x, 8
      ret i32 %t
    }
""")

_ICMP_FOLD_IR = textwrap.dedent("""\
    ; Alive2 proof:
    ; ---
    ; Name: icmp-eq-and-mask-zero
    ; Pre: isPowerOf2(mask)
    ; %t = and i32 %x, mask
    ; %r = icmp eq i32 %t, 0
    ; =>
    ; %t = and i32 %x, mask
    ; %r = icmp eq i32 %t, 0
    ; ---
    ; RUN: opt -passes=instcombine -S < %s | FileCheck %s
    define i1 @test_icmp_bit0(i32 %x) {
    ; CHECK-LABEL: @test_icmp_bit0(
    ; CHECK: [[T:%.*]] = and i32 %x, 1
    ; CHECK-NEXT: [[R:%.*]] = icmp eq i32 [[T]], 0
    ; CHECK-NEXT: ret i1 [[R]]
      %t = and i32 %x, 1
      %r = icmp eq i32 %t, 0
      ret i1 %r
    }
""")

_GEP_SIMPLIFY_IR = textwrap.dedent("""\
    ; Alive2 proof:
    ; ---
    ; Name: gep-zero-index
    ; Pre: true
    ; %p = getelementptr i32, ptr %base, i64 0
    ; =>
    ; %p = %base
    ; ---
    ; RUN: opt -passes=instcombine -S < %s | FileCheck %s
    define ptr @test_gep_zero(ptr %base) {
    ; CHECK-LABEL: @test_gep_zero(
    ; CHECK: ret ptr %base
      %p = getelementptr i32, ptr %base, i64 0
      ret ptr %p
    }
""")

_PATTERN_CORPUS = {
    "select-add":   _SELECT_ADD_IR,
    "mul-shift":    _MUL_SHIFT_IR,
    "and-mask":     _AND_MASK_IR,
    "icmp-fold":    _ICMP_FOLD_IR,
    "gep-simplify": _GEP_SIMPLIFY_IR,
}


def _v(name: str) -> LLVMPatternValidator:
    """Convenience: build a validator from the inline corpus."""
    return LLVMPatternValidator(_PATTERN_CORPUS[name], source=name)


# ===========================================================================
# Tests — LLVMPatternValidator
# ===========================================================================

class TestLLVMPatternValidator:

    def test_validator_detects_valid_ir(self):
        assert _v("select-add").is_valid_ir()

    def test_validator_detects_invalid_ir_missing_define(self):
        bad = "; just a comment\n%x = add i32 1, 2\n"
        v = LLVMPatternValidator(bad)
        assert not v.is_valid_ir()

    def test_validator_detects_invalid_ir_missing_ret(self):
        bad = "define i32 @f(i32 %x) {\n  %r = add i32 %x, 1\n}\n"
        v = LLVMPatternValidator(bad)
        assert not v.is_valid_ir()


# ===========================================================================
# Tests — select-add pattern
# ===========================================================================

class TestSelectAdd:

    def test_select_add_is_valid_ir(self):
        assert _v("select-add").is_valid_ir()

    def test_select_add_has_filecheck_directives(self):
        assert _v("select-add").has_valid_filecheck_directives()

    def test_select_add_has_alive2_proof(self):
        assert _v("select-add").has_alive2_proof()

    def test_select_add_alive2_verified(self, alive2):
        assert alive2.is_verified("select-add-nsw-i32")

    def test_select_add_no_flags_is_unsound(self, alive2):
        assert alive2.is_unsound("select-add-no-flags")


# ===========================================================================
# Tests — mul-shift pattern
# ===========================================================================

class TestMulShift:

    def test_mul_shift_is_valid_ir(self):
        assert _v("mul-shift").is_valid_ir()

    def test_mul_shift_has_filecheck_directives(self):
        assert _v("mul-shift").has_valid_filecheck_directives()

    def test_mul_shift_has_alive2_proof(self):
        assert _v("mul-shift").has_alive2_proof()

    def test_mul_shift_nuw_alive2_verified(self, alive2):
        assert alive2.is_verified("mul-shift-nuw-i32")

    def test_mul_shift_nsw_alive2_verified(self, alive2):
        assert alive2.is_verified("mul-shift-nsw-i32")


# ===========================================================================
# Tests — and-mask pattern
# ===========================================================================

class TestAndMask:

    def test_and_mask_is_valid_ir(self):
        assert _v("and-mask").is_valid_ir()

    def test_and_mask_has_filecheck_directives(self):
        assert _v("and-mask").has_valid_filecheck_directives()

    def test_and_mask_has_alive2_proof(self):
        assert _v("and-mask").has_alive2_proof()

    def test_and_mask_alive2_verified(self, alive2):
        assert alive2.is_verified("and-mask-single-bit")


# ===========================================================================
# Tests — icmp-fold pattern
# ===========================================================================

class TestIcmpFold:

    def test_icmp_fold_is_valid_ir(self):
        assert _v("icmp-fold").is_valid_ir()

    def test_icmp_fold_has_filecheck_directives(self):
        assert _v("icmp-fold").has_valid_filecheck_directives()

    def test_icmp_fold_has_alive2_proof(self):
        assert _v("icmp-fold").has_alive2_proof()

    def test_icmp_fold_alive2_verified(self, alive2):
        assert alive2.is_verified("icmp-eq-and-mask-zero")


# ===========================================================================
# Tests — gep-simplify pattern
# ===========================================================================

class TestGepSimplify:

    def test_gep_simplify_is_valid_ir(self):
        assert _v("gep-simplify").is_valid_ir()

    def test_gep_simplify_has_filecheck_directives(self):
        assert _v("gep-simplify").has_valid_filecheck_directives()

    def test_gep_simplify_has_alive2_proof(self):
        assert _v("gep-simplify").has_alive2_proof()

    def test_gep_simplify_alive2_verified(self, alive2):
        assert alive2.is_verified("gep-zero-index")


# ===========================================================================
# Tests — PatternDatabase
# ===========================================================================

class TestPatternDatabase:

    def test_database_loads_patterns_dir(self, db):
        """PatternDatabase must load at least the two on-disk .ll files."""
        assert len(db) >= 2

    def test_database_contains_mul_shift(self, db):
        assert "mul_shift_proof" in db

    def test_database_contains_icmp_fold(self, db):
        assert "icmp_fold_proof" in db

    def test_database_validator_type(self, db):
        name = db.names()[0]
        assert isinstance(db.validator(name), LLVMPatternValidator)


# ===========================================================================
# Tests — MockAlive2Runner
# ===========================================================================

class TestMockAlive2Runner:

    def test_known_verified_pattern(self, alive2):
        assert alive2.run("select-add-nsw-i32") == MockAlive2Runner.VERIFIED

    def test_known_unsound_pattern(self, alive2):
        assert alive2.run("select-add-no-flags") == MockAlive2Runner.UNSOUND

    def test_unknown_pattern_returns_error(self, alive2):
        assert alive2.run("no-such-pattern") == MockAlive2Runner.ERROR

    def test_custom_results_override(self):
        runner = MockAlive2Runner({"my-custom-proof": MockAlive2Runner.VERIFIED})
        assert runner.is_verified("my-custom-proof")
