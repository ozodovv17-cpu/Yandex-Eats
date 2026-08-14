"""
Majburiy obuna (force-subscribe) moduli.

Admin panel orqali qo'shilgan kanal/guruhlarga foydalanuvchi obuna
bo'lmaguncha, botning oddiy (user) funksiyalaridan foydalana olmaydi.
Adminlar bu tekshiruvdan har doim ozod qilinadi.
"""

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from aiogram import BaseMiddleware, Router, F
from aiogram.types import (
    TelegramObject,
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.exceptions import TelegramAPIError

import database as db
from i18n import t

log = logging.getLogger("bot.force_sub")

router = Router()

# Foydalanuvchi "obuna" deb hisoblanadigan statuslar
SUBSCRIBED_STATUSES = {"member", "administrator", "creator"}


def _channel_url(channel) -> Optional[str]:
    """Kanal/guruh uchun bosiladigan havolani qaytaradi (mavjud bo'lsa)."""
    if channel["invite_link"]:
        return channel["invite_link"]
    chat_id = channel["chat_id"] or ""
    if chat_id.startswith("@"):
        return f"https://t.me/{chat_id.lstrip('@')}"
    return None


def _user_lang(user_id: int) -> str:
    candidate = db.get_latest_candidate_by_tg(user_id)
    if candidate and candidate["lang"]:
        return candidate["lang"]
    return "uz"


async def get_missing_channels(bot, user_id: int) -> List:
    """Foydalanuvchi hali obuna bo'lmagan kanal/guruhlar ro'yxatini qaytaradi."""
    channels = db.list_forced_channels()
    missing = []
    for channel in channels:
        try:
            member = await bot.get_chat_member(chat_id=channel["chat_id"], user_id=user_id)
            if member.status not in SUBSCRIBED_STATUSES:
                missing.append(channel)
        except TelegramAPIError as e:
            # Bot o'sha kanal/guruhda admin bo'lmasa yoki chat topilmasa -
            # tekshira olmaymiz, foydalanuvchini bloklamaslik uchun o'tkazib yuboramiz,
            # lekin logga yozib qo'yamiz, admin muammoni ko'rsin.
            log.warning(
                "Obunani tekshirib bo'lmadi (chat_id=%s, user_id=%s): %s",
                channel["chat_id"], user_id, e,
            )
            continue
    return missing


def build_subscribe_kb(missing: List, lang: str) -> InlineKeyboardMarkup:
    rows = []
    for channel in missing:
        url = _channel_url(channel)
        if url:
            rows.append([InlineKeyboardButton(text=f"📢 {channel['title']}", url=url)])
        else:
            # Havola topilmadi (masalan, yopiq guruh va invite link olinmagan) -
            # baribir nomini ko'rsatamiz, lekin tugma bosilmaydigan bo'lmasin deb o'tkazib yuboramiz
            rows.append([InlineKeyboardButton(text=f"📢 {channel['title']}", callback_data="noop_force_sub")])
    rows.append(
        [InlineKeyboardButton(text=t(lang, "check_subscription_button"), callback_data="check_sub")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


class ForceSubMiddleware(BaseMiddleware):
    """
    Foydalanuvchi kerakli kanal/guruhlarga obuna bo'lmaguncha, hodisani
    haqiqiy handlerga yubormaydi - o'rniga obuna bo'lish taklifini ko'rsatadi.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        bot = data.get("bot")
        user = data.get("event_from_user")

        if bot is None or user is None:
            return await handler(event, data)

        # Adminlar tekshiruvdan ozod
        try:
            if db.is_admin(user.id):
                return await handler(event, data)
        except Exception:
            pass

        # "✅ Tekshirish" tugmasi alohida handlerda ishlanadi - middleware'da o'tkazib yuboramiz
        if isinstance(event, CallbackQuery) and event.data in ("check_sub", "noop_force_sub"):
            return await handler(event, data)

        try:
            channels = db.list_forced_channels()
        except Exception:
            channels = []

        if not channels:
            return await handler(event, data)

        try:
            missing = await get_missing_channels(bot, user.id)
        except Exception as e:
            log.warning("Obunani tekshirishda kutilmagan xatolik: %s", e)
            return await handler(event, data)

        if not missing:
            return await handler(event, data)

        lang = _user_lang(user.id)
        text = t(lang, "force_sub_text")
        kb = build_subscribe_kb(missing, lang)

        try:
            if isinstance(event, CallbackQuery):
                await event.answer()
                if event.message:
                    await event.message.answer(text, reply_markup=kb)
            elif isinstance(event, Message):
                await event.answer(text, reply_markup=kb)
        except TelegramAPIError as e:
            log.warning("Obuna talabini yuborib bo'lmadi: %s", e)

        return  # Foydalanuvchi obuna bo'lguncha asosiy handlerga o'tkazilmaydi


@router.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery, bot):
    user_id = call.from_user.id
    lang = _user_lang(user_id)

    try:
        missing = await get_missing_channels(bot, user_id)
    except Exception as e:
        log.warning("check_sub: tekshirishda xatolik: %s", e)
        await call.answer()
        return

    if missing:
        kb = build_subscribe_kb(missing, lang)
        try:
            await call.message.edit_reply_markup(reply_markup=kb)
        except TelegramAPIError:
            pass
        await call.answer(t(lang, "force_sub_still_missing"), show_alert=True)
        return

    try:
        await call.message.edit_text(t(lang, "force_sub_success"))
    except TelegramAPIError:
        await call.message.answer(t(lang, "force_sub_success"))
    await call.answer()


@router.callback_query(F.data == "noop_force_sub")
async def noop_force_sub(call: CallbackQuery):
    await call.answer()
