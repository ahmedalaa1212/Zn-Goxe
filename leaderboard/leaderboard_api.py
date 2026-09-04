from flask import Blueprint, jsonify, request
import leaderboard_db

leaderboard_bp = Blueprint('leaderboard', __name__)

@leaderboard_bp.route('/api/leaderboard/data', methods=['GET'])
def get_leaderboard():
    user_id = request.args.get('user_id')
    stats = leaderboard_db.get_global_stats()
    leaderboard = leaderboard_db.get_leaderboard_data()
    
    # حساب السعر اللحظي بناءً على نسبة استهلاك المجمّع
    base_price = 0.05
    total_converted = stats.get('total_converted_znx', 0)
    live_price = base_price + (total_converted / 35_000_000) * 0.45

    return jsonify({
        'success': True,
        'global_total': round(total_converted, 2),
        'max_limit': 35000000,
        'live_price': round(live_price, 4),
        'leaderboard': leaderboard
    })

@leaderboard_bp.route('/api/leaderboard/convert', methods=['POST'])
def convert_currency():
    data = request.json or {}
    user_id = data.get('user_id')
    points = data.get('points', 0)

    if not user_id or points <= 0:
        return jsonify({'success': False, 'message': 'بيانات الطلب غير صالحة.'}), 400

    success, response = leaderboard_db.process_conversion(user_id, float(points))
    if success:
        return jsonify({'success': True, 'data': response})
    else:
        return jsonify({'success': False, 'message': response}), 400
