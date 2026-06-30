from pathlib import Path

from playwright.sync_api import sync_playwright

from vmiss_notify.browser import CLOUDFLARE_TEXT_RE


URL = "https://app.vmiss.com/store/us-los-angeles-cn2"
OUT = Path("output/playwright")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch_persistent_context(
            user_data_dir=".browser-profile-public",
            headless=True,
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(10000)
        title = page.title()
        print("TITLE:", title)
        body = page.locator("body").inner_text(timeout=10000)
        print("CLOUDFLARE_MATCH:", bool(CLOUDFLARE_TEXT_RE.search(f"{title}\n{body}")))
        print("BODY_START:")
        print(body[:3000])
        print("BODY_END")
        page.screenshot(path=str(OUT / "public-check.png"), full_page=True)
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
