#!/usr/bin/env python3
"""
Veille automatique des programmes officiels Éduscol.

Deux sources :
  A) data.gouv.fr dataset "programmes-enseignement-second-degre"
     → détecte les mises à jour du dataset officiel (rafraîchi ~trimestriellement)
  B) Légifrance PISTE API (optionnel, si PISTE_CLIENT_ID + PISTE_CLIENT_SECRET définis)
     → détecte tous les arrêtés MENE* dès leur publication au JO

Sortie :
  - stdout : rapport lisible
  - data/raw/.veille_changes.json : liste de changements (lu par le GitHub Action)
  - data/raw/.veille_state.json  : état mémorisé entre deux runs

Usage :
  uv run python scripts/veille_programmes.py
  uv run python scripts/veille_programmes.py --force   # ignore état mémorisé
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).parent.parent
RAW = BASE / "data" / "raw"
STATE_FILE = RAW / ".veille_state.json"
CHANGES_FILE = RAW / ".veille_changes.json"

DATAGOUV_DATASET_ID = "programmes-denseignement-du-second-degre"
DATAGOUV_API = f"https://www.data.gouv.fr/api/1/datasets/{DATAGOUV_DATASET_ID}/"

# Niveaux qui nous intéressent (collège + lycée complet pour Phase H)
TARGET_NIVEAUX = {
    "Cycle 3",
    "Cycle 4",
    "Collège",
    "Seconde générale et technologique",
    "Première générale",
    "Terminale générale",
}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _curl_json(url: str, timeout: int = 20) -> dict | None:
    result = subprocess.run(
        ["curl", "-s", "--max-time", str(timeout), "-L", "-H", "Accept: application/json", url],
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _download_pdf(url: str, dest: Path, timeout: int = 30) -> bool:
    result = subprocess.run(
        ["curl", "-s", "--max-time", str(timeout), "-L", "-o", str(dest), url],
        capture_output=True,
    )
    if result.returncode != 0 or not dest.exists():
        return False
    with open(dest, "rb") as f:
        return f.read(5) == b"%PDF-"


def _pdftotext(pdf: Path) -> Path | None:
    txt = pdf.with_suffix(".txt")
    result = subprocess.run(
        ["pdftotext", "-enc", "UTF-8", "-layout", str(pdf), str(txt)],
        capture_output=True,
    )
    return txt if result.returncode == 0 and txt.exists() else None


def _sha256_url(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_check": None, "dataset_last_modified": None, "known_resource_hashes": {}}


def _save_state(state: dict) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Source A : data.gouv.fr ───────────────────────────────────────────────────


def check_datagouv(state: dict, force: bool) -> list[dict]:
    """Détecte les nouvelles ressources PDF dans le dataset data.gouv.fr."""
    print("▶ Source A — data.gouv.fr API")
    meta = _curl_json(DATAGOUV_API)
    if not meta:
        print("  ✗ Impossible de joindre data.gouv.fr")
        return []

    last_modified = meta.get("last_modified") or meta.get("metadata_modified", "")
    print(f"  Dataset last_modified : {last_modified}")

    if not force and last_modified == state.get("dataset_last_modified"):
        print("  ✓ Pas de changement depuis le dernier run")
        return []

    print("  → Changement détecté, analyse des ressources…")
    resources = meta.get("resources", [])
    changes: list[dict] = []
    known = state.get("known_resource_hashes", {})

    for res in resources:
        url = res.get("url", "")
        title = res.get("title", "")
        checksum = res.get("checksum", {}).get("value", "") or _sha256_url(url)
        res_id = res.get("id", _sha256_url(url))

        if res_id in known and known[res_id] == checksum and not force:
            continue  # déjà connu, pas changé

        # Nouvelle ressource ou checksum différent
        changes.append(
            {
                "source": "datagouv",
                "type": "dataset_resource",
                "title": title,
                "url": url,
                "checksum": checksum,
                "resource_id": res_id,
                "dataset_last_modified": last_modified,
            }
        )
        known[res_id] = checksum

    state["dataset_last_modified"] = last_modified
    state["known_resource_hashes"] = known
    print(f"  → {len(changes)} ressource(s) nouvelle(s) ou modifiée(s)")
    return changes


# ── Source B : Légifrance PISTE API (optionnel) ───────────────────────────────


def check_legifrance(state: dict) -> list[dict]:
    """
    Détecte les nouveaux arrêtés MENE* via l'API Légifrance PISTE.

    Nécessite :
      PISTE_CLIENT_ID     → variable d'environnement ou secret GitHub
      PISTE_CLIENT_SECRET → variable d'environnement ou secret GitHub

    Documentation officielle : https://piste.gouv.fr/
    Endpoint auth   : https://oauth.piste.gouv.fr/api/oauth/token
    Endpoint search : https://api.piste.gouv.fr/dila/legifrance/lf-engine-app/search
    """
    client_id = os.environ.get("PISTE_CLIENT_ID", "")
    client_secret = os.environ.get("PISTE_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        print("▶ Source B — Légifrance PISTE : non configuré (PISTE_CLIENT_ID manquant)")
        print("  → Créez un compte sur https://piste.gouv.fr et ajoutez les secrets GitHub")
        return []

    print("▶ Source B — Légifrance PISTE API")

    # Auth OAuth2 Client Credentials
    grant = (
        f"grant_type=client_credentials&client_id={client_id}"
        f"&client_secret={client_secret}&scope=openid"
    )
    token_result = subprocess.run(
        [
            "curl",
            "-s",
            "--max-time",
            "15",
            "-X",
            "POST",
            "https://oauth.piste.gouv.fr/api/oauth/token",
            "-d",
            grant,
        ],
        capture_output=True,
    )
    if token_result.returncode != 0:
        print("  ✗ Échec auth PISTE")
        return []

    try:
        token_data = json.loads(token_result.stdout)
        token = token_data.get("access_token", "")
    except Exception:
        print("  ✗ Réponse auth PISTE invalide")
        return []

    if not token:
        print("  ✗ Token PISTE vide")
        return []

    # Recherche arrêtés récents avec code NOR MENE* contenant "programme"
    last_check = state.get("legifrance_last_check") or "2025-01-01"
    search_payload = json.dumps(
        {
            "recherche": {
                "champs": [
                    {
                        "typeChamp": "NOR",
                        "criteres": [{"typeRecherche": "CONTIENT", "valeur": "MENE"}],
                    },
                    {
                        "typeChamp": "TITRE",
                        "criteres": [{"typeRecherche": "CONTIENT", "valeur": "programme"}],
                    },
                ],
                "filtres": [
                    {"facette": "DATE_VERSION", "valeur": last_check, "operateur": "GREATER"},
                    {"facette": "NATURE", "valeur": "ARRETE"},
                ],
                "pageNumber": 1,
                "pageSize": 20,
                "sort": "PERTINENCE",
                "typePagination": "DEFAUT",
            }
        }
    )

    search_result = subprocess.run(
        [
            "curl",
            "-s",
            "--max-time",
            "20",
            "-X",
            "POST",
            "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app/search",
            "-H",
            f"Authorization: Bearer {token}",
            "-H",
            "Content-Type: application/json",
            "-d",
            search_payload,
        ],
        capture_output=True,
    )

    try:
        data = json.loads(search_result.stdout)
        results = data.get("results", [])
    except Exception:
        print("  ✗ Réponse recherche PISTE invalide")
        return []

    state["legifrance_last_check"] = datetime.now(UTC).strftime("%Y-%m-%d")

    changes = []
    for item in results:
        nor = item.get("nor", "")
        titre = item.get("titre", "")
        date_pub = item.get("datePublicationJO", "")
        lien = f"https://www.legifrance.gouv.fr/jorf/id/{item.get('id', '')}"
        changes.append(
            {
                "source": "legifrance",
                "type": "arrete",
                "nor": nor,
                "titre": titre,
                "date_publication": date_pub,
                "url_legifrance": lien,
            }
        )

    print(f"  → {len(changes)} arrêté(s) MENE* 'programme' trouvé(s) depuis {last_check}")
    return changes


# ── Téléchargement des PDFs détectés ─────────────────────────────────────────


def download_changes(changes: list[dict]) -> list[dict]:
    """Pour chaque changement avec URL PDF, tente de télécharger et extraire."""
    for change in changes:
        url = change.get("url", "")
        if not url or not url.endswith(".pdf"):
            continue
        if "cache.media.education.gouv.fr" not in url:
            continue

        fname = url.split("/")[-1]
        dest_pdf = RAW / fname
        dest_txt = dest_pdf.with_suffix(".txt")

        if dest_txt.exists():
            change["local_txt"] = str(dest_txt)
            continue

        print(f"  ↓ Téléchargement : {fname}")
        if _download_pdf(url, dest_pdf):
            txt = _pdftotext(dest_pdf)
            if txt:
                change["local_txt"] = str(txt)
                print(f"    ✓ Extrait : {txt.name} ({txt.stat().st_size // 1024} Ko)")
            else:
                print("    ✗ pdftotext échoué")
        else:
            print("    ✗ Téléchargement échoué")

    return changes


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="Ignore l'état mémorisé et retraite tout"
    )
    args = parser.parse_args()

    print(f"{'=' * 60}")
    print(f"VEILLE PROGRAMMES ÉDUSCOL — {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'=' * 60}\n")

    state = _load_state()
    all_changes: list[dict] = []

    all_changes += check_datagouv(state, force=args.force)
    print()
    all_changes += check_legifrance(state)
    print()

    if all_changes:
        print(f"{'=' * 60}")
        print(f"CHANGEMENTS DÉTECTÉS : {len(all_changes)}")
        print(f"{'=' * 60}")
        download_changes(all_changes)
        for c in all_changes:
            if c["source"] == "datagouv":
                print(f"  [data.gouv.fr] {c['title'] or '(sans titre)'}")
                print(f"    URL : {c['url']}")
            else:
                print(f"  [Légifrance] {c['nor']} — {c['titre']}")
                print(f"    Publié : {c['date_publication']} | {c['url_legifrance']}")
    else:
        print("✓ Aucun changement détecté.")

    # Sauvegarde état + fichier changes pour le GitHub Action
    state["last_check"] = datetime.now(UTC).isoformat()
    _save_state(state)

    CHANGES_FILE.write_text(json.dumps(all_changes, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nÉtat sauvegardé : {STATE_FILE.name}")
    print(f"Changements exportés : {CHANGES_FILE.name} ({len(all_changes)} entrée(s))")


if __name__ == "__main__":
    main()
