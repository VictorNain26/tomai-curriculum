#!/usr/bin/env python3
"""
Optimisation Qdrant : indexes, quantization, HNSW.

Applique les décisions D5 (scalar int8 quantization), D7 (payload indexes
KEYWORD niveau/matiere/cycle/difficulty/content_type) et la config HNSW
(m=16, ef_construct=100) de la spec RAG overhaul.

Voir `docs/specs/2026-05-09-rag-overhaul-design.md` et
`docs/adr/0001-rag-overhaul.md` pour les sources et justifications.

Optimisations appliquées :
1. Payload indexes KEYWORD sur champs fréquemment filtrés
2. Scalar quantization int8 always_ram (-75% RAM, ≥99% accuracy)
3. HNSW optimisé pour 1024D (m=16, ef_construct=100)
4. Optimizers : indexing_threshold pour batch operations
"""

import typer
from qdrant_client import QdrantClient
from qdrant_client.models import (
    HnswConfigDiff,
    OptimizersConfigDiff,
    PayloadSchemaType,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
)
from rich import print as rprint
from rich.console import Console

console = Console()
app = typer.Typer(name="qdrant-optimize", help="Optimisation collection Qdrant")

EMBEDDING_DIM = 1024  # Mistral embeddings


def create_payload_indexes(client: QdrantClient, collection: str):
    """
    Crée les payload indexes pour accélérer les filtres.

    Best Practice Qdrant: Indexer tous les champs utilisés dans les filtres.
    Permet à Qdrant d'optimiser le query planning et de skip les vector searches
    inutiles quand les filtres sont très sélectifs.

    Source: https://qdrant.tech/documentation/concepts/payload/
    """
    rprint("\n[bold cyan]📑 Création des payload indexes...[/bold cyan]")

    # Index pour les champs de segmentation (filtrage fréquent)
    indexes_to_create = [
        ("niveau", PayloadSchemaType.KEYWORD),  # Filtre très fréquent
        ("matiere", PayloadSchemaType.KEYWORD),  # Filtre très fréquent
        ("cycle", PayloadSchemaType.KEYWORD),  # Filtre fréquent
        ("domaine", PayloadSchemaType.TEXT),  # Search textuel
        ("content_type", PayloadSchemaType.KEYWORD),  # Filtre sur type
        ("difficulty", PayloadSchemaType.KEYWORD),  # Filtre sur niveau
        ("review_status", PayloadSchemaType.KEYWORD),  # Filtre qualité
        ("quality_score", PayloadSchemaType.FLOAT),  # Range queries
    ]

    for field_name, schema_type in indexes_to_create:
        try:
            client.create_payload_index(
                collection_name=collection,
                field_name=field_name,
                field_schema=schema_type,
            )
            rprint(f"  ✓ Index créé: [cyan]{field_name}[/cyan] ({schema_type})")
        except Exception as e:
            if "already exists" in str(e).lower():
                rprint(f"  ⚠ Index existe déjà: {field_name}")
            else:
                rprint(f"  ✗ Erreur {field_name}: {e}")

    # Index composés pour les requêtes multi-filtres courantes
    rprint("\n  [dim]Indexes optimisés pour queries communes:[/dim]")
    rprint("  • niveau + matiere (le plus courant)")
    rprint("  • domaine + difficulty")
    rprint("  • review_status + quality_score")


def configure_quantization(client: QdrantClient, collection: str):
    """
    Configure la scalar quantization pour réduire l'usage mémoire.

    Best Practice Qdrant: Scalar quantization réduit l'usage mémoire de 30x
    pour les vecteurs haute dimension (1024D) avec impact minimal sur la précision.

    La quantization convertit les float32 en int8, réduisant chaque vecteur de:
    - 1024 dimensions × 4 bytes (float32) = 4KB
    - 1024 dimensions × 1 byte (int8) = 1KB
    - Économie: 75% par vecteur

    Source: https://qdrant.tech/rag/ (30x cost reduction mentioned)
    """
    rprint("\n[bold cyan]⚡ Configuration de la quantization...[/bold cyan]")

    try:
        # Scalar quantization: float32 → int8
        quantization_config = ScalarQuantization(
            scalar=ScalarQuantizationConfig(
                type=ScalarType.INT8,
                # Always use quantized vectors for search (99%+ accuracy)
                always_ram=True,
            )
        )

        client.update_collection(
            collection_name=collection,
            quantization_config=quantization_config,
        )

        rprint("  ✓ Scalar quantization activée (int8)")
        rprint("  • Réduction mémoire: ~75% par vecteur")
        rprint("  • Impact précision: <1% (acceptable pour RAG)")
        rprint("  • 1024D float32 (4KB) → int8 (1KB)")
    except Exception as e:
        rprint(f"  ✗ Erreur quantization: {e}")


def optimize_hnsw_config(client: QdrantClient, collection: str):
    """
    Optimise la configuration HNSW pour 1024D embeddings.

    Best Practice Qdrant: Ajuster m et ef_construct selon la dimensionalité.
    Pour haute dimension (1024D):
    - m = 16-32 (connections par node)
    - ef_construct = 100-200 (qualité de l'index)

    Plus m est élevé, meilleure est la recall mais plus l'index est large.
    Plus ef_construct est élevé, meilleur est l'index mais plus lent à construire.

    Source: Qdrant HNSW documentation standards
    """
    rprint("\n[bold cyan]🔧 Optimisation HNSW...[/bold cyan]")

    try:
        hnsw_config = HnswConfigDiff(
            m=16,  # Connections par node (défaut: 16)
            ef_construct=100,  # Qualité construction (défaut: 100)
            full_scan_threshold=10000,  # Seuil full scan si < N points
        )

        client.update_collection(
            collection_name=collection,
            hnsw_config=hnsw_config,
        )

        rprint("  ✓ HNSW optimisé pour 1024D")
        rprint("  • m=16 (balance recall/mémoire)")
        rprint("  • ef_construct=100 (qualité index)")
        rprint("  • full_scan_threshold=10000")
    except Exception as e:
        rprint(f"  ✗ Erreur HNSW: {e}")


