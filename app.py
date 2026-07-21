import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

app = Flask(__name__)
# السطر ده بيسمح لواجهة الويب بتاعتك إنها تتصل بالسيرفر بدون مشاكل
CORS(app) 

# =========================================
# 1. الاتصال بقاعدة بيانات Firestore
# =========================================
# تأكد إنك حاطط ملف مفتاح الفايربيس (مثلاً firebase.json) 
# أو معرفه في Railway زي ما أنت عامل في الـ Variables
if not firebase_admin._apps:
    try:
        # لو حاطط الملف جوه المشروع
        cred = credentials.Certificate('firebase.json')
        firebase_admin.initialize_app(cred)
    except:
        # لو بتستخدم المتغيرات اللي في Railway
        firebase_admin.initialize_app()

db = firestore.client()

# =========================================
# 2. مسارات (APIs) الإدارة العليا
# =========================================

# أ. جلب المشرفين
@app.route('/api/moderators', methods=['GET'])
def get_moderators():
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
    try:
        data = request.json
        mod_id = str(data.get('id')).strip()
        mod_name = data.get('name').strip()
        permissions = data.get('permissions', {})
        admin_who_added = data.get('addedBy', 'المدير العام')

        if not mod_id or not mod_name:
            return jsonify({'success': False, 'message': 'البيانات ناقصة'}), 400

        # حفظ في Firestore
        doc_ref = db.collection('moderators').document(mod_id)
        doc_ref.set({
            'name': mod_name,
            'permissions': permissions,
            'addedAt': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'isMain': False
        })

        # تسجيل الحركة
        log_ref = db.collection('admin_logs').document()
        log_ref.set({
            'admin': admin_who_added,
            'action': f"إضافة المشرف الجديد: {mod_name} (ID: {mod_id})",
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

        return jsonify({'success': True, 'message': 'تم إضافة المشرف بنجاح'}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ج. حذف مشرف
@app.route('/api/moderators/<mod_id>', methods=['DELETE'])
def delete_moderator(mod_id):
    try:
        admin_who_deleted = request.args.get('deletedBy', 'المدير العام')
        doc_ref = db.collection('moderators').document(mod_id)
        doc = doc_ref.get()

        if not doc.exists:
            return jsonify({'success': False, 'message': 'المشرف غير موجود'}), 404

        mod_data = doc.to_dict()
        if mod_data.get('isMain'):
            return jsonify({'success': False, 'message': 'لا يمكن حذف المدير الأساسي'}), 403

        mod_name = mod_data.get('name', mod_id)
        
        # الحذف من Firestore
        doc_ref.delete()

        # تسجيل الحركة
        log_ref = db.collection('admin_logs').document()
        log_ref.set({
            'admin': admin_who_deleted,
            'action': f"حذف المشرف: {mod_name} (ID: {mod_id})",
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

        return jsonify({'success': True, 'message': 'تم حذف المشرف بنجاح'}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# د. جلب سجل النشاطات
@app.route('/api/admin-logs', methods=['GET'])
def get_admin_logs():
    try:
        # بنجلب السجلات ونرتبها بالتاريخ (أحدث حاجة الأول) وبنجيب آخر 20 بس
        logs_ref = db.collection('admin_logs').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(20)
        docs = logs_ref.stream()
        
        logs_list = []
        for doc in docs:
            logs_list.append(doc.to_dict())

        return jsonify({'success': True, 'logs': logs_list}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    # لازم السيرفر يشتغل على البورت اللي Railway بتحدده
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
