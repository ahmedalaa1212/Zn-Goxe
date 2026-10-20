# -*- coding: utf-8 -*-
"""
tasks/tasks_api.py - مسارات API لنظام المهام والحملات الإعلانية عبر Supabase (PostgreSQL)
مؤمن بالكامل ضد تخطي المؤقت (Server-Side Timer)، وتكرار الطلبات (Atomic Locking)، وحقن القيم الخبيثة ⚡
"""
import math
import urllib.parse
from flask import Blueprint, jsonify, request
from core.security import get_authenticated_user
from database import get_user_balances, _sanitize_id

try:
    from tasks.tasks_db import (
        DEFAULT_TASKS_CONFIG,
        FORBIDDEN_KEYWORDS,
        ensure_tasks_tables_and_settings,
        get_tasks_config,
        get_tasks_config_from_db,
        get_min_reward_for_platform,
        is_task_completed_by_user,
        get_cached_raw_campaigns,
        get_active_campaigns,
        invalidate_campaigns_cache,
        start_user_task,
        complete_user_task,
        create_ad_campaign,
        cancel_ad_campaign,
        convert_balance_to_ad_balance
    )
except ImportError:
    from .tasks_db import (
        DEFAULT_TASKS_CONFIG,
        FORBIDDEN_KEYWORDS,
        ensure_tasks_tables_and_settings,
        get_tasks_config,
        get_tasks_config_from_db,
        get_min_reward_for_platform,
        is_task_completed_by_user,
        get_cached_raw_campaigns,
        get_active_campaigns,
        invalidate_campaigns_cache,
        start_user_task,
        complete_user_task,
        create_ad_campaign,
        cancel_ad_campaign,
        convert_balance_to_ad_balance
    )

# إنشاء الـ Blueprint الخاص بمسارات المهام والحملات الإعلانية
tasks_bp = Blueprint('tasks', __name__)


# ==================== دوال فحص المدخلات الأمنية ====================

def _parse_safe_float(val, field_name="القيمة") -> float:
    """تحويل وفحص الأرقام العشرية بأمان تام ضد NaN و Infinity"""
    try:
        num = float(val)
    except (ValueError, TypeError):
        raise ValueError(f"{field_name} غير صحيحة")
    if not math.isfinite(num) or num <= 0 or num > 1e9:
        raise ValueError(f"{field_name} يجب أن تكون رقماً صحيحاً أكبر من صفر")
    return round(num, 4)


def _parse_safe_int(val, field_name="العدد") -> int:
    """تحويل وفحص الأعداد الصحيحة ومنع تمرير كسور عشرية في عدد الأعضاء"""
    if isinstance(val, bool) or val is None:
        raise ValueError(f"{field_name} غير صحيح")
    try:
        if isinstance(val, float) and not val.is_integer():
            raise ValueError()
        s_val = str(val).strip()
        if '.' in s_val:
            f_val = float(s_val)
            if not f_val.is_integer():
                raise ValueError()
            num = int(f_val)
        else:
            num = int(s_val)
    except (ValueError, TypeError):
        raise ValueError(f"{field_name} يجب أن يكون رقماً صحيحاً بدون كسور")

    if num < 1 or num > 1000000:
        raise ValueError(f"{field_name} خارج النطاق المسموح به")
    return num


# ==================== المسارات (Endpoints) ====================

