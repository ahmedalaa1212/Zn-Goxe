from flask import Blueprint, jsonify, request
# تم تعديل اسم الدالة ليتطابق مع ملف security.py الخاص بك
from core.security import validate_telegram_data
from database import db

# تعريف الـ Blueprint
settings_bp = Blueprint('settings', __name__)

@settings_bp.route('/api/settings/stats', methods=['GET'])
def get_settings_stats():
    # 1. جلب التوقيع من الهيدر (دستور الحماية)
    init_data = request.headers.get('X-Telegram-Init-Data')
    
    if not init_data:
        return jsonify({"success": False, "message": "Missing authentication data"}), 401

    # 2. التحقق من صحة التوقيع عبر ملف security.py
    auth_result = validate_telegram_data(init_data)
    
    if not auth_result or 'id' not in auth_result:
        return jsonify({"success": False, "message": "Unauthorized request, invalid initData"}), 403

    user_id = str(auth_result['id'])

    try:
        # 3. جلب بيانات اللاعب من الفايربيس
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if user_doc.exists:
            user_data = user_doc.to_dict()
            
            # حساب إجمالي مستويات المزرعة (يجمع مستويات الترقية من 1 لـ 10)
            farm_levels_count = 0
            for i in range(1, 11):
                farm_levels_count += int(user_data.get(f'lvl{i}_count', 0))
                
            # جلب مستوى المخزن (لو بتستخدم حقل واحد اسمه storage_level في الداتابيز)
            # ولو بتستخدم نظام مختلف للمخازن، عدل المتغير ده بناءً على الداتابيز بتاعتك
            storage_levels_count = int(user_data.get('storage_level', 0))

            return jsonify({
                "success": True,
                "farm_levels_count": farm_levels_count,
                "storage_levels_count": storage_levels_count
            }), 200
            
        else:
            return jsonify({
                "success": True, 
                "farm_levels_count": 0, 
                "storage_levels_count": 0
            }), 200

    except Exception as e:
        print(f"Settings API Error: {e}")
        return jsonify({"success": False, "message": "Internal server error"}), 500
