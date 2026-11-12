import httpx
import numpy as np
import pytest
from semanticcache_core.embedding import HashingEmbedder, OpenAICompatEmbedder, build_embedder


def cos(a: np.ndarray, b: np.ndarray) -> float:
    return float(a @ b)


async def sims(emb: HashingEmbedder, base: str, others: list[str]) -> list[float]:
    vecs = await emb.embed([base, *others])
    return [cos(vecs[0], v) for v in vecs[1:]]


async def test_vectors_are_unit_length_and_deterministic() -> None:
    emb = HashingEmbedder(256)
    a1, a2 = await emb.embed(["How do I reset my password?", "How do I reset my password?"])
    assert a1.shape == (256,) and abs(float(np.linalg.norm(a1)) - 1.0) < 1e-5
    assert np.array_equal(a1, a2)
    assert np.array_equal((await HashingEmbedder(256).embed(["How do I reset my password?"]))[0], a1)


async def test_paraphrases_score_above_unrelated_text() -> None:
    emb = HashingEmbedder()
    para, unrelated = await sims(
        emb,
        "How do I reset my password?",
        ["how can I reset my password", "What is the capital of France?"],
    )
    assert para > 0.8
    assert unrelated < 0.3
    assert para - unrelated > 0.5


async def test_word_order_and_case_barely_matter() -> None:
    (s,) = await sims(HashingEmbedder(), "reset password account", ["Account password RESET"])
    assert s > 0.7


async def test_empty_prompt_is_not_similar_to_real_text() -> None:
    emb = HashingEmbedder()
    (s,) = await sims(emb, "", ["How do I reset my password?"])
    assert s < 0.2


async def test_openai_compat_embedder_posts_and_normalises() -> None:
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers.get("authorization")
        seen["body"] = req.read().decode()
        data = [{"index": 1, "embedding": [0.0, 2.0]}, {"index": 0, "embedding": [3.0, 4.0]}]
        return httpx.Response(200, json={"data": data})

    emb = OpenAICompatEmbedder(
        "http://llm.test/v1/", "m", "k", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    a, b = await emb.embed(["First", "Second"])
    assert seen["auth"] == "Bearer k" and '"input":["first","second"]' in str(seen["body"]).replace(" ", "")
    assert np.allclose(a, [0.6, 0.8]) and np.allclose(b, [0.0, 1.0])
    assert emb.dim == 2


def test_build_embedder() -> None:
    assert build_embedder("hashing", dim=64).dim == 64
    with pytest.raises(ValueError, match="unknown embedder"):
        build_embedder("nope")
