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
        
        # Сохраняем в CSV
        filename = HISTORY_DIR / f"{pair}.csv"
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
            for c in candles:
                # Пытаемся извлечь поля (dict или tuple)
                if isinstance(c, dict):
                    ts = c.get("time", c.get("timestamp", ""))
                    writer.writerow([ts, c["open"], c["high"], c["low"], c["close"], c.get("volume", 0)])
                elif isinstance(c, (list, tuple)):
                    writer.writerow([c[0], c[1], c[2], c[3], c[4], c[5] if len(c) > 5 else 0])
                else:
                    print(f"⚠ {pair}: неизвестный формат свечи: {type(c)}")
                    return
        print(f"✅ {pair}: сохранено {len(candles)} свечей")
    except Exception as e:
        print(f"❌ {pair}: ошибка {e}")

async def main():
    # Загружаем SSID
    if not os.path.exists(SSID_FILE):
        print(f"❌ SSID не найден: {SSID_FILE}")
        return
    ssid = open(SSID_FILE).read().strip()
    
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

if __name__ == "__main__":
    asyncio.run(main())
