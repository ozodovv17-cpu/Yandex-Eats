"""Kunlik avtomatik hisobot: har kuni belgilangan vaqtda (Toshkent vaqti bo'yicha)
adminlarga o'sha kunning statistikasini yuboradi. Sozlamalar config.py'da:
DAILY_REPORT_ENABLED, DAILY_REPORT_HOUR, DAILY_REPORT_MINUTE.
"""

import asyncio
import logging
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
    TASHKENT_TZ = ZoneInfo("Asia/Tashkent")
except Exception:  # tzdata o'rnatilmagan muhitlar uchun zaxira variant
    from datetime import timezone
    TASHKENT_TZ = timezone(timedelta(hours=5))

import config
import database as db

log = logging.getLogger("bot.scheduler")


def build_daily_report_text() -> str:
    today = datetime.now(TASHKENT_TZ).date().isoformat()
    started, passed = db.get_stats_for_date(today)
    reject_stats = db.get_reject_stats(today, today)
    rejected_total = sum(reject_stats.values())

    lines = [
        f"📊 Kunlik hisobot — {today}",
        "",
        f"Botga kirganlar: {started}",
        f"Sinovdan o'tganlar: {passed}",
        f"Rad etilganlar: {rejected_total}",
    ]
    if reject_stats:
        lines.append("")
        lines.append("Rad sabablari:")
        for step, count in sorted(reject_stats.items(), key=lambda x: -x[1]):
            label = db.REJECT_STEP_LABELS.get(step, step)
            lines.append(f"• {label}: {count} ta")
    return "\n".join(lines)


async def send_daily_report(bot) -> None:
    text = build_daily_report_text()
    admin_ids = [row["tg_id"] for row in db.list_admins()]
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            pass


def seconds_until_next_run() -> float:
    now = datetime.now(TASHKENT_TZ)
    target = now.replace(
        hour=config.DAILY_REPORT_HOUR,
        minute=config.DAILY_REPORT_MINUTE,
        second=0,
        microsecond=0,
    )
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def daily_report_loop(bot) -> None:
    """Har kuni DAILY_REPORT_HOUR:DAILY_REPORT_MINUTE'da (Toshkent vaqti) ishga tushadi."""
    log.info(
        "Kunlik hisobot rejalashtirildi: har kuni %02d:%02d (Toshkent vaqti)",
        config.DAILY_REPORT_HOUR,
        config.DAILY_REPORT_MINUTE,
    )
    while True:
        wait_seconds = seconds_until_next_run()
        await asyncio.sleep(wait_seconds)
        try:
            await send_daily_report(bot)
            log.info("Kunlik hisobot yuborildi.")
        except Exception:
            log.exception("Kunlik hisobotni yuborishda xatolik yuz berdi.")
