"""
IterativeRefinementLoop — the core agent loop.

Drives: propose → evaluate → diagnose → refine → repeat
Handles: budget management, cycle detection, logging, early stopping.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from .logger import RunLogger
from .oracle import FormalOracleInterface, OracleResult


# ---------------------------------------------------------------------------
# Type protocol for the LLM backend (kept loose so any backend works)
# ---------------------------------------------------------------------------

class LLMBackend(Protocol):
    def complete(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> tuple[str, int, int]:
        """Return (text, prompt_tokens, completion_tokens)."""
        ...


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class LoopConfig:
    max_cycles: int = 20
    max_prompt_tokens: int = 200_000
    max_completion_tokens: int = 50_000
    convergence_score: float = 1.0          # stop when score >= this
    min_score_delta: float = 0.01           # early-stop if no improvement
    patience: int = 3                        # cycles without improvement before stopping
    proposal_temperature: float = 0.7
    diagnosis_temperature: float = 0.3
    proposal_max_tokens: int = 2048
    diagnosis_max_tokens: int = 1024
    cycle_detection_window: int = 5         # how many recent hashes to compare


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class LoopResult:
    success: bool
    best_proposal: str
    best_score: float
    cycles_run: int
    stop_reason: str    # "converged" | "budget_prompt" | "budget_completion" |
                        # "max_cycles" | "cycle_detected" | "patience"
    total_prompt_tokens: int
    total_completion_tokens: int
    elapsed_seconds: float


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class IterativeRefinementLoop:
    """
    Core refinement loop shared by all 9 projects.

    Usage::

        loop = IterativeRefinementLoop(
            llm=my_llm,
            oracle=Lean4Oracle(),
            logger=RunLogger("logs", "P1", config),
            config=LoopConfig(max_cycles=15),
        )
        result = loop.run(initial_prompt="Prove that ...")
    """

    def __init__(
        self,
        llm: LLMBackend,
        oracle: FormalOracleInterface,
        logger: RunLogger,
        config: Optional[LoopConfig] = None,
        score_fn: Optional[Callable[[OracleResult], float]] = None,
    ) -> None:
        self.llm = llm
        self.oracle = oracle
        self.logger = logger
        self.config = config or LoopConfig()
        self._score_fn = score_fn or self._default_score

        self._prompt_tokens_used: int = 0
        self._completion_tokens_used: int = 0
        self._recent_proposal_hashes: list[str] = []

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, initial_prompt: str) -> LoopResult:
        start_time = time.perf_counter()
        best_proposal = ""
        best_score = -1.0
        current_prompt = initial_prompt
        diagnosis = ""
        cycles_without_improvement = 0

        for cycle in range(self.config.max_cycles):
            # ---- propose -------------------------------------------------
            proposal, p_tok, c_tok = self.propose(current_prompt)
            proposal_id = self.logger.log_proposal(cycle, proposal, prompt_tokens=p_tok)
            self._prompt_tokens_used += p_tok
            self._completion_tokens_used += c_tok

            # ---- cycle detection -----------------------------------------
            stop = self._check_cycle_detection(proposal)
            if stop:
                return self._make_result(
                    best_proposal, best_score, cycle + 1,
                    "cycle_detected", start_time,
                )

            # ---- evaluate ------------------------------------------------
            oracle_result = self.evaluate(proposal)
            score = self._score_fn(oracle_result)
            self.logger.log_evaluation(
                proposal_id=proposal_id,
                cycle=cycle,
                success=oracle_result.success,
                score=score,
                oracle_name=type(self.oracle).__name__,
                counterexample=oracle_result.counterexample,
                error_message=oracle_result.error_message,
                timing_seconds=oracle_result.timing_seconds,
            )

            # ---- track best ----------------------------------------------
            if score > best_score:
                best_score = score
                best_proposal = proposal
                cycles_without_improvement = 0
            else:
                cycles_without_improvement += 1

            # ---- convergence check ---------------------------------------
            if self.is_converged(score):
                return self._make_result(
                    best_proposal, best_score, cycle + 1,
                    "converged", start_time,
                )

            # ---- budget checks -------------------------------------------
            if stop_reason := self._check_budget():
                return self._make_result(
                    best_proposal, best_score, cycle + 1,
                    stop_reason, start_time,
                )

            # ---- patience early stop -------------------------------------
            if cycles_without_improvement >= self.config.patience:
                return self._make_result(
                    best_proposal, best_score, cycle + 1,
                    "patience", start_time,
                )

            # ---- diagnose ------------------------------------------------
            diagnosis, d_p_tok, d_c_tok = self.diagnose(proposal, oracle_result)
            self.logger.log_diagnosis(proposal_id, cycle, diagnosis, completion_tokens=d_c_tok)
            self._prompt_tokens_used += d_p_tok
            self._completion_tokens_used += d_c_tok

            # ---- refine --------------------------------------------------
            current_prompt = self.refine(initial_prompt, proposal, oracle_result, diagnosis)

        return self._make_result(
            best_proposal, best_score, self.config.max_cycles,
            "max_cycles", start_time,
        )

    # ------------------------------------------------------------------
    # Step methods (override in subclasses if needed)
    # ------------------------------------------------------------------

    def propose(self, prompt: str) -> tuple[str, int, int]:
        """Call LLM to generate a new proposal. Returns (text, p_tokens, c_tokens)."""
        text, p_tok, c_tok = self.llm.complete(
            prompt,
            max_tokens=self.config.proposal_max_tokens,
            temperature=self.config.proposal_temperature,
        )
        return text, p_tok, c_tok

    def evaluate(self, proposal: str) -> OracleResult:
        """Pass proposal to the formal oracle."""
        return self.oracle.check(proposal)

    def diagnose(
        self,
        proposal: str,
        oracle_result: OracleResult,
    ) -> tuple[str, int, int]:
        """Ask LLM to diagnose the oracle failure. Returns (text, p_tokens, c_tokens)."""
        failure_info = (
            f"Counterexample:\n{oracle_result.counterexample}"
            if oracle_result.counterexample
            else f"Error:\n{oracle_result.error_message}"
        )
        diag_prompt = (
            f"The following attempt failed formal verification.\n\n"
            f"Attempt:\n{proposal}\n\n"
            f"{failure_info}\n\n"
            f"Explain the root cause and what must be changed to fix it."
        )
        text, p_tok, c_tok = self.llm.complete(
            diag_prompt,
            max_tokens=self.config.diagnosis_max_tokens,
            temperature=self.config.diagnosis_temperature,
        )
        return text, p_tok, c_tok

    def refine(
        self,
        original_prompt: str,
        last_proposal: str,
        oracle_result: OracleResult,
        diagnosis: str,
    ) -> str:
        """Build the next prompt incorporating the diagnosis."""
        failure_info = (
            f"Counterexample:\n{oracle_result.counterexample}"
            if oracle_result.counterexample
            else f"Error:\n{oracle_result.error_message}"
        )
        return (
            f"{original_prompt}\n\n"
            f"## Previous attempt (failed)\n{last_proposal}\n\n"
            f"## Oracle feedback\n{failure_info}\n\n"
            f"## Diagnosis\n{diagnosis}\n\n"
            f"## Instructions\nApply the diagnosis above and produce a corrected version."
        )

    def is_converged(self, score: float) -> bool:
        return score >= self.config.convergence_score

    # ------------------------------------------------------------------
    # Budget / cycle detection
    # ------------------------------------------------------------------

    def _check_budget(self) -> Optional[str]:
        if self._prompt_tokens_used >= self.config.max_prompt_tokens:
            return "budget_prompt"
        if self._completion_tokens_used >= self.config.max_completion_tokens:
            return "budget_completion"
        return None

    def _check_cycle_detection(self, proposal: str) -> bool:
        h = hashlib.sha256(proposal.encode()).hexdigest()[:16]
        if h in self._recent_proposal_hashes[-self.config.cycle_detection_window :]:
            return True
        self._recent_proposal_hashes.append(h)
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _default_score(result: OracleResult) -> float:
        if result.is_verified:
            return 1.0
        if result.counterexample:
            return 0.3   # partial credit: reached evaluation
        return 0.1       # syntax / tool error

    def _make_result(
        self,
        best_proposal: str,
        best_score: float,
        cycles_run: int,
        stop_reason: str,
        start_time: float,
    ) -> LoopResult:
        return LoopResult(
            success=best_score >= self.config.convergence_score,
            best_proposal=best_proposal,
            best_score=best_score,
            cycles_run=cycles_run,
            stop_reason=stop_reason,
            total_prompt_tokens=self._prompt_tokens_used,
            total_completion_tokens=self._completion_tokens_used,
            elapsed_seconds=time.perf_counter() - start_time,
        )
