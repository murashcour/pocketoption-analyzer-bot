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

# PATCH_073: Classic через full_analysis из analyzer_bot, SR_CCI через strategy_sr_cci
import analyzer_bot
from analyzer_bot import full_analysis as classic_full_analysis
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
    """PATCH_073: >=900 → [], иначе как 072e (300+ live, <300 get_candles)."""
    if period >= 900:
        return []  # 15м в Classic убран (SERVER_FIX), SR_CCI не использует
    if period >= 300:
        # 5м/15м — live (get_candles виснет)
        result = []
        try:
            async def _collect():
                async for closed, forming in client.get_candles_live(asset, period, count):
                    if isinstance(closed, list):
                        result.extend(closed)
                    if isinstance(forming, dict):
                        result.append(forming)
                    if len(result) >= count:
                        break
            await asyncio.wait_for(_collect(), timeout=25)
            return result[:count]
        except asyncio.TimeoutError:
            print(f"⚠ fetch_candles_safe({asset}, {period}): live таймаут 25с (собрано {len(result)})")
            return result[:count]
        except Exception as e:
            print(f"⚠ fetch_candles_safe({asset}, {period}): live {type(e).__name__}: {e}")
            return result[:count]
    # 1м/3м — get_candles (live виснет)
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


def pick_final(classic_sig, sr_sig):
    """Возвращает (final_sig, status): STRONG / WEAK / CONFLICT / NONE."""
    if classic_sig == sr_sig and classic_sig in ("CALL", "PUT"):
        return classic_sig, "STRONG"
    if classic_sig in ("CALL", "PUT") and sr_sig in ("CALL", "PUT"):
        return None, "CONFLICT"
    if classic_sig in ("CALL", "PUT"):
        return classic_sig, "WEAK"
    if sr_sig in ("CALL", "PUT"):
        return sr_sig, "WEAK"
    return None, "NONE"


async def combined_analysis(client, pair, cfg):
    """Возвращает (classic_sig, sr_sig, price, c_reason, s_reason)."""
    classic_sig = None
    classic_reason = ""
    price = None
    try:
        r = await asyncio.wait_for(classic_full_analysis(client, pair), timeout=60)
        if isinstance(r, tuple) and len(r) >= 3:
            classic_sig, price, classic_reason = r[0], r[1], r[2]
        elif isinstance(r, tuple) and len(r) == 2:
            classic_sig, price = r[0], r[1]
            classic_reason = "OK" if classic_sig else "NO_SIGNAL"
    except asyncio.TimeoutError:
        classic_reason = "TIMEOUT"
    except Exception as e:
        classic_reason = f"ERR:{type(e).__name__}"

    sr_sig = None
    sr_reason = ""
    try:
        r = await asyncio.wait_for(
            full_analysis_sr_cci(client, pair, cfg, fetch_candles_safe, get_current_price_safe),
            timeout=60
        )
        if isinstance(r, tuple) and len(r) >= 3:
            sr_sig, sr_price, sr_reason = r[0], r[1], r[2]
            if price is None:
                price = sr_price
        elif isinstance(r, tuple) and len(r) == 2:
            sr_sig, sr_price = r[0], r[1]
            if price is None:
                price = sr_price
            sr_reason = "OK" if sr_sig else "NO_SIGNAL"
    except asyncio.TimeoutError:
        sr_reason = "TIMEOUT"
    except Exception as e:
        sr_reason = f"ERR:{type(e).__name__}"

    return classic_sig, sr_sig, price, classic_reason, sr_reason


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


