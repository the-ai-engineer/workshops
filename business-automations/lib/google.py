"""The few Google calls the automations need: Drive, Sheets and Calendar.

Auth is a service account. On Cloud Run it is the service's own account, with no key.
Locally, GOOGLE_APPLICATION_CREDENTIALS points at a key file. Share each folder,
sheet and calendar with the service account's email and it can use them.
"""
from functools import cache

import google.auth
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar.readonly",
]
FOLDER = "application/vnd.google-apps.folder"
ALL_DRIVES = {"supportsAllDrives": True}


@cache
def _service(name: str, version: str):
    credentials, _ = google.auth.default(scopes=SCOPES)
    return build(name, version, credentials=credentials, cache_discovery=False)


def drive():
    return _service("drive", "v3")


def sheets():
    return _service("sheets", "v4")


def calendar():
    return _service("calendar", "v3")


# Drive

def list_files(folder_id: str) -> list[dict]:
    """Files directly inside a folder, oldest first. Subfolders are left out."""
    result = drive().files().list(
        q=f"'{folder_id}' in parents and trashed = false and mimeType != '{FOLDER}'",
        fields="files(id, name, mimeType, webViewLink)",
        orderBy="createdTime",
        includeItemsFromAllDrives=True,
        **ALL_DRIVES,
    ).execute()
    return result.get("files", [])


def download(file_id: str) -> bytes:
    return drive().files().get_media(fileId=file_id, **ALL_DRIVES).execute()


def move(file_id: str, from_folder: str, to_folder: str) -> None:
    drive().files().update(
        fileId=file_id, addParents=to_folder, removeParents=from_folder, fields="id", **ALL_DRIVES
    ).execute()


def find_folder(parent_id: str, name: str) -> dict | None:
    safe = name.replace("'", "\\'")
    result = drive().files().list(
        q=f"'{parent_id}' in parents and name = '{safe}' and mimeType = '{FOLDER}' and trashed = false",
        fields="files(id, webViewLink)",
        includeItemsFromAllDrives=True,
        **ALL_DRIVES,
    ).execute()
    files = result.get("files", [])
    return files[0] if files else None


def create_folder(parent_id: str, name: str) -> dict:
    return drive().files().create(
        body={"name": name, "mimeType": FOLDER, "parents": [parent_id]},
        fields="id, webViewLink",
        **ALL_DRIVES,
    ).execute()


# Sheets

def append_row(sheet_id: str, tab: str, row: list) -> None:
    sheets().spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"{tab}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [row]},
    ).execute()


# Calendar

def events_between(calendar_id: str, start: str, end: str) -> list[dict]:
    """Events from start to end (RFC 3339), with recurring events expanded."""
    result = calendar().events().list(
        calendarId=calendar_id, timeMin=start, timeMax=end, singleEvents=True, orderBy="startTime"
    ).execute()
    return result.get("items", [])
