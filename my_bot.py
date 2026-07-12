import os
import threading
from flask import Flask, request, jsonify, send_from_directory
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import database

BOT_TOKEN = os.environ.get('BOT_TOKEN')
WEB_URL = os.environ.get('WEB_URL', 'https://zn-goxe-production.up.railway.app')

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__, static_folder='.', static_url_path='')

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/api/user_data', methods=['GET'])
def get_user_data():
    tg_id = request.args.get('tg_id')
    if not tg_id:
        return jsonify({'error': 'Missing telegram ID'}), 400
    user = database.get_user_data(int(tg_id))
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify({
        'telegram_id': user['telegram_id'],
        'balance': user['balance'],
        'is_banned': user['is_banned'],
        'upgrades': {f'lvl{i}': user[f'lvl{i}_count'] for i in range(1, 11)}
    })

@app.route('/api/click', methods=['POST'])
def handle_click():
    data = request.json
    tg_id = data.get('tg_id')
    if not tg_id:
        return jsonify({'error': 'Missing telegram ID'}), 400
    user = database.get_user_data(int(tg_id))
    if not user:
        return jsonify({'error': 'User not found'}), 404
    click_power = 1
    for i in range(1, 11):
        click_power += user[f'lvl{i}_count'] * i
    new_balance = user['balance'] + click_power
    database.update_balance(int(tg_id), new_balance)
    return jsonify({'success': True, 'new_balance': new_balance})

@app.route('/api/upgrade', methods=['POST'])
def handle_upgrade():
    data = request.json
    tg_id = data.get('tg_id')
    lvl_num = data.get('lvl_num')
    if not tg_id or not lvl_num:
        return jsonify({'error': 'Missing data'}), 400
    user = database.get_user_data(int(tg_id))
    if not user:
        return jsonify({'error': 'User not found'}), 404
    lvl_column = f"lvl{lvl_num}_count"
    current_lvl = user[lvl_column]
    upgrade_cost = (current_lvl + 1) * 100 
    if user['balance'] < upgrade_cost:
        return jsonify({'error': 'Not enough balance'}), 400
    new_balance = user['balance'] - upgrade_cost
    new_level = current_lvl + 1
    database.update_balance(int(tg_id), new_balance)
    database.update_upgrade_level(int(tg_id), lvl_column, new_level)
    return jsonify({'success': True, 'new_balance': new_balance, 'new_level': new_level, 'lvl_num': lvl_num})

# ==========================================
# 🤖 أمر التشغيل المطور والرسالة التحفيزية
# ==========================================
@bot.message_handler(commands=['start'])
def start_command(message):
    tg_id = message.from_user.id
    database.init_user(tg_id)
    
    # تجهيز لوحة الأزرار الشفافة
    markup = InlineKeyboardMarkup()
    
    # 1. زرار فتح اللعبة المصغرة
    clean_web_url = WEB_URL.lower().strip()
    web_app_url = f"{clean_web_url}?tg_id={tg_id}"
    btn_game = InlineKeyboardButton("🎮 دخول اللعبة وابدأ التجميع الآن", web_app=WebAppInfo(url=web_app_url))
    
    # 2. زرار الانضمام للقناة التليجرام
    btn_channel = InlineKeyboardButton("📢 تابع قناة اللعبة الرسمية", url="https://t.me/zngoxe")
    
    # إضافة الأزرار تحت بعضها بشكل منظم
    markup.add(btn_game)
    markup.add(btn_channel)
    
    # نص الرسالة التحفيزية المليئة بالحماس
    motivational_text = (
        f"🔥 أهلاً بك يا {message.from_user.first_name} في عالم الـ Zn Goxe المثير! 🔥\n\n"
        f"🚀 فرصة ذهبية مستنياك لتجميع العملات وتطوير إمبراطوريتك الرقمية من الصفر! "
        f"كل ضغطة بتزود رصيدك، وكل ترقية بتشتريها بتضاعف قوتك وتخليك تتصدر قائمة الأبطال. "
        f"بياناتك متأمنة في السحاب ومش هتضيع أبداً، لا تضيع ثانية واحدة وابدأ رحلة المليون الآن!\n\n"
        f"📢 تأكد من الانضمام لقناتنا الرسمية لمتابعة المسابقات، الهدايا، والكود اليومي للمكافآت:\n"
        f"🔗 https://t.me/zngoxe\n\n"
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