@tasks_bp.route('/get_campaigns', methods=['GET'])
def get_campaigns():
    """جلب قائمة الحملات المتاحة للمستخدم مع تحديث حالة الإكمال والرصيد والإعدادات الديناميكية لحظياً من Supabase"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=False)
    if not success:
        return error_res

    telegram_id_str = _sanitize_id(telegram_id) or str(telegram_id).strip()

    # جلب الأرصدة اللحظية من جدول users في Supabase
    balances = get_user_balances(telegram_id_str)
    balance = float(balances.get('zn_balance', 0.0))
    ad_balance = float(balances.get('ad_balance', 0.0))

    # جلب الحملات النشطة مفلترة وجاهزة مع حالة الإكمال الخاصة بالمستخدم
    result_campaigns = get_active_campaigns(telegram_id_str)

    # جلب أو إنشاء الإعدادات الديناميكية من جدول settings في Supabase فوراً
    config = get_tasks_config()

    return jsonify({
        "success": True,
        "user_id": telegram_id_str,
        "ad_balance": ad_balance,
        "balance": balance,
        "campaigns": result_campaigns,
        "config": config
    }), 200


@tasks_bp.route('/start_task', methods=['POST'])
def start_task_endpoint():
    """
    تسجيل بدء تنفيذ المهمة في السيرفر (جدول task_sessions) لحساب وقت الانتظار الفعلي
    ومنع تخطي المؤقت عبر أدوات المطور أو السكريبتات الخارجية.
    """
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    telegram_id_str = _sanitize_id(telegram_id) or str(telegram_id).strip()
    req = request.get_json(silent=True) or {}
    task_id = str(req.get('taskId') or req.get('task_id') or '').strip()

    if not task_id:
        return jsonify({"success": False, "error": "رقم المهمة مفقود"}), 400

    try:
        session_info = start_user_task(telegram_id_str, task_id)
        return jsonify({
            "success": True,
            "task_id": session_info["task_id"],
            "wait_seconds": session_info["wait_seconds"],
            "started_at": session_info["started_at"],
            "message": "تم بدء احتساب وقت المهمة"
        }), 200
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        print(f"[START TASK ERROR] Error starting task {task_id} for user {telegram_id_str}: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء بدء المهمة"}), 500


@tasks_bp.route('/create_campaign', methods=['POST'])
def create_campaign():
    """إنشاء حملة إعلانية جديدة وتخصيص الميزانية لها بمعاملة ذرية آمنة في Supabase"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    telegram_id_str = _sanitize_id(telegram_id) or str(telegram_id).strip()
    req = request.get_json(silent=True) or {}

    platform = str(req.get('platform', '')).strip()
    url = str(req.get('url', '')).strip()
    description = str(req.get('description', '')).strip()
    raw_reward = req.get('reward') if req.get('reward') is not None else req.get('rewardPerClick')
    raw_users_needed = (
        req.get('users_needed')
        if req.get('users_needed') is not None
        else (req.get('usersNeeded') if req.get('usersNeeded') is not None else req.get('totalCount'))
    )

    if not all([platform, url, description, raw_reward is not None, raw_users_needed is not None]):
        return jsonify({"success": False, "error": "جميع البيانات مطلوبة"}), 400

    if len(url) > 2048 or len(description) > 500:
        return jsonify({"success": False, "error": "الرابط أو الوصف يتجاوز الحد المسموح به"}), 400

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        return jsonify({"success": False, "error": "الرابط يجب أن يكون صحيحاً ويبدأ بـ http:// أو https://"}), 400

    url_lower = url.lower()
    if platform == 'يوتيوب' and not ('youtube.com' in url_lower or 'youtu.be' in url_lower):
        return jsonify({"success": False, "error": "رابط يوتيوب غير صحيح"}), 400
    if platform == 'تيليجرام' and 't.me' not in url_lower:
        return jsonify({"success": False, "error": "رابط تيليجرام غير صحيح"}), 400
    if platform == 'انستغرام' and 'instagram.com' not in url_lower:
        return jsonify({"success": False, "error": "رابط انستغرام غير صحيح"}), 400
    if platform in ('X', 'x') and not ('x.com' in url_lower or 'twitter.com' in url_lower):
        return jsonify({"success": False, "error": "رابط منصة X غير صحيح"}), 400

    # فحص الأمان ومنع الكلمات أو المواقع المخالفة
    if any(bad_word in url_lower for bad_word in FORBIDDEN_KEYWORDS):
        return jsonify({"success": False, "error": "الرابط يحتوي على محتوى مخالف للسياسات وحماية الحسابات"}), 400

    try:
        reward = _parse_safe_float(raw_reward, "قيمة المكافأة")
        users_needed = _parse_safe_int(raw_users_needed, "عدد الأعضاء المطلوب")
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400

    try:
        campaign_data, updated_ad_balance = create_ad_campaign(
            telegram_id_str=telegram_id_str,
            platform=platform,
            url=url,
            description=description,
            reward=reward,
            users_needed=users_needed
        )

        return jsonify({
            "success": True,
            "campaign": campaign_data,
            "new_ad_balance": updated_ad_balance,
            "message": "تم إنشاء الإعلان ونشره بنجاح!"
        }), 200

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        print(f"[TRANSACTION ERROR] Error creating campaign in Supabase: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء حفظ الحملة"}), 500


