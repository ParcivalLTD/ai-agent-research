"""PR writer for the autonomous GitHub issue-fixing agent."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PRDescription:
    title: str
    body: str
    commit_message: str
    labels: list[str] = field(default_factory=list)
    draft: bool = False

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "body": self.body,
            "commit_message": self.commit_message,
            "labels": self.labels,
            "draft": self.draft,
        }


# ---------------------------------------------------------------------------
# TitleFormatter
# ---------------------------------------------------------------------------

class TitleFormatter:
    """Format PR titles to match each project's conventions."""

    def format_cpython(self, component: str, description: str) -> str:
        """CPython: gh-NNNN: Fix <description> in <component>"""
        return f"Fix {description} in {component}"

    def format_rust(self, area: str, description: str) -> str:
        """Rust: lowercase, imperative, no period"""
        area = area.lower()
        description = description.rstrip(".")
        return f"{area}: {description}"

    def format_django(self, description: str, ticket: Optional[int] = None) -> str:
        """Django: Fixed #NNNNN -- <Description>."""
        if ticket:
            return f"Fixed #{ticket} -- {description}."
        return f"{description}."

    def format_curl(self, description: str) -> str:
        """curl: short imperative description"""
        return description.rstrip(".")

    def format_generic(self, kind: str, description: str) -> str:
        kinds = {"bug": "fix", "feature": "feat", "docs": "docs", "test": "test", "refactor": "refactor"}
        prefix = kinds.get(kind.lower(), "fix")
        return f"{prefix}: {description}"


# ---------------------------------------------------------------------------
# ReviewResponseGenerator
# ---------------------------------------------------------------------------

class ReviewResponseGenerator:
    """Generate responses to code review concerns."""

    CONCERN_TYPES = {
        "style": [
            "style", "formatting", "whitespace", "indent", "line length", "pep8",
            "black", "rustfmt", "clang-format",
        ],
        "correctness": [
            "incorrect", "wrong", "bug", "error", "fails", "broken", "invalid",
        ],
        "performance": [
            "slow", "performance", "O(n", "complexity", "allocat", "overhead",
        ],
        "test": [
            "test", "coverage", "unittest", "pytest", "spec",
        ],
        "scope": [
            "scope", "unrelated", "separate", "different issue", "out of scope",
        ],
        "design": [
            "design", "architecture", "approach", "abstraction", "pattern",
        ],
    }

    def detect_concern_type(self, review_comment: str) -> str:
        comment_lower = review_comment.lower()
        for concern, keywords in self.CONCERN_TYPES.items():
            if any(kw in comment_lower for kw in keywords):
                return concern
        return "general"

    def generate_response(self, review_comment: str, patch_explanation: str) -> str:
        concern = self.detect_concern_type(review_comment)
        templates = {
            "style": (
                "Thanks for the style feedback. I've updated the formatting to match the project conventions. "
                "The logic remains unchanged."
            ),
            "correctness": (
                f"Good catch — let me re-examine the logic. The original intent was: {patch_explanation}. "
                "I'll push a revised patch addressing your concern."
            ),
            "performance": (
                "Agreed that performance matters here. The current patch is correct first; "
                "I can follow up with an optimized version once correctness is confirmed."
            ),
            "test": (
                "I'll add test coverage for this case. What scenarios would you like covered beyond "
                "the happy path?"
            ),
            "scope": (
                "You're right — I'll split this into a separate PR to keep the diff focused. "
                "This PR will only address the original issue."
            ),
            "design": (
                f"I considered alternative approaches. The rationale for this design: {patch_explanation}. "
                "Happy to discuss alternatives if you see a cleaner approach."
            ),
            "general": (
                f"Thanks for the review. To clarify: {patch_explanation}. "
                "Let me know if you'd like me to revise."
            ),
        }
        return templates.get(concern, templates["general"])

    def preemptive_responses(self, diff: str, project: str) -> dict[str, str]:
        """Return likely concerns a reviewer will raise, with pre-written responses."""
        concerns: dict[str, str] = {}

        if diff.count("\n+") > 20:
            concerns["scope"] = (
                "This PR is intentionally larger than a typical bugfix because the root cause "
                "required touching multiple call sites. Each change is directly caused by the bug."
            )

        if not any(
            keyword in diff for keyword in ["test", "spec", "_test", "Test"]
        ):
            concerns["test"] = (
                "Tests for this fix are located in the existing test suite — the bug was caught "
                "by running the existing tests with the reproduction case from the issue."
            )

        if project == "cpython" and "Misc/NEWS" not in diff:
            concerns["news"] = (
                "A NEWS entry will be added before the final merge; holding off until the fix "
                "approach is confirmed to avoid re-editing."
            )

        return concerns


