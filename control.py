#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
control.py (PATCH_098): управление авто-ботом.

Команды:
  python control.py status   # статус (HUD + флаги + МСК)
  python control.py pause    # поставить паузу
  python control.py resume   # снять паузу
  python control.py stop     # остановить бота
"""
import json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
PAUSE_FLAG = BASE_DIR / "pause.flag"
STOP_FLAG = BASE_DIR / "stop.flag"
CONFIG_FILE = BASE_DIR / "config.json"
HUD_FILE = BASE_DIR / "hud.json"
MSK = timedelta(hours=3)


def msk_now(): return datetime.now(timezone.utc) + MSK

def load_json(p):
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}

def is_bot_running():
    import subprocess
    try:
        r = subprocess.run(["pgrep", "-f", "analyzer_bot.py"],
                           capture_output=True, text=True, timeout=5)
        return bool(r.stdout.strip())
    except Exception:
        return False

def cmd_status():
    cfg, hud, now = load_json(CONFIG_FILE), load_json(HUD_FILE), msk_now()
    work_on = bool(cfg.get("work_hours_enabled", False))
    work_h = cfg.get("work_hours", [])
    in_h = (now.hour in work_h) if work_on else True
    paused, stopped, running = PAUSE_FLAG.exists(), STOP_FLAG.exists(), is_bot_running()
    if stopped: state = "STOPPED (stop.flag)"
    elif not running: state = "NOT_RUNNING"
    elif paused: state = "PAUSED (pause.flag)"
    elif not in_h: state = f"OUT_OF_HOURS (час {now.hour})"
    else: state = "WORKING"
    print("=" * 60)
    print("🤖 PocketOption Analyzer Bot")
    print("=" * 60)
    print(f"Время МСК:   {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Состояние:   {state}")
    print(f"Процесс:     {'✅ жив' if running else '❌ не запущен'}")
    print(f"pause.flag:  {'⏸ ЕСТЬ' if paused else 'нет'}")
    print(f"stop.flag:   {'🛑 ЕСТЬ' if stopped else 'нет'}")
    if work_on:
        print(f"work_hours:  {work_h}")
        print(f"В часах:     {'✅ да' if in_h else '❌ нет'}")
    else:
        print(f"work_hours:  ❌ отключено")
    if hud:
        print("-" * 60)
        print(f"📊 Баланс:   ${hud.get('balance', 0):.2f}")
        print(f"   PnL:      ${hud.get('pnl', 0):+.2f}")
        print(f"   WR сер:   {hud.get('wr_series', 0):.1f}%")
        print(f"   WR сдел:  {hud.get('wr_trades', 0):.1f}%")
        print(f"   Серий:    {hud.get('total_series', 0)}")
        print(f"   Сделок:   {hud.get('total_trades', 0)}")
        print(f"   Просадка: {hud.get('drawdown_pct', 0):+.1f}%")
        print(f"   Uptime:   {hud.get('uptime_str', '?')}")
    else:
        print("📊 HUD: не найден")
    print("=" * 60)

def cmd_pause():
    PAUSE_FLAG.touch()
    print(f"⏸ Пауза установлена: {PAUSE_FLAG.name}")
    print("   Снять: python control.py resume")

def cmd_resume():
    if PAUSE_FLAG.exists():
        PAUSE_FLAG.unlink()
        print(f"▶️  Пауза снята")
    else:
        print("ℹ️  Паузы не было")

def cmd_stop():
    STOP_FLAG.touch()
    print(f"🛑 Стоп-флаг установлен: {STOP_FLAG.name}")

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    cmd = sys.argv[1].strip().lower()
    {"status": cmd_status, "pause": cmd_pause, "resume": cmd_resume, "stop": cmd_stop}.get(
        cmd, lambda: (print(f"❌ Неизвестная команда: {cmd}"), sys.exit(1))
    )()

if __name__ == "__main__":
    main()
