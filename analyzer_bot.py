# -*- coding: utf-8 -*-
"""
PocketOption Analyzer Bot

Автоматический торговый бот для PocketOption (демо/реальный счёт).
Анализирует OTC-валютные пары и торгует по стратегии с мартингейлом.

Created with DeepSeek AI assistance (deepseek.com).

Логика:
- 1м: RSI + SMA14 + EMA20 + EMA50 + свечной паттерн
- 3м: RSI должен совпадать с 1м
- 10м: RSI не в крайних зонах
- Уровни S/R: блок близко к поддержке/сопротивлению
- Волатильность: ATR14 >= 0.1%
- Payout [85, 92]% с перепроверкой каждые 30 мин
- Серия: 4 ступени с удвоением (1%, 2%, 4%, 8%)
- Вход по цене закрытия текущей свечи
- Счётчик пропусков: +серия = 5, -серия = 1
"""

import asyncio
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
from typing import Optional, List, Tuple

from BinaryOptionsToolsV2 import PocketOptionAsync

# ==================== ПУТИ ====================
# ==================== PATHS ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
CONFIG_DEFAULT_FILE = os.path.join(BASE_DIR, "config.default.json")
LOG_FILE = os.path.join(BASE_DIR, "analyzer_bot.log")
STOP_FLAG = os.path.join(BASE_DIR, "stop.flag")
SSID_FILE = os.path.expanduser("~/.po_ssid")

# ==================== КОНФИГ ПО УМОЛЧАНИЮ ====================
# ==================== DEFAULT CONFIG ====================
DEFAULT_CONFIG = {
    "expiration": 60,
    "check_interval_sec": 30,
    "max_checks": 3,
    "base_percent": 1.0,
    "min_balance_for_percent": 100,
    "fixed_steps": [1.0, 2.0, 4.0, 8.0],
      # Payout (общие)
    "payout_min": 85,
    "payout_max": 92,
    # Payout OTC
    "payout_min_otc": 85,
    "payout_max_otc": 92,
    # Payout Real
    "payout_min_real": 75,
    "payout_max_real": 92,
    "payout_recheck_sec": 1800,
    # Real-пары
    "include_real": True,
    "real_asset_types": ["currency"],
    # Часовой пояс
    "timezone": "Europe/Moscow",
    "forex_trade_days": [0, 1, 2, 3, 4],
    "min_confirmations": 3,
    "rsi_overbought": 75,
    "rsi_oversold": 25,
    "rsi_bull_min": 53,
    "rsi_bear_max": 47,
    "sr_lookback": 50,
    "sr_proximity_percent": 0.1,
    "atr_period": 14,
    "atr_min_percent": 0.1,
    "tf_3m_rsi_bull": 55,
    "tf_3m_rsi_bear": 45,
    "tf_3m_neutral_blocks": True,
    "tf_10m_overbought": 75,
    "tf_10m_oversold": 25,
    "skip_before_change_plus": 5,
    "skip_before_change_minus": 3,
    # Просадка (drawdown)
    "max_drawdown_percent": 30,
    "drawdown_pause_sec": 1800,
    "drawdown_max_count": 2,
     # Новости
    "news_enabled": True,
    "news_importance_min": 2,
    "news_pre_pause_min": 10,
    "news_post_pause_min": 20,
    "news_currencies": ["USD", "EUR", "GBP", "JPY"],
    "news_refresh_hours": 4,
    "news_fallback_stop": True,
}

# ==================== ГЛОБАЛЬНЫЕ НАСТРОЙКИ ====================
# ==================== GLOBAL SETTINGS ====================
CFG = {}  # Заполняется в main() / Filled in main()

# ==================== ЛОГИРОВАНИЕ ====================
# ==================== LOGGING ====================
logger = logging.getLogger(__name__)


def setup_logging():
    """Настройка логирования в файл и консоль."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )


# ==================== КОНФИГ ФУНКЦИИ ====================
# ==================== CONFIG FUNCTIONS ====================
def load_config() -> dict:
    """Загружает config.json или создаёт из дефолта."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            # Дополняем отсутствующие ключи дефолтами
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
        except Exception as e:
            logger.error(f"Ошибка чтения config.json: {e}")
            logger.error(f"Error reading config.json: {e}")
            return dict(DEFAULT_CONFIG)
    else:
        # Создаём из дефолта
        cfg = dict(DEFAULT_CONFIG)
        save_config(cfg)
        logger.info(f"Создан новый config.json с дефолтными настройками")
        logger.info(f"Created new config.json with defaults")
        return cfg


def save_config(cfg: dict):
    """Сохраняет config.json."""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Ошибка сохранения config.json: {e}")
        logger.error(f"Error saving config.json: {e}")


def reset_config() -> dict:
    """Сбрасывает config.json на дефолт."""
    cfg = dict(DEFAULT_CONFIG)
    save_config(cfg)
    logger.info("Настройки сброшены на дефолтные")
    logger.info("Settings reset to defaults")
    return cfg


# ==================== ИНДИКАТОРЫ ====================
# ==================== INDICATORS ====================
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


# ==================== РАБОТА СО СВЕЧАМИ ====================
# ==================== CANDLES ====================
def candle_field(c, field: str):
    """Извлекает поле из свечи (dict, tuple, object)."""
    if isinstance(c, dict):
        return c[field]
    if hasattr(c, field):
        return getattr(c, field)
    if isinstance(c, tuple) and len(c) == 2 and isinstance(c[1], dict):
        return c[1][field]
    idx_map = {
        "timestamp": 0, "time": 0, "open": 1, "high": 2,
        "low": 3, "close": 4, "volume": 5
    }
    if isinstance(c, (tuple, list)) and field in idx_map:
        return c[idx_map[field]]
    raise ValueError(f"Не могу извлечь '{field}' из свечи: {c}")


def get_close(c): return candle_field(c, "close")
def get_open(c): return candle_field(c, "open")
def get_high(c): return candle_field(c, "high")
def get_low(c): return candle_field(c, "low")


def get_time(c):
    try:
        return candle_field(c, "time")
    except (KeyError, ValueError):
        return candle_field(c, "timestamp")


async def fetch_candles(client, asset: str, period: int, count: int) -> List:
    """Получить N свечей через get_candles."""
    try:
        result = await client.get_candles(asset, period, count)
        if isinstance(result, (list, tuple)) and len(result) > 0:
            return list(result)
    except Exception as e:
        logger.debug(f"get_candles({asset}, {period}): {e}")
    return []


async def get_current_price(client, pair: str) -> Optional[float]:
    """Цена закрытия текущей свечи через get_candles_live."""
    try:
        async for closed, forming in client.get_candles_live(pair, 60, 100):
            if isinstance(forming, dict) and "close" in forming:
                return float(forming["close"])
            break
    except Exception as e:
        logger.debug(f"get_candles_live ошибка: {e}")
    return None


# ==================== КОНЕЦ ЧАСТИ 1 ====================
# ==================== END OF PART 1 ====================
# ==================== АНАЛИЗ 1м ====================
# ==================== 1m ANALYSIS ====================
def analyze_1m(candles: List) -> Optional[str]:
    """Полный анализ 1-минутного ТФ. Возвращает CALL/PUT/None."""
    if len(candles) < 50:
        return None

    closes = [get_close(c) for c in candles]
    price = closes[-1]

    s14 = sma(closes, 14)
    e20 = ema(closes, 20)
    e50 = ema(closes, 50)
    r14 = rsi(closes, 14)

    if any(x is None for x in [s14, e20, e50, r14]):
        return None

    if r14 < CFG["rsi_oversold"] or r14 > CFG["rsi_overbought"]:
        return None
    if CFG["rsi_bear_max"] <= r14 <= CFG["rsi_bull_min"]:
        return None

    bull = bear = 0
    if r14 > CFG["rsi_bull_min"]:
        bull += 1
    elif r14 < CFG["rsi_bear_max"]:
        bear += 1

    for level in [e20, e50, s14]:
        if price > level:
            bull += 1
        else:
            bear += 1

    if e20 > e50:
        bull += 1
    else:
        bear += 1

    last = candles[-1]
    o = get_open(last); h = get_high(last); l = get_low(last); cl = get_close(last)
    body = abs(cl - o)
    upper = h - max(cl, o)
    lower = min(cl, o) - l
    if body > 0:
        if lower > body * 2 and upper < body * 0.5:
            bull += 1
        if upper > body * 2 and lower < body * 0.5:
            bear += 1

    total = bull + bear
    mc = CFG["min_confirmations"]

    if bull >= mc and bull > bear and bull < total:
        logger.info(f"   [1м] CALL | {bull}/{total}")
        return "CALL"
    if bear >= mc and bear > bull and bear < total:
        logger.info(f"   [1м] PUT | {bear}/{total}")
        return "PUT"
    # 5/5 — сильный сигнал, а не перегрев (для тестов)
    if bull == total and bull >= mc:
        logger.info(f"   [1м] CALL | {bull}/{total} (все!)")
        return "CALL"
    if bear == total and bear >= mc:
        logger.info(f"   [1м] PUT | {bear}/{total} (все!)")
        return "PUT"

    logger.info(f"   [1м] Нет ({bull}/{bear})")
    return None


