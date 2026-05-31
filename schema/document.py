"""
Schéma Pydantic pour le pipeline RAG éducatif TomAI.

Un Chunk = une unité textuelle extraite des programmes officiels Éduscol,
chunkée, embedée, et stockée dans Qdrant.

Source de vérité : data/raw/*.md (préférée) ou *.txt (fallback).

Voir docs/ARCHITECTURE.md pour les décisions architecturales.
"""

from __future__ import annotations

import re
import uuid
from enum import Enum

from pydantic import BaseModel, Field

# ── Vocabulaire contrôlé ─────────────────────────────────────────────────────


class NiveauCollege(str, Enum):
    SIXIEME = "sixieme"
    CINQUIEME = "cinquieme"
    QUATRIEME = "quatrieme"
    TROISIEME = "troisieme"


class NiveauLycee(str, Enum):
    SECONDE = "seconde"
    PREMIERE = "premiere"
    TERMINALE = "terminale"


Niveau = NiveauCollege | NiveauLycee


class Cycle(str, Enum):
    CYCLE3 = "cycle3"  # 6ème (+ CM1/CM2 côté primaire, hors scope MVP)
    CYCLE4 = "cycle4"  # 5ème, 4ème, 3ème
    LYCEE = "lycee"


def cycle_from_niveau(niveau: Niveau | str) -> Cycle:
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


# ── Matières (vocabulaire EU contrôlé) ───────────────────────────────────────


class Matiere(str, Enum):
    # Tronc commun collège + lycée
    MATHEMATIQUES = "mathematiques"
    FRANCAIS = "francais"
    HISTOIRE_GEO = "histoire_geo"
    PHYSIQUE_CHIMIE = "physique_chimie"
    SVT = "svt"
    EMC = "emc"
    TECHNOLOGIE = "technologie"
    # Cycle 3 (6e) : Sciences et technologie est une matière unifiée (vs séparée en cycle 4)
    SCIENCES_TECHNOLOGIE = "sciences_technologie"
    # Arts, musique, EPS — cycle 3 ET cycle 4
    ARTS_PLASTIQUES = "arts_plastiques"
    EDUCATION_MUSICALE = "education_musicale"
    HISTOIRE_DES_ARTS = "histoire_des_arts"
    EDUCATION_PHYSIQUE_SPORTIVE = "eps"
    # Langues vivantes (BO 2025 = un fichier par langue)
    ANGLAIS = "anglais"
    ESPAGNOL = "espagnol"
    ALLEMAND = "allemand"
    ITALIEN = "italien"
    # Langues vivantes générique (utilisé pour la section "Langues vivantes" du
    # programme cycle 3 BO 2020 qui ne spécifie pas la langue — le contenu est
    # méta-pédagogique commun à toutes les LV).
    LANGUES_VIVANTES = "langues_vivantes"
    # Lycée — vocabulaire prêt pour extension future
    SNT = "snt"
    ENSEIGNEMENT_SCIENTIFIQUE = "enseignement_scientifique"
    PHILOSOPHIE = "philosophie"
    SES = "ses"
    NSI = "nsi"
    HGGSP = "hggsp"
    HLP = "hlp"


# Labels affichables (utilisés par le préfixe contextuel — voir schema/contextual.py)
MATIERE_LABELS: dict[Matiere, str] = {
    Matiere.MATHEMATIQUES: "Mathématiques",
    Matiere.FRANCAIS: "Français",
    Matiere.HISTOIRE_GEO: "Histoire-Géographie",
    Matiere.PHYSIQUE_CHIMIE: "Physique-Chimie",
    Matiere.SVT: "Sciences de la Vie et de la Terre",
    Matiere.EMC: "Enseignement Moral et Civique",
    Matiere.TECHNOLOGIE: "Technologie",
    Matiere.SCIENCES_TECHNOLOGIE: "Sciences et Technologie",
    Matiere.ARTS_PLASTIQUES: "Arts plastiques",
    Matiere.EDUCATION_MUSICALE: "Éducation musicale",
    Matiere.HISTOIRE_DES_ARTS: "Histoire des arts",
    Matiere.EDUCATION_PHYSIQUE_SPORTIVE: "Éducation physique et sportive",
    Matiere.ANGLAIS: "Anglais",
    Matiere.ESPAGNOL: "Espagnol",
    Matiere.ALLEMAND: "Allemand",
    Matiere.ITALIEN: "Italien",
    Matiere.LANGUES_VIVANTES: "Langues vivantes",
    Matiere.SNT: "Sciences Numériques et Technologie",
    Matiere.ENSEIGNEMENT_SCIENTIFIQUE: "Enseignement Scientifique",
    Matiere.PHILOSOPHIE: "Philosophie",
    Matiere.SES: "Sciences Économiques et Sociales",
    Matiere.NSI: "Numérique et Sciences Informatiques",
    Matiere.HGGSP: "Histoire-Géographie, Géopolitique et Sciences Politiques",
    Matiere.HLP: "Humanités, Littérature et Philosophie",
}


