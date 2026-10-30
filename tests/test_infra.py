"""
Unit and integration tests for the shared infrastructure.

Run with: pytest tests/ -v

No external processes or real tokens are used.
"""

from __future__ import annotations

import json
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest

from infra.loop import IterativeRefinementLoop, LoopConfig
from infra.logger import RunLogger
from infra.mocks import MockLLM, MockOracle
from infra.oracle import OracleResult, Z3Oracle
from infra.project import Project, Result, Score, Task
from infra.context import CodebaseContextManager


# =============================================================================
# OracleResult
# =============================================================================

class TestOracleResult:
    def test_is_verified_true_when_success_and_no_counterexample(self):
        r = OracleResult(success=True)
        assert r.is_verified is True

    def test_is_verified_false_when_counterexample_present(self):
        r = OracleResult(success=True, counterexample="cex")
        assert r.is_verified is False

    def test_is_verified_false_when_not_success(self):
        r = OracleResult(success=False)
        assert r.is_verified is False


# =============================================================================
# MockOracle
# =============================================================================

class TestMockOracle:
    def test_returns_preset_results_round_robin(self):
        results = [
            OracleResult(success=False, error_message="err"),
            OracleResult(success=True),
        ]
        oracle = MockOracle(results=results)
        assert oracle.check("a").success is False
        assert oracle.check("b").success is True
        # wraps around
        assert oracle.check("c").success is False

    def test_records_calls(self):
        oracle = MockOracle()
        oracle.check("hello")
        oracle.check("world")
        assert oracle.calls == ["hello", "world"]

    def test_is_available(self):
        assert MockOracle().is_available() is True


# =============================================================================
# MockLLM
# =============================================================================

class TestMockLLM:
    def test_returns_fixed_response(self):
        llm = MockLLM(response="proof", prompt_tokens=10, completion_tokens=5)
        text, p, c = llm.complete("prove it")
        assert text == "proof"
        assert p == 10
        assert c == 5

    def test_custom_respond_callable(self):
        llm = MockLLM(respond=lambda prompt: (f"echo:{prompt}", 1, 1))
        text, _, _ = llm.complete("hi")
        assert text == "echo:hi"

    def test_records_calls(self):
        llm = MockLLM()
        llm.complete("a")
        llm.complete("b")
        assert llm.calls == ["a", "b"]


# =============================================================================
# RunLogger
# =============================================================================

