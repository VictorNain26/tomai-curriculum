"""
Tests pour scripts/evaluate_judge.py.

Tous les appels Mistral sont mockés (pas de réseau, pas d'API key requise en CI).
"""

import math
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.evaluate_judge import (  # noqa: E402
    _cosine,
    cross_validate,
    extract_claims,
    faithfulness_score,
    generate_hypothetical_questions,
    response_relevancy_score,
    verify_claim,
)

# ---------------------------------------------------------------------------
# _cosine — fonction pure
# ---------------------------------------------------------------------------


def test_cosine_orthogonal_vectors_zero():
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    assert _cosine(a, b) == 0.0


def test_cosine_identical_normalized_vectors_one():
    # Vecteurs unitaires identiques → cos = 1
    v = [1.0 / math.sqrt(3)] * 3
    assert _cosine(v, v) == pytest.approx(1.0, abs=1e-9)


def test_cosine_opposite_normalized_vectors_minus_one():
    v = [1.0, 0.0]
    minus_v = [-1.0, 0.0]
    assert _cosine(v, minus_v) == -1.0


# ---------------------------------------------------------------------------
# extract_claims
# ---------------------------------------------------------------------------


@patch("scripts.evaluate_judge.chat_json")
def test_extract_claims_parses_list(mock_chat):
    mock_chat.return_value = {"claims": ["claim 1", "claim 2", "claim 3"]}
    result = extract_claims(MagicMock(), "model", "answer text")
    assert result == ["claim 1", "claim 2", "claim 3"]


@patch("scripts.evaluate_judge.chat_json")
def test_extract_claims_strips_whitespace_and_empty(mock_chat):
    mock_chat.return_value = {"claims": ["  ok  ", "", "   ", "valid"]}
    result = extract_claims(MagicMock(), "model", "answer")
    assert result == ["ok", "valid"]


@patch("scripts.evaluate_judge.chat_json")
def test_extract_claims_raises_on_invalid_format(mock_chat):
    mock_chat.return_value = {"claims": "not a list"}
    with pytest.raises(ValueError, match="Format claims invalide"):
        extract_claims(MagicMock(), "model", "answer")


@patch("scripts.evaluate_judge.chat_json")
def test_extract_claims_missing_key_returns_empty(mock_chat):
    mock_chat.return_value = {"other_key": []}
    result = extract_claims(MagicMock(), "model", "answer")
    assert result == []


# ---------------------------------------------------------------------------
# verify_claim
# ---------------------------------------------------------------------------


@patch("scripts.evaluate_judge.chat_json")
def test_verify_claim_supported(mock_chat):
    mock_chat.return_value = {"supported": True, "reason": "Le contexte le dit"}
    ok, reason = verify_claim(MagicMock(), "model", "claim X", ["context Y"])
    assert ok is True
    assert reason == "Le contexte le dit"


@patch("scripts.evaluate_judge.chat_json")
def test_verify_claim_not_supported(mock_chat):
    mock_chat.return_value = {"supported": False, "reason": "Pas mentionné"}
    ok, _ = verify_claim(MagicMock(), "model", "claim", ["context"])
    assert ok is False


@patch("scripts.evaluate_judge.chat_json")
def test_verify_claim_missing_supported_defaults_false(mock_chat):
    mock_chat.return_value = {"reason": "abstention"}
    ok, _ = verify_claim(MagicMock(), "model", "claim", [])
    assert ok is False


# ---------------------------------------------------------------------------
# faithfulness_score
# ---------------------------------------------------------------------------


@patch("scripts.evaluate_judge.chat_json")
def test_faithfulness_all_supported(mock_chat):
    # 2 claims, tous supportés → score = 1.0
    mock_chat.side_effect = [
        {"claims": ["c1", "c2"]},
        {"supported": True, "reason": "ok"},
        {"supported": True, "reason": "ok"},
    ]
    result = faithfulness_score(MagicMock(), "model", "answer", ["context"])
    assert result["score"] == 1.0
    assert len(result["claims"]) == 2


@patch("scripts.evaluate_judge.chat_json")
def test_faithfulness_partial_support(mock_chat):
    # 3 claims, 2 supportés → score = 2/3
    mock_chat.side_effect = [
        {"claims": ["c1", "c2", "c3"]},
        {"supported": True, "reason": "ok"},
        {"supported": False, "reason": "non"},
        {"supported": True, "reason": "ok"},
    ]
    result = faithfulness_score(MagicMock(), "model", "answer", ["context"])
    assert result["score"] == pytest.approx(2 / 3)


@patch("scripts.evaluate_judge.chat_json")
def test_faithfulness_no_claims_returns_one(mock_chat):
    """Réponse sans claim factuel → score = 1.0 (vacuously true, convention RAGAS)."""
    mock_chat.return_value = {"claims": []}
    result = faithfulness_score(MagicMock(), "model", "Bonjour !", [])
    assert result["score"] == 1.0
    assert result["claims"] == []


@patch("scripts.evaluate_judge.chat_json")
def test_faithfulness_all_unsupported_returns_zero(mock_chat):
    mock_chat.side_effect = [
        {"claims": ["c1", "c2"]},
        {"supported": False, "reason": "non"},
        {"supported": False, "reason": "non"},
    ]
    result = faithfulness_score(MagicMock(), "model", "answer", ["context"])
    assert result["score"] == 0.0


