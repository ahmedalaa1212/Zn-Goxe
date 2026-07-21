from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime

# (تأكد أن السيرفر متصل بـ Firebase بالفعل)

# ================= =========================
# API الإدارة العليا (Super Admin Endpoints)
# =========================================

# 1. جلب قائمة المشرفين
@app.route('/api/moderators', methods=['GET'])
def get_moderators():
    try:
        ref = db.reference('moderators')
        mods = ref.get() or {}
        
        # تحويل البيانات لشكل القائمة
        mods_list = []
        for mod_id, data in mods.items():
            mods_list.append({
                'id': mod_id,
                'name': data.get('name', ''),
                'permissions': data.get('permissions', {}),
                'addedAt': data.get('addedAt', ''),
                'isMain': data.get('isMain', False)
            })
            
        return jsonify({'success': True, 'moderators': mods_list}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# 2. إضافة مشرف جديد
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

        # حفظ المشرف في Firebase
        mod_ref = db.reference(f'moderators/{mod_id}')
        mod_data = {
            'name': mod_name,
            'permissions': permissions,
            'addedAt': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'isMain': False
        }
        mod_ref.set(mod_data)

        # تسجيل العملية في سجل النشاط (Logs)
        log_ref = db.reference('admin_logs').push()
        log_ref.set({
            'admin': admin_who_added,
            'action': f"إضافة المشرف الجديد: {mod_name} (ID: {mod_id})",
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

        return jsonify({'success': True, 'message': 'تم إضافة المشرف بنجاح'}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# 3. حذف مشرف
@app.route('/api/moderators/<mod_id>', methods=['DELETE'])
def delete_moderator(mod_id):
    try:
        admin_who_deleted = request.args.get('deletedBy', 'المدير العام')

        mod_ref = db.reference(f'moderators/{mod_id}')
        mod_data = mod_ref.get()

        if not mod_data:
            return jsonify({'success': False, 'message': 'المشرف غير موجود'}), 404

        if mod_data.get('isMain'):
            return jsonify({'success': False, 'message': 'لا يمكن حذف المدير الأساسي'}), 403

        mod_name = mod_data.get('name', mod_id)
        
        # حذف من الفايربيس
        mod_ref.delete()

        # تسجيل الحذف في السجل
        log_ref = db.reference('admin_logs').push()
        log_ref.set({
            'admin': admin_who_deleted,
            'action': f"حذف المشرف: {mod_name} (ID: {mod_id})",
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

        return jsonify({'success': True, 'message': 'تم حذف المشرف بنجاح'}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# 4. جلب سجل النشاطات (Logs)
@app.route('/api/admin-logs', methods=['GET'])
def get_admin_logs():
    try:
        ref = db.reference('admin_logs')
        # جلب أحدث 20 عملية فقط
        logs_data = ref.order_to_last(20).get() or {}
        
        logs_list = []
        for log_id, data in logs_data.items():
            logs_list.append(data)
            
        # ترتيب السجلات من الأحدث للأقدم
        logs_list.reverse()

        return jsonify({'success': True, 'logs': logs_list}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
