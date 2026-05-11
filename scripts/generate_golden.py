#!/usr/bin/env python3
"""
Génère un golden set d'évaluation RAG à partir des `typical_questions`
curatées présentes dans chaque document JSONL.

Pourquoi : chaque document du dataset contient 3-5 questions types rédigées
manuellement par le créateur du contenu (champ `typical_questions` du schema
Pydantic). Ces questions sont exactement le ground truth attendu : "quand un
élève pose cette question, ce document devrait être retrouvé en top-1".

Avantages vs golden set 100% manuel :
- ~5000 queries (1892 docs × 2-3 questions retenues en moyenne) au lieu de 31
- Couverture stratifiée naturelle par (niveau × matière) : 154 cellules
- Coût marginal nul (réutilise un travail de curation déjà fait)
- expected_ids exact (l'UUID du doc source de la question)

Limites :
- Pas un substitut au golden set manuel curé pour les queries adversariales,
  ambiguës ou multi-doc (RAGAS testset generator + review humaine restent
  utiles en complément)
- Une `typical_question` peut être trop proche du `title` du doc, gonflant
  artificiellement le retrieval — on filtre les questions trop courtes ou
  trop similaires au titre

Usage :
    uv run python scripts/generate_golden.py run \\
        --output data/golden/test_queries_from_typical.json

    uv run python scripts/generate_golden.py run \\
        --niveau cinquieme --matiere mathematiques \\
        --output data/golden/cinquieme_math.json

Le fichier produit est consommable directement par `scripts/evaluate.py run`.
"""

import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

sys.path.insert(0, str(Path(__file__).parent.parent))

# Forcer stdout/stderr en UTF-8 sur Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from scripts.ingest import load_documents
from scripts.utils import get_all_jsonl_files

app = typer.Typer(
    name="generate-golden",
    help="Génère un golden set RAG depuis les typical_questions curatées",
)
console = Console()


# Heuristiques de filtrage : on garde les questions qui sont VRAIMENT des
# queries d'élève, pas des reformulations triviales du titre.
MIN_QUERY_LENGTH = 10
MAX_QUERY_LENGTH = 200


def _is_quality_query(query: str, title: str) -> bool:
    """
    Filtre les questions de mauvaise qualité pour le golden set :
    - Trop courtes (< 10 chars) ou trop longues (> 200 chars)
    - Trop similaires au titre (la query est juste le titre + "?")
    """
    q = query.strip()
    if not (MIN_QUERY_LENGTH <= len(q) <= MAX_QUERY_LENGTH):
        return False

    q_normalized = q.rstrip("?!. ").lower()
    title_normalized = title.rstrip("?!. ").lower()

    # Trop proche du titre (overlap de mots Jaccard)
    q_words = set(q_normalized.split())
    title_words = set(title_normalized.split())
    if not q_words or not title_words:
        return True
    overlap = len(q_words & title_words) / len(q_words | title_words)
    return overlap < 0.7  # rejeter si > 70% de mots communs


def _build_query_entry(query: str, doc_data: dict, counter: int) -> dict:
    """Construit une entrée golden conforme au schema attendu par evaluate.py."""
    doc = doc_data["doc"]
    matiere = doc_data["matiere"]
    return {
        "id": f"auto_{matiere}_{doc_data['niveau']}_{counter:04d}",
        "query": query.strip(),
        "expected_ids": [doc_data["id"]],
        "matiere_filter": matiere,
        "niveau_filter": doc_data["niveau"],
        "source": "typical_questions",
        "source_doc_title": doc.title,
        "source_doc_id": doc_data["id"],
    }


@app.command()
def run(
    output: Annotated[
        Path, typer.Option(help="Fichier de sortie JSON")
    ] = Path("data/golden/test_queries_from_typical.json"),
    niveau: Annotated[str | None, typer.Option(help="Filtrer par niveau")] = None,
    matiere: Annotated[str | None, typer.Option(help="Filtrer par matière")] = None,
    max_per_doc: Annotated[
        int, typer.Option(help="Max typical_questions retenues par document")
    ] = 3,
) -> None:
    """Extrait les typical_questions et produit un golden set evaluate.py-compatible."""
    files = get_all_jsonl_files(niveau, matiere)
    if not files:
        rprint("[yellow]Aucun JSONL trouvé[/yellow]")
        raise typer.Exit(0)

    docs = load_documents(files)
    rprint(f"\n[bold cyan]Génération golden set[/bold cyan] depuis {len(docs)} documents")

    queries: list[dict] = []
    stats: dict[str, int] = defaultdict(int)
    counter = 0

    for doc_data in docs:
        doc = doc_data["doc"]
        typical = getattr(doc, "typical_questions", None) or []
        if not typical:
            stats["no_typical"] += 1
            continue

        kept_for_doc = 0
        for q in typical:
            if kept_for_doc >= max_per_doc:
                break
            if not _is_quality_query(q, doc.title):
                stats["filtered_quality"] += 1
                continue
            counter += 1
            queries.append(_build_query_entry(q, doc_data, counter))
            kept_for_doc += 1
            stats["kept"] += 1

        if kept_for_doc == 0:
            stats["all_filtered"] += 1

    # Stratification : nb queries par (niveau, matière)
    distribution: dict[tuple[str, str], int] = defaultdict(int)
    for q in queries:
        distribution[(q["niveau_filter"], q["matiere_filter"])] += 1

    output_data = {
        "version": "1.0.0",
        "schema": "expected_ids",
        "source": "typical_questions",
        "generated_at": datetime.now(UTC).isoformat(),
        "description": (
            "Golden set auto-généré depuis les typical_questions curatées "
            "des documents JSONL. Chaque query a un expected_id unique "
            "(le document source). À compléter par un golden manuel pour "
            "queries adversariales et multi-doc."
        ),
        "metrics_target": {
            "recall@5": 0.85,
            "recall@10": 0.95,
            "precision@5": 0.20,
            "mrr": 0.7,
            "ndcg@10": 0.8,
        },
        "queries": queries,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    rprint(f"\n[green]✓ {len(queries)} queries générées[/green] → {output}")
    rprint(f"  - {stats['kept']} retenues")
    rprint(f"  - {stats['filtered_quality']} filtrées (trop courtes / proches du titre)")
    rprint(f"  - {stats['no_typical']} docs sans typical_questions")
    rprint(f"  - {stats['all_filtered']} docs où toutes les questions ont été filtrées")

    table = Table(title="Distribution par (niveau × matière)")
    table.add_column("Niveau", style="cyan")
    table.add_column("Matière", style="magenta")
    table.add_column("Queries", justify="right")

    for (niv, mat), count in sorted(distribution.items(), key=lambda x: -x[1]):
        table.add_row(niv, mat, str(count))

    console.print(table)


if __name__ == "__main__":
    app()
