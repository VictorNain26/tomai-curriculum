# ADR-0006 — Pipeline RAG v2 : .txt officiels → Qdrant (sans JSONL intermédiaire)

- **Date** : 2026-05-18
- **Statut** : accepté, implémenté
- **Supersède** : ADR-0001, ADR-0003

## Contexte

La v1 du pipeline utilisait des documents JSONL générés par Claude (288 docs) comme couche intermédiaire entre les programmes officiels et Qdrant. Ces JSONL étaient :
- Non vérifiés contre les sources officielles (générés circulairement)
- Couplés à un schema Document complexe (20+ champs, ReviewStatus, QualityMetrics)
- Ingérés via un pipeline multi-script (cli.py, ingest_lib.py, qdrant_optimize.py, utils.py)

## Decision

Supprimer les JSONL et chunker directement les fichiers `.txt` officiels (pdftotext des programmes Eduscol) vers Qdrant. Source de vérité unique : `data/raw/*.txt`.

## Architecture

```
data/raw/*.txt (programmes officiels)
  └── scripts/ingest.py
        ├── extract_section()   # extrait la section matière via regex
        ├── chunk_text()        # SentenceChunker 1600 chars ≈ 400 tokens
        ├── validate_chunks()   # validation Pydantic (Chunk)
        ├── embed_chunks()      # mistral-embed, batch 50, 1024D
        └── upsert_to_qdrant()  # uuid5(sha256(text)) — idempotent
```

## Schema Chunk (schema/document.py)

```python
class Chunk(BaseModel):
    id: str          # UUID4
    text: str        # ≥ 50 chars
    source_file: str # ex: "programme_maths_cycle4_BO2026"
    matiere: Matiere # enum EU-controlled vocabulary
    niveau: NiveauCollege = NiveauCollege.CINQUIEME
    section: str     # ex: "Nombres et calculs"
    chunk_index: int
```

Payload Qdrant : `Chunk.to_qdrant_payload()` (exclut `id`, sérialise enums).

## Consequences

**Positif :**
- Zéro contenu généré par LLM dans le dataset → vérifiable contre les BOs officiels
- Pipeline en 5 fonctions testables indépendamment
- Idempotence garantie (même texte = même UUID)
- Schema minimal (7 champs vs 20+)

**Négatif :**
- Pas de metadata pédagogique enrichie (content_type, difficulty, typical_questions)
- Contenu brut des programmes, pas reformulé pour les élèves

**Neutre :**
- La couche LLM (query.py) compense via system prompt socratique
