import pytest
from semanticcache_core.text import (
    content_tokens,
    guard_failure,
    has_negation,
    identifiers,
    normalize,
    numbers,
)


def test_normalize_is_case_accent_and_whitespace_insensitive() -> None:
    assert normalize("  Héllo\t  WORLD \n") == "hello world"


def test_content_tokens_drop_stopwords_but_keep_negation() -> None:
    assert content_tokens("How do I reset the password?") == ["reset", "password"]
    assert content_tokens("List two reasons, not 12") == ["list", "2", "reasons", "not", "12"]
    assert "not" in content_tokens("It is not working")
    assert "don't" in content_tokens("Why don't cats like water")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("What is 2+2?", {"2"}),
        ("pay 1,000 dollars", {"1000"}),
        ("I have two cats and 003 dogs", {"2", "3"}),
        ("version 3.14 and 3.15", {"3.14", "3.15"}),
        ("no digits here", set()),
    ],
)
def test_numbers(text: str, expected: set[str]) -> None:
    assert numbers(text) == frozenset(expected)


def test_identifiers_pick_codes_versions_and_skus() -> None:
    assert identifiers("error E404 on gpt4 and sku-12a") >= {"e404", "gpt4", "sku-12a"}
    assert identifiers("plain words only") == frozenset()


def test_negation() -> None:
    assert has_negation("Don't do that") and has_negation("without sugar")
    assert not has_negation("Do that")


@pytest.mark.parametrize(
    ("a", "b", "reason"),
    [
        ("What is 2+2?", "What is 3+3?", "numbers differ"),
        ("What is two plus two", "what is 2 plus 2", None),
        ("fix error E404", "fix error E500", "identifiers differ"),
        ("Do cats like milk?", "Don't cats like milk?", "negation differs"),
        ("How do I reset my password?", "how can i reset my password", None),
    ],
)
def test_guard_failure(a: str, b: str, reason: str | None) -> None:
    assert guard_failure(a, b) == reason
