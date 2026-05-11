# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Dataset éducatif français pour le tutorat IA, basé sur les **programmes officiels Éduscol**. Pipeline RAG souverain EU : Mistral embeddings 1024D + Qdrant Cloud (région EU).

**Scope MVP actif (2026-05-11)** : **5ème uniquement** (288 docs Pydantic-valides, 11 matières tronc commun collège). Les autres niveaux (6ème, 4ème, 3ème, lycée) sont archivés via tag git `archive/v1.0-pre-mvp` + branche `archive/pre-mvp-refonte`, restaurables en Phase H une fois le MVP validé.

Voir `docs/specs/2026-05-11-mvp-rebuild-plan.md` pour le plan complet.

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

# === Optimisation Qdrant ===
uv run python scripts/qdrant_optimize.py optimize  # Indexes + quantization HNSW
uv run python scripts/qdrant_optimize.py status

# === Audit couverture vs Éduscol ===
uv run python scripts/audit_coverage.py            # Gap analysis vs PROGRAMME_5EME.md

# === Évaluation RAG (Phase B, RAGAS-based) ===
# À venir : scripts/evaluate.py refait sur RAGAS + Mistral natif

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
├── cli.py              # CLI: validate, stats
├── ingest.py           # Pipeline 3 phases : embed → upsert → prune (CLI Typer)
├── ingest_lib.py       # Helpers ingest (hash, cache, payload, Qdrant ops)
├── audit_coverage.py   # Gap analysis dataset vs programmes Éduscol
├── qdrant_optimize.py  # Optimisation : indexes KEYWORD + scalar int8 + HNSW
└── utils.py            # Helpers communs (load JSONL, validate, etc.)

data/
├── raw/                            # Sources brutes Éduscol (sources_officielles.md)
├── processed/college/cinquieme/    # Scope MVP : 288 docs, 11 matières
└── golden/                         # (Phase D) golden set généré via RAGAS TestsetGenerator

docs/
├── adr/                # Décisions architecturales versionnées
│   ├── 0001-rag-overhaul.md           # Historique chantier mai 2026
│   ├── 0002-archive-pre-mvp.md        # Refonte radicale : archivage
│   ├── 0003-mvp-cinquieme-first.md    # Pourquoi MVP 5ème
│   ├── 0004-ragas-adoption.md         # Pourquoi RAGAS vs custom
│   └── 0005-eduscol-veille-strategy.md # Stratégie veille programmes
├── audits/             # Rapports baseline + suivi (re-créés post Phase C)
├── programmes/
│   ├── PROGRAMME_5EME.md       # Référentiel chapitres 5ème (BO 30/07/2020 + MAJ)
│   └── CALENDRIER_REFORMES.md  # Réformes officielles à anticiper
└── specs/
    ├── 2026-05-09-rag-overhaul-design.md  # Spec chantier précédent
    └── 2026-05-11-mvp-rebuild-plan.md     # Plan refonte MVP (ce chantier)

tests/
├── test_audit_coverage.py    # Parser markdown, normalize, fuzzy match
├── test_ingest_pipeline.py   # Hash, UUID, cache, prune
└── test_schema.py            # Validation Document, cycle_from_niveau
```

## Stats dataset (2026-05-11, post refonte MVP)

| Niveau | Documents | Matières | Statut |
|--------|-----------|----------|--------|
| 5ème | 288 | 11 | **MVP actif** |
| Autres | — | — | Archivés via `archive/v1.0-pre-mvp` |

Pre-refonte stats régénérables via `git checkout archive/pre-mvp-refonte` puis `uv run python scripts/cli.py stats`.

## Schéma Document

Chaque document JSONL suit le modèle Pydantic `Document` (`schema/document.py`). Champs principaux :

| Champ | Type | Description |
|-------|------|-------------|
| id | str? | UUID stable = `uuid5(NAMESPACE_URL, sha256(niveau+matiere+title+content))` |
| niveau | Niveau? | Enum NiveauCollege/NiveauLycee (validé) |
| matiere | Matiere? | Enum (mathematiques, francais, ...) |
| title | str | 10-200 caractères |
| domaine | str | Domaine du programme |
| content_type | ContentType | definition, theoreme, formule, methode, exemple, erreur_courante |
| difficulty | Difficulty | decouverte, standard, approfondissement |
| content | str | 200-2400 caractères (~50-600 tokens) |
| keywords | list[str]? | Mots-clés (15 max) |
| prerequis | list[str]? | Prérequis pédagogiques (10 max) |
| typical_questions | list[str]? | Questions types (10 max) |
| learning_objectives | list[str]? | Objectifs (5 max) |
| common_errors | list[str]? | Erreurs courantes (5 max) |
| review_status | ReviewStatus | draft, reviewed, validated, published |

## Configuration RAG (mai 2026)

| Paramètre | Valeur | Justification |
|-----------|--------|---------------|
| Chunking cible | 300-400 tokens (1200-1600 chars) | Optimal retrieval |
| Embeddings | Mistral `mistral-embed` 1024D | Souveraineté EU |
| Batch embeddings | 50 | Mistral cookbook |
| Distance | Cosine | Standard sémantique |
| Quantization | Scalar int8 always_ram | -75% RAM, ≥99% accuracy |
| HNSW | m=16, ef_construct=100 | Optimisé 1024D |
| Indexes KEYWORD | niveau, matiere, cycle, difficulty, content_type | 2-5x queries filtrées |
| Eval framework (Phase B) | **RAGAS** natif Mistral | Pas de code custom à maintenir |

## Règles d'or

### Souveraineté EU stricte

Aucun SaaS/SDK runtime hors EU. Mistral (chat, embed, judge), Qdrant Cloud (EU), Scaleway (storage). **Pas de Cohere, OpenAI, Anthropic**.

### Sans inventions

Réutiliser les standards éprouvés. Pour eval : RAGAS (pas re-implémenter Faithfulness/Response Relevancy). Pour testset : RAGAS TestsetGenerator (pas curation manuelle artisanale). Pour parser markdown : libs standards.

### Idempotence

ID document = `uuid5(NAMESPACE_URL, content_hash)` stable. Ingest = embed (cache) → upsert (set_payload si hash inchangé) → prune (orphans). Renommer un titre = nouvel ID + ancien pruned automatiquement.

### Qualité des données

Validation Pydantic stricte. Cross-check path ↔ champs JSONL à l'ingestion (`load_documents` fail loud sur divergence niveau/matiere). 200-2400 chars/doc, cible 1200-1600.

### Veille programmes Éduscol

Voir ADR-0005 et `docs/programmes/CALENDRIER_REFORMES.md`. Stratégie 4 couches : RSS BO (GH Action Phase G), API Légifrance semestriel, header `source_bo` dans MD, calendrier anticipation.

## Référence pre-MVP

État détaillé pre-refonte accessible via git :

```bash
git checkout archive/pre-mvp-refonte
# ou cherry-pick d'un fichier précis :
git checkout archive/pre-mvp-refonte -- data/processed/college/sixieme/
```

Voir ADR-0002 pour la procédure complète.
