"""
FormalOracleInterface — unified adapter for Lean 4, TLC, Z3, Alive2.

All oracles implement check(spec: str) -> OracleResult.
"""

from __future__ import annotations

import subprocess
import tempfile
import textwrap
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class OracleResult:
    success: bool
    counterexample: Optional[str] = None
    error_message: Optional[str] = None
    timing_seconds: float = 0.0
    raw_output: str = ""

    @property
    def is_verified(self) -> bool:
        return self.success and self.counterexample is None

    def __repr__(self) -> str:  # pragma: no cover
        status = "✓ verified" if self.is_verified else ("✗ counterexample" if self.counterexample else "✗ error")
        return f"OracleResult({status}, {self.timing_seconds:.2f}s)"


class FormalOracleInterface(ABC):
    """Abstract base class that all formal verification oracles must implement."""

    @abstractmethod
    def check(self, spec: str) -> OracleResult:
        """Verify *spec* and return a structured result."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the backend tool is reachable / installed."""

    def _run(
        self,
        cmd: list[str],
        stdin: Optional[str] = None,
        timeout: int = 120,
    ) -> tuple[int, str, str]:
        """Convenience wrapper around subprocess.run."""
        result = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# Lean 4
# ---------------------------------------------------------------------------

class Lean4Oracle(FormalOracleInterface):
    """Verifies a Lean 4 proof term / tactic block."""

    def __init__(self, lean_bin: str = "lean", timeout: int = 120) -> None:
        self.lean_bin = lean_bin
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            rc, _, _ = self._run([self.lean_bin, "--version"], timeout=10)
            return rc == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def check(self, spec: str) -> OracleResult:
        start = time.perf_counter()
        with tempfile.NamedTemporaryFile(suffix=".lean", mode="w", delete=False) as f:
            f.write(spec)
            tmp = f.name
        try:
            rc, stdout, stderr = self._run([self.lean_bin, tmp], timeout=self.timeout)
            elapsed = time.perf_counter() - start
            raw = stdout + stderr
            if rc == 0 and "error" not in raw.lower():
                return OracleResult(success=True, timing_seconds=elapsed, raw_output=raw)
            # Surface the first error line as the error_message
            error_lines = [l for l in raw.splitlines() if "error" in l.lower()]
            return OracleResult(
                success=False,
                error_message=error_lines[0] if error_lines else raw[:400],
                timing_seconds=elapsed,
                raw_output=raw,
            )
        except subprocess.TimeoutExpired:
            return OracleResult(
                success=False,
                error_message=f"Lean 4 timed out after {self.timeout}s",
                timing_seconds=self.timeout,
            )
        finally:
            Path(tmp).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# TLC (TLA+)
# ---------------------------------------------------------------------------

class TLCOracle(FormalOracleInterface):
    """Model-checks a TLA+ specification with TLC."""

    def __init__(self, tlc_jar: str = "tla2tools.jar", timeout: int = 300) -> None:
        self.tlc_jar = tlc_jar
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            rc, _, _ = self._run(["java", "-jar", self.tlc_jar, "-h"], timeout=10)
            return rc in (0, 1)  # TLC exits 1 on -h
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def check(self, spec: str) -> OracleResult:
        start = time.perf_counter()
        with tempfile.TemporaryDirectory() as tmpdir:
            spec_file = Path(tmpdir) / "Spec.tla"
            spec_file.write_text(spec)
            try:
                rc, stdout, stderr = self._run(
                    ["java", "-jar", self.tlc_jar, str(spec_file), "-deadlock"],
                    timeout=self.timeout,
                )
                elapsed = time.perf_counter() - start
                raw = stdout + stderr
                if "No error has been found" in raw:
                    return OracleResult(success=True, timing_seconds=elapsed, raw_output=raw)
                cex = self._extract_tlc_counterexample(raw)
                return OracleResult(
                    success=False,
                    counterexample=cex,
                    error_message=None if cex else raw[:400],
                    timing_seconds=elapsed,
                    raw_output=raw,
                )
            except subprocess.TimeoutExpired:
                return OracleResult(
                    success=False,
                    error_message=f"TLC timed out after {self.timeout}s",
                    timing_seconds=self.timeout,
                )

    @staticmethod
    def _extract_tlc_counterexample(output: str) -> Optional[str]:
        lines = output.splitlines()
        cex_lines: list[str] = []
        inside = False
        for line in lines:
            if "Error:" in line or "Invariant" in line:
                inside = True
            if inside:
                cex_lines.append(line)
            if inside and line.strip() == "":
                break
        return "\n".join(cex_lines) if cex_lines else None


