from __future__ import annotations

import argparse

from .browser import VmissMonitor, VmissPublicChecker
from .config import AppConfig, PublicCheckConfig
from .notifier import MessageNotifier
from .seleniumbase_bridge import run_seleniumbase_manual_verification


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor VMISS VPS stock and click order when available.")
    parser.add_argument("--env-file", default=".env", help="Path to .env file")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("login", help="Open browser and initialize persistent login state")
    subparsers.add_parser("hybrid-login", help="Use SeleniumBase for manual verification, then initialize Playwright")
    subparsers.add_parser("monitor", help="Run continuous stock monitor")
    subparsers.add_parser("once", help="Run one stock check")
    subparsers.add_parser("public-check", help="Check public product page without login, notify, or order click")
    subparsers.add_parser("test-notify", help="Send a test notification")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "public-check":
        public_config = PublicCheckConfig.from_env_file(args.env_file)
        result = VmissPublicChecker(public_config).check_once()
        print(result.message)
        return 0

    config = AppConfig.from_env_file(args.env_file)
    notifier = MessageNotifier(config)

    if args.command == "test-notify":
        notifier.send_text("服务监控测试通知")
        print("测试通知已发送")
        return 0

    if args.command == "hybrid-login":
        run_seleniumbase_manual_verification(config)
        monitor = VmissMonitor(config, notifier)
        monitor.setup_login()
        return 0

    monitor = VmissMonitor(config, notifier)
    if args.command == "login":
        monitor.setup_login()
        return 0
    if args.command == "once":
        result = monitor.run_once()
        print(result.message)
        return 0
    if args.command == "monitor":
        monitor.monitor_forever()
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
