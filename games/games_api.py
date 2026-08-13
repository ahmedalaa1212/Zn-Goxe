from flask import Blueprint, request, jsonify
from utils.auth import get_authenticated_user
from games.games_db import (
    play_arena_db,
    start_36boxes_game_db,
    reveal_36boxes_tile_db,
    cashout_36boxes_db,
    get_games_state_db
)

games_bp = Blueprint('games', __name__)

# ---------------------------------------------------------
# 1. جلب حالة الألعاب والإعدادات العامة
# ---------------------------------------------------------
@games_bp.route('/state', methods=['GET', 'POST'])
@games_bp.route('/games/state', methods=['GET', 'POST'])
@games_bp.route('/api/games/state', methods=['GET', 'POST'])
def get_games_state():
    user = get_authenticated_user(request)
    if not user:
        return jsonify({"success": False, "error": "مصادقة التليجرام غير صالحة"}), 401

    res = get_games_state_db(user['id'])
    return jsonify(res), 200

# ---------------------------------------------------------
# 2. لعبة الساحة - بدء معركة
# ---------------------------------------------------------
@games_bp.route('/arena/play', methods=['POST'])
@games_bp.route('/games/arena/play', methods=['POST'])
@games_bp.route('/api/games/arena/play', methods=['POST'])
def play_arena():
    user = get_authenticated_user(request)
    if not user:
        return jsonify({"success": False, "error": "غير مصرح بالدخول"}), 401

    data = request.get_json() or {}
    difficulty = data.get("difficulty")
    bet_amount = data.get("bet_amount")

    if not difficulty or bet_amount is None:
        return jsonify({"success": False, "error": "بيانات الطلب غير مكتملة"}), 400

    res = play_arena_db(user['id'], difficulty, bet_amount)
    if not res.get("success"):
        return jsonify(res), 400

    return jsonify(res), 200

# ---------------------------------------------------------
# 3. لعبة 36 صندوق - بدء جلسة
# ---------------------------------------------------------
@games_bp.route('/36boxes/start', methods=['POST'])
@games_bp.route('/games/36boxes/start', methods=['POST'])
@games_bp.route('/api/games/36boxes/start', methods=['POST'])
def start_36boxes():
    user = get_authenticated_user(request)
    if not user:
        return jsonify({"success": False, "error": "غير مصرح بالدخول"}), 401

    data = request.get_json() or {}
    bet_amount = data.get("bet_amount")
    trap_count = data.get("trap_count")

    if bet_amount is None or trap_count is None:
        return jsonify({"success": False, "error": "يرجى تحديد الرهان وعدد القنابل"}), 400

    res = start_36boxes_game_db(user['id'], bet_amount, trap_count)
    if not res.get("success"):
        return jsonify(res), 400

    return jsonify(res), 200

# ---------------------------------------------------------
# 4. لعبة 36 صندوق - كشف صندوق
# ---------------------------------------------------------
@games_bp.route('/36boxes/reveal', methods=['POST'])
@games_bp.route('/games/36boxes/reveal', methods=['POST'])
@games_bp.route('/api/games/36boxes/reveal', methods=['POST'])
def reveal_36boxes():
    user = get_authenticated_user(request)
    if not user:
        return jsonify({"success": False, "error": "غير مصرح بالدخول"}), 401

    data = request.get_json() or {}
    tile_index = data.get("tile_index")

    if tile_index is None:
        return jsonify({"success": False, "error": "لم يتم اختيار الصندوق"}), 400

    res = reveal_36boxes_tile_db(user['id'], tile_index)
    if not res.get("success"):
        return jsonify(res), 400

    return jsonify(res), 200

# ---------------------------------------------------------
# 5. لعبة 36 صندوق - سحب الأرباح (Cashout)
# ---------------------------------------------------------
@games_bp.route('/36boxes/cashout', methods=['POST'])
@games_bp.route('/games/36boxes/cashout', methods=['POST'])
@games_bp.route('/api/games/36boxes/cashout', methods=['POST'])
def cashout_36boxes():
    user = get_authenticated_user(request)
    if not user:
        return jsonify({"success": False, "error": "غير مصرح بالدخول"}), 401

    res = cashout_36boxes_db(user['id'])
    if not res.get("success"):
        return jsonify(res), 400

    return jsonify(res), 200
