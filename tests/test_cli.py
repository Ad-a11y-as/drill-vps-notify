import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vmiss_notify.cli import main


class CliTest(unittest.TestCase):
    def test_hybrid_login_runs_seleniumbase_then_playwright_login(self):
        calls = []

        class FakeMonitor:
            def __init__(self, config, notifier):
                calls.append("monitor-created")

            def setup_login(self):
                calls.append("playwright-login")

        with (
            patch("vmiss_notify.cli.AppConfig.from_env_file", return_value=object()) as load_config,
            patch("vmiss_notify.cli.MessageNotifier", return_value=object()),
            patch("vmiss_notify.cli.VmissMonitor", FakeMonitor),
            patch(
                "vmiss_notify.cli.run_seleniumbase_manual_verification",
                side_effect=lambda config: calls.append("seleniumbase"),
            ),
        ):
            result = main(["--env-file", "test.env", "hybrid-login"])

        self.assertEqual(result, 0)
        load_config.assert_called_once_with("test.env")
        self.assertEqual(calls, ["seleniumbase", "monitor-created", "playwright-login"])


if __name__ == "__main__":
    unittest.main()
