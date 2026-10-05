# Settings (config.json)

All bot settings are stored in config.json. On first run, it is
created automatically with default values. On startup, the bot
shows an interactive menu to adjust parameters.

## Main

| Parameter | Default | Description |
|---|---|---|
| expiration | 60 | Trade expiration in seconds |
| check_interval_sec | 15 | Series check interval (sec) |
| max_checks | 4 | Max steps in series |

## Bets

| Parameter | Default | Description |
|---|---|---|
| base_percent | 1.0 | Base percent of balance (1%) |
| min_balance_for_percent | 100 | Balance threshold for percent mode |
| fixed_steps | [1, 2, 4, 8] | Fixed steps at low balance |

How it works:

- Balance >= 100 → 1st bet = 1% of balance, then x2
- Balance < 100 → fixed 1, 2, 4, 8 USD

Example at balance 150:

- Step 1: 1.50
- Step 2: 3.00 (1.50 x 2)
- Step 3: 6.00 (3.00 x 2)
- Step 4: 12.00 (6.00 x 2)

## Payout

| Parameter | Default | Description |
|---|---|---|
| payout_min | 85 | Min pair payout (%) |
| payout_max | 92 | Max pair payout (%) |
| payout_recheck_sec | 1800 | Payout recheck (sec) |

Pairs with payout outside range are not traded.

## 1m Analysis

| Parameter | Default | Description |
|---|---|---|
| min_confirmations | 3 | Min confirmations for signal |
| rsi_overbought | 75 | RSI above — overbought (skip) |
| rsi_oversold | 25 | RSI below — oversold (skip) |
| rsi_bull_min | 53 | RSI above — bullish signal |
| rsi_bear_max | 47 | RSI below — bearish signal |

## S/R Levels

| Parameter | Default | Description |
|---|---|---|
| sr_lookback | 50 | Candles for level search |
| sr_proximity_percent | 0.1 | Proximity to level (%) |

If price is close to support or resistance — signal is blocked.

## Volatility

| Parameter | Default | Description |
|---|---|---|
| atr_period | 14 | ATR period |
| atr_min_percent | 0.1 | Min ATR (%) |

If ATR < 0.1% of price — market is flat, trade is skipped.

## Multi-timeframe

| Parameter | Default | Description |
|---|---|---|
| tf_3m_rsi_bull | 55 | RSI 3m above — bullish |
| tf_3m_rsi_bear | 45 | RSI 3m below — bearish |
| tf_3m_neutral_blocks | true | Neutral 3m blocks |
| tf_10m_overbought | 75 | RSI 10m — overbought |
| tf_10m_oversold | 25 | RSI 10m — oversold |

## Skip management

| Parameter | Default | Description |
|---|---|---|
| skip_before_change_plus | 5 | Skips after winning series |
| skip_before_change_minus | 1 | Skips after losing series |

Logic:

- After winning series — 5 skips on pair, then switch
- After losing series — 1 skip, then switch
- After pair switch — limit resets to 1

## How to change settings

### Method 1: interactive menu (recommended)

On startup, the bot shows a menu:

    CURRENT SETTINGS
    [1]  expiration              = 60
    [2]  min_confirmations       = 3
    ...

    Number — change
    Enter — trade
    r — reset to defaults
    q — exit

Enter number — change parameter. Enter — start trading.

### Method 2: manually in config.json

    vim config.json

Find parameter, change, save.

IMPORTANT: do not run bot while editing.

### Method 3: reset to defaults

If something broke:

    rm config.json

New one with default values is created on next run.

Or press r in bot menu.

## Where config.json is stored

File is created in project folder:

    ~/bot/config.json

It is added to .gitignore — not pushed to repository. This means
your settings are only yours, not published to GitHub.

## Default settings

Full template with defaults — in config.default.json. If you want
to start fresh — copy it:

    cp config.default.json config.json

## Security

config.json does NOT contain SSID — SSID is passed through
environment variable PO_SSID. This is safer.

If you accidentally committed config.json — it is not critical,
only bot settings, no secrets.
