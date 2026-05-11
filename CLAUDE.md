# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Dataset éducatif français pour le tutorat IA, basé sur les **programmes officiels Éduscol** (BO 30/07/2020, BO 13/06/2024 pour EMC, BO 29/02/2024 pour Technologie). Documents JSONL optimisés pour RAG avec Qdrant + Mistral embeddings 1024D + sparse BM25 IDF (hybrid).

Scope mai 2026 : **6ème → Terminale**. Le primaire (CP-CM2) est reporté.

## Setup

```bash
# Installation des dépendances (uv gère automatiquement l'environnement)
uv sync

# Configuration environnement (créer .env à la racine)
QDRANT_URL=https://your-cluster.qdrant.io
QDRANT_API_KEY=your-api-key
MISTRAL_API_KEY=your-mistral-key
QDRANT_COLLECTION=tomai_educational  # Optionnel, défaut: tomai_educational
```

## Commandes

```bash
# === Validation et statistiques ===
uv run python scripts/cli.py validate              # Valider tous les JSONL
uv run python scripts/cli.py validate --niveau=cinquieme
uv run python scripts/cli.py stats

# === Ingestion Qdrant (3 phases découplées, idempotentes) ===
uv run python scripts/ingest.py embed              # Phase 1 : embeddings → cache local
uv run python scripts/ingest.py upsert             # Phase 2 : cache → Qdrant
uv run python scripts/ingest.py prune              # Phase 3 : supprimer orphelins
uv run python scripts/ingest.py run                # Orchestrateur (embed+upsert+prune)
uv run python scripts/ingest.py status             # Status collection

# === Audit & optimisation Qdrant ===
uv run python scripts/qdrant_optimize.py optimize  # Indexes + quantization HNSW
uv run python scripts/qdrant_optimize.py status
uv run python scripts/audit_qdrant.py              # Audit complet collection
uv run python scripts/audit_coverage.py            # Gap analysis vs programmes officiels

# === Évaluation RAG (expected_ids exact + RAGAS déterministe) ===
uv run python scripts/evaluate.py run --verbose
uv run python scripts/evaluate.py run --output evaluation_results.json
uv run python scripts/evaluate.py compare run-a.json run-b.json

# === Golden set ===
uv run python scripts/generate_golden.py           # Auto-génère smoke test depuis typical_questions

# === Migration & enrichissement ===
uv run python scripts/migrate_collection.py        # Alias swap atomique (cutover)
uv run python scripts/enrich.py                    # Enrichir JSONL (questions, prérequis, etc.)

# === Linting et formatage ===
uv run ruff check .
uv run ruff format .
uv run pytest                                      # Tests unitaires
```

## Architecture

