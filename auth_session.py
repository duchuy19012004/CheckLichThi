import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DEFAULT_SESSION_STATE_PATH = ".auth/huflit_state.json"
DEFAULT_LOCAL_CHROME_PROFILE = ".auth/chrome-profile"


class InteractiveLoginError(RuntimeError):
    pass


class InteractiveLoginTimeoutError(InteractiveLoginError):
    pass


def get_session_state_path(config: dict) -> Path:
    raw_path = (config.get("session_state_path") or DEFAULT_SESSION_STATE_PATH).strip()
    if not raw_path:
        raw_path = DEFAULT_SESSION_STATE_PATH
    return Path(raw_path)


def get_playwright_user_data_dir(config: dict) -> Path:
    configured = (config.get("playwright_user_data_dir") or "").strip()
    if configured:
        return Path(configured)

    fallback = Path(DEFAULT_LOCAL_CHROME_PROFILE)
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _is_home_url(url: str) -> bool:
    try:
        parsed = urlparse(url or "")
    except Exception:
        return False
    path = (parsed.path or "").lower().rstrip("/")
    return path == "/home" or path.startswith("/home/")


def login_and_save_session(config: dict) -> Path:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise InteractiveLoginError(
            "Chua cai playwright. Chay: pip install -r requirements.txt && playwright install chromium"
        ) from exc

    portal_url = config.get("portal_url", "https://portal.huflit.edu.vn/Home/Exam")
    timeout_seconds = int(config.get("interactive_login_timeout_seconds", 300))
    state_path = get_session_state_path(config)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    preferred_profile_dir = get_playwright_user_data_dir(config)
    fallback_profile_dir = Path(DEFAULT_LOCAL_CHROME_PROFILE)
    fallback_profile_dir.mkdir(parents=True, exist_ok=True)
    profile_directory_name = (config.get("playwright_profile_directory") or "Default").strip() or "Default"

    logger.info(
        "Mo Chrome (khong rieng tu) de dang nhap Microsoft. user_data_dir=%s, profile=%s",
        preferred_profile_dir,
        profile_directory_name,
    )

    with sync_playwright() as p:
        chrome_exe = os.environ.get("PROGRAMFILES", "")
        chrome_path = Path(chrome_exe) / "Google" / "Chrome" / "Application" / "chrome.exe"
        browser_locator = {}
        if chrome_path.exists():
            browser_locator["executable_path"] = str(chrome_path)
        else:
            browser_locator["channel"] = "chrome"

        def _launch_context(candidate_profile_dir: Path):
            launch_kwargs = {
                "user_data_dir": str(candidate_profile_dir),
                "headless": False,
                "args": [f"--profile-directory={profile_directory_name}"],
                **browser_locator,
            }
            return p.chromium.launch_persistent_context(**launch_kwargs)

        launch_error = None
        context = None
        actual_profile_dir = None
        for candidate_profile_dir in [preferred_profile_dir, fallback_profile_dir]:
            try:
                context = _launch_context(candidate_profile_dir)
                actual_profile_dir = candidate_profile_dir
                break
            except PlaywrightError as exc:
                launch_error = exc
                if candidate_profile_dir == preferred_profile_dir and preferred_profile_dir != fallback_profile_dir:
                    logger.warning(
                        "Khong mo duoc profile Chrome he thong (%s). Thu fallback profile local: %s",
                        preferred_profile_dir,
                        fallback_profile_dir,
                    )
                    continue
                raise InteractiveLoginError(f"Khong the mo Chrome profile: {exc}") from exc

        if not context:
            raise InteractiveLoginError(f"Khong the mo Chrome profile: {launch_error}")

        if actual_profile_dir and actual_profile_dir != preferred_profile_dir:
            logger.info("Da fallback sang profile local: %s", actual_profile_dir)

        page = context.new_page()

        def _goto_portal(target_page) -> bool:
            try:
                target_page.goto(portal_url, wait_until="domcontentloaded", timeout=30000)
                return True
            except PlaywrightTimeoutError:
                return False

        navigated = _goto_portal(page)
        if not navigated:
            logger.warning("Timeout khi mo portal, thu dieu huong lai mot lan.")
            try:
                page.goto(portal_url, wait_until="load", timeout=30000)
                navigated = True
            except PlaywrightTimeoutError:
                logger.warning("Van timeout khi mo portal, cho user thao tac thu cong.")

        if (
            not navigated
            and actual_profile_dir == preferred_profile_dir
            and preferred_profile_dir != fallback_profile_dir
        ):
            urls = []
            for opened_page in context.pages:
                try:
                    urls.append(opened_page.url)
                except Exception:
                    continue
            if urls and all((u or "").startswith("about:blank") for u in urls):
                logger.warning(
                    "Profile he thong dang ket o about:blank. Thu fallback profile local: %s",
                    fallback_profile_dir,
                )
                try:
                    context.close()
                except Exception:
                    pass
                context = _launch_context(fallback_profile_dir)
                actual_profile_dir = fallback_profile_dir
                page = context.new_page()
                navigated = _goto_portal(page)
                if not navigated:
                    try:
                        page.goto(portal_url, wait_until="load", timeout=30000)
                        navigated = True
                    except PlaywrightTimeoutError:
                        logger.warning("Fallback profile local van timeout khi mo portal.")

        deadline = time.time() + max(30, timeout_seconds)
        retried_from_blank = False

        while time.time() < deadline:
            urls = []
            for opened_page in context.pages:
                try:
                    urls.append(opened_page.url)
                except Exception:
                    continue

            if any(_is_home_url(current_url) for current_url in urls):
                context.storage_state(path=str(state_path))
                logger.info("Da luu session vao: %s", state_path)
                context.close()
                return state_path

            if (
                not retried_from_blank
                and urls
                and all((u or "").startswith("about:blank") for u in urls)
            ):
                retried_from_blank = True
                logger.info("Dang o about:blank, thu mo lai portal.")
                try:
                    fresh_page = context.new_page()
                    fresh_page.goto(portal_url, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass

            page.wait_for_timeout(1000)

        context.close()

    raise InteractiveLoginTimeoutError(
        f"Qua thoi gian cho dang nhap ({timeout_seconds}s). Chua vao duoc /Home."
    )


def _cookie_domain_matches(cookie_domain: str, target_domain: str) -> bool:
    normalized = (cookie_domain or "").lstrip(".").lower()
    target = (target_domain or "").lower()
    if not normalized or not target:
        return False
    if normalized == target:
        return True
    return target.endswith(f".{normalized}") or normalized.endswith(f".{target}")


def load_cookie_header_from_storage_state(state_path: Path, domain: str) -> str:
    if not state_path.exists():
        raise InteractiveLoginError(f"Khong tim thay file session: {state_path}")

    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise InteractiveLoginError(f"Khong doc duoc session state: {exc}") from exc

    cookies = data.get("cookies", [])
    if not isinstance(cookies, list):
        raise InteractiveLoginError("File session state khong hop le (cookies).")

    now_ts = time.time()
    cookie_parts = []
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        name = cookie.get("name")
        value = cookie.get("value")
        cookie_domain = cookie.get("domain", "")
        expires = cookie.get("expires", -1)
        if not name or value is None:
            continue
        if not _cookie_domain_matches(cookie_domain, domain):
            continue
        if isinstance(expires, (int, float)) and expires > 0 and expires <= now_ts:
            continue
        cookie_parts.append(f"{name}={value}")

    if not cookie_parts:
        raise InteractiveLoginError(
            f"Khong tim thay cookie hop le cho domain {domain} trong session state."
        )

    return "; ".join(cookie_parts)
