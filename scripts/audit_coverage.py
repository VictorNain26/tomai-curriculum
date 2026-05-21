#!/usr/bin/env python3
"""
Audit de couverture du RAG : vérifie que les programmes officiels
(data/raw/*.txt, téléchargés depuis data.gouv.fr / cache.media.education.gouv.fr)
sont bien représentés dans la collection Qdrant.

Source de vérité : data/raw/*.txt (annexes officielles BO)
Cible mesurée   : chunks indexés dans Qdrant

Deux métriques par matière :
  1. Couverture texte : (chars indexés / chars source) — détecte les pertes silencieuses
  2. Couverture sections : % des titres de sections du BO présents dans au moins un chunk

Usage :
    uv run python scripts/audit_coverage.py
    uv run python scripts/audit_coverage.py --output docs/audits/rapport.md
    uv run python scripts/audit_coverage.py --matiere=mathematiques
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

BASE = Path(__file__).parent.parent
RAW = BASE / "data" / "raw"


# ── Extraction des titres de sections depuis les .txt officiels ───────────────


_MARKDOWN_TITLE_RE = re.compile(r"^#{2,4}\s+(.+?)\s*$")
"""Markdown H2-H4 : `## Titre`, `### Sous-titre`, etc."""

_MARKDOWN_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__|\*(.+?)\*|_(.+?)_")
"""Wrapping gras/italique markdown autour d'un titre — à stripper."""

_PDF_BULLET_CHARS = "•▪●"
"""Caractères puces graphiques pdftotext (Private Use Area + bullets unicode)."""


def _strip_markdown_wrapping(s: str) -> str:
    """Retire `## `, `**...**`, `_..._`, puces, espaces — pour normaliser un titre."""
    # Retire le préfixe heading `## ` ou `### `
    m = _MARKDOWN_TITLE_RE.match(s)
    if m:
        s = m.group(1)
    # Retire les puces PDF et unicode
    s = "".join(c for c in s if c not in _PDF_BULLET_CHARS)
    # Retire le gras/italique markdown (peut être imbriqué)
    while True:
        new = _MARKDOWN_BOLD_RE.sub(lambda m: next((g for g in m.groups() if g), ""), s)
        if new == s:
            break
        s = new
    return s.strip()


def _looks_like_real_title(line: str) -> bool:
    """
    Filtre anti-faux-positifs : élimine les lignes isolées qui ne sont PAS des titres.

    Faux positifs identifiés dans les programmes Eduscol :
    - Bullets de liste (`- foo`, `* foo`, `• foo`)
    - Lignes de tableaux markdown (`|6e|A1|A2|`)
    - Lignes très courtes ou se terminant par ponctuation de phrase (`:`, `;`, `.` final)
    - Lignes contenant trop de séparateurs `|`
    """
    s = line.strip()
    if not s:
        return False
    # Bullet
    if s[:2] in ("- ", "* ", "• ", "→ ", "→ "):
        return False
    # Ligne de tableau markdown
    if s.startswith("|") or s.count("|") >= 3:
        return False
    # Finit par ponctuation de phrase = c'est une phrase, pas un titre
    if s.rstrip().endswith((".", ":", ";", ",")) and not s.startswith("#"):
        return False
    return True


@dataclass(frozen=True, slots=True)
class ExtractedTitle:
    """Titre extrait du source + provenance (markdown H2 fiable vs heuristique pdftotext)."""

    text: str
    source: str  # "markdown" | "heuristic"


