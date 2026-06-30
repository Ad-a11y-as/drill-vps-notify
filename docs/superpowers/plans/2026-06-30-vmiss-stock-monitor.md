# VMISS Stock Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python Playwright monitor that logs into VMISS, watches `US.LA.CN2.Basic`, clicks order when available, and sends configured text notifications.

**Architecture:** Keep browser automation separate from pure business logic. Test configuration loading, notification transport, and stock rules without launching a browser. Use a persistent Playwright profile to retain login and manual Cloudflare verification state.

**Tech Stack:** Python 3.10+, Playwright for browser automation, standard library `urllib` for notification HTTP calls, `unittest` for tests.

---

## File Structure

- `requirements.txt`: declares Playwright dependency.
- `.env.example`: documents all runtime configuration.
- `.gitignore`: excludes `.env`, browser profile, caches, and Python artifacts.
- `README.md`: setup and operating instructions.
- `src/vmiss_notify/config.py`: `.env` loading and typed settings.
- `src/vmiss_notify/notifier.py`: token retrieval and text message sending.
- `src/vmiss_notify/stock.py`: stock decision helpers.
- `src/vmiss_notify/browser.py`: Playwright workflow.
- `src/vmiss_notify/cli.py`: command-line entry point.
- `tests/test_config.py`: config tests.
- `tests/test_notifier.py`: notifier tests.
- `tests/test_stock.py`: stock rule tests.

## Tasks

### Task 1: Configuration

- [ ] Write tests for loading `.env` values and parsing list/boolean/integer fields.
- [ ] Run config tests and verify they fail because `vmiss_notify.config` does not exist.
- [ ] Implement `AppConfig`, `.env` parser, and validation.
- [ ] Run config tests and verify they pass.

### Task 2: Notification Client

- [ ] Write tests using a fake transport for token request, token reuse before 6600 seconds, token renewal after 6600 seconds, message request, and non-zero `errorCode`.
- [ ] Run notifier tests and verify they fail because `vmiss_notify.notifier` does not exist.
- [ ] Implement `MessageNotifier`, token caching, request JSON bodies, and response validation.
- [ ] Run notifier tests and verify they pass.

### Task 3: Stock Rules

- [ ] Write tests for `0 Available`, `0 可用`, disabled button, and available button cases.
- [ ] Run stock tests and verify they fail because `vmiss_notify.stock` does not exist.
- [ ] Implement `StockStatus` and `assess_stock`.
- [ ] Run stock tests and verify they pass.

### Task 4: Browser Workflow

- [ ] Implement Playwright browser workflow that uses `assess_stock`.
- [ ] Support login, Cloudflare manual wait, target product card lookup, and order click.
- [ ] Keep no-payment behavior by stopping after the order button click.

### Task 5: CLI and Docs

- [ ] Implement commands: `monitor`, `login`, and `test-notify`.
- [ ] Add `.env.example`, `.gitignore`, `requirements.txt`, and `README.md`.
- [ ] Run all unit tests.
- [ ] Run Python compile check.
