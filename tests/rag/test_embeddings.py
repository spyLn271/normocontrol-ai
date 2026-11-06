from __future__ import annotations

import json

import httpx
import pytest
import respx
from pydantic import SecretStr

from normocontrol.config.settings import EmbeddingSettings, LLMProvider
from normocontrol.rag.embeddings import EmbeddingError, HttpEmbedder

BASE = "http://embed.test"


@respx.mock
async def test_ollama_embed_batches_and_prefixes() -> None:
    def reply(request: httpx.Request) -> httpx.Response:
        texts = json.loads(request.content)["input"]
        return httpx.Response(200, json={"embeddings": [[float(len(t)), 1.0] for t in texts]})

    route = respx.post(f"{BASE}/api/embed").mock(side_effect=reply)
    embedder = HttpEmbedder(
        EmbeddingSettings(
            base_url=BASE, batch_size=2, passage_prefix="passage: ", query_prefix="query: "
        )
    )
    vectors = await embedder.embed_documents(["а", "бб", "ввв"])
    assert vectors == [[10.0, 1.0], [11.0, 1.0], [12.0, 1.0]]
    assert route.call_count == 2
    assert json.loads(route.calls[0].request.content)["input"][0] == "passage: а"
    assert await embedder.embed_query("x") == [8.0, 1.0]
    await embedder.aclose()


@respx.mock
async def test_openai_compatible_embeddings_sorted_by_index() -> None:
    respx.post(f"{BASE}/v1/embeddings").mock(
        return_value=httpx.Response(
            200, json={"data": [{"index": 1, "embedding": [2]}, {"index": 0, "embedding": [1]}]}
        )
    )
    embedder = HttpEmbedder(
        EmbeddingSettings(
            base_url=BASE, provider=LLMProvider.OPENAI_COMPATIBLE, api_key=SecretStr("k")
        )
    )
    assert await embedder.embed_documents(["a", "b"]) == [[1.0], [2.0]]


@respx.mock
async def test_embedding_errors() -> None:
    respx.post(f"{BASE}/api/embed").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(EmbeddingError, match="недоступен"):
        await HttpEmbedder(EmbeddingSettings(base_url=BASE)).embed_query("x")


@respx.mock
async def test_embedding_count_mismatch() -> None:
    respx.post(f"{BASE}/api/embed").mock(return_value=httpx.Response(200, json={"embeddings": []}))
    with pytest.raises(EmbeddingError, match="не совпадает"):
        await HttpEmbedder(EmbeddingSettings(base_url=BASE)).embed_query("x")
