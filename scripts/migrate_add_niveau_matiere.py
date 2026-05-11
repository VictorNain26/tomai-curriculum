#!/usr/bin/env python3
"""
Migration one-shot : ajoute `niveau` et `matiere` à chaque document JSONL.

Avant Phase 5, ces deux champs étaient dérivés du path au moment de l'ingestion
(`scripts/ingest.py:load_documents`). Désormais ils font partie du schema
Pydantic (cf. `schema/document.py`) et doivent être stockés dans le JSONL.

Pour chaque fichier `data/processed/<cycle_dir>/<niveau>/<matiere>.jsonl` :
- chaque ligne est lue, validée comme Document
- si `niveau` ou `matiere` sont absents, ils sont injectés depuis le path
- le résultat est réécrit (atomique : .tmp + rename) en préservant la mise
  en forme JSONL standard (un dict compact par ligne, ensure_ascii=False)

Le `content_hash` (ingest.py:compute_content_hash) reste basé sur
`niveau + matiere + title + content` AVANT migration et continue d'être
identique APRÈS : pas d'impact sur les UUIDs Qdrant ni sur la collection prod.

Usage :
    uv run python scripts/migrate_add_niveau_matiere.py            # dry-run (défaut)
    uv run python scripts/migrate_add_niveau_matiere.py --apply    # écriture réelle
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich import print as rprint

sys.path.insert(0, str(Path(__file__).parent.parent))

from schema import Document  # noqa: E402
from scripts.utils import get_all_jsonl_files  # noqa: E402

app = typer.Typer(help=__doc__, no_args_is_help=False)


def _migrate_file(file_path: Path, *, apply: bool) -> tuple[int, int, list[str]]:
    """
    Retourne (added_count, total_count, errors).

    added_count = nombre de documents pour lesquels au moins un champ a été
    ajouté. total_count = nombre total de documents traités.
    """
    niveau = file_path.parent.name
    matiere = file_path.stem
    added = 0
    total = 0
    errors: list[str] = []
    new_lines: list[str] = []

    with open(file_path, encoding="utf-8") as f:
        for line_num, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                # Preserve les lignes vides
                new_lines.append(raw.rstrip("\n"))
                continue
            total += 1
            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"{file_path}:{line_num}: JSON invalide ({e})")
                new_lines.append(raw.rstrip("\n"))
                continue

            mutated = False
            if "niveau" not in data:
                data["niveau"] = niveau
                mutated = True
            if "matiere" not in data:
                data["matiere"] = matiere
                mutated = True

            # Valide le doc enrichi pour catch les inconsistances
            try:
                Document.model_validate(data)
            except Exception as e:
                errors.append(f"{file_path}:{line_num}: validation ({e})")
                new_lines.append(raw.rstrip("\n"))
                continue

            if mutated:
                added += 1
            new_lines.append(json.dumps(data, ensure_ascii=False))

    if apply and added > 0 and not errors:
        tmp = file_path.with_suffix(file_path.suffix + ".tmp")
        tmp.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        tmp.replace(file_path)

    return added, total, errors


@app.command()
def run(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Écrit réellement les fichiers (défaut : dry-run, lecture seule).",
        ),
    ] = False,
):
    """Exécute la migration sur tous les JSONL de data/processed/."""
    files = get_all_jsonl_files()
    rprint(f"[bold]Migration sur {len(files)} fichiers[/bold] (apply={apply})")

    total_added = 0
    total_docs = 0
    total_errors = 0
    files_with_errors: list[Path] = []

    for f in files:
        added, total, errors = _migrate_file(f, apply=apply)
        total_added += added
        total_docs += total
        total_errors += len(errors)
        if errors:
            files_with_errors.append(f)
            for err in errors[:5]:
                rprint(f"  [red]{err}[/red]")

    rprint("")
    rprint(f"  Documents traités : [bold]{total_docs}[/bold]")
    rprint(f"  Champs ajoutés    : [bold]{total_added}[/bold]")
    rprint(f"  Erreurs           : [bold]{total_errors}[/bold]")

    if files_with_errors:
        rprint(
            f"\n[red]{len(files_with_errors)} fichier(s) avec erreurs — migration partielle[/red]"
        )
        raise typer.Exit(1)

    if not apply:
        rprint(
            "\n[yellow]Dry-run terminé. Relancer avec --apply pour écrire les changements.[/yellow]"
        )
    else:
        rprint("\n[green]Migration appliquée.[/green]")


if __name__ == "__main__":
    app()
