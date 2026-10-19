"""Local lexical similarity engine for candidate duplicate detection.

Uses TF-IDF with zero external network or paid embedding calls.
Follows: problem-statement.md §6.2.
"""

from __future__ import annotations

from collections.abc import Sequence

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from slopgate.models import Item


def find_candidate_duplicate(
    target_item: Item,
    candidates: Sequence[Item],
    similarity_min: float = 0.55,
) -> tuple[int, float] | None:
    """Find the most similar existing issue/PR using local TF-IDF cosine scoring.

    Returns:
        (duplicate_issue_number, normalized_similarity_score) if score >= similarity_min,
        otherwise None.
    """
    valid_candidates = [
        c for c in candidates
        if c.repo == target_item.repo and c.number != target_item.number
    ]

    if not valid_candidates:
        return None

    # Title is weighted by repeating twice
    target_doc = f"{target_item.title} {target_item.title} {target_item.body}".strip()
    if not target_doc:
        return None

    corpus = [f"{c.title} {c.title} {c.body}".strip() for c in valid_candidates]

    try:
        vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)
        tfidf_matrix = vectorizer.fit_transform([target_doc, *corpus])
    except ValueError:
        # Handles empty vocabulary
        return None

    sim_scores = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]
    best_idx = int(sim_scores.argmax())
    best_score = float(sim_scores[best_idx])

    if best_score >= similarity_min:
        return valid_candidates[best_idx].number, round(best_score, 2)

    return None
