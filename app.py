import os
import json
import subprocess
import threading
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore

# إنشاء تطبيق Flask وتفعيل الـ CORS لتأمين واستقبال طلبات الويب
app = Flask(__name__)
CORS(app)

# =========================================
# 1. تشغيل بوت التليجرام (admin_bot.py) في الخلفية بأمان
# =========================================
def start_bot_process():
    try:
        if os.path.exists("admin_bot.py"):
            print("🚀 جاري تشغيل admin_bot.py في عملية منفصلة...")
            subprocess.Popen(["python", "my_bot.py"])
        else:
            print("⚠️ تنبيه: ملف admin_bot.py غير موجود في المجلد الرئيسي!")
    except Exception as e:
        print(f"❌ خطأ أثناء تشغيل ملف البوت: {e}")

# تشغيل البوت في Thread منفصل مع بداية إقلاع السيرفر
threading.Thread(target=start_bot_process, daemon=True).start()


# =========================================
# 2. تهيئة الاتصال بـ Firebase Firestore مع الحماية
# =========================================
db = None

def init_firebase():
    global db
    try:
        if not firebase_admin._apps:
            # 1. جلب المفتاح من متغيرات البيئة في Railway (لحماية البيانات من التسريب)
            firebase_env = os.environ.get("FIREBASE_CREDENTIALS") or os.environ.get("FIREBASE_KEY")
            
            if firebase_env:
                try:
                    cred_dict = json.loads(firebase_env)
                    cred = credentials.Certificate(cred_dict)
                except Exception:
                    cred = credentials.Certificate(firebase_env)
                firebase_admin.initialize_app(cred)
            elif os.path.exists("firebase.json"):
                cred = credentials.Certificate("firebase.json")
                firebase_admin.initialize_app(cred)
            else:
                # الاتصال الافتراضي للبيئة
                firebase_admin.initialize_app()
                
        db = firestore.client()
        print("✅ تم الاتصال بقاعدة بيانات Firestore بنجاح!")
    except Exception as e:
        print(f"❌ خطأ في تهيئة Firebase: {e}")

init_firebase()


# =========================================
# 3. مسارات الـ APIs الكاملة (لوحة التحكم)
# =========================================

# مسار الفحص السريع لحالة السيرفر
@app.route('/', methods=['GET'])
def index():
    return jsonify({
        'status': 'online',
        'system': 'Admin ZN Control Server',
        'firebase_connected': db is not None,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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


# ب. إضافة مشرف جديد (مع فحص الحماية والبيانات)
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

        # فحص الحماية: تأمين البيانات ومنع الإدخال الفارغ أو الأرقام الخاطئة
        if not mod_id or not mod_name or not mod_id.isdigit():
            return jsonify({'success': False, 'message': 'يرجى إدخال Telegram ID صحيح (أرقام فقط) واسم للمشرف'}), 400

        # إضافة/تحديث المشرف في Firestore
        doc_ref = db.collection('moderators').document(mod_id)
        doc_ref.set({
            'name': mod_name,
            'permissions': permissions,
            'addedAt': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'isMain': False
        })

        # تسجيل العملية في سجل النشاطات (Admin Logs)
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
        
        # حماية حساب المدير الأساسي من الحذف
        if mod_data.get('isMain') is True:
            return jsonify({'success': False, 'message': 'خطأ حماية: لا يمكن حذف حساب المدير الرئيسي'}), 403

        mod_name = mod_data.get('name', mod_id)
        
        # تنفيذ الحذف من الفايربيس
        doc_ref.delete()

        # تسجيل حركة الحذف في السجل
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
# تشغيل السيرفر المحلي والإنتاج
# =========================================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
