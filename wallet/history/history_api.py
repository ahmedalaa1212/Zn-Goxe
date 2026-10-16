# -*- coding: utf-8 -*-
from flask import Blueprint, request, jsonify, make_response
import logging
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

try:
    from .history_db import get_user_transaction_history
except ImportError:
    from history_db import get_user_transaction_history

history_bp = Blueprint('history_api', __name__)
logger = logging.getLogger('history_api')


def _build_json_response(payload: dict, status_code: int = 200):
    res = make_response(jsonify(payload), status_code)
    res.headers['Access-Control-Allow-Origin'] = '*'
    res.headers['Access-Control-Allow-Headers'] = '*'
    res.headers['Access-Control-Allow-Methods'] = '*'
    res.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    res.headers['Pragma'] = 'no-cache'
    res.headers['Expires'] = '0'
    return res


@history_bp.route('/transactions', methods=['GET', 'POST', 'OPTIONS'])
def get_history_transactions():
    """
    جلب كافة سجلات الإيداع والسحب الخاصة بالمستخدم من Supabase بسرعة ودون كاش متصفح معلق
    """
    if request.method == 'OPTIONS':
        return _build_json_response({'status': 'ok'}, 200)

    try:
        req_json = request.get_json(silent=True) if request.is_json else {}
        if not isinstance(req_json, dict):
            req_json = {}

        user_id_raw = (
            request.headers.get('X-Telegram-User-Id') or
            request.args.get('user_id') or
            request.args.get('tg_id') or
            request.args.get('uid') or
            req_json.get('user_id') or
            req_json.get('tg_id')
        )

        if not user_id_raw or str(user_id_raw).strip() in ['', '0', 'null', 'undefined']:
            return _build_json_response({
                'success': False,
                'message': 'معرّف المستخدم غير موجود (User ID missing)',
                'transactions': []
            }, 400)

        user_id = str(user_id_raw).strip()
        force_refresh = str(request.args.get('force', '0')) == '1'

        transactions = get_user_transaction_history(user_id, force_refresh=force_refresh)

        deposit_count = sum(1 for t in transactions if t.get('type') == 'deposit')
        withdraw_count = sum(1 for t in transactions if t.get('type') == 'withdraw')

        return _build_json_response({
            'success': True,
            'count': len(transactions),
            'deposit_count': deposit_count,
            'withdraw_count': withdraw_count,
            'transactions': transactions
        }, 200)

    except Exception as e:
        logger.error(f"❌ [history_api] Error fetching transactions: {e}")
        return _build_json_response({
            'success': False,
            'message': 'حدث خطأ داخلي أثناء استرجاع السجلات من قاعدة البيانات',
            'error': str(e),
            'transactions': []
        }, 500)
