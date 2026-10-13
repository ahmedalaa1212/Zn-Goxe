from flask import Blueprint, jsonify, request, make_response
from .wallet_db import get_user_wallet_balances

# ربط واجهات برمجة التطبيقات (APIs) للقوائم الفرعية الثلاث
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

# تسجيل الـ Blueprints للأقسام
wallet_bp.register_blueprint(deposit_bp, url_prefix='/deposit')
wallet_bp.register_blueprint(history_bp, url_prefix='/history')
wallet_bp.register_blueprint(withdraw_bp, url_prefix='/withdraw')

@wallet_bp.route('/data', methods=['GET'])
def get_wallet_data():
    """جلب أرصدة ZN و USDT و ZNX مع التحقق الأمني وتحديث لحظي بدون كاش من Supabase"""
    user_id = request.args.get('user_id', type=int)
    header_user_id = request.headers.get('X-Telegram-User-Id')
    
    if header_user_id and str(header_user_id).isdigit():
        user_id = int(header_user_id)
        
    if not user_id:
        return jsonify({'success': False, 'error': 'معرف المستخدم غير متاح'}), 400
        
    # جلب الأرصدة من قاعدة بيانات PostgreSQL مباشرة
    balances = get_user_wallet_balances(user_id)
    
    response = make_response(jsonify({
        'success': True,
        'zn_balance': balances.get('zn_balance', 0.0),
        'usdt_balance': balances.get('usdt_balance', 0.0),
        'znx_balance': balances.get('znx_balance', 0.0)
    }))
    
    # منع التخزين المؤقت (Cache) نهائياً لضمان قراءة الأرقام اللحظية
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response
