from __future__ import annotations

from unittest.mock import patch
import unittest

from config import load_settings


BASE_ENV = {
    "ISSUE_MEMORY_SPREADSHEET_ID": "memory",
    "GOOGLE_SERVICE_ACCOUNT_JSON": "/tmp/key.json",
    "OPENAI_API_KEY": "openai-key",
}


class ConfigTests(unittest.TestCase):
    def test_live_settings_accept_slack_bot_without_webhook(self) -> None:
        with patch.dict(
            "os.environ",
            {**BASE_ENV, "SLACK_BOT_TOKEN": "xoxb-token", "SLACK_CHANNEL_ID": "C123"},
            clear=True,
        ):
            settings = load_settings("/tmp/daily-slack-bugs-missing.env", require_slack=True)

        self.assertEqual(settings.slack_bot_token, "xoxb-token")
        self.assertEqual(settings.slack_channel_id, "C123")
        self.assertEqual(settings.slack_webhook_url, "")

    def test_live_settings_require_some_slack_delivery_config(self) -> None:
        with patch.dict("os.environ", BASE_ENV, clear=True):
            with self.assertRaisesRegex(ValueError, "Missing Slack configuration"):
                load_settings("/tmp/daily-slack-bugs-missing.env", require_slack=True)

    def test_dry_run_settings_do_not_require_slack_config(self) -> None:
        with patch.dict("os.environ", BASE_ENV, clear=True):
            settings = load_settings("/tmp/daily-slack-bugs-missing.env", require_slack=False)

        self.assertEqual(settings.slack_bot_token, "")
        self.assertEqual(settings.slack_channel_id, "")
        self.assertEqual(settings.slack_webhook_url, "")


if __name__ == "__main__":
    unittest.main()
