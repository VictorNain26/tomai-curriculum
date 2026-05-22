"""
Couche d'accès Mistral + Qdrant partagée.

Centralise ce que `ingest.py`, `query.py`, `evaluate.py` faisaient en triple :
- Setup des clients (Mistral, Qdrant) avec retry et check_compatibility
- L2 normalize (mistral-embed ne le garantit pas)
- Hybrid search Qdrant (prefetch dense + sparse → RRF)
- Embedding query avec retry exponentiel sur 429/5xx

Source de vérité unique : modifier `hybrid_search` ici, c'est répercuté partout.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from .bm25 import to_sparse_vector

# ── Constantes ───────────────────────────────────────────────────────────────

# Modèles d'embedding supportés. Tous produisent du 1024D pour rester compatibles
# avec la config Qdrant (named vector "dense" 1024 COSINE).
EMBEDDING_MODELS_1024D = ("mistral-embed", "BAAI/bge-m3")
DEFAULT_EMBED_MODEL = "mistral-embed"

EMBEDDING_DIM = 1024
EMBEDDING_BATCH_SIZE = 50
DEFAULT_TOP_K = 5

DEFAULT_COLLECTION = "tomai_educational"

# Alias rétro-compatibilité (anciens scripts).
EMBEDDING_MODEL = DEFAULT_EMBED_MODEL


# ── Clients lazy singleton ───────────────────────────────────────────────────

_mistral_client = None
_qdrant_client = None
_st_models: dict[str, Any] = {}  # sentence-transformers models cache


def get_mistral_client():
    """Singleton lazy du client Mistral."""
    global _mistral_client
    if _mistral_client is None:
        from mistralai import Mistral

        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise RuntimeError("MISTRAL_API_KEY manquante (.env)")
        _mistral_client = Mistral(api_key=api_key)
    return _mistral_client


def get_qdrant_client():
    """Singleton lazy du client Qdrant. check_compatibility=True pour catch les
    désalignements de version client/server (voir AUDIT P2-1)."""
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import QdrantClient

        url = os.environ.get("QDRANT_URL")
        api_key = os.environ.get("QDRANT_API_KEY")
        if not url or not api_key:
            raise RuntimeError("QDRANT_URL et QDRANT_API_KEY manquantes (.env)")
        _qdrant_client = QdrantClient(url=url, api_key=api_key, check_compatibility=True)
    return _qdrant_client


def get_collection_name() -> str:
    """Nom de collection cible (lecture + écriture). Override via QDRANT_COLLECTION."""
    return os.environ.get("QDRANT_COLLECTION", DEFAULT_COLLECTION)


# ── Helpers numériques ───────────────────────────────────────────────────────


def l2_normalize(vec: list[float]) -> list[float]:
    """
    Normalisation L2 — obligatoire pour mistral-embed (la doc Mistral indique
    que les vecteurs ne sont PAS pré-normalisés ; la cosine similarity Qdrant
    sera instable sans cette normalisation).
    """
    norm = sum(v * v for v in vec) ** 0.5
    if norm == 0.0:
        raise ValueError("Vecteur de norme nulle (texte vide ou tout-blanc ?)")
    return [v / norm for v in vec]


# ── Retry exponentiel transient errors Mistral ───────────────────────────────


def _call_with_retry(fn, label: str, max_attempts: int = 5):
    """
    Retry exponentiel sur 429 / 5xx Mistral. Le SDK mistralai 1.5+ a son propre
    RetryConfig mais on garde un wrapper externe simple pour rester lisible et
    indépendant de la stratégie SDK.
    """
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            msg = str(e).lower()
            transient = "429" in msg or "rate" in msg or "timeout" in msg or "503" in msg
            if attempt == max_attempts - 1 or not transient:
                raise
            wait = 2 * (2**attempt)  # 2, 4, 8, 16, 32 s
            print(f"  ⚠ {label} fail ({attempt + 1}/{max_attempts}): {e}, retry dans {wait}s")
            time.sleep(wait)
    raise RuntimeError("unreachable")


# ── Embeddings (avec normalisation L2 systématique) ──────────────────────────


def _get_sentence_transformer(model_name: str):
    """
    Charge un modèle sentence-transformers (BGE-M3 etc.) en cache module.
    Lib mature, normalize_embeddings=True applique L2 nativement.
    Doc : https://www.sbert.net/
    """
    if model_name not in _st_models:
        from sentence_transformers import SentenceTransformer

        _st_models[model_name] = SentenceTransformer(model_name)
    return _st_models[model_name]


def _embed_mistral(texts: list[str]) -> list[list[float]]:
    """Backend Mistral API (mistral-embed). Retry + L2 normalize côté client."""
    client = get_mistral_client()
    vectors: list[list[float]] = []
    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[i : i + EMBEDDING_BATCH_SIZE]
        response = _call_with_retry(
            lambda b=batch: client.embeddings.create(model="mistral-embed", inputs=b),
            label=f"embed_mistral[{i}:{i + len(batch)}]",
        )
        vectors.extend(l2_normalize(e.embedding) for e in response.data)
    return vectors


def _embed_sentence_transformer(texts: list[str], model_name: str) -> list[list[float]]:
    """Backend local via sentence-transformers (BGE-M3 etc.).
    `normalize_embeddings=True` produit du L2 natif (équivalent à l2_normalize)."""
    model = _get_sentence_transformer(model_name)
    arr = model.encode(
        texts,
        batch_size=EMBEDDING_BATCH_SIZE,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return arr.tolist()


def embed_batch(texts: list[str], embed_model: str = DEFAULT_EMBED_MODEL) -> list[list[float]]:
    """
    Embed une liste de textes. Dispatcher entre Mistral API et
    sentence-transformers selon `embed_model`. Tous les modèles produisent
    du 1024D L2-normalisé pour rester compatibles avec la collection Qdrant.
    """
    if not texts:
        return []
    if embed_model == "mistral-embed":
        return _embed_mistral(texts)
    if embed_model in EMBEDDING_MODELS_1024D:
        return _embed_sentence_transformer(texts, embed_model)
    raise ValueError(
        f"embed_model {embed_model!r} non supporté. "
        f"Modèles 1024D acceptés : {EMBEDDING_MODELS_1024D}"
    )


def embed_query(query: str, embed_model: str = DEFAULT_EMBED_MODEL) -> list[float]:
    """Embed une query (texte court). Délègue à embed_batch pour cohérence."""
    return embed_batch([query], embed_model=embed_model)[0]


# ── Hybrid search Qdrant ─────────────────────────────────────────────────────


@dataclass(slots=True)
class HybridResult:
    """Résultat d'un chunk retourné par hybrid_search."""

    text: str
    matiere: str
    niveau: str
    section: str
    score: float
    payload: dict[str, Any]
    # ID Qdrant (UUID5 calculé à l'ingest). Permet à evaluate.py de
    # mesurer recall@k sur chunk_id quand le golden set est document-grounded.
    id: str | None = None


