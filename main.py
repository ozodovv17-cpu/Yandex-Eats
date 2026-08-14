import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN, ADMIN_IDS, DAILY_REPORT_ENABLED
import database as db
import scheduler
import force_sub
from handlers import user, admin


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log = logging.getLogger("bot")

    if not BOT_TOKEN:
        log.error(
            "BOT_TOKEN topilmadi! Railway'da Variables bo'limiga BOT_TOKEN qo'shing "
            "yoki lokalda .env faylida belgilang."
        )
        return

    if not ADMIN_IDS:
        log.warning(
            "ADMIN_IDS bo'sh! Hech kim /admin panelidan foydalana olmaydi. "
            "Railway'da Variables bo'limiga ADMIN_IDS qo'shing."
        )

    db.init_db()
    log.info("Baza tayyor: %s", db.DB_PATH if hasattr(db, "DB_PATH") else "bot.db")

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Admin routerni birinchi ulaymiz, chunki /admin komandasi ustuvor bo'lishi kerak
    dp.include_router(admin.router)
    # Majburiy obuna routeri: "✅ Tekshirish" tugmasini middleware'siz qabul qiladi
    dp.include_router(force_sub.router)

    # Majburiy obuna middleware'ini faqat oddiy foydalanuvchi routeriga ulaymiz -
    # shunda admin foydalanuvchilar va /admin panel har doim erkin ishlaydi
    user.router.message.outer_middleware(force_sub.ForceSubMiddleware())
    user.router.callback_query.outer_middleware(force_sub.ForceSubMiddleware())
    dp.include_router(user.router)

    if DAILY_REPORT_ENABLED:
        asyncio.create_task(scheduler.daily_report_loop(bot))
    else:
        log.info("Kunlik hisobot o'chirilgan (DAILY_REPORT_ENABLED=0).")

    await bot.delete_webhook(drop_pending_updates=True)
    log.info("Bot ishga tushdi, polling boshlandi...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
