"""
GitHubAgent — GitHub REST API wrapper.

Supports: listing issues, reading files, creating PRs, reading PR feedback.
Handles: rate limiting, pagination, error handling.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

import requests


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class GitHubIssue:
    number: int
    title: str
    body: str
    labels: list[str]
    state: str
    created_at: str
    url: str


@dataclass
class PullRequest:
    number: int
    title: str
    body: str
    head_branch: str
    base_branch: str
    state: str
    url: str
    review_comments: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PRFeedback:
    pr_number: int
    review_state: str   # APPROVED | CHANGES_REQUESTED | COMMENTED
    body: str
    author: str
    submitted_at: str
    inline_comments: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class GitHubAgent:
    """
    Thin, rate-limit-aware GitHub REST v3 wrapper.

    Usage::

        gh = GitHubAgent(token="ghp_...", repo="owner/repo")
        for issue in gh.iter_issues(labels=["bug"]):
            print(issue.title)
        pr = gh.create_pull_request("Fix: ...", "fix-branch", body="...")
    """

    API_BASE = "https://api.github.com"
    _RETRY_STATUSES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        token: str,
        repo: str,
        per_page: int = 100,
        max_retries: int = 5,
        backoff_base: float = 2.0,
    ) -> None:
        owner, name = repo.split("/", 1)
        self.owner = owner
        self.repo_name = name
        self.per_page = per_page
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    # ------------------------------------------------------------------
    # Issues
    # ------------------------------------------------------------------

    def iter_issues(
        self,
        state: str = "open",
        labels: Optional[list[str]] = None,
        assignee: Optional[str] = None,
    ) -> Iterator[GitHubIssue]:
        """Yield all matching issues (handles pagination automatically)."""
        params: dict[str, Any] = {"state": state, "per_page": self.per_page, "page": 1}
        if labels:
            params["labels"] = ",".join(labels)
        if assignee:
            params["assignee"] = assignee

        while True:
            data = self._get(f"/repos/{self.owner}/{self.repo_name}/issues", params=params)
            if not data:
                break
            for item in data:
                if "pull_request" in item:
                    continue  # issues endpoint also returns PRs; skip them
                yield GitHubIssue(
                    number=item["number"],
                    title=item["title"],
                    body=item.get("body") or "",
                    labels=[lb["name"] for lb in item.get("labels", [])],
                    state=item["state"],
                    created_at=item["created_at"],
                    url=item["html_url"],
                )
            if len(data) < self.per_page:
                break
            params["page"] += 1

    def get_issue(self, number: int) -> GitHubIssue:
        item = self._get(f"/repos/{self.owner}/{self.repo_name}/issues/{number}")
        return GitHubIssue(
            number=item["number"],
            title=item["title"],
            body=item.get("body") or "",
            labels=[lb["name"] for lb in item.get("labels", [])],
            state=item["state"],
            created_at=item["created_at"],
            url=item["html_url"],
        )

    # ------------------------------------------------------------------
    # File reading
    # ------------------------------------------------------------------

    def read_file(self, path: str, ref: str = "HEAD") -> str:
        """Return the decoded text content of *path* at *ref*."""
        import base64
        data = self._get(
            f"/repos/{self.owner}/{self.repo_name}/contents/{path}",
            params={"ref": ref},
        )
        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return data.get("content", "")

    def read_file_raw(self, path: str, ref: str = "HEAD") -> bytes:
        """Return raw bytes for *path* at *ref*."""
        import base64
        data = self._get(
            f"/repos/{self.owner}/{self.repo_name}/contents/{path}",
            params={"ref": ref},
        )
        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"])
        return data.get("content", "").encode()

    def list_directory(self, path: str = "", ref: str = "HEAD") -> list[dict[str, str]]:
        """Return directory listing entries with name, type, path, sha."""
        data = self._get(
            f"/repos/{self.owner}/{self.repo_name}/contents/{path}",
            params={"ref": ref},
        )
        if not isinstance(data, list):
            raise ValueError(f"{path!r} is not a directory")
        return [{"name": e["name"], "type": e["type"], "path": e["path"], "sha": e["sha"]} for e in data]

    # ------------------------------------------------------------------
    # Pull requests
    # ------------------------------------------------------------------

    def create_pull_request(
        self,
        title: str,
        head: str,
        body: str = "",
        base: str = "main",
        draft: bool = False,
    ) -> PullRequest:
        payload = {"title": title, "head": head, "base": base, "body": body, "draft": draft}
        data = self._post(f"/repos/{self.owner}/{self.repo_name}/pulls", json=payload)
        return PullRequest(
            number=data["number"],
            title=data["title"],
            body=data.get("body") or "",
            head_branch=data["head"]["ref"],
            base_branch=data["base"]["ref"],
            state=data["state"],
            url=data["html_url"],
        )

    def get_pull_request(self, number: int) -> PullRequest:
        data = self._get(f"/repos/{self.owner}/{self.repo_name}/pulls/{number}")
        return PullRequest(
            number=data["number"],
            title=data["title"],
            body=data.get("body") or "",
            head_branch=data["head"]["ref"],
            base_branch=data["base"]["ref"],
            state=data["state"],
            url=data["html_url"],
        )

    def read_pr_feedback(self, pr_number: int) -> list[PRFeedback]:
        """Return all reviews + their inline review comments."""
        reviews = self._get(
            f"/repos/{self.owner}/{self.repo_name}/pulls/{pr_number}/reviews"
        )
        feedback: list[PRFeedback] = []
        for review in reviews:
            # fetch inline comments for this review
            inline = self._get(
                f"/repos/{self.owner}/{self.repo_name}/pulls/{pr_number}/reviews/{review['id']}/comments"
            )
            feedback.append(PRFeedback(
                pr_number=pr_number,
                review_state=review.get("state", ""),
                body=review.get("body") or "",
                author=review.get("user", {}).get("login", ""),
                submitted_at=review.get("submitted_at", ""),
                inline_comments=inline,
            ))
        return feedback

    def iter_pull_requests(self, state: str = "open") -> Iterator[PullRequest]:
        params: dict[str, Any] = {"state": state, "per_page": self.per_page, "page": 1}
        while True:
            data = self._get(f"/repos/{self.owner}/{self.repo_name}/pulls", params=params)
            if not data:
                break
            for item in data:
                yield PullRequest(
                    number=item["number"],
                    title=item["title"],
                    body=item.get("body") or "",
                    head_branch=item["head"]["ref"],
                    base_branch=item["base"]["ref"],
                    state=item["state"],
                    url=item["html_url"],
                )
            if len(data) < self.per_page:
                break
            params["page"] += 1

    # ------------------------------------------------------------------
    # HTTP helpers with retry + rate-limit handling
    # ------------------------------------------------------------------

    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        return self._request("GET", path, params=params)

    def _post(self, path: str, json: Optional[dict[str, Any]] = None) -> Any:
        return self._request("POST", path, json=json)

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
        json: Optional[dict[str, Any]] = None,
    ) -> Any:
        url = self.API_BASE + path
        for attempt in range(self.max_retries):
            response = self._session.request(method, url, params=params, json=json, timeout=30)

            # Respect primary rate limit
            if response.status_code == 403 and "rate limit" in response.text.lower():
                reset_ts = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
                sleep_for = max(0, reset_ts - time.time()) + 1
                time.sleep(sleep_for)
                continue

            # Respect secondary rate limit (Retry-After header)
            if response.status_code in self._RETRY_STATUSES:
                retry_after = int(response.headers.get("Retry-After", 0))
                sleep_for = retry_after if retry_after else self.backoff_base ** attempt
                time.sleep(sleep_for)
                continue

            response.raise_for_status()
            return response.json()

        raise RuntimeError(f"GitHub API {method} {path} failed after {self.max_retries} retries")
