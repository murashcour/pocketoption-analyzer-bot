# Troubleshooting

Common errors and solutions.

## SSID errors

### PocketOptionError: Failed to parse ssid

Cause: extra quote after uid in SSID.

Check the string:

    "uid":94604880","platform":3

Should be:

    "uid":94604880,"platform":3

Solution: remove extra quote, rewrite SSID.

### Core(ChannelReceiver(Closed))

Cause: SSID expired or invalid.

Signs:

- Balance not returned
- Candles not coming
- Timeouts

Solution:

1. Get new SSID (see docs/SSID.en.md)
2. Restart bot

### Invalid asset

Cause: wrong pair name.

Correct: EURUSD_otc (with underscore and _otc)

Incorrect: EURUSD, EUR/USD OTC, eurusd_otc

## API errors

### Candle fetch timeout

Cause: SSID works, but API is slow.

Signs:

    WARNING | Candle timeout (1/3)
    WARNING | Candle timeout (2/3)
    WARNING | Candle timeout (3/3)

Solution:

1. Check internet
2. Wait 30 seconds (bot waits itself)
3. If repeats — refresh SSID

### get_candles_live hangs

Cause: async-generator. Does not work with await — need async for.

Wrong:

    result = await client.get_candles_live(...)

Correct:

    async for closed, forming in client.get_candles_live(...):
        ...

## Balance problems

### Balance not updating

Cause: freeze on open trades.

Solution: wait for all trades to close.

### Balance drops fast

Cause: series of losses.

Signs:

    LOSS -$1.50
    LOSS -$3.00
    LOSS -$6.00

Solution:

1. Check settings (MIN_CONFIRMATIONS, RSI)
2. Reduce base_percent (risk)
3. Stop for a day
4. Check winrate in log

## Trading problems

### Bot does not open trades

Reasons:

1. Pair payout < 85% — skips
2. No signal (RSI in neutral zone)
3. ATR < 0.1% — flat
4. S/R blocks

Check in log:

    Skip [TIME] No signal
    [PAIR] Payout 78.0% outside [85, 92]%
    [PAIR] Price close to resistance

### Trade open error

Cause: insufficient balance, PocketOption limit.

Check:

    Trade open error $12.00: ...

Solution:

1. Reduce base_percent
2. Top up demo balance
3. Use fixed bets (balance < $100)

## Vim / SSH problems

### Vim does not save file

Cause: file opened read-only, or no permission.

Check:

    ls -la file

Solution:

    sudo chown ps4:ps4 file
    vim file

### SSH disconnect during bot work

Cause: bot not in screen.

Solution:

    screen -S bot
    source venv/bin/activate
    python analyzer_bot.py
    Ctrl+A, D

Or via nohup:

    nohup python analyzer_bot.py > bot.out 2>&1 &

### Error "screen not found"

Cause: screen not installed.

Solution:

    sudo apt install -y screen

## Python errors

### ModuleNotFoundError: No module named 'BinaryOptionsToolsV2'

Cause: virtual environment not activated.

Solution:

    cd ~/bot
    source venv/bin/activate
    python analyzer_bot.py

Check:

    which python
    # Should be: /home/ps4/bot/venv/bin/python

### SyntaxError on startup

Cause: error in code (accidental edit).

Solution:

1. Check syntax:

       python -c "import ast; ast.parse(open('analyzer_bot.py').read())"

2. Download fresh version:

       cd ~/bot
       git pull

## Logs

### Where logs are

    ~/bot/analyzer_bot.log

### How to view in real time

    tail -f ~/bot/analyzer_bot.log

### Log file too large

Cause: long work, many messages.

Solution:

    > ~/bot/analyzer_bot.log

Command clears file (without deleting).

## How to fully reinstall bot

1. Stop bot:

       touch ~/bot/stop.flag
       # Wait 30 sec

2. Save SSID and config:

       cp ~/bot/config.json ~/config.json.backup
       cp ~/.po_ssid ~/.po_ssid.backup

3. Delete:

       rm -rf ~/bot

4. Install again:

       cd ~
       git clone https://github.com/murachour/pocketoption-analyzer-bot.git bot
       cd bot
       python3 -m venv venv
       source venv/bin/activate
       pip install -r requirements.txt

5. Restore config:

       cp ~/config.json.backup ~/bot/config.json

6. Run:

       screen -S bot
       source venv/bin/activate
       export PO_SSID="$(cat ~/.po_ssid)"
       python analyzer_bot.py

## What to do if nothing helps

1. Stop bot (Ctrl+C in screen)
2. Save log:

       cp ~/bot/analyzer_bot.log ~/analyzer_bot.log.$(date +%s)

3. Check basic:

       cd ~/bot
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

4. If balance returns — problem in code, restart bot
5. If not — refresh SSID, try again

## When to ask for help

Collect info:

- Contents of ~/analyzer_bot.log (last 100 lines)
- SSID check output
- What you did before error

This helps find the problem faster.
