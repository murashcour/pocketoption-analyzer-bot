# How to get SSID

SSID is an authorization token for PocketOption. The bot needs it to
connect to API and trade. Lives for 6-12 hours.

## What is SSID

SSID is a string like:

    42["auth",{"session":"...","isDemo":1,"uid":12345678,"platform":3,"isFastHistory":true,"isOptimized":true}]

- session — session identifier
- isDemo — 1 for demo, 0 for live account
- uid — user ID
- platform — platform

## Method 1: Chrome DevTools

1. Open PocketOption in browser
2. Log in to demo account
3. Press F12 (DevTools)
4. Go to Network tab
5. Filter by WS (WebSocket)
6. Refresh page F5
7. Connection to demo-api-eu.po.market appears
8. Click on it — Messages tab opens
9. Find outgoing message starting with 42["auth",
10. Right click — Copy message

## Method 2: SSID-Finder (Linux + VNC)

If you are on Linux server without GUI but with VNC:

1. Start Xvfb (virtual display):

       Xvfb :99 -screen 0 1280x800x24 &
       export DISPLAY=:99

2. Start x11vnc:

       x11vnc -display :99 -forever -nopw -rfbport 5905 &

3. Connect via VNC client to server:5905

4. Inside VNC open Chrome — go to pocketoption.com

5. Install SSID-Finder extension

6. Log in — SSID-Finder will show current SSID

## IMPORTANT: common quote error

When copying SSID, it is easy to capture an extra character.

Check the string after uid.

Correct:

    "uid":94604880,"platform":3

Incorrect (extra quote):

    "uid":94604880","platform":3

If you see error:

    PocketOptionError: Failed to parse ssid: JSON parsing error

Just remove the extra quote.

## How to save SSID

Method 1 — environment variable:

    export PO_SSID='42["auth",{...}]'

Method 2 — file (permanent):

    echo '42["auth",{...}]' > ~/.po_ssid
    chmod 600 ~/.po_ssid

Then on start:

    export PO_SSID="$(cat ~/.po_ssid)"

## Verify SSID

Before starting bot, verify SSID:

    python3 -c "
    import json, os
    s = os.getenv('PO_SSID', '')
    if not s:
        s = open(os.path.expanduser('~/.po_ssid')).read().strip()
    i = s.find('{'); j = s.rfind('}')
    obj = json.loads(s[i:j+1])
    print(f'SSID valid')
    print(f'  uid: {obj[\"uid\"]}')
    print(f'  isDemo: {obj[\"isDemo\"]}')
    "

Should print uid and isDemo without errors.

## Full connection check

    python3 -c "
    import asyncio, os
    from BinaryOptionsToolsV2 import PocketOptionAsync

    async def main():
        async with PocketOptionAsync(ssid=os.getenv('PO_SSID')) as c:
            bal = await c.balance()
            print(f'Balance: \${bal:.2f}')
            candles = await c.get_candles('EURUSD_otc', 60, 5)
            print(f'Candles: {len(candles) if candles else 0}')

    asyncio.run(main())
    "

If you see balance and candles — everything works.

## When SSID dies

SSID is invalidated:

- 6-12 hours after obtaining
- After password change
- After logout in browser
- After login from another device/IP

Signs:

- Error Core(ChannelReceiver(Closed))
- Timeouts on candle fetching
- Balance not returned

Solution: get SSID again.

## Demo vs live account

SSID has field isDemo:

- isDemo: 1 — demo account (safe, for tests)
- isDemo: 0 — live account (real money)

For testing, always use demo (isDemo: 1).

## Security

SSID = full account access. Never publish:

- Do not commit to git
- Do not send in chats
- Do not post in screenshots
- Store only in ~/.po_ssid (chmod 600)

If SSID leaked — change PocketOption password and get new SSID.
