from flask import Blueprint, request, jsonify
from core.security import get_authenticated_user
from games.games_db import (
    play_arena_db,
    start_36boxes_game_db,
    reveal_36boxes_tile_db,
    cashout_36boxes_db,
    get_games_state_db
)

games_bp = Blueprint('games', __name__)

def _get_user_from_request(req):
    """دالة مساعدة للتحقق من مصادقة المستخدم وتجهيز البيانات"""
    is_post = (req.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(req, is_post=is_post)
    if not success:
        return None, error_res
    
    user = user_info if isinstance(user_info, dict) else {}
    if 'id' not in user:
        user['id'] = telegram_id
        
    return user, None

# ---------------------------------------------------------
# 1. جلب حالة الألعاب والإعدادات العامة
# ---------------------------------------------------------
@games_bp.route('/state', methods=['GET', 'POST'])
@games_bp.route('/games/state', methods=['GET', 'POST'])
@games_bp.route('/api/games/state', methods=['GET', 'POST'])
def get_games_state():
    user, error_res = _get_user_from_request(request)
    if error_res:
        return error_res

    res = get_games_state_db(user['id'])
    return jsonify(res), 200

# ---------------------------------------------------------
# 2. لعبة الساحة - بدء معركة
# ---------------------------------------------------------
@games_bp.route('/arena/play', methods=['POST'])
@games_bp.route('/games/arena/play', methods=['POST'])
@games_bp.route('/api/games/arena/play', methods=['POST'])
def play_arena():
    user, error_res = _get_user_from_request(request)
    if error_res:
        return error_res

    data = request.get_json() or {}
    difficulty = data.get("difficulty")
    raw_bet = data.get("bet_amount")

    if not difficulty or raw_bet is None:
        return jsonify({"success": False, "error": "بيانات الطلب غير مكتملة"}), 400

    try:
        bet_amount = float(raw_bet)
        if bet_amount <= 0:
            return jsonify({"success": False, "error": "مبلغ الرهان يجب أن يكون أكبر من 0"}), 400
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "قيمة الرهان غير صالحة"}), 400

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
    user, error_res = _get_user_from_request(request)
    if error_res:
        return error_res

    data = request.get_json() or {}
    raw_bet = data.get("bet_amount")
    raw_trap = data.get("trap_count")

    if raw_bet is None or raw_trap is None:
        return jsonify({"success": False, "error": "يرجى تحديد الرهان وعدد القنابل"}), 400

    try:
        bet_amount = float(raw_bet)
        trap_count = int(raw_trap)
        if bet_amount <= 0 or trap_count < 1 or trap_count >= 36:
            return jsonify({"success": False, "error": "قيم الرهان أو عدد القنابل غير صالحة"}), 400
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "البيانات المدخلة غير صالحة"}), 400

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
    user, error_res = _get_user_from_request(request)
    if error_res:
        return error_res

    data = request.get_json() or {}
    raw_tile = data.get("tile_index")

    if raw_tile is None:
        return jsonify({"success": False, "error": "لم يتم اختيار الصندوق"}), 400

    try:
        tile_index = int(raw_tile)
        if tile_index < 0 or tile_index >= 36:
            return jsonify({"success": False, "error": "رقم الصندوق غير صحيح"}), 400
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "رقم الصندوق غير صالح"}), 400

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
    user, error_res = _get_user_from_request(request)
    if error_res:
        return error_res

    res = cashout_36boxes_db(user['id'])
    if not res.get("success"):
        return jsonify(res), 400

    return jsonify(res), 200
