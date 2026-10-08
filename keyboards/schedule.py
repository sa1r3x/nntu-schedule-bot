from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_schedule_days_markup(is_next: bool = False):
    builder = InlineKeyboardBuilder()
    week_flag = "next" if is_next else "curr"

    builder.button(text="Пн", callback_data=f"sch:{week_flag}:Понедельник")
    builder.button(text="Вт", callback_data=f"sch:{week_flag}:Вторник")
    builder.button(text="Ср", callback_data=f"sch:{week_flag}:Среда")
    builder.button(text="Чт", callback_data=f"sch:{week_flag}:Четверг")
    builder.button(text="Пт", callback_data=f"sch:{week_flag}:Пятница")
    builder.button(text="Сб", callback_data=f"sch:{week_flag}:Суббота")

    if is_next:
        builder.button(text="• Текущая неделя •", callback_data="set_week:curr")
    else:
        builder.button(text="• Следующая неделя •", callback_data="set_week:next")

    builder.button(text="◀️ Вернуться в главное меню", callback_data="back_to_menu")
    builder.adjust(6, 1, 1)
    return builder.as_markup()
