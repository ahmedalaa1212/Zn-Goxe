# wallet/withdraw/withdraw_api.py
from flask import Blueprint, jsonify, request
from database import is_user_banned
from core.security import get_authenticated_user
from wallet.withdraw.withdraw_db import convert_zn_to_usd, request_withdrawal

withdraw_bp = Blueprint('withdraw', __name__)

MIN_CONVERT_ZN = 1000000

@withdraw_bp.route('/convert', methods=['POST'])
def wallet_convert():
    success, user_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res

    if is_user_banned(user_id):
        return jsonify({"success": False, "error": "حسابك محظور من الاستخدام."}), 200
    
    req = request.get_json(silent=True) or {}
    try:
        amount = float(req.get('amount', 0))
        if amount < MIN_CONVERT_ZN or amount <= 0 or not float(amount).is_integer():
            return jsonify({
                "success": False, 
                "error": f"الحد الأدنى لتحويل ZN هو {MIN_CONVERT_ZN:,} نقطة أعداد صحيحة."
            }), 200
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "كمية نقاط غير صالحة"}), 200

    ok, res1, res2, res3 = convert_zn_to_usd(str(user_id).strip(), amount)
    if not ok:
        return jsonify({"success": False, "error": res1}), 200

    return jsonify({
        "success": True, 
        "usd_gained": res1, 
        "new_usd_balance": res2,
        "new_balance": res3,
        "message": "تم تحويل النقاط بنجاح!"
    }), 200


@withdraw_bp.route('/request', methods=['POST'])
def wallet_withdraw():
    success, user_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res

    if is_user_banned(user_id):
        return jsonify({"success": False, "error": "حسابك محظور من الاستخدام."}), 200
    
    req = request.get_json(silent=True) or {}
    try:
        amount = round(float(req.get('amount', 0)), 2)
        if amount <= 0:
            return jsonify({"success": False, "error": "مبلغ سحب غير صالح"}), 200
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "مبلغ سحب غير صالح"}), 200
        
    wallet_address = str(req.get('walletAddress', '')).strip()
    if not wallet_address or len(wallet_address) < 20:
        return jsonify({"success": False, "error": "عنوان المحفظة مفقود أو غير صحيح"}), 200

    ok, new_usd_or_err = request_withdrawal(str(user_id).strip(), amount, wallet_address)
    if not ok:
        return jsonify({"success": False, "error": new_usd_or_err}), 200

    return jsonify({
        "success": True, 
        "new_usd_balance": new_usd_or_err,
        "message": "تم إرسال طلب السحب بنجاح!"
    }), 200

