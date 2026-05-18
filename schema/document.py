"""
Schéma Pydantic pour le pipeline RAG éducatif TomAI.

Un Chunk = une unité textuelle extraite des programmes officiels Éduscol,
chunkée, embedée, et stockée dans Qdrant.

Source de vérité : data/raw/*.txt (programmes officiels extraits par pdftotext).
"""

from __future__ import annotations

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
    CYCLE3 = "cycle3"  # 6ème
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


class Matiere(str, Enum):
    MATHEMATIQUES = "mathematiques"
    FRANCAIS = "francais"
    HISTOIRE_GEO = "histoire_geo"
    PHYSIQUE_CHIMIE = "physique_chimie"
    SVT = "svt"
    EMC = "emc"
    TECHNOLOGIE = "technologie"
    ANGLAIS = "anglais"
    ESPAGNOL = "espagnol"
    ALLEMAND = "allemand"
    ITALIEN = "italien"
    # Lycée
    SNT = "snt"
    ENSEIGNEMENT_SCIENTIFIQUE = "enseignement_scientifique"
    PHILOSOPHIE = "philosophie"
    SES = "ses"
    NSI = "nsi"
    HGGSP = "hggsp"
    HLP = "hlp"


# ── Chunk — unité RAG ────────────────────────────────────────────────────────


class Chunk(BaseModel):
    """
    Chunk textuel extrait d'un programme officiel, prêt pour embedding Qdrant.

    Payload stocké dans Qdrant : tous les champs sauf `id` (utilisé comme point_id).
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str = Field(..., min_length=50, description="Texte du chunk (≈400 tokens)")
    source_file: str = Field(..., description="Nom du fichier .txt source (sans extension)")
    matiere: Matiere
    niveau: NiveauCollege = NiveauCollege.CINQUIEME
    section: str = Field(..., description="Section du programme (ex: 'Nombres et calculs')")
    chunk_index: int = Field(ge=0, description="Position ordinale dans le fichier source")

    @property
    def cycle(self) -> Cycle:
        return cycle_from_niveau(self.niveau)

    def to_qdrant_payload(self) -> dict:
        return {
            "text": self.text,
            "source_file": self.source_file,
            "matiere": self.matiere.value,
            "niveau": self.niveau.value,
            "cycle": self.cycle.value,
            "section": self.section,
            "chunk_index": self.chunk_index,
        }
