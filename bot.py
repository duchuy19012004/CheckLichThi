import json
import logging
import sys
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from fetcher import fetch_exam_schedule, fetch_exam_schedule_simple
from parser import parse_exam_html
from telegram_notify import check_and_notify

# Cau hinh logging
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


def load_config() -> dict:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Khong tim thay {CONFIG_FILE}. Vui long tao cau hinh.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Loi doc JSON: {e}")
        sys.exit(1)


def check_schedule_job():
    """Job chinh - chay dinh ky kiem tra lich thi."""
    logger.info("=== Bat dau kiem tra lich thi ===")
    config = load_config()

    # Thu fetch voi POST form
    html = fetch_exam_schedule(config)

    # Neu that bai, thu fallback GET
    if not html:
        logger.info("Thu cach fetch don gian...")
        html = fetch_exam_schedule_simple(config)

    if not html:
        logger.error("Khong lay duoc HTML tu portal")
        return

    exams = parse_exam_html(html)
    check_and_notify(exams, config)
    logger.info("=== Ket thuc kiem tra lich thi ===")


def main():
    config = load_config()
    interval = config.get("check_interval_minutes", 15)

    logger.info(f"Khoi dong bot - kiem tra lich thi moi {interval} phut/lan")
    logger.info(f"Nam hoc: {config.get('academic_year')}, Hoc ky: {config.get('semester')}")

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
        # Kiem tra ngay lap tuc lan dau
        check_schedule_job()
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Dang dung bot...")
        scheduler.shutdown()
        logger.info("Bot da dung.")


if __name__ == "__main__":
    main()
