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
PAYOUT_CACHE = Path(BASE_DIR) / "pair_payouts.json"
PAYOUT_TTL = 600


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



def load_all_stats(path):
    """Возвращает {pair: stats} из JSON-файла (с нормализацией total)."""
    if not path.exists():
        return {}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(d, dict):
        return {}
    for p, st in d.items():
        if isinstance(st, dict) and "total" not in st:
            w = int(st.get("wins", 0) or 0)
            l = int(st.get("losses", 0) or 0)
            if w or l:
                st["total"] = w + l
    return d



def get_blacklist():
    """Возвращает set пар из EXOTIC_BLACKLIST (read-only, не трогает бот)."""
    try:
        import analyzer_bot
        return set(analyzer_bot.EXOTIC_BLACKLIST)
    except Exception:
        return set()


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


def _norm_pair(raw: str) -> str:
    """EURUSD_OTC -> EURUSD_otc; EURUSD -> EURUSD_otc."""
    if "_" in raw:
        base, suffix = raw.rsplit("_", 1)
        return base.upper() + "_" + suffix.lower()
    return raw.upper() + "_otc"


def cmd_list(min_wr: float = 50.0, min_signals: int = 200):
    """Список пар с WR >= min_wr и сигналов >= min_signals, сортировка по max WR.
    Не требует API — работает даже при запущенном боте.
    [BL] — пара в EXOTIC_BLACKLIST (мёртвая для бота, но в JSON есть)."""
    classic = load_all_stats(CLASSIC_STATS)
    sr_cci = load_all_stats(SR_CCI_STATS)
    blacklist = get_blacklist()
    all_pairs = set(classic.keys()) | set(sr_cci.keys())

    rows = []
    for p in all_pairs:
        c = classic.get(p, {})
        s = sr_cci.get(p, {})
        c_wr = c.get("winrate")
        s_wr = s.get("winrate")
        c_tot = c.get("total", 0)
        s_tot = s.get("total", 0)
        best_wr = max(c_wr or 0, s_wr or 0)
        best_tot = max(c_tot, s_tot)
        if best_wr < min_wr:
            continue
        if best_tot < min_signals:
            continue
        rows.append({
            "pair": p,
            "c": c_wr, "s": s_wr,
            "tot": best_tot,
            "best": best_wr,
            "bl": p in blacklist,
        })

    rows.sort(key=lambda x: x["best"], reverse=True)

    print(f"\n\U0001F4CA \u041f\u0430\u0440\u044b \u0441 WR \u2265 {min_wr}% \u0438 \u2265 {min_signals} \u0441\u0438\u0433\u043d. "
          f"\u2014 {len(rows)} \u0448\u0442. (\u0441\u043e\u0440\u0442\u0438\u0440\u043e\u0432\u043a\u0430 \u043f\u043e max WR)\n")
    print(f"{'PAIR':24} {'Classic':>10} {'SR_CCI':>10} {'\u0421\u0438\u0433\u043d.':>7}  {'\u0420\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0430\u0446\u0438\u044f':<20}")
    print("-" * 82)
    n_bl = 0
    for r in rows:
        p = r["pair"]
        marker = " [BL]" if r["bl"] else ""
        if r["bl"]:
            n_bl += 1
        label = p + marker
        if len(label) > 24:
            label = label[:23] + "."
        c_str = f"{r['c']:.1f}%" if r["c"] is not None else "\u2014"
        s_str = f"{r['s']:.1f}%" if r["s"] is not None else "\u2014"
        # Рекомендация
        c_wr, s_wr = r["c"], r["s"]
        if r["bl"]:
            rec = "BLACKLIST"
        elif c_wr is not None and s_wr is not None:
            if c_wr >= 52 and s_wr < 50:
                rec = "Classic \u2b50"
            elif s_wr >= 52 and c_wr < 50:
                rec = "SR_CCI \u2b50"
            elif c_wr >= 52 and s_wr >= 52:
                rec = "\u041e\u0411\u0410 \u2b50\u2b50"
            elif c_wr >= 50 and s_wr >= 50:
                rec = "\u043f\u043e\u0433\u0440\u0430\u043d\u0438\u0447\u043d\u0430\u044f"
            else:
                rec = "\u2014"
        elif c_wr is not None and c_wr >= 50:
            rec = "Classic"
        elif s_wr is not None and s_wr >= 50:
            rec = "SR_CCI"
        else:
            rec = "\u2014"
        print(f"{label:24} {c_str:>10} {s_str:>10} {r['tot']:>7}  {rec:<20}")

    print()
    print(f"\u0412\u0441\u0435\u0433\u043e: {len(rows)} \u043f\u0430\u0440 (\u0438\u0437 \u043d\u0438\u0445 \u0432 \u0431\u043b\u044d\u043a\u043b\u0438\u0441\u0442\u0435: {n_bl})")
    print()
    print("\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435:")
    print("  python analyzer_manual.py <PAIR>       \u2014 \u0430\u043d\u0430\u043b\u0438\u0437 \u043e\u0434\u043d\u043e\u0439 \u043f\u0430\u0440\u044b")
    print("  python analyzer_manual.py --top 5      \u2014 \u0442\u043e\u043f-5 \u043f\u043e WR")
    print("  python analyzer_manual.py              \u2014 \u0438\u043d\u0442\u0435\u0440\u0430\u043a\u0442\u0438\u0432")


