"""Keyword retrieval over Postgres full-text search. The lexical half of `hybrid`.

**Why this exists.** Dense retrieval matches meaning and misses tokens that carry no meaning to
an embedding model: a policy code (`QC-01`), an allowance amount, a form number, a job title
written exactly as the handbook writes it. Enterprise documents are full of those, which is why
PLAN.md Phase 6 puts hybrid retrieval first by benefit/effort ratio.

**"BM25" is the name of the idea, not of the algorithm here.** Postgres `ts_rank_cd` is a
coverage-density rank, not Okapi BM25 — there is no `k1`, no `b`, and document length enters
differently. The file is named for the role it plays (PLAN.md calls it `bm25.py`) and the
docstring is where the difference gets recorded rather than quietly implied. Nothing downstream
depends on the scores being BM25: the hybrid retriever fuses by rank precisely so that the
scoring function can be exactly this vague without contaminating anything.

**Three decisions worth their own paragraph:**

*`simple`, not `english`.* Postgres 16 has no Vietnamese configuration. `english` stems and
stopword-strips Vietnamese as if it were English, dropping common Vietnamese function words that
are not stopwords at all. `simple` case-folds and splits — no stemming, diacritics preserved.
This is the same reasoning already recorded on `DocumentRepository.search_text`.

*OR, not AND.* `plainto_tsquery` ANDs every term, and on a real question that returns nothing:
"Nhân viên đi công tác tỉnh xa được thanh toán phụ cấp bao nhiêu một ngày?" matches **zero**
chunks under AND on the current corpus, and ranks the correct document in the top 3 under OR.
A retriever that returns an empty list for a well-formed question is not a retriever. OR plus a
ranking function is how a keyword search is supposed to degrade.

*Stopwords are removed by us, not by Postgres.* `simple` has no stopword list, so under OR every
Vietnamese question word (`bao nhiêu`, `không`, `của`, `là`) becomes a term that matches nearly
every chunk and flattens the ranking toward noise. `VIETNAMESE_STOPWORDS` below is the list, kept
deliberately short: only words that carry no topical signal in *any* HR question. Dropping a word
that turns out to matter is the failure mode to fear, so the list errs small.
"""

from __future__ import annotations

import re

from app.core.exceptions import RagChatbotError
from app.llm.rag.retrievers.base import RetrievedChunk, from_hits
from app.repositories.document_repo import TSVECTOR_CONFIG, DocumentRepository

__all__ = ["TSVECTOR_CONFIG", "BM25Retriever", "build_tsquery"]


class KeywordRetrievalFailed(RagChatbotError):
    """The question could not be turned into a keyword query."""


# Function words with no topical signal in an HR question. Kept short on purpose: a term wrongly
# dropped here is a term the retriever can never match on, and that failure is silent. Words that
# look like stopwords but carry meaning in this corpus (`ngày`, `năm`, `phép`, `lương`) are
# deliberately absent.
VIETNAMESE_STOPWORDS = frozenset(
    {
        "là",
        "và",
        "của",
        "có",
        "được",
        "cho",
        "với",
        "các",
        "những",
        "một",
        "trong",
        "khi",
        "thì",
        "mà",
        "này",
        "đó",
        "nào",
        "gì",
        "bao",
        "nhiêu",
        "không",
        "phải",
        "sẽ",
        "đã",
        "về",
        "từ",
        "đến",
        "tôi",
        "ai",
        "sao",
        "như",
        "thế",
        "ra",
        "vào",
        "hay",
        "hoặc",
        "nếu",
        "để",
        "bị",
        "ở",
        "cái",
    }
)

# Tokens that are punctuation-only or a single character carry no signal and cost a scan.
_MIN_TERM_LEN = 2

# Split on anything that is not a word character. `\w` is Unicode-aware in Python 3, so
# Vietnamese letters and their diacritics survive; `/`, `.`, `,` and friends do not. This
# mirrors what the `simple` configuration does on the indexing side.
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(question: str) -> list[str]:
    """Question -> lowercase content terms, stopwords and 1-character tokens removed.

    Order is preserved and duplicates are dropped: a term repeated in the question would
    otherwise appear twice in the tsquery, which changes nothing about the match and only
    makes the query harder to read in a log.
    """
    seen: set[str] = set()
    terms: list[str] = []
    for match in _TOKEN_RE.finditer(question.lower()):
        term = match.group()
        if len(term) < _MIN_TERM_LEN or term in VIETNAMESE_STOPWORDS or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def build_tsquery(question: str) -> str:
    """Question -> a tsquery string ORing every content term. Empty if nothing survives.

    The terms are joined with `|` and each is wrapped in single quotes, which is how `to_tsquery`
    accepts a lexeme containing anything unusual.

    Quotes inside a term are doubled even though `tokenize` cannot currently produce one — `\\w+`
    splits `nhân's` into `nhân` and `s`, and the `s` is then dropped as too short. That makes the
    escaping unreachable today and it is kept anyway: it costs one `str.replace`, and the day
    someone widens the token pattern to keep hyphenated codes like `QC-01`, the alternative is a
    tsquery syntax error surfacing as a 500 on the serving path. The whole string still reaches
    Postgres as a bind parameter, so this is about valid syntax, not about injection.
    """
    terms = tokenize(question)
    return " | ".join(f"'{term.replace(chr(39), chr(39) * 2)}'" for term in terms)


class BM25Retriever:
    """Postgres full-text keyword retrieval. The lexical half of `HybridRetriever`."""

    name = "bm25"

    def __init__(self, repo: DocumentRepository) -> None:
        # The repository, not the VectorStore: `VectorStore` is the embedding-search seam and
        # widening it with a keyword method would make every implementation of it carry a
        # capability that has nothing to do with vectors.
        self._repo = repo

    async def retrieve(self, question: str, k: int) -> list[RetrievedChunk]:
        """Top-k chunks by keyword rank, best first.

        Returns `[]` when the question is made entirely of stopwords — that is a real answer
        ("no keyword in this question is worth matching on"), not an error. `HybridRetriever`
        handles it by falling through to the dense results alone, which is the correct behaviour
        for a question like "Chính sách đó là gì?" that carries no lexical anchor at all.
        """
        if not question.strip():
            raise KeywordRetrievalFailed("cannot retrieve for an empty question")
        if k < 1:
            raise KeywordRetrievalFailed(f"top_k must be at least 1, got {k}")

        tsquery = build_tsquery(question)
        if not tsquery:
            return []

        hits = await self._repo.search_keyword(tsquery, k)
        return from_hits(hits, retriever=self.name)
