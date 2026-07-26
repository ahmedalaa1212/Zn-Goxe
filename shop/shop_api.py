# shop/shop_api.py
from flask import Blueprint, jsonify, request

shop_bp = Blueprint('shop', __name__)

@shop_bp.route('/', methods=['GET', 'POST'])
def shop_index():
    return jsonify({
        "success": True,
        "message": "Shop API is working!"
    }), 200
