import logging
import re
import time
from typing import Optional
from urllib.parse import urljoin

import httpx

from auth_session import (
    InteractiveLoginError,
    get_session_state_path,
    load_cookie_header_from_storage_state,
)

logger = logging.getLogger(__name__)

VIEWSTATE_REGEX = re.compile(r"__VIEWSTATE\|([^|]+)\|")
VIEWSTATEGENERATOR_REGEX = re.compile(r"__VIEWSTATEGENERATOR\|([^|]+)\|")
EVENTVALIDATION_REGEX = re.compile(r"__EVENTVALIDATION\|([^|]+)\|")

_CACHED_SESSION_COOKIE_HEADER: Optional[str] = None
_CACHED_BROWSER_COOKIE_HEADER: Optional[str] = None
_CACHED_BROWSER_COOKIE_SOURCE: Optional[str] = None


class BrowserSessionMissingError(RuntimeError):
    pass


class SessionExpiredError(RuntimeError):
    pass


def normalize_semester(semester: str) -> str:
    value = (semester or "").strip().upper()
    mapping = {"HK1": "HK01", "HK2": "HK02", "HK3": "HK03"}
    return mapping.get(value, value)


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


def _looks_like_login_page(url: str, html: str) -> bool:
    lowered_url = (url or "").lower()
    lowered_html = (html or "").lower()
    url_markers = ["microsoftonline", "/login", "loginadfs", "signin", "oauth2"]
    html_markers = ["dang nhap", "đăng nhập", "microsoft", "sign in", "loginadfs"]
    return any(marker in lowered_url for marker in url_markers) or any(
        marker in lowered_html for marker in html_markers
    )


def _fetch_with_cookie_header(
    config: dict,
    cookie_header: str,
    auth_error_cls: type[RuntimeError],
) -> Optional[str]:
    url = config.get("portal_url", "https://portal.huflit.edu.vn/Home/Exam")
    academic_year = config.get("academic_year", "")
    semester = normalize_semester(config.get("semester", ""))

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cookie": cookie_header,
        "Referer": url,
    }

    with httpx.Client(headers=headers, follow_redirects=True, timeout=30.0) as client:
        response = client.get(url)
        if response.status_code in (401, 403) or _looks_like_login_page(
            str(response.url), response.text
        ):
            raise auth_error_cls("Session khong hop le hoac da het han.")

        show_exam_url = urljoin(url, "/Home/ShowExam")
        ajax_response = client.get(
            show_exam_url,
            params={"YearStudy": academic_year, "TermID": semester, "t": f"{time.time():.6f}"},
        )
        if ajax_response.status_code in (401, 403) or _looks_like_login_page(
            str(ajax_response.url), ajax_response.text
        ):
            raise auth_error_cls("Session khong hop le hoac da het han.")

        if ajax_response.status_code == 200 and "<table" in ajax_response.text.lower():
            return ajax_response.text

        hidden_fields = extract_hidden_fields(response.text)
        form_data = {
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__LASTFOCUS": "",
            **hidden_fields,
            "ddlYearStudy": academic_year,
            "ddlTermID": semester,
        }
        post_response = client.post(url, data=form_data)
        if post_response.status_code == 200 and "<table" in post_response.text.lower():
            return post_response.text
        return None


def fetch_exam_schedule_from_session(config: dict) -> Optional[str]:
    global _CACHED_SESSION_COOKIE_HEADER

    if _CACHED_SESSION_COOKIE_HEADER:
        try:
            html = _fetch_with_cookie_header(config, _CACHED_SESSION_COOKIE_HEADER, SessionExpiredError)
            if html:
                logger.info("Lay duoc lich thi bang session app cache")
                return html
        except SessionExpiredError:
            _CACHED_SESSION_COOKIE_HEADER = None

    state_path = get_session_state_path(config)
    try:
        cookie_header = load_cookie_header_from_storage_state(
            state_path=state_path,
            domain="portal.huflit.edu.vn",
        )
    except InteractiveLoginError as exc:
        raise SessionExpiredError(str(exc)) from exc

    html = _fetch_with_cookie_header(config, cookie_header, SessionExpiredError)
    if html:
        _CACHED_SESSION_COOKIE_HEADER = cookie_header
    return html


