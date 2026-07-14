import os
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import database # ملفك الأصلي

BOT_TOKEN = os.environ.get('BOT_TOKEN')
WEB_URL = os.environ.get('WEB_URL', 'https://zn-goxe-production.up.railway.app')

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# الثوابت (مطابقة تماماً لما هو موجود في منطق اللعبة)
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

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/api/user_data', methods=['GET'])
def get_user_data():
    tg_id = request.args.get('tg_id')
    user = database.get_user_data(str(tg_id))
    if not user: return jsonify({'error': 'User not found'}), 404
    
    # ... (باقي منطق حساب الأرباح اللي عندك سيبه زي ما هو)
    return jsonify(user) 

@app.route('/api/upgrade', methods=['POST'])
def handle_upgrade():
    data = request.json or {}
    tg_id = str(data.get('tg_id'))
    upgrade_type = data.get('type')
    level_num = int(data.get('level_num', 0))
    
    user = database.get_user_data(tg_id)
    if not user: return jsonify({'error': 'User not found'}), 404

    current_balance = user.get('balance', 0)
    
    if upgrade_type == 'mining':
        cost = MINING_PACKAGES[level_num]["price"]
        if current_balance < cost: return jsonify({'error': 'Not enough balance'}), 400
        database.update_balance(tg_id, current_balance - cost)
        database.update_upgrade_level(tg_id, f"lvl{level_num}_count", user.get(f"lvl{level_num}_count", 0) + 1)
        
    elif upgrade_type == 'storage':
        cost = STORAGE_PACKAGES[level_num]["price"]
        if current_balance < cost: return jsonify({'error': 'Not enough balance'}), 400
        database.update_balance(tg_id, current_balance - cost)
        # نستخدم الدالة الجديدة اللي عملناها في database.py
        database.update_storage_level(tg_id, level_num)
        
    return jsonify({'success': True})

# ... (باقي كود البوت والـ Start سيبه زي ما هو)
