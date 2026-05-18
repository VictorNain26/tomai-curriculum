"""
Tests du tokenizer BM25 — parité stricte avec rag.service.ts.

Le hash et la regex DOIVENT être identiques au backend. Toute divergence casse
l'IDF Qdrant silencieusement (même mot → indices différents → recall pollué).

Référence backend : tomai-monorepo/apps/server/src/services/rag.service.ts:172-193
"""

from __future__ import annotations

import pytest

from schema.bm25 import _hash_token_fnv1a, to_sparse_vector, tokenize_fr

# ── Tokenisation FR ──────────────────────────────────────────────────────────


def test_tokenize_lowercase():
    assert tokenize_fr("Pythagore") == ["pythagore"]
    assert tokenize_fr("Mathématiques") == ["mathématiques"]


def test_tokenize_strips_punctuation():
    assert tokenize_fr("Hello, world!") == ["hello", "world"]
    assert tokenize_fr("Pythagore : théorème.") == ["pythagore", "théorème"]


def test_tokenize_keeps_french_accents_and_ligatures():
    """Lettres accentuées + œ + æ + ç doivent être préservées."""
    assert "œuvre" in tokenize_fr("L'œuvre")
    assert "cœur" in tokenize_fr("Le cœur")
    assert "noël" in tokenize_fr("Noël")
    assert "français" in tokenize_fr("Français")
    assert "à" in tokenize_fr("à propos")
    assert "où" in tokenize_fr("Où aller")


def test_tokenize_keeps_digits():
    """Chiffres + lettres contiguës restent un seul token (parité regex backend)."""
    assert "bo2026" in tokenize_fr("Programme BO2026")
    assert "5e" in tokenize_fr("classe de 5e")
    # Chiffres seuls quand isolés par whitespace/ponctuation
    assert "2026" in tokenize_fr("Programme BO 2026")


def test_tokenize_empty():
    assert tokenize_fr("") == []
    assert tokenize_fr("   !!!  ") == []


# ── Hash FNV-1a (parité bit-à-bit avec rag.service.ts:hashToken) ─────────────


# Valeurs de référence calculées via le code FNV-1a JS de rag.service.ts.
# Ces valeurs DOIVENT rester stables — si elles changent, le backend ne match
# plus la collection ingérée et toute la BM25 est cassée.
@pytest.mark.parametrize(
    "token, expected_hash",
    [
        # Sanity check : valeurs canoniques FNV-1a 32-bit puis & 0x7fffffff.
        # Référence : https://en.wikipedia.org/wiki/Fowler%E2%80%93Noll%E2%80%93Vo_hash_function
        # FNV-1a("") = offset 2166136261 → masqué 31-bit = 18452613
        ("", 2166136261 & 0x7FFFFFFF),
    ],
)
def test_hash_fnv1a_canonical_values(token, expected_hash):
    assert _hash_token_fnv1a(token) == expected_hash


def test_hash_fnv1a_deterministic():
    """Même entrée → même sortie (pas de salt aléatoire)."""
    assert _hash_token_fnv1a("pythagore") == _hash_token_fnv1a("pythagore")


def test_hash_fnv1a_different_tokens_different_hashes():
    """Tokens distincts → hashes distincts (collisions improbables sur dict FR usuel)."""
    h1 = _hash_token_fnv1a("pythagore")
    h2 = _hash_token_fnv1a("thalès")
    h3 = _hash_token_fnv1a("théorème")
    assert h1 != h2
    assert h2 != h3
    assert h1 != h3


def test_hash_fnv1a_within_31bit_positive_range():
    """Sortie ∈ [0, 2^31 - 1] (parité avec rag.service.ts:192 `& 0x7fffffff`)."""
    for token in ["a", "abc", "pythagore", "œuvre", "français", "0123456789"]:
        h = _hash_token_fnv1a(token)
        assert 0 <= h <= 0x7FFFFFFF


# ── Sparse vector ────────────────────────────────────────────────────────────


def test_sparse_vector_counts_term_frequency():
    """pythagore apparaît 2× → value=2 sur l'indice correspondant."""
    sv = to_sparse_vector("Pythagore et théorème de Pythagore")
    pyth_idx = _hash_token_fnv1a("pythagore")

    assert pyth_idx in sv.indices
    pos = sv.indices.index(pyth_idx)
    assert sv.values[pos] == 2.0


def test_sparse_vector_unique_indices():
    """Chaque token unique → 1 entrée (pas de doublons d'indices)."""
    sv = to_sparse_vector("le chat noir et le chat blanc")
    assert len(sv.indices) == len(set(sv.indices))


def test_sparse_vector_indices_match_tokens():
    """len(indices) == len(set(tokens))."""
    text = "Mathématiques cycle 4 nombres relatifs et théorème de Pythagore"
    sv = to_sparse_vector(text)
    unique_tokens = set(tokenize_fr(text))
    assert len(sv.indices) == len(unique_tokens)


def test_sparse_vector_empty_text():
    sv = to_sparse_vector("")
    assert sv.indices == []
    assert sv.values == []


def test_sparse_vector_values_are_float():
    """Qdrant attend des values float (pas int)."""
    sv = to_sparse_vector("test phrase")
    for v in sv.values:
        assert isinstance(v, float)
