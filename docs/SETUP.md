# Установка на сервер

Пошаговая инструкция для развёртывания бота на Ubuntu/Debian сервере.

## Требования

- Ubuntu 20.04+ / Debian 11+ / другой Linux
- Python 3.10+
- Доступ к серверу по SSH
- Аккаунт PocketOption (демо или реальный)

## Шаг 1. Системные пакеты

Обновить систему и установить базовые пакеты:

    sudo apt update
    sudo apt install -y python3 python3-pip python3-venv git screen

- python3 — интерпретатор Python
- python3-venv — виртуальное окружение
- git — для клонирования репозитория
- screen — для работы бота в фоне

## Шаг 2. Клонирование репозитория

    cd ~
    git clone https://github.com/murachour/pocketoption-analyzer-bot.git bot
    cd bot

## Шаг 3. Виртуальное окружение

Создать venv и активировать:

    python3 -m venv venv
    source venv/bin/activate

Проверить, что Python в venv:

    which python
    python --version

Должно показать путь внутри venv.

## Шаг 4. Зависимости

    pip install --upgrade pip
    pip install -r requirements.txt

Основная зависимость — BinaryOptionsToolsV2.

## Шаг 5. SSID токен

SSID — токен авторизации в PocketOption. Подробнее в docs/SSID.md.

Кратко:
1. Открыть PocketOption в браузере
2. Залогиниться
3. F12 — Network — WS
4. Найти сообщение 42["auth",...
5. Скопировать целиком

Сохранить SSID в файл:

    echo '42["auth",{...}]' > ~/.po_ssid
    chmod 600 ~/.po_ssid

Проверить:

    python3 -c "
    import json, os
    s = open(os.path.expanduser('~/.po_ssid')).read().strip()
    i = s.find('{'); j = s.rfind('}')
    obj = json.loads(s[i:j+1])
    print(f'SSID валиден, uid={obj[\"uid\"]}')
    "

## Шаг 6. Запуск бота

Запустить в screen (чтобы не терять при обрыве SSH):

    screen -S bot
    source venv/bin/activate
    export PO_SSID="$(cat ~/.po_ssid)"
    python analyzer_bot.py

Отцепиться от screen: Ctrl+A, затем D.

Вернуться к боту: screen -r bot.

## Шаг 7. Остановка бота

Способ 1 — из screen: Ctrl+C

Способ 2 — из другого терминала:

    touch ~/bot/stop.flag

Бот завершит текущую серию и остановится.

## Автозапуск при перезагрузке (опционально)

Если хочешь, чтобы бот стартовал сам:

    crontab -e

Добавить строку:

    @reboot sleep 30 && cd ~/bot && screen -dmS bot bash -c 'source venv/bin/activate && export PO_SSID="$(cat ~/.po_ssid)" && python analyzer_bot.py'

После перезагрузки бот запустится через 30 секунд.

## Обновление бота

Если в репозитории появились изменения:

    cd ~/bot
    git pull
    pip install -r requirements.txt

Перезапустить:

    screen -r bot
    Ctrl+C
    python analyzer_bot.py

## Полезные команды

Проверить, работает ли бот:

    ps aux | grep analyzer_bot | grep -v grep

Посмотреть лог:

    tail -f ~/bot/analyzer_bot.log

Проверить, есть ли stop.flag:

    ls -la ~/bot/stop.flag

Проверить баланс:

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

## Проблемы и решения

См. docs/TROUBLESHOOTING.md.

## Важно

- Не запускай одновременно два экземпляра бота (один SSID — одна сессия)
- Демо-счёт: пополняй виртуальный баланс в интерфейсе PocketOption
- SSID живёт 6-12 часов, при ошибке — обновить
- Логи хранятся в analyzer_bot.log, не удаляй при разборе проблем