def hybrid_search(
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    matiere: str | None = None,
    niveau: str | None = None,
    cycle: str | None = None,
    collection: str | None = None,
    prefetch_multiplier: int = 4,
    fusion: str = "rrf",
    embed_model: str = DEFAULT_EMBED_MODEL,
) -> list[HybridResult]:
    """
    Hybrid search : prefetch dense (mistral-embed) + sparse (BM25 IDF natif
    Qdrant), fusion server-side. Tous filtres combinables.

    Args
    ----
    query : texte de la query (langue libre, fr préféré pour le corpus actuel).
    top_k : nombre de chunks retournés (5 par défaut).
    matiere/niveau/cycle : filtres payload exact-match (KEYWORD indexes).
    collection : override la collection cible (sinon `get_collection_name()`).
    prefetch_multiplier : prefetch top_k × N candidats avant fusion (4 par
        défaut, recommandation Qdrant).
    fusion : "rrf" (Reciprocal Rank Fusion, défaut) ou "dbsf" (Distribution-
        Based Score Fusion, Qdrant 1.11+). Ref :
        https://qdrant.tech/documentation/search/hybrid-queries/
    """
    from qdrant_client import models

    dense = embed_query(query, embed_model=embed_model)
    sparse_data = to_sparse_vector(query)
    sparse = models.SparseVector(indices=sparse_data.indices, values=sparse_data.values)

    must = []
    if matiere:
        must.append(models.FieldCondition(key="matiere", match=models.MatchValue(value=matiere)))
    if niveau:
        must.append(models.FieldCondition(key="niveau", match=models.MatchValue(value=niveau)))
    if cycle:
        must.append(models.FieldCondition(key="cycle", match=models.MatchValue(value=cycle)))
    query_filter = models.Filter(must=must) if must else None

    prefetch_limit = max(top_k * prefetch_multiplier, 20)

    fusion_modes = {"rrf": models.Fusion.RRF, "dbsf": models.Fusion.DBSF}
    if fusion not in fusion_modes:
        raise ValueError(f"fusion must be one of {sorted(fusion_modes)} (got {fusion!r})")

    client = get_qdrant_client()
    response = client.query_points(
        collection_name=collection or get_collection_name(),
        prefetch=[
            models.Prefetch(query=dense, using="dense", limit=prefetch_limit),
            models.Prefetch(query=sparse, using="bm25", limit=prefetch_limit),
        ],
        query=models.FusionQuery(fusion=fusion_modes[fusion]),
        query_filter=query_filter,
        limit=top_k,
        with_payload=True,
    )

    return [
        HybridResult(
            text=r.payload["text"],
            matiere=r.payload["matiere"],
            niveau=r.payload["niveau"],
            section=r.payload.get("section", ""),
            score=r.score,
            payload=r.payload,
            id=str(r.id) if r.id is not None else None,
        )
        for r in response.points
    ]


# ── Sparse vector helper (réexporté pour ergonomie) ──────────────────────────


def query_to_sparse(query: str):
    """Convertit une query en sparse vector Qdrant — alias ergonomique."""
    return to_sparse_vector(query)
