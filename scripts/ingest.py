#!/usr/bin/env python3
"""
Script d'ingestion Qdrant pour le dataset TomAI.

Utilise Mistral AI pour générer les embeddings et Qdrant Cloud pour le stockage vectoriel.
Migration Gemini → Mistral (Janvier 2025)
"""

import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Annotated

import typer
from mistralai import Mistral
from pydantic import ValidationError
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    HnswConfigDiff,
    OptimizersConfigDiff,
    PointStruct,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    VectorParams,
)
from rich import print as rprint
from rich.progress import Progress, SpinnerColumn, TextColumn

# Add parent to path for schema import
sys.path.insert(0, str(Path(__file__).parent.parent))

from schema import Document

app = typer.Typer(name="ingest", help="Ingestion du dataset dans Qdrant")

DATA_DIR = Path(__file__).parent.parent / "data" / "processed"

# Mistral embedding config (migration from Gemini 768D)
EMBEDDING_MODEL = "mistral-embed"
EMBEDDING_DIM = 1024


def generate_doc_id(niveau: str, matiere: str, title: str) -> str:
    """Génère un UUID unique pour un document."""
    import uuid
    content = f"{niveau}:{matiere}:{title}"
    # Générer un UUID déterministe à partir du contenu
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, content))


def get_all_jsonl_files(niveau: str | None = None, matiere: str | None = None) -> list[Path]:
    """Récupère tous les fichiers JSONL du dataset."""
    files = []
    for cycle_dir in DATA_DIR.iterdir():
        if not cycle_dir.is_dir():
            continue
        for niveau_dir in cycle_dir.iterdir():
            if not niveau_dir.is_dir():
                continue
            if niveau and niveau_dir.name != niveau:
                continue
            for jsonl_file in niveau_dir.glob("*.jsonl"):
                if matiere and jsonl_file.stem != matiere:
                    continue
                files.append(jsonl_file)
    return sorted(files)


