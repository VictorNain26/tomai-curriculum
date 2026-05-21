# Sources officielles des programmes scolaires

Fichiers `.txt` extraits avec `pdftotext -enc UTF-8 -layout`.  
PDFs exclus du repo git (`.gitignore`), `.txt` seuls versionnés.  
PDFs régénérables via les URLs ci-dessous.

## Cycle 3 (CM1-CM2-6ème)

| Fichier | Date BO | URL |
|---------|---------|-----|
| `programme_cycle3_BO2020.txt` | 30/07/2020 | `https://cache.media.education.gouv.fr/file/31/88/7/ensel714_annexe2_1312887.pdf` |

## Cycle 4 (5ème-4ème-3ème)

| Fichier | Date BO | URL |
|---------|---------|-----|
| `programme_cycle4_BO2020.txt` | 30/07/2020 | `https://cache.media.education.gouv.fr/file/31/89/1/ensel714_annexe3_1312891.pdf` |
| `programme_maths_cycle4_BO2026.txt` | 05/03/2026 | `https://www.education.gouv.fr/sites/default/files/document/Annexe%202%20%E2%80%93%20Programme%20de%20math%C3%A9matiques%20pour%20le%20cycle%204-480716.pdf` |
| `programme_technologie_cycle4_BO2024.txt` | 29/02/2024 | `https://www.education.gouv.fr/sites/default/files/document/Annexe%20%E2%80%94%20Programme%20de%20technologie%20du%20cycle%204-368016.pdf` |

## Langues vivantes — Collège (BO n°22 du 29 mai 2025)

Arrêté du 5 mai 2025, NOR MENE2504621A. Applicable 5e à rentrée 2026-2027.  
Source : mirror reforme.education (education.gouv.fr bloque curl via Cloudflare).

| Fichier | Langue | URL |
|---------|--------|-----|
| `programme_anglais_college_BO2025.txt` | Anglais | `https://reforme.education/app/uploads/2025/05/prog-college-anglais.pdf` |
| `programme_espagnol_college_BO2025.txt` | Espagnol | `https://reforme.education/app/uploads/2025/05/prog-college-espagnol.pdf` |
| `programme_allemand_college_BO2025.txt` | Allemand | `https://reforme.education/app/uploads/2025/05/prog-college-allemand.pdf` |
| `programme_italien_college_BO2025.txt` | Italien | `https://reforme.education/app/uploads/2025/05/prog-college-italien.pdf` |

## Dataset data.gouv.fr

| Fichier | URL | Mis à jour |
|---------|-----|------------|
| `programmes_second_degre_datagouv.json` | `https://www.data.gouv.fr/api/1/datasets/programmes-denseignement-du-second-degre/` | 02/02/2026 |

## Veille automatique (Légifrance PISTE)

Générés par `scripts/veille_programmes.py` (GitHub Action hebdomadaire) :
- `.veille_state.json` : IDs JOs déjà vus, date dernier check
- `.veille_changes.json` : arrêtés programme détectés au dernier run

Credentials → GitHub Secrets `PISTE_CLIENT_ID` / `PISTE_CLIENT_SECRET`.

## Régénération des PDFs

```bash
# Cycle 3/4 (cache.media, pas de Cloudflare)
curl -L -o data/raw/programme_cycle3_BO2020.pdf \
  "https://cache.media.education.gouv.fr/file/31/88/7/ensel714_annexe2_1312887.pdf"
curl -L -o data/raw/programme_cycle4_BO2020.pdf \
  "https://cache.media.education.gouv.fr/file/31/89/1/ensel714_annexe3_1312891.pdf"

# Maths/Techno (education.gouv.fr/sites)
curl -L -o data/raw/programme_maths_cycle4_BO2026.pdf \
  "https://www.education.gouv.fr/sites/default/files/document/Annexe%202%20%E2%80%93%20Programme%20de%20math%C3%A9matiques%20pour%20le%20cycle%204-480716.pdf"
curl -L -o data/raw/programme_technologie_cycle4_BO2024.pdf \
  "https://www.education.gouv.fr/sites/default/files/document/Annexe%20%E2%80%94%20Programme%20de%20technologie%20du%20cycle%204-368016.pdf"

# LVE (mirror)
for lang in anglais espagnol allemand italien; do
  curl -L -o "data/raw/programme_${lang}_college_BO2025.pdf" \
    "https://reforme.education/app/uploads/2025/05/prog-college-${lang}.pdf"
done

# Extraction texte
for pdf in data/raw/*.pdf; do
  pdftotext -enc UTF-8 -layout "$pdf" "${pdf%.pdf}.txt"
done
```
