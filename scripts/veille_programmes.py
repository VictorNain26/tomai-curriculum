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
        checksum_obj = res.get("checksum") or {}
        checksum = checksum_obj.get("value", "") or _sha256_url(url)
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
    Détecte les arrêtés programme Education dans les JOs récents via PISTE.

    Approche validée (mai 2026) :
      1. lastNJo  → liste des N derniers journaux officiels
      2. jorfCont → structure hiérarchique de chaque JO (tms → liensTxt)
      3. Filtre : sections "Éducation" + "programme" dans le titre du texte

    L'endpoint /search retourne 400 pour fond=JORF — contournement confirmé.

    Nécessite :
      PISTE_CLIENT_ID     → variable d'environnement ou secret GitHub
      PISTE_CLIENT_SECRET → variable d'environnement ou secret GitHub
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
            "-H",
            "Content-Type: application/x-www-form-urlencoded",
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
        token = json.loads(token_result.stdout).get("access_token", "")
    except Exception:
        print("  ✗ Réponse auth PISTE invalide")
        return []

    if not token:
        print("  ✗ Token PISTE vide")
        return []

    def _post_legifrance(endpoint: str, payload: dict) -> dict | None:
        import tempfile as _tmp

        with _tmp.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(payload, f)
            tmp = f.name
        result = subprocess.run(
            [
                "curl",
                "-s",
                "--max-time",
                "20",
                "-H",
                f"Authorization: Bearer {token}",
                "-H",
                "Content-Type: application/json",
                "-H",
                "Accept: application/json",
                "-X",
                "POST",
                "--data",
                f"@{tmp}",
                f"https://api.piste.gouv.fr/dila/legifrance/lf-engine-app/{endpoint}",
            ],
            capture_output=True,
        )
        import os as _os

        _os.unlink(tmp)
        try:
            return json.loads(result.stdout)
        except Exception:
            return None

    def _find_programme_texts(tms_list: list, in_education: bool = False) -> list[dict]:
        found = []
        for node in tms_list:
            titre_node = node.get("titre", "")
            is_edu = (
                in_education or "ducation" in titre_node or "enseignement" in titre_node.lower()
            )
            for lien in node.get("liensTxt", []):
                t = lien.get("titre", "")
                if is_edu and "programme" in t.lower():
                    found.append({"id": lien.get("id", ""), "titre": t})
            found.extend(_find_programme_texts(node.get("tms", []), is_edu))
        return found

    # Identifiants déjà vus pour éviter les doublons
    seen_ids: set[str] = set(state.get("legifrance_seen_jorftext_ids", []))

    # Étape 1 : récupère les 30 derniers JOs
    last_jos = _post_legifrance("consult/lastNJo", {"nbElement": 30})
    if not last_jos:
        print("  ✗ Impossible de récupérer les JOs récents")
        return []

    containers = last_jos.get("containers", [])
    print(f"  → {len(containers)} JOs récents récupérés")

    changes: list[dict] = []
    for c in containers:
        cont_data = _post_legifrance(
            "consult/jorfCont",
            {"highlightActivated": False, "id": c["id"], "pageNumber": 1, "pageSize": 500},
        )
        if not cont_data:
            continue
        for item in cont_data.get("items", []):
            structure = item.get("joCont", {}).get("structure", {}).get("tms", [])
            for text in _find_programme_texts(structure):
                if text["id"] not in seen_ids:
                    seen_ids.add(text["id"])
                    changes.append(
                        {
                            "source": "legifrance",
                            "type": "jorf_programme",
                            "jorftext_id": text["id"],
                            "titre": text["titre"],
                            "jo_titre": c["titre"],
                            "url_legifrance": f"https://www.legifrance.gouv.fr/jorf/id/{text['id']}",
                        }
                    )

    state["legifrance_seen_jorftext_ids"] = list(seen_ids)
    state["legifrance_last_check"] = datetime.now(UTC).strftime("%Y-%m-%d")
    print(f"  → {len(changes)} arrêté(s) programme Education nouveau(x)")
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
                print(f"  [Légifrance] {c.get('jo_titre', '')} | {c['titre'][:70]}")
                print(f"    ID: {c.get('jorftext_id', '?')} | {c['url_legifrance']}")
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
