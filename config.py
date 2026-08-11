import os

# Bot tokenini @BotFather orqali oling.
# Railway'da: Project -> Variables -> BOT_TOKEN qo'shing.
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Admin(lar)ning Telegram ID raqami(lari). Bir nechta bo'lsa vergul bilan ajrating.
# ID ni bilish uchun @userinfobot ga /start bosing.
# Railway'da: Project -> Variables -> ADMIN_IDS qo'shing.
_admin_ids_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in _admin_ids_raw.split(",") if x.strip()]

# SQLite baza fayli manzili. Railway'da Volume ulasangiz (masalan /data ga),
# ma'lumotlar har bir deploy/restartdan keyin ham saqlanib qoladi.
# Volume ulanmagan bo'lsa, konteyner qayta yaratilganda baza tozalanadi.
DB_PATH = os.getenv("DB_PATH", "bot.db")

# DB_PATH papkasi mavjud bo'lmasa, avtomatik yaratamiz (masalan /data/bot.db uchun)
_db_dir = os.path.dirname(DB_PATH)
if _db_dir:
    os.makedirs(_db_dir, exist_ok=True)

# /start xabariga qo'shib yuboriladigan stiker. Bo'sh bo'lsa, stiker yuborilmaydi.
# Qanday olish mumkin: botga (admin sifatida) istalgan stikerni yuboring - bot sizga
# o'sha stikerning file_id'sini javob qilib yuboradi, shuni shu yerga qo'ying.
# Railway'da: Project -> Variables -> WELCOME_STICKER_ID qo'shing.
WELCOME_STICKER_ID = os.getenv("WELCOME_STICKER_ID", "")

# Kunlik avtomatik hisobot (statistika) adminlarga har kuni shu vaqtda yuboriladi.
# Vaqt Toshkent vaqti bo'yicha (UTC+5). O'chirish uchun DAILY_REPORT_ENABLED=0 qiling.
DAILY_REPORT_ENABLED = os.getenv("DAILY_REPORT_ENABLED", "1") != "0"
DAILY_REPORT_HOUR = int(os.getenv("DAILY_REPORT_HOUR", "20"))
DAILY_REPORT_MINUTE = int(os.getenv("DAILY_REPORT_MINUTE", "0"))
