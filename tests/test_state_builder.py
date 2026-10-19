"""Unit tests for StateBuilder, token budget, and hash stability."""

from slopgate.config import PolicyConfig, StatePolicyConfig
from slopgate.models import Item
from slopgate.state.builder import build_state
from slopgate.state.repo_index import RepoIndex


def test_state_builder_format_and_facts():
    item = Item(
        repo="pallets/flask",
        number=101,
        type="issue",
        title="Session cookie KeyError in open_session",
        body="## Steps to reproduce\n```python\napp.test_client().get('/')\n```\nSee flask/sessions.py",
    )
    repo_idx = RepoIndex.from_file_list(["flask/sessions.py"])
    state = build_state(item, repo_index=repo_idx)

    assert "[TYPE] issue" in state.text
    assert "[TITLE] Session cookie KeyError in open_session" in state.text
    assert "[BODY]" in state.text
    assert "[FACTS]" in state.text
    assert "- cited_paths_found: 1 of 1" in state.text
    assert "- has_code_block: yes" in state.text
    assert "- has_repro_heading: yes" in state.text
    assert state.approx_tokens <= 450
    assert len(state.hash) == 64  # SHA-256


def test_token_cap_and_truncation_preserves_facts():
    # Construct an extremely long 10,000 character issue body
    giant_body = "word " * 2500 + "\n\n## Steps to reproduce\n```python\napp.run()\n```"
    item = Item(
        repo="pallets/flask",
        number=102,
        type="issue",
        title="Massive stack trace issue",
        body=giant_body,
    )
    state = build_state(item)

    # Must be bounded under 450 tokens
    assert state.approx_tokens <= 450
    # Facts section must remain completely intact
    assert "[FACTS]" in state.text
    assert "- has_code_block: yes" in state.text
    assert "- has_repro_heading: yes" in state.text
    assert "- ci_status: unknown" in state.text
    # Body was truncated
    assert "..." in state.text


def test_pr_diff_and_files_included():
    item = Item(
        repo="pallets/flask",
        number=205,
        type="pull_request",
        title="Fix session cookies",
        body="Refactored session handler",
        files=["src/flask/sessions.py", "tests/test_sessions.py"],
        additions=45,
        deletions=12,
    )
    state = build_state(item)

    assert "[TYPE] pull_request" in state.text
    assert "[FILES] 2 changed; src/flask/sessions.py, tests/test_sessions.py" in state.text
    assert "[DIFF] +45 -12" in state.text


def test_hash_stability_and_crlf_normalization():
    item1 = Item(
        repo="pallets/flask",
        number=301,
        type="issue",
        title="Windows CRLF test",
        body="Line 1\r\nLine 2\r\nLine 3",
    )
    item2 = Item(
        repo="pallets/flask",
        number=301,
        type="issue",
        title="Windows CRLF test",
        body="Line 1\nLine 2\nLine 3",
    )

    state1 = build_state(item1, schema_version="v1")
    state2 = build_state(item2, schema_version="v1")

    # Hashes must be identical regardless of CRLF or LF line endings
    assert state1.hash == state2.hash

    # Bumping schema version MUST invalidate hash
    state_v2 = build_state(item1, schema_version="v2")
    assert state_v2.hash != state1.hash


def test_author_history_policy_switch():
    item = Item(
        repo="pallets/flask",
        number=401,
        type="issue",
        title="Newcomer issue",
        body="First time report",
        author_login="newbie_developer",
    )

    # Default policy: author history excluded
    pol_default = PolicyConfig()
    state_default = build_state(item, policy=pol_default)
    assert "newbie_developer" not in state_default.text
    assert "author_history" not in state_default.text

    # Opt-in policy: author history included
    pol_opt_in = PolicyConfig(
        state=StatePolicyConfig(include_author_history=True)
    )
    state_opt_in = build_state(item, policy=pol_opt_in)
    assert "author: newbie_developer" in state_opt_in.text