def cmd_pgrep_check():
    """Проверка, что бот не работает (для режимов с API)."""
    pg = subprocess.run(["pgrep", "-f", "analyzer_bot.py"], capture_output=True, text=True)
    if pg.stdout.strip():
        pids = ", ".join(pg.stdout.strip().split())
        print(f"\u26a0 \u0411\u043e\u0442 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 (PID: {pids}). \u041e\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u0435 \u043f\u0435\u0440\u0435\u0434 \u0430\u043d\u0430\u043b\u0438\u0437\u0430\u0442\u043e\u0440\u043e\u043c.")
        print("   touch stop.flag  # \u0438\u043b\u0438  pkill -f analyzer_bot.py")
        sys.exit(2)


async def analyze_one_pair(ssid: str, pair: str, cfg: dict):
    """Полный анализ одной пары: сессия PocketOptionAsync + карточка."""
    classic_cfg = dict(cfg)
    classic_cfg["strategy_mode"] = "Classic"
    analyzer_bot.CFG = classic_cfg

    async with PocketOptionAsync(ssid=ssid) as client:
        classic_sig, sr_sig, price, c_reason, s_reason = await analyze_pair(client, pair, cfg)

    c_stats = load_stats_one(pair, CLASSIC_STATS)
    s_stats = load_stats_one(pair, SR_CCI_STATS)
    print_card(pair, classic_sig, sr_sig, price, c_stats, s_stats, c_reason, s_reason)


def _get_top_pairs(n: int, min_wr: float = 50.0):
    """Возвращает список [(pair, best_wr)] — топ по max(Classic, SR_CCI)."""
    classic = load_all_stats(CLASSIC_STATS)
    sr_cci = load_all_stats(SR_CCI_STATS)
    all_pairs = set(classic.keys()) | set(sr_cci.keys())
    rows = []
    for p in all_pairs:
        c = classic.get(p, {}).get("winrate") or 0
        s = sr_cci.get(p, {}).get("winrate") or 0
        best = max(c, s)
        if best >= min_wr:
            rows.append((p, best))
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows[:n]


