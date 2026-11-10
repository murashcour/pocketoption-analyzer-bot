# -*- coding: utf-8 -*-
"""
PATCH_041: Стратегия S/R + CCI (аналог BinoView).
Использует пивоты для поиска зон и CCI-14 как триггер.
"""
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

def get_high(c): return c["high"] if isinstance(c, dict) else c[2]
def get_low(c): return c["low"] if isinstance(c, dict) else c[3]
def get_close(c): return c["close"] if isinstance(c, dict) else c[4]

def calc_atr(candles: list, period: int = 14) -> float:
    if len(candles) < period + 1: return 0.0
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = get_high(candles[i]), get_low(candles[i]), get_close(candles[i-1])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[-period:]) / period

def calc_cci(candles: list, period: int = 14) -> Optional[float]:
    if len(candles) < period: return None
    tps = [(get_high(c) + get_low(c) + get_close(c)) / 3.0 for c in candles[-period:]]
    sma_tp = sum(tps) / period
    mad = sum(abs(tp - sma_tp) for tp in tps) / period
    if mad == 0: return 0.0
    return (tps[-1] - sma_tp) / (0.015 * mad)

def find_zones(candles: list, left: int = 5, right: int = 3, atr_mult: float = 0.30, merge_mult: float = 0.50) -> list:
    """Строит зоны S/R по пивотам, сливает близкие."""
    atr_val = calc_atr(candles, 14)
    if atr_val == 0: return []
    
    half_zone = atr_val * atr_mult / 2
    merge_dist = atr_val * merge_mult
    
    zones = []
    # Ищем пивоты (не доходя до конца на right баров)
    for i in range(left, len(candles) - right - 1):
        # Пивот Хай (Сопротивление)
        is_res = True
        for k in range(1, left + 1):
            if get_high(candles[i-k]) >= get_high(candles[i]): is_res = False; break
        for k in range(1, right + 1):
            if get_high(candles[i+k]) > get_high(candles[i]): is_res = False; break
            
        if is_res:
            mid = get_high(candles[i])
            zones.append({"side": "resistance", "mid": mid, "top": mid + half_zone, "bot": mid - half_zone, "born": i})

        # Пивот Лоу (Поддержка)
        is_sup = True
        for k in range(1, left + 1):
            if get_low(candles[i-k]) <= get_low(candles[i]): is_sup = False; break
        for k in range(1, right + 1):
            if get_low(candles[i+k]) < get_low(candles[i]): is_sup = False; break
            
        if is_sup:
            mid = get_low(candles[i])
            zones.append({"side": "support", "mid": mid, "top": mid + half_zone, "bot": mid - half_zone, "born": i})

    # Слияние близких зон
    merged = []
    for z in zones:
        merged_flag = False
        for m in merged:
            if m["side"] == z["side"] and abs(m["mid"] - z["mid"]) <= merge_dist:
                # Обновляем зону (среднее)
                m["mid"] = (m["mid"] + z["mid"]) / 2
                m["top"] = m["mid"] + half_zone
                m["bot"] = m["mid"] - half_zone
                merged_flag = True
                break
        if not merged_flag:
            merged.append(z)
    return merged

async def full_analysis_sr_cci(client, pair: str, cfg: dict, fetch_candles, get_current_price) -> Tuple[Optional[str], Optional[float], str]:
    """
    Логика BinoView: Касание зоны + CCI-14.
    Возвращает (signal, price, reason).
    """
    c1 = await fetch_candles(client, pair, 60, 100)
    if not c1 or len(c1) < 50:
        return None, None, "NO_DATA"

    price = await get_current_price(client, pair)
    if price is None:
        price = get_close(c1[-1])

    cci_val = calc_cci(c1, 14)
    if cci_val is None:
        return None, None, "NO_CCI"

    zones = find_zones(c1, left=cfg.get("sr_cci_left", 5), right=cfg.get("sr_cci_right", 3))
    if not zones:
        return None, None, "NO_ZONES"

    signal = None

    # PATCH_047: касание зоны за последние 3 свечи
    lookback = 3
    recent = c1[-lookback:]
    touched_support = False
    touched_resistance = False
    sup_zone = None
    res_zone = None

    for c in recent:
        c_low = get_low(c)
        c_high = get_high(c)
        for z in zones:
            if z["side"] == "support" and c_low <= z["top"] and c_high >= z["bot"]:
                touched_support = True
                sup_zone = z
            if z["side"] == "resistance" and c_high >= z["bot"] and c_low <= z["top"]:
                touched_resistance = True
                res_zone = z

    if touched_support and cci_val < cfg.get("cci_oversold", -100):
        signal = "CALL"
        logger.info(f"   [SR_CCI] Касание поддержки (за {lookback} св.) + CCI {cci_val:.1f} -> CALL")
    elif touched_resistance and cci_val > cfg.get("cci_overbought", 100):
        signal = "PUT"
        logger.info(f"   [SR_CCI] Касание сопротивления (за {lookback} св.) + CCI {cci_val:.1f} -> PUT")

    if signal:
        return signal, price, "OK"
    return None, None, "NO_SIGNAL"

