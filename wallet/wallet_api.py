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

@wallet_bp.route('/data', methods=['GET'])
def get_wallet_data():
    user_id = request.args.get('user_id')
    
    if not user_id or user_id in ['undefined', 'None', '']:
        user_id = request.headers.get('X-Telegram-User-Id')
        
    if not user_id or user_id in ['undefined', 'None', '']:
        return jsonify({'success': False, 'error': 'Missing User ID'}), 400
        
    balances = get_user_wallet_balances(user_id)
    
    # تنسيق الأرقام هنا كسلاسل نصية بـ 4 أصفار عشرية لضمان عدم حدوث خطأ في الجافاسكريبت
    response = make_response(jsonify({
        'success': True,
        'zn_balance': f"{balances.get('zn_balance', 0.0):.4f}",
        'usdt_balance': f"{balances.get('usdt_balance', 0.0):.4f}",
        'znx_balance': f"{balances.get('znx_balance', 0.0):.4f}"
    }))
    
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response
