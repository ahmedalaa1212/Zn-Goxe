from firebase_admin import firestore
from datetime import datetime, timezone, timedelta
import database

def get_shop_catalog():
    """جلب قائمة مستويات التعدين والتخزين والباقات من إعدادات الفيربيس مع تحويل المفاتيح لنصوص"""
    try:
        db = database.db
        
        farm_doc = db.collection('settings').document('farm_settings').get()
        farm_settings = farm_doc.to_dict() if farm_doc.exists else {}

        shop_doc = db.collection('settings').document('shop_settings').get()
        shop_settings = shop_doc.to_dict() if shop_doc.exists else {}

        mining_cfg = farm_settings.get("upgrade_config", {}) or farm_settings.get("mining_config", {})
        storage_cfg = farm_settings.get("storage_capacities", {}) or farm_settings.get("storage_config", {})
        usdt_pkgs = shop_settings.get("usdt_packages", {})

        mining_normalized = {str(k): v for k, v in mining_cfg.items()} if isinstance(mining_cfg, dict) else {}
        storage_normalized = {str(k): v for k, v in storage_cfg.items()} if isinstance(storage_cfg, dict) else {}

        return {
            "mining_config": mining_normalized,
            "upgrade_config": mining_normalized,
            "storage_config": storage_normalized,
            "storage_capacities": storage_normalized,
            "usdt_packages": usdt_pkgs
        }
    except Exception as e:
        print(f"❌ Error in get_shop_catalog: {e}")
        settings = database.get_game_settings() or {}
        mining_cfg = settings.get("mining_config", {})
        storage_cfg = settings.get("storage_config", {})
        return {
            "mining_config": {str(k): v for k, v in mining_cfg.items()} if isinstance(mining_cfg, dict) else {},
            "upgrade_config": {str(k): v for k, v in mining_cfg.items()} if isinstance(mining_cfg, dict) else {},
            "storage_config": {str(k): v for k, v in storage_cfg.items()} if isinstance(storage_cfg, dict) else {},
            "storage_capacities": {str(k): v for k, v in storage_cfg.items()} if isinstance(storage_cfg, dict) else {},
            "usdt_packages": settings.get("usdt_packages", {})
        }


def buy_mining_upgrade(tg_id, upgrade_level):
    """شراء ترقية كرت تعدين مع التحقق المعاملاتي الآمن (Transaction) من الرصيدين (ZN + USD)"""
    try:
        if not tg_id or not upgrade_level:
            return False, "بيانات الترقية غير صالحة", 0.0

        db = database.db
        user_ref = db.collection('users').document(str(tg_id))
        transaction = db.transaction()

        @firestore.transactional
        def _buy_tx(tx, u_ref):
            u_snap = tx.get(u_ref)
            if not u_snap.exists:
                raise Exception("المستخدم غير موجود")

            user_data = u_snap.to_dict() or {}
            catalog = get_shop_catalog()
            mining_cfg = catalog.get("mining_config", {})
            lvl_str = str(upgrade_level)

            if lvl_str not in mining_cfg:
                raise Exception("مستوى الترقية غير موجود")

            item_info = mining_cfg[lvl_str]
            cost_zn = float(item_info.get("cost_zn", item_info.get("price", 0.0)))
            cost_usd = float(item_info.get("cost_usd", item_info.get("usd_cost", 0.0)))
            rate_bonus = float(item_info.get("rate_bonus", item_info.get("rate", 0.0)))
            max_purchases = int(item_info.get("max", 15))

            user_upgrades = user_data.get("upgrades", {})
            if not isinstance(user_upgrades, dict):
                user_upgrades = {}

            current_owned = int(user_upgrades.get(f"lvl{lvl_str}", user_upgrades.get(lvl_str, 0)))

            if current_owned >= max_purchases:
                raise Exception("وصلت للحد الأقصى لشراء هذه الترقية")

            current_balance = float(user_data.get("balance", 0.0) or 0.0)
            current_usd_balance = float(user_data.get("usd_balance", user_data.get("balance_usd", 0.0)) or 0.0)

            if current_balance < cost_zn:
                raise Exception(f"رصيد ZN غير كافٍ! تحتاج {cost_zn:,.0f} ZN")

            if current_usd_balance < cost_usd:
                raise Exception(f"رصيد الدولار غير كافٍ! تحتاج ${cost_usd:.4f}")

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

            new_balance = round(current_balance - cost_zn, 2)
            new_usd_balance = round(current_usd_balance - cost_usd, 4)
            new_hourly_rate = round(old_rate + rate_bonus, 2)

            if new_hourly_rate > 0:
                time_needed = pending_mined / (new_hourly_rate / 3600.0)
                new_last_claim = (now_dt - timedelta(seconds=time_needed)).isoformat()
            else:
                new_last_claim = now_dt.isoformat()

            user_upgrades[f"lvl{lvl_str}"] = current_owned + 1

            tx.update(u_ref, {
                "balance": new_balance,
                "usd_balance": new_usd_balance,
                "hourly_rate": new_hourly_rate,
                "upgrades": user_upgrades,
                "last_claim_time": new_last_claim
            })

            return new_balance, lvl_str

        res_balance, lvl = _buy_tx(transaction, user_ref)
        return True, f"تم شراء الترقية مستوى {lvl} بنجاح!", res_balance

    except Exception as e:
        print(f"❌ Error buying mining upgrade: {e}")
        return False, str(e), 0.0


