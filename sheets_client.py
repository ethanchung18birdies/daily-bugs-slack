from __future__ import annotations

from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import Settings
from issue_memory import (
    ALERT_LOG_COLUMNS,
    ISSUE_MEMORY_COLUMNS,
    MATCHED_REPORTS_COLUMNS,
    issue_from_row,
    issue_to_row,
)
from models import IssueRecord


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
ISSUE_MEMORY_TAB = "Issue Memory"
ALERT_LOG_TAB = "Alert Log"
MATCHED_REPORTS_TAB = "Matched Reports Log"


class SheetsClient:
    def __init__(self, settings: Settings):
        creds = service_account.Credentials.from_service_account_file(
            settings.google_service_account_json,
            scopes=SCOPES,
        )
        self.service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        self.source_spreadsheet_id = settings.product_feedback_spreadsheet_id
        self.memory_spreadsheet_id = settings.issue_memory_spreadsheet_id

    def source_values(self, tab_name: str) -> list[list[str]]:
        return self._get_values(self.source_spreadsheet_id, f"'{tab_name}'!A:Z")

    def ensure_memory_schema(self) -> None:
        self._ensure_tab(self.memory_spreadsheet_id, ISSUE_MEMORY_TAB, ISSUE_MEMORY_COLUMNS)
        self._ensure_tab(self.memory_spreadsheet_id, ALERT_LOG_TAB, ALERT_LOG_COLUMNS)
        self._ensure_tab(self.memory_spreadsheet_id, MATCHED_REPORTS_TAB, MATCHED_REPORTS_COLUMNS)

    def read_issues(self) -> list[IssueRecord]:
        try:
            values = self._get_values(self.memory_spreadsheet_id, f"'{ISSUE_MEMORY_TAB}'!A:Z")
        except HttpError as exc:
            if exc.resp.status == 400:
                return []
            raise
        if not values:
            return []
        headers = [header.strip() for header in values[0]]
        issues: list[IssueRecord] = []
        for row_number, row in enumerate(values[1:], start=2):
            record = _record_from_row(headers, row)
            if record.get("issue_id", "").strip():
                issues.append(issue_from_row(record, row_number=row_number))
        return issues

    def upsert_issue(self, issue: IssueRecord) -> None:
        values = [issue_to_row(issue)]
        if issue.row_number:
            self._update_values(
                self.memory_spreadsheet_id,
                f"'{ISSUE_MEMORY_TAB}'!A{issue.row_number}:T{issue.row_number}",
                values,
            )
        else:
            self._append_values(self.memory_spreadsheet_id, f"'{ISSUE_MEMORY_TAB}'!A:T", values)

    def append_alert_log(self, row: list[str | int | float]) -> None:
        self._append_values(self.memory_spreadsheet_id, f"'{ALERT_LOG_TAB}'!A:I", [row])

    def append_matched_report_logs(self, rows: list[list[str | int | float]]) -> None:
        if rows:
            self._append_values(self.memory_spreadsheet_id, f"'{MATCHED_REPORTS_TAB}'!A:I", rows)

    def _get_values(self, spreadsheet_id: str, range_name: str) -> list[list[str]]:
        response = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_name)
            .execute()
        )
        return response.get("values", [])

    def _append_values(self, spreadsheet_id: str, range_name: str, values: list[list[Any]]) -> None:
        self.service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ).execute()

    def _update_values(self, spreadsheet_id: str, range_name: str, values: list[list[Any]]) -> None:
        self.service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="RAW",
            body={"values": values},
        ).execute()

    def _ensure_tab(self, spreadsheet_id: str, tab_name: str, headers: tuple[str, ...]) -> None:
        sheet_id = self._ensure_sheet_exists(spreadsheet_id, tab_name)
        values = self._get_values(spreadsheet_id, f"'{tab_name}'!1:1")
        current_headers = values[0] if values else []
        if current_headers != list(headers):
            self._update_values(spreadsheet_id, f"'{tab_name}'!A1:Z1", [list(headers)])

        self.service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "updateSheetProperties": {
                            "properties": {
                                "sheetId": sheet_id,
                                "gridProperties": {
                                    "frozenRowCount": 1,
                                    "columnCount": len(headers),
                                },
                            },
                            "fields": "gridProperties.frozenRowCount,gridProperties.columnCount",
                        }
                    }
                ]
            },
        ).execute()

    def _ensure_sheet_exists(self, spreadsheet_id: str, tab_name: str) -> int:
        try:
            return self._lookup_sheet_id(spreadsheet_id, tab_name)
        except KeyError:
            response = (
                self.service.spreadsheets()
                .batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
                )
                .execute()
            )
            return response["replies"][0]["addSheet"]["properties"]["sheetId"]

    def _lookup_sheet_id(self, spreadsheet_id: str, tab_name: str) -> int:
        spreadsheet = self.service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        for sheet in spreadsheet.get("sheets", []):
            props = sheet.get("properties", {})
            if props.get("title") == tab_name:
                return props["sheetId"]
        raise KeyError(f"Worksheet not found: {tab_name}")


def _record_from_row(headers: list[str], row: list[str]) -> dict[str, str]:
    padded = row + [""] * (len(headers) - len(row))
    return {header: padded[index] for index, header in enumerate(headers)}
