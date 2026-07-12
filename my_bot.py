import os
import threading
from flask import Flask, request, jsonify, send_from_directory
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import database

# جلب توكن البوت ورابط الموقع من متغيرات بيئة سيرفر Railway
BOT_TOKEN = os.environ.get('BOT_TOKEN')
WEB_URL = os.environ.get('WEB_URL', 'https://your-app-name.up.railway.app')

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__, static_folder='.', static_url_path='')

# ==========================================
# 🌐 أقسام السيرفر والـ API (الخاصة باللعبة index.html)
# ==========================================

@app.route('/')
def serve_index():
    """عرض صفحة اللعبة الرئيسية للمستخدم"""
    return send_from_directory('.', 'index.html')

@app.route('/api/user_data', methods=['GET'])
def get_user_data():
    """جلب بيانات اللاعب (الرصيد والترقيات) لعرضها جوه اللعبة"""
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
    """حساب الضغطات وزيادة الرصيد بأمان بناءً على مستوى الترقيات"""
    data = request.json
    tg_id = data.get('tg_id')
    if not tg_id:
        return jsonify({'error': 'Missing telegram ID'}), 400
        
    user = database.get_user_data(int(tg_id))
    if not user:
        return jsonify({'error': 'User not found'}), 404

    # حسبة قوة الضغطة: المستوى الأساسي 1 + (مستويات الترقيات المشتراه)
    # تقدر تعدل الحسبة دي براحتك لتغيير قوة كل مستوى ترقية
    click_power = 1
    for i in range(1, 11):
        click_power += user[f'lvl{i}_count'] * i
    
    new_balance = user['balance'] + click_power
    database.update_balance(int(tg_id), new_balance)
    
    return jsonify({'success': True, 'new_balance': new_balance})

@app.route('/api/upgrade', methods=['POST'])
def handle_upgrade():
    """شراء ترقية وخصم الرصيد وتحديث مستواها في قاعدة البيانات"""
    data = request.json
    tg_id = data.get('tg_id')
    lvl_num = data.get('lvl_num') # رقم الترقية المرسل من اللعبة من 1 لـ 10
    
    if not tg_id or not lvl_num:
        return jsonify({'error': 'Missing data'}), 400
        
    user = database.get_user_data(int(tg_id))
    if not user:
        return jsonify({'error': 'User not found'}), 404
        
    lvl_column = f"lvl{lvl_num}_count"
    current_lvl = user[lvl_column]
    
    # معادلة سعر الترقية: السعر يرتفع كل ما المستوى زاد (المستوى الحالي + 1) * 100
    upgrade_cost = (current_lvl + 1) * 100 
    
    if user['balance'] < upgrade_cost:
        return jsonify({'error': 'Not enough balance'}), 400
        
    # تنفيذ عملية الشراء والخصم
    new_balance = user['balance'] - upgrade_cost
    new_level = current_lvl + 1
    
    database.update_balance(int(tg_id), new_balance)
    database.update_upgrade_level(int(tg_id), lvl_column, new_level)
    
    return jsonify({
        'success': True, 
        'new_balance': new_balance, 
        'new_level': new_level,
        'lvl_num': lvl_num
    })

# ==========================================
# 🤖 أوامر البوت على تليجرام
# ==========================================

@bot.message_handler(commands=['start'])
def start_command(message):
    """الترحيب باللاعب وفتح اللعبة المصغرة له"""
    tg_id = message.from_user.id
    # إنشاء المستخدم في قاعدة البيانات فوراً لو أول مرة يدخل
    database.init_user(tg_id)
    
    # تجهيز زرار فتح اللعبة الـ Mini App
    markup = InlineKeyboardMarkup()
    web_app_url = f"{WEB_URL}?tg_id={tg_id}"
    btn = InlineKeyboardButton("🎮 افتح اللعبة وابدأ تجميع الرصيد", web_app=WebAppInfo(url=web_app_url))
    markup.add(btn)
    
    bot.send_message(
        message.chat.id, 
        f"أهلاً بك يا {message.from_user.first_name} في لعبة الضغط والترقيات المطورة! 🚀\n\n"
        f"اضغط على الزرار بالأسفل لفتح اللعبة حلياً، بياناتك متأمنة دلوقتي في السحاب ومش هتضيع تاني أبداً!", 
        reply_markup=markup
    )

# ==========================================
# 🚀 تشغيل البوت والسيرفر معاً في نفس الوقت
# ==========================================

if __name__ == '__main__':
    # تشغيل استقبال رسائل البوت في خلفية السيرفر (Thread) عشان ما يعطلش اللعبة
    bot.remove_webhook()
    bot_thread = threading.Thread(target=lambda: bot.infinity_polling(allowed_updates=telebot.util.update_types))
    bot_thread.daemon = True
    bot_thread.start()
    
    # تشغيل سيرفر الويب الخاص بالـ Mini App على المنفذ المخصص من Railway
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
