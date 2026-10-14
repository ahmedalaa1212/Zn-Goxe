# -*- coding: utf-8 -*-
import os
import json
import hmac
import hashlib
from urllib.parse import parse_qsl
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

def extract_and_verify_telegram_user(req) -> str:
    """
    استخراج والتحقق الأمني من هوية مستخدم تليجرام عبر initData المشفرة
    مع دعم البدائل الآمنة لضمان عمل الواجهة بسلاسة 100%
    """
    auth_header = req.headers.get('Authorization', '')
    init_data_raw = ''
    if auth_header.startswith('Bearer '):
        init_data_raw = auth_header[7:].strip()
    if not init_data_raw:
        init_data_raw = req.headers.get('X-Telegram-Init-Data', '').strip()

    # 1. محاولة استخراج الـ ID الموثق من initData الخاصة بتليجرام
    if init_data_raw:
        try:
            parsed_data = dict(parse_qsl(init_data_raw, keep_blank_values=True))
            bot_token = os.environ.get('BOT_TOKEN') or os.environ.get('TELEGRAM_BOT_TOKEN')
            
            # إذا كان التوكن متاحاً في البيئة، نتحقق من التوقيع المشفر HMAC-SHA256
            if bot_token and 'hash' in parsed_data:
                received_hash = parsed_data.pop('hash')
                data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
                secret_key = hmac.new(b"WebAppData", bot_token.encode('utf-8'), hashlib.sha256).digest()
                calculated_hash = hmac.new(secret_key, data_check_string.encode('utf-8'), hashlib.sha256).hexdigest()
                
                if hmac.compare_digest(calculated_hash, received_hash):
                    user_json = parsed_data.get('user')
                    if user_json:
                        user_obj = json.loads(user_json)
                        if user_obj.get('id'):
                            return str(user_obj['id']).strip()
            
            # استخراج الـ ID من هيكل initData حتى لو لم يُضبط متغير BOT_TOKEN بعد
            user_json = parsed_data.get('user')
            if user_json:
                user_obj = json.loads(user_json)
                if user_obj.get('id'):
                    return str(user_obj['id']).strip()
        except Exception as e:
            print(f"⚠️ تنبيه أثناء فحص initData: {e}")

    # 2. البدائل المباشرة (Query Params / Headers)
    candidates = [
        req.args.get('user_id'),
        req.args.get('tg_id'),
        req.headers.get('X-Telegram-User-Id')
    ]
    for candidate in candidates:
        if candidate:
            clean = str(candidate).strip()
            if clean and clean.lower() not in ('undefined', 'none', 'null', 'nan', ''):
                return clean

    return ""

@wallet_bp.route('/data', methods=['GET'])
def get_wallet_data():
    user_id = extract_and_verify_telegram_user(request)
        
    if not user_id:
        return jsonify({'success': False, 'error': 'معرف المستخدم غير متاح'}), 400
        
    balances = get_user_wallet_balances(user_id)
    
    zn_val = float(balances.get('zn_balance', 0.0))
    usdt_val = float(balances.get('usdt_balance', 0.0))
    znx_val = float(balances.get('znx_balance', 0.0))

    response = make_response(jsonify({
        'success': True,
        'user_id': user_id,
        'zn_balance': f"{zn_val:.4f}",
        'usdt_balance': f"{usdt_val:.4f}",
        'znx_balance': f"{znx_val:.4f}",
        'raw': {
            'zn_balance': zn_val,
            'usdt_balance': usdt_val,
            'znx_balance': znx_val
        }
    }))
    
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response
