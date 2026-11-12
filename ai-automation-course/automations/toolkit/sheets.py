"""Google Sheets: read a tab, add a row. The sheet is the one named in SHEET_ID.

Share the sheet with the service account's email as Editor. That is the whole login.
"""
import os
from functools import cache

import google.auth
from googleapiclient.discovery import build

from toolkit import retry


@cache
def _values():
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return build("sheets", "v4", credentials=credentials, cache_discovery=False).spreadsheets().values()


def read(tab: str) -> list[list[str]]:
    """Every row in a tab, as lists of text."""
    result = retry.call(lambda: _values().get(spreadsheetId=os.environ["SHEET_ID"], range=f"'{tab}'").execute())
    return result.get("values", [])


def add(tab: str, row: list) -> None:
    """Add one row to the bottom of a tab."""
    # RAW: the text goes in as typed, so nothing a model or a stranger wrote can run as a formula.
    retry.call(lambda: _values().append(spreadsheetId=os.environ["SHEET_ID"], range=f"'{tab}'!A1",
                                        valueInputOption="RAW", body={"values": [row]}).execute())
