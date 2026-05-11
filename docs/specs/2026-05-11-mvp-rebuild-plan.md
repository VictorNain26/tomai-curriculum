# Plan — MVP rebuild dataset RAG optimal Éduscol mai 2026

> **Status** : approuvé, sessions multiples
> **Scope** : refonte radicale du dataset + outils pour atteindre un MVP optimal sur 1 niveau (5ème), puis dupliquer
> **Contraintes** : souveraineté EU stricte, sans inventions (réutiliser RAGAS), maintenable à long terme face aux réformes Éduscol

---

## 1. Pourquoi cette refonte ?

L'audit du 2026-05-11 a révélé que la version précédente (1854 docs / 7 niveaux) souffrait de :

- **Code custom inventé** : `evaluate_judge.py` (394 lignes) ré-implémentait Faithfulness/Response Relevancy au lieu d'utiliser RAGAS natif qui supporte Mistral depuis 2025.
- **Couverture artificielle** : ~30% des chapitres Éduscol couverts (vrai chiffre 5ème à recalculer post-fix parser), illusion de complétude.
- **Golden set sous-dimensionné** : 31 queries pour 154 cellules attendues = ~80% des cellules à 0 query.
- **Pas de stratégie veille** : programmes Éduscol changent chaque année (réforme 2025-2028 en cours), aucun mécanisme de détection.
- **Pas d'abstention** : aucune mesure de la capacité à refuser quand hors-corpus (critique en tutorat).

**Décision** : repartir d'une base saine, MVP profond sur 1 niveau, valider le pipeline complet, puis dupliquer.

## 2. Périmètre MVP

- **Niveau** : 5ème (collège, cycle 4 début)
- **Matières** : 11 (tronc commun complet) — math, français, hist-géo, PC, SVT, EMC, anglais, allemand, espagnol, italien, technologie
- **Base de départ** : 288 documents Pydantic-valides existants
- **Cible quantitative** :
  - 100% des chapitres officiels Éduscol couverts (mesuré par `audit_coverage.py` corrigé)
  - Recall@5 ≥ 0.90 / MRR ≥ 0.85 / Context Precision ≥ 0.80 sur golden set RAGAS-généré (50-100 queries stratifiées)
  - Faithfulness ≥ 0.95 / Response Relevancy ≥ 0.85 / Abstention ≥ 0.90 mesurés via RAGAS avec Mistral judge
  - **Aucune cellule (matière) avec Recall@5 < 0.80**

## 3. Hors scope MVP (gelé en archive)

- Autres niveaux (6ème, 4ème, 3ème, lycée) : supprimés du HEAD, immortalisés via tag git `archive/v1.0-pre-mvp` + branche `archive/pre-mvp-refonte`. Récupérables si besoin via `git checkout archive/pre-mvp-refonte -- <path>`.
- Sparse vectors BM25 IDF : Phase 2, à valider via RAGAS integration.
- Refactor `ingest.py` sub-400 : déjà à 408 lignes, pas critique.
- Mode admin/audit citations Éduscol : Phase 4+.

## 4. Plan d'exécution séquencé

### Phase A — Refonte structurelle (cette session) ✅

- [x] Archive immortelle : tag `archive/v1.0-pre-mvp` + branche `archive/pre-mvp-refonte`
- [x] Suppression massive : autres niveaux (~75 JSONL), 7 scripts custom inventés, 4 rapports historiques, 6 PROGRAMME_*.md hors 5ème
- [x] Master plan v2 (ce document)
- [x] ADRs 0002-0005 (archive, MVP-5ème, RAGAS, veille)
- [x] CALENDRIER_REFORMES.md
- [x] CLAUDE.md + README.md mis à jour pour le scope MVP

### Phase B — RAGAS adoption (session suivante, ~4h)

