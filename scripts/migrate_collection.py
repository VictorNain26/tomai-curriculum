#!/usr/bin/env python3
"""
Migration de collection Qdrant : ancienne -> nouvelle architecture (mai 2026).

Architecture cible :
- Vecteur dense : mistral-embed 1024D, cosine, scalar int8 quantization (always_ram)
- Vecteur sparse : BM25 avec Modifier.IDF (natif Qdrant, plus de BM25 manuel server)
- Payload indexes KEYWORD : niveau, matiere, cycle, difficulty, content_type
- HNSW : m=16, ef_construct=100 (défauts documentés, adaptés jusqu'à ~1M points)
- Optimizers : indexing_threshold=20000 (brute-force exact en deçà)

La dim et la distance d'une collection Qdrant sont immuables. Migration via
collection alias swap : on crée _v2, on migre les points, on swap l'alias.
Le code applicatif consomme TOUJOURS l'alias, jamais le nom canonique.

Étapes :
1. `create-v2`         : crée la nouvelle collection (dense + sparse + indexes)
2. `migrate`           : scroll ancienne -> upsert nouvelle (sparse vectors
                        générés côté Qdrant à partir du title+content via Modifier.IDF)
3. `swap-alias`        : alias atomique vers _v2
4. `cleanup-old`       : suppression de l'ancienne (manuelle, après validation)

Sources :
- https://qdrant.tech/articles/sparse-vectors
- https://qdrant.tech/articles/bm42
- https://qdrant.tech/documentation/concepts/indexing/
- https://qdrant.tech/documentation/concepts/collections/ (aliases)
"""

import re
import sys
from pathlib import Path
from typing import Annotated

sys.path.insert(0, str(Path(__file__).parent.parent))

import typer
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    AliasOperations,
    CreateAlias,
    CreateAliasOperation,
    DeleteAlias,
    DeleteAliasOperation,
    Distance,
    HnswConfigDiff,
    Modifier,
    OptimizersConfigDiff,
    PayloadSchemaType,
    PointStruct,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)
from rich import print as rprint

load_dotenv()

app = typer.Typer(name="migrate", help="Migration de collection Qdrant via alias swap")

EMBEDDING_DIM = 1024
PAYLOAD_INDEX_FIELDS = ("niveau", "matiere", "cycle", "difficulty", "content_type")


def _client(qdrant_url: str | None, qdrant_api_key: str | None) -> QdrantClient:
    if not qdrant_url or not qdrant_api_key:
        rprint("[red]QDRANT_URL et QDRANT_API_KEY requis[/red]")
        raise typer.Exit(1)
    return QdrantClient(url=qdrant_url, api_key=qdrant_api_key)


# =============================================================================
# create-v2 : nouvelle collection (dense + sparse + indexes)
# =============================================================================


@app.command("create-v2")
def create_v2(
    new_collection: Annotated[str, typer.Option(help="Nom canonique de la nouvelle collection")],
    qdrant_url: Annotated[str | None, typer.Option(envvar="QDRANT_URL")] = None,
    qdrant_api_key: Annotated[str | None, typer.Option(envvar="QDRANT_API_KEY")] = None,
):
    """
    Crée la collection v2 avec vecteur dense + sparse + 5 payload indexes.

    Idempotent : si la collection existe déjà, vérifie que la config matche.
    """
    client = _client(qdrant_url, qdrant_api_key)

    if client.collection_exists(new_collection):
        rprint(f"[yellow]Collection {new_collection!r} existe déjà, skip création[/yellow]")
    else:
        rprint(f"\n[bold cyan]Création de {new_collection!r}[/bold cyan]")
        client.create_collection(
            collection_name=new_collection,
            vectors_config={
                "dense": VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            },
            sparse_vectors_config={
                # Modifier.IDF active le calcul IDF natif Qdrant -> BM25 server-side
                "bm25": SparseVectorParams(modifier=Modifier.IDF),
            },
            hnsw_config=HnswConfigDiff(
                m=16,
                ef_construct=100,
                full_scan_threshold=10000,
            ),
            quantization_config=ScalarQuantization(
                scalar=ScalarQuantizationConfig(type=ScalarType.INT8, always_ram=True),
            ),
            optimizers_config=OptimizersConfigDiff(
                indexing_threshold=20000,
                flush_interval_sec=5,
            ),
        )
        rprint("   [green]OK collection créée[/green]")

    rprint("\n[bold cyan]Création des payload indexes[/bold cyan]")
    # Look-before-leap : on lit l'état actuel pour ne créer que les index manquants.
    # Évite le try/except sur "already exists" qui dépend du wording d'erreur Qdrant.
    collection_info = client.get_collection(new_collection)
    existing_payload_schema = collection_info.payload_schema or {}
    for field in PAYLOAD_INDEX_FIELDS:
        if field in existing_payload_schema:
            rprint(f"   [dim]index {field} déjà présent (skip)[/dim]")
            continue
        client.create_payload_index(
            collection_name=new_collection,
            field_name=field,
            field_schema=PayloadSchemaType.KEYWORD,
        )
        rprint(f"   [green]OK index KEYWORD sur {field}[/green]")


