# ADR-0002 — Archive immortelle de l'état pre-MVP

- **Date** : 2026-05-11
- **Statut** : accepté, appliqué
- **Spec source** : [`docs/specs/2026-05-11-mvp-rebuild-plan.md`](../specs/2026-05-11-mvp-rebuild-plan.md)

## Contexte

La refonte radicale MVP-5ème supprime ~100 fichiers (autres niveaux, scripts custom inventés, rapports historiques, programmes hors 5ème). Représente ~200h de travail manuel cumulé. Risque de perte irréversible si suppression sans archive.

## Décision

Archiver l'état pré-refonte via **2 mécanismes git redondants** :

1. **Tag git annoté** `archive/v1.0-pre-mvp` sur le commit `7bb4425` (HEAD main au 2026-05-11)
2. **Branche** `archive/pre-mvp-refonte` qui pointe au même commit

Le tag immortalise la référence ; la branche permet le browse via GitHub UI sans manipulation de tag. Les deux sont poussés sur `origin`.

## Récupération sélective post-archive

```bash
# Lister le contenu archivé
git ls-tree -r archive/v1.0-pre-mvp -- data/processed/

# Cherry-pick d'un fichier précis
git checkout archive/pre-mvp-refonte -- docs/programmes/PROGRAMME_6EME.md

# Diff entre archive et MVP
git diff archive/v1.0-pre-mvp..main -- data/processed/
```

## Conséquences

### Positives
- Aucune perte de travail antérieur (200h de curation manuelle préservée)
- Récupération chirurgicale possible (un dossier, un fichier, un commit)
- Référence permanente pour comparaison "ce qu'on avait" vs "ce qu'on construit"
- Phase H (duplication aux autres niveaux) pourra restaurer le contenu pertinent via cherry-pick

### Négatives
- Aucune. Coût stockage négligeable.

## Alternatives considérées

- **Branche orpheline avec snapshot** : moins propre, casse le DAG git.
- **Backup externe (S3, etc.)** : redondant avec git, complique le workflow.
- **Suppression effective sans archive** : refusé, perte irréversible.

## Référence

- Tag : https://github.com/VictorNain26/tomai-curriculum/releases/tag/archive/v1.0-pre-mvp
- Branche : https://github.com/VictorNain26/tomai-curriculum/tree/archive/pre-mvp-refonte
