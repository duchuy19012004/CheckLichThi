import argparse
import json
import logging
import sys
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from auth_session import (
    InteractiveLoginError,
    InteractiveLoginTimeoutError,
    login_and_save_session,
)
from fetcher import (
    BrowserSessionMissingError,
    SessionExpiredError,
    fetch_exam_schedule_from_browser,
    fetch_exam_schedule_from_session,
)
from parser import parse_exam_html
from telegram_notify import check_and_notify, send_auth_required_alert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

CONFIG_FILE = "config.json"
LAST_AUTH_ALERT_TS = 0.0


def load_config() -> dict:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("Khong tim thay %s. Vui long tao cau hinh.", CONFIG_FILE)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        logger.error("Loi doc JSON: %s", exc)
        sys.exit(1)


def _maybe_send_auth_alert(config: dict, reason: str):
    global LAST_AUTH_ALERT_TS
    cooldown_minutes = int(config.get("auth_alert_cooldown_minutes", 60))
    now_ts = time.time()
    elapsed = now_ts - LAST_AUTH_ALERT_TS
    required = cooldown_minutes * 60

    if LAST_AUTH_ALERT_TS == 0 or elapsed >= required:
        send_auth_required_alert(config, reason)
        LAST_AUTH_ALERT_TS = now_ts
        return

    remaining = int(required - elapsed)
    logger.info("Bo qua canh bao auth do dang trong cooldown (%ss con lai)", remaining)


def _run_interactive_login(config: dict, reason: str = "") -> bool:
    if reason:
        logger.info("Can dang nhap lai: %s", reason)

    try:
        login_and_save_session(config)
        return True
    except InteractiveLoginTimeoutError as exc:
        logger.error("Dang nhap interactive bi timeout: %s", exc)
        return False
    except InteractiveLoginError as exc:
        logger.error("Dang nhap interactive that bai: %s", exc)
        return False
    except Exception as exc:
        logger.error("Loi khong xac dinh khi dang nhap interactive: %s", exc)
        return False


def _fetch_with_auto_reauth(config: dict) -> str | None:
    try:
        return fetch_exam_schedule_from_session(config)
    except SessionExpiredError as exc:
        logger.warning("Session app het han/khong hop le: %s", exc)

    if _run_interactive_login(config, "Session app khong hop le, mo login de lam moi."):
        try:
            return fetch_exam_schedule_from_session(config)
        except SessionExpiredError as retry_exc:
            logger.error("Da login lai nhung session van khong dung duoc: %s", retry_exc)
        except Exception as retry_exc:
            logger.error("Loi fetch sau khi login lai: %s", retry_exc)

    try:
        return fetch_exam_schedule_from_browser(config)
    except BrowserSessionMissingError as browser_exc:
        logger.error(str(browser_exc))
        _maybe_send_auth_alert(config, str(browser_exc))
        return None
    except Exception as exc:
        logger.error("Loi fallback browser/config.cookie: %s", exc)
        return None


def check_schedule_job():
    logger.info("=== Bat dau kiem tra lich thi ===")
    config = load_config()

    html = _fetch_with_auto_reauth(config)
    if not html:
        return

    exams = parse_exam_html(html)
    check_and_notify(exams, config)
    logger.info("=== Ket thuc kiem tra lich thi ===")


def _bootstrap_auth_for_run(config: dict):
    try:
        fetch_exam_schedule_from_session(config)
        logger.info("Session app hop le, khong can mo login.")
        return
    except SessionExpiredError as exc:
        logger.info("Session app chua san sang: %s", exc)

    success = _run_interactive_login(config, "Khoi dong run lan dau can xac thuc session.")
    if not success:
        logger.warning(
            "Khong login duoc luc khoi dong. Bot van chay va se thu fallback browser/config.cookie trong tung luot check."
        )


def run_mode():
    config = load_config()
    interval = config.get("check_interval_minutes", 15)

    logger.info("Khoi dong bot - kiem tra lich thi moi %s phut/lan", interval)
    logger.info("Nam hoc: %s, Hoc ky: %s", config.get("academic_year"), config.get("semester"))

    _bootstrap_auth_for_run(config)

    scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
    scheduler.add_job(
        check_schedule_job,
        trigger=IntervalTrigger(minutes=interval),
        id="check_exam",
        name="Kiem tra lich thi",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Bot da khoi dong. Nhan Ctrl+C de dung.")

    try:
        check_schedule_job()
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Dang dung bot...")
        scheduler.shutdown()
        logger.info("Bot da dung.")


def login_mode():
    config = load_config()
    ok = _run_interactive_login(config, "Ban da chon lenh login thu cong.")
    if not ok:
        sys.exit(1)
    logger.info("Dang nhap thanh cong, session da duoc luu.")


def parse_args():
    parser = argparse.ArgumentParser(description="HUFLIT exam schedule bot")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="Chay bot dinh ky (tu auto-login neu can)")
    sub.add_parser("login", help="Dang nhap Microsoft va luu session thu cong")
    return parser.parse_args()


def main():
    args = parse_args()
    command = args.command or "run"

    if command == "run":
        run_mode()
        return
    if command == "login":
        login_mode()
        return

    logger.error("Lenh khong ho tro: %s", command)
    sys.exit(2)


if __name__ == "__main__":
    main()

