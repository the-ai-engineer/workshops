"""The tools: every call the examples make to Drive, Sheets and Gemini.

Each tool is a plain function that does one thing. A workflow calls them in a
fixed order (00, 01, 02). An agent picks which to call (the agent step in 02,
all of 03). The guardrails live here, in code, so they hold whoever is calling:
a handled file is never picked up twice and the same row is never saved twice.

Auth: there are no API keys. On Cloud Run every call signs in as the job's
service account, Gemini included (through Vertex AI). See the README.
"""
import logging
import os
import subprocess
import tempfile
from datetime import date
from functools import cache
from pathlib import Path

import google.auth
from dotenv import load_dotenv
from google import genai
from google.genai import types
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from pydantic import BaseModel

load_dotenv()  # every example imports this file, so .env is loaded once, here
logging.getLogger("google_auth_httplib2").setLevel(logging.ERROR)  # it warns about timeouts on every Drive call

SCOPES = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"]
FOLDER = "application/vnd.google-apps.folder"
ALL_DRIVES = {"supportsAllDrives": True}
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
MAX_AUDIO_BYTES = 19_000_000  # audio goes inside the request, which Vertex AI caps at 20 MB: about 75 minutes
MAX_CELL = 49_000  # a Sheets cell holds 50,000 characters: about 45 minutes of talking


@cache
def _google(name: str, version: str):
    credentials, _ = google.auth.default(scopes=SCOPES)
    return build(name, version, credentials=credentials, cache_discovery=False)


def _files():
    return _google("drive", "v3").files()


def _list(query: str, fields: str) -> list[dict]:
    result = _files().list(q=query, fields=f"files({fields})", orderBy="createdTime",
                           includeItemsFromAllDrives=True, **ALL_DRIVES).execute()
    return result.get("files", [])


def _quote(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'")


@cache
def gemini() -> genai.Client:
    return genai.Client(vertexai=True)  # Gemini on Vertex AI: the service account is the login


# Drive

def new_files(folder_id: str, *types: str) -> list[dict]:
    """Files in a folder that haven't been handled yet, oldest first.

    `types` are MIME types or prefixes: "application/pdf", "audio/", "video/".
    """
    kinds = " or ".join(f"mimeType contains '{kind}'" for kind in types)
    return _list(f"'{folder_id}' in parents and trashed = false and ({kinds})"
                 " and not appProperties has { key='handled' and value='yes' }",
                 "id, name, mimeType, webViewLink")


def mark_handled(file_id: str) -> None:
    """Tag a file so new_files never returns it again."""
    _files().update(fileId=file_id, body={"appProperties": {"handled": "yes"}}, **ALL_DRIVES).execute()


def find_folder(parent_id: str, name: str) -> dict | None:
    found = _list(f"'{parent_id}' in parents and name = '{_quote(name)}' and mimeType = '{FOLDER}'"
                  " and trashed = false", "id, webViewLink")
    return found[0] if found else None


def move_file(file_id: str, from_folder: str, to_folder: str) -> None:
    _files().update(fileId=file_id, addParents=to_folder, removeParents=from_folder,
                    fields="id", **ALL_DRIVES).execute()


# Sheets

def read_rows(sheet_id: str, tab: str) -> list[list[str]]:
    result = _google("sheets", "v4").spreadsheets().values().get(spreadsheetId=sheet_id, range=f"'{tab}'").execute()
    return result.get("values", [])


def add_row(sheet_id: str, tab: str, row: list) -> None:
    # RAW: the text goes in as typed. Model output that starts with "=" must never run as a formula.
    _google("sheets", "v4").spreadsheets().values().append(
        spreadsheetId=sheet_id, range=f"'{tab}'!A1", valueInputOption="RAW", body={"values": [row]},
    ).execute()


def save_once(sheet_id: str, tab: str, key: list[str], text: str) -> bool:
    """Add the row [today, *key, text], unless the tab already has a row with this key.

    Returns whether it was added. This is what makes a retry safe: the same
    transcript, note or draft is never saved twice.
    """
    if any(row[1:1 + len(key)] == key for row in read_rows(sheet_id, tab)):
        return False
    add_row(sheet_id, tab, [date.today().isoformat(), *key, text[:MAX_CELL]])
    return True


# Gemini

def research[T: BaseModel](question: str, schema: type[T]) -> T:
    """Answer a question with Google Search, in the shape of `schema`. One model call, no agent."""
    response = gemini().models.generate_content(
        model=MODEL,
        contents=question,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )
    if response.parsed is None:
        raise RuntimeError("Gemini returned no answer in the expected shape")
    return response.parsed


@cache  # an agent may ask twice; the second answer is free
def transcribe(file_id: str) -> str:
    """The transcript of an audio or video file in Drive. One model call, no agent."""
    with tempfile.TemporaryDirectory() as tmp:
        with open(f"{tmp}/in", "wb") as file:
            download = MediaIoBaseDownload(file, _files().get_media(fileId=file_id, **ALL_DRIVES))
            done = False
            while not done:
                _, done = download.next_chunk()
        # Audio only: a fraction of the size and the tokens of the video.
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{tmp}/in", "-vn", "-ac", "1",
                        "-b:a", "32k", f"{tmp}/audio.mp3"], check=True)
        audio = Path(f"{tmp}/audio.mp3").read_bytes()
    if len(audio) > MAX_AUDIO_BYTES:
        raise ValueError("the recording is too long to send in one request (about 75 minutes is the limit)")
    response = gemini().models.generate_content(
        model=MODEL,
        contents=["Transcribe this audio word for word. Label the speakers if there is more than one.",
                  types.Part.from_bytes(data=audio, mime_type="audio/mp3")],
    )
    return response.text
