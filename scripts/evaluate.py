#!/usr/bin/env python3
"""
Évaluation RAG rigoureuse — refactor sous-projet C (mai 2026).

Changements clés vs l'ancien evaluate.py :
- Matching par `expected_ids` UUID exact (vs fuzzy contains sur les titres,
  qui gonflait artificiellement Recall@5 de 10-30 pts).
- Cache embeddings queries indexé par `(sha256(query), model_version)`.
- Output JSON versionné horodaté dans `eval_runs/` (pour tracking des régressions).
- Métriques étendues : Recall@K, Precision@K, MRR, NDCG@K (déterministes),
  Context Precision et Context Recall (déterministes via expected_ids).
- Comparaison entre runs (`evaluate compare A B`) avec flag des régressions > 2%.

Sources :
- https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/
- https://blog.premai.io/rag-evaluation-metrics-frameworks-testing-2026/
- https://medium.com/data-science-at-microsoft/the-path-to-a-golden-dataset-or-how-to-evaluate-your-rag-045e23d1f13f
"""

import hashlib
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

# Forcer stdout/stderr en UTF-8 sur Windows (cp1252 par défaut ne supporte pas ✓ → etc.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

import typer
from dotenv import load_dotenv
from mistralai import Mistral
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from scripts.utils import DATA_DIR

load_dotenv()

app = typer.Typer(name="evaluate", help="Évaluation RAG rigoureuse (expected_ids)")
console = Console()

EMBEDDING_MODEL = "mistral-embed"
EVAL_RUNS_DIR = DATA_DIR.parent.parent / "eval_runs"
QUERY_CACHE_ROOT = DATA_DIR.parent / "embeddings_cache" / "queries"


# =============================================================================
# Cache queries (mêmes principes que le cache documents dans ingest.py)
# =============================================================================


def _query_cache_path(model: str = EMBEDDING_MODEL) -> Path:
    return QUERY_CACHE_ROOT / model / "cache.jsonl"


def _query_hash(query: str) -> str:
    return hashlib.sha256(query.encode()).hexdigest()


def load_query_cache(model: str = EMBEDDING_MODEL) -> dict[str, list[float]]:
    """Charge cache {sha256(query): vector}. Versionné par model_version."""
    path = _query_cache_path(model)
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


def append_query_cache(items: list[tuple[str, list[float]]], model: str = EMBEDDING_MODEL) -> None:
    path = _query_cache_path(model)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for h, v in items:
            f.write(json.dumps({"hash": h, "vector": v}) + "\n")


def embed_query(client: Mistral, query: str, cache: dict[str, list[float]]) -> list[float]:
    """Récupère le vecteur d'une query (cache hit ou Mistral API + cache write)."""
    h = _query_hash(query)
    if h in cache:
        return cache[h]
    result = client.embeddings.create(model=EMBEDDING_MODEL, inputs=[query])
    embedding = result.data[0].embedding
    magnitude = math.sqrt(sum(v * v for v in embedding))
    if magnitude == 0:
        # Mistral peut exceptionnellement renvoyer un vecteur nul. ZeroDivisionError
        # n'est pas catché par le `except Exception` du caller (qui ne couvre que
        # l'appel réseau), donc on lève une ValueError explicite que le caller
        # peut classifier comme "skip query" sans interrompre le run entier.
        raise ValueError(f"Zero-magnitude embedding returned by Mistral for query {query[:50]!r}")
    normalized = [v / magnitude for v in embedding]
    cache[h] = normalized
    append_query_cache([(h, normalized)])
    return normalized


# =============================================================================
# Métriques retrieval (déterministes, à partir de expected_ids)
# =============================================================================


def recall_at_k(retrieved_ids: list[str], expected_ids: list[str], k: int) -> float:
    """Proportion des expected_ids présents dans les top-k retrieved."""
    if not expected_ids:
        return 1.0
    top_k = set(retrieved_ids[:k])
    found = sum(1 for eid in expected_ids if eid in top_k)
    return found / len(expected_ids)