def extract_section_titles(text: str) -> list[ExtractedTitle]:
    """
    Extrait les titres de sections d'un texte issu de pdftotext OU pymupdf4llm.

    Deux sources :
    1. Markdown H2-H4 (`## **Titre**`) → source="markdown", signal fiable
    2. Heuristique pdftotext (lignes MAJUSCULES, lignes isolées) → source="heuristic"

    Tous les titres extraits sont NORMALISÉS (wrapping markdown retiré).
    Faux positifs typiques filtrés en amont (bullets, lignes de tableau, etc.).

    Le champ `source` permet à `title_covered` d'appliquer un seuil de matching
    différent : 1 occurrence suffit pour les markdown (signal fiable), seuil
    plus élevé pour l'heuristique (faux positifs résiduels possibles).
    """
    lines = text.split("\n")
    titles: list[ExtractedTitle] = []

    for i, raw_line in enumerate(lines):
        line = raw_line.lstrip("\x0c").rstrip()
        if not _looks_like_real_title(line):
            continue

        # 1. Markdown heading — source fiable
        if _MARKDOWN_TITLE_RE.match(line):
            t = _strip_markdown_wrapping(line)
            if 3 <= len(t) <= 100:
                titles.append(ExtractedTitle(text=t, source="markdown"))
            continue

        # 2. Heuristique pdftotext
        if not (5 <= len(line) <= 80):
            continue
        letters = [c for c in line if c.isalpha()]
        is_upper = bool(letters) and sum(c.isupper() for c in letters) / len(letters) >= 0.6
        prev_blank = (i == 0) or not lines[i - 1].strip()
        next_blank = (i == len(lines) - 1) or not lines[i + 1].strip()
        if is_upper or (prev_blank and next_blank):
            t = _strip_markdown_wrapping(line)
            if 3 <= len(t):
                titles.append(ExtractedTitle(text=t, source="heuristic"))

    # Déduplication ordre-préservante (par texte, garde la 1ʳᵉ provenance)
    seen: set[str] = set()
    unique: list[ExtractedTitle] = []
    for t in titles:
        key = t.text.lower()
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return unique


# ── Matching fuzzy ────────────────────────────────────────────────────────────

_ACCENTS = str.maketrans("àâäéèêëïîôùûüç", "aaaeeeeiioouuc")


def _normalize(text: str) -> str:
    text = text.lower().translate(_ACCENTS)
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return " ".join(text.split())


_MONOWORD_OCCURRENCE_THRESHOLD_HEURISTIC = 3
"""
Seuil pour un titre mono-mot extrait par HEURISTIQUE (pdftotext). Plus élevé
pour filtrer les faux positifs (lignes isolées qui ne sont pas vraiment des
titres). Ex: maths cycle 4 BO 2026 a "Puissances", "Angles", "Triangles" qui
apparaissent 30-80× — passent largement le seuil.
"""

_MONOWORD_OCCURRENCE_THRESHOLD_MARKDOWN = 1
"""
Seuil pour un titre mono-mot extrait depuis un `## **Titre**` MARKDOWN
(pymupdf4llm). Source fiable (vrai H2 du PDF), 1 occurrence suffit. Cas réel :
"CM1-CM2" présent 2× mais c'est bien un titre H2 du programme cycle 3.
"""


def title_covered(title, chunk_texts: list[str]) -> bool:
    """
    Vérifie si un titre de section apparaît dans au moins un chunk.

    Accepte soit un `ExtractedTitle` (avec source markdown/heuristic) soit un
    `str` (legacy, traité comme heuristique = seuil mono-mot plus strict).

    Logique :
    - Titres multi-mots : sous-chaîne exacte OU overlap ≥70 % si ≥3 mots
    - Titres mono-mots : seuil d'occurrences variable selon source
      (1 pour markdown fiable, 3 pour heuristique pdftotext)
    """
    if isinstance(title, ExtractedTitle):
        title_text = title.text
        source = title.source
    else:
        title_text = title
        source = "heuristic"

    t = _normalize(title_text)
    t_words = set(t.split())

    if len(t_words) == 1:
        threshold = (
            _MONOWORD_OCCURRENCE_THRESHOLD_MARKDOWN
            if source == "markdown"
            else _MONOWORD_OCCURRENCE_THRESHOLD_HEURISTIC
        )
        occurrences = sum(_normalize(chunk).count(t) for chunk in chunk_texts)
        return occurrences >= threshold

    for chunk in chunk_texts:
        c = _normalize(chunk)
        if t in c:
            return True
        if len(t_words) >= 3:
            c_words = set(c.split())
            overlap = len(t_words & c_words)
            if overlap >= len(t_words) * 0.7:
                return True
    return False


# ── Chargement Qdrant ─────────────────────────────────────────────────────────


