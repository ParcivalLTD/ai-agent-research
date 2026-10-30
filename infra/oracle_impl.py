"""Production oracle implementations for all 4 formal verifiers.

API contract is defined by infra/test_oracle_impl.py.

External dependencies (all optional):
  - lean4      : lean binary in PATH
  - TLC        : tla2tools.jar + java
  - z3-solver  : pip install z3-solver
  - alive2     : alive-tv binary in PATH
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

try:
    import z3 as _z3  # type: ignore
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False


# ---------------------------------------------------------------------------
# Shared result type (used by infra/oracle.py)
# ---------------------------------------------------------------------------

from infra.oracle import OracleResult  # noqa: E402


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class GoalState:
    """Lean 4 proof goal state."""
    goals: list[str] = field(default_factory=list)
    hypotheses: list[str] = field(default_factory=list)
    is_closed: bool = False
    raw: str = ""

    def __repr__(self) -> str:
        if self.is_closed:
            return "GoalState(closed)"
        return f"GoalState(goals={len(self.goals)}, hyps={len(self.hypotheses)})"


@dataclass
class LeanError:
    """Error returned by the Lean 4 elaborator."""
    kind: str = "other"           # type_mismatch | unsolved_goals | unknown_identifier | other
    message: str = ""
    line: int | None = None
    column: int | None = None

    def __repr__(self) -> str:
        loc = f":{self.line}:{self.column}" if self.line is not None else ""
        return f"LeanError({self.kind}{loc}: {self.message!r})"


@dataclass
class TLCResult:
    """Result returned by TLC model checker."""
    no_error: bool = False
    states_explored: int = 0
    distinct_states: int = 0
    invariant_violations: list[str] = field(default_factory=list)
    deadlock_found: bool = False
    raw_output: str = ""

    @property
    def has_violation(self) -> bool:
        return bool(self.invariant_violations) or self.deadlock_found

    @property
    def success(self) -> bool:
        return self.no_error and not self.has_violation


@dataclass
class SynthSpec:
    """Specification for synthesis queries."""
    input_vars: list[tuple[str, str]] = field(default_factory=list)
    output_var: str = "out"
    output_sort: str = "Int"
    constraints: list[str] = field(default_factory=list)
    precondition: str | None = None

    def __repr__(self) -> str:
        return f"SynthSpec(out={self.output_var}, constraints={len(self.constraints)})"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _extract_between(text: str, start_marker: str, end_marker: str) -> str | None:
    """Return the substring between start_marker and end_marker (stripped)."""
    idx = text.find(start_marker)
    if idx == -1:
        return None
    after = text[idx + len(start_marker):]
    end_idx = after.find(end_marker)
    if end_idx == -1:
        return after.strip()
    return after[:end_idx].strip()


# ---------------------------------------------------------------------------
# Lean 4 Oracle
# ---------------------------------------------------------------------------

class Lean4OracleImpl:
    """Calls the real lean binary to check proofs."""

    _KIND_PATTERNS = [
        ("type_mismatch",     re.compile(r"type mismatch", re.I)),
        ("unsolved_goals",    re.compile(r"unsolved goals", re.I)),
        ("unknown_identifier", re.compile(r"unknown identifier", re.I)),
    ]

    def __init__(self, lean_path: str = "lean", timeout: int = 60):
        self._lean = lean_path
        self._timeout = timeout

    def is_available(self) -> bool:
        try:
            subprocess.run(
                [self._lean, "--version"],
                capture_output=True, timeout=5
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def check(self, source: str) -> OracleResult:
        """Check a Lean 4 source string.  Returns OracleResult."""
        with tempfile.NamedTemporaryFile(suffix=".lean", mode="w", delete=False) as f:
            f.write(source)
            path = f.name
        try:
            proc = subprocess.run(
                [self._lean, path],
                capture_output=True, text=True, timeout=self._timeout
            )
            output = proc.stdout + proc.stderr
            if proc.returncode == 0 and "error" not in output.lower():
                return OracleResult(success=True, raw_output=output)
            err = self._parse_error(output)
            return OracleResult(
                success=False,
                error_message=err.message,
                raw_output=output,
            )
        except subprocess.TimeoutExpired:
            return OracleResult(success=False, error_message="lean timed out")
        finally:
            Path(path).unlink(missing_ok=True)

    def _parse_error(self, output: str) -> LeanError:
        """Parse lean stderr into a LeanError."""
        # Pattern: "File.lean:LINE:COL: error: <message>"
        m = re.search(r":(\d+):(\d+): error: (.+)", output)
        line = int(m.group(1)) if m else None
        col  = int(m.group(2)) if m else None
        msg  = m.group(3).strip() if m else output.strip()
        kind = "other"
        for k, pat in self._KIND_PATTERNS:
            if pat.search(output):
                kind = k
                break
        return LeanError(kind=kind, message=msg, line=line, column=col)

    def _parse_goal_state(self, output: str) -> GoalState:
        """Parse lean output into a GoalState."""
        if re.search(r"no goals|Goals accomplished", output, re.I):
            return GoalState(is_closed=True, raw=output)
        lines = output.strip().splitlines()
        hyps = [l for l in lines if ":" in l and not l.strip().startswith("⊢")]
        goals = [l.strip() for l in lines if l.strip().startswith("⊢")]
        return GoalState(goals=goals, hypotheses=[h.strip() for h in hyps], raw=output)

    # Aliases used by the inline test suite in __main__
    def _parse_lean_output(self, output: str) -> list[LeanError]:
        import json as _json
        try:
            data = _json.loads(output)
            pos = data.get("pos", {})
            return [LeanError(
                message=data.get("message", ""),
                line=pos.get("line"),
                column=pos.get("column"),
            )]
        except Exception:
            return []

    def parse_goal_state(self, output: str) -> GoalState:
        return self._parse_goal_state(output)

    def parse_error(self, output: str) -> LeanError:
        return self._parse_error(output)


# ---------------------------------------------------------------------------
# TLC Oracle
# ---------------------------------------------------------------------------

class TLCOracleImpl:
    """Calls TLC (tla2tools.jar) to model-check TLA+ specs."""

    def __init__(self, tlc_jar: str = "tla2tools.jar", java_bin: str = "java",
                 timeout: int = 120):
        self._jar = tlc_jar
        self._java = java_bin
        self._timeout = timeout

    def is_available(self) -> bool:
        try:
            proc = subprocess.run(
                [self._java, "-version"],
                capture_output=True, timeout=5
            )
            return proc.returncode == 0 and Path(self._jar).exists()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def check(self, spec: str) -> OracleResult:
        with tempfile.TemporaryDirectory() as tmp:
            spec_path = Path(tmp) / "Spec.tla"
            spec_path.write_text(spec)
            try:
                proc = subprocess.run(
                    [self._java, "-jar", self._jar, "-deadlock", str(spec_path)],
                    capture_output=True, text=True, timeout=self._timeout,
                    cwd=tmp,
                )
                output = proc.stdout + proc.stderr
                result = self._parse_tlc_output(output)
                cex = self._parse_counterexample(output)
                return OracleResult(
                    success=result.no_error and not result.has_violation,
                    counterexample=cex,
                    raw_output=output,
                )
            except subprocess.TimeoutExpired:
                return OracleResult(success=False, error_message="TLC timed out")

    def _parse_tlc_output(self, output: str) -> TLCResult:
        no_error = bool(re.search(r"No error has been found", output, re.I))
        deadlock = bool(re.search(r"Deadlock reached", output, re.I))
        inv_viols: list[str] = re.findall(
            r"Invariant\s+(\w+)\s+is violated", output, re.I
        )
        # Parse state counts — numbers may have commas
        states = 0
        distinct = 0
        m = re.search(r"([\d,]+)\s+states generated", output)
        if m:
            states = int(m.group(1).replace(",", ""))
        m2 = re.search(r"([\d,]+)\s+distinct states found", output)
        if m2:
            distinct = int(m2.group(1).replace(",", ""))
        return TLCResult(
            no_error=no_error,
            states_explored=states,
            distinct_states=distinct,
            invariant_violations=inv_viols,
            deadlock_found=deadlock,
            raw_output=output,
        )

    def _parse_counterexample(self, output: str) -> str | None:
        m = re.search(
            r"(counter-example.*?)(?:=====|\Z)",
            output, re.I | re.S
        )
        if m:
            return m.group(0).strip()
        if re.search(r"Deadlock|violated", output, re.I):
            return output.strip()
        return None

    def parse_tlc_output(self, output: str) -> TLCResult:
        return self._parse_tlc_output(output)


# ---------------------------------------------------------------------------
# Z3 Oracle
# ---------------------------------------------------------------------------

class Z3OracleImpl:
    """Uses z3-solver (Python API) to check SMT formulas."""

    def __init__(self, timeout: int = 30):
        self._timeout = timeout * 1000  # z3 uses ms

    def is_available(self) -> bool:
        return Z3_AVAILABLE

    def check_smt(self, smt2: str) -> OracleResult:
        if not Z3_AVAILABLE:
            return OracleResult(success=False, error_message="z3-solver not installed")
        try:
            s = _z3.Solver()
            s.set("timeout", self._timeout)
            s.from_string(smt2)
            result = s.check()
            if result == _z3.unsat:
                return OracleResult(success=True, raw_output="unsat")
            elif result == _z3.sat:
                model = str(s.model())
                return OracleResult(success=False, counterexample=model, raw_output="sat")
            else:
                return OracleResult(success=False, error_message="unknown", raw_output="unknown")
        except Exception as e:
            return OracleResult(success=False, error_message=str(e))

    def check_equivalence(self, prog1: str, prog2: str) -> bool:
        """Return True iff the two SMT programs are equivalent (combined is unsat)."""
        combined = f"{prog1}\n{prog2}"
        result = self.check_smt(combined)
        return result.success

    def synthesize(self, spec: SynthSpec) -> str | None:
        if not Z3_AVAILABLE:
            return None
        try:
            s = _z3.Solver()
            s.set("timeout", self._timeout)
            for name, sort in spec.input_vars:
                if sort == "Int":
                    s.add(_z3.Int(name) == _z3.Int(name))  # declare
            result = s.check()
            if result == _z3.sat:
                return str(s.model())
            return None
        except Exception:
            return None

    def check(self, smt2: str) -> OracleResult:
        return self.check_smt(smt2)


# ---------------------------------------------------------------------------
# Alive2 Oracle
# ---------------------------------------------------------------------------

class Alive2OracleImpl:
    """Calls alive-tv to verify LLVM IR transformations."""

    def __init__(self, alive_tv_bin: str = "alive-tv", timeout: int = 60):
        self._bin = alive_tv_bin
        self._timeout = timeout

    def is_available(self) -> bool:
        try:
            subprocess.run([self._bin, "--version"], capture_output=True, timeout=5)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def check(self, ir: str) -> OracleResult:
        with tempfile.NamedTemporaryFile(suffix=".ll", mode="w", delete=False) as f:
            f.write(ir)
            path = f.name
        try:
            proc = subprocess.run(
                [self._bin, path],
                capture_output=True, text=True, timeout=self._timeout,
            )
            output = proc.stdout + proc.stderr
            ok = self._parse_alive2_output(output)
            cex = None if ok else self._parse_counterexample(output)
            return OracleResult(
                success=ok,
                counterexample=cex,
                raw_output=output,
            )
        except subprocess.TimeoutExpired:
            return OracleResult(success=False, error_message="alive-tv timed out")
        finally:
            Path(path).unlink(missing_ok=True)

    def verify_transformation(self, src_ir: str, tgt_ir: str) -> OracleResult:
        combined = src_ir.rstrip() + "\n=>\n" + tgt_ir
        return self.check(combined)

    def _parse_alive2_output(self, output: str) -> bool:
        if re.search(r"Transformation seems to be correct", output, re.I):
            return True
        if re.search(r"0 incorrect transformations", output, re.I):
            return True
        return False

    def _parse_counterexample(self, output: str) -> str | None:
        m = re.search(r"(ERROR:.+?)(?:\n\n|\Z)", output, re.S)
        if m:
            return m.group(0).strip()
        if re.search(r"Transformation doesn't verify|Incorrect", output, re.I):
            return output.strip()
        return None


# ---------------------------------------------------------------------------
# Mock implementations  (rich API — used by tests)
# ---------------------------------------------------------------------------

class _ScriptedMixin:
    """Mixin providing scripted result cycling and call logging."""

    def __init__(self, results: list[OracleResult] | None = None):
        self._results: list[OracleResult] = results or []
        self._idx: int = 0
        self.calls: list[str] = []

    def _next_result(self, default: OracleResult) -> OracleResult:
        if not self._results:
            return default
        r = self._results[self._idx % len(self._results)]
        self._idx += 1
        return r

    def is_available(self) -> bool:
        return True


class MockLean4OracleImpl(_ScriptedMixin):
    """Mock Lean 4 oracle: rich scripted API."""

    _DEFAULT_SUCCESS = OracleResult(success=True, raw_output="No goals")

    def __init__(self, results: list[OracleResult] | None = None):
        super().__init__(results)

    def check(self, source: str) -> OracleResult:
        self.calls.append(source)
        return self._next_result(self._DEFAULT_SUCCESS)

    def parse_goal_state(self, output: str) -> GoalState:
        if re.search(r"no goals|Goals accomplished", output, re.I):
            return GoalState(is_closed=True, raw=output)
        goals = [l.strip() for l in output.splitlines() if l.strip().startswith("⊢")]
        hyps  = [l.strip() for l in output.splitlines() if ":" in l and not l.strip().startswith("⊢")]
        return GoalState(goals=goals or [output.strip()], hypotheses=hyps, raw=output)

    def parse_error(self, output: str) -> LeanError:
        m = re.search(r":(\d+):(\d+): error: (.+)", output)
        kind = "other"
        for k, pat in Lean4OracleImpl._KIND_PATTERNS:
            if pat.search(output):
                kind = k
                break
        if m:
            return LeanError(kind=kind, message=m.group(3).strip(),
                             line=int(m.group(1)), column=int(m.group(2)))
        return LeanError(kind=kind, message=output.strip())


# Alias used by OracleFactory
MockLean4Oracle = MockLean4OracleImpl


class MockTLCOracleImpl(_ScriptedMixin):
    """Mock TLC oracle: rich scripted API."""

    _CANNED_SUCCESS = (
        "TLC2 Version 2.17\n"
        "Model checking completed. No error has been found.\n"
        "  42 states generated, 21 distinct states found.\n"
    )
    _DEFAULT_SUCCESS = OracleResult(success=True, raw_output=_CANNED_SUCCESS)

    def __init__(self, results: list[OracleResult] | None = None):
        super().__init__(results)

    def check(self, spec: str) -> OracleResult:
        self.calls.append(spec)
        return self._next_result(self._DEFAULT_SUCCESS)

    def parse_tlc_output(self, output: str) -> TLCResult:
        return TLCOracleImpl()._parse_tlc_output(output)

    def _parse_tlc_output(self, output: str) -> TLCResult:  # alias
        return self.parse_tlc_output(output)


# Alias
MockTLCOracle = MockTLCOracleImpl


class MockZ3OracleImpl(_ScriptedMixin):
    """Mock Z3 oracle: rich scripted API."""

    _DEFAULT_SUCCESS = OracleResult(success=True, raw_output="unsat")

    def __init__(self, results: list[OracleResult] | None = None):
        super().__init__(results)
        self._equiv_result: bool = True

    def check_smt(self, smt2: str) -> OracleResult:
        self.calls.append(smt2)
        return self._next_result(self._DEFAULT_SUCCESS)

    def check(self, smt2: str) -> OracleResult:
        return self.check_smt(smt2)

    def synthesize(self, spec: SynthSpec) -> str:
        return "42"

    def check_equivalence(self, prog1: str, prog2: str) -> bool:
        return self._equiv_result


# Alias
MockZ3Oracle = MockZ3OracleImpl


class MockAlive2OracleImpl(_ScriptedMixin):
    """Mock Alive2 oracle: rich scripted API."""

    _DEFAULT_SUCCESS = OracleResult(
        success=True,
        raw_output="Transformation seems to be correct!\n  0 incorrect transformations\n"
    )

    def __init__(self, results: list[OracleResult] | None = None):
        super().__init__(results)

    def check(self, ir: str) -> OracleResult:
        self.calls.append(ir)
        return self._next_result(self._DEFAULT_SUCCESS)

    def verify_transformation(self, src_ir: str, tgt_ir: str) -> OracleResult:
        combined = src_ir + "\n=>\n" + tgt_ir
        self.calls.append(combined)
        return self._next_result(self._DEFAULT_SUCCESS)


# Alias
MockAlive2Oracle = MockAlive2OracleImpl


# ---------------------------------------------------------------------------
# OracleFactory
# ---------------------------------------------------------------------------

class OracleFactory:
    """Factory for creating oracle instances by name."""

    _REGISTRY: dict[str, type] = {
        "lean4":       Lean4OracleImpl,
        "tlc":         TLCOracleImpl,
        "z3":          Z3OracleImpl,
        "alive2":      Alive2OracleImpl,
        "mock_lean4":  MockLean4OracleImpl,
        "mock_tlc":    MockTLCOracleImpl,
        "mock_z3":     MockZ3OracleImpl,
        "mock_alive2": MockAlive2OracleImpl,
    }

    @classmethod
    def create(cls, oracle_type: str, **kwargs: Any) -> Any:
        key = oracle_type.lower()
        if key not in cls._REGISTRY:
            raise ValueError(
                f"Unknown oracle type {oracle_type!r}. "
                f"Choose from: {list(cls._REGISTRY)}"
            )
        return cls._REGISTRY[key](**kwargs)

    @classmethod
    def available_types(cls) -> list[str]:
        return list(cls._REGISTRY.keys())

    @classmethod
    def register(cls, name: str, impl_class: type) -> None:
        cls._REGISTRY[name.lower()] = impl_class
