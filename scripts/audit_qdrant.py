#!/usr/bin/env python3
"""
Audit complet de la collection Qdrant TomAI.

Vérifie:
- Configuration collection (HNSW, quantization, indexes)
- Distribution des documents
- Structure des payloads
- Doublons potentiels
- Conformité aux best practices RAG 2025
"""

import json
from collections import Counter
from typing import Annotated

import typer
from qdrant_client import QdrantClient
from rich import print as rprint
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="audit", help="Audit de la collection Qdrant")
console = Console()


@app.command()
def run(
    qdrant_url: Annotated[str | None, typer.Option("--qdrant-url", envvar="QDRANT_URL")] = None,
    qdrant_api_key: Annotated[str | None, typer.Option("--qdrant-api-key", envvar="QDRANT_API_KEY")] = None,
    collection: Annotated[str, typer.Option(envvar="QDRANT_COLLECTION")] = "tomai_educational",
    show_samples: Annotated[int, typer.Option(help="Nombre d'exemples a afficher")] = 3,
    export_json: Annotated[str | None, typer.Option(help="Exporter l'audit en JSON")] = None,
):
    """Audit complet de la collection Qdrant."""

    if not qdrant_url or not qdrant_api_key:
        rprint("[red]QDRANT_URL et QDRANT_API_KEY requis[/red]")
        raise typer.Exit(1)

    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)

    # Vérifier que la collection existe
    collections = [c.name for c in client.get_collections().collections]
    if collection not in collections:
        rprint(f"[red]Collection '{collection}' n'existe pas[/red]")
        rprint(f"Collections disponibles: {collections}")
        raise typer.Exit(1)

    audit_results = {"collection": collection, "issues": [], "warnings": [], "best_practices": []}

    # ============================================================
    # 1. CONFIGURATION DE LA COLLECTION
    # ============================================================
    rprint("\n[bold cyan]=" * 60)
    rprint("[bold cyan]1. CONFIGURATION DE LA COLLECTION[/bold cyan]")
    rprint("[bold cyan]=" * 60)

    info = client.get_collection(collection_name=collection)

    rprint("\n[bold]Statistiques generales:[/bold]")
    rprint(f"  Points totaux: {info.points_count}")
    rprint(f"  Vecteurs indexes: {info.indexed_vectors_count}")
    rprint(f"  Status: {info.status}")

    audit_results["total_points"] = info.points_count
    audit_results["indexed_vectors"] = info.indexed_vectors_count
    audit_results["status"] = str(info.status)

    # Vérifier la configuration des vecteurs
    rprint("\n[bold]Configuration des vecteurs:[/bold]")
    vectors_config = info.config.params.vectors
    if hasattr(vectors_config, 'size'):
        rprint(f"  Dimension: {vectors_config.size}")
        rprint(f"  Distance: {vectors_config.distance}")
        audit_results["vector_dimension"] = vectors_config.size
        audit_results["distance_metric"] = str(vectors_config.distance)

        if vectors_config.size == 1024:
            rprint("  [green]OK: Dimension 1024 (Mistral embeddings)[/green]")
            audit_results["best_practices"].append("Dimension 1024D correcte pour Mistral")
        else:
            rprint(f"  [yellow]WARN: Dimension {vectors_config.size} (attendu 1024 pour Mistral)[/yellow]")
            audit_results["warnings"].append(f"Dimension {vectors_config.size} au lieu de 1024")

    # Vérifier HNSW config
    rprint("\n[bold]Configuration HNSW:[/bold]")
    hnsw = info.config.hnsw_config
    rprint(f"  m: {hnsw.m}")
    rprint(f"  ef_construct: {hnsw.ef_construct}")
    rprint(f"  full_scan_threshold: {hnsw.full_scan_threshold}")

    audit_results["hnsw"] = {"m": hnsw.m, "ef_construct": hnsw.ef_construct}

    if hnsw.m >= 16 and hnsw.ef_construct >= 100:
        rprint("  [green]OK: HNSW optimise pour 1024D[/green]")
        audit_results["best_practices"].append("HNSW optimisé (m>=16, ef_construct>=100)")
    else:
        rprint("  [yellow]WARN: HNSW pourrait etre optimise (m=16, ef_construct=100 recommandé)[/yellow]")
        audit_results["warnings"].append("HNSW non optimisé")

    # Vérifier Quantization
    rprint("\n[bold]Quantization:[/bold]")
    quant = info.config.quantization_config
    if quant:
        rprint(f"  Type: {quant}")
        rprint("  [green]OK: Quantization active (-75% memoire)[/green]")
        audit_results["quantization"] = True
        audit_results["best_practices"].append("Quantization int8 activée")
    else:
        rprint("  [yellow]WARN: Pas de quantization (recommande int8 pour -75% memoire)[/yellow]")
        audit_results["quantization"] = False
        audit_results["warnings"].append("Quantization non activée")

    # Vérifier les payload indexes
    rprint("\n[bold]Payload Indexes:[/bold]")
    payload_schema = info.payload_schema
    if payload_schema:
        indexed_fields = list(payload_schema.keys())
        rprint(f"  Champs indexes: {indexed_fields}")
        audit_results["indexed_fields"] = indexed_fields

        recommended = ["niveau", "matiere", "difficulty", "content_type"]
        missing = [f for f in recommended if f not in indexed_fields]
        if missing:
            rprint(f"  [yellow]WARN: Champs non indexes: {missing}[/yellow]")
            audit_results["warnings"].append(f"Champs non indexés: {missing}")
        else:
            rprint("  [green]OK: Champs principaux indexes[/green]")
            audit_results["best_practices"].append("Payload indexes configurés")
    else:
        rprint("  [yellow]WARN: Aucun payload index configure[/yellow]")
        audit_results["warnings"].append("Aucun payload index")

    # ============================================================
    # 2. DISTRIBUTION DES DOCUMENTS
    # ============================================================
    rprint("\n[bold cyan]=" * 60)
    rprint("[bold cyan]2. DISTRIBUTION DES DOCUMENTS[/bold cyan]")
    rprint("[bold cyan]=" * 60)

    # Récupérer tous les points
    all_points = []
    offset = None

    while True:
        result = client.scroll(
            collection_name=collection,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points, offset = result
        all_points.extend(points)
        if offset is None:
            break

    rprint(f"\n[bold]Points recuperes: {len(all_points)}[/bold]")

    # Analyser la distribution
    by_niveau = Counter()
    by_matiere = Counter()
    by_content_type = Counter()
    by_difficulty = Counter()
    by_niveau_matiere = Counter()
    titles = []
    content_lengths = []

    for point in all_points:
        payload = point.payload
        niveau = payload.get("niveau", "UNKNOWN")
        matiere = payload.get("matiere", "UNKNOWN")
        content_type = payload.get("content_type", "UNKNOWN")
        difficulty = payload.get("difficulty", "UNKNOWN")
        title = payload.get("title", "")
        content = payload.get("content", "")

        by_niveau[niveau] += 1
        by_matiere[matiere] += 1
        by_content_type[content_type] += 1
        by_difficulty[difficulty] += 1
        by_niveau_matiere[(niveau, matiere)] += 1
        titles.append(title)
        content_lengths.append(len(content))

    # Table par niveau
    rprint("\n[bold]Par niveau:[/bold]")
    table = Table(show_header=True)
    table.add_column("Niveau")
    table.add_column("Documents", justify="right")
    for niveau, count in sorted(by_niveau.items()):
        table.add_row(niveau, str(count))
    console.print(table)

    audit_results["by_niveau"] = dict(by_niveau)

    # Table par matière
    rprint("\n[bold]Par matiere:[/bold]")
    table = Table(show_header=True)
    table.add_column("Matiere")
    table.add_column("Documents", justify="right")
    for matiere, count in sorted(by_matiere.items()):
        table.add_row(matiere, str(count))
    console.print(table)

    audit_results["by_matiere"] = dict(by_matiere)

    # Table par content_type
    rprint("\n[bold]Par content_type:[/bold]")
    table = Table(show_header=True)
    table.add_column("Type")
    table.add_column("Documents", justify="right")
    for ct, count in sorted(by_content_type.items()):
        table.add_row(ct, str(count))
    console.print(table)

    audit_results["by_content_type"] = dict(by_content_type)

    # Table par difficulty
    rprint("\n[bold]Par difficulty:[/bold]")
    table = Table(show_header=True)
    table.add_column("Difficulty")
    table.add_column("Documents", justify="right")
    for diff, count in sorted(by_difficulty.items()):
        table.add_row(diff, str(count))
    console.print(table)

    audit_results["by_difficulty"] = dict(by_difficulty)

    # ============================================================
    # 3. ANALYSE DE LA QUALITE
    # ============================================================
    rprint("\n[bold cyan]=" * 60)
    rprint("[bold cyan]3. ANALYSE DE LA QUALITE[/bold cyan]")
    rprint("[bold cyan]=" * 60)

    # Statistiques sur la longueur du contenu
    if content_lengths:
        avg_len = sum(content_lengths) / len(content_lengths)
        min_len = min(content_lengths)
        max_len = max(content_lengths)

        rprint("\n[bold]Longueur du contenu (caracteres):[/bold]")
        rprint(f"  Moyenne: {avg_len:.0f} chars (~{avg_len/4:.0f} tokens)")
        rprint(f"  Min: {min_len} chars (~{min_len/4:.0f} tokens)")
        rprint(f"  Max: {max_len} chars (~{max_len/4:.0f} tokens)")

        audit_results["content_stats"] = {
            "avg_chars": round(avg_len),
            "min_chars": min_len,
            "max_chars": max_len,
            "avg_tokens": round(avg_len / 4),
        }

        # Vérifier les best practices RAG 2025
        optimal_min = 200
        optimal_max = 2400

        too_short = sum(1 for length in content_lengths if length < optimal_min)
        too_long = sum(1 for length in content_lengths if length > optimal_max)
        optimal = sum(1 for length in content_lengths if optimal_min <= length <= optimal_max)

        rprint("\n[bold]Distribution par taille:[/bold]")
        rprint(f"  Optimal ({optimal_min}-{optimal_max} chars): {optimal} ({100*optimal/len(content_lengths):.1f}%)")
        rprint(f"  Trop court (<{optimal_min}): {too_short}")
        rprint(f"  Trop long (>{optimal_max}): {too_long}")

        if too_short > 0 or too_long > 0:
            audit_results["warnings"].append(f"{too_short} docs trop courts, {too_long} docs trop longs")

    # Vérifier les doublons de titres (par matière)
    rprint("\n[bold]Verification des doublons:[/bold]")

    # Doublons réels = même (matière, titre)
    matiere_title_counts = Counter()
    for point in all_points:
        payload = point.payload
        key = (payload.get("matiere", ""), payload.get("title", ""))
        matiere_title_counts[key] += 1

    real_duplicates = [(f"{m}:{t}", c) for (m, t), c in matiere_title_counts.items() if c > 1]

    # Titres partagés entre matières (normal pour langues)
    title_counts = Counter(titles)
    shared_titles = [(t, c) for t, c in title_counts.items() if c > 1]

    if real_duplicates:
        rprint(f"  [red]ERREUR: {len(real_duplicates)} vrais doublons (meme matiere)![/red]")
        for key, count in real_duplicates[:5]:
            rprint(f"    - '{key}' ({count}x)")
        audit_results["issues"].append(f"{len(real_duplicates)} vrais doublons")
        audit_results["duplicates"] = real_duplicates
    elif shared_titles:
        rprint("  [green]OK: Aucun doublon reel[/green]")
        rprint(f"  [dim]Note: {len(shared_titles)} titres partages entre matieres (normal pour langues)[/dim]")
        audit_results["best_practices"].append("Aucun doublon réel")
        audit_results["shared_titles"] = len(shared_titles)
    else:
        rprint("  [green]OK: Aucun doublon de titre[/green]")
        audit_results["best_practices"].append("Aucun doublon de titre")

    # ============================================================
    # 4. VERIFICATION DES PAYLOADS
    # ============================================================
    rprint("\n[bold cyan]=" * 60)
    rprint("[bold cyan]4. STRUCTURE DES PAYLOADS[/bold cyan]")
    rprint("[bold cyan]=" * 60)

    # Analyser les champs présents
    all_fields = set()
    field_counts = Counter()

    for point in all_points:
        for field in point.payload.keys():
            all_fields.add(field)
            field_counts[field] += 1

    rprint("\n[bold]Champs presents dans les payloads:[/bold]")
    table = Table(show_header=True)
    table.add_column("Champ")
    table.add_column("Occurrences", justify="right")
    table.add_column("Coverage", justify="right")

    for field, count in sorted(field_counts.items(), key=lambda x: -x[1]):
        coverage = 100 * count / len(all_points)
        table.add_row(field, str(count), f"{coverage:.1f}%")

    console.print(table)

    audit_results["payload_fields"] = dict(field_counts)

    # Champs requis
    required = ["niveau", "matiere", "domaine", "title", "content", "content_type"]
    missing_required = [f for f in required if field_counts.get(f, 0) < len(all_points)]

    if missing_required:
        rprint(f"\n[red]ERREUR: Champs requis manquants: {missing_required}[/red]")
        audit_results["issues"].append(f"Champs requis manquants: {missing_required}")
    else:
        rprint("\n[green]OK: Tous les champs requis sont presents[/green]")
        audit_results["best_practices"].append("Tous les champs requis présents")

    # ============================================================
    # 5. EXEMPLES DE DOCUMENTS
    # ============================================================
    if show_samples > 0:
        rprint("\n[bold cyan]=" * 60)
        rprint(f"[bold cyan]5. EXEMPLES ({show_samples} documents)[/bold cyan]")
        rprint("[bold cyan]=" * 60)

        import random
        samples = random.sample(all_points, min(show_samples, len(all_points)))

        for i, point in enumerate(samples, 1):
            payload = point.payload
            rprint(f"\n[bold]Document {i}:[/bold]")
            rprint(f"  ID: {point.id}")
            rprint(f"  Titre: {payload.get('title', 'N/A')}")
            rprint(f"  Niveau: {payload.get('niveau', 'N/A')}")
            rprint(f"  Matiere: {payload.get('matiere', 'N/A')}")
            rprint(f"  Domaine: {payload.get('domaine', 'N/A')}")
            rprint(f"  Type: {payload.get('content_type', 'N/A')}")
            rprint(f"  Difficulty: {payload.get('difficulty', 'N/A')}")
            content = payload.get('content', '')
            rprint(f"  Contenu: {content[:200]}..." if len(content) > 200 else f"  Contenu: {content}")

    # ============================================================
    # 6. RESUME ET RECOMMANDATIONS
    # ============================================================
    rprint("\n[bold cyan]=" * 60)
    rprint("[bold cyan]6. RESUME DE L'AUDIT[/bold cyan]")
    rprint("[bold cyan]=" * 60)

    rprint(f"\n[bold]Best Practices respectees ({len(audit_results['best_practices'])}):[/bold]")
    for bp in audit_results["best_practices"]:
        rprint(f"  [green]OK[/green] {bp}")

    if audit_results["warnings"]:
        rprint(f"\n[bold]Avertissements ({len(audit_results['warnings'])}):[/bold]")
        for warn in audit_results["warnings"]:
            rprint(f"  [yellow]WARN[/yellow] {warn}")

    if audit_results["issues"]:
        rprint(f"\n[bold]Problemes ({len(audit_results['issues'])}):[/bold]")
        for issue in audit_results["issues"]:
            rprint(f"  [red]ERREUR[/red] {issue}")

    # Score global
    score = len(audit_results["best_practices"]) * 10 - len(audit_results["warnings"]) * 5 - len(audit_results["issues"]) * 20
    score = max(0, min(100, score + 50))  # Normalize to 0-100

    rprint(f"\n[bold]Score global: {score}/100[/bold]")

    if score >= 80:
        rprint("[green]Excellent! La collection respecte les best practices RAG 2025.[/green]")
    elif score >= 60:
        rprint("[yellow]Correct, mais quelques ameliorations recommandees.[/yellow]")
    else:
        rprint("[red]Ameliorations necessaires pour une performance optimale.[/red]")

    audit_results["score"] = score

    # Export JSON si demandé
    if export_json:
        with open(export_json, "w", encoding="utf-8") as f:
            json.dump(audit_results, f, indent=2, ensure_ascii=False)
        rprint(f"\n[dim]Audit exporte vers {export_json}[/dim]")


if __name__ == "__main__":
    app()
