"""Unit tests for local candidate duplicate detection."""

from slopgate.models import Item
from slopgate.state.similarity import find_candidate_duplicate


def test_find_candidate_duplicate_match():
    target = Item(
        repo="pallets/flask",
        number=102,
        type="issue",
        title="Session cookie TypeError in open_session",
        body="When running with python 3.12, get AttributeError 'NoneType' has no attribute 'get' on cookies.",
    )

    existing_items = [
        Item(
            repo="pallets/flask",
            number=99,
            type="issue",
            title="TypeError in open_session with NoneType session cookie",
            body="When running on python 3.12, request.cookies fails with AttributeError on NoneType in open_session.",
        ),
        Item(
            repo="pallets/flask",
            number=50,
            type="issue",
            title="Docs typo in quickstart tutorial",
            body="Fix grammar mistake on page 3 of the introductory tutorial.",
        ),
    ]

    match = find_candidate_duplicate(target, existing_items, similarity_min=0.40)
    assert match is not None
    number, score = match
    assert number == 99
    assert score >= 0.40


def test_target_item_does_not_match_itself():
    target = Item(
        repo="pallets/flask",
        number=50,
        type="issue",
        title="Same title",
        body="Same body",
    )
    # The candidate list only contains the exact target item
    match = find_candidate_duplicate(target, [target], similarity_min=0.10)
    assert match is None


def test_dissimilar_items_return_none():
    target = Item(
        repo="pallets/flask",
        number=105,
        type="issue",
        title="Database migration error with postgresql dialect",
        body="Alembic engine cannot connect to remote database server socket.",
    )
    existing = [
        Item(
            repo="pallets/flask",
            number=101,
            type="issue",
            title="Typo in license header comment",
            body="Update copyright year from 2024 to 2025.",
        )
    ]
    match = find_candidate_duplicate(target, existing, similarity_min=0.55)
    assert match is None
