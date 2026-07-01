from __future__ import annotations

import asyncio
import inspect
import random
import re
from dataclasses import dataclass
from typing import Awaitable, Callable

from .config import AppConfig, PublicCheckConfig
from .notifier import MessageNotifier
from .stock import StockStatus, assess_stock


CLOUDFLARE_TEXT_RE = re.compile(
    r"(Cloudflare|Verify you are human|Checking if the site connection is secure|请完成|真人认证|安全验证|自动程序|请稍候)",
    re.IGNORECASE,
)

ORDER_TEXTS = ["Order Now", "立即订购", "立即订購", "立即订阅", "立即訂閱", "立即订閱"]
LOGIN_EMAIL_SELECTORS = ['input[type="email"]', 'input[name="email"]', 'input[name="username"]', "#inputEmail", "#email"]
LOGIN_PASSWORD_SELECTORS = ['input[type="password"]', 'input[name="password"]', "#inputPassword", "#password"]
LOGIN_BUTTON_SELECTORS = ['button[type="submit"]', 'input[type="submit"]']


@dataclass(frozen=True)
class CheckResult:
    status: StockStatus
    ordered: bool
    message: str


def build_nodriver_start_options(config: AppConfig | PublicCheckConfig) -> dict:
    return {
        "headless": False,
        "user_data_dir": str(config.user_data_dir),
    }


class NodriverMonitor:
    def __init__(
        self,
        config: AppConfig,
        notifier: MessageNotifier,
        *,
        browser_factory: Callable[..., object] | None = None,
        input_func: Callable[[str], object] = input,
        async_sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
    ) -> None:
        self._config = config
        self._notifier = notifier
        self._browser_factory = browser_factory
        self._input_func = input_func
        self._async_sleep = async_sleep
        self._login_notified = False

    def setup_login(self) -> None:
        self._run(self._setup_login())

    def run_once(self) -> CheckResult:
        return self._run(self._run_once())

    def monitor_forever(self) -> None:
        self._safe_notify("服务监控开始")
        self._run(self._monitor_forever())

    async def _setup_login(self) -> None:
        browser = await self._launch_browser()
        try:
            tab = await browser.get(self._config.store_url)
            await self._handle_cloudflare(tab)
            await self._ensure_logged_in(tab)
            self._notify_login_success()
            self._input_func("请在 Nodriver 浏览器中确认已经登录，然后按 Enter 结束登录初始化...")
        finally:
            await self._stop_browser(browser)

    async def _run_once(self) -> CheckResult:
        browser = await self._launch_browser()
        try:
            tab = await browser.get(self._config.store_url)
            await self._handle_cloudflare(tab)
            await self._ensure_logged_in(tab)
            return await self._check_and_order(tab)
        finally:
            await self._stop_browser(browser)

    async def _monitor_forever(self) -> None:
        browser = await self._launch_browser()
        try:
            tab = await browser.get(self._config.store_url)
            while True:
                try:
                    await self._handle_cloudflare(tab)
                    await self._ensure_logged_in(tab)
                    result = await self._check_and_order(tab)
                    print(result.message, flush=True)
                    if result.ordered:
                        return
                except Exception:
                    message = "服务监控异常"
                    print(message, flush=True)
                    self._safe_notify(message)
                await self._async_sleep(self._config.check_interval_seconds)
                tab = await self._reload_tab(tab, self._config.store_url)
        finally:
            await self._stop_browser(browser)

    async def _launch_browser(self):
        if self._browser_factory is None:
            try:
                import nodriver
            except ImportError as exc:
                raise RuntimeError("Nodriver 未安装，请先安装依赖后再运行") from exc
            return await nodriver.start(**build_nodriver_start_options(self._config))
        return await _maybe_await(self._browser_factory(**build_nodriver_start_options(self._config)))

    async def _handle_cloudflare(self, tab) -> None:
        if not await self._looks_like_cloudflare(tab):
            return
        await _call_if_exists(tab, "bring_to_front")
        message = "服务需要验证重启。"
        print(message, flush=True)
        self._safe_notify(message)
        self._input_func("请在 Nodriver 浏览器中手动完成验证，然后按 Enter 继续...")
        if not await self._looks_like_cloudflare(tab):
            self._safe_notify("服务验证重启，监控继续运行。")

    async def _looks_like_cloudflare(self, tab) -> bool:
        try:
            content = await tab.get_content()
        except Exception:
            return False
        return bool(CLOUDFLARE_TEXT_RE.search(content))

    async def _ensure_logged_in(self, tab) -> None:
        email_input = await _first_selected(tab, LOGIN_EMAIL_SELECTORS)
        if email_input is None:
            return
        password_input = await _first_selected(tab, LOGIN_PASSWORD_SELECTORS)
        if password_input is None:
            return
        await _human_type(email_input, self._config.vmiss_email, self._async_sleep)
        await _human_type(password_input, self._config.vmiss_password, self._async_sleep)
        login_button = await _first_selected(tab, LOGIN_BUTTON_SELECTORS)
        if login_button is not None:
            await login_button.click()
            await self._async_sleep(3)
        self._notify_login_success()

    async def _check_and_order(self, tab) -> CheckResult:
        content = await tab.get_content()
        order = await _find_first_order_control(tab)
        button_enabled = order is not None
        if self._config.target_product not in content:
            status = StockStatus.UNKNOWN
        else:
            status = assess_stock(content, button_enabled=button_enabled)

        if status != StockStatus.AVAILABLE:
            return CheckResult(status=status, ordered=False, message=f"{self._config.target_product} 暂无库存")

        await order.click()
        await self._async_sleep(random.uniform(0.8, 1.8))
        message = "服务可达"
        self._notifier.send_text(message)
        return CheckResult(status=status, ordered=True, message=message)

    async def _reload_tab(self, tab, url: str):
        if hasattr(tab, "reload"):
            await _maybe_await(tab.reload())
            return tab
        if hasattr(tab, "get"):
            await _maybe_await(tab.get(url))
            return tab
        return tab

    async def _stop_browser(self, browser) -> None:
        await _call_if_exists(browser, "stop")

    def _notify_login_success(self) -> None:
        if self._login_notified:
            return
        self._notifier.send_text("服务监控开始")
        self._login_notified = True

    def _safe_notify(self, content: str) -> None:
        try:
            self._notifier.send_text(content)
        except Exception as exc:
            print(f"发送通知失败：{exc}", flush=True)

    def _run(self, coroutine):
        return asyncio.run(coroutine)


