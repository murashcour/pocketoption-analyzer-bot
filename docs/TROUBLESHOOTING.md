# Решение проблем

Частые ошибки и способы их исправить.

## SSID ошибки

### PocketOptionError: Failed to parse ssid

Причина: в SSID лишняя кавычка после uid.

Проверь строку:

    "uid":94604880","platform":3

Должно быть:

    "uid":94604880,"platform":3

Решение: убрать лишнюю кавычку, перезаписать SSID.

### Core(ChannelReceiver(Closed))

Причина: SSID устарел или недействителен.

Признаки:

- Баланс не возвращается
- Свечи не приходят
- Таймауты

Решение:

1. Получить новый SSID (см. docs/SSID.md)
2. Перезапустить бота

### Invalid asset

Причина: неправильное имя пары.

Правильно: EURUSD_otc (с подчёркиванием и _otc)

Неправильно: EURUSD, EUR/USD OTC, eurusd_otc

## Ошибки API

### Таймаут получения свечей

Причина: SSID работает, но API медленный.

Признаки:

    WARNING | Таймаут получения свечей (1/3)
    WARNING | Таймаут получения свечей (2/3)
    WARNING | Таймаут получения свечей (3/3)

Решение:

1. Проверить интернет
2. Подождать 30 секунд (бот сам ждёт)
3. Если повторяется — обновить SSID

### get_candles_live зависает

Причина: async-генератор. Не работает через await — нужен async for.

Неправильно:

    result = await client.get_candles_live(...)

Правильно:

    async for closed, forming in client.get_candles_live(...):
        ...

## Проблемы с балансом

### Баланс не обновляется

Причина: заморозка на открытые сделки.

Решение: подождать закрытия всех сделок.

### Баланс быстро падает

Причина: серия минусов.

Признаки:

    ❌ ПРОИГРЫШ -$1.50
    ❌ ПРОИГРЫШ -$3.00
    ❌ ПРОИГРЫШ -$6.00

Решение:

1. Проверить настройки (MIN_CONFIRMATIONS, RSI)
2. Уменьшить base_percent (риск)
3. Остановить на день
4. Проверить winrate в логе

## Проблемы с Trading

### Бот не открывает сделки

Причины:

1. Payout пары < 85% — пропускает
2. Нет сигнала (RSI в нейтральной зоне)
3. ATR < 0.1% — флэт
4. S/R блокирует

Проверить в логе:

    ⏸ Пропуск [TIME] Нет сигнала
    ⚠ [PAIR] Payout 78.0% вне [85, 92]%
    ⏸ [PAIR] Цена близко к сопротивлению

### Ошибка открытия сделки

Причина: недостаточно баланса, лимит PocketOption.

Проверка:

    Ошибка открытия $12.00: ...

Решение:

1. Уменьшить base_percent
2. Пополнить демо-баланс
3. Использовать фиксированные ставки (баланс < $100)

## Vim / SSH проблемы

### Vim не сохраняет файл

Причина: файл открыт только для чтения, или нет прав.

Проверка:

    ls -la file

Решение:

    sudo chown ps4:ps4 file
    vim file

### SSH disconnect во время работы бота

Причина: бот не в screen.

Решение:

    screen -S bot
    source venv/bin/activate
    python analyzer_bot.py
    Ctrl+A, D

Или через nohup:

    nohup python analyzer_bot.py > bot.out 2>&1 &

### Ошибка "screen not found"

Причина: не установлен screen.

Решение:

    sudo apt install -y screen

## Ошибки Python

### ModuleNotFoundError: No module named 'BinaryOptionsToolsV2'

Причина: не активировано виртуальное окружение.

Решение:

    cd ~/bot
    source venv/bin/activate
    python analyzer_bot.py

Проверка:

    which python
    # Должно быть: /home/ps4/bot/venv/bin/python

### SyntaxError при запуске

Причина: ошибка в коде (случайная правка).

Решение:

1. Проверить синтаксис:

       python -c "import ast; ast.parse(open('analyzer_bot.py').read())"

2. Скачать свежую версию:

       cd ~/bot
       git pull

## Логи

### Где логи

    ~/bot/analyzer_bot.log

### Как смотреть в реальном времени

    tail -f ~/bot/analyzer_bot.log

### Файл лога слишком большой

Причина: долгая работа, много сообщений.

Решение:

    > ~/bot/analyzer_bot.log

Команда очистит файл (не удаляя).

## Как полностью переустановить бота

1. Остановить бота:

       touch ~/bot/stop.flag
       # Подождать 30 сек

2. Сохранить SSID и config:

       cp ~/bot/config.json ~/config.json.backup
       cp ~/.po_ssid ~/.po_ssid.backup

3. Удалить:

       rm -rf ~/bot

4. Установить заново:

       cd ~
       git clone https://github.com/murachour/pocketoption-analyzer-bot.git bot
       cd bot
       python3 -m venv venv
       source venv/bin/activate
       pip install -r requirements.txt

5. Восстановить конфиг:

       cp ~/config.json.backup ~/bot/config.json

6. Запустить:

       screen -S bot
       source venv/bin/activate
       export PO_SSID="$(cat ~/.po_ssid)"
       python analyzer_bot.py

## Что делать если ничего не помогает

1. Остановить бота (Ctrl+C в screen)
2. Сохранить лог:

       cp ~/bot/analyzer_bot.log ~/analyzer_bot.log.$(date +%s)

3. Проверить базовое:

       cd ~/bot
       source venv/bin/activate
       export PO_SSID="$(cat ~/.po_ssid)"
       python3 -c "
       import asyncio, os
       from BinaryOptionsToolsV2 import PocketOptionAsync
       async def main():
           async with PocketOptionAsync(ssid=os.getenv('PO_SSID')) as c:
               print('Баланс:', await c.balance())
       asyncio.run(main())
       "

4. Если баланс возвращается — проблема в коде, перезапустить бота
5. Если нет — обновить SSID, попробовать снова

## Когда обращаться за помощью

Собирай информацию:

- Содержимое ~/analyzer_bot.log (последние 100 строк)
- Вывод проверки SSID
- Что делал перед ошибкой

Это поможет быстрее найти проблему.


## Проблемы с локацией

### IP заблокирован PocketOption

Симптомы:

- Таймауты при подключении
- Ошибка Core(ChannelReceiver(Closed))
- Баланс не возвращается
- Свечи не приходят

Причина: IP сервера в стране с ограничениями, или хостер
попал в чёрный список PocketOption.

Решение:

1. Сменить локацию VDS в панели хостера
2. Перезапустить бота
3. Проверить доступ: см. docs/SETUP.md → «Расположение сервера»

Рекомендуемые локации VDS:

- Гонконг (проверено)
- Турция
- Казахстан
- Таиланд
- Сербия

Подробнее — в docs/SETUP.md → «Расположение сервера».

### Долгий пинг до API

Симптомы:

- Медленное получение свечей
- Задержки в серии
- Частые таймауты

Причина: сервер далеко от API PocketOption (Европа), или сеть
медленная.

Решение:

1. Проверить пинг: `ping demo-api-eu.po.market`
2. Сменить локацию VDS (ближе к Европе)
3. Проверить скорость интернета на сервере: `speedtest-cli`
