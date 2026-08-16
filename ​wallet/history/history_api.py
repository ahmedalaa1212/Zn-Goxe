# wallet/history/history_api.py
from flask import Blueprint, jsonify, request
from database import is_user_banned
from core.security import get_authenticated_user
from wallet.history.history_db import fetch_user_history

history_bp = Blueprint('history', __name__)

@history_bp.route('/get', methods=['GET', 'POST'])
def get_history():
    is_post = (request.method == 'POST')
    success, user_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success: 
        return error_res

    if is_user_banned(user_id):
        return jsonify({"success": False, "error": "حسابك محظور من الاستخدام."}), 200
    
    ok, clean_history = fetch_user_history(user_id)
    if not ok:
        return jsonify({"success": False, "error": "حدث خطأ أثناء جلب سجل المعاملات"}), 200

    return jsonify({"success": True, "history": clean_history}), 200

