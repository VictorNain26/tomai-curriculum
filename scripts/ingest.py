#!/usr/bin/env python3
"""
Pipeline RAG — ingestion des programmes officiels 5ème dans Qdrant.

Flux : data/raw/*.txt → chonkie (SentenceChunker) → mistral-embed → Qdrant

Usage :
  uv run python scripts/ingest.py                    # ingestion complète
  uv run python scripts/ingest.py --dry-run          # affiche chunks sans upserter
  uv run python scripts/ingest.py --matiere=maths    # une seule matière
  uv run python scripts/ingest.py --status           # état collection Qdrant
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

BASE = Path(__file__).parent.parent
RAW = BASE / "data" / "raw"

# ── Mapping matière → fichier source + section de départ ─────────────────────
# Chaque entrée : (fichier_source_sans_ext, motif_regex_section_debut, matiere_enum_value)
# Pour cycle4_BO2020 : les sections débutent par "^NomMatière\n"
# Pour les fichiers matière-spécifiques : tout le fichier = une matière

SOURCES: list[dict] = [
    # Fichiers mono-matière (tout le fichier)
    {
        "file": "programme_maths_cycle4_BO2026",
        "matiere": "mathematiques",
        "section_pattern": None,  # tout le fichier
        "section_name": "Mathématiques",
    },
    {
        "file": "programme_technologie_cycle4_BO2024",
        "matiere": "technologie",
        "section_pattern": None,
        "section_name": "Technologie",
    },
    {
        "file": "programme_anglais_college_BO2025",
        "matiere": "anglais",
        "section_pattern": None,
        "section_name": "Anglais",
    },
    {
        "file": "programme_espagnol_college_BO2025",
        "matiere": "espagnol",
        "section_pattern": None,
        "section_name": "Espagnol",
    },
    {
        "file": "programme_allemand_college_BO2025",
        "matiere": "allemand",
        "section_pattern": None,
        "section_name": "Allemand",
    },
    {
        "file": "programme_italien_college_BO2025",
        "matiere": "italien",
        "section_pattern": None,
        "section_name": "Italien",
    },
    # Sections du fichier cycle4 complet
    {
        "file": "programme_cycle4_BO2020",
        "matiere": "francais",
        "section_pattern": r"^Français\s*$",
        "section_end": (
            r"^Langues vivantes|^Histoire|^Physique"
            r"|^Sciences de la vie|^Technologie|^Mathématiques|^Enseignement moral"
        ),
        "section_name": "Français",
    },
    {
        "file": "programme_cycle4_BO2020",
        "matiere": "histoire_geo",
        "section_pattern": r"^Histoire\s*$|^Histoire et géographie",
        "section_end": (
            r"^Physique|^Sciences de la vie|^Technologie"
            r"|^Mathématiques|^Enseignement moral|^Langues"
        ),
        "section_name": "Histoire-Géographie",
    },
    {
        "file": "programme_cycle4_BO2020",
        "matiere": "physique_chimie",
        "section_pattern": r"^Physique.chimie|^Physique-Chimie",
        "section_end": r"^Sciences de la vie|^Technologie|^Mathématiques|^Enseignement moral",
        "section_name": "Physique-Chimie",
    },
    {
        "file": "programme_cycle4_BO2020",
        "matiere": "svt",
        "section_pattern": r"^Sciences de la vie et de la Terre",
        "section_end": r"^Technologie|^Mathématiques|^Enseignement moral",
        "section_name": "SVT",
    },
    {
        "file": "programme_cycle4_BO2020",
        "matiere": "emc",
        "section_pattern": r"^Enseignement moral et civique",
        "section_end": r"^Histoire|^Physique|^Sciences|^Technologie|^Mathématiques|^Français",
        "section_name": "EMC",
    },
]


def extract_section(text: str, start_pattern: str, end_pattern: str | None) -> str:
    """Extrait une section du texte entre start_pattern et end_pattern."""
    lines = text.split("\n")
    in_section = False
    section_lines: list[str] = []

    for line in lines:
        if not in_section:
            if re.match(start_pattern, line.strip()):
                in_section = True
                section_lines.append(line)
        else:
            if end_pattern and re.match(end_pattern, line.strip()):
                break
            section_lines.append(line)

    return "\n".join(section_lines)


def load_source_text(source: dict) -> str:
    """Charge et extrait le texte d'une source."""
    path = RAW / f"{source['file']}.txt"
    if not path.exists():
        print(f"  ⚠ Fichier manquant : {path.name}", file=sys.stderr)
        return ""

    text = path.read_text(encoding="utf-8")

    if source.get("section_pattern"):
        text = extract_section(
            text,
            source["section_pattern"],
            source.get("section_end"),
        )

    return text.strip()


