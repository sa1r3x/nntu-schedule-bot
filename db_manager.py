import datetime
import logging
import sqlite3

from config import DB_PATH, GROUP_CODE, VALID_SUBGROUPS

logger = logging.getLogger(__name__)


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_group TEXT NOT NULL,
                base_group TEXT NOT NULL,
                subgroup INTEGER NOT NULL CHECK (subgroup IN (1, 2, 3)),
                last_menu_id INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS deadlines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                lab_name TEXT NOT NULL,
                due_date TEXT NOT NULL,
                room TEXT,
                subgroup INTEGER,
                is_done INTEGER DEFAULT 0,
                UNIQUE(user_id, lab_name, due_date)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS labs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lab_name TEXT NOT NULL,
                due_iso TEXT NOT NULL,
                room TEXT,
                subgroup INTEGER,
                UNIQUE(lab_name, due_iso, subgroup)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_completed_labs (
                user_id INTEGER NOT NULL,
                lab_id INTEGER NOT NULL,
                completed_at TEXT NOT NULL,
                PRIMARY KEY (user_id, lab_id)
            )
        """)
        _ensure_column(cursor, "deadlines", "subgroup", "INTEGER")
        conn.commit()


def _ensure_column(cursor, table: str, column: str, definition: str) -> None:
    cursor.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}
    if column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        logger.info("Добавлена колонка %s.%s", table, column)


def save_user(user_id: int, subgroup: int, full_group: str = GROUP_CODE, base_group: str = GROUP_CODE):
    init_db()
    if subgroup not in VALID_SUBGROUPS:
        raise ValueError(f"Подгруппа должна быть 1, 2 или 3, получено: {subgroup}")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, full_group, base_group, subgroup)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                full_group = excluded.full_group,
                base_group = excluded.base_group,
                subgroup = excluded.subgroup
        """, (user_id, full_group, base_group, subgroup))
        conn.commit()
        logger.info("Сохранён пользователь %s, подгруппа %s", user_id, subgroup)


def get_user(user_id: int):
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT full_group, base_group, subgroup FROM users WHERE user_id = ?",
            (user_id,),
        )
        return cursor.fetchone()


def get_user_subgroup(user_id: int) -> int | None:
    user = get_user(user_id)
    if not user:
        return None
    subgroup = int(user[2])
    if subgroup not in VALID_SUBGROUPS:
        logger.warning("У пользователя %s некорректная подгруппа: %s", user_id, subgroup)
        return None
    return subgroup


def update_menu_id(user_id: int, message_id: int):
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET last_menu_id = ? WHERE user_id = ?",
            (message_id, user_id),
        )
        conn.commit()


def get_last_menu_id(user_id: int):
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT last_menu_id FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        return res[0] if res and res[0] else None


def upsert_lab(lab_name: str, due_iso: str, room: str, subgroup: int | None = None) -> int | None:
    """Сохраняет лабу в общий каталог группы и возвращает lab_id."""
    init_db()
    last_id = None
    targets = VALID_SUBGROUPS if subgroup is None else (subgroup,)
    with get_connection() as conn:
        cursor = conn.cursor()
        for group_no in targets:
            cursor.execute("""
                INSERT INTO labs (lab_name, due_iso, room, subgroup)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(lab_name, due_iso, subgroup) DO UPDATE SET
                    room = excluded.room
            """, (lab_name, due_iso, room, group_no))
            cursor.execute(
                """
                SELECT id FROM labs
                WHERE lab_name = ? AND due_iso = ? AND subgroup = ?
                """,
                (lab_name, due_iso, group_no),
            )
            row = cursor.fetchone()
            if row:
                last_id = row[0]
        conn.commit()
    return last_id


