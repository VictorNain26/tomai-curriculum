"""
BM25 sparse vector tokenizer — parité stricte avec le backend.

Qdrant ne tokenise pas côté serveur : il reçoit `{indices: u32[], values: f32[]}`
et calcule l'IDF à partir des compteurs. Pour que l'IDF soit cohérent, le MÊME
algorithme de tokenisation + hash doit être utilisé à l'ingestion (ce module)
ET à la query (tomai-monorepo/apps/server/src/services/rag.service.ts:172-193).

Toute divergence (regex différente, hash différent) casse silencieusement le
recall — le même mot produit deux indices distincts → IDF surévaluée → BM25
inutile.

Référence amont : `rag.service.ts:172-193` (FNV-1a 32-bit, masqué 31-bit, regex
FR incluant œ/æ/ç). Tout changement ici doit être miroir-é côté TS et inversement,
ou les deux doivent importer un package partagé (chantier futur, voir ADR-0007).

Source Qdrant : https://qdrant.tech/articles/sparse-vectors
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Caractères acceptés dans un token (miroir du regex JS de rag.service.ts:173) :
# - lettres latines a-z
# - voyelles accentuées FR : à â ä é è ê ë ï î ô ù û ü ÿ
# - ligatures FR : œ æ
# - cédille : ç
# - chiffres
_TOKEN_RE = re.compile(r"[a-zàâäéèêëïîôùûüÿœæç0-9]+")


@dataclass(frozen=True, slots=True)
class SparseVector:
    """Sparse vector au format Qdrant : indices u32 + values f32."""

    indices: list[int]
    values: list[float]

    def __len__(self) -> int:
        return len(self.indices)


def _hash_token_fnv1a(token: str) -> int:
    """
    Hash 32-bit non-signé d'un token (FNV-1a), masqué 31-bit positif.

    Miroir bit-à-bit de rag.service.ts:hashToken (lignes 185-193). Le masque
    & 0x7fffffff réduit l'espace à 31 bits (max ~2.1 milliards) — Qdrant accepte
    la plage u32 complète mais on conserve la parité avec le backend pour que
    le même mot produise le même indice partout.
    """
    h = 2166136261  # FNV offset basis
    for ch in token:
        h = (h ^ ord(ch)) & 0xFFFFFFFF
        h = (h * 16777619) & 0xFFFFFFFF  # FNV prime, modulo 2^32
    return h & 0x7FFFFFFF


def tokenize_fr(text: str) -> list[str]:
    """Tokenise une chaîne française en lowercase + regex FR (miroir rag.service.ts:173)."""
    return _TOKEN_RE.findall(text.lower())


def to_sparse_vector(text: str) -> SparseVector:
    """
    Convertit un texte en sparse vector Qdrant prêt à upserter/querier.

    Indices = FNV-1a hash de chaque token unique. Values = compte d'occurrences
    du token dans le texte (term frequency brute). Qdrant calcule l'IDF
    server-side à partir des compteurs cumulés sur la collection.

    Exemples
    --------
    >>> sv = to_sparse_vector("Pythagore et théorème de Pythagore")
    >>> len(sv) == 4  # pythagore, et, theoreme, de
    True
    >>> sv.values[sv.indices.index(_hash_token_fnv1a("pythagore"))] == 2
    True
    """
    tokens = tokenize_fr(text)
    counts: dict[int, int] = {}
    for token in tokens:
        idx = _hash_token_fnv1a(token)
        counts[idx] = counts.get(idx, 0) + 1
    return SparseVector(
        indices=list(counts.keys()),
        values=[float(v) for v in counts.values()],
    )
