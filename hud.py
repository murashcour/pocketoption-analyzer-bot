# -*- coding: utf-8 -*-
"""
HUD: красивая карточка в консоль (WR, серии, баланс, просадка).

PATCH_006: только визуализация. Не трогает логику торговли.
"""
from typing import Optional


# PATCH_007: ширина строки с учётом эмодзи
def _display_width(s: str) -> int:
    """Возвращает визуальную ширину строки (эмодзи = 2, обычные = 1)."""
    import unicodedata
    width = 0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ('W', 'F'):
            width += 2
        elif ord(ch) > 0x1F000:  # эмодзи
            width += 2
        else:
            width += 1
    return width


# ANSI-цвета (совместимы с COLORS_FINAL)
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[96m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
WHITE = "\033[97m"
GRAY = "\033[90m"


def _wr_color(wr: float) -> str:
    """Цвет для WR (зелёный > 55, жёлтый 45-55, красный < 45)."""
    if wr >= 55.0:
        return GREEN
    if wr >= 45.0:
        return YELLOW
    return RED


def _delta_color(delta: float) -> str:
    """Цвет для Δ (зелёный > 0, красный < 0)."""
    if delta > 0:
        return GREEN
    if delta < 0:
        return RED
    return GRAY


def render_hud(
    state,
    balance: float,
    ref_balance: float,
    drawdown_threshold: float,
    next_ref: float,
    double_mode: bool = False,
) -> str:
    """
    PATCH_006: рендер HUD-карточки в консоль.

    Параметры:
      state — TraderState (total_series, total_wins, total_losses,
              total_trades, win_trades, loss_trades,
              total_skips, total_pair_changes)
      balance — текущий баланс
      ref_balance — reference (для просадки)
      drawdown_threshold — порог просадки (ref * (1 - max_dd/100))
      next_ref — следующая полка reference
      double_mode — режим удвоения (True/False)

    Возвращает: строку (для print).
    """
    # === WR по сериям ===
    series_wr = 0.0
    if state.total_series > 0:
        series_wr = (state.total_wins / state.total_series) * 100

    # === PATCH_016: WR по сделкам (без ничьих) ===
    _denom = state.win_trades + state.loss_trades
    trade_wr = (state.win_trades / _denom * 100) if _denom > 0 else 0.0

    # === PnL (от старта) ===
    start_bal = getattr(state, "start_balance", 0.0)
    pnl = balance - start_bal if start_bal > 0 else 0.0
    
    # Цвет для PnL (плюс - синий, минус - красный)
    if pnl > 0:
        pnl_color = "\033[94m"  # Синий (как просил)
    elif pnl < 0:
        pnl_color = "\033[91m"  # Красный
    else:
        pnl_color = GRAY

    # === Просадка ===
    dd_pct = 0.0
    if ref_balance > 0:
        dd_pct = ((ref_balance - balance) / ref_balance) * 100

    # === Цвета ===
    wr_series_color = _wr_color(series_wr)
    wr_trade_color = _wr_color(trade_wr)
    dd_color = _delta_color(-dd_pct) if dd_pct > 0 else GRAY

    # === Режим удвоения ===
    double_str = ""
    if double_mode:
        double_str = f" {MAGENTA}[УДВОЕНИЕ]{RESET}"

    # === Формируем карточку ===
    W = 46  # ширина внутри рамки

    def _line(content: str) -> str:
        """PATCH_007: обёртка строки в рамку (с учётом эмодзи)."""
        import re
        clean = re.sub(r"\033\[[0-9;]*m", "", content)
        pad = W - _display_width(clean)
        if pad < 0:
            pad = 0
        return f"║ {content}{' ' * pad} ║"

    lines = []
    lines.append("╔" + "═" * (W + 2) + "╗")
    lines.append(_line(f"{BOLD}{CYAN}📊 POCKET OPTION ANALYZER{RESET}{double_str}"))
    lines.append("╠" + "═" * (W + 2) + "╣")

    # WR по сериям
    lines.append(_line(
        f"WR (серии):  {wr_series_color}{BOLD}{series_wr:5.1f}%{RESET}  "
        f"{GREEN}✅{RESET} {state.total_wins} / {RED}❌{RESET} {state.total_losses}"
    ))
    # WR по сделкам
    lines.append(_line(
        f"WR (сделки): {wr_trade_color}{BOLD}{trade_wr:5.1f}%{RESET}  "
        f"{GREEN}✅{RESET} {state.win_trades} / {RED}❌{RESET} {state.loss_trades}"
    ))

    lines.append("╠" + "═" * (W + 2) + "╣")

    # Баланс
    lines.append(_line(f"Баланс:      {BOLD}${balance:.2f}{RESET}"))
    # PnL
    if start_bal > 0:
        pnl_str = f"+${pnl:.2f}" if pnl > 0 else f"-${abs(pnl):.2f}" if pnl < 0 else "$0.00"
        lines.append(_line(f"PnL (старт): {pnl_color}{pnl_str}{RESET}"))
    # Ref
    lines.append(_line(f"Ref:         ${ref_balance:.2f}"))
    # Просадка
    lines.append(_line(
        f"Просадка:    {dd_color}${drawdown_threshold:.2f} ({dd_pct:.1f}%){RESET}"
    ))
    # Следующая полка
    lines.append(_line(f"Следующая:   ${next_ref:.2f}"))

    lines.append("╠" + "═" * (W + 2) + "╣")

    # PATCH_008: по попыткам
    att = getattr(state, "wins_by_attempt", {})
    if att:
        att_str = ", ".join(f"{k}:{att.get(k, 0)}" for k in (1, 2, 3, 4, 5, 6, 7))
        lines.append(_line(f"По попыткам: {att_str}"))

    # Серий
    lines.append(_line(f"Серий:       {state.total_series}"))
    # Пропусков
    lines.append(_line(f"Пропусков:   {state.total_skips}"))
    # Смен пар
    lines.append(_line(f"Смен пар:    {state.total_pair_changes}"))

    lines.append("╚" + "═" * (W + 2) + "╝")

    return "\n".join(lines)


# PATCH_013: сохранение HUD в JSON (для tmux + hud_show.py)
def save_hud_to_json(
    state,
    balance: float,
    ref_balance: float,
    drawdown_threshold: float,
    next_ref: float,
    path: str = "hud.json",
    double_mode: bool = False,
):
    """PATCH_013: сохраняет HUD в JSON (каждые 10 сек)."""
    import json
    import time

    # WR по сериям
    series_wr = (state.total_wins / state.total_series * 100) if state.total_series else 0.0
    # WR по сделкам (без TIES)
    _denom = state.win_trades + state.loss_trades
    trade_wr = (state.win_trades / _denom * 100) if _denom > 0 else 0.0
    # Просадка
    dd_pct = ((ref_balance - balance) / ref_balance * 100) if ref_balance > 0 else 0.0

    start_bal = getattr(state, "start_balance", 0.0)
    pnl = balance - start_bal if start_bal > 0 else 0.0

    data = {
        "timestamp": time.time(),
        "pnl": round(pnl, 2),
        "start_balance": round(start_bal, 2),
        "double_mode": double_mode,
        "wr_series": round(series_wr, 1),
        "wr_trades": round(trade_wr, 1),
        "total_series": state.total_series,
        "total_wins": state.total_wins,
        "total_losses": state.total_losses,
        "total_trades": state.total_trades,
        "win_trades": state.win_trades,
        "loss_trades": state.loss_trades,
        "ties": getattr(state, "ties", 0),
        "balance": round(balance, 2),
        "ref_balance": round(ref_balance, 2),
        "drawdown_threshold": round(drawdown_threshold, 2),
        "drawdown_pct": round(dd_pct, 1),
        "next_ref": round(next_ref, 2),
        "total_skips": state.total_skips,
        "total_pair_changes": state.total_pair_changes,
        "wins_by_attempt": getattr(state, "wins_by_attempt", {}),
    }

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"save_hud_to_json: {e}")


def print_hud(state, balance: float, ref_balance: float,
              drawdown_threshold: float, next_ref: float,
              double_mode: bool = False):
    """PATCH_006: печатает HUD-карточку в консоль."""
    print()
    print(render_hud(state, balance, ref_balance,
                     drawdown_threshold, next_ref, double_mode))
    print()
