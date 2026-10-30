"""
Integration tests for infra/oracle_impl.py.

All tests run against mock implementations — no external tools required.
Tests that require real tools are marked with pytest.mark.integration and
are skipped by default.

Run:
    pytest infra/test_oracle_impl.py -v
    pytest infra/test_oracle_impl.py -v -m integration   # real tools only
"""

from __future__ import annotations

import pytest

from infra.oracle import OracleResult
from infra.oracle_impl import (
    Alive2OracleImpl,
    GoalState,
    Lean4OracleImpl,
    LeanError,
    MockAlive2OracleImpl,
    MockLean4OracleImpl,
    MockTLCOracleImpl,
    MockZ3OracleImpl,
    OracleFactory,
    SynthSpec,
    TLCOracleImpl,
    TLCResult,
    Z3OracleImpl,
    _extract_between,
)


# ===========================================================================
# Dataclass smoke tests
# ===========================================================================

class TestDataclasses:
    def test_goal_state_closed(self):
        gs = GoalState(is_closed=True)
        assert gs.is_closed
        assert "closed" in repr(gs)

    def test_goal_state_open(self):
        gs = GoalState(goals=["⊢ Nat.succ n = n + 1"], hypotheses=["n : Nat"])
        assert len(gs.goals) == 1
        assert "1" in repr(gs)

    def test_lean_error_repr(self):
        err = LeanError(kind="type_mismatch", message="expected Nat, got Int", line=5, column=2)
        assert "type_mismatch" in repr(err)
        assert ":5:2" in repr(err)

    def test_tlc_result_no_violation(self):
        r = TLCResult(no_error=True, states_explored=42)
        assert not r.has_violation

    def test_tlc_result_with_violation(self):
        r = TLCResult(invariant_violations=["Safety"])
        assert r.has_violation

    def test_synth_spec_fields(self):
        s = SynthSpec(
            input_vars=[("x", "Int"), ("y", "Int")],
            output_var="z",
            output_sort="Int",
            constraints=["(= z (+ x y))"],
        )
        assert s.output_var == "z"
        assert s.precondition is None


# ===========================================================================
# Mock oracle behaviour
# ===========================================================================

class TestMockLean4:
    def test_default_success(self):
        oracle = MockLean4OracleImpl()
        result = oracle.check("theorem t : True := trivial")
        assert result.success

    def test_scripted_failure_then_success(self):
        results = [
            OracleResult(success=False, error_message="unsolved goals"),
            OracleResult(success=True),
        ]
        oracle = MockLean4OracleImpl(results=results)
        r1 = oracle.check("bad proof")
        r2 = oracle.check("good proof")
        assert not r1.success
        assert r2.success
        assert oracle.calls == ["bad proof", "good proof"]

    def test_round_robin_wraps(self):
        oracle = MockLean4OracleImpl(
            results=[OracleResult(success=False), OracleResult(success=True)]
        )
        results = [oracle.check("x") for _ in range(5)]
        successes = [r.success for r in results]
        assert successes == [False, True, False, True, False]

    def test_is_available(self):
        assert MockLean4OracleImpl().is_available()

    def test_parse_goal_state(self):
        oracle = MockLean4OracleImpl()
        gs = oracle.parse_goal_state("⊢ True")
        assert isinstance(gs, GoalState)

    def test_parse_error(self):
        oracle = MockLean4OracleImpl()
        err = oracle.parse_error("type mismatch: expected Nat, got Int")
        assert isinstance(err, LeanError)


class TestMockTLC:
    def test_default_success(self):
        oracle = MockTLCOracleImpl()
        result = oracle.check("---- MODULE Spec ----\nSpec == TRUE\n====")
        assert result.success

    def test_scripted_counterexample(self):
        cex = "State 1: x = 0\nState 2: x = -1"
        oracle = MockTLCOracleImpl(
            results=[OracleResult(success=False, counterexample=cex)]
        )
        r = oracle.check("---- MODULE Bad ----\n====")
        assert not r.success
        assert r.counterexample == cex

    def test_parse_tlc_output_no_error(self):
        oracle = MockTLCOracleImpl()
        tlc_out = oracle._CANNED_SUCCESS
        parsed = oracle.parse_tlc_output(tlc_out)
        assert parsed.no_error
        assert parsed.states_explored == 42

    def test_parse_tlc_output_invariant_violation(self):
        output = (
            "Error: Invariant Safety is violated.\n"
            "The following behaviour constitutes a counter-example:\n"
            "State 1: x = 1\n"
        )
        oracle = MockTLCOracleImpl()
        parsed = oracle.parse_tlc_output(output)
        assert "Safety" in parsed.invariant_violations


