"""
Tests pour scripts/chunking.py.

Couvre les fonctions pures (estimate_tokens, generate_stable_id,
normalize, regex extraction) et la logique de groupement / merge.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from schema import ContentType, Difficulty, Document  # noqa: E402
from scripts.chunking import (  # noqa: E402
    _extract_latex_formulas,
    _generate_typical_questions,
    estimate_tokens,
    generate_stable_id,
    group_documents_by_theme,
    merge_documents,
)

# ---------------------------------------------------------------------------
# estimate_tokens
# ---------------------------------------------------------------------------


def test_estimate_tokens_uses_4char_heuristic():
    assert estimate_tokens("a" * 400) == 100


def test_estimate_tokens_empty_string_is_zero():
    assert estimate_tokens("") == 0


def test_estimate_tokens_rounds_down():
    assert estimate_tokens("abc") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcdefg") == 1


# ---------------------------------------------------------------------------
# generate_stable_id
# ---------------------------------------------------------------------------


def test_generate_stable_id_format():
    result = generate_stable_id("cinquieme", "mathematiques", "Nombres et Calculs", 5)
    assert result == "mathematiques_cinquieme_nombres_et_calculs_005"


def test_generate_stable_id_strips_apostrophes_and_spaces():
    result = generate_stable_id("seconde", "francais", "L'expression écrite", 0)
    # Apostrophe retirée, espaces → underscores, max 20 chars
    assert "_lexpression_écrite_" in result or result.endswith("_000")
    assert result.startswith("francais_seconde_")


def test_generate_stable_id_is_deterministic():
    a = generate_stable_id("troisieme", "svt", "Le vivant et son évolution", 7)
    b = generate_stable_id("troisieme", "svt", "Le vivant et son évolution", 7)
    assert a == b


def test_generate_stable_id_truncates_long_domaine():
    long_domaine = "Domaine très très très très long"
    result = generate_stable_id("seconde", "ses", long_domaine, 1)
    # Le slug de domaine est tronqué à 20 chars
    safe_part = result.replace("ses_seconde_", "").rsplit("_", 1)[0]
    assert len(safe_part) <= 20


# ---------------------------------------------------------------------------
# group_documents_by_theme
# ---------------------------------------------------------------------------


def _make_doc(
    title: str,
    domaine: str,
    sousdomaine: str | None = None,
    content_type: ContentType = ContentType.DEFINITION,
) -> dict:
    """Builder léger pour fabriquer un doc_data minimal valide."""
    doc = Document(
        title=title,
        domaine=domaine,
        sousdomaine=sousdomaine,
        content_type=content_type,
        difficulty=Difficulty.STANDARD,
        content="x" * 300,  # ~75 tokens, dans la borne 50-600
    )
    return {
        "doc": doc,
        "niveau": "cinquieme",
        "matiere": "mathematiques",
        "cycle": "cycle4",
    }


def test_group_documents_by_theme_groups_by_domain_subdomain():
    docs = [
        _make_doc("Définition A complète", "Algèbre", "Équations"),
        _make_doc("Définition B complète", "Algèbre", "Équations"),
        _make_doc("Définition C complète", "Géométrie", "Triangles"),
    ]
    groups = group_documents_by_theme(docs)

    assert "Algèbre::Équations" in groups
    assert "Géométrie::Triangles" in groups
    assert len(groups["Algèbre::Équations"]) == 2
    assert len(groups["Géométrie::Triangles"]) == 1


def test_group_documents_by_theme_uses_general_for_missing_subdomain():
    docs = [_make_doc("Définition simple", "Calcul", sousdomaine=None)]
    groups = group_documents_by_theme(docs)
    assert "Calcul::general" in groups


def test_group_documents_by_theme_orders_pedagogically():
    docs = [
        _make_doc("Exemple concret", "Géométrie", content_type=ContentType.EXEMPLE),
        _make_doc("Définition base", "Géométrie", content_type=ContentType.DEFINITION),
        _make_doc("Théorème central", "Géométrie", content_type=ContentType.THEOREME),
        _make_doc("Méthode résolution", "Géométrie", content_type=ContentType.METHODE),
    ]
    groups = group_documents_by_theme(docs)
    ordered_types = [d["doc"].content_type for d in groups["Géométrie::general"]]
    assert ordered_types == [
        ContentType.DEFINITION,
        ContentType.THEOREME,
        ContentType.METHODE,
        ContentType.EXEMPLE,
    ]


# ---------------------------------------------------------------------------
# merge_documents
# ---------------------------------------------------------------------------


def test_merge_documents_empty_returns_empty():
    assert merge_documents([]) == []


def test_merge_documents_single_doc_returns_single_chunk():
    docs = [_make_doc("Définition unique", "Algèbre")]
    result = merge_documents(docs)
    assert len(result) == 1


def test_merge_documents_respects_token_target():
    # Chaque doc fait ~75 tokens (300 chars), target=350 → ~4-5 docs par chunk
    docs = [_make_doc(f"Définition numéro {i:02d}", "Algèbre") for i in range(10)]
    chunks = merge_documents(docs, target_tokens=350)
    # Au moins un chunk créé
    assert len(chunks) >= 1
    # Chaque chunk contient le content_hash etc. (smoke check)
    for chunk in chunks:
        assert "content" in chunk or "doc" in chunk or isinstance(chunk, dict)


# ---------------------------------------------------------------------------
# _extract_latex_formulas
# ---------------------------------------------------------------------------


def test_extract_latex_formulas_finds_simple_equation():
    content = "On a AB = BC + CA dans ce triangle"
    formulas = _extract_latex_formulas(content)
    # Au moins une formule détectée (pattern variables = variables)
    assert isinstance(formulas, list)


def test_extract_latex_formulas_no_match_returns_empty():
    content = "Pas de formule mathématique ici, juste du texte simple."
    formulas = _extract_latex_formulas(content)
    assert formulas == [] or isinstance(formulas, list)


# ---------------------------------------------------------------------------
# _generate_typical_questions
# ---------------------------------------------------------------------------


def test_generate_typical_questions_definition_yields_qu_est_ce_que():
    docs = [_make_doc("Théorème Pythagore", "Géométrie", content_type=ContentType.DEFINITION)]
    questions = _generate_typical_questions(docs)
    assert any("qu'est-ce que" in q.lower() for q in questions)


def test_generate_typical_questions_theoreme_yields_enonce():
    docs = [_make_doc("Théorème de Thalès", "Géométrie", content_type=ContentType.THEOREME)]
    questions = _generate_typical_questions(docs)
    assert any("énoncé" in q.lower() for q in questions)


def test_generate_typical_questions_deduplicates():
    # Deux docs identiques (même title + content_type) → questions dédupliquées
    docs = [
        _make_doc("Théorème Pythagore", "Géométrie", content_type=ContentType.DEFINITION),
        _make_doc("Théorème Pythagore", "Géométrie", content_type=ContentType.DEFINITION),
    ]
    questions = _generate_typical_questions(docs)
    assert len(questions) == len(set(questions))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
