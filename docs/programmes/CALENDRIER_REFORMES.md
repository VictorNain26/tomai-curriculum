# Calendrier des réformes programmes Éduscol (2025-2028)

> **Mis à jour** : 2026-05-11
> **Source** : recherche WebSearch du 2026-05-11 (BO + reforme.education + Légifrance)
> **Stratégie veille** : voir `docs/adr/0005-eduscol-veille-strategy.md`

Liste des **MAJ programmes officiellement annoncées** par le Ministère de l'Éducation Nationale. Permet d'anticiper les mises à jour du dataset Tom plutôt que de réagir post-publication.

---

## Calendrier détaillé

### Cycle 3 — Mathématiques et Français (arrêté 10/04/2025)

- **Référence officielle** : Arrêté du 10 avril 2025 (Légifrance JORFTEXT000051468918)
- **Niveaux concernés** :
  - **CM1** : applicable rentrée **2025-2026** (hors scope Tom — primaire reporté)
  - **CM2** : applicable rentrée **2026-2027** (hors scope Tom)
  - **6ème** : applicable rentrée **2025-2026** ⚠️ **scope Tom Phase H**
- **Matières** : Mathématiques + Français
- **Action Tom** :
  - Au moment de restaurer la 6ème depuis l'archive (Phase H), partir des **nouveaux programmes** pas de l'ancien `PROGRAMME_6EME.md` archivé
  - Récupérer le texte officiel sur Légifrance ou Éduscol au moment de la restauration

### Cycle 4 — Mathématiques et Français (réforme phasée)

D'après les annonces ministérielles 2025-2026 :
- **5ème** : applicable rentrée **2026-2027**
- **4ème** : applicable rentrée **2027-2028**
- **3ème** : applicable rentrée **2028-2029**

**Action Tom** :
- ⚠️ **MVP 5ème actuel basé sur les programmes en vigueur (BO 30/07/2020)** valide jusqu'à la rentrée 2026
- Anticipation : prévoir une session "MAJ programmes 5ème" été 2026, dès la publication du BO réformé
- À surveiller dans la veille RSS BO (Couche 1 de la stratégie veille)

### Lycée — Statu quo (pas de réforme majeure annoncée à date)

- 2nde, 1ère, Terminale : programmes en vigueur depuis BO 22/01/2019 (1ère) et BO 25/07/2019 (Terminale)
- Aucune réforme majeure connue pour rentrée 2025-2026 ou 2026-2027
- Hors scope MVP actuel (Phase H)

### EMC — Programme 2024 (BO 13/06/2024)

- Programme actualisé en juin 2024, applicable rentrée 2024-2025
- Dataset 5ème a probablement été initialement bâti sur l'ancien programme
- À vérifier en Phase C : `PROGRAMME_5EME.md` doit refléter le BO 13/06/2024

### Technologie — Programme 2024 (BO 29/02/2024)

- Programme actualisé en février 2024, applicable rentrée 2024-2025
- Dataset 5ème : à vérifier alignement avec BO 29/02/2024 en Phase C

---

## Watchlist active

| Indicateur | Sujet | À vérifier |
|------------|-------|------------|
| 🔔 | Nouveaux BO mensuels | GitHub Action eduscol-watch (Phase G) |
| 🔔 | API Légifrance MENE* | Semestriel manuel (cf. ADR-0005 Couche 2) |
| 🟡 | Réforme cycle 4 (5ème prévue 2026-2027) | Veille particulière été 2026 |
| 🟢 | Réformes lycée | Aucune annoncée, monitoring passif |

---

## Sources

- Réforme cycle 3 maths/français : https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000051468918
- BO EMC : https://www.education.gouv.fr/bo/2024/Hebdo41/MENE2415135A
- BO Technologie : https://www.education.gouv.fr/bo/...
- Calendrier réformes synthèse : https://reforme.education/reforme-des-programmes-scolaires-2025/
- BO officiel : https://www.education.gouv.fr/le-bulletin-officiel-de-l-education-nationale-de-la-jeunesse-et-des-sports
