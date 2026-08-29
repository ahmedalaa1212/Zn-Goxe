# API Routes for مهام بسيطة (simple_tasks)
from flask import Blueprint, request, jsonify
import offers.simple_tasks.simple_tasks_db as db

simple_tasks_bp = Blueprint('simple_tasks', __name__)

@simple_tasks_bp.route('/api/offers/simple_tasks/data', methods=['GET'])
def get_data():
    user_id = request.headers.get('X-Telegram-User-Id')
    data = db.get_simple_tasks_status(user_id)
    return jsonify({'success': True, 'data': data})
