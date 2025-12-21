"""
Schema Pydantic pour les documents éducatifs TomAI.

Best practices RAG 2025 (mis à jour Décembre 2025):
- Chunking optimal: 256-512 tokens (cible 300-400) avec overlap 10-20%
- Metadata enrichie: versioning, qualité, relations, contexte d'usage
- Traçabilité complète: timestamps, auteurs, révisions
- Knowledge graph: relations explicites entre concepts
- Support contenu enrichi: LaTeX, diagrammes, exemples interactifs

Sources:
- https://www.edenai.co/post/the-2025-guide-to-retrieval-augmented-generation-rag
- https://milvus.io/ai-quick-reference/what-is-the-optimal-chunk-size-for-rag-applications
- https://www.chitika.com/evaluating-rag-quality-best-practices/
- https://orq.ai/blog/rag-evaluation
- https://unstructured.io/blog/chunking-for-rag-best-practices
"""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# =============================================================================
# ENUMS - Vocabulaire contrôlé
# =============================================================================

class Cycle(str, Enum):
    """Cycles scolaires français."""
    CYCLE3 = "cycle3"  # CM1, CM2, 6ème
    CYCLE4 = "cycle4"  # 5ème, 4ème, 3ème
    LYCEE = "lycee"    # 2nde, 1ère, Terminale


class NiveauCollege(str, Enum):
    """Niveaux collège."""
    SIXIEME = "sixieme"
    CINQUIEME = "cinquieme"
    QUATRIEME = "quatrieme"
    TROISIEME = "troisieme"


class NiveauLycee(str, Enum):
    """Niveaux lycée."""
    SECONDE = "seconde"
    PREMIERE = "premiere"
    TERMINALE = "terminale"


class Matiere(str, Enum):
    """Matières supportées par TomAI."""
    MATHEMATIQUES = "mathematiques"
    FRANCAIS = "francais"
    PHYSIQUE_CHIMIE = "physique_chimie"
    SVT = "svt"
    HISTOIRE_GEO = "histoire_geo"
    ANGLAIS = "anglais"


class ContentType(str, Enum):
    """
    Types de contenu pédagogique.

    Catégorisation pour filtrage metadata et adaptation du prompting.
    """
    DEFINITION = "definition"          # Définition officielle d'un concept
    THEOREME = "theoreme"              # Théorème/propriété mathématique
    FORMULE = "formule"                # Formule à retenir
    METHODE = "methode"                # Méthode de résolution pas à pas
    EXEMPLE = "exemple"                # Exemple illustratif
    ERREUR_COURANTE = "erreur_courante"  # Piège/erreur fréquente à éviter


class Difficulty(str, Enum):
    """
    Niveau de difficulté du contenu.

    Permet le filtrage par niveau de maîtrise de l'élève.
    """
    DECOUVERTE = "decouverte"      # Introduction, bases
    STANDARD = "standard"          # Niveau attendu du programme
    APPROFONDISSEMENT = "approfondissement"  # Pour aller plus loin


class ReviewStatus(str, Enum):
    """
    Statut de validation du document.

    Pipeline qualité: draft → reviewed → validated → published
    """
    DRAFT = "draft"                # Brouillon, non vérifié
    REVIEWED = "reviewed"          # Relu par un expert
    VALIDATED = "validated"        # Validé qualité + sources
    PUBLISHED = "published"        # Publié en production
    DEPRECATED = "deprecated"      # Obsolète, à remplacer


class RelationType(str, Enum):
    """
    Types de relations entre documents.

    Permet de construire un knowledge graph éducatif.
    """
    PREREQUISITE = "prerequisite"  # Concept prérequis strict
    RELATED = "related"            # Concept lié/similaire
    EXTENDS = "extends"            # Approfondit un concept
    APPLIES_TO = "applies_to"      # Application pratique
    CONTRASTS = "contrasts"        # Concept opposé/comparaison
    EXAMPLE_OF = "example_of"      # Exemple d'un concept


# =============================================================================
# MODÈLES AUXILIAIRES - Relations et contenu enrichi
# =============================================================================

