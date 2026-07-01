import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vmiss_notify.config import AppConfig, ConfigError, PublicCheckConfig, parse_bool, parse_env_file


class ConfigTest(unittest.TestCase):
    def test_parse_env_file_supports_comments_quotes_and_empty_lines(self):
        with self.subTest("quoted values"):
            temp_dir = Path(self._testMethodName)
        env_file = Path("tmp_test_config.env")
        self.addCleanup(lambda: env_file.unlink(missing_ok=True))
        env_file.write_text(
            """
# comment
VMISS_EMAIL="user@example.com"
VMISS_PASSWORD='secret'
CHECK_INTERVAL_SECONDS=45
HEADLESS=false
MESSAGE_TO_USERS=user1,user2
""".strip(),
            encoding="utf-8",
        )

        values = parse_env_file(env_file)

        self.assertEqual(values["VMISS_EMAIL"], "user@example.com")
        self.assertEqual(values["VMISS_PASSWORD"], "secret")
        self.assertEqual(values["CHECK_INTERVAL_SECONDS"], "45")
        self.assertEqual(values["HEADLESS"], "false")
        self.assertEqual(values["MESSAGE_TO_USERS"], "user1,user2")


    def test_app_config_loads_typed_values_from_env_file(self):
        env_file = Path("tmp_test_config.env")
        self.addCleanup(lambda: env_file.unlink(missing_ok=True))
        env_file.write_text(
            """
VMISS_EMAIL=user@example.com
VMISS_PASSWORD=secret
VMISS_STORE_URL=https://app.vmiss.com/store/us-los-angeles-cn2
VMISS_TARGET_PRODUCT=US.LA.CN2.Elite
CHECK_INTERVAL_SECONDS=15
HEADLESS=true
PLAYWRIGHT_USER_DATA_DIR=.browser-profile
PLAYWRIGHT_BROWSER_CHANNEL=chrome
MESSAGE_CLOUD_DOMAIN=notify.example.com
MESSAGE_APP_ID=app-id
MESSAGE_APP_SECRET=app-secret
MESSAGE_PERMANENT_CODE=permanent-code
MESSAGE_TO_USERS=user1,user2
""".strip(),
            encoding="utf-8",
        )

        config = AppConfig.from_env_file(env_file)

        self.assertEqual(config.vmiss_email, "user@example.com")
        self.assertEqual(config.vmiss_password, "secret")
        self.assertEqual(config.store_url, "https://app.vmiss.com/store/us-los-angeles-cn2")
        self.assertEqual(config.target_product, "US.LA.CN2.Elite")
        self.assertEqual(config.check_interval_seconds, 15)
        self.assertIs(config.headless, True)
        self.assertEqual(config.user_data_dir, Path(".browser-profile"))
        self.assertEqual(config.browser_channel, "chrome")
        self.assertEqual(config.message_cloud_domain, "notify.example.com")
        self.assertEqual(config.message_to_users, ["user1", "user2"])


    def test_app_config_rejects_missing_required_values(self):
        env_file = Path("tmp_test_config.env")
        self.addCleanup(lambda: env_file.unlink(missing_ok=True))
        env_file.write_text("VMISS_EMAIL=user@example.com\n", encoding="utf-8")

        with self.assertRaises(ConfigError) as exc_info:
            AppConfig.from_env_file(env_file)

        self.assertIn("VMISS_PASSWORD", str(exc_info.exception))
        self.assertIn("MESSAGE_CLOUD_DOMAIN", str(exc_info.exception))

    def test_public_check_config_does_not_require_login_or_message_values(self):
        env_file = Path("tmp_test_config.env")
        self.addCleanup(lambda: env_file.unlink(missing_ok=True))
        env_file.write_text(
            """
VMISS_STORE_URL=https://app.vmiss.com/store/us-los-angeles-cn2
VMISS_TARGET_PRODUCT=US.LA.CN2.Pro
HEADLESS=true
PLAYWRIGHT_BROWSER_CHANNEL=chrome
""".strip(),
            encoding="utf-8",
        )

        config = PublicCheckConfig.from_env_file(env_file)

        self.assertEqual(config.store_url, "https://app.vmiss.com/store/us-los-angeles-cn2")
        self.assertEqual(config.target_product, "US.LA.CN2.Pro")
        self.assertIs(config.headless, True)
        self.assertEqual(config.browser_channel, "chrome")

    def test_public_check_config_requires_target_product(self):
        env_file = Path("tmp_test_config.env")
        self.addCleanup(lambda: env_file.unlink(missing_ok=True))
        env_file.write_text(
            "VMISS_STORE_URL=https://app.vmiss.com/store/us-los-angeles-cn2\n",
            encoding="utf-8",
        )

        with self.assertRaises(ConfigError) as exc_info:
            PublicCheckConfig.from_env_file(env_file)

        self.assertIn("VMISS_TARGET_PRODUCT", str(exc_info.exception))

    def test_parse_bool_accepts_common_values(self):
        cases = [
            ("true", True),
            ("1", True),
            ("yes", True),
            ("false", False),
            ("0", False),
            ("no", False),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertIs(parse_bool(raw, "HEADLESS"), expected)

    def test_parse_bool_rejects_invalid_value(self):
        with self.assertRaises(ConfigError):
            parse_bool("maybe", "HEADLESS")

if __name__ == "__main__":
    unittest.main()
