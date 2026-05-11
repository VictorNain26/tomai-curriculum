#!/usr/bin/env python3
"""
Génère un SMOKE TEST d'évaluation RAG depuis les `typical_questions` curatées.

⚠️ AVERTISSEMENT MÉTHODOLOGIQUE (review §1, contamination train/test)

Les `typical_questions` de chaque document sont AUSSI injectées dans le texte
embeddé (voir `ingest.py:create_embedding_text` → section "Questions fréquentes:").
Conséquence : utiliser ces mêmes questions comme queries d'évaluation crée une
contamination train/test mesurable. Les scores Recall@5 atteindront 0.95+
mécaniquement parce que la query est LITTÉRALEMENT dans le texte indexé, pas
parce que le RAG retrouve sémantiquement le bon document.

CE QUE CE GOLDEN SET DÉTECTE (utile) :
- Bug d'ingestion (typical_questions absentes du texte embeddé alors qu'attendues)
- Crash du pipeline RAG complet (recall = 0.0 partout)
- Désynchronisation des content_hash entre ingestion et server
- Régression majeure du modèle d'embedding (recall passe sous 0.7)

CE QU'IL NE DÉTECTE PAS (besoin d'un golden manuel) :
- Qualité du retrieval pour des queries naturelles d'élèves (différentes des typical)
- Capacité de paraphrase / synonymes
- Queries adversariales ou ambiguës
- Multi-doc relevance

ROADMAP : à compléter par
- Golden manuel curé par profs (queries naturelles, ~50-200 par cellule)
- Génération RAGAS testset (queries synthétiques avec review humaine)

Pourquoi quand même générer ce golden :
- Coût marginal nul (réutilise typical_questions existantes)
- Couverture stratifiée naturelle 154 cellules (niveau × matière)
- Smoke test rapide en CI (< 30s) avant chaque deploy server
- Détecte les régressions majeures sans bloquer le développement

Usage :
    uv run python scripts/generate_golden.py
    uv run python scripts/generate_golden.py --niveau cinquieme --matiere mathematiques
    uv run python scripts/generate_golden.py --max-per-doc 5

Le fichier produit est consommable par `scripts/evaluate.py run`.
"""

import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

sys.path.insert(0, str(Path(__file__).parent.parent))

# Forcer stdout/stderr en UTF-8 sur Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from scripts.ingest import load_documents
from scripts.utils import get_all_jsonl_files

app = typer.Typer(
    name="generate-golden",
    help="Génère un golden set RAG depuis les typical_questions curatées",
)
console = Console()


# Heuristiques de filtrage : on garde les questions qui sont VRAIMENT des
# queries d'élève, pas des reformulations triviales du titre OU du content.
MIN_QUERY_LENGTH = 10
MAX_QUERY_LENGTH = 200
# Nombre de mots du début du content comparés à la query pour le filtre.
# Limite la fenêtre pour éviter qu'un long content fasse passer tout
# (la contamination vient surtout de la phrase qui contient la query).
_CONTENT_HEAD_WORDS = 30
_TITLE_OVERLAP_MAX = 0.7  # Jaccard
_CONTENT_OVERLAP_MAX = 0.6  # Jaccard (un peu plus permissif sur content)


def _is_quality_query(query: str, title: str, content: str = "") -> bool:
    """
    Filtre les questions de mauvaise qualité pour le golden set :
    - Trop courtes (< 10 chars) ou trop longues (> 200 chars)
    - Trop similaires au titre (la query est juste "Title?")
    - Trop similaires au début du content (extraction directe du texte indexé,
      review §3 — auparavant on testait seulement contre title)
    """
    q = query.strip()
    if not (MIN_QUERY_LENGTH <= len(q) <= MAX_QUERY_LENGTH):
        return False

    q_normalized = q.rstrip("?!. ").lower()
    title_normalized = title.rstrip("?!. ").lower()
    q_words = set(q_normalized.split())
    title_words = set(title_normalized.split())

    if q_words and title_words:
        overlap = len(q_words & title_words) / len(q_words | title_words)
        if overlap >= _TITLE_OVERLAP_MAX:
            return False

    # Filtre contre le début du content (review §3)
    if content:
        head = " ".join(content.lower().split()[:_CONTENT_HEAD_WORDS])
        head_words = set(head.split())
        if head_words and q_words:
            head_overlap = len(q_words & head_words) / len(q_words | head_words)
            if head_overlap >= _CONTENT_OVERLAP_MAX:
                return False

    return True


