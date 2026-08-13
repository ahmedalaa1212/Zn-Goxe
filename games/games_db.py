from flask import Blueprint, jsonify, request
from games.games_db import fetch_active_games, init_games_db

# إنشاء Blueprint للألعاب
games_bp = Blueprint('games', __name__, url_prefix='/api/games')

# تهيئة جدول الألعاب عند بدء التشغيل
init_games_db()

@games_bp.route('/list', methods=['GET'])
def get_games_list():
    """إرجاع قائمة الألعاب المفعلة"""
    try:
        games = fetch_active_games()
        return jsonify({"success": True, "games": games}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