class NodriverPublicChecker:
    def __init__(
        self,
        config: PublicCheckConfig,
        *,
        browser_factory: Callable[..., object] | None = None,
        input_func: Callable[[str], object] = input,
    ) -> None:
        self._config = config
        self._browser_factory = browser_factory
        self._input_func = input_func

    def check_once(self) -> CheckResult:
        return asyncio.run(self._check_once())

    async def _check_once(self) -> CheckResult:
        if self._browser_factory is None:
            try:
                import nodriver
            except ImportError as exc:
                raise RuntimeError("Nodriver 未安装，请先安装依赖后再运行") from exc
            browser = await nodriver.start(**build_nodriver_start_options(self._config))
        else:
            browser = await _maybe_await(self._browser_factory(**build_nodriver_start_options(self._config)))
        try:
            tab = await browser.get(self._config.store_url)
            if await self._looks_like_cloudflare(tab):
                print("检测到验证页面，请在 Nodriver 浏览器中手动完成验证。", flush=True)
                self._input_func("验证完成后按 Enter 继续公开检测...")
            content = await tab.get_content()
            order = await _find_first_order_control(tab)
            button_enabled = order is not None
            status = assess_stock(content, button_enabled=button_enabled)
            return CheckResult(
                status=status,
                ordered=False,
                message=f"{self._config.target_product} 公开检测结果：{status.value}；按钮可点击：{button_enabled}",
            )
        finally:
            await _call_if_exists(browser, "stop")

    async def _looks_like_cloudflare(self, tab) -> bool:
        try:
            content = await tab.get_content()
        except Exception:
            return False
        return bool(CLOUDFLARE_TEXT_RE.search(content))


async def _first_selected(tab, selectors: list[str]):
    for selector in selectors:
        try:
            element = await tab.select(selector, timeout=1)
        except Exception:
            element = None
        if element is not None:
            return element
    return None


async def _find_first_order_control(tab):
    for text in ORDER_TEXTS:
        try:
            element = await tab.find(text, best_match=True)
        except Exception:
            element = None
        if element is not None:
            return element
    return None


async def _human_type(element, text: str, async_sleep: Callable[[float], Awaitable[object]]) -> None:
    for char in text:
        await element.send_keys(char)
        await async_sleep(random.uniform(0.08, 0.16))


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def _call_if_exists(target, method_name: str) -> None:
    method = getattr(target, method_name, None)
    if method is None:
        return
    await _maybe_await(method())
