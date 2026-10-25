#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import csv
import json
from pathlib import Path

HISTORY_DIR = Path("history")
STATS_FILE = Path("pair_stats.json")

def analyze_csv(filepath: Path):
    wins = 0
    losses = 0
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if len(rows) < 10:
                return 0, 0
            for i in range(len(rows) - 1):
                try:
                    curr_close = float(rows[i]['close'])
                    next_close = float(rows[i+1]['close'])
                except (ValueError, KeyError):
                    continue
                if next_close > curr_close:
                    wins += 1
                elif next_close < curr_close:
                    losses += 1
    except Exception as e:
        print(f"ERR {filepath.name}: {e}")
    return wins, losses

def main():
    if not HISTORY_DIR.exists():
        print("ERR: Папка history/ не найдена")
        return

    stats = {}
    for csv_file in HISTORY_DIR.glob("*.csv"):
        pair = csv_file.stem
        wins, losses = analyze_csv(csv_file)
        total = wins + losses
        if total == 0:
            continue
        winrate = (wins / total) * 100
        stats[pair] = {
            "winrate": round(winrate, 2),
            "wins": wins,
            "losses": losses,
            "total": total,
        }
        print(f"{pair}: {winrate:.1f}% ({wins}/{total})")

    if not stats:
        print("ERR: Нет данных")
        return

    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f"OK: Сохранено {len(stats)} пар в {STATS_FILE}")

if __name__ == "__main__":
    main()
