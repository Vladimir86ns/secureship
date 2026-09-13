import httpx

from config import settings


class OllamaResponseError(Exception):
    pass


async def ask_ollama(message: str) -> str:
    payload = {
        "model": settings.ollama_model,
        "messages": [{"role": "user", "content": message}],
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{settings.ollama_base_url}/api/chat", json=payload)
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError as exc:
            raise OllamaResponseError("Ollama response was not valid JSON") from exc

    message_obj = data.get("message") if isinstance(data, dict) else None
    content = message_obj.get("content") if isinstance(message_obj, dict) else None
    if not isinstance(content, str):
        raise OllamaResponseError("Ollama response did not contain message.content")
    return content
