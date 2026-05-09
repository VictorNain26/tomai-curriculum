# Tom RAG Overhaul — Design (2026-05-09)

> **Status** : approuvé. Spec local, **non committé** par défaut.
> **Scope** : optimisation complète chaîne RAG (curriculum + server) pour rentrée mai 2026, niveaux 6ème → Terminale, primaire reporté.
> **Contraintes** : souveraineté EU stricte (RGPD), aucun SDK/SaaS US runtime ; code propre sans legacy ; recherche sourcée sans hallucination.

---

## 1. Constat — pourquoi ce chantier

Audit du 2026-05-09 sur `tomai-curriculum/` + lecture des consommateurs RAG dans `tomai-monorepo/apps/server/`. Score global : 5.0/10. Trois familles de problèmes critiques :

1. **Désynchronisations dataset / schema** : enum `Matiere` déclare 6 valeurs, le dataset en sert 22. Aucun `Document.matiere` validé (matière dérivée du nom de fichier). 13 scripts `add_*_chapters.py` hardcodent des données Python en `open("a")` non-idempotent. Re-run = duplication silencieuse.
2. **Eval faussement permissive** : `evaluate.py:52-57` matche les titres par sous-chaîne (`"Théorème" in "Théorème de Pythagore"` → True). Toutes les métriques Recall/MRR/NDCG actuelles sont gonflées artificiellement. On pilote des décisions sur des chiffres qui ne mesurent pas ce qu'on croit.
3. **Architecture sous-optimale** : pas de payload indexes Qdrant (5 filtres scannés à chaque query), pas de prompt caching Mistral (gain 90% sur system prompts longs en multi-turn), BM25 codé manuellement côté server alors qu'il existe natif Qdrant via sparse vectors + `Modifier.IDF`, ingestion non-idempotente (ID dérivé du titre, renommer = orphelins jamais supprimés).

**Vrais enjeux** : dataset incomplet (couverture 6ème = 6 matières JSONL vs 11 annoncées), métriques non fiables, infra qui accumule du déchet.

## 2. Décisions techniques (sources citées)

