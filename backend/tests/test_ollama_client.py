"""ollama_client diagnostics: an empty model reply is logged with counts only (no message text)."""

import logging

import httpx
import pytest

import ollama_client


def _fake_transport(payload: dict) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(200, json=payload))


@pytest.fixture
def ollama_returns(monkeypatch):
    def install(payload: dict) -> None:
        real = httpx.AsyncClient

        def fake_client(*args, **kwargs):
            kwargs["transport"] = _fake_transport(payload)
            return real(*args, **kwargs)

        monkeypatch.setattr(ollama_client.httpx, "AsyncClient", fake_client)

    return install


@pytest.mark.asyncio
async def test_empty_reply_is_logged_without_text(ollama_returns, caplog):
    ollama_returns({
        "message": {"role": "assistant", "content": "", "thinking": "Dana Demo lives at 100 Demo Plaza"},
        "done_reason": "stop", "eval_count": 412, "prompt_eval_count": 1800,
    })
    caplog.set_level(logging.INFO, logger="secureship.ollama")

    await ollama_client.chat_completion("system", [{"role": "user", "content": "where is my shipment?"}], [{"x": 1}])

    line = "\n".join(r.getMessage() for r in caplog.records if r.name == "secureship.ollama")
    assert "empty model reply" in line
    assert "done_reason=stop thinking=yes thinking_chars=33 eval_count=412 prompt_eval_count=1800" in line
    assert "history_messages=1 tools_offered=1" in line
    assert "Dana" not in line and "Plaza" not in line and "where is my shipment" not in line


@pytest.mark.asyncio
async def test_normal_reply_is_not_logged(ollama_returns, caplog):
    ollama_returns({"message": {"role": "assistant", "content": "Hello!"}, "done_reason": "stop"})
    caplog.set_level(logging.INFO, logger="secureship.ollama")

    message = await ollama_client.chat_completion("system", [], None)

    assert message["content"] == "Hello!"
    assert not [r for r in caplog.records if r.name == "secureship.ollama"]
