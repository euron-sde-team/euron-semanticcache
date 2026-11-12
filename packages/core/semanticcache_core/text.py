"""Text normalisation and the safety guards that run on top of vector similarity.

Embeddings place "What is 2+2?" and "What is 3+3?" almost on top of each other, and "Do cats like milk?" next to
"Don't cats like milk?". Serving the cached answer to the wrong one is a correctness bug, not a tuning problem, so a
candidate must also pass these deterministic guards: the same numbers and the same negation.
"""

from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")
_TOKEN = re.compile(r"[a-z0-9']+")
_NUMBER = re.compile(r"(?<![a-z\d])-?\d+(?:[.,]\d+)*")
_IDENT = re.compile(r"\b(?=[a-z0-9_-]*[a-z])(?=[a-z0-9_-]*\d)[a-z0-9_-]+\b")

STOPWORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "am",
        "do",
        "does",
        "did",
        "to",
        "of",
        "in",
        "on",
        "at",
        "for",
        "with",
        "and",
        "or",
        "but",
        "if",
        "then",
        "so",
        "as",
        "by",
        "from",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "i",
        "you",
        "he",
        "she",
        "we",
        "they",
        "me",
        "my",
        "your",
        "our",
        "their",
        "can",
        "could",
        "would",
        "should",
        "will",
        "shall",
        "may",
        "might",
        "please",
        "tell",
        "explain",
        "just",
        "also",
        "how",
        "what",
        "why",
        "when",
        "where",
        "who",
        "which",
        "whom",
    ]
)
NEGATIONS = frozenset(
    [
        "not",
        "no",
        "never",
        "none",
        "nobody",
        "nothing",
        "nowhere",
        "neither",
        "nor",
        "without",
        "cannot",
        "can't",
        "don't",
        "doesn't",
        "didn't",
        "won't",
        "wouldn't",
        "shouldn't",
        "couldn't",
        "isn't",
        "aren't",
        "wasn't",
        "weren't",
        "hasn't",
        "haven't",
        "hadn't",
    ]
)
_NUMBER_WORDS = {
    w: str(i)
    for i, w in enumerate(
        [
            "zero",
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
            "eleven",
            "twelve",
            "thirteen",
            "fourteen",
            "fifteen",
            "sixteen",
            "seventeen",
            "eighteen",
            "nineteen",
            "twenty",
        ]
    )
}
_CONTRACTIONS = {"can't": "cannot", "won't": "will not", "n't": " not"}


def normalize(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace. Two prompts that differ only in this are the same prompt."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return _WS.sub(" ", text.lower()).strip()


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(normalize(text))


def content_tokens(text: str) -> list[str]:
    """Tokens that carry meaning: no stop-words (negations are kept, they flip meaning)."""
    return [t for t in tokens(text) if t not in STOPWORDS or t in NEGATIONS]


def numbers(text: str) -> frozenset[str]:
    """Every number in the text, digits and spelled-out (zero to twenty), canonicalised: '1,000' == '1000'."""
    norm = _IDENT.sub(" ", normalize(text))  # 'e404' is an identifier, not the number 404
    found = {n.replace(",", "").lstrip("0") or "0" for n in _NUMBER.findall(norm)}
    found |= {_NUMBER_WORDS[t] for t in _TOKEN.findall(norm) if t in _NUMBER_WORDS}
    return frozenset(found)


def identifiers(text: str) -> frozenset[str]:
    """Tokens mixing letters and digits (error codes, versions, SKUs): 'e404', 'v2', 'gpt4'."""
    return frozenset(m for m in _IDENT.findall(normalize(text)) if not m.isdigit())


def has_negation(text: str) -> bool:
    return any(t in NEGATIONS for t in tokens(text))


def guard_failure(a: str, b: str) -> str | None:
    """Why two prompts that look alike must NOT share an answer, or None when they may."""
    if numbers(a) != numbers(b):
        return "numbers differ"
    if identifiers(a) != identifiers(b):
        return "identifiers differ"
    if has_negation(a) != has_negation(b):
        return "negation differs"
    return None