def _build_query_entry(query: str, doc_data: dict, counter: int) -> dict:
    """
    Construit une entrée golden conforme au schema attendu par evaluate.py.

    Champs requis (lus par evaluate.py) : id, query, expected_ids,
    matiere_filter, niveau_filter. Les autres sont ignorés par le runner
    mais servent à l'audit humain ; review §4 a demandé de supprimer
    source_doc_id qui dupliquait expected_ids[0] sans valeur ajoutée.
    """
    doc = doc_data["doc"]
    matiere = doc_data["matiere"]
    return {
        "id": f"auto_{matiere}_{doc_data['niveau']}_{counter:04d}",
        "query": query.strip(),
        "expected_ids": [doc_data["id"]],
        "matiere_filter": matiere,
        "niveau_filter": doc_data["niveau"],
        "source": "typical_questions",
        "source_doc_title": doc.title,
    }


@app.command()
def run(
    output: Annotated[
        Path, typer.Option(help="Fichier de sortie JSON")
    ] = Path("data/golden/test_queries_from_typical.json"),
    niveau: Annotated[str | None, typer.Option(help="Filtrer par niveau")] = None,
    matiere: Annotated[str | None, typer.Option(help="Filtrer par matière")] = None,
    max_per_doc: Annotated[
        int,
        typer.Option(
            help=(
                "Max typical_questions retenues par document. Le schema autorise "
                "3-5 questions par doc, défaut 5 = utilise tout. Réduire à 3 pour "
                "limiter la taille du smoke test si CI lent."
            )
        ),
    ] = 5,
) -> None:
    """Extrait les typical_questions et produit un golden set evaluate.py-compatible."""
    files = get_all_jsonl_files(niveau, matiere)
    if not files:
        rprint("[yellow]Aucun JSONL trouvé[/yellow]")
        raise typer.Exit(0)

    docs = load_documents(files)
    rprint(f"\n[bold cyan]Génération golden set[/bold cyan] depuis {len(docs)} documents")

    queries: list[dict] = []
    stats: dict[str, int] = defaultdict(int)
    counter = 0

    for doc_data in docs:
        doc = doc_data["doc"]
        typical = getattr(doc, "typical_questions", None) or []
        if not typical:
            stats["no_typical"] += 1
            continue

        kept_for_doc = 0
        for q in typical:
            if kept_for_doc >= max_per_doc:
                break
            if not _is_quality_query(q, doc.title, doc.content):
                stats["filtered_quality"] += 1
                continue
            counter += 1
            queries.append(_build_query_entry(q, doc_data, counter))
            kept_for_doc += 1
            stats["kept"] += 1

        if kept_for_doc == 0:
            stats["all_filtered"] += 1

    # Stratification : nb queries par (niveau, matière)
    distribution: dict[tuple[str, str], int] = defaultdict(int)
    for q in queries:
        distribution[(q["niveau_filter"], q["matiere_filter"])] += 1

    output_data = {
        "version": "1.0.0",
        "schema": "expected_ids",
        "kind": "smoke_test",  # PAS un benchmark — voir docstring du module
        "source": "typical_questions",
        "generated_at": datetime.now(UTC).isoformat(),
        "description": (
            "SMOKE TEST RAG — pas un benchmark de qualité. Les queries sont "
            "extraites des typical_questions présentes dans le texte embeddé "
            "(contamination train/test assumée). Sert à détecter les bugs "
            "majeurs (ingestion cassée, désync content_hash, modèle d'embedding "
            "régressé). Compléter par un golden manuel curé par profs pour "
            "mesurer la qualité réelle du retrieval sur queries naturelles."
        ),
        # Targets calibrées POUR LE SMOKE TEST : on attend des scores élevés
        # parce que la query est dans le texte embeddé. En dessous = vrai bug.
        # PAS d'extrapolation possible aux queries réelles d'élèves.
        "metrics_target": {
            "recall@5": 0.95,  # contamination → 95%+ attendu mécaniquement
            "recall@10": 0.98,
            "precision@5": 0.20,  # plafond mathématique avec expected_ids = 1 doc
            "mrr": 0.85,
            "ndcg@10": 0.90,
        },
        "queries": queries,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    rprint(f"\n[green]✓ {len(queries)} queries générées[/green] → {output}")
    rprint(f"  - {stats['kept']} retenues")
    rprint(f"  - {stats['filtered_quality']} filtrées (trop courtes / proches du titre)")
    rprint(f"  - {stats['no_typical']} docs sans typical_questions")
    rprint(f"  - {stats['all_filtered']} docs où toutes les questions ont été filtrées")

    table = Table(title="Distribution par (niveau × matière)")
    table.add_column("Niveau", style="cyan")
    table.add_column("Matière", style="magenta")
    table.add_column("Queries", justify="right")

    for (niv, mat), count in sorted(distribution.items(), key=lambda x: -x[1]):
        table.add_row(niv, mat, str(count))

    console.print(table)


if __name__ == "__main__":
    app()