def print_card(pair, classic_sig, sr_sig, final_sig, status, price, stats):
    W = 50
    BLUE = "\033[94m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GRAY = "\033[90m"
    RESET = "\033[0m"
    sep = "\u2560" + "\u2550" * (W + 2) + "\u2563"
    top = "\u2554" + "\u2550" * (W + 2) + "\u2557"
    bot = "\u255a" + "\u2550" * (W + 2) + "\u255d"

    def _sig(s):
        if s == "CALL": return "CALL"
        if s == "PUT": return "PUT"
        return "\u2014"

    lines = [
        top,
        _line(f"\U0001F3AF \u0410\u041d\u0410\u041b\u0418\u0417: {pair}", W),
        sep,
    ]
    if price is not None:
        lines.append(_line(f"\u0426\u0435\u043d\u0430:        {price:.5f}", W))
    lines.append(_line(f"Classic:     {_sig(classic_sig)}", W))
    lines.append(_line(f"SR_CCI:      {_sig(sr_sig)}", W))
    lines.append(sep)

    if status == "STRONG" and final_sig == "CALL":
        lines.append(_line(f"\u0418\u0422\u041e\u0413:        {BLUE}\u2b06 CALL{RESET}", W))
    elif status == "STRONG" and final_sig == "PUT":
        lines.append(_line(f"\u0418\u0422\u041e\u0413:        {RED}\u2b07 PUT{RESET}", W))
    elif status == "CONFLICT":
        lines.append(_line(f"\u0418\u0422\u041e\u0413:        {YELLOW}\u2696 \u041a\u041e\u041d\u0424\u041b\u0418\u041a\u0422 \u2014 \u043f\u0440\u043e\u043f\u0443\u0441\u043a{RESET}", W))
    elif status == "WEAK" and final_sig == "CALL":
        lines.append(_line(f"\u0418\u0422\u041e\u0413:        {YELLOW}\u2b06 CALL (\u0441\u043b\u0430\u0431\u044b\u0439){RESET}", W))
    elif status == "WEAK" and final_sig == "PUT":
        lines.append(_line(f"\u0418\u0422\u041e\u0413:        {YELLOW}\u2b07 PUT (\u0441\u043b\u0430\u0431\u044b\u0439){RESET}", W))
    else:
        lines.append(_line(f"\u0418\u0422\u041e\u0413:        {GRAY}\u23f8 \u041d\u0435\u0442 \u0441\u0438\u0433\u043d\u0430\u043b\u0430{RESET}", W))

    lines.append(sep)

    if stats:
        wr = stats.get("winrate")
        total = stats.get("total")
        if wr is not None:
            try:
                wr_str = f"{float(wr):.1f}%"
            except (ValueError, TypeError):
                wr_str = str(wr)
            total_str = f" ({total} \u0441\u0438\u0433\u043d.)" if total else ""
            lines.append(_line(f"WR \u043f\u0430\u0440\u044b (24\u0447): {wr_str}{total_str}", W))
        else:
            lines.append(_line("WR \u043f\u0430\u0440\u044b (24\u0447): \u043d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445", W))
    else:
        lines.append(_line("WR \u043f\u0430\u0440\u044b (24\u0447): \u043d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445", W))

    lines.append(sep)
    lines.append(_line("\u26a0 \u0410\u043d\u0430\u043b\u0438\u0437, \u043d\u0435 \u0433\u0430\u0440\u0430\u043d\u0442\u0438\u044f. \u041f\u0440\u043e\u0432\u0435\u0440\u044c \u0433\u0440\u0430\u0444\u0438\u043a.", W))
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
        print("\u274c SSID \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d (~/.po_ssid \u0438\u043b\u0438 PO_SSID)")
        sys.exit(1)

    cfg = load_cfg()

    # PATCH_073: monkey-patch analyzer_bot для Classic
    # (безопасно: бот в другом процессе, его CFG/fetch не затронуты)
    classic_cfg = dict(cfg)
    classic_cfg["strategy_mode"] = "Classic"
    analyzer_bot.CFG = classic_cfg
    analyzer_bot.fetch_candles = fetch_candles_safe
    analyzer_bot.get_current_price = get_current_price_safe

    print(f"\u23f3 \u0410\u043d\u0430\u043b\u0438\u0437 {pair}: Classic + SR_CCI...")

    async with PocketOptionAsync(ssid=ssid) as client:
        classic_sig, sr_sig, price, c_reason, s_reason = await combined_analysis(client, pair, cfg)

    final_sig, status = pick_final(classic_sig, sr_sig)
    stats = load_pair_stats(pair)
    print_card(pair, classic_sig, sr_sig, final_sig, status, price, stats)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\u23f9 Остановлено")
