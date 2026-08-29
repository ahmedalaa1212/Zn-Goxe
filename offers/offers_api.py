from flask import Blueprint, request, jsonify
import db

offers_bp = Blueprint('offers', __name__)

@offers_bp.route('/api/offers/tasks', methods=['GET'])
def get_offer_tasks():
    user_id = request.headers.get('X-Telegram-User-Id')
    category = request.args.get('category', 'offer_goxe')
    
    if not user_id:
        return jsonify({'success': False, 'error': 'المستخدم غير معرف'}), 401
        
    tasks = db.get_active_offer_tasks(category, user_id)
    return jsonify({'success': True, 'tasks': tasks})

@offers_bp.route('/api/offers/claim', methods=['POST'])
def claim_offer_task():
    user_id = request.headers.get('X-Telegram-User-Id')
    data = request.get_json() or {}
    task_id = data.get('task_id')

    if not user_id or not task_id:
        return jsonify({'success': False, 'error': 'بيانات الطلب غير مكتملة'}), 400

    result = db.process_offer_reward(user_id, task_id)
    if result.get('success'):
        return jsonify({
            'success': True,
            'reward': result.get('reward'),
            'new_balance': result.get('new_balance')
        })
    else:
        return jsonify({'success': False, 'error': result.get('error', 'فشل معالجة العرض')}), 400
