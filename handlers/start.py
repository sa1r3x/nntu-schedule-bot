import logging

from aiogram import F, Router, types
from aiogram.filters import Command

import db_manager as db
from config import GROUP_CODE, VALID_SUBGROUPS
from handlers.common import (
    delete_old_menu,
    edit_to_main_menu,
    send_subgroup_picker,
)
logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    try:
        await message.delete()
    except Exception:
        logger.debug("Не удалось удалить /start")

    await delete_old_menu(message.bot, message.chat.id, message.from_user.id)
    logger.info(" /start от user_id=%s", message.from_user.id)
    await send_subgroup_picker(message)


@router.callback_query(F.data.startswith("set_subgroup:"))
async def set_subgroup(callback: types.CallbackQuery):
    try:
        subgroup = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        logger.error("Битый callback выбора подгруппы: %s", callback.data)
        await callback.answer("Некорректная кнопка", show_alert=True)
        return

    if subgroup not in VALID_SUBGROUPS:
        logger.error("Подгруппа вне диапазона 1–3: %s", subgroup)
        await callback.answer("Можно выбрать только 1, 2 или 3 подгруппу", show_alert=True)
        return

    await callback.answer()
    db.save_user(callback.from_user.id, subgroup, GROUP_CODE, GROUP_CODE)
    db.update_menu_id(callback.from_user.id, callback.message.message_id)
    logger.info("user_id=%s выбрал подгруппу %s", callback.from_user.id, subgroup)
    await edit_to_main_menu(callback, subgroup)
