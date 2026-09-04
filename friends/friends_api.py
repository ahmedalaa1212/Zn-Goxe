from flask import Blueprint, request, jsonify
from core.security import get_authenticated_user
from .friends_db import (
    get_friends_data_db,
    get_friends_list_db,
    claim_ref_earnings_db,
    claim_ref_task_db,
    get_friends_config
)

friends_bp = Blueprint('friends_bp', __name__)
friends_api = friends_bp


@friends_bp.route('/data', methods=['GET', 'POST'])
@friends_bp.route('/friends/data', methods=['GET', 'POST'])
@friends_bp.route('/api/friends/data', methods=['GET', 'POST'])
def get_friends_data():
    """جلب ملخص بيانات الأصدقاء والمكافآت مع المصادقة وحالة VIP الديناميكية"""
    is_auth, user_id, user_info, err_resp = get_authenticated_user(request, is_post=(request.method == 'POST'))
    if not is_auth:
        return err_resp

    try:
        player_data = get_friends_data_db(str(user_id))
        friends_config = player_data.pop("friends_config", None) or get_friends_config()
        
        # استخراج القيم الديناميكية الخاصة بالـ VIP لنقلها للواجهة مباشرة
        is_vip = player_data.get("is_vip", False)
        effective_commission = player_data.get("effective_commission", 10.0)
        effective_claim_fee = player_data.get("effective_claim_fee", 1.5)

        return jsonify({
            "success": True, 
            "player": player_data,
            "friends_config": friends_config,
            "is_vip": is_vip,
            "effective_commission": effective_commission,
            "effective_claim_fee": effective_claim_fee
        }), 200
    except Exception as e:
        print(f"❌ خطأ في API جلب بيانات الأصدقاء: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء جلب البيانات"}), 500


@friends_bp.route('/list', methods=['GET', 'POST'])
@friends_bp.route('/friends/list', methods=['GET', 'POST'])
@friends_bp.route('/api/friends/list', methods=['GET', 'POST'])
def get_friends_list():
    """جلب قائمة الأصدقاء التفصيلية للمستخدم المصرح له فقط"""
    is_auth, user_id, user_info, err_resp = get_authenticated_user(request, is_post=(request.method == 'POST'))
    if not is_auth:
        return err_resp

    try:
        friends_list = get_friends_list_db(str(user_id))
        return jsonify({"success": True, "friends": friends_list}), 200
    except Exception as e:
        print(f"❌ خطأ في API جلب قائمة الأصدقاء: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء جلب القائمة"}), 500


@friends_bp.route('/claim-earnings', methods=['POST'])
@friends_bp.route('/claim_ref_earnings', methods=['POST'])
@friends_bp.route('/friends/claim-earnings', methods=['POST'])
@friends_bp.route('/api/friends/claim-earnings', methods=['POST'])
@friends_bp.route('/api/friends/claim_ref_earnings', methods=['POST'])
def claim_ref_earnings():
    """سحب أرباح الإحالة المعلقة مع احتساب خصم 0% للـ VIP أو 1.5% للعاديين"""
    is_auth, user_id, user_info, err_resp = get_authenticated_user(request, is_post=True)
    if not is_auth:
        return err_resp

    try:
        result = claim_ref_earnings_db(str(user_id))
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
    except Exception as e:
        print(f"❌ خطأ في API سحب الأرباح: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء عملية السحب"}), 500


@friends_bp.route('/claim-task', methods=['POST'])
@friends_bp.route('/claim_ref_task', methods=['POST'])
@friends_bp.route('/friends/claim-task', methods=['POST'])
@friends_bp.route('/api/friends/claim-task', methods=['POST'])
@friends_bp.route('/api/friends/claim_ref_task', methods=['POST'])
def claim_ref_task():
    """استلام مكافأة مهمة دعوة الأصدقاء مع التحقق من شروط الترقيات الجديدة"""
    is_auth, user_id, user_info, err_resp = get_authenticated_user(request, is_post=True)
    if not is_auth:
        return err_resp

    data = request.get_json(silent=True) or {}
    task_id = data.get('taskId') if data.get('taskId') is not None else data.get('task_id')
    reward = data.get('reward', 0)
    req_friends = data.get('reqFriends') if data.get('reqFriends') is not None else data.get('req_friends', 1)

    if task_id is None:
        return jsonify({"success": False, "error": "مطلوب معرف المهمة task_id"}), 400

    try:
        result = claim_ref_task_db(str(user_id), task_id, reward, req_friends)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
    except Exception as e:
        print(f"❌ خطأ في API استلام مكافأة المهمة: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء استلام المكافأة"}), 500
