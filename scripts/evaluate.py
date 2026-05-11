#!/usr/bin/env python3
"""
Evaluation RAG Expert - Metriques standards 2025.

Calcule les metriques de retrieval:
- Recall@K: % de documents pertinents retrouves
- Precision@K: % de documents retrouves qui sont pertinents
- MRR: Mean Reciprocal Rank (position du 1er doc pertinent)
- NDCG@K: Normalized Discounted Cumulative Gain (qualite du ranking)

Sources:
- https://qdrant.tech/blog/rag-evaluation-guide/
- https://www.confident-ai.com/blog/rag-evaluation-metrics-answer-relevancy-faithfulness-and-more
"""

import json
import math
import time
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv
from mistralai import Mistral
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue
from rich import print as rprint
from rich.console import Console
from rich.table import Table

# Charger .env avant toute lecture d'env var par les commandes Typer
load_dotenv()

app = typer.Typer(name="evaluate", help="Evaluation RAG expert")
console = Console()

EMBEDDING_MODEL = "mistral-embed"


def normalize_title(title: str) -> str:
    """Normalise un titre pour comparaison (lowercase, sans accents basiques)."""
    import unicodedata
    # Lowercase
    title = title.lower().strip()
    # Supprimer accents
    title = unicodedata.normalize('NFD', title)
    title = ''.join(c for c in title if unicodedata.category(c) != 'Mn')
    return title


def title_matches(retrieved_title: str, expected_title: str) -> bool:
    """Verifie si un titre recupere correspond a un titre attendu (fuzzy)."""
    r = normalize_title(retrieved_title)
    e = normalize_title(expected_title)
    # Match exact ou contenu
    return r == e or e in r or r in e


def calculate_recall_at_k(retrieved_titles: list[str], expected_titles: list[str], k: int) -> float:
    """
    Recall@K = |retrieved_relevant| / |expected_relevant|
    Proportion de documents pertinents qui ont ete retrouves.
    """
    if not expected_titles:
        return 1.0

    top_k = retrieved_titles[:k]
    found = 0
    for expected in expected_titles:
        for retrieved in top_k:
            if title_matches(retrieved, expected):
                found += 1
                break

    return found / len(expected_titles)


def calculate_precision_at_k(retrieved_titles: list[str], expected_titles: list[str], k: int) -> float:
    """
    Precision@K = |retrieved_relevant| / K
    Proportion de documents retrouves qui sont pertinents.
    """
    top_k = retrieved_titles[:k]
    if not top_k:
        return 0.0

    relevant = 0
    for retrieved in top_k:
        for expected in expected_titles:
            if title_matches(retrieved, expected):
                relevant += 1
                break

    return relevant / len(top_k)


def calculate_mrr(retrieved_titles: list[str], expected_titles: list[str]) -> float:
    """
    MRR = 1 / rank_of_first_relevant
    Reciprocal rank du premier document pertinent.
    """
    for i, retrieved in enumerate(retrieved_titles, 1):
        for expected in expected_titles:
            if title_matches(retrieved, expected):
                return 1.0 / i
    return 0.0


def calculate_ndcg_at_k(retrieved_titles: list[str], expected_titles: list[str], k: int) -> float:
    """
    NDCG@K = DCG@K / IDCG@K
    Mesure la qualite du ranking (documents pertinents en haut).
    """
    top_k = retrieved_titles[:k]

    # DCG: Discounted Cumulative Gain
    dcg = 0.0
    for i, retrieved in enumerate(top_k, 1):
        rel = 0
        for expected in expected_titles:
            if title_matches(retrieved, expected):
                rel = 1
                break
        dcg += rel / math.log2(i + 1)

    # IDCG: Ideal DCG (tous les pertinents en premier)
    ideal_rels = [1] * min(len(expected_titles), k) + [0] * max(0, k - len(expected_titles))
    idcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(ideal_rels))

    if idcg == 0:
        return 0.0

    return dcg / idcg


def generate_embedding(client: Mistral, text: str) -> list[float]:
    """Genere un embedding Mistral 1024D."""
    result = client.embeddings.create(model=EMBEDDING_MODEL, inputs=[text])
    embedding = result.data[0].embedding
    # Normaliser
    magnitude = math.sqrt(sum(v * v for v in embedding))
    return [v / magnitude for v in embedding]


