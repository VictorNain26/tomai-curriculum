"""
Tests du pipeline d'ingestion RAG.

Structure :
- Unitaires (pas d'I/O fichier, pas d'API) — rapides, toujours actifs
- Intégration (@pytest.mark.integration) — lisent data/raw/*.txt, sans API

Exécution :
  uv run pytest tests/test_ingest.py                    # unitaires uniquement
  uv run pytest tests/test_ingest.py -m integration     # + intégration fichiers réels
  uv run pytest tests/test_ingest.py -v                 # verbeux
"""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

import pytest

from schema import Matiere

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ── extract_section ───────────────────────────────────────────────────────────


def test_extract_section_ignores_indented_false_positive():
    """'Histoire' indenté dans un tableau ne doit pas stopper la section Français."""
    from scripts.ingest import extract_section

    text = load_fixture("sample_cycle4_frag.txt")
    result = extract_section(text, r"^Français\s*$", r"^Histoire\s*$", blank_line_after_header=True)

    assert "développer des compétences de lecture" in result
    assert "narratifs, descriptifs, argumentatifs" in result


def test_extract_section_finds_real_header_after_indented_false_positive():
    from scripts.ingest import extract_section

    text = load_fixture("sample_cycle4_frag.txt")
    result = extract_section(text, r"^Histoire\s*$", None, blank_line_after_header=True)

    assert "L'enseignement de l'histoire" in result


def test_extract_section_blank_line_skips_toc_entry():
    from scripts.ingest import extract_section

    toc_text = "Français\nLangues vivantes\nAutre sujet\n\nFrançais\n\nVrai contenu pédagogique."
    result = extract_section(toc_text, r"^Français\s*$", None, blank_line_after_header=True)

    assert "Vrai contenu pédagogique" in result
    assert "Langues vivantes" not in result


def test_extract_section_handles_formfeed_prefix():
    from scripts.ingest import extract_section

    text = "Section précédente.\n\x0cPhysique-Chimie\n\nContenu de physique.\n"
    result = extract_section(text, r"^Physique-Chimie", None)
    assert "Contenu de physique" in result


def test_extract_section_returns_empty_when_pattern_not_found():
    from scripts.ingest import extract_section

    result = extract_section("texte sans header.", r"^Mathématiques\s*$", None)
    assert result == ""


def test_extract_section_stops_at_end_pattern():
    from scripts.ingest import extract_section

    text = load_fixture("sample_cycle4_frag.txt")
    result = extract_section(text, r"^Français\s*$", r"^Histoire\s*$")
    assert "L'enseignement de l'histoire" not in result


# ── load_source_text ──────────────────────────────────────────────────────────


def test_load_source_text_raises_on_missing_file():
    from scripts.ingest import load_source_text

    source = {
        "file": "fichier_inexistant_99",
        "matiere": Matiere.MATHEMATIQUES,
        "section_pattern": None,
        "section_name": "Test",
    }
    with pytest.raises(FileNotFoundError, match="fichier_inexistant_99"):
        load_source_text(source)


def test_load_source_text_raises_on_section_not_found():
    from scripts.ingest import load_source_text

    source = {
        "file": "programme_maths_cycle4_BO2026",
        "matiere": Matiere.MATHEMATIQUES,
        "section_pattern": r"^SECTION_QUI_NEXISTE_PAS_9999",
        "section_name": "Section fictive",
    }
    with pytest.raises(ValueError, match="introuvable"):
        load_source_text(source)


# ── chunk_text (RecursiveChunker + tokenizer Mistral) ────────────────────────


_SOURCE_MATHS = {
    "file": "programme_maths_cycle4_BO2026",
    "matiere": Matiere.MATHEMATIQUES,
    "section_pattern": None,
    "section_name": "Mathématiques",
}


@pytest.mark.skipif(
    not os.environ.get("RUN_MISTRAL_TOKENIZER_TESTS"),
    reason="mistral_common ~500MB — set RUN_MISTRAL_TOKENIZER_TESTS=1 pour activer",
)
def test_chunk_text_produces_chunks():
    """Smoke test : un texte assez long produit au moins 1 chunk valide."""
    from scripts.ingest import chunk_text

    long_text = (
        "Les nombres rationnels permettent de représenter des fractions ordinaires.\n"
        "Un nombre rationnel est le rapport de deux entiers relatifs non nuls.\n"
    ) * 30
    chunks = chunk_text(long_text, _SOURCE_MATHS)

    assert len(chunks) >= 1
    for c in chunks:
        assert len(c["text"]) >= 50


# ── expand_for_niveaux ───────────────────────────────────────────────────────


def test_expand_for_niveaux_cycle4_triples_chunks():
    """Un fichier cycle4 → 3 niveaux → chaque chunk dupliqué 3×."""
    from scripts.ingest import expand_for_niveaux

    base = [
        {
            "text": "Texte pédagogique sur les mathématiques du cycle 4 de collège en France.",
            "source_file": "programme_maths_cycle4_BO2026",
            "matiere": Matiere.MATHEMATIQUES.value,
            "section": "Nombres",
            "chunk_index": 0,
        }
    ]
    expanded = expand_for_niveaux(base)

    assert len(expanded) == 3
    niveaux = sorted(c["niveau"] for c in expanded)
    assert niveaux == ["cinquieme", "quatrieme", "troisieme"][::1] or set(niveaux) == {
        "cinquieme",
        "quatrieme",
        "troisieme",
    }


