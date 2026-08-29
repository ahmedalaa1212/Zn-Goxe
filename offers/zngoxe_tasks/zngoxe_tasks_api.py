# API Routes for مهام zngoxe (zngoxe_tasks)
from flask import Blueprint, request, jsonify
import offers.zngoxe_tasks.zngoxe_tasks_db as db

zngoxe_tasks_bp = Blueprint('zngoxe_tasks', __name__)

@zngoxe_tasks_bp.route('/api/offers/zngoxe_tasks/data', methods=['GET'])
def get_data():
    user_id = request.headers.get('X-Telegram-User-Id')
    data = db.get_zngoxe_tasks_status(user_id)
    return jsonify({'success': True, 'data': data})