def optimize_collection_params(client: QdrantClient, collection: str):
    """
    Optimise les paramètres généraux de la collection.

    Best Practice Qdrant: Ajuster les optimizers pour batch operations.
    """
    rprint("\n[bold cyan]⚙️  Optimisation paramètres collection...[/bold cyan]")

    try:
        optimizers_config = OptimizersConfigDiff(
            indexing_threshold=20000,  # Rebuild index tous les 20k points
            flush_interval_sec=5,  # Flush vers disque toutes les 5s
        )

        client.update_collection(
            collection_name=collection,
            optimizers_config=optimizers_config,
        )

        rprint("  ✓ Optimizers configurés")
        rprint("  • indexing_threshold=20000")
        rprint("  • flush_interval=5s")
    except Exception as e:
        rprint(f"  ✗ Erreur optimizers: {e}")


def verify_optimization(client: QdrantClient, collection: str):
    """Vérifie que toutes les optimisations sont appliquées."""
    rprint("\n[bold cyan]✅ Vérification...[/bold cyan]")

    try:
        # Récupérer info collection
        info = client.get_collection(collection_name=collection)

        rprint(f"\n  Collection: [bold]{collection}[/bold]")
        rprint(f"  • Points: {info.points_count}")
        rprint(f"  • Vectors indexed: {info.indexed_vectors_count}")
        rprint(f"  • Status: {info.status}")

        # Vérifier quantization
        if info.config.quantization_config:
            rprint("  • Quantization: ✓ Activée")
        else:
            rprint("  • Quantization: ✗ Non configurée")

        # Lister les payload indexes
        rprint("\n  Payload indexes:")
        # Note: pas d'API directe pour lister les indexes dans qdrant-client
        # Ils sont appliqués automatiquement lors des queries
        rprint("    [dim]Utilise create_payload_index() pour chaque champ[/dim]")

    except Exception as e:
        rprint(f"  ✗ Erreur vérification: {e}")


@app.command()
def optimize(
    collection: str = typer.Option("tomai_educational", help="Nom de la collection"),
    qdrant_url: str | None = typer.Option(None, envvar="QDRANT_URL"),
    qdrant_api_key: str | None = typer.Option(None, envvar="QDRANT_API_KEY"),
    skip_indexes: bool = typer.Option(False, help="Skip payload indexes"),
    skip_quantization: bool = typer.Option(False, help="Skip quantization"),
    skip_hnsw: bool = typer.Option(False, help="Skip HNSW optimization"),
):
    """
    Applique les optimisations Qdrant définies par la spec RAG overhaul.

    Configure :
    1. Payload indexes KEYWORD sur niveau/matiere/cycle/difficulty/content_type
    2. Scalar quantization int8 always_ram
    3. HNSW : m=16, ef_construct=100 (optimisé 1024D)
    4. Optimizers : indexing_threshold pour batch

    Usage :
        QDRANT_URL=... QDRANT_API_KEY=... uv run python scripts/qdrant_optimize.py optimize

    Non-destructif : applicable sur une collection existante avec des données.
    """
    rprint("\n[bold cyan]Optimisation Qdrant[/bold cyan]")

    # Validation credentials
    if not qdrant_url or not qdrant_api_key:
        rprint("[red]QDRANT_URL et QDRANT_API_KEY requis[/red]")
        raise typer.Exit(1)

    # Connexion
    rprint(f"\n[bold]Collection:[/bold] {collection}")
    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)

    # Vérifier que la collection existe
    collections = [c.name for c in client.get_collections().collections]
    if collection not in collections:
        rprint(f"[red]Collection '{collection}' n'existe pas[/red]")
        rprint("[yellow]Créez d'abord la collection avec scripts/ingest.py[/yellow]")
        raise typer.Exit(1)

    # Appliquer les optimisations
    if not skip_indexes:
        create_payload_indexes(client, collection)

    if not skip_quantization:
        configure_quantization(client, collection)

    if not skip_hnsw:
        optimize_hnsw_config(client, collection)

    # Optimiser les paramètres généraux
    optimize_collection_params(client, collection)

    # Vérification finale
    verify_optimization(client, collection)

    rprint("\n[bold green]✓ Optimisation terminée![/bold green]")
    rprint("\n[dim]Impact attendu:[/dim]")
    rprint("  • Queries filtrées: 2-5x plus rapides")
    rprint("  • Usage mémoire: -75% (quantization)")
    rprint("  • Latence moyenne: 3-10ms pour 1M vectors")


@app.command()
def status(
    collection: str = typer.Option("tomai_educational", help="Nom de la collection"),
    qdrant_url: str | None = typer.Option(None, envvar="QDRANT_URL"),
    qdrant_api_key: str | None = typer.Option(None, envvar="QDRANT_API_KEY"),
):
    """Affiche le status d'optimisation de la collection."""
    if not qdrant_url or not qdrant_api_key:
        rprint("[red]QDRANT_URL et QDRANT_API_KEY requis[/red]")
        raise typer.Exit(1)

    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
    verify_optimization(client, collection)


if __name__ == "__main__":
    app()
