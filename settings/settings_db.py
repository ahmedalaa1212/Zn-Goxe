import os
from datetime import datetime, timezone
from firebase_admin import firestore
import database

def save_admin_settings(settings_dict):
    """حفظ الإعدادات المرسلة من لوحة تحكم الأدمن للعبة شبكة ZN Go والساحة"""
    try:
        if not isinstance(settings_dict, dict):
            return False, "بيانات الإعدادات غير صالحة"

        current_settings = database.get_game_settings() or {}
        zn_cfg = current_settings.get("zn_go_config") or current_settings.get("grid_game_config", {})

        if "zn_go_bot_profit" in settings_dict or "bot_margin" in settings_dict or "target_margin" in settings_dict:
            val = float(settings_dict.get("zn_go_bot_profit", settings_dict.get("bot_margin", settings_dict.get("target_margin", 70))))
            zn_cfg["target_margin"] = val / 100.0 if val > 1.0 else val

        if "zn_go_min_bet" in settings_dict or "min_bet" in settings_dict:
            zn_cfg["min_bet"] = float(settings_dict.get("zn_go_min_bet", settings_dict.get("min_bet", 10)))

        if "default_broken_coins" in settings_dict:
            zn_cfg["default_broken_coins"] = int(settings_dict["default_broken_coins"])

        payload = {"zn_go_config": zn_cfg, "grid_game_config": zn_cfg}

        if "usd_to_zn_rate" in settings_dict:
            payload["usd_to_zn_rate"] = float(settings_dict["usd_to_zn_rate"])

        if (
            "arena_bot_profit" in settings_dict
            or "arena_min_bet" in settings_dict
            or "arena_entry_fee" in settings_dict
            or "arena_prize_pct" in settings_dict
        ):
            arena_cfg = current_settings.get("arena_config", {})
            if "arena_bot_profit" in settings_dict:
                val = float(settings_dict["arena_bot_profit"])
                arena_cfg["target_margin"] = val / 100.0 if val > 1.0 else val
            if "arena_min_bet" in settings_dict or "arena_entry_fee" in settings_dict:
                arena_cfg["entry_fee"] = float(settings_dict.get("arena_min_bet", settings_dict.get("arena_entry_fee", 10)))
            if "arena_prize_pct" in settings_dict:
                val = float(settings_dict["arena_prize_pct"])
                arena_cfg["prize_pool_percentage"] = val / 100.0 if val > 1.0 else val
            payload["arena_config"] = arena_cfg

        return database.update_game_settings(payload)
    except Exception as e:
        print(f"❌ Error in save_admin_settings: {e}")
        return False, f"خطأ أثناء حفظ الإعدادات: {e}"


def get_admin_dashboard_stats():
    """جلب إحصائيات الشاشة الرئيسية للأدمن بسرعة"""
    try:
        profit_stats = database.get_game_profit_stats()
        total_users_count = 0

        db = database.get_db()
        try:
            users_col = db.collection("users")
            count_query = users_col.count()
            res = count_query.get()
            if res and len(res) > 0:
                total_users_count = res[0][0].value
        except Exception:
            total_users_count = 0

        return {
            "status": "success",
            "stats": {
                "total_users": total_users_count,
                "total_bets": profit_stats.get("total_bets", 0.0),
                "total_wins": profit_stats.get("total_wins", 0.0),
                "total_bot_profit": profit_stats.get("total_bot_profit", 0.0),
                "target_margin": profit_stats.get("target_margin", 0.70),
                "target_margin_percent": profit_stats.get("target_margin_percent", 70.0),
                "actual_bot_percent": profit_stats.get("actual_bot_percent", 70.0),
                "actual_user_percent": profit_stats.get("actual_user_percent", 30.0),
            },
        }
    except Exception as e:
        print(f"❌ Error getting admin dashboard stats: {e}")
        return {"status": "error", "message": str(e), "stats": {}}


def is_admin(tg_id):
    """التحقق مما إذا كان المستخدم هو المدير الرئيسي"""
    if not tg_id:
        return False
    admin_id_env = os.environ.get("ADMIN_ID", "")
    if not admin_id_env:
        return False

    admin_ids = [a.strip() for a in admin_id_env.split(",") if a.strip()]
    return str(tg_id) in admin_ids


def is_moderator(tg_id):
    """التحقق مما إذا كان المستخدم مشرفاً معتمداً"""
    if not tg_id:
        return False
    try:
        db = database.get_db()
        doc = db.collection("moderators").document(str(tg_id)).get()
        return doc.exists
    except Exception as e:
        print(f"❌ Error checking moderator status for {tg_id}: {e}")
        return False


def is_admin_or_mod(tg_id):
    """دالة شاملة للتحقق من صلاحية الوصول"""
    if not tg_id:
        return False
    return is_admin(tg_id) or is_moderator(tg_id)


def get_moderators():
    """جلب قائمة المشرفين للوحة التحكم"""
    try:
        db = database.get_db()
        docs = db.collection("moderators").stream()
        mods = []
        for d in docs:
            data = d.to_dict() or {}
            data["id"] = str(d.id)
            mods.append(data)
        return mods
    except Exception as e:
        print(f"❌ Error getting moderators: {e}")
        return []


def add_moderator(mod_id, name, permissions=None, added_by="المدير العام"):
    """إضافة مشرف جديد مع تسجيل العملية"""
    try:
        db = database.get_db()
        mod_ref = db.collection("moderators").document(str(mod_id))
        mod_data = {
            "id": str(mod_id),
            "name": name,
            "permissions": permissions or {},
            "addedBy": added_by,
            "addedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        }
        mod_ref.set(mod_data, merge=True)
        log_admin_action(added_by, f"إضافة المشرف: {name} ({mod_id})")
        return True
    except Exception as e:
        print(f"❌ Error adding moderator: {e}")
        return False


def delete_moderator(mod_id, deleted_by="المدير العام"):
    """حذف مشرف وتجريده من الصلاحيات"""
    try:
        db = database.get_db()
        db.collection("moderators").document(str(mod_id)).delete()
        log_admin_action(deleted_by, f"حذف المشرف ID: {mod_id}")
        return True
    except Exception as e:
        print(f"❌ Error deleting moderator: {e}")
        return False


def get_admin_logs(limit=50):
    """جلب سجل الأنشطة والتحركات الإدارية"""
    try:
        db = database.get_db()
        logs_ref = (
            db.collection("admin_logs")
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        docs = logs_ref.stream()
        logs = []
        for d in docs:
            data = d.to_dict() or {}
            logs.append(data)
        return logs
    except Exception as e:
        print(f"❌ Error getting admin logs: {e}")
        return []


def log_admin_action(admin_name, action):
    """تسجيل حركة جديدة داخل سجل الإدارة المركزية"""
    try:
        db = database.get_db()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        db.collection("admin_logs").add({
            "admin": admin_name or "المدير العام",
            "action": action,
            "timestamp": now_str,
            "created_at": firestore.SERVER_TIMESTAMP,
        })
    except Exception as e:
        print(f"❌ Error logging admin action: {e}")
