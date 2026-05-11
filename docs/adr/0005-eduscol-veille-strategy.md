# ADR-0005 — Stratégie de veille programmes Éduscol

- **Date** : 2026-05-11
- **Statut** : accepté, implémentation Phase G
- **Spec source** : [`docs/specs/2026-05-11-mvp-rebuild-plan.md`](../specs/2026-05-11-mvp-rebuild-plan.md)

## Contexte

Les programmes officiels de l'Éducation Nationale **changent régulièrement** (réformes cycliques, MAJ matières, modifications horaires). Le dataset Tom doit refléter le programme en vigueur, sinon il fournit du contenu obsolète aux élèves. Recherche du 2026-05-11 :

- **Pas d'API structurée** pour les programmes : Éduscol publie en PDF/HTML uniquement (`https://eduscol.education.gouv.fr/`)
- **API existante mais hors scope** : data.education.gouv.fr a des datasets (calendrier, annuaire, statistiques) mais pas les programmes
- **Flux RSS du BO existe** : `https://www.education.gouv.fr/le-bulletin-officiel-de-l-education-nationale-de-la-jeunesse-et-des-sports` publie chaque hebdo
- **Légifrance API** : publie les arrêtés ministériels (code MENE* = Ministère Éducation Enseignement Scolaire) en JSON
- **Réforme en cours** : nouveaux programmes maths/français cycle 3 publiés avril 2025 (arrêté 10/04/2025), applicables CM1+6ème en 2025-2026, CM2 en 2026-2027

Sans mécanisme de veille → dataset rotira mécaniquement à chaque MAJ programme.

## Décision

**Veille à 4 couches**, pragmatique avant tout :

### Couche 1 — GitHub Action mensuelle de scrape RSS BO

`.github/workflows/eduscol-watch.yml` (Phase G) :
- Cron mensuel
- Fetch RSS BO (`https://www.education.gouv.fr/cid<X>/le-bulletin-officiel-de-l-education-nationale-de-la-jeunesse-et-des-sports.html`)
- Filter par keywords : `programme`, `enseignement`, `cycle`, `lycée`, `arrêté`
- Si match nouveau → crée un **GitHub Issue** "Veille BO : nouveau programme détecté" avec lien

### Couche 2 — Cross-check Légifrance API (semestriel)

API Légifrance (https://api.gouv.fr/les-api/legifrance-api) :
- Search query : `programme enseignement` filtré par code MENE*
- Retourne JSON des arrêtés (titre, date, contenu structuré)
- Tâche manuelle semestrielle : vérifier les MENE* récents et comparer avec nos `PROGRAMME_*.md`

### Couche 3 — Versioning local dans les `PROGRAMME_*.md`

Header strict en tête de chaque fichier :

```markdown
---
source_bo: "BO 30/07/2020"
source_url: "https://www.education.gouv.fr/bo/..."
last_verified: "2026-05-11"
last_verified_by: "humain"  # ou "ci"
content_sha256: "<hash du contenu hors front-matter>"
---
```

CI check : compare `content_sha256` actuel avec celui du fichier → détecte drift par modification accidentelle.

### Couche 4 — Calendrier d'anticipation

`docs/programmes/CALENDRIER_REFORMES.md` : liste les MAJ programmes officiellement annoncées (ex. réforme cycle 3 2025-2028). Anticipation des MAJ dataset.

## Conséquences

### Positives
- Aucune surprise lors d'une réforme : détectée par RSS dans le mois
- Pas de scraping fragile (RSS officiel, format stable)
- Coût opérationnel : 0 (GitHub Action gratuite) + ~30min/semestre pour cross-check Légifrance
- Tom reste aligné Éduscol par construction, pas par chance

### Négatives
- **Action humaine requise** pour mettre à jour les `PROGRAMME_*.md` quand un BO est détecté (la veille notifie, ne corrige pas)
- **Délai** : entre publication du BO et notre MAJ, jusqu'à 1 mois (cron mensuel) — acceptable pour un projet éducatif (les réformes prennent effet à la rentrée suivante, soit plusieurs mois plus tard)

## Alternatives considérées

- **Scraping HTML/PDF auto-différentiel** : trop fragile (changements de structure HTML cassent le scraper)
- **Subscription manuelle aux newsletters Éduscol** : pas de notification machine
- **Crowdsourcing communautaire** (ex. Sésamath) : pas de format structuré ni de garantie de fraîcheur
- **API ministère privée** : n'existe pas

## Validation prévue

Phase G (post-MVP validé) :
- [ ] Workflow GitHub Action implémenté + testé
- [ ] Cross-check Légifrance documenté en runbook ops
- [ ] Header front-matter ajouté à `PROGRAMME_5EME.md` en exemple
- [ ] CALENDRIER_REFORMES.md initialisé avec les réformes connues 2025-2028

## Référence

- BO en ligne : https://www.education.gouv.fr/le-bulletin-officiel-de-l-education-nationale-de-la-jeunesse-et-des-sports
- Légifrance API : https://api.gouv.fr/les-api/legifrance-api
- Calendrier des réformes : `docs/programmes/CALENDRIER_REFORMES.md`
