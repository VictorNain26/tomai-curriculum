# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Dataset éducatif français pour le tutorat IA, basé sur les **programmes officiels Éduscol 2020** (Bulletin Officiel 30/07/2020). Documents JSONL optimisés pour RAG avec Qdrant et Mistral embeddings 1024D.

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
uv run python scripts/cli.py validate --niveau=cinquieme  # Valider un niveau
uv run python scripts/cli.py stats                 # Statistiques du dataset

# === Ingestion Qdrant ===
uv run python scripts/ingest.py run --dry-run      # Test ingestion (n'envoie rien)
uv run python scripts/ingest.py run                # Ingestion réelle (avec .env)
uv run python scripts/ingest.py status             # Status collection Qdrant

# === Optimisation Qdrant ===
uv run python scripts/qdrant_optimize.py optimize  # Appliquer indexes + quantization
uv run python scripts/qdrant_optimize.py status    # Voir config HNSW + indexes

# === Évaluation RAG (expert - 2025 best practices) ===
uv run python scripts/evaluate.py --verbose                    # Évaluation avec détails
uv run python scripts/evaluate.py --output evaluation_results.json  # Export JSON

# === Recherche et testing ===
uv run python scripts/search.py                    # Test recherche interactive
uv run python scripts/rerank.py                    # Test BM25 reranking

# === Linting et formatage ===
uv run ruff check .
uv run ruff format .
```

## Architecture

```
schema/                 # Modèles Pydantic (validation stricte)
├── document.py         # Document, ContentType, Difficulty, QualityMetrics, Relations
└── __init__.py

scripts/
├── cli.py              # CLI: validate, stats
├── ingest.py           # Ingestion Qdrant + Mistral embeddings 1024D
├── qdrant_optimize.py  # Optimisation Qdrant: indexes + quantization + HNSW
├── chunking.py         # Chunking optimal: merge + overlap + enrichment
├── evaluate.py         # Évaluation RAG expert: Recall@K, Precision@K, MRR, NDCG@K
├── audit_qdrant.py     # Audit collection Qdrant: config, indexes, duplicates
├── rerank.py           # Reranking hybride: BM25 + metadata boost
└── search.py           # CLI de recherche interactive (test)

data/
├── processed/          # JSONL optimisés RAG 2025 (50-600 tokens/doc)
│   └── college/cinquieme/
│       ├── mathematiques.jsonl    # 33 docs, ~7,890 tokens (~239 tok/doc)
│       ├── francais.jsonl          # 35 docs, ~10,962 tokens (~313 tok/doc)
│       ├── physique_chimie.jsonl   # 20 docs, ~6,506 tokens (~325 tok/doc)
│       ├── svt.jsonl               # 17 docs, ~5,942 tokens (~350 tok/doc)
│       ├── histoire_geo.jsonl      # 27 docs, ~7,851 tokens (~291 tok/doc)
│       ├── anglais.jsonl           # 18 docs, ~2,077 tokens (~115 tok/doc, atomique)
│       ├── allemand.jsonl          # 20 docs, ~5,140 tokens (~257 tok/doc)
│       ├── espagnol.jsonl          # 20 docs, ~5,222 tokens (~261 tok/doc)
│       └── italien.jsonl           # 22 docs, ~2,919 tokens (~133 tok/doc, atomique)
├── raw/                # Sources brutes et références Éduscol
└── test_queries.json   # Test queries pour évaluation RAG

**Total: 212 documents, ~54,509 tokens (~257 tokens/doc)**
```

## Schéma Document (Version 2.0 - RAG 2025)

Chaque document JSONL suit le modèle Pydantic `Document` :

| Champ | Type | Description |
|-------|------|-------------|
| title | str | 10-200 caractères, descripteur unique |
| domaine | str | Domaine du programme (ex: "Nombres et Calculs") |
| sousdomaine | str? | Sous-domaine optionnel |
| content_type | ContentType | definition, theoreme, formule, methode, exemple, erreur_courante |
| difficulty | Difficulty | decouverte, standard, approfondissement |
| content | str | **200-2400 caractères (~50-600 tokens)** |
| keywords | list[str]? | Jusqu'à 15 mots-clés |
| prerequis | list[str]? | Jusqu'à 10 prérequis (IDs de documents) |
| typical_questions | list[str]? | Questions types (jusqu'à 10) |
| learning_objectives | list[str]? | Objectifs pédagogiques (jusqu'à 5) |
| common_errors | list[str]? | Erreurs courantes (jusqu'à 5) |
| version | str | Version sémantique (défaut: "2.0.0") |
| review_status | ReviewStatus | draft, reviewed, validated, published |
| confidence_level | float | Niveau de confiance (0-1, défaut: 0.8) |
| tags | list[str]? | Tags libres (jusqu'à 10) |

**Distribution de taille** :
- Atomique : 200-600 chars (~50-150 tokens) pour vocabulaire/définitions courtes
- Standard : 800-1600 chars (~200-400 tokens) pour concepts/méthodes
- Cible optimale RAG 2025 : 1200-1600 chars (~300-400 tokens)

## Configuration RAG - Best Practices 2025

| Paramètre | Valeur | Optimisation |
|-----------|--------|--------------|
| **Chunking** |
| Taille chunk cible | 300-400 tokens | Optimal pour retrieval |
| Overlap | 15% | Préserve contexte |
| Validation contenu | 200-600 tokens | Pydantic strict |
| **Embeddings** |
| Modèle | Mistral `mistral-embed` | 1024 dimensions |
| Format | Conversationnel | +15-25% pertinence |
| Distance metric | Cosine | Standard pour sémantique |
| **Qdrant** |
| Collection | `tomai_educational` | Nom par défaut |
| HNSW config | m=16, ef_construct=100 | Optimisé 1024D |
| Quantization | int8 scalar | -75% RAM, 99%+ accuracy |
| Payload indexes | niveau, matiere, difficulty, quality_score | 2-5x queries filtrées |
| **Reranking** |
| Algorithme | BM25 hybride | +25-35% précision |
| Pipeline | top-20 → BM25 → top-5 | Lightweight, 0 ML deps |

## Variables d'environnement

```bash
QDRANT_URL=        # URL Qdrant Cloud
QDRANT_API_KEY=    # Clé API Qdrant
MISTRAL_API_KEY=   # Clé API Mistral (embeddings)
QDRANT_COLLECTION= # Nom collection (défaut: tomai_educational)
```

## Règles

### Pas de sur-engineering

- Format JSONL simple, un document par ligne
- Validation Pydantic stricte
- Pas de transformations complexes

### Qualité des données

- Chaque document doit être autonome et compréhensible
- Respecter les limites de tokens (400-512)
- Keywords pertinents pour le retrieval
