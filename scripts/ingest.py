#!/usr/bin/env python3
"""
Pipeline RAG — ingestion des programmes officiels Eduscol dans Qdrant v2.

Flux :
  data/raw/*.txt
    → load_source_text()       # extraction section matière par regex
    → chunk_text()              # RecursiveChunker rules markdown + tokenizer Mistral
    → expand_for_niveaux()      # 1 chunk × N niveaux du cycle (duplication payload)
    → validate_chunks()         # Pydantic Chunk → payload Qdrant
    → embed (schema.encode_with_sparse / embed_batch)  # dense + sparse
    → upsert_to_qdrant()        # named vectors {dense, bm25} + uuid5 idempotent

Les étapes de transformation pures vivent dans `ingest_pipeline.py` et la
configuration des sources dans `ingest_sources.py` (chaque fichier < 400 lignes).
Ce module orchestre l'embedding + upsert Qdrant et expose la CLI.

Usage :
  uv run python scripts/ingest.py                    # ingestion complète
  uv run python scripts/ingest.py --dry-run          # affiche chunks sans upserter
  uv run python scripts/ingest.py --matiere=mathematiques
  uv run python scripts/ingest.py --status           # état collection
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
import uuid as _uuid

from dotenv import load_dotenv

from schema import (
    Chunk,
    Matiere,
    NiveauCollege,
    NiveauLycee,
    build_contextual_text,
    embed_batch,
    get_qdrant_client,
    to_sparse_vector,
)

# Re-export de l'API publique (imports historiques `from scripts.ingest import …`).
from scripts.ingest_pipeline import (
    chunk_text,
    expand_for_niveaux,
    extract_section,
    load_source_text,
    validate_chunks,
)
from scripts.ingest_sources import SOURCES

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

COLLECTION = os.environ.get("QDRANT_COLLECTION", "tomai_educational")

# Batch d'upsert : Qdrant Cloud peut timeout sur des payloads >20 MB en une
# seule requête. 200 points × ~5 KB ≈ 1 MB par batch — confortable.
UPSERT_BATCH_SIZE = 200

__all__ = [
    "SOURCES",
    "chunk_text",
    "expand_for_niveaux",
    "extract_section",
    "load_source_text",
    "upsert_to_qdrant",
    "validate_chunks",
]


# ── Upsert Qdrant (named vectors + sparse BM25) ──────────────────────────────


def upsert_to_qdrant(
    payloads: list[dict],
    dense_vectors: list[list[float]],
    sparse_vectors: list | None = None,
) -> int:
    """
    Upsert dans la collection cible (named vectors `dense` + sparse `bm25`).

    - ID stable : uuid5(NAMESPACE_URL, sha256(matière:niveau:text))
      → idempotent : re-run = pas de doublons, modif text = nouveau point.
    - Si `sparse_vectors` fourni (BGE-M3 learned sparse), on les utilise tels
      quels. Sinon on retombe sur le BM25 maison (parité TS via FNV-1a).
    """
    from qdrant_client import models

    client = get_qdrant_client()

    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION not in existing:
        raise RuntimeError(
            f"Collection '{COLLECTION}' absente. "
            f"Exécuter d'abord : uv run python scripts/migrate_collection.py"
        )

    points = []
    for i, (payload, dense_vec) in enumerate(zip(payloads, dense_vectors, strict=True)):
        text = payload["text"]
        niveau = payload["niveau"]
        matiere = payload["matiere"]

        # ID stable incluant matière + niveau pour distinguer :
        # - les duplications cycle (même texte × N niveaux du cycle)
        # - les textes COMMUNS entre matières (préambules pédagogiques langues
        #   college sont identiques entre EN/ES/DE/IT — sans matière dans
        #   le seed, le dernier upsert écraserait les précédents et seul
        #   le filtre matière=italien retrouverait ces chunks).
        id_seed = f"{matiere}:{niveau}:{text}"
        text_hash = hashlib.sha256(id_seed.encode("utf-8")).hexdigest()
        point_id = str(_uuid.uuid5(_uuid.NAMESPACE_URL, text_hash))

        # Sparse : soit fourni (BGE-M3 learned sparse), soit BM25 maison.
        sparse = sparse_vectors[i] if sparse_vectors is not None else to_sparse_vector(text)
        sparse_vec = models.SparseVector(
            indices=sparse.indices,
            values=sparse.values,
        )

        points.append(
            models.PointStruct(
                id=point_id,
                vector={
                    "dense": dense_vec,
                    "bm25": sparse_vec,
                },
                payload=payload,
            )
        )

    # Batch upsert par chunks de UPSERT_BATCH_SIZE points. Sans batching,
    # un payload >20 MB peut faire timeout sur Qdrant Cloud (write op).
    # uuid5 garantit l'idempotence : retry sans craindre les doublons.
    upserted = 0
    for i in range(0, len(points), UPSERT_BATCH_SIZE):
        batch = points[i : i + UPSERT_BATCH_SIZE]
        for attempt in range(3):
            try:
                client.upsert(collection_name=COLLECTION, points=batch, wait=True)
                upserted += len(batch)
                break
            except Exception as e:
                if attempt == 2:
                    raise
                wait = 5 * (2**attempt)  # 5, 10 s
                print(
                    f"  ⚠ upsert batch {i // UPSERT_BATCH_SIZE + 1} fail "
                    f"(essai {attempt + 1}/3) : {e}, retry dans {wait}s"
                )
                time.sleep(wait)
    return upserted


def show_status() -> None:
    """Affiche les statistiques de la collection v2."""
    client = get_qdrant_client()
    try:
        info = client.get_collection(COLLECTION)
        counts = client.count(collection_name=COLLECTION)
        print(f"Collection : {COLLECTION}")
        print(f"  Points   : {counts.count}")
        print(f"  Status   : {info.status}")
        print(f"  Vectors  : {info.config.params.vectors}")
        sparse = getattr(info.config.params, "sparse_vectors", None)
        if sparse:
            print(f"  Sparse   : {sparse}")
    except Exception as e:
        print(f"Collection '{COLLECTION}' introuvable : {e}")


# ── Pipeline principal ───────────────────────────────────────────────────────


def _chunk_for_payload(p: dict) -> Chunk:
    """Reconstruit un Chunk Pydantic depuis un payload (pour le préfixe contextuel)."""
    niveau: NiveauCollege | NiveauLycee = (
        NiveauCollege(p["niveau"])
        if p["niveau"] in {n.value for n in NiveauCollege}
        else NiveauLycee(p["niveau"])
    )
    return Chunk(
        text=p["text"],
        source_file=p["source_file"],
        matiere=Matiere(p["matiere"]),
        niveau=niveau,
        section=p["section"],
        chunk_index=p["chunk_index"],
    )


def main() -> None:
    from schema import (
        DEFAULT_EMBED_MODEL,
        DEFAULT_SPARSE_METHOD,
        EMBEDDING_MODELS_1024D,
        SPARSE_METHODS,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Affiche chunks sans upserter")
    parser.add_argument("--matiere", help="Filtre sur une matière (ex: mathematiques)")
    parser.add_argument("--status", action="store_true", help="État collection Qdrant")
    parser.add_argument(
        "--embed-model",
        default=DEFAULT_EMBED_MODEL,
        choices=list(EMBEDDING_MODELS_1024D),
        help=f"Modèle d'embedding (1024D). Défaut: {DEFAULT_EMBED_MODEL}.",
    )
    parser.add_argument(
        "--sparse-method",
        default=DEFAULT_SPARSE_METHOD,
        choices=list(SPARSE_METHODS),
        help=(
            f"Méthode sparse (défaut: {DEFAULT_SPARSE_METHOD}). "
            "'bm25' = tokenizer FNV-1a maison (parité TS backend), "
            "'BAAI/bge-m3' = learned sparse natif via FlagEmbedding."
        ),
    )
    parser.add_argument(
        "--collection",
        default=None,
        help=(
            "Override la collection cible (sinon QDRANT_COLLECTION env ou "
            "'tomai_educational'). Utile pour bench un embedder alternatif "
            "dans une sandbox sans toucher l'index prod."
        ),
    )
    args = parser.parse_args()

    # Validation cohérence : sparse BGE-M3 requiert dense BGE-M3 (single
    # forward pass cohérent — sinon, vecteurs disjoints conceptuellement).
    if args.sparse_method == "BAAI/bge-m3" and args.embed_model != "BAAI/bge-m3":
        print(
            "✗ --sparse-method=BAAI/bge-m3 impose --embed-model=BAAI/bge-m3 "
            "(single forward pass dense+sparse cohérent).",
            file=sys.stderr,
        )
        sys.exit(2)

    # Override collection si demandé (avant que upsert_to_qdrant lise la globale)
    global COLLECTION
    if args.collection:
        COLLECTION = args.collection

    if args.status:
        show_status()
        return

    sources = SOURCES
    if args.matiere:
        sources = [s for s in SOURCES if s["matiere"].value == args.matiere]
        if not sources:
            available = sorted({s["matiere"].value for s in SOURCES})
            print(f"Matière '{args.matiere}' inconnue. Disponibles : {available}")
            sys.exit(1)

    total_points = 0
    errors: list[str] = []

    for source in sources:
        print(f"\n▶ {source['section_name']} ({source['matiere'].value})")
        try:
            text = load_source_text(source)
        except (FileNotFoundError, ValueError) as e:
            print(f"  ✗ {e}", file=sys.stderr)
            errors.append(source["matiere"].value)
            continue

        chunks = chunk_text(text, source)
        print(f"  {len(chunks)} chunks bruts")

        expanded = expand_for_niveaux(chunks)
        print(f"  {len(expanded)} chunks après expansion multi-niveaux")

        if args.dry_run:
            for c in expanded[:3]:
                contextual = build_contextual_text(_chunk_for_payload(c))
                print(f"  [{c['chunk_index']}|{c['niveau']}] {contextual[:200]}…")
            continue

        if not expanded:
            errors.append(source["matiere"].value)
            continue

        print("  Validation…", end=" ", flush=True)
        payloads = validate_chunks(expanded)
        print(f"{len(payloads)} valides")

        # Optimisation : embedder UNE fois chaque texte unique, puis broadcaster
        # aux duplications de niveau.
        unique_texts: dict[str, int] = {}
        embed_inputs: list[str] = []
        for p in payloads:
            text = p["text"]
            if text not in unique_texts:
                # Préfixe contextuel SANS niveau (cf. schema/contextual.py)
                unique_texts[text] = len(embed_inputs)
                embed_inputs.append(build_contextual_text(_chunk_for_payload(p)))

        # Dense (+ sparse selon sparse-method) sur les textes uniques.
        # Si BGE-M3 sparse demandé, on récupère dense+sparse en un seul forward
        # pass via FlagEmbedding (cohérence + gain de latence).
        print(
            f"  Embedding ({len(embed_inputs)} textes uniques, "
            f"dense={args.embed_model}, sparse={args.sparse_method})…",
            end=" ",
            flush=True,
        )
        if args.sparse_method == "BAAI/bge-m3":
            from schema import encode_with_sparse

            unique_vectors, unique_sparse = encode_with_sparse(
                embed_inputs,
                embed_model=args.embed_model,
                sparse_method=args.sparse_method,
            )
        else:
            unique_vectors = embed_batch(embed_inputs, embed_model=args.embed_model)
            unique_sparse = None  # upsert_to_qdrant retombe sur BM25 maison
        print(f"{len(unique_vectors)} vecteurs")

        # Broadcast : chaque payload récupère le vecteur de son texte
        dense_vectors = [unique_vectors[unique_texts[p["text"]]] for p in payloads]
        sparse_vectors = (
            [unique_sparse[unique_texts[p["text"]]] for p in payloads]
            if unique_sparse is not None
            else None
        )

        print(f"  Upsert {len(payloads)} points…", end=" ", flush=True)
        n = upsert_to_qdrant(payloads, dense_vectors, sparse_vectors=sparse_vectors)
        print(f"✓ ({n} points dans '{COLLECTION}')")
        total_points += n

    if errors:
        print(f"\n✗ {len(errors)} matière(s) en erreur : {errors}", file=sys.stderr)
        sys.exit(1)

    if not args.dry_run:
        print(f"\nTotal : {total_points} points upsertés")
        show_status()


if __name__ == "__main__":
    main()
