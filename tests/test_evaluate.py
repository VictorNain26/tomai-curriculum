"""Tests des metrics retrieval (_score_question) dans evaluate.py."""

from __future__ import annotations

from scripts.evaluate import _score_question


def test_all_keywords_in_top1():
    """Tous les keywords dans le 1er chunk → recall=1.0, rank=1, all_found=True."""
    q = {
        "query": "Pythagore",
        "matiere": "mathematiques",
        "expected_keywords": ["pythagore", "hypoténuse"],
    }
    chunks = [
        "Le théorème de Pythagore relie l'hypoténuse aux deux côtés.",
        "Quelque autre chunk non pertinent.",
    ]
    r = _score_question(q, chunks)

    assert r["recall_at_k"] == 1.0
    assert r["all_keywords_found"] is True
    assert r["first_hit_rank"] == 1
    assert r["mrr"] == 1.0
    assert r["skipped"] is False


def test_keywords_split_across_chunks():
    """Keywords dans plusieurs chunks → recall = somme / total."""
    q = {
        "query": "test",
        "expected_keywords": ["pythagore", "hypoténuse", "carré"],
    }
    chunks = [
        "Le théorème de Pythagore.",  # contient pythagore
        "Hypoténuse opposée à l'angle droit.",  # contient hypoténuse
        "Rien.",  # rien
    ]
    r = _score_question(q, chunks)

    assert r["hits"] == 2  # pythagore + hypoténuse
    assert r["recall_at_k"] == round(2 / 3, 3)
    assert r["all_keywords_found"] is False
    assert r["first_hit_rank"] == 1


def test_no_keywords_found():
    """Aucun keyword trouvé → recall=0, rank=None, mrr=0."""
    q = {"query": "test", "expected_keywords": ["xenon", "krypton"]}
    chunks = ["Le théorème de Pythagore.", "Autre texte."]
    r = _score_question(q, chunks)

    assert r["recall_at_k"] == 0.0
    assert r["hits"] == 0
    assert r["all_keywords_found"] is False
    assert r["first_hit_rank"] is None
    assert r["mrr"] == 0.0


def test_first_hit_rank_not_first():
    """First hit au rang 3 → mrr = 1/3."""
    q = {"query": "test", "expected_keywords": ["pythagore"]}
    chunks = [
        "Chunk 1 sans rien.",
        "Chunk 2 non plus.",
        "Chunk 3 avec Pythagore.",
    ]
    r = _score_question(q, chunks)

    assert r["first_hit_rank"] == 3
    assert r["mrr"] == round(1 / 3, 3)
    assert r["hits"] == 1


def test_case_insensitive_match():
    """Matching insensible à la casse (ex: PYTHAGORE matche pythagore)."""
    q = {"query": "test", "expected_keywords": ["pythagore"]}
    chunks = ["LE THÉORÈME DE PYTHAGORE EN MAJUSCULES"]
    r = _score_question(q, chunks)

    assert r["recall_at_k"] == 1.0
    assert r["first_hit_rank"] == 1


def test_multi_word_keyword_contiguous():
    """Un keyword multi-mots doit apparaître comme expression contiguë."""
    q = {"query": "test", "expected_keywords": ["triangle rectangle"]}
    chunks_match = ["Un triangle rectangle a un angle droit."]
    chunks_split = ["Le triangle est une figure. Le rectangle aussi."]

    assert _score_question(q, chunks_match)["recall_at_k"] == 1.0
    assert _score_question(q, chunks_split)["recall_at_k"] == 0.0


def test_skipped_when_no_expected_keywords():
    """Question sans expected_keywords → skipped, métriques None."""
    q = {"query": "test"}
    r = _score_question(q, ["chunk arbitraire"])

    assert r["skipped"] is True
    assert r["recall_at_k"] is None
    assert r["first_hit_rank"] is None
