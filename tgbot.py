import asyncio
import logging
import sys
import random
import requests
import os
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot, Dispatcher, html, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = 794477925 
CITY = "Минск"
TIMEZONE = "Europe/Minsk"

class ReminderState(StatesGroup):
    waiting_for_text = State()
    waiting_for_time = State()

def get_coords(city: str):
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": city, "count": 1, "format": "json"}
    r = requests.get(url, params=params, timeout=10)
    data = r.json()
    if not data.get("results"):
        return None
    res = data["results"][0]
    return res["latitude"], res["longitude"]

def get_weather(city: str):
    coords = get_coords(city)
    if not coords:
        return f"❌ Город «{city}» не найден."
    lat, lon = coords
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": ["temperature_2m_max", "temperature_2m_min", "precipitation_probability_max", "weather_code"],
        "timezone": "auto",
        "forecast_days": 1,
    }
    r = requests.get(url, params=params, timeout=10)
    data = r.json()
    daily = data["daily"]
    t_max = daily["temperature_2m_max"][0]
    t_min = daily["temperature_2m_min"][0]
    rain = daily["precipitation_probability_max"][0]
    code = daily["weather_code"][0]
    
    desc = "☀️ Ясно" if code == 0 else "⛅ Облачно" if code in [1,2,3] else "🌧 Дождь" if code in [51,53,55,61,63,65] else "❄️ Снег" if code in [71,73,75] else "🌤 Переменно"
    
    return (
        f"🌅 Погода в {city}:\n"
        f"{desc}\n"
        f"🌡 {t_min:.0f}°C … {t_max:.0f}°C\n"
        f"💧 Вероятность дождя: {rain}%"
    )

async def morning_weather(bot: Bot, chat_id: int, city: str):
    text = get_weather(city)
    await bot.send_message(chat_id, text)

REMINDERS = ["💊 Не забудь про лекарства!", "💧 Попей водички!", "🚶 Прогуляйся немного."]

async def evening_reminder(bot: Bot, chat_id: int):
    text = random.choice(REMINDERS)
    await bot.send_message(chat_id, text)

async def send_custom_reminder(bot: Bot, chat_id: int, text: str):
    await bot.send_message(chat_id, f"🔔 НАПОМИНАНИЕ:\n{text}")

dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=TIMEZONE)

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(f"Привет, {html.bold(message.from_user.full_name)}!\n\n"
                         f"Мои команды:\n"
                         f"🌤 /weather — погода сейчас\n"
                         f"🔔 /remind — случайное напоминание\n"
                         f"⏰ /set_remind — создать свое напоминание на время")

@dp.message(Command("weather"))
async def weather_handler(message: Message):
    await message.answer(get_weather(CITY))

@dp.message(Command("remind"))
async def remind_handler(message: Message):
    await message.answer(random.choice(REMINDERS))

@dp.message(Command("set_remind"))
async def start_set_reminder(message: Message, state: FSMContext):
    await message.answer("📝 Что нужно напомнить? Напиши текст:")
    await state.set_state(ReminderState.waiting_for_text)

@dp.message(ReminderState.waiting_for_text)
async def get_reminder_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text)
    await message.answer("⏰ Во сколько напомнить? Напиши в формате ЧЧ:ММ (например, 19:30) или через сколько минут (например, 15):")
    await state.set_state(ReminderState.waiting_for_time)

@dp.message(ReminderState.waiting_for_time)
async def get_reminder_time(message: Message, state: FSMContext):
    time_str = message.text.strip()
    data = await state.get_data()
    text = data["text"]
    
    run_date = None
    
    if ":" in time_str:
        try:
            now = datetime.now()
            target_time = datetime.strptime(time_str, "%H:%M").time()
            target_datetime = datetime.combine(now.date(), target_time)
            
            if target_datetime < now:
                target_datetime += timedelta(days=1)
                
            run_date = target_datetime
        except ValueError:
            await message.answer("❌ Неверный формат времени. Напиши как 19:30 или 15 (минут).")
            return
    else:
        try:
            minutes = int(time_str)
            run_date = datetime.now() + timedelta(minutes=minutes)
        except ValueError:
            await message.answer("❌ Я не понял. Напиши время (19:30) или количество минут (15).")
            return

    scheduler.add_job(
        send_custom_reminder, 
        "date", 
        run_date=run_date, 
        args=[message.bot, message.chat.id, text]
    )
    
    await message.answer(f"✅ Окей! Напомню в {run_date.strftime('%H:%M')}:\n«{text}»")
    await state.clear()

async def main() -> None:
    if not TOKEN:
        print("ОШИБКА: Переменная BOT_TOKEN не задана!")
        return

    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    
    scheduler.add_job(morning_weather, "cron", hour=8, minute=0, args=[bot, CHAT_ID, CITY])
    scheduler.add_job(evening_reminder, "cron", hour=20, minute=0, args=[bot, CHAT_ID])
    scheduler.start()
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())