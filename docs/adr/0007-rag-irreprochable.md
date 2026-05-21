# ADR-0007 — RAG curriculum irréprochable (mai 2026)

- **Date** : 2026-05-18 (mis à jour 2026-05-18 après itérations)
- **Statut** : accepté, implémenté
- **Supersède** : aucun (étend ADR-0006)
- **Contexte audit** : `Tom/docs/audits/AUDIT_RAG_2026-05-18.md`

## Mise à jour majeure (fin de chantier)

Cet ADR initial documentait la refonte cycle 4. Le scope a ensuite été élargi
au **collège complet (6e → 3e)** avec :
- Extraction PDF moderne via **pymupdf4llm** (préserve les vrais titres H2
  des programmes Eduscol, fiabilise l'extraction par section)
- **uuid5(matière + niveau + text)** au lieu de `uuid5(text + niveau)` pour
  éviter les collisions cross-matière sur les préambules pédagogiques
  communs (langues college EN/ES/DE/IT partagent du contenu méta-didactique
  identique — l'ancien hash écrasait silencieusement)
- **Refactor DRY** : module `schema/retrieval.py` centralise l'accès Mistral
  + Qdrant, embed_query/embed_batch/hybrid_search/l2_normalize. Plus de
  duplication entre `ingest.py`, `query.py`, `evaluate.py`
- **`query.py` purifié** : retrait de toute la couche LLM (génération
  socratique). Script devient juste un outil interactif de test du retrieval.
  Cohérent avec la séparation des responsabilités : **curriculum = index,
  backend = LLM**.
- **Coverage 100 %** sur toutes les matières, **sans faux positif** (audit
  `--list-missing` confirme).

## Contexte

L'audit du 2026-05-18 a identifié 5 P0 bloquants et 9 P1 importants entre le
pipeline `tomai-curriculum` et le backend `tomai-monorepo/apps/server`. Le
ADR-0006 (accepté le matin même) avait simplifié le schema côté curriculum,
mais le backend était resté sur l'ancien contrat enrichi (`title`, `content`,
`domaine`, `sousdomaine`, `content_type`, `difficulty`, named vectors `dense`
+ sparse `bm25`).

Cet ADR documente les décisions prises pour rendre le pipeline **irréprochable**
avant d'adapter le backend (Phase 2 du chantier).

## Décisions

### D1 — Payload : schema simple + aliases backend

Le payload Qdrant produit par `schema/document.py:to_qdrant_payload()` contient :

| Champ | Source | Rôle |
|---|---|---|
| `text` | Pydantic `Chunk.text` | Source de vérité — texte brut programme |
| `source_file` | nom fichier Eduscol | Audit trail |
| `matiere` | enum `Matiere` | Filtre |
| `niveau` | enum `NiveauCollege`/`NiveauLycee` | Filtre |
| `cycle` | dérivé `cycle_from_niveau` | Filtre |
| `section` | extrait du programme | Métadonnée affichable |
| `chunk_index` | position ordinale | Tri |
| `title` | **alias de `section`** | Compat backend (Phase 1) |
| `content` | **alias de `text`** | Compat backend (Phase 1) |

Les deux aliases (`title`, `content`) permettent au backend
(`apps/server/src/services/qdrant.service.ts:172-180`) de fonctionner sans
refactor immédiat. Ils seront retirés en Phase 2 quand le backend lira
`text`/`section` directement.

**Pas réintroduit** (vs ADR-0001 enrichi) : `domaine`, `sousdomaine`,
`content_type`, `difficulty`. Ces champs nécessitent une couche LLM-generated
qu'on a explicitement supprimée en ADR-0006 (zéro contenu généré par LLM
dans le dataset = vérifiable contre les BOs officiels).

### D2 — Multi-niveau par duplication de payload (1 embed, N points)

Pour les fichiers cycle 4 (`programme_*_cycle4_*`, `programme_*_college_*`),
chaque chunk est dupliqué en N points Qdrant — un par niveau du cycle. Le
même texte → **même embedding** (calculé 1 fois, réutilisé), mais N IDs
distincts et N payloads avec `niveau` différent.

