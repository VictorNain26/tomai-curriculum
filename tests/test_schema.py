"""
Tests pour schema/document.py.

Couvre :
- Validation des champs niveau / matiere (ajoutés Phase 5)
- Helper cycle_from_niveau
- Validation token_estimate
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from schema import (  # noqa: E402
    ContentType,
    Cycle,
    Difficulty,
    Document,
    Matiere,
    NiveauCollege,
    NiveauLycee,
    cycle_from_niveau,
)

# ---------------------------------------------------------------------------
# cycle_from_niveau
# ---------------------------------------------------------------------------


def test_cycle_from_niveau_sixieme_is_cycle3():
    assert cycle_from_niveau(NiveauCollege.SIXIEME) is Cycle.CYCLE3


@pytest.mark.parametrize(
    "niveau",
    [NiveauCollege.CINQUIEME, NiveauCollege.QUATRIEME, NiveauCollege.TROISIEME],
)
def test_cycle_from_niveau_college_others_are_cycle4(niveau):
    assert cycle_from_niveau(niveau) is Cycle.CYCLE4


@pytest.mark.parametrize(
    "niveau", [NiveauLycee.SECONDE, NiveauLycee.PREMIERE, NiveauLycee.TERMINALE]
)
def test_cycle_from_niveau_lycee(niveau):
    assert cycle_from_niveau(niveau) is Cycle.LYCEE


def test_cycle_from_niveau_accepts_string():
    assert cycle_from_niveau("sixieme") is Cycle.CYCLE3
    assert cycle_from_niveau("terminale") is Cycle.LYCEE


def test_cycle_from_niveau_unknown_raises():
    with pytest.raises(ValueError, match="Niveau inconnu"):
        cycle_from_niveau("cp")


# ---------------------------------------------------------------------------
# Document.niveau / matiere (nouveaux champs optionnels)
# ---------------------------------------------------------------------------


def _base_doc_kwargs() -> dict:
    return {
        "title": "Théorème de Pythagore",
        "domaine": "Géométrie",
        "content_type": ContentType.THEOREME,
        "difficulty": Difficulty.STANDARD,
        "content": "x" * 300,
    }


def test_document_accepts_typed_niveau():
    doc = Document(**_base_doc_kwargs(), niveau=NiveauCollege.CINQUIEME)
    assert doc.niveau == NiveauCollege.CINQUIEME


def test_document_accepts_typed_matiere():
    doc = Document(**_base_doc_kwargs(), matiere=Matiere.MATHEMATIQUES)
    assert doc.matiere == Matiere.MATHEMATIQUES


def test_document_accepts_string_niveau_and_coerces():
    """Pydantic coerce les strings vers les enums NiveauCollege/Lycee."""
    doc = Document(**_base_doc_kwargs(), niveau="cinquieme")
    assert doc.niveau == NiveauCollege.CINQUIEME


def test_document_accepts_string_matiere_and_coerces():
    doc = Document(**_base_doc_kwargs(), matiere="mathematiques")
    assert doc.matiere == Matiere.MATHEMATIQUES


def test_document_rejects_unknown_niveau():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Document(**_base_doc_kwargs(), niveau="cp")  # primaire hors scope


def test_document_rejects_unknown_matiere():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Document(**_base_doc_kwargs(), matiere="latin_grec")


def test_document_niveau_and_matiere_default_to_none():
    """Rétrocompat : un JSONL antérieur à la migration reste valide."""
    doc = Document(**_base_doc_kwargs())
    assert doc.niveau is None
    assert doc.matiere is None


# ---------------------------------------------------------------------------
# Document.content — validation token_estimate
# ---------------------------------------------------------------------------


def test_document_rejects_content_too_short():
    from pydantic import ValidationError

    kwargs = _base_doc_kwargs()
    kwargs["content"] = "x" * 100  # ~25 tokens, sous le min 50
    with pytest.raises(ValidationError):
        Document(**kwargs)


def test_document_rejects_content_too_long():
    from pydantic import ValidationError

    kwargs = _base_doc_kwargs()
    kwargs["content"] = "x" * 3000  # ~750 tokens, au-dessus du max 600
    with pytest.raises(ValidationError):
        Document(**kwargs)


def test_document_accepts_content_at_target():
    kwargs = _base_doc_kwargs()
    kwargs["content"] = "x" * 1400  # ~350 tokens, cible
    doc = Document(**kwargs)
    assert len(doc.content) == 1400


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
