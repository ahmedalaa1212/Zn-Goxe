# -*- coding: utf-8 -*-
# settings/settings_api.py
import time
import traceback
from flask import Blueprint, jsonify, request
from core.security import get_authenticated_user
from settings.settings_db import (
    get_user_settings_stats,
    get_top_mining_leaderboard,
    redeem_promo_code
)

settings_bp = Blueprint('settings', __name__)

# حماية ضد التخمين والسبام (Cooldown لكل مستخدم)
_redeem_cooldowns = {}
REDEEM_COOLDOWN_SECONDS = 2.0


@settings_bp.route('/stats', methods=['GET', 'POST'])
def get_settings_stats():
    """جلب إحصائيات اللاعب ومستويات المزرعة والمخزن والرصيد لحظياً من Supabase"""
    try:
        is_post = (request.method == 'POST')
        success, uid, user_info, error_res = get_authenticated_user(request, is_post=is_post)
        if not success:
            return error_res

        stats = get_user_settings_stats(str(uid))

        return jsonify({
            "success": True,
            "farm_levels_count": stats.get("farm_levels_count", 0),
            "storage_levels_count": stats.get("storage_levels_count", 0),
            "balance": stats.get("balance", 0),
            "usd_balance": stats.get("usd_balance", 0),
            "znx_balance": stats.get("znx_balance", 0),
            "mined_points": stats.get("mined_points", 0),
            "upgrades": stats.get("upgrades", {})
        }), 200

    except Exception as e:
        print(f"Error in get_settings_stats: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "Internal server error"}), 500


@settings_bp.route('/leaderboard', methods=['GET', 'POST'])
def get_mining_leaderboard():
    """مسار جلب قائمة أفضل 10 متصدرين في التعدين من Supabase"""
    try:
        is_post = (request.method == 'POST')
        try:
            get_authenticated_user(request, is_post=is_post)
        except Exception:
            pass

        leaderboard = get_top_mining_leaderboard(limit=10)

        return jsonify({
            "success": True,
            "leaderboard": leaderboard
        }), 200

    except Exception as e:
        print(f"Error in get_mining_leaderboard: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "Internal server error"}), 500


@settings_bp.route('/redeem-code', methods=['POST'])
@settings_bp.route('/redeem_code', methods=['POST'])
def handle_redeem_code():
    """مسار تفعيل أكواد الهدايا والمكافآت وتحديث الرصيد والإحصائيات لحظياً"""
    try:
        success, uid, user_info, error_res = get_authenticated_user(request, is_post=True)
        if not success:
            return error_res

        uid_str = str(uid).strip()
        now = time.time()
        last_attempt = _redeem_cooldowns.get(uid_str, 0)
        if now - last_attempt < REDEEM_COOLDOWN_SECONDS:
            return jsonify({
                "success": False,
                "message": "⏳ يرجى الانتظار ثانية قبل المحاولة مرة أخرى."
            }), 429
        _redeem_cooldowns[uid_str] = now

        # تنظيف الذاكرة إذا كبرت القائمة
        if len(_redeem_cooldowns) > 5000:
            _redeem_cooldowns.clear()

        data = request.get_json(silent=True) or {}
        code = str(data.get('code', '')).strip()

        if not code:
            return jsonify({"success": False, "message": "يرجى كتابة الكود أولاً."}), 200

        result = redeem_promo_code(uid_str, code)

        # إذا نجح التفعيل، نرسل أيضاً أحدث إحصائيات للمستخدم ليتحدث الفرونت إند فوراً
        if result.get("success"):
            stats = get_user_settings_stats(uid_str)
            result["stats"] = stats

        return jsonify(result), 200

    except Exception as e:
        print(f"Error in handle_redeem_code: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "Internal server error"}), 500
