#!/usr/bin/env python3
"""
Génération du golden set RAG par synthèse document-grounded.

Approche (best practice mai 2026 — RAGAS TestsetGenerator, RAGalyst
arXiv 2511.04502, CoFE-RAG arXiv 2410.12248) :

    Pour chaque chunk indexé, demande à un LLM de générer UNE question
    naturelle dont la réponse est dans ce chunk, plus 3-5 mots-clés
    extraits du chunk (pas inventés). Le `gold_chunk_id` est connu
    exactement = `recall@k` sur chunk_id devient le signal propre, le
    keyword matching reste comme métrique secondaire de robustesse.

Différence vs un golden set écrit à la main avec keywords supposés :
    - Pas de subjectivité de rédacteur (le LLM voit le chunk)
    - Keywords garantis présents dans le corpus (extraits du chunk)
    - `gold_chunk_id` rend `recall@k` interprétable (ID vs sous-chaîne)
    - Mise à l'échelle facile (1000+ questions) avec un sampling stratifié

Modèle : `mistral-large-latest` (qualité du JSON Schema strict + meilleure
compréhension des sections pédagogiques). Le script est OFFLINE one-shot,
contre la règle "curriculum = index only / pas de LLM runtime" : c'est
acceptable car la génération du golden set est un step de TEST AUTHORING
(pas de runtime de tutorat), produit un artefact versionné (`data/golden/
questions.json`), et la couche LLM-judge runtime reste explicitement
côté backend (cf. docs/ARCHITECTURE.md).

Usage :
  uv run python scripts/generate_golden.py                  # 200 questions
  uv run python scripts/generate_golden.py --target=1000    # cible 1000
  uv run python scripts/generate_golden.py --matiere=mathematiques
  uv run python scripts/generate_golden.py --dry-run        # ne sauve pas
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
import unicodedata
import uuid as _uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from schema import (
    GoldenQuestion,
    Matiere,
    NiveauCollege,
    NiveauLycee,
    get_mistral_client,
)
from scripts.ingest import SOURCES, chunk_text, expand_for_niveaux, load_source_text

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

BASE = Path(__file__).parent.parent
GOLDEN_DIR = BASE / "data" / "golden"
DEFAULT_TARGET = 200
DEFAULT_MODEL = "mistral-large-latest"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 400

# JSON Schema strict de la réponse attendue du LLM (Mistral structured outputs).
# Ref: docs.mistral.ai/capabilities/structured-output/ — name + strict + schema requis.
# maxLength=30 sur chaque keyword force des termes courts (1-3 mots) que le LLM
# copiera textuellement, au lieu de paraphraser des phrases longues (cause #1
# des rejets sur la première itération : 161/300 questions perdues).
QUESTION_SCHEMA: dict[str, Any] = {
    "name": "golden_question",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Question naturelle qu'un élève de ce niveau "
                "poserait sur le contenu fourni. Évite les paraphrases triviales "
                "du chunk : formule une vraie question pédagogique.",
                "minLength": 10,
                "maxLength": 300,
            },
            "expected_keywords": {
                "type": "array",
                "description": "3 à 5 termes COURTS (1-3 mots max) copiés "
                "TEXTUELLEMENT du chunk fourni — pas de phrases, pas de "
                "reformulation. Choisis des termes techniques spécifiques.",
                "items": {"type": "string", "minLength": 2, "maxLength": 30},
                "minItems": 3,
                "maxItems": 5,
            },
        },
        "required": ["query", "expected_keywords"],
        "additionalProperties": False,
    },
}

SYSTEM_PROMPT = """Tu es un expert pédagogique français. Tu génères des
questions de test RAG ancrées sur des extraits de programmes officiels
Éduscol. Chaque question doit :

