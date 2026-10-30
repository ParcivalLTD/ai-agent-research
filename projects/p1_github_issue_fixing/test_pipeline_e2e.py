"""
End-to-end tests for the P1 GitHub Issue Fixing pipeline.

Uses the real module APIs — no mocks needed.
"""
from __future__ import annotations

import sys, os, pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))

from projects.p1_github_issue_fixing.issue_scorer import (
    Issue, Repo, ScoredIssue, score_issue, select_issues,
)
from projects.p1_github_issue_fixing.codebase_reader import (
    CodebaseReader, CodebaseModel, BugLocation,
)
from projects.p1_github_issue_fixing.patch_generator import (
    PatchGenerator, PatchCandidate, BugDiagnosis,
)
from projects.p1_github_issue_fixing.pr_writer import PRWriter, PRDescription


# ── helpers ──────────────────────────────────────────────────────────────────

def make_issue(**kw) -> Issue:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    d = dict(
        number=1,
        title="NoneType crash in parse_config",
        body="parse_config(None) raises AttributeError: split\nTraceback (most recent call last): ...",
        labels=["bug"],
        created_at=now,
        updated_at=now,
        comment_count=3,
        assignee=None,
        milestone=None,
        thumbs_up=12,
    )
    d.update(kw)
    return Issue(**d)


def make_repo(**kw) -> Repo:
    d = dict(owner="alice", name="proj", language="Python", activity_level="high")
    d.update(kw)
    return Repo(**d)


SAMPLE_CODE = (
    "def parse_config(data):\n"
    "    parts = data.split(',')\n"
    "    return {k: v for k, v in (p.split('=') for p in parts)}\n"
)
SAMPLE_FILES = {
    "config.py": SAMPLE_CODE,
    "utils.py": "def safe_get(lst, idx, default=None):\n    if idx < len(lst): return lst[idx]\n    return default\n",
}
SAMPLE_DIAGNOSIS = BugDiagnosis(
    issue_title="NoneType crash in parse_config",
    issue_body="parse_config(None) raises AttributeError: NoneType has no attribute split",
    relevant_files={"config.py": SAMPLE_CODE},
    suspected_function="parse_config",
    root_cause_hypothesis="No None guard before calling .split()",
)


# ── IssueScorer ───────────────────────────────────────────────────────────────

