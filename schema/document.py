"""
Schema Pydantic pour les documents éducatifs TomAI.

Principes (alignés sur la spec RAG overhaul mai 2026) :
- Chunking : 200-2400 chars (~50-600 tokens), cible 1200-1600 chars (~300-400 tokens)
- Metadata enrichie : versioning, qualité, relations, contexte d'usage
- Traçabilité : timestamps, auteurs, révisions
- Knowledge graph : relations explicites entre concepts (DocumentRelation)
- Support contenu enrichi : LaTeX, diagrammes, exemples interactifs

Voir `docs/specs/2026-05-09-rag-overhaul-design.md` et `docs/adr/0001-rag-overhaul.md`
pour le détail des décisions architecturales et leurs sources.
"""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from schema._examples import DOCUMENT_EXAMPLES

# =============================================================================
# ENUMS - Vocabulaire contrôlé
# =============================================================================


class Cycle(str, Enum):
    """
    Cycles scolaires français — scope Tom mai 2026 : 6ème → Terminale.
    Le primaire (cycle 2 CP-CE2, cycle 3 CM1-CM2) sera ajouté ultérieurement.
    """

    CYCLE3 = "cycle3"  # 6ème uniquement (le reste du cycle 3 est primaire, hors scope actuel)
    CYCLE4 = "cycle4"  # 5ème, 4ème, 3ème
    LYCEE = "lycee"  # 2nde, 1ère, Terminale


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


# Type alias défini ici pour pouvoir être utilisé dans le Document plus bas.
Niveau = NiveauCollege | NiveauLycee


def cycle_from_niveau(niveau: Niveau | str) -> Cycle:
    """
    Dérive le cycle Éduscol depuis le niveau.

    - sixième → CYCLE3 (seule année cycle 3 dans le scope, le reste est primaire)
    - 5e, 4e, 3e → CYCLE4
    - 2nde, 1ère, Terminale → LYCEE
    """
    value = niveau.value if isinstance(niveau, Enum) else niveau
    if value == NiveauCollege.SIXIEME.value:
        return Cycle.CYCLE3
    if value in {
        NiveauCollege.CINQUIEME.value,
        NiveauCollege.QUATRIEME.value,
        NiveauCollege.TROISIEME.value,
    }:
        return Cycle.CYCLE4
    if value in {n.value for n in NiveauLycee}:
        return Cycle.LYCEE
    raise ValueError(f"Niveau inconnu: {niveau}")


class Matiere(str, Enum):
    """
    Matières supportées par TomAI (6ème → Terminale).
    Source de vérité unique : tout JSONL ingéré doit utiliser une de ces valeurs.
    """

    # Tronc commun collège + lycée
    MATHEMATIQUES = "mathematiques"
    FRANCAIS = "francais"
    HISTOIRE_GEO = "histoire_geo"
    PHYSIQUE_CHIMIE = "physique_chimie"
    SVT = "svt"
    EMC = "emc"
    # Langues vivantes
    ANGLAIS = "anglais"
    ALLEMAND = "allemand"
    ESPAGNOL = "espagnol"
    ITALIEN = "italien"
    # Spécifiques collège
    TECHNOLOGIE = "technologie"
    SCIENCES_TECHNOLOGIE = "sciences_technologie"
    # Tronc commun lycée
    SNT = "snt"
    ENSEIGNEMENT_SCIENTIFIQUE = "enseignement_scientifique"
    PHILOSOPHIE = "philosophie"
    # Spécialités lycée
    SES = "ses"
    NSI = "nsi"
    HGGSP = "hggsp"
    LLCER_ANGLAIS = "llcer_anglais"
    HLP = "hlp"
    # Options Terminale
    MATHEMATIQUES_COMPLEMENTAIRES = "mathematiques_complementaires"
    MATHEMATIQUES_EXPERTES = "mathematiques_expertes"


class ContentType(str, Enum):
    """
    Types de contenu pédagogique.

    Catégorisation pour filtrage metadata et adaptation du prompting.
    """

    DEFINITION = "definition"  # Définition officielle d'un concept
    THEOREME = "theoreme"  # Théorème/propriété mathématique
    FORMULE = "formule"  # Formule à retenir
    METHODE = "methode"  # Méthode de résolution pas à pas
    EXEMPLE = "exemple"  # Exemple illustratif
    ERREUR_COURANTE = "erreur_courante"  # Piège/erreur fréquente à éviter


