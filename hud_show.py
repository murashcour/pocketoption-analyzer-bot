#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PATCH_013: Рендер HUD из hud.json (для tmux + watch).

Использование:
  # В tmux:
  watch -n 5 python3 hud_show.py

  # Или в отдельном окне:
  while true; do python3 hud_show.py; sleep 5; done
"""
import json
import sys
from pathlib import Path

HUD_JSON = Path("hud.json")

# ANSI-цвета
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[96m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
GRAY = "\033[90m"


def _wr_color(wr: float) -> str:
    if wr >= 55.0:
        return GREEN
    if wr >= 45.0:
        return YELLOW
    return RED


def _delta_color(delta: float) -> str:
    if delta > 0:
        return GREEN
    if delta < 0:
        return RED
    return GRAY


def main():
    if not HUD_JSON.exists():
        print(f"⏳ Ожидание hud.json... (файл не найден)")
        sys.exit(0)

    try:
        data = json.loads(HUD_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ Ошибка чтения hud.json: {e}")
        sys.exit(1)

    # === Формируем карточку ===
    W = 46

    def _display_width(s: str) -> int:
        import unicodedata
        width = 0
        for ch in s:
            if unicodedata.east_asian_width(ch) in ('W', 'F'):
                width += 2
            elif ord(ch) > 0x1F000:
                width += 2
            else:
                width += 1
        return width

    def _line(content: str) -> str:
        import re
        clean = re.sub(r"\033\[[0-9;]*m", "", content)
        pad = W - _display_width(clean)
        if pad < 0:
            pad = 0
        return f"║ {content}{' ' * pad} ║"

    lines = []
    lines.append("╔" + "═" * (W + 2) + "╗")

    # Заголовок
    title = f"{BOLD}{CYAN}📊 POCKET OPTION ANALYZER{RESET}"
    if data.get("double_mode"):
        title += f" {MAGENTA}[УДВОЕНИЕ]{RESET}"
    lines.append(_line(title))

    # PATCH_042: старт и аптайм
    st_time = data.get("start_time_str", "")
    st_tz = data.get("start_tz_str", "")
    up_str = data.get("uptime_str", "")
    if st_time and st_time != "-":
        tz_label = f" ({st_tz})" if st_tz else ""
        lines.append(_line(f"Старт:       {st_time}{tz_label}"))
        lines.append(_line(f"Работает:    {up_str}"))

    lines.append("╠" + "═" * (W + 2) + "╣")

    # WR (серии)
    ws = data.get("wr_series", 0)
    ws_color = _wr_color(ws)
    lines.append(_line(
        f"WR (серии):  {ws_color}{BOLD}{ws:5.1f}%{RESET}  "
        f"{GREEN}✅{RESET} {data.get('total_wins', 0)} / {RED}❌{RESET} {data.get('total_losses', 0)}"
    ))

    # WR (сделки)
    wt = data.get("wr_trades", 0)
    wt_color = _wr_color(wt)
    ties = data.get("ties", 0)
    ties_str = f" / {YELLOW}⚪{RESET} {ties}" if ties > 0 else ""
    lines.append(_line(
        f"WR (сделки): {wt_color}{BOLD}{wt:5.1f}%{RESET}  "
        f"{GREEN}✅{RESET} {data.get('win_trades', 0)} / {RED}❌{RESET} {data.get('loss_trades', 0)}{ties_str}"
    ))

    lines.append("╠" + "═" * (W + 2) + "╣")

    # Баланс
    balance = data.get("balance", 0)
    lines.append(_line(f"Баланс:      {BOLD}${balance:.2f}{RESET}"))
    
    # PnL
    pnl = data.get("pnl", 0)
    start_bal = data.get("start_balance", 0)
    if start_bal > 0:
        if pnl > 0:
            pnl_color = "\033[94m"  # Синий
            pnl_str = f"+${pnl:.2f}"
        elif pnl < 0:
            pnl_color = "\033[91m"  # Красный
            pnl_str = f"-${abs(pnl):.2f}"
        else:
            pnl_color = GRAY
            pnl_str = "$0.00"
        lines.append(_line(f"PnL (старт): {pnl_color}{pnl_str}{RESET}"))

    # Ref
    ref = data.get("ref_balance", 0)
    lines.append(_line(f"Ref:         ${ref:.2f}"))

    # Просадка
    dd = data.get("drawdown_threshold", 0)
    dd_pct = data.get("drawdown_pct", 0)
    dd_color = _delta_color(-dd_pct) if dd_pct > 0 else GRAY
    lines.append(_line(
        f"Просадка:    {dd_color}${dd:.2f} ({dd_pct:+.1f}%){RESET}"
    ))

    # Следующая
    next_ref = data.get("next_ref", 0)
    lines.append(_line(f"Следующая:   ${next_ref:.2f}"))

    lines.append("╠" + "═" * (W + 2) + "╣")

    # По попыткам
    att = data.get("wins_by_attempt", {})
    if att:
        att_str = ", ".join(f"{k}:{att.get(str(k), att.get(k, 0))}" for k in (1, 2, 3, 4, 5, 6, 7))
        lines.append(_line(f"По попыткам: {att_str}"))

    # Серий
    lines.append(_line(f"Серий:       {data.get('total_series', 0)}"))
    # Сделок (PATCH_040)
    max_tr = data.get("max_trades")
    if max_tr:
        lines.append(_line(f"Сделок:      {data.get('total_trades', 0)} / {max_tr}"))
    # Пропусков
    lines.append(_line(f"Пропусков:   {data.get('total_skips', 0)}"))
    # Смен пар
    lines.append(_line(f"Смен пар:    {data.get('total_pair_changes', 0)}"))

    lines.append("╚" + "═" * (W + 2) + "╝")

    print("\n".join(lines))

    # Время обновления
    import time
    ts = data.get("timestamp", 0)
    if ts > 0:
        age = time.time() - ts
        if age > 60:
            print(f"\n{GRAY}⚠ Обновлено {age:.0f} сек назад{RESET}")
        else:
            print(f"\n{GRAY}✓ Обновлено {age:.0f} сек назад{RESET}")


if __name__ == "__main__":
    main()
