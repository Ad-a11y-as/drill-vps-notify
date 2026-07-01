import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vmiss_notify.cli import main


class CliTest(unittest.TestCase):
    def test_login_uses_nodriver_monitor(self):
        calls = []

        class FakeMonitor:
            def __init__(self, config, notifier):
                calls.append("monitor-created")

            def setup_login(self):
                calls.append("login")

        with (
            patch("vmiss_notify.cli.AppConfig.from_env_file", return_value=object()) as load_config,
            patch("vmiss_notify.cli.MessageNotifier", return_value=object()),
            patch("vmiss_notify.cli.NodriverMonitor", FakeMonitor),
        ):
            result = main(["--env-file", "test.env", "login"])

        self.assertEqual(result, 0)
        load_config.assert_called_once_with("test.env")
        self.assertEqual(calls, ["monitor-created", "login"])

    def test_hybrid_login_is_login_alias(self):
        calls = []

        class FakeMonitor:
            def __init__(self, config, notifier):
                calls.append("monitor-created")

            def setup_login(self):
                calls.append("login")

        with (
            patch("vmiss_notify.cli.AppConfig.from_env_file", return_value=object()),
            patch("vmiss_notify.cli.MessageNotifier", return_value=object()),
            patch("vmiss_notify.cli.NodriverMonitor", FakeMonitor),
        ):
            result = main(["hybrid-login"])

        self.assertEqual(result, 0)
        self.assertEqual(calls, ["monitor-created", "login"])

    def test_public_check_uses_nodriver_public_checker(self):
        calls = []

        class FakePublicChecker:
            def __init__(self, config):
                calls.append("public-created")

            def check_once(self):
                calls.append("public-check")
                return FakeResult("ok")

        with (
            patch("vmiss_notify.cli.PublicCheckConfig.from_env_file", return_value=object()),
            patch("vmiss_notify.cli.NodriverPublicChecker", FakePublicChecker),
        ):
            result = main(["public-check"])

        self.assertEqual(result, 0)
        self.assertEqual(calls, ["public-created", "public-check"])


class FakeResult:
    def __init__(self, message):
        self.message = message


if __name__ == "__main__":
    unittest.main()
