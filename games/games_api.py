from flask import Blueprint, request, jsonify
from games.games_db import (
    get_game_profit_stats,
    get_grid_36_config,
    get_big_arena_config,
    clear_user_pending_refund
)
from games.grid_36 import grid_36_manager
from games.arena import big_arena_manager

games_bp = Blueprint('games_api', __name__, url_prefix='/api')

def extract_uid(req) -> str:
    data = req.json or {}
    tg_id = data.get('tg_id') or data.get('uid')
    if tg_id:
        return str(tg_id)
    return ""

# ==========================================
# 🎮 1. مسارات لعبة ZN Go الـ 36 صندوق
# ==========================================

@games_bp.route('/game/start', methods=['POST'])
@games_bp.route('/games/grid36/start', methods=['POST'])
def start_grid36():
    uid = extract_uid(request)
    data = request.json or {}
    bet_amount = float(data.get('bet_amount', 100.0))
    broken_count = int(data.get('broken_count', 3))

    if not uid:
        return jsonify({"success": False, "message": "لم يتم العثور على معرف المستخدم"}), 400

    success, message, result = grid_36_manager.start_new_game(uid, bet_amount, broken_count)
    return jsonify({
        "success": success,
        "status": "success" if success else "error",
        "message": message,
        "new_balance": result.get("new_balance"),
        "session_token": result.get("session_token"),
        "multipliers": result.get("multipliers")
    })

@games_bp.route('/game/step', methods=['POST'])
@games_bp.route('/games/grid36/open', methods=['POST'])
def open_grid36_box():
    uid = extract_uid(request)
    data = request.json or {}
    box_index = int(data.get('box_index', data.get('box_index', -1)))
    session_token = data.get('session_token')

    if not uid or box_index < 0:
        return jsonify({"success": False, "message": "بيانات غير مكتملة"}), 400

    success, message, result = grid_36_manager.open_box(uid, box_index, session_token)
    return jsonify({
        "success": success,
        "status": result.get("status", "error"),
        "message": message,
        "is_bomb": result.get("is_bomb", False),
        "layout": result.get("layout"),
        "multiplier": result.get("multiplier"),
        "current_win": result.get("current_win")
    })

@games_bp.route('/game/cashout', methods=['POST'])
@games_bp.route('/games/grid36/cashout', methods=['POST'])
def cashout_grid36():
    uid = extract_uid(request)
    if not uid:
        return jsonify({"success": False, "message": "مستخدم غير معروف"}), 400

    success, message, result = grid_36_manager.cashout(uid)
    return jsonify({
        "success": success,
        "status": "success" if success else "error",
        "message": message,
        "payout": result.get("payout"),
        "new_balance": result.get("new_balance"),
        "layout": result.get("layout")
    })

# ==========================================
# ⚔️ 2. مسارات الساحة الكبرى Arena
# ==========================================

@games_bp.route('/games/status', methods=['POST', 'GET'])
def arena_status():
    uid = extract_uid(request) if request.method == 'POST' else request.args.get('uid', '')
    res = big_arena_manager.get_status(uid)
    return jsonify(res)

@games_bp.route('/games/join', methods=['POST'])
@games_bp.route('/games/arena/enter', methods=['POST'])
def arena_join():
    uid = extract_uid(request)
    if not uid:
        return jsonify({"success": False, "message": "مستخدم غير معرف"}), 400

    success, message, res = big_arena_manager.enter_arena(uid)
    return jsonify({
        "success": success,
        "message": message,
        "new_balance": res.get("new_balance"),
        "prize_pool": res.get("prize_pool")
    })

@games_bp.route('/games/results', methods=['POST'])
def arena_results():
    data = request.json or {}
    round_id = data.get('round_id', '')
    uid = extract_uid(request)
    res = big_arena_manager.get_results(round_id, uid)
    return jsonify(res)

@games_bp.route('/games/check_notifications', methods=['POST'])
def check_notifications():
    uid = extract_uid(request)
    if not uid:
        return jsonify({"success": False}), 400

    refunded, current_bal = clear_user_pending_refund(uid)
    return jsonify({
        "success": True,
        "refund": refunded,
        "balance": current_bal
    })
