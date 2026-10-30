"""
Self-improvement loop metrics for P9.

Tracks iteration-by-iteration progress of the recursive self-improving agent:
  - Programs attempted per iteration
  - Fix success rate
  - Confidence calibration
  - Regression detection
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class IterationResult:
    """Outcome of one self-improvement iteration."""
    iteration: int
    programs_attempted: int
    programs_fixed: int
    programs_regressed: int = 0
    avg_confidence: float = 0.0
    oracle_calls: int = 0
    wall_time_s: float = 0.0

    @property
    def fix_rate(self) -> float:
        if self.programs_attempted == 0: return 0.0
        return self.programs_fixed / self.programs_attempted

    @property
    def regression_rate(self) -> float:
        if self.programs_attempted == 0: return 0.0
        return self.programs_regressed / self.programs_attempted

    @property
    def net_improvement(self) -> int:
        return self.programs_fixed - self.programs_regressed

    def __repr__(self) -> str:
        return (f"Iter({self.iteration}: fixed={self.programs_fixed}/"
                f"{self.programs_attempted}, conf={self.avg_confidence:.2f})")


@dataclass
class LoopMetrics:
    """Aggregate metrics over many self-improvement iterations."""
    results: list[IterationResult] = field(default_factory=list)

    def add(self, result: IterationResult) -> None:
        self.results.append(result)

    def total_fixed(self) -> int:
        return sum(r.programs_fixed for r in self.results)

    def total_attempted(self) -> int:
        return sum(r.programs_attempted for r in self.results)

    def mean_fix_rate(self) -> float:
        if not self.results: return 0.0
        return sum(r.fix_rate for r in self.results) / len(self.results)

    def convergence_iteration(self, threshold: float = 0.05) -> int | None:
        """Return iteration at which fix_rate improvement dropped below threshold."""
        rates = [r.fix_rate for r in self.results]
        for i in range(1, len(rates)):
            if abs(rates[i] - rates[i-1]) < threshold:
                return self.results[i].iteration
        return None

    def is_improving(self) -> bool:
        """Return True if the last 3 iterations show a net upward trend."""
        if len(self.results) < 3: return True
        recent = self.results[-3:]
        rates = [r.fix_rate for r in recent]
        return rates[-1] >= rates[0]

    def confidence_calibration_error(self) -> float:
        """
        Mean absolute error between avg_confidence and actual fix_rate.
        Lower = better calibrated agent.
        """
        if not self.results: return 0.0
        errors = [abs(r.avg_confidence - r.fix_rate) for r in self.results]
        return sum(errors) / len(errors)

    def regression_budget_exceeded(self, max_rate: float = 0.1) -> bool:
        return any(r.regression_rate > max_rate for r in self.results)

    def efficiency(self) -> float:
        """Fixed programs per oracle call."""
        calls = sum(r.oracle_calls for r in self.results)
        if calls == 0: return 0.0
        return self.total_fixed() / calls

    def summary(self) -> str:
        lines = [
            f"Self-Improvement Loop — {len(self.results)} iterations",
            f"  Total attempted : {self.total_attempted()}",
            f"  Total fixed     : {self.total_fixed()}",
            f"  Mean fix rate   : {self.mean_fix_rate():.1%}",
            f"  Calib. error    : {self.confidence_calibration_error():.3f}",
            f"  Efficiency      : {self.efficiency():.3f} fixes/call",
            f"  Improving       : {self.is_improving()}",
        ]
        conv = self.convergence_iteration()
        if conv:
            lines.append(f"  Converged at    : iter {conv}")
        return "\n".join(lines)


# ── Simulated run data (from our P9 agent runs) ───────────────────────────

SIMULATED_RESULTS: list[IterationResult] = [
    IterationResult(1,  10, 3, 0, 0.82, 45,  12.1),
    IterationResult(2,  10, 5, 0, 0.78, 52,  11.8),
    IterationResult(3,  10, 6, 1, 0.74, 61,  13.2),
    IterationResult(4,  10, 7, 0, 0.71, 58,  12.5),
    IterationResult(5,  10, 7, 1, 0.69, 63,  14.1),
    IterationResult(6,  10, 8, 0, 0.72, 55,  11.9),
    IterationResult(7,  10, 8, 0, 0.75, 50,  10.8),
    IterationResult(8,  10, 9, 0, 0.76, 48,  10.2),
    IterationResult(9,  10, 9, 0, 0.78, 47,  10.0),
    IterationResult(10, 10, 9, 0, 0.79, 46,   9.8),
]


# ── Tests ─────────────────────────────────────────────────────────────────

def test_fix_rate():
    r = IterationResult(1, 10, 7)
    assert abs(r.fix_rate - 0.7) < 1e-9

def test_fix_rate_zero_attempted():
    r = IterationResult(1, 0, 0)
    assert r.fix_rate == 0.0

def test_net_improvement():
    r = IterationResult(1, 10, 7, 1)
    assert r.net_improvement == 6

def test_regression_rate():
    r = IterationResult(1, 10, 7, 2)
    assert abs(r.regression_rate - 0.2) < 1e-9

def test_metrics_add():
    m = LoopMetrics()
    m.add(IterationResult(1, 10, 5))
    assert m.total_fixed() == 5

def test_metrics_total_attempted():
    m = LoopMetrics()
    m.add(IterationResult(1, 10, 5))
    m.add(IterationResult(2, 10, 7))
    assert m.total_attempted() == 20

def test_mean_fix_rate():
    m = LoopMetrics()
    m.add(IterationResult(1, 10, 5))   # 0.5
    m.add(IterationResult(2, 10, 8))   # 0.8
    assert abs(m.mean_fix_rate() - 0.65) < 1e-9

def test_mean_fix_rate_empty():
    assert LoopMetrics().mean_fix_rate() == 0.0

def test_is_improving_true():
    m = LoopMetrics()
    m.add(IterationResult(1, 10, 5))
    m.add(IterationResult(2, 10, 7))
    m.add(IterationResult(3, 10, 9))
    assert m.is_improving()

def test_is_improving_false():
    m = LoopMetrics()
    m.add(IterationResult(1, 10, 9))
    m.add(IterationResult(2, 10, 7))
    m.add(IterationResult(3, 10, 5))
    assert not m.is_improving()

def test_convergence_detected():
    m = LoopMetrics()
    for i, fixed in enumerate([3, 5, 7, 8, 8, 8, 8], start=1):
        m.add(IterationResult(i, 10, fixed))
    conv = m.convergence_iteration(threshold=0.05)
    assert conv is not None
    assert conv >= 4

def test_calibration_error():
    m = LoopMetrics()
    m.add(IterationResult(1, 10, 7, avg_confidence=0.7))   # perfect
    m.add(IterationResult(2, 10, 8, avg_confidence=0.9))   # 0.1 off
    assert abs(m.confidence_calibration_error() - 0.05) < 1e-9

def test_efficiency():
    m = LoopMetrics()
    m.add(IterationResult(1, 10, 5, oracle_calls=50))
    assert abs(m.efficiency() - 0.1) < 1e-9

def test_regression_budget_not_exceeded():
    m = LoopMetrics()
    m.add(IterationResult(1, 10, 8, programs_regressed=0))
    assert not m.regression_budget_exceeded()

def test_regression_budget_exceeded():
    m = LoopMetrics()
    m.add(IterationResult(1, 10, 7, programs_regressed=2))  # 20% > 10%
    assert m.regression_budget_exceeded()

def test_summary_is_string():
    m = LoopMetrics(SIMULATED_RESULTS)
    s = m.summary()
    assert isinstance(s, str) and "fix rate" in s.lower()

def test_iteration_repr():
    r = IterationResult(3, 10, 7, avg_confidence=0.75)
    assert "3" in repr(r) and "7" in repr(r)

def test_simulated_results_count():
    assert len(SIMULATED_RESULTS) == 10

def test_simulated_mean_fix_rate():
    m = LoopMetrics(SIMULATED_RESULTS)
    assert m.mean_fix_rate() >= 0.5


if __name__ == "__main__":
    m = LoopMetrics(SIMULATED_RESULTS)
    print(m.summary())
    print(f"\nIteration-by-iteration fix rates:")
    for r in SIMULATED_RESULTS:
        bar = "█" * r.programs_fixed + "░" * (r.programs_attempted - r.programs_fixed)
        print(f"  Iter {r.iteration:2d}: [{bar}] {r.fix_rate:.0%}  conf={r.avg_confidence:.2f}")
