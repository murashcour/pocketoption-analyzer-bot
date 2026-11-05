# -*- coding: utf-8 -*-
"""
HUD: красивая карточка в консоль (WR, серии, баланс, просадка).

PATCH_006: только визуализация. Не трогает логику торговли.
"""
from typing import Optional


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

    # === WR по сделкам ===
    trade_wr = 0.0
    if state.total_trades > 0:
        trade_wr = (state.win_trades / state.total_trades) * 100

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
        """Обёртка строки в рамку."""
        # Убираем ANSI для подсчёта длины
        import re
        clean = re.sub(r"\033\[[0-9;]*m", "", content)
        pad = W - len(clean)
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
    # Ref
    lines.append(_line(f"Ref:         ${ref_balance:.2f}"))
    # Просадка
    lines.append(_line(
        f"Просадка:    {dd_color}${drawdown_threshold:.2f} ({dd_pct:.1f}%){RESET}"
    ))
    # Следующая полка
    lines.append(_line(f"Следующая:   ${next_ref:.2f}"))

    lines.append("╠" + "═" * (W + 2) + "╣")

    # Серий
    lines.append(_line(f"Серий:       {state.total_series}"))
    # Пропусков
    lines.append(_line(f"Пропусков:   {state.total_skips}"))
    # Смен пар
    lines.append(_line(f"Смен пар:    {state.total_pair_changes}"))

    lines.append("╚" + "═" * (W + 2) + "╝")

    return "\n".join(lines)


def print_hud(state, balance: float, ref_balance: float,
              drawdown_threshold: float, next_ref: float,
              double_mode: bool = False):
    """PATCH_006: печатает HUD-карточку в консоль."""
    print()
    print(render_hud(state, balance, ref_balance,
                     drawdown_threshold, next_ref, double_mode))
    print()
