# Как получить SSID

SSID — токен авторизации в PocketOption. Он нужен боту, чтобы
подключиться к API и торговать. Живёт 6-12 часов.

## Что такое SSID

SSID — это строка вида:

    42["auth",{"session":"...","isDemo":1,"uid":12345678,"platform":3,"isFastHistory":true,"isOptimized":true}]

- session — идентификатор сессии
- isDemo — 1 для демо, 0 для реального счёта
- uid — ID пользователя
- platform — платформа

## Способ 1: через Chrome DevTools (универсальный)

1. Открой PocketOption в браузере (Chrome, Firefox, Edge)
2. Залогинься в демо-аккаунт
3. Нажми F12 (DevTools)
4. Перейди на вкладку Network
5. В фильтре выбери WS (WebSocket)
6. Обнови страницу F5
7. Появится соединение к demo-api-eu.po.market или подобное
8. Кликни на него — откроется вкладка Messages (или Frames)
9. Найди исходящее сообщение, начинающееся на 42["auth",
10. Правый клик — Copy message (или выдели и Ctrl+C)

## Способ 2: через SSID-Finder (Linux + VNC)

Если ты на Linux-сервере без GUI, но с VNC:

1. Запусти Xvfb (виртуальный дисплей):
       Xvfb :99 -screen 0 1280x800x24 &
       export DISPLAY=:99

2. Запусти x11vnc:
       x11vnc -display :99 -forever -nopw -rfbport 5905 &

3. Подключись через VNC-клиент к серверу:5905

4. Внутри VNC открой Chrome — зайди на pocketoption.com

5. Установи расширение SSID-Finder или запусти отдельное приложение

6. Залогинься в PocketOption — SSID-Finder покажет текущий SSID

## ВАЖНО: частая ошибка с кавычкой

При копировании SSID из DevTools легко захватить лишний символ.

Проверь строку после uid:

Правильно:

    "uid":94604880,"platform":3
                ^
                запятая, без кавычки

Неправильно (лишняя кавычка после числа):

    "uid":94604880","platform":3
                 ^
                 лишняя кавычка

Если увидишь такую ошибку — бот упадёт с:

    PocketOptionError: Failed to parse ssid: JSON parsing error

Просто убери лишнюю кавычку.

## Как сохранить SSID

Способ 1 — переменная окружения (одноразово):

    export PO_SSID='42["auth",{...}]'

Способ 2 — файл (постоянно):

    echo '42["auth",{...}]' > ~/.po_ssid
    chmod 600 ~/.po_ssid

Потом при запуске:

    export PO_SSID="$(cat ~/.po_ssid)"

## Проверка SSID

Перед запуском бота проверь SSID:

    python3 -c "
    import json, os
    s = os.getenv('PO_SSID', '')
    if not s:
        s = open(os.path.expanduser('~/.po_ssid')).read().strip()
    i = s.find('{'); j = s.rfind('}')
    obj = json.loads(s[i:j+1])
    print(f'SSID валиден')
    print(f'  uid: {obj[\"uid\"]}')
    print(f'  isDemo: {obj[\"isDemo\"]}')
    "

Должно вывести uid и isDemo без ошибок.

## Полная проверка подключения

Проверить, что SSID работает и API отвечает:

    python3 -c "
    import asyncio, os
    from BinaryOptionsToolsV2 import PocketOptionAsync

    async def main():
        async with PocketOptionAsync(ssid=os.getenv('PO_SSID')) as c:
            bal = await c.balance()
            print(f'Баланс: \${bal:.2f}')
            candles = await c.get_candles('EURUSD_otc', 60, 5)
            print(f'Свечи: {len(candles) if candles else 0}')

    asyncio.run(main())
    "

Если увидишь баланс и свечи — всё работает.

## Когда SSID умирает

SSID инвалидируется:

- Через 6-12 часов после получения
- После смены пароля
- После выхода из аккаунта в браузере
- После входа с другого устройства/IP

Признаки:

- Ошибка Core(ChannelReceiver(Closed))
- Таймауты при получении свечей
- Баланс не возвращается

Решение: получить SSID заново (см. выше).

## Демо vs реальный счёт

В SSID есть поле isDemo:

- isDemo: 1 — демо-счёт (безопасно, для тестов)
- isDemo: 0 — реальный счёт (реальные деньги!)

Для тестирования бота всегда используй демо (isDemo: 1).

## Безопасность

SSID = полный доступ к аккаунту. Никогда не публикуй его:

- Не коммить в git
- Не отправляй в чатах
- Не публикуй в скриншотах
- Храни только в ~/.po_ssid (chmod 600)

Если SSID утёк — смени пароль PocketOption и получи новый SSID.
