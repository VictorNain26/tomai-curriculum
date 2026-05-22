#!/usr/bin/env python3
"""
Outil interactif : tester le retrieval hybrid sur la collection Qdrant.

Affiche les chunks retournés (top-k) — RIEN de plus. Ce repo gère
exclusivement l'INDEX, pas la couche LLM. Toute génération de réponse
(tutorat socratique, chat) est la responsabilité du backend
(tomai-monorepo/apps/server). Voir docs/ARCHITECTURE.md.

Usage :
  uv run python scripts/query.py "Comment calculer le PGCD ?"
  uv run python scripts/query.py --matiere=mathematiques --top-k=5 "Pythagore"
  uv run python scripts/query.py --niveau=cinquieme "respiration cellulaire"
  uv run python scripts/query.py --cycle=cycle4 --matiere=svt "photosynthèse"
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from schema import DEFAULT_TOP_K, hybrid_search

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", help="Question / mots-clés")
    parser.add_argument("--matiere", help="Filtre matière (ex: mathematiques)")
    parser.add_argument("--niveau", help="Filtre niveau (ex: cinquieme)")
    parser.add_argument("--cycle", help="Filtre cycle (ex: cycle4)")
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"Nombre de chunks retournés (défaut {DEFAULT_TOP_K})",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Affiche le texte complet de chaque chunk (sinon tronqué à 250 chars)",
    )
    args = parser.parse_args()

    if not args.query:
        parser.print_help()
        sys.exit(0)

    print(f"Requête : {args.query}")
    filters = []
    if args.matiere:
        filters.append(f"matiere={args.matiere}")
    if args.niveau:
        filters.append(f"niveau={args.niveau}")
    if args.cycle:
        filters.append(f"cycle={args.cycle}")
    if filters:
        print(f"Filtres : {' & '.join(filters)}")

    print(f"Hybrid search (top-{args.top_k})…", end=" ", flush=True)
    chunks = hybrid_search(
        args.query,
        top_k=args.top_k,
        matiere=args.matiere,
        niveau=args.niveau,
        cycle=args.cycle,
    )
    print(f"{len(chunks)} chunks\n")

    for i, c in enumerate(chunks, 1):
        print(f"[{i}] [{c.matiere} | {c.niveau} | {c.section}] score={c.score:.4f}")
        if args.full:
            print(f"    {c.text}\n")
        else:
            print(f"    {c.text[:250]}{'…' if len(c.text) > 250 else ''}\n")


if __name__ == "__main__":
    main()
