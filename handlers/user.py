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

router = Router()


class Form(StatesGroup):
    choosing_language = State()
    waiting_phone = State()
    age = State()
    age_number = State()
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
    "yosh_raqam": "Yoshi 18 dan kichik (aniq yoshda)",
    "pasport": "Pasport nusxasi yo'q",
    "toshkent": "Toshkentda emas",
}


async def reject(message_or_call, state: FSMContext, candidate_id: int, step: str, lang: str, bot: Bot = None):
    db.update_candidate(candidate_id, status="rejected", reject_step=step)
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
        age_str = candidate["age"] if candidate["age"] is not None else "—"
        admin_text = (
            "🚫 Nomzod rad etildi\n\n"
            f"👤 Ism: {candidate['full_name']} {username_str}\n"
            f"📞 Telefon: {phone_str}\n"
            f"🎂 Yosh: {age_str}\n"
            f"❗️ Sabab: {label}"
        )
        admin_ids = [row["tg_id"] for row in db.list_admins()]
        for admin_id in admin_ids:
            try:
                await bot.send_message(admin_id, admin_text)
            except Exception:
                pass


# ---------------- START -> TIL TANLASH ----------------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()

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

    await call.message.answer(t(lang, "ask_age_number"))
    await state.set_state(Form.age_number)
    await call.answer()


# ---------------- AGE (aniq raqam) ----------------

@router.message(Form.age_number)
async def age_number_answer(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    lang = data["lang"]
    text = (message.text or "").strip()

    if not text.isdigit():
        await message.answer(t(lang, "age_not_digit"))
        return

    age = int(text)
    if age < 14 or age > 90:
        await message.answer(t(lang, "age_out_of_range"))
        return

    candidate_id = data["candidate_id"]
    db.update_candidate(candidate_id, age=age)

    if age < 18:
        # Foydalanuvchi oldin "18 yoshga to'lganman" degan bo'lsa-da, aniq
        # yoshni kiritganda 18 dan kichik chiqsa - xavfsizlik uchun rad etamiz
        await reject(message, state, candidate_id, "yosh_raqam", lang, bot=bot)
        return

    await message.answer(t(lang, "ask_passport"), reply_markup=yes_no_kb("passport", lang))
    await state.set_state(Form.passport)


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
    db.update_candidate(candidate_id, transport=answer, status="passed")

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

    # Transport (skuter) takliflari - agar admin panelda qo'shilgan bo'lsa
    scooters = db.list_scooters()
    if scooters:
        await call.message.answer(t(lang, "scooters_intro"))
        for s in scooters:
            caption = (
                f"🛵 {s['name']}\n"
                f"⏳ {t(lang, 'scooter_free_label')}: {s['free_period']}\n"
                f"💵 {t(lang, 'scooter_price_label')}: {s['price']}"
            )
            scooter_kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=t(lang, "want_scooter_button"),
                            callback_data=f"want_scooter_{candidate_id}_{s['id']}",
                        )
                    ]
                ]
            )
            if s["photo_file_id"]:
                await bot.send_photo(
                    call.message.chat.id, s["photo_file_id"], caption=caption, reply_markup=scooter_kb
                )
            else:
                await call.message.answer(caption, reply_markup=scooter_kb)

    # Adminga xabar (har doim o'zbek tilida - admin panel tili)
    candidate = db.get_candidate(candidate_id)
    username_str = f"@{candidate['username']}" if candidate["username"] else "(username yo'q)"
    lang_label = "🇺🇿 UZ" if candidate["lang"] == "uz" else "🇷🇺 RU"
    admin_text = (
        "✅ Yangi nomzod kuryerlik so'rovidan muvaffaqiyatli o'tdi!\n\n"
        f"👤 Ism: {candidate['full_name']} {username_str}\n"
        f"🌐 Til: {lang_label}\n"
        f"📞 Telefon: {candidate['phone']}\n"
        f"🎂 Yosh: {candidate['age']}\n"
        f"🪪 Pasport nusxasi: {candidate['passport_ok']}\n"
        f"🏙 Toshkentda: {candidate['in_tashkent']}\n"
        f"💼 Tajriba bormi? ({candidate['experience']})\n"
        f"🚗 Transport bormi? ({candidate['transport']})"
    )
    admin_ids = [row["tg_id"] for row in db.list_admins()]
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, admin_text)
        except Exception:
            pass

    await state.clear()
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

    username_str = f"@{candidate['username']}" if candidate["username"] else "(username yo'q)"
    admin_text = (
        "🛒 Nomzod skuter tanladi!\n\n"
        f"👤 Ism: {candidate['full_name']} {username_str}\n"
        f"📞 Telefon: {candidate['phone'] or '—'}\n"
        f"🛵 Tanlagan skuteri: {scooter['name']} ({scooter['price']})"
    )
    admin_ids = [row["tg_id"] for row in db.list_admins()]
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, admin_text)
        except Exception:
            pass