- [ ] Ajouter `ragas` à `pyproject.toml` (dev dep d'abord)
- [ ] Créer `scripts/evaluate.py` v2 basé sur RAGAS + Mistral natif (`llm_factory("mistral-large", provider="mistral", client=client)`)
- [ ] Métriques utilisées : Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall, NoiseSensitivity (RAGAS canon, pas custom)
- [ ] Test set blind séparé (10%) pour anti-overfitting (Insider Knowledge arxiv 2601.13227)
- [ ] Cross-validation cross-provider EU : à investiguer un 2e judge non-Mistral (LightOn Alfred ou self-hosted Magistral via HF Inference Endpoints EU)

### Phase C — Audit terrain (session ~2h)

- [ ] Fix `audit_coverage.py:extract_chapters_from_programme` (n'a plus le bug 0% Première/Terminale puisque ces niveaux sont retirés, mais structure markdown hiérarchique à robustifier pour MAJ futures)
- [ ] Convention markdown stricte dans `PROGRAMME_5EME.md` : `<!-- chapter -->` vs `<!-- modality -->` pour distinguer chapitres pédagogiques de modalités d'épreuve
- [ ] Re-run audit → vrai chiffre 5ème par cellule (matière)
- [ ] Rapport baseline dans `docs/audits/`

### Phase D — Golden set scalé (session ~3h)

- [ ] Pipeline RAGAS `TestsetGenerator` sur le corpus 5ème (288 docs)
- [ ] Distribution : simple / multi-hop / reasoning (60/30/10)
- [ ] Ajout queries adversariales hors-corpus pour test Abstention (~15 queries)
- [ ] Stratification minimum 5 queries par matière (55 minimum, cible 80-100)
- [ ] Validation humaine échantillon (~30%)
- [ ] Sauvegarde versionnée dans `data/golden/cinquieme_v1.json`

### Phase E — Production contenu pour combler les trous (plusieurs sessions)

- [ ] Cartographie précise des trous post-Phase C (par matière)
- [ ] Stratégie production : génération LLM contrôlée à partir de PROGRAMME_5EME.md + manuels libres
- [ ] Validation factuelle systématique avant ingestion (RAGAS Faithfulness)
- [ ] Ingestion par batch, re-eval avant/après, régression > 2 pts bloquante

### Phase F — CI eval RAG continu (session ~3h)

- [ ] `.github/workflows/eval-rag.yml` : run RAGAS sur chaque PR qui touche `data/processed/`
- [ ] Mistral + Qdrant API keys en secrets GitHub
- [ ] Comparaison run vs baseline, régression > 2 pts = ❌ blocking
- [ ] Dashboard markdown commenté dans la PR

### Phase G — Veille Éduscol automatisée (session ~3h)

- [ ] `.github/workflows/eduscol-watch.yml` : scheduled (mensuel)
- [ ] Scrape RSS BO (`https://www.education.gouv.fr/le-bulletin-officiel-de-l-education-nationale-de-la-jeunesse-et-des-sports`)
- [ ] Filter : keywords "programme", "enseignement", "cycle", "lycée"
- [ ] Cross-check : API Légifrance pour les arrêtés MENE* officiels
- [ ] Création automatique d'un GitHub Issue si nouveau BO programmes détecté

### Phase H — Duplication aux autres niveaux (sessions multiples post-MVP validé)

- Une fois MVP 5ème en green (toutes métriques cibles atteintes en CI continue) :
  - Restaurer le contenu archivé pertinent : `git checkout archive/pre-mvp-refonte -- data/processed/college/sixieme/`
  - Appliquer le pipeline Phases C → F au niveau suivant
  - Priorité ordre logique : 6ème (réforme 2025-2026 prioritaire), puis 4ème, 3ème, 2nde, 1ère, Terminale

## 5. Architecture cible

```
tomai-curriculum/
├── schema/
│   ├── __init__.py                     # Exports (déjà clean post PR #10)
│   └── document.py                     # Pydantic strict, inchangé
├── scripts/
│   ├── cli.py                          # validate, stats
│   ├── ingest.py + ingest_lib.py       # pipeline 3 phases : embed → upsert → prune
│   ├── audit_coverage.py               # À fixer Phase C, parser hiérarchique robuste
│   ├── qdrant_optimize.py              # Ops : configure indexes + quantization
│   ├── utils.py                        # Helpers communs
│   └── (Phase B) evaluate.py           # NEW : wrapper RAGAS minimal
├── data/
│   ├── raw/                            # Sources officielles
│   ├── processed/college/cinquieme/    # MVP scope (288 → 100% Éduscol après Phase E)
│   └── golden/                         # (Phase D) cinquieme_v1.json généré RAGAS
├── docs/
│   ├── adr/                            # 0001 (rag-overhaul), 0002-0005 (cette refonte)
│   ├── programmes/
│   │   ├── PROGRAMME_5EME.md           # Source de vérité curée 5ème
│   │   └── CALENDRIER_REFORMES.md      # Planning réformes officielles à anticiper
│   ├── audits/                         # Rapports baseline + suivi
│   └── specs/                          # Specs design (this doc + 2026-05-09)
├── tests/
│   ├── test_audit_coverage.py
│   ├── test_ingest_pipeline.py
│   ├── test_schema.py
│   └── (Phase B) test_evaluate_ragas.py
└── .github/workflows/
    ├── ci.yml                          # Lint + tests (existant)
    ├── (Phase F) eval-rag.yml          # NEW : RAGAS eval sur chaque PR data
    └── (Phase G) eduscol-watch.yml     # NEW : veille programmes mensuelle
```

## 6. Critères d'arrêt MVP

Le MVP 5ème est déclaré **optimal** quand :

- ✅ 100% des chapitres `PROGRAMME_5EME.md` (post conversion modalités/chapitres) ont ≥ 1 document JSONL
- ✅ Recall@5 ≥ 0.90 et Faithfulness ≥ 0.95 sur le blind eval set
- ✅ Abstention ≥ 0.90 sur 15+ queries hors-corpus
- ✅ Aucune matière avec Recall@5 < 0.80
- ✅ CI eval RAG verte sur main (Phase F)

Avant ces critères : on est en construction. Pas optimal.

## 7. Décisions architecturales documentées

- ADR-0002 : Pourquoi archiver l'état pre-MVP via tag/branch git
- ADR-0003 : Pourquoi MVP sur 5ème en premier
- ADR-0004 : Pourquoi adopter RAGAS plutôt que maintenir notre code custom
- ADR-0005 : Comment rester à jour avec les programmes Éduscol (veille)

## 8. Références recherche

- RAGAS docs (custom LLM provider Mistral) : https://docs.ragas.io
- Mistral SDK `chat.parse` Pydantic : https://docs.mistral.ai/api
- Insider Knowledge (arxiv 2601.13227, mars 2026) : metric overfitting, blind eval
- LIT-RAGBench (arxiv 2603.06198, mars 2026) : 5 catégories dont Abstention
- GroUSE (arxiv 2409.06595) : 7 generator failure modes
- Justice or Prejudice (arxiv 2410.02736) : 12 biais LLM-as-Judge
- AlloProf (arxiv 2302.07738) : référence FR éducatif
- MTEB-fr (arxiv 2405.20468) : benchmark embeddings français
