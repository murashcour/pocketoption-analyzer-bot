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


def load_pair_stats(pair: str) -> dict:
    """PATCH_077: читает оба JSON — Classic и SR_CCI.
    Возвращает {"classic": {...} | None, "sr_cci": {...} | None}."""
    out = {"classic": None, "sr_cci": None}
    for key, fname in (("classic", "pair_stats_classic.json"),
                       ("sr_cci", "pair_stats_sr_cci.json")):
        p = Path(BASE_DIR) / fname
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        stats = data.get(pair) or data.get(pair.lower()) or data.get(pair.upper())
        if isinstance(stats, dict) and "total" not in stats:
            w = stats.get("wins", 0) or 0
            l = stats.get("losses", 0) or 0
            if w or l:
                stats["total"] = int(w) + int(l)
        if isinstance(stats, dict):
            out[key] = stats
    return out


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


def print_card(pair, classic_sig, sr_sig, price, stats, c_reason="", s_reason=""):
    """PATCH_077: Classic primary, SR_CCI справочно. WR — оба."""
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

    # --- Classic (primary) ---
    lines.append(_line(f"Classic:     {_sig(classic_sig)}", W))
    if classic_sig is None and c_reason and c_reason != "OK":
        _cr = str(c_reason)[:W - 16]
        lines.append(_line(f"  \u043f\u0440\u0438\u0447\u0438\u043d\u0430:   {_cr}", W))
    lines.append(sep)

    # --- ИТОГ по Classic ---
    if classic_sig == "CALL":
        lines.append(_line(f"\u0418\u0422\u041e\u0413:        {BLUE}\u2b06 CALL{RESET}", W))
    elif classic_sig == "PUT":
        lines.append(_line(f"\u0418\u0422\u041e\u0413:        {RED}\u2b07 PUT{RESET}", W))
    else:
        lines.append(_line(f"\u0418\u0422\u041e\u0413:        {GRAY}\u23f8 \u041d\u0435\u0442 \u0441\u0438\u0433\u043d\u0430\u043b\u0430{RESET}", W))
    lines.append(sep)

    # --- SR_CCI (справочно) ---
    lines.append(_line("\u0421\u043f\u0440\u0430\u0432\u043e\u0447\u043d\u043e:", W))
    if sr_sig in ("CALL", "PUT"):
        if classic_sig == sr_sig:
            line = f"  SR_CCI:    {sr_sig} (\u0441\u043e\u0432\u043f\u0430\u0434\u0430\u0435\u0442)"
        elif classic_sig in ("CALL", "PUT"):
            line = f"  SR_CCI:    {sr_sig} (\u043f\u0440\u043e\u0442\u0438\u0432\u043e\u043f\u043e\u043b\u043e\u0436\u043d\u043e)"
        else:
            line = f"  SR_CCI:    {sr_sig} (\u0442\u043e\u043b\u044c\u043a\u043e SR_CCI)"
        if len(line) > W:
            line = line[:W - 1] + "."
        lines.append(_line(line, W))
    elif s_reason == "TIMEOUT":
        lines.append(_line("  SR_CCI:    \u2014 (\u0442\u0430\u0439\u043c\u0430\u0443\u0442)", W))
    elif s_reason and s_reason not in ("OK", "SKIP"):
        _sr = s_reason[:W - 16]
        lines.append(_line(f"  SR_CCI:    \u2014 ({_sr})", W))
    else:
        lines.append(_line("  SR_CCI:    \u2014 (\u043d\u0435\u0442 \u0441\u0438\u0433\u043d\u0430\u043b\u0430)", W))
    lines.append(sep)

    # --- WR: оба ---
    lines.append(_line("WR (24\u0447):", W))
    c = stats.get("classic") or {}
    if c.get("winrate") is not None:
        wr = c["winrate"]
        t = c.get("total", "?")
        col = GREEN if wr >= 52 else (YELLOW if wr >= 50 else RED)
        lines.append(_line(f"  Classic:   {col}{wr:.1f}%{RESET} ({t} \u0441\u0438\u0433\u043d.)", W))
    else:
        lines.append(_line("  Classic:   \u043d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445", W))
    s = stats.get("sr_cci") or {}
    if s.get("winrate") is not None:
        wr = s["winrate"]
        t = s.get("total", "?")
        col = GREEN if wr >= 52 else (YELLOW if wr >= 50 else RED)
        lines.append(_line(f"  SR_CCI:    {col}{wr:.1f}%{RESET} ({t} \u0441\u0438\u0433\u043d.)", W))
    else:
        lines.append(_line("  SR_CCI:    \u043d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445", W))

    lines.append(sep)
    lines.append(_line("\u26a0 \u0410\u043d\u0430\u043b\u0438\u0437, \u043d\u0435 \u0433\u0430\u0440\u0430\u043d\u0442\u0438\u044f. \u041f\u0440\u043e\u0432\u0435\u0440\u044c \u0433\u0440\u0430\u0444\u0438\u043a.", W))
    lines.append(bot)
    print("\n".join(lines))


