# wallet/deposit/deposit_api.py
import hashlib
from flask import Blueprint, jsonify, request
from database import is_user_banned
from core.security import get_authenticated_user
from wallet.deposit.deposit_db import record_user_deposit

deposit_bp = Blueprint('deposit', __name__)

DEPOSIT_FEE_PERCENT = 0.03
MIN_DEPOSIT_USD = 1.00

@deposit_bp.route('/report', methods=['POST'])
def wallet_deposit_report():
    success, user_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success: 
        return error_res

    if is_user_banned(user_id):
        return jsonify({"success": False, "error": "حسابك محظور من الاستخدام."}), 200
    
    req = request.get_json(silent=True) or {}
    try:
        gross_usd = round(float(req.get('usdAmount', 0)), 2)
        ton_amount = float(req.get('tonAmount', 0))
        
        if gross_usd < MIN_DEPOSIT_USD:
            return jsonify({
                "success": False, 
                "error": f"الحد الأدنى للإيداع هو ${MIN_DEPOSIT_USD:.2f}"
            }), 200
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "مبلغ إيداع غير صالح"}), 200
        
    boc = req.get('boc')
    if not boc:
        return jsonify({"success": False, "error": "رمز إثبات المعاملة (BOC) مفقود"}), 200

    fee_usd = round(gross_usd * DEPOSIT_FEE_PERCENT, 2)
    net_usd = round(gross_usd - fee_usd, 2)
    tx_hash = hashlib.sha256(str(boc).encode('utf-8')).hexdigest()

    ok, msg_or_bal = record_user_deposit(str(user_id).strip(), gross_usd, net_usd, fee_usd, ton_amount, tx_hash)
    if not ok:
        return jsonify({"success": False, "error": msg_or_bal}), 200

    return jsonify({
        "success": True, 
        "new_usd_balance": msg_or_bal,
        "net_usd_credited": net_usd,
        "message": "تم الإيداع وتسجيل الرصيد بنجاح!"
    }), 200

