from __future__ import annotations

from typing import Callable

from .config import AppConfig


def build_seleniumbase_driver_options(config: AppConfig) -> dict:
    browser = "edge" if config.browser_channel == "msedge" else "chrome"
    return {
        "browser": browser,
        "headless": False,
        "uc": False,
        "user_data_dir": str(config.user_data_dir),
    }


def run_seleniumbase_manual_verification(
    config: AppConfig,
    *,
    driver_factory: Callable[..., object] | None = None,
    input_func: Callable[[str], object] = input,
) -> None:
    if driver_factory is None:
        try:
            from seleniumbase import Driver
        except ImportError as exc:
            raise RuntimeError("SeleniumBase 未安装，请先安装依赖后再运行 hybrid-login") from exc
        driver_factory = Driver

    driver = driver_factory(**build_seleniumbase_driver_options(config))
    try:
        driver.get(config.store_url)
        input_func("请在 SeleniumBase 浏览器中手动完成验证，然后按 Enter 关闭浏览器并交给 Playwright...")
    finally:
        driver.quit()
