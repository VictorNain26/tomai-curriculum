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
from typing import Any

from dotenv import load_dotenv

from schema import DEFAULT_TOP_K, hybrid_search

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

BASE = Path(__file__).parent.parent
GOLDEN_DIR = BASE / "data" / "golden"


def _score_question(q: dict, chunks: list[Any]) -> dict:
    """
    Calcule les métriques retrieval pour une question + ses chunks retournés.

    Deux signaux complémentaires :

    - `chunk_id_hit_rank` : rang du `gold_chunk_id` attendu dans le top-k.
      Disponible uniquement pour les questions document-grounded (générées
      via `scripts/generate_golden.py`). C'est le signal propre, sans
      faux positif keyword (CoFE-RAG arXiv 2410.12248).

    - `recall_at_k` sur keywords : fraction des `expected_keywords` présents
      dans n'importe quel chunk du top-k (sous-chaîne casefold). Sert de
      métrique secondaire de robustesse — robuste aux faux positifs si les
      keywords sont extraits du chunk (cas généré) ; bruité si keywords
      "supposés" (cas seed humain).
    """
    expected = q.get("expected_keywords", [])
    gold_id = q.get("gold_chunk_id")

    if not expected and not gold_id:
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
            "chunk_id_hit_rank": None,
            "chunk_id_mrr": None,
            "skipped": True,
        }

    # Keyword recall (compat avec golden set seed sans chunk_id)
    chunk_texts = [c.text for c in chunks]
    norm_chunks = [c.lower() for c in chunk_texts]
    expected_lc = [k.lower() for k in expected]

    hits = sum(1 for k in expected_lc if any(k in c for c in norm_chunks)) if expected_lc else 0
    recall = (hits / len(expected_lc)) if expected_lc else None

    first_rank: int | None = None
    for i, c in enumerate(norm_chunks):
        if expected_lc and any(k in c for k in expected_lc):
            first_rank = i + 1
            break

    # Chunk-id recall (signal propre quand dispo)
    chunk_id_hit_rank: int | None = None
    if gold_id:
        for i, c in enumerate(chunks):
            cid = getattr(c, "payload", {}).get("id") if hasattr(c, "payload") else None
            # Le payload Qdrant ne stocke pas l'ID — il est dans `r.id` côté
            # response.points. On le retrouve via `c.payload` si stocké ou
            # via `getattr(c, "id", None)` selon la shape HybridResult.
            cid = cid or getattr(c, "id", None)
            if cid and str(cid) == gold_id:
                chunk_id_hit_rank = i + 1
                break

    return {
        "query": q["query"],
        "matiere": q.get("matiere", "—"),
        "niveau": q.get("niveau", "—"),
        "n_keywords": len(expected_lc),
        "hits": hits,
        "recall_at_k": round(recall, 3) if recall is not None else None,
        "all_keywords_found": (hits == len(expected_lc)) if expected_lc else None,
        "first_hit_rank": first_rank,
        "mrr": round(1.0 / first_rank, 3) if first_rank else 0.0,
        "chunk_id_hit_rank": chunk_id_hit_rank,
        "chunk_id_mrr": round(1.0 / chunk_id_hit_rank, 3)
        if chunk_id_hit_rank
        else (0.0 if gold_id else None),
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
        r = _score_question(q, chunks)
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

    # Separate sets for keyword-only vs chunk_id-grounded scoring.
    kw_scorable = [r for r in scorable if r["recall_at_k"] is not None]
    cid_scorable = [
        r
        for r in scorable
        if r["chunk_id_hit_rank"] is not None or (r.get("chunk_id_mrr") is not None)
    ]

    print("\n" + "─" * 70)
    print(f"AGRÉGATS GLOBAUX (top-{top_k}, {len(scorable)}/{len(results)} scorables)")
    print("─" * 70)
    if kw_scorable:
        avg_recall = sum(r["recall_at_k"] for r in kw_scorable) / len(kw_scorable)
        avg_mrr = sum(r["mrr"] for r in kw_scorable) / len(kw_scorable)
        n_all = sum(1 for r in kw_scorable if r["all_keywords_found"])
        n_any = sum(1 for r in kw_scorable if r["hits"] > 0)
        print(f"  [keyword] Recall@{top_k}     : {avg_recall:.3f}")
        print(f"  [keyword] MRR             : {avg_mrr:.3f}")
        print(
            f"  [keyword] All kw @{top_k}     : {n_all}/{len(kw_scorable)} "
            f"({n_all / len(kw_scorable):.0%})"
        )
        print(
            f"  [keyword] ≥1 kw @{top_k}      : {n_any}/{len(kw_scorable)} "
            f"({n_any / len(kw_scorable):.0%})"
        )
    else:
        avg_recall = avg_mrr = 0.0
        n_all = n_any = 0
    if cid_scorable:
        cid_hits = sum(1 for r in cid_scorable if r["chunk_id_hit_rank"])
        cid_recall = cid_hits / len(cid_scorable)
        cid_mrr = sum(r["chunk_id_mrr"] for r in cid_scorable) / len(cid_scorable)
        print(
            f"  [chunk_id] Recall@{top_k}    : {cid_recall:.3f} "
            f"({cid_hits}/{len(cid_scorable)}) — signal propre, document-grounded"
        )
        print(f"  [chunk_id] MRR            : {cid_mrr:.3f}")
    else:
        cid_recall = cid_mrr = 0.0
    if skipped:
        print(f"  Skippées (no keywords / no gold_chunk_id) : {skipped}")

    if by_matiere:
        print("\n" + "─" * 70)
        print(f"VENTILATION PAR MATIÈRE (top-{top_k})")
        print("─" * 70)
        by_mat: dict[str, list[dict]] = defaultdict(list)
        for r in scorable:
            by_mat[r["matiere"]].append(r)
        for mat in sorted(by_mat):
            rs = by_mat[mat]
            kw_rs = [r for r in rs if r["recall_at_k"] is not None]
            cid_rs = [
                r
                for r in rs
                if r["chunk_id_hit_rank"] is not None or r.get("chunk_id_mrr") is not None
            ]
            mat_kw = sum(r["recall_at_k"] for r in kw_rs) / len(kw_rs) if kw_rs else 0.0
            mat_cid = (
                sum(1 for r in cid_rs if r["chunk_id_hit_rank"]) / len(cid_rs) if cid_rs else 0.0
            )
            mat_mrr = sum(r["mrr"] for r in kw_rs) / len(kw_rs) if kw_rs else 0.0
            print(
                f"  {mat:<22} | n={len(rs):3} | kw_recall={mat_kw:.3f} "
                f"| cid_recall={mat_cid:.3f} | mrr={mat_mrr:.3f}"
            )

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    out = GOLDEN_DIR / "retrieval_eval.json"
    out.write_text(
        json.dumps(
            {
                "top_k": top_k,
                "n_total": len(results),
                "n_scorable": len(scorable),
                "n_kw_scorable": len(kw_scorable),
                "n_chunk_id_scorable": len(cid_scorable),
                "kw_avg_recall_at_k": avg_recall,
                "kw_mrr": avg_mrr,
                "kw_all_keywords_count": n_all,
                "chunk_id_recall_at_k": cid_recall,
                "chunk_id_mrr": cid_mrr,
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
