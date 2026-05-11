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

Sources :
- https://docs.mistral.ai/api (embeddings, prompt_cache_key)
- https://qdrant.tech/articles/sparse-vectors (hybrid search Qdrant)
- https://qdrant.tech/documentation/concepts/indexing/ (payload indexes)
"""

import hashlib
import json
import math
import sys
import time
import uuid
from pathlib import Path
from typing import Annotated

sys.path.insert(0, str(Path(__file__).parent.parent))

import typer
from dotenv import load_dotenv
from mistralai import Mistral
from pydantic import ValidationError
from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    HasIdCondition,
    MatchValue,
    PointStruct,
)
from rich import print as rprint
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from schema import Document
from schema.document import Matiere, NiveauCollege, NiveauLycee
from scripts.utils import DATA_DIR, get_all_jsonl_files

load_dotenv()

app = typer.Typer(name="ingest", help="Pipeline d'ingestion Qdrant 3 phases")
console = Console()

# =============================================================================
# Configuration
# =============================================================================

EMBEDDING_MODEL = "mistral-embed"
EMBEDDING_DIM = 1024
# Mistral cookbook recommandation : chunk_size = 50 inputs par appel
EMBEDDING_BATCH_SIZE = 50
COLLECTION_DEFAULT = "tomai_educational"
CACHE_ROOT = DATA_DIR.parent / "embeddings_cache"


# =============================================================================
# Hashing & IDs
# =============================================================================


def compute_content_hash(niveau: str, matiere: str, title: str, content: str) -> str:
    """
    SHA-256 stable sur (niveau, matiere, title, content).

    Inclure le content garantit que toute modification du texte invalide
    automatiquement le cache embedding pour ce document.
    """
    payload = f"{niveau}|{matiere}|{title}|{content}".encode()
    return hashlib.sha256(payload).hexdigest()


def doc_id_from_hash(content_hash: str) -> str:
    """UUID5 stable dérivé du content_hash (pour Qdrant point id)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, content_hash))


def normalize_vector(embedding: list[float]) -> list[float]:
    """Unit-norme L2 (cosine similarity exige des vecteurs normalisés)."""
    magnitude = math.sqrt(sum(val * val for val in embedding))
    if magnitude == 0:
        raise ValueError("Cannot normalize zero-magnitude embedding vector")
    return [val / magnitude for val in embedding]


# =============================================================================
# Document loading
# =============================================================================


