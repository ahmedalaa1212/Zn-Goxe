import time
from datetime import datetime, timezone
from firebase_admin import firestore
import database

def calculate_farm_earnings(user_data, settings_data=None):
    """حساب الأرباح المتراكمة للتعدين بناءً على معدل الساعات والسعة القصوى"""
    if not user_data:
        return 0.0, 0.0, 100.0

    if settings_data is None:
        settings_data = database.get_game_settings() or {}

    storage_cfg = settings_data.get("storage_config", {})
    storage_lvl = str(user_data.get("storage_level", 0))
    storage_info = storage_cfg.get(storage_lvl, {"capacity": 100.0})

    max_cap = float(storage_info.get("capacity", 100.0)) + float(user_data.get("extra_storage", 0.0) or 0.0)
    hourly_rate = float(user_data.get("hourly_rate", 0.0) or 0.0) + float(user_data.get("daily_boost_rate", 0.0) or 0.0)

    last_claim_str = user_data.get("last_claim_time")
    if not last_claim_str:
        return 0.0, hourly_rate, max_cap

    try:
        if isinstance(last_claim_str, str):
            last_claim = datetime.fromisoformat(last_claim_str.replace("Z", "+00:00"))
        else:
            last_claim = last_claim_str

        now = datetime.now(timezone.utc)
        elapsed_hours = (now - last_claim).total_seconds() / 3600.0
        if elapsed_hours < 0:
            elapsed_hours = 0.0

        accumulated = round(min(max_cap, elapsed_hours * hourly_rate), 4)
        return accumulated, hourly_rate, max_cap
    except Exception as e:
        print(f"❌ Error calculating farm earnings: {e}")
        return 0.0, hourly_rate, max_cap


def claim_farm_reward(tg_id):
    """استلام أرباح التعدين وتحديث وقت الاستلام ورصيد المستخدم"""
    try:
        if not tg_id:
            return False, "معرف مستخدم غير صالح", 0.0, 0.0

        user_data = database.get_user(tg_id)
        if not user_data:
            return False, "المستخدم غير موجود", 0.0, 0.0

        pending_amount, hourly_rate, max_cap = calculate_farm_earnings(user_data)
        if pending_amount <= 0:
            return False, "لا توجد أرباح جاهزة للاستلام حالياً", float(user_data.get("balance", 0.0)), pending_amount

        now_iso = datetime.now(timezone.utc).isoformat()
        new_balance = round(float(user_data.get("balance", 0.0) or 0.0) + pending_amount, 2)

        database.update_user(tg_id, {
            "balance": new_balance,
            "last_claim_time": now_iso
        })

        return True, f"تم استلام {pending_amount} ZN بنجاح!", new_balance, 0.0
    except Exception as e:
        print(f"❌ Error claiming farm reward for {tg_id}: {e}")
        return False, f"حدث خطأ أثناء الاستلام: {e}", 0.0, 0.0


def activate_daily_boost(tg_id, boost_rate=10.0):
    """تفعيل التسريع اليومي لمعدل التعدين"""
    try:
        if not tg_id:
            return False, "معرف غير صالح"
        
        user_data = database.get_user(tg_id)
        if not user_data:
            return False, "المستخدم غير موجود"

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if user_data.get("last_boost_date") == today_str:
            return False, "لقد استخدمت التفعيل اليومي بالفعل اليوم!"

        database.update_user(tg_id, {
            "daily_boost_rate": float(boost_rate),
            "last_boost_date": today_str
        })
        return True, f"تم تفعيل التسريع اليومي (+{boost_rate}/ساعة) بنجاح!"
    except Exception as e:
        print(f"❌ Error activating boost for {tg_id}: {e}")
        return False, f"حدث خطأ: {e}"
