#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyzer_manual.py (PATCH_072): ручной анализатор по выбранной паре.
Read-only: только печатает сигнал + WR пары из pair_stats_sr_cci.json.
НЕ открывает сделки.

Использование:
  python analyzer_manual.py EURUSD_otc
  python analyzer_manual.py GBPJPY_otc
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from BinaryOptionsToolsV2 import PocketOptionAsync

# PATCH_072c: своя загрузка через get_candles (live висит при параллельном боте)
from strategy_sr_cci import full_analysis_sr_cci, get_close

logging.basicConfig(level=logging.WARNING, format="%(levelname)s | %(message)s")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
STATS_FILE = Path(BASE_DIR) / "pair_stats_sr_cci.json"
SSID_FILE = os.path.expanduser("~/.po_ssid")


def load_ssid() -> str:
    s = os.getenv("PO_SSID", "").strip()
    if not s and os.path.exists(SSID_FILE):
        with open(SSID_FILE) as f:
            s = f.read().strip()
    return s


def load_cfg() -> dict:
    if not os.path.exists(CONFIG_FILE):
        print(f"❌ config.json не найден: {CONFIG_FILE}")
        sys.exit(1)
    return json.loads(Path(CONFIG_FILE).read_text(encoding="utf-8"))


def load_pair_stats(pair: str):
    """Возвращает stats для пары или None. Формат — как в pair_stats_sr_cci.json."""
    if not STATS_FILE.exists():
        return None
    try:
        data = json.loads(STATS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(data, dict):
        stats = data.get(pair) or data.get(pair.lower()) or data.get(pair.upper())
        # PATCH_072b: total = wins + losses, если не задан явно
        if isinstance(stats, dict) and "total" not in stats:
            w = stats.get("wins", 0) or 0
            l = stats.get("losses", 0) or 0
            if w or l:
                stats["total"] = int(w) + int(l)
        return stats
    return None


async def fetch_candles_safe(client, asset: str, period: int, count: int):
    """PATCH_072c: get_candles без live (live висит при параллельном боте)."""
    try:
        candles = await asyncio.wait_for(client.get_candles(asset, period, count), timeout=20)
        return candles or []
    except asyncio.TimeoutError:
        print(f"⚠ fetch_candles_safe({asset}, {period}): таймаут 20с")
        return []
    except Exception as e:
        print(f"⚠ fetch_candles_safe({asset}, {period}): {type(e).__name__}: {e}")
        return []


async def get_current_price_safe(client, pair: str):
    """PATCH_072c: цена из закрытой свечи 1м (get_candles)."""
    try:
        candles = await asyncio.wait_for(client.get_candles(pair, 60, 2), timeout=10)
        if candles:
            return get_close(candles[-1])
    except Exception:
        pass
    return None


def _dw(s: str) -> int:
    import unicodedata
    w = 0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ("W", "F") or ord(ch) > 0x1F000:
            w += 2
        else:
            w += 1
    return w


def _line(content: str, W: int = 50) -> str:
    import re
    clean = re.sub(r"\033\[[0-9;]*m", "", content)
    pad = max(0, W - _dw(clean))
    return f"\u2551 {content}{' ' * pad} \u2551"


def print_card(pair, signal, price, reason, stats):
    W = 50
    sep = "\u2560" + "\u2550" * (W + 2) + "\u2563"
    top = "\u2554" + "\u2550" * (W + 2) + "\u2557"
    bot = "\u255a" + "\u2550" * (W + 2) + "\u255d"

    lines = [
        top,
        _line(f"\U0001F3AF \u0410\u041d\u0410\u041b\u0418\u0417: {pair}", W),
        sep,
    ]

    if signal == "CALL":
        lines.append(_line("\u0421\u0438\u0433\u043d\u0430\u043b:      \u2b06 CALL (\u0412\u0412\u0415\u0420\u0425)", W))
    elif signal == "PUT":
        lines.append(_line("\u0421\u0438\u0433\u043d\u0430\u043b:      \u2b07 PUT (\u0412\u041d\u0418\u0417)", W))
    else:
        lines.append(_line("\u0421\u0438\u0433\u043d\u0430\u043b:      \u23f8 \u041d\u0435\u0442 \u0441\u0438\u0433\u043d\u0430\u043b\u0430", W))

    if price is not None:
        lines.append(_line(f"\u0426\u0435\u043d\u0430:        {price:.5f}", W))

    if reason:
        # обрезаем причину по ширине
        r = str(reason)
        if len(r) > W - 14:
            r = r[:W - 17] + "..."
        lines.append(_line(f"\u041f\u0440\u0438\u0447\u0438\u043d\u0430:     {r}", W))

    lines.append(sep)

    if stats:
        # пробуем угадать поля
        wr = stats.get("winrate") or stats.get("wr") or stats.get("win_rate")
        total = stats.get("total") or stats.get("count") or stats.get("signals") or stats.get("total_signals")
        if wr is not None:
            if isinstance(wr, (int, float)):
                wr_str = f"{wr:.1f}%" if wr <= 1.5 else f"{wr:.1f}%"
            else:
                wr_str = str(wr)
            if total is not None:
                lines.append(_line(f"WR \u043f\u0430\u0440\u044b (24\u0447): {wr_str} ({total} \u0441\u0438\u0433\u043d.)", W))
            else:
                lines.append(_line(f"WR \u043f\u0430\u0440\u044b (24\u0447): {wr_str}", W))
        else:
            keys = ", ".join(list(stats.keys())[:3])
            lines.append(_line(f"WR (\u0444\u043e\u0440\u043c\u0430\u0442?): {keys}", W))
    else:
        lines.append(_line("WR \u043f\u0430\u0440\u044b (24\u0447): \u043d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445", W))

    lines.append(sep)
    lines.append(_line("\u26a0 \u0410\u043d\u0430\u043b\u0438\u0437, \u043d\u0435 \u0433\u0430\u0440\u0430\u043d\u0442\u0438\u044f. \u041f\u0440\u043e\u0432\u0435\u0440\u044c \u0433\u0440\u0430\u0444\u0438\u043a \u0432\u0440\u0443\u0447\u043d\u0443\u044e.", W))
    lines.append(bot)
    print("\n".join(lines))


async def main():
    if len(sys.argv) < 2:
        print("Использование: python analyzer_manual.py EURUSD_otc")
        sys.exit(1)

    raw = sys.argv[1].strip()
    if "_" in raw:
        base, suffix = raw.rsplit("_", 1)
        pair = base.upper() + "_" + suffix.lower()
    else:
        pair = raw.upper() + "_otc"
    ssid = load_ssid()
    if not ssid:
        print("❌ SSID не найден (~/.po_ssid или PO_SSID)")
        sys.exit(1)

    cfg = load_cfg()

    async with PocketOptionAsync(ssid=ssid) as client:
        try:
            result = await asyncio.wait_for(
                full_analysis_sr_cci(client, pair, cfg, fetch_candles_safe, get_current_price_safe),
                timeout=60,
            )
        except asyncio.TimeoutError:
            print(f"⚠ Таймаут анализа {pair} (>60 сек). Попробуйте ещё раз.")
            sys.exit(2)

    # full_analysis_sr_cci возвращает (signal, price, reason)
    if isinstance(result, tuple) and len(result) >= 3:
        signal, price, reason = result[0], result[1], result[2]
    elif isinstance(result, tuple) and len(result) == 2:
        signal, price = result[0], result[1]
        reason = ""
    else:
        signal, price, reason = result, None, ""

    stats = load_pair_stats(pair)
    print_card(pair, signal, price, reason, stats)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\u23f9 Остановлено")
