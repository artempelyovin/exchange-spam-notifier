import asyncio
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from exchangelib import DELEGATE, NTLM, Account, Configuration, Credentials

# ==================== НАСТРОЙКИ ====================
EXCHANGE_USER = os.getenv("EXCHANGE_USER")
EXCHANGE_PASS = os.getenv("EXCHANGE_PASS")
EXCHANGE_MAIL = os.getenv("EXCHANGE_MAIL")
EXCHANGE_SERVER = os.getenv("EXCHANGE_SERVER")

TIMEZONE = ZoneInfo("Europe/Moscow")

EVENTS_DIR = os.getenv("EVENTS_DIR", "/tmp/exchange-events")
CHECK_INTERVAL = 5  # секунды между проверками календаря
SPAM_INTERVAL = 2  # секунды между спам-сообщениями
GRACE_MINUTES = 2  # считать событие "начавшимся", если оно началось не раньше N минут назад
CLEAN_INTERVAL = 60  # секунды между очистками файлов завершившихся событий
# ===================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

credentials = Credentials(username=EXCHANGE_USER, password=EXCHANGE_PASS)
config = Configuration(server=EXCHANGE_SERVER, credentials=credentials, auth_type=NTLM)
account = Account(
    primary_smtp_address=EXCHANGE_MAIL,
    config=config,
    autodiscover=False,
    access_type=DELEGATE,
)


@dataclass(frozen=True)
class Event:
    uid: str
    subject: str
    start: datetime
    end: datetime
    disable: bool = False


lock = asyncio.Lock()


def fetch_started_events() -> list[Event]:
    """
    Синхронная функция. Спрашивает Exchange о событиях,
    которые начались недавно и ещё идут.
    """
    now = datetime.now(tz=TIMEZONE)
    window_start = now - timedelta(minutes=GRACE_MINUTES)
    window_end = now + timedelta(minutes=1)

    found = []
    try:
        for item in account.calendar.view(start=window_start, end=window_end):
            item_start = item.start.astimezone(TIMEZONE)
            item_end = item.end.astimezone(TIMEZONE)

            if item_start <= now <= item_end:
                uid = getattr(item, "uid", None) or str(item.id)
                found.append(
                    Event(
                        uid=uid,
                        subject=str(item.subject or "Без названия"),
                        start=datetime.fromisoformat(item_start.isoformat()),
                        end=datetime.fromisoformat(item_end.isoformat()),
                    )
                )
    except Exception as e:
        logger.error(f"Ошибка при запросе к Exchange: {e}")

    return found


def save_event(ev: Event) -> None:
    def encode(o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        raise TypeError

    content = json.dumps(asdict(ev), default=encode, indent=4)
    path = Path(f"{EVENTS_DIR}/{ev.uid}.json")
    path.write_text(content, encoding="utf-8")
    logger.info(f"Создан новый файл события: {path.absolute()}")


def get_all_events() -> list[Event]:
    dir_path = Path(EVENTS_DIR)
    events = []
    for path in dir_path.iterdir():
        if path.is_file() and path.suffix == ".json":
            try:
                content = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.exception(f"Не удалось прочитать {path.absolute()}:")
                continue
            events.append(
                Event(
                    uid=content["uid"],
                    subject=content["subject"],
                    start=datetime.fromisoformat(content["start"]),
                    end=datetime.fromisoformat(content["end"]),
                    disable=content["disable"],
                )
            )
    return events


async def calendar_poller():
    """Бесконечно проверяет календарь и добавляет новые события в {EVENTS_DIR}/{event.uid}.json"""
    while True:
        try:
            actual_events = await asyncio.to_thread(fetch_started_events)
            know_uids = {ev.uid for ev in get_all_events()}
            unknown_events = [ev for ev in actual_events if ev.uid not in know_uids]
            for ev in unknown_events:
                save_event(ev)
                logger.info(
                    f"Началось событие: {ev.subject} ({ev.start.strftime('%H:%M')} - {ev.end.strftime('%H:%M')})"
                )
                await _send_spam(ev)  # уведомляем сразу, не ждём SPAM_INTERVAL
        except Exception:
            logger.exception(f"Ошибка в calendar_poller:")

        await asyncio.sleep(CHECK_INTERVAL)


async def _send_spam(event: Event):
    """Отправляет одно спам-сообщение."""
    path = Path(EVENTS_DIR) / f"{event.uid}.json"
    tmp_path = Path(EVENTS_DIR) / f"{event.uid}.tmp"
    process = await asyncio.create_subprocess_exec(
        "terminal-notifier",
        "-title",
        event.subject,
        "-message",
        f"⏰ {event.start.strftime('%H:%M')} — {event.end.strftime('%H:%M')}",
        "-sound",
        "glass",
        "-execute",
        f"jq '.disable = true' {path} > {tmp_path} && mv {tmp_path} {path}",
    )
    await process.wait()


async def spam_loop():
    """Бесконечно шлёт повторные уведомления по активным событиям."""
    while True:
        await asyncio.sleep(SPAM_INTERVAL)

        know_events = await asyncio.to_thread(get_all_events)

        for ev in know_events:
            if not ev.disable:
                await _send_spam(ev)


async def cleaner_loop():
    """Фоновая очистка JSON-файлов событий, которые уже завершились."""
    while True:
        await asyncio.sleep(CLEAN_INTERVAL)
        now = datetime.now(tz=TIMEZONE)
        dir_path = Path(EVENTS_DIR)
        for path in dir_path.glob("*.json"):
            try:
                content = json.loads(path.read_text(encoding="utf-8"))
                end = datetime.fromisoformat(content["end"])
                if end < now:
                    path.unlink()
                    logger.info(f"Удалён файл завершённого события: {path.absolute()}")
            except Exception:
                logger.exception(f"Ошибка при очистке {path.absolute()}:")


async def main():
    logger.info("Exchange Spam Notifier запущен")

    dir_path = Path(EVENTS_DIR)
    dir_path.mkdir(parents=True, exist_ok=True)
    for path in dir_path.iterdir():
        if path.is_file() and path.suffix == ".json":
            path.unlink()
            logger.info(f"Удалён старый файл события: {path.absolute()}")

    await asyncio.gather(
        calendar_poller(),
        spam_loop(),
        cleaner_loop(),
    )


if __name__ == "__main__":
    asyncio.run(main())
