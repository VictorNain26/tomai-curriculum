"""Schema exports - VERSION 2.0 RAG 2025."""

from .document import (
    ContentType,
    Cycle,
    DatasetMetadata,
    Difficulty,
    Document,
    DocumentRelation,
    EnrichedContent,
    Matiere,
    Niveau,
    NiveauCollege,
    NiveauLycee,
    QualityMetrics,
    RelationType,
    ReviewStatus,
)

__all__ = [
    # Core types
    "Document",
    "DatasetMetadata",

    # Enums
    "ContentType",
    "Cycle",
    "Difficulty",
    "Matiere",
    "Niveau",
    "NiveauCollege",
    "NiveauLycee",
    "RelationType",
    "ReviewStatus",

    # Auxiliary models
    "DocumentRelation",
    "EnrichedContent",
    "QualityMetrics",
]
