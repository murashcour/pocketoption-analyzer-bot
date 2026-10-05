cd "$(dirname "$0")"

# Активация venv / Activate venv
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "❌ venv не найден. Запусти: python3 -m venv venv"
    echo "❌ venv not found. Run: python3 -m venv venv"
    exit 1
fi

# Проверка SSID / Check SSID
if [ -z "$PO_SSID" ]; then
    if [ -f ~/.po_ssid ]; then
        export PO_SSID="$(cat ~/.po_ssid)"
        echo "✅ SSID загружен из ~/.po_ssid"
        echo "✅ SSID loaded from ~/.po_ssid"
    else
        echo "❌ PO_SSID не задан и ~/.po_ssid не найден"
        echo "❌ PO_SSID not set and ~/.po_ssid not found"
        exit 1
    fi
fi

# Удалить stop.flag если остался
rm -f stop.flag

# Запуск в screen
if command -v screen &> /dev/null; then
    echo "🚀 Запуск в screen (сессия: bot)"
    echo "🚀 Starting in screen (session: bot)"
    screen -dmS bot bash -c "cd $(pwd) && source venv/bin/activate && export PO_SSID='$PO_SSID' && python analyzer_bot.py; exec bash"
    echo "✅ Бот запущен. Подключиться: screen -r bot"
    echo "✅ Bot started. Attach: screen -r bot"
else
    echo "⚠️ screen не найден. Запуск в текущем терминале..."
    echo "⚠️ screen not found. Running in current terminal..."
    python analyzer_bot.py
fi
