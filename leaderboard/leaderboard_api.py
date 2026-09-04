from flask import Blueprint, jsonify, request
import leaderboard_db

leaderboard_bp = Blueprint('leaderboard', __name__)

@leaderboard_bp.route('/init', methods=['GET'])
def init_dashboard():
    user_id = request.args.get('user_id') or request.args.get('tg_id', '')
    if not user_id:
        return jsonify({'success': False, 'message': 'المستخدم غير معرف'}), 400

    user_data = leaderboard_db.get_user_data(str(user_id))
    current_tier = leaderboard_db.get_user_tier(user_data['balance'])
    rankings = leaderboard_db.get_leaderboard_rankings()
    global_stats = leaderboard_db.get_global_stats()

    return jsonify({
        'success': True,
        'user': user_data,
        'current_tier': current_tier,
        'tiers_all': leaderboard_db.TIERS_CONFIG,
        'leaderboard': rankings,
        'global_total': float(global_stats.get('total_converted_znx', 0.0)),
        'max_global_znx': leaderboard_db.MAX_GLOBAL_ZNX,
        'live_price': 0.0524
    })

@leaderboard_bp.route('/convert', methods=['POST'])
def process_conversion():
    data = request.json or {}
    user_id = data.get('user_id') or data.get('tg_id')
    
    try:
        amount = float(data.get('amount', 0))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'كمية التحويل غير صالحة'}), 400

    if not user_id or amount <= 0:
        return jsonify({'success': False, 'message': 'بيانات التحويل غير صالحة'}), 400

    success, result = leaderboard_db.execute_conversion(str(user_id), amount)
    if success:
        return jsonify({'success': True, 'data': result})
    else:
        return jsonify({'success': False, 'message': result}), 400
