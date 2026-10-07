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

### OTC

| Parameter | Default | Description |
|---|---|---|
| payout_min_otc | 85 | Min OTC payout (%) |
| payout_max_otc | 92 | Max OTC payout (%) |

### Real

| Parameter | Default | Description |
|---|---|---|
| payout_min_real | 75 | Min Real payout (%) |
| payout_max_real | 92 | Max Real payout (%) |

### Common

| Parameter | Default | Description |
|---|---|---|
| payout_recheck_sec | 1800 | Payout recheck (sec) |

Pairs with payout outside range are not traded.

**Why different ranges:**
- OTC — synthetic, payout higher (85-92%)
- Real — real market, payout lower (75-92%)

## Real pairs

| Parameter | Default | Description |
|---|---|---|
| include_real | True | Include Real pairs |
| real_asset_types | ["currency"] | Real types (Currency only) |
| timezone | "Europe/Moscow" | Timezone for Forex check |
| forex_trade_days | [0, 1, 2, 3, 4] | Forex days (0=Mon, 4=Fri) |

**Logic:**
- Real pairs — **Currency only** (forex), crypto excluded
- Real pairs are not traded on weekends (Forex closed Sat-Sun)
- Weekday check by `timezone` (MSK)

## Drawdown protection

| Parameter | Default | Description |
|---|---|---|
| max_drawdown_percent | 30 | Drawdown % to trigger |
| drawdown_pause_sec | 1800 | Pause on drawdown (sec) |
| drawdown_max_count | 2 | Max drawdowns before STOP |

**Logic:**
- Start: `reference_balance = initial_balance`
- If `current < reference * (1 - percent/100)`:
  - `drawdown_count += 1`
  - If `count >= max_count` → **STOP** (wait for reaction)
  - Else → **pause** → `reference = current` → **continue**

**Modes:**
- `count = 1` → STOP after 1st drawdown (no pause)
- `count = 2` → pause after 1st, STOP after 2nd (default)

## News (TradingView)

| Parameter | Default | Description |
|---|---|---|
| news_enabled | True | Enable news pause |
| news_importance_min | 2 | Min importance (2=Medium, 3=High) |
| news_pre_pause_min | 10 | Pause N min before news |
| news_post_pause_min | 20 | Pause N min after news |
| news_currencies | ["USD", "EUR", "GBP", "JPY"] | News currencies |
| news_refresh_hours | 4 | Calendar refresh (hours) |
| news_fallback_stop | True | STOP if calendar not loaded |

**Source:** `https://economic-calendar.tradingview.com/events` (free).

**Importance:**
- `1` = Low (not blocking)
- `2` = Medium (blocking if `news_importance_min=2`)
- `3` = High (blocking if `importance_min<=3`)

**Fallback:**
- If calendar not loaded and `news_fallback_stop=True` → **STOP**
- If `False` → **trade without pause** (not recommended)



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