# ── Dérivation cycle/niveaux depuis le nom de fichier source ─────────────────

# Patterns extraits du nommage Éduscol observé dans data/raw/ :
# - programme_*_cycle4_BO* → cycle 4 (5ème, 4ème, 3ème)
# - programme_*_cycle3_BO* → cycle 3 (6ème pour le collège — primaire hors scope)
# - programme_*_college_BO* → collège entier (cycle 3 + cycle 4)
# - programme_*_lycee_BO*   → lycée (seconde, première, terminale)

_FILE_NIVEAUX_PATTERNS: list[
    tuple[re.Pattern[str], Cycle, tuple[NiveauCollege | NiveauLycee, ...]]
] = [
    (
        re.compile(r"_cycle4_", re.IGNORECASE),
        Cycle.CYCLE4,
        (NiveauCollege.CINQUIEME, NiveauCollege.QUATRIEME, NiveauCollege.TROISIEME),
    ),
    (
        re.compile(r"_cycle3_", re.IGNORECASE),
        Cycle.CYCLE3,
        (NiveauCollege.SIXIEME,),
    ),
    (
        re.compile(r"_college_", re.IGNORECASE),
        # College = cycle 3 (6e) + cycle 4 (5e/4e/3e). Cycle field = cycle4 par défaut
        # car la majorité des chunks vise le cycle 4 ; le filtrage côté backend doit
        # gérer la disambiguation via le champ `niveau` qui reste le filtre canonique.
        Cycle.CYCLE4,
        (
            NiveauCollege.SIXIEME,
            NiveauCollege.CINQUIEME,
            NiveauCollege.QUATRIEME,
            NiveauCollege.TROISIEME,
        ),
    ),
    (
        re.compile(r"_lycee_", re.IGNORECASE),
        Cycle.LYCEE,
        (NiveauLycee.SECONDE, NiveauLycee.PREMIERE, NiveauLycee.TERMINALE),
    ),
]


def derive_niveaux_from_file(
    source_file: str,
) -> tuple[Cycle, tuple[NiveauCollege | NiveauLycee, ...]]:
    """
    Dérive (cycle, niveaux) depuis le nom du fichier source.

    Le pipeline duplique chaque chunk une fois par niveau retourné (même embed,
    payload distinct) — voir docs/ARCHITECTURE.md §Multi-niveau pour la
    justification du choix duplication vs payload-multi-value.

    Lève ValueError si aucun pattern ne matche : la dérivation doit être explicite,
    pas silencieusement vide.
    """
    for pattern, cycle, niveaux in _FILE_NIVEAUX_PATTERNS:
        if pattern.search(source_file):
            return cycle, niveaux
    raise ValueError(
        f"Impossible de dériver cycle/niveaux depuis '{source_file}'. "
        f"Attendu un suffixe parmi : _cycle3_, _cycle4_, _college_, _lycee_."
    )


# ── Chunk — unité RAG ────────────────────────────────────────────────────────


class Chunk(BaseModel):
    """
    Chunk textuel extrait d'un programme officiel, prêt pour embedding Qdrant.

    Le `text` stocké est le texte BRUT du programme (sans préfixe contextuel) :
    c'est ce qui sera affiché au LLM comme contexte. Le texte embeddé est calculé
    séparément par `schema/contextual.py:build_contextual_text(chunk)`.

    Payload stocké dans Qdrant : schema canonique pur (text, section, matiere,
    niveau, cycle, source_file, chunk_index). Aucun champ alias (title/content)
    ni champ LLM-generated (domaine/difficulty/content_type) — le dataset reste
    strictement vérifiable contre les BO officiels.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str = Field(..., min_length=50, description="Texte BRUT du chunk (≈400 tokens)")
    source_file: str = Field(..., description="Nom du fichier .txt source (sans extension)")
    matiere: Matiere
    niveau: NiveauCollege | NiveauLycee = Field(
        ...,
        description="Niveau scolaire spécifique. Pour cycle4, le chunk est dupliqué 1× par niveau.",
    )
    section: str = Field(..., description="Section du programme (ex: 'Nombres et calculs')")
    chunk_index: int = Field(ge=0, description="Position ordinale dans le fichier source")

    @property
    def cycle(self) -> Cycle:
        return cycle_from_niveau(self.niveau)

    @property
    def matiere_label(self) -> str:
        return MATIERE_LABELS[self.matiere]

    def to_qdrant_payload(self) -> dict[str, str | int]:
        """
        Payload Qdrant canonique — schema pur sans alias compat.

        Le backend (tomai-monorepo/apps/server/src/services/qdrant.service.ts)
        lit directement ces champs. Pas de doublons title/content, ni de champs
        LLM-generated (cf. docs/ARCHITECTURE.md §Schema Chunk).
        """
        return {
            "text": self.text,
            "source_file": self.source_file,
            "matiere": self.matiere.value,
            "niveau": self.niveau.value,
            "cycle": self.cycle.value,
            "section": self.section,
            "chunk_index": self.chunk_index,
        }
