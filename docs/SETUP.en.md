Step-by-step guide for deploying the bot on a Debian-based server.
Recommended: Ubuntu 24.04.5 LTS (tested).

## What the bot does

- 📊 Multi-timeframe analysis: 1m + 3m + 10m
- 🌍 Real pairs (Currency / Forex): OTC + real currency pairs
- 💰 Martingale: 1% -> 2% -> 4% (no 4th step)
- 🔄 Pair rotation: switch on 3 skips or losing series
- 💹 Payout filter: OTC [85, 92]%, Real [75, 92]%
- 🛡 Drawdown protection: pause at -30%, stop after 2nd
- 📰 Pause on important news (TradingView Calendar)
- ⚙️ Interactive menu: 30+ settings
- 🖥️ Runs in screen: survives SSH disconnection

### Real pairs details

- **Currency only** (forex) — crypto excluded
- **Mon-Fri only** — Forex closed on weekends (Sat-Sun)
- **Payout 75-92%** — lower than OTC
- **Day check** — by `Europe/Moscow` timezone

### Protection details

- **Drawdown 30%** — when balance drops:
  - 1st drawdown → pause 30 min
  - 2nd drawdown → STOP (wait for reaction)
- **News pause** — 10 min before and 20 min after:
  - High + Medium importance
  - USD, EUR, GBP, JPY
  - TradingView Calendar

## Requirements

- **Debian-based distribution:**
  - Ubuntu 24.04.5 LTS (recommended, tested)
  - Debian 12+ (compatible)
- Python 3.10+
- SSH access to server
- PocketOption account (demo or live)
- **VDS in a recommended country** (see section below)

## Server Location

The bot connects to the PocketOption API. If the server IP is blocked
by the broker — the bot will not be able to connect.

### Verified location

**🇭🇰 Hong Kong** — tested in production: stable connection,
reasonable price.

- **Platform:** HostVDS (OpenStack, NVMe)
- **Cost:** ~$4-5/month
- **Payment:** Mir card, SBP, crypto, WebMoney, Alipay
- **IP not disclosed** (security)

⚠️ Hong Kong region may be temporarily unavailable for VDS ordering.
Check in the hosting panel when ordering.

### Recommended (community experience)

- 🇹🇷 Turkey
- 🇰🇿 Kazakhstan
- 🇹🇭 Thailand
- 🇷🇸 Serbia

Not personally tested. Use as a guide when choosing a VDS.

### Not recommended

Binary options regulatory restrictions:

- 🇪🇺 EU (ESMA)
- 🇺🇸 USA (CFTC)
- 🇬🇧 UK (FCA)
- 🇦🇺 Australia (ASIC)
- 🇨🇦 Canada
- 🇮🇱 Israel

Sanctions (may be blocked):

- 🇷🇺 Russia
- 🇧🇾 Belarus
- 🇮🇷 Iran
- 🇰🇵 North Korea

### Availability check

Before installing the bot, verify that PocketOption is accessible
from the server:

    curl -sI https://pocketoption.com | head -3

Expected: HTTP/2 200 or 302.

    curl -sI https://demo-api-eu.po.market | head -3

Expected: HTTP/2 403 (this is normal — API requires authorization).

### Full connection test

After installing dependencies and obtaining SSID, verify:

    python3 -c "
    import asyncio, os
    from BinaryOptionsToolsV2 import PocketOptionAsync
    async def main():
        async with PocketOptionAsync(ssid=os.getenv('PO_SSID')) as c:
            bal = await c.balance()
            print(f'✅ Balance: \${bal:.2f}')
            candles = await c.get_candles('EURUSD_otc', 60, 5)
            print(f'✅ Candles: {len(candles) if candles else 0}')
    asyncio.run(main())
    "

If you see balance and candles — the location is suitable.

### What to do if IP is blocked

Symptoms:

- Timeouts on connection
- Error Core(ChannelReceiver(Closed))
- Balance not returned
- Candles not coming

Solutions:

1. Change VDS location in hosting panel
2. Restart the bot
3. Check access with the test above

### Important

- Recommendation list is based on community experience
- PocketOption does not publish an official allowed countries list
- The only reliable check — run the test from a specific IP


## Step 1. System packages

Update system and install base packages:

    sudo apt update
    sudo apt install -y python3 python3-pip python3-venv git screen

- python3 — Python interpreter
- python3-venv — virtual environment
- git — to clone repository
- screen — to run bot in background

## Step 2. Clone repository

    cd ~
    git clone https://github.com/murachour/pocketoption-analyzer-bot.git bot
    cd bot

## Step 3. Virtual environment

Create venv and activate:

    python3 -m venv venv
    source venv/bin/activate

Check that Python is in venv:

    which python
    python --version

Should show a path inside venv.

## Step 4. Dependencies

    pip install --upgrade pip
    pip install -r requirements.txt

Main dependency — BinaryOptionsToolsV2.

## Step 5. SSID token

SSID — authorization token for PocketOption. Details in docs/SSID.en.md.

Briefly:
1. Open PocketOption in browser
2. Log in
3. F12 — Network — WS
4. Find message 42["auth",...
5. Copy entirely

Save SSID to file:

    echo '42["auth",{...}]' > ~/.po_ssid
    chmod 600 ~/.po_ssid

Verify:

    python3 -c "
    import json, os
    s = open(os.path.expanduser('~/.po_ssid')).read().strip()
    i = s.find('{'); j = s.rfind('}')
    obj = json.loads(s[i:j+1])
    print(f'SSID valid, uid={obj[\"uid\"]}')
    "

## Step 6. Run bot

Run in screen (so it survives SSH disconnect):

    screen -S bot
    source venv/bin/activate
    export PO_SSID="$(cat ~/.po_ssid)"
    python analyzer_bot.py

Detach from screen: Ctrl+A, then D.

Return to bot: screen -r bot.

## Step 7. Stop bot

Method 1 — from screen: Ctrl+C

Method 2 — from another terminal:

    touch ~/bot/stop.flag

Bot will finish current series and stop.

## Autostart on reboot (optional)

If you want bot to start automatically:

    crontab -e

Add line:

    @reboot sleep 30 && cd ~/bot && screen -dmS bot bash -c 'source venv/bin/activate && export PO_SSID="$(cat ~/.po_ssid)" && python analyzer_bot.py'

After reboot, bot starts in 30 seconds.

## Updating bot

If repository has new changes:

    cd ~/bot
    git pull
    pip install -r requirements.txt

Restart:

    screen -r bot
    Ctrl+C
    python analyzer_bot.py

## Useful commands

Check if bot is running:

    ps aux | grep analyzer_bot | grep -v grep

View log:

    tail -f ~/bot/analyzer_bot.log

Check if stop.flag exists:

    ls -la ~/bot/stop.flag

Check balance:

    source venv/bin/activate
    export PO_SSID="$(cat ~/.po_ssid)"
    python3 -c "
    import asyncio, os
    from BinaryOptionsToolsV2 import PocketOptionAsync
    async def main():
        async with PocketOptionAsync(ssid=os.getenv('PO_SSID')) as c:
            print('Balance:', await c.balance())
    asyncio.run(main())
    "

## Problems and solutions

See docs/TROUBLESHOOTING.en.md.

## Important

- Do not run two bot instances at the same time (one SSID — one session)
- Demo account: top up virtual balance in PocketOption UI
- SSID lives 6-12 hours, refresh on error
- Logs are stored in analyzer_bot.log, do not delete when debugging
