"""AI: one call to a model. Gemini on Vertex AI, signed in as the service account.

There is no API key. On Cloud Run the client signs in as the service account the
automation runs as. On your laptop it uses your gcloud login.

VERTEX_LOCATION is where the model runs. "global" has every model, and new
models often start there. Set a region, such as europe-west2, to pin where a
customer's data is processed. Check the model you pick is offered in that region.
"""
import os
from functools import cache

from google import genai
from google.genai import types

from toolkit import retry

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
LOCATION = os.environ.get("VERTEX_LOCATION", "global")

tokens = 0  # tokens used so far in this run; the trigger logs it


@cache
def _client() -> genai.Client:
    # Cloud Run sets GOOGLE_CLOUD_PROJECT (deploy.sh). On your laptop it's PROJECT, from .env.
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT")
    return genai.Client(vertexai=True, project=project, location=LOCATION)


def ask(prompt: str, shape=None, search: bool = False):
    """Ask the model one thing.

    shape:   a pydantic class. The answer comes back as that class instead of text.
    search:  let the model search Google before it answers.
    """
    global tokens
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())] if search else None,
        response_mime_type="application/json" if shape else None,
        response_schema=shape,
    )
    response = retry.call(lambda: _client().models.generate_content(model=MODEL, contents=prompt, config=config))
    if response.usage_metadata:
        tokens += response.usage_metadata.total_token_count or 0
    if shape is None:
        return response.text
    if response.parsed is None:
        raise RuntimeError("the model did not answer in the expected shape")
    return response.parsed