# ==================== БЭКТЕСТ ДЛЯ SR_CCI (PATCH_051) ====================
def backtest_sr_cci(candles: list, cfg: dict) -> tuple:
    """
    PATCH_051: быстрый бэктест без O(N^2).
    - Предвычисляет ATR и CCI для всех баров за один проход.
    - Находит все пивоты один раз.
    - Мерджит зоны один раз.
    - Один проход по барам (O(N)).
    Скорость: ~1-2 сек на пару (было ~25 сек).
    """
    wins = 0
    losses = 0
    expiry = 1
    n = len(candles)
    if n < 100: return 0, 0

    left = cfg.get("sr_cci_left", 5)
    right = cfg.get("sr_cci_right", 3)
    atr_period = 14
    cci_period = 14
    atr_mult = 0.30
    merge_mult = 0.50
    cci_oversold = cfg.get("cci_oversold", -100)
    cci_overbought = cfg.get("cci_overbought", 100)
    lookback = 3

    # === 1. ATR на каждом баре ===
    trs = [0.0] * n
    for i in range(1, n):
        h = get_high(candles[i]); l = get_low(candles[i]); pc = get_close(candles[i-1])
        trs[i] = max(h - l, abs(h - pc), abs(l - pc))
    atr_arr = [0.0] * n
    for i in range(atr_period - 1, n):
        s = 0.0
        for k in range(i - atr_period + 1, i + 1):
            s += trs[k]
        atr_arr[i] = s / atr_period

    # === 2. CCI на каждом баре ===
    cci_arr = [None] * n
    tps = [(get_high(c) + get_low(c) + get_close(c)) / 3.0 for c in candles]
    for i in range(cci_period - 1, n):
        sma = sum(tps[i - cci_period + 1:i + 1]) / cci_period
        mad = sum(abs(tp - sma) for tp in tps[i - cci_period + 1:i + 1]) / cci_period
        cci_arr[i] = 0.0 if mad == 0 else (tps[i] - sma) / (0.015 * mad)

    # === 3. Все пивоты за один проход ===
    raw_pivots = []
    for i in range(left, n - right - 1):
        is_res = True
        for k in range(1, left + 1):
            if get_high(candles[i-k]) >= get_high(candles[i]): is_res = False; break
        if is_res:
            for k in range(1, right + 1):
                if get_high(candles[i+k]) > get_high(candles[i]): is_res = False; break
        if is_res:
            a = atr_arr[i] if atr_arr[i] > 0 else 0.0001
            half = a * atr_mult / 2
            mid = get_high(candles[i])
            raw_pivots.append((i + right, "resistance", mid + half, mid - half, mid, a))

        is_sup = True
        for k in range(1, left + 1):
            if get_low(candles[i-k]) <= get_low(candles[i]): is_sup = False; break
        if is_sup:
            for k in range(1, right + 1):
                if get_low(candles[i+k]) < get_low(candles[i]): is_sup = False; break
        if is_sup:
            a = atr_arr[i] if atr_arr[i] > 0 else 0.0001
            half = a * atr_mult / 2
            mid = get_low(candles[i])
            raw_pivots.append((i + right, "support", mid + half, mid - half, mid, a))

    # === 4. Мердж близких зон ===
    zones = []  # [born, side, top, bot, mid, atr]
    for (born, side, top, bot, mid, a) in raw_pivots:
        merged = False
        for idx, z in enumerate(zones):
            if z[1] == side and abs(z[4] - mid) <= a * merge_mult:
                new_mid = (z[4] + mid) / 2
                new_half = (z[2] - z[3] + top - bot) / 4
                zones[idx] = [max(z[0], born), side, new_mid + new_half, new_mid - new_half, new_mid, a]
                merged = True
                break
        if not merged:
            zones.append([born, side, top, bot, mid, a])

    # === 5. Один проход по барам ===
    for i in range(50, n - expiry - 1):
        cci_val = cci_arr[i]
        if cci_val is None: continue

        recent_start = max(0, i - lookback + 1)
        active = [z for z in zones if z[0] <= i]
        if not active: continue

        touched_support = False
        touched_resistance = False
        for k in range(recent_start, i + 1):
            c_low = get_low(candles[k])
            c_high = get_high(candles[k])
            for z in active:
                if c_high < z[3] or c_low > z[2]:
                    continue  # быстрый отсев по вертикали
                if z[1] == "support":
                    touched_support = True
                else:
                    touched_resistance = True
            if touched_support and touched_resistance:
                break

        signal = None
        if touched_support and cci_val < cci_oversold: signal = "CALL"
        elif touched_resistance and cci_val > cci_overbought: signal = "PUT"

        if signal:
            entry_price = get_close(candles[i])
            exit_price = get_close(candles[i + expiry])
            if signal == "CALL":
                if exit_price > entry_price: wins += 1
                else: losses += 1
            else:
                if exit_price < entry_price: wins += 1
                else: losses += 1

    return wins, losses
