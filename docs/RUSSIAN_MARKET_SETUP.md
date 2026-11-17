# Запуск российского рынка

## Локальное приложение

Нужны Python 3.12 и Node.js 22/24. Из корня проекта:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt pytest pytest-timeout flake8
npm ci --prefix apps/dsa-web --registry=https://registry.npmjs.org --replace-registry-host=always
npm run build --prefix apps/dsa-web
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

Откройте локальный адрес `http://127.0.0.1:8000/moex`. Исходный интерфейс иностранных
рынков остаётся на `/`. Проверка API: `GET /api/health` и `GET /api/v1/moex/market`.
Порт можно изменить. В облачной среде рабочая папка `/workspace/MOEXinvest`,
используйте существующую копию; каждая задача изолирована, worktree создавать не нужно.

Для личной конфигурации создайте `.env` по `.env.example`, не заменяя уже существующий файл.
Ключи вводите локально или в защищённых настройках среды, никогда не коммитьте их.
Для аутентификации задайте `ADMIN_AUTH_ENABLED=true`, перезапустите сервер и установите
пароль при первом входе через локальное соединение. Для внешнего размещения необходимы
настроенная аутентификация и HTTPS. Публичная демонстрация не обращается к приватному API.

В Windows активация: `.venv\Scripts\activate`. Остальные команды аналогичны.
`replace-registry-host=always` использует официальный npm registry вместо зеркала из
исходного lockfile, сохраняя версии, integrity и TLS-проверку.

## Настройки и данные

- Начальный список: `config/moex_watchlist.json`; SBER, YDEX, X5, IMOEX и ОФЗ 26248/26243/26247.
- Раздел «Настройки» сохраняет изменения в `data/moex_watchlist.json`.
- `MOEX_WATCHLIST_PATH`: необязательный альтернативный путь списка.
- `DATABASE_PATH`: существующая SQLite-база портфеля, по умолчанию `data/stock_analysis.db`.
- `MOEX_REPORTS_DIR`: каталог локальных отчётов, по умолчанию `reports/moex`.
- `MOEX_ENABLE_AI=false`: включайте только после настройки существующего поддерживаемого LLM-провайдера.
- `MOEX_TELEGRAM_USER_IDS`: список числовых user ID через запятую. Пустой список запрещает все команды.

Сохраняйте резервные копии `data/`, `.env` и `reports/` в защищённом хранилище. Файлы и
зависимости сохраняются в опубликованном снимке облачной среды, процессы запускаются заново.
Python requirements содержит диапазоны версий, frontend устанавливается по lockfile.

## Telegram

Используются существующие `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID`. Для команд дополнительно
задайте `MOEX_TELEGRAM_USER_IDS`, затем:

```bash
python -m bot.platforms.moex_telegram
```

Доступны `/help`, `/portfolio`, `/market`, `/stock SBER`, `/bond 26248`, `/news`, `/risk`.
Чтение портфеля разрешено только user ID из списка в личном чате; группы отклоняются.
Один allowlist относится к одному личному портфелю, это не многопользовательский сервис.
Polling требует постоянно работающего процесса; ежедневные отчёты могут работать без VPS.

```bash
python scripts/moex_report.py --period morning
python scripts/moex_report.py --period evening --send
```

Без `--send` сообщение не отправляется. `--ai` включает существующий LLM-клиент и может
расходовать средства провайдера. Текущие отчёты CLI содержат публичный рынок; личные
данные доступны через защищённый портфель и Telegram-команды. Отправку реальным токеном
нужно проверить после его безопасной настройки: в среде разработки токена нет.

## GitHub Actions и Pages

Workflow `MOEX public dashboard` собирает публичный интерфейс, получает официальные данные
и публикует их через GitHub Pages. В Settings → Pages выберите GitHub Actions.
Ручной запуск: Actions → MOEX public dashboard → Run workflow.
Автообновление: 06:15 и 16:15 UTC (09:15 и 19:15 Москвы). Actions может запускаться позже.
Если все источники недоступны, сборка не публикует выдуманный или пустой снимок.
Если часть источников недоступна, интерфейс показывает ошибки и доступные данные.

`MOEX daily report` запускается утром и вечером, включая выходные: отчёт использует последние
доступные котировки с их временными метками, а не считает каждый будний день торговым.
Для доставки добавьте GitHub Secrets `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
Плановая доставка включается только repository variable `MOEX_SCHEDULE_SEND=true`;
для ручного запуска есть флаг `send`.

**История этого workflow публична:** отчёты о рынке и маркеры доставки хранятся в отдельной
ветке `moex-report-history`. Личный портфель и секреты туда не передаются. Артефакты на 90 дней
служат дополнительной копией. Доставка не может гарантировать exactly-once при аварии между
Telegram и записью маркера; при повторном запуске проверяйте последнее сообщение.
Для личного портфеля используйте постоянный диск локального приложения/VPS, а не Pages или
одноразовую файловую систему Actions.

## Docker

```bash
docker compose -f docker/docker-compose.moex.yml up -d --build server
docker compose -f docker/docker-compose.moex.yml --profile telegram up -d --build
```

Перед запуском подготовьте `.env`. Compose использует Europe/Moscow, аутентификацию и
привязку порта только к loopback. Данные и отчёты монтируются с постоянного диска.
Docker-образ собран в облачной среде. При сборке за корпоративным TLS-прокси
сертификат среды передавался временным BuildKit secret; в образ и репозиторий он не включён.
Проверены запуск API, WebUI и отказ 401 для личного портфеля без входа.
Переменная `ADMIN_AUTH_ENABLED` учитывается и без файла `.env` внутри контейнера;
если файл существует и содержит этот параметр, его значение имеет приоритет для совместимости
с редактированием настроек через существующий API.

## Проверки

```bash
python -m pytest tests/test_moex.py -m 'not network' --timeout=60
python -m pytest tests/test_moex.py -m network --timeout=90
./scripts/ci_gate.sh syntax
./scripts/ci_gate.sh flake8
./scripts/ci_gate.sh deterministic
npm run lint --prefix apps/dsa-web
npm run build --prefix apps/dsa-web
```

Для исходных тестов портфеля в ограниченной сети задавайте `ENABLE_REALTIME_QUOTE=false`:
один upstream-тест запрашивает китайские котировки до проверки неоднозначности счёта.
Сетевые тесты MOEX выполняются отдельно и не заменяются offline-проверками.