```
schema/                 # Modèles Pydantic (source unique de vérité)
├── document.py         # Document, enums (Cycle, Niveau, Matiere, ContentType, Difficulty)
├── _examples.py        # Exemples pour json_schema_extra
└── __init__.py

scripts/
├── cli.py                          # CLI: validate, stats
├── ingest.py                       # Pipeline 3 phases : embed → upsert → prune (CLI Typer)
├── ingest_lib.py                   # Helpers ingest (hash, cache, payload, Qdrant ops)
├── chunking.py                     # Merge + overlap + enrichment
├── enrich.py                       # Enrichissement metadata (remplace add_*_chapters.py legacy)
├── evaluate.py                     # Retrieval eval : expected_ids + Recall/Precision/MRR/NDCG
├── evaluate_judge.py               # LLM-judge eval : Faithfulness + Response Relevancy + cross-EU
├── generate_golden.py              # Auto-génération golden set depuis typical_questions
├── audit_qdrant.py                 # Audit collection : config, indexes, duplicates
├── audit_coverage.py               # Gap analysis dataset vs programmes Éduscol
├── qdrant_optimize.py              # Optimisation : indexes KEYWORD + scalar int8 + HNSW
├── migrate_collection.py           # Alias swap atomique (sparse vectors + indexes)
├── migrate_add_niveau_matiere.py   # Migration one-shot : ajoute niveau/matiere aux JSONL
└── utils.py                        # Helpers communs (load JSONL, validate, etc.)

data/
├── raw/                # Sources brutes Éduscol (sources_officielles.md)
├── processed/          # JSONL validés (1854 docs au 2026-05-11)
│   ├── college/{sixieme,cinquieme,quatrieme,troisieme}/
│   └── lycee/{seconde,premiere,terminale}/
└── golden/
    └── test_queries.json  # Golden set curé (31 queries de référence)

docs/
├── adr/                # Décisions architecturales versionnées
├── audits/             # Rapports d'audit (RAPPORT_*.md)
├── programmes/         # PROGRAMME_*.md (référentiel chapitres par niveau)
└── specs/              # Specs de design (2026-05-09-rag-overhaul-design.md)

tests/
├── test_evaluate_metrics.py    # Métriques retrieval déterministes
├── test_evaluate_judge.py      # Faithfulness, Response Relevancy, cross-validation (mocks)
├── test_ingest_pipeline.py     # Hash, UUID, sparse, cache, prune
├── test_chunking.py            # Estimate tokens, group by theme, merge
├── test_audit_coverage.py      # Normalize, fuzzy match, parse programmes Éduscol
└── test_schema.py              # Validation Document, cycle_from_niveau, niveau/matiere
```

## Stats dataset (2026-05-11)

| Niveau | Documents | Matières |
|--------|-----------|----------|
| 6ème | 150 | 6 |
| 5ème | 288 | 11 |
| 4ème | 255 | 11 |
| 3ème | 200 | 11 |
| 2nde | 302 | 12 |
| 1ère | 312 | 16 (avec spécialités) |
| Terminale | 347 | 18 (avec spécialités + options) |
| **Total** | **1854** | **22 matières uniques** |

Stats régénérables : `uv run python scripts/cli.py stats`.

## Schéma Document

Chaque document JSONL suit le modèle Pydantic `Document` :

