"""Tests du schéma Chunk + dérivation niveaux + labels matières."""

from __future__ import annotations

import pytest

from schema import (
    MATIERE_LABELS,
    Chunk,
    Cycle,
    Matiere,
    NiveauCollege,
    NiveauLycee,
    cycle_from_niveau,
    derive_niveaux_from_file,
)

# ── Chunk Pydantic ───────────────────────────────────────────────────────────


def test_chunk_minimal():
    c = Chunk(
        text="Les nombres relatifs permettent de représenter des valeurs positives et négatives.",
        source_file="programme_maths_cycle4_BO2026",
        matiere=Matiere.MATHEMATIQUES,
        niveau=NiveauCollege.CINQUIEME,
        section="Nombres relatifs",
        chunk_index=0,
    )
    assert c.cycle == Cycle.CYCLE4
    assert c.matiere_label == "Mathématiques"


def test_chunk_text_too_short_fails():
    with pytest.raises(Exception):
        Chunk(
            text="court",
            source_file="prog",
            matiere=Matiere.FRANCAIS,
            niveau=NiveauCollege.CINQUIEME,
            section="test",
            chunk_index=0,
        )


def test_chunk_niveau_is_required():
    """niveau n'a plus de default — doit être fourni explicitement."""
    with pytest.raises(Exception):
        Chunk(
            text="Texte assez long pour passer la validation min_length 50 caractères ici.",
            source_file="prog",
            matiere=Matiere.FRANCAIS,
            section="test",
            chunk_index=0,
        )  # type: ignore[call-arg]


def test_qdrant_payload_canonical_schema():
    """to_qdrant_payload retourne le schema canonique pur — pas d'aliases compat."""
    c = Chunk(
        text="En géographie, le relief terrestre est étudié à travers différentes représentations.",
        source_file="programme_cycle4_BO2020",
        matiere=Matiere.HISTOIRE_GEO,
        niveau=NiveauCollege.QUATRIEME,
        section="Géographie",
        chunk_index=3,
    )
    payload = c.to_qdrant_payload()

    # Champs canoniques exacts (rien d'autre)
    expected_keys = {"text", "source_file", "matiere", "niveau", "cycle", "section", "chunk_index"}
    assert set(payload.keys()) == expected_keys

    # Valeurs
    assert payload["text"] == c.text
    assert payload["section"] == "Géographie"
    assert payload["matiere"] == "histoire_geo"
    assert payload["niveau"] == "quatrieme"
    assert payload["cycle"] == "cycle4"
    assert payload["chunk_index"] == 3
    assert payload["source_file"] == "programme_cycle4_BO2020"


# ── cycle_from_niveau ────────────────────────────────────────────────────────


def test_cycle_from_niveau():
    assert cycle_from_niveau(NiveauCollege.CINQUIEME) == Cycle.CYCLE4
    assert cycle_from_niveau(NiveauCollege.QUATRIEME) == Cycle.CYCLE4
    assert cycle_from_niveau(NiveauCollege.TROISIEME) == Cycle.CYCLE4
    assert cycle_from_niveau(NiveauCollege.SIXIEME) == Cycle.CYCLE3
    assert cycle_from_niveau("terminale") == Cycle.LYCEE
    assert cycle_from_niveau(NiveauLycee.SECONDE) == Cycle.LYCEE


def test_cycle_from_niveau_raises_on_unknown():
    with pytest.raises(ValueError, match="inconnu"):
        cycle_from_niveau("CP")


# ── derive_niveaux_from_file ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "source_file, expected_cycle, expected_niveaux",
    [
        (
            "programme_maths_cycle4_BO2026",
            Cycle.CYCLE4,
            ("cinquieme", "quatrieme", "troisieme"),
        ),
        (
            "programme_cycle4_BO2020",
            Cycle.CYCLE4,
            ("cinquieme", "quatrieme", "troisieme"),
        ),
        (
            "programme_anglais_college_BO2025",
            Cycle.CYCLE4,
            ("sixieme", "cinquieme", "quatrieme", "troisieme"),
        ),
        (
            "programme_cycle3_BO2020",
            Cycle.CYCLE3,
            ("sixieme",),
        ),
    ],
)
def test_derive_niveaux_from_file(source_file, expected_cycle, expected_niveaux):
    cycle, niveaux = derive_niveaux_from_file(source_file)
    assert cycle == expected_cycle
    assert tuple(n.value for n in niveaux) == expected_niveaux


def test_derive_niveaux_raises_on_unknown_filename():
    with pytest.raises(ValueError, match="Impossible de dériver"):
        derive_niveaux_from_file("fichier_sans_pattern_explicite")


# ── MATIERE_LABELS ───────────────────────────────────────────────────────────


def test_matiere_labels_complete():
    """Chaque Matiere a un label affichable."""
    for m in Matiere:
        assert m in MATIERE_LABELS
        assert isinstance(MATIERE_LABELS[m], str)
        assert len(MATIERE_LABELS[m]) > 0


def test_matiere_labels_accents_preserved():
    """Les labels conservent les accents FR (Mathématiques, Français, …)."""
    assert MATIERE_LABELS[Matiere.MATHEMATIQUES] == "Mathématiques"
    assert MATIERE_LABELS[Matiere.FRANCAIS] == "Français"
    assert MATIERE_LABELS[Matiere.HISTOIRE_GEO] == "Histoire-Géographie"
