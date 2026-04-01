import httpx
import logging
import re
from typing import Optional
from urllib.parse import urljoin
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Common ASP.NET hidden form fields needed for POST back
VIEWSTATE_REGEX = re.compile(r'__VIEWSTATE\|([^|]+)\|')
VIEWSTATEGENERATOR_REGEX = re.compile(r'__VIEWSTATEGENERATOR\|([^|]+)\|')
EVENTVALIDATION_REGEX = re.compile(r'__EVENTVALIDATION\|([^|]+)\|')


def normalize_semester(semester: str) -> str:
    value = (semester or "").strip().upper()
    mapping = {
        "HK1": "HK01",
        "HK2": "HK02",
        "HK3": "HK03",
    }
    return mapping.get(value, value)


def build_cookie_header(cookie_string: str) -> str:
    return cookie_string.strip()


def extract_hidden_fields(html: str) -> dict:
    fields = {}
    for regex, key in [
        (VIEWSTATE_REGEX, "__VIEWSTATE"),
        (VIEWSTATEGENERATOR_REGEX, "__VIEWSTATEGENERATOR"),
        (EVENTVALIDATION_REGEX, "__EVENTVALIDATION"),
    ]:
        match = regex.search(html)
        if match:
            fields[key] = match.group(1)
    return fields


def fetch_exam_schedule(config: dict) -> Optional[str]:
    cookie = config.get("cookie", "").strip()
    url = config.get("portal_url", "https://portal.huflit.edu.vn/Home/Exam")
    academic_year = config.get("academic_year", "")
    semester = normalize_semester(config.get("semester", ""))

    if not cookie:
        logger.error("Cookie chua duoc cau hinh. Vui long kiem tra config.json")
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cookie": cookie,
        "Referer": url,
    }

    try:
        with httpx.Client(headers=headers, follow_redirects=True, timeout=30.0) as client:
            # Step 1: GET page Exam to ensure authenticated session
            logger.info("Dang lay trang Exam...")
            response = client.get(url)
            if response.status_code != 200:
                logger.error(f"Loi lay trang: HTTP {response.status_code}")
                return None

            html = response.text

            # Step 2: call AJAX endpoint used by ShowExam() in the UI
            show_exam_url = urljoin(url, "/Home/ShowExam")
            ajax_params = {
                "YearStudy": academic_year,
                "TermID": semester,
                "t": f"{time.time():.6f}",
            }
            logger.info(f"Dang goi ShowExam: Nam hoc={academic_year}, Hoc ky={semester}")
            ajax_response = client.get(show_exam_url, params=ajax_params)
            if ajax_response.status_code == 200 and "<table" in ajax_response.text.lower():
                return ajax_response.text

            logger.warning(
                "ShowExam khong tra du lieu hop le (status=%s), thu fallback POST cu",
                ajax_response.status_code,
            )

            # Step 3: fallback old POST flow (for compatibility if portal changes again)
            year_options = re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)</option>', html)
            logger.info(f"Tim thay {len(year_options)} option nam hoc: {year_options}")

            # Build form data for dropdown selection
            hidden_fields = extract_hidden_fields(html)

            form_data = {
                "__EVENTTARGET": "",
                "__EVENTARGUMENT": "",
                "__LASTFOCUS": "",
                **hidden_fields,
                "ddlYearStudy": academic_year,
                "ddlTermID": semester,
            }

            # Step 4: POST back with selected dropdown values
            logger.info(f"Dang lay lich thi: Nam hoc={academic_year}, Hoc ky={semester}")
            post_response = client.post(url, data=form_data)

            if post_response.status_code != 200:
                logger.error(f"Loi POST: HTTP {post_response.status_code}")
                return None

            return post_response.text

    except httpx.TimeoutException:
        logger.error("Request timeout khi lay lich thi")
        return None
    except Exception as e:
        logger.error(f"Loi khong xac dinh: {e}")
        return None


def fetch_exam_schedule_simple(config: dict) -> Optional[str]:
    """
    Fallback: chi GET request, dung khi portal khong can POST form.
    Su dung method nay neu method chinh that bai.
    """
    cookie = config.get("cookie", "").strip()
    url = config.get("portal_url", "https://portal.huflit.edu.vn/Home/Exam")
    show_exam_url = urljoin(url, "/Home/ShowExam")
    academic_year = config.get("academic_year", "")
    semester = normalize_semester(config.get("semester", ""))

    if not cookie:
        logger.error("Cookie chua duoc cau hinh")
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Cookie": cookie,
    }

    try:
        with httpx.Client(headers=headers, follow_redirects=True, timeout=30.0) as client:
            response = client.get(
                show_exam_url,
                params={"YearStudy": academic_year, "TermID": semester, "t": f"{time.time():.6f}"},
            )
            if response.status_code == 200 and "<table" in response.text.lower():
                return response.text
            return None
    except Exception as e:
        logger.error(f"Loi fetch simple: {e}")
        return None