# =============================================================================
# migrate : scroll ancienne -> upsert nouvelle (sparse calculé par Qdrant)
# =============================================================================


@app.command("migrate")
def migrate(
    source: Annotated[str, typer.Option(help="Nom de la collection source")],
    target: Annotated[str, typer.Option(help="Nom de la collection cible (v2)")],
    qdrant_url: Annotated[str | None, typer.Option(envvar="QDRANT_URL")] = None,
    qdrant_api_key: Annotated[str | None, typer.Option(envvar="QDRANT_API_KEY")] = None,
    batch_size: Annotated[int, typer.Option(help="Points par scroll")] = 256,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Compter sans upsert")] = False,
):
    """
    Copie les points (vector + payload) de source vers target.

    Le vecteur sparse BM25 est généré côté Qdrant à partir du title+content
    via Modifier.IDF (pas besoin de tokenizer Python).

    Pré-requis : la dim et la distance des deux collections doivent matcher
    (vérifié via get_collection).
    """
    client = _client(qdrant_url, qdrant_api_key)

    if not client.collection_exists(source):
        rprint(f"[red]Collection source {source!r} introuvable[/red]")
        raise typer.Exit(1)
    if not client.collection_exists(target):
        rprint(f"[red]Collection cible {target!r} introuvable (lancer create-v2 d'abord)[/red]")
        raise typer.Exit(1)

    rprint(f"\n[bold cyan]Migration {source!r} -> {target!r}[/bold cyan]")

    total = 0
    next_offset = None
    buffer: list[PointStruct] = []

    while True:
        points, next_offset = client.scroll(
            collection_name=source,
            limit=batch_size,
            offset=next_offset,
            with_payload=True,
            with_vectors=True,
        )

        for point in points:
            payload = point.payload or {}
            # Le scroll renvoie soit un dict {nom_vecteur: vector} (collection
            # multi-vecteurs) soit directement une liste (collection legacy).
            raw_vector = point.vector
            if isinstance(raw_vector, dict):
                dense_vector = raw_vector.get("dense") or next(iter(raw_vector.values()))
            else:
                dense_vector = raw_vector

            if dense_vector is None:
                continue

            # Sparse text source : title + content (BM25 IDF natif Qdrant le tokenise)
            sparse_text = f"{payload.get('title', '')} {payload.get('content', '')}".strip()
            sparse_vector = _build_sparse_from_text(sparse_text)

            new_point = PointStruct(
                id=point.id,
                vector={"dense": dense_vector, "bm25": sparse_vector},
                payload=payload,
            )
            buffer.append(new_point)
            total += 1

            if len(buffer) >= batch_size:
                if not dry_run:
                    client.upsert(collection_name=target, points=buffer)
                buffer = []

        if next_offset is None:
            break

    if buffer and not dry_run:
        client.upsert(collection_name=target, points=buffer)

    if dry_run:
        rprint(f"   [yellow]dry-run : {total} points seraient migrés[/yellow]")
    else:
        rprint(f"   [green]OK {total} points migrés[/green]")


_FRENCH_TOKEN_RE = re.compile(r"[a-zàâäéèêëïîôùûüÿœæç0-9]+")


def _fnv1a_32(token: str) -> int:
    """
    Hash FNV-1a 32-bit DÉTERMINISTE et CROSS-LANGAGE.

    `hash()` de Python est non-déterministe (PYTHONHASHSEED aléatoire par défaut
    depuis Python 3.3) et incompatible avec d'autres langages. Pour que les
    indices sparse calculés ici matchent ceux du server TypeScript
    (apps/server/src/services/rag.service.ts:hashToken), il faut une fonction
    de hash stable et identique des deux côtés. FNV-1a 32-bit est trivial à
    implémenter à l'identique en Python/TS/Go/Rust et a une distribution
    suffisamment uniforme pour notre cas (~10k tokens uniques).
    """
    h = 2166136261
    for c in token:
        h ^= ord(c) & 0xFF
        h = (h * 16777619) & 0xFFFFFFFF
    return h & 0x7FFFFFFF  # 31-bit positif (cohérent avec rag.service.ts)


