import sqlite3
from datetime import date
from config import DB_PATH, ADMIN_IDS


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER,
            username TEXT,
            full_name TEXT,
            phone TEXT,
            age INTEGER,
            lang TEXT DEFAULT 'uz',
            passport_ok TEXT,
            in_tashkent TEXT,
            experience TEXT,
            transport TEXT,
            status TEXT DEFAULT 'started',   -- started / passed / rejected
            reject_step TEXT,
            created_date TEXT
        )
        """
    )
    # Eski bazalarda bo'lmagan ustunlar uchun migratsiya
    for column_def in ("age INTEGER", "lang TEXT DEFAULT 'uz'", "wants_scooter TEXT", "scooter_requested_at TEXT", "status_updated_at TEXT"):
        try:
            cur.execute(f"ALTER TABLE candidates ADD COLUMN {column_def}")
        except sqlite3.OperationalError:
            pass  # ustun allaqachon mavjud
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS admins (
            tg_id INTEGER PRIMARY KEY,
            username TEXT,
            is_super INTEGER DEFAULT 0,
            added_by INTEGER,
            added_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS scooters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            photo_file_id TEXT,
            free_period TEXT,
            price TEXT,
            created_at TEXT
        )
        """
    )
    conn.commit()

    # config.py dagi ADMIN_IDS - dasturning "super-admin"lari, birinchi ishga
    # tushirishda ular avtomatik admins jadvaliga qo'shiladi va o'chirib
    # bo'lmaydi (is_super = 1). Botdan boshqa adminlarni ular qo'sha oladi.
    for admin_id in ADMIN_IDS:
        cur.execute(
            "INSERT INTO admins (tg_id, is_super, added_by, added_at) VALUES (?, 1, ?, ?) "
            "ON CONFLICT(tg_id) DO UPDATE SET is_super = 1",
            (admin_id, admin_id, date.today().isoformat()),
        )
    conn.commit()
    conn.close()


# ---------- Nomzodlar (candidates) ----------

def create_candidate(tg_id: int, username: str, full_name: str, lang: str = "uz") -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO candidates (tg_id, username, full_name, lang, created_date) VALUES (?, ?, ?, ?, ?)",
        (tg_id, username, full_name, lang, date.today().isoformat()),
    )
    conn.commit()
    candidate_id = cur.lastrowid
    conn.close()
    return candidate_id


def update_candidate(candidate_id: int, **fields):
    conn = get_conn()
    cur = conn.cursor()
    keys = ", ".join(f"{k} = ?" for k in fields.keys())
    values = list(fields.values()) + [candidate_id]
    cur.execute(f"UPDATE candidates SET {keys} WHERE id = ?", values)
    conn.commit()
    conn.close()


