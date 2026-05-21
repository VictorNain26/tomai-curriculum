"""
Tests générateur golden set document-grounded.

Couvre :
- Pydantic GoldenQuestion : validations + sérialisation.
- stratified_sample : équilibre par (matière × niveau), respect du target.
- _compute_chunk_id : parité avec le hash UUID5 que ingest.upsert_to_qdrant
  utilise (identité de la table de vérité).
- _build_question : filtre des keywords absents du chunk + erreur si
  insuffisant (anti-hallucination).
"""

from __future__ import annotations

import hashlib
import random
import uuid

import pytest
from pydantic import ValidationError

from schema import GoldenQuestion, Matiere, NiveauCollege
from scripts.generate_golden import (
    _build_question,
    _compute_chunk_id,
    stratified_sample,
)

# ── GoldenQuestion Pydantic ────────────────────────────────────────────────


def test_golden_question_minimal_valid():
    q = GoldenQuestion(
        query="Qu'est-ce que le théorème de Pythagore ?",
        matiere=Matiere.MATHEMATIQUES,
        niveau=NiveauCollege.QUATRIEME,
        expected_keywords=["pythagore", "hypoténuse", "triangle rectangle"],
    )
    assert q.gold_chunk_id is None
    assert q.gold_section is None


def test_golden_question_with_grounding():
    q = GoldenQuestion(
        query="Quelle est la formule du périmètre d'un rectangle ?",
        matiere=Matiere.MATHEMATIQUES,
        niveau=NiveauCollege.CINQUIEME,
        expected_keywords=["périmètre", "rectangle", "longueur"],
        gold_chunk_id=str(uuid.uuid4()),
        gold_section="Grandeurs et mesures",
        gold_source_file="programme_maths_cycle4_BO2026",
    )
    assert q.gold_section == "Grandeurs et mesures"


def test_golden_question_query_too_short():
    with pytest.raises(ValidationError):
        GoldenQuestion(
            query="court",
            matiere=Matiere.MATHEMATIQUES,
            niveau=NiveauCollege.CINQUIEME,
            expected_keywords=["a", "b", "c"],
        )


def test_golden_question_needs_at_least_two_keywords():
    with pytest.raises(ValidationError):
        GoldenQuestion(
            query="Qu'est-ce qu'une fraction ?",
            matiere=Matiere.MATHEMATIQUES,
            niveau=NiveauCollege.CINQUIEME,
            expected_keywords=["fraction"],
        )


# ── chunk_id parité avec ingest.upsert_to_qdrant ───────────────────────────


def test_compute_chunk_id_matches_ingest_formula():
    """Le hash doit matcher exactement ce que ingest.upsert_to_qdrant produit."""
    matiere = "mathematiques"
    niveau = "cinquieme"
    text = "Un nombre relatif est un nombre positif, négatif ou nul."
    expected_seed = f"{matiere}:{niveau}:{text}"
    expected_hash = hashlib.sha256(expected_seed.encode("utf-8")).hexdigest()
    expected_id = str(uuid.uuid5(uuid.NAMESPACE_URL, expected_hash))

    assert _compute_chunk_id(matiere, niveau, text) == expected_id


def test_compute_chunk_id_stable_across_calls():
    a = _compute_chunk_id("svt", "cinquieme", "La photosynthèse produit du dioxygène.")
    b = _compute_chunk_id("svt", "cinquieme", "La photosynthèse produit du dioxygène.")
    assert a == b


def test_compute_chunk_id_distinct_per_matiere():
    text = "Texte identique partagé."
    a = _compute_chunk_id("anglais", "cinquieme", text)
    b = _compute_chunk_id("espagnol", "cinquieme", text)
    assert a != b


# ── stratified_sample ──────────────────────────────────────────────────────


def _mk_chunks(matiere: str, niveau: str, count: int) -> list[dict]:
    return [
        {
            "text": f"chunk #{i} matière {matiere} niveau {niveau} contenu pédagogique " * 5,
            "source_file": f"programme_{matiere}_test",
            "matiere": matiere,
            "section": "Section A",
            "chunk_index": i,
            "niveau": niveau,
        }
        for i in range(count)
    ]


def test_stratified_sample_balances_per_matiere_niveau():
    chunks = _mk_chunks("mathematiques", "cinquieme", 50)
    chunks += _mk_chunks("francais", "cinquieme", 50)
    chunks += _mk_chunks("svt", "troisieme", 50)
    rng = random.Random(42)

    sampled = stratified_sample(chunks, target=30, matiere_filter=None, rng=rng)
    assert len(sampled) <= 30

    by_strate: dict[tuple[str, str], int] = {}
    for c in sampled:
        key = (c["matiere"], c["niveau"])
        by_strate[key] = by_strate.get(key, 0) + 1

    # Chaque strate doit être représentée (>=1 chunk)
    assert len(by_strate) == 3
    for n in by_strate.values():
        assert n >= 1


def test_stratified_sample_filter_matiere():
    chunks = _mk_chunks("mathematiques", "cinquieme", 20)
    chunks += _mk_chunks("francais", "cinquieme", 20)
    rng = random.Random(0)
    sampled = stratified_sample(chunks, target=10, matiere_filter="mathematiques", rng=rng)
    assert all(c["matiere"] == "mathematiques" for c in sampled)


def test_stratified_sample_empty_after_filter():
    chunks = _mk_chunks("mathematiques", "cinquieme", 10)
    rng = random.Random(0)
    sampled = stratified_sample(chunks, target=10, matiere_filter="philosophie", rng=rng)
    assert sampled == []


# ── _build_question — filtre des keywords absents ──────────────────────────


def _sample_chunk() -> dict:
    return {
        "text": "Le théorème de Pythagore relie les côtés d'un triangle rectangle. "
        "Si l'hypoténuse mesure c et les côtés a et b, alors c² = a² + b².",
        "source_file": "programme_maths_cycle4_BO2026",
        "matiere": "mathematiques",
        "section": "Géométrie",
        "chunk_index": 5,
        "niveau": "quatrieme",
    }


def test_build_question_filters_absent_keywords():
    chunk = _sample_chunk()
    data = {
        "query": "Énonce le théorème de Pythagore.",
        # Mix de keywords présents (pythagore, hypoténuse, triangle rectangle)
        # et absents (volcan, ADN) — les absents doivent être filtrés.
        "expected_keywords": ["pythagore", "hypoténuse", "triangle rectangle", "volcan", "adn"],
    }
    q = _build_question(chunk, data)
    assert "volcan" not in q.expected_keywords
    assert "adn" not in q.expected_keywords
    assert "pythagore" in [k.lower() for k in q.expected_keywords]
    assert q.gold_chunk_id is not None
    assert q.gold_section == "Géométrie"


def test_build_question_raises_when_no_valid_keyword():
    chunk = _sample_chunk()
    data = {
        "query": "Question non liée au chunk.",
        "expected_keywords": ["volcan", "adn", "haïku"],  # aucun présent
    }
    with pytest.raises(ValueError, match="keywords insuffisants"):
        _build_question(chunk, data)


def test_build_question_raises_when_only_one_valid_keyword():
    chunk = _sample_chunk()
    data = {
        "query": "Question avec un seul keyword valide.",
        "expected_keywords": ["pythagore", "volcan", "adn"],  # 1 valide
    }
    with pytest.raises(ValueError, match="keywords insuffisants"):
        _build_question(chunk, data)
