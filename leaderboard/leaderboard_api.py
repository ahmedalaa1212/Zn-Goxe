from flask import Blueprint, request, jsonify
from leaderboard.leaderboard_db import get_top_leaderboard, get_user_rank_info
from database import is_user_banned

leaderboard_bp = Blueprint('leaderboard_bp', __name__)

def extract_telegram_id(req):
    return req.headers.get('X-Telegram-User-Id')

@leaderboard_bp.route('/api/leaderboard/top', methods=['GET'])
def get_leaderboard():
    tg_id = extract_telegram_id(request)
    if not tg_id:
        return jsonify({"success": False, "error": "المستخدم غير محدد"}), 400

    if is_user_banned(tg_id):
        return jsonify({"success": False, "error": "حسابك محظور."}), 403

    top_players = get_top_leaderboard(limit=50)
    user_rank_data = get_user_rank_info(tg_id)

    return jsonify({
        "success": True,
        "leaderboard": top_players,
        "user_rank": user_rank_data.get('rank', 999),
        "user_balance": user_rank_data.get('user_balance', 0.0)
    }), 200