class DocumentRelation(BaseModel):
    """
    Relation entre deux documents (knowledge graph).

    Permet de construire un graphe de connaissances navigable.
    """
    target_id: str = Field(
        ...,
        description="UUID du document cible"
    )
    relation_type: RelationType = Field(
        ...,
        description="Type de relation"
    )
    strength: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Force de la relation (0-1)"
    )
    description: str | None = Field(
        None,
        max_length=200,
        description="Description optionnelle de la relation"
    )


class EnrichedContent(BaseModel):
    """
    Contenu enrichi pour support multimodal.

    Permet d'ajouter formules LaTeX, diagrammes, exemples interactifs.
    """
    latex_formulas: list[str] | None = Field(
        None,
        max_length=20,
        description="Formules mathématiques en LaTeX"
    )
    diagrams: list[dict] | None = Field(
        None,
        max_length=10,
        description="Références à des diagrammes (format: {type, url, caption})"
    )
    code_examples: list[dict] | None = Field(
        None,
        max_length=5,
        description="Exemples de code (format: {language, code, description})"
    )
    interactive_elements: list[dict] | None = Field(
        None,
        max_length=5,
        description="Éléments interactifs (format: {type, config, description})"
    )


class QualityMetrics(BaseModel):
    """
    Métriques de qualité automatisées pour un document.

    Calculées automatiquement lors de l'ingestion.
    """
    completeness_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Score de complétude (metadata, keywords, etc.)"
    )
    readability_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Score de lisibilité (longueur phrases, complexité)"
    )
    structure_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Score de structure (paragraphes, exemples)"
    )
    embedding_quality: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Qualité de l'embedding (cohérence, distinctivité)"
    )
    overall_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Score global de qualité"
    )


# =============================================================================
# DOCUMENT - Unité de base du dataset (VERSION 2.0 - RAG 2025)
# =============================================================================

