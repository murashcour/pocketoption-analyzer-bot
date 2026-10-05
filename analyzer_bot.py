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
    "check_interval_sec": 15,
    "max_checks": 4,
    "base_percent": 1.0,
    "min_balance_for_percent": 100,
    "fixed_steps": [1.0, 2.0, 4.0, 8.0],
    "payout_min": 85,
    "payout_max": 92,
    "payout_recheck_sec": 1800,
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
    "skip_before_change_minus": 1,
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
    if bull == total or bear == total:
        logger.info(f"   [1м] Перегрев {bull}/{total}")
    else:
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
async def full_analysis(client, pair: str) -> Optional[str]:
    """Мульти-ТФ анализ: 1м + 3м + 10м + S/R + ATR."""
    c1 = await fetch_candles(client, pair, 60, 100)
    c3 = await fetch_candles(client, pair, 180, 100)
    c10 = await fetch_candles(client, pair, 600, 50)

    if not c1 or len(c1) < 50:
        logger.info(f"   [{pair}] Мало данных 1м")
        return None

    sig_1m = analyze_1m(c1)
    if sig_1m is None:
        return None

    price = get_close(c1[-1])

    # Волатильность
    ok_vol, msg_vol = check_volatility(c1, price)
    logger.info(f"   [Волатильность] {msg_vol}")
    if not ok_vol:
        return None

    # S/R
    support, resistance = find_support_resistance(c1)
    ok_sr, msg_sr = check_sr_proximity(price, support, resistance, sig_1m)
    logger.info(f"   [S/R] {msg_sr}")
    if not ok_sr:
        logger.info(f"   [{pair}] S/R блокирует сделку")
        return None

    # 3м
    if c3 and len(c3) >= 30:
        sig_3m = analyze_3m(c3)
        if sig_3m is None:
            if CFG["tf_3m_neutral_blocks"]:
                logger.info(f"   [3м] нейтрально — блокирую")
                return None
            logger.info(f"   [3м] нейтрально — пропускаю")
        elif sig_3m != sig_1m:
            logger.info(f"   [3м] {sig_3m} — конфликт с 1м ({sig_1m})")
            return None
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
            return None
    else:
        logger.info(f"   [{pair}] 10м мало данных")

    logger.info(f"   🎯 СИГНАЛ: {sig_1m} (1м + 3м + 10м + S/R + ATR OK)")
    return sig_1m


