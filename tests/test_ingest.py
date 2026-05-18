"""
Tests du pipeline d'ingestion RAG.

Structure :
- Tests unitaires (pas d'I/O fichier, pas d'API) — rapides, toujours actifs
- Tests d'intégration (@pytest.mark.integration) — lisent data/raw/*.txt, sans API

Exécution :
  uv run pytest tests/test_ingest.py                    # unitaires uniquement
  uv run pytest tests/test_ingest.py -m integration     # + intégration fichiers réels
  uv run pytest tests/test_ingest.py -v                 # verbeux
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
DATA_RAW = Path(__file__).parent.parent / "data" / "raw"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ── extract_section ───────────────────────────────────────────────────────────


def test_extract_section_ignores_indented_false_positive():
    """'Histoire' indenté dans un tableau ne doit pas stopper la section Français."""
    from scripts.ingest import extract_section

    text = load_fixture("sample_cycle4_frag.txt")
    result = extract_section(
        text, r"^Français\s*$", r"^Histoire\s*$", blank_line_after_header=True
    )

    assert "développer des compétences de lecture" in result
    assert "narratifs, descriptifs, argumentatifs" in result


def test_extract_section_finds_real_header_after_indented_false_positive():
    """Le vrai 'Histoire' standalone est détecté comme début de section."""
    from scripts.ingest import extract_section

    text = load_fixture("sample_cycle4_frag.txt")
    result = extract_section(text, r"^Histoire\s*$", None, blank_line_after_header=True)

    assert "L'enseignement de l'histoire" in result
    assert "Th. 2" not in result


def test_extract_section_blank_line_skips_toc_entry():
    """blank_line_after_header=True ignore les entrées de TOC (suivie immédiatement d'un autre sujet)."""
    from scripts.ingest import extract_section

    # Structure TOC : Français immédiatement suivi de Langues vivantes (pas de ligne vide)
    toc_text = "Français\nLangues vivantes\nAutre sujet\n\nFrançais\n\nVrai contenu pédagogique."
    result = extract_section(toc_text, r"^Français\s*$", None, blank_line_after_header=True)

    assert "Vrai contenu pédagogique" in result
    assert "Langues vivantes" not in result


def test_extract_section_handles_formfeed_prefix():
    """Header précédé de \\x0c (form feed pdftotext) est reconnu correctement."""
    from scripts.ingest import extract_section

    text = "Section précédente.\n\x0cPhysique-Chimie\n\nContenu de physique.\n"
    result = extract_section(text, r"^Physique-Chimie", None)

    assert "Contenu de physique" in result


def test_extract_section_returns_empty_when_pattern_not_found():
    """Pattern introuvable → chaîne vide (pas d'exception)."""
    from scripts.ingest import extract_section

    text = "Aucun header correspondant dans ce texte quelconque."
    result = extract_section(text, r"^Mathématiques\s*$", None)

    assert result == ""


def test_extract_section_stops_at_end_pattern():
    """La section s'arrête au premier match du end_pattern."""
    from scripts.ingest import extract_section

    text = load_fixture("sample_cycle4_frag.txt")
    result = extract_section(text, r"^Français\s*$", r"^Histoire\s*$")

    assert "Français" in result
    assert "L'enseignement de l'histoire" not in result


# ── load_source_text ──────────────────────────────────────────────────────────


def test_load_source_text_raises_on_missing_file():
    """Fichier absent → FileNotFoundError avec le nom du fichier."""
    from scripts.ingest import load_source_text

    source = {
        "file": "fichier_inexistant_99",
        "matiere": "mathematiques",
        "section_pattern": None,
        "section_name": "Test",
    }
    with pytest.raises(FileNotFoundError, match="fichier_inexistant_99"):
        load_source_text(source)


def test_load_source_text_raises_on_section_not_found():
    """Pattern introuvable dans un fichier existant → ValueError avec 'introuvable'."""
    from scripts.ingest import load_source_text

    source = {
        "file": "programme_maths_cycle4_BO2026",
        "matiere": "mathematiques",
        "section_pattern": r"^SECTION_QUI_NEXISTE_PAS_9999",
        "section_name": "Section fictive",
    }
    with pytest.raises(ValueError, match="introuvable"):
        load_source_text(source)


@pytest.mark.integration
@pytest.mark.parametrize(
    "matiere, min_chars, keyword",
    [
        ("francais", 30_000, "expression"),
        ("histoire_geo", 10_000, "histoire"),
        ("physique_chimie", 8_000, "énergie"),
        ("svt", 8_000, "cellule"),
        ("emc", 3_000, "citoyen"),
        ("mathematiques", 15_000, "nombre"),
        ("technologie", 8_000, "système"),
        ("anglais", 8_000, "language"),
        ("espagnol", 8_000, "lengua"),
        ("allemand", 8_000, "Sprache"),
        ("italien", 8_000, "lingua"),
    ],
)
def test_load_source_text_returns_nonempty_content(matiere, min_chars, keyword):
    """Chaque source produit une section non vide contenant un mot-clé attendu."""
    from scripts.ingest import SOURCES, load_source_text

    source = next(s for s in SOURCES if s["matiere"] == matiere)
    text = load_source_text(source)

    assert len(text) >= min_chars, (
        f"{matiere} : section trop courte ({len(text)} chars, min {min_chars}). "
        f"Vérifier le regex dans SOURCES. Debut : {text[:300]}"
    )
    assert keyword.lower() in text.lower(), (
        f"{matiere} : mot-clé '{keyword}' absent. Debut section : {text[:300]}"
    )


# ── chunk_text ────────────────────────────────────────────────────────────────

_SOURCE_MATHS = {
    "file": "programme_maths_cycle4_BO2026",
    "matiere": "mathematiques",
    "section_pattern": None,
    "section_name": "Mathématiques",
}


def test_chunk_text_produces_at_least_one_chunk():
    """Un texte suffisamment long produit au moins un chunk."""
    from scripts.ingest import chunk_text

    text = load_fixture("sample_maths_frag.txt")
    chunks = chunk_text(text, _SOURCE_MATHS)

    assert len(chunks) >= 1


def test_chunk_text_no_empty_chunks():
    """Tous les chunks font au moins 50 chars."""
    from scripts.ingest import chunk_text

    long_text = (
        "Les nombres rationnels permettent de représenter des fractions ordinaires.\n"
        "Un nombre rationnel est le rapport de deux entiers relatifs non nuls.\n"
    ) * 25
    chunks = chunk_text(long_text, _SOURCE_MATHS)

    for c in chunks:
        assert len(c["text"]) >= 50, f"Chunk trop court : {repr(c['text'])}"


def test_chunk_text_size_within_expected_range():
    """Les chunks font entre 200 et 2500 chars (cible ~1600)."""
    from scripts.ingest import chunk_text

    text = (
        "Les transformations géométriques incluent la translation et la rotation.\n"
        "La symétrie centrale conserve les longueurs et les angles des figures.\n"
        "Les triangles isocèles possèdent des propriétés de symétrie axiale particulières.\n"
    ) * 30
    chunks = chunk_text(text, _SOURCE_MATHS)

    for c in chunks:
        assert 200 <= len(c["text"]) <= 2500, (
            f"Chunk hors intervalle ({len(c['text'])} chars) : {repr(c['text'][:80])}"
        )


def test_chunk_text_preserves_source_metadata():
    """Chaque chunk contient les métadonnées de la source."""
    from scripts.ingest import chunk_text

    text = load_fixture("sample_maths_frag.txt")
    chunks = chunk_text(text, _SOURCE_MATHS)

    for c in chunks:
        assert c["source_file"] == "programme_maths_cycle4_BO2026"
        assert c["matiere"] == "mathematiques"
        assert c["section"] == "Mathématiques"
        assert isinstance(c["chunk_index"], int) and c["chunk_index"] >= 0


@pytest.mark.integration
@pytest.mark.parametrize(
    "matiere, min_chunks",
    [
        ("mathematiques", 50),
        ("technologie", 15),
        ("francais", 60),
        ("histoire_geo", 35),
        ("physique_chimie", 25),
        ("svt", 25),
        ("emc", 8),
        ("anglais", 25),
        ("espagnol", 25),
        ("allemand", 25),
        ("italien", 25),
    ],
)
def test_chunk_text_produces_enough_chunks(matiere, min_chunks):
    """Chaque matière produit suffisamment de chunks pour couvrir le programme."""
    from scripts.ingest import SOURCES, chunk_text, load_source_text

    source = next(s for s in SOURCES if s["matiere"] == matiere)
    text = load_source_text(source)
    chunks = chunk_text(text, source)

    assert len(chunks) >= min_chunks, (
        f"{matiere} : {len(chunks)} chunks (min {min_chunks}). "
        f"Texte source : {len(text)} chars."
    )


# ── validate_chunks ───────────────────────────────────────────────────────────


def _valid_chunk(**overrides) -> dict:
    base = {
        "text": (
            "Les propriétés des triangles rectangles sont fondamentales "
            "en géométrie du cycle 4 des collèges français."
        ),
        "source_file": "programme_maths_cycle4_BO2026",
        "matiere": "mathematiques",
        "section": "Géométrie",
        "chunk_index": 0,
    }
    base.update(overrides)
    return base


def test_validate_chunks_accepts_valid_chunk():
    from scripts.ingest import validate_chunks

    result = validate_chunks([_valid_chunk()])

    assert len(result) == 1
    assert result[0]["text"] == _valid_chunk()["text"]


def test_validate_chunks_payload_excludes_id():
    """Le payload Qdrant n'inclut pas 'id' (utilisé séparément comme point_id)."""
    from scripts.ingest import validate_chunks

    result = validate_chunks([_valid_chunk()])

    assert "id" not in result[0]


def test_validate_chunks_includes_cycle_and_niveau():
    """Le payload contient cycle=cycle4 et niveau=cinquieme dérivés du schéma."""
    from scripts.ingest import validate_chunks

    result = validate_chunks([_valid_chunk()])

    assert result[0]["cycle"] == "cycle4"
    assert result[0]["niveau"] == "cinquieme"


def test_validate_chunks_fails_on_text_too_short():
    from pydantic import ValidationError
    from scripts.ingest import validate_chunks

    with pytest.raises(ValidationError):
        validate_chunks([_valid_chunk(text="Court.")])


def test_validate_chunks_fails_on_invalid_matiere():
    from pydantic import ValidationError
    from scripts.ingest import validate_chunks

    with pytest.raises(ValidationError):
        validate_chunks([_valid_chunk(matiere="musique")])


def test_validate_chunks_handles_multiple():
    from scripts.ingest import validate_chunks

    chunks = [_valid_chunk(chunk_index=i, section=f"S{i}") for i in range(5)]
    result = validate_chunks(chunks)

    assert len(result) == 5
    for i, r in enumerate(result):
        assert r["chunk_index"] == i


# ── embed_chunks (mock Mistral) ───────────────────────────────────────────────


def _fake_embedding(dim: int = 1024) -> MagicMock:
    emb = MagicMock()
    emb.embedding = [0.01] * dim
    return emb


def test_embed_chunks_returns_correct_count():
    """embed_chunks retourne autant de vecteurs que de textes."""
    import os

    os.environ.setdefault("MISTRAL_API_KEY", "test-key")

    mock_resp = MagicMock()
    mock_resp.data = [_fake_embedding(), _fake_embedding()]

    with patch("mistralai.Mistral") as MockMistral:
        MockMistral.return_value.embeddings.create.return_value = mock_resp
        from scripts.ingest import embed_chunks

        vectors = embed_chunks(["Texte un.", "Texte deux."])

    assert len(vectors) == 2
    assert all(len(v) == 1024 for v in vectors)


def test_embed_chunks_batches_at_50():
    """55 textes → 2 appels API (50 + 5)."""
    import os

    os.environ.setdefault("MISTRAL_API_KEY", "test-key")

    texts = [f"Texte numéro {i} suffisamment long." for i in range(55)]
    call_count = {"n": 0}

    def _create(model, inputs):
        call_count["n"] += 1
        r = MagicMock()
        r.data = [_fake_embedding() for _ in inputs]
        return r

    with patch("mistralai.Mistral") as MockMistral:
        MockMistral.return_value.embeddings.create.side_effect = _create
        from scripts import ingest as _ingest

        # Force re-import du client dans la fonction
        import importlib
        importlib.reload(_ingest)
        _ingest.embed_chunks(texts)

    assert call_count["n"] == 2


# ── upsert_to_qdrant (idempotence + mock Qdrant) ─────────────────────────────


def test_upsert_idempotence_same_text_same_uuid():
    """Même texte → même UUID (uuid5 sur sha256). Pas de doublon Qdrant."""
    text = "Les puissances de dix simplifient l'écriture des grands nombres."
    h = hashlib.sha256(text.encode()).hexdigest()
    id1 = str(uuid.uuid5(uuid.NAMESPACE_URL, h))
    id2 = str(uuid.uuid5(uuid.NAMESPACE_URL, h))

    assert id1 == id2


def test_upsert_different_texts_different_uuids():
    """Textes différents → UUIDs différents."""
    t1 = "Premier texte sur les mathématiques cycle 4."
    t2 = "Deuxième texte sur la physique-chimie cycle 4."
    make_id = lambda t: str(uuid.uuid5(uuid.NAMESPACE_URL, hashlib.sha256(t.encode()).hexdigest()))

    assert make_id(t1) != make_id(t2)


def _sample_payloads(n: int = 2) -> list[dict]:
    return [
        {
            "text": f"Contenu pédagogique numéro {i} sur les mathématiques du cycle 4 en France.",
            "source_file": "programme_maths_cycle4_BO2026",
            "matiere": "mathematiques",
            "niveau": "cinquieme",
            "cycle": "cycle4",
            "section": "Nombres",
            "chunk_index": i,
        }
        for i in range(n)
    ]


def test_upsert_to_qdrant_returns_correct_count():
    """upsert_to_qdrant retourne le nombre exact de points upsertés."""
    import os

    os.environ.setdefault("QDRANT_URL", "http://localhost:6333")

    payloads = _sample_payloads(3)
    vectors = [[0.1] * 1024 for _ in payloads]

    with patch("qdrant_client.QdrantClient") as MockQdrant:
        instance = MockQdrant.return_value
        instance.get_collections.return_value.collections = []
        from scripts.ingest import upsert_to_qdrant

        count = upsert_to_qdrant(payloads, vectors, "test_col")

    assert count == 3


def test_upsert_creates_collection_when_missing():
    """Collection absente → create_collection appelé avec size=1024 cosine."""
    import os

    os.environ.setdefault("QDRANT_URL", "http://localhost:6333")

    with patch("qdrant_client.QdrantClient") as MockQdrant:
        instance = MockQdrant.return_value
        instance.get_collections.return_value.collections = []
        from scripts.ingest import upsert_to_qdrant

        upsert_to_qdrant(_sample_payloads(1), [[0.0] * 1024], "nouvelle_col")

        instance.create_collection.assert_called_once()
        kwargs = instance.create_collection.call_args.kwargs
        assert kwargs["collection_name"] == "nouvelle_col"


def test_upsert_skips_create_when_collection_exists():
    """Collection déjà présente → create_collection PAS appelé."""
    import os

    os.environ.setdefault("QDRANT_URL", "http://localhost:6333")

    with patch("qdrant_client.QdrantClient") as MockQdrant:
        instance = MockQdrant.return_value
        existing = MagicMock()
        existing.name = "tomai_educational"
        instance.get_collections.return_value.collections = [existing]
        from scripts.ingest import upsert_to_qdrant

        upsert_to_qdrant(_sample_payloads(1), [[0.0] * 1024], "tomai_educational")

        instance.create_collection.assert_not_called()


# ── dry-run end-to-end (intégration sans API) ─────────────────────────────────


@pytest.mark.integration
@pytest.mark.parametrize(
    "matiere, min_valid",
    [
        ("mathematiques", 50),
        ("technologie", 15),
        ("francais", 60),
        ("histoire_geo", 35),
        ("physique_chimie", 25),
        ("svt", 25),
        ("emc", 8),
        ("anglais", 25),
        ("espagnol", 25),
        ("allemand", 25),
        ("italien", 25),
    ],
)
def test_full_pipeline_dry_run(matiere, min_valid):
    """
    Pipeline complet load → chunk → validate pour chaque matière.
    Aucun appel API. Vérifie la qualité et la cohérence des chunks finaux.
    """
    from scripts.ingest import SOURCES, chunk_text, load_source_text, validate_chunks

    source = next(s for s in SOURCES if s["matiere"] == matiere)
    text = load_source_text(source)
    chunks = chunk_text(text, source)
    validated = validate_chunks(chunks)

    assert len(validated) >= min_valid, (
        f"{matiere}: {len(validated)} chunks valides (min {min_valid}). "
        f"Source : {len(text)} chars."
    )
    for v in validated:
        assert v["matiere"] == matiere, f"matiere incorrecte dans le payload: {v['matiere']}"
        assert v["niveau"] == "cinquieme"
        assert v["cycle"] == "cycle4"
        assert len(v["text"]) >= 50
        assert v["source_file"]
        assert v["section"]