@tasks_bp.route('/complete_task', methods=['POST'])
def complete_task():
    """تأكيد إكمال المهمة بعد التحقق من المؤقت وإضافة المكافأة إلى رصيد المستخدم بمعاملة ذرية في Supabase"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    telegram_id_str = _sanitize_id(telegram_id) or str(telegram_id).strip()
    req = request.get_json(silent=True) or {}
    task_id = str(req.get('taskId') or req.get('task_id') or '').strip()

    if not task_id:
        return jsonify({"success": False, "error": "رقم المهمة مفقود"}), 400

    try:
        reward_amount, new_balance = complete_user_task(
            telegram_id_str=telegram_id_str,
            task_id=task_id,
            enforce_timer=True
        )

        return jsonify({
            "success": True,
            "reward": reward_amount,
            "new_balance": new_balance,
            "message": "تم إكمال المهمة وإضافة المكافأة"
        }), 200

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        print(f"[TRANSACTION ERROR] Error completing task in Supabase: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء إكمال المهمة"}), 500


@tasks_bp.route('/cancel_campaign', methods=['POST'])
def cancel_campaign():
    """إلغاء الحملة وإرجاع ميزانية الأعضاء المتبقيين لرصيد صاحب الإعلان بمعاملة ذرية آمنة"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    telegram_id_str = _sanitize_id(telegram_id) or str(telegram_id).strip()
    req = request.get_json(silent=True) or {}
    campaign_id = str(req.get('campaignId') or req.get('campaign_id') or req.get('task_id') or '').strip()

    if not campaign_id:
        return jsonify({"success": False, "error": "معرف الحملة مفقود"}), 400

    try:
        refund_amount, new_ad_balance = cancel_ad_campaign(
            telegram_id_str=telegram_id_str,
            campaign_id=campaign_id
        )

        return jsonify({
            "success": True,
            "refund": refund_amount,
            "refunded_amount": refund_amount,
            "new_ad_balance": new_ad_balance,
            "message": "تم إلغاء الحملة وإرجاع الميزانية المتبقية"
        }), 200

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        print(f"[TRANSACTION ERROR] Error canceling campaign in Supabase: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء إلغاء الحملة"}), 500


@tasks_bp.route('/convert_adzn', methods=['POST'])
@tasks_bp.route('/convert_balance', methods=['POST'])
def convert_adzn():
    """تحويل الرصيد الأساسي (ZN) إلى رصيد إعلانات (ad_balance) مع خصم العمولة الديناميكية بمعاملة ذرية في Supabase"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    telegram_id_str = _sanitize_id(telegram_id) or str(telegram_id).strip()
    req = request.get_json(silent=True) or {}

    try:
        amount = _parse_safe_float(req.get('amount'), "المبلغ المراد تحويله")
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400

    try:
        received, fee, fee_percent, new_balance, new_ad_balance = convert_balance_to_ad_balance(
            telegram_id_str=telegram_id_str,
            amount=amount
        )

        return jsonify({
            "success": True,
            "received": received,
            "fee": fee,
            "fee_percent": fee_percent,
            "new_balance": new_balance,
            "new_ad_balance": new_ad_balance,
            "message": "تم تحويل الرصيد بنجاح"
        }), 200

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        print(f"[TRANSACTION ERROR] Error in convert_adzn in Supabase: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء إجراء التحويل في السيرفر"}), 500
