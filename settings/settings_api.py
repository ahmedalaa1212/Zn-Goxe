from flask import Blueprint, jsonify, request
import traceback
# استدعاء دالة الحماية الخاصة بك
from core.security import validate_telegram_data
from database import db

# تعريف الـ Blueprint
settings_bp = Blueprint('settings', __name__)

@settings_bp.route('/api/settings/stats', methods=['GET'])
def get_settings_stats():
    # 1. جلب التوقيع من الهيدر
    init_data = request.headers.get('X-Telegram-Init-Data')
    
    if not init_data:
        return jsonify({"success": False, "message": "Missing authentication data"}), 401

    # 2. التحقق من صحة التوقيع عبر ملف security.py
    auth_result = validate_telegram_data(init_data)
    
    if not auth_result or not isinstance(auth_result, dict) or 'id' not in auth_result:
        return jsonify({"success": False, "message": "Unauthorized request, invalid initData"}), 403

    user_id = str(auth_result['id'])

    try:
        # 3. جلب بيانات اللاعب من الفايربيس
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if user_doc.exists:
            user_data = user_doc.to_dict() or {}
            
            # ==========================================
            # 🟢 التعديل الجذري هنا بناءً على صورة قاعدة البيانات
            # ==========================================
            
            farm_levels_count = 0
            # نجلب الـ Map المسمى 'upgrades' من الفايربيس
            upgrades_map = user_data.get('upgrades', {}) 
            
            # نتأكد أنه Map (قاموس) لتفادي الأخطاء
            if isinstance(upgrades_map, dict):
                # نجمع المستويات من lvl1 إلى lvl10 (حسب أسماء الحقول في صورتك)
                for i in range(1, 11):
                    lvl_val = upgrades_map.get(f'lvl{i}')
                    if lvl_val is not None:
                        try:
                            farm_levels_count += int(lvl_val)
                        except (ValueError, TypeError):
                            pass
                
            # جلب مستوى المخزن (موجود في الجذر الرئيسي باسم storage_level كما في صورتك)
            storage_levels_count = 0
            storage_val = user_data.get('storage_level')
            if storage_val is not None:
                try:
                    storage_levels_count = int(storage_val)
                except (ValueError, TypeError):
                    pass

            # إرسال البيانات للفرونت إند
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
        print(f"Settings API Error for user {user_id}: {str(e)}")
        traceback.print_exc() 
        return jsonify({"success": False, "message": "Internal server error"}), 500