# ==================== PAYOUT ====================
# ==================== PAYOUT ====================
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
async def run_martingale_series(client, pair: str, signal: str, stopper: StopChecker) -> bool:
    """Серия с удвоением. Возвращает True (плюс) / False (минус)."""
    try:
        B_start = float(await client.balance())
    except Exception as e:
        logger.error(f"Не удалось получить баланс: {e}")
        return False

    steps = get_martingale_steps(B_start)
    direction_str = "ВВЕРХ ⬆️ (CALL)" if signal == "CALL" else "ВНИЗ ⬇️ (PUT)"

    logger.info(f"\n🎬 СЕРИЯ {direction_str} | Баланс до = ${B_start:.2f}")
    logger.info(f"   Ступени: {steps}")

    open_deals = []

    # СТУПЕНЬ 1
    current_price = await get_current_price(client, pair)
    if current_price is None:
        logger.error("❌ Не удалось получить цену")
        return False

    bet = steps[0]
    try:
        if signal == "CALL":
            trade_id, _ = await client.buy(pair, bet, CFG["expiration"])
        else:
            trade_id, _ = await client.sell(pair, bet, CFG["expiration"])
    except Exception as e:
        logger.error(f"❌ Ошибка открытия ${bet}: {e}")
        return False

    open_deals.append({
        "id": trade_id,
        "entry": current_price,
        "amount": bet,
        "open_time": time.time(),
    })
    logger.info(f"📈 [1/4] Открыл ${bet:.2f} {direction_str} @ {current_price}")

    # ПРОВЕРКИ
    for check_num in range(1, CFG["max_checks"] + 1):
        if stopper.requested():
            logger.warning("⏹ Остановка во время серии")
            break

        if len(open_deals) >= 4:
            logger.info(f"✅ Все 4 ступени открыты")
            break

        last_deal = open_deals[-1]
        elapsed = time.time() - last_deal["open_time"]
        if elapsed >= CFG["expiration"]:
            logger.info(f"⏰ Последняя сделка закрылась ({elapsed:.0f}с)")
            break

        wait_sec = min(CFG["check_interval_sec"], CFG["expiration"] - elapsed + 1)
        if wait_sec > 0:
            await asyncio.sleep(wait_sec)

        if stopper.requested():
            break

        current_price = await get_current_price(client, pair)
        if current_price is None:
            logger.warning(f"⚠️ Проверка {check_num}: цена не получена")
            continue

        last_deal = open_deals[-1]
        last_entry = last_deal["entry"]

        if signal == "CALL":
            last_in_profit = current_price > last_entry
        else:
            last_in_profit = current_price < last_entry

        status = "+" if last_in_profit else "-"
        logger.info(
            f"   Проверка {check_num}/{CFG['max_checks']} | Цена {current_price} | "
            f"последняя ${last_deal['amount']:.2f}:{status}"
        )

        if last_in_profit:
            logger.info(f"⏸ Последняя в плюсе — ждём")
            continue

        i = len(open_deals)
        bet = steps[i]

        try:
            if signal == "CALL":
                trade_id, _ = await client.buy(pair, bet, CFG["expiration"])
            else:
                trade_id, _ = await client.sell(pair, bet, CFG["expiration"])
        except Exception as e:
            logger.error(f"❌ Ошибка открытия ${bet}: {e}")
            break

        open_deals.append({
            "id": trade_id,
            "entry": current_price,
            "amount": bet,
            "open_time": time.time(),
        })
        logger.info(
            f"📈 [{i+1}/4] Открыл ${bet:.2f} {direction_str} @ {current_price}"
        )

    # ЖДЁМ ЗАКРЫТИЯ
    if open_deals:
        last_open_time = open_deals[-1]["open_time"]
        remaining = max(0, CFG["expiration"] - (time.time() - last_open_time)) + 5
        logger.info(f"⏳ Ждём закрытия {len(open_deals)} сделок (~{remaining:.0f} сек)...")
        await stopper.sleep(remaining)

    try:
        B1 = float(await client.balance())
    except Exception as e:
        logger.error(f"Не удалось получить баланс: {e}")
        return False

    delta = B1 - B_start
    logger.info(f"🏁 СЕРИЯ закрыта: ${B_start:.2f} → ${B1:.2f} (Δ {delta:+.2f})")

    if B1 > B_start:
        logger.info(f"✅ СЕРИЯ ПЛЮС (Δ {delta:+.2f})")
        return True
    else:
        logger.info(f"❌ СЕРИЯ МИНУС (Δ {delta:+.2f})")
        return False