# ==================== АНАЛИЗ 3м ====================
# ==================== 3m ANALYSIS ====================
def analyze_3m(candles: List) -> Optional[str]:
    """Направление на 3м ТФ: CALL/PUT/None (нейтрально)."""
    if len(candles) < 30:
        return None
    closes = [get_close(c) for c in candles]
    r14 = rsi(closes, 14)
    if r14 is None:
        return None
    if r14 > CFG["tf_3m_rsi_bull"]:
        return "CALL"
    if r14 < CFG["tf_3m_rsi_bear"]:
        return "PUT"
    return None


# ==================== ФИЛЬТР 10м ====================
# ==================== 10m FILTER ====================
def analyze_10m_filter(candles: List, tf_name: str) -> Tuple[bool, str]:
    """10м фильтр крайних зон RSI."""
    if len(candles) < 30:
        return True, f"{tf_name}: мало данных (пропуск)"
    closes = [get_close(c) for c in candles]
    r14 = rsi(closes, 14)
    if r14 is None:
        return True, f"{tf_name}: RSI не посчитан"
    if r14 > CFG["tf_10m_overbought"]:
        return False, f"{tf_name}: RSI={r14:.1f} перекуплен"
    if r14 < CFG["tf_10m_oversold"]:
        return False, f"{tf_name}: RSI={r14:.1f} перепродан"
    return True, f"{tf_name}: RSI={r14:.1f} OK"


# ==================== УРОВНИ S/R ====================
# ==================== S/R LEVELS ====================
def find_support_resistance(candles: List) -> Tuple[float, float]:
    """Находит уровни поддержки и сопротивления за N свечей."""
    lookback = CFG["sr_lookback"]
    if len(candles) < lookback:
        lookback = len(candles)
    recent = candles[-lookback:]
    lows = [get_low(c) for c in recent]
    highs = [get_high(c) for c in recent]
    return min(lows), max(highs)


def check_sr_proximity(price: float, support: float, resistance: float,
                       signal: str) -> Tuple[bool, str]:
    """Проверяет близость цены к уровням S/R."""
    if price <= 0:
        return True, "S/R: цена 0"
    threshold = price * CFG["sr_proximity_percent"] / 100

    if signal == "CALL":
        if abs(price - resistance) <= threshold:
            return False, f"Цена близко к сопротивлению {resistance:.5f}"
        if price > resistance:
            return False, f"Цена выше сопротивления {resistance:.5f}"
    else:  # PUT
        if abs(price - support) <= threshold:
            return False, f"Цена близко к поддержке {support:.5f}"
        if price < support:
            return False, f"Цена ниже поддержки {support:.5f}"

    return True, f"S/R OK (под {support:.5f}, сопр {resistance:.5f})"


# ==================== ВОЛАТИЛЬНОСТЬ ====================
# ==================== VOLATILITY ====================
def check_volatility(candles: List, price: float) -> Tuple[bool, str]:
    """ATR14 < 0.1% → флэт, пропуск."""
    atr_val = atr(candles, CFG["atr_period"])
    if atr_val is None:
        return True, "ATR: мало данных"
    if price <= 0:
        return True, "ATR: цена 0"
    atr_percent = atr_val / price * 100
    if atr_percent < CFG["atr_min_percent"]:
        return False, f"ATR={atr_percent:.3f}% < {CFG['atr_min_percent']}% (флэт)"
    return True, f"ATR={atr_percent:.3f}% OK"


# ==================== ПОЛНЫЙ АНАЛИЗ ====================
# ==================== FULL ANALYSIS ====================

async def full_analysis(client, pair: str):
    """Мульти-ТФ анализ: 1м + 3м + 10м + S/R + ATR. Возвращает (signal, price)."""
    # ===== БЫСТРАЯ ПРОВЕРКА: ТОЛЬКО 1м =====
    c1 = await fetch_candles(client, pair, 60, 100)
    if not c1 or len(c1) < 50:
        logger.info(f"   [{pair}] Мало данных 1м")
        return None, None

    sig_1m = analyze_1m(c1)
    if sig_1m is None:
        return None, None      # ← выходим БЕЗ загрузки 3м и 10м

    # ===== 1м ДАЛ СИГНАЛ — грузим 3м и 10м =====
    c3  = await fetch_candles(client, pair, 180, 100)
    c10 = await fetch_candles(client, pair, 600, 50)

    price = get_close(c1[-1])

    # Волатильность
    ok_vol, msg_vol = check_volatility(c1, price)
    logger.info(f"   [Волатильность] {msg_vol}")
    if not ok_vol:
        return None, None

    # S/R
    support, resistance = find_support_resistance(c1)
    ok_sr, msg_sr = check_sr_proximity(price, support, resistance, sig_1m)
    logger.info(f"   [S/R] {msg_sr}")
    if not ok_sr:
        logger.info(f"   [{pair}] S/R блокирует сделку")
        return None, None

    # 3м
    if c3 and len(c3) >= 30:
        sig_3m = analyze_3m(c3)
        if sig_3m is None:
            if CFG["tf_3m_neutral_blocks"]:
                logger.info(f"   [3м] нейтрально — блокирую")
                return None, None
            logger.info(f"   [3м] нейтрально — пропускаю")
        elif sig_3m != sig_1m:
            logger.info(f"   [3м] {sig_3m} — конфликт с 1м ({sig_1m})")
            return None, None
        else:
            logger.info(f"   [3м] {sig_3m} — совпадает с 1м ✓")
    else:
        logger.info(f"   [{pair}] 3м мало данных")

    # 10м
    if c10 and len(c10) >= 30:
        ok, msg = analyze_10m_filter(c10, "10м")
        logger.info(f"   [{msg}]")
        if not ok:
            logger.info(f"   [{pair}] 10м блокирует сделку")
            return None, None
    else:
        logger.info(f"   [{pair}] 10м мало данных")

    logger.info(f"   🎯 СИГНАЛ: {sig_1m} (1м + 3м + 10м + S/R + ATR OK) @ {price}")
    return sig_1m, price

# ==================== PAYOUT ====================
# ==================== PAYOUT ====================


def get_payout_range(pair_name: str) -> Tuple[float, float]:
    """
    Возвращает (min, max) payout для пары.
    OTC → payout_min_otc/max_otc, Real → payout_min_real/max_real.
    """
    if pair_name.endswith("_otc"):
        return (
            CFG.get("payout_min_otc", CFG["payout_min"]),
            CFG.get("payout_max_otc", CFG["payout_max"]),
        )
    return (
        CFG.get("payout_min_real", CFG["payout_min"]),
        CFG.get("payout_max_real", CFG["payout_max"]),
    )

