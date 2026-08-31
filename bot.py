import asyncio
import json
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ============ КОНФИГ ============
BOT_TOKEN = '8709382919:AAGcVpu8ddQLZW9SlG1CukMvzysWVyY2k3o'
API_URL = 'https://cryptomfo.rf.gd/api/bot_worker.php'
API_SECRET = 'your_secret_key_here_change_me'

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ============ СОСТОЯНИЯ ============
class ApplicationStates(StatesGroup):
    waiting_for_source = State()
    waiting_for_experience = State()
    waiting_for_time = State()
    waiting_for_withdraw_amount = State()

# ============ API ЗАПРОСЫ ============
async def api_request(action: str, chat_id: int = 0, data: dict = None):
    url = API_URL
    headers = {
        'X-Bot-Secret': API_SECRET,
        'Content-Type': 'application/json'
    }
    payload = {'action': action, 'chat_id': chat_id}
    if data:
        payload.update(data)
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            return await response.json()

# ============ КЛАВИАТУРЫ ============
def get_main_menu(role='worker'):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Моя статистика", callback_data="stats")],
        [InlineKeyboardButton(text="👥 Мои клиенты", callback_data="clients")],
        [InlineKeyboardButton(text="🔗 Реферальная ссылка", callback_data="ref_link")],
        [InlineKeyboardButton(text="💰 Заявка на выплату", callback_data="withdraw")]
    ])
    
    if role == 'admin':
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="📋 Заявки воркеров", callback_data="pending_workers"),
            InlineKeyboardButton(text="💰 Заявки на выплату", callback_data="pending_withdrawals")
        ])
    
    return keyboard

def get_admin_keyboard(worker_chat_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{worker_chat_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{worker_chat_id}")
        ]
    ])

def get_withdraw_keyboard(withdrawal_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"withdraw_approve_{withdrawal_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"withdraw_reject_{withdrawal_id}")
        ]
    ])

# ============ ОБРАБОТЧИКИ ============

# /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    chat_id = message.chat.id
    
    # Проверяем воркера
    result = await api_request('get_worker', chat_id)
    
    if result.get('success'):
        user = result['user']
        worker = result['worker']
        text = f"👋 Добро пожаловать, {user['email']}!\n\n"
        text += f"📊 Ваша роль: *{user['role'].upper()}*\n"
        text += f"💰 Бонусный баланс: ${worker['bonus_balance']:.2f}\n\n"
        text += "Выберите действие:"
        
        await message.answer(text, reply_markup=get_main_menu(user['role']), parse_mode="Markdown")
    else:
        # Проверяем статус заявки
        status_result = await api_request('check_application_status', chat_id)
        
        if status_result.get('success'):
            status = status_result['status']
            if status == 'pending' or status == 'submitted':
                await message.answer("📝 Ваша заявка уже отправлена и ожидает рассмотрения.")
                return
            elif status == 'rejected':
                await message.answer("❌ Ваша заявка была отклонена. Вы можете подать новую.")
                return
            elif status == 'approved':
                await message.answer("✅ Ваша заявка одобрена! Используйте /start для входа.")
                return
        
        # Начинаем анкету
        await api_request('create_application', chat_id)
        await message.answer(
            "📝 *Анкета воркера*\n\n"
            "Ответьте на несколько вопросов для регистрации.\n"
            "Вопрос 1/3: Откуда вы узнали о нас?",
            parse_mode="Markdown"
        )
        await ApplicationStates.waiting_for_source.set()

# Анкета - вопрос 1
@dp.message(ApplicationStates.waiting_for_source)
async def process_source(message: types.Message, state: FSMContext):
    chat_id = message.chat.id
    await api_request('update_application', chat_id, {
        'step': 2,
        'field': 'source',
        'value': message.text
    })
    
    await message.answer(
        "✅ Ответ сохранен!\n\n"
        "Вопрос 2/3: Был ли у вас опыт в MFO или крипто-кредитовании?"
    )
    await state.set_state(ApplicationStates.waiting_for_experience)

# Анкета - вопрос 2
@dp.message(ApplicationStates.waiting_for_experience)
async def process_experience(message: types.Message, state: FSMContext):
    chat_id = message.chat.id
    await api_request('update_application', chat_id, {
        'step': 3,
        'field': 'experience',
        'value': message.text
    })
    
    await message.answer(
        "✅ Ответ сохранен!\n\n"
        "Вопрос 3/3: Сколько времени готовы уделять работе в день?"
    )
    await state.set_state(ApplicationStates.waiting_for_time)

# Анкета - вопрос 3
@dp.message(ApplicationStates.waiting_for_time)
async def process_time(message: types.Message, state: FSMContext):
    chat_id = message.chat.id
    await api_request('update_application', chat_id, {
        'step': 4,
        'field': 'time',
        'value': message.text
    })
    
    # Отправляем заявку
    await api_request('submit_application', chat_id)
    
    await message.answer(
        "✅ Анкета заполнена!\n\n"
        "Ваша заявка отправлена на рассмотрение администратору.\n"
        "Ожидайте ответа."
    )
    await state.clear()

# Обработка callback
@dp.callback_query()
async def handle_callback(callback: types.CallbackQuery):
    data = callback.data
    chat_id = callback.message.chat.id
    
    await callback.answer()
    
    # Статистика
    if data == "stats":
        result = await api_request('get_stats', chat_id)
        if result.get('success'):
            text = "📊 *Ваша статистика*\n\n"
            text += f"👥 Клиентов: {result['total_clients']}\n"
            text += f"⏳ Ожидают KYC: {result['pending_kyc']}\n"
            text += f"✅ KYC подтвержден: {result['approved_kyc']}\n"
            text += f"💰 Бонусный баланс: ${result['bonus_balance']:.2f}"
            
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_menu())
        return
    
    # Клиенты
    if data == "clients":
        result = await api_request('get_clients', chat_id)
        if result.get('success') and result['clients']:
            text = "👥 *Мои клиенты*\n\n"
            for client in result['clients']:
                status = "✅" if client['kyc_status'] == 'approved' else "⏳" if client['kyc_status'] == 'pending' else "❌"
                text += f"{status} #{client['user_id']} | {client['email']} | ${client['balance']:.2f}\n"
            
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_menu())
        else:
            await callback.message.edit_text("👥 У вас пока нет клиентов.", reply_markup=get_main_menu())
        return
    
    # Реферальная ссылка
    if data == "ref_link":
        result = await api_request('get_ref_link', chat_id)
        if result.get('success'):
            text = f"🔗 *Ваша реферальная ссылка:*\n\n`{result['ref_link']}`"
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_menu())
        return
    
    # Заявка на выплату
    if data == "withdraw":
        await callback.message.edit_text(
            "💰 *Заявка на выплату*\n\n"
            "Введите сумму которую хотите вывести (в USDT):",
            parse_mode="Markdown"
        )
        await ApplicationStates.waiting_for_withdraw_amount.set()
        return
    
    # Одобрение воркера
    if data.startswith("approve_"):
        worker_chat_id = int(data.split("_")[1])
        result = await api_request('approve_worker', 0, {'worker_chat_id': worker_chat_id})
        
        if result.get('success'):
            # Уведомляем воркера
            await bot.send_message(
                worker_chat_id,
                f"🎉 *Поздравляем! Ваша заявка одобрена!*\n\n"
                f"🔗 Ваша реферальная ссылка:\n`https://cryptomfo.rf.gd/?ref={result['referral_code']}`\n\n"
                f"📋 Используйте /start для открытия главного меню.",
                parse_mode="Markdown"
            )
            await callback.message.edit_text("✅ Воркер одобрен!", reply_markup=get_main_menu('admin'))
        return
    
    # Отклонение воркера
    if data.startswith("reject_"):
        worker_chat_id = int(data.split("_")[1])
        await api_request('reject_worker', 0, {'worker_chat_id': worker_chat_id})
        
        await bot.send_message(
            worker_chat_id,
            "❌ К сожалению, ваша заявка была отклонена.\nВы можете попробовать подать заявку позже."
        )
        await callback.message.edit_text("❌ Воркер отклонен!", reply_markup=get_main_menu('admin'))
        return
    
    # Заявки воркеров (админ)
    if data == "pending_workers":
        result = await api_request('get_pending_workers', 0)
        if result.get('success') and result['applications']:
            text = "📋 *Заявки воркеров*\n\n"
            for app in result['applications']:
                app_data = json.loads(app['data'] or '{}')
                text += f"👤 Chat ID: {app['chat_id']}\n"
                text += f"📌 Откуда: {app_data.get('source', 'N/A')}\n"
                text += f"💼 Опыт: {app_data.get('experience', 'N/A')}\n"
                text += f"⏰ Время: {app_data.get('time', 'N/A')}\n\n"
                
                await bot.send_message(
                    chat_id,
                    text,
                    reply_markup=get_admin_keyboard(app['chat_id']),
                    parse_mode="Markdown"
                )
            await callback.message.edit_text("📋 Заявки отправлены выше.", reply_markup=get_main_menu('admin'))
        else:
            await callback.message.edit_text("📋 Нет заявок на рассмотрение.", reply_markup=get_main_menu('admin'))
        return
    
    # Заявки на выплату (админ)
    if data == "pending_withdrawals":
        result = await api_request('get_pending_withdrawals', 0)
        if result.get('success') and result['withdrawals']:
            text = "💰 *Заявки на выплату*\n\n"
            for w in result['withdrawals']:
                text += f"#{w['id']} | {w['email']} | ${w['amount']:.2f}\n"
                await bot.send_message(
                    chat_id,
                    text,
                    reply_markup=get_withdraw_keyboard(w['id']),
                    parse_mode="Markdown"
                )
            await callback.message.edit_text("💰 Заявки отправлены выше.", reply_markup=get_main_menu('admin'))
        else:
            await callback.message.edit_text("💰 Нет заявок на выплату.", reply_markup=get_main_menu('admin'))
        return

# Сумма для вывода
@dp.message(ApplicationStates.waiting_for_withdraw_amount)
async def process_withdraw_amount(message: types.Message, state: FSMContext):
    chat_id = message.chat.id
    try:
        amount = float(message.text)
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше 0. Попробуйте еще раз.")
            return
        
        result = await api_request('create_withdrawal', chat_id, {'amount': amount})
        
        if result.get('success'):
            await message.answer(
                "✅ Заявка на выплату создана!\n"
                "Ожидайте подтверждения администратора."
            )
        else:
            await message.answer(f"❌ {result.get('message', 'Ошибка')}")
    except ValueError:
        await message.answer("❌ Введите корректное число.")
    
    await state.clear()
    await cmd_start(message)

# ============ ЗАПУСК ============
async def main():
    print("🚀 Бот воркеров запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())