async def cmd_top(n: int, min_wr: float = 50.0):
    """Анализ топ-N пар по WR."""
    if n < 1 or n > 20:
        print("\u274c N \u0434\u043e\u043b\u0436\u043d\u043e \u0431\u044b\u0442\u044c 1..20")
        sys.exit(1)

    ssid = load_ssid()
    if not ssid:
        print("\u274c SSID \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d")
        sys.exit(1)

    cmd_pgrep_check()
    cfg = load_cfg()

    top = _get_top_pairs(n, min_wr)
    if not top:
        print(f"\u26a0 \u041d\u0435\u0442 \u043f\u0430\u0440 \u0441 WR \u2265 {min_wr}%")
        os._exit(0)

    pairs_str = ", ".join(f"{p}({w:.1f}%)" for p, w in top)
    print(f"\U0001F504 \u0422\u043e\u043f-{len(top)} \u043f\u043e WR (\u2265 {min_wr}%): {pairs_str}\n")
    print(f"\u23f1 \u041f\u0440\u0438\u043c\u0435\u0440\u043d\u043e {len(top) * 45}\u2013{len(top) * 60} \u0441\u0435\u043a\n")

    for i, (pair, wr) in enumerate(top, 1):
        print(f"\n{'=' * 56}")
        print(f"[{i}/{len(top)}] {pair}  (best WR {wr:.1f}%)")
        print(f"{'=' * 56}")
        try:
            await analyze_one_pair(ssid, pair, cfg)
        except Exception as e:
            print(f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430 {pair}: {type(e).__name__}: {e}")

    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(0)


async def cmd_interactive():
    """Интерактив: спрашивает пару, анализирует, повторяет."""
    ssid = load_ssid()
    if not ssid:
        print("\u274c SSID \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d")
        sys.exit(1)

    cmd_pgrep_check()
    cfg = load_cfg()

    print("\U0001F3AE \u0418\u043d\u0442\u0435\u0440\u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0439 \u0440\u0435\u0436\u0438\u043c. \u041a\u043e\u043c\u0430\u043d\u0434\u044b:")
    print("  PAIR        \u2014 \u0430\u043d\u0430\u043b\u0438\u0437 \u043f\u0430\u0440\u044b (\u043d\u0430\u043f\u0440. EURHUF_otc)")
    print("  list        \u2014 \u0441\u043f\u0438\u0441\u043e\u043a \u043f\u0430\u0440 \u0441 WR \u2265 50%")
    print("  q / exit    \u2014 \u0432\u044b\u0445\u043e\u0434\n")

    while True:
        try:
            user = input("\u041f\u0430\u0440\u0430: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\u23f9 \u0412\u044b\u0445\u043e\u0434")
            break
        if not user:
            continue
        if user.lower() in ("q", "quit", "exit"):
            print("\u23f9 \u0412\u044b\u0445\u043e\u0434")
            break
        if user.lower() == "list":
            cmd_list(50.0)
            continue

        pair = _norm_pair(user)
        print(f"\u23f3 \u0410\u043d\u0430\u043b\u0438\u0437 {pair}...")
        try:
            await analyze_one_pair(ssid, pair, cfg)
        except Exception as e:
            print(f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430: {type(e).__name__}: {e}")

    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(0)


def load_payout_cache():
    """Загружает payout из кеша pair_monitor.py. Пусто если протух."""
    if not PAYOUT_CACHE.exists():
        return {}
    try:
        d = json.loads(PAYOUT_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    ts = d.get("_ts", 0)
    if time.time() - ts > PAYOUT_TTL:
        return {}
    return d


async def refresh_payouts(client, pairs):
    """Обновляет payout для списка пар через API."""
    from analyzer_bot import check_payout
    out = {"_ts": time.time()}
    for p in pairs:
        try:
            v = await asyncio.wait_for(check_payout(client, p), timeout=5)
            if v is not None:
                out[p] = round(float(v), 1)
        except Exception:
            pass
    try:
        PAYOUT_CACHE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return out


async def cmd_auto(ssid: str, cfg: dict):
    """PATCH_092: автоперебор Classic. После сигнала: +WIN / -LOSS / s skip / q выход."""
    classic = load_all_stats(CLASSIC_STATS)
    sr_cci = load_all_stats(SR_CCI_STATS)
    blacklist = get_blacklist()

    MIN_WR_AUTO = 45.0
    MIN_SIGNALS = 200

    async with PocketOptionAsync(ssid=ssid) as client:
        payouts = load_payout_cache()
        if not payouts:
            print("\u23f3 \u041e\u0431\u043d\u043e\u0432\u043b\u044f\u044e payout (\u043a\u0435\u0448 \u043f\u0443\u0441\u0442)... 20-30 \u0441\u0435\u043a")
            all_pairs = list(set(classic.keys()) | set(sr_cci.keys()))
            payouts = await refresh_payouts(client, all_pairs)
            print(f"   \u2705 Payout \u043e\u0431\u043d\u043e\u0432\u043b\u0451\u043d ({len(payouts) - 1} \u043f\u0430\u0440)")
        else:
            print(f"   \u2705 Payout \u0438\u0437 \u043a\u0435\u0448\u0430 ({len(payouts) - 1} \u043f\u0430\u0440)")

        candidates = []
        for p in classic.keys():
            c_wr = classic[p].get("winrate") or 0
            c_tot = classic[p].get("total", 0)
            s_tot = sr_cci.get(p, {}).get("total", 0)
            if c_wr < MIN_WR_AUTO:
                continue
            if max(c_tot, s_tot) < MIN_SIGNALS:
                continue
            if p in blacklist:
                continue
            pay = payouts.get(p)
            threshold = 80.0 if p.endswith("_otc") else 75.0
            if pay is None or pay < threshold:
                continue
            candidates.append({"pair": p, "wr": c_wr, "pay": pay})

        candidates.sort(key=lambda x: -x["wr"])

        if not candidates:
            print("\u274c \u041d\u0435\u0442 \u043f\u0430\u0440 \u043f\u043e\u0441\u043b\u0435 \u0444\u0438\u043b\u044c\u0442\u0440\u043e\u0432")
            os._exit(0)

        print(f"\n\U0001F504 \u0413\u043e\u0442\u043e\u0432\u043e: {len(candidates)} \u043f\u0430\u0440 (\u0441\u043e\u0440\u0442\u0438\u0440\u043e\u0432\u043a\u0430 \u043f\u043e Classic WR)\n")
        for i, c in enumerate(candidates, 1):
            print(f"   {i}. {c['pair']:20} Classic {c['wr']:5.1f}%  payout {c['pay']:3.0f}%")
        print()

        classic_cfg = dict(cfg)
        classic_cfg["strategy_mode"] = "Classic"
        analyzer_bot.CFG = classic_cfg

        idx = 0
        pass_num = 1
        BLUE = "\033[94m"
        RED = "\033[91m"
        RESET = "\033[0m"

        while True:
            if idx >= len(candidates):
                print(f"\n\u2705 \u041f\u0440\u043e\u0445\u043e\u0434 {pass_num} \u0437\u0430\u0432\u0435\u0440\u0448\u0451\u043d: {len(candidates)} \u043f\u0430\u0440")
                try:
                    ans = input("[r] \u043d\u043e\u0432\u044b\u0439 \u043f\u0440\u043e\u0445\u043e\u0434 / [q] \u0432\u044b\u0445\u043e\u0434: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    ans = "q"
                if ans != "r":
                    print("\n\u23f9 \u0412\u044b\u0445\u043e\u0434")
                    try:
                        sys.stdout.flush()
                    except Exception:
                        pass
                    os._exit(0)
                idx = 0
                pass_num += 1
                continue

            c = candidates[idx]
            pair = c["pair"]
            print(f"\n[{idx + 1}/{len(candidates)}] {pair} (Classic {c['wr']:.1f}%, payout {c['pay']:.0f}%)")
            print("   \u23f3 \u0410\u043d\u0430\u043b\u0438\u0437...")

            t0 = time.time()
            try:
                r = await asyncio.wait_for(classic_full_analysis(client, pair), timeout=30)
            except asyncio.TimeoutError:
                print("   \u23f1 \u0422\u0430\u0439\u043c\u0430\u0443\u0442 \u2192 \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0430\u044f")
                idx += 1
                continue
            except Exception as e:
                print(f"   \u274c {type(e).__name__}: {e} \u2192 \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0430\u044f")
                idx += 1
                continue

            dt = time.time() - t0

            if isinstance(r, tuple) and len(r) >= 3:
                sig, price, reason = r[0], r[1], r[2]
            elif isinstance(r, tuple) and len(r) == 2:
                sig, price = r[0], r[1]
                reason = "OK" if sig else "NO_SIGNAL"
            else:
                sig, price, reason = r, None, ""

            if not sig:
                print(f"   Classic: \u2014 ({reason}) [{dt:.1f}s] \u2192 \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0430\u044f")
                idx += 1
                continue

            color = BLUE if sig == "CALL" else RED
            arrow = "\u2b06" if sig == "CALL" else "\u2b07"
            print(f"\n   \u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557")
            print(f"   \u2551 \U0001F3AF \u0421\u0418\u0413\u041d\u0410\u041b: {pair}  \u2192  {color}{arrow} {sig}{RESET}")
            print(f"   \u2551 WR Classic: {c['wr']:.1f}%   |   Payout: {c['pay']:.0f}%")
            if price:
                print(f"   \u2551 \u0426\u0435\u043d\u0430: {price:.5f}")
            print(f"   \u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d")
            print(f"   \U0001F3AC \u041e\u0442\u043a\u0440\u043e\u0439\u0442\u0435: {pair} {sig} $1.00, 60\u0441")

            while True:
                try:
                    ans = input("   [+] WIN  [-] LOSS  [s] skip  [q] \u0432\u044b\u0445\u043e\u0434: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    ans = "q"
                if ans == "+":
                    print(f"   \u2705 WIN \u2192 \u043e\u0441\u0442\u0430\u0451\u043c\u0441\u044f \u043d\u0430 {pair}")
                    break
                elif ans == "-":
                    print("   \u274c LOSS \u2192 \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0430\u044f")
                    idx += 1
                    break
                elif ans in ("s", ""):
                    print("   \u2192 \u043f\u0440\u043e\u043f\u0443\u0441\u043a, \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0430\u044f")
                    idx += 1
                    break
                elif ans == "q":
                    print("\n\u23f9 \u0412\u044b\u0445\u043e\u0434")
                    try:
                        sys.stdout.flush()
                    except Exception:
                        pass
                    os._exit(0)
                else:
                    print("   \u041d\u0435 \u043f\u043e\u043d\u044f\u043b. +, -, s, q")


async def main():
    # Без аргументов — интерактив
    if len(sys.argv) < 2:
        await cmd_interactive()
        return

    arg = sys.argv[1].strip().lower()

    # --list (без API, работает даже при работающем боте)
    if arg == "--list":
        cmd_list(50.0)
        try:
            sys.stdout.flush()
        except Exception:
            pass
        os._exit(0)

    # --top N
    if arg == "--auto":
        await cmd_auto(ssid, cfg)
        return

    if arg == "--top":
        if len(sys.argv) < 3 or not sys.argv[2].strip().isdigit():
            print("\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: python analyzer_manual.py --top N   (N = 1..20)")
            sys.exit(1)
        n = int(sys.argv[2].strip())
        await cmd_top(n)
        return

    # Обычный анализ одной пары
    pair = _norm_pair(sys.argv[1].strip())

    ssid = load_ssid()
    if not ssid:
        print("\u274c SSID \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d")
        sys.exit(1)

    cmd_pgrep_check()
    cfg = load_cfg()

    print(f"\u23f3 \u0410\u043d\u0430\u043b\u0438\u0437 {pair}...")
    await analyze_one_pair(ssid, pair, cfg)

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
