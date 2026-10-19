"""GitHub REST API client for issues, PRs, and repository metadata.

Implements ETag caching, rate-limit inspection, pagination, and token-optional access.
Follows: architecture.md §6.1, docs/defense/03_FLOW.md.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from slopgate.config import get_settings
from slopgate.models import Item

logger = logging.getLogger(__name__)


class GitHubRateLimitExceeded(Exception):
    """Raised when GitHub API rate limits are exhausted."""

    def __init__(self, reset_timestamp: int | None = None) -> None:
        self.reset_timestamp = reset_timestamp
        super().__init__(
            f"GitHub API rate limit exhausted. Resets at epoch {reset_timestamp}."
        )


class GitHubError(Exception):
    """Base exception for GitHub API errors."""


def _parse_github_item(repo: str, raw: dict[str, Any]) -> Item:
    """Transform raw GitHub REST API item into typed SlopGate Item."""
    is_pr = "pull_request" in raw
    item_type = "pull_request" if is_pr else "issue"
    user_data = raw.get("user") or {}
    author_login = user_data.get("login")

    return Item(
        repo=repo,
        number=raw.get("number", 0),
        type=item_type,
        title=raw.get("title") or "",
        body=raw.get("body") or "",
        created_at=raw.get("created_at") or "",
        author_login=author_login,
        raw=raw,
        status="queued",
    )


class GitHubClient:
    """HTTP client for GitHub REST API."""

    def __init__(
        self,
        token: str | None = None,
        base_url: str = "https://api.github.com",
        timeout: float = 15.0,
    ) -> None:
        settings = get_settings()
        self.token = token if token is not None else settings.github_token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _headers(self, etag: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "SlopGate-Triage-Agent",
        }
        if self.token and self.token.strip():
            headers["Authorization"] = f"Bearer {self.token.strip()}"
        if etag:
            headers["If-None-Match"] = etag
        return headers

    def _check_rate_limit(self, response: httpx.Response) -> None:
        remaining = response.headers.get("x-ratelimit-remaining")
        reset = response.headers.get("x-ratelimit-reset")
        if remaining is not None and int(remaining) <= 0 and response.status_code in (403, 429):
            reset_ts = int(reset) if reset and reset.isdigit() else None
            raise GitHubRateLimitExceeded(reset_ts)

    def fetch_issues(
        self,
        repo: str,
        state: str = "all",
        since: str | None = None,
        limit: int = 100,
        etag: str | None = None,
    ) -> tuple[list[Item], str | None]:
        """Fetch issues and PRs with pagination and ETag support.

        Returns:
            (items, response_etag)
        """
        items: list[Item] = []
        page = 1
        per_page = min(limit, 100)
        returned_etag: str | None = None

        with httpx.Client(timeout=self.timeout) as client:
            while len(items) < limit:
                params: dict[str, Any] = {
                    "state": state,
                    "per_page": per_page,
                    "page": page,
                    "sort": "created",
                    "direction": "desc",
                }
                if since:
                    params["since"] = since

                url = f"{self.base_url}/repos/{repo}/issues"
                headers = self._headers(etag=etag if page == 1 else None)

                response = client.get(url, headers=headers, params=params)
                self._check_rate_limit(response)

                if response.status_code == 304:
                    # ETag cache hit: Not modified
                    logger.info("GitHub ETag match (HTTP 304) for %s", repo)
                    return [], etag

                if response.status_code != 200:
                    raise GitHubError(
                        f"GitHub API error {response.status_code} fetching {url}: {response.text[:200]}"
                    )

                if page == 1:
                    returned_etag = response.headers.get("etag")

                raw_items = response.json()
                if not raw_items:
                    break

                for raw in raw_items:
                    items.append(_parse_github_item(repo, raw))
                    if len(items) >= limit:
                        break

                page += 1

        return items, returned_etag

    def fetch_single_item(self, repo: str, number: int) -> Item:
        """Fetch a single issue or PR by number."""
        url = f"{self.base_url}/repos/{repo}/issues/{number}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url, headers=self._headers())
            self._check_rate_limit(response)

            if response.status_code != 200:
                raise GitHubError(
                    f"GitHub API error {response.status_code} fetching {url}: {response.text[:200]}"
                )

            return _parse_github_item(repo, response.json())

    def fetch_repo_tree(self, repo: str, branch: str | None = None) -> list[str]:
        """Fetch repository file tree (list of file paths) for symbol/path matching."""
        with httpx.Client(timeout=self.timeout) as client:
            if not branch:
                # Discover default branch
                repo_resp = client.get(f"{self.base_url}/repos/{repo}", headers=self._headers())
                self._check_rate_limit(repo_resp)
                if repo_resp.status_code == 200:
                    branch = repo_resp.json().get("default_branch", "main")
                else:
                    branch = "main"

            url = f"{self.base_url}/repos/{repo}/git/trees/{branch}?recursive=1"
            response = client.get(url, headers=self._headers())
            self._check_rate_limit(response)

            if response.status_code != 200:
                raise GitHubError(
                    f"GitHub API error {response.status_code} fetching tree for {repo}: {response.text[:200]}"
                )

            tree_data = response.json().get("tree") or []
            return [node["path"] for node in tree_data if node.get("type") == "blob"]

    def add_labels(self, repo: str, number: int, labels: list[str]) -> list[str]:
        """Apply labels to an issue or pull request (requires write token)."""
        url = f"{self.base_url}/repos/{repo}/issues/{number}/labels"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=self._headers(), json={"labels": labels})
            self._check_rate_limit(response)
            if response.status_code not in (200, 201):
                raise GitHubError(
                    f"GitHub API error {response.status_code} adding labels to {repo}#{number}: {response.text[:200]}"
                )
            result = response.json()
            return [item["name"] if isinstance(item, dict) else str(item) for item in result]

    def post_comment(self, repo: str, number: int, body: str) -> dict[str, Any]:
        """Post a comment on an issue or pull request (requires write token)."""
        url = f"{self.base_url}/repos/{repo}/issues/{number}/comments"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=self._headers(), json={"body": body})
            self._check_rate_limit(response)
            if response.status_code not in (200, 201):
                raise GitHubError(
                    f"GitHub API error {response.status_code} posting comment on {repo}#{number}: {response.text[:200]}"
                )
            return response.json()

    def close_item(self, repo: str, number: int, state_reason: str = "completed") -> dict[str, Any]:
        """Close an issue or pull request (requires write token)."""
        url = f"{self.base_url}/repos/{repo}/issues/{number}"
        payload: dict[str, Any] = {"state": "closed"}
        if state_reason:
            payload["state_reason"] = state_reason
        with httpx.Client(timeout=self.timeout) as client:
            response = client.patch(url, headers=self._headers(), json=payload)
            self._check_rate_limit(response)
            if response.status_code != 200:
                raise GitHubError(
                    f"GitHub API error {response.status_code} closing {repo}#{number}: {response.text[:200]}"
                )
            return response.json()
