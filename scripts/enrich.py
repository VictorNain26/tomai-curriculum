#!/usr/bin/env python3
"""
Enrichissement du dataset TomAI à partir d'un fichier source externe.

Remplace les 12 scripts add_*_chapters.py one-shot (données hardcodées en
Python, append non-idempotent → re-run = duplications silencieuses).

Pipeline :
1. Charger un fichier source (JSON ou JSONL) contenant des documents
2. Valider chaque document via le schema Pydantic strict
3. Dédoublonner contre le JSONL cible (clé = title dans le contexte niveau × matière)
4. Append uniquement les nouveaux (écriture .tmp + rename atomique)
5. Logger les rejets (validation, doublons) sans fail global

Usage :
    uv run python scripts/enrich.py from-json data/sources/new.json \\
        --niveau cinquieme --matiere mathematiques --cycle cycle4

    uv run python scripts/enrich.py from-jsonl data/sources/new.jsonl \\
        --niveau seconde --matiere physique_chimie --cycle lycee --dry-run
"""

import json
import sys
from pathlib import Path
from typing import Annotated

sys.path.insert(0, str(Path(__file__).parent.parent))

import typer
from pydantic import ValidationError
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from schema import Document
from schema.document import Cycle, Matiere, NiveauCollege, NiveauLycee
from scripts.utils import DATA_DIR

app = typer.Typer(
    name="enrich",
    help="Enrichissement du dataset à partir d'une source externe (JSON/JSONL)",
)
console = Console()