def chunk_text(text: str, source: dict) -> list[dict]:
    """Découpe le texte en chunks avec chonkie SentenceChunker."""
    from chonkie import SentenceChunker

    chunker = SentenceChunker(
        chunk_size=400,  # tokens cible
        chunk_overlap=40,  # ~10% overlap
        min_sentences_per_chunk=2,
    )

    chunks = chunker(text)
    result = []
    for i, chunk in enumerate(chunks):
        chunk_text_val = chunk.text.strip()
        if len(chunk_text_val) < 50:
            continue
        result.append(
            {
                "text": chunk_text_val,
                "source_file": source["file"],
                "matiere": source["matiere"],
                "section": source["section_name"],
                "chunk_index": i,
            }
        )

    return result


def embed_chunks(texts: list[str]) -> list[list[float]]:
    """Embed une liste de textes avec mistral-embed (batch de 50 max)."""
    from mistralai import Mistral

    client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
    BATCH = 50
    vectors: list[list[float]] = []

    for i in range(0, len(texts), BATCH):
        batch = texts[i : i + BATCH]
        response = client.embeddings.create(model="mistral-embed", inputs=batch)
        vectors.extend([e.embedding for e in response.data])

    return vectors


def upsert_to_qdrant(chunks: list[dict], vectors: list[list[float]], collection: str) -> int:
    """Upsert les chunks dans Qdrant (idempotent via hash du texte)."""
    import hashlib
    import uuid as _uuid

    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    client = QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ.get("QDRANT_API_KEY"),
    )

    # Crée la collection si elle n'existe pas
    existing = [c.name for c in client.get_collections().collections]
    if collection not in existing:
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
        )
        print(f"  Collection '{collection}' créée (1024D, cosine)")

    points = []
    for chunk, vector in zip(chunks, vectors, strict=True):
        # ID stable = uuid5 sur le hash du texte (idempotence)
        text_hash = hashlib.sha256(chunk["text"].encode()).hexdigest()
        point_id = str(_uuid.uuid5(_uuid.NAMESPACE_URL, text_hash))

        points.append(
            PointStruct(
                id=point_id,
                vector=vector,
                payload=chunk,
            )
        )

    client.upsert(collection_name=collection, points=points)
    return len(points)


def show_status(collection: str) -> None:
    """Affiche les statistiques de la collection Qdrant."""
    from qdrant_client import QdrantClient

    client = QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ.get("QDRANT_API_KEY"),
    )
    try:
        info = client.get_collection(collection)
        counts = client.count(collection_name=collection)
        print(f"Collection : {collection}")
        print(f"  Points   : {counts.count}")
        print(f"  Status   : {info.status}")
        print(f"  Vectors  : {info.config.params.vectors}")
    except Exception as e:
        print(f"Collection '{collection}' introuvable : {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Affiche chunks sans upserter")
    parser.add_argument("--matiere", help="Filtre sur une matière (ex: mathematiques)")
    parser.add_argument("--status", action="store_true", help="Affiche état collection Qdrant")
    args = parser.parse_args()

    collection = os.environ.get("QDRANT_COLLECTION", "tomai_educational")

    if args.status:
        show_status(collection)
        return

    sources = SOURCES
    if args.matiere:
        sources = [s for s in SOURCES if s["matiere"] == args.matiere]
        if not sources:
            available = [s["matiere"] for s in SOURCES]
            print(f"Matière '{args.matiere}' non trouvée. Disponibles : {available}")
            sys.exit(1)

    total_chunks = 0

    for source in sources:
        print(f"\n▶ {source['section_name']} ({source['matiere']})")
        text = load_source_text(source)
        if not text:
            continue

        chunks = chunk_text(text, source)
        print(f"  {len(chunks)} chunks extraits")

        if args.dry_run:
            for c in chunks[:2]:
                print(f"  [{c['chunk_index']}] {c['text'][:100]}…")
            continue

        if not chunks:
            continue

        print("  Embedding…", end=" ", flush=True)
        vectors = embed_chunks([c["text"] for c in chunks])
        print(f"{len(vectors)} vecteurs")

        n = upsert_to_qdrant(chunks, vectors, collection)
        print(f"  ✓ {n} points upsertés dans '{collection}'")
        total_chunks += n

    if not args.dry_run:
        print(f"\nTotal : {total_chunks} points upsertés")
        show_status(collection)


if __name__ == "__main__":
    main()