def get_candidate(candidate_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_latest_candidate_by_tg(tg_id: int):
    """Berilgan Telegram foydalanuvchisining eng oxirgi (so'nggi) arizasini qaytaradi."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM candidates WHERE tg_id = ? ORDER BY id DESC LIMIT 1",
        (tg_id,),
    )
    row = cur.fetchone()
    conn.close()
    return row


def get_candidates_count(status: str = None) -> int:
    conn = get_conn()
    cur = conn.cursor()
    if status:
        cur.execute("SELECT COUNT(*) AS c FROM candidates WHERE status = ?", (status,))
    else:
        cur.execute("SELECT COUNT(*) AS c FROM candidates")
    n = cur.fetchone()["c"]
    conn.close()
    return n


def get_candidates_page(offset: int, limit: int, status: str = None):
    """Nomzodlarni eng yangisidan boshlab, sahifalab qaytaradi (admin panel uchun)."""
    conn = get_conn()
    cur = conn.cursor()
    if status:
        cur.execute(
            "SELECT * FROM candidates WHERE status = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (status, limit, offset),
        )
    else:
        cur.execute(
            "SELECT * FROM candidates ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
    rows = cur.fetchall()
    conn.close()
    return rows


# ---------- Sozlamalar (settings) ----------

def set_setting(key: str, value: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def get_setting(key: str, default=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row["value"] if row else default


def delete_setting(key: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM settings WHERE key = ?", (key,))
    conn.commit()
    conn.close()


# Rad etilgan nomzod qayta ariza topshira olmaydigan muddat (soniyalarda).
# Standart bo'yicha 30 kun (admin panel orqali 1 soniyadan 1 yilgacha o'zgartirish mumkin).
REJECT_RETRY_SECONDS_KEY = "reject_retry_seconds"
DEFAULT_REJECT_RETRY_SECONDS = 30 * 86400


def get_reject_retry_seconds() -> int:
    value = get_setting(REJECT_RETRY_SECONDS_KEY, str(DEFAULT_REJECT_RETRY_SECONDS))
    try:
        return int(value)
    except (TypeError, ValueError):
        return DEFAULT_REJECT_RETRY_SECONDS


def set_reject_retry_seconds(seconds: int):
    set_setting(REJECT_RETRY_SECONDS_KEY, str(int(seconds)))


# ---------- Adminlar ----------

def is_admin(tg_id: int) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM admins WHERE tg_id = ?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def is_super_admin(tg_id: int) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT is_super FROM admins WHERE tg_id = ?", (tg_id,))
    row = cur.fetchone()
    conn.close()
    return bool(row and row["is_super"])


def add_admin(tg_id: int, username: str, added_by: int) -> bool:
    """Yangi admin qo'shadi. Agar allaqachon mavjud bo'lsa False qaytaradi."""
    if is_admin(tg_id):
        return False
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO admins (tg_id, username, is_super, added_by, added_at) VALUES (?, ?, 0, ?, ?)",
        (tg_id, username or "", added_by, date.today().isoformat()),
    )
    conn.commit()
    conn.close()
    return True


def remove_admin(tg_id: int) -> bool:
    """Oddiy adminni o'chiradi. Super-adminni o'chirib bo'lmaydi."""
    if is_super_admin(tg_id):
        return False
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM admins WHERE tg_id = ?", (tg_id,))
    conn.commit()
    conn.close()
    return True


def list_admins():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT tg_id, username, is_super FROM admins ORDER BY is_super DESC, tg_id ASC")
    rows = cur.fetchall()
    conn.close()
    return rows


# ---------- Statistika ----------

def get_stats_for_date(day_iso: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM candidates WHERE created_date = ?", (day_iso,))
    started = cur.fetchone()["c"]
    cur.execute(
        "SELECT COUNT(*) AS c FROM candidates WHERE created_date = ? AND status = 'passed'",
        (day_iso,),
    )
    passed = cur.fetchone()["c"]
    conn.close()
    return started, passed


def get_stats_range(start_iso: str, end_iso: str):
    """start_iso va end_iso oralig'idagi (ikkalasi ham kiritiladi) statistikani qaytaradi."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) AS c FROM candidates WHERE created_date BETWEEN ? AND ?",
        (start_iso, end_iso),
    )
    started = cur.fetchone()["c"]
    cur.execute(
        "SELECT COUNT(*) AS c FROM candidates WHERE created_date BETWEEN ? AND ? AND status = 'passed'",
        (start_iso, end_iso),
    )
    passed = cur.fetchone()["c"]
    cur.execute(
        "SELECT COUNT(*) AS c FROM candidates WHERE created_date BETWEEN ? AND ? AND status = 'rejected'",
        (start_iso, end_iso),
    )
    rejected = cur.fetchone()["c"]
    conn.close()
    return started, passed, rejected


# Rad bosqichi kodini o'qilishi oson matnga o'girish
REJECT_STEP_LABELS = {
    "yosh": "18 yoshdan kichik (tasdiqlashda Yo'q bosdi)",
    "yosh_raqam": "Yoshi 18 dan kichik (aniq yoshni kiritganda)",
    "pasport": "Pasport asli yo'q",
    "toshkent": "Toshkentda emas",
}


def get_reject_stats(start_iso: str = None, end_iso: str = None):
    """Rad etilganlar sonini bosqichlar bo'yicha qaytaradi: {reject_step: count}."""
    conn = get_conn()
    cur = conn.cursor()
    if start_iso and end_iso:
        cur.execute(
            "SELECT reject_step, COUNT(*) AS c FROM candidates "
            "WHERE status = 'rejected' AND created_date BETWEEN ? AND ? "
            "GROUP BY reject_step",
            (start_iso, end_iso),
        )
    else:
        cur.execute(
            "SELECT reject_step, COUNT(*) AS c FROM candidates "
            "WHERE status = 'rejected' GROUP BY reject_step"
        )
    rows = cur.fetchall()
    conn.close()
    return {(row["reject_step"] or "noma'lum"): row["c"] for row in rows}


def get_candidates_for_export(start_iso: str = None, end_iso: str = None):
    """CSV eksport uchun barcha nomzodlar ro'yxatini qaytaradi (ixtiyoriy sana oralig'i bilan)."""
    conn = get_conn()
    cur = conn.cursor()
    if start_iso and end_iso:
        cur.execute(
            "SELECT * FROM candidates WHERE created_date BETWEEN ? AND ? ORDER BY id ASC",
            (start_iso, end_iso),
        )
    else:
        cur.execute("SELECT * FROM candidates ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    return rows


# ---------- Skuterlar (transport bo'limi) ----------

def add_scooter(name: str, photo_file_id: str, free_period: str, price: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO scooters (name, photo_file_id, free_period, price, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (name, photo_file_id, free_period, price, date.today().isoformat()),
    )
    conn.commit()
    scooter_id = cur.lastrowid
    conn.close()
    return scooter_id


def list_scooters():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM scooters ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_scooter(scooter_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM scooters WHERE id = ?", (scooter_id,))
    row = cur.fetchone()
    conn.close()
    return row


def update_scooter(scooter_id: int, **fields):
    conn = get_conn()
    cur = conn.cursor()
    keys = ", ".join(f"{k} = ?" for k in fields.keys())
    values = list(fields.values()) + [scooter_id]
    cur.execute(f"UPDATE scooters SET {keys} WHERE id = ?", values)
    conn.commit()
    conn.close()


def delete_scooter(scooter_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM scooters WHERE id = ?", (scooter_id,))
    conn.commit()
    conn.close()
