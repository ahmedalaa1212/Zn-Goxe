# API Routes for مهام الألعاب (games_tasks)
from flask import Blueprint, request, jsonify
import offers.games_tasks.games_tasks_db as db

games_tasks_bp = Blueprint('games_tasks', __name__)

@games_tasks_bp.route('/api/offers/games_tasks/data', methods=['GET'])
def get_data():
    user_id = request.headers.get('X-Telegram-User-Id')
    data = db.get_games_tasks_status(user_id)
    return jsonify({'success': True, 'data': data})
