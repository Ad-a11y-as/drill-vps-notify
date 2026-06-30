# VMISS Stock Monitor Design

## Goal

Build a Python monitor for `US.LA.CN2.Basic` on `https://app.vmiss.com/store/us-los-angeles-cn2`. When the product becomes available, the script clicks the order button and sends a text notification.

## Constraints

- The site requires login with account and password.
- The site can trigger Cloudflare human verification.
- The script must not bypass Cloudflare. When verification appears, it notifies the user and waits for manual completion in a visible browser.
- Secrets and environment-specific fields must come from `.env`, not source code.
- The script should not automatically pay.

## Architecture

The project uses Playwright with a persistent browser profile. The persistent profile keeps login cookies and any manually completed Cloudflare session state. Core logic is split into small Python modules so stock detection and notification can be tested without a browser.

## Components

- `vmiss_notify.config`: loads `.env`, validates required fields, and exposes typed settings.
- `vmiss_notify.notifier`: obtains `corpAccessToken` from the configured cloud domain and sends text messages to configured users.
- `vmiss_notify.stock`: contains browser-independent rules for deciding whether a product card is in stock.
- `vmiss_notify.browser`: drives Playwright login, Cloudflare detection, product card lookup, stock check, and order click.
- `vmiss_notify.cli`: command-line entry point for one-shot login setup, notification test, and continuous monitoring.

## Data Flow

1. Load `.env`.
2. Start a persistent Chromium context using `PLAYWRIGHT_USER_DATA_DIR`.
3. Navigate to the VMISS store page.
4. If login is required, fill username and password from `.env`.
5. If Cloudflare verification is detected, send a notification and wait for manual completion.
6. Locate the card containing `VMISS_TARGET_PRODUCT`.
7. Treat the product as out of stock if the card contains `0 Available` or `0 可用`, or if the order button is disabled.
8. If available, click `Order Now` or `立即订购`.
9. Send a success or failure notification.

## Notification API

The notification provider has two calls:

- `POST https://${MESSAGE_CLOUD_DOMAIN}/cgi/corpAccessToken/get/V2?thirdTraceId=${random}`
- `POST https://${MESSAGE_CLOUD_DOMAIN}/cgi/message/send?thirdTraceId=${random}`

The token request body contains `appId`, `appSecret`, and `permanentCode`. The message request body contains `toUser`, `msgType: text`, and `text.content`. Success is determined by `errorCode == 0`.

`corpAccessToken` is cached after retrieval. The notification client refreshes it after 6600 seconds, because the provider returns the same token before that window and can issue a renewed token from 6600 to 7200 seconds. If `expiresIn` is shorter than 6600 seconds, the client refreshes earlier with a 60 second safety margin.

## Testing

Unit tests cover `.env` parsing, notification request construction/token caching, and stock detection rules. Browser automation is kept thin and manually verifiable because the real site, login state, and Cloudflare behavior are external.
