from flask import Blueprint, request, jsonify
import offers.offers_db as offers_db

offers_bp = Blueprint('offers', __name__)

@offers_bp.route('/api/offers/<module_key>/data', methods=['GET'])
def get_sub_module_data(module_key):
    """توجيه الطلب للبيانات الخاصة بكل مجلد فرعي من الـ 8"""
    user_id = request.headers.get('X-Telegram-User-Id')
    if not user_id:
        return jsonify({'success': False, 'error': 'المستخدم غير معرف'}), 401
        
    data = offers_db.get_sub_module_content(module_key, user_id)
    return jsonify({'success': True, 'items': data.get('items', []), 'html': data.get('html', None)})

@offers_bp.route('/api/offers/<module_key>/claim', methods=['POST'])
def claim_sub_module_reward(module_key):
    """معالجة الأرباح الخاصة بأي قائمة فرعية وتسجيلها بالرصيد الفعلي"""
    user_id = request.headers.get('X-Telegram-User-Id')
    data = request.get_json() or {}
    task_id = data.get('task_id')

    if not user_id or not task_id:
        return jsonify({'success': False, 'error': 'بيانات ناقصة'}), 400

    result = offers_db.process_sub_module_payout(module_key, user_id, task_id)
    if result.get('success'):
        return jsonify({
            'success': True,
            'reward': result.get('reward'),
            'new_balance': result.get('new_balance')
        })
    else:
        return jsonify({'success': False, 'error': result.get('error', 'فشل معالجة الطلب')}), 400
