"""
Étapes de transformation du pipeline d'ingestion (sans Qdrant/Mistral réseau).

Logique pure et testable unitairement :
  load_source_text()   # extraction section matière par regex (.md préféré)
  chunk_text()         # RecursiveChunker chonkie + tokenizer Mistral vrais tokens
  expand_for_niveaux() # 1 chunk × N niveaux du cycle (duplication payload)
  validate_chunks()    # Pydantic Chunk → payload Qdrant

Séparé de `ingest.py` (upsert + CLI) pour garder chaque fichier sous 400 lignes.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from schema import (
    Chunk,
    Matiere,
    NiveauCollege,
    NiveauLycee,
    derive_niveaux_from_file,
)

BASE = Path(__file__).parent.parent
RAW = BASE / "data" / "raw"


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


def _get_mistral_token_counter() -> Callable[[str], int]:
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
    result: list[dict] = []
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
    expanded: list[dict] = []
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
    validated: list[dict] = []
    for c in chunks:
        # Cast niveau str → enum (NiveauCollege ou NiveauLycee selon valeur)
        niveau_str = c["niveau"]
        try:
            niveau: NiveauCollege | NiveauLycee = NiveauCollege(niveau_str)
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
