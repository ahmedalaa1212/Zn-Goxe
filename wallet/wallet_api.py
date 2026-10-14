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
    # 🎯 ترتيب منطقي لجلب user_id
    user_id = request.args.get('user_id')
    
    if not user_id or user_id in ['undefined', 'None', '', 'null']:
        user_id = request.headers.get('X-Telegram-User-Id')
        
    print(f"🔍 [Wallet API] استلام طلب جلب أرصدة للمستخدم: '{user_id}'")

    if not user_id or user_id in ['undefined', 'None', '', 'null']:
        print("❌ [Wallet API] لم يتم العثور على user_id صالح في الطلب.")
        return jsonify({'success': False, 'error': 'معرف المستخدم غير متاح'}), 400
        
    balances = get_user_wallet_balances(user_id)
    
    print(f"📊 [Wallet API] الأرصدة المسترجعة للمستخدم {user_id}: {balances}")

    response = make_response(jsonify({
        'success': True,
        'zn_balance': str(balances.get('zn_balance', 0.0)),
        'usdt_balance': str(balances.get('usdt_balance', 0.0)),
        'znx_balance': str(balances.get('znx_balance', 0.0))
    }))
    
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response
