# CLAUDE.md - TomAI Curriculum

Dataset éducatif français pour le tutorat IA, basé sur les programmes officiels Éduscol. Documents JSONL optimisés pour RAG avec Qdrant et Mistral embeddings.

## Commandes

```bash
# Validation
uv run python scripts/cli.py validate              # Valider tous les JSONL
uv run python scripts/cli.py validate --niveau=cinquieme  # Valider un niveau

# Statistiques
uv run python scripts/cli.py stats

# Ingestion (dry-run)
uv run python scripts/ingest.py run --dry-run

# Ingestion réelle
QDRANT_URL=... QDRANT_API_KEY=... MISTRAL_API_KEY=... uv run python scripts/ingest.py run

# Status collection Qdrant
QDRANT_URL=... QDRANT_API_KEY=... uv run python scripts/ingest.py status

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
└── ingest.py           # Ingestion Qdrant + Mistral embeddings 1024D

data/processed/         # Fichiers JSONL par cycle/niveau/matière
└── college/cinquieme/
    ├── metadata.json
    ├── mathematiques.jsonl
    ├── francais.jsonl
    └── ...
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

## Contraintes RAG

| Paramètre | Valeur |
|-----------|--------|
| Taille chunk cible | 400-512 tokens |
| Validation contenu | 50-600 tokens par document |
| Estimation tokens | 1 token ≈ 4 caractères français |
| Modèle embeddings | Mistral `mistral-embed` (1024 dimensions) |
| Distance metric | Cosine |
| Collection Qdrant | `tomai_educational` |

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
