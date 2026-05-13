# ADR-0003 — MVP sur la 5ème en premier (avant duplication aux autres niveaux)

- **Date** : 2026-05-11
- **Statut** : accepté
- **Spec source** : [`docs/specs/2026-05-11-mvp-rebuild-plan.md`](../specs/2026-05-11-mvp-rebuild-plan.md)

## Contexte

7 niveaux dans le scope Tom (6ème → Terminale), 1854 documents JSONL au total pré-refonte mais qualité inégale. Approche "tout faire en parallèle" → aucun niveau optimal court terme. Approche "MVP profond sur 1 niveau" → un niveau atteint l'optimal, le pipeline est validé, on duplique.

Choix du niveau MVP entre 4 candidats :

| Niveau | Docs pré-MVP | Matières | Argument |
|--------|--------------|----------|----------|
| 6ème | 150 | 6 | Plus petit scope, MVP plus rapide. **MAIS** réforme cycle 3 (math+français) applicable 2025-2026 → contenu obsolète immédiat |
| **5ème** | **288** | **11** | **Le mieux fourni**. Tronc commun coll├⌐ge complet. Pas affect├⌐ par la r├⌐forme 2025-2026 (cycle 4). Familier (le user a d├⌐j├ travaill├⌐ dessus) |
| Terminale | 347 | 18 | Le plus large. **MAIS** parser audit_coverage cassé sur Première/Terminale (hiérarchie markdown H3 sous H2 "Enseignements communs"), correction préalable nécessaire |
| Autres (4ème/3ème/2nde/1ère) | variable | variable | Pas d'argument distinctif |

## Décision

**Démarrer le MVP sur la 5ème.**

Raisons :
1. **288 docs Pydantic-valides** : base de départ la plus solide
2. **11 matières du tronc commun** : scope complet, sans complexités spécialités (Terminale)
3. **Réforme stable** : pas de programmes 5ème en cours de refonte officielle (la réforme cycle 3 ne touche que 6ème côté collège)
4. **Familiarité** : maintenance facilitée pour le user
5. **Aucun blocage technique** : parser audit_coverage fonctionne sur la structure markdown 5ème, contrairement à Première/Terminale

## Conséquences

### Positives
- Pipeline complet validé end-to-end avant duplication (réduit le risque architectural)
- Critères objectifs vérifiables ("MVP est validé quand Recall@5 ≥ 0.90 sur 5ème")
- Plus simple à mesurer (RAGAS sur 11 matières, pas 18+)

### Négatives
- Les élèves 6ème/lycée n'ont pas Tom optimal court terme
- Risque d'over-fitting méthode à la 5ème : à mitiger en Phase H par duplication méthodique avec validation

## Plan de duplication post-MVP (Phase H)

Ordre proposé par priorité réforme + complexité :
1. **6ème** : urgence réforme cycle 3 rentrée 2025-2026 (programmes math+français mis à jour avril 2025)
2. **4ème** puis **3ème** : compléter le cycle 4
3. **2nde** : transition lycée
4. **1ère** puis **Terminale** : fix parser hiérarchique nécessaire avant (markdown H3 sous H2 "Enseignements communs")

Pour chaque niveau : restaurer base archivée → appliquer Phases C→F → critères MVP cibles → merge.

## Référence

- Master plan : `docs/specs/2026-05-11-mvp-rebuild-plan.md`
- Calendrier réformes : `docs/programmes/CALENDRIER_REFORMES.md`
