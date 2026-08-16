# wallet/wallet_api.py
from flask import Blueprint, jsonify
from wallet.deposit.deposit_api import deposit_bp
from wallet.withdraw.withdraw_api import withdraw_bp
from wallet.history.history_api import history_bp

wallet_bp = Blueprint('wallet', __name__)

# تسجيل المسارات الفرعية تلقائياً لتوافق الـ API Routes
wallet_bp.register_blueprint(deposit_bp, url_prefix='/deposit')
wallet_bp.register_blueprint(withdraw_bp, url_prefix='/withdraw')
wallet_bp.register_blueprint(history_bp, url_prefix='/history')

@wallet_bp.route('/', methods=['GET', 'POST'])
def wallet_index():
    return jsonify({"success": True, "message": "Wallet Main API Hub is Active!"}), 200

