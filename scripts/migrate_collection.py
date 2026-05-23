#!/usr/bin/env python3
"""
Administration de la collection Qdrant.

Config canonique :
- Vecteurs nommés `dense` (1024D cosine, Mistral) + `bm25` (sparse, Modifier.IDF)
- Quantization scalar int8 always_ram (4× compression RAM, <1% perte recall)
- Payload indexes KEYWORD sur : niveau, matiere, cycle, source_file

Collection unique : `tomai_educational` (configurable via QDRANT_COLLECTION).

Usage :
  uv run python scripts/migrate_collection.py             # crée si absente
  uv run python scripts/migrate_collection.py --recreate  # drop+create (DESTRUCTIF)
  uv run python scripts/migrate_collection.py --status    # état des collections

Sources :
- https://qdrant.tech/documentation/concepts/indexing/ (sparse + payload index)
- https://qdrant.tech/documentation/guides/quantization/ (scalar int8)
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv
from qdrant_client import QdrantClient, models

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

COLLECTION_NAME = os.environ.get("QDRANT_COLLECTION", "tomai_educational")

PAYLOAD_INDEX_FIELDS = ("niveau", "matiere", "cycle", "source_file")


def get_client() -> QdrantClient:
    url = os.environ.get("QDRANT_URL")
    api_key = os.environ.get("QDRANT_API_KEY")
    if not url or not api_key:
        raise RuntimeError("QDRANT_URL et QDRANT_API_KEY sont obligatoires (.env)")
    # check_compatibility=True : warn si client/server diffèrent — drift catch.
    return QdrantClient(url=url, api_key=api_key, check_compatibility=True)


def create_collection(client: QdrantClient, recreate: bool = False) -> None:
    """Crée la collection avec la config cible. Idempotent sauf si recreate=True."""
    existing = {c.name for c in client.get_collections().collections}

    if COLLECTION_NAME in existing:
        if not recreate:
            print(
                f"✓ Collection '{COLLECTION_NAME}' existe déjà "
                "(skip — utiliser --recreate pour drop+create)"
            )
            _ensure_payload_indexes(client)
            return
        print(f"⚠ --recreate : suppression de '{COLLECTION_NAME}'")
        client.delete_collection(COLLECTION_NAME)

    print(f"▶ Création collection '{COLLECTION_NAME}'")
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "dense": models.VectorParams(
                size=1024,  # mistral-embed
                distance=models.Distance.COSINE,
                on_disk=False,  # corpus <1M points, RAM OK
            ),
        },
        sparse_vectors_config={
            "bm25": models.SparseVectorParams(
                # Modifier.IDF : Qdrant calcule IDF server-side à partir des
                # indices+values fournis par le client.
                modifier=models.Modifier.IDF,
                index=models.SparseIndexParams(on_disk=False),
            ),
        },
        quantization_config=models.ScalarQuantization(
            scalar=models.ScalarQuantizationConfig(
                type=models.ScalarType.INT8,
                quantile=0.99,  # exclut top 1% outliers pour préserver le recall
                always_ram=True,  # int8 en RAM même si vectors on_disk=True
            ),
        ),
    )
    print(f"  ✓ {COLLECTION_NAME} créée (dense 1024D cosine + sparse bm25 IDF + int8)")
    _ensure_payload_indexes(client)


def _ensure_payload_indexes(client: QdrantClient) -> None:
    """Crée les payload indexes KEYWORD (idempotent : recréer = no-op côté Qdrant)."""
    for field in PAYLOAD_INDEX_FIELDS:
        try:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            print(f"  ✓ index KEYWORD sur '{field}'")
        except Exception as e:
            msg = str(e).lower()
            if "already exists" in msg or "exists" in msg:
                print(f"  · index '{field}' déjà présent")
            else:
                raise


def show_status(client: QdrantClient) -> None:
    """Affiche l'état actuel des collections + aliases."""
    collections = client.get_collections().collections
    print("── Collections ──────────────────────────────")
    for c in collections:
        info = client.get_collection(c.name)
        count = client.count(c.name).count
        print(f"  {c.name}")
        print(f"    points : {count}")
        print(f"    status : {info.status}")
        print(f"    vectors: {info.config.params.vectors}")
        sparse = getattr(info.config.params, "sparse_vectors", None)
        if sparse:
            print(f"    sparse : {sparse}")

    print("\n── Aliases ──────────────────────────────────")
    try:
        aliases = client.get_aliases().aliases
        if not aliases:
            print("  (aucun alias)")
        for a in aliases:
            print(f"  {a.alias_name} → {a.collection_name}")
    except Exception as e:
        print(f"  (impossible de lister les aliases : {e})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recreate", action="store_true", help="Drop + create (destructif)")
    parser.add_argument("--status", action="store_true", help="Affiche état des collections")
    args = parser.parse_args()

    client = get_client()

    if args.status:
        show_status(client)
        return

    # Défaut : créer la collection canonique (idempotent)
    create_collection(client, recreate=args.recreate)


if __name__ == "__main__":
    main()
