# CLAUDE.md — tomai-curriculum

Repo Python qui gère **uniquement l'index RAG** des programmes officiels Éduscol
(PDF → markdown → chunks → Qdrant). La couche LLM (chat, prompting,
hallucination eval) appartient EXCLUSIVEMENT au backend
`tomai-monorepo/apps/server`.

## Périmètre

Couvert ici :
- Extraction PDF → markdown (`scripts/extract_pdfs.py`)
- Chunking + embeddings + sparse vectors → Qdrant (`scripts/ingest.py`)
- Création/migration collection (`scripts/migrate_collection.py`)
- Audit coverage % titres BO + diagnostic missing (`scripts/audit_coverage.py`)
- Eval retrieval déterministe — Recall@k, MRR (`scripts/evaluate.py`)
- Veille BO automatique (`scripts/veille_programmes.py`)
- Test interactif retrieval (`scripts/query.py`)

**Pas dans ce repo** :
- Génération de réponses (chat LLM, prompt socratique, prompt cache)
- Choix de modèle large/medium/small
- RAGAS LLM-judge (Faithfulness, hallucination)
- Logique tutorat élève (mémoire, personnalisation)

## Règles générales

- **Souveraineté EU stricte** — Mistral (embeddings) + Qdrant Cloud (fr-par).
  Aucun SaaS hors UE. Pas d'OpenAI, Cohere, Anthropic, Google, Voyage.
- **Pas d'invention dans le dataset** — source de vérité = `data/raw/*.txt|md`
  (programmes officiels Éduscol). Aucun contenu généré par LLM dans
  l'index Qdrant. Le golden set `data/golden/questions.json` est l'unique
  artefact LLM-généré et c'est OFFLINE (script one-shot, pas runtime — voir
  `scripts/generate_golden.py`).
- **Idempotence** — `uuid5(NAMESPACE_URL, sha256(f"{matiere}:{niveau}:{text}"))`
  garantit qu'un re-ingest ne crée pas de doublons et que les textes
  partagés entre matières (préambules langues) ne se piétinent pas.
- **Validation stricte** — chaque chunk passe par `Chunk` Pydantic avant
  upsert. Erreur explicite si section regex échoue (pas de silence).
- **DRY** — accès Mistral/Qdrant centralisé dans `schema/retrieval.py`.
  Pas de duplication entre scripts.
- **Pas de scripts jetables** — si tu as besoin d'une fonction diagnostique,
  l'intégrer comme sous-commande du script permanent existant (ex:
  `audit_coverage.py --list-missing`).

## Commandes

```bash
# Setup
cp .env.example .env       # MISTRAL_API_KEY, QDRANT_URL, QDRANT_API_KEY
uv sync --all-extras

# Pipeline complet
uv run python scripts/extract_pdfs.py              # PDF → .md (pymupdf4llm)
uv run python scripts/migrate_collection.py        # crée v2 (named vectors + indexes)
uv run python scripts/ingest.py                    # chunk + embed + upsert
uv run python scripts/generate_golden.py --target=300  # golden set document-grounded
uv run python scripts/migrate_collection.py --swap-alias  # swap alias prod → v2

# Diagnostic
uv run python scripts/audit_coverage.py            # % titres BO indexés
uv run python scripts/audit_coverage.py --list-missing  # debug coverage <100%
uv run python scripts/evaluate.py --by-matiere     # retrieval Recall@k / MRR
uv run python scripts/query.py "Pythagore" --matiere=mathematiques --niveau=quatrieme

# Veille
uv run python scripts/veille_programmes.py         # check changements BO

# Qualité
uv run ruff check schema/ scripts/ tests/
uv run ruff format schema/ scripts/ tests/
RUN_MISTRAL_TOKENIZER_TESTS=1 uv run pytest tests/
```

## Architecture

