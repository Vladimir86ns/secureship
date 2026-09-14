from typing import Any

import httpx

from config import settings


class OllamaResponseError(Exception):
    pass


async def chat_completion(
    system_prompt: str, history: list[dict[str, Any]], tools: list[dict[str, Any]] | None
) -> dict[str, Any]:
    """Send full conversation history (+ optional tool schemas) to Ollama and
    return the raw `message` object (may contain `content` and/or `tool_calls`).
    """
    messages = [{"role": "system", "content": system_prompt}, *history]
    payload: dict[str, Any] = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": False,
        # Measured: disabling thinking made qwen3:8b fail to emit tool_calls
        # almost deterministically (0/5 on a straightforward identity message
        # with all four fields present) even with an explicit "call the tool"
        # instruction. Keeping thinking on fixed it (5/5). The reasoning text
        # itself is never read/stored — only `content`/`tool_calls` are used.
        "think": True,
    }
    if tools:
        payload["tools"] = tools

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{settings.ollama_base_url}/api/chat", json=payload)
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError as exc:
            raise OllamaResponseError("Ollama response was not valid JSON") from exc

    message = data.get("message") if isinstance(data, dict) else None
    if not isinstance(message, dict):
        raise OllamaResponseError("Ollama response did not contain a message")
    return message