# ---------------------------------------------------------------------------
# generate_hypothetical_questions
# ---------------------------------------------------------------------------


@patch("scripts.evaluate_judge.chat_json")
def test_generate_questions_truncates_to_n(mock_chat):
    mock_chat.return_value = {"questions": ["q1", "q2", "q3", "q4", "q5"]}
    result = generate_hypothetical_questions(MagicMock(), "model", "answer", n=3)
    assert len(result) == 3


@patch("scripts.evaluate_judge.chat_json")
def test_generate_questions_raises_on_invalid_format(mock_chat):
    mock_chat.return_value = {"questions": {"not": "a list"}}
    with pytest.raises(ValueError, match="Format questions invalide"):
        generate_hypothetical_questions(MagicMock(), "model", "answer")


# ---------------------------------------------------------------------------
# response_relevancy_score
# ---------------------------------------------------------------------------


@patch("scripts.evaluate_judge.generate_embeddings_batch")
@patch("scripts.evaluate_judge.chat_json")
def test_response_relevancy_perfect_match(mock_chat, mock_embed):
    """Question originale identique à toutes les questions générées → score 1.0."""
    mock_chat.return_value = {"questions": ["même question", "même question", "même question"]}
    # Tous les embeddings identiques (1024D normalisé)
    same_vec = [1.0 / math.sqrt(1024)] * 1024
    mock_embed.return_value = [same_vec, same_vec, same_vec, same_vec]

    result = response_relevancy_score(MagicMock(), "model", "question originale", "answer")
    assert result["score"] == pytest.approx(1.0, abs=1e-6)


@patch("scripts.evaluate_judge.generate_embeddings_batch")
@patch("scripts.evaluate_judge.chat_json")
def test_response_relevancy_orthogonal_score_zero(mock_chat, mock_embed):
    """Question originale orthogonale aux questions générées → score 0.0."""
    mock_chat.return_value = {"questions": ["q1", "q2"]}
    # Question originale = axe X, générées = axe Y → cosine 0
    orig = [1.0] + [0.0] * 1023
    gen = [0.0, 1.0] + [0.0] * 1022
    mock_embed.return_value = [orig, gen, gen]

    result = response_relevancy_score(MagicMock(), "model", "q originale", "answer")
    assert result["score"] == pytest.approx(0.0, abs=1e-6)


@patch("scripts.evaluate_judge.generate_embeddings_batch")
@patch("scripts.evaluate_judge.chat_json")
def test_response_relevancy_no_generated_questions_returns_zero(mock_chat, mock_embed):
    mock_chat.return_value = {"questions": []}
    result = response_relevancy_score(MagicMock(), "model", "q", "answer")
    assert result["score"] == 0.0
    # Pas d'appel embedding nécessaire si pas de questions générées
    mock_embed.assert_not_called()


# ---------------------------------------------------------------------------
# cross_validate
# ---------------------------------------------------------------------------


@patch("scripts.evaluate_judge.response_relevancy_score")
@patch("scripts.evaluate_judge.faithfulness_score")
def test_cross_validate_computes_deltas(mock_faith, mock_rel):
    # Judge A et B donnent des scores différents
    mock_faith.side_effect = [
        {"score": 0.9},  # A sample 1
        {"score": 0.7},  # B sample 1
        {"score": 0.8},  # A sample 2
        {"score": 0.8},  # B sample 2
    ]
    mock_rel.side_effect = [
        {"score": 0.95},  # A s1
        {"score": 0.90},  # B s1
        {"score": 0.50},  # A s2
        {"score": 0.50},  # B s2
    ]

    samples = [
        {"question": "q1", "answer": "a1", "contexts": ["c1"]},
        {"question": "q2", "answer": "a2", "contexts": ["c2"]},
    ]
    result = cross_validate(MagicMock(), samples)

    # Delta faithfulness moyen : (|0.9-0.7| + |0.8-0.8|) / 2 = 0.1
    assert result["mean_delta_faithfulness"] == pytest.approx(0.1)
    # Delta relevancy moyen : (|0.95-0.90| + |0.50-0.50|) / 2 = 0.025
    assert result["mean_delta_relevancy"] == pytest.approx(0.025)


@patch("scripts.evaluate_judge.response_relevancy_score")
@patch("scripts.evaluate_judge.faithfulness_score")
def test_cross_validate_flags_high_delta_samples(mock_faith, mock_rel):
    # Sample 0 : agreement, sample 1 : strong disagreement
    mock_faith.side_effect = [
        {"score": 0.8},  # A s0
        {"score": 0.8},  # B s0
        {"score": 0.9},  # A s1
        {"score": 0.4},  # B s1 (delta 0.5 > seuil 0.3)
    ]
    mock_rel.side_effect = [
        {"score": 0.7},  # A s0
        {"score": 0.7},  # B s0
        {"score": 0.7},  # A s1
        {"score": 0.7},  # B s1
    ]

    samples = [
        {"question": "q0", "answer": "a0", "contexts": []},
        {"question": "q1", "answer": "a1", "contexts": []},
    ]
    result = cross_validate(MagicMock(), samples)

    assert result["flagged_samples"] == [1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
