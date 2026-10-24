#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Бэктест на исторических данных (CSV).
Прогоняет analyze_1m и фильтры (S/R, ATR, ADX) на истории.
"""
import csv
import os
import sys
from pathlib import Path
from typing import List, Dict

# Импортируем функции из бота (чтобы не дублировать логику)
# ВАЖНО: analyzer_bot.py должен быть в той же папке
try:
    from analyzer_bot import (
        analyze_1m, check_volatility, check_sr_proximity,
        find_support_resistance, adx, get_close, get_high, get_low
    )
except ImportError:
    print("❌ Не удалось импортировать функции из analyzer_bot.py")
    print("   Убедитесь, что backtest.py лежит в той же папке.")
    sys.exit(1)

HISTORY_DIR = Path("history")

def load_csv(pair: str) -> List[Dict]:
    """Загружает CSV в список свечей (dict)."""
    filename = HISTORY_DIR / f"{pair}.csv"
    if not filename.exists():
        return []
    
    candles = []
    with open(filename, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            candles.append({
                "time": int(row["timestamp"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0))
            })
    return candles

def run_backtest(pair: str, candles: List[Dict]):
    """
    Прогоняет стратегию на исторических данных.
    Эмулирует логику full_analysis (1м + 5м + S/R + ATR + ADX).
    """
    if len(candles) < 50:
        return None
    
    wins = 0
    losses = 0
    total = 0
    trades = []
    
    # Проходим по свечам, начиная с 50-й (чтобы было достаточно данных для индикаторов)
    for i in range(50, len(candles) - 1):
        # Берем историю до текущей свечи (i)
        history_1m = candles[:i]
        
        # 1м анализ
        sig_1m = analyze_1m(history_1m)
        if sig_1m is None:
            continue
        
        # Цена входа — закрытие текущей свечи (i)
        entry_price = get_close(candles[i])
        
        # Проверка волатильности
        ok_vol, _ = check_volatility(history_1m, entry_price)
        if not ok_vol:
            continue
        
        # S/R
        support, resistance = find_support_resistance(history_1m)
        ok_sr, _ = check_sr_proximity(entry_price, support, resistance, sig_1m)
        if not ok_sr:
            continue
        
        # Эмуляция 5м тренда (группируем по 5 свечей)
        # Для простоты берем последние 50 свечей и считаем EMA20/EMA50
        # В реальном боте это отдельный запрос, здесь эмулируем
        closes = [get_close(c) for c in history_1m]
        if len(closes) >= 50:
            def ema(prices, period):
                mult = 2 / (period + 1)
                val = prices[0]
                for p in prices[1:]:
                    val = (p - val) * mult + val
                return val
            e20 = ema(closes[-50:], 20)
            e50 = ema(closes[-50:], 50)
            if e20 is not None and e50 is not None:
                trend_5m = "CALL" if e20 > e50 else "PUT"
                if trend_5m != sig_1m:
                    continue
        
        # Результат сделки (следующая свеча i+1)
        next_close = get_close(candles[i+1])
        if sig_1m == "CALL":
            is_win = next_close > entry_price
        else:
            is_win = next_close < entry_price
        
        total += 1
        if is_win:
            wins += 1
        else:
            losses += 1
        
        trades.append({
            "time": candles[i]["time"],
            "signal": sig_1m,
            "entry": entry_price,
            "exit": next_close,
            "win": is_win
        })
    
    if total == 0:
        return None
    
    winrate = wins / total * 100
    return {
        "pair": pair,
        "total": total,
        "wins": wins,
        "losses": losses,
        "winrate": winrate,
        "trades": trades
    }

def main():
    if not HISTORY_DIR.exists():
        print(f"❌ Папка {HISTORY_DIR} не найдена.")
        return
    
    csv_files = list(HISTORY_DIR.glob("*.csv"))
    if not csv_files:
        print(f"❌ В {HISTORY_DIR} нет CSV-файлов.")
        return
    
    print(f"📊 Найдено {len(csv_files)} пар для бэктеста.")
    
    all_results = []
    total_wins = 0
    total_losses = 0
    total_trades = 0
    
    for csv_file in csv_files:
        pair = csv_file.stem
        candles = load_csv(pair)
        if not candles:
            continue
        
        result = run_backtest(pair, candles)
        if result:
            all_results.append(result)
            total_wins += result["wins"]
            total_losses += result["losses"]
            total_trades += result["total"]
            print(f"   {pair}: {result['total']} сделок, Winrate {result['winrate']:.1f}%")
    
    if total_trades == 0:
        print("❌ Нет сделок для анализа.")
        return
    
    # Итоговый отчет
    print("\n" + "=" * 50)
    print("📊 ИТОГОВЫЙ ОТЧЕТ")
    print("=" * 50)
    print(f"   Всего сделок: {total_trades}")
    print(f"   ✅ WIN: {total_wins}")
    print(f"   ❌ LOSS: {total_losses}")
    print(f"   Winrate: {total_wins / total_trades * 100:.1f}%")
    print("=" * 50)

if __name__ == "__main__":
    main()
