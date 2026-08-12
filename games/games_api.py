from flask import Blueprint, request, jsonify
from games.games_db import (
    get_big_arena_config,
    clear_user_pending_refund,
    get_user_data
)
from games.grid_36 import grid_36_manager
from games.arena import big_arena_manager

games_bp = Blueprint('games_api', __name__, url_prefix='/api')

def extract_uid(req) -> str:
    if req.is_json:
        data = req.get_json(silent=True) or {}
        tg_id = data.get('tg_id') or data.get('uid') or data.get('user_id')
        if tg_id:
            return str(tg_id)

    tg_id_arg = req.args.get('tg_id') or req.args.get('uid') or req.args.get('user_id')
    if tg_id_arg:
        return str(tg_id_arg)

    if req.form:
        tg_id_form = req.form.get('tg_id') or req.form.get('uid')
        if tg_id_form:
            return str(tg_id_form)

    return ""

@games_bp.route('/user/info', methods=['GET', 'POST'])
def get_user_info():
    uid = extract_uid(request)
    if not uid:
        return jsonify({"success": False, "message": "لم يتم العثور على ID المستخدم"}), 400

    refunded, new_bal, msg = clear_user_pending_refund(uid)
    exists, udata = get_user_data(uid)
    if not exists:
        return jsonify({"success": False, "message": "المستخدم غير موجود"}), 404

    udata = udata or {}
    real_bal = round(float(udata.get('balance', udata.get('zn_balance', new_bal))), 2)

    return jsonify({
        "success": True,
        "uid": uid,
        "balance": real_bal,
        "refund_amount": refunded,
        "name": udata.get('name', udata.get('first_name', 'مستخدم'))
    })

@games_bp.route('/game/start', methods=['POST'])
@games_bp.route('/games/grid36/start', methods=['POST'])
def start_grid36():
    uid = extract_uid(request)
    data = request.get_json(silent=True) or {}
    bet_amount = float(data.get('bet_amount', 100.0))
    broken_count = int(data.get('broken_count', 3))

    if not uid:
        return jsonify({"success": False, "message": "لم يتم العثور على معرف المستخدم"}), 400

    success, message, result = grid_36_manager.start_new_game(uid, bet_amount, broken_count)
    result = result or {}
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
    data = request.get_json(silent=True) or {}
    box_index = int(data.get('box_index', -1))
    session_token = data.get('session_token')

    if not uid or box_index < 0:
        return jsonify({"success": False, "message": "بيانات غير مكتملة"}), 400

    success, message, result = grid_36_manager.open_box(uid, box_index, session_token)
    result = result or {}
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
    result = result or {}
    return jsonify({
        "success": success,
        "status": "success" if success else "error",
        "message": message,
        "payout": result.get("payout"),
        "new_balance": result.get("new_balance"),
        "layout": result.get("layout")
    })

@games_bp.route('/games/status', methods=['POST', 'GET'])
def arena_status():
    uid = extract_uid(request)
    res = big_arena_manager.get_status(uid)
    if isinstance(res, dict):
        arena_cfg = get_big_arena_config()
        if 'payout_percentages' not in res:
            res['payout_percentages'] = arena_cfg.get('payout_percentages', [40.0, 20.0, 10.0, 8.0, 6.0, 5.0, 4.0, 3.0, 2.0, 2.0])
        return jsonify(res)
    return jsonify({"success": False})

@games_bp.route('/games/join', methods=['POST'])
@games_bp.route('/games/arena/enter', methods=['POST'])
def arena_join():
    uid = extract_uid(request)
    if not uid:
        return jsonify({"success": False, "message": "مستخدم غير معرف"}), 400

    success, message, res = big_arena_manager.enter_arena(uid)
    res = res or {}
    return jsonify({
        "success": success,
        "message": message,
        "new_balance": res.get("new_balance"),
        "prize_pool": res.get("prize_pool")
    })

@games_bp.route('/games/results', methods=['POST'])
def arena_results():
    data = request.get_json(silent=True) or {}
    round_id = data.get('round_id', '')
    uid = extract_uid(request)
    res = big_arena_manager.get_results(round_id, uid)
    return jsonify(res if isinstance(res, dict) else {"success": False})

@games_bp.route('/games/check_notifications', methods=['GET', 'POST'])
def check_notifications():
    uid = extract_uid(request)
    if not uid:
        return jsonify({"success": False, "message": "لم يتم العثور على المعرف"}), 400

    refunded, current_bal, message = clear_user_pending_refund(uid)
    return jsonify({
        "success": True,
        "refund": refunded,
        "balance": current_bal,
        "message": message,
        "has_notification": bool(message or refunded > 0)
    })
