#!/usr/bin/env python3
"""
Évaluation RETRIEVAL du RAG curriculum — métriques déterministes.

Mesure UNIQUEMENT la qualité de l'INDEX (chunk_id recall, MRR, keyword recall),
pas la qualité des réponses LLM. La couche LLM (faithfulness, hallucination,
style socratique) est la responsabilité du backend (tomai-monorepo/apps/server).
Voir docs/ARCHITECTURE.md.

Deux signaux complémentaires, sans appel LLM :

  - **[primary] chunk_id recall@k** : le `gold_chunk_id` (UUID5 du chunk
    source) est-il dans le top-k ? Disponible pour les questions générées
    par `generate_golden.py` (document-grounded). Signal propre, immune
    aux faux positifs lexicaux. Référence : arXiv 2510.21440 (Redefining
    Retrieval Evaluation), CoFE-RAG arXiv 2410.12248.

  - **[secondary] keyword recall@k** : fraction des `expected_keywords`
    présents dans n'importe quel chunk du top-k (sous-chaîne casefold).
    Robuste si les keywords sont extraits du chunk (cas généré) ; biaisé
    si keywords "supposés" (cas seed humain — surestime le recall).
    Conservé pour comparaison historique et pour les golden sets seed.

Format golden (`data/golden/questions.json`) — schema Pydantic
`schema.golden.GoldenQuestion` :
  {"query": "...", "matiere": "...", "niveau": "...",
   "expected_keywords": [...], "gold_chunk_id": "...", "gold_section": "...",
   "gold_source_file": "..."}

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

from schema import (
    DEFAULT_EMBED_MODEL,
    DEFAULT_SPARSE_METHOD,
    DEFAULT_TOP_K,
    EMBEDDING_MODELS_1024D,
    SPARSE_METHODS,
    hybrid_search,
)

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


def run_evaluation(
    questions_file: str | None,
    top_k: int,
    by_matiere: bool,
    fusion: str = "rrf",
    output_suffix: str = "",
    embed_model: str = DEFAULT_EMBED_MODEL,
    sparse_method: str = DEFAULT_SPARSE_METHOD,
    collection: str | None = None,
) -> None:
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

    print(f"Top-k      : {top_k}")
    print(f"Fusion     : {fusion}")
    print(f"Embed      : {embed_model}")
    print(f"Sparse     : {sparse_method}")
    if collection:
        print(f"Collection : {collection}")
    print()

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
            fusion=fusion,
            embed_model=embed_model,
            sparse_method=sparse_method,
            collection=collection,
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
    # [primary] chunk_id recall affiché EN PREMIER — métrique propre,
    # document-grounded (arXiv 2510.21440, CoFE-RAG arXiv 2410.12248).
    if cid_scorable:
        cid_hits = sum(1 for r in cid_scorable if r["chunk_id_hit_rank"])
        cid_recall = cid_hits / len(cid_scorable)
        cid_mrr = sum(r["chunk_id_mrr"] for r in cid_scorable) / len(cid_scorable)
        print(
            f"  [PRIMARY] chunk_id Recall@{top_k} : {cid_recall:.3f} "
            f"({cid_hits}/{len(cid_scorable)})"
        )
        print(f"  [PRIMARY] chunk_id MRR        : {cid_mrr:.3f}")
    else:
        cid_recall = cid_mrr = 0.0
        print(
            f"  [PRIMARY] chunk_id Recall@{top_k} : N/A "
            "(régénérer le golden via scripts/generate_golden.py)"
        )
    if kw_scorable:
        avg_recall = sum(r["recall_at_k"] for r in kw_scorable) / len(kw_scorable)
        avg_mrr = sum(r["mrr"] for r in kw_scorable) / len(kw_scorable)
        n_all = sum(1 for r in kw_scorable if r["all_keywords_found"])
        n_any = sum(1 for r in kw_scorable if r["hits"] > 0)
        print(f"  [secondary] keyword Recall@{top_k}: {avg_recall:.3f}")
        print(f"  [secondary] keyword MRR       : {avg_mrr:.3f}")
        print(
            f"  [secondary] All kw @{top_k}       : {n_all}/{len(kw_scorable)} "
            f"({n_all / len(kw_scorable):.0%})"
        )
        print(
            f"  [secondary] ≥1 kw @{top_k}        : {n_any}/{len(kw_scorable)} "
            f"({n_any / len(kw_scorable):.0%})"
        )
    else:
        avg_recall = avg_mrr = 0.0
        n_all = n_any = 0
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
                f"  {mat:<22} | n={len(rs):3} | cid_recall={mat_cid:.3f} "
                f"| kw_recall={mat_kw:.3f} | mrr={mat_mrr:.3f}"
            )

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    out_name = f"retrieval_eval{output_suffix}.json"
    out = GOLDEN_DIR / out_name
    out.write_text(
        json.dumps(
            {
                "top_k": top_k,
                "fusion": fusion,
                "embed_model": embed_model,
                "sparse_method": sparse_method,
                "collection": collection,
                "n_total": len(results),
                "n_scorable": len(scorable),
                # [primary] chunk_id metrics first (document-grounded signal propre)
                "n_chunk_id_scorable": len(cid_scorable),
                "chunk_id_recall_at_k": cid_recall,
                "chunk_id_mrr": cid_mrr,
                # [secondary] keyword metrics (biaisé sur seed sets)
                "n_kw_scorable": len(kw_scorable),
                "kw_avg_recall_at_k": avg_recall,
                "kw_mrr": avg_mrr,
                "kw_all_keywords_count": n_all,
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
    parser.add_argument(
        "--fusion",
        choices=["rrf", "dbsf"],
        default="rrf",
        help="Méthode de fusion hybrid search (rrf par défaut, dbsf = "
        "Distribution-Based Score Fusion Qdrant 1.11+).",
    )
    parser.add_argument(
        "--output-suffix",
        default="",
        help="Suffixe pour le fichier de sortie (ex: '-dbsf' → retrieval_eval-dbsf.json)",
    )
    parser.add_argument(
        "--embed-model",
        default=DEFAULT_EMBED_MODEL,
        choices=list(EMBEDDING_MODELS_1024D),
        help=f"Modèle d'embedding pour la query (défaut {DEFAULT_EMBED_MODEL}).",
    )
    parser.add_argument(
        "--sparse-method",
        default=DEFAULT_SPARSE_METHOD,
        choices=list(SPARSE_METHODS),
        help=(
            f"Méthode sparse (défaut {DEFAULT_SPARSE_METHOD}). "
            "Doit matcher la méthode utilisée à l'ingest sur cette collection."
        ),
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="Override la collection Qdrant cible (sinon QDRANT_COLLECTION env).",
    )
    args = parser.parse_args()

    run_evaluation(
        args.questions,
        args.top_k,
        args.by_matiere,
        fusion=args.fusion,
        output_suffix=args.output_suffix,
        embed_model=args.embed_model,
        sparse_method=args.sparse_method,
        collection=args.collection,
    )


if __name__ == "__main__":
    main()
