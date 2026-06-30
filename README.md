# drill-vps-notify

Python 脚本，用 Playwright 监控 VMISS 洛杉矶 CN2 GIA 页面中 `.env` 配置的套餐。检测到补货后会点击“立即订购 / Order Now”，并通过企业消息接口发送通知。

脚本不会绕过 Cloudflare 真人认证，也不会自动付款。遇到真人认证时，会发送通知并等待你在打开的浏览器里手动完成。

## 功能

- 使用 VMISS 账号密码登录。
- 使用 Playwright 持久化浏览器目录保存登录态。
- 监控 `https://app.vmiss.com/store/us-los-angeles-cn2`。
- 通过 `VMISS_TARGET_PRODUCT` 配置要检查的套餐，例如 `US.LA.CN2.Basic`、`US.LA.CN2.Pro`、`US.LA.CN2.Elite`。
- 识别 `0 Available` / `0 可用` 和不可点击按钮为无货。
- 有货时点击该套餐卡片内的下单按钮，支持 `Order Now`、`立即订购`、`立即订阅` 等中英文文案。
- 通过 `.env` 配置消息接口字段。
- `corpAccessToken` 会缓存，6600 秒后主动续期；如果接口返回更短的 `expiresIn`，会提前 60 秒刷新。

## 安装

本项目推荐使用 `uv` 管理虚拟环境和依赖。

### Windows

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv venv
.\.venv\Scripts\Activate.ps1
uv pip install -e .
uv run python -m playwright install chromium
```

### macOS / Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv
source .venv/bin/activate
uv pip install -e .
uv run python -m playwright install chromium
```

Linux 如果运行浏览器时报缺少系统依赖，可再执行：

```bash
uv run python -m playwright install-deps chromium
```

## 配置

复制 `.env.example` 为 `.env`，然后填写真实值：

Windows:

```powershell
Copy-Item .env.example .env
```

macOS / Linux:

```bash
cp .env.example .env
```

核心配置：

```env
VMISS_EMAIL=your-email@example.com
VMISS_PASSWORD=your-password

VMISS_STORE_URL=https://app.vmiss.com/store/us-los-angeles-cn2
VMISS_TARGET_PRODUCT=US.LA.CN2.Basic
CHECK_INTERVAL_SECONDS=30
HEADLESS=false
PLAYWRIGHT_USER_DATA_DIR=.browser-profile
CLOUDFLARE_WAIT_SECONDS=900

MESSAGE_CLOUD_DOMAIN=your-cloud-domain.example.com
MESSAGE_APP_ID=your-app-id
MESSAGE_APP_SECRET=your-app-secret
MESSAGE_PERMANENT_CODE=your-permanent-code
MESSAGE_TO_USERS=USER1,USER2
TOKEN_REFRESH_AFTER_SECONDS=6600
```

`MESSAGE_CLOUD_DOMAIN` 只填域名，不需要 `https://`。

## 使用

以下命令在 Windows PowerShell、macOS Terminal、Linux shell 中相同。Windows 如果没有激活虚拟环境，也可以在命令前加 `uv run`，例如 `uv run vmiss-monitor public-check`。

首次使用建议先初始化登录态：

```bash
vmiss-monitor login
```

如果出现 Cloudflare 真人认证，在打开的浏览器中手动完成。登录完成后回到终端按 Enter。

发送测试通知：

```bash
vmiss-monitor test-notify
```

执行一次库存检查：

```bash
vmiss-monitor once
```

只测试公开页面监测是否能定位套餐并判断库存，不登录、不通知、不点击下单：

```bash
vmiss-monitor public-check
```

如果该命令提示触发 Cloudflare 真人认证，需要在打开的 Chromium 窗口中手动完成验证；验证通过后命令会继续定位 `VMISS_TARGET_PRODUCT` 指定的套餐并输出库存判断结果。这个命令适合在正式监控前做完整性检查。

持续监控：

```bash
vmiss-monitor monitor
```

## Cloudflare 处理

脚本只做合规处理：

- 检测到 Cloudflare 页面后发送通知，并把浏览器页面置前，等待你在可见浏览器中手动验证。
- 验证完成后继续监控。
- 等待超过 `CLOUDFLARE_WAIT_SECONDS` 会报错并在下一轮重试。

## 测试

```bash
uv run python -m unittest discover -s tests -v
uv run python -m compileall src tests
```

## 注意

- 建议保持 `HEADLESS=false`，方便处理登录和 Cloudflare。
- macOS / Linux 桌面环境同样建议保持 `HEADLESS=false`；如果是无桌面的 Linux 服务器，需要先配置 X11、Wayland、VNC 或其他可见浏览器环境，否则无法人工处理 Cloudflare。
- 脚本点击下单后会停止监控并通知你，不会自动付款。
- 如果 VMISS 页面结构或按钮文案大幅变化，需要更新 `src/vmiss_notify/browser.py` 中的定位逻辑。
