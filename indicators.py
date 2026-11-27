"""indicators.py (PATCH_099): sma, ema, rsi, atr, cci, adx, calc_vwap, calc_squeeze."""
from typing import List, Optional
from candles import get_high, get_low, get_close


def sma(prices: List[float], period: int = 14) -> Optional[float]:
    """Simple Moving Average / Простое скользящее среднее."""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def ema(prices: List[float], period: int) -> Optional[float]:
    """Exponential Moving Average / Экспоненциальное скользящее среднее."""
    if len(prices) < period:
        return None
    mult = 2 / (period + 1)
    val = prices[0]
    for p in prices[1:]:
        val = (p - val) * mult + val
    return val


def rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """Relative Strength Index / Индекс относительной силы."""
    if len(prices) < period + 1:
        return None
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    if al == 0:
        return 100.0
    return 100 - (100 / (1 + ag / al))


def atr(candles: List, period: int = 14) -> Optional[float]:
    """Average True Range / Средний истинный диапазон."""
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        h = get_high(candles[i])
        l = get_low(candles[i])
        prev_close = get_close(candles[i - 1])
        tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        trs.append(tr)
    return sum(trs[-period:]) / period


def cci(candles: List, period: int = 20) -> Optional[float]:
    """Commodity Channel Index (PATCH_038)."""
    if len(candles) < period:
        return None
    tps = []
    for c in candles[-period:]:
        tps.append((get_high(c) + get_low(c) + get_close(c)) / 3.0)
    sma_tp = sum(tps) / period
    mad = sum(abs(tp - sma_tp) for tp in tps) / period
    if mad == 0:
        return 0.0
    return (tps[-1] - sma_tp) / (0.015 * mad)


def adx(candles: List, period: int = 14) -> Optional[float]:
    """ADX — сила тренда (0-100). MANUAL_V4."""
    if len(candles) < period * 2:
        return None
    trs, plus_dm, minus_dm = [], [], []
    for i in range(1, len(candles)):
        h = get_high(candles[i])
        l = get_low(candles[i])
        prev_h = get_high(candles[i - 1])
        prev_l = get_low(candles[i - 1])
        prev_c = get_close(candles[i - 1])
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
        up = h - prev_h
        down = prev_l - l
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)
    atr_val = sum(trs[-period:]) / period
    if atr_val == 0:
        return 0.0
    plus_di = sum(plus_dm[-period:]) / period / atr_val * 100
    minus_di = sum(minus_dm[-period:]) / period / atr_val * 100
    di_sum = plus_di + minus_di
    if di_sum == 0:
        return 0.0
    return abs(plus_di - minus_di) / di_sum * 100


def calc_vwap(candles: List) -> Optional[float]:
    """Дневной VWAP."""
    if not candles:
        return None
    total_pv = total_v = 0.0
    for c in candles:
        h, l, cl = get_high(c), get_low(c), get_close(c)
        try:
            v = float(c.get("volume", 0)) if isinstance(c, dict) else 0
        except Exception:
            v = 0
        if v <= 0: v = 1.0
        total_pv += ((h + l + cl) / 3.0) * v
        total_v += v
    return total_pv / total_v if total_v > 0 else None


def calc_squeeze(candles: List, period: int = 20, mult: float = 2.0) -> bool:
    """True, если BB внутри KC (сжатие)."""
    if len(candles) < period:
        return False
    closes = [get_close(c) for c in candles[-period:]]
    mid = sum(closes) / period
    std = (sum((x - mid) ** 2 for x in closes) / period) ** 0.5
    bb_upper, bb_lower = mid + mult * std, mid - mult * std
    trs = []
    for i in range(1, len(candles[-period:])):
        h = get_high(candles[-period:][i])
        l = get_low(candles[-period:][i])
        prev_c = get_close(candles[-period:][i - 1])
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    atr_val = sum(trs) / len(trs) if trs else 0
    kc_upper, kc_lower = mid + mult * atr_val, mid - mult * atr_val
    return (bb_upper < kc_upper) and (bb_lower > kc_lower)
