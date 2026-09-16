"""
Configuration des SOURCES d'ingestion — quels fichiers, quelle matière, quelle
section extraire.

Données pures (aucun appel réseau, aucun état mutable) : l'ordre des matières
dans chaque document `.md` et la table `SOURCES` consommée par le pipeline
d'ingestion. Séparé de `ingest.py` pour garder chaque fichier sous la limite de
400 lignes.
"""

from __future__ import annotations

import re

from schema import Matiere


def markdown_matiere_sources(
    file: str,
    document_order: list[tuple[Matiere | None, str]],
    *,
    exclude: set[Matiere] | None = None,
) -> list[dict]:
    """
    Génère les SOURCES pour un fichier markdown multi-matières.

    Chaque entrée extrait la section comprise entre `## **Matière**` et le
    `## **MatièreSuivante**` (calculé depuis l'ORDRE RÉEL du document, pour
    que section_end pointe sur la bonne frontière même si une matière est
    exclue de l'extraction).

    Args
    ----
    file : nom du fichier source (sans extension).
    document_order : [(Matiere | None, label), ...] dans l'ordre exact des
        `## **Titre**` markdown. Une matière=None marque une section présente
        dans le doc mais qu'on ne veut pas indexer (sentinelle pour section_end
        seulement).
    exclude : matières listées dans document_order à NE PAS matérialiser
        (typique : version BO obsolète remplacée par un fichier dédié plus
        récent). Conservées dans document_order pour calculer section_end.
    """
    exclude = exclude or set()
    sources: list[dict] = []
    for i, (matiere, label) in enumerate(document_order):
        if matiere is None or matiere in exclude:
            continue
        start = rf"^## \*\*{re.escape(label)}\*\*"
        # section_end = la prochaine entrée du document_order (peu importe
        # qu'elle soit exclue ou non — on veut juste savoir où s'arrête la
        # section courante dans le PDF).
        if i + 1 < len(document_order):
            next_labels = [re.escape(lbl) for _, lbl in document_order[i + 1 :]]
            end: str | None = r"^## \*\*(?:" + "|".join(next_labels) + r")\*\*"
        else:
            end = None
        sources.append(
            {
                "file": file,
                "matiere": matiere,
                "section_pattern": start,
                "section_end": end,
                "blank_line_after_header": False,  # markdown H2 = pas d'ambiguïté TOC
                "section_name": label,
            }
        )
    return sources


# Matières du programme cycle 3 BO 2020 — ordre des `## **Titre**` dans le .md
_CYCLE3_DOCUMENT_ORDER: list[tuple[Matiere | None, str]] = [
    (Matiere.FRANCAIS, "Français"),
    (Matiere.LANGUES_VIVANTES, "Langues vivantes (étrangères ou régionales)"),
    (Matiere.ARTS_PLASTIQUES, "Arts plastiques"),
    (Matiere.EDUCATION_MUSICALE, "Éducation musicale"),
    (Matiere.HISTOIRE_DES_ARTS, "Histoire des arts"),
    (Matiere.EDUCATION_PHYSIQUE_SPORTIVE, "Éducation physique et sportive"),
    (Matiere.EMC, "Enseignement moral et civique"),
    (Matiere.HISTOIRE_GEO, "Histoire et géographie"),
    (Matiere.SCIENCES_TECHNOLOGIE, "Sciences et technologie"),
    (Matiere.MATHEMATIQUES, "Mathématiques"),
]

# Matières du programme cycle 4 BO 2020 — ordre EXACT du document .md
# (utilisé pour calculer section_end). Maths & Techno présents dans la liste
# mais exclus de l'extraction (superseded par programme_maths_cycle4_BO2026 et
# programme_technologie_cycle4_BO2024 — sinon doublon).
_CYCLE4_DOCUMENT_ORDER: list[tuple[Matiere | None, str]] = [
    (Matiere.FRANCAIS, "Français"),
    (Matiere.LANGUES_VIVANTES, "Langues vivantes (étrangères ou régionales)"),
    (Matiere.ARTS_PLASTIQUES, "Arts plastiques"),
    (Matiere.EDUCATION_MUSICALE, "Éducation musicale"),
    (Matiere.HISTOIRE_DES_ARTS, "Histoire des arts"),
    (Matiere.EDUCATION_PHYSIQUE_SPORTIVE, "Éducation physique et sportive"),
    (Matiere.EMC, "Enseignement moral et civique"),
    (Matiere.HISTOIRE_GEO, "Histoire et géographie"),
    (Matiere.PHYSIQUE_CHIMIE, "Physique-Chimie"),
    (Matiere.SVT, "Sciences de la vie et de la Terre"),
    (Matiere.TECHNOLOGIE, "Technologie"),  # exclu, sentinelle section_end
    (Matiere.MATHEMATIQUES, "Mathématiques"),  # exclu, sentinelle section_end
]
_CYCLE4_EXCLUDE: set[Matiere] = {Matiere.TECHNOLOGIE, Matiere.MATHEMATIQUES}


SOURCES: list[dict] = [
    # ── Fichiers mono-matière (tout le fichier — .md préféré au .txt) ──
    {
        "file": "programme_maths_cycle4_BO2026",
        "matiere": Matiere.MATHEMATIQUES,
        "section_pattern": None,
        "section_name": "Mathématiques",
    },
    {
        "file": "programme_technologie_cycle4_BO2024",
        "matiere": Matiere.TECHNOLOGIE,
        "section_pattern": None,
        "section_name": "Technologie",
    },
    {
        "file": "programme_anglais_college_BO2025",
        "matiere": Matiere.ANGLAIS,
        "section_pattern": None,
        "section_name": "Anglais",
    },
    {
        "file": "programme_espagnol_college_BO2025",
        "matiere": Matiere.ESPAGNOL,
        "section_pattern": None,
        "section_name": "Espagnol",
    },
    {
        "file": "programme_allemand_college_BO2025",
        "matiere": Matiere.ALLEMAND,
        "section_pattern": None,
        "section_name": "Allemand",
    },
    {
        "file": "programme_italien_college_BO2025",
        "matiere": Matiere.ITALIEN,
        "section_pattern": None,
        "section_name": "Italien",
    },
    # ── Programmes BO 2020 multi-matières (extraction par H2 markdown) ──
    *markdown_matiere_sources(
        "programme_cycle4_BO2020",
        _CYCLE4_DOCUMENT_ORDER,
        exclude=_CYCLE4_EXCLUDE,
    ),
    *markdown_matiere_sources("programme_cycle3_BO2020", _CYCLE3_DOCUMENT_ORDER),
]
