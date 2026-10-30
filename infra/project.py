"""
Project ABC — abstract base class that all 9 projects implement.

Each project must provide:
  get_next_task() -> Task
  execute(task)   -> Result
  evaluate(result) -> Score
  is_done()       -> bool
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Task:
    task_id: str
    description: str
    priority: int = 0                        # higher = more urgent
    metadata: dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other: "Task") -> bool:
        return self.priority > other.priority  # max-heap semantics


@dataclass
class Result:
    task_id: str
    output: str
    success: bool
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Score:
    task_id: str
    value: float          # 0.0 – 1.0
    passed: bool
    feedback: str = ""
    breakdown: dict[str, float] = field(default_factory=dict)


class Project(ABC):
    """
    Abstract base that every one of the 9 research projects inherits from.

    The main loop calls these methods in this order::

        while not project.is_done():
            task   = project.get_next_task()
            result = project.execute(task)
            score  = project.evaluate(result)
            # main loop handles budget tracking and logging

    Projects should NOT manage their own run loop — that is the job of
    IterativeRefinementLoop + main.py.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.project_id: str = config["project_id"]
        self.priority: int = config.get("priority", 0)
        self._tasks_completed: int = 0
        self._tasks_failed: int = 0

    # ------------------------------------------------------------------
    # Required methods
    # ------------------------------------------------------------------

    @abstractmethod
    def get_next_task(self) -> Optional[Task]:
        """
        Return the next Task to work on, or None if no tasks remain.

        Implementations should be idempotent — calling this when the
        previous task has not yet been executed is safe.
        """

    @abstractmethod
    def execute(self, task: Task) -> Result:
        """
        Execute *task* and return a Result.

        This is where the IterativeRefinementLoop is invoked.
        Implementations should not swallow exceptions — let them
        propagate so the main loop can decide on retry vs. abort.
        """

    @abstractmethod
    def evaluate(self, result: Result) -> Score:
        """
        Score a completed Result.

        Must be deterministic given the same result so that resumption
        produces consistent comparisons.
        """

    @abstractmethod
    def is_done(self) -> bool:
        """
        Return True when the project has no more work to do.

        This may be due to all tasks completing, budget exhaustion,
        or a project-specific stopping condition.
        """

    # ------------------------------------------------------------------
    # Optional hooks (override as needed)
    # ------------------------------------------------------------------

    def on_task_success(self, task: Task, result: Result, score: Score) -> None:
        """Called by the main loop after a successful task + positive score."""
        self._tasks_completed += 1

    def on_task_failure(self, task: Task, result: Result, score: Score) -> None:
        """Called by the main loop after a task that scored below threshold."""
        self._tasks_failed += 1

    def daily_summary(self) -> dict[str, Any]:
        """Return a dict suitable for inclusion in the daily progress report."""
        return {
            "project_id": self.project_id,
            "priority": self.priority,
            "tasks_completed": self._tasks_completed,
            "tasks_failed": self._tasks_failed,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"{type(self).__name__}(id={self.project_id!r}, priority={self.priority})"
