import logging

from aiogram import F, Router, types

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.photo)
async def get_photo_file_id(message: types.Message):
    photo_id = message.photo[-1].file_id
    try:
        await message.delete()
    except Exception:
        logger.debug("Не удалось удалить фото пользователя")

    await message.answer(
        "⬇️ <b>Успешно! Вот file_id твоей картинки:</b>\n\n"
        f"<code>{photo_id}</code>\n\n"
        "Скопируй эту строку и вставь в константы кода.",
        parse_mode="HTML",
    )
