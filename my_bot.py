import os
import threading
import json
from datetime import datetime, timezone
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import database
import requests

BOT_TOKEN = os.environ.get('BOT_TOKEN')
WEB_URL = os.environ.get('WEB_URL', 'https://zn-goxe-production.up.railway.app')

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
        if last_claim.tzinfo is None:
            last_claim = last_claim.replace(tzinfo=timezone.utc)
            
        seconds_passed = (datetime.now(timezone.utc) - last_claim).total_seconds()
        if seconds_passed < 0: seconds_passed = 0

        hourly_rate = BASE_MINING_RATE
        for i in range(1, 11):
            count = user.get(f'lvl{i}_count', 0)
            hourly_rate += count * MINING_PACKAGES.get(i, {}).get("boost", 0)

        storage_lvl = user.get('storage_level', 0)
        max_cap = STORAGE_PACKAGES.get(storage_lvl, {}).get("cap", BASE_STORAGE_CAP)

        unclaimed = seconds_passed * (hourly_rate / 3600.0)
        if unclaimed > max_cap: unclaimed = max_cap
            
        return int(unclaimed), hourly_rate, max_cap
    except Exception as e:
        print(f"Error calculating unclaimed: {e}")
        return 0, BASE_MINING_RATE, BASE_STORAGE_CAP

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

# (لقد تم حذف الـ Routes المكررة من هنا لأنه يجب أن يعمل server.py كخادم API)
# لو كنت تستخدم my_bot.py كخادم أساسي، يمكنك تركها كما هي. هنا نركز على البوت نفسه:

@bot.message_handler(commands=['start'])
def start_command(message):
    tg_id = str(message.from_user.id).strip()
    user_name = message.from_user.first_name
    
    # 1. استخراج كود الإحالة لو دخل من رابط صديق
    ref_payload = message.text.replace("/start", "").strip()
    ref_id = ref_payload.replace("ref_", "") if ref_payload.startswith("ref_") else None
    
    # 2. إنشاء الحساب مع نظام الإحالة وتسجيل الصديق وإرسال الإشعار
    if database.db is None: database.initialize_firebase()
    user_ref = database.db.collection('users').document(tg_id)
    doc = user_ref.get()
    
    if not doc.exists:
        new_user = {
            'telegram_id': tg_id,
            'user_name': user_name,
            'balance': 0.0,
            'ad_balance': 0.0,
            'is_banned': False,
            'last_claim_time': datetime.utcnow().isoformat(),
            'storage_level': 0,
            'referred_by': ref_id if (ref_id and ref_id != tg_id) else None,
            'pending_ref_earnings': 0.0,
            'invited_friends_count': 0,
            'claimed_ref_tasks': [],
            'contributed_to_referrer': 0.0
        }
        for i in range(1, 11): new_user[f'lvl{i}_count'] = 0
        user_ref.set(new_user)
        
        # إذا دخل من رابط صديق، نزود العداد للصديق ونبعتله إشعار!
        if new_user['referred_by']:
            referrer_ref = database.db.collection('users').document(new_user['referred_by'])
            ref_doc = referrer_ref.get()
            if ref_doc.exists:
                r_data = ref_doc.to_dict()
                ref_count = r_data.get('invited_friends_count', 0)
                referrer_ref.update({'invited_friends_count': ref_count + 1})
                
                # 🔥 إرسال الإشعار الاحترافي 🔥
                try:
                    notify_text = (
                        f"🎉 <b>أخبار رائعة!</b>\n\n"
                        f"لقد انضم <b>{user_name}</b> للتو إلى اللعبة باستخدام رابط الإحالة الخاص بك!\n\n"
                        f"💰 ستحصل الآن على 10% من أرباح التعدين الخاصة به مدى الحياة. استمر في دعوة المزيد لمضاعفة أرباحك! 🚀"
                    )
                    bot.send_message(new_user['referred_by'], notify_text, parse_mode="HTML")
                except Exception as e:
                    print("Error sending notification:", e)
    else:
        # لو الحساب موجود، نحدث اسمه بس لو اتغير
        user_ref.update({'user_name': user_name})

    # 3. إرسال أزرار الدخول
    markup = InlineKeyboardMarkup()
    clean_web_url = WEB_URL.lower().strip()
    
    # تمرير الـ ref_id داخل الويب آب لزيادة الأمان
    web_app_url = f"{clean_web_url}?tg_id={tg_id}&ref_id={ref_id}" if ref_id else f"{clean_web_url}?tg_id={tg_id}"
    
    btn_game = InlineKeyboardButton("🎮 دخول اللعبة وابدأ التجميع الآن", web_app=WebAppInfo(url=web_app_url))
    btn_channel = InlineKeyboardButton("📢 تابع قناة اللعبة الرسمية", url="https://t.me/zngoxe")
    markup.add(btn_game)
    markup.add(btn_channel)
    
    motivational_text = (
        f"🔥 أهلاً بك يا {user_name} في عالم الـ Zn Goxe المثير! 🔥\n\n"
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
