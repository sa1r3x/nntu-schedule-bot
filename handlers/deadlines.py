import asyncio
import datetime
import html
import logging

from aiogram import F, Router, types
from aiogram.types import InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder

import db_manager as db
from config import URL_DEAD_IMG
from handlers.common import LAB_MESSAGES, clear_lab_messages, nntu_parser, require_subgroup
from keyboards import get_back_markup

logger = logging.getLogger(__name__)
router = Router()


def build_lab_text(lab: dict, status: str) -> str:
    labels = {
        "debt": "🔴 [ПРОСРОЧЕНО / ДОЛГ]",
        "upcoming": "⏳ [АКТУАЛЬНО]",
        "done": "🟢 [СДАНО]",
    }
    due = datetime.date.fromisoformat(str(lab["due_iso"])[:10]).strftime("%d.%m.%Y")
    return (
        f"<b>{labels.get(status, status)}</b>\n"
        f"└ 📅 Дедлайн: <b>{due}</b>\n"
        f"└ 📚 <i>{html.escape(str(lab['lab_name']))}</i>\n"
        f"└ 🏛 Ауд: <code>{html.escape(str(lab['room'] or '—'))}</code>"
    )


def get_done_lab_markup(lab_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Отметить как сданную", callback_data=f"done_lab_{lab_id}")
    return builder.as_markup()


@router.callback_query(F.data == "view_deadlines")
async def view_deadlines(callback: types.CallbackQuery):
    await callback.answer()
    subgroup = await require_subgroup(callback)
    if not subgroup:
        return

    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    logger.info("Запрос дедлайнов user_id=%s subgroup=%s", user_id, subgroup)

    await clear_lab_messages(callback.bot, chat_id, user_id)

    header = (
        f"⏳ <b>Лабораторные — {subgroup} подгруппа</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
    )
    labs = []
    try:
        labs = await asyncio.to_thread(
            nntu_parser.get_deadlines_for_subgroup,
            subgroup,
            user_id,
        )
        debts = sum(1 for lab in labs if lab["status"] == "debt")
        upcoming = sum(1 for lab in labs if lab["status"] == "upcoming")
        done = sum(1 for lab in labs if lab["status"] == "done")
        if not labs:
            header += "🎉 <b>Долгов и актуальных лаб нет!</b>"
        else:
            header += (
                f"🔴 Долгов: <b>{debts}</b>\n"
                f"⏳ Актуально (14 дней): <b>{upcoming}</b>\n"
                f"🟢 Сдано, срок ещё не наступил: <b>{done}</b>\n\n"
                "Лабы ниже ⬇️. Нажми «✅ Отметить как сданную» под сданной лабой."
            )
    except Exception:
        logger.exception("Ошибка построения дедлайнов")
        header += "❌ <b>Не удалось получить дедлайны.</b> Смотри лог в консоли."

    try:
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=URL_DEAD_IMG,
                caption=header[:1024],
                parse_mode="HTML",
            ),
            reply_markup=get_back_markup(),
        )
    except Exception:
        logger.exception("Ошибка Telegram в view_deadlines")

    sent_ids = LAB_MESSAGES.setdefault(user_id, [])
    for lab in labs:
        try:
            markup = None if lab["status"] == "done" else get_done_lab_markup(lab["id"])
            sent = await callback.message.answer(
                build_lab_text(lab, lab["status"]),
                reply_markup=markup,
                parse_mode="HTML",
            )
            sent_ids.append(sent.message_id)
            await asyncio.sleep(0.05)
        except Exception:
            logger.exception("Не удалось отправить лабу id=%s", lab.get("id"))


@router.callback_query(F.data.startswith("done_lab_"))
async def mark_lab_done(callback: types.CallbackQuery):
    try:
        lab_id = int(callback.data.removeprefix("done_lab_"))
    except ValueError:
        logger.error("Битый callback отметки лабы: %s", callback.data)
        await callback.answer("Некорректная кнопка", show_alert=True)
        return

    user_id = callback.from_user.id
    lab = await asyncio.to_thread(db.get_lab_by_id, lab_id)
    if not lab:
        await callback.answer("Лаба не найдена", show_alert=True)
        return

    ok = await asyncio.to_thread(db.mark_lab_completed, user_id, lab_id)
    if not ok:
        await callback.answer("Не удалось сохранить отметку", show_alert=True)
        return

    status = db.get_lab_status(lab["due_iso"], True)
    if status is None:
        # Дедлайн наступил или прошёл — сданная лаба скрывается
        try:
            await callback.message.delete()
        except Exception:
            logger.debug("Не удалось удалить сообщение лабы, правим текст")
            try:
                await callback.message.edit_text("✅ Лаба сдана и скрыта.", reply_markup=None)
            except Exception:
                logger.debug("Не удалось отредактировать сообщение лабы")
        ids = LAB_MESSAGES.get(user_id, [])
        if callback.message.message_id in ids:
            ids.remove(callback.message.message_id)
        await callback.answer("✅ Долг закрыт, лаба скрыта")
    else:
        # Дедлайн в будущем — показываем 🟢 [СДАНО]
        try:
            await callback.message.edit_text(
                build_lab_text(lab, "done"),
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception:
            logger.exception("Не удалось обновить сообщение лабы")
        await callback.answer("🟢 Отмечено как сданное")