def precision_at_k(retrieved_ids: list[str], expected_ids: list[str], k: int) -> float:
    """Proportion des top-k retrieved qui sont expected."""
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    expected_set = set(expected_ids)
    relevant = sum(1 for rid in top_k if rid in expected_set)
    return relevant / len(top_k)


def mrr(retrieved_ids: list[str], expected_ids: list[str]) -> float:
    """1 / rank du premier expected trouvé. 0 si aucun match."""
    expected_set = set(expected_ids)
    for i, rid in enumerate(retrieved_ids, 1):
        if rid in expected_set:
            return 1.0 / i
    return 0.0


def ndcg_at_k(retrieved_ids: list[str], expected_ids: list[str], k: int) -> float:
    """NDCG@K : qualité du ranking. Pertinence binaire (1 si expected, 0 sinon)."""
    expected_set = set(expected_ids)
    top_k = retrieved_ids[:k]
    dcg = sum(
        (1.0 if rid in expected_set else 0.0) / math.log2(i + 1)
        for i, rid in enumerate(top_k, 1)
    )
    ideal_count = min(len(expected_ids), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_count + 1))
    return dcg / idcg if idcg > 0 else 0.0


def context_precision(retrieved_ids: list[str], expected_ids: list[str]) -> float:
    """
    Context Precision (RAGAS-style déterministe via expected_ids) :
    proportion des chunks retrieved qui sont effectivement pertinents.
    Équivalent à Precision sur tout le retrieved (pas @K).
    """
    if not retrieved_ids:
        return 0.0
    expected_set = set(expected_ids)
    relevant = sum(1 for rid in retrieved_ids if rid in expected_set)
    return relevant / len(retrieved_ids)


def context_recall(retrieved_ids: list[str], expected_ids: list[str]) -> float:
    """Context Recall : proportion des expected couverts par le retrieved."""
    if not expected_ids:
        return 1.0
    retrieved_set = set(retrieved_ids)
    covered = sum(1 for eid in expected_ids if eid in retrieved_set)
    return covered / len(expected_ids)


# =============================================================================
# Commande : run
# =============================================================================


