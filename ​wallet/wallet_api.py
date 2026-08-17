from flask import Blueprint, jsonify, request
from .wallet_db import get_user_wallet_balances

# استيراد الـ API الخاصة بالمجلدات الفرعية
from .deposit.deposit_api import deposit_bp
from .history.history_api import history_bp
from .withdraw.withdraw_api import withdraw_bp

wallet_bp = Blueprint('wallet', __name__, url_prefix='/api/wallet')

# تسجيل Blueprints الفرعية (الإيداع - السجلات - السحب)
wallet_bp.register_blueprint(deposit_bp, url_prefix='/deposit')
wallet_bp.register_blueprint(history_bp, url_prefix='/history')
wallet_bp.register_blueprint(withdraw_bp, url_prefix='/withdraw')

@wallet_bp.route('/data', methods=['GET'])
def get_wallet_data():
    """جلب أرصدة ZN و USDT الخاصة بالعميل"""
    user_id = request.args.get('user_id', type=int)
    
    if not user_id:
        return jsonify({'success': False, 'error': 'معرف المستخدم غير متاح'}), 400
        
    balances = get_user_wallet_balances(user_id)
    return jsonify({
        'success': True,
        'zn_balance': balances.get('zn_balance', 0.0),
        'usdt_balance': balances.get('usdt_balance', 0.0)
    })
