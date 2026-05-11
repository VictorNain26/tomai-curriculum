#!/usr/bin/env python3
"""
Utilitaires partagés pour les scripts du dataset TomAI.

Ce module centralise les fonctions communes pour éviter la duplication de code.
"""

import json
import sys
from pathlib import Path

from pydantic import ValidationError

# Add parent to path for schema import
sys.path.insert(0, str(Path(__file__).parent.parent))

from schema import Document

# Constante partagée
DATA_DIR = Path(__file__).parent.parent / "data" / "processed"


def get_all_jsonl_files(
    niveau: str | None = None,
    matiere: str | None = None,
    data_dir: Path | None = None,
) -> list[Path]:
    """
    Récupère tous les fichiers JSONL du dataset.

    Args:
        niveau: Filtrer par niveau (ex: "cinquieme", "seconde")
        matiere: Filtrer par matière (ex: "mathematiques")
        data_dir: Répertoire de données (défaut: DATA_DIR)

    Returns:
        Liste triée des fichiers JSONL correspondants
    """
    base_dir = data_dir or DATA_DIR
    files = []

    for cycle_dir in base_dir.iterdir():
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


def load_documents_from_file(file_path: Path) -> list[dict]:
    """
    Charge et valide les documents d'un fichier JSONL.

    Args:
        file_path: Chemin vers le fichier JSONL

    Returns:
        Liste de dicts avec clés: niveau, matiere, cycle, doc (Document), line_num

    Raises:
        ValueError: Si un document est invalide
    """
    documents = []
    niveau = file_path.parent.name
    matiere = file_path.stem
    cycle = file_path.parent.parent.name

    with open(file_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                doc = Document.model_validate(data)
                documents.append({
                    "niveau": niveau,
                    "matiere": matiere,
                    "cycle": cycle,
                    "doc": doc,
                    "line_num": line_num,
                    "raw_data": data,
                })
            except json.JSONDecodeError as e:
                raise ValueError(f"{file_path}:{line_num}: JSON invalide - {e}")
            except ValidationError as e:
                raise ValueError(f"{file_path}:{line_num}: {e.errors()[0]['msg']}")

    return documents


def load_all_documents(
    niveau: str | None = None,
    matiere: str | None = None,
) -> list[dict]:
    """
    Charge tous les documents du dataset.

    Args:
        niveau: Filtrer par niveau
        matiere: Filtrer par matière

    Returns:
        Liste de tous les documents avec métadonnées
    """
    files = get_all_jsonl_files(niveau, matiere)
    all_docs = []

    for file_path in files:
        docs = load_documents_from_file(file_path)
        all_docs.extend(docs)

    return all_docs


def save_documents_to_file(documents: list[dict], file_path: Path) -> int:
    """
    Sauvegarde des documents dans un fichier JSONL.

    Args:
        documents: Liste de dicts avec clé 'raw_data' ou 'doc'
        file_path: Chemin de sortie

    Returns:
        Nombre de documents écrits
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as f:
        for doc_data in documents:
            if "raw_data" in doc_data:
                data = doc_data["raw_data"]
            elif "doc" in doc_data:
                data = doc_data["doc"].model_dump(exclude_none=True)
            else:
                raise ValueError("Document must have 'raw_data' or 'doc' key")

            f.write(json.dumps(data, ensure_ascii=False) + "\n")

    return len(documents)


def count_tokens(text: str) -> int:
    """
    Estime le nombre de tokens (approximation: 1 token ~ 4 caractères).

    Args:
        text: Texte à analyser

    Returns:
        Nombre de tokens estimé
    """
    return len(text) // 4
