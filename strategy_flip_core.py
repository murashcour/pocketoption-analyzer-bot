#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategy_flip_core.py (PATCH_097e): Flip Core (UT Bot ATR trailing stop).

Логика BinoView:
- UT line: ATR trailing stop (Wilder ATR)
- Flip UP: prev.close < prev.ts AND curr.close > curr.ts → CALL
- Flip DOWN: prev.close > prev.ts AND curr.close < curr.ts → PUT
- Вход по close свечи сигнала, экспирация 60 сек.
"""
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def _h(c): return c["high"] if isinstance(c, dict) else c[2]
def _l(c): return c["low"] if isinstance(c, dict) else c[3]
def _cl(c): return c["close"] if isinstance(c, dict) else c[4]


def ut_line(candles: list, period: int = 14, mult: float = 1.0) -> list:
    """Wilder ATR trailing stop."""
    n = len(candles)
    if n == 0:
        return []
    ts = [None] * n
    atr = _h(candles[0]) - _l(candles[0])
    ts[0] = _cl(candles[0]) - atr * mult
    for i in range(1, n):
        h, l = _h(candles[i]), _l(candles[i])
        cl, pc = _cl(candles[i]), _cl(candles[i - 1])
        tr = max(h - l, abs(h - pc), abs(l - pc))
        atr = (atr * (period - 1) + tr) / period
        loss = atr * mult
        prev = ts[i - 1]
        if cl > prev and pc > prev:
            ts[i] = max(prev, cl - loss)
        elif cl < prev and pc < prev:
            ts[i] = min(prev, cl + loss)
        elif cl > prev:
            ts[i] = cl - loss
        else:
            ts[i] = cl + loss
    return ts


async def full_analysis_flip_core(client, pair: str, cfg: dict, fetch_candles, get_current_price) -> Tuple[Optional[str], Optional[float], str]:
    """Возвращает (signal, price, reason)."""
    # Нужно минимум 30 свечей для стабильного UT line
    c1 = await fetch_candles(client, pair, 60, 200)
    if not c1 or len(c1) < 30:
        return None, None, "NO_DATA"

    atr_period = int(cfg.get("flip_core_atr_period", 14))
    atr_mult = float(cfg.get("flip_core_atr_mult", 1.0))

    ts = ut_line(c1, atr_period, atr_mult)
    if len(ts) < 2 or ts[-1] is None or ts[-2] is None:
        return None, None, "NO_UT"

    price = await get_current_price(client, pair)
    if price is None:
        price = _cl(c1[-1])

    prev_close, prev_ts = _cl(c1[-2]), ts[-2]
    curr_close, curr_ts = _cl(c1[-1]), ts[-1]

    signal = None
    if prev_close < prev_ts and curr_close > curr_ts:
        signal = "CALL"
        logger.info(f"   [FLIP_CORE] FLIP UP @ {curr_close:.5f} (ts={curr_ts:.5f}) -> CALL")
    elif prev_close > prev_ts and curr_close < curr_ts:
        signal = "PUT"
        logger.info(f"   [FLIP_CORE] FLIP DOWN @ {curr_close:.5f} (ts={curr_ts:.5f}) -> PUT")
    else:
        return None, price, "NO_FLIP"

    return signal, price, "OK"


def backtest_flip_core(candles: list, cfg: dict) -> tuple:
    """Бэктест для pair_stats (закрытая логика). Возвращает (wins, losses)."""
    if len(candles) < 50:
        return 0, 0
    atr_period = int(cfg.get("flip_core_atr_period", 14))
    atr_mult = float(cfg.get("flip_core_atr_mult", 1.0))
    ts = ut_line(candles, atr_period, atr_mult)
    wins = losses = 0
    for i in range(1, len(candles) - 1):
        if ts[i - 1] is None or ts[i] is None:
            continue
        pc, pts = _cl(candles[i - 1]), ts[i - 1]
        cc, cts = _cl(candles[i]), ts[i]
        sig = None
        if pc < pts and cc > cts:
            sig = 1
        elif pc > pts and cc < cts:
            sig = -1
        if sig is None:
            continue
        nxt = _cl(candles[i + 1])
        d = (nxt - cc) * sig
        if d > 0: wins += 1
        else: losses += 1
    return wins, losses
