# exchange-spam-notifier

Уведомляет о начавшихся событиях в Microsoft Exchange календаре через нативные уведомления macOS. Повторно напоминает о
событии каждые несколько секунд, пока вы не кликнете на уведомление.

## Как это работает

1. Каждые 30 секунд опрашивает Exchange и ищет текущие события
2. При обнаружении нового события сразу отправляет уведомление
3. Повторяет уведомление каждые 5 секунд, пока вы не кликнете по нему
4. После клика уведомление отключается; завершившиеся события очищаются автоматически

## Требования

- macOS
- Python 3.13+
- [uv](https://github.com/astral-sh/uv)
- [jq](https://stedolan.github.io/jq/)
- [terminal-notifier](https://github.com/julienXX/terminal-notifier)

Установка системных зависимостей:

```bash
brew install jq terminal-notifier
```

## Установка

```bash
git clone https://github.com/artempelyovin/exchange-spam-notifier.git
cd exchange-spam-notifier
uv sync
```

## Настройка

Задайте переменные окружения:

| Переменная        | Описание                                                         |
|-------------------|------------------------------------------------------------------|
| `EXCHANGE_USER`   | Имя пользователя (домен\логин)                                   |
| `EXCHANGE_PASS`   | Пароль                                                           |
| `EXCHANGE_MAIL`   | Email-адрес почтового ящика                                      |
| `EXCHANGE_SERVER` | Адрес Exchange-сервера                                           |
| `EVENTS_DIR`      | Папка для временных файлов (по умолчанию `/tmp/exchange-events`) |

Пример:

```bash
export EXCHANGE_USER="DOMAIN\username"
export EXCHANGE_PASS="secret"
export EXCHANGE_MAIL="user@company.com"
export EXCHANGE_SERVER="mail.company.com"
```

## Запуск (в фоне)

```bash
nohup uv run main.py >> /tmp/exchange-spam-notifier.log 2>&1 &
echo $! > /tmp/exchange-spam-notifier.pid
```

## Остановка

```bash
kill $(cat /tmp/exchange-spam-notifier.pid)
```

## Лицензия

[MIT](LICENSE)