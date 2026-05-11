#!/usr/bin/env python3
"""
Évaluation LLM-judge RAG : Faithfulness + Response Relevancy.

Implémente les métriques de qualité de génération définies par RAGAS, mais
avec un judge **Mistral** (souveraineté EU stricte, cf. D11/D12 spec RAG
overhaul mai 2026). Pas de dépendance au package `ragas` qui suppose OpenAI.

Métriques :
- **Faithfulness** : score 0-1, proportion des claims de la réponse qui sont
  supportés par les contextes récupérés. Pipeline : extraction des claims via
  LLM → verdict NLI claim-par-claim → score = supported / total.
- **Response Relevancy** : score 0-1, similarité cosine moyenne entre la
  question originale et N questions hypothétiques re-générées depuis la
  réponse. Élevé si la réponse adresse précisément la question.

Cross-model (D12) : `cross_validate` exécute la même évaluation avec 2 judges
(Mistral Large + Magistral) et expose le delta. Un désaccord élevé signale un
échantillon à revoir humainement.

Sources :
- Spec D11/D12 : docs/specs/2026-05-09-rag-overhaul-design.md
- ADR-0001 : docs/adr/0001-rag-overhaul.md
- RAGAS Faithfulness : https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/
- RAGAS Response Relevancy : https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_relevance/
- Mistral chat API : https://docs.mistral.ai/api/

Usage :
    uv run python scripts/evaluate_judge.py run \\
        --input eval_runs/2026-05-11.json --judge mistral-large-latest

    uv run python scripts/evaluate_judge.py cross-validate \\
        --input eval_runs/2026-05-11.json
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv
from mistralai import Mistral
from mistralai.models import SDKError
from rich import print as rprint

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.ingest_lib import (  # noqa: E402
    EMBEDDING_MODEL,
    generate_embeddings_batch,
    normalize_vector,
)

load_dotenv()

app = typer.Typer(name="evaluate-judge", help="LLM-judge RAG eval (Mistral, EU sovereignty)")

# D4 spec : models EU souverains pour judging
JUDGE_PRIMARY = "mistral-large-latest"
JUDGE_CROSS = "magistral-medium-latest"
RESPONSE_RELEVANCY_N_QUESTIONS = 3


# =============================================================================
# Prompts (FR — corpus pédagogique français)
# =============================================================================


CLAIM_EXTRACTION_PROMPT = """\
Tu reçois une réponse à analyser. Extrait toutes les affirmations factuelles
distinctes qu'elle contient (1 affirmation = 1 fait vérifiable, sans
combinaison artificielle).

Réponds STRICTEMENT en JSON : {{"claims": ["claim 1", "claim 2", ...]}}.

Réponse à analyser :
{answer}
"""

CLAIM_VERIFICATION_PROMPT = """Tu reçois des contextes de référence et une affirmation à vérifier. \
L'affirmation est-elle SUPPORTÉE par les contextes (déductible sans \
spéculation) ?

Contextes :
{contexts}

Affirmation : {claim}

Réponds STRICTEMENT en JSON : {{"supported": true/false, "reason": "..."}}.
"""

RELEVANCY_QUESTION_GEN_PROMPT = """\
Tu reçois une réponse. Génère {n} questions DISTINCTES auxquelles cette
réponse pourrait raisonnablement répondre. Les questions doivent être
formulées comme un élève les poserait.

Réponds STRICTEMENT en JSON : {{"questions": ["q1", "q2", ...]}}.

