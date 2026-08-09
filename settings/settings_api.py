# settings/settings_api.py
import traceback
from flask import Blueprint, jsonify, request
from core.security import get_authenticated_user
from settings.db import get_user_settings_stats

settings_bp = Blueprint('settings', __name__)

@settings_bp.route('/stats', methods=['GET', 'POST'])
def get_settings_stats():
    try:
        is_post = (request.method == 'POST')
        success, uid, user_info, error_res = get_authenticated_user(request, is_post=is_post)
        if not success:
            return error_res

        # استخدام دالة قاعدة البيانات السريعة
        stats = get_user_settings_stats(str(uid))

        return jsonify({
            "success": True,
            "farm_levels_count": stats.get("farm_levels_count", 0),
            "storage_levels_count": stats.get("storage_levels_count", 0),
            "balance": stats.get("balance", 0)
        }), 200

    except Exception as e:
        print(f"Error in get_settings_stats: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "Internal server error"}), 500
