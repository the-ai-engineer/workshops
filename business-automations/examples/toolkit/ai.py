"""AI: one call to a model, or an agent with tools. Gemini on Vertex AI, signed in as the service account."""
import asyncio
import os
import subprocess
import tempfile
from functools import cache
from pathlib import Path

from google import genai
from google.adk.agents import Agent, RunConfig
from google.adk.models import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import types

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")


@cache
def _client() -> genai.Client:
    return genai.Client(vertexai=True)


def ask(prompt: str, shape=None, search: bool = False, file: tuple[bytes, str] | None = None):
    """Ask the model one thing.

    shape:   a pydantic class. The answer comes back as that class instead of text.
    search:  let the model search Google before it answers.
    file:    a document, image or recording to read, as (contents, MIME type).
    """
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())] if search else None,
        response_mime_type="application/json" if shape else None,
        response_schema=shape,
    )
    contents = [prompt, types.Part.from_bytes(data=file[0], mime_type=file[1])] if file else prompt
    response = _client().models.generate_content(model=MODEL, contents=contents, config=config)
    if shape is None:
        return response.text
    if response.parsed is None:
        raise RuntimeError("the model did not answer in the expected shape")
    return response.parsed


def transcribe(recording: bytes) -> str:
    """The words spoken in an audio or video file."""
    with tempfile.TemporaryDirectory() as folder:
        Path(folder, "in").write_bytes(recording)
        # Keep only the sound: it is a fraction of the size of the video.
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{folder}/in", "-vn", "-ac", "1",
                        "-b:a", "32k", f"{folder}/sound.mp3"], check=True)
        sound = Path(folder, "sound.mp3").read_bytes()
    return ask("Transcribe this recording word for word.", file=(sound, "audio/mp3"))


def agent(instruction: str, task: str, tools: list, max_turns: int = 10) -> str:
    """Run an agent: the model picks a tool, the code runs it, and so on until the model answers.

    tools:      plain Python functions. The agent can do nothing except call these.
    max_turns:  the most calls to the model it may make before the run is stopped.
    """
    worker = Agent(name="agent", model=Gemini(model=MODEL, client=_client()), instruction=instruction, tools=tools)
    runner = InMemoryRunner(agent=worker, app_name="automation")
    events = asyncio.run(runner.run_debug(task, quiet=True, run_config=RunConfig(max_llm_calls=max_turns)))

    answer, tokens = "", 0
    for event in events:
        for call in event.get_function_calls():
            print(f"  tool: {call.name}")  # the path the agent chose, for the logs
        if event.usage_metadata:
            tokens += event.usage_metadata.total_token_count or 0
        if event.is_final_response() and event.content and event.content.parts:
            answer = event.content.parts[0].text or answer
    print(f"  agent: {tokens} tokens")
    return answer
