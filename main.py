"""
main.py — master orchestrator for all 9 research projects.

Loads all projects, runs them in priority order, manages the global token
budget, and generates a daily progress report.

Usage::

    python main.py --config config.yaml [--resume] [--project P7]
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from infra.logger import RunLogger
from infra.loop import IterativeRefinementLoop, LoopConfig
from infra.oracle import (
    Alive2Oracle,
    FormalOracleInterface,
    Lean4Oracle,
    OracleResult,
    TLCOracle,
    Z3Oracle,
)
from infra.project import Project, Result, Score, Task


# ---------------------------------------------------------------------------
# Global budget tracker
# ---------------------------------------------------------------------------

class GlobalBudget:
    def __init__(self, max_prompt: int, max_completion: int) -> None:
        self.max_prompt = max_prompt
        self.max_completion = max_completion
        self.used_prompt = 0
        self.used_completion = 0

    def consume(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.used_prompt += prompt_tokens
        self.used_completion += completion_tokens

    @property
    def prompt_exhausted(self) -> bool:
        return self.used_prompt >= self.max_prompt

    @property
    def completion_exhausted(self) -> bool:
        return self.used_completion >= self.max_completion

    @property
    def exhausted(self) -> bool:
        return self.prompt_exhausted or self.completion_exhausted

    def remaining_prompt(self) -> int:
        return max(0, self.max_prompt - self.used_prompt)

    def remaining_completion(self) -> int:
        return max(0, self.max_completion - self.used_completion)

    def summary(self) -> dict[str, Any]:
        return {
            "used_prompt_tokens": self.used_prompt,
            "used_completion_tokens": self.used_completion,
            "remaining_prompt_tokens": self.remaining_prompt(),
            "remaining_completion_tokens": self.remaining_completion(),
            "prompt_pct": round(100 * self.used_prompt / self.max_prompt, 1),
            "completion_pct": round(100 * self.used_completion / self.max_completion, 1),
        }


# ---------------------------------------------------------------------------
# Oracle factory
# ---------------------------------------------------------------------------

def build_oracle(oracle_name: str, oracle_cfg: dict[str, Any]) -> FormalOracleInterface:
    cfg = oracle_cfg.get(oracle_name, {})
    if oracle_name == "lean4":
        return Lean4Oracle(
            lean_bin=cfg.get("lean_bin", "lean"),
            timeout=cfg.get("timeout_seconds", 120),
        )
    if oracle_name == "tlc":
        return TLCOracle(
            tlc_jar=cfg.get("tlc_jar", "tla2tools.jar"),
            timeout=cfg.get("timeout_seconds", 300),
        )
    if oracle_name == "z3":
        return Z3Oracle(
            use_python_api=cfg.get("use_python_api", True),
            timeout=cfg.get("timeout_seconds", 60),
        )
    if oracle_name == "alive2":
        return Alive2Oracle(
            alive_tv_bin=cfg.get("alive_tv_bin", "alive-tv"),
            timeout=cfg.get("timeout_seconds", 120),
        )
    raise ValueError(f"Unknown oracle: {oracle_name!r}")


# ---------------------------------------------------------------------------
# LLM backend factory (minimal stub — replace with real implementation)
# ---------------------------------------------------------------------------

class OpenAIBackend:
    """Thin wrapper around the OpenAI chat completions API."""

    def __init__(self, model: str, api_key: str, timeout: int = 120) -> None:
        self.model = model
        self.timeout = timeout
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key, timeout=timeout)
        except ImportError:
            raise RuntimeError("openai package not installed: pip install openai")

    def complete(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> tuple[str, int, int]:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = response.choices[0].message.content or ""
        p_tok = response.usage.prompt_tokens
        c_tok = response.usage.completion_tokens
        return text, p_tok, c_tok


# ---------------------------------------------------------------------------
# Project loader
# ---------------------------------------------------------------------------

def load_projects(
    cfg: dict[str, Any],
    filter_project: str | None = None,
) -> list[Project]:
    projects: list[Project] = []
    for proj_cfg in cfg["projects"]:
        if not proj_cfg.get("enabled", True):
            continue
        if filter_project and proj_cfg["project_id"] != filter_project:
            continue
        module_path, class_name = proj_cfg["class"].rsplit(".", 1)
        module = importlib.import_module(module_path)
        klass = getattr(module, class_name)
        projects.append(klass(proj_cfg))
    # Sort descending by priority
    projects.sort(key=lambda p: p.priority, reverse=True)
    return projects


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_daily_report(
    project_summaries: list[dict[str, Any]],
    budget: GlobalBudget,
    elapsed: float,
    output_dir: Path,
    fmt: str = "json",
) -> Path:
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(elapsed, 2),
        "budget": budget.summary(),
        "projects": project_summaries,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = time.strftime("%Y%m%d")

    if fmt == "json":
        out_path = output_dir / f"report_{date_str}.json"
        out_path.write_text(json.dumps(report, indent=2))
    elif fmt in ("html", "markdown"):
        out_path = output_dir / f"report_{date_str}.{'html' if fmt == 'html' else 'md'}"
        out_path.write_text(_render_report(report, fmt=fmt))
    else:
        raise ValueError(f"Unknown report format: {fmt!r}")

    return out_path


def _render_report(report: dict[str, Any], fmt: str) -> str:
    lines: list[str] = []
    b = report["budget"]
    if fmt == "markdown":
        lines.append(f"# Daily Progress Report — {report['generated_at']}\n")
        lines.append(f"**Elapsed:** {report['elapsed_seconds']:.0f}s  ")
        lines.append(f"**Prompt tokens:** {b['used_prompt_tokens']:,} / {b['used_prompt_tokens'] + b['remaining_prompt_tokens']:,} ({b['prompt_pct']}%)  ")
        lines.append(f"**Completion tokens:** {b['used_completion_tokens']:,} ({b['completion_pct']}%)\n")
        lines.append("## Project Results\n")
        lines.append("| Project | Priority | Completed | Failed |")
        lines.append("|---------|----------|-----------|--------|")
        for p in report["projects"]:
            lines.append(f"| {p['project_id']} | {p['priority']} | {p['tasks_completed']} | {p['tasks_failed']} |")
    else:  # html
        rows = "".join(
            f"<tr><td>{p['project_id']}</td><td>{p['priority']}</td>"
            f"<td>{p['tasks_completed']}</td><td>{p['tasks_failed']}</td></tr>"
            for p in report["projects"]
        )
        lines.append(f"""<!DOCTYPE html><html><head><title>Daily Report</title></head><body>
