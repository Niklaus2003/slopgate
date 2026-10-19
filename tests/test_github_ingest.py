"""Unit tests for GitHub REST API client."""

import httpx
import pytest

from slopgate.ingest.github import (
    GitHubClient,
    GitHubRateLimitExceeded,
    _parse_github_item,
)


def test_parse_github_item_issue():
    raw = {
        "number": 42,
        "title": "Bug in session cookies",
        "body": "Steps to reproduce...",
        "created_at": "2026-10-15T12:00:00Z",
        "user": {"login": "testuser"},
    }
    item = _parse_github_item("pallets/flask", raw)
    assert item.repo == "pallets/flask"
    assert item.number == 42
    assert item.type == "issue"
    assert item.title == "Bug in session cookies"
    assert item.author_login == "testuser"
    assert item.id == "pallets/flask#42"


def test_parse_github_item_pr():
    raw = {
        "number": 99,
        "title": "Fix session cookies",
        "body": "Closes #42",
        "created_at": "2026-10-15T13:00:00Z",
        "pull_request": {"url": "https://api.github.com/..."},
        "user": {"login": "contributor"},
    }
    item = _parse_github_item("pallets/flask", raw)
    assert item.type == "pull_request"
    assert item.number == 99


def test_github_client_headers():
    client = GitHubClient(token="ghp_test_token")
    headers = client._headers(etag="W/'abc'")
    assert headers["Authorization"] == "Bearer ghp_test_token"
    assert headers["If-None-Match"] == "W/'abc'"
    assert "SlopGate" in headers["User-Agent"]


def test_github_rate_limit_check():
    client = GitHubClient()
    response = httpx.Response(
        status_code=403,
        headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1700000000"},
    )
    with pytest.raises(GitHubRateLimitExceeded):
        client._check_rate_limit(response)
