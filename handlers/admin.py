import csv
import io
import re
from datetime import date, timedelta

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BufferedInputFile,
)
from aiogram.exceptions import TelegramAPIError

import database as db
import scheduler
from duration import parse_duration, format_duration, DURATION_HELP

# Telefon raqami uchun sodda validatsiya: + bilan yoki raqam bilan boshlanadi,
# 9-15 ta raqamdan iborat bo'lishi kerak
PHONE_RE = re.compile(r"^\+?\d{9,15}$")

CANDIDATES_PAGE_SIZE = 5

router = Router()


def is_admin(user_id: int) -> bool:
    return db.is_admin(user_id)


class AdminForm(StatesGroup):
    waiting_phone = State()
    waiting_location = State()
    waiting_meeting_time = State()
    waiting_new_admin = State()
    waiting_scooter_photo = State()
    waiting_scooter_name = State()
    waiting_scooter_free = State()
    waiting_scooter_price = State()
    waiting_scooter_edit_value = State()
    waiting_retry_cooldown = State()
    waiting_force_sub_input = State()


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📞 Aloqa raqamini o'zgartirish", callback_data="adm_phone")],
            [InlineKeyboardButton(text="📍 Lokatsiyani belgilash", callback_data="adm_location")],
            [InlineKeyboardButton(text="🗑 Lokatsiyani o'chirish", callback_data="adm_del_location")],
            [InlineKeyboardButton(text="🕐 Uchrashuv vaqtini belgilash", callback_data="adm_time")],
            [InlineKeyboardButton(text="⏱ Qayta urinish muddati", callback_data="adm_retry_cooldown")],
            [InlineKeyboardButton(text="📊 Statistika", callback_data="adm_stats_menu")],
            [InlineKeyboardButton(text="📋 Nomzodlar ro'yxati", callback_data="adm_cand_list")],
            [InlineKeyboardButton(text="🛵 Skuterlar (transport)", callback_data="adm_scooters")],
            [InlineKeyboardButton(text="📢 Majburiy obuna", callback_data="adm_force_sub")],
            [InlineKeyboardButton(text="👤 Adminlar", callback_data="adm_admins")],
        ]
    )


def stats_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Bugun/Kecha", callback_data="adm_stats_today")],
            [InlineKeyboardButton(text="🗓 Shu hafta", callback_data="adm_stats_week")],
            [InlineKeyboardButton(text="🗓 Shu oy", callback_data="adm_stats_month")],
            [InlineKeyboardButton(text="🚫 Rad sabablari", callback_data="adm_stats_rejects")],
            [InlineKeyboardButton(text="📥 CSV eksport", callback_data="adm_stats_csv")],
            [InlineKeyboardButton(text="📨 Kunlik hisobotni hozir yuborish", callback_data="adm_stats_send_report")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="adm_back")],
        ]
    )


def admins_menu_kb(admins) -> InlineKeyboardMarkup:
    rows = []
    for a in admins:
        label = f"{'⭐️ ' if a['is_super'] else ''}{a['tg_id']}"
        if a["username"]:
            label += f" (@{a['username']})"
        row = [InlineKeyboardButton(text=label, callback_data=f"noop_{a['tg_id']}")]
        if not a["is_super"]:
            row.append(
                InlineKeyboardButton(text="❌ O'chirish", callback_data=f"adm_rm_{a['tg_id']}")
            )
        rows.append(row)
    rows.append([InlineKeyboardButton(text="➕ Admin qo'shish", callback_data="adm_add_admin")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="adm_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


STATUS_ICONS = {"passed": "✅", "rejected": "❌", "started": "⏳"}
STATUS_LABELS = {"passed": "O'tdi", "rejected": "Rad etildi", "started": "Jarayonda / tark etdi"}


def candidates_list_kb(rows, offset: int, total: int) -> InlineKeyboardMarkup:
    buttons = []
    for r in rows:
        icon = STATUS_ICONS.get(r["status"], "❔")
        name = r["full_name"] or "Noma'lum"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{icon} {name} — {r['created_date']}",
                    callback_data=f"adm_cand_detail_{r['id']}",
                )
            ]
        )

    nav = []
    if offset > 0:
        prev_offset = max(0, offset - CANDIDATES_PAGE_SIZE)
        nav.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"adm_cand_page_{prev_offset}"))
    if offset + CANDIDATES_PAGE_SIZE < total:
        next_offset = offset + CANDIDATES_PAGE_SIZE
        nav.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"adm_cand_page_{next_offset}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="adm_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def scooters_menu_kb(scooters) -> InlineKeyboardMarkup:
    rows = []
    for s in scooters:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🛵 {s['name']} — {s['price']}",
                    callback_data=f"adm_scooter_view_{s['id']}",
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"adm_scooter_edit_menu_{s['id']}"),
                InlineKeyboardButton(text="❌ O'chirish", callback_data=f"adm_scooter_del_{s['id']}"),
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ Skuter qo'shish", callback_data="adm_scooter_add")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="adm_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def force_sub_menu_kb(channels) -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        rows.append(
            [
                InlineKeyboardButton(text=f"📢 {ch['title']}", callback_data=f"noop_{ch['id']}"),
                InlineKeyboardButton(text="❌ O'chirish", callback_data=f"adm_force_sub_del_{ch['id']}"),
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ Kanal/guruh qo'shish", callback_data="adm_force_sub_add")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="adm_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def scooter_edit_menu_kb(scooter_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Nomi", callback_data=f"adm_scooter_editf_name_{scooter_id}")],
            [InlineKeyboardButton(text="📸 Rasmi", callback_data=f"adm_scooter_editf_photo_{scooter_id}")],
            [InlineKeyboardButton(text="⏳ Bepul muddati", callback_data=f"adm_scooter_editf_free_{scooter_id}")],
            [InlineKeyboardButton(text="💵 Narxi", callback_data=f"adm_scooter_editf_price_{scooter_id}")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="adm_scooters")],
        ]
    )