async def check_active_pair(ssid: str, pair: str) -> bool:
    """PATCH_079: быстрая проверка — есть ли пара в active_assets.
    True — активна, False — нет (мёртвая / недоступна)."""
    try:
        async with PocketOptionAsync(ssid=ssid) as client:
            assets = await asyncio.wait_for(client.active_assets(), timeout=10)
        symbols = {a.get("symbol") for a in assets if a.get("is_active")}
        return pair in symbols
    except Exception as e:
        # Не блокируем — если проверка упала, пробуем анализ (лучше так, чем отказ)
        print(f"\u26a0 \u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 active_assets: {type(e).__name__}: {e}")
        return True


async def combined_analysis(ssid, pair, cfg):
    """PATCH_077c: Classic primary (60s), SR_CCI справочно (30s).
    Два отдельных PocketOptionAsync — live-генератор Classic закрывает websocket."""
    classic_sig = None
    classic_reason = "SKIP"
    price = None
    try:
        async with PocketOptionAsync(ssid=ssid) as client:
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
    sr_reason = "SKIP"
    try:
        async with PocketOptionAsync(ssid=ssid) as client:
            r = await asyncio.wait_for(
                full_analysis_sr_cci(client, pair, cfg, analyzer_bot.fetch_candles, analyzer_bot.get_current_price),
                timeout=30
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
        print("\u274c SSID \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d")
        sys.exit(1)

    # PATCH_081: проверка, что бот не работает (иначе get_candles_live виснет)
    import subprocess
    _pg = subprocess.run(["pgrep", "-f", "analyzer_bot.py"], capture_output=True, text=True)
    if _pg.stdout.strip():
        pids = ", ".join(_pg.stdout.strip().split())
        print(f"\u26a0 \u0411\u043e\u0442 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 (PID: {pids}).")
        print("   \u041e\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u0435 \u0431\u043e\u0442\u0430 \u043f\u0435\u0440\u0435\u0434 \u0437\u0430\u043f\u0443\u0441\u043a\u043e\u043c \u0430\u043d\u0430\u043b\u0438\u0437\u0430\u0442\u043e\u0440\u0430.")
        print("   touch stop.flag  # \u0438\u043b\u0438  pkill -f analyzer_bot.py")
        sys.exit(2)

    cfg = load_cfg()

    # PATCH_079: быстрая проверка active_assets (2-3 сек)
    print(f"\u23f3 \u041f\u0440\u043e\u0432\u0435\u0440\u044f\u044e \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e\u0441\u0442\u044c {pair}...")
    if not await check_active_pair(ssid, pair):
        print(f"\u26a0 {pair} \u043d\u0435\u0442 \u0432 active_assets \u2014 \u043f\u0430\u0440\u0430 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430 \u0441\u0435\u0439\u0447\u0430\u0441")
        try:
            sys.stdout.flush()
        except Exception:
            pass
        os._exit(3)

    # PATCH_081b: monkey-patch только CFG. Родные fetch_candles/get_current_price — не трогаем.
    classic_cfg = dict(cfg)
    classic_cfg["strategy_mode"] = "Classic"
    analyzer_bot.CFG = classic_cfg

    print(f"\u23f3 \u0410\u043d\u0430\u043b\u0438\u0437 {pair}...")

    # PATCH_079: общий таймаут 45с (защита от зависания)
    try:
        classic_sig, sr_sig, price, c_reason, s_reason = await asyncio.wait_for(
            combined_analysis(ssid, pair, cfg), timeout=45
        )
    except asyncio.TimeoutError:
        print(f"\u26a0 \u041e\u0431\u0449\u0438\u0439 \u0442\u0430\u0439\u043c\u0430\u0443\u0442 \u0430\u043d\u0430\u043b\u0438\u0437\u0430 {pair} (>45\u0441)")
        try:
            sys.stdout.flush()
        except Exception:
            pass
        os._exit(4)

    stats = load_pair_stats(pair)
    print_card(pair, classic_sig, sr_sig, price, stats, c_reason, s_reason)

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
        print("\n\u23f9 Остановлено")
