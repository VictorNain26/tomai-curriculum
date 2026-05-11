"""
Tests pour scripts/audit_coverage.py.

Couvre :
- normalize_for_comparison (pure)
- check_coverage (fuzzy match, anti-faux-positifs)
- extract_chapters_from_programme (parse markdown)
- extract_titles_from_jsonl (lecture JSONL)
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.audit_coverage import (  # noqa: E402
    check_coverage,
    extract_chapters_from_programme,
    extract_titles_from_jsonl,
    normalize_for_comparison,
)

# ---------------------------------------------------------------------------
# normalize_for_comparison
# ---------------------------------------------------------------------------


def test_normalize_lowercases():
    assert normalize_for_comparison("ABCdef") == "abcdef"


def test_normalize_keeps_french_accents():
    assert normalize_for_comparison("élève français") == "élève français"


def test_normalize_strips_punctuation():
    assert normalize_for_comparison("Bonjour, monde !") == "bonjour monde"


def test_normalize_collapses_whitespace():
    assert normalize_for_comparison("a   b\tc\nd") == "a b c d"


def test_normalize_preserves_digits():
    assert normalize_for_comparison("Niveau 5ème (cycle 4)") == "niveau 5ème cycle 4"


# ---------------------------------------------------------------------------
# check_coverage — containment strict
# ---------------------------------------------------------------------------


def test_check_coverage_strict_containment_chapter_in_title():
    titles = ["théorème de pythagore - énoncé complet"]
    assert check_coverage("Théorème de Pythagore", titles) is True


def test_check_coverage_strict_containment_title_in_chapter():
    # Le chapitre attendu contient le titre normalisé
    titles = ["pythagore"]
    assert check_coverage("Théorème de Pythagore - énoncé", titles) is True


def test_check_coverage_no_match_returns_false():
    titles = ["nombres décimaux", "fractions équivalentes"]
    assert check_coverage("Trigonométrie sphérique", titles) is False


def test_check_coverage_empty_titles_returns_false():
    assert check_coverage("Théorème de Pythagore", []) is False


# ---------------------------------------------------------------------------
# check_coverage — fuzzy overlap (anti-faux-positifs)
# ---------------------------------------------------------------------------


def test_check_coverage_fuzzy_requires_min_words():
    # Chapitre 2 mots distincts, overlap parfait dans un titre plus long.
    # Sans le garde `< 3 mots`, l'overlap (100%) déclencherait un faux positif.
    # Avec le garde, on REFUSE le fuzzy → False. Pas de containment substring
    # car l'ordre des mots diffère et le chapitre n'est pas une sous-chaîne.
    titles = ["calculs équivalents en fractions usuelles"]
    assert check_coverage("Fractions calculs", titles) is False


def test_check_coverage_fuzzy_match_with_three_words():
    # Chapitre de 3 mots, titre couvre 2 mots = 67% overlap >= 60% seuil
    titles = ["addition nombres décimaux positifs"]
    assert check_coverage("Addition nombres entiers", titles) is True


def test_check_coverage_fuzzy_no_match_below_threshold():
    # Chapitre 3 mots, titre couvre 1 mot = 33% < 60% seuil
    titles = ["géométrie dans le plan euclidien"]
    assert check_coverage("Probabilités événements indépendants", titles) is False


# ---------------------------------------------------------------------------
# extract_chapters_from_programme — parsing markdown
# ---------------------------------------------------------------------------


def test_extract_chapters_returns_empty_for_missing_file(tmp_path: Path):
    nonexistent = tmp_path / "MISSING.md"
    result = extract_chapters_from_programme(nonexistent)
    assert result == {} or len(result) == 0


def test_extract_chapters_groups_by_matiere(tmp_path: Path):
    md = tmp_path / "PROGRAMME.md"
    md.write_text(
        "# Programme\n"
        "\n"
        "## Mathématiques (4h30/semaine)\n"
        "\n"
        "### Nombres et Calculs\n"
        "- [ ] Fractions\n"
        "- [ ] Nombres relatifs\n"
        "\n"
        "## Français (4h/semaine)\n"
        "\n"
        "### Grammaire\n"
        "- [ ] Conjugaison\n",
        encoding="utf-8",
    )

    chapters = extract_chapters_from_programme(md)

    assert "Mathématiques" in chapters
    assert "Français" in chapters
    assert "Fractions" in chapters["Mathématiques"]
    assert "Nombres relatifs" in chapters["Mathématiques"]
    assert "Conjugaison" in chapters["Français"]


def test_extract_chapters_subdomain_attaches_to_matiere(tmp_path: Path):
    """Un `### sous-domaine` ne crée PAS une clé séparée — attach à la matière parente."""
    md = tmp_path / "PROGRAMME.md"
    md.write_text(
        "## Mathématiques\n### Géométrie\n- [ ] Triangle rectangle\n### Algèbre\n- [ ] Équations\n",
        encoding="utf-8",
    )

    chapters = extract_chapters_from_programme(md)

    assert "Mathématiques" in chapters
    assert "Géométrie" not in chapters
    assert "Algèbre" not in chapters
    assert "Triangle rectangle" in chapters["Mathématiques"]
    assert "Équations" in chapters["Mathématiques"]


def test_extract_chapters_ignores_meta_sections(tmp_path: Path):
    """`## Thème transversal` et `## Récapitulatif` ne sont pas des matières."""
    md = tmp_path / "PROGRAMME.md"
    md.write_text(
        "## Mathématiques\n"
        "- [ ] Chapitre maths\n"
        "## Thème transversal\n"
        "- [ ] Chapitre théma\n"
        "## Récapitulatif horaire\n"
        "- [ ] Item ignoré\n",
        encoding="utf-8",
    )

    chapters = extract_chapters_from_programme(md)

    assert "Mathématiques" in chapters
    assert "Thème transversal" not in chapters
    assert "Récapitulatif horaire" not in chapters
    assert "Chapitre théma" not in chapters.get("Mathématiques", [])


def test_extract_chapters_strips_hourly_suffix(tmp_path: Path):
    """`## Mathématiques (4h30/semaine)` → clé `Mathématiques`."""
    md = tmp_path / "PROGRAMME.md"
    md.write_text("## Mathématiques (4h30/semaine)\n- [ ] Item\n", encoding="utf-8")

    chapters = extract_chapters_from_programme(md)

    assert "Mathématiques" in chapters
    assert "Mathématiques (4h30/semaine)" not in chapters


# ---------------------------------------------------------------------------
# extract_titles_from_jsonl
# ---------------------------------------------------------------------------


def test_extract_titles_returns_empty_for_missing_file(tmp_path: Path):
    result = extract_titles_from_jsonl(tmp_path / "missing.jsonl")
    assert result == []


def test_extract_titles_lowercases(tmp_path: Path):
    jsonl = tmp_path / "test.jsonl"
    jsonl.write_text(
        json.dumps({"title": "Théorème de Pythagore"})
        + "\n"
        + json.dumps({"title": "FRACTIONS DÉCIMALES"})
        + "\n",
        encoding="utf-8",
    )

    titles = extract_titles_from_jsonl(jsonl)

    assert titles == ["théorème de pythagore", "fractions décimales"]


def test_extract_titles_skips_blank_lines(tmp_path: Path):
    jsonl = tmp_path / "test.jsonl"
    jsonl.write_text(
        json.dumps({"title": "Premier"}) + "\n\n   \n" + json.dumps({"title": "Second"}) + "\n",
        encoding="utf-8",
    )

    titles = extract_titles_from_jsonl(jsonl)

    assert titles == ["premier", "second"]


def test_extract_titles_handles_missing_title_key(tmp_path: Path):
    jsonl = tmp_path / "test.jsonl"
    jsonl.write_text(json.dumps({"no_title": "value"}) + "\n", encoding="utf-8")

    titles = extract_titles_from_jsonl(jsonl)

    # Pas de title → chaîne vide (lowercased)
    assert titles == [""]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
