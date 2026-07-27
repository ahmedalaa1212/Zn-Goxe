import os
import json
import hmac
import hashlib
import urllib.parse
import tempfile
import threading
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from flask import Flask, send_from_directory, jsonify, request
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

# ==========================================
# 🛡️ دالة التحقق الأمني الرقمي لبيانات تليجرام
# ==========================================
def validate_telegram_admin(init_data):
    if not init_data or not BOT_TOKEN:
        return None
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data))
        hash_from_telegram = parsed_data.pop('hash', None)
        if not hash_from_telegram:
            return None
        
        data_check_string = '\n'.join([f"{k}={v}" for k, v in sorted(parsed_data.items())])
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if calculated_hash == hash_from_telegram:
            user_data = json.loads(parsed_data.get('user', '{}'))
            user_id = str(user_data.get('id'))
            
            # 1. فحص هل هو الأدمن الرئيسي؟
            if user_id == str(ADMIN_ID):
                return {"user": user_data, "role": "Super Admin", "is_owner": True}
                
            # 2. فحص هل هو مشرف مضاف في الفايربيس؟
            if db:
                mod_doc = db.collection('moderators').document(user_id).get()
                if mod_doc.exists:
                    mod_data = mod_doc.to_dict() or {}
                    return {"user": user_data, "role": "مشرف", "is_owner": False, "permissions": mod_data.get('permissions', {})}
                    
        return None
    except Exception as e:
        print(f"Auth Error: {e}")
        return None

# ==========================================
# 🔗 تسجيل المجلدات والـ APIs
# ==========================================
try:
    from admin_chat.admin_chat_api import admin_chat_bp
    app.register_blueprint(admin_chat_bp, url_prefix='/api/admin/chat')
    print("✅ تم تسجيل API الدردشة والدعم بنجاح")
except ImportError as e:
    print(f"⚠️ لم يتم العثور على ملف admin_chat/admin_chat_api.py: {e}")

# ==========================================
# 🌐 المسارات الرئيسية
# ==========================================
@app.route('/')
def home():
    return send_from_directory('.', 'admin.html')

@app.route('/<path:filename>')
def serve_files(filename):
    return send_from_directory('.', filename)

@app.route('/api/verify_admin', methods=['POST'])
def verify_admin_endpoint():
    init_data = request.headers.get('X-Telegram-Init-Data')
    auth_info = validate_telegram_admin(init_data)
    
    if not auth_info:
        return jsonify({"success": False, "message": "غير مصرح لك بالدخول!"}), 403
        
    return jsonify({
        "success": True,
        "role": auth_info["role"],
        "user": auth_info["user"]
    }), 200

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = str(message.from_user.id)
    
    # فحص الحماية للبوت
    is_authorized = (user_id == str(ADMIN_ID))
    if not is_authorized and db:
        is_authorized = db.collection('moderators').document(user_id).get().exists

    if not is_authorized:
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
