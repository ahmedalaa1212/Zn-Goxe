from flask import Blueprint, request, jsonify
from games.arena import big_arena_manager
from games.grid_36 import boxes_game_manager

games_bp = Blueprint('games_bp', __name__)

@games_bp.route('/api/games/arena/status', methods=['POST'])
def arena_status():
    data = request.get_json(silent=True) or {}
    uid = data.get('tg_id', '')
    res = big_arena_manager.get_status(uid)
    return jsonify(res)

@games_bp.route('/api/games/arena/join', methods=['POST'])
def arena_join():
    data = request.get_json(silent=True) or {}
    uid = data.get('tg_id', '')
    success, msg, extra = big_arena_manager.enter_arena(uid)
    return jsonify({"success": success, "message": msg, **extra})

@games_bp.route('/api/games/boxes/play', methods=['POST'])
def boxes_play():
    data = request.get_json(silent=True) or {}
    uid = data.get('tg_id', '')
    box_index = data.get('box_index', 0)
    bet_amount = data.get('bet_amount', 100.0)

    success, msg, result = boxes_game_manager.play_box(uid, box_index, bet_amount)
    return jsonify({"success": success, "message": msg, **result})
