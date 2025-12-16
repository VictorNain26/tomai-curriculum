#!/usr/bin/env python3
"""
CLI pour la gestion du dataset curriculum TomAI.

Usage:
    uv run curriculum validate                    # Valide tous les fichiers JSONL
    uv run curriculum validate --niveau=cinquieme # Valide un niveau spécifique
    uv run curriculum stats                       # Affiche les statistiques
    uv run curriculum ingest                      # Ingère dans Qdrant
    uv run curriculum ingest --dry-run            # Simulation
"""

import json
import os
import sys
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich import print as rprint
from rich.console import Console
from rich.table import Table

# Add parent to path for schema import
sys.path.insert(0, str(Path(__file__).parent.parent))

from schema import Document, Matiere, NiveauCollege, NiveauLycee

app = typer.Typer(name="curriculum", help="Gestion du dataset curriculum TomAI")
console = Console()

DATA_DIR = Path(__file__).parent.parent / "data" / "processed"


def get_all_jsonl_files(niveau: str | None = None, matiere: str | None = None) -> list[Path]:
    """Récupère tous les fichiers JSONL du dataset."""
    files = []
    for cycle_dir in DATA_DIR.iterdir():
        if not cycle_dir.is_dir():
            continue
        for niveau_dir in cycle_dir.iterdir():
            if not niveau_dir.is_dir():
                continue
            if niveau and niveau_dir.name != niveau:
                continue
            for jsonl_file in niveau_dir.glob("*.jsonl"):
                if matiere and jsonl_file.stem != matiere:
                    continue
                files.append(jsonl_file)
    return sorted(files)


def validate_jsonl_file(file_path: Path) -> tuple[int, int, list[str]]:
    """
    Valide un fichier JSONL.

    Returns:
        (valid_count, error_count, error_messages)
    """
    valid = 0
    errors = 0
    messages = []

    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                Document.model_validate(data)
                valid += 1
            except json.JSONDecodeError as e:
                errors += 1
                messages.append(f"Line {line_num}: Invalid JSON - {e}")
            except ValidationError as e:
                errors += 1
                messages.append(f"Line {line_num}: {e.errors()[0]['msg']}")

    return valid, errors, messages


@app.command()
def validate(
    niveau: Annotated[str | None, typer.Option(help="Filtrer par niveau")] = None,
    matiere: Annotated[str | None, typer.Option(help="Filtrer par matière")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Afficher les détails")] = False,
):
    """Valide les fichiers JSONL du dataset."""
    files = get_all_jsonl_files(niveau, matiere)

    if not files:
        rprint("[yellow]Aucun fichier JSONL trouvé.[/yellow]")
        raise typer.Exit(0)

    total_valid = 0
    total_errors = 0

    table = Table(title="Validation des fichiers JSONL")
    table.add_column("Fichier", style="cyan")
    table.add_column("Valides", style="green", justify="right")
    table.add_column("Erreurs", style="red", justify="right")
    table.add_column("Status")

    for file_path in files:
        relative = file_path.relative_to(DATA_DIR)
        valid, errors, messages = validate_jsonl_file(file_path)
        total_valid += valid
        total_errors += errors

        status = "OK" if errors == 0 else "FAIL"
        table.add_row(str(relative), str(valid), str(errors), status)

        if verbose and messages:
            for msg in messages[:5]:  # Limit to 5 errors per file
                rprint(f"  [red]{msg}[/red]")

    console.print(table)
    rprint(f"\n[bold]Total: {total_valid} valides, {total_errors} erreurs[/bold]")

    if total_errors > 0:
        raise typer.Exit(1)


@app.command()
def stats():
    """Affiche les statistiques du dataset."""
    files = get_all_jsonl_files()

    if not files:
        rprint("[yellow]Aucun fichier JSONL trouvé.[/yellow]")
        raise typer.Exit(0)

    table = Table(title="Statistiques du Dataset")
    table.add_column("Niveau", style="cyan")
    table.add_column("Matière", style="magenta")
    table.add_column("Documents", justify="right")
    table.add_column("Tokens (approx)", justify="right")

    total_docs = 0
    total_tokens = 0

    for file_path in files:
        niveau = file_path.parent.name
        matiere = file_path.stem
        doc_count = 0
        token_count = 0

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    doc_count += 1
                    # Approximation: 1 token ≈ 4 caractères
                    token_count += len(data.get("content", "")) // 4
                except json.JSONDecodeError:
                    pass

        total_docs += doc_count
        total_tokens += token_count
        table.add_row(niveau, matiere, str(doc_count), f"~{token_count:,}")

    console.print(table)
    rprint(f"\n[bold]Total: {total_docs} documents, ~{total_tokens:,} tokens[/bold]")


@app.command()
def ingest(
    niveau: Annotated[str | None, typer.Option(help="Filtrer par niveau")] = None,
    matiere: Annotated[str | None, typer.Option(help="Filtrer par matière")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Simulation sans écriture")] = False,
    qdrant_url: Annotated[str | None, typer.Option(envvar="QDRANT_URL")] = None,
    qdrant_api_key: Annotated[str | None, typer.Option(envvar="QDRANT_API_KEY")] = None,
    collection: Annotated[str, typer.Option(envvar="QDRANT_COLLECTION")] = "tomai_educational",
):
    """Ingère les documents dans Qdrant."""
    if not dry_run and (not qdrant_url or not qdrant_api_key):
        rprint("[red]QDRANT_URL et QDRANT_API_KEY requis pour l'ingestion[/red]")
        raise typer.Exit(1)

    files = get_all_jsonl_files(niveau, matiere)

    if not files:
        rprint("[yellow]Aucun fichier JSONL trouvé.[/yellow]")
        raise typer.Exit(0)

    # Validate first
    rprint("[bold]1. Validation...[/bold]")
    total_docs = 0
    documents = []

    for file_path in files:
        niveau_name = file_path.parent.name
        matiere_name = file_path.stem
        cycle = file_path.parent.parent.name

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    doc = Document.model_validate(data)
                    documents.append({
                        "niveau": niveau_name,
                        "matiere": matiere_name,
                        "cycle": cycle,
                        "doc": doc,
                    })
                    total_docs += 1
                except (json.JSONDecodeError, ValidationError) as e:
                    rprint(f"[red]Erreur validation: {e}[/red]")
                    raise typer.Exit(1)

    rprint(f"   [green]OK[/green] {total_docs} documents valides")

    if dry_run:
        rprint("\n[yellow]Mode dry-run: ingestion ignorée[/yellow]")
        raise typer.Exit(0)

    # Actual ingestion would go here
    rprint(f"\n[bold]2. Ingestion vers Qdrant ({collection})...[/bold]")
    rprint("[yellow]TODO: Implémenter ingestion Qdrant[/yellow]")


if __name__ == "__main__":
    app()
