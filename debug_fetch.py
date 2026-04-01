"""Script debug - kiem tra HTML portal tra ve gi."""
import json
from fetcher import fetch_exam_schedule, fetch_exam_schedule_simple
from parser import parse_exam_html

with open("config.json", encoding="utf-8") as f:
    config = json.load(f)

print("=== Thu POST form ===")
html = fetch_exam_schedule(config)
if html:
    print(f"Lay duoc HTML qua POST: {len(html)} ky tu")
else:
    print("POST that bai, thu GET...")
    html = fetch_exam_schedule_simple(config)
    if html:
        print(f"Lay duoc HTML qua GET: {len(html)} ky tu")
    else:
        print("Khong lay duoc HTML!")
        exit(1)

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
