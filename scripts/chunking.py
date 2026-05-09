#!/usr/bin/env python3
"""
Script de chunking optimal pour RAG 2025.

Regroupe les documents atomiques existants (~100 tokens) en documents
optimaux de 300-400 tokens selon les best practices 2025.

Stratégie:
- Regroupement sémantique par domaine/sousdomaine
- Préservation du contexte pédagogique
- Enrichissement automatique des metadata
- Génération d'IDs stables

Usage:
    uv run python scripts/chunking.py merge --niveau=cinquieme --matiere=mathematiques --dry-run
    uv run python scripts/chunking.py merge --niveau=cinquieme --matiere=mathematiques --output=data/processed_v2/
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

from rich import print as rprint
from rich.console import Console
from rich.table import Table

# Add parent to path for schema import
sys.path.insert(0, str(Path(__file__).parent.parent))

from schema import ContentType, ReviewStatus
from scripts.utils import DATA_DIR

console = Console()


class UnvalidatedDocument:
    """
    Wrapper minimal pour charger les documents v1 sans déclencher la validation
    Pydantic v2 stricte. Sert uniquement au pipeline de migration/chunking où on
    veut tolérer des documents non-conformes pour les fusionner et les ré-émettre
    aux contraintes v2.
    """

    def __init__(self, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


def estimate_tokens(text: str) -> int:
    """Estime le nombre de tokens (1 token ≈ 4 chars en français)."""
    return len(text) // 4


def generate_stable_id(niveau: str, matiere: str, domaine: str, index: int) -> str:
    """Génère un ID stable pour un document."""
    # Format: matiere_niveau_domaine_index
    safe_domaine = domaine.lower().replace(" ", "_").replace("'", "")[:20]
    return f"{matiere}_{niveau}_{safe_domaine}_{index:03d}"


def group_documents_by_theme(documents: list[dict]) -> dict:
    """
    Regroupe les documents par thème sémantique.

    Stratégie:
    - Par domaine + sousdomaine
    - Par content_type similaire
    - Ordre pédagogique: definition → theoreme → methode → exemple
    """
    groups = defaultdict(list)

    for doc_data in documents:
        doc = doc_data["doc"]
        # Clé de groupage: domaine + sousdomaine
        key = f"{doc.domaine}::{doc.sousdomaine or 'general'}"
        groups[key].append(doc_data)

    # Trier par ordre pédagogique dans chaque groupe
    content_order = {
        ContentType.DEFINITION: 0,
        ContentType.THEOREME: 1,
        ContentType.FORMULE: 2,
        ContentType.METHODE: 3,
        ContentType.EXEMPLE: 4,
        ContentType.ERREUR_COURANTE: 5,
    }

    for key in groups:
        groups[key].sort(key=lambda x: content_order.get(x["doc"].content_type, 99))

    return dict(groups)


def merge_documents(docs_group: list[dict], target_tokens: int = 350, overlap_pct: float = 0.15) -> list[dict]:
    """
    Fusionne des documents pour atteindre la cible de tokens avec overlap.

    Best Practice 2025: Overlap de 15% entre chunks pour préserver le contexte.
    Source: https://www.firecrawl.dev/blog/best-chunking-strategies-rag-2025

    Args:
        docs_group: Groupe de documents à fusionner
        target_tokens: Nombre de tokens cible (défaut: 350)
        overlap_pct: Pourcentage d'overlap (défaut: 0.15 = 15%)

    Returns:
        Liste de documents fusionnés avec overlap
    """
    if len(docs_group) <= 1:
        return [_create_merged_document(docs_group)] if docs_group else []

    merged = []
    i = 0

    while i < len(docs_group):
        current_batch = []
        current_tokens = 0

        # Construire un chunk jusqu'à atteindre la cible
        while i < len(docs_group) and current_tokens < target_tokens:
            doc_data = docs_group[i]
            doc_tokens = estimate_tokens(doc_data["doc"].content)

            # Vérifier si l'ajout ne dépasse pas trop la limite (max 500 tokens)
            if current_tokens > 0 and current_tokens + doc_tokens > 500:
                break

            current_batch.append(doc_data)
            current_tokens += doc_tokens
            i += 1

        # Si le chunk est trop petit, ajouter encore un document
        if current_tokens < 250 and i < len(docs_group):
            current_batch.append(docs_group[i])
            current_tokens += estimate_tokens(docs_group[i]["doc"].content)
            i += 1

        # Créer le chunk
        if current_batch:
            merged.append(_create_merged_document(current_batch))

        # OVERLAP: Reculer de 15% pour le prochain chunk
        # Cela permet de capturer le contexte aux bordures
        if i < len(docs_group) and len(current_batch) > 1:
            overlap_size = max(1, int(len(current_batch) * overlap_pct))
            i -= overlap_size  # Reculer pour créer l'overlap

    return merged


def _create_merged_document(docs_data: list[dict]) -> dict:
    """
    Crée un document fusionné à partir d'un groupe.

    Enrichit automatiquement avec:
    - typical_questions
    - learning_objectives
    - relations entre concepts
    - keywords agrégés
    """
    if not docs_data:
        raise ValueError("docs_data cannot be empty")

    if len(docs_data) == 1:
        # Document déjà assez grand, juste enrichir
        doc = docs_data[0]["doc"]
        # S'assurer que docs_data[0] contient niveau/matiere
        if "niveau" not in docs_data[0]:
            raise ValueError(f"Missing 'niveau' in doc_data: {docs_data[0].keys()}")
        return _enrich_single_document(doc, docs_data[0])

    # Fusionner plusieurs documents
    first = docs_data[0]["doc"]
    domaine = first.domaine
    sousdomaine = first.sousdomaine

    # Construire le titre fusionné
    if len(docs_data) <= 3:
        titles = [d["doc"].title.split(" - ")[0] for d in docs_data]
        merged_title = f"{domaine} - {' et '.join(titles[:3])}"
    else:
        merged_title = f"{domaine} - {sousdomaine or 'Concepts fondamentaux'}"

    # Fusionner les contenus avec sections
    content_parts = []
    for i, doc_data in enumerate(docs_data):
        doc = doc_data["doc"]
        # Ajouter un titre de section si multiple documents
        if len(docs_data) > 1:
            section_title = doc.title.split(" - ")[-1] if " - " in doc.title else doc.title
            content_parts.append(f"## {section_title}\n\n{doc.content}")
        else:
            content_parts.append(doc.content)

    merged_content = "\n\n".join(content_parts)

    # Agréger les keywords (uniques)
    all_keywords = set()
    for d in docs_data:
        keywords = getattr(d["doc"], 'keywords', None)
        if keywords:
            all_keywords.update(keywords)

    # Agréger les prérequis
    all_prerequis = set()
    for d in docs_data:
        prerequis = getattr(d["doc"], 'prerequis', None)
        if prerequis:
            all_prerequis.update(prerequis)

    # Générer typical_questions
    typical_questions = _generate_typical_questions(docs_data)

    # Générer learning_objectives
    learning_objectives = _generate_learning_objectives(docs_data)

    # Générer common_errors
    common_errors = _extract_common_errors(docs_data)

    # Extraire les formules LaTeX si présentes
    latex_formulas = _extract_latex_formulas(merged_content)

    niveau = docs_data[0]["niveau"]
    matiere = docs_data[0]["matiere"]

    # Gérer content_type et difficulty (string ou enum)
    content_type_raw = getattr(first, 'content_type', 'definition')
    content_type_val = content_type_raw if isinstance(content_type_raw, str) else content_type_raw.value

    difficulty_raw = getattr(first, 'difficulty', 'standard')
    difficulty_val = difficulty_raw if isinstance(difficulty_raw, str) else difficulty_raw.value

    return {
        "title": merged_title[:200],
        "domaine": domaine,
        "sousdomaine": sousdomaine,
        "content_type": content_type_val,
        "difficulty": difficulty_val,
        "content": merged_content,
        "keywords": list(all_keywords)[:15] if all_keywords else None,
        "prerequis": list(all_prerequis)[:10] if all_prerequis else None,
        "typical_questions": typical_questions[:10] if typical_questions else None,
        "learning_objectives": learning_objectives[:5] if learning_objectives else None,
        "common_errors": common_errors[:5] if common_errors else None,
        "enriched": {
            "latex_formulas": latex_formulas[:20]
        } if latex_formulas else None,
        "version": "2.0.0",
        "author": "TomAI - Migration automatique",
        "source_revision": "BO 30/07/2020",
        "review_status": ReviewStatus.DRAFT.value,
        "confidence_level": 0.85,
        "tags": ["auto_merged", f"niveau_{niveau}", f"matiere_{matiere}"]
    }


def _enrich_single_document(doc, doc_data: dict) -> dict:
    """Enrichit un document unique avec metadata manquantes."""
    # Convertir OldDocument en dict
    if hasattr(doc, 'model_dump'):
        doc_dict = doc.model_dump(exclude_none=True)
    else:
        doc_dict = {k: v for k, v in doc.__dict__.items() if v is not None}

    # Générer des questions types basées sur le content_type
    typical_questions = []
    title_lower = doc.title.lower()
    content_type_str = doc.content_type if isinstance(doc.content_type, str) else doc.content_type.value

    if content_type_str == "definition":
        typical_questions.append(f"Qu'est-ce que {title_lower} ?")
        typical_questions.append(f"Définition de {title_lower}")
    elif content_type_str == "theoreme":
        typical_questions.append(f"Énoncé du {title_lower}")
        typical_questions.append(f"Comment appliquer {title_lower} ?")
    elif content_type_str == "methode":
        typical_questions.append(f"Comment {title_lower} ?")
        typical_questions.append(f"Méthode pour {title_lower}")

    latex_formulas = _extract_latex_formulas(doc.content)

    return {
        **doc_dict,
        "typical_questions": typical_questions[:10] if typical_questions else None,
        "enriched": {
            "latex_formulas": latex_formulas
        } if latex_formulas else None,
        "version": "2.0.0",
        "review_status": ReviewStatus.DRAFT.value,
        "confidence_level": 0.9,
        "tags": ["single_doc", f"niveau_{doc_data['niveau']}", f"matiere_{doc_data['matiere']}"]
    }


def _generate_typical_questions(docs_data: list[dict]) -> list[str]:
    """Génère des questions types basées sur les documents."""
    questions = []
    for doc_data in docs_data:
        doc = doc_data["doc"]
        title = doc.title.lower().replace(" - ", " ")
        content_type = getattr(doc, 'content_type', None)
        content_type_str = content_type if isinstance(content_type, str) else (content_type.value if content_type else "")

        if content_type_str == "definition":
            questions.append(f"Qu'est-ce que {title} ?")
        elif content_type_str == "theoreme":
            questions.append(f"Quel est l'énoncé de {title} ?")
        elif content_type_str == "methode":
            questions.append(f"Comment {title} ?")
        elif content_type_str == "formule":
            questions.append(f"Quelle est la formule pour {title} ?")

    return list(set(questions))


def _generate_learning_objectives(docs_data: list[dict]) -> list[str]:
    """Génère des objectifs pédagogiques."""
    objectives = []
    for doc_data in docs_data:
        doc = doc_data["doc"]
        content_type = getattr(doc, 'content_type', None)
        content_type_str = content_type if isinstance(content_type, str) else (content_type.value if content_type else "")

        if content_type_str == "definition":
            objectives.append(f"Connaître la définition de {doc.domaine}")
        elif content_type_str == "theoreme":
            objectives.append(f"Appliquer {doc.title.split(' - ')[0]}")
        elif content_type_str == "methode":
            objectives.append(f"Maîtriser la méthode: {doc.title.split(' - ')[-1]}")

    return list(set(objectives))


def _extract_common_errors(docs_data: list[dict]) -> list[str]:
    """Extrait les erreurs courantes mentionnées."""
    errors = []
    keywords = ["erreur", "attention", "ne pas", "piège", "confusion"]

    for doc_data in docs_data:
        content = doc_data["doc"].content.lower()
        for keyword in keywords:
            if keyword in content:
                # Extraire la phrase contenant l'erreur
                sentences = doc_data["doc"].content.split(".")
                for sentence in sentences:
                    if keyword in sentence.lower():
                        errors.append(sentence.strip() + ".")
                        break

    return list(set(errors))


def _extract_latex_formulas(content: str) -> list[str]:
    """Extrait les formules mathématiques pour conversion LaTeX."""
    formulas = []

    # Patterns simples pour détecter des formules
    import re

    # Chercher des équations avec = et opérations
    equation_pattern = r'([A-Z]{1,3}[²³]?\s*[=+\-×÷]\s*[A-Z]{1,3}[²³]?(?:\s*[+\-×÷]\s*[A-Z]{1,3}[²³]?)*)'
    matches = re.findall(equation_pattern, content)
    formulas.extend(matches)

    # Chercher des fractions
    fraction_pattern = r'(\d+/\d+)'
    fractions = re.findall(fraction_pattern, content)
    formulas.extend(fractions)

    return list(set(formulas))[:20]


def load_documents_from_jsonl(file_path: Path, niveau: str, matiere: str, cycle: str) -> list[dict]:
    """
    Charge les documents depuis un fichier JSONL (anciens format V1).

    Désactive la validation stricte pour charger les vieux documents
    qui ne respectent pas encore les contraintes V2.
    """
    documents = []

    with open(file_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                doc = UnvalidatedDocument(**data)
                documents.append({
                    "niveau": niveau,
                    "matiere": matiere,
                    "cycle": cycle,
                    "doc": doc,
                })
            except Exception as e:
                rprint(f"[red]Erreur ligne {line_num}: {e}[/red]")

    return documents


def merge(
    niveau: str | None = None,
    matiere: str | None = None,
    target_tokens: int = 350,
    output: Path = Path("data/processed_v2"),
    dry_run: bool = False,
):
    """
    Fusionne les documents atomiques en chunks optimaux de 300-400 tokens.

    Best practice 2025: chunking sémantique par thème avec enrichissement auto.
    """
    rprint("\n[bold cyan]Chunking Optimal - RAG 2025[/bold cyan]\n")

    # Trouver les fichiers
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

    if not files:
        rprint("[yellow]Aucun fichier trouvé[/yellow]")
        return

    rprint(f"📁 Fichiers trouvés: {len(files)}")

    table = Table(title="Résultats du Chunking")
    table.add_column("Matière", style="cyan")
    table.add_column("Docs originaux", justify="right")
    table.add_column("Docs fusionnés", justify="right", style="green")
    table.add_column("Tokens moy", justify="right")
    table.add_column("Réduction", justify="right", style="yellow")

    total_original = 0
    total_merged = 0

    for file_path in files:
        niveau_name = file_path.parent.name
        matiere_name = file_path.stem
        cycle = file_path.parent.parent.name

        rprint(f"\n[bold]Traitement: {niveau_name}/{matiere_name}[/bold]")

        # Charger les documents
        documents = load_documents_from_jsonl(file_path, niveau_name, matiere_name, cycle)
        total_original += len(documents)

        # Grouper par thème
        groups = group_documents_by_theme(documents)
        rprint(f"  └─ {len(groups)} thèmes détectés")

        # Fusionner chaque groupe
        merged_docs = []
        for theme, docs_group in groups.items():
            merged = merge_documents(docs_group, target_tokens=target_tokens)
            merged_docs.extend(merged)
            rprint(f"     • {theme.split('::')[0]}: {len(docs_group)} → {len(merged)} docs")

        total_merged += len(merged_docs)

        # Calculer tokens moyens
        if merged_docs:
            avg_tokens = sum(estimate_tokens(d["content"]) for d in merged_docs) / len(merged_docs)
            reduction = ((len(documents) - len(merged_docs)) / len(documents) * 100) if documents else 0

            table.add_row(
                matiere_name,
                str(len(documents)),
                str(len(merged_docs)),
                f"~{int(avg_tokens)}",
                f"{reduction:.0f}%"
            )
        else:
            rprint("[yellow]  Aucun document valide trouvé[/yellow]")

        # Sauvegarder
        if not dry_run:
            output_dir = output / cycle / niveau_name
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"{matiere_name}.jsonl"

            with open(output_file, "w", encoding="utf-8") as f:
                for doc_dict in merged_docs:
                    f.write(json.dumps(doc_dict, ensure_ascii=False) + "\n")

            rprint(f"  [green]✓ Sauvegardé: {output_file}[/green]")

    console.print(table)

    rprint("\n[bold]Résumé:[/bold]")
    rprint(f"  • Documents originaux: {total_original}")
    rprint(f"  • Documents fusionnés: {total_merged}")
    rprint(f"  • Réduction: {((total_original - total_merged) / total_original * 100):.1f}%")

    if dry_run:
        rprint("\n[yellow]Mode dry-run: aucun fichier créé[/yellow]")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Chunking optimal pour RAG 2025")
    parser.add_argument("--niveau", help="Niveau à traiter")
    parser.add_argument("--matiere", help="Matière à traiter")
    parser.add_argument("--target-tokens", type=int, default=350, help="Tokens cible")
    parser.add_argument("--output", default="data/processed_v2", help="Répertoire sortie")
    parser.add_argument("--dry-run", action="store_true", help="Simulation")

    args = parser.parse_args()
    merge(
        niveau=args.niveau,
        matiere=args.matiere,
        target_tokens=args.target_tokens,
        output=Path(args.output),
        dry_run=args.dry_run
    )
