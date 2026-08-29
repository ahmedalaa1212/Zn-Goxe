# API Routes for مهام اسطوانة (disk_tasks)
from flask import Blueprint, request, jsonify
import offers.disk_tasks.disk_tasks_db as db

disk_tasks_bp = Blueprint('disk_tasks', __name__)

@disk_tasks_bp.route('/api/offers/disk_tasks/data', methods=['GET'])
def get_data():
    user_id = request.headers.get('X-Telegram-User-Id')
    data = db.get_disk_tasks_status(user_id)
    return jsonify({'success': True, 'data': data})