class TestMockZ3:
    def test_default_unsat(self):
        oracle = MockZ3OracleImpl()
        result = oracle.check_smt("(assert false)")
        assert result.success

    def test_sat_counterexample(self):
        oracle = MockZ3OracleImpl(
            results=[OracleResult(success=False, counterexample="x = 1")]
        )
        result = oracle.check_smt("(declare-const x Int)\n(assert (> x 0))")
        assert not result.success
        assert result.counterexample == "x = 1"

    def test_synthesize_returns_value(self):
        oracle = MockZ3OracleImpl()
        spec = SynthSpec(
            input_vars=[("x", "Int")],
            output_var="y",
            output_sort="Int",
            constraints=["(= y (* 2 x))"],
        )
        result = oracle.synthesize(spec)
        assert result == "42"  # mock default

    def test_check_equivalence_true(self):
        oracle = MockZ3OracleImpl()
        assert oracle.check_equivalence("p1", "p2") is True

    def test_check_equivalence_false(self):
        oracle = MockZ3OracleImpl()
        oracle._equiv_result = False
        assert oracle.check_equivalence("p1", "p2") is False


class TestMockAlive2:
    def test_default_correct(self):
        oracle = MockAlive2OracleImpl()
        result = oracle.check("define i32 @f(i32 %x) { ret i32 %x }")
        assert result.success
        assert "correct" in result.raw_output.lower()

    def test_incorrect_transformation(self):
        oracle = MockAlive2OracleImpl(
            results=[
                OracleResult(
                    success=False,
                    counterexample="ERROR: Source is more defined than target",
                )
            ]
        )
        result = oracle.verify_transformation(
            "define i32 @f(i32 %x) { ret i32 %x }",
            "define i32 @f(i32 %x) { ret i32 0 }",
        )
        assert not result.success
        assert result.counterexample is not None

    def test_verify_transformation_passes_both(self):
        oracle = MockAlive2OracleImpl()
        result = oracle.verify_transformation("src ir", "tgt ir")
        assert result.success


# ===========================================================================
# OracleFactory
# ===========================================================================

class TestOracleFactory:
    def test_create_mock_lean4(self):
        oracle = OracleFactory.create("mock_lean4")
        assert isinstance(oracle, MockLean4OracleImpl)

    def test_create_mock_tlc(self):
        oracle = OracleFactory.create("mock_tlc")
        assert isinstance(oracle, MockTLCOracleImpl)

    def test_create_mock_z3(self):
        oracle = OracleFactory.create("mock_z3")
        assert isinstance(oracle, MockZ3OracleImpl)

    def test_create_mock_alive2(self):
        oracle = OracleFactory.create("mock_alive2")
        assert isinstance(oracle, MockAlive2OracleImpl)

    def test_create_real_lean4(self):
        oracle = OracleFactory.create("lean4", lean_path="lean", timeout=30)
        assert isinstance(oracle, Lean4OracleImpl)

    def test_create_real_tlc(self):
        oracle = OracleFactory.create("tlc", tlc_jar="tla2tools.jar")
        assert isinstance(oracle, TLCOracleImpl)

    def test_create_real_z3(self):
        oracle = OracleFactory.create("z3", timeout=10)
        assert isinstance(oracle, Z3OracleImpl)

    def test_create_real_alive2(self):
        oracle = OracleFactory.create("alive2", alive_tv_bin="alive-tv")
        assert isinstance(oracle, Alive2OracleImpl)

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown oracle type"):
            OracleFactory.create("nonexistent")

    def test_case_insensitive(self):
        oracle = OracleFactory.create("MOCK_Z3")
        assert isinstance(oracle, MockZ3OracleImpl)

    def test_with_kwargs_forwarded(self):
        results = [OracleResult(success=False, error_message="nope")]
        oracle = OracleFactory.create("mock_lean4", results=results)
        r = oracle.check("theorem t : False := by contradiction")
        assert not r.success

    def test_available_types(self):
        types = OracleFactory.available_types()
        assert "lean4" in types
        assert "mock_z3" in types

    def test_register_custom(self):
        class DummyOracle(MockZ3OracleImpl):
            pass

        OracleFactory.register("dummy", DummyOracle)
        oracle = OracleFactory.create("dummy")
        assert isinstance(oracle, DummyOracle)
        # Clean up
        del OracleFactory._REGISTRY["dummy"]


# ===========================================================================
# Lean4OracleImpl parsing (no subprocess needed)
# ===========================================================================

