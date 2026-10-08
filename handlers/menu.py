import logging

from aiogram import F, Router, types
from aiogram.types import InputMediaPhoto

from config import URL_MAIN_IMG
from handlers.common import SETTINGS_TEXT, clear_lab_messages, edit_to_main_menu, require_subgroup
from keyboards import get_subgroup_markup

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await callback.answer()
    await clear_lab_messages(callback.bot, callback.message.chat.id, callback.from_user.id)
    subgroup = await require_subgroup(callback)
    if not subgroup:
        return
    await edit_to_main_menu(callback, subgroup)

@router.callback_query(F.data == "edit_profile")
async def edit_profile(callback: types.CallbackQuery):
    await callback.answer()
    logger.info("Смена подгруппы: user_id=%s", callback.from_user.id)
    await callback.message.edit_media(
        media=InputMediaPhoto(media=URL_MAIN_IMG, caption=SETTINGS_TEXT, parse_mode="HTML"),
        reply_markup=get_subgroup_markup(),
    )
