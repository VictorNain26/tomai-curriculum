#!/usr/bin/env python3
"""
Pipeline RAG — ingestion des programmes officiels Eduscol dans Qdrant v2.

Flux :
  data/raw/*.txt
    → load_source_text()       # extraction section matière par regex
    → chunk_text()              # RecursiveChunker rules markdown + tokenizer Mistral
    → expand_for_niveaux()      # 1 chunk × N niveaux du cycle (duplication payload)
    → validate_chunks()         # Pydantic Chunk → payload Qdrant
    → embed_chunks()            # mistral-embed batch 50 + normalisation L2
    → build_sparse_vectors()    # BM25 indices/values (parité backend rag.service.ts)
    → upsert_to_qdrant()        # named vectors {dense, bm25} + uuid5 idempotent

Usage :
  uv run python scripts/ingest.py                    # ingestion complète
  uv run python scripts/ingest.py --dry-run          # affiche chunks sans upserter
  uv run python scripts/ingest.py --matiere=mathematiques
  uv run python scripts/ingest.py --status           # état collection
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import time
import uuid as _uuid
from pathlib import Path

from dotenv import load_dotenv

from schema import (
    Chunk,
    Matiere,
    NiveauCollege,
    NiveauLycee,
    build_contextual_text,
    derive_niveaux_from_file,
    embed_batch,
    get_qdrant_client,
    to_sparse_vector,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

BASE = Path(__file__).parent.parent
RAW = BASE / "data" / "raw"

COLLECTION = os.environ.get("QDRANT_COLLECTION", "tomai_educational")

# Batch d'upsert : Qdrant Cloud peut timeout sur des payloads >20 MB en une
# seule requête. 200 points × ~5 KB ≈ 1 MB par batch — confortable.
UPSERT_BATCH_SIZE = 200

# ── Sources : fichier → matière + extraction section ─────────────────────────


def _markdown_matiere_sources(
    file: str,
    document_order: list[tuple[Matiere | None, str]],
    *,
    exclude: set[Matiere] | None = None,
) -> list[dict]:
    """
    Génère les SOURCES pour un fichier markdown multi-matières.

    Chaque entrée extrait la section comprise entre `## **Matière**` et le
    `## **MatièreSuivante**` (calculé depuis l'ORDRE RÉEL du document, pour
    que section_end pointe sur la bonne frontière même si une matière est
    exclue de l'extraction).

    Args
    ----
    file : nom du fichier source (sans extension).
    document_order : [(Matiere | None, label), ...] dans l'ordre exact des
        `## **Titre**` markdown. Une matière=None marque une section présente
        dans le doc mais qu'on ne veut pas indexer (sentinelle pour section_end
        seulement).
    exclude : matières listées dans document_order à NE PAS matérialiser
        (typique : version BO obsolète remplacée par un fichier dédié plus
        récent). Conservées dans document_order pour calculer section_end.
    """
    exclude = exclude or set()
    sources = []
    for i, (matiere, label) in enumerate(document_order):
        if matiere is None or matiere in exclude:
            continue
        start = rf"^## \*\*{re.escape(label)}\*\*"
        # section_end = la prochaine entrée du document_order (peu importe
        # qu'elle soit exclue ou non — on veut juste savoir où s'arrête la
        # section courante dans le PDF).
        if i + 1 < len(document_order):
            next_labels = [re.escape(lbl) for _, lbl in document_order[i + 1 :]]
            end: str | None = r"^## \*\*(?:" + "|".join(next_labels) + r")\*\*"
        else:
            end = None
        sources.append(
            {
                "file": file,
                "matiere": matiere,
                "section_pattern": start,
                "section_end": end,
                "blank_line_after_header": False,  # markdown H2 = pas d'ambiguïté TOC
                "section_name": label,
            }
        )
    return sources


# Matières du programme cycle 3 BO 2020 — ordre des `## **Titre**` dans le .md
_CYCLE3_DOCUMENT_ORDER: list[tuple[Matiere | None, str]] = [
    (Matiere.FRANCAIS, "Français"),
    (Matiere.LANGUES_VIVANTES, "Langues vivantes (étrangères ou régionales)"),
    (Matiere.ARTS_PLASTIQUES, "Arts plastiques"),
    (Matiere.EDUCATION_MUSICALE, "Éducation musicale"),
    (Matiere.HISTOIRE_DES_ARTS, "Histoire des arts"),
    (Matiere.EDUCATION_PHYSIQUE_SPORTIVE, "Éducation physique et sportive"),
    (Matiere.EMC, "Enseignement moral et civique"),
    (Matiere.HISTOIRE_GEO, "Histoire et géographie"),
    (Matiere.SCIENCES_TECHNOLOGIE, "Sciences et technologie"),
    (Matiere.MATHEMATIQUES, "Mathématiques"),
]

# Matières du programme cycle 4 BO 2020 — ordre EXACT du document .md
# (utilisé pour calculer section_end). Maths & Techno présents dans la liste
# mais exclus de l'extraction (superseded par programme_maths_cycle4_BO2026 et
# programme_technologie_cycle4_BO2024 — sinon doublon).
_CYCLE4_DOCUMENT_ORDER: list[tuple[Matiere | None, str]] = [
    (Matiere.FRANCAIS, "Français"),
    (Matiere.LANGUES_VIVANTES, "Langues vivantes (étrangères ou régionales)"),
    (Matiere.ARTS_PLASTIQUES, "Arts plastiques"),
    (Matiere.EDUCATION_MUSICALE, "Éducation musicale"),
    (Matiere.HISTOIRE_DES_ARTS, "Histoire des arts"),
    (Matiere.EDUCATION_PHYSIQUE_SPORTIVE, "Éducation physique et sportive"),
    (Matiere.EMC, "Enseignement moral et civique"),
    (Matiere.HISTOIRE_GEO, "Histoire et géographie"),
    (Matiere.PHYSIQUE_CHIMIE, "Physique-Chimie"),
    (Matiere.SVT, "Sciences de la vie et de la Terre"),
    (Matiere.TECHNOLOGIE, "Technologie"),  # exclu, sentinelle section_end
    (Matiere.MATHEMATIQUES, "Mathématiques"),  # exclu, sentinelle section_end
]
_CYCLE4_EXCLUDE: set[Matiere] = {Matiere.TECHNOLOGIE, Matiere.MATHEMATIQUES}


SOURCES: list[dict] = [
    # ── Fichiers mono-matière (tout le fichier — .md préféré au .txt) ──
    {
        "file": "programme_maths_cycle4_BO2026",
        "matiere": Matiere.MATHEMATIQUES,
        "section_pattern": None,
        "section_name": "Mathématiques",
    },
    {
        "file": "programme_technologie_cycle4_BO2024",
        "matiere": Matiere.TECHNOLOGIE,
        "section_pattern": None,
        "section_name": "Technologie",
    },
    {
        "file": "programme_anglais_college_BO2025",
        "matiere": Matiere.ANGLAIS,
        "section_pattern": None,
        "section_name": "Anglais",
    },
    {
        "file": "programme_espagnol_college_BO2025",
        "matiere": Matiere.ESPAGNOL,
        "section_pattern": None,
        "section_name": "Espagnol",
    },
    {
        "file": "programme_allemand_college_BO2025",
        "matiere": Matiere.ALLEMAND,
        "section_pattern": None,
        "section_name": "Allemand",
    },
    {
        "file": "programme_italien_college_BO2025",
        "matiere": Matiere.ITALIEN,
        "section_pattern": None,
        "section_name": "Italien",
    },
    # ── Programmes BO 2020 multi-matières (extraction par H2 markdown) ──
    *_markdown_matiere_sources(
        "programme_cycle4_BO2020",
        _CYCLE4_DOCUMENT_ORDER,
        exclude=_CYCLE4_EXCLUDE,
    ),
    *_markdown_matiere_sources("programme_cycle3_BO2020", _CYCLE3_DOCUMENT_ORDER),
]


# ── Extraction texte ─────────────────────────────────────────────────────────


def extract_section(
    text: str,
    start_pattern: str,
    end_pattern: str | None,
    blank_line_after_header: bool = False,
) -> str:
    """
    Extrait une section entre start_pattern et end_pattern.

    lstrip('\\x0c').rstrip() au lieu de strip() :
    - Retire les form feeds (\\x0c) pdftotext sans toucher les espaces de début
    - Les faux positifs indentés dans les tableaux ne matchent plus
      (ex: "         Histoire" dans une colonne ne matche pas r"^Histoire")

    blank_line_after_header=True : ignore les occurrences du start_pattern qui
    ne sont PAS suivies d'une ligne vide (= entrées de table des matières).
    """
    lines = text.split("\n")
    in_section = False
    section_lines: list[str] = []

    for i, line in enumerate(lines):
        check = line.lstrip("\x0c").rstrip()
        if not in_section:
            if re.match(start_pattern, check):
                if blank_line_after_header:
                    next_check = lines[i + 1].strip() if i + 1 < len(lines) else ""
                    if next_check:
                        continue  # ligne suivante non vide → entrée de TOC
                in_section = True
                section_lines.append(line)
        else:
            if end_pattern and re.match(end_pattern, check):
                break
            section_lines.append(line)

    return "\n".join(section_lines)


def load_source_text(source: dict) -> str:
    """
    Charge et extrait le texte d'une source. Préfère .md (pymupdf4llm — vraies
    sections H2) à .txt (pdftotext — flat). Lève une erreur si section
    introuvable.
    """
    md_path = RAW / f"{source['file']}.md"
    txt_path = RAW / f"{source['file']}.txt"
    if md_path.exists():
        path = md_path
    elif txt_path.exists():
        path = txt_path
    else:
        raise FileNotFoundError(
            f"Aucun fichier source pour {source['file']} (cherché .md puis .txt dans {RAW})"
        )

    # errors='replace' : pdftotext peut produire des octets invalides en UTF-8
    text = path.read_text(encoding="utf-8", errors="replace")

    if source.get("section_pattern"):
        extracted = extract_section(
            text,
            source["section_pattern"],
            source.get("section_end"),
            blank_line_after_header=source.get("blank_line_after_header", False),
        )
        if len(extracted.strip()) < 200:
            raise ValueError(
                f"Section '{source['section_name']}' introuvable dans {path.name} "
                f"(pattern: {source['section_pattern']}). "
                f"Vérifier le formatage du fichier source."
            )
        return extracted.strip()

    return text.strip()


# ── Chunking : RecursiveChunker avec tokenizer Mistral ───────────────────────


_MISTRAL_TOKENIZER = None


def _get_mistral_token_counter():
    """
    Retourne un callable `str -> int` qui compte les vrais tokens Mistral.

    Lazy import + lazy init : mistral_common charge ~500MB de tokenizer state,
    on ne le charge qu'au premier appel du chunker.
    """
    global _MISTRAL_TOKENIZER
    if _MISTRAL_TOKENIZER is None:
        from mistral_common.tokens.tokenizers.mistral import MistralTokenizer

        _MISTRAL_TOKENIZER = MistralTokenizer.v3()

    def counter(text: str) -> int:
        return len(
            _MISTRAL_TOKENIZER.instruct_tokenizer.tokenizer.encode(text, bos=False, eos=False)
        )

    return counter


def chunk_text(text: str, source: dict) -> list[dict]:
    """
    Découpe le texte en chunks avec chonkie RecursiveChunker.

    Règles de découpe en cascade (Chonkie RecursiveRules) :
    1. Titres markdown (`\\n## `, `\\n### `) → garde le titre AVANT le chunk suivant
    2. Paragraphes (`\\n\\n`) → garde la fin du paragraphe à la fin du chunk
    3. Phrases (`. `, `! `, `? `) → fin de phrase à la fin du chunk
    4. Mots (whitespace) → fallback ultime

    chunk_size=400 = 400 tokens Mistral vrais (et non 400 caractères comme avant).
    """
    from chonkie import RecursiveChunker, RecursiveLevel, RecursiveRules

    rules = RecursiveRules(
        levels=[
            RecursiveLevel(delimiters=["\n## ", "\n### "], include_delim="next"),
            RecursiveLevel(delimiters=["\n\n"], include_delim="prev"),
            RecursiveLevel(delimiters=[". ", "! ", "? "], include_delim="prev"),
            RecursiveLevel(whitespace=True),
        ]
    )

    chunker = RecursiveChunker(
        # Chonkie 1.6 : `tokenizer` accepte un Callable[[str], int] via
        # CallableAutoTokenizer. Sûr ici car nos `rules` couvrent tous les niveaux
        # avec delimiters/whitespace — le fallback encode/decode (non implémenté
        # pour callables) n'est jamais déclenché.
        tokenizer=_get_mistral_token_counter(),
        chunk_size=400,  # tokens Mistral vrais
        rules=rules,
        min_characters_per_chunk=100,
    )

    raw_chunks = chunker(text)
    result = []
    for i, c in enumerate(raw_chunks):
        chunk_text_val = c.text.strip()
        if len(chunk_text_val) < 50:
            continue
        result.append(
            {
                "text": chunk_text_val,
                "source_file": source["file"],
                "matiere": source["matiere"].value,
                "section": source["section_name"],
                "chunk_index": i,
            }
        )
    return result


# ── Expansion multi-niveaux ──────────────────────────────────────────────────


def expand_for_niveaux(chunks: list[dict]) -> list[dict]:
    """
    Pour chaque chunk : duplique 1× par niveau du cycle dérivé du fichier source.

    Un même texte (même embed) → N payloads distincts avec niveau différent.
    L'ID Qdrant inclut le niveau pour garantir l'unicité de point.

    Le préfixe contextuel n'inclut PAS le niveau → un seul embed par texte,
    réutilisé pour toutes les variantes de niveau.
    """
    expanded = []
    for chunk in chunks:
        _cycle, niveaux = derive_niveaux_from_file(chunk["source_file"])
        for niveau in niveaux:
            new = dict(chunk)
            new["niveau"] = niveau.value
            expanded.append(new)
    return expanded


# ── Validation Pydantic ──────────────────────────────────────────────────────


def validate_chunks(chunks: list[dict]) -> list[dict]:
    """
    Valide les chunks via Chunk Pydantic, retourne les payloads Qdrant.

    Lève ValidationError au premier échec (pas de silence sur les bugs schema).
    """
    validated = []
    for c in chunks:
        # Cast niveau str → enum (NiveauCollege ou NiveauLycee selon valeur)
        niveau_str = c["niveau"]
        try:
            niveau = NiveauCollege(niveau_str)
        except ValueError:
            niveau = NiveauLycee(niveau_str)

        chunk = Chunk(
            text=c["text"],
            source_file=c["source_file"],
            matiere=Matiere(c["matiere"]),
            niveau=niveau,
            section=c["section"],
            chunk_index=c["chunk_index"],
        )
        validated.append(chunk.to_qdrant_payload())
    return validated


# ── Upsert Qdrant (named vectors + sparse BM25) ──────────────────────────────


def upsert_to_qdrant(payloads: list[dict], dense_vectors: list[list[float]]) -> int:
    """
    Upsert dans la collection v2 (named vectors `dense` + sparse `bm25`).

    - ID stable : uuid5(NAMESPACE_URL, sha256(text + ":" + niveau))
      → idempotent : re-run = pas de doublons, modif text = nouveau point.
    - Sparse vector calculé à partir du texte BRUT (chunk["text"]).
      Doit utiliser la MÊME tokenisation que rag.service.ts:172-193 — d'où
      `schema/bm25.py:to_sparse_vector` partagé.
    """
    from qdrant_client import models

    client = get_qdrant_client()

    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION not in existing:
        raise RuntimeError(
            f"Collection '{COLLECTION}' absente. "
            f"Exécuter d'abord : uv run python scripts/migrate_collection.py"
        )

    points = []
    for payload, dense_vec in zip(payloads, dense_vectors, strict=True):
        text = payload["text"]
        niveau = payload["niveau"]
        matiere = payload["matiere"]

        # ID stable incluant matière + niveau pour distinguer :
        # - les duplications cycle (même texte × N niveaux du cycle)
        # - les textes COMMUNS entre matières (préambules pédagogiques langues
        #   college sont identiques entre EN/ES/DE/IT — sans matière dans
        #   le seed, le dernier upsert écraserait les précédents et seul
        #   le filtre matière=italien retrouverait ces chunks).
        id_seed = f"{matiere}:{niveau}:{text}"
        text_hash = hashlib.sha256(id_seed.encode("utf-8")).hexdigest()
        point_id = str(_uuid.uuid5(_uuid.NAMESPACE_URL, text_hash))

        # Sparse BM25 calculé sur le texte BRUT (cohérent avec query côté backend)
        sparse = to_sparse_vector(text)
        sparse_vec = models.SparseVector(
            indices=sparse.indices,
            values=sparse.values,
        )

        points.append(
            models.PointStruct(
                id=point_id,
                vector={
                    "dense": dense_vec,
                    "bm25": sparse_vec,
                },
                payload=payload,
            )
        )

    # Batch upsert par chunks de UPSERT_BATCH_SIZE points. Sans batching,
    # un payload >20 MB peut faire timeout sur Qdrant Cloud (write op).
    # uuid5 garantit l'idempotence : retry sans craindre les doublons.
    upserted = 0
    for i in range(0, len(points), UPSERT_BATCH_SIZE):
        batch = points[i : i + UPSERT_BATCH_SIZE]
        for attempt in range(3):
            try:
                client.upsert(collection_name=COLLECTION, points=batch, wait=True)
                upserted += len(batch)
                break
            except Exception as e:
                if attempt == 2:
                    raise
                wait = 5 * (2**attempt)  # 5, 10 s
                print(
                    f"  ⚠ upsert batch {i // UPSERT_BATCH_SIZE + 1} fail "
                    f"(essai {attempt + 1}/3) : {e}, retry dans {wait}s"
                )
                time.sleep(wait)
    return upserted


def show_status() -> None:
    """Affiche les statistiques de la collection v2."""
    client = get_qdrant_client()
    try:
        info = client.get_collection(COLLECTION)
        counts = client.count(collection_name=COLLECTION)
        print(f"Collection : {COLLECTION}")
        print(f"  Points   : {counts.count}")
        print(f"  Status   : {info.status}")
        print(f"  Vectors  : {info.config.params.vectors}")
        sparse = getattr(info.config.params, "sparse_vectors", None)
        if sparse:
            print(f"  Sparse   : {sparse}")
    except Exception as e:
        print(f"Collection '{COLLECTION}' introuvable : {e}")


# ── Pipeline principal ───────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Affiche chunks sans upserter")
    parser.add_argument("--matiere", help="Filtre sur une matière (ex: mathematiques)")
    parser.add_argument("--status", action="store_true", help="État collection Qdrant")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    sources = SOURCES
    if args.matiere:
        sources = [s for s in SOURCES if s["matiere"].value == args.matiere]
        if not sources:
            available = sorted({s["matiere"].value for s in SOURCES})
            print(f"Matière '{args.matiere}' inconnue. Disponibles : {available}")
            sys.exit(1)

    total_points = 0
    errors: list[str] = []

    for source in sources:
        print(f"\n▶ {source['section_name']} ({source['matiere'].value})")
        try:
            text = load_source_text(source)
        except (FileNotFoundError, ValueError) as e:
            print(f"  ✗ {e}", file=sys.stderr)
            errors.append(source["matiere"].value)
            continue

        chunks = chunk_text(text, source)
        print(f"  {len(chunks)} chunks bruts")

        expanded = expand_for_niveaux(chunks)
        print(f"  {len(expanded)} chunks après expansion multi-niveaux")

        if args.dry_run:
            for c in expanded[:3]:
                contextual = build_contextual_text(
                    Chunk(
                        text=c["text"],
                        source_file=c["source_file"],
                        matiere=Matiere(c["matiere"]),
                        niveau=NiveauCollege(c["niveau"])
                        if c["niveau"] in {n.value for n in NiveauCollege}
                        else NiveauLycee(c["niveau"]),
                        section=c["section"],
                        chunk_index=c["chunk_index"],
                    )
                )
                print(f"  [{c['chunk_index']}|{c['niveau']}] {contextual[:200]}…")
            continue

        if not expanded:
            errors.append(source["matiere"].value)
            continue

        print("  Validation…", end=" ", flush=True)
        payloads = validate_chunks(expanded)
        print(f"{len(payloads)} valides")

        # Optimisation : embedder UNE fois chaque texte unique, puis broadcaster
        # aux duplications de niveau.
        unique_texts: dict[str, int] = {}
        embed_inputs: list[str] = []
        for p in payloads:
            text = p["text"]
            if text not in unique_texts:
                # Préfixe contextuel SANS niveau (cf. schema/contextual.py)
                chunk_for_prefix = Chunk(
                    text=text,
                    source_file=p["source_file"],
                    matiere=Matiere(p["matiere"]),
                    niveau=NiveauCollege(p["niveau"])
                    if p["niveau"] in {n.value for n in NiveauCollege}
                    else NiveauLycee(p["niveau"]),
                    section=p["section"],
                    chunk_index=p["chunk_index"],
                )
                unique_texts[text] = len(embed_inputs)
                embed_inputs.append(build_contextual_text(chunk_for_prefix))

        print(f"  Embedding ({len(embed_inputs)} textes uniques)…", end=" ", flush=True)
        unique_vectors = embed_batch(embed_inputs)
        print(f"{len(unique_vectors)} vecteurs")

        # Broadcast : chaque payload récupère le vecteur de son texte
        dense_vectors = [unique_vectors[unique_texts[p["text"]]] for p in payloads]

        print(f"  Upsert {len(payloads)} points…", end=" ", flush=True)
        n = upsert_to_qdrant(payloads, dense_vectors)
        print(f"✓ ({n} points dans '{COLLECTION}')")
        total_points += n

    if errors:
        print(f"\n✗ {len(errors)} matière(s) en erreur : {errors}", file=sys.stderr)
        sys.exit(1)

    if not args.dry_run:
        print(f"\nTotal : {total_points} points upsertés")
        show_status()


if __name__ == "__main__":
    main()