ID stable : `uuid5(NAMESPACE_URL, sha256(f"{text}:{niveau}"))`. Idempotent
sur re-run.

**Alternative écartée** : payload `niveaux: list[str]` + filtre `MatchAny`
côté backend. Imposerait un refactor immédiat du filtre `qdrant.service.ts`,
et déplace la logique multi-niveau dans le code consommateur. Le choix de
duplication est plus simple (le filtre `niveau == X` reste exact) au prix
d'un coût stockage 3× sur le cycle 4 — négligeable (<1M points, ~4 GB).

Implémentation : `scripts/ingest.py:expand_for_niveaux()`, dérive via
`schema.derive_niveaux_from_file()`.

### D3 — Contextual prefix gratuit (sans LLM)

Avant embedding, chaque chunk est préfixé par sa hiérarchie :

```
Cet extrait provient du programme officiel Éduscol de {Matière_label},
section « {section} ».

{texte brut}
```

Inspiré de [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)
(sept 2024) qui mesure −35 % failure rate (top-20) avec embeddings contextualisés,
−49 % cumulé avec BM25, −67 % avec rerank. La version Anthropic utilise un
LLM (Claude Haiku) pour générer le préfixe ; ici on l'extrait gratuitement
de la hiérarchie déjà connue (corpus structuré).

**Pas de `niveau` dans le préfixe** : permet de réutiliser le même embedding
pour les N duplications de niveau. Le niveau reste filtrable via le payload
Qdrant.

Implémentation : `schema/contextual.py:build_contextual_text()`.

### D4 — Chunking : RecursiveChunker rules markdown + tokenizer Mistral

`chonkie.RecursiveChunker` avec règles cascade respectant la structure :
1. Titres markdown (`\n## `, `\n### `) — `include_delim="next"` garde le titre
2. Paragraphes (`\n\n`)
3. Phrases (`. `, `! `, `? `)
4. Mots (whitespace) — fallback

`chunk_size=400` en **tokens Mistral vrais** (via `mistral_common`), pas
caractères approximés. Précédemment 1600 chars ≈ 400 tokens (ratio 4 approx),
maintenant exact.

Implémentation : `scripts/ingest.py:chunk_text()`.

### D5 — Hybrid search Qdrant : named vectors + sparse BM25 IDF natif

Collection créée avec :
- `vectors_config={"dense": VectorParams(1024, COSINE)}` (mistral-embed normalisé L2)
- `sparse_vectors_config={"bm25": SparseVectorParams(modifier=Modifier.IDF)}`
  — Qdrant calcule l'IDF server-side
- `quantization_config=ScalarQuantization(int8, quantile=0.99, always_ram=True)`
  — gain 4× RAM, <1 % perte recall
- Payload indexes KEYWORD sur `niveau`, `matiere`, `cycle`, `source_file`

Query API : `prefetch=[dense, bm25] + fusion=RRF` natif Qdrant.

Implémentation : `scripts/migrate_collection.py` + `scripts/query.py:hybrid_search()`.

### D6 — Tokenizer BM25 partagé Python ↔ TS (parité stricte)

`schema/bm25.py:tokenize_fr()` + `_hash_token_fnv1a()` répliquent **bit-à-bit**
le code TS de `tomai-monorepo/apps/server/src/services/rag.service.ts:172-193` :
- Regex `[a-zàâäéèêëïîôùûüÿœæç0-9]+` (lettres FR + ligatures + chiffres)
- Lowercase
- Hash FNV-1a 32-bit, masqué 31-bit positif (`& 0x7fffffff`)

**Sans parité stricte, l'IDF Qdrant est cassée silencieusement** : même mot
indexé à `idx_A` à l'ingest, queryé à `idx_B` au search → IDF inflated, recall
écroulé.

Tests de non-régression : `tests/test_bm25.py` (14 tests).

**Évolution future** : extraire dans un package npm `@repo/tokenizer` + module
Python `tomai_tokenizer` partagés. Pour l'instant, duplication contrôlée par
les tests de parité.

### D7 — Normalisation L2 obligatoire côté client

