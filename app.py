import os
import json
import tempfile
import threading
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

app = Flask(__name__)
CORS(app)

# =========================================
# 1. إعداد المتغيرات الأساسية
# =========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBAPP_URL = os.environ.get("WEB_URL", "https://admin-zn-production.up.railway.app/") 
ADMIN_ID = "5102387551" # ⚠️ الـ ID الخاص بك (المدير الأساسي)

# =========================================
# 2. تهيئة الاتصال بـ Firebase Firestore
# =========================================
db = None

def init_firebase():
    global db
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
        print(f"❌ خطأ في تهيئة Firebase: {e}")
        db = None

init_firebase()

# دالة التحقق من المستخدم وإرجاع بياناته وصلاحياته
def get_user_data(user_id):
    str_id = str(user_id).strip()
    
    # الأدمن الأساسي له كافة الصلاحيات المطلقة
    if str_id == str(ADMIN_ID):
        return {
            'is_admin': True,
            'name': 'المدير العام',
            'permissions': {'users': True, 'support': True, 'settings': True, 'transactions': True, 'security': True, 'ads': True}
        }
        
    if not db:
        return None
        
    try:
        doc_ref = db.collection('moderators').document(str_id)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            return {
                'is_admin': False,
                'name': data.get('name', 'مشرف'),
                'permissions': data.get('permissions', {})
            }
    except Exception as e:
        print(f"❌ خطأ في جلب بيانات المشرف: {e}")
        
    return None

# =========================================
# 3. إعداد بوت التليجرام ودمج التشغيل
# =========================================
bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    user_info = get_user_data(user_id)
    
    if not user_info:
        bot.reply_to(message, "⛔ عذراً، هذا البوت مخصص للأدمن والمشرفين المصرح لهم فقط.")
        return

    markup = InlineKeyboardMarkup()
    webapp = WebAppInfo(url=WEBAPP_URL)
    btn = InlineKeyboardButton(text="💻 فتح لوحة التحكم", web_app=webapp)
    markup.add(btn)

    greeting = f"👑 أهلاً بك يا {user_info['name']}!\n\nتم التحقق من صلاحياتك بنجاح، اضغط لفتح لوحة التحكم:"
    bot.send_message(message.chat.id, greeting, reply_markup=markup, parse_mode="Markdown")

def run_telegram_bot():
    if bot:
        print("🤖 بوت الأدمن والمشرفين قيد التشغيل...")
        bot.infinity_polling()
    else:
        print("⚠️ تنبيه: لم يتم العثور على BOT_TOKEN في متغيرات البيئة.")

if bot:
    threading.Thread(target=run_telegram_bot, daemon=True).start()

# =========================================
# 4. مسارات سيرفر الويب و الـ APIs (الأساسية)
# =========================================

@app.route('/', methods=['GET'])
def serve_admin_panel():
    return send_from_directory('.', 'admin.html')

@app.route('/<path:filename>')
def serve_static_files(filename):
    return send_from_directory('.', filename)

@app.route('/api/status', methods=['GET'])
def server_status():
    return jsonify({
        'status': 'online',
        'system': 'Admin ZN Control Server',
        'firebase_connected': db is not None,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }), 200

# مسار يتحقق من صلاحية المستخدم ويرسل صلاحياته للويب
@app.route('/api/verify/<user_id>', methods=['GET'])
def verify_user(user_id):
    user_info = get_user_data(user_id)
    if not user_info:
        return jsonify({'authorized': False}), 200
        
    return jsonify({
        'authorized': True,
        'is_admin': user_info['is_admin'],
        'name': user_info['name'],
        'permissions': user_info['permissions']
    }), 200

