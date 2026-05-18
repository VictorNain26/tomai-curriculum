#!/usr/bin/env python3
"""
Extraction PDF → Markdown via pymupdf4llm.

Remplace `pdftotext` pour les PDFs où la structure sectionnelle compte (cycle 3
et cycle 4 BO 2020 monolithiques qui regroupent toutes les matières).
Le markdown généré préserve les vrais titres en `## Titre` (extraits depuis
les attributs typographiques du PDF : gras, taille de police).

ingest.py préfère le .md s'il existe, sinon retombe sur .txt.

Usage :
  uv run python scripts/extract_pdfs.py                          # tous les PDFs
  uv run python scripts/extract_pdfs.py --pdf=programme_cycle3_BO2020
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pymupdf4llm

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).parent.parent
RAW = BASE / "data" / "raw"


def extract_one(pdf_path: Path, output_md: Path) -> tuple[int, int]:
    """Extrait un PDF → markdown. Retourne (n_chars, n_h2)."""
    md = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=False)
    output_md.write_text(md, encoding="utf-8")
    n_h2 = md.count("\n## ")
    return len(md), n_h2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf",
        help="Nom du PDF sans extension (ex: programme_cycle3_BO2020). "
        "Sinon tous les PDFs de data/raw/ sont traités.",
    )
    args = parser.parse_args()

    if args.pdf:
        pdfs = [RAW / f"{args.pdf}.pdf"]
    else:
        pdfs = sorted(RAW.glob("*.pdf"))

    if not pdfs:
        print("Aucun PDF trouvé.", file=sys.stderr)
        sys.exit(1)

    print(f"Traitement de {len(pdfs)} PDF(s) :\n")
    for pdf in pdfs:
        md_path = pdf.with_suffix(".md")
        try:
            n_chars, n_h2 = extract_one(pdf, md_path)
            print(f"  ✓ {pdf.name:55} → {md_path.name:55} ({n_chars:>7} chars, {n_h2:3} H2)")
        except Exception as e:
            print(f"  ✗ {pdf.name}: {e}", file=sys.stderr)
            raise

    print("\n✓ Tous les PDFs convertis. ingest.py utilisera les .md prioritairement.")


if __name__ == "__main__":
    main()
