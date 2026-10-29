# -*- coding: utf-8 -*-
# addons/addons_api.py
from flask import Blueprint, request, jsonify
from core.security import get_authenticated_user
from addons.addons_db import (
    create_promo_code,
    redeem_promo_code,
    get_all_promo_codes,
    delete_promo_code,
    toggle_promo_code_status,
    get_user_full_data_for_admin,
    execute_admin_data_action,
    undo_last_admin_actions,
    get_admin_action_logs,
    clear_admin_action_logs
)

addons_bp = Blueprint('addons_bp', __name__)


def _check_admin_auth(is_post=True):
    """التحقق الصارم من توقيع تيليجرام وصلاحية الأدمن لمنع أي اختراق أو تلاعب"""
    from admin_app import is_admin_authorized
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success:
        return False, None, error_res
    if not is_admin_authorized(telegram_id):
        return False, None, (jsonify({"success": False, "message": "🚫 غير مصرح لك للوصول إلى لوحة الإدارة"}), 403)
    return True, str(telegram_id), None


# ==================== مسارات أكواد المكافآت (Promo Codes) ====================

@addons_bp.route('/api/admin/promo/create', methods=['POST'])
def api_create_promo():
    is_auth, admin_id, err_resp = _check_admin_auth(is_post=True)
    if not is_auth:
        return err_resp

    data = request.get_json(silent=True) or {}
    code = data.get('code')
    coins = data.get('coins', 0)
    duration_val = data.get('duration_val', 1)
    duration_type = data.get('duration_type', 'hours')
    max_uses = data.get('max_uses', 0)

    success, msg = create_promo_code(code, coins, duration_val, duration_type, max_uses)
    return jsonify({'success': success, 'message': msg})


@addons_bp.route('/api/admin/promo/list', methods=['GET'])
def api_list_promo():
    is_auth, admin_id, err_resp = _check_admin_auth(is_post=False)
    if not is_auth:
        return err_resp

    codes = get_all_promo_codes()
    return jsonify({'success': True, 'codes': codes})


@addons_bp.route('/api/admin/promo/delete', methods=['POST'])
def api_delete_promo():
    is_auth, admin_id, err_resp = _check_admin_auth(is_post=True)
    if not is_auth:
        return err_resp

    data = request.get_json(silent=True) or {}
    code = data.get('code')
    success, msg = delete_promo_code(code)
    return jsonify({'success': success, 'message': msg})


@addons_bp.route('/api/admin/promo/toggle', methods=['POST'])
def api_toggle_promo():
    is_auth, admin_id, err_resp = _check_admin_auth(is_post=True)
    if not is_auth:
        return err_resp

    data = request.get_json(silent=True) or {}
    code = data.get('code')
    is_active = data.get('is_active', True)
    success, msg = toggle_promo_code_status(code, is_active)
    return jsonify({'success': success, 'message': msg})


@addons_bp.route('/api/user/promo/redeem', methods=['POST'])
def api_redeem_promo():
    # تأمين المسار: أخذ الـ ID الموثق من التوكن حصراً وليس من الـ Body لمنع التزوير
    success_auth, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success_auth:
        return error_res

    data = request.get_json(silent=True) or {}
    code = data.get('code')
    success, msg, reward = redeem_promo_code(telegram_id, code)
    return jsonify({'success': success, 'message': msg, 'reward': reward})


# ==================== مسارات التحكم الشامل في بيانات المستخدمين ====================

@addons_bp.route('/api/admin/data/user-info', methods=['GET'])
def api_admin_get_user_info():
    """فحص وجلب كافة بيانات وممتلكات اللاعب بالـ ID"""
    is_auth, admin_id, err_resp = _check_admin_auth(is_post=False)
    if not is_auth:
        return err_resp

    target_id = request.args.get('telegram_id', '').strip()
    result = get_user_full_data_for_admin(target_id)
    return jsonify(result)


@addons_bp.route('/api/admin/data/execute', methods=['POST'])
def api_admin_execute_data_action():
    """تنفيذ عمليات الإضافة / الخصم / الترقية / المخازن / شحن VIP لمستخدم أو للجميع"""
    is_auth, admin_id, err_resp = _check_admin_auth(is_post=True)
    if not is_auth:
        return err_resp

    payload = request.get_json(silent=True) or {}
    result = execute_admin_data_action(admin_id, payload)
    return jsonify(result)


@addons_bp.route('/api/admin/data/undo', methods=['POST'])
def api_admin_undo_actions():
    """إرجاع آخر N عمليات أو عملية محددة وإعادة بيانات الحسابات كما كانت تماماً"""
    is_auth, admin_id, err_resp = _check_admin_auth(is_post=True)
    if not is_auth:
        return err_resp

    data = request.get_json(silent=True) or {}
    count = data.get('count', 1)
    log_id = data.get('log_id', None)
    result = undo_last_admin_actions(admin_id, count=count, specific_log_id=log_id)
    return jsonify(result)


@addons_bp.route('/api/admin/data/logs', methods=['GET'])
def api_admin_get_data_logs():
    """جلب سجل العمليات الإدارية"""
    is_auth, admin_id, err_resp = _check_admin_auth(is_post=False)
    if not is_auth:
        return err_resp

    logs = get_admin_action_logs(limit=50)
    return jsonify({'success': True, 'logs': logs})


@addons_bp.route('/api/admin/data/clear-logs', methods=['POST'])
def api_admin_clear_data_logs():
    """مسح سجل العرض فقط دون المساس بأرصدة أو بيانات المستخدمين"""
    is_auth, admin_id, err_resp = _check_admin_auth(is_post=True)
    if not is_auth:
        return err_resp

    success, msg = clear_admin_action_logs()
    return jsonify({'success': success, 'message': msg})
