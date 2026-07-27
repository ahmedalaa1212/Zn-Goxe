from flask import Blueprint, jsonify, request
import traceback # أضفنا هذه المكتبة لطباعة الأخطاء بوضوح في سجلات Railway
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
    
    # التأكد من أن auth_result ليس False وأنه يحتوي على id
    if not auth_result or not isinstance(auth_result, dict) or 'id' not in auth_result:
        return jsonify({"success": False, "message": "Unauthorized request, invalid initData"}), 403

    user_id = str(auth_result['id'])

    try:
        # 3. جلب بيانات اللاعب من الفايربيس
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if user_doc.exists:
            # نجلب البيانات، وفي حال كانت فارغة نضع قاموساً فارغاً لتفادي الأخطاء
            user_data = user_doc.to_dict() or {}
            
            # 4. حساب إجمالي مستويات المزرعة بشكل آمن (Safe Casting)
            farm_levels_count = 0
            for i in range(1, 11):
                # نستخدم .get لجلب القيمة. إذا كانت غير موجودة سترجع None
                lvl_val = user_data.get(f'lvl{i}_count')
                if lvl_val is not None:
                    try:
                        farm_levels_count += int(lvl_val)
                    except (ValueError, TypeError):
                        # إذا كان الحقل يحتوي على نص غير مفهوم أو معطوب، يتجاهله ولا ينهار السيرفر
                        pass
                
            # 5. جلب مستوى المخزن بشكل آمن
            storage_levels_count = 0
            storage_val = user_data.get('storage_level')
            if storage_val is not None:
                try:
                    storage_levels_count = int(storage_val)
                except (ValueError, TypeError):
                    pass

            return jsonify({
                "success": True,
                "farm_levels_count": farm_levels_count,
                "storage_levels_count": storage_levels_count
            }), 200
            
        else:
            # المستخدم ليس له وثيقة في قاعدة البيانات بعد
            return jsonify({
                "success": True, 
                "farm_levels_count": 0, 
                "storage_levels_count": 0
            }), 200

    except Exception as e:
        # طباعة الخطأ بالكامل في الكونسول لمعرفة سببه بدقة في Railway
        print(f"Settings API Error for user {user_id}: {str(e)}")
        traceback.print_exc() 
        return jsonify({"success": False, "message": "Internal server error"}), 500
