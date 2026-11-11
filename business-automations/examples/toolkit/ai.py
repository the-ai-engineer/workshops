"""AI: one call to a model. Gemini on Vertex AI, signed in as the service account."""
import os
from functools import cache

from google import genai
from google.genai import types

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")


@cache
def _client() -> genai.Client:
    return genai.Client(vertexai=True)


def ask(prompt: str, shape=None, search: bool = False):
    """Ask the model one thing.

    shape:   a pydantic class. The answer comes back as that class instead of text.
    search:  let the model search Google before it answers.
    """
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())] if search else None,
        response_mime_type="application/json" if shape else None,
        response_schema=shape,
    )
    response = _client().models.generate_content(model=MODEL, contents=prompt, config=config)
    if shape is None:
        return response.text
    if response.parsed is None:
        raise RuntimeError("the model did not answer in the expected shape")
    return response.parsed
