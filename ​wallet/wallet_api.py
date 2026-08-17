from flask import Blueprint, request, jsonify
from wallet.wallet_db import save_user_wallet_address, process_withdrawal_request, get_user_transaction_history

wallet_bp = Blueprint('wallet', __name__)

def get_user_id_from_req():
    return request.headers.get('X-Telegram-User-Id') or request.args.get('user_id') or (request.get_json(silent=True) or {}).get('user_id')

@wallet_bp.route('/api/wallet/save_address', methods=['POST'])
def save_address():
    try:
        data = request.get_json(silent=True) or {}
        user_id = get_user_id_from_req()
        wallet_address = data.get('wallet_address')

        if not user_id or not wallet_address:
            return jsonify({"success": False, "error": "بيانات غير مكتملة"}), 400

        res = save_user_wallet_address(user_id, wallet_address)
        return jsonify({"success": True, "message": "تم حفظ المحفظة"}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@wallet_bp.route('/api/wallet/withdraw', methods=['POST'])
def withdraw():
    try:
        data = request.get_json(silent=True) or {}
        user_id = get_user_id_from_req()
        amount = float(data.get('amount', 0))
        address = data.get('address')

        if amount <= 0 or not address:
            return jsonify({"success": False, "error": "المبلغ أو العنوان غير صحيح"}), 400

        result = process_withdrawal_request(user_id, amount, address)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@wallet_bp.route('/api/wallet/history', methods=['GET'])
def history():
    try:
        user_id = get_user_id_from_req()
        history_data = get_user_transaction_history(user_id) if user_id else []
        return jsonify({"success": True, "history": history_data}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
