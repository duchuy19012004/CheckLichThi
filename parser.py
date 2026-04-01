import hashlib
import logging
import textwrap
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def parse_exam_html(html: str) -> List[Dict[str, str]]:
    """
    Parse HTML tu trang Exam, trich xuat bang lich thi.
    Tra ve list cac dict, moi dict la 1 dong lich thi.
    """
    from bs4 import BeautifulSoup

    exams = []
    try:
        soup = BeautifulSoup(html, "lxml")

        # Tim bang lich thi - thuong nam trong div#MainContent hoac table class chua "exam"
        table = soup.find("table", {"id": lambda x: x and "Exam" in str(x)})
        if not table:
            table = soup.find("table", {"class": lambda x: x and "table" in str(x).lower()})
        if not table:
            # Thu tim bat ky table nao co header tuong ung
            tables = soup.find_all("table")
            for t in tables:
                headers = [th.get_text(strip=True) for th in t.find_all("th")]
                if any("Ngày" in h or "Môn" in h for h in headers):
                    table = t
                    break

        if not table:
            logger.warning("Khong tim thay bang lich thi trong HTML")
            return []

        # Doc header
        header_row = table.find("thead")
        if header_row:
            headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]
        else:
            first_row = table.find("tr")
            headers = [td.get_text(strip=True) for td in first_row.find_all(["th", "td"])]

        # Doc body
        rows = table.find_all("tr")[1:]  # Bo header row
        for row in rows:
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if not cells or all(c == "" for c in cells):
                continue
            record = dict(zip(headers, cells))
            # Portal tra thong bao 1 dong khi chua co lich thi.
            if len(record) == 1:
                only_value = next(iter(record.values()), "").strip().lower()
                if "chưa có lịch thi" in only_value or "chua co lich thi" in only_value:
                    logger.info("Portal thong bao chua co lich thi")
                    return []
            exams.append(record)

        logger.info(f"Tim thay {len(exams)} dong lich thi")

    except Exception as e:
        logger.error(f"Loi parse HTML: {e}")

    return exams


def compute_hash(exams: List[Dict[str, str]]) -> str:
    """Tinh hash cua danh sach lich thi de so sanh thay doi."""
    if not exams:
        return hashlib.sha256(b"").hexdigest()

    # Sort de dam bao thu tu nhat quan
    content = str(sorted(exams, key=lambda x: str(x)))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def format_exam_message(exams: List[Dict[str, str]], academic_year: str, semester: str) -> str:
    """Format danh sach lich thi thanh message Telegram."""
    if not exams:
        return f"📋 *Lich thi - {academic_year} - {semester}*\n\nKhong co lich thi nao."

    def pick(record: Dict[str, str], keys: List[str]) -> str:
        for key in keys:
            value = record.get(key, "")
            if value:
                return value
        return ""

    lines = [
        f"📋 *Lich thi - {academic_year} - {semester}*",
        f"Tong cong: {len(exams)} mon\n",
    ]

    lines.append("```")
    mon_width = 30
    lines.append(
        f"{'Ngay Thi':10} | {'Gio':5} | {'Mon Thi':{mon_width}} | {'Phong':8} | {'TL':3} | {'Dia diem':14} |"
    )
    lines.append("-" * (56 + mon_width))

    for exam in exams:
        ngay = pick(exam, ["Ngày Thi", "Ngày thi", "NgayThi", "Ngay thi"])
        gio = pick(exam, ["Giờ Thi", "Giờ thi", "GioThi", "Gio thi"])
        mon = pick(exam, ["Môn Thi", "Môn thi", "MonThi", "Mon thi", "Tên học phần", "Ten hoc phan"])
        phong = pick(exam, ["Phòng Thi", "Phòng thi", "PhongThi", "Phong thi"])
        thoiluong = pick(exam, ["Thời lượng (phút)", "Thoi luong (phut)", "Thời lượng", "Thoi luong"])
        diadiem = pick(exam, ["Địa điểm", "Dia diem"])
        hinhthuc = pick(exam, ["Hình Thức", "Hình thức", "HinhThuc"])
        ghichu = pick(exam, ["Ghi Chú", "Ghi chú", "GhiChu"])

        mon_lines = textwrap.wrap(mon, width=mon_width) or [""]
        lines.append(
            f"{ngay[:10]:10} | {gio[:5]:5} | {mon_lines[0]:{mon_width}} | {phong[:8]:8} | {thoiluong[:3]:3} | {diadiem[:14]:14} |"
        )
        for extra in mon_lines[1:]:
            lines.append(
                f"{'':10} | {'':5} | {extra:{mon_width}} | {'':8} | {'':3} | {'':14} |"
            )
        if hinhthuc or ghichu:
            lines.append(f"  HT: {hinhthuc} | GC: {ghichu}")

    lines.append("```")
    return "\n".join(lines)
