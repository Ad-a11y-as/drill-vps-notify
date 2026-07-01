from __future__ import annotations

import asyncio
import html
import inspect
import random
import re
from dataclasses import dataclass
from datetime import datetime
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
CLOUDFLARE_CHECKBOX_SELECTORS = ['input[type="checkbox"]', 'label input[type="checkbox"]']
CLOUDFLARE_CHECKBOX_XPATHS = ['//input[@type="checkbox"]', '//label//input[@type="checkbox"]']
CLOUDFLARE_RECHECK_SECONDS = 20
BROWSER_ACTION_TIMEOUT_SECONDS = 15
PAGE_RENDER_WAIT_SECONDS = 3
SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
HTML_TAG_RE = re.compile(r"<[^>]+>")


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
                    _log("开始一轮库存检查。")
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
                _log(f"等待 {self._config.check_interval_seconds} 秒后刷新页面。")
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
        print("请在 Nodriver 浏览器中手动完成验证，程序会每 20 秒自动检查。", flush=True)
        await self._wait_until_cloudflare_cleared(tab)
        print("服务验证重启，监控继续运行。", flush=True)
        self._safe_notify("服务验证重启，监控继续运行。")

    async def _looks_like_cloudflare(self, tab) -> bool:
        _log("开始检测 Cloudflare。")
        try:
            content = await _visible_text_or_content(tab)
        except Exception as exc:
            _log(f"Cloudflare 检测异常：{exc}")
            return False
        matched = bool(CLOUDFLARE_TEXT_RE.search(content))
        _log(f"Cloudflare 检测结果：{'命中' if matched else '未命中'}。")
        if matched:
            await _click_cloudflare_checkbox_if_present(tab)
        return matched

    async def _wait_until_cloudflare_cleared(self, tab) -> None:
        max_checks = max(1, (self._config.cloudflare_wait_seconds + CLOUDFLARE_RECHECK_SECONDS - 1) // CLOUDFLARE_RECHECK_SECONDS)
        for _ in range(max_checks):
            _log(f"等待 {CLOUDFLARE_RECHECK_SECONDS} 秒后重新检测 Cloudflare。")
            await self._async_sleep(CLOUDFLARE_RECHECK_SECONDS)
            if not await self._looks_like_cloudflare(tab):
                _log("Cloudflare 验证已通过。")
                return
            print("仍在等待 Cloudflare 验证完成。", flush=True)
        raise RuntimeError("Cloudflare 真人认证等待超时")

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
            message = f"{_current_timestamp()} {self._config.target_product} 暂无库存"
            return CheckResult(status=status, ordered=False, message=message)

        await order.click()
        await self._async_sleep(random.uniform(0.8, 1.8))
        message = "服务可达"
        self._notifier.send_text(message)
        return CheckResult(status=status, ordered=True, message=message)

    async def _reload_tab(self, tab, url: str):
        _log("准备刷新页面。")
        if hasattr(tab, "reload"):
            await _await_browser_action(tab.reload(), "刷新页面")
            _log("页面刷新完成。")
            _log(f"等待页面渲染 {PAGE_RENDER_WAIT_SECONDS} 秒。")
            await self._async_sleep(PAGE_RENDER_WAIT_SECONDS)
            _log("页面渲染等待结束。")
            return tab
        if hasattr(tab, "get"):
            new_tab = await _await_browser_action(tab.get(url), "重新打开页面")
            _log("页面重新打开完成。")
            _log(f"等待页面渲染 {PAGE_RENDER_WAIT_SECONDS} 秒。")
            await self._async_sleep(PAGE_RENDER_WAIT_SECONDS)
            _log("页面渲染等待结束。")
            return new_tab or tab
        _log("当前 tab 不支持刷新或重新打开页面。")
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
        async_sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
    ) -> None:
        self._config = config
        self._browser_factory = browser_factory
        self._input_func = input_func
        self._async_sleep = async_sleep

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
                print("程序会每 20 秒自动检查验证是否完成。", flush=True)
                await self._wait_until_cloudflare_cleared(tab)
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
        _log("开始检测 Cloudflare。")
        try:
            content = await _visible_text_or_content(tab)
        except Exception as exc:
            _log(f"Cloudflare 检测异常：{exc}")
            return False
        matched = bool(CLOUDFLARE_TEXT_RE.search(content))
        _log(f"Cloudflare 检测结果：{'命中' if matched else '未命中'}。")
        if matched:
            await _click_cloudflare_checkbox_if_present(tab)
        return matched

    async def _wait_until_cloudflare_cleared(self, tab) -> None:
        max_checks = max(1, (self._config.cloudflare_wait_seconds + CLOUDFLARE_RECHECK_SECONDS - 1) // CLOUDFLARE_RECHECK_SECONDS)
        for _ in range(max_checks):
            _log(f"等待 {CLOUDFLARE_RECHECK_SECONDS} 秒后重新检测 Cloudflare。")
            await self._async_sleep(CLOUDFLARE_RECHECK_SECONDS)
            if not await self._looks_like_cloudflare(tab):
                _log("Cloudflare 验证已通过。")
                return
            print("仍在等待 Cloudflare 验证完成。", flush=True)
        raise RuntimeError("Cloudflare 真人认证等待超时")


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


async def _visible_text_or_content(tab) -> str:
    _log("准备读取页面可见文本。")
    evaluate = getattr(tab, "evaluate", None)
    if evaluate is not None:
        try:
            text = await _await_browser_action(evaluate("document.body ? document.body.innerText : ''"), "读取页面可见文本")
        except Exception:
            text = None
        if isinstance(text, str) and text.strip():
            _log(f"页面可见文本读取完成，长度 {len(text)}。")
            return text
        _log("页面可见文本为空，回退读取页面 HTML。")
    _log("准备读取页面 HTML。")
    content = await _await_browser_action(tab.get_content(), "读取页面 HTML")
    _log(f"页面 HTML 读取完成，长度 {len(content)}。")
    return _html_to_visible_text(content)


def _html_to_visible_text(content: str) -> str:
    without_scripts = SCRIPT_STYLE_RE.sub(" ", content)
    without_tags = HTML_TAG_RE.sub(" ", without_scripts)
    return html.unescape(without_tags)


async def _click_cloudflare_checkbox_if_present(tab) -> None:
    _log("准备查找 Cloudflare checkbox。")
    await _print_cloudflare_checkbox_page(tab)
    element = await _first_selected(tab, CLOUDFLARE_CHECKBOX_SELECTORS)
    if element is None:
        element = await _first_xpath(tab, CLOUDFLARE_CHECKBOX_XPATHS)
    if element is None:
        _log("未找到 Cloudflare checkbox。")
        return
    _log("找到 Cloudflare checkbox，准备点击。")

    try:
        await _await_browser_action(element.click(), "点击 Cloudflare checkbox")
        _log("已点击 Cloudflare checkbox。")
    except Exception as exc:
        _log(f"点击 Cloudflare checkbox 异常：{exc}")
        return


async def _print_cloudflare_checkbox_page(tab) -> None:
    _log("开始打印 Cloudflare checkbox 页面 HTML。")
    try:
        content = await _await_browser_action(tab.get_content(), "读取 Cloudflare checkbox 页面 HTML")
    except Exception as exc:
        _log(f"打印 Cloudflare checkbox 页面 HTML 异常：{exc}")
        return
    print("===== Cloudflare checkbox 页面 HTML 开始 =====", flush=True)
    print(content, flush=True)
    print("===== Cloudflare checkbox 页面 HTML 结束 =====", flush=True)


async def _first_xpath(tab, xpaths: list[str]):
    xpath = getattr(tab, "xpath", None)
    if xpath is None:
        return None
    for expression in xpaths:
        try:
            element = await xpath(expression)
        except Exception:
            element = None
        if isinstance(element, (list, tuple)):
            element = element[0] if element else None
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


async def _await_browser_action(value, action: str, timeout_seconds: int = BROWSER_ACTION_TIMEOUT_SECONDS):
    try:
        return await asyncio.wait_for(_maybe_await(value), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        _log(f"{action}超时（{timeout_seconds} 秒）。")
        raise
    except Exception as exc:
        _log(f"{action}异常：{exc}")
        raise


async def _call_if_exists(target, method_name: str) -> None:
    method = getattr(target, method_name, None)
    if method is None:
        return
    await _maybe_await(method())


def _log(message: str) -> None:
    print(f"{_current_timestamp()} {message}", flush=True)


def _current_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