| # | Décision | Source |
|---|----------|--------|
| D1 | `mistral-embed` 1024D reste le modèle d'embedding (codestral-embed = code uniquement) | [Mistral Embeddings](https://docs.mistral.ai/llms-full.txt) |
| D2 | Batch embeddings : passer 10 → 50 par appel API | [Mistral cookbook](https://docs.mistral.ai/llms-full.txt) |
| D3 | Ajouter `prompt_cache_key` dans appels chat Mistral (-90% sur tokens cachés) | [Mistral API Specs](https://docs.mistral.ai/api) |
| D4 | Modèle chat principal : `mistral-large-2512` (256k contexte, $0.5/$1.5) ; reasoning explicite via `magistral-medium-latest` quand pertinent | [Models overview](https://docs.mistral.ai/getting-started/models/models_overview/) |
| D5 | Garder Scalar int8 quantization Qdrant (1024D + ~10k points → BinaryQuantization sans ROI) | [Qdrant quantization](https://qdrant.tech/documentation/guides/quantization/) |
| D6 | Ajouter sparse vectors BM25 IDF natif Qdrant + Query API RRF côté server | [Qdrant hybrid](https://qdrant.tech/articles/sparse-vectors), [BM42](https://qdrant.tech/articles/bm42) |
| D7 | Créer payload indexes KEYWORD sur `niveau`, `matiere`, `cycle`, `difficulty`, `content_type` | [Qdrant payload indexing](https://qdrant.tech/documentation/concepts/indexing/) |
| D8 | Migration Qdrant via collection alias swap atomique (dim/schema = immuables) | [Qdrant collections](https://qdrant.tech/documentation/concepts/collections/) |
| D9 | Eval matching = `expected_ids` UUID exact, jamais fuzzy titre | [Microsoft DS](https://medium.com/data-science-at-microsoft/the-path-to-a-golden-dataset-or-how-to-evaluate-your-rag-045e23d1f13f) |
| D10 | Test set golden stratifié par (niveau × matière) ≈ 460-770 queries (3-5 par cellule sur 154 cellules) | [Premai 2026](https://blog.premai.io/rag-evaluation-metrics-frameworks-testing-2026/) |
| D11 | Métriques RAGAS : Context Precision/Recall (déterministes) + Faithfulness/Response Relevancy (LLM-judge) + Tool Call Accuracy (agent) | [RAGAS docs](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) |
| D12 | LLM-judge cross-model = Mistral Large + autre modèle EU (Magistral, Aleph Alpha, LightOn) — **jamais Claude/GPT** | [LLM judge bias](https://openreview.net/forum?id=3GTtZFiajM) + souveraineté EU |
| D13 | Référence éducative FR : AlloProf (lyon-nlp, MTEB) — inspiration structurelle, pas drop-in | [AlloProf arxiv](https://arxiv.org/abs/2302.07738) |
| D14 | Cache embeddings éval par `(sha256(query), model_version)`, invalidé sur bump modèle | [Microsoft DS](https://medium.com/data-science-at-microsoft/the-path-to-a-golden-dataset-or-how-to-evaluate-your-rag-045e23d1f13f) |
| D15 | Déprécier `rerank-cohere.service.ts` (Cohere = société US, viole souveraineté EU) | Constitution Tom + RGPD |

## 3. Architecture cible

```
tomai-curriculum/
├── schema/
│   └── document.py             # Source unique vérité, enums complets
├── scripts/
│   ├── enrich.py               # Remplace les 13 add_*_chapters.py
│   ├── chunking.py             # Inchangé sauf OldDocument hors fonction
│   ├── ingest.py               # 3 phases découplées : embed → upsert → prune
│   ├── evaluate.py             # expected_ids + RAGAS + cache
│   ├── audit_coverage.py       # NEW : gap analysis vs référentiel
│   ├── migrate_collection.py   # NEW : alias swap (sparse vectors + indexes)
│   ├── qdrant_optimize.py      # Existant, conservé
│   └── utils.py                # Existant, étendu
├── data/
│   ├── processed/              # JSONL existants
│   ├── reference/              # NEW : matrice cible Eduscol
│   │   └── curriculum_targets.yaml
│   ├── golden/                 # NEW : test set 460-770 queries stratifié
│   │   └── test_queries.json
│   └── embeddings_cache/       # NEW : .parquet par model_version
├── docs/
│   ├── programmes/             # PROGRAMME_*.md déplacés
│   ├── audits/                 # RAPPORT_*.md déplacés + nouveaux
│   ├── adr/                    # Décisions architecturales (this doc + futures)
│   └── specs/                  # Specs design (ce doc)
├── eval_runs/                  # NEW : historique runs eval JSON horodatés
├── pyproject.toml
├── .env.example                # NEW
└── CLAUDE.md / README.md

Qdrant collection (nouvelle, alias-swap depuis l'ancienne) :
  - Nom canonique : tomai_educational_v2
  - Alias : tomai_educational (consommé par le server, swap atomique au cutover)
  - Dense vectors : mistral-embed 1024D, cosine, scalar int8 always_ram
  - Sparse vectors : BM25 IDF (Modifier.IDF natif Qdrant)
  - Payload indexes KEYWORD : niveau, matiere, cycle, difficulty, content_type
  - Query API RRF côté Qdrant (BM25+dense fusion server-side)

tomai-monorepo/apps/server/ (PR séparée) :
  - rag.service.ts : Query API hybrid (sparse+dense) + RRF natif
  - rerank.service.ts : DEPRECATED (suppression)
  - rerank-cohere.service.ts : DEPRECATED (suppression — souveraineté EU)
  - mistral-chat.service.ts : ajouter prompt_cache_key
```

## 4. Principes architecturaux

1. **Single source of truth** : schema Pydantic = unique source pour validation, génération types TS exposés via `@repo/api`, doc.
2. **Embeddings = artefact cacheable** : versionnés par `model_version`, jamais re-générés sans changement explicite.
3. **Ingestion idempotente** : ID stable = `uuid5(NAMESPACE_DNS, sha256(niveau + matiere + title + content))`, prune orphans systématique après upsert complet.
4. **Eval déterministe + LLM-judge ciblée** : retrieval mesuré par `expected_ids` exact (binaire), génération par RAGAS LLM-judge (Mistral Large interne + judge EU externe pour cross-validation, calibration humaine trimestrielle).
5. **Pas de legacy** : tout code one-shot supprimé en même temps que son remplacement, pas de feature flag, pas de shim de rétrocompat. Migration Qdrant via alias = rollback possible sans dual code.
6. **Souveraineté EU runtime** : Mistral (chat, embed, judge), Qdrant Cloud (région EU), Scaleway (storage). Pas de Cohere, OpenAI, Anthropic dans le runtime de l'app.

## 5. Plan d'exécution — sous-projets séquencés

### Sous-projet A — Foundation cleanup *(2-3h)*

**Objectif** : éliminer les inconsistances bloquantes avant tout refactor.

Actions :
1. Étendre `schema/document.py` :
   - `Matiere` : 22 valeurs (mathematiques, francais, physique_chimie, svt, histoire_geo, anglais, allemand, espagnol, italien, emc, technologie, sciences_technologie, snt, enseignement_scientifique, philosophie, ses, nsi, hggsp, llcer_anglais, hlp, mathematiques_complementaires, mathematiques_expertes)
   - `Cycle` : retirer le commentaire CM1/CM2 du `CYCLE3` (CP-CE2-CM1-CM2 sera géré quand on fera le primaire). Documenter explicitement scope 6ème→Terminale.
   - `datetime.utcnow()` → `datetime.now(UTC)` (2 occurrences)
   - `model_validator` quality auto-compute → méthode explicite `compute_quality()` appelée à l'ingestion uniquement
2. Supprimer commande `cli.py:ingest` (TODO non implémenté qui doublonne `ingest.py:run`)
3. Sortir `OldDocument` de `chunking.py:load_documents_from_jsonl` au top-level (ou utiliser `Document.model_construct(skip_validation=True)`)
4. Bouger `PROGRAMME_*.md` (7 fichiers) → `docs/programmes/`
5. Bouger `RAPPORT_*.md` (3 fichiers) → `docs/audits/`
6. Créer `.env.example` avec : `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`, `MISTRAL_API_KEY`
7. Dans `ingest.py:status`, dériver les listes `niveaux` et `matieres` des enums (plus de hardcodé)
8. Décider sort des `learning_objectives` template stéréotypé : **option retenue** = les retirer du texte embeddé dans `create_embedding_text` (ils restent dans le payload pour UI). Justification : ils polluent le vecteur sémantique sans valeur distinctive.
9. Commit : `chore(curriculum): foundation cleanup — schema enums, datetime UTC, doc reorg`

**Validation** :
- `uv run python scripts/cli.py validate` passe sur tous les JSONL existants
- `uv run ruff check . && uv run ruff format .` zéro warning

### Sous-projet B — Ingestion refactor *(5-7h)*

**Objectif** : pipeline ingestion idempotent, cacheable, prunable, hybrid-ready.

Actions :
1. **Supprimer** les 13 scripts `add_*_chapters.py` (données déjà présentes dans les JSONL)
2. **Créer** `scripts/enrich.py` :
   - Input : fichier JSON ou YAML externe (path en argument)
   - Validation Pydantic stricte via `Document.model_validate`
   - Dédoublonnage par `(niveau, matiere, title)` — log les doublons rejetés
   - Append au JSONL cible (mode `"a"` mais avec dédoublonnage en mémoire d'abord)
3. **Refactor** `ingest.py` en 3 commandes Typer :
   - `ingest embed` : génère embeddings par batch de 50, écrit dans `data/embeddings_cache/<model_version>/<batch>.parquet` indexé par `(content_hash, model_version)`. Ne touche jamais Qdrant.
   - `ingest upsert` : lit le cache `.parquet`, upsert vers Qdrant. ID = `uuid5(NAMESPACE_DNS, sha256(niveau:matiere:title))`. Si point existe déjà avec même `content_hash` payload, utilise `set_payload` (pas de re-upload vector). Si dim/model change, force re-upload.
   - `ingest prune` : `Filter(must_not=[HasId(current_batch_ids)])` après upsert complet → supprime les orphelins.
4. **Créer** `scripts/migrate_collection.py` :
   - Crée nouvelle collection `tomai_educational_v2` avec :
     - `vectors_config` dense (mistral-embed 1024D, cosine, scalar int8)
     - `sparse_vectors_config` BM25 avec `Modifier.IDF`
     - 5 payload indexes KEYWORD
   - Migre les points existants : `scroll` ancienne collection → upsert vers nouvelle (re-embed si la dim change, sinon copy `vector` + ajout sparse via tokenization Python BM25 OU on laisse Qdrant calculer)
   - Alias swap atomique : `update_aliases` delete `tomai_educational` ancien + create alias vers `_v2`
   - Garde l'ancienne collection 7 jours puis suppression manuelle (sécurité rollback)
5. Retirer `time.sleep(base_delay)` préventif dans `ingest.py` ; garder uniquement le backoff exponentiel sur 429
6. Tests : `tests/test_ingest_roundtrip.py` qui ingère un mini-set vers une collection éphémère, vérifie idempotence (run × 2 = même nombre de points), vérifie prune
7. Commit : `refactor(curriculum): idempotent embed/upsert/prune pipeline + sparse vectors migration`

**Validation** :
- Re-run `ingest embed` deux fois consécutivement = aucun nouvel embedding généré (cache hit 100%)
- Re-run `ingest upsert` = même `points_count` Qdrant
- Suppression manuelle d'un JSONL puis `ingest upsert + prune` = orphans correspondants supprimés de Qdrant
- Ancienne collection accessible via name direct, nouvelle via alias

### Sous-projet C — Eval rigor *(6-8h)*

**Objectif** : métriques fiables et reproductibles pour piloter toutes les optimisations futures.

Actions :
1. **Refactor** `evaluate.py` :
   - Schema `test_queries.json` v2 : `expected_ids: list[str]` (UUIDs Qdrant) au lieu de `expected_titles`
   - Fonction `id_match(retrieved_id, expected_ids) -> bool` exacte
   - Cache embeddings queries dans `data/embeddings_cache/queries/<model_version>.parquet` indexé par `sha256(query)`
   - Output JSON versionné dans `eval_runs/<YYYY-MM-DD-HHMMSS>-<git_sha>.json` avec : config (model, version, top_k, dataset_version), métriques agrégées + par cellule (niveau×matière), métadonnées (durée, coût estimé)
2. **Étendre** `data/golden/test_queries.json` :
   - Phase 1 : génération assistée RAGAS depuis le corpus actuel (~500 queries synthétiques)
   - Phase 2 : review humaine obligatoire — le user (ou prof recruté) valide / corrige / supprime
   - Cible : 3-5 queries par cellule (niveau × matière), prioriser collège (cellules avec contenu actuel) puis lycée
   - Stratifier par `content_type` : ratio 30% definition / 25% méthode / 20% theoreme / 15% formule / 10% autres
3. **Ajouter** métriques RAGAS dans `evaluate.py` :
   - Déterministes : Context Precision, Context Recall (sur expected_ids)
   - LLM-judge : Faithfulness, Response Relevancy via Mistral Large (`mistral-large-2512`)
   - Cross-validation : 10% des queries jugées par un 2ème modèle EU (à choisir : Magistral, Aleph Alpha) pour mesurer désaccord
4. **Tracking** : commande `evaluate compare <run_a> <run_b>` qui affiche delta par métrique, flag les régressions > 2%
5. Commit : `feat(curriculum): rigorous eval with expected_ids, golden stratifié, RAGAS metrics`

**Validation** :
- 1er run baseline produit un fichier dans `eval_runs/`
- Run sur le même test set deux fois → deltas tous = 0 (déterminisme retrieval)
- Faithfulness sur sample manuel cohérent avec jugement humain (calibration initiale)

### Sous-projet D — Coverage analysis *(4h audit + remplissage progressif)*

**Objectif** : identifier objectivement les manques 6ème → Terminale pour atteindre couverture optimale mai 2026.

Actions :
1. **Créer** `data/reference/curriculum_targets.yaml` :
   - Pour chaque (niveau × matière), liste des chapitres officiels Eduscol attendus + estimation min docs cible
   - Source : Bulletins Officiels (BO 30/07/2020 général, 13/06/2024 EMC, 29/02/2024 Technologie, etc.)
   - Format : `{niveau: sixieme, matiere: mathematiques, chapitres: [{nom: "Nombres et calculs", docs_min: 8}, ...], total_min: 40}`
2. **Créer** `scripts/audit_coverage.py` :
   - Compare `data/processed/` actuel vs `data/reference/curriculum_targets.yaml`
   - Sort tableau par cellule (niveau × matière) : `actual_docs / target_docs`, statut (OK ≥100%, partial 50-99%, insufficient <50%, missing 0%)
   - Détaille les chapitres manquants
3. **Output** : `docs/audits/RAPPORT_GAPS_COVERAGE.md` généré, listant les manques priorisés
4. **NE PAS inclure** la production de contenu pédagogique dans ce sous-projet — ça se fera progressivement via `enrich.py` selon le rapport
5. Commit : `feat(curriculum): coverage gap analysis with Eduscol target reference`

**Validation** :
- `uv run python scripts/audit_coverage.py` produit le rapport sans erreur
- Les chiffres correspondent aux JSONL réels

### Sous-projet E — Server optimizations *(8-12h, PR séparée monorepo)*

**Objectif** : aligner le server avec la nouvelle architecture Qdrant + souveraineté EU.

Actions sur `tomai-monorepo/apps/server/` (branche staging, workflow constitution) :

1. **Refactor** `src/services/rag.service.ts` :
   - Utiliser Qdrant Query API hybrid (prefetch dense + prefetch sparse → FusionQuery RRF)
   - Plus de `rerankWithBm25Rrf` côté server
   - Garder Cohere pour stage 2 ? **NON** : le **supprimer** (souveraineté EU)
2. **Supprimer** `src/services/rerank.service.ts` et `src/services/rerank-cohere.service.ts` + leurs tests
3. **Modifier** `src/services/chat/mistral-chat.service.ts` :
   - Ajouter `prompt_cache_key` sur les appels chat (cache 90% sur system prompt long)
   - Choisir une stratégie de clé : `prompt_cache_key = sha256(system_prompt + niveau)` (stable par session, varie par config)
4. **Mesurer avant d'optimiser** : ajouter logs `rag_call_count_per_session` pour quantifier la fréquence d'appel RAG dans `tool-executor.ts`. Si > 3 appels/session moyenne, envisager précharge contextuel par chapitre. Sinon, laisser tel quel.
5. **Tests** : `src/tests/rag-hybrid.test.ts` valide que la fusion Qdrant retourne des résultats au moins aussi bons que l'ancien BM25+Cohere sur un mini golden set
6. **Optionnel (sortir si scope trop gros)** : éval e2e agent (Topic Adherence, Tool Call Accuracy) sur 50-100 conversations golden — possible étape ultérieure
7. PR vers `staging` (CodeRabbit Free auto-review), puis merge `staging` → `main` après approbation humaine

**Validation** :
- `bun run typecheck && bun run lint && bun run test` passe
- Comparaison Recall@5 ancien (BM25 manual + Cohere) vs nouveau (Qdrant hybrid native) : pas de régression > 2%
- Logs montrent prompt_cache hit rate > 50% en production sur sessions multi-turn

## 6. Risques et mitigations

| Risque | Impact | Mitigation |
|--------|--------|------------|
| Migration Qdrant alias swap échoue en cours | Server down | Garder ancienne collection 7j, alias revert atomique |
| Sparse vectors Qdrant moins bons que BM25 manuel | Régression Recall | Sous-projet C en premier permet de mesurer avant cutover |
| Suppression Cohere = baisse précision | Régression qualité génération flashcards | Mesurer avant/après sur golden set, accepter régression mineure pour conformité EU |
| Test set golden chronophage à reviewer | Sous-projet C ralenti | Phase 1 RAGAS auto + phase 2 review étalée ; commencer petit (50-100 queries) si urgence |
| Coverage Eduscol incomplète à mai 2026 | Pas optimal pour rentrée | Sous-projet D produit le rapport gaps prioritisé, le remplissage est une activité continue post-chantier |

## 7. Critères de succès mai 2026

1. ✅ Schema curriculum reflète exactement le dataset (zéro désync)
2. ✅ Ingestion idempotente : `--prune` supprime les orphelins, embed cacheable
3. ✅ Qdrant collection moderne : sparse vectors BM25 IDF + payload indexes + alias migration
4. ✅ Eval RAG fiable : `expected_ids` exact, ≥ 460 queries golden stratifiées par cellule, métriques RAGAS reproductibles
5. ✅ Coverage map publiée : référentiel cible vs réel, plan de remplissage priorisé
6. ✅ Server : prompt caching actif, BM25 natif Qdrant, Cohere supprimé (souveraineté EU)
7. ✅ Aucun script `add_*_chapters.py`, aucun `time.sleep` préventif, aucun `OldDocument` dans une fonction
8. ✅ Documentation : ce design + ADR par sous-projet majeur, README curriculum à jour
9. ✅ Métriques baseline mesurées sur golden : Recall@5 ≥ 0.8, Faithfulness ≥ 0.8 (cibles ajustables après baseline réelle)

## 8. Hors scope (à faire plus tard)

- Couverture primaire (CP-CM2) : reportée explicitement par le user
- Bench `mistral-embed` vs nouveau modèle EU si Mistral en sort un (suivi Mistral release notes)
- Éval e2e agent complète (Topic Adherence, Tool Call Accuracy F1) — partie optionnelle de E
- Multi-tenant (segmentation par école / classe) — pas de besoin actuel

## 9. Tracking

Sous-projets gérés via TaskCreate (IDs 1-5 dans cette session). Dépendances :
- 2 (B) blocked by 1 (A)
- 3 (C) blocked by 1 (A) + 2 (B)
- 4 (D) blocked by 1 (A)
- 5 (E) blocked by 2 (B) + 3 (C)