def test_expand_for_niveaux_college_quadruples_chunks():
    """Un fichier college (langues) couvre les 4 niveaux collège."""
    from scripts.ingest import expand_for_niveaux

    base = [
        {
            "text": "Apprentissage de l'anglais au collège, du A1 au A2+ selon le CECRL européen.",
            "source_file": "programme_anglais_college_BO2025",
            "matiere": Matiere.ANGLAIS.value,
            "section": "Anglais",
            "chunk_index": 0,
        }
    ]
    expanded = expand_for_niveaux(base)

    assert len(expanded) == 4
    assert set(c["niveau"] for c in expanded) == {
        "sixieme",
        "cinquieme",
        "quatrieme",
        "troisieme",
    }


def test_expand_preserves_chunk_text_and_section():
    """L'expansion ne modifie ni text ni section, seul niveau diffère."""
    from scripts.ingest import expand_for_niveaux

    base = [
        {
            "text": "Texte commun du cycle 4 partagé entre les trois niveaux du collège.",
            "source_file": "programme_maths_cycle4_BO2026",
            "matiere": Matiere.MATHEMATIQUES.value,
            "section": "Nombres",
            "chunk_index": 0,
        }
    ]
    expanded = expand_for_niveaux(base)

    texts = {c["text"] for c in expanded}
    sections = {c["section"] for c in expanded}
    assert len(texts) == 1
    assert len(sections) == 1


# ── validate_chunks ───────────────────────────────────────────────────────────


def _valid_chunk(**overrides) -> dict:
    base = {
        "text": (
            "Les propriétés des triangles rectangles sont fondamentales "
            "en géométrie du cycle 4 des collèges français."
        ),
        "source_file": "programme_maths_cycle4_BO2026",
        "matiere": "mathematiques",
        "niveau": "cinquieme",
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
    assert result[0]["niveau"] == "cinquieme"
    assert result[0]["cycle"] == "cycle4"


def test_validate_chunks_payload_canonical_no_aliases():
    """Payload Qdrant canonique pur — aucun alias title/content."""
    from scripts.ingest import validate_chunks

    result = validate_chunks([_valid_chunk()])
    payload = result[0]

    expected = {"text", "source_file", "matiere", "niveau", "cycle", "section", "chunk_index"}
    assert set(payload.keys()) == expected
    assert "title" not in payload
    assert "content" not in payload


def test_validate_chunks_fails_on_text_too_short():
    from pydantic import ValidationError

    from scripts.ingest import validate_chunks

    with pytest.raises(ValidationError):
        validate_chunks([_valid_chunk(text="Court.")])


def test_validate_chunks_fails_on_invalid_matiere():
    from scripts.ingest import validate_chunks

    with pytest.raises(ValueError):
        validate_chunks([_valid_chunk(matiere="musique")])


def test_validate_chunks_fails_on_invalid_niveau():
    from scripts.ingest import validate_chunks

    with pytest.raises(ValueError):
        validate_chunks([_valid_chunk(niveau="maternelle")])


# ── Idempotence ID (uuid5 inclut matière + niveau + text) ───────────────────


def _make_id(matiere: str, niveau: str, text: str) -> str:
    """Reproduit le calcul d'ID utilisé par upsert_to_qdrant."""
    seed = f"{matiere}:{niveau}:{text}"
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, h))


def test_id_stable_same_triple():
    """Même (matière, niveau, text) → même UUID."""
    assert _make_id("mathematiques", "cinquieme", "Les puissances de dix.") == _make_id(
        "mathematiques", "cinquieme", "Les puissances de dix."
    )


def test_id_differs_per_niveau():
    """Même text + matière, niveau différent → UUIDs distincts."""
    text = "Texte commun cycle 4."
    assert _make_id("svt", "cinquieme", text) != _make_id("svt", "quatrieme", text)


def test_id_differs_per_matiere_for_shared_text():
    """
    Texte commun entre matières (préambules pédagogiques langues college) →
    UUIDs distincts. Sans matière dans le seed, le dernier upsert écrasait les
    autres (bug détecté lors de l'audit `--list-missing` : sections
    'Le cahier', 'Composante pragmatique' absentes du filtre matiere=anglais).
    """
    text = "L'apprentissage repose sur divers outils, parmi lesquels le cahier."
    ids = {_make_id(m, "cinquieme", text) for m in ["anglais", "espagnol", "allemand", "italien"]}
    assert len(ids) == 4, "Chaque matière doit avoir son propre UUID pour un texte partagé"


# ── L2 normalize ─────────────────────────────────────────────────────────────


def test_l2_normalize_produces_unit_vector():
    from schema import l2_normalize

    vec = [3.0, 4.0]  # norme = 5
    normed = l2_normalize(vec)
    norm = sum(v * v for v in normed) ** 0.5

    assert abs(norm - 1.0) < 1e-9


def test_l2_normalize_raises_on_zero_vector():
    from schema import l2_normalize

    with pytest.raises(ValueError, match="norme nulle"):
        l2_normalize([0.0, 0.0, 0.0])


# ── Sources catalog ───────────────────────────────────────────────────────────


def test_sources_uses_matiere_enums():
    """SOURCES contient des Matiere (enum), pas des strings."""
    from scripts.ingest import SOURCES

    for s in SOURCES:
        assert isinstance(s["matiere"], Matiere), (
            f"SOURCES[{s['file']}] doit utiliser Matiere enum, pas string."
        )


def test_sources_files_cover_college():
    """Toutes les sources se dérivent vers au moins un niveau collège (6e→3e)."""
    from schema import derive_niveaux_from_file
    from scripts.ingest import SOURCES

    college_niveaux = {"sixieme", "cinquieme", "quatrieme", "troisieme"}
    for s in SOURCES:
        _cycle, niveaux = derive_niveaux_from_file(s["file"])
        nv_values = {n.value for n in niveaux}
        assert nv_values & college_niveaux, (
            f"Source {s['file']} ne couvre aucun niveau collège (niveaux={nv_values})"
        )
