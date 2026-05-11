#!/usr/bin/env python3
"""
Pipeline d'ingestion Qdrant pour le dataset TomAI — 3 phases découplées.

Architecture refactor B (mai 2026) :
- `embed` : charge JSONL, calcule content_hash, génère embeddings Mistral
  par batch=50, cache localement par (model_version, content_hash).
- `upsert` : lit le cache, upsert vers Qdrant. ID = uuid5(content_hash).
  Si le point existe déjà avec le même content_hash, set_payload sans
  recompute du vecteur (gain coût Mistral).
- `prune` : supprime de Qdrant les points dont (niveau, matiere, title) n'existe
  plus dans les JSONL locaux (orphelins).
- `run` : orchestrateur embed → upsert → prune.
- `status` : statistiques de la collection.

Les helpers (hashing, cache, payload, Qdrant ops) sont dans `ingest_lib.py`
pour respecter la limite 400 lignes/fichier du monorepo Tom.

Sources :
- https://docs.mistral.ai/api (embeddings, prompt_cache_key)
- https://qdrant.tech/articles/sparse-vectors (hybrid search Qdrant)
- https://qdrant.tech/documentation/concepts/indexing/ (payload indexes)
"""

import sys
from pathlib import Path
from typing import Annotated

# Forcer stdout/stderr en UTF-8 sur Windows (cp1252 par défaut ne supporte pas ✓ → etc.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

import typer  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from mistralai import Mistral  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client.models import (  # noqa: E402
    FieldCondition,
    Filter,
    HasIdCondition,
    MatchValue,
    PointStruct,
)
from rich import print as rprint  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.progress import Progress, SpinnerColumn, TextColumn  # noqa: E402

from schema.document import Matiere, NiveauCollege, NiveauLycee  # noqa: E402
from scripts.ingest_lib import (  # noqa: E402
    COLLECTION_DEFAULT,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MODEL,
    _cache_path,
    append_to_cache,
    compute_content_hash,
    create_embedding_text,
    create_payload,
    doc_id_from_hash,
    fetch_existing_hashes,
    find_orphans,
    generate_embeddings_batch,
    load_documents,
    load_embedding_cache,
    normalize_vector,
)
from scripts.utils import get_all_jsonl_files  # noqa: E402

# Re-exports pour rétrocompat avec les tests qui importent depuis scripts.ingest.
# Voir tests/test_ingest_pipeline.py.
__all__ = [
    "app",
    "compute_content_hash",
    "doc_id_from_hash",
    "normalize_vector",
    "load_documents",
    "load_embedding_cache",
    "append_to_cache",
    "create_embedding_text",
    "generate_embeddings_batch",
    "create_payload",
    "fetch_existing_hashes",
    "find_orphans",
]

# Alias historique (avant Phase 4, ces fonctions étaient privées dans ingest.py).
_fetch_existing_hashes = fetch_existing_hashes
_find_orphans = find_orphans

load_dotenv()

app = typer.Typer(name="ingest", help="Pipeline d'ingestion Qdrant 3 phases")
console = Console()


# =============================================================================
# Commands : embed
# =============================================================================


@app.command()
def embed(
    niveau: Annotated[str | None, typer.Option(help="Filtrer par niveau")] = None,
    matiere: Annotated[str | None, typer.Option(help="Filtrer par matière")] = None,
    mistral_api_key: Annotated[str | None, typer.Option(envvar="MISTRAL_API_KEY")] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Ignorer le cache (re-embed tout)")
    ] = False,
):
    """
    Phase 1 : génère les embeddings et les écrit dans le cache local.

    Idempotent : un document déjà en cache (même content_hash) n'est pas
    re-embeddé. Coût Mistral épargné sur les re-runs.
    """
    if not mistral_api_key:
        rprint("[red]MISTRAL_API_KEY requis[/red]")
        raise typer.Exit(1)

    rprint("\n[bold cyan]Phase 1 : embeddings[/bold cyan]")
    files = get_all_jsonl_files(niveau, matiere)
    if not files:
        rprint("[yellow]Aucun fichier JSONL trouvé.[/yellow]")
        raise typer.Exit(0)

    documents = load_documents(files)
    rprint(f"   {len(documents)} documents chargés")

    cache = {} if force else load_embedding_cache()
    if cache:
        rprint(f"   [dim]{len(cache)} vecteurs déjà en cache[/dim]")

    to_embed = [d for d in documents if d["content_hash"] not in cache]
    if not to_embed:
        rprint("   [green]✓ Tous les vecteurs sont déjà en cache, rien à faire[/green]")
        return

    rprint(f"   {len(to_embed)} documents à embedder (batch={EMBEDDING_BATCH_SIZE})")

    client = Mistral(api_key=mistral_api_key)
    total_batches = (len(to_embed) + EMBEDDING_BATCH_SIZE - 1) // EMBEDDING_BATCH_SIZE

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        task = progress.add_task("Embedding...", total=total_batches)

        for batch_idx in range(0, len(to_embed), EMBEDDING_BATCH_SIZE):
            batch = to_embed[batch_idx : batch_idx + EMBEDDING_BATCH_SIZE]
            batch_num = batch_idx // EMBEDDING_BATCH_SIZE + 1
            progress.update(
                task, description=f"[Batch {batch_num}/{total_batches}] {len(batch)} docs..."
            )

            texts = [create_embedding_text(d) for d in batch]
            vectors = generate_embeddings_batch(client, texts)

            items = [(d["content_hash"], v) for d, v in zip(batch, vectors, strict=True)]
            append_to_cache(items)
            progress.advance(task)

    rprint(f"\n[green]✓ Embeddings écrits dans {_cache_path(EMBEDDING_MODEL)}[/green]")


