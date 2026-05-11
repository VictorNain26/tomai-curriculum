"""Schema exports (v2.0)."""

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
    cycle_from_niveau,
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
    # Helpers
    "cycle_from_niveau",
]