Réponse :
{answer}
"""


# =============================================================================
# Mistral chat helper
# =============================================================================


def chat_json(
    client: Mistral,
    model: str,
    prompt: str,
    max_retries: int = 3,
    base_delay: float = 2.0,
) -> dict:
    """
    Appel chat Mistral attendu en JSON, avec retry sur 429.

    Si le modèle renvoie du JSON malformé, lève ValueError (à catch par
    l'appelant qui décide d'un fallback ou d'un skip).
    """
    for attempt in range(max_retries):
        try:
            response = client.chat.complete(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except SDKError as e:
            if e.raw_response.status_code != 429 or attempt >= max_retries - 1:
                raise
            wait = base_delay * (3**attempt) + 5
            rprint(f"[yellow]429 (essai {attempt + 1}/{max_retries}), attente {wait:.0f}s[/yellow]")
            time.sleep(wait)
        except json.JSONDecodeError as e:
            raise ValueError(f"Modèle {model} a renvoyé du JSON invalide : {e}") from e

    raise RuntimeError(f"Échec après {max_retries} tentatives sur {model}")


# =============================================================================
# Faithfulness
# =============================================================================


def extract_claims(client: Mistral, model: str, answer: str) -> list[str]:
    """Extrait la liste des claims factuels d'une réponse via LLM."""
    payload = chat_json(client, model, CLAIM_EXTRACTION_PROMPT.format(answer=answer))
    claims = payload.get("claims", [])
    if not isinstance(claims, list):
        raise ValueError(f"Format claims invalide : {claims!r}")
    return [str(c).strip() for c in claims if str(c).strip()]


def verify_claim(client: Mistral, model: str, claim: str, contexts: list[str]) -> tuple[bool, str]:
    """Verdict NLI : claim supporté par contexts ? Retourne (supported, reason)."""
    contexts_block = "\n---\n".join(contexts)
    payload = chat_json(
        client,
        model,
        CLAIM_VERIFICATION_PROMPT.format(contexts=contexts_block, claim=claim),
    )
    supported = bool(payload.get("supported", False))
    reason = str(payload.get("reason", ""))
    return supported, reason


def faithfulness_score(client: Mistral, model: str, answer: str, contexts: list[str]) -> dict:
    """
    Score Faithfulness 0-1 = #claims_supportés / #claims_totaux.

    Edge case : réponse sans claim factuel → score = 1.0 (vacuously true,
    convention RAGAS).
    """
    claims = extract_claims(client, model, answer)
    if not claims:
        return {"score": 1.0, "claims": [], "details": []}

    details: list[dict] = []
    supported_count = 0
    for claim in claims:
        ok, reason = verify_claim(client, model, claim, contexts)
        details.append({"claim": claim, "supported": ok, "reason": reason})
        if ok:
            supported_count += 1

    return {
        "score": supported_count / len(claims),
        "claims": claims,
        "details": details,
    }


# =============================================================================
# Response Relevancy
# =============================================================================


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity sur vecteurs déjà normalisés (dot product)."""
    return sum(x * y for x, y in zip(a, b, strict=True))


def generate_hypothetical_questions(
    client: Mistral, model: str, answer: str, n: int = RESPONSE_RELEVANCY_N_QUESTIONS
) -> list[str]:
    """Génère n questions distinctes auxquelles `answer` pourrait répondre."""
    payload = chat_json(client, model, RELEVANCY_QUESTION_GEN_PROMPT.format(n=n, answer=answer))
    questions = payload.get("questions", [])
    if not isinstance(questions, list):
        raise ValueError(f"Format questions invalide : {questions!r}")
    return [str(q).strip() for q in questions if str(q).strip()][:n]


def response_relevancy_score(client: Mistral, judge_model: str, question: str, answer: str) -> dict:
    """
    Score 0-1 = cosine moyen(embed(question), embed(question_générée)).

    Élevé = la réponse adresse précisément la question. Bas = la réponse part
    en hors-sujet ou répond à une autre question.
    """
    generated = generate_hypothetical_questions(client, judge_model, answer)
    if not generated:
        return {"score": 0.0, "generated_questions": []}

    # Re-utilise le pipeline embed du curriculum (mistral-embed 1024D normalisé)
    texts = [question] + generated
    vectors = generate_embeddings_batch(client, texts)
    query_vec = vectors[0]  # déjà normalisé par generate_embeddings_batch
    similarities = [_cosine(query_vec, normalize_vector(v)) for v in vectors[1:]]
    return {
        "score": sum(similarities) / len(similarities),
        "generated_questions": generated,
        "similarities": similarities,
    }


# =============================================================================
# Cross-validation (D12)
# =============================================================================


def cross_validate(
    client: Mistral,
    samples: list[dict],
    judge_a: str = JUDGE_PRIMARY,
    judge_b: str = JUDGE_CROSS,
) -> dict:
    """
    Exécute Faithfulness + Response Relevancy avec 2 judges, expose le désaccord.

    Chaque sample doit avoir les clés : `question`, `answer`, `contexts` (list[str]).
    Retourne un dict avec :
    - scores_a, scores_b : listes de dicts {faithfulness, response_relevancy}
    - mean_delta_faithfulness, mean_delta_relevancy : moyenne |scores_a - scores_b|
    - flagged : indices des samples avec delta > 0.3 (à revoir humainement)
    """
    scores_a: list[dict] = []
    scores_b: list[dict] = []

    for sample in samples:
        question = sample["question"]
        answer = sample["answer"]
        contexts = sample.get("contexts", [])

        f_a = faithfulness_score(client, judge_a, answer, contexts)
        f_b = faithfulness_score(client, judge_b, answer, contexts)
        r_a = response_relevancy_score(client, judge_a, question, answer)
        r_b = response_relevancy_score(client, judge_b, question, answer)

        scores_a.append({"faithfulness": f_a["score"], "response_relevancy": r_a["score"]})
        scores_b.append({"faithfulness": f_b["score"], "response_relevancy": r_b["score"]})

    deltas_f = [
        abs(a["faithfulness"] - b["faithfulness"]) for a, b in zip(scores_a, scores_b, strict=True)
    ]
    deltas_r = [
        abs(a["response_relevancy"] - b["response_relevancy"])
        for a, b in zip(scores_a, scores_b, strict=True)
    ]
    flagged = [
        i for i, (df, dr) in enumerate(zip(deltas_f, deltas_r, strict=True)) if max(df, dr) > 0.3
    ]

    return {
        "judge_a": judge_a,
        "judge_b": judge_b,
        "scores_a": scores_a,
        "scores_b": scores_b,
        "mean_delta_faithfulness": sum(deltas_f) / len(deltas_f) if deltas_f else 0.0,
        "mean_delta_relevancy": sum(deltas_r) / len(deltas_r) if deltas_r else 0.0,
        "flagged_samples": flagged,
    }


# =============================================================================
# CLI
# =============================================================================


@app.command()
def run(
    input_file: Annotated[Path, typer.Option("--input", help="JSON avec samples à juger")],
    output: Annotated[Path | None, typer.Option(help="Sortie JSON (sinon stdout)")] = None,
    judge: Annotated[str, typer.Option(help="Modèle judge")] = JUDGE_PRIMARY,
    mistral_api_key: Annotated[str | None, typer.Option(envvar="MISTRAL_API_KEY")] = None,
):
    """Exécute Faithfulness + Response Relevancy sur un fichier de samples."""
    if not mistral_api_key:
        rprint("[red]MISTRAL_API_KEY requis[/red]")
        raise typer.Exit(1)

    samples = json.loads(input_file.read_text(encoding="utf-8"))
    if not isinstance(samples, list):
        rprint("[red]Input doit être une liste de samples[/red]")
        raise typer.Exit(1)

    client = Mistral(api_key=mistral_api_key)
    results: list[dict] = []
    for i, sample in enumerate(samples):
        rprint(f"  [dim]Sample {i + 1}/{len(samples)}...[/dim]")
        f = faithfulness_score(client, judge, sample["answer"], sample.get("contexts", []))
        r = response_relevancy_score(client, judge, sample["question"], sample["answer"])
        results.append(
            {
                "question": sample["question"],
                "answer": sample["answer"],
                "faithfulness": f["score"],
                "response_relevancy": r["score"],
                "details": {
                    "faithfulness": f["details"],
                    "generated_questions": r["generated_questions"],
                },
            }
        )

    avg_f = sum(r["faithfulness"] for r in results) / len(results) if results else 0.0
    avg_r = sum(r["response_relevancy"] for r in results) / len(results) if results else 0.0

    rprint(f"\n[bold]Faithfulness moy.   :[/bold] {avg_f:.3f}")
    rprint(f"[bold]Response Relevancy   :[/bold] {avg_r:.3f}")

    output_data = {
        "judge": judge,
        "embedding_model": EMBEDDING_MODEL,
        "n_samples": len(results),
        "avg_faithfulness": avg_f,
        "avg_response_relevancy": avg_r,
        "results": results,
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")
        rprint(f"\n[green]Résultats écrits dans {output}[/green]")


@app.command("cross-validate")
def cross_validate_cmd(
    input_file: Annotated[Path, typer.Option("--input", help="JSON avec samples")],
    output: Annotated[Path | None, typer.Option(help="Sortie JSON (sinon stdout)")] = None,
    judge_a: Annotated[str, typer.Option(help="Judge primaire")] = JUDGE_PRIMARY,
    judge_b: Annotated[str, typer.Option(help="Judge cross-validation")] = JUDGE_CROSS,
    mistral_api_key: Annotated[str | None, typer.Option(envvar="MISTRAL_API_KEY")] = None,
):
    """Exécute la même éval avec 2 judges EU et expose le désaccord (D12)."""
    if not mistral_api_key:
        rprint("[red]MISTRAL_API_KEY requis[/red]")
        raise typer.Exit(1)

    samples = json.loads(input_file.read_text(encoding="utf-8"))
    client = Mistral(api_key=mistral_api_key)
    result = cross_validate(client, samples, judge_a=judge_a, judge_b=judge_b)

    rprint(f"\n[bold]Δ Faithfulness moy. :[/bold] {result['mean_delta_faithfulness']:.3f}")
    rprint(f"[bold]Δ Relevancy moy.    :[/bold] {result['mean_delta_relevancy']:.3f}")
    rprint(f"[bold]Flagged samples     :[/bold] {len(result['flagged_samples'])}")

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        rprint(f"\n[green]Résultats écrits dans {output}[/green]")


if __name__ == "__main__":
    # Compat : `_cosine` est utilisé par les tests, on s'assure que `math` reste référencé
    assert math is math
    app()
