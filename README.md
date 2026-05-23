# TomAI Curriculum — Index RAG souverain EU

Pipeline d'indexation des **programmes officiels Éduscol** (collège 6e → 3e)
pour le RAG du tuteur TomAI.

**Scope** : ce repo gère **UNIQUEMENT l'index** (PDF → markdown → chunks →
Qdrant). La couche LLM (chat socratique, prompting, hallucination eval) est
la responsabilité du backend `tomai-monorepo/apps/server`. Source de vérité
architecture : [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

**Souveraineté EU stricte** : Mistral (embeddings) + Qdrant Cloud (fr-par).
Aucun SaaS hors UE.

## État

| Indicateur | Valeur |
|---|---|
| Collection Qdrant | `tomai_educational` (5238 points uniques) |
| Niveaux couverts | 6e, 5e, 4e, 3e (collège complet) |
| Matières | 16 (tronc commun + LV + arts + EPS + sciences-techno) |
| Coverage sections BO | **100 %** sur toutes les matières (audit 2026-05-18, sans faux positif) |
| Retrieval baseline | `chunk_id_recall@5 = **0.894**` / MRR=**0.739** sur 189 questions document-grounded — BGE-M3 dense + sparse natif via FlagEmbedding |
| Tests | 82 pass · ruff clean |

### Baseline par matière (top-5, golden 189 questions, BGE-M3 + sparse natif)

| Matière | n | cid_recall@5 | MRR |
|---|---|---|---|
| eps, histoire_geo, mathematiques, education_musicale, physique_chimie, svt | 71 | **1.000** | 0.83-1.00 |
| allemand | 15 | 0.933 | 0.811 |
| arts_plastiques | 13 | 0.923 | 0.923 |
| langues_vivantes | 10 | 0.900 | 0.883 |
| emc | 11 | 0.909 | 1.000 |
| francais | 16 | 0.875 | 0.771 |
| histoire_des_arts | 13 | 0.846 | 0.833 |
| anglais | 12 | 0.750 | 0.794 |
| sciences_technologie | 4 | 0.750 | 1.000 |
| espagnol | 7 | 0.714 | 0.857 |
| technologie | 9 | 0.667 | 0.781 |
| italien | 8 | 0.625 | 0.875 |

**Findings** :
- Switch d'embedder réalisé suite au bench du 2026-05-23 : BGE-M3 (BAAI,
  MIT, self-host Scaleway) remplace mistral-embed. Justification chiffrée
  dans `docs/ARCHITECTURE.md §Décision benchmark embedder`.
- Gains majeurs : **allemand** 0.60→0.93 (+0.33), **espagnol** 0.43→0.71
  (+0.28), **arts_plastiques** 0.69→0.92 (+0.23). MRR global +0.16.
- Italien (n=8) et technologie restent les 2 matières à investiguer
  (golden ciblé requis pour départager bruit vs vraie régression).

> **Note backend** : le switch BGE-M3 + sparse natif (learned sparse via
> FlagEmbedding) obsolète le tokenizer BM25 maison FNV-1a précédemment
> reproductible en TS pur. Le backend doit exécuter BGE-M3 pour ses
> queries via un service Python ou un endpoint dédié. Cf. ARCHITECTURE.md
> §Recommandations backend pour les options détaillées.

## Architecture

```
schema/
├── document.py        Pydantic Chunk + dérivation niveaux + MATIERE_LABELS
├── bm25.py            Tokenizer FR + FNV-1a (parité stricte avec backend)
├── contextual.py      Préfixe contextuel hiérarchique (gratuit, sans LLM)
└── retrieval.py       Accès Mistral/Qdrant partagé (embed, hybrid_search, L2 normalize)

scripts/
├── extract_pdfs.py        PDF → markdown via pymupdf4llm (vrais H2)
├── ingest.py              .md → chunks → embeddings L2 → sparse BM25 → upsert
├── migrate_collection.py  Création collection (named vectors + indexes)
├── query.py               Test interactif retrieval (chunks bruts, pas de LLM)
├── evaluate.py            Métriques retrieval déterministes (chunk_id recall, MRR)
├── generate_golden.py     Génère le golden set document-grounded
├── audit_coverage.py      % titres BO indexés + `--list-missing` debug
├── dump_bm25_fixture.py   Exporte fixture parité BM25 pour le backend TS
└── veille_programmes.py   Détecte changements BO (data.gouv + Légifrance)

data/
├── raw/                   PDFs + markdowns sources + manifest data.gouv
└── golden/                Questions de test + résultats eval (versionnés)

docs/ARCHITECTURE.md       Source de vérité unique sur l'architecture
docs/audits/               Rapports coverage horodatés
```

## Quickstart

```bash
# 1. Setup
cp .env.example .env       # MISTRAL_API_KEY, QDRANT_URL, QDRANT_API_KEY
uv sync --all-extras

# 2. Extraire les PDFs en markdown (idempotent)
uv run python scripts/extract_pdfs.py

# 3. Créer la collection Qdrant cible
uv run python scripts/migrate_collection.py

# 4. Ingérer (chunking + embeddings + upsert)
uv run python scripts/ingest.py

# 5. Tester le retrieval
uv run python scripts/query.py "Théorème de Pythagore" --matiere=mathematiques --niveau=quatrieme

# 6. Générer le golden set document-grounded (one-shot offline)
uv run python scripts/generate_golden.py --target=300

# 7. Vérifier la qualité
uv run python scripts/audit_coverage.py              # coverage par matière
uv run python scripts/audit_coverage.py --list-missing  # titres BO non couverts
uv run python scripts/evaluate.py --by-matiere       # chunk_id recall + MRR

# 8. Veille BO
uv run python scripts/veille_programmes.py
```

## Qualité & CI

```bash
uv run ruff check schema/ scripts/ tests/
uv run ruff format schema/ scripts/ tests/
RUN_MISTRAL_TOKENIZER_TESTS=1 uv run pytest tests/
```

GitHub Actions :
- `ci.yml` — lint + tests à chaque PR / push main
- `veille_bo.yml` — veille Eduscol hebdomadaire (issue GitHub si changement)

## Sources officielles

- **Éduscol** : <https://eduscol.education.gouv.fr/>
- **Bulletin Officiel** : <https://www.education.gouv.fr/pid285/bulletin_officiel.html>
- **Manifest data.gouv** : `data/raw/programmes_second_degre_datagouv.json`
- **Légifrance PISTE** : <https://piste.gouv.fr> (option, pour veille temps réel)

Inventaire détaillé des fichiers et URLs : `data/raw/sources_officielles.md`.

## License

MIT — contenu pédagogique extrait des programmes officiels (domaine public,
Open Etalab pour les annexes Eduscol).
