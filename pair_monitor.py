#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pair_monitor.py (PATCH_087): монитор пар с WR + payout + рекомендации.
Запуск: watch -n 10 python3 pair_monitor.py
Не подключается к API, если payout-кеш свежий (моложе 10 мин).
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent
CLASSIC_STATS = BASE_DIR / "pair_stats_classic.json"
SR_CCI_STATS = BASE_DIR / "pair_stats_sr_cci.json"
PAYOUT_CACHE = BASE_DIR / "pair_payouts.json"
SSID_FILE = os.path.expanduser("~/.po_ssid")

MIN_SIGNALS = 200          # минимум сигналов (отсечь шум)
MIN_WR = 50.0              # порог WR для показа
PAYOUT_TTL = 600           # 10 мин — срок жизни payout-кеша
TOP_N = 20                 # сколько пар показывать


def load_ssid():
    s = os.getenv("PO_SSID", "").strip()
    if not s and os.path.exists(SSID_FILE):
        with open(SSID_FILE) as f:
            s = f.read().strip()
    return s


def load_all_stats(path):
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
    try:
        import analyzer_bot
        return set(analyzer_bot.EXOTIC_BLACKLIST)
    except Exception:
        return set()


def load_payout_cache():
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


async def refresh_payouts(pairs):
    """Подключается к API и запрашивает payout для пар. Сохраняет в кеш."""
    try:
        from BinaryOptionsToolsV2 import PocketOptionAsync
        from analyzer_bot import check_payout
    except Exception as e:
        print(f"⚠ refresh_payouts: {type(e).__name__}: {e}")
        return {}

    ssid = load_ssid()
    if not ssid:
        return {}

    out = {"_ts": time.time()}
    try:
        async with PocketOptionAsync(ssid=ssid) as client:
            for p in pairs:
                try:
                    v = await asyncio.wait_for(check_payout(client, p), timeout=5)
                    if v is not None:
                        out[p] = round(float(v), 1)
                except asyncio.TimeoutError:
                    pass
                except Exception:
                    pass
    except Exception as e:
        print(f"⚠ refresh_payouts connect: {type(e).__name__}: {e}")
        return {}

    try:
        PAYOUT_CACHE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return out


def _dw(s):
    import unicodedata
    w = 0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ("W", "F") or ord(ch) > 0x1F000:
            w += 2
        else:
            w += 1
    return w


def _line(content, W):
    import re
    clean = re.sub(r"\033\[[0-9;]*m", "", content)
    pad = max(0, W - _dw(clean))
    return f"\u2551 {content}{' ' * pad} \u2551"


