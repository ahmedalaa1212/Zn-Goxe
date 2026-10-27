# -*- coding: utf-8 -*-
"""
ملف admin_database.py
يعمل كوسيط موحد (Facade Router) يربط بين جميع موديولات الإدارة وبوت الأدمن
وقاعدة البيانات الرئيسية (Supabase PostgreSQL).
"""

from database import (
    get_db,
    get_db_connection,
    _sanitize_id,
    format_iso,
    get_moderators,
    add_moderator,
    delete_moderator,
    is_admin_or_mod,
    is_admin_exempt,
    log_admin_action
)

from super_admin.super_admin_db import (
    ban_user_db,
    unban_user_db,
    get_banned_users_db,
    get_user_security_details_db,
    get_system_global_analytics,
    add_moderator_db,
    list_moderators_db,
    remove_moderator_db,
    get_admin_logs,
    modify_user_balance_admin,
    reset_user_account_admin,
    get_all_user_ids,
    get_user_by_id,
    log_broadcast_campaign,
    get_latest_broadcast_stats
)


def _get_db():
    """جلب كائن قاعدة البيانات من الملف الرئيسي"""
    return get_db()


# ==================== إعادة توجيه وظائف قسم الإضافات (Addons / Promo Codes) ====================
try:
    from addons.addons_db import (
        create_promo_code,
        redeem_promo_code,
        get_all_promo_codes,
        delete_promo_code,
        toggle_promo_code_status
    )
except ImportError as e:
    print(f"⚠️ Error importing addons_db in admin_database: {e}")


# ==================== إعادة توجيه وظائف محادثات الدعم والإدارة (Admin Chat) ====================
try:
    from admin_chat.admin_chat_db import *
except ImportError:
    pass