# ==================== СОСТОЯНИЕ ====================
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
async def load_currency_pairs(client) -> List[str]:
    """Загружает OTC-валютные пары с payout в диапазоне."""
    try:
        assets = await client.active_assets()
    except Exception as e:
        logger.error(f"❌ Ошибка active_assets: {e}")
        return []

    candidates = []
    for a in assets:
        if not isinstance(a, dict):
            continue
        sym = a.get("symbol") or ""
        atype = (a.get("asset_type") or "").lower()
        if not (a.get("is_otc") and a.get("is_active", True)):
            continue
        if atype != "currency":
            continue
        if not sym.endswith("_otc"):
            continue
        candidates.append(sym)

    logger.info(f"📋 Всего OTC-валют: {len(candidates)}")
    logger.info(f"🔎 Фильтр payout [{CFG['payout_min']}, {CFG['payout_max']}]%...")

    pairs = []
    for i, sym in enumerate(candidates, 1):
        pay = await check_payout(client, sym)
        if pay is None:
            continue
        if pay < CFG["payout_min"] or pay > CFG["payout_max"]:
            continue
        pairs.append(sym)
        if i % 10 == 0:
            logger.info(f"   ...проверено {i}/{len(candidates)}")

    logger.info(f"📋 Прошли фильтр: {len(pairs)} пар")
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

    async def run(self):
        async with PocketOptionAsync(ssid=self.ssid) as client:
            logger.info("✅ Подключение установлено")
            try:
                balance = float(await client.balance())
                logger.info(f"💰 Баланс: ${balance:.2f}")
            except Exception as e:
                logger.error(f"Ошибка баланса: {e}")
                return

            pairs = await load_currency_pairs(client)
            if not pairs:
                logger.error(f"❌ Нет пар с payout [{CFG['payout_min']}, {CFG['payout_max']}]%")
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
                try:
                    if self.stopper.requested():
                        break

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
                        if live_payout < CFG["payout_min"] or live_payout > CFG["payout_max"]:
                            logger.warning(
                                f"⚠️ [{pair}] Payout {live_payout:.1f}% вне "
                                f"[{CFG['payout_min']}, {CFG['payout_max']}]%"
                            )
                            self.state.change_pair("payout вне диапазона")
                            continue
                        self.state.current_payout = live_payout
                        logger.info(f"💹 [{pair}] Payout {live_payout:.1f}% — OK")

                    # Анализ
                    signal = await full_analysis(client, pair)
                    if signal is None:
                        if self.state.on_skip() == "CHANGE_PAIR":
                            continue
                        await self.stopper.sleep(20)
                        continue

                    self.state.skip_streak = 0
                    is_win = await run_martingale_series(
                        client, pair, signal, self.stopper
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

                    await self.stopper.sleep(5)

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logger.error(f"❌ Ошибка в цикле: {e}")
                    logger.info("🔄 Переподключение через 30 сек...")
                    await self.stopper.sleep(30)
                    try:
                        _ = await client.balance()
                        logger.info("✅ Соединение живо")
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
MENU_FIELDS = [
    ("expiration", "Экспирация (сек)"),
    ("check_interval_sec", "Интервал проверок (сек)"),
    ("max_checks", "Макс. проверок ступеней"),
    ("base_percent", "Базовый % от баланса"),
    ("min_balance_for_percent", "Порог баланса для %"),
    ("payout_min", "Мин. payout (%)"),
    ("payout_max", "Макс. payout (%)"),
    ("payout_recheck_sec", "Перепроверка payout (сек)"),
    ("min_confirmations", "Мин. подтверждений"),
    ("rsi_overbought", "RSI перекуп"),
    ("rsi_oversold", "RSI перепрод"),
    ("rsi_bull_min", "RSI бычий порог"),
    ("rsi_bear_max", "RSI медвежий порог"),
    ("sr_lookback", "S/R lookback (свечей)"),
    ("sr_proximity_percent", "S/R близость (%)"),
    ("atr_period", "ATR период"),
    ("atr_min_percent", "ATR мин. (%)"),
    ("tf_3m_rsi_bull", "3м RSI бычий"),
    ("tf_3m_rsi_bear", "3м RSI медвежий"),
    ("tf_3m_neutral_blocks", "3м нейтральный блок"),
    ("tf_10m_overbought", "10м RSI перекуп"),
    ("tf_10m_oversold", "10м RSI перепрод"),
    ("skip_before_change_plus", "Пропусков после +"),
    ("skip_before_change_minus", "Пропусков после -"),
]


def show_settings_menu(cfg: dict):
    """Показывает текущие настройки."""
    print("\n" + "=" * 60)
    print("  ТЕКУЩИЕ НАСТРОЙКИ")
    print("=" * 60)
    for i, (key, desc) in enumerate(MENU_FIELDS, 1):
        val = cfg.get(key, "?")
        print(f"  [{i:2d}]  {key:28s} = {val}")
    print("=" * 60)
    print("  Номер     — изменить параметр")
    print("  Enter     — запустить торговлю")
    print("  r         — сбросить на дефолты")
    print("  q         — выход")
    print("=" * 60)


def change_parameter(cfg: dict, key: str, current_value):
    """Меняет один параметр."""
    print(f"\n  Текущее значение {key} = {current_value}")
    new_val_str = input(f"  Новое значение (Enter=отмена): ").strip()
    if not new_val_str:
        print("  Отменено")
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
            # Список (fixed_steps)
            parts = [x.strip() for x in new_val_str.split(",")]
            new_val = [float(x) for x in parts]
        else:
            new_val = new_val_str

        cfg[key] = new_val
        save_config(cfg)
        print(f"  ✅ {key} = {new_val}")
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
                key, _ = MENU_FIELDS[idx]
                if key in cfg:
                    change_parameter(cfg, key, cfg[key])
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
