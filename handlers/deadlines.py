import asyncio
import logging

from aiogram import F, Router, types
from aiogram.types import InputMediaPhoto

from config import URL_DEAD_IMG
from handlers.common import nntu_parser, require_subgroup
from keyboards import get_back_markup

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "view_deadlines")
async def view_deadlines(callback: types.CallbackQuery):
    await callback.answer()
    subgroup = await require_subgroup(callback)
    if not subgroup:
        return

    logger.info("Запрос дедлайнов user_id=%s subgroup=%s", callback.from_user.id, subgroup)
    deadlines_text = (
        f"⏳ <b>Дедлайны по лабораторным — {subgroup} подгруппа</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Показаны только твои лабы на 7 дней вперёд.\n\n"
    )

    try:
        labs = await asyncio.to_thread(
            nntu_parser.get_deadlines_for_subgroup,
            subgroup,
            callback.from_user.id,
        )
        if not labs:
            logger.warning("Пустой список лаб для подгруппы %s", subgroup)
            deadlines_text += (
                "🎉 <b>На ближайшую неделю лаб не найдено.</b>\n\n"
                "Если пары в расписании есть, а здесь пусто — смотри логи: "
                "истёкший LKS_TOKEN или лаба размечена как чужая подгруппа."
            )
        else:
            for lab in labs:
                deadlines_text += (
                    f"🟩 <b>До {lab['due_date']}:</b>\n"
                    f"└ 📚 <i>{lab['lab_name']}</i>\n"
                    f"└ 🏛 Ауд: <code>{lab['room']}</code>\n\n"
                )
            deadlines_text += "📊 <i>Данные выкачаны из сетки занятий НГТУ только для твоей подгруппы.</i>"
    except Exception:
        logger.exception("Ошибка построения дедлайнов")
        deadlines_text += "❌ <b>Не удалось получить дедлайны.</b> Смотри лог в консоли."

    if len(deadlines_text) > 1024:
        deadlines_text = deadlines_text[:1000] + "\n…"

    try:
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=URL_DEAD_IMG,
                caption=deadlines_text,
                parse_mode="HTML",
            ),
            reply_markup=get_back_markup(),
        )
    except Exception:
        logger.exception("Ошибка Telegram в view_deadlines")
