import re
from datetime import datetime, timedelta

MIN_SECONDS = 1
MAX_SECONDS = 365 * 24 * 3600  # 1 yil

UNIT_SECONDS = {
    "s": 1, "son": 1, "soniya": 1, "sek": 1,
    "m": 60, "min": 60, "daq": 60, "daqiqa": 60,
    "h": 3600, "soat": 3600,
    "d": 86400, "kun": 86400,
    "mo": 2592000, "oy": 2592000,   # taxminan 30 kun
    "y": 31536000, "yil": 31536000,  # taxminan 365 kun
}

DURATION_RE = re.compile(r"^\s*(\d+)\s*([a-zA-Z\u0400-\u04FF']+)\s*$")

# Foydalanuvchiga ko'rsatiladigan misollar
DURATION_HELP = (
    "Masalan:\n"
    "• <code>45s</code> — 45 soniya\n"
    "• <code>30m</code> — 30 daqiqa\n"
    "• <code>6h</code> — 6 soat\n"
    "• <code>3d</code> — 3 kun\n"
    "• <code>2mo</code> — 2 oy\n"
    "• <code>1y</code> — 1 yil"
)


def parse_duration(text: str) -> int | None:
    """
    Foydalanuvchi kiritgan davomiylik matnini (masalan "3d", "45s", "1y")
    soniyalarga o'giradi. Noto'g'ri format yoki 1 soniya - 1 yil oralig'idan
    tashqarida bo'lsa None qaytaradi.
    """
    if not text:
        return None
    match = DURATION_RE.match(text.strip())
    if not match:
        return None
    amount_str, unit = match.groups()
    unit_key = unit.lower()
    if unit_key not in UNIT_SECONDS:
        return None
    seconds = int(amount_str) * UNIT_SECONDS[unit_key]
    if seconds < MIN_SECONDS or seconds > MAX_SECONDS:
        return None
    return seconds


def format_duration(seconds: int) -> str:
    """Soniyalarni o'qilishi oson (eng yirik mos birlikda) matnga o'giradi."""
    seconds = int(seconds)
    if seconds >= 31536000 and seconds % 31536000 == 0:
        return f"{seconds // 31536000} yil"
    if seconds >= 2592000 and seconds % 2592000 == 0:
        return f"{seconds // 2592000} oy"
    if seconds >= 86400 and seconds % 86400 == 0:
        return f"{seconds // 86400} kun"
    if seconds >= 3600 and seconds % 3600 == 0:
        return f"{seconds // 3600} soat"
    if seconds >= 60 and seconds % 60 == 0:
        return f"{seconds // 60} daqiqa"
    return f"{seconds} soniya"


def format_datetime(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def compute_retry_at(status_updated_at_iso: str, retry_seconds: int) -> datetime:
    base = datetime.fromisoformat(status_updated_at_iso)
    return base + timedelta(seconds=retry_seconds)
