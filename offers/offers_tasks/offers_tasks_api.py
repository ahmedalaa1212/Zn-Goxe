# API Routes for مهام العروض (offers_tasks)
from flask import Blueprint, request, jsonify
import offers.offers_tasks.offers_tasks_db as db

offers_tasks_bp = Blueprint('offers_tasks', __name__)

@offers_tasks_bp.route('/api/offers/offers_tasks/data', methods=['GET'])
def get_data():
    user_id = request.headers.get('X-Telegram-User-Id')
    data = db.get_offers_tasks_status(user_id)
    return jsonify({'success': True, 'data': data})