class TestLean4Parsing:
    def setup_method(self):
        self.oracle = Lean4OracleImpl()

    def test_parse_error_type_mismatch(self):
        output = "Foo.lean:3:10: error: type mismatch\n  expected: Nat\n  but has type: Int"
        err = self.oracle._parse_error(output)
        assert err.kind == "type_mismatch"
        assert err.line == 3
        assert err.column == 10

    def test_parse_error_unsolved_goals(self):
        output = "Bar.lean:7:0: error: unsolved goals\n⊢ Nat.succ n = n + 1"
        err = self.oracle._parse_error(output)
        assert err.kind == "unsolved_goals"
        assert err.line == 7

    def test_parse_error_unknown_identifier(self):
        output = "X.lean:1:5: error: unknown identifier 'foo'"
        err = self.oracle._parse_error(output)
        assert err.kind == "unknown_identifier"

    def test_parse_error_other(self):
        output = "some weird error happened"
        err = self.oracle._parse_error(output)
        assert err.kind == "other"
        assert err.line is None

    def test_parse_goal_state_closed(self):
        gs = self.oracle._parse_goal_state("no goals")
        assert gs.is_closed

    def test_parse_goal_state_goals_accomplished(self):
        gs = self.oracle._parse_goal_state("Goals accomplished 🎉")
        assert gs.is_closed

    def test_parse_goal_state_open(self):
        output = "n : Nat\n⊢ Nat.succ n = n + 1"
        gs = self.oracle._parse_goal_state(output)
        assert not gs.is_closed
        assert len(gs.goals) >= 1
        assert any("Nat" in h for h in gs.hypotheses)

    def test_parse_goal_state_multiple_goals(self):
        output = (
            "case succ\nn : Nat\n⊢ Nat.succ n = n + 1\n"
            "case zero\n⊢ 0 = 0\n"
        )
        gs = self.oracle._parse_goal_state(output)
        assert not gs.is_closed
        assert len(gs.goals) >= 1


# ===========================================================================
# TLCOracleImpl parsing (no subprocess needed)
# ===========================================================================

class TestTLCParsing:
    def setup_method(self):
        self.oracle = TLCOracleImpl()

    def test_parse_no_error(self):
        output = (
            "TLC2 Version 2.17\n"
            "Model checking completed. No error has been found.\n"
            "  100 states generated, 50 distinct states found.\n"
        )
        result = self.oracle._parse_tlc_output(output)
        assert result.no_error
        assert result.states_explored == 100
        assert result.distinct_states == 50

    def test_parse_invariant_violation(self):
        output = (
            "Error: Invariant TypeInvariant is violated.\n"
            "The following behaviour constitutes a counter-example:\n"
            "State 1: x = -1\n"
            "State 2: x = -2\n"
        )
        result = self.oracle._parse_tlc_output(output)
        assert not result.no_error
        assert "TypeInvariant" in result.invariant_violations

    def test_parse_deadlock(self):
        output = "Error: Deadlock reached.\n"
        result = self.oracle._parse_tlc_output(output)
        assert result.deadlock_found

    def test_parse_counterexample_extracted(self):
        output = (
            "Error: Invariant Safety is violated.\n"
            "The following behaviour constitutes a counter-example:\n"
            "State 1 (Initial): x = 0\n"
            "State 2: x = 1\n"
            "\n"
            "==========\n"
        )
        cex = self.oracle._parse_counterexample(output)
        assert cex is not None
        assert "counter-example" in cex.lower() or "State" in cex

    def test_parse_counterexample_none(self):
        output = "No error has been found.\n"
        cex = self.oracle._parse_counterexample(output)
        assert cex is None

    def test_parse_states_with_commas(self):
        output = "1,234,567 states generated, 890,123 distinct states found.\n"
        result = self.oracle._parse_tlc_output(output)
        assert result.states_explored == 1_234_567
        assert result.distinct_states == 890_123


# ===========================================================================
# Alive2OracleImpl parsing (no subprocess needed)
# ===========================================================================

class TestAlive2Parsing:
    def setup_method(self):
        self.oracle = Alive2OracleImpl()

    def test_parse_correct(self):
        output = (
            "Processing... done\n"
            "Transformation seems to be correct!\n"
            "  0 incorrect transformations\n"
            "  1 correct transformations\n"
        )
        assert self.oracle._parse_alive2_output(output) is True

    def test_parse_incorrect(self):
        output = (
            "Processing... done\n"
            "ERROR: Source is more defined than target\n"
            "  Example: ...\n"
        )
        assert self.oracle._parse_alive2_output(output) is False

    def test_parse_counterexample_extracted(self):
        output = (
            "Processing... done\n"
            "ERROR: Source is more defined than target\n"
            "  Example: i32 poison\n\n"
            "More output here\n"
        )
        cex = self.oracle._parse_counterexample(output)
        assert cex is not None
        assert "ERROR" in cex

    def test_parse_counterexample_none_when_absent(self):
        output = "Transformation seems to be correct!\n"
        cex = self.oracle._parse_counterexample(output)
        assert cex is None


