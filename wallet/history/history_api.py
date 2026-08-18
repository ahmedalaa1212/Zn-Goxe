from flask import Blueprint, request, jsonify
import logging
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from history_db import get_user_transaction_history

history_bp = Blueprint('history_api', __name__)
logger = logging.getLogger('history_api')

@history_bp.route('/transactions', methods=['GET', 'POST', 'OPTIONS'])
def get_history_transactions():
    """
    جلب كافة سجلات الإيداع والسحب الخاصة بالمستخدم الحالي
    """
    if request.method == 'OPTIONS':
        res = jsonify({'status': 'ok'})
        res.headers['Access-Control-Allow-Origin'] = '*'
        res.headers['Access-Control-Allow-Headers'] = '*'
        res.headers['Access-Control-Allow-Methods'] = '*'
        return res, 200

    try:
        req_json = request.get_json(silent=True) if request.is_json else {}
        user_id_raw = (
            request.headers.get('X-Telegram-User-Id') or 
            request.args.get('user_id') or 
            request.args.get('tg_id') or
            (req_json.get('user_id') if isinstance(req_json, dict) else None) or
            (req_json.get('tg_id') if isinstance(req_json, dict) else None)
        )

        if not user_id_raw:
            response = jsonify({
                'success': False,
                'message': 'معرّف المستخدم غير موجود (User ID missing)',
                'transactions': []
            })
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response, 400

        user_id = str(user_id_raw).strip()
        transactions = get_user_transaction_history(user_id)

        response = jsonify({
            'success': True,
            'count': len(transactions),
            'transactions': transactions
        })
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response, 200

    except Exception as e:
        logger.error(f"❌ [history_api] Error fetching transactions: {e}")
        response = jsonify({
            'success': False,
            'message': 'حدث خطأ داخلي أثناء استرجاع السجلات',
            'error': str(e),
            'transactions': []
        })
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response, 500
