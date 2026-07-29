# settings/settings_api.py
import traceback
from flask import Blueprint, jsonify, request
from database import db
from core.security import get_authenticated_user

settings_bp = Blueprint('settings', __name__)

@settings_bp.route('/stats', methods=['GET', 'POST'])
def get_settings_stats():
    try:
        # دعم المصادقة الموحدة الآمنة عبر Authorization Bearer
        is_post = (request.method == 'POST')
        success, uid, error_res = get_authenticated_user(request, is_post=is_post)
        if not success:
            return error_res

        # جلب بيانات اللاعب من الفايربيس
        user_ref = db.collection('users').document(uid)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({
                "success": True,
                "farm_levels_count": 0,
                "storage_levels_count": 0,
                "balance": 0
            }), 200

        user_data = user_doc.to_dict() or {}
        
        # ==========================================
        # 🟢 حساب مستويات المزرعة والمخزن والرصيد
        # ==========================================
        farm_levels_count = 0
        upgrades_map = user_data.get('upgrades', {})
        if isinstance(upgrades_map, dict):
            # مطابقة 9 مستويات (من lvl1 حتى lvl9)
            for i in range(1, 10):
                lvl_val = upgrades_map.get(f'lvl{i}')
                if lvl_val is not None:
                    try:
                        farm_levels_count += int(lvl_val)
                    except (ValueError, TypeError):
                        pass

        # جلب مستوى المخزن
        storage_levels_count = 0
        storage_val = user_data.get('storage_level')
        if storage_val is not None:
            try:
                storage_levels_count = int(storage_val)
            except (ValueError, TypeError):
                pass

        # جلب الرصيد للمزامنة الفورية
        balance = user_data.get('balance', 0)

        return jsonify({
            "success": True,
            "farm_levels_count": farm_levels_count,
            "storage_levels_count": storage_levels_count,
            "balance": balance
        }), 200

    except Exception as e:
        print(f"Error in get_settings_stats for user {uid if 'uid' in locals() else 'unknown'}: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "Internal server error"}), 500