def parse_payout(raw) -> Optional[float]:
    """Парсит payout из разных форматов."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        v = float(raw)
        if 0 < v <= 1:
            v *= 100
        return v
    if isinstance(raw, str):
        s = raw.strip().replace("%", "")
        try:
            v = float(s)
            if 0 < v <= 1:
                v *= 100
            return v
        except ValueError:
            return None
    if isinstance(raw, dict):
        for key in ("payout", "value", "percent"):
            if key in raw:
                return parse_payout(raw[key])
    return None


async def check_payout(client, asset: str) -> Optional[float]:
    try:
        raw = await client.payout(asset)
        return parse_payout(raw)
    except Exception:
        return None


# ==================== КОНЕЦ ЧАСТИ 2 ====================
# ==================== END OF PART 2 ====================
# ==================== РАСЧЁТ СТУПЕНЕЙ ====================
# ==================== MARTINGALE STEPS ====================
def get_martingale_steps(balance: float) -> List[float]:
    """Ступени мартингейла: при >= 100 → 1% и ×2, при < 100 → фикс."""
    if balance < CFG["min_balance_for_percent"]:
        return list(CFG["fixed_steps"])
    base = round(balance * CFG["base_percent"] / 100, 2)
    return [
        base,
        round(base * 2, 2),
        round(base * 4, 2),
        round(base * 8, 2),
    ]


# ==================== STOP CHECKER ====================
# ==================== STOP CHECKER ====================
class StopChecker:
    """Обработка Ctrl+C, SIGTERM и stop.flag."""
    def __init__(self):
        self._stop = False
        signal.signal(signal.SIGINT, self._handler)
        signal.signal(signal.SIGTERM, self._handler)

    def _handler(self, signum, frame):
        logger.warning(f"⏹ Получен сигнал {signum}")
        self._stop = True

    def requested(self) -> bool:
        if self._stop:
            return True
        if os.path.exists(STOP_FLAG):
            logger.warning(f"⏹ Найден файл stop.flag")
            return True
        return False

    async def sleep(self, seconds: float):
        for _ in range(int(seconds)):
            if self.requested():
                return
            await asyncio.sleep(1)

# ==================== СЕРИЯ С УДВОЕНИЕМ ====================
# ==================== MARTINGALE SERIES ====================

async def _wait_candle_start(stopper, max_sec: int = 8) -> bool:
    """
    Ждёт начала 1м свечи (когда прошло < max_sec секунд от HH:MM:00).
    Возвращает True, если удалось; False, если stopper.requested().
    """
    start_wait = time.time()
    while True:
        if stopper.requested():
            return False
        # Секунд от начала текущей минуты
        now = time.time()
        seconds_into = now % 60
        if seconds_into < max_sec:
            logger.info(f"   ⏱ Начало 1м свечи ({seconds_into:.1f} сек от 00) — OK")
            return True
        # Ждём до следующей секунды
        await asyncio.sleep(1)
        # Защита от бесконечного ожидания
        if time.time() - start_wait > 70:
            logger.warning(f"   ⚠️ Не дождались начала свечи за 70 сек — продолжаю")
            return True


async def _check_momentum(client, pair: str, signal: str, entry_price: float) -> bool:
    """
    Проверка momentum через текущую цену vs entry_price (быстро).
    Использует get_current_price (get_candles_live).

    Логика:
    - CALL: current_price > entry_price → OK
    - PUT:  current_price < entry_price → OK
    - Иначе — пропуск
    """
    if not CFG.get("momentum_enabled", True):
        logger.info(f"   ⏸ Momentum отключён в config")
        return True

    try:
        t0 = time.time()
        current_price = await get_current_price(client, pair)
        dt = time.time() - t0

        if current_price is None:
            logger.warning(f"   ⚠ Цена не получена за {dt:.2f} сек — пропуск momentum")
            return True   # не блокируем

        delta = current_price - entry_price

        logger.info(
            f"   [Momentum] entry={entry_price:.5f} → current={current_price:.5f} "
            f"(Δ={delta:+.5f}, за {dt:.2f} сек)"
        )

        if signal == "CALL":
            if delta <= 0:
                logger.info(f"   ⏸ Цена против CALL (Δ {delta:+.5f})")
                return False
        elif signal == "PUT":
            if delta >= 0:
                logger.info(f"   ⏸ Цена против PUT (Δ {delta:+.5f})")
                return False

        logger.info(f"   ✅ Momentum OK — можно открывать")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка momentum check: {e}")
        return True   # не блокируем при ошибке


async def _open_deal_raw(client, p: str, step_idx: int, sig: str, steps: list, stopper) -> Optional[dict]:
    """
    Открывает сделку СРАЗУ (без запроса цены перед открытием).
    Возвращает deal dict или None.
    """
    try:
        bet = steps[step_idx]
        t0 = time.time()
        if sig == "CALL":
            trade_id, _ = await client.buy(p, bet, CFG["expiration"])
        else:
            trade_id, _ = await client.sell(p, bet, CFG["expiration"])
        dt = time.time() - t0

        deal = {
            "id": trade_id,
            "pair": p,
            "entry": 0,
            "amount": bet,
            "signal": sig,
            "open_time": time.time(),
            "step": step_idx + 1,
        }
        dir_str = "ВВЕРХ ⬆️ (CALL)" if sig == "CALL" else "ВНИЗ ⬇️ (PUT)"
        logger.info(f"📈 [{step_idx+1}/3] Открыл ${bet:.2f} {dir_str} на {p} (за {dt:.2f} сек)")
        return deal
    except Exception as e:
        logger.error(f"❌ Ошибка открытия ${steps[step_idx]:.2f}: {e}")
        return None

async def _wait_close(deal: dict, stopper):
    """
    Ждёт закрытия сделки (expiration + 5 сек запас).
    """
    last_open_time = deal["open_time"]
    remaining = max(0, CFG["expiration"] - (time.time() - last_open_time)) + 5
    logger.info(f"⏳ Ждём закрытия сделки #{deal['step']} (~{remaining:.0f} сек)...")
    await stopper.sleep(remaining)

async def _check_first_30s(client, pair: str, signal: str, entry_price: float):
    """
    Проверка через 30 сек после открытия 1-й ступени.
    Возвращает:
      "STEP2_NOW" — момент минус → открываем 2-ю сразу
      "WAIT_CLOSE" — момент плюс → ждём закрытия 1-й
    """
    try:
        current_price = await get_current_price(client, pair)
        if current_price is None:
            logger.warning(f"   ⚠️ Цена не получена при T+30 — STEP2_NOW (безопасно)")
            return "STEP2_NOW"

        if signal == "CALL":
            in_profit = current_price > entry_price
        else:
            in_profit = current_price < entry_price

        status = "+" if in_profit else "-"
        logger.info(f"   Проверка T+30 | Цена {current_price:.5f} | 1-я: {status}")

        if in_profit:
            return "WAIT_CLOSE"
        else:
            return "STEP2_NOW"
    except Exception as e:
        logger.error(f"❌ Ошибка T+30 проверки: {e}")
        return "STEP2_NOW"   # при ошибке — открываем 2-ю (безопаснее)


async def _open_step_1(client, pair: str, signal: str, entry_price: float,
                        steps: list, stopper, state=None):
    """
    Полный вход 1-й ступени.
    Если momentum против — ИЩЕМ СНОВА (другая пара).
    Возвращает (deal, entry_price) или (None, None) при остановке.
    """
    pass_number = 0
    pairs_tried = 0
    max_pairs = len(state.pairs) if state else 20
    start_time = time.time()
    last_log_time = start_time

    while True:
        if stopper.requested():
            return None, None

        # Progress каждые 5 минут
        if time.time() - last_log_time >= 300:
            elapsed_min = (time.time() - start_time) / 60
            logger.info(
                f"   🔍 Ищу 1-ю: круг {pass_number+1}, "
                f"пар {pairs_tried}, время {elapsed_min:.0f} мин"
            )
            last_log_time = time.time()

        # 1. Ждать начало 1м свечи
        if not await _wait_candle_start(stopper, max_sec=CFG.get("candle_start_max_sec", 8)):
            return None, None

        # 2. Momentum check
        ok = await _check_momentum(client, pair, signal, entry_price)
        if not ok:
            logger.info(f"   ⏸ Momentum против {pair} — меняю пару")
            if state is not None:
                state.change_pair("1-я momentum против")
                pair = state.current_pair()
                pairs_tried += 1

                live_payout = await check_payout(client, pair)
                pmin, pmax = get_payout_range(pair)
                if live_payout is None or live_payout < pmin or live_payout > pmax:
                    await stopper.sleep(2)
                    if pairs_tried >= max_pairs:
                        pass_number += 1
                        await stopper.sleep(CFG.get("step3_pause_between_circles_sec", 30))
                        pairs_tried = 0
                    continue

                new_sig, new_entry = await full_analysis(client, pair)
                if new_sig is not None:
                    signal, entry_price = new_sig, new_entry
                    continue
            await stopper.sleep(2)

            if pairs_tried >= max_pairs:
                pass_number += 1
                await stopper.sleep(CFG.get("step3_pause_between_circles_sec", 30))
                pairs_tried = 0
            continue

        # 3. Открыть
        deal = await _open_deal_raw(client, pair, 0, signal, steps, stopper)
        if deal is None:
            logger.warning(f"   ⚠️ Ошибка открытия — повтор через 5 сек")
            await stopper.sleep(5)
            continue

        deal["entry"] = entry_price
        return deal, entry_price


async def _open_step_2(client, pair: str, signal: str, steps: list, stopper,
                        with_analysis: bool = False, state=None):
    """
    2-я ступень.
    with_analysis=False → СРАЗУ (без анализа).
    with_analysis=True  → С АНАЛИЗОМ + цикл до открытия.
    Возвращает deal или None.
    """
    if not with_analysis:
        # === Вариант A: СРАЗУ (без анализа, без цикла) ===
        logger.info(f"   📈 2-я ступень СРАЗУ (момент минус)")
        deal = await _open_deal_raw(client, pair, 1, signal, steps, stopper)
        return deal

    # === Вариант B: С АНАЛИЗОМ + цикл ===
    logger.info(f"   📈 2-я ступень с ПОЛНЫМ АНАЛИЗОМ")

    pass_number = 0
    pairs_tried = 0
    max_pairs = len(state.pairs) if state else 20
    start_time = time.time()
    last_log_time = start_time

    while True:
        if stopper.requested():
            return None

        # Progress каждые 5 минут
        if time.time() - last_log_time >= 300:
            elapsed_min = (time.time() - start_time) / 60
            logger.info(
                f"   🔍 Ищу 2-ю: круг {pass_number+1}, "
                f"пар {pairs_tried}, время {elapsed_min:.0f} мин"
            )
            last_log_time = time.time()

        # Анализ
        new_signal, new_entry = await full_analysis(client, pair)
        if new_signal is None:
            logger.info(f"   ⏸ 2-я (анализ): нет сигнала на {pair} — смена пары")
            if state is not None:
                state.change_pair("2-я нет сигнала")
                pair = state.current_pair()
                pairs_tried += 1
            await stopper.sleep(2)
            if pairs_tried >= max_pairs:
                pass_number += 1
                await stopper.sleep(CFG.get("step3_pause_between_circles_sec", 30))
                pairs_tried = 0
            continue

        logger.info(f"   ✅ 2-я (анализ): сигнал {new_signal} @ {new_entry}")

        # Ждать начало 1м свечи
        if not await _wait_candle_start(stopper, max_sec=CFG.get("candle_start_max_sec", 8)):
            return None

        # Momentum check
        ok = await _check_momentum(client, pair, new_signal, new_entry)
        if not ok:
            logger.info(f"   ⏸ 2-я (анализ): momentum против — меняю пару")
            if state is not None:
                state.change_pair("2-я momentum против")
                pair = state.current_pair()
                pairs_tried += 1
            await stopper.sleep(2)
            if pairs_tried >= max_pairs:
                pass_number += 1
                await stopper.sleep(CFG.get("step3_pause_between_circles_sec", 30))
                pairs_tried = 0
            continue

        # Открыть
        deal = await _open_deal_raw(client, pair, 1, new_signal, steps, stopper)
        if deal is None:
            logger.warning(f"   ⚠️ Ошибка открытия 2-й — повтор через 5 сек")
            await stopper.sleep(5)
            continue
        deal["entry"] = new_entry
        return deal


async def _open_step_3(client, pair: str, signal: str, entry_price: float,
                        steps: list, stopper, state=None):
    """
    3-я ступень (полный вход как 1-я).
    Если momentum против — ищем снова.
    Возвращает deal или None.
    """
    pass_number = 0
    pairs_tried = 0
    max_pairs = len(state.pairs) if state else 20
    start_time = time.time()
    last_log_time = start_time

    while True:
        if stopper.requested():
            return None

        # Progress каждые 5 минут
        if time.time() - last_log_time >= 300:
            elapsed_min = (time.time() - start_time) / 60
            logger.info(
                f"   🔍 Ищу 3-ю: круг {pass_number+1}, "
                f"пар {pairs_tried}, время {elapsed_min:.0f} мин"
            )
            last_log_time = time.time()

        # Ждать начало 1м свечи
        if not await _wait_candle_start(stopper, max_sec=CFG.get("candle_start_max_sec", 8)):
            return None

        # Momentum check
        ok = await _check_momentum(client, pair, signal, entry_price)
        if not ok:
            logger.info(f"   ⏸ 3-я: momentum против {pair} — меняю пару")
            if state is not None:
                state.change_pair("3-я momentum против")
                pair = state.current_pair()
                pairs_tried += 1

                # Payout
                live_payout = await check_payout(client, pair)
                pmin, pmax = get_payout_range(pair)
                if live_payout is None or live_payout < pmin or live_payout > pmax:
                    await stopper.sleep(2)
                    if pairs_tried >= max_pairs:
                        pass_number += 1
                        await stopper.sleep(CFG.get("step3_pause_between_circles_sec", 30))
                        pairs_tried = 0
                    continue

                # Новый анализ
                new_sig, new_entry = await full_analysis(client, pair)
                if new_sig is not None:
                    signal, entry_price = new_sig, new_entry
                    continue
            await stopper.sleep(2)

            if pairs_tried >= max_pairs:
                pass_number += 1
                await stopper.sleep(CFG.get("step3_pause_between_circles_sec", 30))
                pairs_tried = 0
            continue

        # Открыть $4
        deal = await _open_deal_raw(client, pair, 2, signal, steps, stopper)
        if deal is None:
            logger.warning(f"   ⚠️ Ошибка открытия 3-й — повтор через 5 сек")
            await stopper.sleep(5)
            continue
        deal["entry"] = entry_price
        return deal


async def run_martingale_series(client, pair: str, signal: str, stopper: StopChecker, state, entry_price: float = 0) -> bool:
    """
    Серия мартингейла (новая логика).

    Ступени:
    - 1-я: full_analysis + начало 1м + 3 сек + momentum
    - 2-я: A) СРАЗУ (момент минус T+30) / B) С АНАЛИЗОМ (реально минус T+60)
    - 3-я: независимая, как 1-я

    Возвращает True (серия плюс) / False (серия минус).
    """
    # ===== Инициализация =====
    try:
        B_start = float(await client.balance())
    except Exception as e:
        logger.error(f"Не удалось получить баланс: {e}")
        return False

    steps = get_martingale_steps(B_start)
    direction_str = "ВВЕРХ ⬆️ (CALL)" if signal == "CALL" else "ВНИЗ ⬇️ (PUT)"

    logger.info(f"\n🎬 СЕРИЯ {direction_str} на {pair} | Баланс до = ${B_start:.2f}")
    logger.info(f"   Ступени: {steps}")

    # ===== ШАГ 1: 1-я ступень (полный вход) =====
    deal_1, entry_1 = await _open_step_1(client, pair, signal, entry_price, steps, stopper, state=state)
    if deal_1 is None:
        logger.info(f"⏸ СЕРИЯ прервана: не удалось открыть 1-ю")
        return False

    # ===== ШАГ 2: T+30 проверка =====
    await stopper.sleep(CFG["check_interval_sec"])
    if stopper.requested():
        logger.warning("⏹ Остановка во время серии")
        return False

    action = await _check_first_30s(client, pair, signal, entry_1)

    deal_2 = None

    if action == "STEP2_NOW":
        # Момент минус → 2-я СРАЗУ (без анализа)
        logger.info(f"   → 2-я СРАЗУ (момент минус в T+30)")
        deal_2 = await _open_step_2(
            client, pair, signal, steps, stopper,
            with_analysis=False, state=state
        )
    else:  # WAIT_CLOSE
        # Момент плюс → ждём закрытия 1-й
        logger.info(f"   → 1-я в плюсе в моменте, ждём закрытия")
        await _wait_close(deal_1, stopper)

        try:
            B_after_1 = float(await client.balance())
        except Exception as e:
            logger.error(f"Не удалось получить баланс: {e}")
            return False

        delta_1 = B_after_1 - B_start
        logger.info(f"🏁 Итог 1-й: ${B_start:.2f} → ${B_after_1:.2f} (Δ {delta_1:+.2f})")

        if delta_1 > 0:
            logger.info(f"✅ СЕРИЯ ПЛЮС (Δ {delta_1:+.2f})")
            return True

        # Реально минус → 2-я С АНАЛИЗОМ (ФИКС #11)
        logger.info(f"   → 1-я закрылась в минус → 2-я С АНАЛИЗОМ")
        deal_2 = await _open_step_2(
            client, pair, signal, steps, stopper,
            with_analysis=True, state=state
        )

    if deal_2 is None:
        logger.info(f"❌ 2-я не открыта — серия закрыта")
        return False

    # ===== ШАГ 3: Ждём закрытия 2-й =====
    await _wait_close(deal_2, stopper)

    try:
        B_after_2 = float(await client.balance())
    except Exception as e:
        logger.error(f"Не удалось получить баланс: {e}")
        return False

    delta_2 = B_after_2 - B_start
    logger.info(f"🏁 Итог 1+2: ${B_start:.2f} → ${B_after_2:.2f} (Δ {delta_2:+.2f})")

    if delta_2 > 0:
        logger.info(f"✅ СЕРИЯ ПЛЮС (Δ {delta_2:+.2f})")
        return True

    # ===== ШАГ 4: 3-я ступень =====
    logger.info(f"❌ Итог 1+2 минус (Δ {delta_2:+.2f}) — ищу сигнал для 3-й")

    pair_3, signal_3, entry_3 = await _find_signal_for_step_3(client, stopper, state)
    if pair_3 is None:
        logger.warning("⏹ Не нашли сигнал для 3-й — серия закрыта")
        return False

    deal_3 = await _open_step_3(
        client, pair_3, signal_3, entry_3, steps, stopper, state=state
    )
    if deal_3 is None:
        logger.info(f"❌ 3-я не открыта — серия закрыта")
        return False

    # ===== ШАГ 5: Ждём закрытия 3-й =====
    await _wait_close(deal_3, stopper)

    try:
        B_final = float(await client.balance())
    except Exception as e:
        logger.error(f"Не удалось получить баланс: {e}")
        return False

    delta_final = B_final - B_start
    logger.info(f"🏁 СЕРИЯ закрыта: ${B_start:.2f} → ${B_final:.2f} (Δ {delta_final:+.2f})")

    if delta_final > 0:
        logger.info(f"✅ СЕРИЯ ПЛЮС (Δ {delta_final:+.2f})")
        return True
    else:
        logger.info(f"❌ СЕРИЯ МИНУС (Δ {delta_final:+.2f})")
        return False



#===================== СОСТОЯНИЕ ====================
# ==================== STATE ====================
class TraderState:
    """Состояние трейдера: пары, счётчики, лимиты."""

    def __init__(self, pairs: List[str]):
        self.pairs = pairs
        self.current_idx = 0
        self.skip_streak = 0
        self.current_payout: Optional[float] = None

        self.total_series = 0
        self.total_wins = 0
        self.total_losses = 0
        self.total_skips = 0
        self.total_pair_changes = 0

        self.last_series_won: Optional[bool] = None
        self.skip_limit: int = CFG["skip_before_change_minus"]

    def current_pair(self) -> str:
        return self.pairs[self.current_idx]

    def change_pair(self, reason: str):
        old = self.current_pair()
        self.current_idx = (self.current_idx + 1) % len(self.pairs)
        self.total_pair_changes += 1
        self.skip_streak = 0
        self.current_payout = None
        self.skip_limit = CFG["skip_before_change_minus"]
        logger.info(
            f"🔄 Смена пары ({reason}): {old} → {self.current_pair()} "
            f"| лимит пропусков: {self.skip_limit}"
        )

    def update_pairs(self, new_pairs: List[str]):
        if not new_pairs:
            logger.warning("⚠️ Новый список пар пустой — оставляю старый")
            return
        old_pair = self.current_pair() if self.pairs else None
        old_count = len(self.pairs)
        self.pairs = new_pairs
        if old_pair and old_pair in new_pairs:
            self.current_idx = new_pairs.index(old_pair)
            logger.info(f"📋 Список пар обновлён ({old_count} → {len(new_pairs)}), "
                        f"текущая {old_pair} сохранена")
        else:
            self.current_idx = 0
            self.current_payout = None
            logger.info(f"📋 Список пар обновлён ({old_count} → {len(new_pairs)}), "
                        f"переход на {self.current_pair()}")

    def on_win(self):
        self.skip_streak = 0
        self.total_wins += 1
        self.total_series += 1
        self.last_series_won = True
        self.skip_limit = CFG["skip_before_change_plus"]
        logger.info(f"✅ Плюс — лимит пропусков: {self.skip_limit}")

    def on_loss(self):
        self.skip_streak = 0
        self.total_losses += 1
        self.total_series += 1
        self.last_series_won = False
        self.skip_limit = CFG["skip_before_change_minus"]
        logger.info(f"❌ Минус — лимит пропусков: {self.skip_limit}")

    def on_skip(self) -> str:
        self.skip_streak += 1
        self.total_skips += 1
        if self.skip_streak >= self.skip_limit:
            self.change_pair(f"{self.skip_streak} пропусков (лимит {self.skip_limit})")
            return "CHANGE_PAIR"
        logger.info(f"⏸ Пропуск {self.skip_streak}/{self.skip_limit} на паре")
        return "CONTINUE"

    def summary(self) -> str:
        wr = (self.total_wins / self.total_series * 100) if self.total_series else 0.0
        return (
            f"📊 ИТОГИ:\n"
            f"   Серий: {self.total_series} (✅ {self.total_wins} / ❌ {self.total_losses})\n"
            f"   Winrate: {wr:.1f}%\n"
            f"   Пропусков: {self.total_skips}\n"
            f"   Смен пар: {self.total_pair_changes}"
        )


# ==================== ЗАГРУЗКА ПАР ====================
# ==================== LOAD PAIRS ====================

# ==================== ЧЁРНЫЙ СПИСОК ЭКЗОТИКИ ====================
# ==================== EXOTIC BLACKLIST ====================

EXOTIC_BLACKLIST = {
    "TNDUSD_otc", "USDBRL_otc", "USDARS_otc", "SYPUSD_otc",
    "USDCLP_otc", "USDINR_otc", "USDPKR_otc", "USDBDT_otc",
    "USDEGP_otc", "NGNUSD_otc", "UAHUSD_otc", "USDPHP_otc",
    "USDMYR_otc", "JODCNY_otc", "OMRCNY_otc", "SARCNY_otc",
    "AEDCNY_otc", "QARCNY_otc", "EURRUB_otc", "LBPUSD_otc",
    "ZARUSD_otc", "MADUSD_otc", "USDDZD_otc", "USDCOP_otc",
    # Пары с ATR=0 (мёртвые свечи на OTC)
    "USDCNH_otc", "EURTRY_otc", "USDIDR_otc", "BHDCNY_otc",
    "IRRUSD_otc", "USDTHB_otc", "YERUSD_otc", "USDMXN_otc",
}

# ==================== НОВОСТИ (TRADINGVIEW) ====================
# ==================== NEWS (TRADINGVIEW) ====================
NEWS_CACHE = []  # Кэш событий
NEWS_LAST_LOAD = 0


def fetch_news_calendar() -> list:
    """
    Загружает экономический календарь с TradingView.
    Возвращает список событий.
    """
    if not REQUESTS_AVAILABLE:
        logger.warning("⚠️ requests не установлен — новости недоступны")
        return []

    try:
        from datetime import timedelta
        now = datetime.utcnow()
        from_date = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        to_date = (now + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        url = "https://economic-calendar.tradingview.com/events"
        headers = {
            "Origin": "https://www.tradingview.com",
            "User-Agent": "Mozilla/5.0",
        }
        params = {
            "from": from_date,
            "to": to_date,
        }

        r = requests.get(url, headers=headers, params=params, timeout=15)
        if r.status_code != 200:
            logger.warning(f"⚠️ TradingView API: HTTP {r.status_code}")
            return []

        data = r.json()
        events = data.get("result", [])
        logger.info(f"📰 Загружено {len(events)} новостей с TradingView")
        return events
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки новостей: {e}")
        return []


def check_news_pause():
    """
    Проверяет, не идёт ли сейчас новость.
    Возвращает (пауза_нужна, секунд_ждать, событие).
    Или ("STOP", 0, None) если календарь не загружен и fallback_stop=True.
    """
    global NEWS_CACHE, NEWS_LAST_LOAD

    if not CFG.get("news_enabled", False):
        return False, 0, None

    refresh_sec = CFG.get("news_refresh_hours", 4) * 3600
    if time.time() - NEWS_LAST_LOAD > refresh_sec or not NEWS_CACHE:
        NEWS_CACHE = fetch_news_calendar()
        NEWS_LAST_LOAD = time.time()

        if not NEWS_CACHE and CFG.get("news_fallback_stop", True):
            logger.error("❌ Календарь новостей не загружен — СТОП")
            return "STOP", 0, None

    importance_min = CFG.get("news_importance_min", 2)
    pre_pause = CFG.get("news_pre_pause_min", 10) * 60
    post_pause = CFG.get("news_post_pause_min", 20) * 60
    allowed_currencies = CFG.get("news_currencies", ["USD", "EUR", "GBP", "JPY"])

    now = time.time()

    for event in NEWS_CACHE:
        importance = event.get("importance", 0)
        if importance < importance_min:
            continue

        currency = event.get("currency", "")
        if currency not in allowed_currencies:
            continue

        try:
            event_time_str = event.get("date", "")
            event_time = datetime.fromisoformat(
                event_time_str.replace("Z", "+00:00")
            ).timestamp()
        except Exception:
            continue

        if event_time - pre_pause <= now <= event_time + post_pause:
            wait_sec = int(event_time + post_pause - now)
            title = event.get("title", "?")
            logger.warning(f"📰 НОВОСТЬ: {title} ({currency}) — пауза {wait_sec} сек")
            return True, wait_sec, event

    return False, 0, None

async def load_currency_pairs(client) -> List[str]:
    """
    Загружает OTC + Real пары с разными payout-фильтрами.
    - OTC: payout 85-92%
    - Real: payout 75-92%, только Currency (forex), Пн-Пт
    """
    try:
        assets = await client.active_assets()
    except Exception as e:
        logger.error(f"❌ Ошибка active_assets: {e}")
        return []

    # Определяем текущий день недели (для Forex)
    try:
        import pytz
        tz = pytz.timezone(CFG.get("timezone", "Europe/Moscow"))
        now = datetime.now(tz)
        weekday = now.weekday()  # 0=Пн, 6=Вс
    except Exception:
        now = datetime.now()
        weekday = now.weekday()

    forex_open = weekday in CFG.get("forex_trade_days", [0, 1, 2, 3, 4])

    candidates_otc = []
    candidates_real = []

    for a in assets:
        if not isinstance(a, dict):
            continue
        sym = a.get("symbol") or ""
        atype = (a.get("asset_type") or "").lower()
        is_otc = a.get("is_otc", False)
        is_active = a.get("is_active", True)

        if not is_active:
            continue

        # === OTC ===
        if is_otc or sym.endswith("_otc"):
            if atype != "currency":
                continue
            if not sym.endswith("_otc"):
                continue
            if sym in EXOTIC_BLACKLIST:
                continue
            candidates_otc.append(("OTC", sym))
            continue

        # === REAL ===
        if not CFG.get("include_real", False):
            continue

        # Только разрешённые типы (currency)
        if atype not in CFG.get("real_asset_types", ["currency"]):
            continue

        # Forex — только Пн-Пт
        if atype == "currency" and not forex_open:
            logger.debug(f"⏸ [{sym}] Forex закрыт ({now.strftime('%A')}) — пропуск")
            continue

        if sym in EXOTIC_BLACKLIST:
            continue

        candidates_real.append(("REAL", sym))

    logger.info(f"📋 OTC-кандидатов: {len(candidates_otc)}")
    logger.info(f"📋 REAL-кандидатов: {len(candidates_real)}")
    if not forex_open:
        logger.info(f"   ⏸ Forex закрыт ({now.strftime('%A')}) — real не включаются")

    # === Фильтр payout ===
    logger.info(
        f"🔎 Фильтр payout: OTC [{CFG['payout_min_otc']}, {CFG['payout_max_otc']}]%, "
        f"REAL [{CFG['payout_min_real']}, {CFG['payout_max_real']}]%..."
    )

    pairs = []
    total = len(candidates_otc) + len(candidates_real)
    i = 0

    for kind, sym in candidates_otc + candidates_real:
        i += 1
        pay = await check_payout(client, sym)
        if pay is None:
            continue

        if kind == "OTC":
            if pay < CFG["payout_min_otc"] or pay > CFG["payout_max_otc"]:
                continue
        else:  # REAL
            if pay < CFG["payout_min_real"] or pay > CFG["payout_max_real"]:
                continue

        pairs.append(sym)
        if i % 10 == 0:
            logger.info(f"   ...проверено {i}/{total}")

    # Разделяем по типам (для лога)
    otc_in = [p for p in pairs if p.endswith("_otc")]
    real_in = [p for p in pairs if not p.endswith("_otc")]

    logger.info(f"📋 Прошли фильтр: {len(pairs)} пар")
    logger.info(f"   ├─ OTC: {len(otc_in)}")
    logger.info(f"   └─ REAL: {len(real_in)}")
    if pairs:
        logger.info(f"📋 {', '.join(pairs)}")

    return pairs
# ==================== ОСНОВНОЙ ЦИКЛ ====================
# ==================== MAIN LOOP ====================
class Trader:
    """Основной торговый цикл."""

    def __init__(self, ssid: str):
        self.ssid = ssid
        self.stopper = StopChecker()
        self.state: Optional[TraderState] = None
        self.empty_candles_count = 0
        self.initial_balance = 0.0
        self.reference_balance = 0.0
        self.drawdown_count = 0
        self.last_status_show = 0.0
        # === Автостоп + защита от ошибок ===
        self.start_time = time.time()
        self.max_runtime_sec = CFG.get("max_runtime_hours", 24) * 3600
        self.error_streak = 0
        self.max_error_streak = CFG.get("max_error_streak", 5)

    async def run(self):
        async with PocketOptionAsync(ssid=self.ssid) as client:
            logger.info("✅ Подключение установлено")
            try:
                balance = float(await client.balance())
                logger.info(f"💰 Баланс: ${balance:.2f}")
            except Exception as e:
                logger.error(f"Ошибка баланса: {e}")
                return

            # === ИНИЦИАЛИЗАЦИЯ ПРОСАДКИ ===
            self.initial_balance = balance
            self.reference_balance = balance
            self.drawdown_count = 0
            logger.info(
                f"🛡 Защита от просадки: {CFG['max_drawdown_percent']}%, "
                f"пауза {CFG['drawdown_pause_sec']//60} мин, "
                f"макс {CFG['drawdown_max_count']} просадок"
            )

            pairs = await load_currency_pairs(client)
            if not pairs:
                logger.error(
                    f"❌ Нет пар с payout: OTC [{CFG['payout_min_otc']}, {CFG['payout_max_otc']}]%, "
                    f"REAL [{CFG['payout_min_real']}, {CFG['payout_max_real']}]%"
                )
                return

            self.state = TraderState(pairs)
            logger.info(f"💡 Остановка: Ctrl+C или создай файл stop.flag")
            logger.info(
                f"📊 Настройки: EXPIRATION={CFG['expiration']}s, "
                f"MIN_CONF={CFG['min_confirmations']}, "
                f"RSI {CFG['rsi_bear_max']}/{CFG['rsi_bull_min']}, "
                f"S/R ±{CFG['sr_proximity_percent']}%, "
                f"ATR≥{CFG['atr_min_percent']}%, "
                f"пропусков: +серия→{CFG['skip_before_change_plus']}, "
                f"-серия→{CFG['skip_before_change_minus']}"
            )

            last_payout_check = time.time()

            while True:
                # === АВТОСТОП 24 ЧАСА ===
                if time.time() - self.start_time >= self.max_runtime_sec:
                    hours = self.max_runtime_sec / 3600
                    logger.warning(f"⏹ Автостоп: {hours:.0f} часов работы завершены")
                    if self.state:
                        logger.info(self.state.summary())
                    return

                try:
                    if self.stopper.requested():
                        break

                     # === ПРОВЕРКА ПРОСАДКИ ===
                    try:
                        current_balance = float(await client.balance())

                        # Санитарная проверка — защита от бага API
                        if current_balance < 0:
                            logger.warning(
                                f"⚠️ Баланс отрицательный (${current_balance:.2f}) — "
                                f"вероятно, баг API. Пропускаю проверку просадки."
                            )
                        elif current_balance > self.reference_balance * 3:
                            logger.warning(
                                f"⚠️ Баланс подозрительно большой "
                                f"(${current_balance:.2f} при reference "
                                f"${self.reference_balance:.2f}) — пропускаю проверку."
                            )
                        else:
                            # === REFERENCE UPDATE (+10%) ===
                            if current_balance >= self.reference_balance * 1.10:
                                old_ref = self.reference_balance
                                self.reference_balance = current_balance
                                logger.info(
                                    f"📈 Reference обновлён: "
                                    f"${old_ref:.2f} → ${current_balance:.2f} (+10%)"
                                )

                            # === ПРОВЕРКА ПРОСАДКИ ===
                            threshold = self.reference_balance * (
                                1 - CFG["max_drawdown_percent"] / 100
                            )
                            if current_balance < threshold:
                                self.drawdown_count += 1
                                logger.warning(
                                    f"🛑 ПРОСАДКА #{self.drawdown_count} "
                                    f"({CFG['max_drawdown_percent']}%): "
                                    f"${self.reference_balance:.2f} → ${current_balance:.2f}"
                                )
                                if self.drawdown_count >= CFG["drawdown_max_count"]:
                                    logger.error(
                                        f"🛑 Достигнут лимит просадок "
                                        f"({CFG['drawdown_max_count']}) — СТОП"
                                    )
                                    return
                                pause_sec = CFG["drawdown_pause_sec"]
                                logger.info(f"⏸ Пауза {pause_sec//60} мин...")
                                await self.stopper.sleep(pause_sec)
                                self.reference_balance = current_balance
                                logger.info(
                                    f"✅ После паузы. Новый reference: "
                                    f"${self.reference_balance:.2f}"
                                )
                    except Exception as e:
                        logger.debug(f"Ошибка проверки просадки: {e}")

                    # === ПОКАЗ REF/BAL КАЖДЫЕ 5 МИН ===
                    if time.time() - self.last_status_show >= 300:
                        try:
                            _bal_now = float(await client.balance())
                            _threshold = self.reference_balance * (
                                1 - CFG["max_drawdown_percent"] / 100
                            )
                            _msg = (
                                f"💰 Reference: ${self.reference_balance:.2f} | "
                                f"Текущий: ${_bal_now:.2f} | "
                                f"Порог просадки: ${_threshold:.2f}"
                            )
                            logger.info(_msg)
                            # Синий цвет в консоль
                            print(f"\033[94m{_msg}\033[0m")
                        except Exception as e:
                            logger.debug(f"Ошибка показа REF/BAL: {e}")
                        self.last_status_show = time.time()

                    # === ПРОВЕРКА НОВОСТЕЙ ===
                    news_pause, news_wait, news_event = check_news_pause()
                    if news_pause == "STOP":
                        logger.error("🛑 Новости недоступны — СТОП")
                        return
                    if news_pause:
                        logger.info(f"⏸ Пауза до конца новости ({news_wait} сек)...")
                        await self.stopper.sleep(news_wait + 5)
                        continue

                    # Перепроверка payout
                    if time.time() - last_payout_check >= CFG["payout_recheck_sec"]:
                        logger.info(f"\n🔄 Перепроверка payout всех пар...")
                        new_pairs = await load_currency_pairs(client)
                        if new_pairs:
                            self.state.update_pairs(new_pairs)
                        last_payout_check = time.time()

                    pair = self.state.current_pair()
                    logger.info(f"\n🎯 Проверяю {pair}...")

                    # Payout кэш
                    if self.state.current_payout is None:
                        live_payout = await check_payout(client, pair)
                        if live_payout is None:
                            logger.warning(f"⚠️ [{pair}] Payout не получен")
                            self.state.change_pair("payout не получен")
                            continue
                        pmin, pmax = get_payout_range(pair)
                        if live_payout < pmin or live_payout > pmax:
                            logger.warning(
                                f"⚠️ [{pair}] Payout {live_payout:.1f}% вне "
                                f"[{pmin}, {pmax}]%"
                            )
                            self.state.change_pair("payout вне диапазона")
                            continue
                        self.state.current_payout = live_payout
                        logger.info(f"💹 [{pair}] Payout {live_payout:.1f}% — OK")

                                      # Анализ
                    signal, entry_price = await full_analysis(client, pair)
                    if signal is None:
                        # Счётчик "Мало данных"
                        self.empty_candles_count += 1
                        if self.empty_candles_count >= 5:
                            logger.warning("⚠️ 5 раз подряд 'Мало данных' — пауза 60 сек")
                            await self.stopper.sleep(60)
                            self.empty_candles_count = 0
                            continue

                        if self.state.on_skip() == "CHANGE_PAIR":
                            await self.stopper.sleep(2)   # ← sleep при CHANGE_PAIR
                            continue
                        await self.stopper.sleep(5)
                        continue
                    else:
                        self.empty_candles_count = 0   # ← СБРОС при успехе

                    self.state.skip_streak = 0
                    is_win = await run_martingale_series(
                        client, pair, signal, self.stopper, self.state, entry_price
                    )

                    if is_win:
                        self.state.on_win()
                        logger.info(f"✅ Серия плюс — остаёмся на {pair}")
                    else:
                        self.state.on_loss()
                        logger.info(f"❌ Серия минус — смена пары")
                        self.state.change_pair("серия минус")

                    try:
                        balance = float(await client.balance())
                        logger.info(f"💰 Баланс: ${balance:.2f}")
                    except Exception:
                        pass

                    self.error_streak = 0   # ← СБРОС при успешной итерации
                    await self.stopper.sleep(5)

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    self.error_streak += 1
                    logger.error(f"⚠️ Ошибка #{self.error_streak}/{self.max_error_streak}: {e}")

                    if self.error_streak >= self.max_error_streak:
                        logger.error(f"🛑 {self.max_error_streak} ошибок подряд — ПОЛНЫЙ СТОП")
                        return

                    logger.info("🔄 Переподключение через 30 сек...")
                    await self.stopper.sleep(30)
                    try:
                        _ = await client.balance()
                        logger.info("✅ Соединение живо")
                        self.error_streak = 0   # соединение восстановлено
                    except Exception as e2:
                        logger.error(f"❌ Соединение потеряно: {e2}")
                        logger.error("⏹ Требуется перезапуск")
                        return

            if self.state:
                print("\n" + "=" * 60)
                print(self.state.summary())
                print("=" * 60)
                logger.info(self.state.summary())


# ==================== ИНТЕРАКТИВНОЕ МЕНЮ ====================
# ==================== INTERACTIVE MENU ====================
# Поля, которые можно менять через меню

# Формат: (key, ru_description, en_description)
MENU_FIELDS = [
    # ==================== Основные ====================
    ("expiration",                "Экспирация сделки (сек)",              "Trade expiration (sec)"),
    ("check_interval_sec",        "Интервал проверки серии (сек)",        "Series check interval (sec)"),
    ("max_checks",                "Макс. проверок в серии",               "Max checks in series"),
    ("base_percent",              "Базовый % от баланса",                 "Base % of balance"),
    ("min_balance_for_percent",   "Мин. баланс для %-режима ($)",         "Min balance for % mode ($)"),

    # ==================== Payout OTC ====================
    ("payout_min_otc",            "Мин. payout OTC (%)",                  "Min OTC payout (%)"),
    ("payout_max_otc",            "Макс. payout OTC (%)",                 "Max OTC payout (%)"),

    # ==================== Payout Real ====================
    ("payout_min_real",           "Мин. payout Real (%)",                 "Min Real payout (%)"),
    ("payout_max_real",           "Макс. payout Real (%)",                "Max Real payout (%)"),

    # ==================== Общие payout ====================
    ("payout_recheck_sec",        "Перепроверка payout (сек)",            "Payout recheck (sec)"),

    # ==================== Real-пары ====================
    ("include_real",              "Включать Real-пары (True/False)",      "Include Real pairs (True/False)"),
    ("real_asset_types",          "Типы Real (currency)",                 "Real types (currency)"),
    ("timezone",                  "Часовой пояс (Europe/Moscow)",         "Timezone (Europe/Moscow)"),
    ("forex_trade_days",          "Дни Forex (0=Пн..4=Пт)",               "Forex days (0=Mon..4=Fri)"),

    # ==================== Анализ 1м ====================
    ("min_confirmations",         "Мин. подтверждений сигнала",           "Min signal confirmations"),
    ("rsi_overbought",            "RSI перекуп (>X — пропуск)",           "RSI overbought (>X — skip)"),
    ("rsi_oversold",              "RSI перепрод (<X — пропуск)",          "RSI oversold (<X — skip)"),
    ("rsi_bull_min",              "RSI бычий порог (>X — CALL)",          "RSI bullish min (>X — CALL)"),
    ("rsi_bear_max",              "RSI медвежий порог (<X — PUT)",        "RSI bearish max (<X — PUT)"),

    # ==================== S/R ====================
    ("sr_lookback",               "S/R lookback (свечей)",                "S/R lookback (candles)"),
    ("sr_proximity_percent",      "S/R близость к уровню (%)",            "S/R proximity to level (%)"),

    # ==================== Волатильность ====================
    ("atr_period",                "ATR период",                           "ATR period"),
    ("atr_min_percent",           "ATR мин. волатильность (%)",           "ATR min volatility (%)"),

    # ==================== Мульти-ТФ ====================
    ("tf_3m_rsi_bull",            "3м RSI бычий порог",                   "3m RSI bullish threshold"),
    ("tf_3m_rsi_bear",            "3м RSI медвежий порог",                "3m RSI bearish threshold"),
    ("tf_3m_neutral_blocks",      "3м нейтральный блокирует (True/False)", "3m neutral blocks (True/False)"),
    ("tf_10m_overbought",         "10м RSI перекуп",                      "10m RSI overbought"),
    ("tf_10m_oversold",           "10м RSI перепрод",                     "10m RSI oversold"),

    # ==================== Пропуски ====================
    ("skip_before_change_plus",   "Пропусков после +серии",               "Skips after winning series"),
    ("skip_before_change_minus",  "Пропусков после -серии",               "Skips after losing series"),

    # ==================== Просадка ====================
    ("max_drawdown_percent",      "Макс. просадка (%)",                   "Max drawdown (%)"),
    ("drawdown_pause_sec",        "Пауза при просадке (сек)",             "Drawdown pause (sec)"),
    ("drawdown_max_count",        "Макс. кол-во просадок",                "Max drawdown count"),

    # ==================== Новости ====================
    ("news_enabled",              "Пауза при новостях (True/False)",      "News pause enabled (True/False)"),
    ("news_importance_min",       "Мин. важность (2=Medium,3=High)",      "Min importance (2=Med, 3=High)"),
    ("news_pre_pause_min",        "Пауза ДО новости (мин)",               "Pre-news pause (min)"),
    ("news_post_pause_min",       "Пауза ПОСЛЕ новости (мин)",            "Post-news pause (min)"),
    ("news_currencies",           "Валюты новостей (USD,EUR..)",          "News currencies (USD,EUR..)"),
    ("news_refresh_hours",        "Обновление календаря (часы)",          "Calendar refresh (hours)"),
    ("news_fallback_stop",        "СТОП если календарь не загружен",      "STOP if calendar not loaded"),
]

def _format_value(val) -> str:
    """Форматирует значение для отображения."""
    if isinstance(val, bool):
        return "True" if val else "False"
    if isinstance(val, list):
        return "[" + ", ".join(str(x) for x in val) + "]"
    return str(val)


def show_settings_menu(cfg: dict):
    """Показывает текущие настройки (двуязычное меню)."""
    W = 100  # ширина разделителя
    print("\n" + "=" * W)
    print("  ТЕКУЩИЕ НАСТРОЙКИ / CURRENT SETTINGS")
    print("=" * W)
    print(f"  {'#':>3}  {'Параметр / Parameter':<28}  {'Значение':<14}  Описание / Description")
    print("-" * W)
    for i, (key, ru_desc, en_desc) in enumerate(MENU_FIELDS, 1):
        val = _format_value(cfg.get(key, "?"))
        # Строка вида:
        #  [ 1]  expiration                    = 60              Экспирация сделки (сек) / Trade expiration (sec)
        print(f"  [{i:2d}]  {key:<28}  = {val:<12}  {ru_desc} / {en_desc}")
    print("=" * W)
    print("  Номер / Number    — изменить параметр / change parameter")
    print("  Enter             — запустить торговлю / start trading")
    print("  r                 — сбросить на дефолты / reset to defaults")
    print("  q                 — выход / exit")
    print("=" * W)


def change_parameter(cfg: dict, key: str, current_value, ru_desc: str = "", en_desc: str = ""):
    """Меняет один параметр (двуязычный)."""
    print(f"\n  ┌─ {key}")
    if ru_desc:
        print(f"  │  RU: {ru_desc}")
    if en_desc:
        print(f"  │  EN: {en_desc}")
    print(f"  │  Текущее / Current: {_format_value(current_value)}")

    # Подсказка по типу
    if isinstance(current_value, bool):
        hint = "True/False (или y/n, да/нет)"
    elif isinstance(current_value, list):
        hint = "через запятую, напр.: 1, 2, 4, 8"
    elif isinstance(current_value, int):
        hint = "целое число"
    elif isinstance(current_value, float):
        hint = "число (можно с точкой)"
    else:
        hint = "строка"
    print(f"  │  Формат / Format: {hint}")
    print(f"  └─ Enter = отмена / cancel")

    new_val_str = input(f"  > ").strip()
    if not new_val_str:
        print("  Отменено / Cancelled")
        return current_value

    # Определяем тип по текущему значению
    try:
        if isinstance(current_value, bool):
            new_val = new_val_str.lower() in ("true", "1", "yes", "да", "y")
        elif isinstance(current_value, int):
            new_val = int(new_val_str)
        elif isinstance(current_value, float):
            new_val = float(new_val_str)
        elif isinstance(current_value, list):
            parts = [x.strip() for x in new_val_str.split(",")]
            if current_value and isinstance(current_value[0], (int, float)):
                new_val = [float(x) for x in parts]
            else:
                new_val = parts
        else:
            new_val = new_val_str

        cfg[key] = new_val
        save_config(cfg)
        print(f"  ✅ {key} = {_format_value(new_val)}")
        logger.info(f"Настройка изменена: {key} = {new_val}")
        return new_val
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")
        return current_value


def settings_menu(cfg: dict) -> dict:
    """Интерактивное меню настроек. Возвращает обновлённый cfg."""
    while True:
        show_settings_menu(cfg)
        choice = input("Выбор: ").strip().lower()

        if choice == "":
            return cfg
        if choice == "q":
            print("Выход.")
            sys.exit(0)
        if choice == "r":
            cfg = reset_config()
            print("✅ Настройки сброшены на дефолтные")
            continue

        # Пытаемся распознать номер
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(MENU_FIELDS):
                key, ru_desc, en_desc = MENU_FIELDS[idx]
                if key in cfg:
                    change_parameter(cfg, key, cfg[key], ru_desc, en_desc)
                else:
                    print(f"  ⚠️ Параметр {key} отсутствует в конфиге")
            else:
                print(f"  ⚠️ Неверный номер: {choice}")
        except ValueError:
            print(f"  ⚠️ Неверный ввод: {choice}")


# ==================== MAIN ====================
# ==================== MAIN ====================
def load_ssid() -> Optional[str]:
    """Загружает SSID из переменной или файла."""
    ssid = os.getenv("PO_SSID", "").strip()
    if ssid:
        return ssid
    if os.path.exists(SSID_FILE):
        try:
            with open(SSID_FILE, 'r', encoding='utf-8') as f:
                ssid = f.read().strip()
            if ssid:
                logger.info(f"✅ SSID загружен из {SSID_FILE}")
                return ssid
        except Exception as e:
            logger.error(f"Ошибка чтения SSID файла: {e}")
    return None


def validate_ssid(ssid: str) -> bool:
    """Проверяет валидность SSID."""
    if not ssid:
        return False
    try:
        i = ssid.find('{')
        j = ssid.rfind('}')
        if i == -1 or j == -1:
            return False
        obj = json.loads(ssid[i:j+1])
        return "uid" in obj and "isDemo" in obj
    except Exception:
        return False


async def main():
    global CFG

    setup_logging()

    print("\n" + "=" * 60)
    print("  PocketOption Analyzer Bot")
    print("  Created with DeepSeek AI assistance")
    print("=" * 60)

    # Загрузка SSID
    ssid = load_ssid()
    if not ssid:
        logger.error("❌ SSID не найден")
        print("\n⚠️ SSID не задан. Установи переменную PO_SSID")
        print("   или положи SSID в ~/.po_ssid")
        print("\nПодробнее: docs/SSID.md\n")
        return

    if not validate_ssid(ssid):
        logger.error("❌ SSID невалиден (проверь кавычки)")
        print("\n⚠️ SSID невалиден. Проверь строку в ~/.po_ssid")
        print("Подробнее: docs/SSID.md\n")
        return

    logger.info("✅ SSID валиден")

    # === ПРОВЕРКА SSID ЧЕРЕЗ API ===
    logger.info("🔎 Проверка подключения к PocketOption API...")
    ssid_ok = False
    try:
        async with PocketOptionAsync(ssid=ssid) as test_client:
            for attempt in range(3):
                try:
                    candles = await test_client.get_candles("EURUSD_otc", 60, 5)
                    if candles and len(candles) > 0:
                        ssid_ok = True
                        logger.info(f"✅ Свечи получены ({len(candles)} шт.)")
                        break
                except Exception as e:
                    logger.debug(f"Попытка {attempt+1}: {e}")
                await asyncio.sleep(2)
    except Exception as e:
        logger.error(f"❌ Ошибка подключения: {e}")

    if not ssid_ok:
        logger.error("❌ SSID не отдаёт свечи — возможно, инвалидирован")
        print("\n⚠️ SSID валиден по формату, но API не отвечает свечами.")
        print("   Обнови SSID через SSID-finder или заново залогинься.")
        print("   Подробнее: docs/SSID.md\n")
        return

    logger.info("✅ SSID работает")

    # Загрузка конфига
    CFG = load_config()

    # Интерактивное меню
    print("\n" + "=" * 60)
    print("  Интерактивное меню настроек")
    print("  Interactive settings menu")
    print("=" * 60)
    print("  Enter — торговать с текущими настройками")
    print("  Номер — изменить параметр")
    print("  r — сброс на дефолты")
    print("  q — выход")
    print("=" * 60)
    input("Нажми Enter чтобы открыть меню...")

    CFG = settings_menu(CFG)

    print("\n" + "=" * 60)
    print("  Запуск торговли...")
    print("  Starting trading...")
    print("=" * 60 + "\n")

    # Запуск
    trader = Trader(ssid)
    await trader.run()


# ==================== ТОЧКА ВХОДА ====================
# ==================== ENTRY POINT ====================
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹ Остановка по Ctrl+C.")
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
        sys.exit(1)
