# TomAI Curriculum Dataset

Dataset éducatif français pour le tutorat IA, basé sur les **programmes officiels Éduscol**.

Pipeline RAG souverain EU : **Mistral embeddings 1024D + sparse BM25 IDF (hybrid)** ingéré dans **Qdrant Cloud** (région EU).

## Scope

| Cycle | Niveaux | Matières |
|-------|---------|----------|
| Cycle 3 | 6ème | 6 |
| Cycle 4 | 5ème, 4ème, 3ème | 11 par niveau |
| Lycée | 2nde, 1ère, Terminale | 12 / 16 / 18 (avec spécialités) |

**Total : 1854 documents, 22 matières uniques** (6ème → Terminale). Le primaire est reporté.

## Structure

```
data/
├── raw/
│   └── sources_officielles.md         # Liens Éduscol et structure programmes
├── processed/
│   ├── college/{sixieme,cinquieme,quatrieme,troisieme}/<matiere>.jsonl
│   └── lycee/{seconde,premiere,terminale}/<matiere>.jsonl
└── golden/
    └── test_queries.json               # 31 queries curées pour évaluation
```

## Format JSONL

Chaque ligne est un document JSON validé Pydantic :

```json
{
  "title": "Théorème de Pythagore - Énoncé",
  "domaine": "Géométrie",
  "sousdomaine": "Triangles",
  "content_type": "theoreme",
  "difficulty": "standard",
  "content": "Dans un triangle rectangle...",
  "keywords": ["pythagore", "triangle rectangle"],
  "typical_questions": ["Comment calculer l'hypoténuse ?"],
  "prerequis": ["Triangle rectangle"]
}
```

Validation : `200-2400 chars` (cible 1200-1600 chars ≈ 300-400 tokens). Voir `schema/document.py` pour le modèle complet (knowledge graph, qualité, versioning).

## Pipeline RAG (mai 2026)

| Étape | Outil | Note |
|-------|-------|------|
| Chunking | Pydantic strict + `chunking.py` | Cible 300-400 tokens, overlap 15% |
| Embeddings | Mistral `mistral-embed` 1024D | Batch 50, cache local versionné par modèle |
| Storage | Qdrant Cloud (EU) | Scalar int8 + sparse BM25 IDF, indexes KEYWORD |
| Retrieval | Hybrid search RRF (Query API) | Dense + sparse, fusion server-side |
| Eval | `expected_ids` exact + RAGAS | Recall, Precision, MRR, NDCG, Context P/R |

## CLI

```bash
# Validation et stats
uv run python scripts/cli.py validate
uv run python scripts/cli.py stats

# Ingestion (3 phases idempotentes)
uv run python scripts/ingest.py embed              # 1. Embeddings → cache
uv run python scripts/ingest.py upsert             # 2. Cache → Qdrant
uv run python scripts/ingest.py prune              # 3. Supprimer orphelins
uv run python scripts/ingest.py run                # Orchestrateur

# Évaluation
uv run python scripts/evaluate.py run --verbose

# Gap analysis (couverture vs programmes officiels)
uv run python scripts/audit_coverage.py
```

Setup complet et architecture détaillée : voir `CLAUDE.md`.

## Souveraineté EU

Aucun SaaS/SDK runtime hors UE. Pipeline 100% Mistral + Qdrant Cloud EU + Scaleway. RGPD-compatible.

## Sources Officielles

- **Éduscol** : https://eduscol.education.fr/
- **Bulletin Officiel** : BO 30/07/2020 (programmes en vigueur), BO 13/06/2024 (EMC), BO 29/02/2024 (Technologie)
- Référentiel local : `docs/programmes/PROGRAMME_*.md`

## License

MIT — contenu pédagogique adapté des programmes officiels de l'Éducation Nationale française.
