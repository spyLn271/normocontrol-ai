from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
import respx

from normocontrol.config.settings import LLMProvider, LLMSettings
from normocontrol.llm.client import (
    LLMError,
    OllamaClient,
    OpenAICompatibleClient,
    create_llm_client,
)

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
BASE = "http://llm.test"


def settings(**overrides: object) -> LLMSettings:
    values: dict[str, object] = {"base_url": BASE, "model": "qwen3:4b", "max_retries": 2}
    values.update(overrides)
    return LLMSettings.model_validate(values)


def chat(content: str) -> httpx.Response:
    return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})


@respx.mock
async def test_ollama_payload_and_success() -> None:
    route = respx.post(f"{BASE}/api/chat").mock(return_value=chat('{"ok": true}'))
    client = OllamaClient(settings(think=False, temperature=0.0))
    assert await client.complete_json(system="s", user="u", schema=SCHEMA) == {"ok": True}
    payload = json.loads(route.calls.last.request.content)
    assert payload["format"] == SCHEMA
    assert payload["stream"] is False
    assert payload["think"] is False
    assert payload["options"]["temperature"] == 0.0
    assert [m["role"] for m in payload["messages"]] == ["system", "user"]
    await client.aclose()


@respx.mock
async def test_invalid_json_is_retried() -> None:
    route = respx.post(f"{BASE}/api/chat").mock(
        side_effect=[chat("not json"), chat("[1, 2]"), chat('{"ok": false}')]
    )
    client = OllamaClient(settings())
    assert await client.complete_json(system="s", user="u", schema=SCHEMA) == {"ok": False}
    assert route.call_count == 3


@respx.mock
async def test_invalid_json_gives_up() -> None:
    respx.post(f"{BASE}/api/chat").mock(return_value=chat("{broken"))
    client = OllamaClient(settings(max_retries=1))
    with pytest.raises(LLMError, match="валидный JSON"):
        await client.complete_json(system="s", user="u", schema=SCHEMA)


@respx.mock
async def test_server_errors_retried_then_fail() -> None:
    route = respx.post(f"{BASE}/api/chat").mock(return_value=httpx.Response(503))
    client = OllamaClient(settings(max_retries=0))
    with pytest.raises(LLMError, match="недоступна"):
        await client.complete_json(system="s", user="u", schema=SCHEMA)
    assert route.call_count == 3  # tenacity: 3 попытки


@respx.mock
async def test_connection_error() -> None:
    respx.post(f"{BASE}/api/chat").mock(side_effect=httpx.ConnectError("refused"))
    client = OllamaClient(settings(max_retries=0))
    with pytest.raises(LLMError):
        await client.complete_json(system="s", user="u", schema=SCHEMA)


@respx.mock
async def test_client_error_not_retried() -> None:
    route = respx.post(f"{BASE}/api/chat").mock(return_value=httpx.Response(404))
    client = OllamaClient(settings(max_retries=0))
    with pytest.raises(LLMError):
        await client.complete_json(system="s", user="u", schema=SCHEMA)
    assert route.call_count == 1


@respx.mock
async def test_cache_avoids_second_call() -> None:
    route = respx.post(f"{BASE}/api/chat").mock(return_value=chat('{"ok": true}'))
    client = OllamaClient(settings())
    for _ in range(3):
        await client.complete_json(system="s", user="u", schema=SCHEMA)
    assert route.call_count == 1


@respx.mock
async def test_exchange_log_written_only_when_enabled(tmp_path: Path) -> None:
    respx.post(f"{BASE}/api/chat").mock(return_value=chat('{"ok": true}'))
    client = OllamaClient(settings(log_dir=tmp_path))
    await client.complete_json(system="s", user="фрагмент", schema=SCHEMA)
    log_file = await asyncio.to_thread(lambda: next(tmp_path.glob("*.jsonl")))
    lines = (await asyncio.to_thread(log_file.read_text, encoding="utf-8")).splitlines()
    assert json.loads(lines[0])["user"] == "фрагмент"


@respx.mock
async def test_health_checks_model_presence() -> None:
    respx.get(f"{BASE}/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "qwen3:4b"}]})
    )
    assert await OllamaClient(settings()).health() is True
    assert await OllamaClient(settings(model="other")).health() is False


@respx.mock
async def test_openai_compatible_client() -> None:
    route = respx.post(f"{BASE}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200, json={"choices": [{"message": {"content": '{"ok": true}'}}]}
        )
    )
    client = create_llm_client(settings(provider=LLMProvider.OPENAI_COMPATIBLE, api_key="secret"))
    assert isinstance(client, OpenAICompatibleClient)
    assert await client.complete_json(system="s", user="u", schema=SCHEMA) == {"ok": True}
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer secret"
    assert json.loads(request.content)["response_format"]["json_schema"]["schema"] == SCHEMA
