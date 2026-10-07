# PocketOption Analyzer Bot

[Russian](README.md) | [English](README.en.md)

> This is the English version. The primary language is Russian.

Automated trading bot for PocketOption (demo/live account).
Analyzes OTC currency pairs, generates signals, and trades using
a martingale strategy within each series.

## Important

**This project was built with DeepSeek AI assistance** (deepseek.com).

Architecture, strategy logic, and code were developed through
conversations with an AI assistant. All strategy decisions were made
by the project owner; AI helped with implementation, debugging,
and documentation.

**The bot is intended for DEMO accounts.** Use on a live account
at your own risk. The author is not responsible for financial losses.

## Features

- 📊 Multi-timeframe analysis: 1m + 3m + 10m
- 🎯 Indicators: SMA14, EMA20, EMA50, RSI14
- 📈 Filters: S/R levels, ATR (volatility), candlestick patterns
- 🌍 Real pairs (Currency / Forex): OTC + real currency pairs
- 💰 Martingale: 1% -> 2% -> 4% (no 4th step)
- 🔄 Pair rotation: switch on 3 skips or losing series
- 💹 Payout filter: OTC [85, 92]%, Real [75, 92]%
- 🛡 Drawdown protection: pause at -30%, stop after 2nd
- 📰 Pause on important news (TradingView Calendar)
- ⚙️ Interactive menu: 30+ settings
- 🖥️ Runs in screen: survives SSH disconnection

## Requirements

- **Debian-based server:**
  - Ubuntu 24.04.5 LTS (recommended, tested)
  - Debian 12+ (compatible)
- Python 3.10+
- PocketOption account (demo or live)
- SSID token (obtained via browser)
- **VDS in a recommended country** (see [docs/SETUP.en.md](docs/SETUP.en.md))

## Installation

Clone repository:

    git clone https://github.com/murachour/pocketoption-analyzer-bot.git
    cd pocketoption-analyzer-bot

Create virtual environment:

    python3 -m venv venv
    source venv/bin/activate

Install dependencies:

    pip install -r requirements.txt

Set SSID (get via browser, see docs/SSID.en.md):

    export PO_SSID='42["auth",{...}]'

Run:

    python analyzer_bot.py

## Documentation

- docs/SETUP.en.md — Server setup
- docs/SSID.en.md — How to get SSID
- docs/CONFIG.en.md — All settings
- docs/TROUBLESHOOTING.en.md — Problem solving

## Strategy

1. 1m analysis — RSI + 3 MAs + candlestick pattern
2. 3m check — RSI must match 1m direction
3. 10m check — RSI not in extreme zones
4. S/R levels — do not enter near support/resistance
5. Volatility — ATR14 >= 0.1%
6. Pair payout — [85, 92]%
7. Series — up to 4 steps with doubling
8. After win — stay on pair, limit 5 skips
9. After loss — switch pair, limit 1 skip

## License

MIT License

## Author

murachour — https://github.com/murachour

Project built with DeepSeek AI.

## Disclaimer

This project is not financial advice. Binary options trading
involves high risk.
