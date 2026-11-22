"""
api.py
Backend для Mini App. Отдаёт профиль/баланс/кейсы, открывает кейсы,
создаёт инвойсы на оплату Telegram Stars.

Запуск:  uvicorn backend.api:app --host 0.0.0.0 --port 8000
"""
import os
import hashlib
import hmac
import json
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from aiogram import Bot
from aiogram.types import LabeledPrice

import database as db

BOT_TOKEN = os.environ["BOT_TOKEN"]
bot = Bot(token=BOT_TOKEN)

app = FastAPI(title="Case Bot API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    db.init_db()


def validate_init_data(init_data: str) -> dict:
    """
    Проверяет подпись Telegram.WebApp.initData по официальной схеме:
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    Поднимает HTTPException(401), если подпись неверна.
    """
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        raise HTTPException(401, "Некорректный initData")

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(401, "Нет подписи")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(401, "Неверная подпись initData")

    user = json.loads(parsed.get("user", "{}"))
    return user


# ---------------------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------------------

@app.get("/api/profile")
def profile(initData: str = Query(...)):
    tg_user = validate_init_data(initData)
    user = db.get_or_create_user(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
    can_open, remaining = db.can_open_free_case(user)
    return {
        "telegram_id": user["telegram_id"],
        "first_name": user["first_name"],
        "balance": user["balance"],
        "is_owner": db.is_owner(user["telegram_id"]),
        "free_case_available": can_open,
        "free_case_cooldown": remaining,
        "inventory": [
            {"name": i["item_name"], "video": i["video_file"], "obtained_at": i["obtained_at"]}
            for i in db.get_inventory(user["telegram_id"])
        ],
    }


@app.get("/api/cases")
def cases():
    result = []
    for case in db.get_cases():
        items = db.get_case_items(case["id"])
        total_weight = sum(i["weight"] for i in items)
        result.append({
            "slug": case["slug"],
            "name": case["name"],
            "price_stars": case["price_stars"],
            "items": [
                {
                    "name": i["name"],
                    "video": i["video_file"],
                    "is_empty": bool(i["is_empty"]),
                    "chance": round(i["weight"] / total_weight * 100, 2),
                }
                for i in items
            ],
        })
    return result


@app.post("/api/open_case/free")
def open_free_case(initData: str = Query(...)):
    tg_user = validate_init_data(initData)
    db.get_or_create_user(tg_user["id"], tg_user.get("username"), tg_user.get("first_name"))
    try:
        item = db.open_case(tg_user["id"], "free")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"name": item["name"], "video": item["video_file"], "is_empty": bool(item["is_empty"])}


@app.post("/api/create_invoice")
async def create_invoice(initData: str = Query(...)):
    """Создаёт ссылку-инвойс на оплату премиум-кейса звёздами (XTR)."""
    tg_user = validate_init_data(initData)
    case = db.get_case_by_slug("premium")
    link = await bot.create_invoice_link(
        title=case["name"],
        description="Откройте премиум кейс и получите один из эксклюзивных подарков",
        payload=f"premium_case:{tg_user['id']}",
        provider_token="",          # для Stars (XTR) provider_token всегда пустой
        currency="XTR",
        prices=[LabeledPrice(label=case["name"], amount=case["price_stars"])],
    )
    return {"invoice_url": link}


@app.get("/api/latest_opening")
def latest_opening(initData: str = Query(...)):
    """Фронтенд дергает это после успешной оплаты инвойса, чтобы узнать приз."""
    tg_user = validate_init_data(initData)
    inv = db.get_inventory(tg_user["id"])
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT co.*, ci.name, ci.video_file, ci.is_empty FROM case_openings co "
            "JOIN case_items ci ON ci.id = co.item_id "
            "JOIN users u ON u.id = co.user_id "
            "WHERE u.telegram_id = ? ORDER BY co.opened_at DESC LIMIT 1",
            (tg_user["id"],),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Нет открытий")
    return {"name": row["name"], "video": row["video_file"], "is_empty": bool(row["is_empty"])}


# Раздаём видео подарков и саму статику мини-аппа
app.mount("/assets", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "webapp", "assets")), name="assets")
app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "webapp"), html=True), name="webapp")
