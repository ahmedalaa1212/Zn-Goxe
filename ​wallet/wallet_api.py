from flask import Blueprint, jsonify, request
import database
from core.security import get_authenticated_user

wallet_bp = Blueprint('wallet_bp', __name__)

@wallet_bp.route('/info', methods=['GET', 'POST'])
def get_wallet_info():
    """جلب معلومات المحفظة الإجمالية للمستخدم"""
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    
    if not success:
        return error_res

    try:
        user_data = database.get_user(telegram_id) or {}
        return jsonify({
            "success": True,
            "balance": float(user_data.get('balance', 0.0)),
            "usd_balance": float(user_data.get('usd_balance', 0.0)),
            "ad_balance": float(user_data.get('ad_balance', 0.0)),
            "wallet_address": user_data.get('wallet_address', None)
        }), 200
    except Exception as e:
        print(f"❌ Error in wallet_info: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء جلب بيانات المحفظة"}), 500
