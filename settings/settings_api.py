# settings/settings_api.py
import traceback
from flask import Blueprint, jsonify, request
import database
from core.security import get_authenticated_user

settings_bp = Blueprint('settings', __name__)

def get_db():
    """ضمان الحصول على كائن قاعدة البيانات Firestore"""
    if database.db is None:
        return database.initialize_firebase()
    return database.db

@settings_bp.route('/stats', methods=['GET', 'POST'])
def get_settings_stats():
    try:
        is_post = (request.method == 'POST')
        success, uid, user_info, error_res = get_authenticated_user(request, is_post=is_post)
        if not success:
            return error_res

        db_conn = get_db()
        user_ref = db_conn.collection('users').document(str(uid))
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({
                "success": True,
                "farm_levels_count": 0,
                "storage_levels_count": 0,
                "balance": 0
            }), 200

        user_data = user_doc.to_dict() or {}
        
        # حساب مستويات التعدين عبر الـ 9 مستويات
        farm_levels_count = 0
        upgrades_map = user_data.get('upgrades', {})
        if isinstance(upgrades_map, dict):
            for i in range(1, 10):
                lvl_val = upgrades_map.get(f'lvl{i}')
                if lvl_val is not None:
                    try:
                        farm_levels_count += int(lvl_val)
                    except (ValueError, TypeError):
                        pass

        # حساب مستويات التخزين
        storage_levels_count = 0
        storage_val = user_data.get('storage_level')
        if storage_val is not None:
            try:
                storage_levels_count = int(storage_val)
            except (ValueError, TypeError):
                pass

        balance = user_data.get('balance', 0)

        return jsonify({
            "success": True,
            "farm_levels_count": farm_levels_count,
            "storage_levels_count": storage_levels_count,
            "balance": balance
        }), 200

    except Exception as e:
        print(f"Error in get_settings_stats: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "Internal server error"}), 500
