# CLAUDE.md — tomai-curriculum

Pipeline RAG educatif : programmes officiels Eduscol 5eme → Qdrant EU.
Stack 100% EU-souverain : Mistral (embed + LLM) + Qdrant Cloud EU.

## Setup

```bash
cp .env.example .env   # remplir les 3 cles obligatoires
uv sync                # installe les dependances
uv sync --all-extras   # + dev (ruff, pytest) + eval (ragas)
```

Variables obligatoires dans `.env` :
- `MISTRAL_API_KEY` — api.mistral.ai
- `QDRANT_URL` — cluster Qdrant Cloud EU
- `QDRANT_API_KEY` — cle Qdrant

## Commandes

```bash
# Ingestion (chunk + embed + upsert Qdrant)
uv run python scripts/ingest.py --dry-run          # verifier chunks sans upserter
uv run python scripts/ingest.py                    # ingestion complete (11 matieres)
uv run python scripts/ingest.py --matiere=mathematiques
uv run python scripts/ingest.py --status           # etat collection Qdrant

# Requete socratique
uv run python scripts/query.py "Qu est-ce qu un angle droit ?"
uv run python scripts/query.py --matiere=mathematiques --top-k=5 "Pythagore"
uv run python scripts/query.py --no-llm "SVT respiration"   # chunks seuls

# Evaluation RAGAS (necessite uv sync --all-extras + dep eval)
uv run python scripts/evaluate.py
uv run python scripts/evaluate.py --questions=data/golden/questions.json

# Audit couverture vs referentiel officiel
uv run python scripts/audit_coverage.py
uv run python scripts/audit_coverage.py --output=docs/audits/rapport.md

# Veille programmes Eduscol (hebdomadaire via GitHub Action)
uv run python scripts/veille_programmes.py
uv run python scripts/veille_programmes.py --force

# Qualite
uv run ruff check .
uv run ruff format .
uv run pytest
```

## Architecture

```
schema/
└── document.py         # Chunk (Pydantic) : text, source_file, matiere, niveau, section
                        # + enums : Matiere, Niveau, Cycle, cycle_from_niveau()

scripts/
├── ingest.py           # data/raw/*.txt → SentenceChunker → mistral-embed → Qdrant
├── query.py            # embed question → retrieval Qdrant → reponse socratique Mistral
├── evaluate.py         # RAGAS avec Mistral natif (faithfulness, answer_relevancy, context_precision)
├── audit_coverage.py   # Gap analysis PROGRAMME_5EME.md vs chapitres dans les sources
└── veille_programmes.py # data.gouv.fr + Legifrance PISTE → detecte nouveaux programmes

data/
├── raw/                # Sources officielles extraites (*.txt) + veille state
│   ├── programme_maths_cycle4_BO2026.txt
│   ├── programme_technologie_cycle4_BO2024.txt
│   ├── programme_cycle4_BO2020.txt        # Francais, Hist-Geo, PC, SVT, EMC
│   ├── programme_cycle3_BO2020.txt
│   ├── programme_*_college_BO2025.txt     # Anglais, Espagnol, Allemand, Italien
│   └── sources_officielles.md             # URLs + procedure regeneration PDFs
├── processed/          # Vide (MVP sans JSONL pre-generes, chunks directs depuis .txt)
└── golden/             # Questions de test + resultats RAGAS

docs/
├── adr/                # Decisions architecturales (0001-0005)
├── programmes/
│   ├── PROGRAMME_5EME.md       # Referentiel chapitres (maths verifie vs BO 2026)
│   └── CALENDRIER_REFORMES.md  # Reformes Eduscol a anticiper
└── specs/              # Plans et specs techniques

.github/workflows/
├── ci.yml              # Lint + tests sur PR/push main
└── veille_bo.yml       # Veille hebdomadaire (lundi 8h UTC) → GitHub Issue si changement
```

## Pipeline ingest (detail)

```
data/raw/*.txt
  └─ load_source_text()       # extrait section par matiere via regex
      └─ chunk_text()          # SentenceChunker 1600 chars (≈400 tokens)
          └─ validate_chunks() # Pydantic Chunk → to_qdrant_payload()
              └─ embed_chunks() # mistral-embed batch 50, 1024D
                  └─ upsert_to_qdrant() # uuid5(sha256(text)) → idempotent
```

## Sources officielles des programmes

| Matiere | Fichier source | BO de reference |
|---------|---------------|-----------------|
| Mathematiques | programme_maths_cycle4_BO2026.txt | BO 5 mars 2026 |
| Technologie | programme_technologie_cycle4_BO2024.txt | BO 29 fev 2024 |
| Francais, Hist-Geo, PC, SVT, EMC | programme_cycle4_BO2020.txt | BO 30 juil 2020 |
| Anglais/Espagnol/Allemand/Italien | programme_*_college_BO2025.txt | BO 29 mai 2025 |

Voir `data/raw/sources_officielles.md` pour les URLs et la procedure de regeneration.

## Regles

- **EU-souverain strict** : Mistral + Qdrant EU uniquement. Jamais OpenAI/Cohere/Anthropic.
- **Pas d invention** : source de verite = data/raw/*.txt (programmes officiels).
- **Idempotence** : ID chunk = uuid5(sha256(text)), ingest rejouable sans doublons.
- **Erreurs explicites** : section introuvable = exception, pas de silence.
- **Validation systematique** : tout chunk passe par Pydantic avant upsert Qdrant.