ADMIN_DIVIDER = "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈"
ADMIN_HOME_TEXT = f"🛠 <b>ADMIN PANEL</b>\n{ADMIN_DIVIDER}\n\n<i>Kerakli bo'limni tanlang</i> 👇"


@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(ADMIN_HOME_TEXT, reply_markup=admin_menu_kb())


@router.callback_query(F.data == "adm_back")
async def adm_back(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text(ADMIN_HOME_TEXT, reply_markup=admin_menu_kb())
    await call.answer()


@router.callback_query(F.data == "adm_phone")
async def adm_phone(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    current = db.get_setting("contact_phone") or "—"
    await call.message.answer(
        f"📞 <b>Aloqa raqamini o'zgartirish</b>\n{ADMIN_DIVIDER}\n\n"
        f"Joriy raqam: <b>{current}</b>\n\n"
        "Yangi raqamni yuboring (masalan: +998901234567):"
    )
    await state.set_state(AdminForm.waiting_phone)
    await call.answer()


@router.message(AdminForm.waiting_phone)
async def adm_phone_save(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not PHONE_RE.match(text):
        await message.answer(
            "❗️ Raqam noto'g'ri formatda. Iltimos, faqat raqamlardan iborat "
            "(ixtiyoriy + bilan), masalan +998901234567 ko'rinishida yuboring:"
        )
        return  # holat o'zgarmaydi, qayta so'raladi
    db.set_setting("contact_phone", text)
    await message.answer(f"✅ Aloqa raqami yangilandi: <b>{text}</b>")
    await state.clear()


@router.callback_query(F.data == "adm_location")
async def adm_location(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.answer(
        f"📍 <b>Lokatsiyani belgilash</b>\n{ADMIN_DIVIDER}\n\n"
        "Ofis lokatsiyasini yuboring (📎 → Location orqali) yoki manzil matnini yozing:"
    )
    await state.set_state(AdminForm.waiting_location)
    await call.answer()


@router.message(AdminForm.waiting_location, F.location)
async def adm_location_save_geo(message: Message, state: FSMContext):
    db.set_setting("location_lat", str(message.location.latitude))
    db.set_setting("location_lon", str(message.location.longitude))
    db.delete_setting("location_address")
    await message.answer("✅ Lokatsiya (geo) saqlandi.")
    await state.clear()


@router.message(AdminForm.waiting_location)
async def adm_location_save_text(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 5:
        await message.answer(
            "❗️ Manzil juda qisqa yoki bo'sh. Iltimos, to'liqroq manzil matnini yozing "
            "yoki 📎 → Location orqali geo-lokatsiya yuboring:"
        )
        return  # holat o'zgarmaydi, qayta so'raladi
    db.set_setting("location_address", text)
    db.delete_setting("location_lat")
    db.delete_setting("location_lon")
    await message.answer("✅ Manzil saqlandi.")
    await state.clear()


@router.callback_query(F.data == "adm_del_location")
async def adm_del_location(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    db.delete_setting("location_lat")
    db.delete_setting("location_lon")
    db.delete_setting("location_address")
    await call.message.answer("🗑 Lokatsiya o'chirildi.")
    await call.answer()


@router.callback_query(F.data == "adm_time")
async def adm_time(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    current = db.get_setting("meeting_time") or "—"
    await call.message.answer(
        f"🕐 <b>Uchrashuv vaqtini belgilash</b>\n{ADMIN_DIVIDER}\n\n"
        f"Joriy vaqt: <b>{current}</b>\n\n"
        "Yangi uchrashuv vaqtini yuboring (masalan: ertaga soat 11:00):"
    )
    await state.set_state(AdminForm.waiting_meeting_time)
    await call.answer()


@router.message(AdminForm.waiting_meeting_time)
async def adm_time_save(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("❗️ Bo'sh matn yuborildi. Iltimos, uchrashuv vaqtini matn ko'rinishida yozing:")
        return  # holat o'zgarmaydi, qayta so'raladi
    db.set_setting("meeting_time", text)
    await message.answer(f"✅ Uchrashuv vaqti yangilandi: <b>{text}</b>")
    await state.clear()


@router.callback_query(F.data == "adm_retry_cooldown")
async def adm_retry_cooldown(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    current_seconds = db.get_reject_retry_seconds()
    await call.message.answer(
        f"⏱ <b>Qayta urinish muddati</b>\n{ADMIN_DIVIDER}\n\n"
        f"Rad etilgan nomzod qayta ariza topshira olmaydigan muddat.\n\n"
        f"Joriy qiymat: <b>{format_duration(current_seconds)}</b>\n\n"
        f"Yangi muddatni yuboring (1 soniyadan 1 yilgacha).\n{DURATION_HELP}"
    )
    await state.set_state(AdminForm.waiting_retry_cooldown)
    await call.answer()


@router.message(AdminForm.waiting_retry_cooldown)
async def adm_retry_cooldown_save(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    seconds = parse_duration(text)
    if seconds is None:
        await message.answer(
            "❗️ Format noto'g'ri yoki 1 soniya — 1 yil oralig'idan tashqarida.\n\n"
            f"{DURATION_HELP}"
        )
        return  # holat o'zgarmaydi, qayta so'raladi
    db.set_reject_retry_seconds(seconds)
    await message.answer(f"✅ Qayta urinish muddati yangilandi: <b>{format_duration(seconds)}</b>")
    await state.clear()


@router.callback_query(F.data == "adm_force_sub")
async def adm_force_sub(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    channels = db.list_forced_channels()
    text = (
        f"📢 <b>MAJBURIY OBUNA</b>\n{ADMIN_DIVIDER}\n\n"
        "Bu yerda qo'shilgan kanal/guruhlarga obuna bo'lmagan foydalanuvchilar "
        "botdan foydalana olmaydi.\n\n"
        "<i>Kerakli amalni tanlang</i> 👇"
        if channels
        else (
            f"📢 <b>MAJBURIY OBUNA</b>\n{ADMIN_DIVIDER}\n\n"
            "Hozircha kanal/guruh qo'shilmagan - majburiy obuna o'chirilgan holatda.\n\n"
            "<i>Qo'shish uchun pastdagi tugmani bosing</i> 👇"
        )
    )
    await call.message.edit_text(text, reply_markup=force_sub_menu_kb(channels))
    await call.answer()


@router.callback_query(F.data == "adm_force_sub_add")
async def adm_force_sub_add(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.answer(
        f"➕ <b>Kanal/guruh qo'shish</b>\n{ADMIN_DIVIDER}\n\n"
        "Kanal yoki guruhning <b>@username</b>'ini (masalan: @mychannel) "
        "yoki <b>ID raqamini</b> (masalan: -1001234567890) yuboring.\n\n"
        "❗️ <b>Muhim:</b>\n"
        "1️⃣ Botni o'sha kanal/guruhga <b>admin</b> qilib qo'shing "
        "(obunani tekshirish uchun shart).\n"
        "2️⃣ Yopiq (username'i yo'q) kanal/guruh uchun ID raqamini bilish uchun "
        "o'sha yerdan biror xabarni @userinfobot yoki @getidsbot ga forward qiling."
    )
    await state.set_state(AdminForm.waiting_force_sub_input)
    await call.answer()


@router.message(AdminForm.waiting_force_sub_input)
async def adm_force_sub_save(message: Message, state: FSMContext, bot: Bot):
    raw = (message.text or "").strip()
    if not raw:
        await message.answer("❗️ Iltimos, kanal/guruhning @username'ini yoki ID raqamini yuboring:")
        return  # holat o'zgarmaydi, qayta so'raladi

    # https://t.me/username yoki t.me/username ko'rinishida yuborilsa - tozalab olamiz
    cleaned = raw.replace("https://t.me/", "").replace("http://t.me/", "").replace("t.me/", "").strip()

    if re.match(r"^-?\d+$", cleaned):
        chat_ref = int(cleaned)
    else:
        chat_ref = cleaned if cleaned.startswith("@") else f"@{cleaned}"

    try:
        chat = await bot.get_chat(chat_ref)
    except TelegramAPIError:
        await message.answer(
            "❗️ Kanal/guruh topilmadi. @username yoki ID raqami to'g'ri ekanini tekshiring "
            "va botni o'sha joyga <b>admin</b> qilib qo'shganingizga ishonch hosil qiling. "
            "Qayta urinib ko'ring:"
        )
        return  # holat o'zgarmaydi, qayta so'raladi

    try:
        bot_member = await bot.get_chat_member(chat.id, bot.id)
        if bot_member.status not in ("administrator", "creator"):
            raise TelegramAPIError(method=None, message="bot not admin")
    except TelegramAPIError:
        await message.answer(
            f"❗️ Bot «{chat.title or chat_ref}» kanal/guruhida <b>admin</b> emas. "
            "Iltimos, botni o'sha yerga admin qilib qo'shing va shu xabarni qayta yuboring:"
        )
        return  # holat o'zgarmaydi, qayta so'raladi

    existing = db.get_forced_channel_by_chat_id(str(chat.id))
    if existing:
        await message.answer("❗️ Bu kanal/guruh ro'yxatda allaqachon mavjud.")
        await state.clear()
        channels = db.list_forced_channels()
        await message.answer(f"📢 <b>MAJBURIY OBUNA</b>\n{ADMIN_DIVIDER}", reply_markup=force_sub_menu_kb(channels))
        return

    invite_link = None
    if chat.username:
        invite_link = f"https://t.me/{chat.username}"
    else:
        try:
            invite_link = await bot.export_chat_invite_link(chat.id)
        except TelegramAPIError:
            invite_link = None  # link olinmadi - baribir qo'shamiz, tugma ko'rsatilmasligi mumkin

    title = chat.title or chat.username or str(chat.id)
    db.add_forced_channel(chat_id=str(chat.id), title=title, invite_link=invite_link)
    await state.clear()

    warn = "" if invite_link else "\n\n⚠️ Havola avtomatik olinmadi - foydalanuvchilarga kanal nomi ko'rinadi, lekin tugma ishlamasligi mumkin."
    await message.answer(f"✅ Qo'shildi: <b>{title}</b>{warn}")

    channels = db.list_forced_channels()
    await message.answer(f"📢 <b>MAJBURIY OBUNA</b>\n{ADMIN_DIVIDER}", reply_markup=force_sub_menu_kb(channels))


@router.callback_query(F.data.startswith("adm_force_sub_del_"))
async def adm_force_sub_del(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    channel_id = int(call.data.replace("adm_force_sub_del_", ""))
    db.delete_forced_channel(channel_id)
    await call.answer("🗑 O'chirildi")

    channels = db.list_forced_channels()
    text = (
        f"📢 <b>MAJBURIY OBUNA</b>\n{ADMIN_DIVIDER}"
        if channels
        else f"📢 <b>MAJBURIY OBUNA</b>\n{ADMIN_DIVIDER}\n\n<i>Hozircha kanal/guruh qo'shilmagan.</i>"
    )
    await call.message.edit_text(text, reply_markup=force_sub_menu_kb(channels))


@router.callback_query(F.data == "adm_stats_menu")
async def adm_stats_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text(
        f"📊 <b>STATISTIKA</b>\n{ADMIN_DIVIDER}\n\n<i>Kerakli davrni tanlang</i> 👇",
        reply_markup=stats_menu_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "adm_stats_today")
async def adm_stats_today(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    today = date.today()
    yesterday = today - timedelta(days=1)

    started_today, passed_today = db.get_stats_for_date(today.isoformat())
    started_yday, passed_yday = db.get_stats_for_date(yesterday.isoformat())

    text = (
        f"📅 <b>Bugun / Kecha</b>\n{ADMIN_DIVIDER}\n\n"
        f"<b>Bugun:</b> {started_today} ta kirdi, {passed_today} tasi o'tdi ✅\n"
        f"<b>Kecha:</b> {started_yday} ta kirgan edi, {passed_yday} tasi o'tgan edi ✅"
    )
    await call.message.answer(text)
    await call.answer()


@router.callback_query(F.data == "adm_stats_week")
async def adm_stats_week(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    today = date.today()
    start = today - timedelta(days=today.weekday())  # shu haftaning dushanbasi
    started, passed, rejected = db.get_stats_range(start.isoformat(), today.isoformat())
    text = (
        f"🗓 <b>Shu hafta</b> <i>({start.isoformat()} — {today.isoformat()})</i>\n{ADMIN_DIVIDER}\n\n"
        f"👥 <b>Botga kirganlar:</b> {started}\n"
        f"✅ <b>Sinovdan o'tganlar:</b> {passed}\n"
        f"❌ <b>Rad etilganlar:</b> {rejected}"
    )
    await call.message.answer(text)
    await call.answer()


@router.callback_query(F.data == "adm_stats_month")
async def adm_stats_month(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    today = date.today()
    start = today.replace(day=1)
    started, passed, rejected = db.get_stats_range(start.isoformat(), today.isoformat())
    text = (
        f"🗓 <b>Shu oy</b> <i>({start.isoformat()} — {today.isoformat()})</i>\n{ADMIN_DIVIDER}\n\n"
        f"👥 <b>Botga kirganlar:</b> {started}\n"
        f"✅ <b>Sinovdan o'tganlar:</b> {passed}\n"
        f"❌ <b>Rad etilganlar:</b> {rejected}"
    )
    await call.message.answer(text)
    await call.answer()


@router.callback_query(F.data == "adm_stats_rejects")
async def adm_stats_rejects(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    reject_stats = db.get_reject_stats()
    if not reject_stats:
        await call.message.answer("🚫 Hozircha rad etilgan nomzodlar yo'q.")
        await call.answer()
        return

    lines = [f"🚫 <b>Rad etilganlar</b> <i>(bosqichlar bo'yicha)</i>\n{ADMIN_DIVIDER}\n"]
    for step, count in sorted(reject_stats.items(), key=lambda x: -x[1]):
        label = db.REJECT_STEP_LABELS.get(step, step)
        lines.append(f"▪️ {label}: <b>{count}</b> ta")
    await call.message.answer("\n".join(lines))
    await call.answer()


@router.callback_query(F.data == "adm_stats_csv")
async def adm_stats_csv(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        return
    rows = db.get_candidates_for_export()
    if not rows:
        await call.message.answer("📥 Eksport qilinadigan ma'lumot yo'q.")
        await call.answer()
        return

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["id", "tg_id", "username", "full_name", "phone", "age", "lang", "passport_ok",
         "in_tashkent", "experience", "transport", "status", "reject_step", "created_date",
         "wants_scooter", "scooter_requested_at"]
    )
    for row in rows:
        writer.writerow([row[key] for key in row.keys()])

    file_bytes = buffer.getvalue().encode("utf-8-sig")  # utf-8-sig -> Excelda kirill/lotin harflar to'g'ri ko'rinadi
    filename = f"nomzodlar_{date.today().isoformat()}.csv"
    doc = BufferedInputFile(file_bytes, filename=filename)
    await bot.send_document(call.message.chat.id, doc, caption="📥 Barcha nomzodlar ro'yxati (CSV)")
    await call.answer()


@router.callback_query(F.data == "adm_stats_send_report")
async def adm_stats_send_report(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        return
    await scheduler.send_daily_report(bot)
    await call.answer("📨 Kunlik hisobot barcha adminlarga yuborildi.", show_alert=True)


# ---------------- Adminlarni boshqarish ----------------

ADMINS_LIST_TEXT = f"👤 <b>ADMINLAR RO'YXATI</b>\n{ADMIN_DIVIDER}\n<i>⭐️ — super-admin (o'chirib bo'lmaydi)</i>"


@router.callback_query(F.data == "adm_admins")
async def adm_admins(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    admins = db.list_admins()
    await call.message.edit_text(ADMINS_LIST_TEXT, reply_markup=admins_menu_kb(admins))
    await call.answer()


@router.callback_query(F.data.startswith("noop_"))
async def adm_noop(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data == "adm_add_admin")
async def adm_add_admin(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.answer(
        f"➕ <b>Yangi admin qo'shish</b>\n{ADMIN_DIVIDER}\n\n"
        "Yangi adminning Telegram ID raqamini yuboring.\n\n"
        "<i>ID ni bilish uchun o'sha kishi @userinfobot ga /start bossin, "
        "yoki o'sha kishidan istalgan xabarini shu yerga forward qiling.</i>"
    )
    await state.set_state(AdminForm.waiting_new_admin)
    await call.answer()


@router.message(AdminForm.waiting_new_admin)
async def adm_add_admin_save(message: Message, state: FSMContext):
    new_id = None
    new_username = ""

    # Forward qilingan xabardan foydalanuvchi ID sini olishga urinamiz
    forward_from = getattr(message, "forward_from", None)
    if forward_from is not None:
        new_id = forward_from.id
        new_username = forward_from.username or ""
    else:
        text = message.text.strip() if message.text else ""
        if text.isdigit():
            new_id = int(text)

    if new_id is None:
        await message.answer(
            "❗️ ID topilmadi. Iltimos, faqat raqam (masalan: 123456789) yuboring "
            "yoki o'sha foydalanuvchining xabarini forward qiling."
        )
        return

    added = db.add_admin(new_id, new_username, added_by=message.from_user.id)
    if added:
        await message.answer(f"✅ Yangi admin qo'shildi: <b>{new_id}</b>")
    else:
        await message.answer("⚠️ Bu foydalanuvchi allaqachon admin.")

    await state.clear()
    admins = db.list_admins()
    await message.answer(ADMINS_LIST_TEXT, reply_markup=admins_menu_kb(admins))


@router.callback_query(F.data.startswith("adm_rm_"))
async def adm_remove_admin(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    target_id = int(call.data.replace("adm_rm_", ""))
    removed = db.remove_admin(target_id)
    if removed:
        await call.answer("O'chirildi ✅")
    else:
        await call.answer("Super-adminni o'chirib bo'lmaydi ❌", show_alert=True)

    admins = db.list_admins()
    await call.message.edit_text(ADMINS_LIST_TEXT, reply_markup=admins_menu_kb(admins))


# ---------------- Nomzodlar ro'yxati (bot ichida) ----------------

async def show_candidates_page(call: CallbackQuery, offset: int):
    total = db.get_candidates_count()
    rows = db.get_candidates_page(offset, CANDIDATES_PAGE_SIZE)

    header = f"📋 <b>NOMZODLAR RO'YXATI</b>\n{ADMIN_DIVIDER}\n\n"
    if total == 0:
        text = header + "<i>Hozircha hech qanday nomzod yo'q.</i>"
    elif not rows:
        text = header + "<i>Bu sahifada nomzod yo'q.</i>"
    else:
        start_n = offset + 1
        end_n = offset + len(rows)
        text = header + f"<b>{start_n}-{end_n}</b> / {total} ta"

    await call.message.edit_text(text, reply_markup=candidates_list_kb(rows, offset, total))


@router.callback_query(F.data == "adm_cand_list")
async def adm_cand_list(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await show_candidates_page(call, 0)
    await call.answer()


@router.callback_query(F.data.startswith("adm_cand_page_"))
async def adm_cand_page(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    offset = int(call.data.replace("adm_cand_page_", ""))
    await show_candidates_page(call, offset)
    await call.answer()


@router.callback_query(F.data.startswith("adm_cand_detail_"))
async def adm_cand_detail(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    candidate_id = int(call.data.replace("adm_cand_detail_", ""))
    c = db.get_candidate(candidate_id)
    if not c:
        await call.answer("Nomzod topilmadi.", show_alert=True)
        return

    username_str = f"@{c['username']}" if c["username"] else "—"
    lang_label = "🇺🇿 UZ" if c["lang"] == "uz" else "🇷🇺 RU"
    status_label = STATUS_LABELS.get(c["status"], c["status"])
    status_icon = STATUS_ICONS.get(c["status"], "❔")

    lines = [
        f"👤 <b>{c['full_name'] or '—'}</b> ({username_str})",
        ADMIN_DIVIDER,
        f"🌐 <b>Til:</b> {lang_label}",
        f"📞 <b>Telefon:</b> {c['phone'] or '—'}",
        f"🎂 <b>Yosh:</b> {c['age'] if c['age'] is not None else '—'}",
        f"🪪 <b>Pasport asli:</b> {c['passport_ok'] or '—'}",
        f"🏙 <b>Toshkentda:</b> {c['in_tashkent'] or '—'}",
        f"💼 <b>Tajriba:</b> {c['experience'] or '—'}",
        f"🚗 <b>Transport:</b> {c['transport'] or '—'}",
        f"📅 <b>Murojaat sanasi:</b> {c['created_date']}",
        f"📌 <b>Holat:</b> {status_icon} {status_label}",
    ]
    if c["status"] == "rejected" and c["reject_step"]:
        label = db.REJECT_STEP_LABELS.get(c["reject_step"], c["reject_step"])
        lines.append(f"🚫 <b>Rad sababi:</b> {label}")
    if c["wants_scooter"]:
        lines.append(f"🛴 <b>Skuter so'rovi:</b> {c['wants_scooter']} ({c['scooter_requested_at'] or '—'})")

    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Ro'yxatga qaytish", callback_data="adm_cand_list")]]
    )
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


# ---------------- Skuterlar (transport bo'limi) ----------------
# Bu yerda qo'shilgan skuterlar kuryerlik testidan o'tgan nomzodlarga
# lokatsiya xabaridan keyin ko'rsatiladi (handlers/user.py -> transport_answer).

def scooter_caption(s) -> str:
    return (
        f"🛵 <b>{s['name']}</b>\n"
        f"{ADMIN_DIVIDER}\n"
        f"⏳ <b>Bepul muddat:</b> {s['free_period']}\n"
        f"💵 <b>Narxi:</b> {s['price']}"
    )


@router.callback_query(F.data == "adm_scooters")
async def adm_scooters(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    scooters = db.list_scooters()
    header = f"🛵 <b>SKUTERLAR</b> <i>(transport bo'limi)</i>\n{ADMIN_DIVIDER}\n\n"
    text = (
        header + "Bu yerga qo'shilgan skuterlar testdan o'tgan nomzodlarga "
        "lokatsiyadan keyin avtomatik ko'rsatiladi."
        if scooters
        else header + "<i>Hozircha skuter qo'shilmagan.</i>\n\n"
        "Qo'shilgan skuterlar testdan o'tgan nomzodlarga lokatsiyadan keyin ko'rsatiladi."
    )
    await call.message.edit_text(text, reply_markup=scooters_menu_kb(scooters))
    await call.answer()


@router.callback_query(F.data.startswith("adm_scooter_view_"))
async def adm_scooter_view(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        return
    scooter_id = int(call.data.replace("adm_scooter_view_", ""))
    s = db.get_scooter(scooter_id)
    if not s:
        await call.answer("Skuter topilmadi.", show_alert=True)
        return
    if s["photo_file_id"]:
        await bot.send_photo(call.message.chat.id, s["photo_file_id"], caption=scooter_caption(s))
    else:
        await call.message.answer(scooter_caption(s))
    await call.answer()


@router.callback_query(F.data == "adm_scooter_add")
async def adm_scooter_add(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.answer(
        f"➕ <b>Yangi skuter qo'shish</b>\n{ADMIN_DIVIDER}\n\n"
        "📸 Skuterning rasmini yuboring.\n\n"
        "<i>Agar rasm bo'lmasa, shunchaki \"-\" deb yozing — rasmsiz ham qo'shish mumkin.</i>"
    )
    await state.set_state(AdminForm.waiting_scooter_photo)
    await call.answer()


@router.message(AdminForm.waiting_scooter_photo, F.photo)
async def adm_scooter_photo(message: Message, state: FSMContext):
    photo_file_id = message.photo[-1].file_id  # eng katta o'lchamdagi versiyasi
    await state.update_data(scooter_photo=photo_file_id)
    await message.answer("✅ Rasm qabul qilindi.\n\n📝 Endi skuter nomini/modelini yozing (masalan: Xiaomi M365):")
    await state.set_state(AdminForm.waiting_scooter_name)


@router.message(AdminForm.waiting_scooter_photo)
async def adm_scooter_photo_skip(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text != "-":
        await message.answer(
            "❗️ Iltimos, rasm yuboring, yoki rasmsiz o'tish uchun faqat \"-\" deb yozing:"
        )
        return
    await state.update_data(scooter_photo=None)
    await message.answer("📝 Skuter nomini/modelini yozing (masalan: Xiaomi M365):")
    await state.set_state(AdminForm.waiting_scooter_name)


@router.message(AdminForm.waiting_scooter_name)
async def adm_scooter_name(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("❗️ Bo'sh matn. Iltimos, skuter nomini yozing:")
        return
    await state.update_data(scooter_name=text)
    await message.answer(
        "⏳ Necha muddatga bepul foydalanish mumkin? (masalan: 1 oy bepul, keyin ijaraga):"
    )
    await state.set_state(AdminForm.waiting_scooter_free)


@router.message(AdminForm.waiting_scooter_free)
async def adm_scooter_free(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("❗️ Bo'sh matn. Iltimos, bepul muddatni yozing (masalan: 1 oy bepul):")
        return
    await state.update_data(scooter_free=text)
    await message.answer("💵 Narxini yozing (masalan: 500 000 so'm/oy):")
    await state.set_state(AdminForm.waiting_scooter_price)


@router.message(AdminForm.waiting_scooter_price)
async def adm_scooter_price(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("❗️ Bo'sh matn. Iltimos, narxini yozing (masalan: 500 000 so'm/oy):")
        return

    data = await state.get_data()
    scooter_id = db.add_scooter(
        name=data["scooter_name"],
        photo_file_id=data.get("scooter_photo"),
        free_period=data["scooter_free"],
        price=text,
    )
    await state.clear()

    s = db.get_scooter(scooter_id)
    if s["photo_file_id"]:
        await message.answer_photo(s["photo_file_id"], caption=f"✅ Skuter qo'shildi!\n\n{scooter_caption(s)}")
    else:
        await message.answer(f"✅ Skuter qo'shildi!\n\n{scooter_caption(s)}")

    scooters = db.list_scooters()
    await message.answer(f"🛵 <b>SKUTERLAR</b>\n{ADMIN_DIVIDER}", reply_markup=scooters_menu_kb(scooters))


@router.callback_query(F.data.startswith("adm_scooter_del_"))
async def adm_scooter_del(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    scooter_id = int(call.data.replace("adm_scooter_del_", ""))
    db.delete_scooter(scooter_id)
    await call.answer("🗑 O'chirildi")

    scooters = db.list_scooters()
    text = (
        f"🛵 <b>SKUTERLAR</b> <i>(transport bo'limi)</i>\n{ADMIN_DIVIDER}"
        if scooters
        else f"🛵 <b>SKUTERLAR</b>\n{ADMIN_DIVIDER}\n\n<i>Hozircha skuter qo'shilmagan.</i>"
    )
    await call.message.edit_text(text, reply_markup=scooters_menu_kb(scooters))


# ---------------- Skuterni tahrirlash ----------------

SCOOTER_EDIT_FIELD_DB_COLUMN = {
    "name": "name",
    "photo": "photo_file_id",
    "free": "free_period",
    "price": "price",
}
SCOOTER_EDIT_FIELD_LABEL = {
    "name": "nomi",
    "photo": "rasmi",
    "free": "bepul muddati",
    "price": "narxi",
}


@router.callback_query(F.data.startswith("adm_scooter_edit_menu_"))
async def adm_scooter_edit_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    scooter_id = int(call.data.replace("adm_scooter_edit_menu_", ""))
    s = db.get_scooter(scooter_id)
    if not s:
        await call.answer("Skuter topilmadi.", show_alert=True)
        return
    await call.message.edit_text(
        f"✏️ \"{s['name']}\" — qaysi maydonni tahrirlaysiz?",
        reply_markup=scooter_edit_menu_kb(scooter_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm_scooter_editf_"))
async def adm_scooter_editf(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    # format: adm_scooter_editf_{field}_{scooter_id}
    remainder = call.data.replace("adm_scooter_editf_", "")
    field, scooter_id_str = remainder.rsplit("_", 1)
    scooter_id = int(scooter_id_str)
    s = db.get_scooter(scooter_id)
    if not s or field not in SCOOTER_EDIT_FIELD_DB_COLUMN:
        await call.answer("Skuter topilmadi.", show_alert=True)
        return

    await state.update_data(edit_scooter_id=scooter_id, edit_field=field)
    await state.set_state(AdminForm.waiting_scooter_edit_value)

    label = SCOOTER_EDIT_FIELD_LABEL[field]
    if field == "photo":
        has_photo = "bor" if s["photo_file_id"] else "yo'q"
        await call.message.answer(
            f"📸 Yangi rasmni yuboring, yoki rasmni olib tashlash uchun \"-\" deb yozing "
            f"(joriy: {has_photo}):"
        )
    else:
        current = s[SCOOTER_EDIT_FIELD_DB_COLUMN[field]] or "—"
        await call.message.answer(f"✏️ Yangi {label}ni yozing (joriy: {current}):")
    await call.answer()


@router.message(AdminForm.waiting_scooter_edit_value, F.photo)
async def adm_scooter_edit_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("edit_field") != "photo":
        return  # matn kutilayotgan maydonga rasm yuborilsa - e'tiborsiz qoldiramiz
    scooter_id = data["edit_scooter_id"]
    photo_file_id = message.photo[-1].file_id
    db.update_scooter(scooter_id, photo_file_id=photo_file_id)
    await state.clear()

    s = db.get_scooter(scooter_id)
    await message.answer_photo(photo_file_id, caption=f"✅ Rasm yangilandi!\n\n{scooter_caption(s)}")
    scooters = db.list_scooters()
    await message.answer(f"🛵 <b>SKUTERLAR</b>\n{ADMIN_DIVIDER}", reply_markup=scooters_menu_kb(scooters))


@router.message(AdminForm.waiting_scooter_edit_value)
async def adm_scooter_edit_value(message: Message, state: FSMContext):
    data = await state.get_data()
    field = data.get("edit_field")
    scooter_id = data.get("edit_scooter_id")
    text = (message.text or "").strip()

    if field == "photo":
        if text != "-":
            await message.answer(
                "❗️ Iltimos, rasm yuboring, yoki rasmni olib tashlash uchun faqat \"-\" deb yozing:"
            )
            return
        db.update_scooter(scooter_id, photo_file_id=None)
        await message.answer("✅ Rasm olib tashlandi.")
    else:
        if not text:
            label = SCOOTER_EDIT_FIELD_LABEL.get(field, field)
            await message.answer(f"❗️ Bo'sh matn. Iltimos, yangi {label}ni yozing:")
            return
        column = SCOOTER_EDIT_FIELD_DB_COLUMN[field]
        db.update_scooter(scooter_id, **{column: text})
        await message.answer("✅ Yangilandi.")

    await state.clear()
    s = db.get_scooter(scooter_id)
    if s:
        if s["photo_file_id"]:
            await message.answer_photo(s["photo_file_id"], caption=scooter_caption(s))
        else:
            await message.answer(scooter_caption(s))
    scooters = db.list_scooters()
    await message.answer(f"🛵 <b>SKUTERLAR</b>\n{ADMIN_DIVIDER}", reply_markup=scooters_menu_kb(scooters))


# ---------------- Stiker ID olish yordamchisi ----------------
# Admin botga istalgan stikerni yuborsa, bot o'sha stikerning file_id'sini qaytaradi.
# Shu ID'ni WELCOME_STICKER_ID muhit o'zgaruvchisiga qo'yish orqali /start xabariga
# istalgan stikerni biriktirish mumkin (config.py'dagi izohga qarang).

@router.message(F.sticker)
async def adm_get_sticker_id(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.reply(
        "🆔 Stiker ID:\n"
        f"<code>{message.sticker.file_id}</code>\n\n"
        "Shu ID'ni <code>WELCOME_STICKER_ID</code> muhit o'zgaruvchisiga qo'ysangiz, "
        "/start bosilganda shu stiker yuboriladi."
    )
