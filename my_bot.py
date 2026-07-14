import os
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import telebot
from telebot.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
import database

BOT_TOKEN = os.environ.get('BOT_TOKEN')
WEB_URL = os.environ.get('WEB_URL', 'https://zn-goxe-production.up.railway.app')

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

MINING_PACKAGES = {i: {"price": [1000,3000,7000,15000,30000,60000,120000,250000,500000,1000000][i-1], 
                      "boost": [500,1200,2500,5000,10000,22000,45000,100000,250000,600000][i-1]} for i in range(1,11)}

STORAGE_PACKAGES = {i: {"price": [2000,5000,10000,25000,50000,100000,250000,500000][i-1], 
                       "cap": [20000,30000,50000,100000,250000,500000,1000000,2500000][i-1]} for i in range(1,9)}

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/api/user_data', methods=['GET'])
def get_user_data():
    tg_id = request.args.get('tg_id')
    user = database.get_user_data(tg_id)
    if not user: return jsonify({'error': 'Not found'}), 404
    return jsonify(user)

@app.route('/api/upgrade', methods=['POST'])
def handle_upgrade():
    data = request.json
    tg_id = str(data.get('tg_id'))
    upgrade_type = data.get('type')
    level_num = int(data.get('level_num'))
    
    user = database.get_user_data(tg_id)
    current_balance = user.get('balance', 0)
    
    if upgrade_type == 'mining':
        cost = MINING_PACKAGES[level_num]["price"]
        if current_balance < cost: return jsonify({'error': 'Low balance'}), 400
        database.update_balance(tg_id, current_balance - cost)
        database.update_upgrade_level(tg_id, f"lvl{level_num}_count", user.get(f"lvl{level_num}_count", 0) + 1)
        
    elif upgrade_type == 'storage':
        cost = STORAGE_PACKAGES[level_num]["price"]
        if current_balance < cost: return jsonify({'error': 'Low balance'}), 400
        database.update_balance(tg_id, current_balance - cost)
        database.update_storage_level(tg_id, level_num)
        
    return jsonify({'success': True})

@bot.message_handler(commands=['start'])
def start(message):
    tg_id = message.from_user.id
    database.init_user(tg_id)
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎮 العب الآن", web_app=WebAppInfo(url=f"{WEB_URL}?tg_id={tg_id}")))
    bot.send_message(message.chat.id, "أهلاً بك! اضغط للبدء:", reply_markup=markup)

if __name__ == '__main__':
    threading.Thread(target=lambda: bot.infinity_polling()).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