# أ. جلب قائمة المشرفين
@app.route('/api/moderators', methods=['GET'])
def get_moderators():
    if not db:
        return jsonify({'success': False, 'message': 'سيرفر قاعدة البيانات غير متصل'}), 500
    
    try:
        mods_ref = db.collection('moderators')
        docs = mods_ref.stream()
        
        mods_list = []
        for doc in docs:
            data = doc.to_dict()
            mods_list.append({
                'id': doc.id,
                'name': data.get('name', ''),
                'permissions': data.get('permissions', {}),
                'addedAt': data.get('addedAt', ''),
                'isMain': data.get('isMain', False)
            })
            
        return jsonify({'success': True, 'moderators': mods_list}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ب. إضافة مشرف جديد
@app.route('/api/moderators', methods=['POST'])
def add_moderator():
    if not db:
        return jsonify({'success': False, 'message': 'سيرفر قاعدة البيانات غير متصل'}), 500
    
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'success': False, 'message': 'بيانات الطلب غير صالحة'}), 400

        mod_id = str(data.get('id', '')).strip()
        mod_name = str(data.get('name', '')).strip()
        permissions = data.get('permissions', {})
        admin_who_added = data.get('addedBy', 'المدير العام')

        if not mod_id or not mod_name or not mod_id.isdigit():
            return jsonify({'success': False, 'message': 'يرجى إدخال Telegram ID صحيح (أرقام فقط)'}), 400

        doc_ref = db.collection('moderators').document(mod_id)
        doc_ref.set({
            'name': mod_name,
            'permissions': permissions,
            'addedAt': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'isMain': False
        })

        log_ref = db.collection('admin_logs').document()
        log_ref.set({
            'admin': admin_who_added,
            'action': f"إضافة المشرف الجديد: {mod_name} (ID: {mod_id})",
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

        return jsonify({'success': True, 'message': f'تمت إضافة المشرف {mod_name} بنجاح'}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ج. حذف مشرف
@app.route('/api/moderators/<mod_id>', methods=['DELETE'])
def delete_moderator(mod_id):
    if not db:
        return jsonify({'success': False, 'message': 'سيرفر قاعدة البيانات غير متصل'}), 500
    
    try:
        mod_id = str(mod_id).strip()
        admin_who_deleted = request.args.get('deletedBy', 'المدير العام')
        
        doc_ref = db.collection('moderators').document(mod_id)
        doc = doc_ref.get()

        if not doc.exists:
            return jsonify({'success': False, 'message': 'المشرف غير موجود في قاعدة البيانات'}), 404

        mod_data = doc.to_dict()
        
        if mod_data.get('isMain') is True:
            return jsonify({'success': False, 'message': 'خطأ حماية: لا يمكن حذف حساب المدير الرئيسي'}), 403

        mod_name = mod_data.get('name', mod_id)
        doc_ref.delete()

        log_ref = db.collection('admin_logs').document()
        log_ref.set({
            'admin': admin_who_deleted,
            'action': f"حذف المشرف: {mod_name} (ID: {mod_id})",
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

        return jsonify({'success': True, 'message': f'تم حذف المشرف {mod_name} بنجاح'}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# د. جلب سجل النشاطات
@app.route('/api/admin-logs', methods=['GET'])
def get_admin_logs():
    if not db:
        return jsonify({'success': False, 'message': 'سيرفر قاعدة البيانات غير متصل'}), 500
    
    try:
        logs_ref = db.collection('admin_logs').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(25)
        docs = logs_ref.stream()
        
        logs_list = []
        for doc in docs:
            logs_list.append(doc.to_dict())

        return jsonify({'success': True, 'logs': logs_list}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# =========================================
# 5. مسارات قسم بيانات المستخدمين (Users)
# =========================================

# جلب قائمة المستخدمين
@app.route('/api/users', methods=['GET'])
def get_all_users():
    if not db:
        return jsonify({'success': False, 'message': 'سيرفر قاعدة البيانات غير متصل'}), 500
    
    try:
        # بنجلب آخر 100 مستخدم
        users_ref = db.collection('users').limit(100)
        docs = users_ref.stream()
        
        users_list = []
        for doc in docs:
            data = doc.to_dict()
            users_list.append({
                'id': doc.id,
                'name': data.get('name', 'بدون اسم'),
                'balance': data.get('balance', 0),
                'joinDate': data.get('joinDate', 'غير معروف'),
                'isBanned': data.get('isBanned', False)
            })
            
        return jsonify({'success': True, 'users': users_list}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# التحكم في المستخدم (حظر / فك حظر / إضافة رصيد / خصم رصيد)
@app.route('/api/users/<user_id>/action', methods=['POST'])
def user_action(user_id):
    if not db:
        return jsonify({'success': False, 'message': 'قاعدة البيانات غير متصلة'}), 500
    
    try:
        data = request.get_json(silent=True) or {}
        action = data.get('action') 
        value = data.get('value', 0)
        
        doc_ref = db.collection('users').document(str(user_id).strip())
        doc = doc_ref.get()
        
        # التأكد من وجود المستند، وإنشائه إذا كان غير موجود
        if not doc.exists:
            current_time = datetime.now().strftime('%Y-%m-%d %I:%M %p') # إضافة الوقت مع التاريخ
            doc_ref.set({
                'name': 'بدون اسم',
                'balance': 0,
                'joinDate': current_time,
                'isBanned': False
            })
            doc = doc_ref.get()

        curr_data = doc.to_dict() or {}
        action_text = ""

        if action == 'ban':
            doc_ref.update({'isBanned': True})
            action_text = f"حظر المستخدم {user_id}"

        elif action == 'unban':
            doc_ref.update({'isBanned': False})
            action_text = f"فك حظر المستخدم {user_id}"

        elif action == 'add_balance':
            val = abs(int(value))
            doc_ref.update({'balance': firestore.Increment(val)})
            action_text = f"إضافة {val} لرصيد المستخدم {user_id}"

        elif action == 'deduct_balance':
            val = abs(int(value))
            current_bal = curr_data.get('balance', 0)
            new_bal = max(0, current_bal - val)
            doc_ref.update({'balance': new_bal})
            action_text = f"خصم {val} من رصيد المستخدم {user_id}"

        else:
            return jsonify({'success': False, 'message': 'إجراء غير معروف'}), 400
            
        # تسجيل الحركة في السجل
        try:
            log_ref = db.collection('admin_logs').document()
            log_ref.set({
                'admin': 'النظام / المشرف',
                'action': action_text,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        except Exception as e_log:
            print(f"⚠️ خطأ في تسجيل اللوج: {e_log}")
            
        return jsonify({'success': True, 'message': 'تم تنفيذ الإجراء وتحديث قاعدة البيانات بنجاح'})

    except Exception as e:
        print(f"❌ خطأ في تنفيذ إجراء المستخدم: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
