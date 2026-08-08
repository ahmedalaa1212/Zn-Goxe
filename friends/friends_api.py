import json
from urllib.parse import parse_qs, unquote
from flask import Blueprint, request, jsonify
from .friends_db import (
    get_friends_data_db,
    get_friends_list_db,
    claim_ref_earnings_db,
    claim_ref_task_db,
    get_friends_config
)

# تعريف الـ Blueprint الخاص بنظام الأصدقاء
friends_bp = Blueprint('friends_bp', __name__)

# اسم بديل لضمان التوافق التام
friends_api = friends_bp


def extract_user_id(req):
    """استخراج ID المستخدم سواء من initData أو من الكائن المباشر"""
    data = req.get_json(silent=True) or {}
    user_id = data.get('user_id') or req.args.get('user_id')
    if user_id:
        return str(user_id)
    
    init_data = data.get('initData') or req.args.get('initData')
    if init_data:
        try:
            parsed = parse_qs(init_data)
            if 'user' in parsed:
                user_json = unquote(parsed['user'][0])
                user_data = json.loads(user_json)
                if user_data.get('id'):
                    return str(user_data.get('id'))
        except Exception as e:
            print(f"⚠️ Error parsing initData: {e}")
    return None


@friends_bp.route('/data', methods=['GET', 'POST'])
@friends_bp.route('/api/friends/data', methods=['GET', 'POST'])
def get_friends_data():
    """جلب ملخص بيانات الأصدقاء والمكافآت للمستخدم مع الإعدادات الديناميكية من الفايربيس"""
    user_id = extract_user_id(request)
    if not user_id:
        return jsonify({"success": False, "error": "مطلوب معرف المستخدم (user_id)"}), 400

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
    """جلب قائمة الأصدقاء التفصيلية"""
    user_id = extract_user_id(request)
    if not user_id:
        return jsonify({"success": False, "error": "مطلوب معرف المستخدم (user_id)"}), 400

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
    """سحب أرباح الإحالة المعلقة إلى الرصيد الرئيسي"""
    user_id = extract_user_id(request)
    if not user_id:
        return jsonify({"success": False, "error": "مطلوب معرف المستخدم (user_id)"}), 400

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
    """استلام مكافأة مهمة دعوة الأصدقاء"""
    data = request.get_json(silent=True) or {}
    user_id = extract_user_id(request)
    
    task_id = data.get('taskId') or data.get('task_id')
    reward = data.get('reward', 0)
    req_friends = data.get('reqFriends') or data.get('req_friends', 1)

    if not user_id or task_id is None:
        return jsonify({"success": False, "error": "مطلوب user_id و task_id"}), 400

    try:
        result = claim_ref_task_db(str(user_id), task_id, reward, req_friends)
        if result.get("success"):
            return jsonify(result), 200
        else:
            return jsonify(result), 400
    except Exception as e:
        print(f"❌ خطأ في API استلام مكافأة المهمة: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء استلام المكافأة"}), 500
