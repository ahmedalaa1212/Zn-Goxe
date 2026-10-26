# -*- coding: utf-8 -*-
from flask import Blueprint, request, jsonify, make_response
from urllib.parse import parse_qs, unquote
import logging
import json
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
    res.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    res.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    res.headers['Pragma'] = 'no-cache'
    res.headers['Expires'] = '0'
    return res


def _extract_user_id_from_request():
    req_json = request.get_json(silent=True) if request.is_json else {}
    if not isinstance(req_json, dict):
        req_json = {}

    candidates = [
        request.headers.get('X-Telegram-User-Id'),
        request.args.get('user_id'),
        request.args.get('tg_id'),
        request.args.get('uid'),
        req_json.get('user_id'),
        req_json.get('tg_id'),
    ]

    for c in candidates:
        if c is not None:
            s = str(c).strip()
            if s.endswith('.0'):
                s = s[:-2]
            if s and s.lower() not in ('', '0', 'null', 'undefined', 'none', 'nan'):
                return s

    init_header = (
        request.headers.get('X-Telegram-Init-Data')
        or request.headers.get('X-Init-Data')
        or request.headers.get('Authorization', '')
        or request.args.get('init_data', '')
    )
    if init_header:
        try:
            raw_init = str(init_header).replace('Bearer ', '').strip()
            parsed = parse_qs(raw_init)
            user_str = parsed.get('user', [None])[0]
            if user_str:
                user_obj = json.loads(unquote(user_str))
                uid = user_obj.get('id')
                if uid:
                    return str(uid).strip()
        except Exception:
            pass

    return None


@history_bp.route('/', methods=['GET', 'POST', 'OPTIONS'])
@history_bp.route('/transactions', methods=['GET', 'POST', 'OPTIONS'])
def get_history_transactions():
    """
    جلب كافة سجلات الإيداع والسحب الخاصة بالمستخدم من Supabase بسرعة ودون كاش متصفح معلق
    """
    if request.method == 'OPTIONS':
        return _build_json_response({'status': 'ok'}, 200)

    try:
        user_id = _extract_user_id_from_request()

        if not user_id:
            return _build_json_response({
                'success': False,
                'message': 'معرّف المستخدم غير موجود (User ID missing)',
                'transactions': []
            }, 400)

        force_refresh = str(request.args.get('force', '1')) == '1'

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
