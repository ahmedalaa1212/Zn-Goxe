# API Routes for مهام الحائط (wall_tasks)
from flask import Blueprint, request, jsonify
import offers.wall_tasks.wall_tasks_db as db

wall_tasks_bp = Blueprint('wall_tasks', __name__)

@wall_tasks_bp.route('/api/offers/wall_tasks/data', methods=['GET'])
def get_data():
    user_id = request.headers.get('X-Telegram-User-Id')
    data = db.get_wall_tasks_status(user_id)
    return jsonify({'success': True, 'data': data})
