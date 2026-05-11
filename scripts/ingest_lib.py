#!/usr/bin/env python3
"""
Helpers du pipeline d'ingestion Qdrant (extraits de ingest.py).

Ce module regroupe les fonctions pures et les helpers d'I/O (cache disque,
batchs Mistral, opérations Qdrant) consommés par les commandes CLI dans
`scripts/ingest.py`. Le découpage suit la règle 400 lignes max du monorepo
Tom et la spec RAG overhaul (3 phases découplées : embed / upsert / prune).
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import time
import uuid
from pathlib import Path

import typer
from mistralai import Mistral
from mistralai.models import SDKError
from pydantic import ValidationError
from qdrant_client import QdrantClient
from rich import print as rprint

sys.path.insert(0, str(Path(__file__).parent.parent))

from schema import Document  # noqa: E402
from scripts.utils import DATA_DIR  # noqa: E402

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
    """Charge et valide tous les documents JSONL, enrichit avec niveau/matiere/cycle/hash.

    Si le JSONL contient `niveau`/`matiere` (post-migration Phase 5), ces valeurs
    sont **cross-checkées** avec le path : une divergence est un bug d'organisation
    du dataset et fail l'ingestion. Sinon (legacy), on dérive du path silencieusement.
    """
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
                    raise typer.Exit(1) from e

                # Cross-check path ↔ champs JSONL. Source de vérité = path (les
                # JSONL sont organisés par dossier). Une divergence indique un
                # fichier mal placé ou un champ corrompu.
                doc_niveau = doc.niveau.value if doc.niveau else None
                doc_matiere = doc.matiere.value if doc.matiere else None
                if doc_niveau and doc_niveau != niveau:
                    rprint(
                        f"[red]{file_path}:{line_num}: niveau mismatch "
                        f"(path={niveau}, doc={doc_niveau})[/red]"
                    )
                    raise typer.Exit(1)
                if doc_matiere and doc_matiere != matiere:
                    rprint(
                        f"[red]{file_path}:{line_num}: matiere mismatch "
                        f"(path={matiere}, doc={doc_matiere})[/red]"
                    )
                    raise typer.Exit(1)

                # Calcule les métriques de qualité explicitement à l'ingestion.
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
# Embedding cache + Mistral
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
        except SDKError as e:
            # Détection 429 par status code typé (vs string match sur str(e) qui
            # casserait au moindre changement de wording côté Mistral). Tous les
            # autres status codes (400, 401, 500…) propagent immédiatement, pas
            # de retry silencieux qui masque un vrai bug.
            if e.raw_response.status_code != 429 or attempt >= max_retries - 1:
                raise
            wait_time = base_delay * (3**attempt) + 5
            rprint(
                f"[yellow]Rate limit 429 (tentative {attempt + 1}/{max_retries}), "
                f"attente {wait_time:.0f}s...[/yellow]"
            )
            time.sleep(wait_time)

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
# Qdrant helpers (upsert / prune)
# =============================================================================


def fetch_existing_hashes(
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


def find_orphans(client: QdrantClient, collection: str, current_ids: set[str]) -> list[str]:
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
