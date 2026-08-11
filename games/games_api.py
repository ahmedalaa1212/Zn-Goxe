
from flask import Blueprint, request, jsonify
from games.games_db import (
    get_game_profit_stats,
    get_grid_36_config,
    get_big_arena_config,
    clear_user_pending_refund
)
from games.grid_36 import grid_36_manager
from games.arena import big_arena_manager

games_bp = Blueprint('games_api', __name__, url_prefix='/api/games')

# ==========================================
# ⚙️ 1. إعدادات وإحصائيات الألعاب
# ==========================================

@games_bp.route('/stats', methods=['GET'])
def game_stats_endpoint():
    """جلب إحصائيات الأرباح والمخاطرة"""
    stats = get_game_profit_stats()
    return jsonify({"success": True, "stats": stats})

@games_bp.route('/configs', methods=['GET'])
def game_configs_endpoint():
    """جلب إعدادات الألعاب كاملة"""
    return jsonify({
        "success": True,
        "grid_36": get_grid_36_config(),
        "big_arena": get_big_arena_config()
    })

# ==========================================
# 🎮 2. مسارات لعبة ZN Go (الـ 36 صندوق)
# ==========================================

@games_bp.route('/grid36/start', methods=['POST'])
def start_grid36():
    data = request.json or {}
    uid = data.get('uid')
    bet_amount = float(data.get('bet_amount', 0.0))

    if not uid:
        return jsonify({"success": False, "message": "المستخدم غير محدد"}), 400

    success, message, result = grid_36_manager.start_new_game(uid, bet_amount)
    return jsonify({"success": success, "message": message, "data": result})

@games_bp.route('/grid36/open', methods=['POST'])
def open_grid36_box():
    data = request.json or {}
    uid = data.get('uid')
    box_index = int(data.get('box_index', -1))

    if not uid or box_index < 0:
        return jsonify({"success": False, "message": "بيانات الطلب غير مكتملة"}), 400

    success, message, result = grid_36_manager.open_box(uid, box_index)
    return jsonify({"success": success, "message": message, "data": result})

@games_bp.route('/grid36/cashout', methods=['POST'])
def cashout_grid36():
    data = request.json or {}
    uid = data.get('uid')

    if not uid:
        return jsonify({"success": False, "message": "المستخدم غير محدد"}), 400

    success, message, new_bal = grid_36_manager.cashout(uid)
    return jsonify({"success": success, "message": message, "new_balance": new_bal})

# ==========================================
# ⚔️ 3. مسارات لعبة الساحة الكبرى Arena
# ==========================================

@games_bp.route('/arena/enter', methods=['POST'])
def enter_arena_endpoint():
    data = request.json or {}
    uid = data.get('uid')

    if not uid:
        return jsonify({"success": False, "message": "المستخدم غير محدد"}), 400

    success, message, new_bal = big_arena_manager.enter_arena(uid)
    return jsonify({"success": success, "message": message, "new_balance": new_bal})

@games_bp.route('/refund/check', methods=['POST'])
def check_refund_endpoint():
    """استرداد المبالغ المعلقة إن وجدت"""
    data = request.json or {}
    uid = data.get('uid')

    if not uid:
        return jsonify({"success": False, "message": "المستخدم غير محدد"}), 400

    refunded, current_bal = clear_user_pending_refund(uid)
    return jsonify({
        "success": True,
        "refunded_amount": refunded,
        "current_balance": current_bal
    })
