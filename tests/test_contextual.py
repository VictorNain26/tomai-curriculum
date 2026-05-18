"""Tests du préfixe contextuel (build_contextual_text)."""

from __future__ import annotations

from schema import Chunk, Matiere, NiveauCollege, build_contextual_text


def _chunk(**overrides) -> Chunk:
    base = dict(
        text="Les triangles rectangles vérifient le théorème de Pythagore : a²+b²=c².",
        source_file="programme_maths_cycle4_BO2026",
        matiere=Matiere.MATHEMATIQUES,
        niveau=NiveauCollege.QUATRIEME,
        section="Géométrie — Pythagore",
        chunk_index=0,
    )
    base.update(overrides)
    return Chunk(**base)


def test_contextual_prefix_includes_matiere_label():
    """Le préfixe contient le label affichable de la matière (pas l'enum value)."""
    out = build_contextual_text(_chunk())
    assert "Mathématiques" in out
    assert "mathematiques" not in out  # pas la version enum


def test_contextual_prefix_includes_section():
    out = build_contextual_text(_chunk(section="Nombres relatifs"))
    assert "Nombres relatifs" in out


def test_contextual_prefix_does_not_include_niveau():
    """
    Le niveau est volontairement absent du préfixe : permet 1 seul embed par
    texte puis duplication payload pour 5e/4e/3e (économie 3× sur l'API).
    Voir ADR-0007 §contextual prefix.
    """
    out = build_contextual_text(_chunk(niveau=NiveauCollege.QUATRIEME))
    assert "quatrieme" not in out
    assert "4e" not in out
    assert "4ème" not in out


def test_contextual_prefix_text_position():
    """Le préfixe est AVANT le texte brut (et non après)."""
    out = build_contextual_text(_chunk())
    prefix_pos = out.find("Cet extrait")
    text_pos = out.find("triangles rectangles")
    assert prefix_pos < text_pos
    assert prefix_pos == 0


def test_contextual_prefix_separator():
    """Préfixe et chunk séparés par une ligne vide pour faciliter l'embed."""
    out = build_contextual_text(_chunk())
    assert "\n\n" in out


def test_contextual_prefix_preserves_chunk_text():
    """Le texte brut est entièrement présent à la fin de l'output."""
    chunk = _chunk()
    out = build_contextual_text(chunk)
    assert out.endswith(chunk.text)
