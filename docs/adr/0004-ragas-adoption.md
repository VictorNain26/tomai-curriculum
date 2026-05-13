# ADR-0004 — Adoption de RAGAS pour l'évaluation RAG (vs code custom)

- **Date** : 2026-05-11
- **Statut** : accepté, implémentation Phase B
- **Spec source** : [`docs/specs/2026-05-11-mvp-rebuild-plan.md`](../specs/2026-05-11-mvp-rebuild-plan.md)

## Contexte

Pré-refonte, le repo contenait `scripts/evaluate_judge.py` (394 lignes) qui ré-implémentait à la main les métriques **Faithfulness** et **Response Relevancy** définies par RAGAS depuis 2023. Le code custom :

- Maintenait ses propres prompts (extraction claims, verdict NLI, génération questions hypothétiques)
- Parsait du JSON manuellement (`json.loads()` + try/except) au lieu d'utiliser le structured output Mistral
- N'incluait pas les métriques canoniques **NoiseSensitivity**, **AnswerCorrectness**, **AnswerSimilarity** de RAGAS
- N'avait aucune protection contre les **12 biais LLM-as-Judge** documentés (arxiv 2410.02736)
- Demandait maintenance perpétuelle alors que RAGAS est mis à jour par la communauté

Investigation Context7 du 2026-05-11 : RAGAS supporte **Mistral en provider natif** depuis 2025 :

```python
from mistralai import Mistral
from ragas.llms import llm_factory

client = Mistral(api_key="...")
llm = llm_factory("mistral-large", provider="mistral", client=client)
# Instructor adapter automatique, aucun LangChain requis
```

Compatible souveraineté EU stricte (pas d'OpenAI/Anthropic au runtime).

## Décision

**Supprimer le code eval custom et adopter RAGAS avec Mistral natif.**

Ce qui est supprimé :
- `scripts/evaluate_judge.py` (394 lignes)
- `scripts/evaluate.py` (603 lignes, version pré-MVP)
- `tests/test_evaluate_judge.py`, `tests/test_evaluate_metrics.py`

Ce qui sera créé en Phase B :
- `scripts/evaluate.py` v2 : wrapper minimal RAGAS + Mistral natif (~150 lignes)
- `tests/test_evaluate_ragas.py` : tests d'intégration mockés

Métriques utilisées (toutes RAGAS canon) :
- **Faithfulness** : factuality de la réponse vs context
- **AnswerRelevancy** : la réponse adresse la question
- **ContextPrecision** : les contexts retournés sont pertinents
- **ContextRecall** : les contexts couvrent l'information attendue
- **NoiseSensitivity** : robustesse à l'ajout de contexts noisy
- **AspectCritic** custom : Abstention (refuser si hors-corpus) — D11/LIT-RAGBench

## Conséquences

### Positives
- **~1000 lignes de code custom supprimées** (eval + tests + prompts)
- **Métriques canon** maintenues par la communauté RAGAS
- **Protection biais** héritée des recherches RAGAS (continuellement améliorée)
- **NoiseSensitivity** et **AnswerCorrectness** disponibles immédiatement (manquaient en custom)
- **Souveraineté EU préservée** : Mistral natif, pas de dépendance OpenAI/Anthropic au runtime

### Négatives
- **Dépendance externe** : `ragas` ajouté à `pyproject.toml`. Mitigé par le fait que c'est un package mature et activement maintenu.
- **Apprentissage** : équipe doit connaître RAGAS API. Mitigé par docs Context7 et docs.ragas.io.
- **Vérifier transitivité OpenAI** : RAGAS importe-t-il `langchain-openai` même quand Mistral provider est utilisé ? À vérifier en Phase B. Si oui, install `ragas[mistral]` minimal ou strip les deps OpenAI.

## Alternatives considérées

- **DeepEval** (Confident AI) : très mature, syntax pytest-friendly. Aussi viable mais RAGAS a la mention "mistral provider natif" la plus claire dans les docs.
- **Garder le code custom** : refusé, dette maintenue inutilement, biais non corrigés, métriques manquantes.
- **Coder un wrapper TRACe** (RAGBench arxiv 2407.11005) : intéressant (5 métriques explicables, RoBERTa fine-tuné > LLM-judge) mais nécessite training d'un modèle, hors scope MVP.

## Validation prévue

Phase B (session suivante) :
- [ ] `pip install ragas` puis `uv pip compile` pour figer
- [ ] Vérifier transitivité : RAGAS doit pouvoir tourner sans `langchain-openai` installé
- [ ] Smoke test : run RAGAS sur 1 sample, vérifier qu'aucun appel sortant n'atteint OpenAI/Anthropic
- [ ] Architecture finale dans ADR-0006 si findings inattendus

## Référence

- RAGAS docs : https://docs.ragas.io
- RAGAS GitHub : https://github.com/vibrantlabsai/ragas
- Mistral SDK Python : https://github.com/mistralai/client-python
- Spec D11 (RAGAS metrics) : `docs/specs/2026-05-09-rag-overhaul-design.md`