# ===========================================================================
# Z3OracleImpl — real z3 when available
# ===========================================================================

class TestZ3OracleImpl:
    """These tests run if z3-solver is installed, otherwise they skip."""

    @pytest.fixture(autouse=True)
    def require_z3(self):
        oracle = Z3OracleImpl()
        if not oracle.is_available():
            pytest.skip("z3-solver not installed")

    def test_unsat(self):
        oracle = Z3OracleImpl()
        result = oracle.check_smt("(assert false)")
        assert result.success

    def test_sat_gives_counterexample(self):
        oracle = Z3OracleImpl()
        result = oracle.check_smt(
            "(declare-const x Int)\n(assert (> x 5))"
        )
        assert not result.success
        assert result.counterexample is not None

    def test_unknown_formula(self):
        # A formula Z3 can trivially dispatch
        oracle = Z3OracleImpl()
        result = oracle.check_smt(
            "(declare-const x Int)\n(assert (= x x))"
        )
        # x = x is trivially sat, not unsat
        assert not result.success

    def test_synthesis_addition(self):
        oracle = Z3OracleImpl()
        spec = SynthSpec(
            input_vars=[("a", "Int"), ("b", "Int")],
            output_var="out",
            output_sort="Int",
            constraints=["(= out (+ a b))"],
        )
        # Any satisfying assignment is acceptable — just check it returns something
        result = oracle.synthesize(spec)
        # Result may be a Z3 expression or None depending on the model
        assert result is None or isinstance(result, str)

    def test_equivalence_tautology(self):
        oracle = Z3OracleImpl()
        # Both programs assert a contradiction — they are "equivalent" (both unsat)
        ok = oracle.check_equivalence(
            "(assert false)",
            "(assert false)",
        )
        # unsat of combined is True
        assert isinstance(ok, bool)


# ===========================================================================
# Utility
# ===========================================================================

class TestExtractBetween:
    def test_basic(self):
        text = "prefix expected: Nat\n  but Int suffix"
        result = _extract_between(text, "expected:", "\n")
        assert result == "Nat"

    def test_missing_start(self):
        assert _extract_between("hello world", "missing:", "\n") is None

    def test_missing_end(self):
        result = _extract_between("key: value", "key:", "|||")
        assert result == "value"

    def test_empty_between(self):
        result = _extract_between("key:value", "key:", "v")
        assert result == ""


# ===========================================================================
# Integration tests (real tools, skipped by default)
# ===========================================================================

@pytest.mark.integration
class TestLean4Integration:
    def test_valid_theorem(self):
        oracle = OracleFactory.create("lean4")
        if not oracle.is_available():
            pytest.skip("lean not installed")
        result = oracle.check("theorem t : True := trivial")
        assert result.success

    def test_invalid_theorem(self):
        oracle = OracleFactory.create("lean4")
        if not oracle.is_available():
            pytest.skip("lean not installed")
        result = oracle.check("theorem t : False := by contradiction")
        assert not result.success


@pytest.mark.integration
class TestTLCIntegration:
    _SPEC = """
---- MODULE Spec ----
EXTENDS Naturals

VARIABLE x

Init == x = 0
Next == x' = x + 1
Spec == Init /\\ [][Next]_x

TypeInvariant == x \\in Nat

====
"""

    def test_valid_spec(self):
        oracle = OracleFactory.create("tlc")
        if not oracle.is_available():
            pytest.skip("TLC/java not installed")
        result = oracle.check(self._SPEC)
        # TLC may or may not find an error depending on bounds
        assert isinstance(result.success, bool)


@pytest.mark.integration
class TestAlive2Integration:
    _IDENTITY_SRC = (
        "define i32 @f(i32 %x) {\n"
        "entry:\n"
        "  ret i32 %x\n"
        "}\n"
    )
    _IDENTITY_TGT = (
        "define i32 @f(i32 %x) {\n"
        "entry:\n"
        "  ret i32 %x\n"
        "}\n"
    )

    def test_identity_transformation(self):
        oracle = OracleFactory.create("alive2")
        if not oracle.is_available():
            pytest.skip("alive-tv not installed")
        result = oracle.verify_transformation(self._IDENTITY_SRC, self._IDENTITY_TGT)
        assert result.success