```
schema/                    Bibliothèque partagée (importée par tous les scripts)
├── document.py            Pydantic Chunk + derive_niveaux_from_file + MATIERE_LABELS
├── bm25.py                Tokenizer FR + FNV-1a (parité stricte avec backend TS)
├── contextual.py          Préfixe contextuel hiérarchique (sans LLM)
└── retrieval.py           Accès Mistral/Qdrant : embed, hybrid_search, L2 normalize

scripts/                   CLI permanents (jamais de _tmp_*.py jetable)
├── extract_pdfs.py        PDF → markdown (pymupdf4llm — préserve les H2)
├── ingest.py              .md → chunk → embed → sparse BM25 → upsert Qdrant
├── migrate_collection.py  create v2 / status / swap-alias / drop-v1
├── query.py               Retrieval interactif (chunks bruts, pas de LLM)
├── evaluate.py            Recall@k, MRR (déterministe, sans LLM judge)
├── audit_coverage.py      % titres BO + --list-missing diagnostic
└── veille_programmes.py   data.gouv + Légifrance → détecte nouveaux BO

data/
├── raw/                   PDFs + .md (générés) + manifest data.gouv
├── golden/questions.json  Golden set pour evaluate.py
└── golden/retrieval_eval.json  Résultats eval (versionnés en CI)

docs/ARCHITECTURE.md       Source de vérité unique sur l'architecture
docs/audits/               Rapports coverage horodatés
```

## Pipeline ingest (détail)

```
data/raw/*.pdf
  └─ extract_pdfs.py        pymupdf4llm → .md (titres ## **...** fiables)
data/raw/*.md
  └─ load_source_text()     préfère .md sinon .txt
  └─ extract_section()      regex `^## \*\*Matière\*\*` pour fichiers multi-matières
  └─ chunk_text()           chonkie RecursiveChunker + tokenizer Mistral vrais tokens
  └─ expand_for_niveaux()   duplique 1 chunk × N niveaux du cycle
  └─ validate_chunks()      Pydantic Chunk → payload Qdrant
  └─ embed_batch()          mistral-embed batch 50 + normalisation L2 (déduplique textes)
  └─ upsert_to_qdrant()     named {dense, bm25} + uuid5(matiere+niveau+text) idempotent
```

Collection cible : `tomai_educational` (variable d'env `QDRANT_COLLECTION`).
- `dense` (1024D cosine, mistral-embed) + sparse `bm25` (Modifier.IDF natif)
- Scalar int8 quantization always_ram (4× compression, <1 % perte recall)
- Payload indexes KEYWORD : `niveau`, `matiere`, `cycle`, `source_file`

## Conventions de code

- **TypeScript-like strict** côté Python : type hints partout, pas de `Any` sauf
  bordure SDK externe (qdrant-client, mistralai)
- **400 lignes max** par fichier (cf `Tom/CLAUDE.md` racine)
- **Zéro warning ruff** en CI (line-length 100)
- **Tests systématiques** : unitaires + intégration (`@pytest.mark.integration`)
- **Idempotence** garantie sur tous les scripts d'ingestion / migration
- **`check_compatibility=True`** sur tous les `QdrantClient` (évite drift version
  client/server silencieux)

## Sources officielles

| Matière / niveau | Fichier source | BO |
|---|---|---|
| Cycle 3 (6e) — toutes matières | `programme_cycle3_BO2020.md` | 30/07/2020 |
| Cycle 4 BO 2020 — FR/HG/PC/SVT/EMC/Arts/Musique/EPS/HDA | `programme_cycle4_BO2020.md` | 30/07/2020 |
| Maths cycle 4 (à jour) | `programme_maths_cycle4_BO2026.md` | 05/03/2026 |
| Technologie cycle 4 (à jour) | `programme_technologie_cycle4_BO2024.md` | 29/02/2024 |
| Langues vivantes collège | `programme_{anglais,espagnol,allemand,italien}_college_BO2025.md` | 29/05/2025 |

URLs + procédure de régénération : `data/raw/sources_officielles.md`.

## Frontière avec le backend

Le backend (`tomai-monorepo/apps/server`) consomme l'index Qdrant produit ici
via une couche `qdrant.service.ts` + `rag.service.ts`. **Contrats critiques** :

- Le **payload** Qdrant doit rester stable : `text, section, matiere, niveau,
  cycle, source_file, chunk_index` (+ aliases `title`, `content` pour compat).
- Le **tokenizer BM25** (FNV-1a 32-bit + regex FR) doit rester strictement
  identique entre `schema/bm25.py` ici et `rag.service.ts:172-193` côté backend.
  Toute divergence casse l'IDF Qdrant silencieusement.
- Le nom de collection / alias se gère par variable d'env partagée
  (`QDRANT_COLLECTION`).
