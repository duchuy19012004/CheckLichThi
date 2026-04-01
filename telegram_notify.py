import json
import logging
import os
from typing import List, Dict

try:
    import telegram
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

from parser import compute_hash, format_exam_message

logger = logging.getLogger(__name__)
STATE_FILE = "state.json"


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Khong doc duoc state.json: {e}")
    return {}


def save_state(state: dict):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Loi ghi state.json: {e}")


def send_telegram_message(token: str, chat_id: str, message: str) -> bool:
    if not TELEGRAM_AVAILABLE:
        logger.error("python-telegram-bot chua duoc cai dat")
        return False

    try:
        bot = telegram.Bot(token=token)
        import asyncio

        async def _send():
            await bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="Markdown",
            )

        asyncio.run(_send())
        logger.info("Gui thong bao Telegram thanh cong")
        return True
    except telegram.error.TelegramError as e:
        logger.error(f"Loi Telegram: {e}")
        return False


def check_and_notify(exams: List[Dict[str, str]], config: dict):
    """
    So sanh lich thi moi voi trang thai cu, gui thong bao neu co thay doi.
    """
    if not exams:
        logger.info("Khong co lich thi de kiem tra")
        return

    new_hash = compute_hash(exams)
    state = load_state()
    old_hash = state.get("exam_hash", "")

    force_notify = bool(config.get("force_notify_every_check", False))

    if new_hash == old_hash and not force_notify:
        logger.info("Lich thi khong thay doi, khong gui thong bao")
        return

    if force_notify:
        logger.info("Dang o che do test: luon gui thong bao moi lan kiem tra")
    else:
        logger.info(f"Phat hien lich thi thay doi! Hash cu: {old_hash[:16]}..., Hash moi: {new_hash[:16]}...")

    # Co thay doi - gui thong bao
    token = config.get("telegram_bot_token", "")
    chat_id = config.get("telegram_chat_id", "")

    if not token or not chat_id:
        logger.error("Telegram token hoac chat_id chua duoc cau hinh")
        return

    message = format_exam_message(
        exams,
        config.get("academic_year", ""),
        config.get("semester", ""),
    )
    if force_notify:
        message = "⚠️ TEST MODE: gui dinh ky moi lan kiem tra\n\n" + message

    if send_telegram_message(token, chat_id, message):
        state["exam_hash"] = new_hash
        save_state(state)
        logger.info("Cap nhat state.json voi hash moi")
