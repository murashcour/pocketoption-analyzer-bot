# PocketOption Analyzer Bot

[Russian](README.md) | [English](README.en.md)

Automated trading bot for PocketOption (demo/live account).
Analyzes OTC and Real currency pairs, generates signals, and trades
using a martingale strategy within each series.

## Important

**This project was built with DeepSeek AI assistance** (deepseek.com).

Architecture, strategy logic, and code were developed through
conversations with an AI assistant. All strategy decisions were made
by the project owner; AI helped with implementation, debugging,
and documentation.

**The bot is intended for DEMO accounts.** Use on a live account
at your own risk. The author is not responsible for financial losses.

## Features

- 📊 Multi-timeframe analysis: 1m + 5m + 15m
- 🎯 Indicators: SMA14, EMA20, EMA50, RSI14
- 📈 Filters: S/R levels, ATR (volatility), candlestick patterns
- 🌍 Real pairs (Currency / Forex): OTC + real currency pairs
- 💰 Martingale: up to 4 steps (1% -> 2% -> 4% -> 8%)
- 🔄 Pair rotation: switch on skips or losing series
- 💹 Payout filter: OTC [90, 95]%, Real [85, 92]%
- 🔍 Payout check before steps 2/3/4: if payout drops — change pair
- ⚡ Step 2 chase (`pure_martingale`): by original signal, 0 sec
- 🛡 Drawdown protection: STOP at -30% (1 drawdown, no pause)
- 🛑 Pause after 4 consecutive losses: 30 minutes
- 📰 Pause on important news (TradingView Calendar)
- ⏱ Auto-stop after 24 hours
- ⚙️ Interactive menu: 30+ settings
- 🖥️ Runs in screen: survives SSH disconnection
- 🎮 Manual analyzer mode (`--show-only` / `--confirm`)

## Requirements

- **Debian-based server:**
  - Ubuntu 24.04.5 LTS (recommended, tested)
  - Debian 12+ (compatible)
- Python 3.10+
- PocketOption account (demo or live)
- SSID token (obtained via browser, lives 6-12 hours)
- **VDS in a recommended country** (see [docs/SETUP.en.md](docs/SETUP.en.md)).
  **Not Russia:** PocketOption blocks IP from RU (sanctions).
  Need Hong Kong, Turkey, Kazakhstan, Thailand, Serbia.

## Installation

Clone repository:

    git clone https://github.com/murashcour/pocketoption-analyzer-bot.git
    cd pocketoption-analyzer-bot

Create virtual environment:

    python3 -m venv venv
    source venv/bin/activate

Install dependencies:

    pip install -r requirements.txt

Get SSID (see docs/SSID.en.md) and save:

    echo '42["auth",{...}]' > ~/.po_ssid
    chmod 600 ~/.po_ssid

## Run

Run in screen (survives SSH disconnect):

    ./run.sh

Or manually:

    screen -S bot
    source venv/bin/activate
    export PO_SSID="$(cat ~/.po_ssid)"
    python analyzer_bot.py

On startup, the bot shows an interactive menu:

    CURRENT SETTINGS
    [1]  expiration = 60
    ...
    Number — change
    Enter — start trading
    r — reset to defaults
    q — exit

**Important:** after `./run.sh`, attach to screen (`screen -d -r bot`) and press **Enter**.
Otherwise the bot waits for input in the menu.

Detach from screen without stopping the bot: **Ctrl+A**, then **D**.
**Do not press Ctrl+C** — it stops the bot.

## Stop

Soft (wait for the current series, up to 3-5 minutes):

    ./stop.sh

Hard (immediately):

    pkill -9 -f "python analyzer_bot.py"
    screen -wipe
    rm -f stop.flag

## Documentation

- docs/SETUP.en.md — Server setup
- docs/SSID.en.md — How to get SSID
- docs/CONFIG.en.md — All settings
- docs/TROUBLESHOOTING.en.md — Problem solving

## Strategy

1. **1m analysis** — RSI + 3 MAs + candlestick pattern
2. **5m check** — RSI must match 1m direction
3. **15m check** — RSI not in extreme zones + direction conflict
4. **S/R levels** — do not enter near support/resistance
5. **Volatility** — ATR14 >= 0.008%
6. **Pair payout** — OTC [90, 95]%, Real [85, 92]%
7. **Series** — up to 4 steps with doubling (1% -> 2% -> 4% -> 8%)
8. **After win** — stay on pair, limit 3 skips
9. **After loss** — switch pair, limit 2 skips

### Martingale (4 steps)

- **1st** — full analysis, entry at 1m candle start
- **2nd** — chase by original signal (`pure_martingale: true`, 0 sec).
  If payout of original pair dropped — change pair + analysis for new.
- **3rd** — with analysis (check, may change direction/pair)
- **4th** — with analysis (check)

**Payout check** before 2/3/4: if payout out of range — change pair
until good payout found. Series is not closed, continues on new pair.

### Protection

- **30% drawdown** — when balance drops 30% from reference → **STOP**
  (1 drawdown, no pause)
- **4 consecutive losses** — 30 min pause
- **News** — pause 10 min before and 20 min after (High + Medium, USD/EUR/GBP/JPY)
- **Auto-stop** — after 24 hours of work

## Manual Mode (Analyzer)

The bot supports manual mode for testing strategies:

    # Only shows signals, does not open trades
    python analyzer_bot.py --show-only

    # Shows, asks, opens on y
    python analyzer_bot.py --confirm

**What it does:**
- Checks pair payout
- Runs `full_analysis` (1m + 5m + 15m + S/R + ATR)
- Shows signal (CALL/PUT), pair, price
- In `--confirm` — asks bet and confirmation

**Commands in process:**
- `Enter` — continue (same pair)
- `s` — change pair
- `q` — exit

**Why:** test how the strategy works on different pairs,
without risk of automatic series. Useful for tuning RSI thresholds,
S/R, ATR before running in auto mode.

## Configuration

All settings — in `config.json` (created on first run).
Key parameters:

| Parameter | Value | Description |
|---|---|---|
| `martingale_steps_count` | 4 | Steps in series |
| `pure_martingale` | true | Chase step 2 by original signal |
| `payout_min_otc` / `max` | 90 / 95 | OTC payout (%) |
| `payout_min_real` / `max` | 85 / 92 | Real payout (%) |
| `max_drawdown_percent` | 30 | Drawdown for STOP (%) |
| `drawdown_max_count` | 1 | Drawdowns until STOP |
| `pause_after_losses` | 4 | Consecutive losses until pause |
| `pause_after_losses_sec` | 1800 | Pause (sec) |
| `max_runtime_hours` | 24 | Auto-stop (hours) |
| `base_percent` | 1.0 | % of balance (at >= $100) |
| `fixed_steps` | [1,2,4,8] | Fixed bets (at < $100) |

Full list — in docs/CONFIG.en.md.

## Logs

    ~/Git/pocketoption-analyzer-bot/analyzer_bot.log

View in real time:

    tail -f analyzer_bot.log

## License

MIT License

## Author

murashcour — https://github.com/murashcour

Project built with DeepSeek AI.

## Disclaimer

This project is not financial advice. Binary options trading
involves high risk.