class Difficulty(str, Enum):
    """
    Niveau de difficulté du contenu.

    Permet le filtrage par niveau de maîtrise de l'élève.
    """

    DECOUVERTE = "decouverte"  # Introduction, bases
    STANDARD = "standard"  # Niveau attendu du programme
    APPROFONDISSEMENT = "approfondissement"  # Pour aller plus loin


class ReviewStatus(str, Enum):
    """
    Statut de validation du document.

    Pipeline qualité: draft → reviewed → validated → published
    """

    DRAFT = "draft"  # Brouillon, non vérifié
    REVIEWED = "reviewed"  # Relu par un expert
    VALIDATED = "validated"  # Validé qualité + sources
    PUBLISHED = "published"  # Publié en production
    DEPRECATED = "deprecated"  # Obsolète, à remplacer


class RelationType(str, Enum):
    """
    Types de relations entre documents.

    Permet de construire un knowledge graph éducatif.
    """

    PREREQUISITE = "prerequisite"  # Concept prérequis strict
    RELATED = "related"  # Concept lié/similaire
    EXTENDS = "extends"  # Approfondit un concept
    APPLIES_TO = "applies_to"  # Application pratique
    CONTRASTS = "contrasts"  # Concept opposé/comparaison
    EXAMPLE_OF = "example_of"  # Exemple d'un concept


# =============================================================================
# MODÈLES AUXILIAIRES - Relations et contenu enrichi
# =============================================================================


class DocumentRelation(BaseModel):
    """
    Relation entre deux documents (knowledge graph).

    Permet de construire un graphe de connaissances navigable.
    """

    target_id: str = Field(..., description="UUID du document cible")
    relation_type: RelationType = Field(..., description="Type de relation")
    strength: float = Field(default=1.0, ge=0.0, le=1.0, description="Force de la relation (0-1)")
    description: str | None = Field(
        None, max_length=200, description="Description optionnelle de la relation"
    )


class EnrichedContent(BaseModel):
    """
    Contenu enrichi pour support multimodal.

    Permet d'ajouter formules LaTeX, diagrammes, exemples interactifs.
    """

    latex_formulas: list[str] | None = Field(
        None, max_length=20, description="Formules mathématiques en LaTeX"
    )
    diagrams: list[dict] | None = Field(
        None,
        max_length=10,
        description="Références à des diagrammes (format: {type, url, caption})",
    )
    code_examples: list[dict] | None = Field(
        None, max_length=5, description="Exemples de code (format: {language, code, description})"
    )
    interactive_elements: list[dict] | None = Field(
        None, max_length=5, description="Éléments interactifs (format: {type, config, description})"
    )


class QualityMetrics(BaseModel):
    """
    Métriques de qualité automatisées pour un document.

    Calculées automatiquement lors de l'ingestion.
    """

    completeness_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Score de complétude (metadata, keywords, etc.)"
    )
    readability_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Score de lisibilité (longueur phrases, complexité)",
    )
    structure_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Score de structure (paragraphes, exemples)"
    )
    embedding_quality: float | None = Field(
        None, ge=0.0, le=1.0, description="Qualité de l'embedding (cohérence, distinctivité)"
    )
    overall_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Score global de qualité")


# =============================================================================
# DOCUMENT - Unité de base du dataset (v2.0)
# =============================================================================


