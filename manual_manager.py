#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import json
import os
import time
from pathlib import Path
from BinaryOptionsToolsV2 import PocketOptionAsync

FIRST_BET = 1.0
MULTIPLIER = 2.3
MAX_STEPS = 7
PAYOUT = 0.92
TARGET_PCT = 10.0
STOP_LOSS_PCT = 35.0
SSID_FILE = os.path.expanduser("~/.po_ssid")
MODE = os.getenv("MM_MODE", "advisor").strip().lower()  # advisor | manual
HUD_MANUAL_JSON = Path("hud_manual.json")

class ManualManager:
    def __init__(self, ssid):
        self.ssid = ssid
        self.start_balance = 0.0
        self.current_balance = 0.0
        self.current_step = 1
        self.wins = 0
        self.losses = 0
        self.seen_ids = set()
        self.stopped = False
        self.steps = []
        self.start_ts = 0.0
        # PATCH_070
        self.series_wins = 0
        self.series_losses = 0
        self.wins_by_attempt = {i: 0 for i in range(1, 8)}
        self.last_deal = None
        self.started_wall = 0.0
        
        cumulative_loss = 0.0
        for i in range(MAX_STEPS):
            bet = round(FIRST_BET * (MULTIPLIER ** i), 2)
            self.steps.append({
                "step": i + 1,
                "bet": bet,
                "loss": -cumulative_loss if i > 0 else 0,
                # PATCH_066: правильный профит = bet * PAYOUT - cumulative_loss
                "profit": round(bet * PAYOUT - cumulative_loss, 2)
            })
            cumulative_loss += bet

    async def get_balance(self, client):
        try: return float(await client.balance())
        except: return None

    def print_table(self):
        print("\n" + "="*55)
        print(f"📊 ТАБЛИЦА МАРТИНГЕЙЛА (x{MULTIPLIER}, payout {PAYOUT*100}%)")
        print("="*55)
        print(f"{'Шаг':<5} | {'Ставка':<10} | {'Затраты':<10} | {'Профит (если WIN)':<15}")
        print("-" * 55)
        cum = 0
        for s in self.steps:
            print(f"{s['step']:<5} | ${s['bet']:<9.2f} | ${cum:<9.2f} | +${s['profit']:<14.2f}")
            cum += s['bet']
        print("="*55 + "\n")

    @staticmethod
    def _dw(s: str) -> int:
        import unicodedata
        w = 0
        for ch in s:
            if unicodedata.east_asian_width(ch) in ("W", "F") or ord(ch) > 0x1F000:
                w += 2
            else:
                w += 1
        return w

    def _line(self, content: str, W: int = 46) -> str:
        import re
        clean = re.sub(r"\033\[[0-9;]*m", "", content)
        pad = max(0, W - self._dw(clean))
        padding = " " * pad
        return f"\u2551 {content}{padding} \u2551"

    def _write_hud(self):
        now = time.time()
        if self.started_wall <= 0: self.started_wall = now
        up = int(now - self.started_wall); uh, um = divmod(up // 60, 60)
        up_str = f"{uh}\u0447 {um}\u043c" if uh > 0 else f"{um}\u043c"
        ts = self.series_wins + self.series_losses
        tt = self.wins + self.losses
        wr_s = (self.series_wins / ts * 100.0) if ts > 0 else 0.0
        wr_t = (self.wins / tt * 100.0) if tt > 0 else 0.0
        pnl = self.current_balance - self.start_balance if self.start_balance > 0 else 0.0
        ref = self.start_balance if self.start_balance > 0 else 0.0
        dd_th = ref * (1 - STOP_LOSS_PCT / 100.0)
        dd_p = max(0.0, (1 - self.current_balance / ref) * 100.0) if ref > 0 else 0.0
        try: st_local = time.strftime("%d.%m %H:%M", time.localtime(self.started_wall)) if self.started_wall > 0 else "-"
        except Exception: st_local = "-"
        mode_label = "advisor" if MODE == "advisor" else "manual"
        data = {
            "timestamp": now,
            "title": f"\U0001F3AF MANUAL MANAGER [{mode_label}]",
            "pnl": round(pnl, 2),
            "start_time_str": st_local,
            "start_tz_str": "\u041c\u0421\u041a",
            "uptime_str": up_str,
            "start_balance": round(self.start_balance, 2),
            "double_mode": False,
            "wr_series": round(wr_s, 1),
            "wr_trades": round(wr_t, 1),
            "total_series": ts,
            "total_wins": self.series_wins,
            "total_losses": self.series_losses,
            "total_trades": tt,
            "win_trades": self.wins,
            "loss_trades": self.losses,
            "ties": 0,
            "balance": round(self.current_balance, 2),
            "ref_balance": round(ref, 2),
            "drawdown_threshold": round(dd_th, 2),
            "drawdown_pct": round(dd_p, 1),
            "next_ref": round(ref * 1.10, 2),
            "total_skips": 0,
            "total_pair_changes": 0,
            "wins_by_attempt": {str(k): v for k, v in self.wins_by_attempt.items()},
        }
        try: HUD_MANUAL_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e: print(f"\u26a0 hud_manual.json: {e}")

    def _print_card(self):
        W = 46
        now = time.time()
        if self.started_wall <= 0: self.started_wall = now
        up = int(now - self.started_wall); uh, um = divmod(up // 60, 60)
        up_str = f"{uh}\u0447 {um}\u043c" if uh > 0 else f"{um}\u043c"
        ts = self.series_wins + self.series_losses
        tt = self.wins + self.losses
        wr_s = (self.series_wins / ts * 100.0) if ts > 0 else 0.0
        wr_t = (self.wins / tt * 100.0) if tt > 0 else 0.0
        pnl = self.current_balance - self.start_balance if self.start_balance > 0 else 0.0
        cum = sum(s["bet"] for s in self.steps[:self.current_step - 1])
        profit_at_win = self.steps[self.current_step - 1]["profit"]
        mode_label = "advisor" if MODE == "advisor" else "manual"
        sep = "\u2560" + "\u2550" * (W + 2) + "\u2563"
        top = "\u2554" + "\u2550" * (W + 2) + "\u2557"
        bot = "\u255a" + "\u2550" * (W + 2) + "\u255d"
        lines = [
            top,
            self._line(f"\U0001F3AF MANUAL MANAGER [{mode_label}]", W),
            self._line(f"\u0420\u0430\u0431\u043e\u0442\u0430\u0435\u0442:    {up_str}", W),
            sep,
            self._line(f"\u0428\u0430\u0433:         {self.current_step} / {MAX_STEPS}", W),
            self._line(f"\u0421\u0442\u0430\u0432\u043a\u0430:      ${self.get_bet():.2f}", W),
            self._line(f"\u0417\u0430\u0442\u0440\u0430\u0442\u044b:     ${cum:.2f}", W),
            self._line(f"\u041f\u0440\u043e\u0444\u0438\u0442:      +${profit_at_win:.2f} (\u0435\u0441\u043b\u0438 WIN)", W),
            sep,
            self._line(f"WR (\u0441\u0435\u0440\u0438\u0438):  {wr_s:5.1f}%  \u2705 {self.series_wins} / \u274c {self.series_losses}", W),
            self._line(f"WR (\u0441\u0434\u0435\u043b\u043a\u0438): {wr_t:5.1f}%  \u2705 {self.wins} / \u274c {self.losses}", W),
            sep,
            self._line(f"\u0411\u0430\u043b\u0430\u043d\u0441:      ${self.current_balance:.2f}", W),
            self._line(f"PnL:         {pnl:+.2f}", W),
            self._line(f"\u0426\u0435\u043b\u044c:        +{TARGET_PCT}% (${self.start_balance * TARGET_PCT / 100:.2f})", W),
            self._line(f"\u0421\u0442\u043e\u043f:        -{STOP_LOSS_PCT}% (${self.start_balance * STOP_LOSS_PCT / 100:.2f})", W),
            sep,
        ]
        if self.last_deal:
            ld = self.last_deal; pr = ld.get("profit", 0)
            sign = "\u2705" if pr > 0 else ("\u26aa" if pr == 0 else "\u274c")
            asset = ld.get("asset", "?")
            lines.append(self._line(f"\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u044f\u044f:   {asset} {sign} ${pr:+.2f}", W))
        else:
            lines.append(self._line("\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u044f\u044f:   \u2014", W))
        lines.append(self._line("\u0421\u0442\u0430\u0442\u0443\u0441:      \u0416\u0434\u0443 \u0441\u0434\u0435\u043b\u043a\u0443", W))
        lines.append(bot)
        print("\n".join(lines))

    def get_bet(self):
        if self.current_step <= MAX_STEPS:
            return self.steps[self.current_step - 1]["bet"]
        return self.steps[-1]["bet"]

    async def run(self):
        async with PocketOptionAsync(ssid=self.ssid) as client:
            for _ in range(10):
                bal = await self.get_balance(client)
                if bal: self.start_balance = self.current_balance = bal; break
                await asyncio.sleep(2)
            
            # PATCH_069: фиксируем время старта для фильтра openTimestamp
            self.start_ts = time.time()
            # PATCH_070: wall-clock для uptime
            self.started_wall = time.time()
            # PATCH_065: игнорируем все существующие сделки (от прошлых прогонов)
            try:
                _existing = await client.closed_deals()
                for _d in _existing:
                    if _d.get("id"):
                        self.seen_ids.add(_d.get("id"))
                print(f"📚 Проигнорировано старых сделок: {len(self.seen_ids)}")
            except Exception as _e:
                print(f"⚠ Не удалось загрузить старые сделки: {_e}")
            
            self.print_table()
            print(f"💰 Баланс: ${self.start_balance:.2f}")
            print(f"🎯 Цель: +{TARGET_PCT}% (${self.start_balance * TARGET_PCT / 100:.2f})")
            print(f"🛑 Стоп: -{STOP_LOSS_PCT}% (${self.start_balance * STOP_LOSS_PCT / 100:.2f})\n")
            
            print(f"🎯 СТАВКА: ${self.get_bet():.2f} (Шаг 1/{MAX_STEPS})")
            print("⏳ Жду закрытия сделок... (открывай вручную в PocketOption)")
            # PATCH_070: первичная отрисовка
            self._print_card()
            self._write_hud()

            last_check = time.time()

            while not self.stopped:
                try:
                    closed = await client.closed_deals()
                    new_deals = [d for d in closed if d.get("id") not in self.seen_ids]
                    for d in new_deals: self.seen_ids.add(d.get("id"))
                    new_deals.sort(key=lambda x: x.get("closeTimestamp", 0))

                    for d in new_deals:
                        # PATCH_069: фильтр по openTimestamp (приведение к float)
                        try:
                            open_ts = float(d.get("openTimestamp", 0))
                        except (ValueError, TypeError):
                            open_ts = 0.0
                        if open_ts < self.start_ts:
                            continue
                        asset = d.get("asset", "")
                        profit_str = str(d.get("profit", "0")).replace("+", "").replace(",", ".")
                        try: profit = float(profit_str)
                        except: continue
                        
                        if profit == 0:
                            print(f"\n⚪ {asset}: возврат. Ставка та же: ${self.get_bet():.2f}")
                            self.last_deal = {"asset": asset, "profit": 0.0}
                            self._print_card(); self._write_hud()
                            continue

                        if profit > 0:
                            self.wins += 1
                            prev_step = self.current_step
                            self.series_wins += 1
                            if 1 <= prev_step <= 7:
                                self.wins_by_attempt[prev_step] = self.wins_by_attempt.get(prev_step, 0) + 1
                            self.current_step = 1
                            print(f"\n✅ WIN {asset}: +${profit:.2f}. Серия окончена.")
                            print(f"🎯 Следующая ставка: ${self.get_bet():.2f} (Шаг 1/{MAX_STEPS})")
                            self.last_deal = {"asset": asset, "profit": profit}
                            self._print_card(); self._write_hud()
                        else:
                            self.losses += 1
                            if self.current_step < MAX_STEPS:
                                self.current_step += 1
                                print(f"\n❌ LOSS {asset}: -${abs(profit):.2f}. Переход на шаг {self.current_step}.")
                                print(f"🎯 СТАВКА: ${self.get_bet():.2f} (Шаг {self.current_step}/{MAX_STEPS})")
                                self.last_deal = {"asset": asset, "profit": profit}
                                self._print_card(); self._write_hud()
                            else:
                                self.series_losses += 1
                                self.current_step = 1
                                print(f"\n💀 LOSS {asset}: -${abs(profit):.2f}. СЕРИЯ ПРОИГРАНА.")
                                print(f"🎯 Новая серия. Ставка: ${self.get_bet():.2f} (Шаг 1/{MAX_STEPS})")
                                self.last_deal = {"asset": asset, "profit": profit}
                                self._print_card(); self._write_hud()

                    # PATCH_067: проверяем лимиты только после закрытия сделки, без спама
                    if len(new_deals) > 0:
                        bal = await self.get_balance(client)
                        if bal:
                            self.current_balance = bal
                            pnl = self.current_balance - self.start_balance
                            pnl_pct = (pnl / self.start_balance) * 100 if self.start_balance > 0 else 0
                            
                            if pnl_pct >= TARGET_PCT:
                                print(f"\n🎯 ЦЕЛЬ ДОСТИГНУТА! PnL: {pnl_pct:+.2f}%. СТОП.")
                                self.stopped = True; break
                            if pnl_pct <= -STOP_LOSS_PCT:
                                print(f"\n🛑 СТОП-ЛОСС! PnL: {pnl_pct:+.2f}%. ОСТАНОВИСЬ.")
                                self.stopped = True; break

                    await asyncio.sleep(3)
                except Exception as e:
                    print(f"⚠ Ошибка: {e}")
                    await asyncio.sleep(5)

async def main():
    ssid = os.getenv("PO_SSID", "").strip()
    if not ssid and os.path.exists(SSID_FILE):
        with open(SSID_FILE) as f: ssid = f.read().strip()
    if not ssid: print("❌ SSID не найден"); return
    await ManualManager(ssid).run()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("\n⏹ Остановлено")
