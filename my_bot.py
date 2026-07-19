import os
import threading
import json
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import database

BOT_TOKEN = os.environ.get('BOT_TOKEN')
WEB_URL = os.environ.get('WEB_URL', 'https://zn-goxe-production.up.railway.app')

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# القوانين والثوابت الخاصة بباقات التعدين وسعة التخزين
BASE_MINING_RATE = 20  # عملة في الساعة مجاناً كبداية
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
    """حساب الأرباح التي تم تعدينها بأمان في السيرفر بناءً على الوقت المنقضي"""
    try:
        last_claim_str = user.get('last_claim_time', datetime.utcnow().isoformat())
        last_claim = datetime.fromisoformat(last_claim_str)
        seconds_passed = (datetime.utcnow() - last_claim).total_seconds()
        if seconds_passed < 0:
            seconds_passed = 0

        hourly_rate = BASE_MINING_RATE
        for i in range(1, 11):
            count = user.get(f'lvl{i}_count', 0)
            hourly_rate += count * MINING_PACKAGES[i]["boost"]

        storage_lvl = user.get('storage_level', 0)
        max_cap = STORAGE_PACKAGES.get(storage_lvl, {}).get("cap", BASE_STORAGE_CAP)

        unclaimed = seconds_passed * (hourly_rate / 3600.0)
        
        if unclaimed > max_cap:
            unclaimed = max_cap
            
        return int(unclaimed), hourly_rate, max_cap
    except Exception as e:
        print(f"Error calculating unclaimed: {e}")
        return 0, BASE_MINING_RATE, BASE_STORAGE_CAP

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/api/user_data', methods=['GET'])
def get_user_data():
    tg_id = request.args.get('tg_id')
    if not tg_id:
        return jsonify({'error': 'Missing telegram ID'}), 400
    
    user = database.get_user_data(str(tg_id))
    if not user:
        return jsonify({'error': 'User not found'}), 404
        
    unclaimed, hourly_rate, max_cap = calculate_unclaimed(user)
    
    return jsonify({
        'telegram_id': user.get('telegram_id'),
        'balance': user.get('balance', 0),
        'storage_level': user.get('storage_level', 0),
        'hourly_rate': hourly_rate,
        'max_cap': max_cap,
        'unclaimed': unclaimed,
        'upgrades': {f'lvl{i}': user.get(f'lvl{i}_count', 0) for i in range(1, 11)}
    })

@app.route('/api/claim', methods=['POST'])
def handle_claim():
    data = request.json or {}
    tg_id = data.get('tg_id')
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
    
    return jsonify({'success': True, 'new_balance': new_balance, 'unclaimed': 0})

@app.route('/api/upgrade', methods=['POST'])
def handle_upgrade():
    data = request.json or {}
    tg_id = str(data.get('tg_id'))
    upgrade_type = data.get('type') 
    level_num = int(data.get('level_num', 0))
    
    if not tg_id or not upgrade_type or not level_num:
        return jsonify({'error': 'Missing data'}), 400
        
    user = database.get_user_data(tg_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    current_balance = user.get('balance', 0)
    
    if upgrade_type == 'mining':
        lvl_column = f"lvl{level_num}_count"
        current_count = user.get(lvl_column, 0)
        if current_count >= 20:
            return jsonify({'error': 'Max level reached'}), 400
            
        cost = MINING_PACKAGES[level_num]["price"]
        if current_balance < cost:
            return jsonify({'error': 'Not enough balance'}), 400
            
        database.update_balance(tg_id, current_balance - cost)
        database.update_upgrade_level(tg_id, lvl_column, current_count + 1)
        
    elif upgrade_type == 'storage':
        current_storage_lvl = user.get('storage_level', 0)
        if level_num != current_storage_lvl + 1:
            return jsonify({'error': 'Must upgrade sequentially'}), 400
        if level_num not in STORAGE_PACKAGES:
            return jsonify({'error': 'Max storage level reached'}), 400
            
        cost = STORAGE_PACKAGES[level_num]["price"]
        if current_balance < cost:
            return jsonify({'error': 'Not enough balance'}), 400
            
        database.update_balance(tg_id, current_balance - cost)
        database.db.collection('users').document(tg_id).update({'storage_level': level_num})
        
    return jsonify({'success': True})

@bot.message_handler(commands=['start'])
def start_command(message):
    tg_id = message.from_user.id
    first_name = message.from_user.first_name or "صديقي"
    
    # 🔥 سحب كود الإحالة من رابط الدخول
    text_parts = message.text.split()
    ref_id = None
    if len(text_parts) > 1 and text_parts[1].startswith('ref_'):
        ref_id = text_parts[1].replace('ref_', '')
        
    # تسجيل المستخدم مع كود الإحالة
    database.init_user(str(tg_id), ref_id, first_name)
    
    markup = InlineKeyboardMarkup()
    clean_web_url = WEB_URL.lower().strip()
    # تمرير بيانات الدخول للويب اب
    web_app_url = f"{clean_web_url}?tg_id={tg_id}"
    if ref_id:
        web_app_url += f"&start_param=ref_{ref_id}"
        
    btn_game = InlineKeyboardButton("🎮 دخول اللعبة وابدأ التجميع الآن", web_app=WebAppInfo(url=web_app_url))
    btn_channel = InlineKeyboardButton("📢 تابع قناة اللعبة الرسمية", url="https://t.me/zngoxe")
    markup.add(btn_game)
    markup.add(btn_channel)
    
    motivational_text = (
        f"🔥 أهلاً بك يا {first_name} في عالم الـ Zn Goxe المثير! 🔥\n\n"
        f"🚀 فرصة ذهبية مستنياك لتجميع العملات وتطوير إمبراطوريتك الرقمية من الصفر! "
        f"جهاز التعدين الخاص بك يعمل الآن في السحاب ويجمع لك الأرباح ثانية بثانية حتى وأنت مغلق للتطبيق!\n\n"
        f"👇 اضغط على الأزرار بالأسفل وانطلق فوراً!"
    )
    bot.send_message(message.chat.id, motivational_text, reply_markup=markup)

if __name__ == '__main__':
    database.create_tables()
    bot.remove_webhook()
    bot_thread = threading.Thread(target=lambda: bot.infinity_polling(allowed_updates=telebot.util.update_types))
    bot_thread.daemon = True
    bot_thread.start()
    
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
