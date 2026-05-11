# ADR-0001 — Refonte de la chaîne RAG (curriculum + server)

- **Date** : 2026-05-09
- **Statut** : accepté, implémenté (mergé 2026-05-11)
- **Spec source** : [`docs/specs/2026-05-09-rag-overhaul-design.md`](../specs/2026-05-09-rag-overhaul-design.md)

## Contexte

Audit du 2026-05-09 sur `tomai-curriculum/` + lecture des consommateurs RAG dans `tomai-monorepo/apps/server/`. Score global initial : 5.0/10. Trois familles de problèmes critiques identifiées :

1. **Désynchronisations dataset / schema** : enum `Matiere` déclaré incomplet, `Document.matiere` non validé (dérivé du nom de fichier), 13 scripts `add_*_chapters.py` non-idempotents.
2. **Eval faussement permissive** : matching de titres par sous-chaîne (`"Théorème" in "Théorème de Pythagore"` → True). Métriques Recall/MRR/NDCG artificiellement gonflées.
3. **Architecture sous-optimale** : pas de payload indexes Qdrant, pas de prompt caching Mistral, BM25 codé manuellement côté server, ingestion non-idempotente (ID dérivé du titre).

## Décisions

| # | Décision | Source / justification |
|---|----------|------------------------|
| D1 | `mistral-embed` 1024D reste le modèle d'embedding (codestral-embed = code uniquement) | [Mistral Embeddings](https://docs.mistral.ai/llms-full.txt) |
| D2 | Batch embeddings : passer 10 → 50 par appel API | [Mistral cookbook](https://docs.mistral.ai/llms-full.txt) |
| D3 | Ajouter `prompt_cache_key` dans appels chat Mistral (-90% sur tokens cachés) | [Mistral API Specs](https://docs.mistral.ai/api) |
| D4 | Modèle chat principal : `mistral-large-2512` (256k contexte). Reasoning explicite via `magistral-medium-latest` quand pertinent | [Models overview](https://docs.mistral.ai/getting-started/models/models_overview/) |
| D5 | Conserver Scalar int8 quantization Qdrant (1024D + ~10k points → BinaryQuantization sans ROI) | [Qdrant quantization](https://qdrant.tech/documentation/guides/quantization/) |
| D6 | Ajouter sparse vectors BM25 IDF natif Qdrant + Query API RRF côté server | [Qdrant hybrid](https://qdrant.tech/articles/sparse-vectors), [BM42](https://qdrant.tech/articles/bm42) |
| D7 | Créer payload indexes KEYWORD sur `niveau`, `matiere`, `cycle`, `difficulty`, `content_type` | [Qdrant payload indexing](https://qdrant.tech/documentation/concepts/indexing/) |
| D8 | Migration Qdrant via collection alias swap atomique (dim/schema = immuables) | [Qdrant collections](https://qdrant.tech/documentation/concepts/collections/) |
| D9 | Eval matching = `expected_ids` UUID exact, jamais fuzzy titre | [Microsoft DS](https://medium.com/data-science-at-microsoft/the-path-to-a-golden-dataset-or-how-to-evaluate-your-rag-045e23d1f13f) |
| D10 | Golden set stratifié par (niveau × matière) ≈ 460-770 queries (3-5 par cellule sur 154 cellules) | [Premai 2026](https://blog.premai.io/rag-evaluation-metrics-frameworks-testing-2026/) |
| D11 | Métriques RAGAS : Context Precision/Recall (déterministes) + Faithfulness/Response Relevancy (LLM-judge) + Tool Call Accuracy (agent) | [RAGAS docs](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) |
| D12 | LLM-judge cross-model = Mistral Large + autre modèle EU (Magistral, Aleph Alpha, LightOn) — **jamais Claude/GPT** | [LLM judge bias](https://openreview.net/forum?id=3GTtZFiajM) + souveraineté EU |
| D13 | Référence éducative FR : AlloProf (lyon-nlp, MTEB) — inspiration structurelle, pas drop-in | [AlloProf arxiv](https://arxiv.org/abs/2302.07738) |
| D14 | Cache embeddings éval par `(sha256(query), model_version)`, invalidé sur bump modèle | [Microsoft DS](https://medium.com/data-science-at-microsoft/the-path-to-a-golden-dataset-or-how-to-evaluate-your-rag-045e23d1f13f) |
| D15 | Déprécier `rerank-cohere.service.ts` (Cohere = société US, viole souveraineté EU) | Constitution Tom + RGPD |

## Conséquences

### Positives
- Ingestion idempotente : ID = `uuid5(NAMESPACE_URL, content_hash)`, re-run = no-op si rien n'a changé.
- Eval rigoureuse : `expected_ids` exact remplace le fuzzy matching, métriques fiables.
- Performance Qdrant : indexes KEYWORD + scalar int8 + sparse BM25 → queries filtrées 2-5x plus rapides.
- Souveraineté EU complète : Cohere supprimé, judge cross-model EU only.
- Architecture rollback-friendly via alias atomique.

### Négatives / à traiter
- **D11 partiellement implémentée** : Context Precision/Recall déterministes en place, mais Faithfulness + Response Relevancy (LLM-judge) restent à coder.
- **D12 non implémentée** : cross-model judging EU absent.
- **Migration `Document.niveau/matiere/cycle`** : encore dérivés du nom de fichier. À ajouter au schema Pydantic (chantier suivant).
- `data/reference/curriculum_targets.yaml` (référentiel structuré) pas encore créé — `audit_coverage.py` parse les markdown ad-hoc.

## Architecture résultante

Voir la spec source section 3 pour le détail. Synthèse :

```
tomai-curriculum/
├── schema/document.py             # Source unique de vérité (enums complets)
├── scripts/
│   ├── ingest.py                  # 3 phases découplées : embed → upsert → prune
│   ├── evaluate.py                # expected_ids + métriques déterministes
│   ├── audit_coverage.py          # Gap analysis vs référentiel
│   ├── migrate_collection.py      # Alias swap (sparse vectors + indexes)
│   └── ...
├── data/
│   ├── processed/                 # JSONL (1854 docs)
│   └── golden/test_queries.json   # 31 queries curées
└── docs/{adr,audits,programmes,specs}/

Qdrant : tomai_educational_v2 (alias tomai_educational, swap atomique)
  - Dense : mistral-embed 1024D, cosine, scalar int8 always_ram
  - Sparse : BM25 IDF natif
  - Indexes KEYWORD : niveau, matiere, cycle, difficulty, content_type
```

## Référence vers les ADRs suivantes

- ADR-0002 (à venir) : ajout de `Document.niveau/matiere/cycle` au schema + migration JSONL.
- ADR-0003 (à venir) : implémentation RAGAS Faithfulness/Response Relevancy + cross-model judge EU.