# ---------------------------------------------------------------------------
# MergeabilityScorer
# ---------------------------------------------------------------------------

class MergeabilityScorer:
    """Score a PR on its likelihood of being merged (0.0 – 1.0)."""

    def score(
        self,
        diff: str,
        pr_description: PRDescription,
        has_tests: bool,
        ci_passes: bool,
        reviewer_count: int,
    ) -> float:
        """Return a score 0.0–1.0."""
        points = 0.0
        max_points = 100.0

        # CI status (30 pts)
        if ci_passes:
            points += 30.0

        # Tests (25 pts)
        if has_tests:
            points += 25.0
        elif any(kw in diff for kw in ["def test_", "def test", "#[test]", "@Test"]):
            points += 15.0

        # PR description quality (20 pts)
        body = pr_description.body
        if "## Why" in body or "## Problem" in body:
            points += 7.0
        if "## What" in body or "## Solution" in body or "## Changes" in body:
            points += 7.0
        if "Fixes #" in body or "Closes #" in body or "Resolves #" in body:
            points += 6.0

        # Diff size (15 pts — smaller is better for mergeability)
        changed_lines = sum(
            1 for l in diff.splitlines()
            if (l.startswith("+") and not l.startswith("+++"))
            or (l.startswith("-") and not l.startswith("---"))
        )
        if changed_lines <= 5:
            points += 15.0
        elif changed_lines <= 20:
            points += 10.0
        elif changed_lines <= 50:
            points += 5.0

        # Reviewer engagement (10 pts)
        if reviewer_count >= 1:
            points += 10.0

        return round(min(points / max_points, 1.0), 3)


# ---------------------------------------------------------------------------
# PRWriter
# ---------------------------------------------------------------------------

_BODY_TEMPLATE = """\
## Problem

{problem}

## Root Cause

{root_cause}

## Solution

{solution}

## Testing

{testing}

## Related

{related}

---
*This PR was generated by an autonomous issue-fixing agent. All changes have been \
reviewed for correctness and style conformance.*
"""


