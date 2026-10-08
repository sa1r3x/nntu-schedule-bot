from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_main_menu_markup():
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Посмотреть расписание пар", callback_data="view_schedule")
    builder.button(text="⏳ Контроль дедлайнов по лабам", callback_data="view_deadlines")
    builder.button(text="⚙️ Настройки и изменение профиля", callback_data="edit_profile")
    builder.adjust(1)
    return builder.as_markup()


def get_back_markup():
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Вернуться в главное меню", callback_data="back_to_menu")
    return builder.as_markup()
