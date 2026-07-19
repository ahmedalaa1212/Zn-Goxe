import os
import threading
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import database

BOT_TOKEN = os.environ.get('BOT_TOKEN')
BOT_USERNAME = "zngoxe_bot"
APP_SHORT_NAME = "app"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

BASE_MINING_RATE = 20  
BASE_STORAGE_CAP = 10000

MINING_PACKAGES = {
    1: {"price": 1000, "boost": 500}, 2: {"price": 3000, "boost": 1200},
    3: {"price": 7000, "boost": 2500}, 4: {"price": 15000, "boost": 5000},
    5: {"price": 30000, "boost": 10000}, 6: {"price": 60000, "boost": 22000},
    7: {"price": 120000, "boost": 45000}, 8: {"price": 250000, "boost": 100000},
    9: {"price": 500000, "boost": 250000}, 10: {"price": 1000000, "boost": 600000}
}

STORAGE_PACKAGES = {
    1: {"price": 2000, "cap": 20000}, 2: {"price": 5000, "cap": 30000},
    3: {"price": 10000, "cap": 50000}, 4: {"price": 25000, "cap": 100000},
    5: {"price": 50000, "cap": 250000}, 6: {"price": 100000, "cap": 500000},
    7: {"price": 250000, "cap": 1000000}, 8: {"price": 500000, "cap": 2500000}
}

def calculate_unclaimed(user):
    try:
        last_claim_str = user.get('last_claim_time', datetime.utcnow().isoformat())
        last_claim = datetime.fromisoformat(last_claim_str)
        seconds_passed = (datetime.utcnow() - last_claim).total_seconds()
        if seconds_passed < 0: seconds_passed = 0

        hourly_rate = BASE_MINING_RATE
        for i in range(1, 11):
            count = user.get(f'lvl{i}_count', 0)
            hourly_rate += count * MINING_PACKAGES[i]["boost"]

        storage_lvl = user.get('storage_level', 0)
        max_cap = STORAGE_PACKAGES.get(storage_lvl, {}).get("cap", BASE_STORAGE_CAP)

        unclaimed = seconds_passed * (hourly_rate / 3600.0)
        if unclaimed > max_cap: unclaimed = max_cap
            
        return int(unclaimed), hourly_rate, max_cap
    except Exception as e:
        return 0, BASE_MINING_RATE, BASE_STORAGE_CAP

@app.route('/')
def serve_index(): 
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename): 
    return send_from_directory('.', filename)

@app.route('/api/user_data', methods=['GET'])
def get_user_data():
    tg_id = request.args.get('tg_id') or request.args.get('telegramId')
    ref_id = request.args.get('ref_id')
    user_name = request.args.get('name', 'صديق')
    
    if not tg_id: 
        return jsonify({'error': 'Missing telegram ID'}), 400
    
    # ضمان التسجيل الفوري للمستخدم
    database.init_user(tg_id, ref_id, user_name)
    
    user = database.get_user_data(str(tg_id))
    if not user: 
        return jsonify({'error': 'User not found'}), 404
        
    unclaimed, hourly_rate, max_cap = calculate_unclaimed(user)
    
    response_data = user.copy()
    response_data['calculated_hourly_rate'] = hourly_rate
    response_data['calculated_max_cap'] = max_cap
    response_data['calculated_unclaimed'] = unclaimed
    
    return jsonify({'success': True, 'data': response_data})

@app.route('/api/claim', methods=['POST'])
def handle_claim():
    data = request.json or {}
    tg_id = data.get('tg_id') or data.get('telegramId')
    if not tg_id: 
        return jsonify({'error': 'Missing telegram ID'}), 400
        
    user = database.get_user_data(str(tg_id))
    if not user: 
        return jsonify({'error': 'User not found'}), 404
        
    unclaimed, _, _ = calculate_unclaimed(user)
    if unclaimed <= 0: 
        return jsonify({'success': False, 'error': 'No rewards to claim yet'}), 400
        
    new_balance = user.get('balance', 0) + unclaimed
    
    database.update_balance(str(tg_id), new_balance)
    database.update_claim_time(str(tg_id))
    
    # تفعيل مكافأة الـ 10% للداعي عند كل عملية سحب
    database.add_referral_bonus(str(tg_id), unclaimed)
    
    return jsonify({'success': True, 'claimed': unclaimed, 'new_balance': new_balance})

@app.route('/api/get_friends_list', methods=['GET'])
def fetch_friends():
    tg_id = request.args.get('tg_id') or request.args.get('telegramId')
    if not tg_id: 
        return jsonify({'error': 'Missing telegram ID'}), 400
    
    friends = database.get_friends_list(str(tg_id))
    return jsonify({'success': True, 'friends': friends})

@app.route('/api/claim_ref_earnings', methods=['POST'])
def handle_claim_ref():
    data = request.json or {}
    tg_id = data.get('tg_id') or data.get('telegramId')
    if not tg_id: 
        return jsonify({'error': 'Missing telegram ID'}), 400
        
    success, amount = database.claim_referral_earnings(str(tg_id))
    if success:
        user = database.get_user_data(str(tg_id))
        return jsonify({'success': True, 'claimed': amount, 'new_balance': user.get('balance', 0)})
    return jsonify({'success': False, 'error': 'No pending earnings or error occurred'}), 400

@bot.message_handler(commands=['start'])
def start_command(message):
    tg_id = str(message.from_user.id)
    first_name = message.from_user.first_name or "صديق"
    
    text_parts = message.text.split()
    ref_id = None
    if len(text_parts) > 1:
        ref_id = text_parts[1].replace('ref_', '').strip()
        
    database.init_user(tg_id, ref_id, first_name)
    
    markup = InlineKeyboardMarkup()
    web_app_url = f"https://t.me/{BOT_USERNAME}/{APP_SHORT_NAME}"
    if ref_id:
        web_app_url += f"?startapp={ref_id}"
        
    btn_game = InlineKeyboardButton("🎮 دخول اللعبة وابدأ التجميع الآن", web_app=WebAppInfo(url=web_app_url))
    btn_channel = InlineKeyboardButton("📢 تابع قناة اللعبة الرسمية", url="https://t.me/zngoxe")
    markup.add(btn_game)
    markup.add(btn_channel)
    
    bot.send_message(message.chat.id, f"🔥 أهلاً بك يا {first_name} في عالم الـ Zn Goxe! 🔥\nالعب، اجمع الـ ZN، وادعُ أصدقاءك لزيادة أرباحك.", reply_markup=markup)

if __name__ == '__main__':
    database.create_tables()
    bot.remove_webhook()
    bot_thread = threading.Thread(target=lambda: bot.infinity_polling(allowed_updates=telebot.util.update_types))
    bot_thread.daemon = True
    bot_thread.start()
    
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
