# settings/settings_api.py
import traceback
from flask import Blueprint, jsonify, request
from core.security import get_authenticated_user
from settings.settings_db import get_user_settings_stats, get_top_mining_leaderboard

settings_bp = Blueprint('settings', __name__)

@settings_bp.route('/stats', methods=['GET', 'POST'])
def get_settings_stats():
    try:
        is_post = (request.method == 'POST')
        success, uid, user_info, error_res = get_authenticated_user(request, is_post=is_post)
        if not success:
            return error_res

        # جلب البيانات باستخدام الدالة من settings_db.py
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


@settings_bp.route('/leaderboard', methods=['GET', 'POST'])
def get_mining_leaderboard():
    """مسار جلب قائمة أفضل 10 متصدرين في التعدين"""
    try:
        is_post = (request.method == 'POST')
        success, uid, user_info, error_res = get_authenticated_user(request, is_post=is_post)
        if not success:
            return error_res

        leaderboard = get_top_mining_leaderboard(limit=10)

        return jsonify({
            "success": True,
            "leaderboard": leaderboard
        }), 200

    except Exception as e:
        print(f"Error in get_mining_leaderboard: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "Internal server error"}), 500
