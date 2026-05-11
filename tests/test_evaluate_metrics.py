"""
Tests des métriques retrieval (scripts/evaluate.py).

Toutes les métriques sont déterministes à partir de (retrieved_ids, expected_ids).
On vérifie : cas nominaux, bornes (0/1), inputs vides, ordre du ranking.
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.evaluate import (
    context_precision,
    context_recall,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)

# =============================================================================
# recall_at_k
# =============================================================================


def test_recall_full_hit_at_k():
    assert recall_at_k(["a", "b", "c"], ["a", "b"], k=5) == 1.0


def test_recall_partial_hit():
    assert recall_at_k(["a", "x", "y"], ["a", "b"], k=5) == 0.5


def test_recall_no_hit():
    assert recall_at_k(["x", "y"], ["a", "b"], k=5) == 0.0


def test_recall_k_smaller_than_expected_count():
    # 2 expected, k=1, et le 1er retrieved est l'un des deux
    assert recall_at_k(["a", "b"], ["a", "b"], k=1) == 0.5


def test_recall_empty_expected_returns_one():
    """Convention : aucune attente -> recall = 1 (rien à manquer)."""
    assert recall_at_k(["a"], [], k=5) == 1.0


# =============================================================================
# precision_at_k
# =============================================================================


def test_precision_full_precision():
    assert precision_at_k(["a", "b"], ["a", "b", "c"], k=2) == 1.0


def test_precision_no_relevant():
    assert precision_at_k(["x", "y"], ["a"], k=2) == 0.0


def test_precision_k_caps_to_retrieved_length():
    # k > len(retrieved) : la précision se calcule sur ce qui existe
    assert precision_at_k(["a"], ["a"], k=5) == 1.0


def test_precision_empty_retrieved_returns_zero():
    assert precision_at_k([], ["a"], k=5) == 0.0


# =============================================================================
# mrr
# =============================================================================


def test_mrr_first_position():
    assert mrr(["a", "x", "y"], ["a"]) == 1.0


def test_mrr_second_position():
    assert mrr(["x", "a", "y"], ["a"]) == 0.5


def test_mrr_third_position():
    assert abs(mrr(["x", "y", "a"], ["a"]) - 1 / 3) < 1e-9


def test_mrr_no_match():
    assert mrr(["x", "y"], ["a"]) == 0.0


def test_mrr_any_expected_matches():
    # 1er match (a) en position 2
    assert mrr(["x", "a", "b"], ["a", "b"]) == 0.5


# =============================================================================
# ndcg_at_k
# =============================================================================


def test_ndcg_perfect_ranking():
    # Tous les expected en tête : NDCG = 1
    assert ndcg_at_k(["a", "b", "c"], ["a", "b"], k=5) == 1.0


def test_ndcg_zero_when_no_match():
    assert ndcg_at_k(["x", "y"], ["a"], k=5) == 0.0


def test_ndcg_worse_when_relevant_lower_ranked():
    """Un expected en position 1 doit donner un meilleur NDCG qu'en position 3."""
    high = ndcg_at_k(["a", "x", "y"], ["a"], k=5)
    low = ndcg_at_k(["x", "y", "a"], ["a"], k=5)
    assert high > low


def test_ndcg_dcg_formula():
    """Sanity check sur la formule : 1 expected en position 2, IDCG=1 / log2(2)."""
    # DCG = 1/log2(3), IDCG = 1/log2(2)
    expected = (1 / math.log2(3)) / (1 / math.log2(2))
    assert abs(ndcg_at_k(["x", "a"], ["a"], k=5) - expected) < 1e-9


# =============================================================================
# context_precision / context_recall (RAGAS-style déterministe)
# =============================================================================


def test_context_precision_basic():
    # 2/3 des retrieved sont pertinents
    assert abs(context_precision(["a", "b", "x"], ["a", "b"]) - 2 / 3) < 1e-9


def test_context_precision_empty_retrieved():
    assert context_precision([], ["a"]) == 0.0


def test_context_recall_full_coverage():
    assert context_recall(["a", "b", "c"], ["a", "b"]) == 1.0


def test_context_recall_partial_coverage():
    assert context_recall(["a", "x"], ["a", "b"]) == 0.5


def test_context_recall_empty_expected():
    """Convention cohérente avec recall_at_k : empty expected = 1.0."""
    assert context_recall(["a"], []) == 1.0