@app.command()
def run(
    test_file: Annotated[str, typer.Option(help="Fichier de test queries")] = "data/test_queries.json",
    qdrant_url: Annotated[str | None, typer.Option("--qdrant-url", envvar="QDRANT_URL")] = None,
    qdrant_api_key: Annotated[str | None, typer.Option("--qdrant-api-key", envvar="QDRANT_API_KEY")] = None,
    mistral_api_key: Annotated[str | None, typer.Option("--mistral-api-key", envvar="MISTRAL_API_KEY")] = None,
    collection: Annotated[str, typer.Option(envvar="QDRANT_COLLECTION")] = "tomai_educational",
    top_k: Annotated[int, typer.Option(help="Nombre de resultats a recuperer")] = 10,
    output: Annotated[str | None, typer.Option(help="Fichier de sortie JSON")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
):
    """Execute l'evaluation RAG avec les metriques standard."""

    if not qdrant_url or not qdrant_api_key or not mistral_api_key:
        rprint("[red]QDRANT_URL, QDRANT_API_KEY et MISTRAL_API_KEY requis[/red]")
        raise typer.Exit(1)

    # Charger les test queries
    test_path = Path(test_file)
    if not test_path.exists():
        rprint(f"[red]Fichier de test non trouve: {test_file}[/red]")
        raise typer.Exit(1)

    with open(test_path, encoding="utf-8") as f:
        test_data = json.load(f)

    queries = test_data["queries"]
    targets = test_data.get("metrics_target", {})

    rprint("\n[bold cyan]Evaluation RAG Expert[/bold cyan]")
    rprint(f"  Collection: {collection}")
    rprint(f"  Test queries: {len(queries)}")
    rprint(f"  Top-K: {top_k}")

    # Initialiser clients
    mistral_client = Mistral(api_key=mistral_api_key)
    qdrant_client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)

    # Resultats
    results = []
    all_recall_5 = []
    all_recall_10 = []
    all_precision_5 = []
    all_mrr = []
    all_ndcg_10 = []

    rprint("\n[bold]Execution des queries...[/bold]")

    for i, q in enumerate(queries, 1):
        query_id = q["id"]
        query_text = q["query"]
        expected_titles = q["expected_titles"]
        matiere_filter = q.get("matiere_filter")

        # Generer embedding
        try:
            embedding = generate_embedding(mistral_client, query_text)
            time.sleep(0.5)  # Rate limit
        except Exception as e:
            rprint(f"  [red]Erreur embedding {query_id}: {e}[/red]")
            continue

        # Construire filtre
        search_filter = None
        if matiere_filter:
            search_filter = Filter(
                must=[FieldCondition(key="matiere", match=MatchValue(value=matiere_filter))]
            )

        # Recherche Qdrant (API v2: query_points)
        search_results = qdrant_client.query_points(
            collection_name=collection,
            query=embedding,
            query_filter=search_filter,
            limit=top_k,
            with_payload=True,
        )

        retrieved_titles = [r.payload.get("title", "") for r in search_results.points]

        # Calculer metriques
        recall_5 = calculate_recall_at_k(retrieved_titles, expected_titles, 5)
        recall_10 = calculate_recall_at_k(retrieved_titles, expected_titles, 10)
        precision_5 = calculate_precision_at_k(retrieved_titles, expected_titles, 5)
        mrr = calculate_mrr(retrieved_titles, expected_titles)
        ndcg_10 = calculate_ndcg_at_k(retrieved_titles, expected_titles, 10)

        all_recall_5.append(recall_5)
        all_recall_10.append(recall_10)
        all_precision_5.append(precision_5)
        all_mrr.append(mrr)
        all_ndcg_10.append(ndcg_10)

        result = {
            "id": query_id,
            "query": query_text,
            "expected": expected_titles,
            "retrieved": retrieved_titles[:5],
            "recall@5": recall_5,
            "recall@10": recall_10,
            "precision@5": precision_5,
            "mrr": mrr,
            "ndcg@10": ndcg_10,
        }
        results.append(result)

        # Affichage verbose
        if verbose:
            status = "[green]OK[/green]" if recall_5 >= 0.8 else "[yellow]PARTIAL[/yellow]" if recall_5 > 0 else "[red]MISS[/red]"
            rprint(f"  [{i}/{len(queries)}] {query_id}: {status} (R@5={recall_5:.2f}, MRR={mrr:.2f})")
        else:
            rprint(f"  [{i}/{len(queries)}] {query_id}...", end="\r")

    # Moyennes
    avg_recall_5 = sum(all_recall_5) / len(all_recall_5) if all_recall_5 else 0
    avg_recall_10 = sum(all_recall_10) / len(all_recall_10) if all_recall_10 else 0
    avg_precision_5 = sum(all_precision_5) / len(all_precision_5) if all_precision_5 else 0
    avg_mrr = sum(all_mrr) / len(all_mrr) if all_mrr else 0
    avg_ndcg_10 = sum(all_ndcg_10) / len(all_ndcg_10) if all_ndcg_10 else 0

    # Affichage resultats
    rprint(f"\n[bold cyan]{'='*60}[/bold cyan]")
    rprint("[bold cyan]RESULTATS DE L'EVALUATION RAG[/bold cyan]")
    rprint(f"[bold cyan]{'='*60}[/bold cyan]")

    table = Table(show_header=True)
    table.add_column("Metrique")
    table.add_column("Score", justify="right")
    table.add_column("Target", justify="right")
    table.add_column("Status", justify="center")

    def status_icon(score: float, target: float) -> str:
        if score >= target:
            return "[green]PASS[/green]"
        elif score >= target * 0.8:
            return "[yellow]CLOSE[/yellow]"
        else:
            return "[red]FAIL[/red]"

    metrics_display = [
        ("Recall@5", avg_recall_5, targets.get("recall@5", 0.8)),
        ("Recall@10", avg_recall_10, targets.get("recall@10", 0.9)),
        ("Precision@5", avg_precision_5, targets.get("precision@5", 0.4)),
        ("MRR", avg_mrr, targets.get("mrr", 0.7)),
        ("NDCG@10", avg_ndcg_10, targets.get("ndcg@10", 0.75)),
    ]

    for name, score, target in metrics_display:
        table.add_row(name, f"{score:.3f}", f"{target:.2f}", status_icon(score, target))

    console.print(table)

    # Score global
    passed = sum(1 for _, score, target in metrics_display if score >= target)
    total = len(metrics_display)
    global_score = passed / total * 100

    rprint(f"\n[bold]Score global: {passed}/{total} metriques passees ({global_score:.0f}%)[/bold]")

    if global_score >= 80:
        rprint("[green]Excellent! Le systeme RAG est performant.[/green]")
    elif global_score >= 60:
        rprint("[yellow]Correct, mais des ameliorations sont recommandees.[/yellow]")
    else:
        rprint("[red]Ameliorations necessaires - verifier embeddings et documents.[/red]")

    # Details par categorie
    rprint("\n[bold]Details par query:[/bold]")

    # Queries avec problemes
    failed_queries = [r for r in results if r["recall@5"] < 0.5]
    if failed_queries:
        rprint("\n[yellow]Queries avec faible recall (<0.5):[/yellow]")
        for r in failed_queries[:5]:
            rprint(f"  - {r['id']}: '{r['query'][:50]}...'")
            rprint(f"    Attendu: {r['expected']}")
            rprint(f"    Obtenu: {r['retrieved'][:3]}")

    # Export JSON
    if output:
        export_data = {
            "evaluation_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "collection": collection,
            "num_queries": len(queries),
            "top_k": top_k,
            "metrics": {
                "recall@5": avg_recall_5,
                "recall@10": avg_recall_10,
                "precision@5": avg_precision_5,
                "mrr": avg_mrr,
                "ndcg@10": avg_ndcg_10,
            },
            "targets": targets,
            "global_score": global_score,
            "results": results,
        }
        with open(output, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        rprint(f"\n[dim]Resultats exportes vers {output}[/dim]")


if __name__ == "__main__":
    app()
