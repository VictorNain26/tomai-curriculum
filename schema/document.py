"""
Schema Pydantic pour les documents éducatifs TomAI.

Best practices RAG 2025:
- Chunking optimal: 400-512 tokens avec 10-20% overlap
- Metadata structurée mais pas excessive
- Hiérarchie: Cycle → Niveau → Matière → Domaine → Document

Sources:
- https://developer.nvidia.com/blog/finding-the-best-chunking-strategy-for-accurate-ai-responses/
- https://www.datasciencecentral.com/best-practices-for-structuring-large-datasets-in-rag/
- https://huggingface.co/blog/tegridydev/llm-dataset-formats-101-hugging-face
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


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


# =============================================================================
# DOCUMENT - Unité de base du dataset
# =============================================================================

class Document(BaseModel):
    """
    Document éducatif unitaire pour RAG.

    Optimisé pour:
    - Chunking: 400-512 tokens (content entre 200-2000 chars)
    - Retrieval: metadata structurée pour filtrage
    - Embedding: titre + domaine + content pour contexte complet

    Un document = une notion/méthode/définition autonome et cohérente.
    """

    # === Identification ===
    title: str = Field(
        ...,
        min_length=10,
        max_length=150,
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

    # === Contenu principal ===
    content: str = Field(
        ...,
        min_length=100,   # Minimum pour contexte utile
        max_length=2500,  # ~500 tokens max pour chunking optimal
        description="Contenu pédagogique principal"
    )

    # === Metadata optionnelle pour enrichissement ===
    keywords: list[str] | None = Field(
        None,
        max_length=10,
        description="Mots-clés pour améliorer le retrieval"
    )
    prerequis: list[str] | None = Field(
        None,
        max_length=5,
        description="Concepts prérequis (liens entre documents)"
    )

    @field_validator('content')
    @classmethod
    def validate_token_estimate(cls, v: str) -> str:
        """Estime les tokens et avertit si hors range optimal."""
        # Approximation: 1 token ≈ 4 caractères en français
        token_estimate = len(v) / 4
        if token_estimate < 50:
            raise ValueError(f"Contenu trop court (~{int(token_estimate)} tokens, min 50)")
        if token_estimate > 600:
            raise ValueError(f"Contenu trop long (~{int(token_estimate)} tokens, max 600)")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "title": "Théorème de Pythagore - Énoncé et conditions",
                    "domaine": "Géométrie",
                    "sousdomaine": "Triangles",
                    "content_type": "theoreme",
                    "difficulty": "standard",
                    "content": "Dans un triangle rectangle, le carré de l'hypoténuse est égal à la somme des carrés des deux autres côtés. Si ABC est un triangle rectangle en A, alors BC² = AB² + AC². Ce théorème ne s'applique QUE dans un triangle rectangle. L'hypoténuse est toujours le côté opposé à l'angle droit, c'est le plus grand côté du triangle.",
                    "keywords": ["pythagore", "triangle rectangle", "hypoténuse", "carré"],
                    "prerequis": ["Triangle rectangle", "Carré d'un nombre"]
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
