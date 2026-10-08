import asyncio
import datetime
import logging

from aiogram import F, Router, types
from aiogram.types import InputMediaPhoto

from config import GROUP_TITLE, URL_SCHED_IMG
from handlers.common import DAYS_MAP, nntu_parser, require_subgroup
from keyboards import get_schedule_days_markup

logger = logging.getLogger(__name__)
router = Router()


def _today_name() -> str:
    current_day_num = datetime.datetime.now().weekday()
    return "Понедельник" if current_day_num == 6 else DAYS_MAP[current_day_num]


async def _render_schedule(callback: types.CallbackQuery, target_day: str, is_next: bool) -> None:
    week_title = "СЛЕДУЮЩАЯ НЕДЕЛЯ" if is_next else "ТЕКУЩАЯ НЕДЕЛЯ"
    markup = get_schedule_days_markup(is_next=is_next)

    await callback.message.edit_media(
        media=InputMediaPhoto(
            media=URL_SCHED_IMG,
            caption="🔄 <b>Загрузка расписания...</b>",
            parse_mode="HTML",
        ),
        reply_markup=markup,
    )

    logger.info(
        "Запрос расписания user_id=%s day=%s next_week=%s",
        callback.from_user.id,
        target_day,
        is_next,
    )

    schedule_result = await asyncio.to_thread(
        nntu_parser.get_clean_schedule,
        target_day=target_day,
        user_id=callback.from_user.id,
        is_next_week=is_next,
    )

    if not schedule_result or "не получено" in schedule_result.lower():
        logger.warning("Пустой/ошибочный ответ расписания для дня %s", target_day)

    caption = (
        f"📆 <b>РАСПИСАНИЕ {GROUP_TITLE} ({week_title} — {target_day.upper()})</b>\n"
        f"👥 Общая сетка для всех трёх подгрупп\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{schedule_result}"
    )
    if len(caption) > 1024:
        caption = caption[:1000] + "\n…"

    await callback.message.edit_caption(
        caption=caption,
        reply_markup=markup,
        parse_mode="HTML",
    )


@router.callback_query(F.data == "view_schedule")
async def view_schedule(callback: types.CallbackQuery):
    await callback.answer()
    if not await require_subgroup(callback):
        return
    await _render_schedule(callback, _today_name(), is_next=False)


@router.callback_query(F.data.startswith("sch:"))
async def process_schedule_day_switch(callback: types.CallbackQuery):
    await callback.answer()
    if not await require_subgroup(callback):
        return
    _, week_flag, target_day = callback.data.split(":")
    await _render_schedule(callback, target_day, is_next=(week_flag == "next"))


@router.callback_query(F.data.startswith("set_week:"))
async def process_week_toggle(callback: types.CallbackQuery):
    await callback.answer()
    if not await require_subgroup(callback):
        return
    week_type = callback.data.split(":")[-1]
    await _render_schedule(callback, "Среда", is_next=(week_type == "next"))
