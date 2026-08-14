from firebase_admin import firestore
from datetime import datetime, timezone, timedelta
import database

def get_shop_catalog():
    """جلب قائمة مستويات التعدين والتخزين والباقات من إعدادات الفيربيس"""
    try:
        db = database.db
        
        # جلب إعدادات المزرعة التي تحتوي على upgrade_config و storage_capacities
        farm_doc = db.collection('settings').document('farm_settings').get()
        farm_settings = farm_doc.to_dict() if farm_doc.exists else {}

        # جلب إعدادات الباقات المخصصة للمتجر
        shop_doc = db.collection('settings').document('shop_settings').get()
        shop_settings = shop_doc.to_dict() if shop_doc.exists else {}

        mining_cfg = farm_settings.get("upgrade_config", {}) or farm_settings.get("mining_config", {})
        storage_cfg = farm_settings.get("storage_capacities", {}) or farm_settings.get("storage_config", {})
        usdt_pkgs = shop_settings.get("usdt_packages", {})

        return {
            "mining_config": mining_cfg,
            "upgrade_config": mining_cfg,
            "storage_config": storage_cfg,
            "storage_capacities": storage_cfg,
            "usdt_packages": usdt_pkgs
        }
    except Exception as e:
        print(f"❌ Error in get_shop_catalog: {e}")
        settings = database.get_game_settings() or {}
        return {
            "mining_config": settings.get("mining_config", {}),
            "upgrade_config": settings.get("mining_config", {}),
            "storage_config": settings.get("storage_config", {}),
            "storage_capacities": settings.get("storage_config", {}),
            "usdt_packages": settings.get("usdt_packages", {})
        }


def buy_mining_upgrade(tg_id, upgrade_level):
    """شراء ترقية كرت تعدين زيادة إنتاج الساعات من الفيربيس مع الحفاظ على إنتاج المخزن الحالي"""
    try:
        if not tg_id or not upgrade_level:
            return False, "بيانات الترقية غير صالحة", 0.0

        user_data = database.get_user(tg_id)
        if not user_data:
            return False, "المستخدم غير موجود", 0.0

        catalog = get_shop_catalog()
        mining_cfg = catalog.get("mining_config", {})
        lvl_str = str(upgrade_level)

        if lvl_str not in mining_cfg:
            return False, "مستوى الترقية غير موجود", float(user_data.get("balance", 0.0))

        item_info = mining_cfg[lvl_str]
        price = float(item_info.get("cost_zn", item_info.get("price", 0.0)))
        rate_bonus = float(item_info.get("rate_bonus", item_info.get("rate", 0.0)))
        max_purchases = int(item_info.get("max", 15))

        user_upgrades = user_data.get("upgrades", {})
        current_owned = int(user_upgrades.get(f"lvl{lvl_str}", user_upgrades.get(lvl_str, 0)))

        if current_owned >= max_purchases:
            return False, "وصلت للحد الأقصى لشراء هذه الترقية", float(user_data.get("balance", 0.0))

        current_balance = float(user_data.get("balance", 0.0) or 0.0)
        if current_balance < price:
            return False, f"رصيدك غير كافٍ! تحتاج {price:,.0f} ZN", current_balance

        # حساب الرصيد المتراكم بالمخزن لحفظه بدون تصفير
        last_claim_str = user_data.get('last_claim_time')
        now_dt = datetime.now(timezone.utc)
        old_rate = float(user_data.get("hourly_rate", 0.0) or 0.0)
        old_cap = float(user_data.get("max_cap", 100.0) or 100.0)
        
        pending_mined = 0.0
        if last_claim_str:
            try:
                last_claim_dt = datetime.fromisoformat(last_claim_str.replace('Z', '+00:00'))
                time_elapsed = max(0.0, now_dt.timestamp() - last_claim_dt.timestamp())
                pending_mined = min(time_elapsed * (old_rate / 3600.0), old_cap)
            except Exception:
                pending_mined = 0.0

        new_balance = round(current_balance - price, 2)
        new_hourly_rate = round(old_rate + rate_bonus, 2)

        if new_hourly_rate > 0:
            time_needed = pending_mined / (new_hourly_rate / 3600.0)
            new_last_claim = (now_dt - timedelta(seconds=time_needed)).isoformat()
        else:
            new_last_claim = now_dt.isoformat()

        user_upgrades[f"lvl{lvl_str}"] = current_owned + 1

        database.update_user(tg_id, {
            "balance": new_balance,
            "hourly_rate": new_hourly_rate,
            "upgrades": user_upgrades,
            "last_claim_time": new_last_claim
        })

        return True, f"تم شراء الترقية مستوى {lvl_str} بنجاح!", new_balance
    except Exception as e:
        print(f"❌ Error buying mining upgrade: {e}")
        return False, f"حدث خطأ أثناء الشراء: {e}", 0.0


def upgrade_storage_capacity(tg_id):
    """ترقية المخزن إلى المستوى التالي وزيادة السعة التخزينية القصوى دون تصفير العملات"""
    try:
        if not tg_id:
            return False, "معرف غير صالح", 0.0

        user_data = database.get_user(tg_id)
        if not user_data:
            return False, "المستخدم غير موجود", 0.0

        current_lvl = int(user_data.get("storage_level", 0))
        next_lvl_str = str(current_lvl + 1)

        catalog = get_shop_catalog()
        storage_cfg = catalog.get("storage_config", {})

        if next_lvl_str not in storage_cfg:
            return False, "وصلت لأعلى مستوى مخزن حالياً!", float(user_data.get("balance", 0.0))

        next_info = storage_cfg[next_lvl_str]
        price = float(next_info.get("cost_zn", next_info.get("price", 0.0)))
        new_base_capacity = float(next_info.get("capacity", 100.0))
        extra_storage = float(user_data.get("extra_storage", 0.0))

        current_balance = float(user_data.get("balance", 0.0) or 0.0)
        if current_balance < price:
            return False, f"رصيدك غير كافٍ لترقية المخزن! تحتاج {price:,.0f} ZN", current_balance

        # حساب الأرباح الحالية للابتعاد عن التصفير
        last_claim_str = user_data.get('last_claim_time')
        now_dt = datetime.now(timezone.utc)
        hourly_rate = float(user_data.get("hourly_rate", 0.0) or 0.0)
        old_cap = float(user_data.get("max_cap", 100.0) or 100.0)

        pending_mined = 0.0
        if last_claim_str:
            try:
                last_claim_dt = datetime.fromisoformat(last_claim_str.replace('Z', '+00:00'))
                time_elapsed = max(0.0, now_dt.timestamp() - last_claim_dt.timestamp())
                pending_mined = min(time_elapsed * (hourly_rate / 3600.0), old_cap)
            except Exception:
                pending_mined = 0.0

        new_balance = round(current_balance - price, 2)
        new_max_cap = round(new_base_capacity + extra_storage, 2)

        if hourly_rate > 0:
            time_needed = pending_mined / (hourly_rate / 3600.0)
            new_last_claim = (now_dt - timedelta(seconds=time_needed)).isoformat()
        else:
            new_last_claim = now_dt.isoformat()

        database.update_user(tg_id, {
            "balance": new_balance,
            "storage_level": int(next_lvl_str),
            "max_cap": new_max_cap,
            "last_claim_time": new_last_claim
        })

        return True, f"تم ترقية المخزن إلى المستوى {next_lvl_str} (سعة: {new_max_cap}) بنجاح!", new_balance
    except Exception as e:
        print(f"❌ Error upgrading storage: {e}")
        return False, f"حدث خطأ أثناء الترقية: {e}", 0.0
