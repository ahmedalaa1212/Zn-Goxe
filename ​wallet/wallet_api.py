from flask import Blueprint, request, jsonify
from wallet.wallet_db import save_user_wallet_address, process_withdrawal_request, get_user_transaction_history

wallet_bp = Blueprint('wallet', __name__)

@wallet_bp.route('/api/wallet/save_address', methods=['POST'])
def save_address():
    try:
        user_id = request.headers.get('X-Telegram-User-Id') or request.json.get('user_id')
        wallet_address = request.json.get('wallet_address')

        if not user_id or not wallet_address:
            return jsonify({"success": False, "error": "بيانات غير مكتملة"}), 400

        res = save_user_wallet_address(user_id, wallet_address)
        return jsonify({"success": True, "message": "تم حفظ المحفظة"}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@wallet_bp.route('/api/wallet/withdraw', methods=['POST'])
def withdraw():
    try:
        user_id = request.headers.get('X-Telegram-User-Id') or request.json.get('user_id')
        data = request.get_json() or {}
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
        user_id = request.headers.get('X-Telegram-User-Id') or request.args.get('user_id')
        history_data = get_user_transaction_history(user_id)
        return jsonify({"success": True, "history": history_data}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
