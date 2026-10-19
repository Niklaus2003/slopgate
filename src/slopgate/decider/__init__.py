"""Strands Decider 2B client, typed question registry, and question cascade."""

from slopgate.decider.cascade import pick_q1, run_cascade, select_followups
from slopgate.decider.client import DeciderClient, DeciderUnavailable, FakeDecider
from slopgate.decider.http_client import HttpDecider
from slopgate.decider.in_process import InProcessDecider
from slopgate.decider.questions import (
    N1_QUESTION,
    N2_QUESTION,
    N3_QUESTION,
    N4_QUESTION,
    N5_QUESTION,
    QUESTION_REGISTRY,
    get_q1_question,
    hash_question_text,
)

__all__ = [
    "N1_QUESTION",
    "N2_QUESTION",
    "N3_QUESTION",
    "N4_QUESTION",
    "N5_QUESTION",
    "QUESTION_REGISTRY",
    "DeciderClient",
    "DeciderUnavailable",
    "FakeDecider",
    "HttpDecider",
    "InProcessDecider",
    "get_q1_question",
    "hash_question_text",
    "pick_q1",
    "run_cascade",
    "select_followups",
]
