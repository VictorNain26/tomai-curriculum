# Audit Mathématiques 5e — `PROGRAMME_5EME.md` actuel vs BO 5 mars 2026

> **Date** : 2026-05-11
> **Source officielle** : Arrêté du 18 février 2026, publié au BO n°10 du 5 mars 2026. Applicable à la classe de cinquième à la rentrée 2026-2027.
> **Légifrance** : https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000053613385
> **BO en ligne** : https://www.education.gouv.fr/bo/2026/Hebdo10/MENE2602912A
> **PDF Annexe 2 (programme maths cycle 4)** : sauvegardé dans `data/raw/programme_maths_cycle4_BO2026.txt`

## 1. Verdict

`PROGRAMME_5EME.md` ne reflète **PAS** le programme officiel mai 2026. La section Mathématiques a été produite par Claude antérieur (commit `0479f2f` du 21/01/2026) sans validation contre la source canonique. Conséquence : couverture de 46.2% mesurée par `audit_coverage.py` partiellement faussée.

**Estimation après réécriture** : la section Mathématiques actuelle a ~50% de chapitres officiels manquants + ~15% de chapitres en trop ou mal placés. Réécriture complète nécessaire.

## 2. Structure officielle vs structure actuelle

| BO 5 mars 2026 (officiel) | `PROGRAMME_5EME.md` actuel | Conclusion |
|--|--|--|
| Nombres et calculs | Nombres et Calculs | ✅ Aligné |
| Espace et géométrie | Géométrie | ⚠️ Renommer + intégrer "représentation de l'espace" |
| Organisation et gestion de données et probabilités | Organisation et Gestion de Données | ⚠️ Renommer |
| **Proportionnalité, fonctions** | (mélangé dans "Organisation et Gestion de Données") | ❌ **Section absente** à créer |
| La pensée informatique | Algorithmique et Programmation | ⚠️ Renommer |
| (absent) | **Grandeurs et Mesures** | ❌ **Section inventée**, à supprimer et redistribuer |

## 3. Détail par section

### 3.1 Nombres et calculs