# ---------------------------------------------------------------------------
# Z3
# ---------------------------------------------------------------------------

class Z3Oracle(FormalOracleInterface):
    """Checks a Z3 SMT-LIB2 formula via the z3 Python API or CLI."""

    def __init__(self, use_python_api: bool = True, timeout: int = 60) -> None:
        self.use_python_api = use_python_api
        self.timeout = timeout

    def is_available(self) -> bool:
        if self.use_python_api:
            try:
                import z3  # noqa: F401
                return True
            except ImportError:
                return False
        try:
            rc, _, _ = self._run(["z3", "--version"], timeout=5)
            return rc == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def check(self, spec: str) -> OracleResult:
        if self.use_python_api:
            return self._check_via_api(spec)
        return self._check_via_cli(spec)

    def _check_via_api(self, spec: str) -> OracleResult:
        import z3

        start = time.perf_counter()
        try:
            solver = z3.Solver()
            solver.set("timeout", self.timeout * 1000)
            solver.from_string(spec)
            result = solver.check()
            elapsed = time.perf_counter() - start
            if result == z3.sat:
                model = str(solver.model())
                return OracleResult(
                    success=False,
                    counterexample=model,
                    timing_seconds=elapsed,
                    raw_output=model,
                )
            if result == z3.unsat:
                return OracleResult(success=True, timing_seconds=elapsed, raw_output="unsat")
            return OracleResult(
                success=False,
                error_message="Z3 returned unknown",
                timing_seconds=elapsed,
                raw_output="unknown",
            )
        except Exception as exc:
            return OracleResult(
                success=False,
                error_message=str(exc),
                timing_seconds=time.perf_counter() - start,
            )

    def _check_via_cli(self, spec: str) -> OracleResult:
        start = time.perf_counter()
        try:
            rc, stdout, stderr = self._run(["z3", "-in"], stdin=spec, timeout=self.timeout)
            elapsed = time.perf_counter() - start
            raw = stdout + stderr
            if "unsat" in raw:
                return OracleResult(success=True, timing_seconds=elapsed, raw_output=raw)
            if "sat" in raw:
                return OracleResult(
                    success=False,
                    counterexample=raw,
                    timing_seconds=elapsed,
                    raw_output=raw,
                )
            return OracleResult(
                success=False,
                error_message=raw[:400],
                timing_seconds=elapsed,
                raw_output=raw,
            )
        except subprocess.TimeoutExpired:
            return OracleResult(
                success=False,
                error_message=f"Z3 timed out after {self.timeout}s",
                timing_seconds=self.timeout,
            )


# ---------------------------------------------------------------------------
# Alive2
# ---------------------------------------------------------------------------

class Alive2Oracle(FormalOracleInterface):
    """Checks LLVM IR optimization correctness with Alive2."""

    def __init__(self, alive_tv_bin: str = "alive-tv", timeout: int = 120) -> None:
        self.alive_tv_bin = alive_tv_bin
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            rc, _, _ = self._run([self.alive_tv_bin, "--version"], timeout=5)
            return rc == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def check(self, spec: str) -> OracleResult:
        """spec should be two LLVM IR functions separated by a blank line."""
        start = time.perf_counter()
        with tempfile.NamedTemporaryFile(suffix=".ll", mode="w", delete=False) as f:
            f.write(spec)
            tmp = f.name
        try:
            rc, stdout, stderr = self._run(
                [self.alive_tv_bin, tmp],
                timeout=self.timeout,
            )
            elapsed = time.perf_counter() - start
            raw = stdout + stderr
            if "Transformation seems to be correct" in raw:
                return OracleResult(success=True, timing_seconds=elapsed, raw_output=raw)
            cex_start = raw.find("ERROR:")
            cex = raw[cex_start:cex_start + 600] if cex_start != -1 else raw[:400]
            return OracleResult(
                success=False,
                counterexample=cex if cex_start != -1 else None,
                error_message=None if cex_start != -1 else raw[:400],
                timing_seconds=elapsed,
                raw_output=raw,
            )
        except subprocess.TimeoutExpired:
            return OracleResult(
                success=False,
                error_message=f"Alive2 timed out after {self.timeout}s",
                timing_seconds=self.timeout,
            )
        finally:
            Path(tmp).unlink(missing_ok=True)