def _get_cookie_header_from_browser(browser_name: str, domain: str) -> Optional[str]:
    try:
        import browser_cookie3
    except Exception as exc:
        raise RuntimeError("Chua cai browser-cookie3. Chay: pip install -r requirements.txt") from exc

    browser = (browser_name or "").strip().lower()
    loaders = {
        "brave": "brave",
        "chrome": "chrome",
        "edge": "edge",
    }
    loader_name = loaders.get(browser)
    if not loader_name:
        return None

    loader = getattr(browser_cookie3, loader_name, None)
    if loader is None:
        raise RuntimeError(f"browser-cookie3 khong ho tro browser: {browser}")

    cookie_jar = loader(domain_name=domain)
    cookie_parts = [f"{c.name}={c.value}" for c in cookie_jar if c.name and c.value is not None]
    if not cookie_parts:
        return None

    return "; ".join(cookie_parts)


def fetch_exam_schedule_from_browser(config: dict) -> Optional[str]:
    global _CACHED_BROWSER_COOKIE_HEADER, _CACHED_BROWSER_COOKIE_SOURCE

    domain = "portal.huflit.edu.vn"
    browser_priority = config.get("browser_priority", ["brave", "chrome", "edge"])
    if not isinstance(browser_priority, list) or not browser_priority:
        browser_priority = ["brave", "chrome", "edge"]

    if _CACHED_BROWSER_COOKIE_HEADER:
        try:
            html = _fetch_with_cookie_header(config, _CACHED_BROWSER_COOKIE_HEADER, BrowserSessionMissingError)
            if html:
                logger.info(
                    "Lay duoc lich thi bang browser cookie cache (%s)",
                    _CACHED_BROWSER_COOKIE_SOURCE or "unknown",
                )
                return html
        except BrowserSessionMissingError:
            _CACHED_BROWSER_COOKIE_HEADER = None
            _CACHED_BROWSER_COOKIE_SOURCE = None

    found_cookie = False
    auth_errors = []
    requires_admin_detected = False

    for browser_name in browser_priority:
        try:
            cookie_header = _get_cookie_header_from_browser(str(browser_name), domain)
        except RuntimeError as exc:
            auth_errors.append(f"{browser_name}: {exc}")
            continue
        except Exception as exc:
            if "requires admin" in str(exc).lower():
                requires_admin_detected = True
            auth_errors.append(f"{browser_name}: loi doc cookie ({exc})")
            continue

        if not cookie_header:
            continue

        found_cookie = True
        try:
            html = _fetch_with_cookie_header(config, cookie_header, BrowserSessionMissingError)
            if html:
                _CACHED_BROWSER_COOKIE_HEADER = cookie_header
                _CACHED_BROWSER_COOKIE_SOURCE = str(browser_name)
                logger.info("Lay duoc lich thi bang session browser: %s", browser_name)
                return html
        except BrowserSessionMissingError as exc:
            auth_errors.append(f"{browser_name}: {exc}")
            continue
        except Exception as exc:
            auth_errors.append(f"{browser_name}: loi khong xac dinh ({exc})")
            continue

    config_cookie = (config.get("cookie") or "").strip()
    if config_cookie:
        try:
            html = _fetch_with_cookie_header(config, config_cookie, BrowserSessionMissingError)
            if html:
                logger.info("Lay duoc lich thi bang config.cookie (fallback cuoi)")
                return html
        except Exception as exc:
            auth_errors.append(f"config.cookie: {exc}")

    if not found_cookie:
        if requires_admin_detected:
            raise BrowserSessionMissingError(
                "Khong the doc cookie browser do file Cookies dang bi khoa "
                "(RequiresAdminError). Thu dong tat het Brave/Chrome/Edge (ke ca process nen) "
                "roi chay lai bot, hoac chay terminal voi quyen Administrator."
            )
        raise BrowserSessionMissingError(
            f"Khong tim thay cookie portal tren browser uu tien {browser_priority}. "
            "Vui long dang nhap portal tren Brave/Chrome/Edge truoc."
        )

    raise BrowserSessionMissingError(
        "Tim thay cookie browser nhung khong su dung duoc. "
        + ("; ".join(auth_errors) if auth_errors else "")
    )

