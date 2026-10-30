"""
Issue selection scoring algorithm for the autonomous GitHub issue-fixing agent.

Produces a 0-100 fixability score for any GitHub issue.
See docs/master_plan.md §P1 for the full rubric rationale.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Issue:
    number: int
    title: str
    body: str
    labels: list[str]
    created_at: datetime
    updated_at: datetime
    comment_count: int
    assignee: str | None
    milestone: str | None
    linked_prs: list["PR"] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)
    thumbs_up: int = 0
    maintainer_replied: bool = False
    maintainer_replied_recent: bool = False  # within 14 days

    @property
    def age_days(self) -> int:
        return (datetime.now(timezone.utc) - self.created_at).days

    @property
    def label_set(self) -> set[str]:
        return {l.lower() for l in self.labels}

    @property
    def has_reproduction_steps(self) -> bool:
        keywords = ["steps to reproduce", "to reproduce", "how to reproduce",
                    "minimal reproducer", "reproduction", "repro"]
        return any(k in self.body.lower() for k in keywords)

    @property
    def has_error_message(self) -> bool:
        return "traceback" in self.body.lower() or "error:" in self.body.lower()

    @property
    def has_expected_vs_actual(self) -> bool:
        return ("expected" in self.body.lower() and
                ("actual" in self.body.lower() or "got" in self.body.lower()))


@dataclass
class PR:
    number: int
    state: Literal["open", "closed", "merged"]
    updated_at: datetime
    ci_status: Literal["passing", "failing_tests", "failing_lint", "no_ci", "pending"] = "no_ci"
    files_changed: int = 0
    fixes_issue: bool = False


@dataclass
class Repo:
    owner: str
    name: str
    language: str
    activity_level: Literal["high", "medium", "low", "archived"] = "medium"
    maintainers: set[str] = field(default_factory=set)

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass
class ScoredIssue:
    issue: Issue
    score: float
    tier: Literal["HIGH", "MEDIUM", "LOW"]
    reject_reason: str | None = None


# ---------------------------------------------------------------------------
# Sub-formula helpers
# ---------------------------------------------------------------------------

def _age_delta(days: int) -> float:
    if days < 7:    return 5.0
    if days < 30:   return 3.0
    if days < 90:   return 0.0
    if days < 365:  return -3.0
    if days < 730:  return -7.0
    return -12.0


def _comment_delta(n: int) -> float:
    if n == 0:   return 0.0
    if n <= 3:   return 2.0
    if n <= 10:  return -3.0
    if n <= 25:  return -8.0
    return -15.0


def _body_length_delta(chars: int) -> float:
    if chars < 50:    return -8.0
    if chars < 200:   return -3.0
    if chars < 2000:  return 4.0
    if chars < 5000:  return 0.0
    return -5.0


def _file_count_delta(n: int) -> float:
    if n == 0:   return 0.0
    if n <= 2:   return 8.0
    if n <= 5:   return 4.0
    if n <= 15:  return 0.0
    if n <= 40:  return -6.0
    return -15.0


_CI_DELTA = {
    "passing":       5.0,
    "no_ci":         0.0,
    "pending":       0.0,
    "failing_tests": -5.0,
    "failing_lint":  -2.0,
}

_REPO_ACTIVITY_DELTA = {
    "high":      3.0,
    "medium":    0.0,
    "low":      -5.0,
    "archived": -50.0,
}


# ---------------------------------------------------------------------------
# Language-specific modifiers
# ---------------------------------------------------------------------------

def _language_modifier(issue: Issue, repo: Repo) -> float:
    lang = repo.language.lower()
    if lang == "python" and "cpython" in repo.name.lower():
        return _cpython_modifier(issue)
    if lang == "rust":
        return _rust_modifier(issue)
    if lang == "c":
        return _c_modifier(issue)
    if lang in ("lua", "c"):  # neovim
        return _neovim_modifier(issue)
    if lang == "python":
        return _django_modifier(issue)
    return 0.0


def _cpython_modifier(issue: Issue) -> float:
    delta = 0.0
    body_lower = issue.body.lower()
    files = issue.affected_files
    if any(f.startswith("Lib/") and not f.startswith("Lib/test") for f in files):
        delta += 3.0
    if any(f.endswith(".c") or f.endswith(".h") for f in files):
        delta -= 12.0
    if "segfault" in body_lower or "segmentation fault" in body_lower:
        delta -= 15.0
    if 'File "' in issue.body and "cpython/Objects" not in issue.body:
        delta += 4.0
    return delta


def _rust_modifier(issue: Issue) -> float:
    delta = 0.0
    labels = issue.label_set
    if "e-mentor"      in labels: delta += 8.0
    if "e-easy"        in labels: delta += 5.0
    if "t-libs"        in labels: delta += 4.0
    if "a-diagnostics" in labels: delta += 6.0
    if "t-rustdoc"     in labels: delta += 3.0
    if "t-compiler"    in labels: delta -= 8.0
    if "t-lang"        in labels: delta -= 8.0
    if "requires-nightly" in labels: delta -= 6.0
    if "ice"           in labels: delta -= 4.0
    return delta


def _c_modifier(issue: Issue) -> float:
    delta = 0.0
    body_lower = issue.body.lower()
    files = issue.affected_files
    if any("tool_" in f for f in files): delta += 6.0
    if "valgrind" in body_lower and "invalid read" in body_lower: delta += 4.0
    if any(k in body_lower for k in ["openssl", "tls", "ssl", "nss", "gnutls"]): delta -= 8.0
    if any(k in body_lower for k in ["thread", "race condition", "mutex"]): delta -= 10.0
    if any(k in body_lower for k in ["http/3", "quic", "ngtcp2"]): delta -= 12.0
    if issue.body.count("curl ") >= 2: delta += 5.0
    return delta


def _neovim_modifier(issue: Issue) -> float:
    delta = 0.0
    files = issue.affected_files
    labels = issue.label_set
    lua_files = [f for f in files if f.startswith("runtime/") or f.endswith(".lua")]
    c_files   = [f for f in files if f.endswith(".c") or f.endswith(".h")]
    if lua_files and not c_files:   delta += 8.0
    if c_files and not lua_files:   delta -= 5.0
    if lua_files and c_files:       delta -= 12.0
    if "lsp" in labels:             delta += 2.0
    if "treesitter" in labels:      delta -= 3.0
    if "regression" in labels:      delta += 3.0
    return delta


def _django_modifier(issue: Issue) -> float:
    delta = 0.0
    labels = issue.label_set
    files  = issue.affected_files
    body_lower = issue.body.lower()
    if "easy pickings" in labels:   delta += 12.0
    if "async" in labels:           delta -= 8.0
    if "migrations" in labels:      delta -= 6.0
    if any(k in body_lower for k in ["annotate", "aggregate", "subquery", "prefetch_related"]):
        delta -= 5.0
    if any(f.startswith("django/utils/") for f in files): delta += 5.0
    if any(f.startswith("django/db/migrations/") for f in files): delta -= 8.0
    if "SELECT" in issue.body or "str(qs.query)" in issue.body: delta += 5.0
    return delta


# ---------------------------------------------------------------------------
# Hard exclusion rules
# ---------------------------------------------------------------------------

_HARD_EXCLUSION_LABELS = {
    "security", "blocked", "wontfix", "duplicate", "needs-design",
    "do-not-merge", "stale",
}

_QUESTION_PREFIXES = ("how ", "why ", "can ", "should ", "is ", "what ")


def _hard_exclude(issue: Issue, repo: Repo) -> str | None:
    """Return a rejection reason string, or None if the issue passes."""
    if repo.activity_level == "archived":
        return "archived repo"
    if issue.assignee:
        return "already assigned"
    if issue.label_set & {"security", "blocked", "wontfix", "duplicate", "do-not-merge"}:
        matching = issue.label_set & {"security", "blocked", "wontfix", "duplicate", "do-not-merge"}
        return f"label: {next(iter(matching))}"
    if any(pr.state == "merged" and pr.fixes_issue for pr in issue.linked_prs):
        return "already fixed (merged PR)"
    if len(issue.body.strip()) < 30:
        return "body too short"
    title_lower = issue.title.lower()
    if any(title_lower.startswith(p) for p in _QUESTION_PREFIXES):
        return "question/support request"
    hardware_kw = {"arm", "mips", "risc-v", "embedded", "stm32", "raspberry pi",
                   "arduino", "cuda", "tpu"}
    if any(kw in (issue.title + " " + issue.body).lower() for kw in hardware_kw):
        return "requires hardware"
    return None


# ---------------------------------------------------------------------------
# Main scorer
# ---------------------------------------------------------------------------

ATTEMPT_THRESHOLD = 60.0
TIER_HIGH         = 80.0
TIER_MEDIUM       = 65.0


def score_issue(issue: Issue, repo: Repo) -> ScoredIssue:
    """Score a single issue for fixability. Returns a ScoredIssue."""
    reject = _hard_exclude(issue, repo)
    if reject:
        return ScoredIssue(issue=issue, score=0.0, tier="LOW", reject_reason=reject)

    s = 50.0

    # --- Label signals ---
    labels = issue.label_set
    if "good first issue" in labels:  s += 12.0
    if "bug" in labels:               s += 8.0
    if any(l in labels for l in ["easy", "beginner", "e-easy"]): s += 10.0
    if any(l in labels for l in ["feature", "enhancement"]):     s -= 8.0
    if "needs-design" in labels:      s -= 15.0
    if "stale" in labels:             s -= 10.0
    if "milestone" in labels:         s -= 5.0

    # --- Temporal signals ---
    s += _age_delta(issue.age_days)
    s += _comment_delta(issue.comment_count)

    # --- Content quality ---
    if issue.has_reproduction_steps:  s += 10.0
    if issue.has_error_message:       s += 7.0
    if issue.has_expected_vs_actual:  s += 5.0
    s += _body_length_delta(len(issue.body))

    # --- PR linkage ---
    open_prs = [pr for pr in issue.linked_prs if pr.state == "open"]
    s -= 6.0 * len(open_prs)
    if open_prs:
        latest = max(open_prs, key=lambda p: p.updated_at)
        s += _CI_DELTA.get(latest.ci_status, 0.0)
        s += _file_count_delta(latest.files_changed)

    # --- Ownership & activity ---
    if issue.milestone:               s -= 5.0
    if issue.maintainer_replied:      s += 3.0
    if issue.maintainer_replied_recent: s += 5.0
    s += min(issue.thumbs_up * 0.05, 5.0)

    # --- Repo-level ---
    s += _REPO_ACTIVITY_DELTA.get(repo.activity_level, 0.0)

    # --- Language-specific ---
    s += _language_modifier(issue, repo)

    s = max(0.0, min(100.0, s))

    if s < ATTEMPT_THRESHOLD:
        return ScoredIssue(issue=issue, score=s, tier="LOW", reject_reason="below threshold")

    tier: Literal["HIGH", "MEDIUM", "LOW"] = (
        "HIGH"   if s >= TIER_HIGH   else
        "MEDIUM" if s >= TIER_MEDIUM else
        "LOW"
    )
    return ScoredIssue(issue=issue, score=s, tier=tier)


def select_issues(issues: list[Issue], repo: Repo) -> list[ScoredIssue]:
    """Score and rank all issues for a repo. Returns only actionable ones."""
    results = [score_issue(issue, repo) for issue in issues]
    actionable = [r for r in results if r.reject_reason is None]
    actionable.sort(key=lambda x: (-x.score, x.issue.age_days))
    return actionable
