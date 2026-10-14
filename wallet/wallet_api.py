# -*- coding: utf-8 -*-
import json
from urllib.parse import parse_qs, unquote
from flask import Blueprint, jsonify, request, make_response
from .wallet_db import get_user_wallet_balances

try:
    from .deposit.deposit_api import deposit_bp
except ImportError:
    deposit_bp = Blueprint('deposit_placeholder', __name__)
try:
    from .history.history_api import history_bp
except ImportError:
    history_bp = Blueprint('history_placeholder', __name__)
try:
    from .withdraw.withdraw_api import withdraw_bp
except ImportError:
    withdraw_bp = Blueprint('withdraw_placeholder', __name__)

wallet_bp = Blueprint('wallet', __name__, url_prefix='/api/wallet')

wallet_bp.register_blueprint(deposit_bp, url_prefix='/deposit')
wallet_bp.register_blueprint(history_bp, url_prefix='/history')
wallet_bp.register_blueprint(withdraw_bp, url_prefix='/withdraw')

def _extract_telegram_user_id():
    """استخراج معرف المستخدم من كافة المصادر الممكنة بما فيها Telegram initData"""
    candidates = [
        request.args.get('user_id'),
        request.args.get('tg_id'),
        request.args.get('telegram_id'),
        request.headers.get('X-Telegram-User-Id'),
    ]
    if request.is_json:
        body = request.get_json(silent=True) or {}
        candidates.extend([body.get('user_id'), body.get('tg_id'), body.get('telegram_id')])

    for cid in candidates:
        if cid is not None:
            s = str(cid).strip()
            if s.endswith('.0'):
                s = s[:-2]
            if s and s.lower() not in ('undefined', 'none', 'null', 'nan', ''):
                return s

    # محاولة الاستخراج من ترويسة Authorization (Telegram WebApp initData)
    auth_header = request.headers.get('Authorization', '') or request.headers.get('X-Telegram-Init-Data', '')
    if auth_header:
        raw_init = auth_header.replace('Bearer ', '').strip()
        try:
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

@wallet_bp.route('/data', methods=['GET', 'POST'])
@wallet_bp.route('/balances', methods=['GET', 'POST'])
def get_wallet_data():
    user_id = _extract_telegram_user_id()
        
    if not user_id:
        return jsonify({'success': False, 'error': 'معرف المستخدم غير متاح'}), 400
        
    balances = get_user_wallet_balances(user_id)
    
    # إذا حدث خطأ في الاتصال بالقاعدة، نرسل success: False حتى لا تصفر الواجهة الرصيد الحالي
    if not balances.get('db_ok', True):
        return jsonify({'success': False, 'error': 'خطأ مؤقت في الاتصال بقاعدة البيانات'}), 503

    zn_val = float(balances.get('zn_balance', 0.0))
    usdt_val = float(balances.get('usdt_balance', 0.0))
    znx_val = float(balances.get('znx_balance', 0.0))

    response = make_response(jsonify({
        'success': True,
        'user_id': user_id,
        'zn_balance': f"{zn_val:.4f}",
        'usdt_balance': f"{usdt_val:.4f}",
        'znx_balance': f"{znx_val:.4f}",
        'balance': zn_val,
        'usd_balance': usdt_val,
        'znx': znx_val
    }))
    
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response
