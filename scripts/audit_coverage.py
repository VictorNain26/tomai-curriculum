#!/usr/bin/env python3
"""
Audit de couverture du curriculum : compare les chapitres attendus (extraits
des PROGRAMME_*.md sous docs/programmes/, qui font office de référentiel cible
Eduscol) avec les titres présents dans les JSONL.

Sous-projet D du chantier RAG overhaul mai 2026.

Pourquoi pas un YAML séparé `data/reference/curriculum_targets.yaml` ?
Les PROGRAMME_*.md sont déjà la source de vérité curatée à la main, lisible,
versionnée avec git, et utilisable directement. Pas de duplication.

Usage :
    uv run python scripts/audit_coverage.py                       # rapport stdout
    uv run python scripts/audit_coverage.py --output rapport.md   # écrit aussi un MD
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

# Force UTF-8 output (cp1252 sur Windows par défaut)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def extract_titles_from_jsonl(jsonl_path: Path) -> list[str]:
    """Extract all titles from a JSONL file."""
    titles = []
    if jsonl_path.exists():
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    doc = json.loads(line)
                    titles.append(doc.get("title", "").lower())
    return titles


def extract_chapters_from_programme(md_path: Path) -> dict[str, list[str]]:
    """
    Extract chapters from a PROGRAMME_*.md file, grouped by MATIÈRE.

    Hiérarchie attendue :
        ## Mathématiques (4h30/semaine)    <- matière (groupé ici)
        ### Nombres et Calculs              <- sous-domaine (ignoré comme clé)
        - [ ] Multiples et diviseurs        <- chapitre

    Précédemment, chaque `### sous-domaine` écrasait current_subject, ce qui
    faisait que les chapitres étaient regroupés par sous-domaine et que les
    matières du SUBJECT_MAPPING (mathematiques, francais, etc.) ne matchaient
    jamais. Maintenant on garde la matière `##` comme clé stable jusqu'au
    prochain `##`.
    """
    chapters: dict[str, list[str]] = defaultdict(list)
    current_matiere: str | None = None

    if not md_path.exists():
        return chapters

    with open(md_path, encoding="utf-8") as f:
        content = f.read()

    for line in content.split("\n"):
        if line.startswith("## ") and not line.startswith("### "):
            subject = line.lstrip("#").strip()
            subject = re.sub(r"\s*\([^)]*\)", "", subject).strip()  # Remove (Xh/semaine)
            is_meta = subject.startswith("Thème") or subject.startswith("Récapitulatif")
            current_matiere = subject if subject and not is_meta else None
            continue

        # Les `###` sous-domaines sont ignorés comme groupes — leurs `- [ ]`
        # s'attachent à la matière `##` parente.

        # Detect checkbox items (chapters)
        if line.strip().startswith("- [ ]") and current_matiere:
            chapter = line.strip()[5:].strip()
            if chapter:
                chapters[current_matiere].append(chapter)

    return chapters


def normalize_for_comparison(text: str) -> str:
    """Normalize text for fuzzy comparison."""
    text = text.lower()
    text = re.sub(r"[^a-zàâäéèêëïîôùûüç0-9\s]", "", text)
    text = " ".join(text.split())
    return text


# Minimum significatif de mots dans un chapitre pour autoriser le fuzzy overlap.
# En dessous (titres courts type "Fractions décimales", 2 mots), on n'utilise
# que le containment strict pour éviter les faux positifs symétriques.
# Exemple bloqué : "Fractions" et "Fractions décimales" matchent en 60% overlap
# alors que ce sont deux chapitres distincts.
_FUZZY_OVERLAP_MIN_WORDS = 3
_FUZZY_OVERLAP_THRESHOLD = 0.6


def check_coverage(chapter: str, titles: list[str]) -> bool:
    """
    Check if a chapter is covered in the titles (fuzzy match).

    Stratégie : containment direct toujours autorisé. Overlap de mots autorisé
    UNIQUEMENT si le chapitre a >= 3 mots distincts (sinon trop de faux positifs
    sur les titres courts à vocabulaire commun).
    """
    chapter_norm = normalize_for_comparison(chapter)
    chapter_words = set(chapter_norm.split())

    for title in titles:
        title_norm = normalize_for_comparison(title)
        # Containment strict : toujours autorisé
        if chapter_norm in title_norm or title_norm in chapter_norm:
            return True

        # Overlap de mots : uniquement si chapitre suffisamment spécifique
        if len(chapter_words) < _FUZZY_OVERLAP_MIN_WORDS:
            continue
        title_words = set(title_norm.split())
        overlap = len(chapter_words & title_words)
        if overlap >= len(chapter_words) * _FUZZY_OVERLAP_THRESHOLD:
            return True

    return False


SUBJECT_MAPPING = {
    # Mapping from PROGRAMME subjects to JSONL filenames
    "mathématiques": ["mathematiques"],
    "français": ["francais"],
    "histoire": ["histoire_geo"],
    "histoire-géographie": ["histoire_geo"],
    "géographie": ["histoire_geo"],
    "emc": ["emc"],
    "enseignement moral et civique": ["emc"],
    "physique-chimie": ["physique_chimie"],
    "svt": ["svt"],
    "sciences de la vie et de la terre": ["svt"],
    "sciences et technologie": ["sciences_technologie"],
    "technologie": ["technologie"],
    "anglais": ["anglais"],
    "lva - anglais": ["anglais"],
    "lv1 - anglais": ["anglais"],
    "lvb": ["espagnol", "allemand", "italien"],
    "lv2": ["espagnol", "allemand", "italien"],
    "langues vivantes": ["anglais", "espagnol", "allemand", "italien"],
    "espagnol": ["espagnol"],
    "allemand": ["allemand"],
    "italien": ["italien"],
    "snt": ["snt"],
    "sciences numériques et technologie": ["snt"],
    "enseignement scientifique": ["enseignement_scientifique"],
    "philosophie": ["philosophie"],
    "ses": ["ses"],
    "sciences économiques et sociales": ["ses"],
    "hggsp": ["hggsp"],
    "histoire-géographie, géopolitique et sciences politiques": ["hggsp"],
    "hlp": ["hlp"],
    "humanités, littérature et philosophie": ["hlp"],
    "nsi": ["nsi"],
    "numérique et sciences informatiques": ["nsi"],
    "llce": ["llcer_anglais"],
    "langues, littératures et cultures étrangères": ["llcer_anglais"],
}


def find_jsonl_files(subject: str, data_paths: dict[str, Path]) -> list[Path]:
    """Find JSONL files matching a subject using mapping."""
    subject_lower = subject.lower()

    # Try direct mapping first
    for key, files in SUBJECT_MAPPING.items():
        if key in subject_lower or subject_lower in key:
            return [data_paths[f] for f in files if f in data_paths]

    # Fallback to fuzzy matching
    for key, path in data_paths.items():
        if key in subject_lower or subject_lower in key:
            return [path]

    return []


def audit_level(level_name: str, programme_path: Path, data_paths: dict[str, Path]) -> dict:
    """Audit a single level's coverage."""
    results = {
        "level": level_name,
        "subjects": {},
        "total_expected": 0,
        "total_covered": 0,
        "coverage_percent": 0,
    }

    expected = extract_chapters_from_programme(programme_path)

    # Combine all JSONL files into one pool of titles for the level
    all_titles = []
    for path in data_paths.values():
        all_titles.extend(extract_titles_from_jsonl(path))

    for subject, chapters in expected.items():
        # Find matching JSONL files
        jsonl_paths = find_jsonl_files(subject, data_paths)

        titles = []
        for path in jsonl_paths:
            titles.extend(extract_titles_from_jsonl(path))

        # Fallback : si aucun JSONL ne matche, on N'utilise PAS le pool global.
        # Précédemment on basculait sur all_titles, ce qui produisait des chiffres
        # de couverture trompeurs (un chapitre de "SES" pouvait matcher contre un
        # doc de "mathematiques" du même niveau). Maintenant on marque
        # explicitement N/A pour signaler la matière non-mappée.
        unmapped = not jsonl_paths
        if unmapped:
            print(
                f"  [WARN] Subject {subject!r} ({level_name}) non mappé dans "
                f"SUBJECT_MAPPING — couverture marquée N/A",
                flush=True,
            )

        covered = []
        missing = list(chapters) if unmapped else []

        if not unmapped:
            for chapter in chapters:
                if check_coverage(chapter, titles):
                    covered.append(chapter)
                else:
                    missing.append(chapter)

        results["subjects"][subject] = {
            "expected": len(chapters),
            "covered": len(covered),
            "missing": missing,
            "coverage_percent": (len(covered) / len(chapters) * 100) if chapters else 0,
            "jsonl_docs": len(titles),
            "matched_files": [p.name for p in jsonl_paths],
            "unmapped": unmapped,
        }

        # Les matières non-mappées ne sont PAS comptées dans le total global :
        # elles biaiseraient la moyenne vers 0% alors qu'on n'a juste pas vérifié.
        if not unmapped:
            results["total_expected"] += len(chapters)
            results["total_covered"] += len(covered)

    if results["total_expected"] > 0:
        results["coverage_percent"] = results["total_covered"] / results["total_expected"] * 100

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Si fourni, écrit aussi le rapport au format Markdown vers ce chemin",
    )
    args = parser.parse_args()

    base_path = Path(__file__).parent.parent
    data_path = base_path / "data" / "processed"
    programmes_dir = base_path / "docs" / "programmes"

    levels = {
        "6ème": {
            "programme": programmes_dir / "PROGRAMME_6EME.md",
            "data_dir": data_path / "college" / "sixieme",
        },
        "5ème": {
            "programme": programmes_dir / "PROGRAMME_5EME.md",
            "data_dir": data_path / "college" / "cinquieme",
        },
        "4ème": {
            "programme": programmes_dir / "PROGRAMME_4EME.md",
            "data_dir": data_path / "college" / "quatrieme",
        },
        "3ème": {
            "programme": programmes_dir / "PROGRAMME_3EME.md",
            "data_dir": data_path / "college" / "troisieme",
        },
        "Seconde": {
            "programme": programmes_dir / "PROGRAMME_SECONDE.md",
            "data_dir": data_path / "lycee" / "seconde",
        },
        "Première": {
            "programme": programmes_dir / "PROGRAMME_PREMIERE.md",
            "data_dir": data_path / "lycee" / "premiere",
        },
        "Terminale": {
            "programme": programmes_dir / "PROGRAMME_TERMINALE.md",
            "data_dir": data_path / "lycee" / "terminale",
        },
    }

    all_results = []
    for level_name, config in levels.items():
        data_dir = config["data_dir"]
        data_paths: dict[str, Path] = {}
        if data_dir.exists():
            for jsonl in data_dir.glob("*.jsonl"):
                data_paths[jsonl.stem.lower()] = jsonl

        results = audit_level(level_name, config["programme"], data_paths)
        all_results.append(results)

    _emit_report(all_results, output=sys.stdout)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        buf = StringIO()
        _emit_report(all_results, output=buf, markdown=True)
        args.output.write_text(buf.getvalue(), encoding="utf-8")
        print(f"\nRapport Markdown écrit : {args.output}")


