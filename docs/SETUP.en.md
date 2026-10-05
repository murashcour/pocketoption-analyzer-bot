# Server Setup

Step-by-step guide for deploying the bot on an Ubuntu/Debian server.

## Requirements

- Ubuntu 20.04+ / Debian 11+ / other Linux
- Python 3.10+
- SSH access to server
- PocketOption account (demo or live)

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