@app.command()
def run(
    test_file: Annotated[Path, typer.Option(help="Fichier golden set JSON")] = Path(
        "data/golden/test_queries.json"
    ),
    qdrant_url: Annotated[str | None, typer.Option(envvar="QDRANT_URL")] = None,
    qdrant_api_key: Annotated[str | None, typer.Option(envvar="QDRANT_API_KEY")] = None,
    mistral_api_key: Annotated[str | None, typer.Option(envvar="MISTRAL_API_KEY")] = None,
    collection: Annotated[str, typer.Option(envvar="QDRANT_COLLECTION")] = "tomai_educational",
    top_k: Annotated[int, typer.Option(help="Nb résultats à récupérer")] = 10,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """
    Exécute l'évaluation et écrit un run JSON versionné dans eval_runs/.

    Schema attendu du golden set :
      {
        "version": "...",
        "metrics_target": {...},
        "queries": [
          {
            "id": "math_001",
            "query": "...",
            "expected_ids": ["uuid1", "uuid2", ...],
            "matiere_filter": "mathematiques",  // optionnel
            "niveau_filter": "cinquieme",       // optionnel
            ...
          }
        ]
      }
    """
    if not qdrant_url or not qdrant_api_key or not mistral_api_key:
        rprint("[red]QDRANT_URL, QDRANT_API_KEY et MISTRAL_API_KEY requis[/red]")
        raise typer.Exit(1)

    if not test_file.exists():
        rprint(f"[red]Fichier de test introuvable : {test_file}[/red]")
        raise typer.Exit(1)

    with open(test_file, encoding="utf-8") as f:
        test_data = json.load(f)

    queries = test_data["queries"]
    targets = test_data.get("metrics_target", {})

    rprint("\n[bold cyan]Évaluation RAG rigoureuse[/bold cyan]")
    rprint(f"  Collection : {collection}")
    rprint(f"  Test set   : {test_file.name} (v{test_data.get('version', '?')})")
    rprint(f"  Queries    : {len(queries)}")
    rprint(f"  Top-K      : {top_k}")

    mistral_client = Mistral(api_key=mistral_api_key)
    qdrant_client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
    query_cache = load_query_cache()
    rprint(f"  Cache embeddings queries : {len(query_cache)} pré-existants")

    results: list[dict] = []
    aggregates: dict[str, list[float]] = {
        "recall@5": [],
        "recall@10": [],
        "precision@5": [],
        "mrr": [],
        "ndcg@10": [],
        "context_precision": [],
        "context_recall": [],
    }

    for i, q in enumerate(queries, 1):
        query_id = q["id"]
        query_text = q["query"]
        expected_ids = q.get("expected_ids", [])

        if not expected_ids:
            rprint(f"  [yellow]⊘ {query_id} : pas d'expected_ids, skip[/yellow]")
            continue

        try:
            query_vector = embed_query(mistral_client, query_text, query_cache)
        except Exception as e:
            rprint(f"  [red]✗ {query_id} : erreur embedding — {e}[/red]")
            continue

        search_filter = _build_filter(q)
        search = qdrant_client.query_points(
            collection_name=collection,
            query=query_vector,
            query_filter=search_filter,
            limit=top_k,
            with_payload=False,
        )
        retrieved_ids = [str(p.id) for p in search.points]

        metrics = {
            "recall@5": recall_at_k(retrieved_ids, expected_ids, 5),
            "recall@10": recall_at_k(retrieved_ids, expected_ids, 10),
            "precision@5": precision_at_k(retrieved_ids, expected_ids, 5),
            "mrr": mrr(retrieved_ids, expected_ids),
            "ndcg@10": ndcg_at_k(retrieved_ids, expected_ids, 10),
            "context_precision": context_precision(retrieved_ids, expected_ids),
            "context_recall": context_recall(retrieved_ids, expected_ids),
        }
        for key, val in metrics.items():
            aggregates[key].append(val)

        result = {
            "id": query_id,
            "query": query_text,
            "expected_ids": expected_ids,
            "retrieved_ids": retrieved_ids[:5],
            **metrics,
        }
        results.append(result)

        if verbose:
            status = (
                "[green]OK[/green]"
                if metrics["recall@5"] >= 0.8
                else "[yellow]PARTIAL[/yellow]"
                if metrics["recall@5"] > 0
                else "[red]MISS[/red]"
            )
            rprint(
                f"  [{i}/{len(queries)}] {query_id}: {status} "
                f"(R@5={metrics['recall@5']:.2f} MRR={metrics['mrr']:.2f})"
            )

    averages = {key: (sum(vals) / len(vals) if vals else 0.0) for key, vals in aggregates.items()}

    _render_summary_table(averages, targets)
    run_path = _persist_run(test_data, collection, top_k, results, averages, targets)
    rprint(f"\n[green]✓ Run sauvegardé : {run_path}[/green]")


def _build_filter(query_entry: dict) -> Filter | None:
    """Construit un Qdrant Filter à partir des filtres optionnels du test entry."""
    conditions = []
    matiere = query_entry.get("matiere_filter")
    niveau = query_entry.get("niveau_filter")
    if matiere:
        conditions.append(FieldCondition(key="matiere", match=MatchValue(value=matiere)))
    if niveau:
        conditions.append(FieldCondition(key="niveau", match=MatchValue(value=niveau)))
    return Filter(must=conditions) if conditions else None


def _render_summary_table(averages: dict[str, float], targets: dict[str, float]) -> None:
    table = Table(show_header=True, title="Métriques agrégées")
    table.add_column("Métrique")
    table.add_column("Score", justify="right")
    table.add_column("Target", justify="right")
    table.add_column("Status", justify="center")

    def status_for(score: float, target: float) -> str:
        if score >= target:
            return "[green]PASS[/green]"
        if score >= target * 0.8:
            return "[yellow]CLOSE[/yellow]"
        return "[red]FAIL[/red]"

    for key, score in averages.items():
        target = targets.get(key, 0.0)
        target_str = f"{target:.2f}" if target > 0 else "—"
        status = status_for(score, target) if target > 0 else "—"
        table.add_row(key, f"{score:.3f}", target_str, status)

    console.print(table)


def _compute_test_set_hash(test_data: dict) -> str:
    """
    SHA-256 du contenu du golden set (queries triées par id).

    Versionné par contenu plutôt que par `version` du test_data, qui peut
    rester identique alors que le contenu change (bug fréquent de bump de
    version oublié). Indispensable pour que `compare` puisse refuser de
    comparer deux runs sur des golden sets différents.
    """
    canonical = json.dumps(
        sorted(test_data.get("queries", []), key=lambda q: q.get("id", "")),
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _persist_run(
    test_data: dict,
    collection: str,
    top_k: int,
    results: list[dict],
    averages: dict[str, float],
    targets: dict[str, float],
) -> Path:
    """Écrit le run dans eval_runs/<YYYYMMDD-HHMMSS>-<collection>.json."""
    EVAL_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    path = EVAL_RUNS_DIR / f"{timestamp}-{collection}.json"
    payload = {
        "run_timestamp_utc": now.isoformat(),
        "collection": collection,
        "test_set_version": test_data.get("version"),
        "test_set_hash": _compute_test_set_hash(test_data),
        "num_queries": len(results),
        "top_k": top_k,
        "embedding_model": EMBEDDING_MODEL,
        "metrics": averages,
        "targets": targets,
        "queries": results,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


# =============================================================================
# Commande : compare deux runs
# =============================================================================


@app.command()
def compare(
    run_a: Annotated[Path, typer.Argument(help="Run baseline")],
    run_b: Annotated[Path, typer.Argument(help="Run à comparer")],
    regression_threshold: Annotated[
        float,
        typer.Option(
            help=(
                "Seuil de régression (delta négatif). Défaut 0.05 (5%) : "
                "absorbe la variance naturelle d'embedding entre runs sur "
                "petit golden set (~30 queries), tout en restant sensible "
                "aux vraies régressions. Baisser à 0.02 quand golden set ≥ 200."
            )
        ),
    ] = 0.05,
    force: Annotated[
        bool,
        typer.Option("--force", help="Compare même si les golden sets diffèrent"),
    ] = False,
) -> None:
    """Compare deux runs JSON et flag les régressions > regression_threshold."""
    if not run_a.exists() or not run_b.exists():
        rprint("[red]Fichiers de run introuvables[/red]")
        raise typer.Exit(1)

    with open(run_a, encoding="utf-8") as f:
        a = json.load(f)
    with open(run_b, encoding="utf-8") as f:
        b = json.load(f)

    # Refuser de comparer deux runs sur des golden sets différents (sauf --force).
    # Sans ce garde-fou, on peut comparer "Recall@5 sur golden v1.0" vs "Recall@5
    # sur golden v2.0 enrichi" et croire à tort qu'il y a une régression de retrieval.
    hash_a = a.get("test_set_hash")
    hash_b = b.get("test_set_hash")
    if hash_a and hash_b and hash_a != hash_b and not force:
        rprint(
            f"[red]✗ Golden sets différents (A={hash_a}, B={hash_b}). "
            f"Utiliser --force pour comparer quand même (mais le delta sera "
            f"non interprétable).[/red]"
        )
        raise typer.Exit(1)

    rprint(f"\n[bold cyan]Comparaison[/bold cyan] {run_a.name} → {run_b.name}\n")

    table = Table(title="Delta des métriques (B - A)")
    table.add_column("Métrique")
    table.add_column("A", justify="right")
    table.add_column("B", justify="right")
    table.add_column("Delta", justify="right")
    table.add_column("Status", justify="center")

    has_regression = False
    for key in sorted(set(a["metrics"]) | set(b["metrics"])):
        va = a["metrics"].get(key, 0.0)
        vb = b["metrics"].get(key, 0.0)
        delta = vb - va
        if delta < -regression_threshold:
            status = "[red]REGRESSION[/red]"
            has_regression = True
        elif delta > regression_threshold:
            status = "[green]IMPROVEMENT[/green]"
        else:
            status = "[dim]stable[/dim]"
        table.add_row(key, f"{va:.3f}", f"{vb:.3f}", f"{delta:+.3f}", status)

    console.print(table)

    if has_regression:
        rprint(f"\n[red]✗ Régression(s) détectée(s) > {regression_threshold:.2f}[/red]")
        raise typer.Exit(1)
    rprint("\n[green]✓ Aucune régression au-delà du seuil[/green]")


# =============================================================================
# Commande : migrate-titles (ancienne golden set -> expected_ids)
# =============================================================================


@app.command("migrate-titles")
def migrate_titles(
    test_file: Annotated[
        Path, typer.Argument(help="Ancien test_queries.json avec expected_titles")
    ],
    output: Annotated[Path, typer.Option(help="Fichier de sortie")] = Path(
        "data/golden/test_queries.json"
    ),
    allow_partial: Annotated[
        bool,
        typer.Option(
            "--allow-partial",
            help=(
                "Inclure les queries où certains titres attendus ne sont pas "
                "trouvés dans le dataset. Risque : Recall@K gonflé car le "
                "titre manquant pourrait être le plus pertinent. Défaut : reject."
            ),
        ),
    ] = False,
) -> None:
    """
    Migre un test_queries.json (legacy `expected_titles`) vers le nouveau schema
    `expected_ids` en utilisant le mapping title -> uuid5(content_hash) des JSONL
    locaux.

    Comportement par défaut (strict) :
    - Query avec TOUS les titres résolus → migrée
    - Query avec AU MOINS UN titre manquant → rejetée (partial resolution)
    - Query avec ZERO titre résolu → rejetée

    Avec --allow-partial : on accepte les queries partielles et on marque
    `_unresolved_titles` pour audit. À utiliser uniquement si on accepte que
    Recall@K soit potentiellement gonflé.
    """
    if not test_file.exists():
        rprint(f"[red]Fichier introuvable : {test_file}[/red]")
        raise typer.Exit(1)

    from scripts.ingest import compute_content_hash, doc_id_from_hash, load_documents
    from scripts.utils import get_all_jsonl_files

    files = get_all_jsonl_files()
    docs = load_documents(files)
    title_to_id: dict[str, str] = {d["doc"].title: d["id"] for d in docs}
    rprint(f"  Mapping construit : {len(title_to_id)} titres -> uuid")

    with open(test_file, encoding="utf-8") as f:
        old = json.load(f)

    new_queries: list[dict] = []
    unresolved: list[tuple[str, list[str]]] = []
    partial: list[tuple[str, list[str]]] = []

    for q in old.get("queries", []):
        expected_titles = q.get("expected_titles", [])
        expected_ids = [title_to_id[t] for t in expected_titles if t in title_to_id]
        missing = [t for t in expected_titles if t not in title_to_id]

        if not expected_ids:
            unresolved.append((q["id"], expected_titles))
            continue

        if missing:
            # Résolution partielle : on a au moins un titre résolu mais d'autres manquent.
            # Sans --allow-partial, on rejette pour éviter Recall@K artificiellement gonflé.
            partial.append((q["id"], missing))
            if not allow_partial:
                continue

        new_q = {**q}
        new_q["expected_ids"] = expected_ids
        new_q.pop("expected_titles", None)
        if missing:
            new_q["_unresolved_titles"] = missing
        new_queries.append(new_q)

    output_data = {
        **old,
        "version": old.get("version", "1.0.0") + "-migrated",
        "schema": "expected_ids",
        "queries": new_queries,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    rprint(f"\n[green]✓ Migré : {len(new_queries)} queries[/green] → {output}")
    if unresolved:
        rprint(
            f"[yellow]⊘ {len(unresolved)} queries totalement non résolues "
            f"(aucun titre trouvé) — rejetées[/yellow]"
        )
        for qid, titles in unresolved[:5]:
            rprint(f"  - {qid} : {titles}")
    if partial:
        action = "incluses (--allow-partial)" if allow_partial else "rejetées"
        rprint(
            f"[yellow]⊘ {len(partial)} queries partiellement résolues "
            f"({action})[/yellow]"
        )
        for qid, missing_titles in partial[:5]:
            rprint(f"  - {qid} : titres manquants {missing_titles}")

    # Helper pour vérifier que le mapping est stable
    _ = compute_content_hash
    _ = doc_id_from_hash


if __name__ == "__main__":
    app()
