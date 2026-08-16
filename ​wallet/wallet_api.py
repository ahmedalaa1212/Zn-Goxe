from flask import Blueprint, jsonify, request
from core.security import get_authenticated_user
import wallet.wallet_db as wallet_db

wallet_bp = Blueprint('wallet', __name__)

@wallet_bp.route('/info', methods=['GET', 'POST'])
def wallet_info():
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    
    if not success:
        req_json = request.get_json(silent=True) if request.is_json else {}
        telegram_id = request.args.get('tg_id') or req_json.get('tg_id')
        if not telegram_id:
            return error_res

    info = wallet_db.get_wallet_info(str(telegram_id))
    return jsonify({
        "success": True,
        "wallet_address": info.get('wallet_address'),
        "balance": info.get('balance', 0.0),
        "usd_balance": info.get('usd_balance', 0.0)
    }), 200

@wallet_bp.route('/save_address', methods=['POST'])
def save_address():
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    data = request.get_json(silent=True) or {}
    
    if not success:
        telegram_id = data.get('tg_id')
        if not telegram_id:
            return error_res

    wallet_address = data.get('wallet_address')
    if not wallet_address:
        return jsonify({"success": False, "error": "عنوان المحفظة مطلوب"}), 400

    wallet_db.save_wallet_address(str(telegram_id), wallet_address)
    return jsonify({"success": True, "message": "تم حفظ المحفظة بنجاح"}), 200
