from __future__ import annotations

import sys
import types
import unittest


google_module = types.ModuleType("google")
google_oauth2_module = types.ModuleType("google.oauth2")
service_account_module = types.ModuleType("google.oauth2.service_account")
service_account_module.Credentials = type("Credentials", (), {"from_service_account_file": staticmethod(lambda *args, **kwargs: object())})
googleapiclient_module = types.ModuleType("googleapiclient")
discovery_module = types.ModuleType("googleapiclient.discovery")
discovery_module.build = lambda *args, **kwargs: object()
errors_module = types.ModuleType("googleapiclient.errors")
errors_module.HttpError = type("HttpError", (Exception,), {})
sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.oauth2", google_oauth2_module)
sys.modules.setdefault("google.oauth2.service_account", service_account_module)
sys.modules.setdefault("googleapiclient", googleapiclient_module)
sys.modules.setdefault("googleapiclient.discovery", discovery_module)
sys.modules.setdefault("googleapiclient.errors", errors_module)

from sheets_client import SheetsClient


class FakeBatchUpdate:
    def __init__(self, calls: list[tuple[str, object]], body: dict):
        self.calls = calls
        self.body = body

    def execute(self) -> dict:
        self.calls.append(("batch_update", self.body))
        return {}


class FakeSpreadsheets:
    def __init__(self, calls: list[tuple[str, object]]):
        self.calls = calls

    def batchUpdate(self, *, spreadsheetId: str, body: dict) -> FakeBatchUpdate:
        del spreadsheetId
        return FakeBatchUpdate(self.calls, body)


class FakeService:
    def __init__(self, calls: list[tuple[str, object]]):
        self.calls = calls

    def spreadsheets(self) -> FakeSpreadsheets:
        return FakeSpreadsheets(self.calls)


class TestSheetsClient(SheetsClient):
    def __init__(self, current_headers: list[str]) -> None:
        self.calls: list[tuple[str, object]] = []
        self.current_headers = current_headers
        self.service = FakeService(self.calls)

    def _ensure_sheet_exists(self, spreadsheet_id: str, tab_name: str) -> int:
        del spreadsheet_id, tab_name
        return 123

    def _get_values(self, spreadsheet_id: str, range_name: str) -> list[list[str]]:
        del spreadsheet_id, range_name
        return [self.current_headers]

    def _update_values(self, spreadsheet_id: str, range_name: str, values: list[list[object]]) -> None:
        del spreadsheet_id
        self.calls.append(("update_values", {"range": range_name, "values": values}))


class SheetsClientTests(unittest.TestCase):
    def test_ensure_tab_expands_grid_before_writing_missing_headers(self) -> None:
        headers = tuple(f"header_{index}" for index in range(1, 31))
        client = TestSheetsClient(list(headers[:20]))

        client._ensure_tab("spreadsheet", "Issue Memory", headers)

        self.assertEqual(client.calls[0][0], "batch_update")
        first_update = client.calls[0][1]["requests"][0]["updateSheetProperties"]["properties"]
        self.assertEqual(first_update["gridProperties"]["columnCount"], 30)

        self.assertEqual(client.calls[1][0], "batch_update")
        second_update = client.calls[1][1]["requests"][0]["updateSheetProperties"]["properties"]
        self.assertEqual(second_update["gridProperties"]["columnCount"], 30)

        self.assertEqual(client.calls[2][0], "update_values")
        self.assertEqual(client.calls[2][1]["range"], "'Issue Memory'!U1:AD1")


if __name__ == "__main__":
    unittest.main()