<h1>Daily Progress Report — {report['generated_at']}</h1>
<p>Elapsed: {report['elapsed_seconds']:.0f}s &nbsp;|&nbsp;
Prompt: {b['used_prompt_tokens']:,} tokens ({b['prompt_pct']}%) &nbsp;|&nbsp;
Completion: {b['used_completion_tokens']:,} tokens ({b['completion_pct']}%)</p>
<table border="1" cellpadding="4"><thead>
<tr><th>Project</th><th>Priority</th><th>Completed</th><th>Failed</th></tr>
</thead><tbody>{rows}</tbody></table>
</body></html>""")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(cfg: dict[str, Any], filter_project: str | None = None) -> None:
    start = time.perf_counter()

    gb_cfg = cfg["global"]
    budget = GlobalBudget(
        max_prompt=gb_cfg["token_budget"]["max_prompt_tokens"],
        max_completion=gb_cfg["token_budget"]["max_completion_tokens"],
    )

    llm_cfg = gb_cfg["llm"]
    api_key = os.path.expandvars(llm_cfg.get("api_key", ""))
    llm = OpenAIBackend(
        model=llm_cfg["model"],
        api_key=api_key,
        timeout=llm_cfg.get("timeout_seconds", 120),
    )

    projects = load_projects(cfg, filter_project=filter_project)
    if not projects:
        print("No projects to run.", file=sys.stderr)
        return

    log_dir = Path(gb_cfg["logging"]["log_dir"])
    oracle_cfg = cfg.get("oracles", {})
    summaries: list[dict[str, Any]] = []

    for project in projects:
        if budget.exhausted:
            print(f"[budget] Global budget exhausted; skipping {project.project_id}")
            break

        proj_cfg = next(p for p in cfg["projects"] if p["project_id"] == project.project_id)
        oracle_name = proj_cfg.get("oracle", "z3")
        oracle = build_oracle(oracle_name, oracle_cfg)

        loop_cfg_raw = proj_cfg.get("loop", {})
        loop_config = LoopConfig(
            max_cycles=loop_cfg_raw.get("max_cycles", 20),
            max_prompt_tokens=gb_cfg["token_budget"]["per_project_prompt_tokens"],
            max_completion_tokens=gb_cfg["token_budget"]["per_project_completion_tokens"],
            convergence_score=loop_cfg_raw.get("convergence_score", 1.0),
            patience=loop_cfg_raw.get("patience", 3),
            proposal_temperature=loop_cfg_raw.get("proposal_temperature", 0.7),
            diagnosis_temperature=loop_cfg_raw.get("diagnosis_temperature", 0.3),
        )

        with RunLogger(log_dir, project.project_id, proj_cfg) as logger:
            print(f"\n[{project.project_id}] Starting (priority={project.priority})")
            while not project.is_done():
                if budget.exhausted:
                    print(f"[{project.project_id}] Budget exhausted mid-project")
                    break

                task: Task | None = project.get_next_task()
                if task is None:
                    break

                loop = IterativeRefinementLoop(
                    llm=llm,
                    oracle=oracle,
                    logger=logger,
                    config=loop_config,
                )
                loop_result = loop.run(initial_prompt=task.description)

                result = Result(
                    task_id=task.task_id,
                    output=loop_result.best_proposal,
                    success=loop_result.success,
                    metadata={"stop_reason": loop_result.stop_reason,
                              "cycles": loop_result.cycles_run},
                )
                score = project.evaluate(result)

                budget.consume(
                    loop_result.total_prompt_tokens,
                    loop_result.total_completion_tokens,
                )

                if score.passed:
                    project.on_task_success(task, result, score)
                    print(f"  ✓ {task.task_id} score={score.value:.2f} ({loop_result.stop_reason})")
                else:
                    project.on_task_failure(task, result, score)
                    print(f"  ✗ {task.task_id} score={score.value:.2f} ({loop_result.stop_reason})")

        summaries.append(project.daily_summary())

    elapsed = time.perf_counter() - start
    report_cfg = gb_cfg.get("report", {})
    report_path = generate_daily_report(
        summaries,
        budget,
        elapsed,
        output_dir=Path(report_cfg.get("output_dir", "./reports")),
        fmt=report_cfg.get("format", "json"),
    )
    print(f"\n[report] Written to {report_path}")
    print(f"[budget] {budget.summary()}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _resolve_env(value: Any) -> Any:
    """Recursively expand ${VAR} in string config values."""
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    return value


def load_config(path: str) -> dict[str, Any]:
    with open(path) as f:
        raw = yaml.safe_load(f)
    return _resolve_env(raw)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Agent Research Orchestrator")
    parser.add_argument("--config", default="config.yaml", help="Path to config YAML")
    parser.add_argument("--project", default=None, help="Run only this project ID")
    args = parser.parse_args()

    cfg = load_config(args.config)
    run(cfg, filter_project=args.project)


if __name__ == "__main__":
    main()
