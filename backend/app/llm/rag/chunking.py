"""Character-window chunking with boundary snapping. No semantic chunking in v1.

Two rules drive the whole design:

1. **A chunk never spans a page break.** Each page is chunked on its own, so every chunk
   carries the exact `page_no` a citation can point at. The cost is that a sentence running
   across a page break becomes two partial chunks; the benefit is that no citation is a guess.
2. **A chunk never ends mid-word.** The window end is pulled back to the nearest paragraph,
   sentence, line or word boundary, and the overlap start is pulled back the same way.

`chunk_size=800` / `chunk_overlap=100` are frozen until Phase 6 (CLAUDE.md 5.3).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.core.config import PipelineConfig
from app.llm.rag.loaders import Page

# A sentence terminator followed by whitespace. Requiring the whitespace is what keeps
# "6.3. Trong thời gian" from being cut inside the clause number "6.3" — that dot has no
# space after it, while the one ending the numbering does.
_SENTENCE_END = re.compile(r"[.!?…:;]\s")

# How far back from the ideal end the search for a boundary is allowed to reach. A quarter of
# the window: far enough to find a sentence end in normal prose, near enough that chunks stay
# roughly the configured size.
_LOOKBACK_RATIO = 4


@dataclass(frozen=True)
class TextChunk:
    """A chunk before it reaches the database.

    Named TextChunk, not Chunk, so it never gets confused with the ORM model of the same idea
    in `app.models.chunk`. `token_count` is filled in by the ingest service from the embedder,
    because counting tokens means knowing which tokenizer, which is not this module's business.
    """

    content: str
    page_no: int | None
    chunk_index: int
    token_count: int | None = None


def _snap_end(text: str, start: int, ideal_end: int, lookback: int) -> int:
    """Return the cut point at or before `ideal_end`, preferring the strongest boundary found.

    Searches paragraph break, then sentence end, then line break, then space. Falls back to
    `ideal_end` only when the whole lookback window holds no boundary at all — a single
    unbroken token longer than the window, which real prose does not produce.
    """
    floor = max(start + 1, ideal_end - lookback)
    window = text[floor:ideal_end]

    paragraph = window.rfind("\n\n")
    if paragraph != -1:
        return floor + paragraph + 2

    sentence = None
    for match in _SENTENCE_END.finditer(window):
        sentence = match.end()
    if sentence is not None:
        return floor + sentence

    for separator in ("\n", " "):
        found = window.rfind(separator)
        if found != -1:
            return floor + found + 1

    return ideal_end


def _snap_start(text: str, ideal_start: int, floor: int) -> int:
    """Pull an overlap start back to a word boundary so the chunk does not open mid-word.

    Pulled back rather than forward: erring towards slightly more overlap keeps the sentence
    that straddles the boundary whole in both chunks, which is the point of having overlap.
    """
    if ideal_start <= floor or ideal_start >= len(text) or text[ideal_start - 1].isspace():
        return max(ideal_start, floor)

    boundary = text.rfind(" ", floor, ideal_start)
    line = text.rfind("\n", floor, ideal_start)
    boundary = max(boundary, line)
    return boundary + 1 if boundary > floor else max(ideal_start, floor)


def _chunk_page(text: str, size: int, overlap: int) -> list[str]:
    """Split one page's text into overlapping windows."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    lookback = max(size // _LOOKBACK_RATIO, 1)
    chunks: list[str] = []
    start = 0

    while start < len(text):
        ideal_end = start + size
        if ideal_end >= len(text):
            piece = text[start:].strip()
            if piece:
                chunks.append(piece)
            break

        end = _snap_end(text, start, ideal_end, lookback)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)

        # `start + 1` as the floor guarantees forward progress: without it a boundary that
        # snaps back past the previous start would loop forever on pathological input.
        start = _snap_start(text, end - overlap, start + 1)

    return chunks


def chunk(pages: Sequence[Page], cfg: PipelineConfig) -> list[TextChunk]:
    """Chunk a loaded document, page by page.

    `chunk_index` runs across the whole document, not per page, because it is half of the
    unique key `(document_id, chunk_index)`.
    """
    if cfg.chunk_overlap >= cfg.chunk_size:
        raise ValueError(
            f"chunk_overlap ({cfg.chunk_overlap}) must be smaller than "
            f"chunk_size ({cfg.chunk_size}) — otherwise a window never advances"
        )

    chunks: list[TextChunk] = []
    for page in pages:
        for content in _chunk_page(page.text, cfg.chunk_size, cfg.chunk_overlap):
            chunks.append(TextChunk(content=content, page_no=page.page_no, chunk_index=len(chunks)))
    return chunks
