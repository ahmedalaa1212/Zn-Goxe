import os
import json
import tempfile
import threading
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBAPP_URL = os.environ.get("WEB_URL", "https://admin-zn-production.up.railway.app/") 
ADMIN_ID = "5102387551"

db = None
try:
    if not firebase_admin._apps:
        firebase_env = os.environ.get("FIREBASE_CREDENTIALS") or os.environ.get("FIREBASE_KEY")
        if firebase_env:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_file:
                temp_file.write(firebase_env)
                temp_path = temp_file.name
            cred = credentials.Certificate(temp_path)
            firebase_admin.initialize_app(cred)
        elif os.path.exists("firebase.json"):
            cred = credentials.Certificate("firebase.json")
            firebase_admin.initialize_app(cred)
        else:
            firebase_admin.initialize_app()
    db = firestore.client()
    print("✅ تم الاتصال بقاعدة بيانات Firestore بنجاح!")
except Exception as e:
    print(f"❌ خطأ في الاتصال بـ Firebase: {e}")

app = Flask(__name__, static_folder='.')
CORS(app)

@app.route('/')
def home():
    return send_from_directory('.', 'admin.html')

@app.route('/<path:filename>')
def serve_files(filename):
    return send_from_directory('.', filename)

@app.route('/api/status', methods=['GET'])
def server_status():
    return jsonify({
        'status': 'online',
        'system': 'Admin ZN Control Server',
        'firebase_connected': db is not None
    }), 200

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def is_admin(user_id):
    str_id = str(user_id)
    if str_id == str(ADMIN_ID):
        return True
    if not db:
        return False
    try:
        doc_ref = db.collection('moderators').document(str_id)
        return doc_ref.get().exists
    except Exception as e:
        print(f"❌ خطأ أثناء التحقق من المشرف: {e}")
        return False

bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "⛔ عذراً، هذا البوت مخصص للأدمن والمشرفين المصرح لهم فقط.")
        return

    markup = InlineKeyboardMarkup()
    webapp = WebAppInfo(url=WEBAPP_URL)
    btn = InlineKeyboardButton(text="💻 فتح لوحة التحكم", web_app=webapp)
    markup.add(btn)

    bot.send_message(
        message.chat.id,
        "👑 **أهلاً بك يا مدير!**\n\nتم التحقق من صلاحياتك بنجاح، اضغط لفتح لوحة التحكم:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

if __name__ == "__main__":
    print("🌐 جاري تشغيل سيرفر الويب...")
    threading.Thread(target=run_web_server, daemon=True).start()
    
    if bot:
        print("🤖 بوت الأدمن قيد التشغيل...")
        bot.infinity_polling()
    else:
        print("❌ خطأ: يرجى التأكد من ضبط BOT_TOKEN في متغيرات البيئة.")
