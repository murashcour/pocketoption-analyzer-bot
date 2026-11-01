#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import csv
import json
from pathlib import Path

HISTORY_DIR = Path("history")
HISTORY_REAL_DIR = Path("history_real")
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
            
            # NEW_FEATURES: фильтрация по history_window_hours
            import json
            import os
            from datetime import datetime, timedelta
            
            cfg_path = Path("config.json")
            window_hours = 24
            if cfg_path.exists():
                try:
                    with open(cfg_path, 'r', encoding='utf-8') as cf:
                        cfg = json.load(cf)
                    window_hours = cfg.get("history_window_hours", 24)
                except Exception:
                    pass
            
            cutoff = datetime.utcnow() - timedelta(hours=window_hours)
            
            filtered_rows = []
            for row in rows:
                try:
                    ts = row.get('timestamp', '')
                    if ts:
                        # Пытаемся распарсить timestamp
                        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        if dt.replace(tzinfo=None) >= cutoff:
                            filtered_rows.append(row)
                    else:
                        filtered_rows.append(row)  # если нет timestamp — берём
                except Exception:
                    filtered_rows.append(row)  # если не парсится — берём
            
            rows = filtered_rows
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
    stats = {}
    
    # OTC-пары (history/)
    if HISTORY_DIR.exists():
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
            print(f"{pair} (OTC): {winrate:.1f}% ({wins}/{total})")
    
    # REAL_PAIRS: Real-пары (history_real/)
    if HISTORY_REAL_DIR.exists():
        for csv_file in HISTORY_REAL_DIR.glob("*.csv"):
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
            print(f"{pair} (REAL): {winrate:.1f}% ({wins}/{total})")

    if not stats:
        print("ERR: Нет данных")
        return

    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f"OK: Сохранено {len(stats)} пар в {STATS_FILE}")

if __name__ == "__main__":
    main()
