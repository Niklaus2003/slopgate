"""Unit tests for deterministic fact extractors."""

from slopgate.models import Item
from slopgate.state.facts import (
    check_has_code_block,
    check_has_repro_heading,
    check_template_sections_filled,
    extract_all_facts,
    extract_ci_status,
    extract_contributing_summary,
    extract_links_to_issue,
)
from slopgate.state.repo_index import RepoIndex


def test_code_block_detection():
    assert check_has_code_block("Here is code:\n```python\nprint(1)\n```") is True
    assert check_has_code_block("Here is indented code:\n    x = 1 + 2\n") is True
    assert check_has_code_block("Plain text without any code at all.") is False


def test_repro_heading_detection():
    assert check_has_repro_heading("## Steps to reproduce\n1. Do this") is True
    assert check_has_repro_heading("### Reproduction Steps\nRun test suite") is True
    assert check_has_repro_heading("## How to reproduce\nCrash occurs") is True
    assert check_has_repro_heading("I have a feature request for dark mode.") is False


def test_template_sections_filled():
    text = """
    ## Environment
    Python 3.12, Windows 11

    ## Description
    Session cookie throws AttributeError

    ## Steps to Reproduce
    1. Start app
    """
    filled, total = check_template_sections_filled(text)
    assert filled == 3
    assert total == 4


def test_extract_links_to_issue():
    text = "Fixes #123 and closes #456. See also #789 or https://github.com/pallets/flask/issues/999"
    links = extract_links_to_issue(text)
    assert links == [123, 456, 789, 999]


def test_extract_contributing_summary():
    assert extract_contributing_summary("Please add unit test coverage") is not None
    assert extract_contributing_summary("Unrelated generic text") is None


def test_extract_ci_status():
    item_unknown = Item(repo="owner/repo", number=1, type="issue")
    assert extract_ci_status(item_unknown) == "unknown"

    item_pr = Item(
        repo="owner/repo",
        number=2,
        type="pull_request",
        raw={"head": {"status": "passing"}},
    )
    assert extract_ci_status(item_pr) == "passing"


def test_extract_all_facts_default_author_history():
    item = Item(
        repo="pallets/flask",
        number=10,
        type="issue",
        title="Bug in session",
        body="## Steps to reproduce\n```python\napp.run()\n```\nIn flask/sessions.py",
        author_login="someuser",
    )
    repo_idx = RepoIndex.from_file_list(["flask/sessions.py"])

    # Default: author_history MUST be None (protect newcomers)
    facts_default = extract_all_facts(item, repo_index=repo_idx, include_author_history=False)
    assert facts_default.author_history is None
    assert facts_default.has_code_block is True
    assert facts_default.has_repro_heading is True
    assert facts_default.cited_paths_found == (1, 1)

    # Opt-in: author_history populated
    facts_opt_in = extract_all_facts(item, repo_index=repo_idx, include_author_history=True)
    assert facts_opt_in.author_history == "author: someuser"
