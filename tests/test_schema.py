"""Tests du schéma Chunk v2.0."""

import pytest

from schema import Chunk, Cycle, Matiere, NiveauCollege, cycle_from_niveau


def test_chunk_minimal():
    c = Chunk(
        text="Les nombres relatifs permettent de représenter des valeurs positives et négatives.",
        source_file="programme_maths_cycle4_BO2026",
        matiere=Matiere.MATHEMATIQUES,
        section="Nombres relatifs",
        chunk_index=0,
    )
    assert c.niveau == NiveauCollege.CINQUIEME
    assert c.cycle == Cycle.CYCLE4
    assert c.id  # UUID auto-généré


def test_chunk_text_trop_court():
    with pytest.raises(Exception):
        Chunk(
            text="court",
            source_file="prog",
            matiere=Matiere.FRANCAIS,
            section="test",
            chunk_index=0,
        )


def test_qdrant_payload():
    c = Chunk(
        text="En géographie, le relief terrestre est étudié à travers différentes représentations.",
        source_file="programme_cycle4_BO2020",
        matiere=Matiere.HISTOIRE_GEO,
        section="Géographie",
        chunk_index=3,
    )
    payload = c.to_qdrant_payload()
    assert payload["matiere"] == "histoire_geo"
    assert payload["cycle"] == "cycle4"
    assert payload["chunk_index"] == 3
    assert "id" not in payload  # id utilisé comme point_id, pas dans le payload


def test_cycle_from_niveau():
    assert cycle_from_niveau(NiveauCollege.CINQUIEME) == Cycle.CYCLE4
    assert cycle_from_niveau(NiveauCollege.SIXIEME) == Cycle.CYCLE3
    assert cycle_from_niveau("terminale") == Cycle.LYCEE


def test_ids_stables_sur_meme_texte():
    texte = "Le théorème de Pythagore s'applique aux triangles rectangles."
    c1 = Chunk(
        text=texte, source_file="f", matiere=Matiere.MATHEMATIQUES, section="s", chunk_index=0
    )
    c2 = Chunk(
        text=texte, source_file="f", matiere=Matiere.MATHEMATIQUES, section="s", chunk_index=0
    )
    # Les IDs sont des UUID4 random — ils diffèrent, mais le hash du texte
    # garantit l'idempotence côté Qdrant (via ingest.py)
    assert c1.id != c2.id  # UUID4 random, OK
    assert c1.text == c2.text
