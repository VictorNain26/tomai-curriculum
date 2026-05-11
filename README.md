# TomAI Curriculum Dataset

Dataset éducatif français pour le tutorat IA, basé sur les **programmes officiels Éduscol**.

Pipeline RAG souverain EU : **Mistral embeddings 1024D** ingéré dans **Qdrant Cloud** (région EU). Évaluation via **RAGAS** natif Mistral (Phase B).

## Scope MVP (2026-05-11)

**5ème uniquement** : 288 documents Pydantic-valides, 11 matières du tronc commun collège (math, français, hist-géo, PC, SVT, EMC, anglais, allemand, espagnol, italien, technologie).

Les autres niveaux (6ème, 4ème, 3ème, lycée) sont **archivés** via tag git `archive/v1.0-pre-mvp` et branche `archive/pre-mvp-refonte`. Restaurés en Phase H après validation du MVP. Voir `docs/specs/2026-05-11-mvp-rebuild-plan.md`.

## Structure

```
data/
├── raw/
│   └── sources_officielles.md         # Liens Éduscol et structure programmes
└── processed/
    └── college/cinquieme/<matiere>.jsonl

docs/
├── adr/                # Décisions architecturales versionnées (0001-0005)
├── programmes/
│   ├── PROGRAMME_5EME.md
│   └── CALENDRIER_REFORMES.md
├── specs/              # Specs design (mai 2026 RAG overhaul + MVP rebuild)
└── audits/             # Rapports baseline (post Phase C)
```

## Format JSONL

Chaque ligne est un document JSON validé Pydantic (`schema/document.py`) :

```json
{
  "title": "Théorème de Pythagore - Énoncé",
  "niveau": "cinquieme",
  "matiere": "mathematiques",
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

## CLI

```bash
# Validation et stats
uv run python scripts/cli.py validate
uv run python scripts/cli.py stats

# Ingestion Qdrant (3 phases idempotentes)
uv run python scripts/ingest.py run

# Gap analysis vs PROGRAMME_5EME.md
uv run python scripts/audit_coverage.py
```

Détails dans `CLAUDE.md`.

## Souveraineté EU

Aucun SaaS/SDK runtime hors UE. Pipeline 100% Mistral + Qdrant Cloud EU + Scaleway. RGPD-compatible.

## Veille programmes Éduscol

Les programmes changent régulièrement (réforme cycle 3 en 2025-2028). Stratégie de veille à 4 couches documentée dans `docs/adr/0005-eduscol-veille-strategy.md` et calendrier anticipé dans `docs/programmes/CALENDRIER_REFORMES.md`.

## Récupération état pre-MVP

L'état détaillé avant la refonte (1854 docs / 7 niveaux) reste accessible :

```bash
# Browse l'état archivé
git checkout archive/pre-mvp-refonte

# Cherry-pick d'un fichier précis sans switch
git checkout archive/pre-mvp-refonte -- data/processed/college/sixieme/
```

## Sources Officielles

- **Éduscol** : https://eduscol.education.gouv.fr/
- **Bulletin Officiel** : https://www.education.gouv.fr/le-bulletin-officiel-de-l-education-nationale-de-la-jeunesse-et-des-sports
- **Légifrance API** (arrêtés MENE*) : https://api.gouv.fr/les-api/legifrance-api
- BO en vigueur pour la 5ème : BO 30/07/2020 (commun), BO 13/06/2024 (EMC), BO 29/02/2024 (Technologie)

## License

MIT — contenu pédagogique adapté des programmes officiels de l'Éducation Nationale française.
