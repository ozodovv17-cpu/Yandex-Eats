from datetime import date, datetime

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

import config
import database as db
from i18n import t
from duration import compute_retry_at, format_datetime

router = Router()


class Form(StatesGroup):
    choosing_language = State()
    waiting_phone = State()
    age = State()
    passport = State()
    tashkent = State()
    experience = State()
    transport = State()


def lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
            ]
        ]
    )


def yes_no_kb(prefix: str, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(lang, "yes"), callback_data=f"{prefix}_yes"),
                InlineKeyboardButton(text=t(lang, "no"), callback_data=f"{prefix}_no"),
            ]
        ]
    )


REJECT_STEP_LABELS = {
    "yosh": "18 yoshdan kichik",
    "pasport": "Pasport asli yo'q",
    "toshkent": "Toshkentda emas",
}


async def reject(message_or_call, state: FSMContext, candidate_id: int, step: str, lang: str, bot: Bot = None):
    db.update_candidate(
        candidate_id,
        status="rejected",
        reject_step=step,
        status_updated_at=datetime.now().isoformat(),
    )
    reject_text = t(lang, "reject")
    if isinstance(message_or_call, CallbackQuery):
        await message_or_call.message.answer(reject_text)
    else:
        await message_or_call.answer(reject_text)
    await state.clear()

    # Adminlarga rad etilgani haqida qisqa xabar (bot obyekti berilgan bo'lsa) - har doim o'zbek tilida
    if bot is not None:
        candidate = db.get_candidate(candidate_id)
        username_str = f"@{candidate['username']}" if candidate["username"] else "(username yo'q)"
        label = REJECT_STEP_LABELS.get(step, step)
        phone_str = candidate["phone"] or "—"
        admin_text = (
            "🚫 <b>Nomzod rad etildi</b>\n"
            "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
            f"👤 <b>Ism:</b> {candidate['full_name']} {username_str}\n"
            f"📞 <b>Telefon:</b> {phone_str}\n"
            f"❗️ <b>Sabab:</b> {label}"
        )
        admin_ids = [row["tg_id"] for row in db.list_admins()]
        for admin_id in admin_ids:
            try:
                await bot.send_message(admin_id, admin_text)
            except Exception:
                pass


# ---------------- QAYTA KIRGAN FOYDALANUVCHI (o'tgan/rad etilgan) ----------------

def already_passed_menu_kb(lang: str, candidate_id: int, has_scooters: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=t(lang, "menu_location_button"), callback_data="menu_location")],
        [InlineKeyboardButton(text=t(lang, "menu_contact_button"), callback_data="menu_contact")],
        [InlineKeyboardButton(text=t(lang, "menu_time_button"), callback_data="menu_time")],
    ]
    if has_scooters:
        rows.append(
            [
                InlineKeyboardButton(
                    text=t(lang, "menu_scooters_button"),
                    callback_data=f"menu_scooters_{candidate_id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_already_passed_menu(message: Message, candidate) -> None:
    lang = candidate["lang"] or "uz"
    has_scooters = bool(db.list_scooters())
    await message.answer(
        t(lang, "already_passed_title"),
        reply_markup=already_passed_menu_kb(lang, candidate["id"], has_scooters),
    )


@router.callback_query(F.data == "menu_location")
async def menu_location(call: CallbackQuery, bot: Bot):
    candidate = db.get_latest_candidate_by_tg(call.from_user.id)
    lang = (candidate["lang"] if candidate else None) or "uz"
    lat = db.get_setting("location_lat")
    lon = db.get_setting("location_lon")
    if lat and lon:
        await call.message.answer(t(lang, "office_location"))
        await bot.send_location(call.message.chat.id, latitude=float(lat), longitude=float(lon))
    else:
        address_text = db.get_setting("location_address")
        if address_text:
            await call.message.answer(f"{t(lang, 'office_location')} {address_text}")
        else:
            await call.message.answer(t(lang, "menu_no_location"))
    await call.answer()


@router.callback_query(F.data == "menu_contact")
async def menu_contact(call: CallbackQuery):
    candidate = db.get_latest_candidate_by_tg(call.from_user.id)
    lang = (candidate["lang"] if candidate else None) or "uz"
    contact_phone = db.get_setting("contact_phone", "—")
    await call.message.answer(t(lang, "menu_contact_value", contact_phone=contact_phone))
    await call.answer()


@router.callback_query(F.data == "menu_time")
async def menu_time(call: CallbackQuery):
    candidate = db.get_latest_candidate_by_tg(call.from_user.id)
    lang = (candidate["lang"] if candidate else None) or "uz"
    meeting_time = db.get_setting("meeting_time", "—")
    await call.message.answer(t(lang, "menu_time_value", meeting_time=meeting_time))
    await call.answer()


@router.callback_query(F.data.startswith("menu_scooters_"))
async def menu_scooters(call: CallbackQuery):
    candidate_id = int(call.data.replace("menu_scooters_", ""))
    candidate = db.get_candidate(candidate_id)
    lang = (candidate["lang"] if candidate else None) or "uz"
    scooters = db.list_scooters()
    if not scooters:
        await call.message.answer(t(lang, "menu_no_scooters"))
        await call.answer()
        return

    menu_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🛵 {s['name']}",
                    callback_data=f"scoot_view_{candidate_id}_{s['id']}",
                )
            ]
            for s in scooters
        ]
    )
    await call.message.answer(t(lang, "scooters_intro"), reply_markup=menu_kb)
    await call.answer()