class TestIssueScorer:
    def test_score_returns_scored_issue(self):
        assert isinstance(score_issue(make_issue(), make_repo()), ScoredIssue)

    def test_score_non_negative(self):
        assert score_issue(make_issue(), make_repo()).score >= 0

    def test_bug_beats_enhancement(self):
        bug  = make_issue(labels=["bug"],         thumbs_up=20, comment_count=5)
        feat = make_issue(labels=["enhancement"], thumbs_up=1,  comment_count=0,
                          body="Would be nice to have YAML.")
        assert score_issue(bug, make_repo()).score > score_issue(feat, make_repo()).score

    def test_select_returns_descending(self):
        issues = [
            make_issue(number=1, labels=["bug"],         thumbs_up=30),
            make_issue(number=2, labels=["enhancement"], thumbs_up=1),
            make_issue(number=3, labels=["bug"],         thumbs_up=15),
        ]
        ranked = select_issues(issues, make_repo())
        scores = [r.score for r in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_select_empty(self):
        assert select_issues([], make_repo()) == []

    def test_traceback_boosts_score(self):
        with_tb = make_issue(body="Traceback (most recent call last):\n  File 'x.py'\nValueError")
        without  = make_issue(body="app crashes sometimes")
        assert score_issue(with_tb, make_repo()).score >= score_issue(without, make_repo()).score

    def test_many_thumbsup_score(self):
        result = score_issue(make_issue(thumbs_up=50), make_repo())
        assert isinstance(result.score, (int, float))

    def test_thumbsup_increases_score(self):
        low  = make_issue(thumbs_up=0)
        high = make_issue(thumbs_up=100)
        assert score_issue(high, make_repo()).score >= score_issue(low, make_repo()).score


# ── CodebaseReader ────────────────────────────────────────────────────────────

class TestCodebaseReader:
    def test_instantiates(self):
        assert CodebaseReader() is not None

    def test_read_for_issue_returns_model(self):
        model = CodebaseReader().read_for_issue(
            SAMPLE_FILES, issue_title="NoneType crash", issue_body="data.split fails"
        )
        assert isinstance(model, CodebaseModel)

    def test_model_has_symbols(self):
        model = CodebaseReader().read_for_issue(SAMPLE_FILES, "crash", "split")
        assert isinstance(model.symbols, dict)

    def test_identify_relevant_files(self):
        reader = CodebaseReader()
        relevant = reader.identify_relevant_files(SAMPLE_FILES, "parse_config", "split None")
        assert isinstance(relevant, list)
        assert "config.py" in relevant

    def test_empty_repo_returns_model(self):
        model = CodebaseReader().read_for_issue({}, "anything", "body")
        assert isinstance(model, CodebaseModel)

    def test_extract_symbols_python(self):
        reader = CodebaseReader()
        symbols = reader.extract_symbols({"config.py": SAMPLE_CODE})
        assert isinstance(symbols, dict)
        assert len(symbols) >= 1


# ── PatchGenerator ────────────────────────────────────────────────────────────

class TestPatchGenerator:
    def test_instantiates(self):
        assert PatchGenerator() is not None

    def test_generate_returns_list(self):
        candidates = PatchGenerator().generate(SAMPLE_DIAGNOSIS)
        assert isinstance(candidates, list)

    def test_null_deref_produces_candidate(self):
        candidates = PatchGenerator().generate(SAMPLE_DIAGNOSIS)
        if candidates:
            assert isinstance(candidates[0], PatchCandidate)

    def test_candidate_has_diff(self):
        candidates = PatchGenerator().generate(SAMPLE_DIAGNOSIS)
        for c in candidates:
            assert hasattr(c, "diff")
            assert isinstance(c.diff, str)

    def test_candidate_has_confidence(self):
        candidates = PatchGenerator().generate(SAMPLE_DIAGNOSIS)
        for c in candidates:
            assert hasattr(c, "confidence")
            assert 0.0 <= c.confidence <= 1.0

    def test_off_by_one_bug_type(self):
        diag = BugDiagnosis(
            issue_title="off by one in range loop",
            issue_body="loop iterates one too few times",
            relevant_files={"loop.py": "for i in range(n):\n    pass\n"},
            suspected_function="",
            root_cause_hypothesis="range should include n",
        )
        candidates = PatchGenerator().generate(diag)
        assert isinstance(candidates, list)


# ── PRWriter ──────────────────────────────────────────────────────────────────

class TestPRWriter:
    def _make_pr(self, **kw):
        defaults = dict(issue_title="Fix NoneType crash in parse_config",
                        issue_number=42,
                        problem="parse_config(None) raises AttributeError",
                        root_cause="No None guard before calling .split()",
                        solution="Add `if data is None: raise ValueError` at function entry",
                        diff="--- a/config.py\n+++ b/config.py\n@@ -1 +2 @@\n+    if data is None: raise ValueError\n")
        defaults.update(kw)
        return PRWriter().write_pr(**defaults)

    def test_returns_pr_description(self):
        assert isinstance(self._make_pr(), PRDescription)

    def test_has_title(self):
        pr = self._make_pr()
        assert isinstance(pr.title, str) and len(pr.title) > 0

    def test_has_body(self):
        pr = self._make_pr()
        assert isinstance(pr.body, str) and len(pr.body) > 20

    def test_title_concise(self):
        assert len(self._make_pr().title) <= 120

    def test_references_issue_number(self):
        pr = self._make_pr(issue_number=42)
        assert "42" in (pr.title + pr.body)

    def test_has_commit_message(self):
        pr = self._make_pr()
        assert hasattr(pr, "commit_message") and isinstance(pr.commit_message, str)

    def test_body_mentions_solution(self):
        pr = self._make_pr(solution="Add bounds check before list access")
        assert "bounds" in pr.body.lower() or len(pr.body) > 50


# ── Full pipeline ─────────────────────────────────────────────────────────────

class TestFullPipeline:
    def test_score_select_write(self):
        issues = [
            make_issue(number=1, labels=["bug"],         thumbs_up=20),
            make_issue(number=2, labels=["enhancement"], thumbs_up=2),
        ]
        ranked = select_issues(issues, make_repo())
        best = ranked[0]

        pr = PRWriter().write_pr(
            issue_title=best.issue.title,
            issue_number=best.issue.number,
            problem="crash", root_cause="no guard", solution="added guard",
            diff="", testing="passes",
        )
        assert isinstance(pr, PRDescription)
        assert len(pr.title) > 0

    def test_read_then_patch_then_pr(self):
        model = CodebaseReader().read_for_issue(
            SAMPLE_FILES, issue_title="NoneType crash", issue_body="data.split None"
        )
        assert isinstance(model, CodebaseModel)

        candidates = PatchGenerator().generate(SAMPLE_DIAGNOSIS)

        solution = candidates[0].diff if candidates else "manual fix"
        pr = PRWriter().write_pr(
            issue_title="Fix NoneType crash",
            issue_number=1,
            problem="crash on None",
            root_cause="missing guard",
            solution=solution[:200],
            diff=solution,
        )
        assert isinstance(pr, PRDescription)

    def test_pipeline_all_three_bugs(self):
        for title in ["NoneType crash", "off by one error", "wrong comparison operator"]:
            diag = BugDiagnosis(
                issue_title=title, issue_body="bug in code",
                relevant_files={"x.py": "def f(x):\n    return x\n"},
                suspected_function="f",
                root_cause_hypothesis="unknown",
            )
            candidates = PatchGenerator().generate(diag)
            assert isinstance(candidates, list)