def add_auto_deadline(user_id: int, lab_name: str, due_date: str, room: str, subgroup: int | None = None):
    """Совместимость: кладёт лабу в каталог. due_date — ISO YYYY-MM-DD или ДД.ММ."""
    due_iso = _normalize_due_iso(due_date)
    if not due_iso:
        logger.warning("Пропуск лабы без даты: %s %s", lab_name, due_date)
        return
    upsert_lab(lab_name, due_iso, room, subgroup)
    if user_id:
        with get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO deadlines (user_id, lab_name, due_date, room, subgroup, is_done)
                    VALUES (?, ?, ?, ?, ?, 0)
                """, (user_id, lab_name, due_iso, room, subgroup))
                conn.commit()
            except Exception:
                logger.exception("Ошибка сохранения лабы в БД")


def _normalize_due_iso(due_date: str) -> str | None:
    raw = (due_date or "").strip()
    if len(raw) >= 10 and raw[4] == "-":
        return raw[:10]
    try:
        day, month = raw.split(".")[:2]
        year = datetime.date.today().year
        parsed = datetime.date(year, int(month), int(day))
        today = datetime.date.today()
        if parsed.month == 1 and today.month == 12:
            parsed = parsed.replace(year=year + 1)
        return parsed.isoformat()
    except Exception:
        logger.warning("Не разобрали due_date=%r", due_date)
        return None


def mark_lab_completed(user_id: int, lab_id: int) -> bool:
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, due_iso FROM labs WHERE id = ?", (lab_id,))
        lab = cursor.fetchone()
        if not lab:
            logger.warning("Отметка сдачи: lab_id=%s не найден", lab_id)
            return False
        cursor.execute("""
            INSERT OR IGNORE INTO user_completed_labs (user_id, lab_id, completed_at)
            VALUES (?, ?, datetime('now'))
        """, (user_id, lab_id))
        conn.commit()
        logger.info("user_id=%s отметил lab_id=%s как сданную", user_id, lab_id)
        return True


def get_completed_lab_ids(user_id: int) -> set[int]:
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT lab_id FROM user_completed_labs WHERE user_id = ?",
            (user_id,),
        )
        return {row[0] for row in cursor.fetchall()}


def get_semester_start(today: datetime.date | None = None) -> datetime.date:
    """1 сентября текущего учебного года."""
    today = today or datetime.date.today()
    year = today.year if today.month >= 9 else today.year - 1
    return datetime.date(year, 9, 1)


def get_lab_status(
    due_iso: str,
    is_done: bool,
    today: datetime.date | None = None,
    horizon_days: int = 14,
) -> str | None:
    """
    Возвращает состояние лабы для пользователя:
      "debt"     - не сдана, дедлайн уже прошёл          -> 🔴
      "upcoming" - не сдана, дедлайн в ближайшие N дней  -> ⏳
      "done"     - сдана, дедлайн ещё не наступил        -> 🟢
      None       - лаба скрыта (сдана и дедлайн наступил/прошёл, либо слишком далёкое будущее)
    """
    today = today or datetime.date.today()
    due = datetime.date.fromisoformat(str(due_iso)[:10])
    if is_done:
        return "done" if due > today else None
    if due < today:
        return "debt"
    if due <= today + datetime.timedelta(days=horizon_days):
        return "upcoming"
    return None


def get_lab_by_id(lab_id: int) -> dict | None:
    init_db()
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, lab_name, due_iso, room, subgroup FROM labs WHERE id = ?",
            (lab_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_visible_deadlines(user_id: int, subgroup: int, horizon_days: int = 14) -> list[dict]:
    """
    Все лабы подгруппы с 1 сентября учебного года, которые нужно показать пользователю.
    К каждой лабе добавляются поля: status ("debt" / "upcoming" / "done") и is_done.
    """
    init_db()
    today = datetime.date.today()
    semester_start = get_semester_start(today)
    completed = get_completed_lab_ids(user_id)

    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, lab_name, due_iso, room, subgroup
            FROM labs
            WHERE (subgroup = ? OR subgroup IS NULL)
              AND due_iso >= ?
            ORDER BY due_iso ASC, lab_name ASC
        """, (subgroup, semester_start.isoformat()))
        rows = cursor.fetchall()

    result = []
    for row in rows:
        item = dict(row)
        is_done = item["id"] in completed
        status = get_lab_status(item["due_iso"], is_done, today, horizon_days)
        if status is None:
            continue
        item["status"] = status
        item["is_done"] = is_done
        result.append(item)

    logger.info(
        "Видимые лабы user_id=%s subgroup=%s с %s: %s из %s",
        user_id, subgroup, semester_start.isoformat(), len(result), len(rows),
    )
    return result


def get_active_deadlines(user_id: int, subgroup: int | None = None):
    if subgroup is None:
        user = get_user(user_id)
        subgroup = int(user[2]) if user else None
    if subgroup is None:
        return []
    return get_visible_deadlines(user_id, subgroup)
