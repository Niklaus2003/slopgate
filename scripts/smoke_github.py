"""Smoke test for GitHub REST API connectivity and rate-limit tracking."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from slopgate.config import get_settings


def main():
    settings = get_settings()
    print("=" * 60)
    print("  GitHub REST API Smoke Test")
    print("=" * 60)
    target_repo = "pallets/flask"
    print(f"Target Repository: {target_repo}")
    print(f"Token Configured:  {'YES' if settings.github_token else 'NO (Unauthenticated Mode)'}")

    try:
        import httpx
    except ImportError:
        print("httpx not installed yet.")
        return 1

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "SlopGate-Triage-SmokeTest"
    }
    if settings.github_token:
        headers["Authorization"] = f"token {settings.github_token}"

    url = f"https://api.github.com/repos/{target_repo}/issues"
    params = {"state": "closed", "per_page": 5}

    print(f"\nFetching 5 recent closed issues from {url}...")
    try:
        resp = httpx.get(url, headers=headers, params=params, timeout=10.0)
        print(f"HTTP Status: {resp.status_code}")
        rate_limit = resp.headers.get("x-ratelimit-limit", "unknown")
        rate_remaining = resp.headers.get("x-ratelimit-remaining", "unknown")
        print(f"Rate Limit:  {rate_remaining}/{rate_limit} remaining")

        if resp.status_code == 200:
            items = resp.json()
            print(f"\nSuccessfully fetched {len(items)} items:")
            for item in items:
                item_type = "PR" if "pull_request" in item else "Issue"
                print(f"  - [{item_type} #{item['number']}] {item['title'][:65]}")
            print("\nGitHub smoke test PASSED!")
            return 0
        else:
            print(f"GitHub API returned non-200 status: {resp.text}")
            return 1
    except Exception as e:
        print(f"Failed to connect to GitHub API: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