`mistral-embed` ne garantit **pas** que les vecteurs retournés sont normalisés
L2 (doc Mistral confirme par l'exemple du cookbook qui calcule explicitement
la cosine similarity via `dot / (norm × norm)`). Sans normalisation client,
les distances Qdrant `Distance.COSINE` peuvent être instables.

Implémentation : `scripts/ingest.py:_l2_normalize()` + `embed_texts()` applique
la normalisation systématiquement. Idem côté `query.py:embed_query()`.

### D8 — Prompt caching Mistral

Tous les appels chat Mistral incluent `prompt_cache_key` (top-level param) :
- `query.py` → `tom-socratic-cycle4-v1`
- `evaluate.py` → `tom-eval-socratic-v1`

Discount : 90 % sur cached tokens (system prompt socratique réutilisé à
chaque request).

Clé stable par profil de prompt — bumper le suffixe `vN` quand le system
prompt change pour forcer un nouveau cache.

### D9 — Eval RETRIEVAL déterministe (pas RAGAS LLM-judge)

**Décision révisée en cours de chantier** : `scripts/evaluate.py` mesure la
**qualité de l'index Qdrant**, pas la qualité des réponses LLM.

**Pourquoi ce pivot ?** La qualité des réponses (faithfulness, hallucination,
style socratique, adaptation pédagogique) dépend du chat service, du
prompting, de l'historique élève, des tools, de l'orchestration — tout cela
vit dans `tomai-monorepo/apps/server`. Tester ça côté curriculum aurait
mesuré le mauvais étage : un score Faithfulness faible peut venir d'un
mauvais prompt backend ET non d'un défaut de l'index. RAGAS appartient au
backend (où l'ensemble de la stack tutorat est en place).

**Côté curriculum, on mesure** :
- **Recall@k** : sur k chunks retournés, combien des `expected_keywords` ?
- **MRR** : 1 / rang du premier chunk contenant ≥ 1 keyword
- **All keywords@k** : binaire — tous les keywords présents dans le top-k ?
- **≥1 keyword@k** : binaire — au moins 1 keyword trouvé (sanity baseline)

Toutes ces métriques sont **déterministes, rapides (~10 s sur 57 questions),
sans appel LLM, sans rate limit, sans coût significatif**.

**Format golden set** (`data/golden/questions.json`) :
```json
{
  "query": "Théorème de Pythagore",
  "matiere": "mathematiques",
  "niveau": "quatrieme",
  "expected_keywords": ["pythagore", "hypoténuse", "triangle rectangle"]
}
```

**Premier baseline mesuré sur `tomai_educational_v2`** (57 questions,
top-5, 2026-05-18) :
- Recall@5 global : 0.53
- MRR : 0.72
- ≥1 keyword dans top-5 : 84 % (48/57)
- Bons résultats : Technologie 72 %, PC 68 %, EMC 67 %, HG 61 %
- À améliorer : Allemand/Espagnol/Italien à 22 % (probable mauvaise
  multilinguité de `mistral-embed` ou keywords mal choisis pour les langues
  étrangères — à investiguer)

Le `audit_coverage.py` complète : il vérifie que les **titres de sections BO**
sont présents dans la collection (sanity check exhaustivité).
- Texte indexé : 100 % sur toutes les matières (× 3 niveaux pour cycle 4)
- Sections BO couvertes : SVT/EMC 100 %, Italien 98 %, Espagnol 94 %,
  Français 92 %, Allemand 91 %, Anglais 88 %, Tech 90 %, HG 92 %, PC 87 %,
  Maths 79 %

**Phase 2 backend** ajoutera ses propres tests RAGAS dans le chat service
(Faithfulness sur le LLM, hallucination detection, style socratique via
AspectCritic) — c'est là que ces métriques ont du sens.

### D10 — Migration via alias swap atomique

`scripts/migrate_collection.py --swap-alias` bascule l'alias
`tomai_educational` → `tomai_educational_v2` en une seule opération atomique.
Zero-downtime, rollback trivial (`--swap-alias` inverse).

Procédure :
1. `migrate_collection.py` crée `tomai_educational_v2` (config cible)
2. `ingest.py` peuple v2 (utilise `QDRANT_COLLECTION + "_v2"`)
3. Smoke test `query.py` sur v2
4. `migrate_collection.py --swap-alias` bascule l'alias
5. Validation 24h en monitoring
6. `migrate_collection.py --drop-v1` libère le storage

### D11 — Souveraineté EU stricte (rappel)

Tous les modèles utilisés dans le pipeline curriculum sont **Mistral** :
- Embeddings : `mistral-embed`
- Chat / réponses : `mistral-large-latest`
- Judge primaire RAGAS : `mistral-large-latest`
- Judge secondaire RAGAS : `magistral-medium-latest`
- (Voxtral pour TTS — pas dans le scope curriculum mais EU OK)

**Aucun appel sortant** vers OpenAI / Anthropic / Cohere / Google. Aligné
avec `Tom/CLAUDE.md` racine et la mémoire user `feedback_eu_sovereignty.md`.

## Conséquences

### Positives
- **Désync curriculum ↔ backend résolue** : payload contient les aliases
  `title`/`content` qu'attend le backend, vecteurs nommés `dense`/`bm25`
  attendus, multi-niveau correct.
- **Recall mesurable** : RAGAS 0.4 avec 6 métriques (incluant ContextRecall
  et NoiseSensitivity). Cross-model judge en option.
- **Coût LLM réduit** : prompt caching −90 % sur system prompt. Embeds
  déduplifiés sur les chunks multi-niveau.
- **Idempotence préservée** : `uuid5(text+niveau)` → re-run sans doublons.
- **EU sovereignty stricte** : 100 % Mistral.

### Négatives / à traiter
- **Tokenizer BM25 dupliqué** Python+TS. Tests de parité en place mais
  réplication manuelle. Chantier futur : module partagé.
- **Coût stockage Qdrant 3×** sur cycle 4 (duplication payload). Acceptable
  pour <1 M points.
- **`mistral-common` charge ~500 MB** au premier appel chunk_text → tests
  qui l'utilisent gated par `RUN_MISTRAL_TOKENIZER_TESTS=1`.
- **Golden set encore minuscule** (4 questions hardcodées en smoke test).
  Stratification 5 × 11 matières × 3 niveaux à compléter via
  `data/golden/questions.json`.
- **`test_audit_coverage.py` supprimé** car obsolète (importait des fonctions
  renommées). À recréer si `audit_coverage.py` est utilisé en CI.

### Neutres
- Le payload reste source de vérité côté Python (Pydantic `Chunk`). Tout
  changement de schema part de `schema/document.py`.

## Phase 2 — Backend (non couvert par cet ADR)

Après validation Phase 1 :
1. Adapter `qdrant.service.ts:mapPointsToResults` pour lire `text`/`section`
   directement (retirer la dépendance aux aliases `title`/`content`).
2. Retirer les aliases du payload Phase 1 quand backend prêt.
3. Aligner `apps/server/CLAUDE.md` (retirer mentions Cohere obsolètes).
4. Décider du scope `niveau` exposé par `education.service.ts` (12 niveaux
   actuels vs cycle 4 réel).

## Phase 3 — Migration Gemini → Mistral chat (à part)

Hors scope de cet ADR. Le `chat` du backend utilise actuellement
`@google/genai` (Gemini 2.5 Flash). Violation de la souveraineté EU à
trancher dans un ADR backend séparé.

## Références

- Audit : `Tom/docs/audits/AUDIT_RAG_2026-05-18.md`
- Anthropic Contextual Retrieval : <https://www.anthropic.com/news/contextual-retrieval>
- Qdrant Sparse Vectors : <https://qdrant.tech/articles/sparse-vectors/>
- Mistral Embeddings : <https://docs.mistral.ai/capabilities/embeddings>
- Mistral Models : <https://docs.mistral.ai/getting-started/models>
- RAGAS 0.4 Migration : <https://docs.ragas.io/en/stable/howtos/migrations/migrate_from_v03_to_v04/>
- Chonkie RecursiveChunker : <https://github.com/chonkie-inc/chonkie>