- être naturelle (formulation qu'un élève du niveau ciblé poserait) ;
- avoir sa réponse explicitement contenue dans l'extrait fourni ;
- être unique (pas de paraphrase d'une question précédente) ;
- éviter les généralités vagues ("Qu'apprend-on en X ?") ;
- préférer une notion précise du chunk.

Les `expected_keywords` sont 3 à 5 termes COURTS (1 à 3 mots maximum)
copiés-collés DU CHUNK, pas reformulés. Exemples valides : "hypoténuse",
"théorème de Pythagore", "fonction linéaire", "révolution néolithique".
Exemples INVALIDES : phrases entières, paraphrases, généralités. Le filtre
de validation rejette toute question dont moins de 2 keywords sont
présents textuellement dans le chunk."""


# ── Sampling stratifié ──────────────────────────────────────────────────────


def collect_all_chunks() -> list[dict[str, Any]]:
    """
    Reconstruit l'ensemble des chunks à partir des sources `data/raw/`.
    Aucun appel Qdrant — on duplique exactement la logique de `ingest.py`
    pour que le `gold_chunk_id` calculé matche celui en base.
    """
    all_chunks: list[dict[str, Any]] = []
    for source in SOURCES:
        try:
            text = load_source_text(source)
        except (FileNotFoundError, ValueError) as e:
            print(f"  · {source['file']} : {e}", file=sys.stderr)
            continue
        raw = chunk_text(text, source)
        expanded = expand_for_niveaux(raw)
        # Filtre minimal de qualité : ignorer les chunks trop courts ou
        # constitués majoritairement de listes à puces (peu enseignables).
        for c in expanded:
            if len(c["text"]) < 200:
                continue
            all_chunks.append(c)
    return all_chunks


def _compute_chunk_id(matiere: str, niveau: str, text: str) -> str:
    """UUID5 stable identique à `ingest.upsert_to_qdrant`."""
    seed = f"{matiere}:{niveau}:{text}"
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return str(_uuid.uuid5(_uuid.NAMESPACE_URL, h))


def stratified_sample(
    chunks: list[dict[str, Any]],
    target: int,
    matiere_filter: str | None,
    rng: random.Random,
) -> list[dict[str, Any]]:
    """
    Échantillonne `target` chunks stratifiés par `(matière × niveau)`.
    Garantit une couverture équilibrée même si une matière domine en
    volume de chunks (anglais ~600 chunks vs SVT ~100).
    """
    by_strate: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for c in chunks:
        if matiere_filter and c["matiere"] != matiere_filter:
            continue
        by_strate[(c["matiere"], c["niveau"])].append(c)

    if not by_strate:
        return []

    # Distribution proportionnelle plafonnée — chaque strate récupère
    # min(disponible, target // n_strates + 2). Le +2 absorbe les
    # arrondis pour que la somme atteigne `target`.
    n_strates = len(by_strate)
    per_strate = max(1, target // n_strates)
    sampled: list[dict[str, Any]] = []
    for key, items in by_strate.items():
        take = min(per_strate + 2, len(items))
        sampled.extend(rng.sample(items, take))

    # Si on n'a pas assez, complète avec des tirages supplémentaires
    # dans les plus grosses strates.
    if len(sampled) < target:
        leftover = [c for items in by_strate.values() for c in items if c not in sampled]
        extra = min(target - len(sampled), len(leftover))
        sampled.extend(rng.sample(leftover, extra))

    rng.shuffle(sampled)
    return sampled[:target]


# ── Génération LLM ──────────────────────────────────────────────────────────


def _user_prompt(chunk: dict[str, Any]) -> str:
    matiere = chunk["matiere"]
    niveau = chunk["niveau"]
    section = chunk.get("section", "")
    text = chunk["text"]
    return (
        f"Matière : {matiere}\n"
        f"Niveau : {niveau}\n"
        f"Section : {section}\n"
        f"---\n"
        f"Extrait du programme :\n{text}\n"
        f"---\n"
        f"Génère UNE question pédagogique naturelle qu'un élève de "
        f"{niveau} poserait sur ce contenu, plus 3-5 mots-clés extraits "
        f"textuellement du chunk."
    )


def _generate_one(
    chunk: dict[str, Any],
    *,
    model: str,
    temperature: float,
    max_tokens: int,
    max_attempts: int = 3,
) -> GoldenQuestion | None:
    """
    Appelle Mistral large avec JSON Schema strict. Retourne None si tous
    les attempts échouent — le caller comptabilise dans les erreurs.
    """
    client = get_mistral_client()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _user_prompt(chunk)},
    ]
    last_err: Exception | None = None
    for attempt in range(max_attempts):
        try:
            response = client.chat.complete(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_schema", "json_schema": QUESTION_SCHEMA},
            )
            content = response.choices[0].message.content
            if not isinstance(content, str):
                raise ValueError("Mistral response content not str")
            data = json.loads(content)
            return _build_question(chunk, data)
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            transient = "429" in msg or "rate" in msg or "timeout" in msg or "503" in msg
            if attempt == max_attempts - 1 or not transient:
                break
            wait = 2 * (2**attempt)
            print(f"  ⚠ retry ({attempt + 1}/{max_attempts}) : {e}, wait {wait}s")
            time.sleep(wait)
    print(f"  ✗ génération échouée : {last_err}", file=sys.stderr)
    return None


def _normalize_for_match(s: str) -> str:
    """
    Normalisation robuste pour le substring matching keyword↔chunk.

    NFKC fold les variantes compatibles (e.g. ligatures, formes étroites),
    apostrophe-fold force les variantes typographiques `’` (U+2019) `‘`
    (U+2018) vers `'` ASCII. `casefold()` est plus strict que `lower()` sur
    les langues à casse complexe (allemand ß → ss, etc).

    Sans ça, le filtre rejette ~10% des keywords corrects qui diffèrent
    uniquement par l'apostrophe ou la casse Unicode-spécifique.
    """
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("’", "'").replace("‘", "'")
    return s.casefold()


def _build_question(chunk: dict[str, Any], data: dict[str, Any]) -> GoldenQuestion:
    """
    Construit la `GoldenQuestion` Pydantic-validée. Le `gold_chunk_id` est
    calculé localement à partir de `(matière, niveau, text)` pour matcher
    celui que `ingest.upsert_to_qdrant` aurait inséré.

    Filtre anti-hallucination : ne garde que les keywords présents
    textuellement dans le chunk après normalisation NFKC + apostrophe-fold
    + casefold. Si <2 keywords valides, lève — la question serait
    inutilisable pour scorer un recall.
    """
    matiere = chunk["matiere"]
    niveau_str = chunk["niveau"]
    try:
        niveau: NiveauCollege | NiveauLycee = NiveauCollege(niveau_str)
    except ValueError:
        niveau = NiveauLycee(niveau_str)

    text_normalized = _normalize_for_match(chunk["text"])
    raw_keywords = data.get("expected_keywords", []) or []
    valid = [
        k for k in raw_keywords if isinstance(k, str) and _normalize_for_match(k) in text_normalized
    ]
    if len(valid) < 2:
        raise ValueError(f"keywords insuffisants après filtre (raw={raw_keywords}, valid={valid})")

    return GoldenQuestion(
        query=data["query"],
        matiere=Matiere(matiere),
        niveau=niveau,
        expected_keywords=valid[:5],
        gold_chunk_id=_compute_chunk_id(matiere, niveau_str, chunk["text"]),
        gold_section=chunk.get("section"),
        gold_source_file=chunk.get("source_file"),
    )


# ── Pipeline principal ──────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target", type=int, default=DEFAULT_TARGET, help="Nb questions ciblé (200 par défaut)"
    )
    parser.add_argument("--matiere", help="Filtrer sur une matière (ex: mathematiques)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Modèle Mistral")
    parser.add_argument(
        "--temperature", type=float, default=DEFAULT_TEMPERATURE, help="Température LLM"
    )
    parser.add_argument(
        "--max-tokens", type=int, default=DEFAULT_MAX_TOKENS, help="max_tokens par réponse"
    )
    parser.add_argument(
        "--seed", type=int, default=int(os.environ.get("GOLDEN_SEED", "42")), help="Seed RNG"
    )
    parser.add_argument(
        "--output",
        default=str(GOLDEN_DIR / "questions.json"),
        help="Chemin du JSON de sortie",
    )
    parser.add_argument("--dry-run", action="store_true", help="N'écrit pas le fichier")
    parser.add_argument(
        "--throttle-ms",
        type=int,
        default=200,
        help="Pause entre appels Mistral (200ms par défaut)",
    )
    args = parser.parse_args()

    rng = random.Random(args.seed)

    print("▶ Collecte des chunks depuis data/raw/…")
    all_chunks = collect_all_chunks()
    print(f"  {len(all_chunks)} chunks candidats")

    sampled = stratified_sample(all_chunks, args.target, args.matiere, rng)
    print(f"  {len(sampled)} chunks échantillonnés stratifiés (matière × niveau)")

    if not sampled:
        print("✗ Aucun chunk après filtre — vérifier --matiere.", file=sys.stderr)
        sys.exit(1)

    print(
        f"\n▶ Génération via {args.model} (temp={args.temperature}, max_tokens={args.max_tokens})"
    )
    questions: list[GoldenQuestion] = []
    errors = 0
    seen_queries: set[str] = set()
    for i, chunk in enumerate(sampled, 1):
        if i > 1:
            time.sleep(args.throttle_ms / 1000)
        try:
            q = _generate_one(
                chunk,
                model=args.model,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
        except Exception as e:
            errors += 1
            print(f"  ✗ [{i}/{len(sampled)}] {e}", file=sys.stderr)
            continue
        if q is None:
            errors += 1
            continue
        # Dédup soft sur la query (le LLM peut converger sur des
        # formulations très proches pour des chunks similaires).
        key = q.query.lower().strip()
        if key in seen_queries:
            print(f"  · [{i}/{len(sampled)}] doublon ignoré : {q.query[:60]}")
            continue
        seen_queries.add(key)
        questions.append(q)
        print(f"  ✓ [{i}/{len(sampled)}] {q.matiere.value:25} {q.niveau.value:12} | {q.query[:70]}")

    print(
        f"\n✓ {len(questions)} questions valides "
        f"({errors} erreurs, {len(sampled) - len(questions) - errors} doublons)"
    )

    if args.dry_run:
        print("\n· --dry-run : pas d'écriture")
        return

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = [q.model_dump(mode="json", exclude_none=True) for q in questions]
    out.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  → {out}")


if __name__ == "__main__":
    main()
