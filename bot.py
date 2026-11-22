"""
bot.py
Телеграм-бот: присылает кнопку с мини-аппом, принимает оплату Telegram Stars
за премиум-кейс, даёт владельцу закрытые админ-команды.

Запуск:  python bot/bot.py
"""
import asyncio
import os
import sys

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, PreCheckoutQuery, WebAppInfo,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))
import database as db  # noqa: E402

BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBAPP_URL = os.environ["WEBAPP_URL"]       # например https://твой-домен.ru

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def owner_only(handler):
    async def wrapper(message: Message, *args, **kwargs):
        if not db.is_owner(message.from_user.id):
            await message.answer("⛔ Эта команда доступна только владельцу бота.")
            return
        return await handler(message, *args, **kwargs)
    return wrapper


@dp.message(CommandStart())
async def start(message: Message):
    db.get_or_create_user(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Открыть приложение", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Здесь можно открывать кейсы и получать подарки 🎁\n"
        "Жми кнопку ниже, чтобы открыть приложение.",
        reply_markup=kb,
    )


# ---------------------------------------------------------------------------
# ОПЛАТА ЗВЁЗДАМИ (Telegram Stars)
# ---------------------------------------------------------------------------

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    # Здесь можно добавить доп. проверки (бан, лимиты) перед подтверждением оплаты
    await bot.answer_pre_checkout_query(query.id, ok=True)


@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    payment = message.successful_payment
    try:
        item = db.open_case(
            message.from_user.id,
            "premium",
            telegram_payment_id=payment.telegram_payment_charge_id,
        )
    except ValueError as e:
        await message.answer(f"Платёж получен, но произошла ошибка: {e}. Напишите владельцу.")
        return

    if item["is_empty"]:
        await message.answer("Увы, в этот раз пусто 😔 Попробуйте ещё раз!")
    else:
        await message.answer(f"🎉 Поздравляем! Вам выпал приз: <b>{item['name']}</b>", parse_mode="HTML")


# ---------------------------------------------------------------------------
# АДМИН-КОМАНДЫ (только владелец, определяется по OWNER_ID в .env)
# ---------------------------------------------------------------------------

@dp.message(Command("admin"))
@owner_only
async def admin_panel(message: Message):
    stats = db.get_stats()
    await message.answer(
        "🛠 <b>Админ-панель</b>\n\n"
        f"👥 Пользователей: {stats['users']}\n"
        f"🎁 Открытий кейсов: {stats['openings']}\n"
        f"⭐ Заработано звёзд: {stats['stars_earned']}\n\n"
        "Команды:\n"
        "/give &lt;telegram_id&gt; &lt;сумма&gt; — начислить баланс\n"
        "/ban &lt;telegram_id&gt; — заблокировать пользователя\n"
        "/unban &lt;telegram_id&gt; — разблокировать\n"
        "/setweight &lt;item_id&gt; &lt;вес&gt; — изменить шанс выпадения предмета",
        parse_mode="HTML",
    )


@dp.message(Command("give"))
@owner_only
async def give_balance(message: Message):
    try:
        _, tg_id, amount = message.text.split()
        db.set_balance(int(tg_id), int(amount))
        await message.answer(f"✅ Начислено {amount} пользователю {tg_id}")
    except Exception:
        await message.answer("Использование: /give <telegram_id> <сумма>")


@dp.message(Command("ban"))
@owner_only
async def ban_cmd(message: Message):
    try:
        _, tg_id = message.text.split()
        db.ban_user(int(tg_id), True)
        await message.answer(f"🚫 Пользователь {tg_id} заблокирован")
    except Exception:
        await message.answer("Использование: /ban <telegram_id>")


@dp.message(Command("unban"))
@owner_only
async def unban_cmd(message: Message):
    try:
        _, tg_id = message.text.split()
        db.ban_user(int(tg_id), False)
        await message.answer(f"✅ Пользователь {tg_id} разблокирован")
    except Exception:
        await message.answer("Использование: /unban <telegram_id>")


@dp.message(Command("setweight"))
@owner_only
async def setweight_cmd(message: Message):
    try:
        _, item_id, weight = message.text.split()
        db.update_item_weight(int(item_id), float(weight))
        await message.answer(f"✅ Вес предмета {item_id} изменён на {weight}")
    except Exception:
        await message.answer("Использование: /setweight <item_id> <вес>")


async def main():
    db.init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