def load_documents(files: list[Path]) -> list[dict]:
    """Charge et valide tous les documents JSONL, enrichit avec niveau/matiere/cycle/hash."""
    documents: list[dict] = []

    for file_path in files:
        niveau = file_path.parent.name
        matiere = file_path.stem
        cycle = file_path.parent.parent.name

        with open(file_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    doc = Document.model_validate(data)
                except (json.JSONDecodeError, ValidationError) as e:
                    rprint(f"[red]Erreur {file_path}:{line_num}: {e}[/red]")
                    raise typer.Exit(1)

                # Calcule les métriques de qualité explicitement à l'ingestion.
                # Le schema (PR A) a sorti ce calcul du model_validator pour
                # éviter les side-effects à la simple validation ; il faut donc
                # l'appeler ici pour que le payload Qdrant ait le quality_score.
                doc.compute_quality()

                content_hash = compute_content_hash(niveau, matiere, doc.title, doc.content)
                documents.append(
                    {
                        "id": doc_id_from_hash(content_hash),
                        "content_hash": content_hash,
                        "niveau": niveau,
                        "matiere": matiere,
                        "cycle": cycle,
                        "doc": doc,
                    }
                )

    return documents


# =============================================================================
# Embedding (Mistral) + cache local
# =============================================================================


def _cache_path(model: str) -> Path:
    """Path du fichier cache pour un modèle d'embedding donné."""
    return CACHE_ROOT / model / "cache.jsonl"


def load_embedding_cache(model: str = EMBEDDING_MODEL) -> dict[str, list[float]]:
    """
    Charge le cache disque : {content_hash: vector_1024D}.

    Cache versionné par modèle d'embedding : bump du modèle → cache invalidé
    automatiquement (pas de fausses correspondances entre versions).
    """
    path = _cache_path(model)
    if not path.exists():
        return {}
    cache: dict[str, list[float]] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                cache[entry["hash"]] = entry["vector"]
            except (json.JSONDecodeError, KeyError):
                continue
    return cache


def append_to_cache(
    items: list[tuple[str, list[float]]],
    model: str = EMBEDDING_MODEL,
) -> None:
    """Append batch au cache (atomique par ligne JSONL)."""
    path = _cache_path(model)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for content_hash, vector in items:
            f.write(json.dumps({"hash": content_hash, "vector": vector}) + "\n")


def create_embedding_text(doc_data: dict) -> str:
    """
    Construit le texte à embedder. Format conversationnel + signaux pédagogiques.

    learning_objectives volontairement absents (template stéréotypé → bruit
    sémantique uniforme, cf. décision sous-projet A).
    """
    doc = doc_data["doc"]
    text_parts: list[str] = []

    context = f"Cours de {doc_data['matiere']} niveau {doc_data['niveau']}"
    if doc.sousdomaine:
        context += f", {doc.domaine} - {doc.sousdomaine}"
    else:
        context += f", {doc.domaine}"
    text_parts.append(context)

    text_parts.append(f"\n{doc.title}\n")
    text_parts.append(doc.content)

    typical_questions = getattr(doc, "typical_questions", None)
    if typical_questions:
        text_parts.append("\nQuestions fréquentes:")
        for q in typical_questions[:5]:
            text_parts.append(f"- {q}")

    keywords = getattr(doc, "keywords", None)
    if keywords:
        text_parts.append(f"\nConcepts clés: {', '.join(keywords[:8])}")

    common_errors = getattr(doc, "common_errors", None)
    if common_errors:
        text_parts.append("\nErreurs à éviter:")
        for err in common_errors[:3]:
            text_parts.append(f"- {err}")

    return "\n".join(text_parts)


def generate_embeddings_batch(
    client: Mistral,
    texts: list[str],
    max_retries: int = 5,
    base_delay: float = 2.0,
) -> list[list[float]]:
    """
    Génère les embeddings d'un batch en un seul appel Mistral.

    Backoff exponentiel sur 429 uniquement. Pas de sleep préventif entre batches
    (n'apporte rien tant que l'API ne signale pas de rate limit).
    """
    for attempt in range(max_retries):
        try:
            result = client.embeddings.create(model=EMBEDDING_MODEL, inputs=texts)
            return [normalize_vector(data.embedding) for data in result.data]
        except Exception as e:
            error_str = str(e).lower()
            is_rate_limit = "429" in str(e) or "rate" in error_str or "too many" in error_str
            if is_rate_limit and attempt < max_retries - 1:
                wait_time = base_delay * (3**attempt) + 5
                rprint(
                    f"[yellow]Rate limit (tentative {attempt + 1}/{max_retries}), "
                    f"attente {wait_time:.0f}s...[/yellow]"
                )
                time.sleep(wait_time)
                continue
            raise

    raise RuntimeError(f"Échec après {max_retries} tentatives — rate limits trop restrictifs")


# =============================================================================
# Qdrant payload
# =============================================================================


def create_payload(doc_data: dict) -> dict:
    """Payload Qdrant : tout ce qui sert au filtering, reranking, UI."""
    doc = doc_data["doc"]

    payload: dict = {
        "niveau": doc_data["niveau"],
        "matiere": doc_data["matiere"],
        "cycle": doc_data["cycle"],
        "domaine": doc.domaine,
        "sousdomaine": doc.sousdomaine,
        "title": doc.title,
        "content_type": (
            doc.content_type.value if hasattr(doc.content_type, "value") else doc.content_type
        ),
        "content": doc.content,
        "content_hash": doc_data["content_hash"],
    }

    optional_fields = [
        "difficulty",
        "keywords",
        "prerequis",
        "typical_questions",
        "learning_objectives",
        "common_errors",
        "tags",
        "version",
    ]
    for field in optional_fields:
        value = getattr(doc, field, None)
        if value:
            payload[field] = value.value if hasattr(value, "value") else value

    quality = getattr(doc, "quality", None)
    if quality:
        payload["quality_score"] = quality.overall_score

    confidence_level = getattr(doc, "confidence_level", None)
    if confidence_level is not None:
        payload["confidence_level"] = confidence_level

    review_status = getattr(doc, "review_status", None)
    if review_status:
        payload["review_status"] = (
            review_status.value if hasattr(review_status, "value") else review_status
        )

    return payload


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

    existing_hashes = _fetch_existing_hashes(client, collection, [d["id"] for d in documents])

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


def _fetch_existing_hashes(
    client: QdrantClient, collection: str, point_ids: list[str]
) -> dict[str, str]:
    """
    Récupère le content_hash actuel pour chaque point_id (s'il existe).

    Retourne un mapping {point_id: content_hash}. Les points absents ne
    figurent pas dans le mapping.
    """
    hashes: dict[str, str] = {}
    batch_size = 100
    for i in range(0, len(point_ids), batch_size):
        batch_ids = point_ids[i : i + batch_size]
        result = client.retrieve(
            collection_name=collection,
            ids=batch_ids,
            with_payload=["content_hash"],
            with_vectors=False,
        )
        for point in result:
            payload = point.payload or {}
            stored_hash = payload.get("content_hash")
            if stored_hash:
                hashes[str(point.id)] = stored_hash
    return hashes


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

    orphans = _find_orphans(client, collection, current_ids)
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


def _find_orphans(client: QdrantClient, collection: str, current_ids: set[str]) -> list[str]:
    """
    Scroll la collection pour identifier les points dont l'id n'est plus dans current_ids.

    Filtre sur les points "curriculum" uniquement (niveau + matiere + title présents).
    """
    orphans: list[str] = []
    next_offset = None
    while True:
        points, next_offset = client.scroll(
            collection_name=collection,
            limit=512,
            offset=next_offset,
            with_payload=["niveau", "matiere", "title"],
            with_vectors=False,
        )
        for point in points:
            payload = point.payload or {}
            is_curriculum = (
                payload.get("niveau") and payload.get("matiere") and payload.get("title")
            )
            if is_curriculum and str(point.id) not in current_ids:
                orphans.append(str(point.id))
        if next_offset is None:
            break
    return orphans


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
