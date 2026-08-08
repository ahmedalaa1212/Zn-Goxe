from firebase_admin import firestore
import database

def modify_user_balance_admin(tg_id, amount, balance_type="balance", operation="add", admin_name="السوبر أدمن"):
    """تعديل رصيد مستخدم (إضافة / خصم / تعيين) بواسطة الأدمن الرئيسي"""
    try:
        if not tg_id:
            return False, "معرف مستخدم غير صالح", 0.0

        db = database.get_db()
        tg_id_str = str(tg_id)
        user_ref = db.collection("users").document(tg_id_str)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return False, "المستخدم غير موجود", 0.0

        user_data = user_doc.to_dict() or {}
        field_key = balance_type if balance_type in ["balance", "ad_balance", "usd_balance"] else "balance"
        current_val = float(user_data.get(field_key, 0.0) or 0.0)
        amount = float(amount)

        if operation == "add":
            new_val = round(current_val + amount, 2)
        elif operation == "subtract":
            new_val = round(max(0.0, current_val - amount), 2)
        elif operation == "set":
            new_val = round(max(0.0, amount), 2)
        else:
            return False, "نوع العملية غير معروف", current_val

        user_ref.update({field_key: new_val})
        database.log_admin_action(admin_name, f"تعديل رصيد {field_key} للمستخدم {tg_id_str}: من {current_val} إلى {new_val}")

        return True, f"تم تعديل رصيد {field_key} بنجاح إلى {new_val}", new_val
    except Exception as e:
        print(f"❌ Error modifying user balance: {e}")
        return False, f"حدث خطأ: {e}", 0.0


def reset_user_account_admin(tg_id, admin_name="السوبر أدمن"):
    """تصفير بيانات وحساب مستخدم بالكامل"""
    try:
        if not tg_id:
            return False, "معرف غير صالح"

        db = database.get_db()
        tg_id_str = str(tg_id)
        user_ref = db.collection("users").document(tg_id_str)

        if not user_ref.get().exists:
            return False, "المستخدم غير موجود"

        user_ref.update({
            "balance": 0.0,
            "ad_balance": 0.0,
            "usd_balance": 0.0,
            "hourly_rate": 0.0,
            "daily_boost_rate": 0.0,
            "upgrades": {},
            "storage_level": 0,
            "completed_tasks": [],
            "total_bets": 0.0,
            "total_wins": 0.0,
            "total_losses": 0.0
        })

        database.log_admin_action(admin_name, f"تصفير حساب المستخدم {tg_id_str} بالكامل")
        return True, f"تم إعادة تصفير حساب المستخدم {tg_id_str} بنجاح!"
    except Exception as e:
        print(f"❌ Error resetting user account: {e}")
        return False, f"حدث خطأ: {e}"


def get_system_global_analytics():
    """تحليلات النظام الكلية للمشروع بأكمله"""
    try:
        db = database.get_db()
        users = db.collection("users").stream()

        total_users = 0
        total_balance_zn = 0.0
        total_ad_balance = 0.0
        banned_users_count = 0

        for u in users:
            total_users += 1
            d = u.to_dict() or {}
            total_balance_zn += float(d.get("balance", 0.0) or 0.0)
            total_ad_balance += float(d.get("ad_balance", 0.0) or 0.0)
            if d.get("banned", False):
                banned_users_count += 1

        game_stats = database.get_game_profit_stats()

        return {
            "total_users": total_users,
            "active_users": total_users - banned_users_count,
            "banned_users": banned_users_count,
            "total_circulating_zn": round(total_balance_zn, 2),
            "total_ad_balance_zn": round(total_ad_balance, 2),
            "game_stats": game_stats
        }
    except Exception as e:
        print(f"❌ Error getting global analytics: {e}")
        return {}
