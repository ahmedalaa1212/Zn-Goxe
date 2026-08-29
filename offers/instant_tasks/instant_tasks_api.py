# API Routes for مهام فوري (instant_tasks)
from flask import Blueprint, request, jsonify
import offers.instant_tasks.instant_tasks_db as db

instant_tasks_bp = Blueprint('instant_tasks', __name__)

@instant_tasks_bp.route('/api/offers/instant_tasks/data', methods=['GET'])
def get_data():
    user_id = request.headers.get('X-Telegram-User-Id')
    data = db.get_instant_tasks_status(user_id)
    return jsonify({'success': True, 'data': data})