class Document(BaseModel):
    """
    Document éducatif unitaire pour RAG (VERSION 2.0 - Best Practices 2025).

    Optimisé pour:
    - Chunking: 256-512 tokens (cible 300-400) pour retrieval optimal
    - Metadata enrichie: versioning, qualité, relations, contexte
    - Knowledge graph: relations explicites entre concepts
    - Traçabilité: timestamps, auteurs, révisions
    - Contenu enrichi: LaTeX, diagrammes, exemples interactifs

    Un document = une unité de connaissance autonome et cohérente.
    """

    # === Identification unique ===
    id: str | None = Field(
        None,
        description="UUID unique du document (généré automatiquement si absent)"
    )

    title: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="Titre descriptif et unique du document"
    )

    # === Classification hiérarchique ===
    domaine: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Domaine du programme (ex: 'Nombres et Calculs', 'Grammaire')"
    )
    sousdomaine: str | None = Field(
        None,
        max_length=50,
        description="Sous-domaine optionnel pour granularité"
    )

    # === Metadata pédagogique ===
    content_type: ContentType = Field(
        ...,
        description="Type de contenu pour adaptation du prompting"
    )
    difficulty: Difficulty = Field(
        default=Difficulty.STANDARD,
        description="Niveau de difficulté"
    )

    # === Contenu principal (OPTIMISÉ 2025: 300-400 tokens cible) ===
    content: str = Field(
        ...,
        min_length=200,    # ~50 tokens minimum (accepte contenu atomique)
        max_length=2400,   # ~600 tokens maximum
        description="Contenu pédagogique principal (cible 1200-1600 chars = 300-400 tokens, min 200 chars pour contenu atomique)"
    )

    # === Metadata pour retrieval ===
    keywords: list[str] | None = Field(
        None,
        max_length=15,
        description="Mots-clés pour améliorer le retrieval (15 max)"
    )

    # === Relations et knowledge graph ===
    prerequis: list[str] | None = Field(
        None,
        max_length=10,
        description="IDs des concepts prérequis (pour parcours pédagogique)"
    )
    relations: list[DocumentRelation] | None = Field(
        None,
        max_length=20,
        description="Relations explicites avec d'autres documents"
    )

    # === Contexte d'utilisation RAG ===
    typical_questions: list[str] | None = Field(
        None,
        max_length=10,
        description="Questions types auxquelles ce document répond"
    )
    learning_objectives: list[str] | None = Field(
        None,
        max_length=5,
        description="Objectifs pédagogiques couverts"
    )
    common_errors: list[str] | None = Field(
        None,
        max_length=5,
        description="Erreurs courantes liées à ce concept"
    )

    # === Contenu enrichi (multimodal) ===
    enriched: EnrichedContent | None = Field(
        None,
        description="Contenu enrichi: LaTeX, diagrammes, code, interactifs"
    )

    # === Versioning et traçabilité ===
    version: str = Field(
        default="1.0.0",
        pattern=r"^\d+\.\d+\.\d+$",
        description="Version sémantique du document"
    )
    created_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Date de création ISO 8601"
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Date de dernière modification ISO 8601"
    )
    author: str | None = Field(
        None,
        max_length=100,
        description="Auteur du contenu (humain ou IA)"
    )
    source_revision: str | None = Field(
        None,
        max_length=50,
        description="Révision du programme source (ex: 'BO 30/07/2020')"
    )

    # === Qualité et validation ===
    review_status: ReviewStatus = Field(
        default=ReviewStatus.DRAFT,
        description="Statut de validation du document"
    )
    validated_by: str | None = Field(
        None,
        max_length=100,
        description="Validateur (expert humain)"
    )
    quality: QualityMetrics | None = Field(
        None,
        description="Métriques de qualité automatisées"
    )
    confidence_level: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Niveau de confiance de la source (0-1)"
    )

    # === Tags et filtres additionnels ===
    tags: list[str] | None = Field(
        None,
        max_length=10,
        description="Tags libres pour catégorisation flexible"
    )

    @field_validator('content')
    @classmethod
    def validate_token_estimate(cls, v: str) -> str:
        """
        Valide que le contenu respecte les best practices 2025 pour chunking.

        Cible: 300-400 tokens (1200-1600 chars en français)
        Acceptable: 50-600 tokens (200-2400 chars)
        Atomique: 50-150 tokens pour contenu très spécifique (vocabulaire, définitions courtes)
        """
        token_estimate = len(v) / 4  # Approximation: 1 token ≈ 4 chars français

        if token_estimate < 50:
            raise ValueError(
                f"Contenu trop court (~{int(token_estimate)} tokens, min 50). "
                f"Même pour du contenu atomique, un minimum de contexte est nécessaire."
            )
        if token_estimate > 600:
            raise ValueError(
                f"Contenu trop long (~{int(token_estimate)} tokens, max 600). "
                f"Diviser en plusieurs documents pour meilleur retrieval."
            )

        return v

    @model_validator(mode='after')
    def compute_quality_if_missing(self) -> 'Document':
        """Calcule automatiquement les métriques de qualité si absentes."""
        if self.quality is None:
            self.quality = self._compute_quality_metrics()
        return self

    def _compute_quality_metrics(self) -> QualityMetrics:
        """
        Calcule les métriques de qualité automatisées.

        Best practice 2025: scoring automatisé pour QA.
        """
        # Complétude (presence de metadata optionnelles)
        completeness = 0.0
        if self.keywords and len(self.keywords) >= 5:
            completeness += 0.2
        if self.prerequis and len(self.prerequis) >= 2:
            completeness += 0.15
        if self.typical_questions and len(self.typical_questions) >= 3:
            completeness += 0.15
        if self.learning_objectives:
            completeness += 0.15
        if self.enriched:
            completeness += 0.15
        if self.relations:
            completeness += 0.2

        # Lisibilité (longueur moyenne des phrases)
        sentences = self.content.count('.') + self.content.count('!') + self.content.count('?')
        avg_sentence_length = len(self.content) / max(sentences, 1)
        readability = 1.0 if 50 <= avg_sentence_length <= 150 else 0.6

        # Structure (présence d'exemples)
        structure = 0.7
        if "exemple" in self.content.lower() or "ex:" in self.content.lower():
            structure += 0.3

        # Score global
        overall = (completeness * 0.4 + readability * 0.3 + structure * 0.3)

        return QualityMetrics(
            completeness_score=min(completeness, 1.0),
            readability_score=readability,
            structure_score=structure,
            overall_score=overall
        )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "math_5eme_pythagore_001",
                    "title": "Théorème de Pythagore - Énoncé, conditions et applications",
                    "domaine": "Géométrie",
                    "sousdomaine": "Triangles rectangles",
                    "content_type": "theoreme",
                    "difficulty": "standard",
                    "content": "Dans un triangle rectangle, le carré de l'hypoténuse est égal à la somme des carrés des deux autres côtés. Si ABC est un triangle rectangle en A, alors BC² = AB² + AC². Ce théorème ne s'applique QUE dans un triangle rectangle. L'hypoténuse est toujours le côté opposé à l'angle droit, c'est le plus grand côté du triangle. Exemple d'application : Dans un triangle rectangle dont les côtés de l'angle droit mesurent 3 cm et 4 cm, l'hypoténuse mesure √(3² + 4²) = √(9 + 16) = √25 = 5 cm. Cette relation permet de vérifier qu'un triangle est rectangle : si BC² = AB² + AC², alors le triangle ABC est rectangle en A. Attention aux erreurs courantes : ne pas confondre l'hypoténuse avec un des côtés de l'angle droit, et bien identifier l'angle droit avant d'appliquer le théorème.",
                    "keywords": ["pythagore", "triangle rectangle", "hypoténuse", "carré", "théorème", "géométrie", "côtés", "angle droit"],
                    "prerequis": ["math_5eme_triangle_rectangle_001", "math_5eme_carre_nombre_001"],
                    "typical_questions": [
                        "Comment calculer l'hypoténuse d'un triangle rectangle ?",
                        "Qu'est-ce que le théorème de Pythagore ?",
                        "Comment vérifier qu'un triangle est rectangle ?"
                    ],
                    "learning_objectives": [
                        "Connaître et appliquer le théorème de Pythagore",
                        "Calculer la longueur d'un côté d'un triangle rectangle"
                    ],
                    "common_errors": [
                        "Confondre l'hypoténuse avec un côté de l'angle droit",
                        "Appliquer le théorème à un triangle non rectangle"
                    ],
                    "enriched": {
                        "latex_formulas": ["BC^2 = AB^2 + AC^2", "c^2 = a^2 + b^2"]
                    },
                    "version": "1.0.0",
                    "author": "Éduscol - Programme officiel",
                    "source_revision": "BO 30/07/2020",
                    "review_status": "validated",
                    "confidence_level": 1.0,
                    "tags": ["essentiel", "programme_5eme", "géométrie_plane"]
                }
            ]
        }
    }


# =============================================================================
# DATASET METADATA - Informations globales du fichier
# =============================================================================

class DatasetMetadata(BaseModel):
    """
    Métadonnées d'un fichier JSONL de dataset.

    Stocké dans un fichier metadata.json à côté des JSONL.
    Permet versioning et traçabilité.
    """
    name: str = Field(..., description="Nom du dataset")
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$", description="Version semver")
    description: str = Field(..., description="Description du contenu")

    # Source officielle
    source: str = Field(..., description="Source officielle (ex: Éduscol)")
    source_url: str | None = Field(None, description="URL de la source")
    source_date: str | None = Field(None, description="Date du programme (ex: BO 30/07/2020)")

    # Scope du dataset
    cycle: Cycle
    niveau: NiveauCollege | NiveauLycee
    matiere: Matiere

    # Stats (mises à jour automatiquement)
    document_count: int = Field(0, description="Nombre de documents")
    total_tokens: int = Field(0, description="Estimation tokens totaux")

    # Qualité
    validated: bool = Field(False, description="Dataset validé par le schema")
    last_updated: str | None = Field(None, description="Date dernière mise à jour ISO")


# =============================================================================
# TYPE ALIASES
# =============================================================================

Niveau = NiveauCollege | NiveauLycee
