from typing import Any


def tool_call_message(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
    }


def text_message(content: str) -> dict[str, Any]:
    return {"role": "assistant", "content": content}