def load_chunks_from_qdrant(
    collection: str, matiere_filter: str | None = None
) -> dict[str, list[str]]:
    """
    Scrolle tous les points Qdrant. Retourne dict matiere -> [textes chunks].
    Source API : qdrant.tech/documentation/concepts/points/#scroll-points
    """
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    from schema import get_qdrant_client

    client = get_qdrant_client()

    scroll_filter = None
    if matiere_filter:
        scroll_filter = Filter(
            must=[FieldCondition(key="matiere", match=MatchValue(value=matiere_filter))]
        )

    result: dict[str, list[str]] = {}
    offset = None

    while True:
        points, next_offset = client.scroll(
            collection_name=collection,
            scroll_filter=scroll_filter,
            limit=250,
            with_payload=True,
            with_vectors=False,
            offset=offset,
        )
        for p in points:
            if not p.payload:
                continue
            mat = p.payload.get("matiere", "inconnu")
            text = p.payload.get("text", "")
            if text:
                result.setdefault(mat, []).append(text)
        if next_offset is None:
            break
        offset = next_offset

    return result


# ── Audit par matière ─────────────────────────────────────────────────────────


def audit_source(source: dict, chunks: list[str]) -> dict:
    """
    Audite une matière :
    - Charge le texte officiel (data/raw/*.txt)
    - Compare longueur texte source vs. chars indexés
    - Extrait les titres de sections du BO et vérifie leur présence dans les chunks
    """
    from scripts.ingest import load_source_text

    try:
        source_text = load_source_text(source)
    except (FileNotFoundError, ValueError) as e:
        return {
            "error": str(e),
            "source_chars": 0,
            "indexed_chars": 0,
            "text_coverage_pct": 0.0,
            "section_titles": [],
            "titles_covered": 0,
            "titles_total": 0,
            "section_coverage_pct": 0.0,
        }

    source_chars = len(source_text)
    indexed_chars = sum(len(c) for c in chunks)
    text_coverage = min(indexed_chars / source_chars * 100, 100.0) if source_chars else 0.0

    titles = extract_section_titles(source_text)
    covered = [t for t in titles if title_covered(t, chunks)]
    section_pct = len(covered) / len(titles) * 100 if titles else 0.0

    # Expose le texte des titres manquants (str) pour rétro-compat avec le rapport.
    missing_texts = [t.text for t in titles if t not in covered]

    return {
        "error": None,
        "source_chars": source_chars,
        "indexed_chars": indexed_chars,
        "text_coverage_pct": round(text_coverage, 1),
        "section_titles": [t.text for t in titles],
        "titles_covered": len(covered),
        "titles_total": len(titles),
        "section_coverage_pct": round(section_pct, 1),
        "missing_titles": missing_texts,
    }


# ── Rapport ───────────────────────────────────────────────────────────────────


