#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скачивает 334 свечи (1м) для всех OTC-пар и сохраняет в CSV.
"""
import asyncio
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

# Добавляем путь к библиотеке
sys.path.append(os.path.expanduser("~/Git/pocketoption-analyzer-bot"))
from BinaryOptionsToolsV2 import PocketOptionAsync
from tvkit.api.chart.ohlcv import OHLCV

# HISTORY_APPEND
# Настройки
HISTORY_DIR = Path("history")
HISTORY_DIR.mkdir(exist_ok=True)
SSID_FILE = os.path.expanduser("~/.po_ssid")

async def download_pair(client, pair):
    try:
        # Запрашиваем максимум (334 свечи)
        candles = await client.get_candles(pair, 60, 400)
        if not candles or len(candles) < 50:
            print(f"⚠ {pair}: мало данных ({len(candles) if candles else 0})")
            return
        
        # HISTORY_APPEND: дописываем, а не перезаписываем
        filename = HISTORY_DIR / f"{pair}.csv"
        file_exists = filename.exists()
        
        # Читаем существующие timestamp, чтобы не дублировать
        existing_ts = set()
        if file_exists:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    next(reader, None)  # пропускаем заголовок
                    for row in reader:
                        if row:
                            existing_ts.add(row[0])
            except Exception as e:
                print(f"⚠ {pair}: ошибка чтения существующего файла: {e}")
                file_exists = False
        
        # Открываем на дописывание ('a') или создание ('w')
        mode = 'a' if file_exists else 'w'
        with open(filename, mode, newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
            
            added = 0
            for c in candles:
                if isinstance(c, dict):
                    ts = c.get("time", c.get("timestamp", ""))
                    if str(ts) in existing_ts:
                        continue  # уже есть, пропускаем
                    writer.writerow([ts, c["open"], c["high"], c["low"], c["close"], c.get("volume", 0)])
                    added += 1
                elif isinstance(c, (list, tuple)):
                    ts = c[0]
                    if str(ts) in existing_ts:
                        continue
                    writer.writerow([ts, c[1], c[2], c[3], c[4], c[5] if len(c) > 5 else 0])
                    added += 1
                else:
                    print(f"⚠ {pair}: неизвестный формат свечи: {type(c)}")
                    return
        print(f"✅ {pair}: добавлено {added} свечей (всего в файле: ~{len(existing_ts) + added})")
    except Exception as e:
        print(f"❌ {pair}: ошибка {e}")


# REAL_PAIRS: скачивание Real-пар через tvkit
async def download_real_pairs():
    """Скачивает историю по реальным парам через TradingView (OANDA)."""
    pairs = [
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
        "USDCHF", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY",
    ]
    history_real = Path("history_real")
    history_real.mkdir(exist_ok=True)
    
    # DOWNLOAD_REAL_SAFE: каждая пара в отдельном try/except
    for pair in pairs:
        symbol = f"OANDA:{pair}"
        try:
            async with OHLCV() as client:
                bars = await client.get_historical_ohlcv(
                    exchange_symbol=symbol,
                    interval="1",
                    bars_count=5000,
                )
                if not bars:
                    print(f"⚠ {pair}: нет данных")
                    continue
                
                filename = history_real / f"{pair}.csv"
                with open(filename, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
                    for bar in bars:
                        writer.writerow([
                            bar.timestamp, bar.open, bar.high, bar.low, bar.close, bar.volume
                        ])
                print(f"✅ {pair}: {len(bars)} баров → {filename}")
        except Exception as e:
            print(f"❌ {pair}: {e}")
        await asyncio.sleep(2)  # пауза между парами


async def main():
    # Загружаем SSID
    if not os.path.exists(SSID_FILE):
        print(f"❌ SSID не найден: {SSID_FILE}")
        return
    ssid = open(SSID_FILE).read().strip()
    
    # DOWNLOAD_SAFE: OTC-часть (может упасть, если SSID битый)
    try:
        async with PocketOptionAsync(ssid=ssid) as client:
            print("✅ Подключение установлено")
            # Получаем список OTC-пар (берем из active_assets)
            assets = await client.active_assets()
            otc_pairs = []
            for a in assets:
                if isinstance(a, dict) and a.get("is_otc", False) and a.get("asset_type") == "currency":
                    symbol = a.get("symbol", "")
                    if symbol.endswith("_otc"):
                        otc_pairs.append(symbol)
            
            print(f"📋 Найдено {len(otc_pairs)} OTC-пар")
            for pair in otc_pairs:
                await download_pair(client, pair)
                await asyncio.sleep(0.5)  # Пауза, чтобы не забанили
    except Exception as e:
        print(f"⚠ OTC-часть пропущена (SSID?): {e}")

    # REAL_PAIRS: скачиваем Real-пары через tvkit (не требует SSID)
    print("📊 Скачиваем Real-пары через TradingView...")
    await download_real_pairs()

if __name__ == "__main__":
    asyncio.run(main())
