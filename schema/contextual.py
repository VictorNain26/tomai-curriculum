"""
Contextual prefix — situe chaque chunk dans la hiérarchie Eduscol AVANT embedding.

Inspiré de la méthode "Contextual Retrieval" d'Anthropic (sept 2024) :
https://www.anthropic.com/news/contextual-retrieval

Anthropic mesure -35% failure rate (top-20 retrieval) avec embeddings contextualisés,
-49% combiné avec BM25, -67% combiné avec rerank. Leur approche utilise un LLM
(Claude Haiku) pour générer le préfixe ; ici on l'extrait gratuitement de la
hiérarchie déjà connue (matière > section) car le corpus est structuré.

**Pas de niveau dans le préfixe** : permet d'embedder une seule fois un chunk
cycle 4 puis de le dupliquer en payload pour 5è/4è/3è (économie 3×). Le niveau
reste filtrable côté Qdrant via le payload — il n'a pas besoin d'être dans le
texte embeddé.
"""

from __future__ import annotations

from .document import Chunk


def build_contextual_text(chunk: Chunk) -> str:
    """
    Texte embeddé = préfixe situant + texte brut.

    Format prose (et non markdown ou bullets) car les embedding models — y
    compris mistral-embed — sont entraînés sur prose. Position : préfixe AVANT
    le chunk pour que le sujet conditionne la représentation vectorielle.
    """
    return (
        f"Cet extrait provient du programme officiel Éduscol de "
        f"{chunk.matiere_label}, section « {chunk.section} ».\n\n"
        f"{chunk.text}"
    )