def emit_report(
    results: list[dict],
    output,
    markdown: bool = False,
) -> None:
    def w(s: str = "") -> None:
        print(s, file=output)

    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    if markdown:
        w("# Audit couverture RAG — programmes officiels BO")
        w()
        w(f"_Généré le {ts}_")
        w()
        w(
            "**Source de vérité** : `data/raw/*.txt` (annexes officielles téléchargées"
            " depuis cache.media.education.gouv.fr / data.gouv.fr)"
        )
        w()
        w("| Matière | Texte indexé | Sections BO couvertes |")
        w("|---------|-------------|----------------------|")
    else:
        w("=" * 70)
        w(f"AUDIT COUVERTURE RAG — PROGRAMMES OFFICIELS BO — {ts}")
        w("=" * 70)
        w("Source de vérité : data/raw/*.txt (annexes officielles BO)")
        w()

    for r in results:
        name = r["section_name"]
        mat = r["matiere"]
        if r.get("error"):
            if markdown:
                w(f"| {name} | ❌ {r['error'][:50]} | — |")
            else:
                w(f"  [XX] {name} ({mat}): ERREUR — {r['error']}")
            continue

        txt_pct = r["text_coverage_pct"]
        sec_pct = r["section_coverage_pct"]
        chunks_n = r["chunk_count"]

        if markdown:
            txt_icon = "✅" if txt_pct >= 80 else "⚠️"
            sec_icon = "✅" if sec_pct >= 70 else "⚠️" if sec_pct >= 50 else "❌"
            txt_stat = (
                f"{txt_icon} {txt_pct:.0f}% "
                f"({r['indexed_chars']:,}/{r['source_chars']:,} chars, {chunks_n} chunks)"
            )
            sec_stat = f"{sec_icon} {sec_pct:.0f}% ({r['titles_covered']}/{r['titles_total']})"
            w(f"| {name} | {txt_stat} | {sec_stat} |")
        else:
            txt_tag = "[OK]" if txt_pct >= 80 else "[!!]"
            sec_tag = "[OK]" if sec_pct >= 70 else "[!!]" if sec_pct >= 50 else "[XX]"
            w(f"  {name} ({mat})")
            txt_chars = f"{r['indexed_chars']:,}/{r['source_chars']:,} chars ({chunks_n} chunks)"
            sec_count = f"{r['titles_covered']}/{r['titles_total']} titres BO couverts"
            w(f"    Texte   : {txt_tag} {txt_pct:.0f}% — {txt_chars}")
            w(f"    Sections: {sec_tag} {sec_pct:.0f}% — {sec_count}")
            if r.get("missing_titles") and sec_pct < 70:
                for t in r["missing_titles"][:4]:
                    w(f"       - {t}")
                if len(r["missing_titles"]) > 4:
                    w(f"       … et {len(r['missing_titles']) - 4} autres")
            w()

    if markdown:
        w()
        w("---")
        w()
        w("## Titres de sections BO non couverts")
        w()
        for r in results:
            if r.get("error") or not r.get("missing_titles"):
                continue
            if r["section_coverage_pct"] < 70:
                w(f"### {r['section_name']}")
                w()
                for t in r["missing_titles"]:
                    w(f"- `{t}`")
                w()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None, help="Rapport Markdown")
    parser.add_argument("--matiere", default=None, help="Filtre sur une matière")
    parser.add_argument(
        "--list-missing",
        action="store_true",
        help="Liste exhaustive des titres BO non couverts (debug coverage <100%%)",
    )
    args = parser.parse_args()

    collection = os.environ.get("QDRANT_COLLECTION", "tomai_educational")

    # Importation des SOURCES depuis ingest.py (liste des matières + fichiers source)
    from scripts.ingest import SOURCES

    print(f"Chargement des chunks depuis Qdrant ({collection})…", flush=True)

    # Comparaison Matiere enum vs string CLI (ADR-0007 : SOURCES utilise des enums)
    def _matiere_value(s: dict) -> str:
        m = s["matiere"]
        return m.value if hasattr(m, "value") else str(m)

    sources_to_audit = [s for s in SOURCES if not args.matiere or _matiere_value(s) == args.matiere]
    matieres = [_matiere_value(s) for s in sources_to_audit]
    chunks_by_matiere = load_chunks_from_qdrant(
        collection,
        matiere_filter=args.matiere if len(matieres) == 1 else None,
    )
    total = sum(len(v) for v in chunks_by_matiere.values())
    print(f"  {total} chunks chargés ({len(chunks_by_matiere)} matières)\n")

    results = []
    for source in sources_to_audit:
        mat = _matiere_value(source)
        chunks = chunks_by_matiere.get(mat, [])
        print(f"  Audit {source['section_name']}… ({len(chunks)} chunks)", flush=True)
        r = audit_source(source, chunks)
        r["matiere"] = mat
        r["section_name"] = source["section_name"]
        r["chunk_count"] = len(chunks)
        results.append(r)

    print()

    if args.list_missing:
        # Diagnostic exhaustif : pour chaque matière <100 %, liste les titres BO
        # non couverts. Permet d'investiguer (faux positif heuristique ?
        # faux négatif matching ? vrai trou ?) sans script jetable.
        any_missing = False
        for r in results:
            if r.get("error"):
                continue
            if r["section_coverage_pct"] < 100.0:
                any_missing = True
                cov = f"{r['section_coverage_pct']:.0f}%"
                count = f"{r['titles_covered']}/{r['titles_total']}"
                print(f"\n── {r['section_name']} ({r['matiere']}) = {cov} ({count}) ──")
                for t in r.get("missing_titles", []):
                    print(f"  - {t!r}")
        if not any_missing:
            print("✓ Toutes les matières à 100 % de couverture sections BO.")
        return

    emit_report(results, sys.stdout)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        buf = StringIO()
        emit_report(results, buf, markdown=True)
        args.output.write_text(buf.getvalue(), encoding="utf-8")
        print(f"\nRapport Markdown écrit : {args.output}")


if __name__ == "__main__":
    main()
