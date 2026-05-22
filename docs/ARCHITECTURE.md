# Architecture — tomai-curriculum

Source de vérité unique sur l'architecture du pipeline RAG des programmes
officiels Éduscol.

## Scope

Ce repo gère **uniquement l'index RAG** : extraction PDF → markdown →
chunking → embeddings → indexation Qdrant. La couche LLM (chat socratique,
prompting, faithfulness/hallucination eval, mémoire élève) est la
responsabilité du backend `tomai-monorepo/apps/server`.

Frontière non négociable :

| Curriculum (ce repo) | Backend (`apps/server`) |
|---|---|
| Extraction PDF, chunking, contextual prefix | Récupération runtime (query Qdrant) |
| Choix et version du modèle d'embedding | Reranker runtime |
| Schema payload Qdrant, named vectors, BM25 IDF | Prompt socratique, history, tools |
| Eval **retrieval** déterministe (recall@k, MRR) | Eval **réponse** LLM (faithfulness, hallu) |
| Golden set generation offline | Monitoring runtime (latence, cache hit) |
| Veille BO + ingestion | Mémoire élève, personnalisation |

## Souveraineté EU stricte

Toute la stack passe par des fournisseurs ou modèles EU-déployables :

- **Embeddings** : `mistral-embed` (1024D)
- **Génération offline du golden set** : `mistral-large-latest`
- **Index vectoriel** : Qdrant Cloud, région `fr-par`
- **Veille** : data.gouv.fr + Légifrance (PISTE)

Aucun appel sortant vers OpenAI, Anthropic, Cohere, Google, Voyage.

## Pipeline de données

```
data/raw/*.pdf
  └─ scripts/extract_pdfs.py (pymupdf4llm)
       → data/raw/*.md (titres H2/H3 fiables)

data/raw/*.md
  └─ scripts/ingest.py
       ├─ load_source_text()       préfère .md sinon .txt
       ├─ extract_section()        regex `^## \*\*Matière\*\*` pour fichiers
       │                           multi-matières (cycle3 BO2020, cycle4 BO2020)
       ├─ chunk_text()             chonkie RecursiveChunker, 400 vrais tokens
       │                           Mistral, cascade règles markdown
       ├─ expand_for_niveaux()     duplique 1 chunk × N niveaux du cycle
       ├─ validate_chunks()        Pydantic Chunk → payload Qdrant
       ├─ embed_batch()            mistral-embed batch 50, L2 normalize
       │                           (préfixe contextuel hiérarchique sans LLM)
       └─ upsert_to_qdrant()       named {dense, bm25}, idempotent
                                   uuid5(NAMESPACE_URL, sha256(matière:niveau:text))
```

## Schema Chunk

Payload Qdrant canonique (`schema/document.py`, classe `Chunk` Pydantic) :

| Champ | Source | Rôle |
|---|---|---|
| `text` | texte brut du programme | Source de vérité affichable au LLM |
| `source_file` | nom du fichier Éduscol | Audit trail |
| `matiere` | enum `Matiere` | Filtre payload |
| `niveau` | enum `NiveauCollege` ou `NiveauLycee` | Filtre payload |
| `cycle` | dérivé `cycle_from_niveau(niveau)` | Filtre payload |
| `section` | section du programme (ex: "Nombres et calculs") | Métadonnée affichable |
| `chunk_index` | position ordinale | Tri |

Tous les champs sont validés Pydantic. Aucun champ LLM-generated dans
l'index (pas de `domaine`, `sousdomaine`, `difficulty`, `content_type`) —
le dataset est strictement vérifiable contre les BO officiels.

## Multi-niveau par duplication de payload

Pour les fichiers cycle 4 ou collège complet, chaque chunk est dupliqué en
N points Qdrant — un par niveau du cycle. Le même texte produit le **même
embedding** (calculé une fois, réutilisé) mais N IDs distincts et N payloads
avec `niveau` différent.

ID stable : `uuid5(NAMESPACE_URL, sha256(f"{matière}:{niveau}:{text}"))`.
Le préfixe `matière` évite les collisions cross-matière sur les préambules
pédagogiques communs (langues collège EN/ES/DE/IT partagent du contenu
identique).

Alternative écartée : `niveaux: list[str]` + filtre `MatchAny` côté backend.
Imposerait un refactor du filtre `niveau` et déplacerait la logique
multi-niveau dans le code consommateur. La duplication coûte ~3× en
stockage sur le cycle 4 — négligeable (<1M points, ~4 GB).

## Contextual prefix hiérarchique (sans LLM)

Avant embedding, chaque chunk est préfixé par sa hiérarchie matière + section :

```
Cet extrait provient du programme officiel Éduscol de {Matière_label},
section « {section} ».

