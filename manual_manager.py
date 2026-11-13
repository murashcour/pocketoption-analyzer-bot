#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import os
import time
from BinaryOptionsToolsV2 import PocketOptionAsync

FIRST_BET = 1.0
MULTIPLIER = 2.3
MAX_STEPS = 7
PAYOUT = 0.92
TARGET_PCT = 10.0
STOP_LOSS_PCT = 35.0
SSID_FILE = os.path.expanduser("~/.po_ssid")

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
        
        cumulative_loss = 0.0
        for i in range(MAX_STEPS):
            bet = round(FIRST_BET * (MULTIPLIER ** i), 2)
            self.steps.append({
                "step": i + 1,
                "bet": bet,
                "loss": -cumulative_loss if i > 0 else 0,
                "profit": round((bet / PAYOUT) - bet, 2)
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
            print(f"{s['step']:<5} | ${s['bet']:<9.2f} | ${cum:<9.2f} | +${(s['bet']/PAYOUT - s['bet']):<14.2f}")
            cum += s['bet']
        print("="*55 + "\n")

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
            
            self.print_table()
            print(f"💰 Баланс: ${self.start_balance:.2f}")
            print(f"🎯 Цель: +{TARGET_PCT}% (${self.start_balance * TARGET_PCT / 100:.2f})")
            print(f"🛑 Стоп: -{STOP_LOSS_PCT}% (${self.start_balance * STOP_LOSS_PCT / 100:.2f})\n")
            
            print(f"🎯 СТАВКА: ${self.get_bet():.2f} (Шаг 1/{MAX_STEPS})")
            print("⏳ Жду закрытия сделок... (открывай вручную в PocketOption)")

            last_check = time.time()

            while not self.stopped:
                try:
                    closed = await client.closed_deals()
                    new_deals = [d for d in closed if d.get("id") not in self.seen_ids]
                    for d in new_deals: self.seen_ids.add(d.get("id"))
                    new_deals.sort(key=lambda x: x.get("closeTimestamp", 0))

                    for d in new_deals:
                        asset = d.get("asset", "")
                        profit_str = str(d.get("profit", "0")).replace("+", "").replace(",", ".")
                        try: profit = float(profit_str)
                        except: continue
                        
                        if profit == 0:
                            print(f"\n⚪ {asset}: возврат. Ставка та же: ${self.get_bet():.2f}")
                            continue

                        if profit > 0:
                            self.wins += 1
                            self.current_step = 1
                            print(f"\n✅ WIN {asset}: +${profit:.2f}. Серия окончена.")
                            print(f"🎯 Следующая ставка: ${self.get_bet():.2f} (Шаг 1/{MAX_STEPS})")
                        else:
                            self.losses += 1
                            if self.current_step < MAX_STEPS:
                                self.current_step += 1
                                print(f"\n❌ LOSS {asset}: -${abs(profit):.2f}. Переход на шаг {self.current_step}.")
                                print(f"🎯 СТАВКА: ${self.get_bet():.2f} (Шаг {self.current_step}/{MAX_STEPS})")
                            else:
                                self.current_step = 1
                                print(f"\n💀 LOSS {asset}: -${abs(profit):.2f}. СЕРИЯ ПРОИГРАНА.")
                                print(f"🎯 Новая серия. Ставка: ${self.get_bet():.2f} (Шаг 1/{MAX_STEPS})")

                    if time.time() - last_check > 10:
                        bal = await self.get_balance(client)
                        if bal:
                            self.current_balance = bal
                            pnl = self.current_balance - self.start_balance
                            pnl_pct = (pnl / self.start_balance) * 100 if self.start_balance > 0 else 0
                            print(f"💰 Баланс: ${self.current_balance:.2f} | PnL: {pnl:+.2f} ({pnl_pct:+.1f}%)")
                            
                            if pnl_pct >= TARGET_PCT:
                                print(f"\n🎯 ЦЕЛЬ ДОСТИГНУТА! PnL: {pnl_pct:+.2f}%. СТОП.")
                                self.stopped = True; break
                            if pnl_pct <= -STOP_LOSS_PCT:
                                print(f"\n🛑 СТОП-ЛОСС! PnL: {pnl_pct:+.2f}%. ОСТАНОВИСЬ.")
                                self.stopped = True; break
                        last_check = time.time()

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