# =============================================================================
# Commands : upsert
# =============================================================================


@app.command()
def upsert(
    niveau: Annotated[str | None, typer.Option(help="Filtrer par niveau")] = None,
    matiere: Annotated[str | None, typer.Option(help="Filtrer par matière")] = None,
    qdrant_url: Annotated[str | None, typer.Option(envvar="QDRANT_URL")] = None,
    qdrant_api_key: Annotated[str | None, typer.Option(envvar="QDRANT_API_KEY")] = None,
    collection: Annotated[str, typer.Option(envvar="QDRANT_COLLECTION")] = COLLECTION_DEFAULT,
    batch_size: Annotated[int, typer.Option(help="Taille des batches d'upsert")] = 100,
):
    """
    Phase 2 : upsert vers Qdrant depuis le cache embeddings.

    Pour chaque document, si un point Qdrant existe déjà avec le même
    content_hash dans le payload, on fait set_payload sans toucher au vecteur
    (économie de bande passante, pas de re-build d'index inutile).

    Pré-requis : la collection doit déjà exister (`migrate_collection.py`).
    """
    if not qdrant_url or not qdrant_api_key:
        rprint("[red]QDRANT_URL et QDRANT_API_KEY requis[/red]")
        raise typer.Exit(1)

    rprint(f"\n[bold cyan]Phase 2 : upsert vers Qdrant ({collection})[/bold cyan]")
    files = get_all_jsonl_files(niveau, matiere)
    if not files:
        rprint("[yellow]Aucun fichier JSONL trouvé.[/yellow]")
        raise typer.Exit(0)

    documents = load_documents(files)
    cache = load_embedding_cache()

    missing = [d for d in documents if d["content_hash"] not in cache]
    if missing:
        rprint(
            f"[red]✗ {len(missing)} documents sans embedding en cache. "
            f"Lancer `ingest embed` d'abord.[/red]"
        )
        raise typer.Exit(1)

    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
    if not client.collection_exists(collection):
        rprint(
            f"[red]✗ Collection {collection!r} introuvable. "
            f"Lancer `migrate_collection.py` d'abord.[/red]"
        )
        raise typer.Exit(1)

    existing_hashes = fetch_existing_hashes(client, collection, [d["id"] for d in documents])

    upserted = 0
    payload_only_updated = 0
    points_to_upsert: list[PointStruct] = []

    for doc_data in documents:
        point_id = doc_data["id"]
        payload = create_payload(doc_data)

        if existing_hashes.get(point_id) == doc_data["content_hash"]:
            client.set_payload(
                collection_name=collection,
                payload=payload,
                points=[point_id],
            )
            payload_only_updated += 1
            continue

        vector = cache[doc_data["content_hash"]]
        points_to_upsert.append(PointStruct(id=point_id, vector=vector, payload=payload))
        upserted += 1

        if len(points_to_upsert) >= batch_size:
            client.upsert(collection_name=collection, points=points_to_upsert)
            points_to_upsert = []

    if points_to_upsert:
        client.upsert(collection_name=collection, points=points_to_upsert)

    rprint(f"   [green]✓ {upserted} points upsertés (vector + payload)[/green]")
    rprint(f"   [dim]{payload_only_updated} payloads mis à jour (vector inchangé)[/dim]")


# =============================================================================
# Commands : prune
# =============================================================================