class TestRunLogger:
    def setup_method(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.log_dir = self._tmpdir.name

    def teardown_method(self):
        self._tmpdir.cleanup()

    def _make_logger(self, project="test") -> RunLogger:
        return RunLogger(self.log_dir, project, config={"project_id": project})

    def test_creates_run_directory(self):
        with self._make_logger() as logger:
            assert (Path(self.log_dir) / "test" / logger.run_id).is_dir()

    def test_log_proposal_returns_id(self):
        with self._make_logger() as logger:
            pid = logger.log_proposal(0, "proposal text", prompt_tokens=42)
        assert pid.startswith(logger.run_id)

    def test_meta_records_tokens(self):
        with self._make_logger() as logger:
            logger.log_proposal(0, "p", prompt_tokens=100)
            logger.log_diagnosis("x", 0, "diag", completion_tokens=50)
        assert logger.meta.total_prompt_tokens == 100
        assert logger.meta.total_completion_tokens == 50

    def test_evaluation_records_appended(self):
        with self._make_logger() as logger:
            run_dir = logger._run_dir
            logger.log_evaluation("id1", 0, True, 1.0, "MockOracle")
        records = list(logger.iter_records("evaluations"))
        assert len(records) == 1
        assert records[0]["success"] is True

    def test_failure_summary(self):
        with self._make_logger() as logger:
            logger.log_evaluation("id1", 0, False, 0.0, "MockOracle", error_message="syntax error")
            logger.log_evaluation("id2", 1, False, 0.0, "MockOracle", error_message="syntax error")
            logger.log_evaluation("id3", 2, True, 1.0, "MockOracle")
        summary = logger.failure_summary()
        assert summary.get("syntax error") == 2

    def test_meta_outcome_on_close(self):
        logger = self._make_logger()
        logger.close(outcome="success")
        meta = json.loads((logger._run_dir / "meta.json").read_text())
        assert meta["outcome"] == "success"

    def test_context_manager_sets_outcome_error_on_exception(self):
        with pytest.raises(ValueError):
            with self._make_logger() as logger:
                run_dir = logger._run_dir
                raise ValueError("boom")
        meta = json.loads((run_dir / "meta.json").read_text())
        assert meta["outcome"] == "error"

    def test_resume_reopens_run(self):
        with self._make_logger() as logger:
            run_dir = logger._run_dir
            logger.log_proposal(0, "p", prompt_tokens=5)

        resumed = RunLogger.resume(run_dir)
        resumed.log_proposal(1, "p2", prompt_tokens=7)
        resumed.close()
        records = list(resumed.iter_records("proposals"))
        assert len(records) == 2


# =============================================================================
# IterativeRefinementLoop
# =============================================================================

class TestIterativeRefinementLoop:
    def setup_method(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def teardown_method(self):
        self._tmpdir.cleanup()

    def _make_loop(
        self,
        llm=None,
        oracle=None,
        config: Optional[LoopConfig] = None,
    ) -> tuple[IterativeRefinementLoop, RunLogger]:
        llm = llm or MockLLM()
        oracle = oracle or MockOracle()
        logger = RunLogger(self._tmpdir.name, "test", {})
        loop = IterativeRefinementLoop(llm=llm, oracle=oracle, logger=logger, config=config)
        return loop, logger

    def test_converges_on_first_success(self):
        oracle = MockOracle(results=[OracleResult(success=True)])
        loop, _ = self._make_loop(oracle=oracle, config=LoopConfig(max_cycles=5))
        result = loop.run("prove it")
        assert result.success is True
        assert result.cycles_run == 1
        assert result.stop_reason == "converged"

    def test_runs_multiple_cycles_before_success(self):
        oracle = MockOracle(results=[
            OracleResult(success=False, error_message="e1"),
            OracleResult(success=False, error_message="e2"),
            OracleResult(success=True),
        ])
        # unique response each call so cycle detection never fires
        counter = {"n": 0}
        def _unique(p):
            counter["n"] += 1
            return f"proposal_{counter['n']}", 10, 5
        loop, _ = self._make_loop(
            llm=MockLLM(respond=_unique),
            oracle=oracle,
            config=LoopConfig(max_cycles=10),
        )
        result = loop.run("prove it")
        assert result.success is True
        assert result.cycles_run == 3

    def test_stops_at_max_cycles(self):
        oracle = MockOracle(results=[OracleResult(success=False, error_message="e")])
        counter = {"n": 0}
        def _unique(p):
            counter["n"] += 1
            return f"proposal_{counter['n']}", 10, 5
        loop, _ = self._make_loop(
            llm=MockLLM(respond=_unique),
            oracle=oracle,
            config=LoopConfig(max_cycles=3, patience=100),
        )
        result = loop.run("prove it")
        assert result.stop_reason == "max_cycles"
        assert result.cycles_run == 3

    def test_patience_early_stop(self):
        oracle = MockOracle(results=[OracleResult(success=False, error_message="e")])
        counter = {"n": 0}
        def _unique(p):
            counter["n"] += 1
            return f"proposal_{counter['n']}", 10, 5
        loop, _ = self._make_loop(
            llm=MockLLM(respond=_unique),
            oracle=oracle,
            config=LoopConfig(max_cycles=20, patience=2),
        )
        result = loop.run("prove it")
        assert result.stop_reason == "patience"
        assert result.cycles_run <= 4

    def test_cycle_detection_stops_loop(self):
        # Same proposal every time → cycle detected after window
        llm = MockLLM(response="identical_proposal")
        oracle = MockOracle(results=[OracleResult(success=False, error_message="e")])
        loop, _ = self._make_loop(
            llm=llm,
            oracle=oracle,
            config=LoopConfig(max_cycles=20, cycle_detection_window=3),
        )
        result = loop.run("prove it")
        assert result.stop_reason == "cycle_detected"

    def test_prompt_budget_stops_loop(self):
        counter = {"n": 0}
        def _unique(p):
            counter["n"] += 1
            return f"proposal_{counter['n']}", 100_000, 5
        llm = MockLLM(respond=_unique)
        oracle = MockOracle(results=[OracleResult(success=False, error_message="e")])
        loop, _ = self._make_loop(
            llm=llm,
            oracle=oracle,
            config=LoopConfig(
                max_cycles=20,
                max_prompt_tokens=150_000,
                patience=100,
            ),
        )
        result = loop.run("prove it")
        assert result.stop_reason == "budget_prompt"

    def test_logs_are_written(self):
        oracle = MockOracle(results=[OracleResult(success=True)])
        loop, logger = self._make_loop(oracle=oracle, config=LoopConfig(max_cycles=5))
        loop.run("prove it")
        proposals = list(logger.iter_records("proposals"))
        evaluations = list(logger.iter_records("evaluations"))
        assert len(proposals) >= 1
        assert len(evaluations) >= 1
        logger.close()

    def test_best_proposal_is_tracked(self):
        oracle = MockOracle(results=[
            OracleResult(success=False, counterexample="cex"),
            OracleResult(success=True),
        ])
        counter = {"n": 0}
        def _unique(p):
            counter["n"] += 1
            return f"proposal_{counter['n']}", 10, 5
        loop, logger = self._make_loop(
            llm=MockLLM(respond=_unique),
            oracle=oracle,
            config=LoopConfig(max_cycles=5),
        )
        result = loop.run("task")
        assert result.best_score == 1.0
        logger.close()


# =============================================================================
# CodebaseContextManager
# =============================================================================

class TestCodebaseContextManager:
    def setup_method(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)

    def teardown_method(self):
        self._tmpdir.cleanup()

    def _write(self, rel_path: str, content: str) -> None:
        full = self.root / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(textwrap.dedent(content))

    def test_get_file_meta_python(self):
        self._write("foo.py", "x = 1\n")
        ctx = CodebaseContextManager(self.root)
        meta = ctx.get_file_meta("foo.py")
        assert meta.language == "python"
        assert meta.line_count == 1

    def test_get_symbols_python(self):
        self._write("foo.py", """\
            def greet(name: str) -> str:
                \"\"\"Say hello.\"\"\"
                return f"hi {name}"

            class Dog:
                \"\"\"A dog.\"\"\"
                pass
        """)
        ctx = CodebaseContextManager(self.root)
        syms = ctx.get_symbols("foo.py")
        names = {s.name for s in syms}
        assert "greet" in names
        assert "Dog" in names

    def test_get_source_caches_and_returns(self):
        self._write("bar.py", "y = 2\n")
        ctx = CodebaseContextManager(self.root)
        src = ctx.get_source("bar.py")
        assert "y = 2" in src
        assert ctx.cache_stats()["l4_files"] == 1

    def test_lru_eviction(self):
        for i in range(5):
            self._write(f"f{i}.py", f"x = {i}\n")
        ctx = CodebaseContextManager(self.root, max_l4_files=3)
        for i in range(5):
            ctx.get_source(f"f{i}.py")
        assert ctx.cache_stats()["l4_files"] == 3

    def test_scan_directory(self):
        self._write("a.py", "pass\n")
        self._write("sub/b.rs", "fn main() {}\n")
        ctx = CodebaseContextManager(self.root)
        paths = ctx.scan_directory()
        assert "a.py" in paths
        assert "sub/b.rs" in paths

    def test_callers_of(self):
        self._write("mod.py", """\
            def foo():
                bar()
                baz()

            def bar():
                pass

            def baz():
                pass
        """)
        ctx = CodebaseContextManager(self.root)
        called = ctx.callers_of("mod.py", "foo")
        assert "bar" in called
        assert "baz" in called

    def test_rust_symbol_extraction(self):
        self._write("lib.rs", """\
            pub fn add(a: i32, b: i32) -> i32 { a + b }
            pub struct Point { x: f64, y: f64 }
        """)
        ctx = CodebaseContextManager(self.root)
        syms = ctx.get_symbols("lib.rs")
        names = {s.name for s in syms}
        assert "add" in names
        assert "Point" in names

    def test_c_symbol_extraction(self):
        self._write("main.c", """\
            int add(int a, int b) {
                return a + b;
            }
        """)
        ctx = CodebaseContextManager(self.root)
        syms = ctx.get_symbols("main.c")
        assert any(s.name == "add" for s in syms)


# =============================================================================
# Project ABC enforcement
# =============================================================================

class TestProjectABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            Project({})  # type: ignore[abstract]

    def test_concrete_subclass_works(self):
        class ConcreteProject(Project):
            def get_next_task(self):
                return None
            def execute(self, task):
                return Result(task.task_id, "", True)
            def evaluate(self, result):
                return Score(result.task_id, 1.0, True)
            def is_done(self):
                return True

        p = ConcreteProject({"project_id": "X", "priority": 5})
        assert p.project_id == "X"
        assert p.is_done() is True

    def test_daily_summary(self):
        class P(Project):
            def get_next_task(self): return None
            def execute(self, t): return Result(t.task_id, "", True)
            def evaluate(self, r): return Score(r.task_id, 1.0, True)
            def is_done(self): return True

        p = P({"project_id": "T", "priority": 3})
        s = p.daily_summary()
        assert s["project_id"] == "T"
        assert "tasks_completed" in s


# =============================================================================
# Integration test: full loop without external calls
# =============================================================================

class TestIntegrationLoop:
    def setup_method(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def teardown_method(self):
        self._tmpdir.cleanup()

    def test_full_successful_run(self):
        """Full loop: 2 failures then success, checks logs + result."""
        oracle = MockOracle(results=[
            OracleResult(success=False, error_message="type mismatch"),
            OracleResult(success=False, counterexample="counter = 0"),
            OracleResult(success=True),
        ])
        llm = MockLLM(
            respond=lambda p: (f"attempt_{len(p)}", 50, 20),
        )
        logger = RunLogger(self._tmpdir.name, "integration", {})
        config = LoopConfig(max_cycles=10, patience=5)
        loop = IterativeRefinementLoop(llm=llm, oracle=oracle, logger=logger, config=config)

        result = loop.run("prove theorem X")

        assert result.success is True
        assert result.cycles_run == 3
        assert result.stop_reason == "converged"
        assert result.total_prompt_tokens == 3 * 50 + 2 * 50  # 3 proposals + 2 diagnoses
        assert result.total_completion_tokens == 3 * 20 + 2 * 20

        proposals = list(logger.iter_records("proposals"))
        evaluations = list(logger.iter_records("evaluations"))
        diagnoses = list(logger.iter_records("diagnoses"))
        assert len(proposals) == 3
        assert len(evaluations) == 3
        assert len(diagnoses) == 2
        logger.close()

    def test_full_budget_exhausted_run(self):
        oracle = MockOracle(results=[OracleResult(success=False, error_message="e")])
        counter = {"n": 0}
        def _unique(p):
            counter["n"] += 1
            return f"proposal_{counter['n']}", 60_000, 20_000
        llm = MockLLM(respond=_unique)
        logger = RunLogger(self._tmpdir.name, "budget_test", {})
        config = LoopConfig(
            max_cycles=20,
            max_prompt_tokens=100_000,
            max_completion_tokens=500_000,
            patience=50,
        )
        loop = IterativeRefinementLoop(llm=llm, oracle=oracle, logger=logger, config=config)
        result = loop.run("task")
        assert result.stop_reason == "budget_prompt"
        logger.close()