def upgrade_storage_capacity(tg_id):
    """ترقية المخزن وزيادة السعة بنظام معاملات آمن مع التحقق من الرصيدين"""
    try:
        if not tg_id:
            return False, "معرف غير صالح", 0.0

        db = database.db
        user_ref = db.collection('users').document(str(tg_id))
        transaction = db.transaction()

        @firestore.transactional
        def _storage_tx(tx, u_ref):
            u_snap = tx.get(u_ref)
            if not u_snap.exists:
                raise Exception("المستخدم غير موجود")

            user_data = u_snap.to_dict() or {}
            current_lvl = int(user_data.get("storage_level", 0))
            next_lvl_str = str(current_lvl + 1)

            catalog = get_shop_catalog()
            storage_cfg = catalog.get("storage_config", {})

            if next_lvl_str not in storage_cfg:
                raise Exception("وصلت لأعلى مستوى مخزن حالياً!")

            next_info = storage_cfg[next_lvl_str]
            cost_zn = float(next_info.get("cost_zn", next_info.get("price", 0.0)))
            cost_usd = float(next_info.get("cost_usd", next_info.get("usd_cost", 0.0)))
            new_base_capacity = float(next_info.get("capacity", 100.0))
            extra_storage = float(user_data.get("extra_storage", 0.0))

            current_balance = float(user_data.get("balance", 0.0) or 0.0)
            current_usd_balance = float(user_data.get("usd_balance", user_data.get("balance_usd", 0.0)) or 0.0)

            if current_balance < cost_zn:
                raise Exception(f"رصيدك من ZN غير كافٍ لترقية المخزن! تحتاج {cost_zn:,.0f} ZN")

            if current_usd_balance < cost_usd:
                raise Exception(f"رصيدك من الدولار غير كافٍ لترقية المخزن! تحتاج ${cost_usd:.4f}")

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

            new_balance = round(current_balance - cost_zn, 2)
            new_usd_balance = round(current_usd_balance - cost_usd, 4)
            new_max_cap = round(new_base_capacity + extra_storage, 2)

            if hourly_rate > 0:
                time_needed = pending_mined / (hourly_rate / 3600.0)
                new_last_claim = (now_dt - timedelta(seconds=time_needed)).isoformat()
            else:
                new_last_claim = now_dt.isoformat()

            tx.update(u_ref, {
                "balance": new_balance,
                "usd_balance": new_usd_balance,
                "storage_level": int(next_lvl_str),
                "max_cap": new_max_cap,
                "last_claim_time": new_last_claim
            })

            return new_balance, next_lvl_str, new_max_cap

        res_balance, next_lvl, new_cap = _storage_tx(transaction, user_ref)
        return True, f"تم ترقية المخزن إلى المستوى {next_lvl} (سعة: {new_cap}) بنجاح!", res_balance

    except Exception as e:
        print(f"❌ Error upgrading storage: {e}")
        return False, str(e), 0.0
