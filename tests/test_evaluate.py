"""Tests des metrics retrieval (_score_question) dans evaluate.py."""

from __future__ import annotations

from types import SimpleNamespace

from scripts.evaluate import _score_question


def _chunks(*texts: str, ids: list[str] | None = None) -> list:
    """Mock HybridResult-like (juste les attrs lus par _score_question)."""
    ids = ids or [None] * len(texts)
    return [SimpleNamespace(text=t, id=i, payload={}) for t, i in zip(texts, ids, strict=True)]


def test_all_keywords_in_top1():
    """Tous les keywords dans le 1er chunk → recall=1.0, rank=1, all_found=True."""
    q = {
        "query": "Pythagore",
        "matiere": "mathematiques",
        "expected_keywords": ["pythagore", "hypoténuse"],
    }
    chunks = _chunks(
        "Le théorème de Pythagore relie l'hypoténuse aux deux côtés.",
        "Quelque autre chunk non pertinent.",
    )
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
    chunks = _chunks(
        "Le théorème de Pythagore.",  # contient pythagore
        "Hypoténuse opposée à l'angle droit.",  # contient hypoténuse
        "Rien.",  # rien
    )
    r = _score_question(q, chunks)

    assert r["hits"] == 2  # pythagore + hypoténuse
    assert r["recall_at_k"] == round(2 / 3, 3)
    assert r["all_keywords_found"] is False
    assert r["first_hit_rank"] == 1


def test_no_keywords_found():
    """Aucun keyword trouvé → recall=0, rank=None, mrr=0."""
    q = {"query": "test", "expected_keywords": ["xenon", "krypton"]}
    chunks = _chunks("Le théorème de Pythagore.", "Autre texte.")
    r = _score_question(q, chunks)

    assert r["recall_at_k"] == 0.0
    assert r["hits"] == 0
    assert r["all_keywords_found"] is False
    assert r["first_hit_rank"] is None
    assert r["mrr"] == 0.0


def test_first_hit_rank_not_first():
    """First hit au rang 3 → mrr = 1/3."""
    q = {"query": "test", "expected_keywords": ["pythagore"]}
    chunks = _chunks(
        "Chunk 1 sans rien.",
        "Chunk 2 non plus.",
        "Chunk 3 avec Pythagore.",
    )
    r = _score_question(q, chunks)

    assert r["first_hit_rank"] == 3
    assert r["mrr"] == round(1 / 3, 3)
    assert r["hits"] == 1


def test_case_insensitive_match():
    """Matching insensible à la casse (ex: PYTHAGORE matche pythagore)."""
    q = {"query": "test", "expected_keywords": ["pythagore"]}
    chunks = _chunks("LE THÉORÈME DE PYTHAGORE EN MAJUSCULES")
    r = _score_question(q, chunks)

    assert r["recall_at_k"] == 1.0
    assert r["first_hit_rank"] == 1


def test_multi_word_keyword_contiguous():
    """Un keyword multi-mots doit apparaître comme expression contiguë."""
    q = {"query": "test", "expected_keywords": ["triangle rectangle"]}
    chunks_match = _chunks("Un triangle rectangle a un angle droit.")
    chunks_split = _chunks("Le triangle est une figure. Le rectangle aussi.")

    assert _score_question(q, chunks_match)["recall_at_k"] == 1.0
    assert _score_question(q, chunks_split)["recall_at_k"] == 0.0


def test_chunk_id_hit_top1():
    """gold_chunk_id présent et top-1 du retrieval → cid_hit_rank=1, mrr=1.0."""
    q = {
        "query": "test",
        "expected_keywords": ["pythagore"],
        "gold_chunk_id": "abc-123",
    }
    chunks = _chunks(
        "Le théorème de Pythagore.",
        "Autre chunk.",
        ids=["abc-123", "def-456"],
    )
    r = _score_question(q, chunks)

    assert r["chunk_id_hit_rank"] == 1
    assert r["chunk_id_mrr"] == 1.0


def test_chunk_id_hit_rank3():
    """gold_chunk_id présent au rang 3 → cid_hit_rank=3, mrr=1/3."""
    q = {
        "query": "test",
        "expected_keywords": ["pythagore"],
        "gold_chunk_id": "gold-xyz",
    }
    chunks = _chunks(
        "Chunk 1.",
        "Chunk 2.",
        "Chunk 3 avec Pythagore.",
        ids=["a-1", "b-2", "gold-xyz"],
    )
    r = _score_question(q, chunks)

    assert r["chunk_id_hit_rank"] == 3
    assert r["chunk_id_mrr"] == round(1 / 3, 3)


def test_chunk_id_miss():
    """gold_chunk_id absent du top-k → cid_hit_rank=None, mrr=0."""
    q = {
        "query": "test",
        "expected_keywords": ["pythagore"],
        "gold_chunk_id": "missing-id",
    }
    chunks = _chunks("Le théorème de Pythagore.", ids=["abc-123"])
    r = _score_question(q, chunks)

    assert r["chunk_id_hit_rank"] is None
    assert r["chunk_id_mrr"] == 0.0


def test_chunk_id_miss_when_all_ids_none():
    """gold_chunk_id attendu mais résultats sans id (.id=None) → miss propre.

    Couvre la vraie shape HybridResult quand Qdrant ne renvoie pas d'id : on ne
    doit jamais matcher par accident (payload n'a jamais contenu l'id)."""
    q = {
        "query": "test",
        "expected_keywords": ["pythagore"],
        "gold_chunk_id": "gold-xyz",
    }
    chunks = _chunks("Le théorème de Pythagore.", "Autre chunk.")  # ids défaut = None

    r = _score_question(q, chunks)

    assert r["chunk_id_hit_rank"] is None
    assert r["chunk_id_mrr"] == 0.0


def test_seed_format_without_chunk_id():
    """Seed humain (sans gold_chunk_id) : keyword OK, chunk_id None."""
    q = {"query": "test", "expected_keywords": ["pythagore"]}
    chunks = _chunks("Le théorème de Pythagore.", ids=["abc-123"])
    r = _score_question(q, chunks)

    assert r["recall_at_k"] == 1.0
    assert r["chunk_id_hit_rank"] is None
    assert r["chunk_id_mrr"] is None


def test_skipped_when_no_expected_keywords():
    """Question sans expected_keywords ni gold_chunk_id → skipped."""
    q = {"query": "test"}
    r = _score_question(q, _chunks("chunk arbitraire"))

    assert r["skipped"] is True
    assert r["recall_at_k"] is None
    assert r["first_hit_rank"] is None
