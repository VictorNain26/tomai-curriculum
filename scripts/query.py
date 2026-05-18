#!/usr/bin/env python3
"""
Test du pipeline RAG — requête + réponse socratique.

Usage :
  uv run python scripts/query.py "Comment calculer le PGCD de deux nombres ?"
  uv run python scripts/query.py --matiere=mathematiques "Qu'est-ce qu'une puissance ?"
  uv run python scripts/query.py --top-k=5 "Définition d'un angle"
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

SYSTEM_PROMPT = """Tu es TomAI, un tuteur pédagogique socratique pour les élèves de 5ème.

Règles absolues :
- Ne donne JAMAIS la réponse directement.
- Pose une question de relance qui guide l'élève vers la découverte.
- Utilise UNIQUEMENT les informations du contexte fourni.
- Si le contexte ne contient pas l'information, dis-le clairement.
- Adapte ton langage au niveau 5ème (11-12 ans).

Format de réponse :
1. Valide ou reformule ce que l'élève semble chercher (1 phrase).
2. Pose une question socratique qui l'aide à progresser.
3. Si pertinent, indique une piste (sans donner la solution)."""


def embed_query(query: str) -> list[float]:
    from mistralai import Mistral

    client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
    response = client.embeddings.create(model="mistral-embed", inputs=[query])
    return response.data[0].embedding


def retrieve(
    query_vector: list[float], collection: str, top_k: int, matiere: str | None
) -> list[dict]:
    from qdrant_client import QdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client = QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ.get("QDRANT_API_KEY"),
    )

    query_filter = None
    if matiere:
        query_filter = Filter(must=[FieldCondition(key="matiere", match=MatchValue(value=matiere))])

    results = client.query_points(
        collection_name=collection,
        query=query_vector,
        query_filter=query_filter,
        limit=top_k,
        with_payload=True,
    )

    return [
        {"text": r.payload["text"], "matiere": r.payload["matiere"], "score": r.score}
        for r in results.points
    ]


def generate_response(query: str, context_chunks: list[dict]) -> str:
    from mistralai import Mistral

    client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])

    context = "\n\n---\n\n".join(f"[{c['matiere']}] {c['text']}" for c in context_chunks)

    messages = [
        {
            "role": "user",
            "content": (
                f"Contexte du programme officiel :\n{context}\n\nQuestion de l'élève : {query}"
            ),
        },
    ]

    response = client.chat.complete(
        model="mistral-large-latest",
        messages=messages,
        system=SYSTEM_PROMPT,
        temperature=0.3,
        max_tokens=400,
    )

    return response.choices[0].message.content


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", help="Question à poser")
    parser.add_argument("--matiere", help="Filtre sur une matière")
    parser.add_argument("--top-k", type=int, default=3, help="Nombre de chunks récupérés")
    parser.add_argument(
        "--no-llm", action="store_true", help="Affiche seulement les chunks (sans LLM)"
    )
    args = parser.parse_args()

    if not args.query:
        parser.print_help()
        sys.exit(0)

    collection = os.environ.get("QDRANT_COLLECTION", "tomai_educational")

    print(f"Requête : {args.query}")
    print("Embedding…", end=" ", flush=True)
    vector = embed_query(args.query)
    print("OK")

    print(f"Retrieval (top-{args.top_k})…", end=" ", flush=True)
    chunks = retrieve(vector, collection, args.top_k, args.matiere)
    print(f"{len(chunks)} chunks")

    print("\n── Contexte récupéré ──────────────────────────")
    for i, c in enumerate(chunks, 1):
        print(f"[{i}] [{c['matiere']}] score={c['score']:.3f}")
        print(f"    {c['text'][:200]}…")

    if args.no_llm:
        return

    print("\n── Réponse TomAI ──────────────────────────────")
    response = generate_response(args.query, chunks)
    print(response)


if __name__ == "__main__":
    main()
