from flask import Blueprint, request, jsonify, make_response
from core.security import get_authenticated_user
from .friends_db import (
    get_friends_data_db,
    get_friends_list_db,
    claim_ref_earnings_db,
    claim_ref_task_db,
    get_friends_config,
    register_referral_db
)

friends_bp = Blueprint('friends_bp', __name__)
friends_api = friends_bp


def _no_cache_json(payload, status_code=200):
    """منع المتصفح أو WebView من تخزين استجابات الـ API لضمان التحديث اللحظي من Supabase"""
    resp = make_response(jsonify(payload), status_code)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@friends_bp.route('/data', methods=['GET', 'POST'])
@friends_bp.route('/friends/data', methods=['GET', 'POST'])
@friends_bp.route('/api/friends/data', methods=['GET', 'POST'])
def get_friends_data():
    """جلب ملخص بيانات الأصدقاء والمكافآت وقائمة الأصدقاء الحية من Supabase"""
    is_auth, user_id, user_info, err_resp = get_authenticated_user(request, is_post=(request.method == 'POST'))
    if not is_auth:
        return err_resp

    try:
        body = request.get_json(silent=True) or {}
        start_param = body.get("start_param") or request.args.get("start_param")
        user_name = None
        if isinstance(user_info, dict):
            user_name = user_info.get("first_name") or user_info.get("username")

        player_data = get_friends_data_db(str(user_id), start_param=start_param, user_name=user_name)

        friends_config = player_data.get("friends_config") or get_friends_config(force_refresh=True)
        friends_list = player_data.get("friends", [])

        is_vip = player_data.get("is_vip", False)
        effective_commission = player_data.get("effective_commission", 10.0)
        effective_claim_fee = player_data.get("effective_claim_fee", 1.5)

        return _no_cache_json({
            "success": True,
            "player": player_data,
            "friends": friends_list,
            "friends_config": friends_config,
            "is_vip": is_vip,
            "effective_commission": effective_commission,
            "effective_claim_fee": effective_claim_fee
        }, 200)
    except Exception as e:
        print(f"❌ خطأ في API جلب بيانات الأصدقاء: {e}")
        return _no_cache_json({"success": False, "error": "حدث خطأ أثناء جلب البيانات"}, 500)


@friends_bp.route('/list', methods=['GET', 'POST'])
@friends_bp.route('/friends/list', methods=['GET', 'POST'])
@friends_bp.route('/api/friends/list', methods=['GET', 'POST'])
def get_friends_list():
    """جلب قائمة الأصدقاء التفصيلية مع قراءة ترقياتهم الحية من قاعدة البيانات"""
    is_auth, user_id, user_info, err_resp = get_authenticated_user(request, is_post=(request.method == 'POST'))
    if not is_auth:
        return err_resp

    try:
        friends_list = get_friends_list_db(str(user_id))
        return _no_cache_json({"success": True, "friends": friends_list}, 200)
    except Exception as e:
        print(f"❌ خطأ في API جلب قائمة الأصدقاء: {e}")
        return _no_cache_json({"success": False, "error": "حدث خطأ أثناء جلب القائمة"}, 500)


@friends_bp.route('/register', methods=['POST'])
@friends_bp.route('/friends/register', methods=['POST'])
@friends_bp.route('/api/friends/register', methods=['POST'])
def register_referral():
    """نقطة نهاية لتسجيل دعوة صديق جديد بأمان"""
    is_auth, user_id, user_info, err_resp = get_authenticated_user(request, is_post=True)
    if not is_auth:
        return err_resp

    data = request.get_json(silent=True) or {}
    referrer_id = data.get("referrer_id") or data.get("ref") or data.get("start_param")
    if not referrer_id:
        return _no_cache_json({"success": False, "error": "مطلوب معرف الداعي referrer_id"}, 400)

    user_name = "صديق"
    if isinstance(user_info, dict):
        user_name = user_info.get("first_name") or user_info.get("username") or "صديق"

    try:
        result = register_referral_db(str(referrer_id), str(user_id), friend_name=user_name)
        status_code = 200 if result.get("success") else 400
        return _no_cache_json(result, status_code)
    except Exception as e:
        print(f"❌ خطأ في API تسجيل الإحالة: {e}")
        return _no_cache_json({"success": False, "error": "حدث خطأ أثناء تسجيل الإحالة"}, 500)


@friends_bp.route('/claim-earnings', methods=['POST'])
@friends_bp.route('/claim_ref_earnings', methods=['POST'])
@friends_bp.route('/friends/claim-earnings', methods=['POST'])
@friends_bp.route('/api/friends/claim-earnings', methods=['POST'])
@friends_bp.route('/api/friends/claim_ref_earnings', methods=['POST'])
def claim_ref_earnings():
    """سحب أرباح الإحالة المعلقة مع احتساب خصم 0% للـ VIP أو النسبة المحددة للعاديين"""
    is_auth, user_id, user_info, err_resp = get_authenticated_user(request, is_post=True)
    if not is_auth:
        return err_resp

    try:
        result = claim_ref_earnings_db(str(user_id))
        status_code = 200 if result.get("success") else 400
        return _no_cache_json(result, status_code)
    except Exception as e:
        print(f"❌ خطأ في API سحب الأرباح: {e}")
        return _no_cache_json({"success": False, "error": "حدث خطأ أثناء عملية السحب"}, 500)


@friends_bp.route('/claim-task', methods=['POST'])
@friends_bp.route('/claim_ref_task', methods=['POST'])
@friends_bp.route('/friends/claim-task', methods=['POST'])
@friends_bp.route('/api/friends/claim-task', methods=['POST'])
@friends_bp.route('/api/friends/claim_ref_task', methods=['POST'])
def claim_ref_task():
    """استلام مكافأة مهمة دعوة الأصدقاء مع التحقق الصارم من شرط الترقيات المحدد في Supabase"""
    is_auth, user_id, user_info, err_resp = get_authenticated_user(request, is_post=True)
    if not is_auth:
        return err_resp

    data = request.get_json(silent=True) or {}
    task_id = data.get('taskId') if data.get('taskId') is not None else data.get('task_id')
    reward = data.get('reward', 0)
    req_friends = data.get('reqFriends') if data.get('reqFriends') is not None else data.get('req_friends', 1)

    if task_id is None:
        return _no_cache_json({"success": False, "error": "مطلوب معرف المهمة task_id"}, 400)

    try:
        result = claim_ref_task_db(str(user_id), task_id, reward, req_friends)
        status_code = 200 if result.get("success") else 400
        return _no_cache_json(result, status_code)
    except Exception as e:
        print(f"❌ خطأ في API استلام مكافأة المهمة: {e}")
        return _no_cache_json({"success": False, "error": "حدث خطأ أثناء استلام المكافأة"}, 500)