# ---------------- START -> TIL TANLASH ----------------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()

    latest = db.get_latest_candidate_by_tg(message.from_user.id)
    if latest is not None:
        if latest["status"] == "passed":
            # Sinovdan allaqachon o'tgan - qayta anketa so'ralmaydi, faqat menyu ko'rsatiladi
            await send_already_passed_menu(message, latest)
            return

        if latest["status"] == "rejected":
            retry_seconds = db.get_reject_retry_seconds()
            status_updated_at = latest["status_updated_at"] or latest["created_date"]
            try:
                retry_at = compute_retry_at(status_updated_at, retry_seconds)
            except (TypeError, ValueError):
                retry_at = None

            if retry_at is not None and datetime.now() < retry_at:
                lang = latest["lang"] or "uz"
                await message.answer(
                    t(lang, "reject_cooldown", retry_at=format_datetime(retry_at))
                )
                return
            # Muddat o'tgan - qayta urinishga ruxsat, oddiy oqim davom etadi

    if config.WELCOME_STICKER_ID:
        try:
            await bot.send_sticker(message.chat.id, config.WELCOME_STICKER_ID)
        except Exception:
            pass  # stiker ID noto'g'ri/eskirgan bo'lsa - shunchaki o'tkazib yuboramiz

    await message.answer(t("uz", "intro"))
    await message.answer(t("uz", "choose_language"), reply_markup=lang_kb())
    await state.set_state(Form.choosing_language)


@router.callback_query(Form.choosing_language, F.data.in_({"lang_uz", "lang_ru"}))
async def lang_chosen(call: CallbackQuery, state: FSMContext):
    await call.message.edit_reply_markup()
    lang = "uz" if call.data == "lang_uz" else "ru"

    candidate_id = db.create_candidate(
        tg_id=call.from_user.id,
        username=call.from_user.username or "",
        full_name=call.from_user.full_name or "",
        lang=lang,
    )
    await state.update_data(candidate_id=candidate_id, lang=lang)

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, "share_phone_button"), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await call.message.answer(t(lang, "greeting"), reply_markup=kb)
    await state.set_state(Form.waiting_phone)
    await call.answer()


# ---------------- PHONE ----------------

@router.message(Form.waiting_phone, F.contact)
async def got_phone(message: Message, state: FSMContext):
    data = await state.get_data()
    candidate_id = data["candidate_id"]
    lang = data["lang"]
    db.update_candidate(candidate_id, phone=message.contact.phone_number)

    await message.answer(t(lang, "thanks_phone"), reply_markup=ReplyKeyboardRemove())
    await message.answer(t(lang, "ask_age_confirm"), reply_markup=yes_no_kb("age", lang))
    await state.set_state(Form.age)


@router.message(Form.waiting_phone)
async def phone_not_shared(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "uz")
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, "share_phone_button"), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(t(lang, "phone_not_shared"), reply_markup=kb)


# ---------------- AGE (tasdiqlash) ----------------

