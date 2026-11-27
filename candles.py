"""candles.py (PATCH_099): работа со свечами (dict, tuple, object)."""


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