def _emit_report(all_results: list[dict], output, markdown: bool = False) -> None:
    """Écrit le rapport (texte ou markdown) vers output (stdout ou StringIO)."""

    def line(s: str = "") -> None:
        print(s, file=output)

    if markdown:
        line("# Rapport d'audit — couverture du curriculum")
        line()
        line(f"_Généré le {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}_")
        line()
        line(
            "Compare les chapitres attendus (extraits des PROGRAMME_*.md sous "
            "`docs/programmes/`) avec les titres présents dans les JSONL "
            "`data/processed/`. Match fuzzy (chevauchement de mots), peut produire "
            "des faux positifs/négatifs sur les chapitres au titre court."
        )
        line()
    else:
        line("=" * 80)
        line("RAPPORT D'AUDIT - COUVERTURE DU CURRICULUM")
        line("=" * 80)
        line()

    total_expected = 0
    total_covered = 0

    for result in all_results:
        if markdown:
            line(f"## Niveau : {result['level']}")
            line()
            line(
                f"**Couverture globale : {result['coverage_percent']:.1f}%** "
                f"({result['total_covered']}/{result['total_expected']} chapitres)"
            )
            line()
            line("| Statut | Matière | Couverture | Docs JSONL |")
            line("|--------|---------|------------|------------|")
        else:
            line(f"\n{'=' * 60}")
            line(f"NIVEAU: {result['level']}")
            line(f"{'=' * 60}")
            line(
                f"Couverture globale: {result['coverage_percent']:.1f}% "
                f"({result['total_covered']}/{result['total_expected']} chapitres)"
            )
            line()

        subjects_sorted = sorted(result["subjects"].items(), key=lambda x: x[1]["coverage_percent"])

        for subject, data in subjects_sorted:
            pct = data["coverage_percent"]
            if markdown:
                status = "✅" if pct >= 80 else "⚠️" if pct >= 50 else "❌"
                line(
                    f"| {status} | {subject} | {pct:.0f}% ({data['covered']}/{data['expected']}) "
                    f"| {data['jsonl_docs']} |"
                )
            else:
                status = "[OK]" if pct >= 80 else "[!!]" if pct >= 50 else "[XX]"
                line(
                    f"  {status} {subject}: {pct:.0f}% "
                    f"({data['covered']}/{data['expected']}) - {data['jsonl_docs']} docs"
                )
                if data["missing"] and pct < 80:
                    line(f"      Manquants ({len(data['missing'])}):")
                    for chapter in data["missing"][:5]:
                        line(f"        - {chapter}")
                    if len(data["missing"]) > 5:
                        line(f"        ... et {len(data['missing']) - 5} autres")

        if markdown:
            line()
            # Détail des manques par matière, après la table
            for subject, data in subjects_sorted:
                if data["missing"] and data["coverage_percent"] < 80:
                    line(f"### Manques en {subject} ({len(data['missing'])})")
                    line()
                    for chapter in data["missing"]:
                        line(f"- [ ] {chapter}")
                    line()

        total_expected += result["total_expected"]
        total_covered += result["total_covered"]

    global_pct = (total_covered / total_expected * 100) if total_expected > 0 else 0
    if markdown:
        line("---")
        line()
        line("## Résumé global")
        line()
        line(
            f"**Couverture totale : {global_pct:.1f}%** "
            f"({total_covered}/{total_expected} chapitres)"
        )
        line()
        line("### Lacunes critiques (< 50% couverture, > 3 chapitres attendus)")
        line()
        line("| Niveau | Matière | Couverture |")
        line("|--------|---------|------------|")
    else:
        line()
        line("=" * 80)
        line("RÉSUMÉ GLOBAL")
        line("=" * 80)
        line(f"Couverture totale: {global_pct:.1f}% ({total_covered}/{total_expected} chapitres)")
        line()
        line("LACUNES CRITIQUES (< 50% couverture):")

    for result in all_results:
        for subject, data in result["subjects"].items():
            if data["coverage_percent"] < 50 and data["expected"] > 3:
                if markdown:
                    line(f"| {result['level']} | {subject} | {data['coverage_percent']:.0f}% |")
                else:
                    line(f"  - {result['level']} / {subject}: {data['coverage_percent']:.0f}%")


if __name__ == "__main__":
    main()
