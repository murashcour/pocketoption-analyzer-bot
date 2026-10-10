#!/bin/bash
# Запуск бота PocketOption Analyzer
cd "$(dirname "$0")"

# Проверка, не запущен ли уже бот
if screen -ls 2>/dev/null | grep -q "\.bot"; then
    echo "⚠️ Сессия screen 'bot' уже существует."
    echo "   Останови: screen -r bot (Ctrl+C), затем: screen -X -S bot quit"
    exit 1
fi

# Проверка ~/.po_ssid
if [ ! -f ~/.po_ssid ]; then
    echo "❌ ~/.po_ssid не найден. Получи SSID (см. docs/SSID.md)"
    exit 1
fi

# Активация venv
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "❌ venv не найден. Запусти: python3 -m venv venv"
    exit 1
fi

# Удалить stop.flag если остался
rm -f stop.flag

# Запуск в screen (SSID читается ботом из ~/.po_ssid, НЕ передаётся через env)
if command -v screen &> /dev/null; then
    echo "🚀 Запуск в screen (сессия: bot)"
    screen -dmS bot bash -c "cd $(pwd) && source venv/bin/activate && python analyzer_bot.py; exec bash"
    echo "✅ Бот запущен. Подключиться: screen -r bot"
else
    echo "⚠️ screen не найден. Запуск в текущем терминале..."
    python analyzer_bot.py
fi
