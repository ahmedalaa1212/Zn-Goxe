import json
from flask import Blueprint, request, jsonify
from core.security import get_authenticated_user
from .friends_db import (
    get_friends_data_db,
    get_friends_list_db,
    claim_ref_earnings_db,
    claim_ref_task_db,
    get_friends_config
)

# تعريف الـ Blueprint الخاص بنظام الأصدقاء
friends_bp = Blueprint('friends_bp', __name__)

# اسم بديل لضمان التوافق التام مع النظام الرئيسي
friends_api = friends_bp


@friends_bp.route('/data', methods=['GET', 'POST'])
@friends_bp.route('/api/friends/data', methods=['GET', 'POST'])
def get_friends_data():
    """جلب ملخص بيانات الأصدقاء والمكافآت مع المصادقة والحماية التامة"""
    is_auth, user_id, user_info, err_resp = get_authenticated_user(request, is_post=(request.method == 'POST'))
    if not is_auth:
        return err_resp

    try:
        player_data = get_friends_data_db(str(user_id))
        friends_config = player_data.pop("friends_config", None) or get_friends_config()
        
        return jsonify({
            "success": True, 
            "player": player_data,
            "friends_config": friends_config
        }), 200
    except Exception as e:
        print(f"❌ خطأ في API جلب بيانات الأصدقاء: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء جلب البيانات"}), 500


@friends_bp.route('/list', methods=['GET', 'POST'])
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
@friends_bp.route('/api/friends/claim-earnings', methods=['POST'])
@friends_bp.route('/api/friends/claim_ref_earnings', methods=['POST'])
def claim_ref_earnings():
    """سحب أرباح الإحالة المعلقة مع التحقق من الهوية من التشفير الرسمى لتليجرام"""
    is_auth, user_id, user_info, err_resp = get_authenticated_user(request, is_post=True)
    if not is_auth:
        return err_resp

    try:
        result = claim_ref_earnings_db(str(user_id))
        if result.get("success"):
            return jsonify(result), 200
        else:
            return jsonify(result), 400
    except Exception as e:
        print(f"❌ خطأ في API سحب الأرباح: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء عملية السحب"}), 500


@friends_bp.route('/claim-task', methods=['POST'])
@friends_bp.route('/claim_ref_task', methods=['POST'])
@friends_bp.route('/api/friends/claim-task', methods=['POST'])
@friends_bp.route('/api/friends/claim_ref_task', methods=['POST'])
def claim_ref_task():
    """استلام مكافأة مهمة دعوة الأصدقاء بشكل مؤمن تماماً"""
    is_auth, user_id, user_info, err_resp = get_authenticated_user(request, is_post=True)
    if not is_auth:
        return err_resp

    data = request.get_json(silent=True) or {}
    task_id = data.get('taskId') or data.get('task_id')
    reward = data.get('reward', 0)
    req_friends = data.get('reqFriends') or data.get('req_friends', 1)

    if task_id is None:
        return jsonify({"success": False, "error": "مطلوب معرف المهمة task_id"}), 400

    try:
        result = claim_ref_task_db(str(user_id), task_id, reward, req_friends)
        if result.get("success"):
            return jsonify(result), 200
        else:
            return jsonify(result), 400
    except Exception as e:
        print(f"❌ خطأ في API استلام مكافأة المهمة: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء استلام المكافأة"}), 500
