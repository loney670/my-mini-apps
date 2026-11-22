-- =====================================================
-- Database schema: Telegram Case-Opening Bot + Mini App
-- SQLite 3
-- =====================================================

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id     INTEGER UNIQUE NOT NULL,
    username        TEXT,
    first_name      TEXT,
    balance         INTEGER NOT NULL DEFAULT 0,       -- внутренняя валюта (если понадобится)
    is_banned       INTEGER NOT NULL DEFAULT 0,
    last_free_case_at TEXT,                            -- когда последний раз открывал бесплатный кейс
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);

-- ---------- CASES (бесплатный и платный) ----------
CREATE TABLE IF NOT EXISTS cases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT UNIQUE NOT NULL,              -- 'free' / 'premium'
    name            TEXT NOT NULL,
    price_stars     INTEGER NOT NULL DEFAULT 0,        -- 0 = бесплатный
    cooldown_seconds INTEGER NOT NULL DEFAULT 0,        -- для бесплатного: таймер до след. открытия
    is_active       INTEGER NOT NULL DEFAULT 1,
    sort_order      INTEGER NOT NULL DEFAULT 0
);

-- ---------- CASE_ITEMS (содержимое кейса + веса вероятностей) ----------
CREATE TABLE IF NOT EXISTS case_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id         INTEGER NOT NULL REFERENCES cases(id),
    name            TEXT NOT NULL,                      -- 'Мишка', 'Пусто', ...
    video_file      TEXT,                                -- имя файла в assets/gifts, NULL для "пусто"
    weight          REAL NOT NULL,                       -- вес (проценты считаются из суммы весов кейса)
    is_empty        INTEGER NOT NULL DEFAULT 0,
    sort_order      INTEGER NOT NULL DEFAULT 0
);

-- ---------- CASE_OPENINGS (лог каждого открытия) ----------
CREATE TABLE IF NOT EXISTS case_openings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    case_id         INTEGER NOT NULL REFERENCES cases(id),
    item_id         INTEGER NOT NULL REFERENCES case_items(id),
    opened_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_openings_user ON case_openings(user_id, opened_at DESC);

-- ---------- INVENTORY (выигранные подарки пользователя) ----------
CREATE TABLE IF NOT EXISTS inventory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    item_name       TEXT NOT NULL,
    video_file      TEXT,
    obtained_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------- TRANSACTIONS (платежи звёздами + начисления) ----------
CREATE TABLE IF NOT EXISTS transactions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL REFERENCES users(id),
    type                TEXT NOT NULL,                  -- 'case_open_paid', 'case_open_free', 'admin_grant'
    amount_stars        INTEGER NOT NULL DEFAULT 0,
    telegram_payment_id TEXT,
    description         TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------- SETTINGS (редактируется владельцем из бота) ----------
CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL
);

-- =====================================================
-- Стартовые данные: 2 кейса и их содержимое
-- =====================================================

INSERT OR IGNORE INTO cases (slug, name, price_stars, cooldown_seconds, sort_order) VALUES
    ('free',    'Бесплатный кейс', 0,  28800, 1),   -- кулдаун 8 часов
    ('premium', 'Премиум кейс',    25, 0,     2);

-- Бесплатный кейс: 70% пусто, 30% делится поровну на все 7 подарков (~4.2857% каждый)
INSERT OR IGNORE INTO case_items (case_id, name, video_file, weight, is_empty, sort_order)
SELECT id, 'Пусто', NULL, 70, 1, 0 FROM cases WHERE slug = 'free';

INSERT OR IGNORE INTO case_items (case_id, name, video_file, weight, is_empty, sort_order)
SELECT id, 'Мишка',    'teddy.mp4',    30.0/7, 0, 1 FROM cases WHERE slug = 'free';
INSERT OR IGNORE INTO case_items (case_id, name, video_file, weight, is_empty, sort_order)
SELECT id, 'Подарок',  'giftbox.mp4',  30.0/7, 0, 2 FROM cases WHERE slug = 'free';
INSERT OR IGNORE INTO case_items (case_id, name, video_file, weight, is_empty, sort_order)
SELECT id, 'Тортик',   'cake.mp4',     30.0/7, 0, 3 FROM cases WHERE slug = 'free';
INSERT OR IGNORE INTO case_items (case_id, name, video_file, weight, is_empty, sort_order)
SELECT id, 'Кубок',    'trophy.mp4',   30.0/7, 0, 4 FROM cases WHERE slug = 'free';
INSERT OR IGNORE INTO case_items (case_id, name, video_file, weight, is_empty, sort_order)
SELECT id, 'Ракета',   'rocket.mp4',   30.0/7, 0, 5 FROM cases WHERE slug = 'free';
INSERT OR IGNORE INTO case_items (case_id, name, video_file, weight, is_empty, sort_order)
SELECT id, 'Алмаз',    'diamond.mp4',  30.0/7, 0, 6 FROM cases WHERE slug = 'free';
INSERT OR IGNORE INTO case_items (case_id, name, video_file, weight, is_empty, sort_order)
SELECT id, 'Мороженое','icecream.mp4', 30.0/7, 0, 7 FROM cases WHERE slug = 'free';

-- Премиум кейс (25 звёзд): 50% Мишка, 50% делится поровну на остальные 6 подарков (~8.33% каждый)
INSERT OR IGNORE INTO case_items (case_id, name, video_file, weight, is_empty, sort_order)
SELECT id, 'Мишка',    'teddy.mp4',    50,     0, 0 FROM cases WHERE slug = 'premium';
INSERT OR IGNORE INTO case_items (case_id, name, video_file, weight, is_empty, sort_order)
SELECT id, 'Подарок',  'giftbox.mp4',  50.0/6, 0, 1 FROM cases WHERE slug = 'premium';
INSERT OR IGNORE INTO case_items (case_id, name, video_file, weight, is_empty, sort_order)
SELECT id, 'Тортик',   'cake.mp4',     50.0/6, 0, 2 FROM cases WHERE slug = 'premium';
INSERT OR IGNORE INTO case_items (case_id, name, video_file, weight, is_empty, sort_order)
SELECT id, 'Кубок',    'trophy.mp4',   50.0/6, 0, 3 FROM cases WHERE slug = 'premium';
INSERT OR IGNORE INTO case_items (case_id, name, video_file, weight, is_empty, sort_order)
SELECT id, 'Ракета',   'rocket.mp4',   50.0/6, 0, 4 FROM cases WHERE slug = 'premium';
INSERT OR IGNORE INTO case_items (case_id, name, video_file, weight, is_empty, sort_order)
SELECT id, 'Алмаз',    'diamond.mp4',  50.0/6, 0, 5 FROM cases WHERE slug = 'premium';

INSERT OR IGNORE INTO settings (key, value) VALUES ('owner_id', 'PUT_YOUR_TELEGRAM_ID_HERE');
