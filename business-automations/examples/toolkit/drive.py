"""Google Drive: find new files in a folder, download one, mark it as done."""
from functools import cache

import google.auth
from googleapiclient.discovery import build


@cache
def _files():
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=credentials, cache_discovery=False).files()


def new_files(folder_id: str, *types: str) -> list[dict]:
    """Files in a folder that are not marked as done, oldest first.

    types:  MIME types or their first part, such as "application/pdf", "image/" or "video/".
    """
    kinds = " or ".join(f"mimeType contains '{kind}'" for kind in types)
    result = _files().list(
        q=f"'{folder_id}' in parents and trashed = false and ({kinds})"
          " and not appProperties has { key='done' and value='yes' }",
        fields="files(id, name, mimeType, webViewLink)", orderBy="createdTime",
        includeItemsFromAllDrives=True, supportsAllDrives=True,
    ).execute()
    return result.get("files", [])


def download(file_id: str) -> bytes:
    """The contents of a file."""
    return _files().get_media(fileId=file_id, supportsAllDrives=True).execute()


def mark_done(file_id: str) -> None:
    """Tag a file so new_files never returns it again. This is what makes a rerun safe."""
    _files().update(fileId=file_id, body={"appProperties": {"done": "yes"}}, supportsAllDrives=True).execute()