def _load_source_json(source: Path) -> list[dict]:
    with open(source, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise typer.BadParameter(
            f"{source}: le JSON doit être une liste de documents "
            f"(trouvé: {type(data).__name__})"
        )
    return data


def _load_source_jsonl(source: Path) -> list[dict]:
    docs: list[dict] = []
    with open(source, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                docs.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise typer.BadParameter(f"{source}:{line_num}: JSON invalide — {e}")
    return docs


def _load_existing_titles(target: Path) -> set[str]:
    """Charge les titres déjà présents dans le JSONL cible (pour dédoublonnage)."""
    if not target.exists():
        return set()
    titles: set[str] = set()
    with open(target, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
                title = doc.get("title", "").strip()
                if title:
                    titles.add(title)
            except json.JSONDecodeError:
                continue
    return titles


def _resolve_target_path(niveau: str, matiere: str, cycle: str) -> Path:
    return DATA_DIR / cycle / niveau / f"{matiere}.jsonl"


def _validate_enums(niveau: str, matiere: str, cycle: str) -> None:
    valid_niveaux = {n.value for n in NiveauCollege} | {n.value for n in NiveauLycee}
    if niveau not in valid_niveaux:
        raise typer.BadParameter(
            f"niveau {niveau!r} invalide. Valeurs autorisées : {sorted(valid_niveaux)}"
        )
    valid_matieres = {m.value for m in Matiere}
    if matiere not in valid_matieres:
        raise typer.BadParameter(
            f"matiere {matiere!r} invalide. Valeurs autorisées : {sorted(valid_matieres)}"
        )
    valid_cycles = {c.value for c in Cycle}
    if cycle not in valid_cycles:
        raise typer.BadParameter(
            f"cycle {cycle!r} invalide. Valeurs autorisées : {sorted(valid_cycles)}"
        )


def _enrich(
    source_docs: list[dict],
    target: Path,
    *,
    dry_run: bool,
) -> dict[str, int]:
    """
    Cœur du pipeline : valide, dédoublonne, append atomique.

    Clé de dédoublonnage = title. Valable dans le contexte (niveau × matière) car
    le JSONL cible est déjà scopé à un (niveau, matière) unique.
    """
    existing_titles = _load_existing_titles(target)
    counts = {"added": 0, "duplicate": 0, "invalid": 0}
    accepted: list[dict] = []

    for idx, raw in enumerate(source_docs, 1):
        title = (raw.get("title") or "").strip()

        try:
            Document.model_validate(raw)
        except ValidationError as e:
            first_error = e.errors()[0]
            loc = ".".join(str(p) for p in first_error["loc"])
            rprint(
                f"  [red]✗ doc {idx} {title[:50]!r}: {loc} — {first_error['msg']}[/red]"
            )
            counts["invalid"] += 1
            continue

        if title in existing_titles:
            rprint(f"  [yellow]⊖ doc {idx} {title[:50]!r}: déjà présent (skip)[/yellow]")
            counts["duplicate"] += 1
            continue

        if any(d.get("title", "").strip() == title for d in accepted):
            rprint(
                f"  [yellow]⊖ doc {idx} {title[:50]!r}: doublon dans la source (skip)[/yellow]"
            )
            counts["duplicate"] += 1
            continue

        accepted.append(raw)
        counts["added"] += 1

    if accepted and not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target.with_suffix(target.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as out:
            if target.exists():
                with open(target, encoding="utf-8") as src:
                    for line in src:
                        out.write(line)
            for doc in accepted:
                out.write(json.dumps(doc, ensure_ascii=False) + "\n")
        tmp_path.replace(target)

    return counts


def _print_summary(counts: dict[str, int], target: Path | None) -> None:
    table = Table(title="Résumé enrichissement")
    table.add_column("Catégorie", style="cyan")
    table.add_column("Nombre", justify="right")

    table.add_row("Ajoutés", f"[green]{counts['added']}[/green]")
    table.add_row("Doublons (skip)", f"[yellow]{counts['duplicate']}[/yellow]")
    table.add_row("Invalides (rejetés)", f"[red]{counts['invalid']}[/red]")
    console.print(table)

    if target:
        rprint(f"\n[green]✓ Cible mise à jour : {target}[/green]")

    if counts["invalid"] > 0:
        raise typer.Exit(1)


@app.command("from-json")
def from_json_cmd(
    source: Annotated[Path, typer.Argument(help="Fichier JSON source (liste de documents)")],
    niveau: Annotated[str, typer.Option(help="Niveau scolaire (ex: cinquieme)")],
    matiere: Annotated[str, typer.Option(help="Matière (ex: mathematiques)")],
    cycle: Annotated[str, typer.Option(help="Cycle (cycle3 / cycle4 / lycee)")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Simulation sans écriture")] = False,
):
    """Enrichit un JSONL cible à partir d'un fichier JSON source."""
    if not source.exists():
        rprint(f"[red]Fichier source introuvable: {source}[/red]")
        raise typer.Exit(1)

    _validate_enums(niveau, matiere, cycle)
    target = _resolve_target_path(niveau, matiere, cycle)

    rprint(
        f"\n[bold cyan]Enrichissement[/bold cyan] {source.name} → "
        f"{target.relative_to(DATA_DIR.parent)}"
    )
    if dry_run:
        rprint("[yellow]Mode dry-run : aucune écriture[/yellow]\n")
    else:
        rprint("")

    source_docs = _load_source_json(source)
    rprint(f"  {len(source_docs)} documents dans la source\n")

    counts = _enrich(source_docs, target, dry_run=dry_run)
    _print_summary(counts, target if not dry_run else None)


@app.command("from-jsonl")
def from_jsonl_cmd(
    source: Annotated[Path, typer.Argument(help="Fichier JSONL source (un doc par ligne)")],
    niveau: Annotated[str, typer.Option(help="Niveau scolaire (ex: cinquieme)")],
    matiere: Annotated[str, typer.Option(help="Matière (ex: mathematiques)")],
    cycle: Annotated[str, typer.Option(help="Cycle (cycle3 / cycle4 / lycee)")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Simulation sans écriture")] = False,
):
    """Enrichit un JSONL cible à partir d'un fichier JSONL source."""
    if not source.exists():
        rprint(f"[red]Fichier source introuvable: {source}[/red]")
        raise typer.Exit(1)

    _validate_enums(niveau, matiere, cycle)
    target = _resolve_target_path(niveau, matiere, cycle)

    rprint(
        f"\n[bold cyan]Enrichissement[/bold cyan] {source.name} → "
        f"{target.relative_to(DATA_DIR.parent)}"
    )
    if dry_run:
        rprint("[yellow]Mode dry-run : aucune écriture[/yellow]\n")
    else:
        rprint("")

    source_docs = _load_source_jsonl(source)
    rprint(f"  {len(source_docs)} documents dans la source\n")

    counts = _enrich(source_docs, target, dry_run=dry_run)
    _print_summary(counts, target if not dry_run else None)


if __name__ == "__main__":
    app()
