Пошагово инструкция для развёртывания бота на Debian-based сервере.
Рекомендуется: Ubuntu 24.04.5 LTS (проверено).
## Что делает бот

- 📊 Мульти-таймфрейм анализ: 1м + 3м + 10м
- 🌍 Real-пары (Currency / Forex): OTC + реальные валютные пары
- 💰 Мартингейл: 1% → 2% → 4% (без 4-й ступени)
- 🔄 Ротация пар: смена при 3 пропусках или минусовой серии
- 💹 Payout-фильтр: OTC [85, 92]%, Real [75, 92]%
- 🛡 Защита от просадки: пауза при -30%, стоп после 2-й
- 📰 Пауза при важных новостях (TradingView Calendar)
- ⚙️ Интерактивное меню: 30+ параметров настройки
- 🖥️ Работа через screen: не теряется при обрыве SSH

### Особенности Real-пар

- **Только Currency** (форекс) — крипта исключена
- **Только Пн-Пт** — Forex закрыт в выходные (Сб-Вс)
- **Payout 75-92%** — ниже, чем у OTC
- **Проверка дня** — по часовому поясу `Europe/Moscow`

### Особенности защиты

- **Просадка 30%** — при падении баланса:
  - 1-я просадка → пауза 30 мин
  - 2-я просадка → СТОП (ждём реакции)
- **Пауза при новостях** — за 10 мин до и 20 мин после:
  - High + Medium важность
  - USD, EUR, GBP, JPY
  - TradingView Calendar


## Требования

- **Debian-based дистрибутив:**
  - Ubuntu 24.04.5 LTS (рекомендуется, проверено)
  - Debian 12+ (совместимо)
- Python 3.10+
- Доступ к серверу по SSH
- Аккаунт PocketOption (демо или реальный)
- **VDS в рекомендованной стране** (см. раздел ниже)

## Расположение сервера

Бот работает через API PocketOption. Если IP сервера заблокирован
брокером — бот не сможет подключиться.

### Проверенная локация

**🇭🇰 Гонконг** — проверено в работе: стабильное подключение,
приемлемая цена.

- **Платформа:** HostVDS (OpenStack, NVMe)
- **Стоимость:** ~$4-5/мес
- **Оплата:** карта Мир, СБП, криптовалюта, WebMoney, Alipay
- **IP не раскрывается** (безопасность)

⚠️ Регион Гонконг может быть временно недоступен для заказа VDS.
Проверяй в панели хостера при заказе.

### Рекомендуемые (по опыту сообщества)

- 🇹🇷 Турция
- 🇰🇿 Казахстан
- 🇹🇭 Таиланд
- 🇷🇸 Сербия

Лично не проверялись. Используй как ориентир при выборе VDS.

### Не рекомендуются

Регуляторные ограничения бинарных опционов:

- 🇪🇺 ЕС (ESMA)
- 🇺🇸 США (CFTC)
- 🇬🇧 Великобритания (FCA)
- 🇦🇺 Австралия (ASIC)
- 🇨🇦 Канада
- 🇮🇱 Израиль

Санкционные (могут блокироваться):

- 🇷🇺 Россия
- 🇧🇾 Беларусь
- 🇮🇷 Иран
- 🇰🇵 Северная Корея

### Проверка доступности

Перед установкой бота проверь, что PocketOption доступен с сервера:

    curl -sI https://pocketoption.com | head -3

Ожидаемо: HTTP/2 200 или 302.

    curl -sI https://demo-api-eu.po.market | head -3

Ожидаемо: HTTP/2 403 (это нормально — API требует авторизации).

### Полный тест подключения

После установки зависимостей и получения SSID проверь:

    python3 -c "
    import asyncio, os
    from BinaryOptionsToolsV2 import PocketOptionAsync
    async def main():
        async with PocketOptionAsync(ssid=os.getenv('PO_SSID')) as c:
            bal = await c.balance()
            print(f'✅ Баланс: \${bal:.2f}')
            candles = await c.get_candles('EURUSD_otc', 60, 5)
            print(f'✅ Свечи: {len(candles) if candles else 0}')
    asyncio.run(main())
    "

Если видишь баланс и свечи — локация подходит для работы.

### Что делать если IP заблокирован

Симптомы:

- Таймауты при подключении
- Ошибка Core(ChannelReceiver(Closed))
- Баланс не возвращается
- Свечи не приходят

Решения:

1. Сменить локацию VDS в панели хостера
2. Перезапустить бота
3. Проверить доступ тестом выше

### Важно

- Список рекомендаций основан на опыте сообщества
- PocketOption не публикует официальный список разрешённых стран
- Единственная надёжная проверка — запустить тест с конкретного IP


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
    git clone https://github.com/murashcour/pocketoption-analyzer-bot.git bot
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
