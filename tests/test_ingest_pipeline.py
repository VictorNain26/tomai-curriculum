"""
Tests pipeline ingestion : embed cache, idempotence, prune.

Pas de réseau : on mocke Mistral et Qdrant. Le but est de vérifier la
logique applicative (hashing, cache, idempotence), pas les SDK externes.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.ingest import (
    compute_content_hash,
    doc_id_from_hash,
    load_documents,
    normalize_vector,
)

# =============================================================================
# Helpers
# =============================================================================


def _sample_doc(title: str = "Titre Test", content: str | None = None) -> dict:
    """Document JSONL minimal conforme au schema."""
    return {
        "title": title,
        "domaine": "Domaine Test",
        "content_type": "definition",
        "difficulty": "standard",
        "content": (
            content
            or "Contenu pédagogique de test suffisamment long pour passer la validation "
            "Pydantic. Il doit dépasser 200 caractères pour être accepté par le schema "
            "qui impose un minimum, et inclure un exemple concret pour la note de structure. "
            "Voici donc du texte de remplissage cohérent."
        ),
    }


def _write_jsonl(path: Path, docs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")


# =============================================================================
# compute_content_hash
# =============================================================================


def test_content_hash_is_stable_on_identical_input():
    h1 = compute_content_hash("cinquieme", "mathematiques", "Titre", "contenu")
    h2 = compute_content_hash("cinquieme", "mathematiques", "Titre", "contenu")
    assert h1 == h2


def test_content_hash_changes_when_content_changes():
    h1 = compute_content_hash("cinquieme", "mathematiques", "Titre", "contenu A")
    h2 = compute_content_hash("cinquieme", "mathematiques", "Titre", "contenu B")
    assert h1 != h2


def test_content_hash_changes_when_title_changes():
    h1 = compute_content_hash("cinquieme", "mathematiques", "Titre A", "contenu")
    h2 = compute_content_hash("cinquieme", "mathematiques", "Titre B", "contenu")
    assert h1 != h2


def test_content_hash_changes_when_niveau_or_matiere_changes():
    h1 = compute_content_hash("cinquieme", "mathematiques", "T", "c")
    h2 = compute_content_hash("quatrieme", "mathematiques", "T", "c")
    h3 = compute_content_hash("cinquieme", "francais", "T", "c")
    assert h1 != h2
    assert h1 != h3


# =============================================================================
# doc_id_from_hash
# =============================================================================


def test_doc_id_is_uuid5_deterministic():
    h = compute_content_hash("cinquieme", "mathematiques", "T", "c")
    assert doc_id_from_hash(h) == doc_id_from_hash(h)


def test_doc_id_differs_for_different_hashes():
    h1 = "a" * 64
    h2 = "b" * 64
    assert doc_id_from_hash(h1) != doc_id_from_hash(h2)


def test_rename_doc_produces_new_id():
    """Documente le choix intentionnel : renommer un doc crée un nouvel id Qdrant
    (et un orphelin de l'ancien que prune supprimera). Si quelqu'un simplifie
    `compute_content_hash` pour ignorer le title/content, ce test casse."""
    h_before = compute_content_hash("cinquieme", "mathematiques", "Pythagore", "Contenu identique")
    h_renamed = compute_content_hash(
        "cinquieme", "mathematiques", "Théorème de Pythagore", "Contenu identique"
    )
    h_recontent = compute_content_hash(
        "cinquieme", "mathematiques", "Pythagore", "Contenu différent"
    )
    # Title change → new id
    assert doc_id_from_hash(h_before) != doc_id_from_hash(h_renamed)
    # Content change → new id
    assert doc_id_from_hash(h_before) != doc_id_from_hash(h_recontent)


# Note : les tests sparse_vector_* ont été retirés avec scripts/migrate_collection.py
# lors de la refonte MVP-5ème (2026-05-11). Sparse vectors BM25 IDF reviendront en
# Phase 2 (RAGAS integration) via une implémentation conjointe avec ingest_lib si
# pertinent, sinon Qdrant natif Modifier.IDF côté collection config.
# Référence pre-MVP : tag git archive/v1.0-pre-mvp.


# =============================================================================
# normalize_vector
# =============================================================================


def test_normalize_vector_unit_norm():
    v = [3.0, 4.0]  # ||v|| = 5
    normalized = normalize_vector(v)
    norm = sum(x * x for x in normalized) ** 0.5
    assert abs(norm - 1.0) < 1e-9


def test_normalize_zero_vector_raises():
    with pytest.raises(ValueError, match="zero-magnitude"):
        normalize_vector([0.0, 0.0, 0.0])


# =============================================================================
# load_documents : validation + hash assignment
# =============================================================================


def test_load_documents_assigns_hash_and_id(tmp_path: Path):
    jsonl_path = tmp_path / "cycle4" / "cinquieme" / "mathematiques.jsonl"
    _write_jsonl(jsonl_path, [_sample_doc()])

    docs = load_documents([jsonl_path])

    assert len(docs) == 1
    d = docs[0]
    assert d["niveau"] == "cinquieme"
    assert d["matiere"] == "mathematiques"
    assert d["cycle"] == "cycle4"
    assert "content_hash" in d
    assert len(d["content_hash"]) == 64  # SHA-256 hex
    assert "id" in d  # UUID5 string


def test_load_documents_rejects_invalid(tmp_path: Path):
    import typer

    jsonl_path = tmp_path / "cycle4" / "cinquieme" / "mathematiques.jsonl"
    invalid = {"title": "x"}  # missing required fields, content trop court
    _write_jsonl(jsonl_path, [invalid])

    with pytest.raises(typer.Exit):
        load_documents([jsonl_path])


# =============================================================================
# Idempotence du embed cache
# =============================================================================


def test_embed_cache_skips_already_cached(tmp_path: Path, monkeypatch):
    """
    Le pipeline embed ne doit pas redemander à Mistral pour les content_hash
    déjà en cache. On vérifie en mockant la classe Mistral.
    """
    from scripts import ingest, ingest_lib

    cache_dir = tmp_path / "cache"
    # CACHE_ROOT vit dans ingest_lib depuis Phase 4. C'est le module qui possède
    # l'attribut qu'il faut patcher (le re-export depuis ingest ne suffit pas).
    monkeypatch.setattr(ingest_lib, "CACHE_ROOT", cache_dir)

    # Pré-remplit le cache avec un hash connu
    sample = _sample_doc("Théorème de Pythagore")
    known_hash = compute_content_hash(
        "cinquieme", "mathematiques", sample["title"], sample["content"]
    )
    cache_dir.mkdir(parents=True, exist_ok=True)
    model_cache = cache_dir / ingest.EMBEDDING_MODEL / "cache.jsonl"
    model_cache.parent.mkdir(parents=True, exist_ok=True)
    with open(model_cache, "w", encoding="utf-8") as f:
        f.write(json.dumps({"hash": known_hash, "vector": [0.1] * 1024}) + "\n")

    cache = ingest.load_embedding_cache()
    assert known_hash in cache
    assert len(cache[known_hash]) == 1024


def test_embed_cache_roundtrip(tmp_path: Path, monkeypatch):
    """Le append_to_cache + load_embedding_cache restitue exactement ce qui a été écrit."""
    from scripts import ingest, ingest_lib

    monkeypatch.setattr(ingest_lib, "CACHE_ROOT", tmp_path)

    items = [
        ("hash_a" + "0" * 58, [0.5] * 1024),
        ("hash_b" + "0" * 58, [1.0] * 1024),
    ]
    ingest.append_to_cache(items)

    cache = ingest.load_embedding_cache()
    assert len(cache) == 2
    assert cache[items[0][0]] == items[0][1]
    assert cache[items[1][0]] == items[1][1]


# =============================================================================
# Prune : find_orphans
# =============================================================================


def testfind_orphans_keeps_only_curriculum_points():
    """Les points sans niveau/matiere/title (hors curriculum) ne sont jamais marqués orphelins."""
    from scripts.ingest import find_orphans

    mock_client = MagicMock()

    # 3 points dans Qdrant :
    # - point1 : curriculum, dans current_ids → garde
    # - point2 : curriculum, PAS dans current_ids → orphelin
    # - point3 : hors curriculum (payload partiel) → ignoré
    mock_point_1 = MagicMock(id="point1", payload={"niveau": "x", "matiere": "y", "title": "z"})
    mock_point_2 = MagicMock(
        id="point2", payload={"niveau": "x", "matiere": "y", "title": "orphan"}
    )
    mock_point_3 = MagicMock(id="point3", payload={"other": "stuff"})

    mock_client.scroll.return_value = ([mock_point_1, mock_point_2, mock_point_3], None)

    orphans = find_orphans(mock_client, "test_collection", {"point1"})

    assert orphans == ["point2"]


def testfind_orphans_returns_empty_when_all_match():
    from scripts.ingest import find_orphans

    mock_client = MagicMock()
    mock_point = MagicMock(id="point1", payload={"niveau": "x", "matiere": "y", "title": "z"})
    mock_client.scroll.return_value = ([mock_point], None)

    orphans = find_orphans(mock_client, "test_collection", {"point1"})
    assert orphans == []


# =============================================================================
# Upsert : payload-only update quand content_hash inchangé
# =============================================================================


def testfetch_existing_hashes_extracts_content_hash():
    """fetch_existing_hashes doit extraire le content_hash du payload Qdrant."""
    from scripts.ingest import fetch_existing_hashes

    mock_client = MagicMock()
    mock_point_1 = MagicMock(id="id_1", payload={"content_hash": "hash_1"})
    mock_point_2 = MagicMock(id="id_2", payload={})  # pas de content_hash → skip
    mock_client.retrieve.return_value = [mock_point_1, mock_point_2]

    result = fetch_existing_hashes(mock_client, "test", ["id_1", "id_2"])

    assert result == {"id_1": "hash_1"}


@patch("scripts.ingest.QdrantClient")
def test_upsert_uses_set_payload_when_hash_unchanged(MockQdrant, tmp_path: Path, monkeypatch):
    """
    Quand le content_hash en Qdrant matche celui calculé localement, upsert
    doit faire `set_payload` (pas de recompute vector) au lieu de `upsert`.
    """
    from scripts import ingest, ingest_lib

    # Setup cache + JSONL minimal
    monkeypatch.setattr(ingest_lib, "CACHE_ROOT", tmp_path / "cache")
    jsonl_path = tmp_path / "cycle4" / "cinquieme" / "mathematiques.jsonl"
    sample = _sample_doc()
    _write_jsonl(jsonl_path, [sample])

    known_hash = compute_content_hash(
        "cinquieme", "mathematiques", sample["title"], sample["content"]
    )
    ingest.append_to_cache([(known_hash, [0.1] * 1024)])

    # Mock Qdrant : la collection existe, le point existe avec le bon hash
    mock_client = MockQdrant.return_value
    mock_client.collection_exists.return_value = True
    mock_existing_point = MagicMock(id=doc_id_from_hash(known_hash))
    mock_existing_point.payload = {"content_hash": known_hash}
    mock_client.retrieve.return_value = [mock_existing_point]

    monkeypatch.setattr(ingest, "get_all_jsonl_files", lambda *a, **k: [jsonl_path])

    ingest.upsert(
        qdrant_url="http://fake",
        qdrant_api_key="fake",
        collection="test",
    )

    # set_payload appelé, upsert non appelé pour le vecteur
    assert mock_client.set_payload.called
    mock_client.upsert.assert_not_called()
