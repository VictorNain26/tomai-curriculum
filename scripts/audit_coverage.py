#!/usr/bin/env python3
"""
Audit script to compare dataset coverage vs reference programs.
Generates a detailed report of coverage and missing chapters.
"""

import json
import re
import sys
from pathlib import Path
from collections import defaultdict

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')


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
    """Extract chapters from a PROGRAMME_*.md file, grouped by subject."""
    chapters = defaultdict(list)
    current_subject = None

    if not md_path.exists():
        return chapters

    with open(md_path, encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")
    for line in lines:
        # Detect main subject headers (## or ###)
        if line.startswith("## ") or line.startswith("### "):
            subject = line.lstrip("#").strip()
            # Clean up subject name
            subject = re.sub(r"\s*\([^)]*\)", "", subject)  # Remove (Xh/semaine)
            subject = subject.strip()
            if subject and not subject.startswith("Thème") and not subject.startswith("Récapitulatif"):
                current_subject = subject

        # Detect checkbox items (chapters)
        if line.strip().startswith("- [ ]") and current_subject:
            chapter = line.strip()[5:].strip()
            if chapter:
                chapters[current_subject].append(chapter)

    return chapters


def normalize_for_comparison(text: str) -> str:
    """Normalize text for fuzzy comparison."""
    text = text.lower()
    text = re.sub(r"[^a-zàâäéèêëïîôùûüç0-9\s]", "", text)
    text = " ".join(text.split())
    return text


def check_coverage(chapter: str, titles: list[str]) -> bool:
    """Check if a chapter is covered in the titles (fuzzy match)."""
    chapter_norm = normalize_for_comparison(chapter)
    chapter_words = set(chapter_norm.split())

    # Direct match
    for title in titles:
        title_norm = normalize_for_comparison(title)
        if chapter_norm in title_norm or title_norm in chapter_norm:
            return True

        # Word overlap match (at least 60% of words)
        title_words = set(title_norm.split())
        overlap = len(chapter_words & title_words)
        if chapter_words and overlap >= len(chapter_words) * 0.6:
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

        # If no specific match, use all titles as fallback for checking
        check_titles = titles if titles else all_titles

        covered = []
        missing = []

        for chapter in chapters:
            if check_coverage(chapter, check_titles):
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
        }

        results["total_expected"] += len(chapters)
        results["total_covered"] += len(covered)

    if results["total_expected"] > 0:
        results["coverage_percent"] = results["total_covered"] / results["total_expected"] * 100

    return results


def main():
    base_path = Path(__file__).parent.parent
    data_path = base_path / "data" / "processed"

    # Define levels and their paths
    levels = {
        "6ème": {
            "programme": base_path / "PROGRAMME_6EME.md",
            "data_dir": data_path / "college" / "sixieme",
        },
        "5ème": {
            "programme": base_path / "PROGRAMME_5EME.md",
            "data_dir": data_path / "college" / "cinquieme",
        },
        "4ème": {
            "programme": base_path / "PROGRAMME_4EME.md",
            "data_dir": data_path / "college" / "quatrieme",
        },
        "3ème": {
            "programme": base_path / "PROGRAMME_3EME.md",
            "data_dir": data_path / "college" / "troisieme",
        },
        "Seconde": {
            "programme": base_path / "PROGRAMME_SECONDE.md",
            "data_dir": data_path / "lycee" / "seconde",
        },
        "Première": {
            "programme": base_path / "PROGRAMME_PREMIERE.md",
            "data_dir": data_path / "lycee" / "premiere",
        },
        "Terminale": {
            "programme": base_path / "PROGRAMME_TERMINALE.md",
            "data_dir": data_path / "lycee" / "terminale",
        },
    }

    all_results = []

    for level_name, config in levels.items():
        # Map subject to JSONL files
        data_dir = config["data_dir"]
        data_paths = {}
        if data_dir.exists():
            for jsonl in data_dir.glob("*.jsonl"):
                key = jsonl.stem.lower()
                data_paths[key] = jsonl

        results = audit_level(level_name, config["programme"], data_paths)
        all_results.append(results)

    # Print summary
    print("=" * 80)
    print("RAPPORT D'AUDIT - COUVERTURE DU CURRICULUM")
    print("=" * 80)
    print()

    total_expected = 0
    total_covered = 0

    for result in all_results:
        print(f"\n{'='*60}")
        print(f"NIVEAU: {result['level']}")
        print(f"{'='*60}")
        print(f"Couverture globale: {result['coverage_percent']:.1f}% ({result['total_covered']}/{result['total_expected']} chapitres)")
        print()

        # Sort subjects by coverage (lowest first)
        subjects_sorted = sorted(
            result["subjects"].items(),
            key=lambda x: x[1]["coverage_percent"]
        )

        for subject, data in subjects_sorted:
            status = "[OK]" if data["coverage_percent"] >= 80 else "[!!]" if data["coverage_percent"] >= 50 else "[XX]"
            print(f"  {status} {subject}: {data['coverage_percent']:.0f}% ({data['covered']}/{data['expected']}) - {data['jsonl_docs']} docs")

            if data["missing"] and data["coverage_percent"] < 80:
                print(f"      Manquants ({len(data['missing'])}):")
                for chapter in data["missing"][:5]:
                    print(f"        - {chapter}")
                if len(data["missing"]) > 5:
                    print(f"        ... et {len(data['missing']) - 5} autres")

        total_expected += result["total_expected"]
        total_covered += result["total_covered"]

    print()
    print("=" * 80)
    print("RÉSUMÉ GLOBAL")
    print("=" * 80)
    global_coverage = (total_covered / total_expected * 100) if total_expected > 0 else 0
    print(f"Couverture totale: {global_coverage:.1f}% ({total_covered}/{total_expected} chapitres)")
    print()

    # Critical gaps
    print("LACUNES CRITIQUES (< 50% couverture):")
    for result in all_results:
        for subject, data in result["subjects"].items():
            if data["coverage_percent"] < 50 and data["expected"] > 3:
                print(f"  - {result['level']} / {subject}: {data['coverage_percent']:.0f}%")


if __name__ == "__main__":
    main()
