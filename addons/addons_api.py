from flask import Blueprint, request, jsonify
from addons.addons_db import (
    create_promo_code,
    redeem_promo_code,
    get_all_promo_codes,
    delete_promo_code,
    toggle_promo_code_status
)

addons_bp = Blueprint('addons_bp', __name__)

@addons_bp.route('/api/admin/promo/create', methods=['POST'])
def api_create_promo():
    data = request.json or {}
    code = data.get('code')
    coins = data.get('coins', 0)
    duration_val = data.get('duration_val', 1)
    duration_type = data.get('duration_type', 'hours')
    max_uses = data.get('max_uses', 0)
    
    success, msg = create_promo_code(code, coins, duration_val, duration_type, max_uses)
    return jsonify({'success': success, 'message': msg})

@addons_bp.route('/api/admin/promo/list', methods=['GET'])
def api_list_promo():
    codes = get_all_promo_codes()
    return jsonify({'success': True, 'codes': codes})

@addons_bp.route('/api/admin/promo/delete', methods=['POST'])
def api_delete_promo():
    data = request.json or {}
    code = data.get('code')
    success, msg = delete_promo_code(code)
    return jsonify({'success': success, 'message': msg})

@addons_bp.route('/api/admin/promo/toggle', methods=['POST'])
def api_toggle_promo():
    data = request.json or {}
    code = data.get('code')
    is_active = data.get('is_active', True)
    success, msg = toggle_promo_code_status(code, is_active)
    return jsonify({'success': success, 'message': msg})

@addons_bp.route('/api/user/promo/redeem', methods=['POST'])
def api_redeem_promo():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    code = data.get('code')
    success, msg, reward = redeem_promo_code(telegram_id, code)
    return jsonify({'success': success, 'message': msg, 'reward': reward})
