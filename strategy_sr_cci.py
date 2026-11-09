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
    reason = "OK"
    
    # Проверяем последние 3 свечи на касание
    for z in zones:
        # Зона актуальна, если цена её ещё не пробила (BinoView keepUntilBreak)
        # Для простоты проверяем касание текущей цены
        if z["side"] == "support" and z["bot"] <= price <= z["top"]:
            if cci_val < cfg.get("cci_oversold", -100):
                signal = "CALL"
                logger.info(f"   [SR_CCI] Касание поддержки {z['bot']:.5f}-{z['top']:.5f} + CCI {cci_val:.1f} -> CALL")
                break
        elif z["side"] == "resistance" and z["bot"] <= price <= z["top"]:
            if cci_val > cfg.get("cci_overbought", 100):
                signal = "PUT"
                logger.info(f"   [SR_CCI] Касание сопротивления {z['bot']:.5f}-{z['top']:.5f} + CCI {cci_val:.1f} -> PUT")
                break

    if signal:
        return signal, price, "OK"
    return None, None, "NO_SIGNAL"
