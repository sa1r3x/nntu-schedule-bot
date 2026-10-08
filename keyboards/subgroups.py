from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_subgroup_markup():
    builder = InlineKeyboardBuilder()
    builder.button(text="1 подгруппа", callback_data="set_subgroup:1")
    builder.button(text="2 подгруппа", callback_data="set_subgroup:2")
    builder.button(text="3 подгруппа", callback_data="set_subgroup:3")
    builder.adjust(1)
    return builder.as_markup()
