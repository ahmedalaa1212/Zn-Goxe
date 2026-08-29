# API Routes for مهام الفولترا (voltra_tasks)
from flask import Blueprint, request, jsonify
import offers.voltra_tasks.voltra_tasks_db as db

voltra_tasks_bp = Blueprint('voltra_tasks', __name__)

@voltra_tasks_bp.route('/api/offers/voltra_tasks/data', methods=['GET'])
def get_data():
    user_id = request.headers.get('X-Telegram-User-Id')
    data = db.get_voltra_tasks_status(user_id)
    return jsonify({'success': True, 'data': data})
