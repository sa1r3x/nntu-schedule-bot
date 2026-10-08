import base64
import datetime
import json
import logging
import os
import re

import requests

import db_manager as db

logger = logging.getLogger(__name__)

DEFAULT_TIMES = {
    1: "08:00 - 09:35",
    2: "09:45 - 11:20",
    3: "11:35 - 13:10",
    4: "13:40 - 15:15",
    5: "15:25 - 17:00",
    6: "17:10 - 18:45",
}

MONTHS_MAP = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

DAY_ALIASES = {
    "понедельник": ("понедельник", "пн", "monday"),
    "вторник": ("вторник", "вт", "tuesday"),
    "среда": ("среда", "ср", "wednesday"),
    "четверг": ("четверг", "чт", "thursday"),
    "пятница": ("пятница", "пт", "friday"),
    "суббота": ("суббота", "сб", "saturday"),
    "воскресенье": ("воскресенье", "вс", "sunday"),
}


class NNTUParser:
    def __init__(self):
        self.base_url = "https://lks-api.nntu.ru"
        self._token_status_logged = False

    def _lks_token(self) -> str:
        token = (os.getenv("LKS_TOKEN") or "").strip().strip('"').strip("'")
        if not token:
            logger.error("LKS_TOKEN пустой: проверь файл .env")
        elif not self._token_status_logged:
            self._log_token_expiry(token)
            self._token_status_logged = True
        return token

    @staticmethod
    def _log_token_expiry(token: str) -> None:
        try:
            payload_b64 = token.split(".")[1]
            pad = "=" * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64 + pad))
            exp = datetime.datetime.fromtimestamp(int(payload["exp"]))
            now = datetime.datetime.now()
            if now >= exp:
                logger.error(
                    "LKS_TOKEN истёк %s (сейчас %s). Обнови токен в .env из личного кабинета НГТУ.",
                    exp.isoformat(sep=" ", timespec="seconds"),
                    now.isoformat(sep=" ", timespec="seconds"),
                )
            else:
                logger.info("LKS_TOKEN действителен до %s", exp.isoformat(sep=" ", timespec="seconds"))
        except Exception:
            logger.debug("Не удалось прочитать срок действия JWT", exc_info=True)

    def fetch_week_data(self, target_date: datetime.date) -> list:
        url = f"{self.base_url}/lesson-schedule/schedule/lks"
        date_iso = f"{target_date.strftime('%Y-%m-%d')}T13:30:13.844Z"
        token = self._lks_token()
        headers = {
            "Host": "lks-api.nntu.ru",
            "Authorization": f"Bearer {token}",
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }

        logger.info("Запрос расписания: url=%s date=%s", url, date_iso)

        try:
            response = requests.get(url, headers=headers, params={"date": date_iso}, timeout=15)
        except Exception:
            logger.exception("Сетевая ошибка при скачивании недели %s", target_date)
            return []

        logger.info(
            "Ответ ЛК: status=%s content_type=%s body_len=%s",
            response.status_code,
            response.headers.get("content-type"),
            len(response.text or ""),
        )

        if response.status_code != 200:
            snippet = (response.text or "")[:300].replace("\n", " ")
            logger.error("ЛК вернул %s, тело: %r", response.status_code, snippet)
            return []

        try:
            payload = response.json()
        except Exception:
            logger.exception("Не JSON в ответе ЛК: %r", (response.text or "")[:300])
            return []

        if not isinstance(payload, dict):
            logger.error("Ожидали объект JSON, получили %s", type(payload))
            return []

        logger.info("Ключи ответа ЛК: %s", list(payload.keys()))
        daily = payload.get("dailySchedule")
        if daily is None:
            logger.warning("Поле dailySchedule отсутствует или null. payload=%s", payload)
            return []
        if not isinstance(daily, list):
            logger.error("dailySchedule не список: %s", type(daily))
            return []
        if not daily:
            logger.warning("dailySchedule пустой массив на дату %s", target_date)
            return []

        titles = [str(day.get("dayOfTheWeek", "")) for day in daily if isinstance(day, dict)]
        logger.info("Получено дней: %s, заголовки: %s", len(daily), titles)
        return daily

    def get_clean_schedule(self, *args, **kwargs) -> str:
        target_day = kwargs.get("target_day", args[1] if len(args) > 1 else "Среда")
        is_next_week = kwargs.get("is_next_week", False)
        if len(args) > 3 and isinstance(args[3], bool):
            is_next_week = args[3]

        if isinstance(target_day, list):
            target_day = target_day[-1]

        user_id = kwargs.get("user_id", args[2] if len(args) > 2 else None)
        target_schedule = self._week_schedule(is_next_week=is_next_week, user_id=user_id)
        if not target_schedule:
            logger.warning("Пустая сетка недели is_next_week=%s day=%s", is_next_week, target_day)
            return (
                "⚠️ <b>Расписание не получено из ЛК.</b>\n"
                "Проверь консоль бота: часто это истёкший <code>LKS_TOKEN</code> в .env "
                "или пустой ответ API."
            )

        matched_days = [day for day in target_schedule if self._day_matches(day, target_day)]
        if not matched_days:
            titles = [str(day.get("dayOfTheWeek", "")) for day in target_schedule]
            logger.warning(
                "День %r не найден в сетке. Доступные заголовки: %s",
                target_day,
                titles,
            )
            return f"🎉 <b>В день ({str(target_day).upper()}) пар нет! Отдыхай.</b>"

        output = ""
        for day in matched_days:
            lessons = day.get("lessonElements") or []
            if not lessons:
                logger.info("Пустой lessonElements для %s", day.get("dayOfTheWeek"))
                continue
            try:
                lessons = sorted(lessons, key=lambda x: int(x.get("timeIndex") or 0))
            except Exception:
                logger.exception("Не удалось отсортировать пары")

            for lesson in lessons:
                line = self._format_lesson(lesson, show_subgroup=True)
                if line:
                    output += line

        if not output:
            logger.info("После разбора пар текст пустой, день=%s", target_day)
            return f"🎉 <b>В день ({str(target_day).upper()}) пар нет! Отдыхай.</b>"
        return output

    def get_deadlines_for_subgroup(self, subgroup: int, user_id: int | None = None) -> list[dict]:
        today = datetime.date.today()
        horizon = today + datetime.timedelta(days=7)
        all_days = self.fetch_week_data(today) + self.fetch_week_data(today + datetime.timedelta(days=7))
        if not all_days:
            logger.warning("Дедлайны: обе недели пустые, подгруппа=%s", subgroup)
            return []

        labs: list[dict] = []
        for day in all_days:
            due_date = self._parse_day_date(day)
            if due_date is None or due_date < today or due_date > horizon:
                continue
            lessons = day.get("lessonElements") or []
            for lesson in lessons:
                if not self._is_lab(lesson):
                    continue
                lesson_groups = self._lesson_subgroups(lesson)
                if lesson_groups is not None and subgroup not in lesson_groups:
                    logger.debug(
                        "Пропуск чужой лабы %s (подгруппы %s, нужна %s)",
                        lesson.get("subject"),
                        lesson_groups,
                        subgroup,
                    )
                    continue
                subject = str(lesson.get("subject") or "").strip()
                if not subject:
                    continue
                room = lesson.get("room") or "—"
                labs.append({
                    "lab_name": subject,
                    "due_date": due_date.strftime("%d.%m"),
                    "due_iso": due_date.isoformat(),
                    "room": room,
                    "subgroup": subgroup,
                })
                if user_id:
                    db.add_auto_deadline(user_id, subject, due_date.strftime("%d.%m"), room, subgroup)

        labs.sort(key=lambda item: item["due_iso"])
        logger.info("Дедлайны подгруппы %s на неделю вперёд: %s шт.", subgroup, len(labs))
        return labs

    def _week_schedule(self, is_next_week: bool, user_id=None) -> list:
        today = datetime.date.today()
        current_week = self.fetch_week_data(today)
        next_week = self.fetch_week_data(today + datetime.timedelta(days=7))
        if user_id:
            self._collect_deadlines_cache(user_id, current_week + next_week)
        return next_week if is_next_week else current_week

    def _collect_deadlines_cache(self, user_id: int, days: list) -> None:
        for day in days:
            due_date = self._parse_day_date(day)
            if due_date is None:
                continue
            for lesson in day.get("lessonElements") or []:
                if not self._is_lab(lesson):
                    continue
                subject = str(lesson.get("subject") or "").strip()
                if not subject:
                    continue
                groups = self._lesson_subgroups(lesson)
                room = lesson.get("room") or "—"
                if groups is None:
                    db.add_auto_deadline(user_id, subject, due_date.strftime("%d.%m"), room, None)
                else:
                    for group_no in groups:
                        db.add_auto_deadline(user_id, subject, due_date.strftime("%d.%m"), room, group_no)

    def _parse_day_date(self, day: dict) -> datetime.date | None:
        raw_title = str(day.get("dayOfTheWeek") or "").strip()
        if "," in raw_title:
            try:
                date_part = raw_title.split(",")[-1].strip().lower()
                day_num, month_name = date_part.split()
                month_num = MONTHS_MAP.get(month_name)
                if not month_num:
                    logger.warning("Неизвестный месяц в заголовке дня: %r", raw_title)
                    return None
                year = datetime.date.today().year
                parsed = datetime.date(year, month_num, int(day_num))
                if parsed.month == 1 and datetime.date.today().month == 12:
                    parsed = datetime.date(year + 1, month_num, int(day_num))
                return parsed
            except Exception:
                logger.exception("Не разобрали дату из заголовка %r", raw_title)
        for key in ("date", "dayDate", "lessonDate"):
            raw = day.get(key)
            if not raw:
                continue
            try:
                return datetime.date.fromisoformat(str(raw)[:10])
            except Exception:
                logger.debug("Не разобрали поле %s=%r", key, raw)
        return None

    @staticmethod
    def _day_matches(day: dict, target_day: str) -> bool:
        raw = str(day.get("dayOfTheWeek") or "").strip().lower()
        wanted = str(target_day).strip().lower()
        aliases = DAY_ALIASES.get(wanted, (wanted,))
        return any(alias in raw for alias in aliases)

    @staticmethod
    def _is_lab(lesson: dict) -> bool:
        study_type = str(lesson.get("studyType") or "").lower()
        subject = str(lesson.get("subject") or "").lower()
        return "лаб" in study_type or "лаб" in subject

    @staticmethod
    def _lesson_subgroups(lesson: dict) -> set[int] | None:
        for key in ("subGroup", "subgroup", "subGroupNumber", "subgroupNumber", "sub_group", "groupNumber"):
            value = lesson.get(key)
            if value is None or str(value).strip() in ("", "0", "None"):
                continue
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if number in (1, 2, 3):
                return {number}

        chunks = [
            str(lesson.get("subject") or ""),
            str(lesson.get("studyType") or ""),
            str(lesson.get("room") or ""),
            str(lesson.get("comment") or ""),
            str(lesson.get("note") or ""),
            str(lesson.get("stream") or ""),
            str(lesson.get("groups") or ""),
        ]
        blob = " ".join(chunks)
        found: set[int] = set()
        patterns = [
            r"(?:подгрупп[аые]?|п/?г|пг)\s*[:.\-]?\s*([123])",
            r"([123])\s*(?:подгрупп[аые]?|п/?г|пг)",
            r"/([123])(?:\b|$)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, blob, flags=re.IGNORECASE):
                found.add(int(match.group(1)))
        return found or None

    @staticmethod
    def _format_lesson(lesson: dict, show_subgroup: bool = False) -> str:
        subject = lesson.get("subject")
        if not subject or str(subject).strip() == "":
            return ""

        room = lesson.get("room", "—")
        study_type = str(lesson.get("studyType") or "").lower()
        try:
            time_index = int(lesson.get("timeIndex") or 0)
        except (TypeError, ValueError):
            time_index = 0
        lesson_time = DEFAULT_TIMES.get(time_index, f"{time_index} пара")

        if "лаб" in study_type or "лаб" in str(subject).lower():
            prefix = "🧪 <b>ЛАБОРАТОРНАЯ</b>"
        elif "прак" in study_type:
            prefix = "📝 <b>ПРАКТИКА</b>"
        else:
            prefix = "📘 <b>ЛЕКЦИЯ</b>"

        extra = ""
        if show_subgroup:
            groups = NNTUParser._lesson_subgroups(lesson)
            if groups:
                extra = f"\n👥 Подгруппа: {', '.join(str(n) for n in sorted(groups))}"

        return (
            f"{prefix}\n"
            f"⏰ <b>{lesson_time}</b>\n"
            f"📖 {subject}{extra}\n"
            f"🏛 Аудитория: <code>{room}</code>\n"
            f"────────────────━━━━\n"
        )
