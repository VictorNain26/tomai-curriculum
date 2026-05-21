#!/usr/bin/env python3
"""
Génère la fixture de parité BM25 Python ↔ TS.

Run :
  uv run python scripts/dump_bm25_fixture.py > path/to/bm25_parity.json

La fixture est consommée par
`apps/server/src/tests/bm25-parity.test.ts` côté monorepo pour vérifier
que le tokeniser TS produit exactement les mêmes indices/values que le
tokeniser Python sur des chaînes françaises avec accents, ligatures, et
ponctuations variées.

Toute divergence fait casser la CI — c'est volontaire. Le hash BM25 fait
partie du contrat d'index Qdrant : si Python ingère avec un indice et que
TS query avec un autre, l'IDF côté Qdrant devient incohérent et le recall
chute silencieusement.
"""

from __future__ import annotations

import io
import json
import sys

from schema.bm25 import _hash_token_fnv1a, tokenize_fr

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


SAMPLES = [
    "Pythagore et théorème de Pythagore",
    "L'égalité de deux fractions",
    "Histoire-Géographie au cycle 4 : la Renaissance européenne",
    "L'œuvre d'art au Moyen Âge",
    "L'ADN et l'évolution des espèces",
    "œuvre, ça marche, déjà, où",
    "",
    "123 456 nombres",
    "Café, naïveté, façon, hôtel",
    "Aujourd'hui les élèves apprennent le théorème.",
]


def main() -> None:
    fixtures = []
    for s in SAMPLES:
        tokens = tokenize_fr(s)
        token_hashes = [[t, _hash_token_fnv1a(t)] for t in tokens]
        fixtures.append({"text": s, "tokens": list(tokens), "token_hashes": token_hashes})
    print(json.dumps(fixtures, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
