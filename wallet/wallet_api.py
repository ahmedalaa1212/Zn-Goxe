# wallet/wallet_api.py
from flask import Blueprint, jsonify, request

wallet_bp = Blueprint('wallet', __name__)

@wallet_bp.route('/', methods=['GET', 'POST'])
def wallet_index():
    return jsonify({
        "success": True,
        "message": "Wallet API is working!"
    }), 200