def _build_sparse_from_text(text: str) -> SparseVector:
    """
    Construit un SparseVector pour Qdrant Modifier.IDF.

    Tokenisation : regex sur caractères alpha/numériques français (cohérent
    avec rag.service.ts:toSparseVector). NE PAS utiliser split() qui ne casse
    pas sur les apostrophes (`l'aire` resterait un seul token côté Python alors
    que le server produit ['l', 'aire'] → indices divergents → recall sparse=0).

    Qdrant calcule l'IDF côté server à partir de (indices, values) qu'on fournit.
    """
    tokens = _FRENCH_TOKEN_RE.findall(text.lower())
    counts: dict[int, float] = {}
    for token in tokens:
        token_id = _fnv1a_32(token)
        counts[token_id] = counts.get(token_id, 0.0) + 1.0
    indices = list(counts.keys())
    values = [counts[i] for i in indices]
    return SparseVector(indices=indices, values=values)


# =============================================================================
# swap-alias : alias atomique
# =============================================================================


@app.command("swap-alias")
def swap_alias(
    alias: Annotated[str, typer.Option(help="Nom d'alias consommé par l'app")],
    new_collection: Annotated[str, typer.Option(help="Nouvelle collection cible de l'alias")],
    qdrant_url: Annotated[str | None, typer.Option(envvar="QDRANT_URL")] = None,
    qdrant_api_key: Annotated[str | None, typer.Option(envvar="QDRANT_API_KEY")] = None,
):
    """
    Swap atomique : supprime l'alias existant (s'il existe) et le recrée
    pointant vers new_collection. Opération atomique côté Qdrant.

    Après ce swap, le server (qui consomme `alias`) bascule immédiatement
    sur la nouvelle collection sans redémarrage.
    """
    client = _client(qdrant_url, qdrant_api_key)

    if not client.collection_exists(new_collection):
        rprint(f"[red]Collection {new_collection!r} introuvable[/red]")
        raise typer.Exit(1)

    operations: list[AliasOperations] = []

    # Vérifier si l'alias existe déjà (pour le delete préalable)
    aliases = client.get_aliases().aliases
    existing_alias = next((a for a in aliases if a.alias_name == alias), None)
    if existing_alias:
        rprint(
            f"[yellow]Alias {alias!r} pointe actuellement vers "
            f"{existing_alias.collection_name!r}[/yellow]"
        )
        operations.append(DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=alias)))

    operations.append(
        CreateAliasOperation(
            create_alias=CreateAlias(collection_name=new_collection, alias_name=alias)
        )
    )

    client.update_collection_aliases(change_aliases_operations=operations)
    rprint(f"[green]OK alias {alias!r} -> {new_collection!r}[/green]")


# =============================================================================
# cleanup-old : suppression manuelle de l'ancienne collection
# =============================================================================


@app.command("cleanup-old")
def cleanup_old(
    old_collection: Annotated[str, typer.Option(help="Ancienne collection à supprimer")],
    confirm: Annotated[bool, typer.Option("--yes", help="Confirmer la suppression")] = False,
    qdrant_url: Annotated[str | None, typer.Option(envvar="QDRANT_URL")] = None,
    qdrant_api_key: Annotated[str | None, typer.Option(envvar="QDRANT_API_KEY")] = None,
):
    """Supprime l'ancienne collection (à lancer manuellement après validation v2)."""
    if not confirm:
        rprint(
            f"[yellow]Confirmer la suppression de {old_collection!r} en repassant "
            f"avec --yes[/yellow]"
        )
        raise typer.Exit(0)

    client = _client(qdrant_url, qdrant_api_key)
    if not client.collection_exists(old_collection):
        rprint(f"[yellow]Collection {old_collection!r} n'existe pas[/yellow]")
        return

    client.delete_collection(collection_name=old_collection)
    rprint(f"[green]OK collection {old_collection!r} supprimée[/green]")


if __name__ == "__main__":
    app()