{texte brut}
```

Inspiré de la méthode [Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)
d'Anthropic. La version Anthropic utilise un LLM (Claude Haiku) pour générer
le préfixe ; ici on l'extrait gratuitement de la hiérarchie déjà connue
(corpus structuré H2/H3 fiable via pymupdf4llm).

Le `niveau` n'est PAS dans le préfixe : permet de réutiliser le même
embedding pour les N duplications de niveau (économie 3× sur l'API
embeddings). Le niveau reste filtrable via le payload Qdrant.

Implémentation : `schema/contextual.py:build_contextual_text()`.

## Chunking

`chonkie.RecursiveChunker` avec cascade :

1. Titres markdown (`\n## `, `\n### `) — `include_delim="next"` garde le titre
2. Paragraphes (`\n\n`)
3. Phrases (`. `, `! `, `? `)
4. Mots (whitespace) — fallback

`chunk_size=400` en **tokens Mistral réels** via `mistral_common`.

## Index Qdrant

Collection unique : `tomai_educational` (variable d'env `QDRANT_COLLECTION`).
Pas de versioning dans le nom — migration via `--recreate` si schéma immuable.

Config (`scripts/migrate_collection.py`) :

- `vectors_config["dense"]` : `VectorParams(size=1024, distance=COSINE)`
- `sparse_vectors_config["bm25"]` : `SparseVectorParams(modifier=Modifier.IDF)`
- `quantization_config` : Scalar int8, `quantile=0.99`, `always_ram=True`
  — 4× compression RAM, <1% perte recall sur 1024D
- Payload indexes KEYWORD sur : `niveau`, `matiere`, `cycle`, `source_file`

## Retrieval hybrid

`schema/retrieval.py:hybrid_search()` :

- Prefetch dense (mistral-embed) — `top_k * 4`
- Prefetch sparse BM25 (Qdrant calcule l'IDF server-side) — `top_k * 4`
- Fusion RRF native via `models.FusionQuery(fusion=models.Fusion.RRF)`
- Filtres exact-match sur `matiere`, `niveau`, `cycle` (KEYWORD indexes)

`schema/retrieval.py` est l'**unique** point d'accès Mistral + Qdrant.
Source de vérité pour `embed_query`, `embed_batch`, `l2_normalize`,
`hybrid_search`. Aucune duplication dans les scripts.

## BM25 sparse : parité stricte Python ↔ TypeScript

Qdrant ne tokenise pas côté serveur : il reçoit `{indices: u32[], values:
f32[]}` et calcule l'IDF. Pour que l'IDF soit cohérent, le **même**
algorithme de tokenisation + hash doit être utilisé à l'ingestion (ce repo)
ET à la query (backend `tomai-monorepo/apps/server/src/services/rag.service.ts`).

Algorithme (`schema/bm25.py`) :

- Regex `[a-zàâäéèêëïîôùûüÿœæç0-9]+` (lettres FR + ligatures + chiffres)
- Lowercase
- Hash FNV-1a 32-bit, masqué 31-bit positif (`& 0x7fffffff`)

Sans parité stricte, l'IDF Qdrant est cassée silencieusement — même mot
indexé à un indice, queryé à un autre → recall écroulé.

Validation : `tests/test_bm25.py` (14 tests) + fixture export
`scripts/dump_bm25_fixture.py` consommée par le test TS côté monorepo.

## L2 normalize obligatoire

`mistral-embed` ne garantit pas que les vecteurs retournés sont normalisés
L2. Sans normalisation client-side, `Distance.COSINE` Qdrant est instable.
`schema/retrieval.py:l2_normalize()` est appliqué systématiquement sur
embed_query et embed_batch.

## Evaluation retrieval

`scripts/evaluate.py` mesure la qualité de l'INDEX uniquement. Aucun appel
LLM. Métriques déterministes, ~10 s par 60 questions.

Deux signaux complémentaires :

- **[primary] chunk_id Recall@k** : le `gold_chunk_id` (UUID5 du chunk
  source) est-il dans le top-k ? Disponible pour les questions générées
  par `generate_golden.py` (document-grounded). Signal propre, immune aux
  faux positifs lexicaux.
  - Référence : [arXiv 2510.21440](https://arxiv.org/abs/2510.21440)
    (Redefining Retrieval Evaluation in the Era of LLMs),
    [CoFE-RAG arXiv 2410.12248](https://arxiv.org/abs/2410.12248).
- **[secondary] keyword Recall@k** : fraction des `expected_keywords`
  présents dans le top-k (sous-chaîne casefold). Surestime systématiquement
  vs human-judged relevance. Conservé pour comparaison historique et
  golden sets seed (sans `gold_chunk_id`).

Toute eval LLM-judge (Faithfulness, hallucination, style socratique) est
backend.

## Golden set

`data/golden/questions.json` — schema Pydantic `schema.golden.GoldenQuestion`.
Cible 300 questions stratifiées par `(matière × niveau)`.

Génération document-grounded via `scripts/generate_golden.py` :

1. **Context sampling** : tirage stratifié par strate `(matière × niveau)`
   pour garantir une couverture équilibrée
2. **QA generation** : Mistral large génère 1 question + 3-5 keywords
   extraits textuellement du chunk, via `response_format` JSON Schema strict
3. **Anti-hallucination filter** : Pydantic vérifie que ≥2 keywords sont
   effectivement présents dans le chunk source. Sinon la question est
   rejetée.
4. **`gold_chunk_id`** calculé localement avec la même formule UUID5
   `(matière, niveau, text)` que `ingest.upsert_to_qdrant` — garantit que
   le chunk attendu est bien celui en base.

Alignement avec l'état de l'art :

- [RAGalyst arXiv 2511.04502](https://arxiv.org/abs/2511.04502) — pipeline
  agentique document-grounded, single-hop only.
- [RAGAS TestsetGenerator](https://docs.ragas.io/en/stable/concepts/test_data_generation/rag/)
  — knowledge graph + synthesizers. Notre approche est plus légère (pas de
  knowledge graph), suffisante pour un corpus déjà structuré.

Hard negatives (PrismRAG arXiv 2507.18857) : **hors scope curriculum**.
Mesurent la résilience de la **génération** (le LLM doit ignorer un
distracteur). Mesure runtime → backend.

## Veille programmes Éduscol

`scripts/veille_programmes.py` + `.github/workflows/veille_bo.yml` :

- **data.gouv.fr** — dataset `programmes-denseignement-du-second-degre`
  surveillé via `last_modified` + hash des ressources PDF
- **Légifrance PISTE API** (optionnel, secrets `PISTE_CLIENT_ID/SECRET`) —
  endpoint `consult/lastNJo` + `jorfCont` pour détecter les arrêtés MENE*
  (Éducation) publiés au JO

Workflow hebdomadaire (lundi 8h UTC) :

1. Détecte changements + télécharge nouveaux PDFs
2. Commit `data/raw/.veille_state.json`
3. Crée une GitHub Issue avec checklist d'intégration manuelle

Sortie programmatique : `data/raw/.veille_changes.json`.

## Sources officielles

| Matière / niveau | Fichier source | BO |
|---|---|---|
| Cycle 3 (6e) — toutes matières | `programme_cycle3_BO2020.md` | 30/07/2020 |
| Cycle 4 BO 2020 — FR/HG/PC/SVT/EMC/Arts/Musique/EPS/HDA | `programme_cycle4_BO2020.md` | 30/07/2020 |
| Maths cycle 4 | `programme_maths_cycle4_BO2026.md` | 05/03/2026 |
| Technologie cycle 4 | `programme_technologie_cycle4_BO2024.md` | 29/02/2024 |
| Langues vivantes collège | `programme_{anglais,espagnol,allemand,italien}_college_BO2025.md` | 29/05/2025 |

URLs + procédure de régénération : `data/raw/sources_officielles.md`.
Inventaire de référence : `data/raw/programmes_second_degre_datagouv.json`.

## Audit coverage

`scripts/audit_coverage.py` vérifie que les titres de sections des BO
officiels sont présents dans la collection. Deux signaux :

- **Couverture texte** : `chars_indexés / chars_source`
- **Couverture sections** : % des titres extraits du BO présents dans ≥1 chunk

Diagnostic : `--list-missing` liste les titres BO non couverts.
Rapport horodaté : `docs/audits/coverage_YYYY-MM-DD.md`.

Dernière mesure (2026-05-18) : 100 % texte indexé sur toutes les matières,
couverture sections BO 79 % (maths) à 100 % (SVT, EMC).

## Frontière des contrats avec le backend

Le backend (`tomai-monorepo/apps/server`) consomme l'index Qdrant via une
couche `qdrant.service.ts` + `rag.service.ts`. **Contrats critiques** :

- **Payload Qdrant** stable : `text, section, matiere, niveau, cycle,
  source_file, chunk_index`. Tout ajout/retrait de champ doit être planifié
  avec le backend.
- **Tokenizer BM25** strictement identique (FNV-1a 32-bit + regex FR
  documentée plus haut). Toute divergence casse l'IDF Qdrant silencieusement.
- **Nom de collection** partagé via variable d'env `QDRANT_COLLECTION`.

## Pistes à mesurer (sans engagement prématuré)

Ces leviers ont été identifiés par recherche état de l'art mai 2026 ; à
benchmarker sur la baseline `chunk_id_recall` avant tout commit de
migration :

1. **`chunk_size` 400 → 512 tokens** — consensus 2025-2026 (Vecta, Firecrawl,
   PreMAI). Gain attendu ~2-5 %.
2. **`Fusion.RRF` → `Fusion.DBSF`** (Qdrant 1.11+, [release notes](https://qdrant.tech/blog/qdrant-1.11.x/)).
   Aucun bench public sur corpus FR éducatif — test trivial à faire.
3. **Bump `pymupdf4llm`** à la dernière release ([github.com/pymupdf/pymupdf4llm/releases](https://github.com/pymupdf/pymupdf4llm/releases))
   pour gains perf et extras `[layout]`.
4. **Mesure offline d'un reranker** dans `evaluate.py --rerank=...`. La seule
   option EU Apache 2.0 production-ready en mai 2026 est
   [`mxbai-rerank-large-v2`](https://www.mixedbread.com/docs/models/reranking/mxbai-rerank-large-v2)
   (Mixedbread, Berlin, 1.5B, BEIR nDCG@10 57.49). Jina v3 = CC-BY-NC, BGE
   = Chine, Cohere = US.
5. **Embedder multilingue alternatif** SI la baseline `chunk_id_recall`
   confirme un déficit LV (Allemand/Espagnol/Italien). `mistral-embed`
   n'est pas officiellement multilingue selon la doc Mistral. Candidats
   self-host Scaleway : BGE-M3 (MIT, 1024D, sparse natif → simplifierait
   le BM25), multilingual-e5-large-instruct (MIT, US-origin).

Le **branchement runtime** (rerank, alternatives) reste responsabilité
backend. Côté curriculum, on **mesure** offline pour informer la décision.

## Références

### Documentation officielle (sources de vérité)

- [Mistral structured outputs](https://github.com/mistralai/platform-docs-public/blob/main/src/app/(docs)/(products)/studio-api/conversations/structured-output/custom/page.mdx)
- [Mistral embeddings](https://docs.mistral.ai/capabilities/embeddings)
- [Qdrant hybrid queries (RRF, DBSF)](https://qdrant.tech/documentation/search/hybrid-queries/)
- [Qdrant sparse vectors](https://qdrant.tech/articles/sparse-vectors/)
- [Qdrant quantization](https://qdrant.tech/documentation/guides/quantization/)
- [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)
- [PyMuPDF4LLM](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/)
- [Chonkie RecursiveChunker](https://github.com/chonkie-inc/chonkie)
- [RAGAS docs](https://docs.ragas.io/en/stable/)

### Recherche académique citée

- [arXiv 2511.04502 — RAGalyst](https://arxiv.org/abs/2511.04502)
- [arXiv 2510.21440 — Redefining Retrieval Evaluation in the Era of LLMs](https://arxiv.org/abs/2510.21440)
- [arXiv 2410.12248 — CoFE-RAG](https://arxiv.org/abs/2410.12248)
- [arXiv 2507.18857 — PrismRAG](https://arxiv.org/abs/2507.18857)