def render(payouts):
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
        best = max(c_wr or 0, s_wr or 0)
        if best < MIN_WR:
            continue
        # фильтр по сигналам: хотя бы в одной стратегии ≥ MIN_SIGNALS
        if max(c_tot, s_tot) < MIN_SIGNALS:
            continue
        pay = payouts.get(p)
        rows.append({
            "pair": p,
            "classic": c_wr, "sr_cci": s_wr,
            "c_tot": c_tot, "s_tot": s_tot,
            "best": best,
            "payout": pay,
            "blacklist": p in blacklist,
        })

    rows.sort(key=lambda x: x["best"], reverse=True)
    shown = rows[:TOP_N]

    W = 72
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    GRAY = "\033[90m"
    RESET = "\033[0m"

    def wr_str(v):
        if v is None:
            return "\u2014"
        col = GREEN if v >= 52 else (YELLOW if v >= 50 else RED)
        return f"{col}{v:5.1f}%{RESET}"

    def pay_str(v):
        if v is None:
            return "\u2014"
        if v >= 90:
            return f"{GREEN}{v:4.0f}%{RESET}"
        if v >= 88:
            return f"{YELLOW}{v:4.0f}%{RESET}"
        return f"{RED}{v:4.0f}%{RESET}"

    top = "\u2554" + "\u2550" * (W + 2) + "\u2557"
    sep = "\u2560" + "\u2550" * (W + 2) + "\u2563"
    bot = "\u255a" + "\u2550" * (W + 2) + "\u255d"

    ts = payouts.get("_ts", 0)
    age = int(time.time() - ts) if ts else -1
    age_str = f"{age}\u0441" if age >= 0 else "?"
    lines = [
        top,
        _line(f"\U0001F4CA PAIR MONITOR    \u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u043e: {age_str} \u043d\u0430\u0437\u0430\u0434", W),
        sep,
        _line(f"{'PAIR':22} {'Classic':>9} {'SR_CCI':>9} {'\u0421\u0438\u0433\u043d.':>6} {'Pay':>6}  {'\u0420\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0430\u0446\u0438\u044f':<18}", W),
        _line("-" * W, W),
    ]

    n_blacklist_shown = 0
    n_payout_ok = 0
    for r in shown:
        p = r["pair"]
        marker = " [BL]" if r["blacklist"] else ""
        if r["blacklist"]:
            n_blacklist_shown += 1
        pair_label = p + marker
        if len(pair_label) > 22:
            pair_label = pair_label[:21] + "."

        # рекомендация
        c_wr, s_wr, pay = r["classic"], r["sr_cci"], r["payout"]
        if r["blacklist"]:
            rec = "BLACKLIST"
        elif pay is not None and pay < 90:
            rec = "\u26a0 payout <90"
        elif c_wr is not None and s_wr is not None and c_wr >= 52 and s_wr >= 52:
            rec = "\u041e\u0411\u0410 \u2b50\u2b50"
        elif c_wr is not None and c_wr >= 52 and (s_wr is None or s_wr < 50):
            rec = "Classic \u2b50"
        elif s_wr is not None and s_wr >= 52 and (c_wr is None or c_wr < 50):
            rec = "SR_CCI \u2b50"
        elif (c_wr or 0) >= 50 and (s_wr or 0) >= 50:
            rec = "\u043f\u043e\u0433\u0440\u0430\u043d\u0438\u0447\u043d\u0430\u044f"
        else:
            rec = "\u2014"

        if not r["blacklist"] and pay is not None and pay >= 90:
            n_payout_ok += 1

        tot_label = f"{max(r['c_tot'], r['s_tot'])}"
        lines.append(_line(
            f"{pair_label:22} {wr_str(c_wr):>9} {wr_str(s_wr):>9} {tot_label:>6} {pay_str(pay):>6}  {rec:<18}",
            W,
        ))

    if len(rows) > TOP_N:
        lines.append(_line(f"... \u0438 \u0435\u0449\u0451 {len(rows) - TOP_N} \u043f\u0430\u0440", W))

    lines.append(sep)
    lines.append(_line(
        f"\u0412\u0441\u0435\u0433\u043e (\u2265{MIN_SIGNALS} \u0441\u0438\u0433\u043d., WR\u2265{MIN_WR:.0f}%): {len(rows)}  |  "
        f"payout \u226590%: {n_payout_ok}  |  \u0432 \u0431\u043b\u044d\u043a\u043b\u0438\u0441\u0442\u0435: {n_blacklist_shown}",
        W,
    ))
    lines.append(bot)
    print("\n".join(lines))


def main():
    # Собираем список пар для payout-проверки (только те, что показываем)
    classic = load_all_stats(CLASSIC_STATS)
    sr_cci = load_all_stats(SR_CCI_STATS)
    all_pairs = set(classic.keys()) | set(sr_cci.keys())
    candidates = []
    for p in all_pairs:
        c = classic.get(p, {})
        s = sr_cci.get(p, {})
        c_wr = c.get("winrate") or 0
        s_wr = s.get("winrate") or 0
        c_tot = c.get("total", 0)
        s_tot = s.get("total", 0)
        if max(c_wr, s_wr) >= MIN_WR and max(c_tot, s_tot) >= MIN_SIGNALS:
            candidates.append(p)

    payouts = load_payout_cache()
    if not payouts and candidates:
        # Кеш пустой или протух — обновляем
        payouts = asyncio.run(refresh_payouts(candidates))
    elif candidates and payouts:
        # Кеш есть, но новых пар может не хватать
        missing = [p for p in candidates if p not in payouts]
        if missing:
            extra = asyncio.run(refresh_payouts(missing))
            if extra:
                payouts.update(extra)
                payouts["_ts"] = extra.get("_ts", payouts.get("_ts", 0))

    render(payouts)


if __name__ == "__main__":
    main()