| Champ | Type | Description |
|-------|------|-------------|
| id | str? | UUID stable = `uuid5(NAMESPACE_URL, sha256(niveau+matiere+title+content))` |
| title | str | 10-200 caractères, descripteur unique |
| domaine | str | Domaine du programme (ex: "Nombres et Calculs") |
| sousdomaine | str? | Sous-domaine optionnel |
| content_type | ContentType | definition, theoreme, formule, methode, exemple, erreur_courante |
| difficulty | Difficulty | decouverte, standard, approfondissement |
| content | str | **200-2400 caractères (~50-600 tokens)** |
| keywords | list[str]? | Jusqu'à 15 mots-clés |
| prerequis | list[str]? | Jusqu'à 10 prérequis (IDs documents) |
| typical_questions | list[str]? | Questions types (jusqu'à 10) — source pour golden auto-gen |
| learning_objectives | list[str]? | Objectifs pédagogiques (jusqu'à 5) |
| common_errors | list[str]? | Erreurs courantes (jusqu'à 5) |
| relations | list[DocumentRelation]? | Knowledge graph (prerequisite, related, extends...) |
| enriched | EnrichedContent? | LaTeX, diagrammes, code, interactifs |
| version | str | Semver (défaut: "2.0.0") |
| review_status | ReviewStatus | draft, reviewed, validated, published, deprecated |
| confidence_level | float | 0-1 (défaut: 0.8) |
| quality | QualityMetrics? | Calculé à l'ingestion via `compute_quality()` |
| tags | list[str]? | Tags libres (jusqu'à 10) |

**Note** : `niveau`, `matiere`, `cycle` sont actuellement dérivés du chemin du fichier au moment de l'ingestion (pas dans le JSONL). Voir spec RAG overhaul pour la migration prévue vers validation explicite.

## Configuration RAG (mai 2026)

| Paramètre | Valeur | Justification |
|-----------|--------|---------------|
| **Chunking** |
| Taille chunk cible | 300-400 tokens | Optimal retrieval (validé eval) |
| Overlap | 15% | Préserve contexte |
| Validation contenu | 200-600 tokens (Pydantic strict) | Atomique → standard |
| **Embeddings** |
| Modèle | Mistral `mistral-embed` | 1024 dimensions, EU sovereignty |
| Format | Conversationnel | +15-25% pertinence (cookbook Mistral) |
| Batch size API | 50 | D2 spec RAG overhaul |
| Distance metric | Cosine | Standard sémantique |
| **Qdrant** |
| Collection | `tomai_educational` (alias) → `tomai_educational_v2` (canonical) | Alias swap atomique |
| Dense vectors | 1024D, scalar int8 quantization always_ram | -75% RAM, ≥99% accuracy |
| Sparse vectors | BM25 IDF (`Modifier.IDF` natif Qdrant) | Hybrid search |
| HNSW config | m=16, ef_construct=100 | Optimisé 1024D |
| Payload indexes KEYWORD | niveau, matiere, cycle, difficulty, content_type | 2-5x queries filtrées |
| **Reranking** |
| Fusion | RRF (Reciprocal Rank Fusion) Query API côté Qdrant | BM25 + dense server-side |
| Pas de Cohere | Souveraineté EU (D15) | Cohere déprécié côté server |

## Évaluation

Pipeline d'évaluation à deux étages :

- **Retrieval déterministe** (`evaluate.py`, sans LLM) : Recall@K, Precision@K, MRR, NDCG@K, Context Precision/Recall — basés sur `expected_ids` exact (UUID), pas de fuzzy title matching.
- **LLM-judge** (`evaluate_judge.py`, Mistral seul, souveraineté EU) : Faithfulness (claims supportés / claims totaux) + Response Relevancy (cosine entre question originale et N questions re-générées). Cross-validation avec second modèle EU (`magistral-medium-latest`) via `cross-validate` qui flag les samples à désaccord > 0.3.
- **Golden set** : `data/golden/test_queries.json` (31 queries curées) + auto-générées depuis `typical_questions` (4615 queries smoke test, régénérable via `generate_golden.py`, gitignored).
- **Cache eval** : `data/embeddings_cache/` (versionné par `model_version`).
- **Historique runs** : `eval_runs/*.json` horodatés.

## Variables d'environnement

```bash
QDRANT_URL=        # URL Qdrant Cloud (région EU obligatoire)
QDRANT_API_KEY=    # Clé API Qdrant
MISTRAL_API_KEY=   # Clé API Mistral (embeddings + judge)
QDRANT_COLLECTION= # Nom collection (défaut: tomai_educational)
```

Voir `.env.example` pour le template complet.

## Règles d'or

### Souveraineté EU stricte

Aucun SaaS/SDK runtime hors EU. Mistral (chat, embed, judge), Qdrant Cloud (EU), Scaleway (storage). **Pas de Cohere, OpenAI, Anthropic dans le runtime**.

### Pas de sur-engineering

- Format JSONL simple, un document par ligne
- Validation Pydantic stricte
- Pas de transformations complexes implicites
- Pas de feature flag ou shim de rétrocompat : migration via alias = rollback gratuit

### Idempotence

- ID document = `uuid5(NAMESPACE_URL, content_hash)` (stable sur re-run)
- Ingest = embed (cache) → upsert (set_payload si hash inchangé) → prune (orphelins)
- Renommer un titre = nouvel ID + ancien pruned automatiquement

### Qualité des données

- Chaque document doit être autonome et compréhensible
- Respecter 200-2400 chars (~50-600 tokens), cible 1200-1600 chars (~300-400 tokens)
- Keywords pertinents pour le retrieval
- `typical_questions` réalistes (utilisées pour le golden set auto)

## Références

- Spec design RAG overhaul : `docs/specs/2026-05-09-rag-overhaul-design.md`
- ADR référence : `docs/adr/0001-rag-overhaul.md`
- Audits historiques : `docs/audits/`
- Programmes officiels : `docs/programmes/PROGRAMME_*.md`
