# CLAUDE.md - TomAI Curriculum

Dataset éducatif français pour le tutorat IA, basé sur les programmes officiels Éduscol. Documents JSONL optimisés pour RAG avec Qdrant et Mistral embeddings.

## Commandes

```bash
# Validation
uv run python scripts/cli.py validate              # Valider tous les JSONL
uv run python scripts/cli.py validate --niveau=cinquieme  # Valider un niveau

# Statistiques
uv run python scripts/cli.py stats

# Chunking optimal (V2)
uv run python scripts/chunking.py --niveau=cinquieme --matiere=mathematiques --dry-run
uv run python scripts/chunking.py  # Tous les niveaux/matières

# Ingestion (dry-run)
uv run python scripts/ingest.py run --dry-run

# Ingestion réelle (crée collection avec optimisations Qdrant)
QDRANT_URL=... QDRANT_API_KEY=... MISTRAL_API_KEY=... uv run python scripts/ingest.py run

# Status collection Qdrant
QDRANT_URL=... QDRANT_API_KEY=... uv run python scripts/ingest.py status

# Optimiser collection Qdrant existante
QDRANT_URL=... QDRANT_API_KEY=... uv run python scripts/qdrant_optimize.py optimize
QDRANT_URL=... QDRANT_API_KEY=... uv run python scripts/qdrant_optimize.py status

# Évaluation RAG
uv run python scripts/evaluate.py --test-queries data/test_queries.json
uv run python scripts/evaluate.py --test-queries data/test_queries.json --output metrics.json

# Test reranking
python scripts/rerank.py  # Test BM25 reranking

# Linting
uv run ruff check .
uv run ruff format .
```

## Architecture

```
schema/                 # Modèles Pydantic
├── document.py         # Document, ContentType, Difficulty, Cycle, Niveau
└── __init__.py

scripts/
├── cli.py              # CLI: validate, stats
├── ingest.py           # Ingestion Qdrant + Mistral embeddings 1024D (optimisé)
├── qdrant_optimize.py  # Optimisation Qdrant: indexes + quantization + HNSW
├── chunking.py         # Chunking optimal V2: merge + overlap + enrichment
├── evaluate.py         # Évaluation RAG: Recall@K, MRR, NDCG@K
└── rerank.py           # Reranking hybride: BM25 + metadata boost

data/processed/         # Fichiers JSONL V1 par cycle/niveau/matière
└── college/cinquieme/
    ├── metadata.json
    ├── mathematiques.jsonl
    ├── francais.jsonl
    └── ...

data/processed_v2/      # Fichiers JSONL V2 (merged + enriched)
data/test_queries.json  # Test queries pour évaluation RAG
```

## Schéma Document

Chaque document JSONL suit le modèle Pydantic `Document` :

| Champ | Type | Description |
|-------|------|-------------|
| title | str | 10-150 caractères, descripteur unique |
| domaine | str | Domaine du programme (ex: "Nombres et Calculs") |
| sousdomaine | str? | Sous-domaine optionnel |
| content_type | ContentType | definition, theoreme, formule, methode, exemple, erreur_courante |
| difficulty | Difficulty | decouverte, standard, approfondissement |
| content | str | 100-2500 caractères (~25-600 tokens) |
| keywords | list[str]? | Jusqu'à 10 mots-clés |
| prerequis | list[str]? | Jusqu'à 5 prérequis |

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