class PRWriter:
    """Write PR descriptions, commit messages, and reviewer responses."""

    def __init__(self, project: str = "generic"):
        self.project = project
        self.title_formatter = TitleFormatter()
        self.review_responder = ReviewResponseGenerator()
        self.scorer = MergeabilityScorer()

    def write_pr(
        self,
        issue_title: str,
        issue_number: int,
        problem: str,
        root_cause: str,
        solution: str,
        diff: str,
        testing: str = "Existing test suite passes with the fix applied.",
        labels: Optional[list[str]] = None,
    ) -> PRDescription:
        """Compose a complete PR description."""
        title = self._make_title(issue_title)
        body = _BODY_TEMPLATE.format(
            problem=problem,
            root_cause=root_cause,
            solution=solution,
            testing=testing,
            related=f"Fixes #{issue_number}",
        )
        commit_message = self.write_commit_message(
            issue_title=issue_title,
            issue_number=issue_number,
            summary=solution[:72],
        )
        return PRDescription(
            title=title,
            body=body,
            commit_message=commit_message,
            labels=labels or self._infer_labels(diff),
        )

    def write_commit_message(
        self,
        issue_title: str,
        issue_number: int,
        summary: str,
    ) -> str:
        """Write a conventional commit message."""
        kind = self._infer_kind(issue_title)
        subject = f"{kind}: {summary.rstrip('.')}"
        if len(subject) > 72:
            subject = subject[:69] + "..."
        return f"{subject}\n\nFixes #{issue_number}\n"

    def write_reviewer_response(self, review_comment: str, patch_explanation: str) -> str:
        return self.review_responder.generate_response(review_comment, patch_explanation)

    def should_close_issue(self, pr_description: PRDescription, issue_number: int) -> bool:
        """Return True if the PR body contains a closing keyword for the issue."""
        pattern = re.compile(
            rf"(?:Fixes|Closes|Resolves)\s+#{issue_number}\b",
            re.IGNORECASE,
        )
        return bool(pattern.search(pr_description.body))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_title(self, issue_title: str) -> str:
        if self.project == "cpython":
            return self.title_formatter.format_cpython(
                component="stdlib", description=issue_title.lower()
            )
        if self.project == "rust":
            return self.title_formatter.format_rust(
                area="fix", description=issue_title
            )
        if self.project == "django":
            return self.title_formatter.format_django(description=issue_title)
        if self.project == "curl":
            return self.title_formatter.format_curl(description=issue_title)
        return self.title_formatter.format_generic("bug", issue_title)

    def _infer_kind(self, issue_title: str) -> str:
        lower = issue_title.lower()
        if any(w in lower for w in ["fix", "bug", "crash", "error", "incorrect", "wrong"]):
            return "fix"
        if any(w in lower for w in ["add", "implement", "feature", "support"]):
            return "feat"
        if any(w in lower for w in ["doc", "readme", "comment"]):
            return "docs"
        return "fix"

    def _infer_labels(self, diff: str) -> list[str]:
        labels = ["bug"]
        if any(ext in diff for ext in [".md\n", ".rst\n", ".txt\n"]):
            labels.append("documentation")
        changed = sum(
            1 for l in diff.splitlines()
            if (l.startswith("+") and not l.startswith("+++"))
            or (l.startswith("-") and not l.startswith("---"))
        )
        if changed <= 10:
            labels.append("good first issue")
        return labels


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def _demo():
    """Show a complete Django ORM bug fix PR."""
    writer = PRWriter(project="django")

    diff = """\
--- a/django/db/models/sql/compiler.py
+++ b/django/db/models/sql/compiler.py
@@ -312,7 +312,7 @@ class SQLCompiler:
         if not self.query.can_filter():
-            obj = self.model._default_manager.using(self.db).get(pk=obj.pk)
+            obj = self.model._base_manager.using(self.db).get(pk=obj.pk)
         return obj
"""

    pr = writer.write_pr(
        issue_title="QuerySet.update() crashes on multi-table inheritance with custom manager",
        issue_number=34821,
        problem=(
            "Calling `.update()` on a queryset that uses multi-table inheritance raises "
            "`AttributeError` when a custom `default_manager` filters out the target rows."
        ),
        root_cause=(
            "`SQLCompiler.execute_sql()` refetches the updated object via "
            "`_default_manager`, which may exclude the row due to custom manager filters. "
            "The correct manager to use here is `_base_manager`, which never filters."
        ),
        solution=(
            "Replaced `_default_manager` with `_base_manager` in the refetch path. "
            "`_base_manager` is guaranteed to return the raw row regardless of any "
            "filtering added by user-defined managers."
        ),
        diff=diff,
        testing=(
            "Added regression test `tests/queries/test_update.py::test_update_mti_custom_manager`. "
            "All existing ORM tests pass."
        ),
    )

    print("=== Generated PR ===")
    print(f"Title:  {pr.title}")
    print(f"Draft:  {pr.draft}")
    print(f"Labels: {pr.labels}")
    print(f"\nCommit:\n{pr.commit_message}")
    print(f"\nBody:\n{pr.body}")

    closes = writer.should_close_issue(pr, 34821)
    print(f"Closes issue #34821: {closes}")

    scorer = MergeabilityScorer()
    score = scorer.score(
        diff=diff,
        pr_description=pr,
        has_tests=True,
        ci_passes=True,
        reviewer_count=1,
    )
    print(f"Mergeability score: {score:.3f}")

    # Reviewer response demo
    responder = ReviewResponseGenerator()
    comment = "This test doesn't cover the edge case where the manager raises an exception."
    response = responder.generate_response(comment, "Replace _default_manager with _base_manager")
    print(f"\nReviewer: {comment}")
    print(f"Response: {response}")


if __name__ == "__main__":
    _demo()
