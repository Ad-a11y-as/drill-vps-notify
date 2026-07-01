from __future__ import annotations

import re
import time
from dataclasses import dataclass

from .config import AppConfig, PublicCheckConfig
from .notifier import MessageNotifier
from .stock import StockStatus, assess_stock


ORDER_TEXT_RE = re.compile(r"(Order Now|立即订购|立即订購|立即订阅|立即訂閱|立即订閱)", re.IGNORECASE)
CLOUDFLARE_TEXT_RE = re.compile(
    r"(Cloudflare|Verify you are human|Checking if the site connection is secure|请完成|真人认证|安全验证|自动程序|请稍候)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CheckResult:
    status: StockStatus
    ordered: bool
    message: str


class LoginStateNotifier:
    def __init__(self, notifier: MessageNotifier) -> None:
        self._notifier = notifier
        self._sent = False

    def notify_success(self, target_product: str) -> None:
        if self._sent:
            return
        self._notifier.send_text("服务监控开始")
        self._sent = True


def bring_page_to_front(page) -> None:
    try:
        page.bring_to_front()
    except Exception:
        pass


def _response_indicates_cloudflare(response) -> bool:
    if response is None:
        return False
    try:
        status = response.status
        url = response.url
    except Exception:
        return False
    return status == 403 or "/cdn-cgi/challenge" in url


def build_launch_options(config: AppConfig | PublicCheckConfig) -> dict:
    options = {
        "user_data_dir": str(config.user_data_dir),
        "headless": config.headless,
        "viewport": {"width": 1280, "height": 900},
        "locale": "zh-CN",
    }
    if config.browser_channel:
        options["channel"] = config.browser_channel
    return options


class VmissMonitor:
    def __init__(self, config: AppConfig, notifier: MessageNotifier) -> None:
        self._config = config
        self._notifier = notifier
        self._login_notifier = LoginStateNotifier(notifier)

    def setup_login(self) -> None:
        with self._launch_context() as context:
            page = context.new_page()
            response = page.goto(self._config.store_url, wait_until="domcontentloaded")
            self._handle_cloudflare(page, response)
            self._ensure_logged_in(page)
            self._login_notifier.notify_success(self._config.target_product)
            input("请在打开的浏览器中确认已经登录，然后按 Enter 结束登录初始化...")

    def run_once(self) -> CheckResult:
        with self._launch_context() as context:
            page = context.new_page()
            response = page.goto(self._config.store_url, wait_until="domcontentloaded")
            self._handle_cloudflare(page, response)
            self._ensure_logged_in(page)
            return self._check_and_order(page)

    def monitor_forever(self) -> None:
        self._safe_notify("服务监控开始")
        while True:
            try:
                result = self.run_once()
                print(result.message, flush=True)
                if result.ordered:
                    return
            except Exception:
                message = "服务监控异常"
                print(message, flush=True)
                self._safe_notify(message)
            time.sleep(self._config.check_interval_seconds)

    def _launch_context(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("Playwright 未安装，请先运行 pip install -r requirements.txt") from exc

        playwright = sync_playwright().start()
        context = playwright.chromium.launch_persistent_context(**build_launch_options(self._config))
        return _ContextManager(playwright, context)

    def _ensure_logged_in(self, page) -> None:
        if self._is_login_form_visible(page):
            page.fill(self._first_selector(page, LOGIN_EMAIL_SELECTORS), self._config.vmiss_email)
            page.fill(self._first_selector(page, LOGIN_PASSWORD_SELECTORS), self._config.vmiss_password)
            self._click_first(page, LOGIN_BUTTON_SELECTORS)
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            self._handle_cloudflare(page)
            response = page.goto(self._config.store_url, wait_until="domcontentloaded")
            self._handle_cloudflare(page, response)
        self._login_notifier.notify_success(self._config.target_product)

    def _is_login_form_visible(self, page) -> bool:
        for selector in LOGIN_EMAIL_SELECTORS:
            if page.locator(selector).first.is_visible(timeout=1000):
                return True
        login_links = page.get_by_role("link", name=re.compile(r"(Login|登录|登入|Sign In)", re.IGNORECASE))
        if login_links.count() > 0:
            login_links.first.click()
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            return any(page.locator(selector).first.is_visible(timeout=1000) for selector in LOGIN_EMAIL_SELECTORS)
        return False

    def _handle_cloudflare(self, page, response=None) -> None:
        if not self._wait_until_cloudflare_or_product(page, response):
            return

        bring_page_to_front(page)
        message = "服务需要验证重启。"
        print(message, flush=True)
        self._safe_notify(message)
        deadline = time.time() + self._config.cloudflare_wait_seconds
        while time.time() < deadline:
            if not self._looks_like_cloudflare(page):
                self._safe_notify("服务验证重启，监控继续运行。")
                return
            time.sleep(5)
        raise RuntimeError("Cloudflare 真人认证等待超时")

    def _wait_until_cloudflare_or_product(self, page, response=None) -> bool:
        if _response_indicates_cloudflare(response):
            return True
        deadline = time.time() + 15
        while time.time() < deadline:
            if self._looks_like_cloudflare(page):
                return True
            try:
                if page.get_by_text(self._config.target_product, exact=True).first.is_visible(timeout=1000):
                    return False
            except Exception:
                pass
            time.sleep(1)
        return self._looks_like_cloudflare(page)

    def _looks_like_cloudflare(self, page) -> bool:
        title = ""
        body = ""
        try:
            title = page.title()
            body = page.locator("body").inner_text(timeout=3000)
        except Exception:
            return False
        content = f"{title}\n{body}"
        return bool(CLOUDFLARE_TEXT_RE.search(content))

    def _check_and_order(self, page) -> CheckResult:
        card = self._find_product_card(page)
        card_text = card.inner_text(timeout=10000)
        order = self._find_order_control(card)
        button_enabled = self._is_order_control_enabled(order)
        status = assess_stock(card_text, button_enabled=button_enabled)

        if status != StockStatus.AVAILABLE:
            return CheckResult(status=status, ordered=False, message=f"{self._config.target_product} 暂无库存")

        order.click(timeout=10000)
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        message = "服务可达"
        self._notifier.send_text(message)
        return CheckResult(status=status, ordered=True, message=message)

    def _find_product_card(self, page):
        product = page.get_by_text(self._config.target_product, exact=True).first
        product.wait_for(timeout=30000)
        return product.locator(
            "xpath=ancestor::*[.//*[contains(normalize-space(.), 'Order Now') or contains(normalize-space(.), '立即订购') or contains(normalize-space(.), '立即订購') or contains(normalize-space(.), '立即订阅') or contains(normalize-space(.), '立即訂閱') or contains(normalize-space(.), '立即订閱')]][1]"
        )

    def _find_order_control(self, card):
        by_role_button = card.get_by_role("button", name=ORDER_TEXT_RE)
        if by_role_button.count() > 0:
            return by_role_button.first
        by_role_link = card.get_by_role("link", name=ORDER_TEXT_RE)
        if by_role_link.count() > 0:
            return by_role_link.first
        return card.get_by_text(ORDER_TEXT_RE).first

    def _is_order_control_enabled(self, locator) -> bool:
        try:
            if not locator.is_visible(timeout=3000):
                return False
            disabled = locator.evaluate(
                """node => {
                    const el = node.closest('button,a') || node;
                    const cls = (el.className || '').toString().toLowerCase();
                    return Boolean(el.disabled)
                        || el.getAttribute('aria-disabled') === 'true'
                        || cls.includes('disabled')
                        || cls.includes('opacity-50')
                        || cls.includes('cursor-not-allowed');
                }"""
            )
            return not disabled
        except Exception:
            return False

    def _first_selector(self, page, selectors: list[str]) -> str:
        for selector in selectors:
            if page.locator(selector).first.is_visible(timeout=1000):
                return selector
        raise RuntimeError(f"找不到可见输入框：{selectors}")

    def _click_first(self, page, selectors: list[str]) -> None:
        for selector in selectors:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=1000):
                locator.click()
                return
        raise RuntimeError("找不到登录按钮")

    def _safe_notify(self, content: str) -> None:
        try:
            self._notifier.send_text(content)
        except Exception as exc:
            print(f"发送通知失败：{exc}", flush=True)


class VmissPublicChecker:
    def __init__(self, config: PublicCheckConfig) -> None:
        self._config = config

    def check_once(self) -> CheckResult:
        with self._launch_context() as context:
            page = context.new_page()
            response = page.goto(self._config.store_url, wait_until="domcontentloaded")
            self._handle_cloudflare(page, response)
            card = self._find_product_card(page)
            card_text = card.inner_text(timeout=10000)
            order = self._find_order_control(card)
            button_enabled = self._is_order_control_enabled(order)
            status = assess_stock(card_text, button_enabled=button_enabled)
            return CheckResult(
                status=status,
                ordered=False,
                message=(
                    f"{self._config.target_product} 公开检测结果：{status.value}；"
                    f"按钮可点击：{button_enabled}"
                ),
            )

    def _launch_context(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("Playwright 未安装，请先运行 pip install -r requirements.txt") from exc

        playwright = sync_playwright().start()
        context = playwright.chromium.launch_persistent_context(**build_launch_options(self._config))
        return _ContextManager(playwright, context)

    def _handle_cloudflare(self, page, response=None) -> None:
        if not self._wait_until_cloudflare_or_product(page, response):
            return

        bring_page_to_front(page)
        print("检测到 Cloudflare 真人认证，已打开浏览器窗口，请手动点击完成验证。", flush=True)
        deadline = time.time() + self._config.cloudflare_wait_seconds
        while time.time() < deadline:
            if not self._looks_like_cloudflare(page):
                print("Cloudflare 真人认证已通过，继续公开检测。", flush=True)
                return
            time.sleep(5)
        raise RuntimeError("Cloudflare 真人认证等待超时")

    def _wait_until_cloudflare_or_product(self, page, response=None) -> bool:
        if _response_indicates_cloudflare(response):
            return True
        deadline = time.time() + 15
        while time.time() < deadline:
            if self._looks_like_cloudflare(page):
                return True
            try:
                if page.get_by_text(self._config.target_product, exact=True).first.is_visible(timeout=1000):
                    return False
            except Exception:
                pass
            time.sleep(1)
        return self._looks_like_cloudflare(page)

    def _looks_like_cloudflare(self, page) -> bool:
        try:
            title = page.title()
            body = page.locator("body").inner_text(timeout=3000)
        except Exception:
            return False
        return bool(CLOUDFLARE_TEXT_RE.search(f"{title}\n{body}"))

    def _find_product_card(self, page):
        product = page.get_by_text(self._config.target_product, exact=True).first
        product.wait_for(timeout=30000)
        return product.locator(
            "xpath=ancestor::*[.//*[contains(normalize-space(.), 'Order Now') or contains(normalize-space(.), '立即订购') or contains(normalize-space(.), '立即订購') or contains(normalize-space(.), '立即订阅') or contains(normalize-space(.), '立即訂閱') or contains(normalize-space(.), '立即订閱')]][1]"
        )

    def _find_order_control(self, card):
        by_role_button = card.get_by_role("button", name=ORDER_TEXT_RE)
        if by_role_button.count() > 0:
            return by_role_button.first
        by_role_link = card.get_by_role("link", name=ORDER_TEXT_RE)
        if by_role_link.count() > 0:
            return by_role_link.first
        return card.get_by_text(ORDER_TEXT_RE).first

    def _is_order_control_enabled(self, locator) -> bool:
        try:
            if not locator.is_visible(timeout=3000):
                return False
            disabled = locator.evaluate(
                """node => {
                    const el = node.closest('button,a') || node;
                    const cls = (el.className || '').toString().toLowerCase();
                    return Boolean(el.disabled)
                        || el.getAttribute('aria-disabled') === 'true'
                        || cls.includes('disabled')
                        || cls.includes('opacity-50')
                        || cls.includes('cursor-not-allowed');
                }"""
            )
            return not disabled
        except Exception:
            return False


class _ContextManager:
    def __init__(self, playwright, context) -> None:
        self._playwright = playwright
        self._context = context

    def __enter__(self):
        return self._context

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._context.close()
        self._playwright.stop()


LOGIN_EMAIL_SELECTORS = [
    'input[type="email"]',
    'input[name="email"]',
    'input[name="username"]',
    "#inputEmail",
    "#email",
]

LOGIN_PASSWORD_SELECTORS = [
    'input[type="password"]',
    'input[name="password"]',
    "#inputPassword",
    "#password",
]

LOGIN_BUTTON_SELECTORS = [
    'button[type="submit"]',
    'input[type="submit"]',
    'button:has-text("Login")',
    'button:has-text("登录")',
    'button:has-text("登入")',
    'button:has-text("Sign In")',
]