class Document(BaseModel):
    """
    Document éducatif unitaire pour RAG (v2.0).

    Optimisé pour :
    - Chunking : 200-2400 chars (~50-600 tokens), cible ~300-400 tokens
    - Metadata enrichie : versioning, qualité, relations, contexte
    - Knowledge graph : relations explicites entre concepts
    - Traçabilité : timestamps, auteurs, révisions
    - Contenu enrichi : LaTeX, diagrammes, exemples interactifs

    Un document = une unité de connaissance autonome et cohérente.
    """

    # === Identification unique ===
    id: str | None = Field(
        None, description="UUID unique du document (généré automatiquement si absent)"
    )

    title: str = Field(
        ..., min_length=10, max_length=200, description="Titre descriptif et unique du document"
    )

    # === Classification hiérarchique ===
    # niveau et matiere : optionnels pour rétrocompat avec les JSONL antérieurs
    # à la migration. Le pipeline d'ingestion remplit toujours ces champs (depuis
    # le path si absents) et les fichiers générés depuis la migration les ont
    # renseignés. Le cycle reste dérivable du niveau (cf. cycle_from_niveau).
    niveau: Niveau | None = Field(
        None,
        description="Niveau scolaire (sixieme, cinquieme, ..., terminale)",
    )
    matiere: Matiere | None = Field(
        None,
        description="Matière (mathematiques, francais, svt, ...)",
    )

    domaine: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Domaine du programme (ex: 'Nombres et Calculs', 'Grammaire')",
    )
    sousdomaine: str | None = Field(
        None, max_length=50, description="Sous-domaine optionnel pour granularité"
    )

    # === Metadata pédagogique ===
    content_type: ContentType = Field(
        ..., description="Type de contenu pour adaptation du prompting"
    )
    difficulty: Difficulty = Field(default=Difficulty.STANDARD, description="Niveau de difficulté")

    # === Contenu principal (OPTIMISÉ 2025: 300-400 tokens cible) ===
    content: str = Field(
        ...,
        min_length=200,  # ~50 tokens minimum (accepte contenu atomique)
        max_length=2400,  # ~600 tokens maximum
        description=(
            "Contenu pédagogique principal "
            "(cible 1200-1600 chars = 300-400 tokens, "
            "min 200 chars pour contenu atomique)"
        ),
    )

    # === Metadata pour retrieval ===
    keywords: list[str] | None = Field(
        None, max_length=15, description="Mots-clés pour améliorer le retrieval (15 max)"
    )

    # === Relations et knowledge graph ===
    prerequis: list[str] | None = Field(
        None, max_length=10, description="IDs des concepts prérequis (pour parcours pédagogique)"
    )
    relations: list[DocumentRelation] | None = Field(
        None, max_length=20, description="Relations explicites avec d'autres documents"
    )

    # === Contexte d'utilisation RAG ===
    typical_questions: list[str] | None = Field(
        None, max_length=10, description="Questions types auxquelles ce document répond"
    )
    learning_objectives: list[str] | None = Field(
        None, max_length=5, description="Objectifs pédagogiques couverts"
    )
    common_errors: list[str] | None = Field(
        None, max_length=5, description="Erreurs courantes liées à ce concept"
    )

    # === Contenu enrichi (multimodal) ===
    enriched: EnrichedContent | None = Field(
        None, description="Contenu enrichi: LaTeX, diagrammes, code, interactifs"
    )

    # === Versioning et traçabilité ===
    version: str = Field(
        default="1.0.0", pattern=r"^\d+\.\d+\.\d+$", description="Version sémantique du document"
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="Date de création ISO 8601 (UTC)",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="Date de dernière modification ISO 8601 (UTC)",
    )
    author: str | None = Field(None, max_length=100, description="Auteur du contenu (humain ou IA)")
    source_revision: str | None = Field(
        None, max_length=50, description="Révision du programme source (ex: 'BO 30/07/2020')"
    )

    # === Qualité et validation ===
    review_status: ReviewStatus = Field(
        default=ReviewStatus.DRAFT, description="Statut de validation du document"
    )
    validated_by: str | None = Field(None, max_length=100, description="Validateur (expert humain)")
    quality: QualityMetrics | None = Field(None, description="Métriques de qualité automatisées")
    confidence_level: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Niveau de confiance de la source (0-1)"
    )

    # === Tags et filtres additionnels ===
    tags: list[str] | None = Field(
        None, max_length=10, description="Tags libres pour catégorisation flexible"
    )

    @field_validator("content")
    @classmethod
    def validate_token_estimate(cls, v: str) -> str:
        """
        Valide que le contenu respecte les bornes de chunking.

        Cible : 300-400 tokens (1200-1600 chars en français).
        Acceptable : 50-600 tokens (200-2400 chars).
        Atomique : 50-150 tokens pour contenu très spécifique (vocabulaire, définitions courtes).
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

    def compute_quality(self) -> QualityMetrics:
        """
        Calcule et assigne les métriques de qualité.

        À appeler explicitement à l'ingestion (pas en model_validator) pour
        éviter les effets de bord à la simple validation : charger un JSONL pour
        valider ne doit pas modifier le score, sinon le stockage et la lecture
        peuvent diverger.
        """
        self.quality = self._compute_quality_metrics()
        return self.quality

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
        sentences = self.content.count(".") + self.content.count("!") + self.content.count("?")
        avg_sentence_length = len(self.content) / max(sentences, 1)
        readability = 1.0 if 50 <= avg_sentence_length <= 150 else 0.6

        # Structure (présence d'exemples)
        structure = 0.7
        if "exemple" in self.content.lower() or "ex:" in self.content.lower():
            structure += 0.3

        # Score global
        overall = completeness * 0.4 + readability * 0.3 + structure * 0.3

        return QualityMetrics(
            completeness_score=min(completeness, 1.0),
            readability_score=readability,
            structure_score=structure,
            overall_score=overall,
        )

    model_config = {
        "json_schema_extra": {"examples": DOCUMENT_EXAMPLES},
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
