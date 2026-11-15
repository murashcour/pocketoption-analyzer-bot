#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_classic_stats.py (PATCH_076):
Бэктест Classic-стратегии по history/*.csv и history_real/*.csv.
Пишет pair_stats_classic.json в формате: {"PAIR": {winrate, wins, losses, total, skipped}}.
"""
import csv
import json
import logging
import sys
import time
from pathlib import Path

# PATCH_076: analyze_1m пишет INFO-лог на каждый сигнал — глушим для скорости
logging.disable(logging.INFO)

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
STATS_FILE = BASE_DIR / "pair_stats_classic.json"
HISTORY_DIRS = [BASE_DIR / "history", BASE_DIR / "history_real"]

import analyzer_bot
from analyzer_bot import (
    analyze_1m, check_volatility,
    find_support_resistance, check_sr_proximity,
    get_close, load_config,
)


def load_candles(csv_path):
    candles = []
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    candles.append({
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                    })
                except (KeyError, ValueError):
                    continue
    except Exception as e:
        print(f"WARN {csv_path.name}: {e}")
    return candles


def backtest_classic(candles, window_size=100):
    if len(candles) < 51:
        return 0, 0, 0
    wins = losses = skipped = 0
    for i in range(50, len(candles) - 1):
        start = max(0, i - window_size + 1)
        window = candles[start:i + 1]
        if len(window) < 50:
            continue
        sig = analyze_1m(window)
        if sig is None:
            skipped += 1
            continue
        price = get_close(window[-1])
        ok_vol, _ = check_volatility(window, price)
        if not ok_vol:
            skipped += 1
            continue
        sup, res = find_support_resistance(window)
        ok_sr, _ = check_sr_proximity(price, sup, res, sig)
        if not ok_sr:
            skipped += 1
            continue
        next_close = get_close(candles[i + 1])
        if (sig == "CALL" and next_close > price) or (sig == "PUT" and next_close < price):
            wins += 1
        else:
            losses += 1
    return wins, losses, skipped


def main():
    print("build_classic_stats.py - start")
    if not CONFIG_FILE.exists():
        print(f"ERR config.json not found: {CONFIG_FILE}")
        sys.exit(1)

    cfg = load_config()
    analyzer_bot.CFG = cfg
    print(f"   CFG: strategy={cfg.get('strategy_mode')}, "
          f"min_conf={cfg.get('min_confirmations')}, "
          f"rsi=[{cfg.get('rsi_oversold')},{cfg.get('rsi_overbought')}]")

    stats = {}
    total_signals = 0
    t_start = time.time()

    for hdir in HISTORY_DIRS:
        if not hdir.exists():
            print(f"WARN {hdir} not found - skip")
            continue
        csv_files = sorted(hdir.glob("*.csv"))
        print(f"\nDIR {hdir.name}: {len(csv_files)} files")
        for csv_path in csv_files:
            pair = csv_path.stem
            candles = load_candles(csv_path)
            if len(candles) < 100:
                continue
            wins, losses, skipped = backtest_classic(candles)
            total = wins + losses
            if total < 10:
                continue
            wr = (wins / total) * 100
            stats[pair] = {
                "winrate": round(wr, 2),
                "wins": wins,
                "losses": losses,
                "total": total,
                "skipped": skipped,
            }
            total_signals += total
            print(f"   {pair}: {wr:.1f}% ({wins}/{total}) [skip={skipped}]")

    elapsed = time.time() - t_start
    if not stats:
        print("ERR no data")
        sys.exit(1)

    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"\nOK saved {len(stats)} pairs to {STATS_FILE.name} in {elapsed:.1f}s")
    print(f"   total signals: {total_signals}")


if __name__ == "__main__":
    main()