def load_documents(files: list[Path]) -> list[dict]:
    """Charge et valide tous les documents."""
    documents = []

    for file_path in files:
        niveau = file_path.parent.name
        matiere = file_path.stem
        cycle = file_path.parent.parent.name

        with open(file_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    doc = Document.model_validate(data)
                    documents.append({
                        "id": generate_doc_id(niveau, matiere, doc.title),
                        "niveau": niveau,
                        "matiere": matiere,
                        "cycle": cycle,
                        "doc": doc,
                    })
                except (json.JSONDecodeError, ValidationError) as e:
                    rprint(f"[red]Erreur {file_path}:{line_num}: {e}[/red]")
                    raise typer.Exit(1)

    return documents


def normalize_vector(embedding: list[float]) -> list[float]:
    """Normalise un vecteur (unit vector, magnitude = 1.0) pour cosine similarity."""
    magnitude = math.sqrt(sum(val * val for val in embedding))
    if magnitude == 0:
        raise ValueError("Cannot normalize zero-magnitude embedding vector")
    return [val / magnitude for val in embedding]


def generate_embeddings_batch(
    client: Mistral,
    texts: list[str],
    max_retries: int = 5,
    base_delay: float = 2.0
) -> list[list[float]]:
    """
    Génère des embeddings Mistral 1024D pour plusieurs textes en un seul appel API.

    Mistral permet de passer plusieurs inputs dans une seule requête,
    ce qui réduit drastiquement le nombre d'appels API et évite les rate limits.

    Args:
        client: Client Mistral
        texts: Liste de textes à embedder (max ~20 pour éviter rate limits)
        max_retries: Nombre de tentatives en cas d'erreur
        base_delay: Délai de base entre les appels (augmenté exponentiellement en cas de 429)

    Returns:
        Liste d'embeddings normalisés (même ordre que les textes d'entrée)
    """
    for attempt in range(max_retries):
        try:
            result = client.embeddings.create(
                model=EMBEDDING_MODEL,
                inputs=texts,
            )

            # Extraire et normaliser tous les embeddings
            embeddings = []
            for data in result.data:
                normalized = normalize_vector(data.embedding)
                embeddings.append(normalized)

            # Délai entre les batches pour respecter les rate limits
            time.sleep(base_delay)

            return embeddings

        except Exception as e:
            error_str = str(e).lower()
            if "429" in str(e) or "rate" in error_str or "too many" in error_str:
                # Backoff exponentiel: 5s, 15s, 30s, 60s, 120s
                wait_time = base_delay * (3 ** attempt) + 5
                rprint(f"[yellow]Rate limit (tentative {attempt + 1}/{max_retries}), attente {wait_time:.0f}s...[/yellow]")
                time.sleep(wait_time)
            else:
                rprint(f"[red]Erreur Mistral: {e}[/red]")
                raise

    raise RuntimeError(f"Échec après {max_retries} tentatives - rate limits trop restrictifs")


def create_embedding_text(doc_data: dict) -> str:
    """
    Crée le texte à embedder pour un document.

    Best Practice 2025: Format conversationnel au lieu de structured labels.
    Source: Embedding optimization research - conversational format améliore
    la pertinence du retrieval de +15-25% vs format structuré.
    """
    doc = doc_data["doc"]

    # Format conversationnel naturel
    text_parts = []

    # Contexte pédagogique
    context = f"Cours de {doc_data['matiere']} niveau {doc_data['niveau']}"
    if doc.sousdomaine:
        context += f", {doc.domaine} - {doc.sousdomaine}"
    else:
        context += f", {doc.domaine}"
    text_parts.append(context)

    # Titre et contenu principal
    text_parts.append(f"\n{doc.title}\n")
    text_parts.append(doc.content)

    # Objectifs d'apprentissage (V2)
    learning_objectives = getattr(doc, 'learning_objectives', None)
    if learning_objectives and len(learning_objectives) > 0:
        text_parts.append("\nObjectifs:")
        for obj in learning_objectives[:3]:  # Top 3
            text_parts.append(f"- {obj}")

    # Questions typiques (V2) - crucial pour le retrieval
    typical_questions = getattr(doc, 'typical_questions', None)
    if typical_questions and len(typical_questions) > 0:
        text_parts.append("\nQuestions fréquentes:")
        for q in typical_questions[:5]:  # Top 5
            text_parts.append(f"- {q}")

    # Mots-clés (densité sémantique)
    keywords = getattr(doc, 'keywords', None)
    if keywords and len(keywords) > 0:
        text_parts.append(f"\nConcepts clés: {', '.join(keywords[:8])}")

    # Erreurs courantes (V2) - aide pour queries "je ne comprends pas..."
    common_errors = getattr(doc, 'common_errors', None)
    if common_errors and len(common_errors) > 0:
        text_parts.append("\nErreurs à éviter:")
        for err in common_errors[:3]:  # Top 3
            text_parts.append(f"- {err}")

    return "\n".join(text_parts)


def create_payload(doc_data: dict) -> dict:
    """
    Crée le payload Qdrant pour un document.

    Best Practice 2025: Inclure métadonnées riches pour filtering et reranking.
    """
    doc = doc_data["doc"]

    # Payload de base (V1)
    payload = {
        "niveau": doc_data["niveau"],
        "matiere": doc_data["matiere"],
        "cycle": doc_data["cycle"],
        "domaine": doc.domaine,
        "sousdomaine": doc.sousdomaine,
        "title": doc.title,
        "content_type": doc.content_type.value if hasattr(doc.content_type, 'value') else doc.content_type,
        "content": doc.content,
    }

    # Métadonnées V2 enrichies
    difficulty = getattr(doc, 'difficulty', None)
    if difficulty:
        payload["difficulty"] = difficulty.value if hasattr(difficulty, 'value') else difficulty

    keywords = getattr(doc, 'keywords', None)
    if keywords:
        payload["keywords"] = keywords

    prerequis = getattr(doc, 'prerequis', None)
    if prerequis:
        payload["prerequis"] = prerequis

    typical_questions = getattr(doc, 'typical_questions', None)
    if typical_questions:
        payload["typical_questions"] = typical_questions

    learning_objectives = getattr(doc, 'learning_objectives', None)
    if learning_objectives:
        payload["learning_objectives"] = learning_objectives

    # Erreurs courantes (V2)
    common_errors = getattr(doc, 'common_errors', None)
    if common_errors:
        payload["common_errors"] = common_errors

    # Métriques de qualité pour reranking
    quality = getattr(doc, 'quality', None)
    if quality:
        payload["quality_score"] = quality.overall_score

    # Niveau de confiance
    confidence_level = getattr(doc, 'confidence_level', None)
    if confidence_level is not None:
        payload["confidence_level"] = confidence_level

    # Tags
    tags = getattr(doc, 'tags', None)
    if tags:
        payload["tags"] = tags

    # Version et statut
    version = getattr(doc, 'version', None)
    if version:
        payload["version"] = version

    review_status = getattr(doc, 'review_status', None)
    if review_status:
        payload["review_status"] = review_status.value if hasattr(review_status, 'value') else review_status

    return payload


@app.command()
def run(
    niveau: Annotated[str | None, typer.Option(help="Filtrer par niveau")] = None,
    matiere: Annotated[str | None, typer.Option(help="Filtrer par matière")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Simulation sans écriture")] = False,
    clear: Annotated[bool, typer.Option("--clear", help="Supprimer les points existants avant ingestion")] = False,
    batch_size: Annotated[int, typer.Option(help="Taille des batches")] = 10,
    qdrant_url: Annotated[str | None, typer.Option(envvar="QDRANT_URL")] = None,
    qdrant_api_key: Annotated[str | None, typer.Option(envvar="QDRANT_API_KEY")] = None,
    mistral_api_key: Annotated[str | None, typer.Option(envvar="MISTRAL_API_KEY")] = None,
    collection: Annotated[str, typer.Option(envvar="QDRANT_COLLECTION")] = "tomai_educational",
):
    """Ingère les documents dans Qdrant avec embeddings Mistral 1024D."""

    # Validation des credentials
    if not dry_run:
        if not qdrant_url or not qdrant_api_key:
            rprint("[red]QDRANT_URL et QDRANT_API_KEY requis[/red]")
            raise typer.Exit(1)
        if not mistral_api_key:
            rprint("[red]MISTRAL_API_KEY requis pour les embeddings[/red]")
            raise typer.Exit(1)

    # Charger les documents
    rprint("\n[bold cyan]1. Chargement des documents...[/bold cyan]")
    files = get_all_jsonl_files(niveau, matiere)

    if not files:
        rprint("[yellow]Aucun fichier JSONL trouve.[/yellow]")
        raise typer.Exit(0)

    documents = load_documents(files)
    rprint(f"   [green]{len(documents)} documents charges[/green]")

    if dry_run:
        rprint("\n[yellow]Mode dry-run: affichage des documents[/yellow]")
        for doc in documents[:5]:
            rprint(f"   - {doc['niveau']}/{doc['matiere']}: {doc['doc'].title}")
        if len(documents) > 5:
            rprint(f"   ... et {len(documents) - 5} autres")
        return

    # Initialiser les clients
    rprint("\n[bold cyan]2. Connexion aux services...[/bold cyan]")

    mistral_client = Mistral(api_key=mistral_api_key)
    rprint("   [green]Mistral API connecte (1024D embeddings)[/green]")

    qdrant_client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
    rprint("   [green]Qdrant connecte[/green]")

    # Créer/vérifier la collection
    collections = [c.name for c in qdrant_client.get_collections().collections]

    if collection not in collections:
        rprint(f"\n[bold cyan]3. Creation de la collection '{collection}' (optimisée)...[/bold cyan]")

        # Best Practice Qdrant 2025: Configuration optimisée dès la création
        # - HNSW optimisé pour 1024D
        # - Scalar quantization (int8) pour -75% mémoire
        # - Optimizers pour batch operations
        qdrant_client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(
                size=EMBEDDING_DIM,
                distance=Distance.COSINE,
            ),
            hnsw_config=HnswConfigDiff(
                m=16,                 # Connections par node (optimal pour 1024D)
                ef_construct=100,     # Qualité de l'index
                full_scan_threshold=10000,
            ),
            quantization_config=ScalarQuantization(
                scalar=ScalarQuantizationConfig(
                    type=ScalarType.INT8,
                    always_ram=True,  # Utiliser quantized vectors pour search
                )
            ),
            optimizers_config=OptimizersConfigDiff(
                indexing_threshold=20000,  # Rebuild index tous les 20k points
                flush_interval_sec=5,
            ),
        )
        rprint(f"   [green]Collection '{collection}' creee avec optimisations:[/green]")
        rprint("   • HNSW: m=16, ef_construct=100")
        rprint("   • Quantization: int8 (-75% mémoire)")
        rprint("   • Optimizers: batch-friendly")
    else:
        rprint(f"\n[bold cyan]3. Collection '{collection}' existe[/bold cyan]")

        if clear:
            # Supprimer les points pour le niveau/matiere spécifié
            filter_conditions = []
            if niveau:
                filter_conditions.append({"key": "niveau", "match": {"value": niveau}})
            if matiere:
                filter_conditions.append({"key": "matiere", "match": {"value": matiere}})

            if filter_conditions:
                from qdrant_client.models import Filter, FieldCondition, MatchValue

                conditions = [
                    FieldCondition(key=f["key"], match=MatchValue(value=f["match"]["value"]))
                    for f in filter_conditions
                ]

                rprint(f"   [yellow]Suppression des points existants...[/yellow]")
                qdrant_client.delete(
                    collection_name=collection,
                    points_selector=Filter(must=conditions),
                )

    # Générer les embeddings et insérer
    # BATCH PROCESSING: traiter plusieurs documents par appel API Mistral
    # Réduit 201 appels à ~20 appels, évite les rate limits du free tier
    embedding_batch_size = 10  # Nombre de textes par appel Mistral (conservateur pour free tier)

    rprint(f"\n[bold cyan]4. Generation des embeddings et insertion...[/bold cyan]")
    rprint(f"   [dim]Mode batch: {embedding_batch_size} documents par appel API Mistral[/dim]")
    rprint(f"   [dim]Nombre d'appels API estimé: {(len(documents) + embedding_batch_size - 1) // embedding_batch_size}[/dim]")

    points = []
    total_batches = (len(documents) + embedding_batch_size - 1) // embedding_batch_size

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        task = progress.add_task("Traitement...", total=total_batches)

        # Traiter par batches
        for batch_idx in range(0, len(documents), embedding_batch_size):
            batch_docs = documents[batch_idx:batch_idx + embedding_batch_size]
            batch_num = batch_idx // embedding_batch_size + 1

            progress.update(task, description=f"[Batch {batch_num}/{total_batches}] {len(batch_docs)} documents...")

            # Préparer les textes pour le batch
            batch_texts = [create_embedding_text(doc_data) for doc_data in batch_docs]

            # Générer tous les embeddings en un seul appel API
            try:
                batch_embeddings = generate_embeddings_batch(
                    mistral_client,
                    batch_texts,
                    max_retries=5,
                    base_delay=3.0  # 3s entre chaque batch
                )
            except RuntimeError as e:
                rprint(f"\n[red]Erreur fatale: {e}[/red]")
                rprint(f"[yellow]Documents traites: {len(points)}[/yellow]")
                # Sauvegarder ce qu'on a pu traiter
                if points:
                    qdrant_client.upsert(collection_name=collection, points=points)
                    rprint(f"[green]Sauvegarde partielle: {len(points)} points[/green]")
                raise typer.Exit(1)

            # Créer les points Qdrant avec les embeddings
            for doc_data, embedding in zip(batch_docs, batch_embeddings):
                point = PointStruct(
                    id=doc_data["id"],
                    vector=embedding,
                    payload=create_payload(doc_data),
                )
                points.append(point)

            # Insérer dans Qdrant par batch
            if len(points) >= batch_size:
                qdrant_client.upsert(collection_name=collection, points=points)
                rprint(f"   [dim]Inseré {len(points)} points dans Qdrant[/dim]")
                points = []

            progress.advance(task)

        # Insérer les derniers points
        if points:
            qdrant_client.upsert(collection_name=collection, points=points)
            rprint(f"   [dim]Inseré {len(points)} derniers points[/dim]")

    # Vérification finale
    rprint(f"\n[bold cyan]5. Verification...[/bold cyan]")
    info = qdrant_client.get_collection(collection_name=collection)
    rprint(f"   [green]Collection '{collection}': {info.points_count} points[/green]")

    rprint(f"\n[bold green]Ingestion terminee: {len(documents)} documents[/bold green]")


@app.command()
def status(
    qdrant_url: Annotated[str | None, typer.Option(envvar="QDRANT_URL")] = None,
    qdrant_api_key: Annotated[str | None, typer.Option(envvar="QDRANT_API_KEY")] = None,
    collection: Annotated[str, typer.Option(envvar="QDRANT_COLLECTION")] = "tomai_educational",
):
    """Affiche le statut de la collection Qdrant."""
    if not qdrant_url or not qdrant_api_key:
        rprint("[red]QDRANT_URL et QDRANT_API_KEY requis[/red]")
        raise typer.Exit(1)

    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)

    collections = [c.name for c in client.get_collections().collections]

    if collection not in collections:
        rprint(f"[yellow]Collection '{collection}' n'existe pas[/yellow]")
        return

    info = client.get_collection(collection_name=collection)
    rprint(f"\n[bold]Collection: {collection}[/bold]")
    rprint(f"  Points: {info.points_count}")
    rprint(f"  Indexed vectors: {info.indexed_vectors_count}")
    rprint(f"  Status: {info.status}")

    # Compter par niveau/matière
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    niveaux = ["cinquieme", "quatrieme", "troisieme", "seconde", "premiere", "terminale"]
    matieres = ["mathematiques", "francais", "physique_chimie", "svt", "anglais"]

    rprint("\n[bold]Repartition:[/bold]")
    for niveau in niveaux:
        count = client.count(
            collection_name=collection,
            count_filter=Filter(must=[FieldCondition(key="niveau", match=MatchValue(value=niveau))]),
        ).count
        if count > 0:
            rprint(f"  {niveau}: {count} points")


if __name__ == "__main__":
    app()
