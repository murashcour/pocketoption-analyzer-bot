#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyzer_manual.py (PATCH_082): ручной анализатор по выбранной паре.
Read-only. Classic — primary, SR_CCI — справочно. WR из обоих JSON.

Использование:
    python analyzer_manual.py EURHUF_otc

Требование: бот (analyzer_bot.py) должен быть остановлен (иначе live-свечи висят).
"""
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from BinaryOptionsToolsV2 import PocketOptionAsync

import analyzer_bot
from analyzer_bot import (
    fetch_candles,
    get_current_price,
    full_analysis as classic_full_analysis,
    load_config,
)
from strategy_sr_cci import full_analysis_sr_cci, get_close

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
CLASSIC_STATS = Path(BASE_DIR) / "pair_stats_classic.json"
SR_CCI_STATS = Path(BASE_DIR) / "pair_stats_sr_cci.json"
SSID_FILE = os.path.expanduser("~/.po_ssid")


def load_ssid():
    s = os.getenv("PO_SSID", "").strip()
    if not s and os.path.exists(SSID_FILE):
        with open(SSID_FILE) as f:
            s = f.read().strip()
    return s


def load_cfg():
    if not os.path.exists(CONFIG_FILE):
        print(f"❌ config.json не найден: {CONFIG_FILE}")
        sys.exit(1)
    return json.loads(Path(CONFIG_FILE).read_text(encoding="utf-8"))


def load_stats_one(pair, path):
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    st = d.get(pair) or d.get(pair.lower()) or d.get(pair.upper())
    if isinstance(st, dict) and "total" not in st:
        w = int(st.get("wins", 0) or 0)
        l = int(st.get("losses", 0) or 0)
        if w or l:
            st["total"] = w + l
    return st


def _dw(s):
    import unicodedata
    w = 0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ("W", "F") or ord(ch) > 0x1F000:
            w += 2
        else:
            w += 1
    return w


def _line(content, W=50):
    import re
    clean = re.sub(r"\033\[[0-9;]*m", "", content)
    pad = max(0, W - _dw(clean))
    return f"\u2551 {content}{' ' * pad} \u2551"


def print_card(pair, classic_sig, sr_sig, price, c_stats, s_stats, c_reason, s_reason):
    W = 50
    BLUE = "\033[94m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GRAY = "\033[90m"
    GREEN = "\033[92m"
    RESET = "\033[0m"
    sep = "\u2560" + "\u2550" * (W + 2) + "\u2563"
    top = "\u2554" + "\u2550" * (W + 2) + "\u2557"
    bot = "\u255a" + "\u2550" * (W + 2) + "\u255d"

    def sig(s):
        return s if s in ("CALL", "PUT") else "\u2014"

    lines = [top, _line(f"\U0001F3AF \u0410\u041d\u0410\u041b\u0418\u0417: {pair}", W), sep]
    if price is not None:
        lines.append(_line(f"\u0426\u0435\u043d\u0430:        {price:.5f}", W))

    # Classic (primary)
    lines.append(_line(f"Classic:     {sig(classic_sig)}", W))
    if classic_sig is None and c_reason and c_reason not in ("OK", "NO_SIGNAL"):
        lines.append(_line(f"  \u043f\u0440\u0438\u0447\u0438\u043d\u0430:   {str(c_reason)[:W-16]}", W))
    lines.append(sep)

    # ИТОГ по Classic
    if classic_sig == "CALL":
        lines.append(_line(f"\u0418\u0422\u041e\u0413:        {BLUE}\u2b06 CALL{RESET}", W))
    elif classic_sig == "PUT":
        lines.append(_line(f"\u0418\u0422\u041e\u0413:        {RED}\u2b07 PUT{RESET}", W))
    else:
        lines.append(_line(f"\u0418\u0422\u041e\u0413:        {GRAY}\u23f8 \u041d\u0435\u0442 \u0441\u0438\u0433\u043d\u0430\u043b\u0430{RESET}", W))
    lines.append(sep)

    # SR_CCI (справочно)
    lines.append(_line("\u0421\u043f\u0440\u0430\u0432\u043e\u0447\u043d\u043e:", W))
    if sr_sig in ("CALL", "PUT"):
        if classic_sig == sr_sig:
            line = f"  SR_CCI:    {sr_sig} (\u0441\u043e\u0432\u043f\u0430\u0434\u0430\u0435\u0442)"
        elif classic_sig in ("CALL", "PUT"):
            line = f"  SR_CCI:    {sr_sig} (\u043f\u0440\u043e\u0442\u0438\u0432\u043e\u043f\u043e\u043b\u043e\u0436\u043d\u043e)"
        else:
            line = f"  SR_CCI:    {sr_sig} (\u0442\u043e\u043b\u044c\u043a\u043e SR_CCI)"
        lines.append(_line(line[:W], W))
    elif s_reason == "TIMEOUT":
        lines.append(_line("  SR_CCI:    \u2014 (\u0442\u0430\u0439\u043c\u0430\u0443\u0442)", W))
    elif s_reason and s_reason not in ("OK", "SKIP", "NO_SIGNAL"):
        lines.append(_line(f"  SR_CCI:    \u2014 ({str(s_reason)[:W-16]})", W))
    else:
        lines.append(_line("  SR_CCI:    \u2014 (\u043d\u0435\u0442 \u0441\u0438\u0433\u043d\u0430\u043b\u0430)", W))
    lines.append(sep)

    # WR: оба
    lines.append(_line("WR (24\u0447):", W))
    if c_stats and c_stats.get("winrate") is not None:
        wr = c_stats["winrate"]; t = c_stats.get("total", "?")
        col = GREEN if wr >= 52 else (YELLOW if wr >= 50 else RED)
        lines.append(_line(f"  Classic:   {col}{wr:.1f}%{RESET} ({t} \u0441\u0438\u0433\u043d.)", W))
    else:
        lines.append(_line("  Classic:   \u043d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445", W))
    if s_stats and s_stats.get("winrate") is not None:
        wr = s_stats["winrate"]; t = s_stats.get("total", "?")
        col = GREEN if wr >= 52 else (YELLOW if wr >= 50 else RED)
        lines.append(_line(f"  SR_CCI:    {col}{wr:.1f}%{RESET} ({t} \u0441\u0438\u0433\u043d.)", W))
    else:
        lines.append(_line("  SR_CCI:    \u043d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445", W))

    lines.append(sep)
    lines.append(_line("\u26a0 \u0410\u043d\u0430\u043b\u0438\u0437, \u043d\u0435 \u0433\u0430\u0440\u0430\u043d\u0442\u0438\u044f. \u041f\u0440\u043e\u0432\u0435\u0440\u044c \u0433\u0440\u0430\u0444\u0438\u043a.", W))
    lines.append(bot)
    print("\n".join(lines))


async def analyze_pair(client, pair, cfg):
    """Одна сессия. Classic (25с) + SR_CCI (20с). Родные функции бота."""
    classic_sig = None
    classic_reason = "SKIP"
    price = None
    t0 = time.time()
    try:
        r = await asyncio.wait_for(classic_full_analysis(client, pair), timeout=25)
        if isinstance(r, tuple) and len(r) >= 3:
            classic_sig, price, classic_reason = r[0], r[1], r[2]
        elif isinstance(r, tuple) and len(r) == 2:
            classic_sig, price = r[0], r[1]
            classic_reason = "OK" if classic_sig else "NO_SIGNAL"
    except asyncio.TimeoutError:
        classic_reason = "TIMEOUT"
    except Exception as e:
        classic_reason = f"ERR:{type(e).__name__}"
    print(f"   Classic: {classic_sig or '—'} ({classic_reason}) [{time.time()-t0:.1f}s]")

    sr_sig = None
    sr_reason = "SKIP"
    t0 = time.time()
    try:
        r = await asyncio.wait_for(
            full_analysis_sr_cci(client, pair, cfg, fetch_candles, get_current_price),
            timeout=20
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
    print(f"   SR_CCI:  {sr_sig or '—'} ({sr_reason}) [{time.time()-t0:.1f}s]")

    return classic_sig, sr_sig, price, classic_reason, sr_reason


async def main():
    if len(sys.argv) < 2:
        print("Использование: python analyzer_manual.py EURHUF_otc")
        sys.exit(1)

    raw = sys.argv[1].strip()
    if "_" in raw:
        base, suffix = raw.rsplit("_", 1)
        pair = base.upper() + "_" + suffix.lower()
    else:
        pair = raw.upper() + "_otc"

    ssid = load_ssid()
    if not ssid:
        print("❌ SSID не найден")
        sys.exit(1)

    # pgrep-проверка
    pg = subprocess.run(["pgrep", "-f", "analyzer_bot.py"], capture_output=True, text=True)
    if pg.stdout.strip():
        pids = ", ".join(pg.stdout.strip().split())
        print(f"⚠ Бот работает (PID: {pids}). Остановите перед анализатором.")
        print("   touch stop.flag  # или  pkill -f analyzer_bot.py")
        sys.exit(2)

    cfg = load_cfg()
    classic_cfg = dict(cfg)
    classic_cfg["strategy_mode"] = "Classic"
    analyzer_bot.CFG = classic_cfg

    print(f"⏳ Анализ {pair}...")
    async with PocketOptionAsync(ssid=ssid) as client:
        classic_sig, sr_sig, price, c_reason, s_reason = await analyze_pair(client, pair, cfg)

    c_stats = load_stats_one(pair, CLASSIC_STATS)
    s_stats = load_stats_one(pair, SR_CCI_STATS)
    print_card(pair, classic_sig, sr_sig, price, c_stats, s_stats, c_reason, s_reason)

    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹ Остановлено")
