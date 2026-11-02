import json
import requests
import urllib3
from flask import Flask, request, jsonify

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
app = Flask(__name__)

BOT_TOKEN   = '8709382919:AAGcVpu8ddQLZW9SlG1CukMvzysWVyY2k3o'
WEBHOOK_URL = 'https://ВАШ-СЕРВИС.onrender.com/webhook'   
API_URL     = 'https://cryptomfo.hhos.net/api/bot.php'
API_SECRET  = 'inaaal'

FSM = {}

def tg(method, **payload):
    try:
        return requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
                             json=payload, timeout=30).json()
    except Exception as e:
        print('tg error:', e); return None

def api_request(action, chat_id=0, data=None):
    payload = {'action': action, 'chat_id': chat_id}
    if data:
        payload.update(data)
    try:
        r = requests.post(API_URL, json=payload, timeout=60,
                          headers={'X-Bot-Secret': API_SECRET,
                                   'Content-Type': 'application/json'},
                          verify=False)
        return r.json()
    except Exception as e:
        print('api error:', repr(e)); return {}

def send(chat_id, text, kb=None, parse_mode='Markdown'):
    p = {'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode,
         'disable_web_page_preview': True}
    if kb: p['reply_markup'] = kb
    return tg('sendMessage', **p)

def edit(chat_id, message_id, text, kb=None, parse_mode='Markdown'):
    p = {'chat_id': chat_id, 'message_id': message_id, 'text': text,
         'parse_mode': parse_mode, 'disable_web_page_preview': True}
    if kb: p['reply_markup'] = kb
    return tg('editMessageText', **p)

def get_main_menu(role='worker'):
    kb = [[{'text': "📊 Моя статистика", 'callback_data': "stats"}],
          [{'text': "👥 Мои клиенты", 'callback_data': "clients"}],
          [{'text': "🔗 Реферальная ссылка", 'callback_data': "ref_link"}],
          [{'text': "💰 Заявка на выплату", 'callback_data': "withdraw"}]]
    if role == 'admin':
        kb.append([{'text': "📋 Заявки воркеров", 'callback_data': "pending_workers"},
                   {'text': "💰 Заявки на выплату", 'callback_data': "pending_withdrawals"}])
    return {'inline_keyboard': kb}

def get_admin_keyboard(worker_chat_id):
    return {'inline_keyboard': [[
        {'text': "✅ Одобрить", 'callback_data': f"approve_{worker_chat_id}"},
        {'text': "❌ Отклонить", 'callback_data': f"reject_{worker_chat_id}"}
    ]]}

def get_withdraw_keyboard(wid):
    return {'inline_keyboard': [[
        {'text': "✅ Одобрить", 'callback_data': f"withdraw_approve_{wid}"},
        {'text': "❌ Отклонить", 'callback_data': f"withdraw_reject_{wid}"}
    ]]}

def cmd_start(chat_id):
    result = api_request('get_worker', chat_id)
    if result.get('success'):
        user = result['user']; worker = result['worker']
        text = (f"👋 Добро пожаловать, {user['email']}!\n\n"
                f"📊 Ваша роль: *{user['role'].upper()}*\n"
                f"💰 Бонусный баланс: ${worker['bonus_balance']:.2f}\n\n"
                f"Выберите действие:")
        send(chat_id, text, get_main_menu(user['role']))
        return

    status_result = api_request('check_application_status', chat_id)
    if status_result.get('success'):
        st = status_result['status']
        if st in ('pending', 'submitted'):
            send(chat_id, "📝 Ваша заявка уже отправлена и ожидает рассмотрения."); return
        if st == 'rejected':
            send(chat_id, "❌ Ваша заявка была отклонена. Вы можете подать новую."); return
        if st == 'approved':
            send(chat_id, "✅ Ваша заявка одобрена! Используйте /start для входа."); return

    api_request('create_application', chat_id)
    send(chat_id,
         "📝 *Анкета воркера*\n\n"
         "Ответьте на несколько вопросов для регистрации.\n"
         "Вопрос 1/3: Откуда вы узнали о нас?")
    FSM[chat_id] = 'waiting_for_source'

def process_source(chat_id, text):
    api_request('update_application', chat_id,
                {'step': 2, 'field': 'source', 'value': text})
    send(chat_id, "✅ Ответ сохранен!\n\nВопрос 2/3: Был ли у вас опыт в MFO или крипто-кредитовании?")
    FSM[chat_id] = 'waiting_for_experience'

def process_experience(chat_id, text):
    api_request('update_application', chat_id,
                {'step': 3, 'field': 'experience', 'value': text})
    send(chat_id, "✅ Ответ сохранен!\n\nВопрос 3/3: Сколько времени готовы уделять работе в день?")
    FSM[chat_id] = 'waiting_for_time'

def process_time(chat_id, text):
    api_request('update_application', chat_id,
                {'step': 4, 'field': 'time', 'value': text})
    api_request('submit_application', chat_id)
    send(chat_id, "✅ Анкета заполнена!\n\n"
                  "Ваша заявка отправлена на рассмотрение администратору.\n"
                  "Ожидайте ответа.")
    FSM.pop(chat_id, None)

def process_withdraw_amount(chat_id, text):
    try:
        amount = float(text)
        if amount <= 0:
            send(chat_id, "❌ Сумма должна быть больше 0. Попробуйте еще раз."); return
        result = api_request('create_withdrawal', chat_id, {'amount': amount})
        if result.get('success'):
            send(chat_id, "✅ Заявка на выплату создана!\nОжидайте подтверждения администратора.")
        else:
            send(chat_id, f"❌ {result.get('message', 'Ошибка')}")
    except ValueError:
        send(chat_id, "❌ Введите корректное число."); return
    FSM.pop(chat_id, None)
    cmd_start(chat_id)

def handle_message(msg):
    chat_id = msg['chat']['id']
    text = (msg.get('text') or '').strip()
    state = FSM.get(chat_id)

    if text == '/start':
        FSM.pop(chat_id, None)
        cmd_start(chat_id); return

    if state == 'waiting_for_source':
        process_source(chat_id, text); return
    if state == 'waiting_for_experience':
        process_experience(chat_id, text); return
    if state == 'waiting_for_time':
        process_time(chat_id, text); return
    if state == 'waiting_for_withdraw_amount':
        process_withdraw_amount(chat_id, text); return

def handle_callback(cb):
    data = cb.get('data', '')
    chat_id = cb['message']['chat']['id']
    message_id = cb['message']['message_id']
    tg('answerCallbackQuery', callback_query_id=cb['id'])

    if data == "stats":
        result = api_request('get_stats', chat_id)
        if result.get('success'):
            text = ("📊 *Ваша статистика*\n\n"
                    f"👥 Клиентов: {result['total_clients']}\n"
                    f"⏳ Ожидают KYC: {result['pending_kyc']}\n"
                    f"✅ KYC подтвержден: {result['approved_kyc']}\n"
                    f"💰 Бонусный баланс: ${result['bonus_balance']:.2f}")
            edit(chat_id, message_id, text, get_main_menu())
        return

    if data == "clients":
        result = api_request('get_clients', chat_id)
        if result.get('success') and result.get('clients'):
            text = "👥 *Мои клиенты*\n\n"
            for c in result['clients']:
                st = "✅" if c['kyc_status'] == 'approved' else "⏳" if c['kyc_status'] == 'pending' else "❌"
                text += f"{st} #{c['user_id']} | {c['email']} | ${c['balance']:.2f}\n"
            edit(chat_id, message_id, text, get_main_menu())
        else:
            edit(chat_id, message_id, "👥 У вас пока нет клиентов.", get_main_menu())
        return

    if data == "ref_link":
        result = api_request('get_ref_link', chat_id)
        if result.get('success'):
            edit(chat_id, message_id,
                 f"🔗 *Ваша реферальная ссылка:*\n\n`{result['ref_link']}`",
                 get_main_menu())
        return

    if data == "withdraw":
        edit(chat_id, message_id,
             "💰 *Заявка на выплату*\n\nВведите сумму которую хотите вывести (в USDT):")
        FSM[chat_id] = 'waiting_for_withdraw_amount'
        return

    if data.startswith("approve_"):
        wcid = int(data.split("_")[1])
        result = api_request('approve_worker', 0, {'worker_chat_id': wcid})
        if result.get('success'):
            send(wcid,
                 f"🎉 *Поздравляем! Ваша заявка одобрена!*\n\n"
                 f"🔗 Ваша реферальная ссылка:\n`https://cryptomfo.rf.gd/?ref={result['referral_code']}`\n\n"
                 f"📋 Используйте /start для открытия главного меню.")
            edit(chat_id, message_id, "✅ Воркер одобрен!", get_main_menu('admin'))
        return

    if data.startswith("reject_"):
        wcid = int(data.split("_")[1])
        api_request('reject_worker', 0, {'worker_chat_id': wcid})
        send(wcid, "❌ К сожалению, ваша заявка была отклонена.\nВы можете попробовать подать заявку позже.")
        edit(chat_id, message_id, "❌ Воркер отклонен!", get_main_menu('admin'))
        return

    if data == "pending_workers":
        result = api_request('get_pending_workers', 0)
        if result.get('success') and result.get('applications'):
            for a in result['applications']:
                app_data = {}
                try: app_data = json.loads(a.get('data') or '{}')
                except Exception: pass
                text = (f"📋 *Заявка воркера*\n\n"
                        f"👤 Chat ID: {a['chat_id']}\n"
                        f"📌 Откуда: {app_data.get('source', 'N/A')}\n"
                        f"💼 Опыт: {app_data.get('experience', 'N/A')}\n"
                        f"⏰ Время: {app_data.get('time', 'N/A')}")
                send(chat_id, text, get_admin_keyboard(a['chat_id']))
            edit(chat_id, message_id, "📋 Заявки отправлены выше.", get_main_menu('admin'))
        else:
            edit(chat_id, message_id, "📋 Нет заявок на рассмотрение.", get_main_menu('admin'))
        return

    if data == "pending_withdrawals":
        result = api_request('get_pending_withdrawals', 0)
        if result.get('success') and result.get('withdrawals'):
            for w in result['withdrawals']:
                text = f"💰 *Заявка на выплату #{w['id']}*\n\n👤 {w['email']}\n💵 ${w['amount']:.2f}"
                send(chat_id, text, get_withdraw_keyboard(w['id']))
            edit(chat_id, message_id, "💰 Заявки отправлены выше.", get_main_menu('admin'))
        else:
            edit(chat_id, message_id, "💰 Нет заявок на выплату.", get_main_menu('admin'))
        return

    if data.startswith("withdraw_approve_"):
        wid = int(data.split("_")[2])
        api_request('approve_withdrawal', 0, {'withdrawal_id': wid})
        edit(chat_id, message_id, "✅ Выплата одобрена!", get_main_menu('admin'))
        return

    if data.startswith("withdraw_reject_"):
        wid = int(data.split("_")[2])
        api_request('reject_withdrawal', 0, {'withdrawal_id': wid})
        edit(chat_id, message_id, "❌ Выплата отклонена!", get_main_menu('admin'))
        return

@app.route('/webhook', methods=['POST'])
def webhook():
    u = request.get_json(force=True, silent=True) or {}
    if 'message' in u:
        try: handle_message(u['message'])
        except Exception as e: print('msg err', e)
    if 'callback_query' in u:
        try: handle_callback(u['callback_query'])
        except Exception as e: print('cb err', e)
    return 'OK', 200

@app.route('/set_webhook')
def set_webhook():
    return jsonify(requests.get(
        f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
        params={'url': WEBHOOK_URL}, timeout=15).json())

@app.route('/webhook_info')
def webhook_info():
    return jsonify(requests.get(
        f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo",
        timeout=15).json())

@app.route('/health')
def health(): return 'OK', 200

@app.route('/')
def home(): return 'WORKERS bot', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
