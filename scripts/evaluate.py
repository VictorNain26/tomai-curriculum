#!/usr/bin/env python3
"""
Evaluation RAG avec RAGAS + Mistral natif (souverainete EU).

Usage :
  uv run python scripts/evaluate.py --collection=tomai_educational
  uv run python scripts/evaluate.py --questions=data/golden/questions.json

Metriques calculees (sans OpenAI) :
  - faithfulness       : la reponse est-elle fidele au contexte recupere ?
  - answer_relevancy   : la reponse repond-elle a la question ?
  - context_precision  : les chunks recuperes sont-ils pertinents ?
  - context_recall     : le contexte couvre-t-il la reponse attendue ?
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

BASE = Path(__file__).parent.parent

# Questions de test integrees (suffisent pour un premier run)
DEFAULT_QUESTIONS = [
    {
        "question": "Comment calcule-t-on le perimetre d un rectangle ?",
        "ground_truth": "P = 2 x (longueur + largeur).",
        "matiere": "mathematiques",
    },
    {
        "question": "Qu est-ce qu un nombre relatif ?",
        "ground_truth": "Un nombre relatif est un nombre qui peut etre positif ou negatif, ou nul.",
        "matiere": "mathematiques",
    },
    {
        "question": "Quelles sont les grandes etapes de la Revolution francaise ?",
        "ground_truth": "La Revolution francaise debute en 1789 avec la prise de la Bastille.",
        "matiere": "histoire_geo",
    },
    {
        "question": "Comment fonctionne la photosynthese ?",
        "ground_truth": "Les plantes transforment lumiere + CO2 + eau en glucose + dioxygene.",
        "matiere": "svt",
    },
]


def build_dataset(questions: list[dict], collection: str) -> Any:
    """Construit un dataset RAGAS a partir de questions + retrieval en live."""
    from datasets import Dataset
    from mistralai import Mistral
    from qdrant_client import QdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    mistral = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
    qdrant = QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ.get("QDRANT_API_KEY"),
    )

    rows = []
    for q in questions:
        # Embed la question
        emb = mistral.embeddings.create(model="mistral-embed", inputs=[q["question"]])
        vector = emb.data[0].embedding

        # Retrieval (top 3)
        query_filter = None
        if q.get("matiere"):
            query_filter = Filter(
                must=[FieldCondition(key="matiere", match=MatchValue(value=q["matiere"]))]
            )
        results = qdrant.query_points(
            collection_name=collection,
            query=vector,
            query_filter=query_filter,
            limit=3,
            with_payload=True,
        )
        contexts = [r.payload["text"] for r in results.points]

        # Generation socratique
        system = (
            "Tu es un tuteur socratique pour eleves de 5eme. "
            "Utilise uniquement le contexte fourni. Ne donne jamais la reponse directement."
        )
        context_str = "\n\n".join(contexts)
        resp = mistral.chat.complete(
            model="mistral-large-latest",
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": f"Contexte :\n{context_str}\n\nQuestion : {q['question']}",
                },
            ],
            temperature=0.3,
            max_tokens=300,
        )
        answer = resp.choices[0].message.content

        rows.append(
            {
                "question": q["question"],
                "answer": answer,
                "contexts": contexts,
                "ground_truth": q.get("ground_truth", ""),
            }
        )

    return Dataset.from_list(rows)


def run_evaluation(collection: str, questions_file: str | None) -> None:
    from ragas import evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import answer_relevancy, context_precision, faithfulness

    # Charge les questions
    if questions_file and Path(questions_file).exists():
        questions = json.loads(Path(questions_file).read_text(encoding="utf-8"))
        print(f"Questions chargees depuis {questions_file} : {len(questions)}")
    else:
        questions = DEFAULT_QUESTIONS
        print(f"Questions integrees par defaut : {len(questions)}")

    print("\nConstruction du dataset (retrieval live)…")
    dataset = build_dataset(questions, collection)
    print(f"Dataset : {len(dataset)} lignes")

    # Config RAGAS avec Mistral natif via LangChain wrapper
    # Note : ragas >= 0.4 supporte Mistral directement via llm_factory si disponible
    # On utilise le wrapper LangChain comme fallback universel
    from langchain_mistralai import ChatMistralAI, MistralAIEmbeddings

    llm = LangchainLLMWrapper(
        ChatMistralAI(
            model="mistral-large-latest",
            mistral_api_key=os.environ["MISTRAL_API_KEY"],
        )
    )
    embeddings = LangchainEmbeddingsWrapper(
        MistralAIEmbeddings(
            model="mistral-embed",
            mistral_api_key=os.environ["MISTRAL_API_KEY"],
        )
    )

    metrics = [faithfulness, answer_relevancy, context_precision]
    for m in metrics:
        m.llm = llm
        m.embeddings = embeddings

    print("\nEvaluation RAGAS…")
    results = evaluate(dataset=dataset, metrics=metrics)

    print("\n── Resultats ──────────────────────────────")
    df = results.to_pandas()
    print(df[["question", "faithfulness", "answer_relevancy", "context_precision"]].to_string())
    print("\nMoyennes :")
    print(f"  faithfulness       : {df['faithfulness'].mean():.3f}")
    print(f"  answer_relevancy   : {df['answer_relevancy'].mean():.3f}")
    print(f"  context_precision  : {df['context_precision'].mean():.3f}")

    # Export JSON
    out = BASE / "data" / "golden" / "eval_results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(results.scores, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"\nResultats exportes : {out}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--collection",
        default=os.environ.get("QDRANT_COLLECTION", "tomai_educational"),
        help="Nom de la collection Qdrant",
    )
    parser.add_argument("--questions", default=None, help="Fichier JSON de questions (optionnel)")
    args = parser.parse_args()

    run_evaluation(args.collection, args.questions)
