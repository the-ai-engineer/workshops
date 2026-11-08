"""One Claude call with a typed answer. This is the only AI in the automations."""
import base64
import os
from functools import cache

import anthropic
from pydantic import BaseModel


@cache
def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def extract[T: BaseModel](prompt: str, schema: type[T], pdf: bytes | None = None) -> T:
    """Ask Claude to fill in `schema` from the prompt and, optionally, a PDF."""
    content: list[dict] = []
    if pdf is not None:
        content.append({
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.standard_b64encode(pdf).decode(),
            },
        })
    content.append({"type": "text", "text": prompt})

    response = _client().messages.parse(
        model=os.environ.get("CLAUDE_MODEL", "claude-opus-5-5"),
        max_tokens=16000,
        messages=[{"role": "user", "content": content}],
        output_format=schema,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise RuntimeError(f"Claude returned no answer (stop reason: {response.stop_reason})")
    return response.parsed_output
