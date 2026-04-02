"""Script debug - kiem tra HTML portal tra ve gi."""
import json
from fetcher import (
    BrowserSessionMissingError,
    SessionExpiredError,
    fetch_exam_schedule_from_browser,
    fetch_exam_schedule_from_session,
)
from parser import parse_exam_html

with open("config.json", encoding="utf-8") as f:
    config = json.load(f)

print("=== Thu lay lich thi bang session app (.auth) ===")
html = None
try:
    html = fetch_exam_schedule_from_session(config)
    print("OK: session app")
except SessionExpiredError as exc:
    print("Session app chua dung duoc:", exc)

if not html:
    print("\n=== Thu fallback browser cookie (Brave -> Chrome -> Edge -> config.cookie) ===")
    try:
        html = fetch_exam_schedule_from_browser(config)
        print("OK: browser/config fallback")
    except BrowserSessionMissingError as exc:
        print("Khong tim thay session browser hop le!")
        print("Chi tiet:", exc)
        exit(1)

if not html:
    print("Khong lay duoc HTML!")
    exit(1)

print(f"Lay duoc HTML: {len(html)} ky tu")

# Luu HTML de xem
with open("debug_output.html", "w", encoding="utf-8") as f:
    f.write(html)
print("Da luu HTML vao debug_output.html")

# Thu parse
exams = parse_exam_html(html)
print(f"\nTim thay {len(exams)} mon thi")
if exams:
    for e in exams[:3]:
        print(" ", e)
else:
    print("Khong co mon thi nao! Kiem tra debug_output.html")
    # Tim cac bang trong HTML
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    print(f"\nCo {len(tables)} bang (<table>) trong HTML:")
    for i, t in enumerate(tables):
        headers = [th.get_text(strip=True) for th in t.find_all("th")]
        rows = t.find_all("tr")
        print(f"  Bang {i+1}: {len(rows)} dong, headers: {headers[:5]}")