**Officiel BO 5 mars 2026 (5 sous-thèmes pour la 5e)** :
1. Opérations (divisibilité 2/5/10/3/9, division euclidienne, multiples/diviseurs, distributivité, priorités, diviser par décimal)
2. Nombres relatifs (définition, opposé, valeur absolue, positif/négatif strict, abscisse, comparer, additionner/soustraire avec parenthèses)
3. Nombres rationnels (comparer fractions, additionner/soustraire dénominateurs quelconques)
4. **Puissances** (carré, cube, carrés entiers 0-12, cube de 10, calcul d'expressions)
5. Calcul littéral et algébrique (formules, substitution, factoriser/développer simples, réduire, **équations a·x=c et x+b=c par méthodes arithmétiques**)

**Manquants dans MD actuel** :
- ❌ **Puissances** (chapitre 5e entier, complètement absent)
- ❌ **Équations simples** (a·x=c, x+b=c)
- ❌ **Diviser par un nombre décimal**
- ❌ **Critères divisibilité par 3 et 9**
- ❌ **Valeur absolue, opposé** d'un nombre relatif

**En trop / mal qualifié** :
- ⚠️ "Nombres premiers (introduction)" — c'est un **prolongement possible**, pas chapitre obligatoire
- ⚠️ "Comparaison de fractions (même dénominateur)" — dénominateurs **quelconques** attendus en 5e

### 3.2 Espace et géométrie

**Officiel BO 5 mars 2026 (6 sous-thèmes 5e)** :
1. Repérage sur une droite et dans le plan (abscisse, repère orthogonal, coordonnées)
2. Représentation de l'espace (perspective cavalière pavé/cube/cylindre/prisme, patrons, **volumes cube/pavé/prisme**, **aire disque, volume cylindre**)
3. Transformations (demi-tour / symétrie centrale)
4. Angles (caractériser parallélisme par angles alternes internes et correspondants)
5. Triangles (somme des angles + démonstration, médiatrices, cercle circonscrit, **aire triangle**, hauteurs, médianes)
6. Parallélogrammes (propriétés diagonales/côtés, parallélogrammes particuliers, **aire parallélogramme**)

**Manquants dans MD actuel** :
- ❌ **Repérage sur une droite et dans le plan** (coordonnées, repère orthogonal)
- ❌ **Représentation de l'espace** (perspective cavalière, patrons)
- ❌ **Aires (triangle, parallélogramme, disque)** — explicites dans le BO 5e
- ❌ **Volumes (cube, pavé, prisme, cylindre)** — explicites dans le BO 5e
- ❌ **Hauteurs et médianes du triangle**

**En trop** :
- ⚠️ "Symétrie axiale (rappels)" — vue cycle 3, pas chapitre 5e indépendant

### 3.3 Organisation et gestion de données et probabilités

**Officiel BO 5 mars 2026 (2 sous-thèmes 5e)** :
1. Statistiques (recueillir/organiser données, effectifs et fréquences décimale/fractionnaire/pourcentage, tableaux/diagrammes/graphiques, **moyenne simple**)
2. Probabilités (vocabulaire : expérience aléatoire / issue / évènement, équiprobabilité, répéter expérience)

**Au MD actuel mais hors 5e** :
- ❌ **Médiane** (Statistiques) — chapitre **4e** dans le BO, pas 5e

### 3.4 Proportionnalité, fonctions (SECTION ABSENTE DU MD)

**Officiel BO 5 mars 2026 (2 sous-thèmes 5e)** :
1. **Proportionnalité** (proportions, pourcentages, coefficient, situations concrètes prix/recettes/distances/échelles, tableau/graphique, nuage de points)
2. **Fonctions** (5e !) (expression "en fonction de", tableaux de valeurs, placer points dans repère, lire graphique cartésien, traduire dépendance, formule simple, caractériser proportionnalité graphiquement)

**Constat critique** : la section "Proportionnalité, fonctions" n'existe pas comme telle dans le MD. Les éléments de proportionnalité sont dilués dans "Organisation et Gestion de Données" et **toute la partie Fonctions (chapitre 5e à part entière) est absente**.

### 3.5 La pensée informatique

**Officiel BO 5 mars 2026 (5e)** :
- Manipuler instructions simples et les séquencer
- Identifier entrées/sorties d'un programme
- Représenter formules en programmation par blocs
- Calculer valeur de formules
- Prévoir valeur d'expression
- Analyser et modifier programme simple
- **Boucle inconditionnelle simple** (répéter N fois)
- Variable : **uniquement en lecture** d'une donnée saisie (manipulation en écriture = 4e)

**MD actuel — 3 items** :
- "Scratch (bases)" → ✅ couvert (langage par blocs)
- "Variables et boucles" → ⚠️ formulation ambiguë, variable en écriture est en 4e
- "Instructions conditionnelles" → ❌ **chapitre 4e**, pas 5e

### 3.6 Section inventée à supprimer

**MD actuel — "Grandeurs et Mesures"** (6 items) :
- Périmètres / Aires / Unités / Volumes / Unités de volume / Durées

**Constat** : ce thème n'existe **pas comme section indépendante** dans le programme cycle 4 (ni BO 30/07/2020 ni BO 5 mars 2026). Tout est intégré ailleurs (Espace et géométrie pour les aires/volumes/conversions). "Durées (calculs)" n'apparait nulle part dans le programme maths cycle 4 — il est en cycle 3 (CM1-CM2) ou hors champ maths.

**Action** : supprimer cette section, redistribuer aires/volumes/conversions dans Espace et géométrie.

## 4. Conséquence sur les 288 docs JSONL

L'audit du MD a révélé des chapitres manquants et en trop. Les **docs JSONL existants** ont probablement été produits **selon le MD actuel** (même session Claude). Donc :

- Les docs sur Puissances/Équations simples/Fonctions 5e/Repère orthogonal → **probablement inexistants** dans le dataset
- Les docs sur "Médiane" en 5e → **probablement existent mais hors programme** (à déplacer en 4e ou supprimer)
- Les docs sur "Instructions conditionnelles" en 5e → idem
- Les docs sur "Durées" → idem
- Les docs sur "Symétrie axiale" en 5e → probablement marqués 5e à tort

**À faire en Phase E (production contenu)** :
1. Identifier les docs JSONL mal classifiés (recherche par titres correspondants aux chapitres en trop)
2. Soit les déplacer (4e/3e quand pertinent), soit les supprimer
3. Produire les docs manquants pour les ~10 chapitres officiels absents
4. Audit factualité du contenu sur sample stratifié (Phase E aussi)

## 5. Prochaines étapes

### Cette session
- [x] Rédaction de cet audit
- [x] Réécriture de la section Mathématiques de `PROGRAMME_5EME.md` à partir du BO officiel
- [x] Ajout header `source_bo` / `last_verified` à `PROGRAMME_5EME.md` (cf. ADR-0005 Couche 3)

### Sessions suivantes (1 par matière)
- [ ] Français : récupérer BO français cycle 4 + audit similaire
- [ ] Histoire-Géographie : BO commun (à identifier précisément, programme 5e + EMC inclus)
- [ ] Physique-Chimie : BO PC cycle 4
- [ ] SVT : BO SVT cycle 4
- [ ] EMC : BO 13/06/2024 (séparé)
- [ ] Technologie : BO 29/02/2024 (programme 2024 spécifique)
- [ ] Anglais, Allemand, Espagnol, Italien : CECRL niveau attendu 5e (A2 visé) + programmes langues vivantes

## 6. Méthode reproductible

```bash
# 1. Identifier le BO officiel pour la matière + cycle ciblé
# 2. Trouver l'URL du PDF Annexe (ex. annexe par matière du BO n°X)
# 3. Télécharger
curl -o data/raw/programme_<matiere>_<cycle>_BO<year>.pdf <url>

# 4. Extraire en texte UTF-8
pdftotext -enc UTF-8 -layout <pdf> data/raw/programme_<matiere>_<cycle>_BO<year>.txt

# 5. Lire les sections "Cinquième" du texte extrait
# 6. Comparer chapitre par chapitre avec PROGRAMME_5EME.md section <matière>
# 7. Lister manques / prolongements / hors-niveau / inventions
# 8. Rédiger audit dans docs/audits/<date>-audit-<matiere>-<niveau>-vs-BO<year>.md
# 9. Réécrire section correspondante de PROGRAMME_5EME.md à partir du BO officiel
```

## 7. Source canonique

Le texte officiel complet du programme maths cycle 4 BO 5 mars 2026 est sauvegardé dans `data/raw/programme_maths_cycle4_BO2026.txt` pour référence. Ce fichier est la **source de vérité** ; si on doit re-vérifier ou re-générer la section maths du `PROGRAMME_5EME.md`, on repart de là.

URLs canoniques :
- Arrêté Légifrance : https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000053613385
- BO en ligne : https://www.education.gouv.fr/bo/2026/Hebdo10/MENE2602912A
- PDF Annexe 2 : https://www.education.gouv.fr/sites/default/files/document/Annexe%202%20%E2%80%93%20Programme%20de%20math%C3%A9matiques%20pour%20le%20cycle%204-480716.pdf
