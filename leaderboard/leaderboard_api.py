from flask import Blueprint, jsonify, request
import leaderboard_db

leaderboard_bp = Blueprint('leaderboard', __name__)

@leaderboard_bp.route('/api/leaderboard/init', methods=['GET'])
def init_dashboard():
    user_id = request.args.get('user_id', '')
    if not user_id:
        return jsonify({'success': False, 'message': 'المستخدم غير معرف'}), 400

    user_data = leaderboard_db.get_user_data(user_id) or {
        'balance': 0.0, 'usd_balance': 0.0, 'znx_balance': 0.0, 'total_znx_earned': 0.0
    }
    
    current_tier = leaderboard_db.get_user_tier(user_data['balance'])
    rankings = leaderboard_db.get_leaderboard_rankings()
    global_stats = leaderboard_db.get_global_stats()

    return jsonify({
        'success': True,
        'user': user_data,
        'current_tier': current_tier,
        'tiers_all': leaderboard_db.TIERS_CONFIG,
        'leaderboard': rankings,
        'global_total': global_stats.get('total_converted_znx', 0.0),
        'live_price': 0.0524 # سعر ابتدائي وسيتم رفعه تلقائياً بواسطة الواجهة
    })

@leaderboard_bp.route('/api/leaderboard/convert', methods=['POST'])
def process_conversion():
    data = request.json or {}
    user_id = data.get('user_id')
    amount = float(data.get('amount', 0))

    if not user_id or amount <= 0:
        return jsonify({'success': False, 'message': 'كمية التحويل غير صالحة'}), 400

    success, result = leaderboard_db.execute_conversion(user_id, amount)
    if success:
        return jsonify({'success': True, 'data': result})
    else:
        return jsonify({'success': False, 'message': result}), 400