@router.callback_query(Form.age, F.data.in_({"age_yes", "age_no"}))
async def age_answer(call: CallbackQuery, state: FSMContext, bot: Bot):
    await call.message.edit_reply_markup()
    data = await state.get_data()
    candidate_id = data["candidate_id"]
    lang = data["lang"]

    if call.data == "age_no":
        await reject(call, state, candidate_id, "yosh", lang, bot=bot)
        await call.answer()
        return

    await call.message.answer(t(lang, "ask_passport"), reply_markup=yes_no_kb("passport", lang))
    await state.set_state(Form.passport)
    await call.answer()


# ---------------- PASSPORT ----------------

@router.callback_query(Form.passport, F.data.in_({"passport_yes", "passport_no"}))
async def passport_answer(call: CallbackQuery, state: FSMContext, bot: Bot):
    await call.message.edit_reply_markup()
    data = await state.get_data()
    candidate_id = data["candidate_id"]
    lang = data["lang"]

    if call.data == "passport_no":
        db.update_candidate(candidate_id, passport_ok="Yo'q")
        await reject(call, state, candidate_id, "pasport", lang, bot=bot)
        await call.answer()
        return

    db.update_candidate(candidate_id, passport_ok="Ha")
    await call.message.answer(t(lang, "ask_tashkent"), reply_markup=yes_no_kb("tashkent", lang))
    await state.set_state(Form.tashkent)
    await call.answer()


# ---------------- TASHKENT ----------------

@router.callback_query(Form.tashkent, F.data.in_({"tashkent_yes", "tashkent_no"}))
async def tashkent_answer(call: CallbackQuery, state: FSMContext, bot: Bot):
    await call.message.edit_reply_markup()
    data = await state.get_data()
    candidate_id = data["candidate_id"]
    lang = data["lang"]

    if call.data == "tashkent_no":
        db.update_candidate(candidate_id, in_tashkent="Yo'q")
        await reject(call, state, candidate_id, "toshkent", lang, bot=bot)
        await call.answer()
        return

    db.update_candidate(candidate_id, in_tashkent="Ha")
    await call.message.answer(t(lang, "ask_experience"), reply_markup=yes_no_kb("exp", lang))
    await state.set_state(Form.experience)
    await call.answer()


# ---------------- EXPERIENCE ----------------

@router.callback_query(Form.experience, F.data.in_({"exp_yes", "exp_no"}))
async def experience_answer(call: CallbackQuery, state: FSMContext):
    await call.message.edit_reply_markup()
    data = await state.get_data()
    candidate_id = data["candidate_id"]
    lang = data["lang"]

    answer = "Ha" if call.data == "exp_yes" else "Yo'q"
    db.update_candidate(candidate_id, experience=answer)

    await call.message.answer(t(lang, "ask_transport"), reply_markup=yes_no_kb("transport", lang))
    await state.set_state(Form.transport)
    await call.answer()


# ---------------- TRANSPORT (yakuniy savol) ----------------

@router.callback_query(Form.transport, F.data.in_({"transport_yes", "transport_no"}))
async def transport_answer(call: CallbackQuery, state: FSMContext, bot: Bot):
    await call.message.edit_reply_markup()
    data = await state.get_data()
    candidate_id = data["candidate_id"]
    lang = data["lang"]

    answer = "Ha" if call.data == "transport_yes" else "Yo'q"
    db.update_candidate(
        candidate_id,
        transport=answer,
        status="passed",
        status_updated_at=datetime.now().isoformat(),
    )

    contact_phone = db.get_setting("contact_phone", "—")
    meeting_time = db.get_setting("meeting_time", "—")

    await call.message.answer(
        t(lang, "congrats", meeting_time=meeting_time, contact_phone=contact_phone)
    )

    lat = db.get_setting("location_lat")
    lon = db.get_setting("location_lon")
    if lat and lon:
        await call.message.answer(t(lang, "office_location"))
        await bot.send_location(call.message.chat.id, latitude=float(lat), longitude=float(lon))
    else:
        address_text = db.get_setting("location_address")
        if address_text:
            await call.message.answer(f"{t(lang, 'office_location')} {address_text}")

    # Transport (skuter) menyusi - agar admin panelda qo'shilgan bo'lsa
    scooters = db.list_scooters()
    if scooters:
        menu_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"🛵 {s['name']}",
                        callback_data=f"scoot_view_{candidate_id}_{s['id']}",
                    )
                ]
                for s in scooters
            ]
        )
        await call.message.answer(t(lang, "scooters_intro"), reply_markup=menu_kb)

    # Adminga xabar (har doim o'zbek tilida - admin panel tili)
    candidate = db.get_candidate(candidate_id)
    username_str = f"@{candidate['username']}" if candidate["username"] else "(username yo'q)"
    lang_label = "🇺🇿 UZ" if candidate["lang"] == "uz" else "🇷🇺 RU"
    admin_text = (
        "✅ <b>Yangi nomzod muvaffaqiyatli o'tdi!</b>\n"
        "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
        f"👤 <b>Ism:</b> {candidate['full_name']} {username_str}\n"
        f"🌐 <b>Til:</b> {lang_label}\n"
        f"📞 <b>Telefon:</b> {candidate['phone']}\n"
        f"🪪 <b>Pasport asli:</b> {candidate['passport_ok']}\n"
        f"🏙 <b>Toshkentda:</b> {candidate['in_tashkent']}\n"
        f"💼 <b>Tajriba bormi:</b> {candidate['experience']}\n"
        f"🚗 <b>Transport bormi:</b> {candidate['transport']}"
    )
    admin_ids = [row["tg_id"] for row in db.list_admins()]
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, admin_text)
        except Exception:
            pass

    await state.clear()
    await call.answer()


