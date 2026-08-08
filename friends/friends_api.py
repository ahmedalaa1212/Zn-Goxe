from flask import Blueprint, request, jsonify
from .friends_db import (
    get_friends_data_db,
    get_friends_list_db,
    claim_ref_earnings_db,
    claim_ref_task_db
)

# تعريف الـ Blueprint الخاص بنظام الأصدقاء
friends_bp = Blueprint('friends_bp', __name__)

# اسم بديل لضمان التوافق مع أي ملف يستدعيه بـ friends_api أو friends_bp
friends_api = friends_bp


@friends_bp.route('/data', methods=['GET'])
@friends_bp.route('/api/friends/data', methods=['GET'])
def get_friends_data():
    """جلب ملخص بيانات الأصدقاء والمكافآت للمستخدم"""
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"success": False, "error": "مطلوب معرف المستخدم (user_id)"}), 400

    try:
        data = get_friends_data_db(str(user_id))
        return jsonify({"success": True, **data}), 200
    except Exception as e:
        print(f"❌ خطأ في API جلب بيانات الأصدقاء: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء جلب البيانات"}), 500


@friends_bp.route('/list', methods=['GET'])
@friends_bp.route('/api/friends/list', methods=['GET'])
def get_friends_list():
    """جلب قائمة الأصدقاء التفصيلية"""
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"success": False, "error": "مطلوب معرف المستخدم (user_id)"}), 400

    try:
        friends_list = get_friends_list_db(str(user_id))
        return jsonify({"success": True, "friends": friends_list}), 200
    except Exception as e:
        print(f"❌ خطأ في API جلب قائمة الأصدقاء: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء جلب القائمة"}), 500


@friends_bp.route('/claim-earnings', methods=['POST'])
@friends_bp.route('/api/friends/claim-earnings', methods=['POST'])
def claim_ref_earnings():
    """سحب أرباح الإحالة المعلقة إلى الرصيد الرئيسي"""
    data = request.get_json() or {}
    user_id = data.get('user_id')

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
@friends_bp.route('/api/friends/claim-task', methods=['POST'])
def claim_ref_task():
    """استلام مكافأة مهمة دعوة الأصدقاء"""
    data = request.get_json() or {}
    user_id = data.get('user_id')
    task_id = data.get('task_id')

    if not user_id or task_id is None:
        return jsonify({"success": False, "error": "مطلوب user_id و task_id"}), 400

    try:
        result = claim_ref_task_db(str(user_id), task_id)
        if result.get("success"):
            return jsonify(result), 200
        else:
            return jsonify(result), 400
    except Exception as e:
        print(f"❌ خطأ في API استلام مكافأة المهمة: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء استلام المكافأة"}), 500
