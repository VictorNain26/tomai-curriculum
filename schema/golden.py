"""
Schéma Pydantic pour le golden set RAG — format document-grounded.

Chaque entrée référence le chunk d'origine via `gold_chunk_id` (l'UUID5
calculé par `ingest.upsert_to_qdrant` sur `(matière, niveau, text)`). Cela
permet de mesurer `recall@k` directement sur l'identité du chunk attendu,
sans dépendre du keyword matching (sujet aux faux positifs/négatifs sur le
français).

Source : RAGAS TestsetGenerator + RAGalyst (arXiv 2511.04502) — document-
grounded synthesis est l'état de l'art mai 2026 pour les golden sets RAG.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .document import Matiere, NiveauCollege, NiveauLycee


class GoldenQuestion(BaseModel):
    """Une question du golden set, ancrée sur un chunk précis."""

    query: str = Field(..., min_length=10, max_length=300, description="Question naturelle")
    matiere: Matiere
    niveau: NiveauCollege | NiveauLycee
    expected_keywords: list[str] = Field(
        ...,
        min_length=2,
        max_length=8,
        description="Mots-clés présents dans le chunk source (extraits, pas inventés)",
    )
    # Document-grounded fields (présents si générés via generate_golden.py)
    gold_chunk_id: str | None = Field(
        None,
        description="UUID5 du chunk source attendu. Calculé par "
        "ingest.upsert_to_qdrant comme uuid5(matière+niveau+text).",
    )
    gold_section: str | None = Field(None, description="Section BO du chunk source")
    gold_source_file: str | None = Field(None, description="Nom du fichier source (sans extension)")


class GoldenSet(BaseModel):
    """Container racine — accepte list ou wrapping pour évolutions futures."""

    questions: list[GoldenQuestion]
