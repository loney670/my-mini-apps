"""
database.py
Общий слой работы с SQLite для бота и API мини-аппа.
Все функции синхронные (sqlite3), т.к. нагрузка небольшая — этого достаточно
для старта. При росте проекта можно перейти на aiosqlite/PostgreSQL.
"""
import sqlite3
import os
import random
import datetime
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "bot.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")


def init_db():
    """Создаёт базу и накатывает схему, если её ещё нет."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# USERS
# ---------------------------------------------------------------------------

def get_or_create_user(telegram_id: int, username: str = None, first_name: str = None) -> sqlite3.Row:
    with get_conn() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        if user:
            conn.execute(
                "UPDATE users SET username = ?, first_name = ? WHERE telegram_id = ?",
                (username, first_name, telegram_id),
            )
            conn.commit()
            return conn.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
            ).fetchone()
        conn.execute(
            "INSERT INTO users (telegram_id, username, first_name) VALUES (?, ?, ?)",
            (telegram_id, username, first_name),
        )
        conn.commit()
        return conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()


def get_user_by_telegram_id(telegram_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()


def set_balance(telegram_id: int, amount: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET balance = balance + ? WHERE telegram_id = ?",
            (amount, telegram_id),
        )
        conn.commit()


def ban_user(telegram_id: int, banned: bool = True):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET is_banned = ? WHERE telegram_id = ?",
            (1 if banned else 0, telegram_id),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# CASES
# ---------------------------------------------------------------------------

def get_cases():
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM cases WHERE is_active = 1 ORDER BY sort_order"
        ).fetchall()


def get_case_by_slug(slug: str):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM cases WHERE slug = ?", (slug,)).fetchone()


def get_case_items(case_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM case_items WHERE case_id = ? ORDER BY sort_order", (case_id,)
        ).fetchall()


def roll_case_item(case_id: int) -> sqlite3.Row:
    """Взвешенный случайный выбор приза из кейса."""
    items = get_case_items(case_id)
    weights = [item["weight"] for item in items]
    return random.choices(items, weights=weights, k=1)[0]


def can_open_free_case(user_row) -> tuple[bool, int]:
    """Проверяет кулдаун бесплатного кейса. Возвращает (можно_ли, секунд_осталось)."""
    case = get_case_by_slug("free")
    if not user_row["last_free_case_at"]:
        return True, 0
    last = datetime.datetime.fromisoformat(user_row["last_free_case_at"])
    elapsed = (datetime.datetime.utcnow() - last).total_seconds()
    remaining = case["cooldown_seconds"] - elapsed
    if remaining <= 0:
        return True, 0
    return False, int(remaining)


def open_case(telegram_id: int, slug: str, telegram_payment_id: str = None):
    """
    Открывает кейс для пользователя: проверяет условия, крутит рулетку,
    пишет в inventory/case_openings/transactions. Поднимает ValueError с
    понятным сообщением, если открыть нельзя.
    Возвращает выпавший item (sqlite3.Row).
    """
    user = get_user_by_telegram_id(telegram_id)
    if not user:
        raise ValueError("Пользователь не найден")
    if user["is_banned"]:
        raise ValueError("Вы заблокированы")

    case = get_case_by_slug(slug)
    if not case:
        raise ValueError("Кейс не найден")

    if case["price_stars"] == 0:
        can_open, remaining = can_open_free_case(user)
        if not can_open:
            raise ValueError(f"Бесплатный кейс будет доступен через {remaining} сек.")
    else:
        if not telegram_payment_id:
            raise ValueError("Платёж не подтверждён")

    item = roll_case_item(case["id"])

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO case_openings (user_id, case_id, item_id) VALUES (?, ?, ?)",
            (user["id"], case["id"], item["id"]),
        )
        if not item["is_empty"]:
            conn.execute(
                "INSERT INTO inventory (user_id, item_name, video_file) VALUES (?, ?, ?)",
                (user["id"], item["name"], item["video_file"]),
            )
        if case["price_stars"] == 0:
            conn.execute(
                "UPDATE users SET last_free_case_at = ? WHERE id = ?",
                (datetime.datetime.utcnow().isoformat(), user["id"]),
            )
            conn.execute(
                "INSERT INTO transactions (user_id, type, amount_stars, description) VALUES (?, 'case_open_free', 0, ?)",
                (user["id"], f"Открытие бесплатного кейса, выпало: {item['name']}"),
            )
        else:
            conn.execute(
                "INSERT INTO transactions (user_id, type, amount_stars, telegram_payment_id, description) "
                "VALUES (?, 'case_open_paid', ?, ?, ?)",
                (user["id"], case["price_stars"], telegram_payment_id, f"Открытие премиум кейса, выпало: {item['name']}"),
            )
        conn.commit()

    return item


def get_inventory(telegram_id: int):
    user = get_user_by_telegram_id(telegram_id)
    if not user:
        return []
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM inventory WHERE user_id = ? ORDER BY obtained_at DESC", (user["id"],)
        ).fetchall()


# ---------------------------------------------------------------------------
# ADMIN / OWNER
# ---------------------------------------------------------------------------

def get_setting(key: str, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


def is_owner(telegram_id: int) -> bool:
    owner_id = os.environ.get("OWNER_ID") or get_setting("owner_id")
    return owner_id is not None and str(telegram_id) == str(owner_id)


def update_item_weight(item_id: int, new_weight: float):
    """Позволяет владельцу менять шанс выпадения конкретного предмета."""
    with get_conn() as conn:
        conn.execute("UPDATE case_items SET weight = ? WHERE id = ?", (new_weight, item_id))
        conn.commit()


def get_stats():
    with get_conn() as conn:
        users_count = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        openings_count = conn.execute("SELECT COUNT(*) c FROM case_openings").fetchone()["c"]
        stars_earned = conn.execute(
            "SELECT COALESCE(SUM(amount_stars),0) s FROM transactions WHERE type='case_open_paid'"
        ).fetchone()["s"]
        return {
            "users": users_count,
            "openings": openings_count,
            "stars_earned": stars_earned,
        }
