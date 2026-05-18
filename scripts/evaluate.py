#!/usr/bin/env python3
"""
Évaluation RETRIEVAL du RAG curriculum — métriques déterministes.

Mesure UNIQUEMENT la qualité de l'INDEX (recall@k, MRR, all_keywords@k),
pas la qualité des réponses LLM. La couche LLM (faithfulness, hallucination,
style socratique) est la responsabilité du backend (tomai-monorepo/apps/server).
Voir docs/adr/0007.

Métriques (aucun appel LLM, juste embed + Qdrant) :
  - Recall@k          : combien des `expected_keywords` apparaissent dans le top-k ?
  - All keywords@k    : binaire — tous les keywords présents dans le top-k ?
  - First hit rank    : rang du premier chunk contenant ≥ 1 keyword
  - MRR               : 1 / first_hit_rank (0 si jamais touché)

Format golden (`data/golden/questions.json`) :
  {"query": "...", "matiere": "...", "niveau": "...", "expected_keywords": [...]}

Usage :
  uv run python scripts/evaluate.py                                # golden défaut
  uv run python scripts/evaluate.py --questions=path/to.json
  uv run python scripts/evaluate.py --top-k=10 --by-matiere
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

from schema import DEFAULT_TOP_K, hybrid_search

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

BASE = Path(__file__).parent.parent
GOLDEN_DIR = BASE / "data" / "golden"


def _score_question(q: dict, chunk_texts: list[str]) -> dict:
    """
    Calcule les métriques retrieval pour une question + ses chunks retournés.

    Match casefold (insensible à la casse), sous-chaîne stricte. Un keyword
    multi-mots ("triangle rectangle") doit apparaître comme expression contiguë.
    """
    expected = q.get("expected_keywords", [])
    if not expected:
        return {
            "query": q["query"],
            "matiere": q.get("matiere", "—"),
            "niveau": q.get("niveau", "—"),
            "n_keywords": 0,
            "hits": 0,
            "recall_at_k": None,
            "all_keywords_found": None,
            "first_hit_rank": None,
            "mrr": None,
            "skipped": True,
        }

    norm_chunks = [c.lower() for c in chunk_texts]
    expected_lc = [k.lower() for k in expected]

    hits = sum(1 for k in expected_lc if any(k in c for c in norm_chunks))
    recall = hits / len(expected_lc)

    first_rank: int | None = None
    for i, c in enumerate(norm_chunks):
        if any(k in c for k in expected_lc):
            first_rank = i + 1
            break

    return {
        "query": q["query"],
        "matiere": q.get("matiere", "—"),
        "niveau": q.get("niveau", "—"),
        "n_keywords": len(expected_lc),
        "hits": hits,
        "recall_at_k": round(recall, 3),
        "all_keywords_found": hits == len(expected_lc),
        "first_hit_rank": first_rank,
        "mrr": round(1.0 / first_rank, 3) if first_rank else 0.0,
        "skipped": False,
    }


def run_evaluation(questions_file: str | None, top_k: int, by_matiere: bool) -> None:
    if questions_file:
        path = Path(questions_file)
    else:
        path = GOLDEN_DIR / "questions.json"

    if not path.exists():
        print(f"✗ Fichier golden absent : {path}", file=sys.stderr)
        sys.exit(1)

    questions = json.loads(path.read_text(encoding="utf-8"))
    print(f"Golden set : {path.name} ({len(questions)} questions)")

    # Compat avec ancien format (question → query)
    for q in questions:
        if "query" not in q and "question" in q:
            q["query"] = q["question"]

    print(f"Top-k      : {top_k}\n")

    results = []
    skipped = 0
    for i, q in enumerate(questions, 1):
        # Pause courte pour rester sous le rate limit Mistral free tier (~1 req/s)
        if i > 1:
            time.sleep(0.8)

        chunks = hybrid_search(
            q["query"],
            top_k=top_k,
            matiere=q.get("matiere"),
            niveau=q.get("niveau"),
        )
        chunk_texts = [c.text for c in chunks]
        r = _score_question(q, chunk_texts)
        results.append(r)

        if r["skipped"]:
            skipped += 1
            status = "·"
        elif r["all_keywords_found"]:
            status = "✓"
        elif r["hits"] > 0:
            status = "~"
        else:
            status = "✗"
        print(
            f"  [{i:3}/{len(questions)}] {status} "
            f"recall={r['recall_at_k'] if r['recall_at_k'] is not None else '—'} "
            f"rank={r['first_hit_rank'] if r['first_hit_rank'] else '—'} "
            f"| {q['query'][:60]}"
        )

    scorable = [r for r in results if not r["skipped"]]
    if not scorable:
        print("\n✗ Aucune question scorable (manquent 'expected_keywords').", file=sys.stderr)
        sys.exit(1)

    print("\n" + "─" * 70)
    print(f"AGRÉGATS GLOBAUX (top-{top_k}, {len(scorable)}/{len(results)} scorables)")
    print("─" * 70)
    avg_recall = sum(r["recall_at_k"] for r in scorable) / len(scorable)
    avg_mrr = sum(r["mrr"] for r in scorable) / len(scorable)
    n_all = sum(1 for r in scorable if r["all_keywords_found"])
    n_any = sum(1 for r in scorable if r["hits"] > 0)
    print(f"  Recall@{top_k} moyen     : {avg_recall:.3f}")
    print(f"  MRR                  : {avg_mrr:.3f}")
    print(f"  All keywords @{top_k}     : {n_all}/{len(scorable)} ({n_all / len(scorable):.0%})")
    print(f"  ≥1 keyword @{top_k}      : {n_any}/{len(scorable)} ({n_any / len(scorable):.0%})")
    if skipped:
        print(f"  Skippées (no keywords) : {skipped}")

    if by_matiere:
        print("\n" + "─" * 70)
        print(f"VENTILATION PAR MATIÈRE (top-{top_k})")
        print("─" * 70)
        by_mat: dict[str, list[dict]] = defaultdict(list)
        for r in scorable:
            by_mat[r["matiere"]].append(r)
        for mat in sorted(by_mat):
            rs = by_mat[mat]
            mat_recall = sum(r["recall_at_k"] for r in rs) / len(rs)
            mat_mrr = sum(r["mrr"] for r in rs) / len(rs)
            mat_all = sum(1 for r in rs if r["all_keywords_found"])
            print(
                f"  {mat:<22} | n={len(rs):2} | recall={mat_recall:.3f} "
                f"| mrr={mat_mrr:.3f} | all_kw={mat_all}/{len(rs)}"
            )

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    out = GOLDEN_DIR / "retrieval_eval.json"
    out.write_text(
        json.dumps(
            {
                "top_k": top_k,
                "n_total": len(results),
                "n_scorable": len(scorable),
                "avg_recall_at_k": avg_recall,
                "mrr": avg_mrr,
                "all_keywords_count": n_all,
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\n✓ Résultats exportés : {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", default=None, help="JSON de questions")
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"Nombre de chunks récupérés (défaut {DEFAULT_TOP_K})",
    )
    parser.add_argument(
        "--by-matiere",
        action="store_true",
        help="Ventile les métriques par matière",
    )
    args = parser.parse_args()

    run_evaluation(args.questions, args.top_k, args.by_matiere)


if __name__ == "__main__":
    main()
