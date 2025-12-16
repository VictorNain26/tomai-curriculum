# TomAI Curriculum Dataset

Dataset éducatif français pour le tutorat IA, basé sur les **programmes officiels Éduscol**.

## Structure

```
data/
├── raw/                          # Sources brutes et références
│   └── sources_officielles.md    # Liens Éduscol et structure programmes
└── processed/                    # Données prêtes pour ingestion
    └── college/
        └── cinquieme/
            ├── metadata.json     # Métadonnées du niveau
            ├── mathematiques.jsonl
            ├── francais.jsonl
            ├── physique_chimie.jsonl
            ├── svt.jsonl
            └── anglais.jsonl
```

## Format JSONL

Chaque ligne est un document JSON autonome :

```json
{
  "title": "Théorème de Pythagore - Énoncé",
  "domaine": "Géométrie",
  "sousdomaine": "Triangles",
  "content_type": "theoreme",
  "difficulty": "standard",
  "content": "Dans un triangle rectangle...",
  "keywords": ["pythagore", "triangle rectangle"],
  "prerequis": ["Triangle rectangle"]
}
```

## Best Practices RAG 2025

Ce dataset suit les recommandations :

| Aspect | Implémentation | Source |
|--------|----------------|--------|
| **Chunking** | 400-512 tokens/doc | [NVIDIA](https://developer.nvidia.com/blog/finding-the-best-chunking-strategy/) |
| **Metadata** | Hiérarchique, pas excessive | [DataScienceCentral](https://www.datasciencecentral.com/best-practices-for-structuring-large-datasets-in-rag/) |
| **Format** | JSONL streamable | [HuggingFace](https://huggingface.co/blog/tegridydev/llm-dataset-formats-101-hugging-face) |

## CLI

```bash
# Validation
uv run python scripts/cli.py validate

# Statistiques
uv run python scripts/cli.py stats

# Ingestion Qdrant (dry-run)
uv run python scripts/ingest.py run --dry-run

# Ingestion réelle
QDRANT_URL=... QDRANT_API_KEY=... MISTRAL_API_KEY=... \
  uv run python scripts/ingest.py run
```

## Schema Pydantic

```python
from schema import Document, ContentType, Difficulty

# Types de contenu
ContentType.DEFINITION    # Définition officielle
ContentType.THEOREME      # Théorème mathématique
ContentType.FORMULE       # Formule à retenir
ContentType.METHODE       # Méthode pas à pas
ContentType.EXEMPLE       # Exemple illustratif
ContentType.ERREUR_COURANTE  # Piège à éviter

# Niveaux de difficulté
Difficulty.DECOUVERTE        # Introduction
Difficulty.STANDARD          # Niveau programme
Difficulty.APPROFONDISSEMENT # Pour aller plus loin
```

## Sources Officielles

- **Éduscol** : https://eduscol.education.fr/
- **Bulletin Officiel** : 30 juillet 2020 (programmes en vigueur 2024-2025)
- **Cycle 4** : 5ème, 4ème, 3ème

## Stats Actuelles

| Niveau | Documents | Tokens | Matières |
|--------|-----------|--------|----------|
| 5ème   | 114       | ~12k   | Maths, Français, PC, SVT, Anglais |

## License

MIT - Contenu pédagogique adapté des programmes officiels de l'Éducation Nationale française.
