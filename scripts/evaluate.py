#!/usr/bin/env python3
"""
Script d'évaluation RAG - Best Practices 2025.

Mesure la qualité du retrieval avec des métriques standard:
- Recall@K: Proportion de documents pertinents retrouvés dans les top-K
- MRR (Mean Reciprocal Rank): Position moyenne du premier document pertinent
- NDCG@K (Normalized Discounted Cumulative Gain): Qualité du ranking

Usage:
    uv run python scripts/evaluate.py run --test-queries data/test_queries.json
    uv run python scripts/evaluate.py run --test-queries data/test_queries.json --output metrics.json
"""

import json
import math
import sys
from pathlib import Path
from typing import Annotated

from rich import print as rprint
from rich.console import Console
from rich.table import Table

console = Console()

# Add parent to path for schema import
sys.path.insert(0, str(Path(__file__).parent.parent))


def recall_at_k(retrieved: list[str], expected: list[str], k: int = 5) -> float:
    """
    Calcule le Recall@K.

    Mesure la proportion de documents pertinents retrouvés dans les top-K.

    Args:
        retrieved: Liste des IDs de documents retrouvés (ordonnés par score)
        expected: Liste des IDs de documents pertinents
        k: Nombre de résultats à considérer

    Returns:
        Score entre 0 et 1
    """
    if not expected:
        return 1.0  # Pas de document attendu

    top_k = set(retrieved[:k])
    relevant_found = len(top_k.intersection(expected))

    return relevant_found / len(expected)


def mean_reciprocal_rank(retrieved: list[str], expected: list[str]) -> float:
    """
    Calcule le MRR (Mean Reciprocal Rank).

    Mesure la position du premier document pertinent.
    Plus le document pertinent est haut dans le ranking, meilleur est le score.

    Args:
        retrieved: Liste des IDs de documents retrouvés (ordonnés par score)
        expected: Liste des IDs de documents pertinents

    Returns:
        Score entre 0 et 1 (1/position du premier document pertinent)
    """
    for i, doc_id in enumerate(retrieved, 1):
        if doc_id in expected:
            return 1.0 / i

    return 0.0  # Aucun document pertinent trouvé


def ndcg_at_k(retrieved: list[str], expected: list[str], k: int = 5) -> float:
    """
    Calcule le NDCG@K (Normalized Discounted Cumulative Gain).

    Mesure la qualité du ranking en pénalisant les documents pertinents
    placés loin dans la liste.

    Args:
        retrieved: Liste des IDs de documents retrouvés (ordonnés par score)
        expected: Liste des IDs de documents pertinents
        k: Nombre de résultats à considérer

    Returns:
        Score entre 0 et 1
    """
    def dcg(relevances: list[int], k: int) -> float:
        """Calcule le DCG (Discounted Cumulative Gain)."""
        return sum(
            (2 ** rel - 1) / math.log2(i + 2)
            for i, rel in enumerate(relevances[:k])
        )

    # Relevances pour les documents récupérés
    relevances = [1 if doc_id in expected else 0 for doc_id in retrieved[:k]]

    # DCG idéal (documents pertinents en premier)
    ideal_relevances = sorted(relevances, reverse=True)

    dcg_score = dcg(relevances, k)
    idcg_score = dcg(ideal_relevances, k)

    if idcg_score == 0:
        return 0.0

    return dcg_score / idcg_score


def precision_at_k(retrieved: list[str], expected: list[str], k: int = 5) -> float:
    """
    Calcule la Precision@K.

    Mesure la proportion de documents pertinents parmi les top-K.

    Args:
        retrieved: Liste des IDs de documents retrouvés (ordonnés par score)
        expected: Liste des IDs de documents pertinents
        k: Nombre de résultats à considérer

    Returns:
        Score entre 0 et 1
    """
    if k == 0:
        return 0.0

    top_k = retrieved[:k]
    relevant_in_top_k = len([doc_id for doc_id in top_k if doc_id in expected])

    return relevant_in_top_k / k


def evaluate_query(query: dict, retrieval_fn, k: int = 5) -> dict:
    """
    Évalue une query unique.

    Args:
        query: Dict contenant 'query', 'expected_docs', etc.
        retrieval_fn: Fonction de retrieval qui prend une query et retourne une liste d'IDs
        k: Nombre de résultats à considérer

    Returns:
        Dict avec les métriques
    """
    query_text = query["query"]
    expected_docs = query["expected_docs"]

    # Récupérer les documents
    retrieved_docs = retrieval_fn(query_text, k=k)

    # Calculer les métriques
    metrics = {
        "query_id": query["id"],
        "recall@5": recall_at_k(retrieved_docs, expected_docs, k=5),
        "recall@10": recall_at_k(retrieved_docs, expected_docs, k=10),
        "mrr": mean_reciprocal_rank(retrieved_docs, expected_docs),
        "ndcg@5": ndcg_at_k(retrieved_docs, expected_docs, k=5),
        "precision@5": precision_at_k(retrieved_docs, expected_docs, k=5),
        "retrieved_count": len(retrieved_docs),
        "expected_count": len(expected_docs),
    }

    return metrics


def aggregate_metrics(results: list[dict]) -> dict:
    """
    Agrège les métriques sur toutes les queries.

    Args:
        results: Liste des résultats individuels

    Returns:
        Dict avec moyennes et écarts-types
    """
    if not results:
        return {}

    metrics_keys = ["recall@5", "recall@10", "mrr", "ndcg@5", "precision@5"]
    aggregated = {}

    for key in metrics_keys:
        values = [r[key] for r in results if key in r]
        aggregated[f"{key}_mean"] = sum(values) / len(values) if values else 0.0
        aggregated[f"{key}_min"] = min(values) if values else 0.0
        aggregated[f"{key}_max"] = max(values) if values else 0.0

    return aggregated


