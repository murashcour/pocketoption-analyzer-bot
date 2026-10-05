#!/bin/bash
# Остановка бота
# Stop bot

cd "$(dirname "$0")"

touch stop.flag
echo "⏹ Флаг stop.flag создан"
echo "⏹ stop.flag created"
echo ""
echo "Бот завершит текущую серию и остановится (~70 сек)"
echo "Bot will finish current series and stop (~70 sec)"
echo ""
echo "Проверить статус: ps aux | grep analyzer_bot"
echo "Check status: ps aux | grep analyzer_bot"
