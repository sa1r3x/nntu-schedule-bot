import logging

from aiogram import types
from aiogram.types import InputMediaPhoto

import db_manager as db
from config import GROUP_TITLE, URL_MAIN_IMG
from keyboards import get_main_menu_markup, get_subgroup_markup
from parser import NNTUParser

logger = logging.getLogger(__name__)
nntu_parser = NNTUParser()

WELCOME_NEW = (
    f"👋 <b>Привет! Я органайзер группы {GROUP_TITLE}.</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "Выбери свою подгруппу — от этого зависят дедлайны по лабораторным:"
)

SETTINGS_TEXT = (
    "⚙️ <b>Смена подгруппы</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "Нажми кнопку своей подгруппы. Расписание общее для всей группы, "
    "а дедлайны по лабам будут только твои."
)
LAB_MESSAGES: dict[int, list[int]] = {}
DAYS_MAP = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


def welcome_text(subgroup: int | None = None) -> str:
    extra = ""
    if subgroup:
        extra = (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Группа:</b> <code>{GROUP_TITLE}</code>\n"
            f"🔢 <b>Твоя подгруппа:</b> <code>{subgroup}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Выбери нужный раздел:"
        )
        return f"👋 <b>Приветствуем в Органайзере НГТУ!</b>\n{extra}"
    return WELCOME_NEW


async def delete_old_menu(bot, chat_id: int, user_id: int, extra_message_id: int | None = None) -> None:
    ids = []
    if extra_message_id:
        ids.append(extra_message_id)
    last_id = db.get_last_menu_id(user_id)
    if last_id:
        ids.append(last_id)
    for message_id in ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            logger.debug("Не удалось удалить сообщение %s", message_id)

async def clear_lab_messages(bot, chat_id: int, user_id: int) -> None:
    for message_id in LAB_MESSAGES.pop(user_id, []):
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            logger.debug("Не удалось удалить сообщение лабы %s", message_id)

async def send_main_menu(message: types.Message, subgroup: int) -> None:
    sent = await message.answer_photo(
        photo=URL_MAIN_IMG,
        caption=welcome_text(subgroup),
        reply_markup=get_main_menu_markup(),
        parse_mode="HTML",
    )
    db.update_menu_id(message.from_user.id, sent.message_id)


async def send_subgroup_picker(message: types.Message) -> None:
    sent = await message.answer_photo(
        photo=URL_MAIN_IMG,
        caption=welcome_text(),
        reply_markup=get_subgroup_markup(),
        parse_mode="HTML",
    )
    if db.get_user(message.from_user.id):
        db.update_menu_id(message.from_user.id, sent.message_id)


async def edit_to_main_menu(callback: types.CallbackQuery, subgroup: int) -> None:
    await callback.message.edit_media(
        media=InputMediaPhoto(
            media=URL_MAIN_IMG,
            caption=welcome_text(subgroup),
            parse_mode="HTML",
        ),
        reply_markup=get_main_menu_markup(),
    )


async def require_subgroup(callback: types.CallbackQuery) -> int | None:
    subgroup = db.get_user_subgroup(callback.from_user.id)
    if subgroup:
        return subgroup
    logger.warning("Пользователь %s без подгруппы нажал %s", callback.from_user.id, callback.data)
    await callback.message.edit_media(
        media=InputMediaPhoto(
            media=URL_MAIN_IMG,
            caption=welcome_text(),
            parse_mode="HTML",
        ),
        reply_markup=get_subgroup_markup(),
    )
    return None

import asyncio
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import StateFilter
from aiogram.exceptions import TelegramBadRequest

# Этот роутер мы будем импортировать
router = Router()

@router.message(StateFilter("*"))
async def trap_and_delete_user_messages(message: Message):
    if message.text and message.text.startswith("/"):
        return

    try:
        await message.delete()
        warning = await message.answer("⚠️ **Используйте только инлайн-кнопки меню!**")
        await asyncio.sleep(3)
        await warning.delete()
    except TelegramBadRequest:
        pass
    except Exception as e:
        print(f"Ошибка ловушки: {e}")