@app.command()
def prune(
    qdrant_url: Annotated[str | None, typer.Option(envvar="QDRANT_URL")] = None,
    qdrant_api_key: Annotated[str | None, typer.Option(envvar="QDRANT_API_KEY")] = None,
    collection: Annotated[str, typer.Option(envvar="QDRANT_COLLECTION")] = COLLECTION_DEFAULT,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Lister les orphelins sans supprimer")
    ] = False,
):
    """
    Phase 3 : supprime de Qdrant les points dont (niveau, matiere, title) n'existe
    plus dans les JSONL locaux.

    Sécurité : opère uniquement sur les points dont le payload comporte
    niveau ET matiere ET title — ne touche pas aux points "hors curriculum".
    """
    if not qdrant_url or not qdrant_api_key:
        rprint("[red]QDRANT_URL et QDRANT_API_KEY requis[/red]")
        raise typer.Exit(1)

    rprint(f"\n[bold cyan]Phase 3 : prune orphelins Qdrant ({collection})[/bold cyan]")

    files = get_all_jsonl_files()
    documents = load_documents(files)
    current_ids = {d["id"] for d in documents}
    rprint(f"   {len(current_ids)} points attendus dans Qdrant")

    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
    if not client.collection_exists(collection):
        rprint(f"[red]✗ Collection {collection!r} introuvable.[/red]")
        raise typer.Exit(1)

    orphans = find_orphans(client, collection, current_ids)
    if not orphans:
        rprint("   [green]✓ Aucun orphelin détecté[/green]")
        return

    rprint(f"   [yellow]{len(orphans)} orphelins à supprimer[/yellow]")
    if dry_run:
        for orphan in orphans[:10]:
            rprint(f"     - {orphan}")
        if len(orphans) > 10:
            rprint(f"     ... et {len(orphans) - 10} autres")
        rprint("\n[yellow]Mode dry-run : aucune suppression[/yellow]")
        return

    client.delete(
        collection_name=collection,
        points_selector=Filter(must=[HasIdCondition(has_id=orphans)]),
    )
    rprint(f"   [green]✓ {len(orphans)} orphelins supprimés[/green]")


# =============================================================================
# Commands : run (orchestrator) + status
# =============================================================================


@app.command()
def run(
    niveau: Annotated[str | None, typer.Option(help="Filtrer par niveau")] = None,
    matiere: Annotated[str | None, typer.Option(help="Filtrer par matière")] = None,
    qdrant_url: Annotated[str | None, typer.Option(envvar="QDRANT_URL")] = None,
    qdrant_api_key: Annotated[str | None, typer.Option(envvar="QDRANT_API_KEY")] = None,
    mistral_api_key: Annotated[str | None, typer.Option(envvar="MISTRAL_API_KEY")] = None,
    collection: Annotated[str, typer.Option(envvar="QDRANT_COLLECTION")] = COLLECTION_DEFAULT,
    skip_prune: Annotated[
        bool, typer.Option("--skip-prune", help="Ne pas pruner les orphelins")
    ] = False,
):
    """Orchestrateur : embed -> upsert -> prune (sequentiel, idempotent)."""
    embed(
        niveau=niveau,
        matiere=matiere,
        mistral_api_key=mistral_api_key,
        force=False,
    )
    upsert(
        niveau=niveau,
        matiere=matiere,
        qdrant_url=qdrant_url,
        qdrant_api_key=qdrant_api_key,
        collection=collection,
        batch_size=100,
    )
    if not skip_prune and not niveau and not matiere:
        # Prune uniquement quand on traite TOUT le dataset (sinon ça supprime
        # à tort les points hors du filtre actuel)
        prune(
            qdrant_url=qdrant_url,
            qdrant_api_key=qdrant_api_key,
            collection=collection,
            dry_run=False,
        )


@app.command()
def status(
    qdrant_url: Annotated[str | None, typer.Option(envvar="QDRANT_URL")] = None,
    qdrant_api_key: Annotated[str | None, typer.Option(envvar="QDRANT_API_KEY")] = None,
    collection: Annotated[str, typer.Option(envvar="QDRANT_COLLECTION")] = COLLECTION_DEFAULT,
):
    """Affiche le statut de la collection Qdrant : points, répartition niveau/matière."""
    if not qdrant_url or not qdrant_api_key:
        rprint("[red]QDRANT_URL et QDRANT_API_KEY requis[/red]")
        raise typer.Exit(1)

    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)

    if not client.collection_exists(collection):
        rprint(f"[yellow]Collection {collection!r} n'existe pas[/yellow]")
        return

    info = client.get_collection(collection_name=collection)
    rprint(f"\n[bold]Collection: {collection}[/bold]")
    rprint(f"  Points: {info.points_count}")
    rprint(f"  Indexed vectors: {info.indexed_vectors_count}")
    rprint(f"  Status: {info.status}")

    # Listes dérivées des enums du schema (source de vérité unique).
    niveaux = [n.value for n in NiveauCollege] + [n.value for n in NiveauLycee]
    matieres = [m.value for m in Matiere]

    rprint("\n[bold]Répartition par niveau:[/bold]")
    for niveau in niveaux:
        count = client.count(
            collection_name=collection,
            count_filter=Filter(
                must=[FieldCondition(key="niveau", match=MatchValue(value=niveau))]
            ),
        ).count
        if count > 0:
            rprint(f"  {niveau}: {count} points")

    rprint("\n[bold]Répartition par matière:[/bold]")
    for matiere in matieres:
        count = client.count(
            collection_name=collection,
            count_filter=Filter(
                must=[FieldCondition(key="matiere", match=MatchValue(value=matiere))]
            ),
        ).count
        if count > 0:
            rprint(f"  {matiere}: {count} points")


if __name__ == "__main__":
    app()
