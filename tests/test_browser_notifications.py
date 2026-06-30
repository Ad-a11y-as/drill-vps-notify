import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vmiss_notify.browser import LoginStateNotifier


class FakeNotifier:
    def __init__(self):
        self.messages = []

    def send_text(self, content):
        self.messages.append(content)


class LoginStateNotifierTest(unittest.TestCase):
    def test_notify_login_success_once(self):
        notifier = FakeNotifier()
        login_notifier = LoginStateNotifier(notifier)

        login_notifier.notify_success("US.LA.CN2.Pro")
        login_notifier.notify_success("US.LA.CN2.Pro")

        self.assertEqual(notifier.messages, ["VMISS 登录成功，开始监控：US.LA.CN2.Pro"])


if __name__ == "__main__":
    unittest.main()
