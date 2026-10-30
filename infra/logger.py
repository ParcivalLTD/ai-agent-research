"""
RunLogger — structured experiment tracking.

Logs every proposal, evaluation result, diagnosis, timing, and token count.
Supports run resumption, experiment comparison, and failure clustering.
"""

from __future__ import annotations

import gzip
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional


@dataclass
class ProposalRecord:
    proposal_id: str
    cycle: int
    content: str
    prompt_tokens: int
    timestamp: float = field(default_factory=time.time)


@dataclass
class EvaluationRecord:
    proposal_id: str
    cycle: int
    success: bool
    score: float
    oracle_name: str
    counterexample: Optional[str]
    error_message: Optional[str]
    timing_seconds: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class DiagnosisRecord:
    proposal_id: str
    cycle: int
    diagnosis: str
    completion_tokens: int
    timestamp: float = field(default_factory=time.time)


@dataclass
class RunMetadata:
    run_id: str
    project_name: str
    started_at: float
    config_snapshot: dict[str, Any]
    finished_at: Optional[float] = None
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cycles: int = 0
    outcome: str = "in_progress"  # in_progress | success | budget_exhausted | error


class RunLogger:
    """
    Thread-safe, append-only JSONL logger with gzip rotation support.

    Directory layout::

        logs/
          {run_id}/
            meta.json       — RunMetadata (rewritten on close)
            proposals.jsonl — one ProposalRecord per line
            evaluations.jsonl
            diagnoses.jsonl

    All methods are thread-safe.
    """

    def __init__(self, log_dir: str | Path, project_name: str, config: dict[str, Any]) -> None:
        self.run_id = str(uuid.uuid4())[:8]
        self._lock = threading.Lock()
        self._run_dir = Path(log_dir) / project_name / self.run_id
        self._run_dir.mkdir(parents=True, exist_ok=True)

        self.meta = RunMetadata(
            run_id=self.run_id,
            project_name=project_name,
            started_at=time.time(),
            config_snapshot=config,
        )
        self._write_meta()

        self._files: dict[str, Any] = {
            "proposals": open(self._run_dir / "proposals.jsonl", "a"),
            "evaluations": open(self._run_dir / "evaluations.jsonl", "a"),
            "diagnoses": open(self._run_dir / "diagnoses.jsonl", "a"),
        }

    # ------------------------------------------------------------------
    # Core logging methods
    # ------------------------------------------------------------------

    def log_proposal(
        self,
        cycle: int,
        content: str,
        prompt_tokens: int,
    ) -> str:
        """Returns the generated proposal_id."""
        proposal_id = f"{self.run_id}-c{cycle}"
        record = ProposalRecord(
            proposal_id=proposal_id,
            cycle=cycle,
            content=content,
            prompt_tokens=prompt_tokens,
        )
        with self._lock:
            self.meta.total_prompt_tokens += prompt_tokens
            self._append("proposals", asdict(record))
        return proposal_id

    def log_evaluation(
        self,
        proposal_id: str,
        cycle: int,
        success: bool,
        score: float,
        oracle_name: str,
        counterexample: Optional[str] = None,
        error_message: Optional[str] = None,
        timing_seconds: float = 0.0,
    ) -> None:
        record = EvaluationRecord(
            proposal_id=proposal_id,
            cycle=cycle,
            success=success,
            score=score,
            oracle_name=oracle_name,
            counterexample=counterexample,
            error_message=error_message,
            timing_seconds=timing_seconds,
        )
        with self._lock:
            self.meta.total_cycles = cycle
            self._append("evaluations", asdict(record))

    def log_diagnosis(
        self,
        proposal_id: str,
        cycle: int,
        diagnosis: str,
        completion_tokens: int,
    ) -> None:
        record = DiagnosisRecord(
            proposal_id=proposal_id,
            cycle=cycle,
            diagnosis=diagnosis,
            completion_tokens=completion_tokens,
        )
        with self._lock:
            self.meta.total_completion_tokens += completion_tokens
            self._append("diagnoses", asdict(record))

    def close(self, outcome: str = "success") -> None:
        with self._lock:
            self.meta.finished_at = time.time()
            self.meta.outcome = outcome
            self._write_meta()
            for fh in self._files.values():
                fh.close()
            self._files.clear()

    # ------------------------------------------------------------------
    # Resumption helpers
    # ------------------------------------------------------------------

    @classmethod
    def resume(cls, run_dir: str | Path) -> "RunLogger":
        """Re-open an existing run directory for appending."""
        run_dir = Path(run_dir)
        meta_path = run_dir / "meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"No meta.json in {run_dir}")
        meta = RunMetadata(**json.loads(meta_path.read_text()))
        project_name = meta.project_name
        log_dir = run_dir.parent.parent
        instance = cls.__new__(cls)
        instance.run_id = meta.run_id
        instance._lock = threading.Lock()
        instance._run_dir = run_dir
        instance.meta = meta
        instance.meta.outcome = "in_progress"
        instance._files = {
            "proposals": open(run_dir / "proposals.jsonl", "a"),
            "evaluations": open(run_dir / "evaluations.jsonl", "a"),
            "diagnoses": open(run_dir / "diagnoses.jsonl", "a"),
        }
        return instance

    def last_cycle(self) -> int:
        """Return the highest cycle index already logged (for resumption)."""
        return self.meta.total_cycles

    # ------------------------------------------------------------------
    # Analysis helpers
    # ------------------------------------------------------------------

    def iter_records(self, kind: str) -> Iterator[dict[str, Any]]:
        """Stream records from proposals / evaluations / diagnoses."""
        path = self._run_dir / f"{kind}.jsonl"
        if not path.exists():
            return
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def failure_summary(self) -> dict[str, int]:
        """Count failures grouped by error_message prefix (first 80 chars)."""
        counts: dict[str, int] = {}
        for rec in self.iter_records("evaluations"):
            if not rec["success"]:
                key = (rec.get("error_message") or rec.get("counterexample") or "unknown")[:80]
                counts[key] = counts.get(key, 0) + 1
        return counts

    @staticmethod
    def compare_runs(run_dirs: list[str | Path]) -> list[dict[str, Any]]:
        """Load metadata from multiple runs for side-by-side comparison."""
        rows: list[dict[str, Any]] = []
        for d in run_dirs:
            meta_path = Path(d) / "meta.json"
            if meta_path.exists():
                rows.append(json.loads(meta_path.read_text()))
        rows.sort(key=lambda r: r.get("started_at", 0))
        return rows

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append(self, kind: str, record: dict[str, Any]) -> None:
        fh = self._files[kind]
        fh.write(json.dumps(record) + "\n")
        fh.flush()

    def _write_meta(self) -> None:
        (self._run_dir / "meta.json").write_text(json.dumps(asdict(self.meta), indent=2))

    def __enter__(self) -> "RunLogger":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        outcome = "error" if exc_type else "success"
        self.close(outcome=outcome)