def mock_retrieval(query: str, k: int = 5) -> list[str]:
    """
    Fonction de retrieval mock pour tests.

    Dans une vraie implémentation, cela ferait appel à Qdrant + embeddings.

    Args:
        query: Texte de la query
        k: Nombre de résultats à retourner

    Returns:
        Liste d'IDs de documents simulés
    """
    # Simulation simple basée sur des mots-clés
    query_lower = query.lower()

    mock_results = []

    # Mathématiques
    if "triangle" in query_lower or "pythagore" in query_lower:
        mock_results.extend([
            "mathematiques_cinquieme_geometrie_002",
            "mathematiques_cinquieme_geometrie_triangles_001"
        ])
    if "aire" in query_lower or "périmètre" in query_lower:
        mock_results.extend([
            "mathematiques_cinquieme_grandeurs_mesures_001",
            "mathematiques_cinquieme_grandeurs_mesures_002"
        ])
    if "relatif" in query_lower or "additionner" in query_lower:
        mock_results.extend([
            "mathematiques_cinquieme_nombres_calculs_001"
        ])
    if "distributivité" in query_lower or "développer" in query_lower:
        mock_results.extend([
            "mathematiques_cinquieme_calcul_litteral_001"
        ])
    if "parallélogramme" in query_lower or "rectangle" in query_lower:
        mock_results.extend([
            "mathematiques_cinquieme_geometrie_quadrilateres_001"
        ])

    # Français
    if "cod" in query_lower:
        mock_results.extend([
            "francais_cinquieme_grammaire_fonctions_001",
            "francais_cinquieme_grammaire_fonctions_002"
        ])
    if "conjuguer" in query_lower or "présent" in query_lower:
        mock_results.extend([
            "francais_cinquieme_conjugaison_present_001"
        ])
    if "coi" in query_lower:
        mock_results.extend([
            "francais_cinquieme_grammaire_fonctions_002"
        ])

    # Physique-Chimie
    if "eau" in query_lower or "états" in query_lower:
        mock_results.extend([
            "physique_chimie_cinquieme_eau_001"
        ])
    if "circuit" in query_lower or "électrique" in query_lower:
        mock_results.extend([
            "physique_chimie_cinquieme_electricite_001"
        ])

    # SVT
    if "photosynthèse" in query_lower:
        mock_results.extend([
            "svt_cinquieme_vivant_evolution_001"
        ])

    # Dédupliquer et limiter
    seen = set()
    unique_results = []
    for doc_id in mock_results:
        if doc_id not in seen:
            unique_results.append(doc_id)
            seen.add(doc_id)

    return unique_results[:k]


def run_evaluation(test_queries_path: Path, output_path: Path | None = None, k: int = 5):
    """
    Lance l'évaluation complète.

    Args:
        test_queries_path: Chemin vers le fichier de test queries
        output_path: Chemin de sortie pour les métriques (optionnel)
        k: Nombre de résultats à considérer
    """
    rprint("\n[bold cyan]📊 Évaluation RAG - Best Practices 2025[/bold cyan]\n")

    # Charger les test queries
    with open(test_queries_path, "r", encoding="utf-8") as f:
        test_data = json.load(f)

    queries = test_data["queries"]
    targets = test_data.get("metrics_target", {})

    rprint(f"📝 Nombre de queries: {len(queries)}")
    rprint(f"🎯 Objectifs: Recall@5={targets.get('recall@5', 'N/A')}, MRR={targets.get('mrr', 'N/A')}")

    # Évaluer chaque query
    results = []
    for query in queries:
        metrics = evaluate_query(query, mock_retrieval, k=k)
        results.append(metrics)

    # Agréger les métriques
    aggregated = aggregate_metrics(results)

    # Afficher les résultats
    table = Table(title="Métriques par Query")
    table.add_column("Query ID", style="cyan")
    table.add_column("Recall@5", justify="right")
    table.add_column("MRR", justify="right")
    table.add_column("NDCG@5", justify="right")
    table.add_column("Precision@5", justify="right")

    for result in results[:10]:  # Afficher les 10 premières
        table.add_row(
            result["query_id"],
            f"{result['recall@5']:.3f}",
            f"{result['mrr']:.3f}",
            f"{result['ndcg@5']:.3f}",
            f"{result['precision@5']:.3f}"
        )

    console.print(table)

    # Afficher les moyennes
    rprint("\n[bold]Résultats agrégés:[/bold]")
    for key, value in aggregated.items():
        if "_mean" in key:
            metric_name = key.replace("_mean", "")
            target_val = targets.get(metric_name, None)
            status = ""
            if target_val:
                status = " ✓" if value >= target_val else " ✗"
            rprint(f"  • {metric_name:15s}: {value:.3f}{status}")

    # Sauvegarder les résultats
    if output_path:
        output_data = {
            "version": "1.0.0",
            "timestamp": "2025-12-17",
            "test_queries": test_queries_path.name,
            "k": k,
            "aggregated": aggregated,
            "details": results
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dumps(output_data, f, ensure_ascii=False, indent=2)

        rprint(f"\n[green]✓ Résultats sauvegardés: {output_path}[/green]")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Évaluation RAG")
    parser.add_argument("--test-queries", required=True, help="Fichier test queries JSON")
    parser.add_argument("--output", help="Fichier de sortie pour métriques")
    parser.add_argument("--k", type=int, default=5, help="Nombre de résultats top-K")

    args = parser.parse_args()

    run_evaluation(
        test_queries_path=Path(args.test_queries),
        output_path=Path(args.output) if args.output else None,
        k=args.k
    )
