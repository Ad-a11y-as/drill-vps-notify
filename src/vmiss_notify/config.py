from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """Raised when runtime configuration is missing or invalid."""


@dataclass(frozen=True)
class AppConfig:
    vmiss_email: str
    vmiss_password: str
    store_url: str
    target_product: str
    check_interval_seconds: int
    headless: bool
    user_data_dir: Path
    login_url: str
    cloudflare_wait_seconds: int
    message_cloud_domain: str
    message_app_id: str
    message_app_secret: str
    message_permanent_code: str
    message_to_users: list[str]
    token_refresh_after_seconds: int = 6600

    @classmethod
    def from_env_file(cls, path: Path | str = ".env") -> "AppConfig":
        file_values = parse_env_file(Path(path))
        values = {**file_values, **os.environ}

        required = [
            "VMISS_EMAIL",
            "VMISS_PASSWORD",
            "VMISS_STORE_URL",
            "VMISS_TARGET_PRODUCT",
            "MESSAGE_CLOUD_DOMAIN",
            "MESSAGE_APP_ID",
            "MESSAGE_APP_SECRET",
            "MESSAGE_PERMANENT_CODE",
            "MESSAGE_TO_USERS",
        ]
        missing = [name for name in required if not values.get(name, "").strip()]
        if missing:
            raise ConfigError(f"Missing required configuration: {', '.join(missing)}")

        return cls(
            vmiss_email=values["VMISS_EMAIL"].strip(),
            vmiss_password=values["VMISS_PASSWORD"].strip(),
            store_url=values["VMISS_STORE_URL"].strip(),
            target_product=values["VMISS_TARGET_PRODUCT"].strip(),
            check_interval_seconds=parse_int(values.get("CHECK_INTERVAL_SECONDS", "30"), "CHECK_INTERVAL_SECONDS"),
            headless=parse_bool(values.get("HEADLESS", "false"), "HEADLESS"),
            user_data_dir=Path(values.get("PLAYWRIGHT_USER_DATA_DIR", ".browser-profile").strip()),
            login_url=values.get("VMISS_LOGIN_URL", "https://app.vmiss.com/login").strip(),
            cloudflare_wait_seconds=parse_int(
                values.get("CLOUDFLARE_WAIT_SECONDS", "900"), "CLOUDFLARE_WAIT_SECONDS"
            ),
            message_cloud_domain=normalize_domain(values["MESSAGE_CLOUD_DOMAIN"]),
            message_app_id=values["MESSAGE_APP_ID"].strip(),
            message_app_secret=values["MESSAGE_APP_SECRET"].strip(),
            message_permanent_code=values["MESSAGE_PERMANENT_CODE"].strip(),
            message_to_users=parse_csv(values["MESSAGE_TO_USERS"]),
            token_refresh_after_seconds=parse_int(
                values.get("TOKEN_REFRESH_AFTER_SECONDS", "6600"), "TOKEN_REFRESH_AFTER_SECONDS"
            ),
        )


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = strip_quotes(value.strip())
        if key:
            values[key] = value
    return values


def strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_bool(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ConfigError(f"{name} must be a boolean value, got {value!r}")


def parse_int(value: str, name: str) -> int:
    try:
        parsed = int(value.strip())
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {value!r}") from exc
    if parsed <= 0:
        raise ConfigError(f"{name} must be greater than 0")
    return parsed


def parse_csv(value: str) -> list[str]:
    items = [item.strip() for item in value.split(",")]
    return [item for item in items if item]


def normalize_domain(value: str) -> str:
    domain = value.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
    if not domain:
        raise ConfigError("MESSAGE_CLOUD_DOMAIN must not be empty")
    return domain