# ---------------- SKUTER MENYUSI: MODELNI KO'RISH ----------------

@router.callback_query(F.data.startswith("scoot_view_"))
async def scoot_view(call: CallbackQuery, bot: Bot):
    # format: scoot_view_{candidate_id}_{scooter_id}
    parts = call.data.split("_")
    candidate_id = int(parts[2])
    scooter_id = int(parts[3])

    candidate = db.get_candidate(candidate_id)
    scooter = db.get_scooter(scooter_id)
    if not candidate or not scooter:
        await call.answer("Ma'lumot topilmadi.", show_alert=True)
        return

    lang = candidate["lang"] or "uz"
    caption = (
        f"🛵 <b>{scooter['name']}</b>\n"
        "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"{t(lang, 'scooter_free_label')}: {scooter['free_period']}\n"
        f"{t(lang, 'scooter_price_label')}: {scooter['price']}"
    )
    detail_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "want_scooter_button"),
                    callback_data=f"want_scooter_{candidate_id}_{scooter_id}",
                )
            ]
        ]
    )
    if scooter["photo_file_id"]:
        await bot.send_photo(
            call.message.chat.id, scooter["photo_file_id"], caption=caption, reply_markup=detail_kb
        )
    else:
        await call.message.answer(caption, reply_markup=detail_kb)
    await call.answer()


# ---------------- SKUTER TANLASH ----------------

@router.callback_query(F.data.startswith("want_scooter_"))
async def want_scooter(call: CallbackQuery, bot: Bot):
    # format: want_scooter_{candidate_id}_{scooter_id}
    parts = call.data.split("_")
    candidate_id = int(parts[2])
    scooter_id = int(parts[3])

    candidate = db.get_candidate(candidate_id)
    scooter = db.get_scooter(scooter_id)
    if not candidate or not scooter:
        await call.answer("Ma'lumot topilmadi.", show_alert=True)
        return

    lang = candidate["lang"] or "uz"
    await call.answer(t(lang, "scooter_chosen_toast"), show_alert=True)
    await call.message.answer(t(lang, "scooter_chosen_confirm", scooter_name=scooter["name"]))

    # Nomzod yozuviga ham saqlaymiz - statistika/CSV eksportda ko'rinishi uchun
    db.update_candidate(
        candidate_id,
        wants_scooter=scooter["name"],
        scooter_requested_at=date.today().isoformat(),
    )

    username_str = f"@{candidate['username']}" if candidate["username"] else "(username yo'q)"
    admin_text = (
        "🛴 <b>Foydalanuvchi skuter olmoqchi!</b>\n"
        "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
        f"👤 <b>Ism:</b> {candidate['full_name']} {username_str}\n"
        f"📞 <b>Telefon:</b> {candidate['phone'] or '—'}\n"
        f"🛵 <b>Xohlagan skuteri:</b> {scooter['name']} ({scooter['price']})"
    )
    admin_ids = [row["tg_id"] for row in db.list_admins()]
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, admin_text)
        except Exception:
            pass
